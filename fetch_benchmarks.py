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


# Alternate tickers tried in order when the primary returns a stale or
# near-empty series (Turkey's ^XU100 froze at 2021-09 on Yahoo; Thailand's
# ^SET.BK returned a single bar) — a silent stale benchmark anchored
# every .IS rel-52w-high five years in the past.
ALTERNATES = {
    '^XU100': ['XU100.IS', '^XU100'],
    '^SET.BK': ['^SET.BK', 'SET.BK'],
}


def _fetch_series(sess, sym):
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/"
           f"{urllib.parse.quote(sym)}?range=10y&interval=1mo")
    d = json.loads(sess.opener.open(url, timeout=15).read())
    res = d['chart']['result'][0]
    idx = pd.to_datetime([pd.Timestamp(t, unit='s') for t in res['timestamp']])
    close = res['indicators']['quote'][0]['close']
    return pd.Series(close, index=idx).dropna()


def _fresh(s):
    return (len(s) >= 24 and
            (pd.Timestamp.now() - s.index.max()).days <= 62)


def main():
    sess = YahooSession()
    sess.warm()
    frames = {}
    for b in BENCHMARKS:
        best = None
        for cand in ALTERNATES.get(b, [b]):
            for attempt in range(3):
                try:
                    s = _fetch_series(sess, cand)
                except Exception as e:
                    print(f"  {b} via {cand} try{attempt+1}: FAILED ({e})",
                          file=sys.stderr)
                    time.sleep(2 * (attempt + 1))
                    continue
                if best is None or len(s) > len(best):
                    best = s
                if _fresh(s):
                    break
                time.sleep(1)
            if best is not None and _fresh(best):
                break
        if best is not None:
            frames[b] = best
            tag = 'OK' if _fresh(best) else 'STALE/THIN'
            print(f"  {b}: {len(best)} bars through "
                  f"{best.index.max().date()} [{tag}]", file=sys.stderr)
        else:
            print(f"  {b}: NO DATA", file=sys.stderr)
        time.sleep(0.5)
    out = pd.DataFrame(frames)
    out.index.name = 'date'
    out.to_csv('benchmark_series.csv')
    print(f"wrote benchmark_series.csv: {out.shape}", file=sys.stderr)


if __name__ == '__main__':
    main()
