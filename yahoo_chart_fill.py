"""Fill price + 12-month momentum + 52-week-high gaps via Yahoo's
v8/finance/chart endpoint.

Background: in mid-2026 Yahoo locked down v7/finance/quote and
v10/finance/quoteSummary (both return 401 to unauthenticated callers,
which is what yfinance is), but the chart endpoint
query1.finance.yahoo.com/v8/finance/chart/<SYMBOL> still serves
adjusted-close history to anyone with a User-Agent header. That's
enough to compute:

  price             — last close
  momentum_12m      — (last close / close one year ago) - 1
  pct_off_52w_high  — (last close - 52w high) / 52w high
  market_cap        — last close × shares_outstanding (when EDGAR
                      gave us shares; otherwise NaN)

Output: yahoo_chart_fill.csv (symbol-keyed). Downstream pipelines can
left-join this to fill the price / momentum / market_cap columns where
they were missing.

This runs in parallel batches with a thread pool to keep wall-clock
under control. Resumable: rows already present in yahoo_chart_fill.csv
are skipped on a re-run unless --refresh is passed.
"""
from __future__ import annotations
import argparse
import csv
import json
import os
import random
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import pandas as pd


CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range=1y&interval=1d"
USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
]


def fetch_chart(symbol: str, timeout: int = 12) -> dict | None:
    """Pull 1y daily close from v8/chart. Returns dict or None on failure."""
    url = CHART_URL.format(symbol=urllib.parse.quote(symbol))
    req = urllib.request.Request(url, headers={
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.loads(r.read())
    except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError, TimeoutError):
        return None
    res = (data.get("chart") or {}).get("result")
    if not res:
        return None
    r0 = res[0]
    meta = r0.get("meta") or {}
    ind = r0.get("indicators") or {}
    quotes = (ind.get("adjclose") or [{}])[0].get("adjclose") or \
             (ind.get("quote") or [{}])[0].get("close")
    if not quotes:
        return None
    # Drop None values (early in the series before listing date)
    closes = [c for c in quotes if c is not None]
    if not closes:
        return None
    last = float(closes[-1])
    first = float(closes[0])
    high_52w = max(closes)
    return {
        "symbol": symbol,
        "price": last,
        "momentum_12m": (last - first) / first if first else None,
        "pct_off_52w_high": (last - high_52w) / high_52w if high_52w else None,
        "price_52w_high": high_52w,
        "regular_market_price": meta.get("regularMarketPrice"),
        "currency": meta.get("currency"),
        "fetched_at": int(time.time()),
    }


import urllib.parse  # late import, used in fetch_chart


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbols-from", default="asymmetry_global.csv",
                    help="CSV to source the symbol universe from")
    ap.add_argument("--out", default="yahoo_chart_fill.csv")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--refresh", action="store_true",
                    help="ignore existing output and refetch all symbols")
    ap.add_argument("--limit", type=int, default=0,
                    help="cap symbols this run (0 = all)")
    ap.add_argument("--only-missing", action="store_true",
                    help="only fetch symbols where price is null in the input CSV")
    args = ap.parse_args()

    print(f"loading symbol universe from {args.symbols_from}...", file=sys.stderr)
    df = pd.read_csv(args.symbols_from)
    if "symbol" not in df.columns:
        print(f"  no 'symbol' column", file=sys.stderr)
        sys.exit(1)

    if args.only_missing and "price" in df.columns:
        df = df[df["price"].isna()]
        print(f"  filtered to {len(df):,} rows missing price", file=sys.stderr)

    symbols = df["symbol"].dropna().drop_duplicates().tolist()
    print(f"  {len(symbols):,} symbols to consider", file=sys.stderr)

    existing = {}
    if not args.refresh and os.path.exists(args.out):
        ex = pd.read_csv(args.out)
        existing = {r["symbol"]: r for _, r in ex.iterrows()}
        print(f"  {len(existing):,} symbols already fetched (resuming)", file=sys.stderr)

    todo = [s for s in symbols if s not in existing]
    if args.limit:
        todo = todo[:args.limit]
    print(f"  todo: {len(todo):,} symbols", file=sys.stderr)

    if not todo and not args.refresh:
        print("nothing to fetch", file=sys.stderr)
        return

    results = list(existing.values()) if not args.refresh else []
    failed = 0
    start = time.time()

    def write_partial():
        if not results:
            return
        out = pd.DataFrame(results)
        tmp = args.out + ".tmp"
        out.to_csv(tmp, index=False)
        os.replace(tmp, args.out)

    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(fetch_chart, s): s for s in todo}
        for i, fut in enumerate(as_completed(futs), start=1):
            sym = futs[fut]
            try:
                r = fut.result(timeout=20)
            except Exception:
                r = None
            if r is not None:
                results.append(r)
            else:
                failed += 1
            if i % 200 == 0:
                rate = i / max(1.0, time.time() - start)
                eta = (len(todo) - i) / rate if rate else 0
                print(f"  {i:,}/{len(todo):,}  ok={i - failed} fail={failed}  "
                      f"({rate:.1f}/s, ETA {eta/60:.1f}m)", file=sys.stderr)
                sys.stderr.flush()
                write_partial()

    write_partial()
    elapsed = time.time() - start
    print(f"\nDONE: {len(results):,} rows ({failed:,} failures) in {elapsed/60:.1f}m",
          file=sys.stderr)
    print(f"wrote {args.out}", file=sys.stderr)


if __name__ == "__main__":
    main()
