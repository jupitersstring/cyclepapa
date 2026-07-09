"""Batched resume-safe Dormeier volume-leg scan over the full native
universe (weekly bars). Appends to /tmp/volume_rank.csv.

Usage: python volume_scan.py [--fresh]
"""

import os
import sys
import gc
import warnings

import numpy as np
import pandas as pd

sys.path.insert(0, "/home/user/cyclepapa")
from mtf_psar_rank import load_universe, is_native, fetch_interval_bulk
from volume_leg import volume_breakout

warnings.filterwarnings("ignore")

OUT = "/tmp/volume_rank.csv"
BATCH = 1500


def main():
    if "--fresh" in sys.argv and os.path.exists(OUT):
        os.remove(OUT)

    big = load_universe(include_rejected=True)
    big = big[big.ticker.apply(is_native)].drop_duplicates(subset=["ticker"])
    meta = big[["ticker", "region"]]
    tickers = big.ticker.astype(str).tolist()
    print(f"Universe: {len(tickers)}", file=sys.stderr)

    done = set()
    if os.path.exists(OUT):
        done = set(pd.read_csv(OUT, usecols=["ticker"]).ticker)
        print(f"Resume: {len(done)} done", file=sys.stderr)
    todo = [t for t in tickers if t not in done]
    print(f"To scan: {len(todo)}", file=sys.stderr)
    if not todo:
        print("Nothing to scan.")
        return

    # Fast-fail probe (rate-limit detection)
    probe = fetch_interval_bulk(todo[:40], "1wk", include_volume=True)
    if len(probe) < 8:
        print(f"ABORT: probe {len(probe)}/40 — rate limited", file=sys.stderr)
        sys.exit(2)

    n_batches = (len(todo) + BATCH - 1) // BATCH
    for b in range(n_batches):
        batch = todo[b * BATCH:(b + 1) * BATCH]
        print(f"--- batch {b+1}/{n_batches} ({len(batch)}) ---", file=sys.stderr)
        weekly = fetch_interval_bulk(batch, "1wk", include_volume=True)
        if len(weekly) < len(batch) * 0.2:
            print("ABORT: batch fetch rate-limited; exit 2", file=sys.stderr)
            sys.exit(2)
        rows = []
        for t in batch:
            try:
                w = weekly.get(t)
                if w is None:
                    continue
                # fetch_interval_bulk returns OHLC only if Volume absent from
                # its column set; ensure Volume present
                if "Volume" not in w.columns:
                    continue
                r = volume_breakout(w)
                if not r:
                    continue
                r["ticker"] = t
                rows.append(r)
            except Exception:
                continue
        if rows:
            out = pd.DataFrame(rows).merge(meta, on="ticker", how="left")
            out.to_csv(OUT, mode="a", header=not os.path.exists(OUT), index=False)
            print(f"  appended {len(out)} -> {OUT}", file=sys.stderr)
        del weekly
        gc.collect()

    print(f"Volume scan complete -> {OUT}")


if __name__ == "__main__":
    main()
