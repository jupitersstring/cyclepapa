"""Universe coverage audit: verify the methodology ranks every ticker
that was ever screened, with no silent drops to local memory.

Runs purely off disk (no Python-level caching/imports of cached state).
Reports the dropout funnel at each filter stage so any gap is visible.
"""

import glob
import os
import warnings

import pandas as pd
import numpy as np

warnings.filterwarnings("ignore")

NATIVE_SUF = {".L", ".PA", ".AS", ".BR", ".LS", ".IR", ".MI", ".MC", ".SW", ".VI",
              ".DE", ".ST", ".OL", ".CO", ".HE", ".AT", ".T", ".JP", ".HK", ".SI",
              ".KS", ".KQ", ".TW", ".TWO", ".NS", ".BO", ".SS", ".SZ", ".AX", ".NZ"}


def is_native(t):
    if not isinstance(t, str):
        return False
    if "." not in t:
        if len(t) == 5 and t[-1] in ("F", "Y"):
            return False
        return True
    return "." + t.rsplit(".", 1)[1] in NATIVE_SUF


def main():
    print("=" * 72)
    print("UNIVERSE COVERAGE AUDIT — disk-only, no local memory")
    print("=" * 72)

    # 1. Raw screen output
    files = sorted(glob.glob("/tmp/stars_aligned_*.csv"))
    print(f"\n[1] Source: {len(files)} region CSVs in /tmp/stars_aligned_*.csv")
    for f in files:
        n = sum(1 for _ in open(f)) - 1
        size = os.path.getsize(f)
        print(f"    {os.path.basename(f):45s} {n:>5} rows  {size/1024:.0f}KB")

    rows = []
    for p in files:
        region = p.split("stars_aligned_")[-1].replace(".csv", "")
        d = pd.read_csv(p)
        d["region"] = region
        rows.append(d)
    big = pd.concat(rows, ignore_index=True)
    print(f"\n    Total rows (with cross-region dupes):  {len(big):>6}")
    print(f"    Unique tickers (cross-region dedup):   {big.ticker.nunique():>6}")

    # 2. Filter funnel
    print(f"\n[2] Dropout funnel from raw -> ranked:")
    stages = []
    stages.append(("0. raw rows in CSVs", len(big)))
    big_dedup = big.drop_duplicates("ticker")
    stages.append(("1. unique tickers", len(big_dedup)))
    big_native = big_dedup[big_dedup.ticker.apply(is_native)]
    stages.append(("2. native (no OTC wrappers, has suffix)", len(big_native)))
    stages.append(("3. has M leg",  big_native.M.notna().sum() if "M" in big_native.columns else 0))
    stages.append(("4. has E leg",  big_native.E.notna().sum() if "E" in big_native.columns else 0))
    stages.append(("5. has DSR leg",big_native.DSR.notna().sum() if "DSR" in big_native.columns else 0))
    stages.append(("6. has ADV leg",big_native.ADV_play_now.notna().sum() if "ADV_play_now" in big_native.columns else 0))

    # PSAR
    psar = pd.read_csv("/tmp/mtf_psar_rank_full_clean.csv")
    psar_set = set(psar.ticker)
    n_psar_in_native = sum(1 for t in big_native.ticker if t in psar_set)
    stages.append(("7. has PSAR data (intersect with PSAR scan)", n_psar_in_native))

    prev = None
    for label, count in stages:
        delta = "" if prev is None else f"  (dropped {prev-count:+d})"
        print(f"    {label:55s} {count:>6}{delta}")
        prev = count

    # 3. Confirm master_full_universe.csv covers everything
    print(f"\n[3] Master analysis output coverage:")
    try:
        mf = pd.read_csv("/tmp/master_full_universe.csv")
        print(f"    /tmp/master_full_universe.csv:        {len(mf):>6} rows")
        print(f"      with PSAR contribution:             {mf.has_psar.sum():>6}")
        print(f"      PSAR-optional (rescued):            {(~mf.has_psar).sum():>6}")
        print(f"      with master score computed:         {mf.master.notna().sum():>6}")
        print(f"      with adv_usd populated:             {mf.adv_usd.notna().sum():>6}")
    except FileNotFoundError:
        print("    /tmp/master_full_universe.csv NOT FOUND - run master_full_universe.py")

    # 4. Tickers in native universe NOT in master output (gap detection)
    if 'mf' in locals():
        gap = set(big_native.ticker) - set(mf.ticker)
        print(f"\n[4] Gap detection:")
        print(f"    Tickers in native universe but NOT in master output: {len(gap)}")
        if gap and len(gap) <= 30:
            print(f"    {sorted(gap)}")
        elif gap:
            print(f"    First 30: {sorted(gap)[:30]}")

    # 5. Verify durability: every input file is sourced from /tmp (disk), not memory
    print(f"\n[5] Durability check — all inputs read fresh from disk:")
    for path in files + ["/tmp/mtf_psar_rank_full_clean.csv", "/tmp/master_full_universe.csv"]:
        if os.path.exists(path):
            mtime = os.path.getmtime(path)
            size = os.path.getsize(path)
            print(f"    {path:55s} {size/1024:>7.0f}KB  "
                  f"mtime={pd.Timestamp.fromtimestamp(mtime).strftime('%Y-%m-%d %H:%M')}")

    # 6. Per-region master coverage table
    if 'mf' in locals():
        print(f"\n[6] Per-region master coverage:")
        for region in sorted(mf.region.unique()):
            sub_native = big_native[big_native.region == region]
            sub_master = mf[mf.region == region]
            n_native = len(sub_native)
            n_master = len(sub_master)
            pct = n_master / n_native * 100 if n_native else 0
            print(f"    {region:25s} native={n_native:>5}  master={n_master:>5}  ({pct:>5.1f}%)")


if __name__ == "__main__":
    main()
