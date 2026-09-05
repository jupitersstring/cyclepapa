"""Merge stooq_price_fill.csv into asymmetry_global.csv.

Fill-don't-overwrite semantics for price, momentum_12m, pct_off_52w_high.
Only rows with status == 'ok' are merged.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pandas as pd


COLS_TO_REPORT = ["price", "momentum_12m", "pct_off_52w_high"]


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
    master_path = Path("asymmetry_global.csv")
    fill_path = Path("stooq_price_fill.csv")
    if not master_path.exists():
        print(f"ERROR: master CSV not found: {master_path}", file=sys.stderr)
        return 1
    if not fill_path.exists():
        print(f"ERROR: fill CSV not found: {fill_path}", file=sys.stderr)
        return 1

    df = pd.read_csv(master_path, low_memory=False)
    print(f"master: {len(df):,} rows, {len(df.columns)} cols", file=sys.stderr)

    fill = pd.read_csv(fill_path, low_memory=False)
    if "status" in fill.columns:
        fill = fill[fill["status"] == "ok"].copy()
    fill = fill.dropna(subset=["symbol"]).drop_duplicates("symbol", keep="last")
    print(f"stooq ok rows: {len(fill):,}", file=sys.stderr)

    before = coverage(df, COLS_TO_REPORT)
    print_coverage("BEFORE", before)

    suff = "__s"
    merged = df.merge(
        fill[["symbol", "price", "momentum_12m", "pct_off_52w_high"]],
        on="symbol", how="left", suffixes=("", suff),
    )

    filled = {}
    for col in COLS_TO_REPORT:
        ycol = col + suff
        if ycol not in merged.columns:
            continue
        master_col = pd.to_numeric(merged[col], errors="coerce")
        yahoo_col = pd.to_numeric(merged[ycol], errors="coerce")
        will_fill = master_col.isna() & yahoo_col.notna()
        merged.loc[will_fill, col] = yahoo_col[will_fill]
        merged.drop(columns=[ycol], inplace=True)
        filled[col] = int(will_fill.sum())

    print("\nFILLS")
    for k, v in filled.items():
        print(f"  {k:<20s} {v:>7,}")

    after = coverage(merged, COLS_TO_REPORT)
    print_coverage("AFTER", after)

    tmp = str(master_path) + ".tmp"
    merged.to_csv(tmp, index=False)
    os.replace(tmp, master_path)
    print(f"\nwrote {master_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
