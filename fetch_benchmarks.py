"""One-time fetch of country benchmark index series (10y monthly closes).

Used by lynch_reward_enrich to compute RELATIVE-strength 52-week highs
(stock/index ratio making a new high) — "making highs against the index".
~16 requests total; negligible against the shared throttle.
Output: benchmark_series.csv (date, index symbol columns of closes).
"""
from __future__ import annotations
import json
import sys
import time
import urllib.parse

import pandas as pd

from ticker_yf import YahooSession

BENCHMARKS = ['^GSPC', '^N225', '^KS11', '^TWII', '^HSI', '000001.SS',
              '^NSEI', '^SET.BK', '^JKSE', '^KLSE', '^STI', '^AXJO',
              '^FTSE', '^GDAXI', '^FCHI', '^BVSP', '^MXX', '^XU100']


def main():
    sess = YahooSession()
    sess.warm()
    frames = {}
    for b in BENCHMARKS:
        url = (f"https://query1.finance.yahoo.com/v8/finance/chart/"
               f"{urllib.parse.quote(b)}?range=10y&interval=1mo")
        try:
            d = json.loads(sess.opener.open(url, timeout=15).read())
            res = d['chart']['result'][0]
            idx = pd.to_datetime([pd.Timestamp(t, unit='s') for t in res['timestamp']])
            close = res['indicators']['quote'][0]['close']
            frames[b] = pd.Series(close, index=idx).dropna()
            print(f"  {b}: {len(frames[b])} bars", file=sys.stderr)
        except Exception as e:
            print(f"  {b}: FAILED ({e})", file=sys.stderr)
        time.sleep(0.5)
    out = pd.DataFrame(frames)
    out.index.name = 'date'
    out.to_csv('benchmark_series.csv')
    print(f"wrote benchmark_series.csv: {out.shape}", file=sys.stderr)


if __name__ == '__main__':
    main()
