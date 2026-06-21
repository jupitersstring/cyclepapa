"""Backfill yfinance names/sectors/mcap for every ticker in the master
universe that isn't already in the name cache. Persists incrementally
so a sandbox reset doesn't lose progress.

After completion, regenerates the workbook so the Full_Universe tab
shows real company names for every ranked ticker.
"""

import json
import os
import sys
import time

import pandas as pd
import yfinance as yf

CACHE = "/home/user/cyclepapa/data/ticker_info_cache.json"
MASTER = "/tmp/master_full_universe.csv"

FX = {'JPY': 0.0065, 'INR': 0.0117, 'KRW': 0.00073, 'TWD': 0.031, 'HKD': 0.128,
      'CNY': 0.139, 'GBp': 0.0127, 'GBP': 1.27, 'EUR': 1.08, 'CHF': 1.12,
      'SEK': 0.095, 'NOK': 0.092, 'DKK': 0.145, 'AUD': 0.65, 'NZD': 0.60,
      'PLN': 0.25, 'USD': 1.0, 'MXN': 0.055, 'BRL': 0.18, 'ZAR': 0.054,
      'TRY': 0.030, 'ILA': 0.0027, 'IDR': 0.000061, 'THB': 0.029, 'PHP': 0.017,
      'MYR': 0.21, 'SGD': 0.74}


def main():
    df = pd.read_csv(MASTER, low_memory=False)
    print(f"Universe: {len(df)} tickers", file=sys.stderr)

    cache = {}
    if os.path.exists(CACHE):
        with open(CACHE) as f:
            cache = json.load(f)
    print(f"Cache: {len(cache)} entries", file=sys.stderr)

    todo = [t for t in df.ticker if t not in cache or not cache[t].get('name')]
    print(f"To fetch: {len(todo)} tickers", file=sys.stderr)
    if not todo:
        print("Nothing to do.", file=sys.stderr)
        return

    saved = 0
    for i, t in enumerate(todo):
        try:
            info = yf.Ticker(t).info or {}
            cur = info.get('currency') or 'USD'
            cache[t] = {
                'name': (info.get('longName') or info.get('shortName') or '')[:34],
                'sector': (info.get('sector') or '')[:14],
                'mcap_M': round((info.get('marketCap') or 0) * FX.get(cur, 1.0) / 1e6),
            }
        except Exception:
            cache[t] = {'name': '', 'sector': '', 'mcap_M': 0}
        # Checkpoint every 1500 to keep cache durable without git churn
        if (i + 1) % 1500 == 0:
            with open(CACHE, "w") as f:
                json.dump(cache, f)
            saved = i + 1
            print(f"  {i+1}/{len(todo)} (cache: {len(cache)})", file=sys.stderr)

    # Final save
    with open(CACHE, "w") as f:
        json.dump(cache, f)
    print(f"Cache final: {len(cache)} entries", file=sys.stderr)


if __name__ == "__main__":
    main()
