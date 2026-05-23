"""Universe cache filler.

Fetches the four pieces of per-ticker data needed by the screener stack:

  1. Daily price history (1Y minimum, 5Y if available) -> __price.parquet
  2. Yahoo Ticker.info snapshot                        -> __info_metrics.parquet
  3. Quarterly EPS history (get_earnings_dates)        -> __eps_history.parquet
  4. Quarterly income_stmt & cashflow (shallow)        -> __income.parquet, __cashflow.parquet

For each ticker, skips any of the four that are already cached. Logs the
delta. Designed to be re-runnable -- just adds whatever's missing.

Default universe: US Mid + Small + Micro + Nano (clean tickers from
financedatabase) UNION any ticker that's already partially cached. That
fills both gaps:

  1. Names with EPS/info but no prices                 -- bottleneck of
                                                           price-based screeners
  2. Names that financedatabase has but we haven't touched at all.

Run:
    python fetch_universe.py --workers 6 --request-sleep 0.4
"""
from __future__ import annotations
import argparse, time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional

import numpy as np, pandas as pd, yfinance as yf

CACHE = Path('.cache/yf')
CACHE.mkdir(parents=True, exist_ok=True)


def _safe(t: str) -> str:
    return ''.join(c if c.isalnum() or c in '-_' else '_' for c in t)


def _cache_paths(ticker: str) -> dict[str, Path]:
    s = _safe(ticker)
    return {
        'price':        CACHE / f'{s}__price.parquet',
        'info':         CACHE / f'{s}__info_metrics.parquet',
        'eps_history':  CACHE / f'{s}__eps_history.parquet',
        'income':       CACHE / f'{s}__income.parquet',
        'cashflow':     CACHE / f'{s}__cashflow.parquet',
    }


def has_nonempty(p: Path) -> bool:
    if not p.exists(): return False
    try:
        df = pd.read_parquet(p)
        return not df.empty
    except Exception:
        return False


def fetch_with_timeout(fn, *args, timeout: float = 20.0, **kwargs):
    """Run fn(*args) in a daemon sub-thread with a hard wall-clock cap."""
    import concurrent.futures as _cf
    with _cf.ThreadPoolExecutor(max_workers=1, thread_name_prefix='fetch') as ex:
        fut = ex.submit(fn, *args, **kwargs)
        try:
            return fut.result(timeout=timeout)
        except _cf.TimeoutError:
            ex.shutdown(wait=False, cancel_futures=True)
            return None
        except Exception:
            return None


def fetch_one(ticker: str) -> dict:
    """Fetch any missing data for a ticker. Returns a dict of which slots
    were newly populated (skip / fetched / failed)."""
    paths = _cache_paths(ticker)
    status: dict[str, str] = {k: 'skip' for k in paths}

    needs_anything = any(not has_nonempty(p) for p in paths.values())
    if not needs_anything:
        return {**status, '_ticker': ticker, '_all_cached': True}

    # Create the Ticker once, reuse across endpoints
    try:
        t = yf.Ticker(ticker)
    except Exception as exc:
        return {**status, '_ticker': ticker, '_error': f'ticker init: {exc}'}

    # ---- 1. price (1y; the 200w SMA needs ~5y but most price-based screeners
    # only require 1Y; we save Close+Volume; period='5y' to be future-proof)
    if not has_nonempty(paths['price']):
        try:
            hist = fetch_with_timeout(t.history, period='5y', auto_adjust=True, timeout=25)
            if hist is not None and not hist.empty:
                idx = pd.to_datetime(hist.index)
                if getattr(idx, 'tz', None) is not None:
                    idx = idx.tz_localize(None)
                hist.index = idx
                cols = [c for c in ('Close', 'Volume') if c in hist.columns]
                sub = hist[cols].dropna(subset=['Close']) if 'Close' in cols else pd.DataFrame()
                if not sub.empty:
                    sub.to_parquet(paths['price'])
                    status['price'] = 'fetched'
                else:
                    status['price'] = 'empty'
            else:
                status['price'] = 'empty'
        except Exception as exc:
            status['price'] = f'err:{type(exc).__name__}'

    # ---- 2. info ----
    if not has_nonempty(paths['info']):
        try:
            info = fetch_with_timeout(lambda: t.info or {}, timeout=20)
            if info:
                keep = ('priceToBook','priceToSalesTrailing12Months','trailingPE',
                        'forwardPE','enterpriseToEbitda','enterpriseToRevenue',
                        'marketCap','sharesOutstanding','floatShares',
                        'currentPrice','previousClose','bookValue','trailingEps',
                        'totalRevenue','profitMargins','operatingMargins','grossMargins',
                        'returnOnEquity','returnOnAssets','enterpriseValue',
                        'totalCash','totalDebt','totalCashPerShare','currentRatio',
                        'quickRatio','debtToEquity','longName','shortName',
                        'sector','industry','currency','country')
                row = {}
                for k in keep:
                    v = info.get(k)
                    if v is None: continue
                    if isinstance(v, (int, float, str)): row[k] = v
                    else:
                        try: row[k] = float(v)
                        except (TypeError, ValueError): pass
                if row:
                    pd.DataFrame([row]).to_parquet(paths['info'])
                    status['info'] = 'fetched'
                else:
                    status['info'] = 'empty'
        except Exception as exc:
            status['info'] = f'err:{type(exc).__name__}'

    # ---- 3. eps_history (get_earnings_dates) ----
    if not has_nonempty(paths['eps_history']):
        try:
            ed = fetch_with_timeout(t.get_earnings_dates, limit=80, timeout=20)
            if ed is not None and not ed.empty and 'Reported EPS' in ed.columns:
                df = ed[['Reported EPS']].copy()
                idx = pd.to_datetime(df.index)
                if getattr(idx, 'tz', None) is not None:
                    idx = idx.tz_localize(None)
                df.index = idx
                df = df.sort_index().dropna(subset=['Reported EPS'])
                if not df.empty:
                    df.to_parquet(paths['eps_history'])
                    status['eps_history'] = 'fetched'
                else:
                    status['eps_history'] = 'empty'
            else:
                status['eps_history'] = 'empty'
        except Exception as exc:
            status['eps_history'] = f'err:{type(exc).__name__}'

    # ---- 4 + 5: quarterly_income_stmt, quarterly_cashflow ----
    for kind, attr in (('income', 'quarterly_income_stmt'),
                        ('cashflow', 'quarterly_cashflow')):
        if not has_nonempty(paths[kind]):
            try:
                df = fetch_with_timeout(getattr, t, attr, timeout=20)
                if df is not None and isinstance(df, pd.DataFrame) and not df.empty:
                    df.to_parquet(paths[kind])
                    status[kind] = 'fetched'
                else:
                    status[kind] = 'empty'
            except Exception as exc:
                status[kind] = f'err:{type(exc).__name__}'

    return {**status, '_ticker': ticker, '_all_cached': False}


def build_universe() -> list[str]:
    """US Mid+Small+Micro+Nano clean tickers from financedatabase, UNION any
    ticker already partially in cache."""
    import financedatabase as fd
    e = fd.Equities()
    parts = []
    for cap in ('Mid Cap', 'Small Cap', 'Micro Cap', 'Nano Cap'):
        try:
            df = e.select(country='United States', market_cap=cap)
            parts.append(df)
        except Exception: pass
    fd_uni = pd.concat(parts) if parts else pd.DataFrame()
    if not fd_uni.empty:
        syms = fd_uni.index.astype(str)
        fd_uni = fd_uni[syms.str.match(r'^[A-Z][A-Z]{0,4}$')]
    fd_tickers = set(fd_uni.index.astype(str))
    print(f"financedatabase US Mid+Small+Micro+Nano clean: {len(fd_tickers)}")

    # All cached tickers regardless of which slot they're in
    cached = set()
    for kind in ('price','info_metrics','eps_history','income','cashflow'):
        for f in CACHE.glob(f'*__{kind}.parquet'):
            cached.add(f.name.split('__')[0])
    print(f"any cached: {len(cached)}")

    # Reverse safe-name mapping isn't perfect (CACHE keys are safe names),
    # but most US tickers are ASCII alpha so safe_name == ticker. Just union.
    union = fd_tickers | cached
    print(f"union: {len(union)}")
    # Strip caret-style index tickers (we don't want to refetch ^GSPC etc.)
    union = {t for t in union if not t.startswith('_') and not t.startswith('^')}
    return sorted(union)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--workers', type=int, default=6)
    ap.add_argument('--request-sleep', type=float, default=0.4)
    ap.add_argument('--tickers', nargs='+', default=None,
                    help='override: fetch only these tickers')
    ap.add_argument('--max', type=int, default=None,
                    help='limit total tickers (for testing)')
    args = ap.parse_args()

    if args.tickers:
        universe = args.tickers
    else:
        universe = build_universe()
    if args.max:
        universe = universe[:args.max]
    print(f"Universe to process: {len(universe)}")

    results = []
    t0 = time.time()
    fetched_counts = {'price':0,'info':0,'eps_history':0,'income':0,'cashflow':0}
    skipped_all = 0
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futs = {pool.submit(fetch_one, t): t for t in universe}
        for i, fut in enumerate(as_completed(futs), 1):
            try:
                r = fut.result(timeout=180)
            except Exception as exc:
                r = {'_ticker': futs[fut], '_error': f'worker exc: {exc}'}
            results.append(r)
            if r.get('_all_cached'):
                skipped_all += 1
            for k in fetched_counts:
                if r.get(k) == 'fetched':
                    fetched_counts[k] += 1
            if i % 100 == 0 or i == len(universe):
                el = time.time() - t0
                rate = i/el if el>0 else 0
                eta_sec = (len(universe)-i)/rate if rate>0 else 0
                print(f"  {i}/{len(universe)}  ({rate:.1f}/s)  "
                      f"all-cached={skipped_all}  fetched={fetched_counts}  "
                      f"eta={eta_sec/60:.0f}min")
            time.sleep(args.request_sleep / args.workers)
    print(f"\nDone in {time.time()-t0:.0f}s")
    print(f"All-cached (skipped): {skipped_all}")
    print(f"New fetches:  {fetched_counts}")
    # Save log
    log = pd.DataFrame([{k: v for k, v in r.items()} for r in results])
    log_path = Path('fetch_universe.log.csv')
    log.to_csv(log_path, index=False)
    print(f"Per-ticker log: {log_path}")


if __name__ == '__main__':
    main()
