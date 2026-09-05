"""Merge yahoo_chart_fill.csv into asymmetry_global.csv.

yahoo_chart_fill.csv is populated by the background yahoo_chart_fill.py
worker (Yahoo v8/chart endpoint). This script folds those values into
the master CSV using fill-don't-overwrite semantics, then derives
market_cap and enterprise_value where EDGAR has given us the
fundamentals to do so.

Merge rules:
  - price             : fill where master.price is null
  - momentum_12m      : fill where master.momentum_12m is null
  - pct_off_52w_high  : fill where master.pct_off_52w_high is null
                        (master has the column but it's empty for all
                         rows today, so this is effectively additive)
  - market_cap        : where master.market_cap is null AND we now have
                        a price AND shares_outstanding is present,
                        derive market_cap = price * shares_outstanding
  - enterprise_value  : where price + market_cap are populated AND
                        total_debt + cash are present (from EDGAR),
                        derive ev = market_cap + total_debt - cash.
                        This column does not exist in master today; we
                        add it.

Writes back to asymmetry_global.csv in place (atomic via .tmp swap)
and prints a before/after coverage report.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import pandas as pd


COLS_TO_REPORT = [
    "price",
    "momentum_12m",
    "pct_off_52w_high",
    "market_cap",
    "enterprise_value",
]


def coverage(df: pd.DataFrame, cols: list[str]) -> dict[str, tuple[int, int]]:
    n = len(df)
    out = {}
    for c in cols:
        if c in df.columns:
            out[c] = (int(df[c].notna().sum()), n)
        else:
            out[c] = (0, n)
    return out


def print_coverage(label: str, cov: dict[str, tuple[int, int]]) -> None:
    print(f"\n{label}")
    for c, (k, n) in cov.items():
        pct = 100.0 * k / n if n else 0.0
        print(f"  {c:<20s} {k:>7,} / {n:,}  ({pct:5.1f}%)")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--master", default="asymmetry_global.csv",
                    help="Master CSV to merge into (default: asymmetry_global.csv)")
    ap.add_argument("--fill", default="yahoo_chart_fill.csv",
                    help="Yahoo fill CSV (default: yahoo_chart_fill.csv)")
    ap.add_argument("--dry-run", action="store_true",
                    help="Compute and report but do not write")
    args = ap.parse_args()

    master_path = Path(args.master)
    fill_path = Path(args.fill)
    if not master_path.exists():
        print(f"ERROR: master CSV not found: {master_path}", file=sys.stderr)
        return 1
    if not fill_path.exists():
        print(f"ERROR: fill CSV not found: {fill_path}", file=sys.stderr)
        return 1

    print(f"loading master from {master_path}...", file=sys.stderr)
    df = pd.read_csv(master_path, low_memory=False)
    print(f"  {len(df):,} rows, {len(df.columns)} columns", file=sys.stderr)

    print(f"loading fill from {fill_path}...", file=sys.stderr)
    fill = pd.read_csv(fill_path, low_memory=False)
    print(f"  {len(fill):,} rows", file=sys.stderr)

    # Ensure target columns exist on master so we can fill into them.
    if "pct_off_52w_high" not in df.columns:
        df["pct_off_52w_high"] = pd.NA
    if "enterprise_value" not in df.columns:
        df["enterprise_value"] = pd.NA

    before = coverage(df, COLS_TO_REPORT)
    print_coverage("BEFORE", before)

    # Build a symbol -> row dict from the fill (latest row wins if there
    # are duplicates; yahoo_chart_fill.py dedups already but be safe).
    fill = fill.dropna(subset=["symbol"]).drop_duplicates("symbol", keep="last")

    # Left-join keeps the master ordering intact.
    suff = "__y"
    merged = df.merge(
        fill[["symbol", "price", "momentum_12m", "pct_off_52w_high"]],
        on="symbol",
        how="left",
        suffixes=("", suff),
    )

    # --- price / momentum_12m / pct_off_52w_high : fill-don't-overwrite -----
    filled = {}
    for col in ("price", "momentum_12m", "pct_off_52w_high"):
        ycol = col + suff
        if ycol not in merged.columns:
            # Column didn't get a suffix because it wasn't in master pre-add
            # (shouldn't happen since we ensured pct_off_52w_high above).
            continue
        master_col = pd.to_numeric(merged[col], errors="coerce")
        yahoo_col = pd.to_numeric(merged[ycol], errors="coerce")
        was_null = master_col.isna()
        will_fill = was_null & yahoo_col.notna()
        merged.loc[will_fill, col] = yahoo_col[will_fill]
        merged.drop(columns=[ycol], inplace=True)
        filled[col] = int(will_fill.sum())

    # --- market_cap derivation ----------------------------------------------
    price_num = pd.to_numeric(merged["price"], errors="coerce")
    mcap_num = pd.to_numeric(merged["market_cap"], errors="coerce")
    if "shares_outstanding" in merged.columns:
        shares_num = pd.to_numeric(merged["shares_outstanding"], errors="coerce")
    else:
        shares_num = pd.Series([float("nan")] * len(merged), index=merged.index)

    need_mcap = mcap_num.isna() & price_num.notna() & shares_num.notna()
    derived_mcap = price_num * shares_num
    merged.loc[need_mcap, "market_cap"] = derived_mcap[need_mcap]
    filled["market_cap (derived)"] = int(need_mcap.sum())

    # Refresh after derivation for EV step.
    mcap_num = pd.to_numeric(merged["market_cap"], errors="coerce")
    price_num = pd.to_numeric(merged["price"], errors="coerce")

    # --- enterprise_value derivation ----------------------------------------
    if "total_debt" in merged.columns:
        debt_num = pd.to_numeric(merged["total_debt"], errors="coerce")
    else:
        debt_num = pd.Series([float("nan")] * len(merged), index=merged.index)
    if "cash" in merged.columns:
        cash_num = pd.to_numeric(merged["cash"], errors="coerce")
    else:
        cash_num = pd.Series([float("nan")] * len(merged), index=merged.index)
    ev_num = pd.to_numeric(merged["enterprise_value"], errors="coerce")

    need_ev = (
        ev_num.isna()
        & price_num.notna()
        & mcap_num.notna()
        & debt_num.notna()
        & cash_num.notna()
    )
    derived_ev = mcap_num + debt_num - cash_num
    merged.loc[need_ev, "enterprise_value"] = derived_ev[need_ev]
    filled["enterprise_value (derived)"] = int(need_ev.sum())

    # Report ------------------------------------------------------------------
    print("\nFILLS")
    for k, v in filled.items():
        print(f"  {k:<32s} {v:>7,}")

    after = coverage(merged, COLS_TO_REPORT)
    print_coverage("AFTER", after)

    # Delta summary
    print("\nDELTA")
    for c in COLS_TO_REPORT:
        b = before[c][0]
        a = after[c][0]
        print(f"  {c:<20s} {b:>7,} -> {a:>7,}  (+{a - b:,})")

    print(f"\nfinal columns: {len(merged.columns)} (master had {len(df.columns)})")

    if args.dry_run:
        print("\n--dry-run set; not writing.", file=sys.stderr)
        return 0

    # Atomic write
    tmp = str(master_path) + ".tmp"
    merged.to_csv(tmp, index=False)
    os.replace(tmp, master_path)
    print(f"\nwrote {master_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
