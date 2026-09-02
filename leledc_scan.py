"""Batched, resumable Leledc Exhaustion scan (weekly + monthly) over the
full native universe. Appends to /tmp/leledc_rank.csv; already-scanned
tickers are skipped on restart, so process-level retries lose nothing.

Usage:
  python leledc_scan.py            # resume or start
  python leledc_scan.py --fresh    # start over
"""

import os
import sys
import gc
import warnings

import numpy as np
import pandas as pd

sys.path.insert(0, "/home/user/cyclepapa")
from mtf_psar_rank import load_universe, is_native, fetch_interval_bulk
from leledc_exhaustion import evaluate_ticker

warnings.filterwarnings("ignore")

OUT = "/tmp/leledc_rank.csv"
BATCH = 1500
KEEP_COLS = ["LELE", "LELE_W", "LELE_M",
             "w_close", "w_support", "w_resistance", "w_rr", "w_position",
             "w_bars_since_bull", "w_bars_since_bear",
             "m_support", "m_resistance", "m_rr", "m_position",
             "m_bars_since_bull"]


def main():
    if "--fresh" in sys.argv and os.path.exists(OUT):
        os.remove(OUT)
        print("Fresh start", file=sys.stderr)

    big = load_universe(include_rejected=True)
    big = big[big.ticker.apply(is_native)].copy()
    big = big.drop_duplicates(subset=["ticker"], keep="first")
    meta = big[["ticker", "region"]]
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

    # Fast-fail probe: one small chunk. If rate-limited, exit immediately so
    # the shell's cooldown actually lets the limit decay instead of the full
    # batch fetch hammering through 30 chunks of retries.
    probe = fetch_interval_bulk(todo[:40], "1wk")
    if len(probe) < 8:
        print(f"ABORT: probe got {len(probe)}/40 — rate limited; exit 2",
              file=sys.stderr)
        sys.exit(2)

    n_batches = (len(todo) + BATCH - 1) // BATCH
    for b in range(n_batches):
        batch = todo[b * BATCH:(b + 1) * BATCH]
        print(f"--- batch {b+1}/{n_batches} ({len(batch)} tickers) ---",
              file=sys.stderr)
        weekly = fetch_interval_bulk(batch, "1wk")
        monthly = fetch_interval_bulk(batch, "1mo")
        # Guard: if the fetch produced almost nothing, we're rate-limited —
        # exit nonzero so the shell rotates to a fresh process.
        if len(weekly) < len(batch) * 0.2:
            print(f"ABORT: weekly fetch got {len(weekly)}/{len(batch)} — "
                  "rate limited; exit for process retry", file=sys.stderr)
            sys.exit(2)

        rows = []
        rej = {"no_fetch": 0, "exception": 0}
        for t in batch:
            try:
                w = weekly.get(t)
                m = monthly.get(t)
                if w is None and m is None:
                    rej["no_fetch"] += 1
                    continue
                r = evaluate_ticker(w, m)
                row = {"ticker": t}
                for k in KEEP_COLS:
                    row[k] = r.get(k, np.nan)
                rows.append(row)
            except Exception:
                rej["exception"] += 1
                continue

        if rows:
            out = pd.DataFrame(rows).merge(meta, on="ticker", how="left")
            header = not os.path.exists(OUT)
            out.to_csv(OUT, mode="a", header=header, index=False)
            print(f"  appended {len(out)} rows -> {OUT}", file=sys.stderr)
        if sum(rej.values()):
            print(f"  rejected {sum(rej.values())}/{len(batch)}: {rej}", file=sys.stderr)

        del weekly, monthly
        gc.collect()

    print(f"Leledc scan complete -> {OUT}")


if __name__ == "__main__":
    main()
