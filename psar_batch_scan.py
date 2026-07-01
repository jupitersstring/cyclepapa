"""Batched, resumable MTF PSAR scan over the full native universe.

Loads every ticker from /tmp/stars_aligned_*.csv (native filter, OTC
wrappers excluded), splits into batches of 1500, fetches all 5 yfinance
intervals per batch, computes composites, and APPENDS results to the
output CSV. Resume-safe: tickers already present in the output are
skipped, so a crash/reset loses at most one batch.

Usage:
  python psar_batch_scan.py            # resume or start
  python psar_batch_scan.py --fresh    # delete output, start over
"""

import os
import sys
import gc
import warnings

import pandas as pd

sys.path.insert(0, "/home/user/cyclepapa")
from mtf_psar_rank import (
    load_universe, is_native, fetch_interval_bulk, fetch_benchmark_bulk,
    composites_for_ticker, current_and_slope, TF_CONFIG,
)

warnings.filterwarnings("ignore")

OUT = "/tmp/mtf_psar_rank_full.csv"
BATCH = 1500


def main():
    if "--fresh" in sys.argv and os.path.exists(OUT):
        os.remove(OUT)
        print("Fresh start: removed old output", file=sys.stderr)

    big = load_universe(include_rejected=True)
    big = big[big.ticker.apply(is_native)].copy()
    big["best_rank"] = big[["daily_rank", "weekly_rank", "monthly_rank"]].max(axis=1)
    big = big.drop_duplicates(subset=["ticker"], keep="first")
    meta = big[["ticker", "region", "best_rank"]]
    tickers = big.ticker.astype(str).tolist()
    print(f"Universe: {len(tickers)} native tickers", file=sys.stderr)

    done = set()
    if os.path.exists(OUT):
        done = set(pd.read_csv(OUT, usecols=["ticker"]).ticker)
        print(f"Resume: {len(done)} already scanned", file=sys.stderr)
    todo = [t for t in tickers if t not in done]
    print(f"To scan: {len(todo)}", file=sys.stderr)
    if not todo:
        print("Nothing to scan.")
        return

    intervals = list({iv for _, iv, _, _ in TF_CONFIG})
    bench = fetch_benchmark_bulk(intervals)

    n_batches = (len(todo) + BATCH - 1) // BATCH
    for b in range(n_batches):
        batch = todo[b * BATCH:(b + 1) * BATCH]
        print(f"--- batch {b+1}/{n_batches} ({len(batch)} tickers) ---",
              file=sys.stderr)
        per_interval = {}
        for iv in intervals:
            per_interval[iv] = fetch_interval_bulk(batch, iv)

        rows = []
        for t in batch:
            try:
                asset_ma, rel_ma, used = composites_for_ticker(
                    t, per_interval, bench)
                a = current_and_slope(asset_ma)
                r = current_and_slope(rel_ma)
                if a is None and r is None:
                    continue
                row = {"ticker": t, "n_active_tfs": len(used)}
                if a is not None:
                    row.update(asset_net_ma=a[0], asset_slope_norm=a[1],
                               asset_score=a[2])
                if r is not None:
                    row.update(rel_net_ma=r[0], rel_slope_norm=r[1],
                               rel_score=r[2])
                rows.append(row)
            except Exception:
                continue

        if rows:
            out = pd.DataFrame(rows).merge(meta, on="ticker", how="left")
            out["combined_score"] = (out.get("asset_score", 0).fillna(0) +
                                      out.get("rel_score", 0).fillna(0))
            header = not os.path.exists(OUT)
            out.to_csv(OUT, mode="a", header=header, index=False)
            print(f"  appended {len(out)} rows -> {OUT}", file=sys.stderr)

        del per_interval
        gc.collect()

    print(f"Scan complete -> {OUT}")


if __name__ == "__main__":
    main()
