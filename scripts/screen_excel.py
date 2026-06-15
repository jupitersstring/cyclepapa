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
from earnings_model import cluster, config, metrics, prebreakout, quality, screens, valuation

# Sheets in display order (name -> friendly tab title). Leads with the asymmetry
# synthesis, then the cross-screen conviction list, then each contributing screen.
SHEETS = [
    ("asymmetry", "Asymmetric Opps"),
    ("conviction", "Conviction"),
    ("new-reality", "New Reality"),
    ("forensic", "Forensic"),
    ("divergence", "Divergence"),
    ("yoy-unpriced", "YoY Unpriced"),
    ("surprises", "Surprises"),
    ("consensus-lagging", "Consensus Lagging"),
    ("inflecting-positive", "Inflecting+"),
    ("accel-unpriced", "Accel Unpriced"),
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
    df = quality.apply_quality_flags(df)
    # Match pipeline.step_analyze exactly: rank WITHIN region when multi-region,
    # else global. (Previously this path ranked globally and silently disagreed
    # with the pipeline's scored.parquet on every richness/quietness number.)
    gcols = ("region",) if "region" in df.columns and df["region"].nunique() > 1 else None
    df = valuation.add_all_scores(df, group_cols=gcols)
    df = prebreakout.add_prebreakout_score(df, group_cols=gcols)
    df["is_operating"] = valuation.is_operating(df)
    return df


def top5_by_region_sheet(df: pd.DataFrame):
    """Mechanical top-5 per region by RAW asymmetry score (no web overlay) - the
    straight data ranking, region by region."""
    try:
        a = screens.asymmetry(df, top=None)
    except Exception:
        return None
    if a is None or a.empty:
        return None
    a = a.merge(df[["symbol", "marketCap"]], on="symbol", how="left")
    a["mcap_m"] = (a["marketCap"] / 1e6).round(1)
    order = ["US", "EU", "UK", "JP", "CN", "HK", "TW", "KR", "SEA", "ANZ", "CA", "LATAM", "MEA"]
    seen, parts = set(), []
    for reg in order + sorted(set(a["region"].dropna()) - set(order)):
        if reg in seen:
            continue
        seen.add(reg)
        sub = a[a["region"] == reg].sort_values("score", ascending=False).head(5).copy()
        if sub.empty:
            continue
        sub["rank"] = range(1, len(sub) + 1)
        parts.append(sub)
    if not parts:
        return None
    m = pd.concat(parts)
    cols = ["region", "rank", "symbol", "name", "industry", "mcap_m", "score",
            "revenue_growth", "ebitda_growth", "enterpriseToEbitda", "forwardPE", "ret_12m"]
    return m[[c for c in cols if c in m.columns]].round(3)


def web_validated_sheet(df: pd.DataFrame):
    """Lead synthesis sheet: web-research verdicts (data/web_verdicts.csv) joined
    to the live quant scores/metrics, ordered KEEP -> SPECULATIVE -> REJECT, so
    the workbook shows *why* a high-scoring screen name was kept or killed once
    stress-tested against current public information."""
    vpath = config.DATA_DIR / "web_verdicts.csv"
    if not vpath.exists():
        return None
    v = pd.read_csv(vpath)
    # The relevant "score" is the asymmetry-screen score (scored.parquet has no
    # generic score column); merge it in so kept names show their screen rank.
    try:
        asc = screens.asymmetry(df, top=None)[["symbol", "score"]]
    except Exception:
        asc = pd.DataFrame({"symbol": [], "score": []})
    m = v.merge(asc, on="symbol", how="left")
    mcols = [c for c in ["name", "enterpriseToEbitda", "forwardPE", "ret_12m"]
             if c in df.columns]
    m = m.merge(df[["symbol"] + mcols], on="symbol", how="left")
    try:
        uni = pd.read_parquet(config.UNIVERSE_PATH)
        m = m.merge(uni[["symbol", "country", "industry"]], on="symbol", how="left")
    except (OSError, KeyError):
        pass
    order = {"KEEP": 0, "SPECULATIVE": 1, "REJECT": 2}
    m["_o"] = m["verdict"].map(order).fillna(3)
    m["rank"] = pd.to_numeric(m["rank"], errors="coerce")
    keys = [k for k in ["_o", "rank", "score"] if k in m.columns]
    m = m.sort_values(keys, ascending=[True] * len(keys), na_position="last")
    cols = ["verdict", "rank", "symbol", "name", "country", "industry", "score",
            "enterpriseToEbitda", "forwardPE", "ret_12m", "reason"]
    return m[[c for c in cols if c in m.columns]].round(3)


def _fmt_sheet(writer, sheet, df, hdr, pct_fmt, f2_fmt):
    ws = writer.sheets[sheet]
    pct_cols = {"score", "behaviour_change", "reaction", "surprise_beat_rate", "rev_up_frac",
                "valuation_richness", "inflection_score", "dormancy", "cheapness", "consensus_gap_pct",
                "gross_margin_delta", "ebitda_margin_slope"}
    for i, c in enumerate(df.columns):
        ws.write(0, i, c, hdr)
        if c == "reason":
            ws.set_column(i, i, 95)
        elif c in ("name", "industry"):
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
    wv = web_validated_sheet(df)
    if wv is not None and not wv.empty:
        wv.to_excel(writer, sheet_name="Web-Validated", index=False, startrow=1, header=False)
        _fmt_sheet(writer, "Web-Validated", wv, hdr, pct_fmt, f2_fmt)
        written.append(f"Web-Validated({len(wv)})")
    t5 = top5_by_region_sheet(df)
    if t5 is not None and not t5.empty:
        t5.to_excel(writer, sheet_name="Top5 by Region", index=False, startrow=1, header=False)
        _fmt_sheet(writer, "Top5 by Region", t5, hdr, pct_fmt, f2_fmt)
        written.append(f"Top5 by Region({len(t5)})")
    # BEST BY ARCHETYPE — top 3 names in each broad archetype, one compact table.
    arche = [("asymmetry", "Unpriced inflection"), ("accel-unpriced", "Earnings acceleration"),
             ("yoy-unpriced", "YoY growth unpriced"), ("inflecting-positive", "Positive inflection"),
             ("surprises", "Earnings surprises"), ("consensus-lagging", "Consensus lagging"),
             ("new-reality", "New reality / re-rating"), ("divergence", "Price-fundamental divergence"),
             ("forensic", "Forensic value"), ("conviction", "Multi-screen conviction")]
    brows = []
    for key, label in arche:
        fn = screens.SCREENS.get(key)
        if fn is None:
            continue
        try:
            r = fn(df, top=3)
        except Exception:
            continue
        if r is None or r.empty:
            continue
        t = r[["symbol"]].copy()
        t["score"] = r["score"] if "score" in r.columns else pd.NA
        t.insert(0, "rank", range(1, len(t) + 1))
        t.insert(0, "archetype", label)
        brows.append(t)
    if brows:
        disp = df[[c for c in ["symbol", "name", "region", "industry", "marketCap",
                               "revenue_growth", "ebitda_growth", "enterpriseToEbitda",
                               "forwardPE", "ret_12m"] if c in df.columns]]
        best = pd.concat(brows, ignore_index=True).merge(disp, on="symbol", how="left")
        if "marketCap" in best.columns:
            best["mcap_m"] = (best["marketCap"] / 1e6).round(1)
        cols = ["archetype", "rank", "symbol", "name", "region", "industry", "mcap_m", "score",
                "revenue_growth", "ebitda_growth", "enterpriseToEbitda", "forwardPE", "ret_12m"]
        best = best[[c for c in cols if c in best.columns]].round(3)
        best.to_excel(writer, sheet_name="Best by Archetype", index=False, startrow=1, header=False)
        _fmt_sheet(writer, "Best by Archetype", best, hdr, pct_fmt, f2_fmt)
        written.append(f"Best by Archetype({len(best)})")
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

    # Behavioural clusters across the ENTIRE universe (every name with data, not
    # just operating companies) — a profile sheet (the k centroids) + per-name
    # assignments. is_operating is kept as a column so you can still filter.
    try:
        ck = cluster.run_kmeans(df, k=config.DEFAULT_CLUSTERS)
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
        # Per-name assignments (entire universe).
        acols = [c for c in ["symbol", "name", "region", "industry", "size_bucket", "is_operating",
                             "cluster", "cluster_label", "revenue_growth", "ebitda_growth",
                             "earnings_growth", "gross_margin_delta", "ebitda_margin_slope", "ret_24m"]
                 if c in lab.columns]
        names = lab[acols].sort_values(["cluster", "symbol"]).round(3)
        names.to_excel(writer, sheet_name="Clusters", index=False, startrow=1, header=False)
        _fmt_sheet(writer, "Clusters", names, hdr, pct_fmt, f2_fmt)
        written.append(f"Clusters({len(names)} of {len(df)} universe)")
    except Exception as e:
        print(f"  skip Clusters: {e}")

    # Analyze "views" the pipeline writes to cache/*.csv — the special-situation
    # archetypes beyond the headline screens.
    for fname, title in [("prebreakout.csv", "Pre-Breakout"),
                         ("valuation_gap.csv", "Valuation Gap"),
                         ("inflecting_lagging.csv", "Inflecting+Lagging"),
                         ("case_studies.csv", "Case Studies")]:
        fp = config.CACHE_DIR / fname
        if not fp.exists():
            continue
        try:
            v = pd.read_csv(fp).round(3)
        except Exception as e:
            print(f"  skip {title}: {e}"); continue
        if v.empty:
            continue
        v.to_excel(writer, sheet_name=title[:31], index=False, startrow=1, header=False)
        _fmt_sheet(writer, title[:31], v, hdr, pct_fmt, f2_fmt)
        written.append(f"{title}({len(v)})")

    # ALL MEASURES — every name with data x every measure column (the full table
    # behind every screen). Also dropped to data/all_measures.csv (durable).
    ident = [c for c in ["region", "symbol", "name", "sector", "industry", "size_bucket",
                         "is_operating", "secular_cyclical", "marketCap"] if c in df.columns]
    rest = [c for c in df.columns if c not in ident and c not in ("payload_fp", "asof", "fetch_ok")]
    allm = df[ident + rest].copy()
    for c in allm.columns:
        if allm[c].dtype.kind in "fc":
            allm[c] = allm[c].round(4)
    allm = allm.sort_values([c for c in ["region", "symbol"] if c in allm.columns])
    try:
        allm.to_csv(config.DATA_DIR / "all_measures.csv.gz", index=False,
                    compression={"method": "gzip", "mtime": 0})  # deterministic -> no git churn
    except OSError:
        pass

    # MEASURES DICTIONARY — one-line definition per measure family.
    DICT = [
        ("Measure", "Definition"),
        ("score", "Per-screen composite (0-1), ranked within region; each screen tab has its own."),
        ("revenue/ebitda/earnings_growth", "YoY growth of the latest annual figure."),
        ("*_accel / *_accel_abs", "Change in the growth rate vs the prior period (inflection)."),
        ("*_cagr", "Multi-year compound annual growth rate of the line."),
        ("*_q_yoy / *_q_accel", "Latest-quarter YoY growth and its acceleration."),
        ("rev_up_frac", "Fraction of recent periods with rising revenue (consistency)."),
        ("operating_leverage", "EBITDA growth / revenue growth (>1 = margin expansion)."),
        ("gross/ebitda_margin (+_delta/_delta3/_slope)", "Margin level and its change vs 1/3 periods / fitted trend."),
        ("surprise_robust", "Scale-stable EPS-surprise stat (winsorized per config.SURPRISE_WINSOR)."),
        ("surprise_beat_rate", "Fraction of recent quarters that beat consensus."),
        ("surprise_trend / _recency / _quality", "Direction, recency-weighting, quality of the surprise series."),
        ("consensus_gap_pct", "Gap between fundamentals-implied and analyst-implied value."),
        ("enterpriseToEbitda/forwardPE/priceToSales/priceToBook/pegRatio", "Raw valuation multiples."),
        ("cheapness / valuation_richness", "Region-ranked valuation cheapness, and its inverse."),
        ("inflection_score / inflection_flag_score", "Strength of the earnings-inflection signal."),
        ("ret_1m..ret_36m", "Trailing total returns per window (|ret|>900% nulled as split artifacts)."),
        ("max_drawdown / range_position", "Drawdown from peak; position within the 52-week range."),
        ("trend_slope / realized_vol", "Fitted price-trend slope; realized volatility."),
        ("dormancy / price_quiet", "How quiet/forgotten the price action is (low = dormant)."),
        ("gap_score", "Composite 'cheap + improving + ignored' signal."),
        ("basing_tightness / prebreakout_score / breaking_out", "Base tightness and pre-breakout technical setup."),
        ("*_turned_positive/_improving/_trough_up/_inflecting", "Boolean inflection flags per line."),
        ("secular_cyclical", "Classified as secular grower vs cyclical."),
        ("dup_payload", "Yahoo served identical statements under another ticker (quality flag)."),
        ("is_operating", "Passed the operating-company filter (excludes funds/shells/non-operating)."),
    ]
    dws = wb.add_worksheet("Measures Dictionary")
    dws.set_column(0, 0, 46); dws.set_column(1, 1, 95)
    for r, (k, v) in enumerate(DICT):
        dws.write(r, 0, k, hdr if r == 0 else None)
        dws.write(r, 1, v, hdr if r == 0 else None)
    written.append(f"Measures Dictionary({len(DICT) - 1})")

    # Provenance — data vintage + what the quality guards removed, so the sheet
    # is self-documenting about freshness and filtering.
    try:
        prov = wb.add_worksheet("Provenance")
        prov.set_column(0, 0, 26); prov.set_column(1, 1, 60)
        man = {}
        mpath = config.DATA_DIR / "manifest.json"
        if mpath.exists():
            man = json.loads(mpath.read_text())
        n_dup = int(df.get("dup_payload", pd.Series(dtype=bool)).fillna(False).sum())
        n_surp = int((df.get("surprise_n", pd.Series(dtype=float)).fillna(0) > 0).sum())
        prows = [
            ("Field", "Value"),
            ("Generated (UTC)", date.today().isoformat()),
            ("Data as-of", str(man.get("data_asof", "see cache"))[:10]),
            ("Snapshot git sha", man.get("git_sha", "n/a")),
            ("Schema version", str(man.get("schema_version", "n/a"))),
            ("Universe rows (with data)", str(len(df))),
            ("Names with EPS surprises", str(n_surp)),
            ("Duplicate-payload rows removed", f"{n_dup} (Yahoo serving identical statements under another ticker)"),
            ("Return outliers quarantined", "|ret|>900% nulled as split artifacts (see earnings_model.quality)"),
            ("Ranking", "within-region (a multiple only means something vs same-market peers)"),
            ("Source", "yfinance + financedatabase. Research scaffold, not investment advice."),
        ]
        bold0 = wb.add_format({"bold": True, "valign": "top"})
        wrap0 = wb.add_format({"text_wrap": True, "valign": "top"})
        for r, (a, b) in enumerate(prows):
            prov.write(r, 0, a, hdr if r == 0 else bold0)
            prov.write(r, 1, b, hdr if r == 0 else wrap0)
    except Exception as e:
        print(f"  skip Provenance: {e}")

    # Legend
    leg = wb.add_worksheet("Legend")
    leg.set_column(0, 0, 22); leg.set_column(1, 1, 95)
    rows = [
        ("Sheet / field", "Meaning"),
        ("Asymmetric Opps", "THE SYNTHESIS: inflecting business + cheap + dormant price + surprise/consensus catalyst + margin trend; gated to require genuine improvement. 'secular_cyclical' tags the driver. Duplicates + split-artifact returns removed upstream."),
        ("Conviction", "Names passing >=2 of yoy-unpriced/divergence/forensic/new-reality/consensus-lagging. n_screens + in_* show which."),
        ("New Reality", "Serial EPS beats GATED on rising revenue+EBITDA (excludes beating-a-falling-bar), price dormant."),
        ("Forensic", "Revenue rising >=2/3yrs, EBITDA positive throughout AND margin expanding, no one-off lump."),
        ("Divergence", "Biggest fundamental behaviour change vs least price reaction (cheapness-independent)."),
        ("YoY Unpriced", "Annual growth accel/inflection that is cheap and price-dormant."),
        ("Surprises", "Greatest EPS surprises vs consensus: recent + cumulative (cum8) + consistency (beat_rate/streak)."),
        ("Consensus Lagging", "Forward EPS below trailing reality while fundamentals grow (>=5 analysts, ex-REIT). 'confirmation' = beats (surprise-confirmed, US/UK/EU/CA/ANZ) or fundamentals (earnings-growth-confirmed, no-surprise markets e.g. Japan)."),
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
