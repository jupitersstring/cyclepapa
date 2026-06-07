"""Generate a formatted multi-sheet Excel workbook of every screen + the
cross-screen *conviction* synthesis.

    python scripts/screen_excel.py                       # from cache/scored.parquet
    python scripts/screen_excel.py --from-cache          # rebuild scored from cache/raw
    python scripts/screen_excel.py --top 60 --out wb.xlsx

Sheet order leads with Conviction (multi-screen agreement), then each individual
screen, then a Legend. Score columns get a red->green colour scale; panes are
frozen and auto-filtered.
"""
from __future__ import annotations

import argparse
import glob
import json
import sys
import warnings
from datetime import date
from pathlib import Path

import pandas as pd

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from earnings_model import cluster, config, metrics, prebreakout, screens, valuation

# Sheets in display order (name -> friendly tab title).
SHEETS = [
    ("conviction", "Conviction"),
    ("new-reality", "New Reality"),
    ("forensic", "Forensic"),
    ("divergence", "Divergence"),
    ("yoy-unpriced", "YoY Unpriced"),
    ("asymmetry", "Asymmetry"),
    ("surprises", "Surprises"),
    ("consensus-lagging", "Consensus Lagging"),
    ("inflecting-positive", "Inflecting+"),
    ("prebreakout-na", None),  # placeholder, ignored
]

_NUMERIC = ["forwardPE", "trailingPE", "enterpriseToEbitda", "priceToSalesTrailing12Months",
            "priceToBook", "marketCap", "enterpriseValue", "trailingEps", "forwardEps",
            "analyst_coverage"]


def build_scored_from_cache() -> pd.DataFrame:
    """Rebuild the scored table directly from cache/raw (always-current metrics)."""
    uni = pd.read_parquet(config.UNIVERSE_PATH)
    rows = []
    for p in glob.glob(str(config.RAW_CACHE_DIR / "*.json")):
        try:
            r = json.loads(Path(p).read_text())
        except (json.JSONDecodeError, OSError):
            continue
        if not r.get("fetch_ok"):
            continue
        m = metrics.compute_metrics(r)
        for s, d in {"sector": "yf_sector", "industry": "yf_industry", "currency": "yf_currency"}.items():
            if s in m:
                m[d] = m.pop(s)
        rows.append(m)
    df = pd.DataFrame(rows)
    idc = [c for c in ["symbol", "name", "sector", "industry_group", "industry", "size_bucket", "region"]
           if c in uni.columns]
    df = df.merge(uni[idc], on="symbol", how="left")
    for c in _NUMERIC:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.replace([float("inf"), float("-inf")], pd.NA)
    df = valuation.add_all_scores(df)
    df = prebreakout.add_prebreakout_score(df)
    df["is_operating"] = valuation.is_operating(df)
    return df


def _fmt_sheet(writer, sheet, df, hdr, pct_fmt, f2_fmt):
    ws = writer.sheets[sheet]
    pct_cols = {"score", "behaviour_change", "reaction", "surprise_beat_rate", "rev_up_frac",
                "valuation_richness", "inflection_score", "dormancy", "cheapness", "consensus_gap_pct",
                "gross_margin_delta", "ebitda_margin_slope"}
    for i, c in enumerate(df.columns):
        ws.write(0, i, c, hdr)
        if c in ("name", "industry"):
            ws.set_column(i, i, 28)
        elif c in pct_cols:
            ws.set_column(i, i, 12, pct_fmt)
        elif df[c].dtype.kind in "fc":
            ws.set_column(i, i, 12, f2_fmt)
        else:
            ws.set_column(i, i, 12)
    ws.freeze_panes(1, 0)
    ws.autofilter(0, 0, max(len(df), 1), len(df.columns) - 1)
    if "score" in df.columns:
        si = list(df.columns).index("score")
        ws.conditional_format(1, si, len(df), si,
                              {"type": "3_color_scale", "min_color": "#F8696B",
                               "mid_color": "#FFEB84", "max_color": "#63BE7B"})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from-cache", action="store_true", help="rebuild scored from cache/raw")
    ap.add_argument("--in", dest="inp", default=str(config.CACHE_DIR / "scored.parquet"))
    ap.add_argument("--out", default="cross_screen_workbook.xlsx")
    ap.add_argument("--top", type=int, default=50)
    args = ap.parse_args()

    df = build_scored_from_cache() if args.from_cache else pd.read_parquet(args.inp)
    print(f"scored rows: {len(df)} | operating: {int(df.get('is_operating', pd.Series()).sum())}")

    writer = pd.ExcelWriter(args.out, engine="xlsxwriter")
    wb = writer.book
    hdr = wb.add_format({"bold": True, "bg_color": "#1F4E78", "font_color": "white",
                         "border": 1, "text_wrap": True, "valign": "top"})
    pct_fmt = wb.add_format({"num_format": "0.00"})
    f2_fmt = wb.add_format({"num_format": "0.00"})

    written = []
    for name, title in SHEETS:
        fn = screens.SCREENS.get(name)
        if fn is None:
            continue
        try:
            res = fn(df, top=args.top).round(3)
        except Exception as e:
            print(f"  skip {title}: {e}")
            continue
        if res.empty:
            print(f"  {title}: empty")
            continue
        res.to_excel(writer, sheet_name=title[:31], index=False, startrow=1, header=False)
        _fmt_sheet(writer, title[:31], res, hdr, pct_fmt, f2_fmt)
        written.append(f"{title}({len(res)})")

    # Behavioural clusters: a profile sheet (the k centroids) + per-name assignments.
    try:
        op = df[df.get("is_operating", True)].copy() if "is_operating" in df.columns else df
        ck = cluster.run_kmeans(op, k=config.DEFAULT_CLUSTERS)
        lab = ck["labeled"].dropna(subset=["cluster"]).copy()
        # Profile sheet with region mix + median valuation/return per cluster.
        prof = ck["profile"].copy()
        comp = lab.groupby("cluster").agg(
            top_region=("region", lambda x: x.value_counts().index[0] if len(x) else ""),
            ret_24m=("ret_24m", "median"),
            ev_ebitda=("enterpriseToEbitda", lambda x: x[x > 0].median()),
        ).reset_index()
        prof = prof.merge(comp, on="cluster", how="left").sort_values("revenue_growth", ascending=False).round(3)
        prof.to_excel(writer, sheet_name="Cluster Profile", index=False, startrow=1, header=False)
        _fmt_sheet(writer, "Cluster Profile", prof, hdr, pct_fmt, f2_fmt)
        written.append(f"Cluster Profile({len(prof)})")
        # Per-name assignments.
        acols = [c for c in ["symbol", "name", "region", "industry", "size_bucket", "cluster",
                             "cluster_label", "revenue_growth", "ebitda_growth", "earnings_growth",
                             "gross_margin_delta", "ebitda_margin_slope", "ret_24m"] if c in lab.columns]
        names = lab[acols].sort_values(["cluster", "symbol"]).round(3)
        names.to_excel(writer, sheet_name="Clusters", index=False, startrow=1, header=False)
        _fmt_sheet(writer, "Clusters", names, hdr, pct_fmt, f2_fmt)
        written.append(f"Clusters({len(names)})")
    except Exception as e:
        print(f"  skip Clusters: {e}")

    # Legend
    leg = wb.add_worksheet("Legend")
    leg.set_column(0, 0, 22); leg.set_column(1, 1, 95)
    rows = [
        ("Sheet / field", "Meaning"),
        ("Conviction", "Names passing >=2 of yoy-unpriced/divergence/forensic/new-reality/consensus-lagging. n_screens + in_* show which."),
        ("New Reality", "Serial EPS beats GATED on rising revenue+EBITDA (excludes beating-a-falling-bar), price dormant."),
        ("Forensic", "Revenue rising >=2/3yrs, EBITDA positive throughout AND margin expanding, no one-off lump."),
        ("Divergence", "Biggest fundamental behaviour change vs least price reaction (cheapness-independent)."),
        ("YoY Unpriced", "Annual growth accel/inflection that is cheap and price-dormant."),
        ("Surprises", "Greatest EPS surprises vs consensus: recent + cumulative (cum8) + consistency (beat_rate/streak)."),
        ("Consensus Lagging", "Forward EPS below trailing reality while fundamentals grow and company is beating (>=5 analysts)."),
        ("Cluster Profile", f"K-means behavioural clusters (k={config.DEFAULT_CLUSTERS}); each row = a centroid, labelled growth-band x acceleration x margin-trend."),
        ("Clusters", "Every operating name with its behavioural cluster + label (rank-transformed growth/accel/margin/momentum features)."),
        ("score", "Each screen's composite rank (0-1); colour-scaled."),
        ("ret_12m / ret_24m", "Trailing price return; low/negative = market hasn't reacted."),
        ("surprise_cum8", "Cumulative EPS surprise gap, last 8 quarters (%)."),
        ("consensus_gap_pct", "(forwardEps - trailingEps)/|trailingEps|; negative = consensus below reality."),
        ("Universe", "Operating companies only; UK/US/EU + rest-of-world primary listings (ex-India, ex-Russia)."),
        ("Generated", f"{date.today().isoformat()} via yfinance + financedatabase. Research scaffold, not advice."),
    ]
    bold = wb.add_format({"bold": True, "valign": "top"})
    wrap = wb.add_format({"text_wrap": True, "valign": "top"})
    for r, (a, b) in enumerate(rows):
        leg.write(r, 0, a, hdr if r == 0 else bold)
        leg.write(r, 1, b, hdr if r == 0 else wrap)

    writer.close()
    print(f"WROTE {args.out}: {', '.join(written)}")


if __name__ == "__main__":
    main()
