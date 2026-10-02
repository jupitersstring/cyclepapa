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


def fetch_chart(symbol: str, timeout: int = 4) -> dict | None:
    """Pull 1y daily close from v8/chart. Returns dict or None on failure.

    No retries: Yahoo's failures are mostly server-side flakiness (random
    25% empty-response rate observed). Retrying just blocks workers on a
    slow path. Better to skip + cover on the next run.
    """
    url = CHART_URL.format(symbol=urllib.parse.quote(symbol))
    req = urllib.request.Request(url, headers={
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.loads(r.read())
    except Exception:
        return None
    res = (data.get("chart") or {}).get("result")
    if not res:
        return None
    r0 = res[0]
    meta = r0.get("meta") or {}
    ind = r0.get("indicators") or {}
    # (audit #8) RAW close and ADJUSTED close have separate roles. The old
    # code preferred adjclose and stored it as `price`, then derived market
    # cap from it — but adjclose is back-adjusted for dividends/splits and is
    # NOT what the share trades at. PRICE (-> market cap) must be the RAW
    # close; MOMENTUM and the 52w drawdown are RETURN measures, so they use
    # the ADJUSTED series (total-return-consistent).
    quotes_adj = (ind.get("adjclose") or [{}])[0].get("adjclose") or []
    quotes_raw = (ind.get("quote") or [{}])[0].get("close") or []
    adj = [c for c in quotes_adj if c is not None]   # drop pre-listing Nones
    raw = [c for c in quotes_raw if c is not None]
    if not adj and not raw:
        return None
    series = adj if adj else raw                     # return series (adjusted)
    last = float(series[-1])
    first = float(series[0])
    high_52w = max(series)
    last_raw = float(raw[-1]) if raw else last       # price basis (raw close)
    return {
        "symbol": symbol,
        "price": last_raw,
        "adj_close": last,
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
    ap.add_argument("--max-age-days", type=float, default=30.0,
                    help="(audit #8) refetch a cached symbol once its fetched_at is "
                         "older than this many days (TTL); previously cached rows "
                         "were skipped forever")
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
        # Convert each row to a plain dict so it concats cleanly with new fetches
        existing = {r["symbol"]: r.to_dict() for _, r in ex.iterrows()}
        print(f"  {len(existing):,} symbols already fetched (resuming)", file=sys.stderr)

    # (audit #8) TTL REFRESH. The old resume logic skipped every already-
    # fetched symbol FOREVER (99.4% of the 40,757-row cache was >30 days old,
    # 88% >60 days), so "resumed" runs refreshed nothing. A cached row is now
    # STALE once its fetched_at is older than --max-age-days and is refetched;
    # fresh rows are kept. --refresh still forces a full refetch.
    _now = time.time()
    _max_age = float(args.max_age_days) * 86400.0
    def _stale(row):
        fa = row.get("fetched_at")
        try:
            return (fa is None) or pd.isna(fa) or (_now - float(fa)) > _max_age
        except Exception:
            return True
    stale = {s for s, r in existing.items() if _stale(r)}
    todo = [s for s in symbols if s not in existing or s in stale]
    if args.limit:
        todo = todo[:args.limit]
    print(f"  todo: {len(todo):,} symbols ({len(stale):,} stale > {args.max_age_days}d)",
          file=sys.stderr)

    if not todo and not args.refresh:
        print("nothing to fetch", file=sys.stderr)
        return

    # keep the FRESH cached rows; stale ones are replaced by the refetch
    results = ([r for s, r in existing.items() if s not in stale]
               if not args.refresh else [])
    failed = 0
    start = time.time()

    def write_partial():
        if not results:
            return
        out = pd.DataFrame(results)
        tmp = args.out + ".tmp"
        out.to_csv(tmp, index=False)
        os.replace(tmp, args.out)

    # Process in batches so a single bad symbol can't stall the pipeline
    BATCH = 500
    for batch_start in range(0, len(todo), BATCH):
        batch = todo[batch_start:batch_start + BATCH]
        with ThreadPoolExecutor(max_workers=args.workers) as ex:
            futs = {ex.submit(fetch_chart, s): s for s in batch}
            for fut in as_completed(futs, timeout=120):
                sym = futs[fut]
                try:
                    r = fut.result(timeout=30)
                except Exception:
                    r = None
                if r is not None:
                    results.append(r)
                else:
                    failed += 1
        # Per-batch progress + checkpoint
        done_so_far = batch_start + len(batch)
        rate = done_so_far / max(1.0, time.time() - start)
        eta = (len(todo) - done_so_far) / rate if rate else 0
        print(f"  {done_so_far:,}/{len(todo):,}  ok={done_so_far - failed} fail={failed}  "
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
