"""Merge authoritative Yahoo fundamentals (ticker_yf.csv) into the master.

ticker_yf.py pulls Yahoo's own mcap / EV / EV-EBITDA / P/B / P/E and a
broad fundamentals set via the cookie/crumb quoteSummary endpoint — for
US *and* foreign tickers, which is the gap SEC XBRL can't reach.

Policy
------
Yahoo's quoteSummary values are authoritative for valuation ratios
(they reflect Yahoo's own real-time mcap + current EV), so for the
VALUATION columns we PREFER the Yahoo value and overwrite whatever was
there (derived/stale). For raw financial LEVELS we only fill gaps —
EDGAR/XBRL audited levels are higher quality where present.

A provenance column `valuation_source` records 'yahoo' where we took
Yahoo's authoritative ratios, else leaves the existing source.

Writes back to asymmetry_global.csv in place (or --out).
"""
from __future__ import annotations
import argparse
import sys

import numpy as np
import pandas as pd


# Yahoo column -> master column, and whether Yahoo is authoritative
# (overwrite) or only gap-fills.
#   ('overwrite')  : Yahoo's own computed ratio, prefer it
#   ('fill')       : only fill where master is null
MERGE_SPEC = [
    # Authoritative valuation ratios — prefer Yahoo
    ("yf_market_cap", "market_cap", "overwrite"),
    ("yf_enterprise_value", "enterprise_value", "overwrite"),
    ("yf_ev_ebitda", "ev_ebitda", "overwrite"),
    ("yf_ev_sales", "ev_sales", "overwrite"),
    ("yf_pb", "pb", "overwrite"),
    ("yf_pe", "p_e", "overwrite"),
    ("yf_ps", "p_s", "overwrite"),
    ("yf_price", "price", "overwrite"),
    # Margins / returns — fill gaps (EDGAR audited wins where present)
    ("yf_ebitda_margin", "ebitda_margin", "fill"),
    ("yf_gross_margin", "gross_margin", "fill"),
    ("yf_operating_margin", "op_margin", "fill"),
    ("yf_profit_margin", "net_margin", "fill"),
    ("yf_roe", "roe", "fill"),
    ("yf_roa", "roa", "fill"),
    # Levels — fill gaps only
    ("yf_revenue", "revenue_ttm", "fill"),
    ("yf_ebitda", "ebitda_ttm", "fill"),
    ("yf_fcf", "fcf_ttm", "fill"),
    ("yf_cfo", "cfo_ttm", "fill"),
    ("yf_cash", "cash", "fill"),
    ("yf_total_debt", "total_debt", "fill"),
    ("yf_shares_outstanding", "shares_outstanding", "fill"),
    # Ownership / sell-side — fill gaps
    ("yf_insider_pct", "insider_ownership_pct", "fill"),
    ("yf_dividend_yield", "dividend_yield", "fill"),
    ("yf_target_mean", "analyst_target_mean", "fill"),
    ("yf_n_analysts", "n_analysts", "fill"),
    # 52-week
    ("yf_52w_high", "price_52w_high", "fill"),
]

# Extra Yahoo-native columns we keep with a yf_ prefix (no master equivalent)
YF_NATIVE_KEEP = [
    "yf_forward_pe", "yf_peg", "yf_beta", "yf_revenue_growth",
    "yf_earnings_growth", "yf_recommendation_mean", "yf_institution_pct",
    "yf_52w_low",
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--master", default="asymmetry_global.csv")
    ap.add_argument("--yf", default="ticker_yf.csv")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    out_path = args.out or args.master

    print(f"loading master {args.master}...", file=sys.stderr)
    master = pd.read_csv(args.master).drop_duplicates("symbol")
    print(f"  {len(master):,} rows", file=sys.stderr)

    try:
        yf = pd.read_csv(args.yf).drop_duplicates("symbol", keep="last")
    except FileNotFoundError:
        print(f"  {args.yf} not found — nothing to merge", file=sys.stderr)
        sys.exit(0)
    print(f"  {len(yf):,} Yahoo rows", file=sys.stderr)

    m = master.set_index("symbol")
    y = yf.set_index("symbol")
    common = m.index.intersection(y.index)
    print(f"  {len(common):,} symbols overlap", file=sys.stderr)

    # Recompute derived EV/EBITDA-type ratios sanity: Yahoo's ev_ebitda is
    # a ratio already. Use directly.
    changes = {}
    for yf_col, master_col, mode in MERGE_SPEC:
        if yf_col not in y.columns:
            continue
        src = pd.to_numeric(y[yf_col], errors="coerce")
        src = src.reindex(m.index)
        if master_col not in m.columns:
            m[master_col] = np.nan
        before = m[master_col].notna().sum()
        if mode == "overwrite":
            mask = src.notna()
        else:  # fill
            mask = src.notna() & m[master_col].isna()
        m.loc[mask, master_col] = src[mask]
        after = m[master_col].notna().sum()
        changes[master_col] = (before, after, int(mask.sum()), mode)

    # Keep Yahoo-native extras
    for yf_col in YF_NATIVE_KEEP:
        if yf_col in y.columns:
            m[yf_col] = pd.to_numeric(y[yf_col], errors="coerce").reindex(m.index)

    # Provenance
    if "valuation_source" not in m.columns:
        m["valuation_source"] = ""
    has_yf_val = pd.to_numeric(y.get("yf_ev_ebitda"), errors="coerce").reindex(m.index).notna() \
        if "yf_ev_ebitda" in y.columns else pd.Series(False, index=m.index)
    m.loc[has_yf_val.fillna(False), "valuation_source"] = "yahoo"

    out = m.reset_index()
    out.to_csv(out_path, index=False)
    print(f"\nwrote {out_path}: {len(out):,} rows, {len(out.columns)} cols",
          file=sys.stderr)

    n = len(out)
    print("\nMerge results (col: before -> after, applied, mode):", file=sys.stderr)
    for col, (b, a, applied, mode) in sorted(changes.items(), key=lambda kv: -kv[1][2]):
        print(f"  {col:24s} {b:6,} -> {a:6,}  applied={applied:6,}  [{mode}]  "
              f"{100*a/n:.1f}%", file=sys.stderr)


if __name__ == "__main__":
    main()
