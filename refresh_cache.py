#!/usr/bin/env python3
"""
Refresh the trailing bars of an existing OHLCV cache (closes ISSUES.md #5:
the accumulating caches previously only ADDED symbols, never updated them, so
signals went stale as days passed).

Bulk-downloads the recent window for every cached symbol and splices the new
bars onto each frame. Early-aborts on rate limiting (re-run to resume; only
symbols still stale are re-fetched).

  python3 refresh_cache.py 1d  3mo     # refresh daily cache, 3-month window
  python3 refresh_cache.py 1wk 6mo
"""
from __future__ import annotations

import os
import sys
import time
import warnings

import pandas as pd

warnings.filterwarnings("ignore")
CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".cache")


def refresh(interval="1d", window="3mo", period_key="20y", batch=40,
            stale_days=4) -> None:
    import yfinance as yf
    from yfsession import SESSION
    path = os.path.join(CACHE_DIR, f"ohlcvdict_{interval}_{period_key}.pkl")
    have: dict = pd.read_pickle(path)
    asof = max(d.index[-1] for d in have.values() if len(d))
    now = pd.Timestamp.utcnow().tz_localize(None)
    todo = [s for s, d in have.items()
            if len(d) and (now - d.index[-1]).days > stale_days]
    print(f"[refresh:{interval}] cache asof {asof.date()} | {len(todo)}/{len(have)} "
          f"symbols stale (> {stale_days}d)", flush=True)

    updated = miss_streak = 0
    for i in range(0, len(todo), batch):
        chunk = todo[i:i + batch]
        if i:
            time.sleep(2.0)
        try:
            data = yf.download(chunk, period=window, interval=interval,
                               auto_adjust=True, progress=False, threads=True,
                               group_by="ticker", session=SESSION)
        except Exception as e:
            print(f"  batch failed: {e!r}", flush=True)
            data = None
        got = 0
        if data is not None:
            for s in chunk:
                try:
                    new = (data[s] if len(chunk) > 1 else data)[["Close", "Volume"]].dropna()
                    if new.empty:
                        continue
                    new.index = pd.DatetimeIndex(new.index).tz_localize(None)
                    old = have[s]
                    have[s] = pd.concat([old[old.index < new.index[0]], new]).sort_index()
                    got += 1
                except Exception:
                    continue
        updated += got
        miss_streak = 0 if got else miss_streak + 1
        if (i // batch) % 5 == 4 or got == 0:
            pd.to_pickle(have, path)
            print(f"  {min(i+batch,len(todo))}/{len(todo)} updated={updated}", flush=True)
        if miss_streak >= 5:
            print("  rate-limited; stopping early (re-run to resume).", flush=True)
            break
    pd.to_pickle(have, path)
    new_asof = max(d.index[-1] for d in have.values() if len(d))
    print(f"[refresh:{interval}] DONE updated={updated} | cache asof now {new_asof.date()}",
          flush=True)


if __name__ == "__main__":
    refresh(interval=sys.argv[1] if len(sys.argv) > 1 else "1d",
            window=sys.argv[2] if len(sys.argv) > 2 else "3mo")
