"""
Unified Q-Roque-Darvas-Volume-FailedBearish-Fundamentals composite scorer.

Inputs (all optional - missing files are skipped):
  - momentum_rank csv for a universe (Roque + weekly + Darvas + relative SPY)
  - volume_screen csv for the same tickers (COILED/POC/ATR/BB compression)
  - failed_bearish CSVs (any number of files) - any membership = bonus
  - yfinance fundamentals fetch for top N rows (optional, slow)

Final composite stacks every measure onto one number per ticker so the
ranking reflects every screen we've ever defined.
"""

import argparse
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf


def load_with_default(path, **kw):
    try:
        return pd.read_csv(path, index_col=0, **kw)
    except Exception:
        return None


def fundamentals_score(info):
    """0..15 score from fundamentals; missing data -> 0."""
    s = 0
    pb = info.get("priceToBook")
    if pb and 0 < pb < 1.5: s += 5
    elif pb and 1.5 <= pb < 3: s += 3
    elif pb and 3 <= pb < 6: s += 1
    ev = info.get("enterpriseToEbitda")
    if ev and 0 < ev < 8: s += 4
    elif ev and 8 <= ev < 15: s += 2
    roe = info.get("returnOnEquity")
    if roe and roe > 0.20: s += 3
    elif roe and roe > 0.10: s += 2
    elif roe and roe > 0.05: s += 1
    margin = info.get("profitMargins")
    if margin and margin > 0.15: s += 2
    elif margin and margin > 0.05: s += 1
    growth = info.get("revenueGrowth")
    if growth and growth > 0.15: s += 1
    return s


def fetch_fundamentals(tickers, sleep=1.0, max_retries=3):
    rows = []
    for i, t in enumerate(tickers, 1):
        if i % 5 == 0:
            print(f"  fund {i}/{len(tickers)}")
        info = {}
        for attempt in range(max_retries):
            try:
                info = yf.Ticker(t).info or {}
                break
            except Exception as e:
                if "rate" in str(e).lower() or "429" in str(e):
                    time.sleep(sleep * (2 ** attempt) + 2)
                else:
                    break
        rows.append({
            "Ticker": t,
            "priceToBook": info.get("priceToBook"),
            "trailingPE": info.get("trailingPE"),
            "enterpriseToEbitda": info.get("enterpriseToEbitda"),
            "returnOnEquity": info.get("returnOnEquity"),
            "debtToEquity": info.get("debtToEquity"),
            "profitMargins": info.get("profitMargins"),
            "revenueGrowth": info.get("revenueGrowth"),
            "fund_score": fundamentals_score(info),
        })
        time.sleep(sleep)
    return pd.DataFrame(rows).set_index("Ticker")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--momentum-csv", required=True)
    p.add_argument("--volume-csv", default=None)
    p.add_argument("--failed-bearish-csvs", nargs="*", default=[])
    p.add_argument("--with-fundamentals", action="store_true",
                   help="Pull yfinance fundamentals (slow due to rate limits).")
    p.add_argument("--fund-top-n", type=int, default=20)
    p.add_argument("--top", type=int, default=50)
    p.add_argument("--cap-filter", default=None,
                   help="Filter to market caps via financedatabase (e.g. small,mid).")
    p.add_argument("--out", default=None)
    args = p.parse_args()

    mom = pd.read_csv(args.momentum_csv, index_col=0)
    print(f"Loaded {len(mom)} momentum rows from {args.momentum_csv}")

    if args.cap_filter:
        import financedatabase as fd
        caps = [c.strip().title() + " Cap" if not c.strip().title().endswith("Cap") else c.strip().title()
                for c in args.cap_filter.split(",")]
        caps = [c.replace("Cap Cap", "Cap") for c in caps]
        eq = fd.Equities()
        frames = [eq.select(country="United States", market_cap=c).assign(_cap=c) for c in caps]
        cap_df = pd.concat(frames)
        cap_df = cap_df[cap_df["exchange"].isin({"NYQ", "NMS", "NGM", "NCM", "ASE", "BATS"})]
        mom = mom[mom.index.isin(cap_df.index)].join(cap_df[["_cap"]], how="left")
        print(f"  after {args.cap_filter} filter: {len(mom)}")

    # ---- Layer volume_screen ----
    if args.volume_csv:
        vol = load_with_default(args.volume_csv)
        if vol is not None:
            vol_cols = ["atr_compression", "bb_compression", "vol_stepup_2w",
                        "vol_stepup_4w", "range_pct_2w", "poc_13w_dist_pct", "tags"]
            keep = [c for c in vol_cols if c in vol.columns]
            overlap = [c for c in keep if c in mom.columns]
            if overlap:
                mom = mom.drop(columns=overlap)
            mom = mom.join(vol[keep], how="left")
            mom["tags"] = mom["tags"].fillna("")
            mom["n_coil_tags"] = mom["tags"].str.count("COILED")
            mom["n_poc_tags"] = mom["tags"].str.count("POC")
            mom["n_value_tags"] = mom["tags"].str.count("AT_VALUE")
            mom["n_strong_vol"] = mom["tags"].str.count("STRONG_VOLUME")
            mom["n_breakout_fire"] = mom["tags"].str.count("BREAKOUT_FIRING")
            print(f"  volume tags joined")

    # ---- Layer failed-bearish memberships ----
    fb_sets = {}
    for path in args.failed_bearish_csvs:
        try:
            f = pd.read_csv(path, index_col=0)
            fb_sets[Path(path).stem] = set(f.index)
            print(f"  fb {Path(path).stem}: {len(f)}")
        except Exception as e:
            print(f"  fb {path} err: {e}")
    if fb_sets:
        mom["fb_hit_count"] = mom.index.to_series().apply(
            lambda t: sum(1 for s in fb_sets.values() if t in s))
        mom["fb_lists"] = mom.index.to_series().apply(
            lambda t: ",".join(k for k, s in fb_sets.items() if t in s))
    else:
        mom["fb_hit_count"] = 0
        mom["fb_lists"] = ""

    # ---- Compute composite ranking BEFORE fundamentals so we can pick top N ----
    def col(c, default=0):
        return mom[c].fillna(default) if c in mom.columns else default
    def bcol(c):
        return mom[c].fillna(False).astype(int) if c in mom.columns else 0

    mom["composite_pre"] = (
        col("roque_score") * 1.5
        + bcol("prebreakout_w") * 8
        + bcol("roque_big_base") * 10
        + bcol("long_base") * 4
        + bcol("very_long_base") * 6
        + bcol("darvas_tight") * 5
        + bcol("base_on_base") * 4
        + bcol("near_box_top") * 6
        + bcol("box_breakout") * 5
        + bcol("vol_drying") * 4
        + bcol("monthly_uptrend") * 3
        + bcol("uptrend_w") * 3
        + bcol("macd_above_signal") * 2
        + bcol("rel_macd_above_signal") * 3
        + col("rel_return_6m_pct").clip(0, 100) / 5
        + col("n_coil_tags") * 3
        + col("n_poc_tags") * 4
        + col("n_value_tags") * 3
        + col("n_strong_vol") * 2
        + col("fb_hit_count") * 5
    )

    # ---- Fundamentals (optional, top N only) ----
    if args.with_fundamentals:
        top_for_fund = mom.sort_values("composite_pre", ascending=False).head(args.fund_top_n)
        print(f"Fetching fundamentals for top {len(top_for_fund)}...")
        fund = fetch_fundamentals(list(top_for_fund.index))
        overlap = [c for c in fund.columns if c in mom.columns]
        if overlap:
            mom = mom.drop(columns=overlap)
        mom = mom.join(fund, how="left")
        mom["fund_score"] = mom["fund_score"].fillna(0)
    else:
        mom["fund_score"] = 0
        for c in ["priceToBook", "enterpriseToEbitda", "returnOnEquity",
                  "debtToEquity", "profitMargins", "revenueGrowth", "trailingPE"]:
            if c not in mom.columns:
                mom[c] = None

    mom["composite_final"] = mom["composite_pre"] + mom["fund_score"] * 2

    out_path = args.out or args.momentum_csv.replace(".csv", "_unified.csv")
    mom.to_csv(out_path)
    print(f"Saved: {out_path}")

    show_cols = ["name", "sector", "_cap", "last_close",
                 "mom_3m", "mom_6m", "rel_return_6m_pct",
                 "box_length_weeks", "box_height_pct", "pos_in_box_pct",
                 "dist_from_box_top_pct", "vol_drying_ratio",
                 "atr_compression", "bb_compression", "vol_stepup_2w",
                 "priceToBook", "enterpriseToEbitda", "returnOnEquity",
                 "fb_hit_count", "fb_lists",
                 "prebreakout_w", "roque_big_base", "long_base", "darvas_tight",
                 "tags", "roque_score", "fund_score",
                 "composite_pre", "composite_final"]
    show_cols = [c for c in show_cols if c in mom.columns]
    top = mom.sort_values("composite_final", ascending=False).head(args.top)
    with pd.option_context("display.max_columns", None, "display.width", 320,
                            "display.float_format", "{:.2f}".format):
        print(f"\n=== Top {args.top} unified composite (Roque + Darvas + Volume + POC + FailedBearish + Fundamentals) ===")
        print(top[show_cols].to_string())


if __name__ == "__main__":
    main()
