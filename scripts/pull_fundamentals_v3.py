#!/usr/bin/env python3
"""Fundamentals puller v3 — fills EV multiple gaps from financial statements.

When yfinance .info returns null for ev_ebit / ev_ebitda / ev_sales (very
common for non-US tickers and many US small-caps too), this puller falls
back to computing them from the income statement and balance sheet:

    EBIT       = Operating Income (from income statement)
    EBITDA     = EBIT + D&A (from cashflow statement)
    EV         = mktCap + totalDebt - cash
    EV/EBIT    = EV / EBIT(ttm)
    EV/EBITDA  = EV / EBITDA(ttm)
    EV/Sales   = EV / Revenue(ttm)

Multi-worker (4 threads default) with global token-bucket rate limiter.
Resumes from existing output (--resume).
"""
import argparse, sys, time, threading, warnings, os
from concurrent.futures import ThreadPoolExecutor, as_completed
import pandas as pd
import numpy as np
import sys as _sys, os as _os; _sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__))); import yf_patch  # noqa
import yfinance as yf

warnings.filterwarnings('ignore')

class RateLimiter:
    def __init__(self, rate_per_sec):
        self.interval = 1.0 / rate_per_sec
        self.lock = threading.Lock()
        self.next_ok = 0.0
    def wait(self):
        with self.lock:
            now = time.time()
            if now < self.next_ok:
                time.sleep(self.next_ok - now)
                now = time.time()
            self.next_ok = now + self.interval


def _row_sum(df, candidates):
    """Sum the first row found from any of `candidates` keys."""
    if df is None or df.empty: return None
    for k in candidates:
        if k in df.index:
            try:
                vals = pd.to_numeric(df.loc[k], errors='coerce').dropna()
                if len(vals): return float(vals.iloc[0])
            except Exception: pass
    return None


def fetch_one(t, limiter, max_retries=3):
    for attempt in range(max_retries):
        limiter.wait()
        try:
            tk = yf.Ticker(t)
            info = tk.info or {}
            if not info.get('marketCap') and not info.get('totalRevenue'):
                return None

            mcap = info.get('marketCap') or 0
            debt = info.get('totalDebt') or 0
            cash = info.get('totalCash') or 0
            ev = (mcap + debt - cash) if mcap else None
            fcf = info.get('freeCashflow') or 0
            ebitda_info = info.get('ebitda') or 0
            ebit_info = info.get('ebit')
            rev_info = info.get('totalRevenue')

            # ── Fall back to financial statements when info is missing ──
            ebit_calc = ebitda_calc = rev_calc = da_calc = None
            try:
                fin = tk.financials
                if fin is not None and not fin.empty:
                    ebit_calc = _row_sum(fin, ['Operating Income','Ebit','EBIT','Operating Income Loss'])
                    rev_calc  = _row_sum(fin, ['Total Revenue','Revenue','Total Revenues'])
                cf = tk.cashflow
                if cf is not None and not cf.empty:
                    da_calc = _row_sum(cf, ['Depreciation','Depreciation And Amortization','Depreciation Amortization Depletion'])
            except Exception:
                pass

            ebit = ebit_info if ebit_info else ebit_calc
            ebitda = ebitda_info if ebitda_info else (
                (ebit + (da_calc or 0)) if (ebit and da_calc) else None
            )
            rev = rev_info if rev_info else rev_calc

            ev_ebit = (ev / ebit) if (ev and ebit and ebit != 0) else None
            ev_ebitda = (ev / ebitda) if (ev and ebitda and ebitda != 0) else None
            ev_sales = (ev / rev) if (ev and rev and rev != 0) else None

            return {
                'ticker': t,
                'name': info.get('shortName'),
                'industry': info.get('industry'),
                'sector': info.get('sector'),
                'currency': info.get('currency'),
                'mktCap': mcap, 'ev': ev,
                'rev': rev, 'rev_source': 'info' if rev_info else ('calc' if rev_calc else None),
                'gm': info.get('grossMargins'),
                'opm': info.get('operatingMargins'),
                'roe': info.get('returnOnEquity'),
                'roa': info.get('returnOnAssets'),
                'rev_g': info.get('revenueGrowth'),
                'earn_g': info.get('earningsGrowth'),
                'fcf': fcf,
                'fcf_yield': (fcf / mcap) if (mcap and fcf) else None,
                'ebitda': ebitda,
                'ebitda_source': 'info' if ebitda_info else ('calc' if ebitda else None),
                'ebit': ebit,
                'ebit_source': 'info' if ebit_info else ('calc' if ebit else None),
                'ev_ebitda': ev_ebitda,
                'ev_ebit': ev_ebit,
                'ev_sales': ev_sales,
                'pe': info.get('trailingPE'),
                'fpe': info.get('forwardPE'),
                'pb': info.get('priceToBook'),
                'ps': info.get('priceToSalesTrailing12Months'),
                'net_debt': debt - cash,
                'nd_ebitda': ((debt - cash) / ebitda) if ebitda and ebitda != 0 else None,
                'insiders': info.get('heldPercentInsiders'),
                'div_yield': info.get('dividendYield'),
                'beta': info.get('beta'),
            }
        except Exception as e:
            msg = str(e)[:80]
            if '429' in msg or 'rate' in msg.lower() or 'Too Many' in msg:
                time.sleep(2 ** attempt * 3)
                continue
            return None
    return None


ap = argparse.ArgumentParser()
ap.add_argument('--universe', required=True)
ap.add_argument('--out', required=True)
ap.add_argument('--workers', type=int, default=4)
ap.add_argument('--rate', type=float, default=0.5)
ap.add_argument('--checkpoint', type=int, default=100)
ap.add_argument('--resume', action='store_true')
args = ap.parse_args()

uni = pd.read_csv(args.universe)
syms = uni['ticker'].dropna().astype(str).unique().tolist()

already = set(); existing = []
if args.resume and os.path.exists(args.out) and os.path.getsize(args.out) > 10:
    try:
        prev = pd.read_csv(args.out)
        already = set(prev['ticker'].dropna().astype(str).tolist())
        existing = prev.to_dict('records')
        print(f"[v3] resume: {len(already)} done, skipping", file=sys.stderr)
    except Exception: pass

todo = [t for t in syms if t not in already]
print(f"[v3] {len(todo)} tickers · {args.workers} workers · {args.rate} req/s", file=sys.stderr)

limiter = RateLimiter(args.rate)
rows = list(existing); lock = threading.Lock(); done = [0]; start = time.time()

def task(t):
    r = fetch_one(t, limiter)
    with lock:
        done[0] += 1
        if r: rows.append(r)
        if done[0] % args.checkpoint == 0:
            pd.DataFrame(rows).to_csv(args.out, index=False)
            elapsed = time.time() - start
            rate = done[0] / max(elapsed, 0.1)
            eta_min = (len(todo) - done[0]) / max(rate, 0.01) / 60
            print(f"[v3] {done[0]}/{len(todo)}  kept {len(rows)-len(existing)}  rate {rate:.2f}/s  ETA {eta_min:.1f}m", file=sys.stderr)

with ThreadPoolExecutor(max_workers=args.workers) as ex:
    futures = [ex.submit(task, t) for t in todo]
    for _ in as_completed(futures): pass

pd.DataFrame(rows).to_csv(args.out, index=False)

# Report fill rates
df = pd.DataFrame(rows)
if len(df):
    print(f"[v3] DONE: {len(df)} rows", file=sys.stderr)
    for col in ['ev_ebit','ev_ebitda','ev_sales','pe','pb']:
        if col in df.columns:
            n = df[col].notna().sum()
            print(f"  {col}: {n}/{len(df)} ({n/len(df)*100:.0f}%)", file=sys.stderr)
    for col in ['ebit_source','ebitda_source','rev_source']:
        if col in df.columns:
            print(f"  {col}: {df[col].value_counts().to_dict()}", file=sys.stderr)
