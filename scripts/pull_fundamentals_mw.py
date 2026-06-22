#!/usr/bin/env python3
"""Multi-worker fundamentals puller with global rate limit + retry/backoff.

Uses threading.ThreadPoolExecutor with a token-bucket rate limiter shared
across workers. Resumes from existing output (skips already-pulled tickers).

Designed for yfinance: tested-safe ~40 req/min total across 4 workers.

Usage:
    python3 pull_fundamentals_mw.py \\
        --universe path/to/uni.csv --out path/to/fund.csv \\
        --workers 4 --rate 0.7 --resume
"""
import argparse, sys, time, threading, warnings, os
from concurrent.futures import ThreadPoolExecutor, as_completed
import pandas as pd
import yfinance as yf

warnings.filterwarnings('ignore')

class RateLimiter:
    """Simple token bucket — limits combined req/sec across all workers."""
    def __init__(self, rate_per_sec):
        self.interval = 1.0 / rate_per_sec
        self.lock = threading.Lock()
        self.next_ok = 0.0
    def wait(self):
        with self.lock:
            now = time.time()
            if now < self.next_ok:
                wait = self.next_ok - now
                time.sleep(wait)
                now = time.time()
            self.next_ok = now + self.interval

def fetch_one(t, limiter, max_retries=3):
    for attempt in range(max_retries):
        limiter.wait()
        try:
            info = yf.Ticker(t).info
            if not info or (not info.get('totalRevenue') and not info.get('marketCap')):
                return None
            mcap = info.get('marketCap') or 0
            debt = info.get('totalDebt') or 0
            cash = info.get('totalCash') or 0
            ev = (mcap + debt - cash) if mcap else None
            fcf = info.get('freeCashflow') or 0
            ebitda = info.get('ebitda') or 0
            ebit = info.get('ebit')
            return {
                'ticker': t,
                'name': info.get('shortName'),
                'industry': info.get('industry'),
                'sector': info.get('sector'),
                'currency': info.get('currency'),
                'mktCap': mcap, 'ev': ev,
                'rev': info.get('totalRevenue'),
                'gm': info.get('grossMargins'),
                'opm': info.get('operatingMargins'),
                'roe': info.get('returnOnEquity'),
                'roa': info.get('returnOnAssets'),
                'rev_g': info.get('revenueGrowth'),
                'earn_g': info.get('earningsGrowth'),
                'fcf': fcf,
                'fcf_yield': (fcf / mcap) if (mcap and fcf) else None,
                'ebitda': ebitda,
                'ev_ebitda': (ev / ebitda) if (ebitda and ev) else None,
                'ev_ebit': (ev / ebit) if (ebit and ev) else None,
                'pe': info.get('trailingPE'),
                'fpe': info.get('forwardPE'),
                'pb': info.get('priceToBook'),
                'ps': info.get('priceToSalesTrailing12Months'),
                'net_debt': debt - cash,
                'nd_ebitda': ((debt - cash) / ebitda) if ebitda else None,
                'insiders': info.get('heldPercentInsiders'),
                'div_yield': info.get('dividendYield'),
                'beta': info.get('beta'),
            }
        except Exception as e:
            msg = str(e)[:80]
            if '429' in msg or 'rate' in msg.lower() or 'Too Many' in msg:
                # backoff
                time.sleep(2 ** attempt * 3)
                continue
            return None
    return None

ap = argparse.ArgumentParser()
ap.add_argument('--universe', required=True)
ap.add_argument('--out', required=True)
ap.add_argument('--workers', type=int, default=4)
ap.add_argument('--rate', type=float, default=0.7, help='Global req/sec ceiling')
ap.add_argument('--checkpoint', type=int, default=100)
ap.add_argument('--resume', action='store_true', help='Skip tickers already in --out')
args = ap.parse_args()

uni = pd.read_csv(args.universe)
syms = uni['ticker'].dropna().astype(str).unique().tolist()

# Resume: skip already-done
already = set()
existing_rows = []
if args.resume and os.path.exists(args.out) and os.path.getsize(args.out) > 10:
    try:
        prev = pd.read_csv(args.out)
        already = set(prev['ticker'].dropna().astype(str).tolist())
        existing_rows = prev.to_dict('records')
        print(f"[mw] resume: {len(already)} already done, skipping", file=sys.stderr)
    except Exception:
        pass

to_fetch = [t for t in syms if t not in already]
print(f"[mw] {len(to_fetch)} tickers to fetch with {args.workers} workers @ {args.rate} req/s", file=sys.stderr)

limiter = RateLimiter(args.rate)
rows = list(existing_rows)
lock = threading.Lock()
done = [0]
start = time.time()

def task(t):
    r = fetch_one(t, limiter)
    with lock:
        done[0] += 1
        if r: rows.append(r)
        if done[0] % args.checkpoint == 0:
            pd.DataFrame(rows).to_csv(args.out, index=False)
            elapsed = time.time() - start
            rate = done[0] / elapsed
            eta_min = (len(to_fetch) - done[0]) / max(rate, 0.01) / 60
            print(f"[mw] {done[0]}/{len(to_fetch)}  kept {len(rows)-len(existing_rows)}  "
                  f"rate {rate:.2f}/s  ETA {eta_min:.1f}m", file=sys.stderr)

with ThreadPoolExecutor(max_workers=args.workers) as ex:
    futures = [ex.submit(task, t) for t in to_fetch]
    for _ in as_completed(futures):
        pass

pd.DataFrame(rows).to_csv(args.out, index=False)
print(f"[mw] DONE: {len(rows)} total rows ({len(rows)-len(existing_rows)} new) → {args.out}", file=sys.stderr)
