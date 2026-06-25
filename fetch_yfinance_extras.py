"""Fetch high-value yfinance endpoints not previously cached.

Adds five new per-ticker caches (one parquet each), per the YFINANCE_REFERENCE
audit:

  *  growth_estimates         — 5-year consensus growth + peer comparisons
  *  analyst_price_targets    — current/mean/low/high target prices
  *  insider_purchases        — net insider buy/sell over the last 6 months
  *  recommendations_summary  — broker rating bucket (strongBuy/buy/hold/sell)
  *  earnings_estimate        — next-Q and next-Y consensus EPS

Each row is keyed on `<safe_ticker>__<slot>.parquet`. A `<slot>.dead` sentinel
is written when an endpoint legitimately returns nothing — so future runs
don't re-fetch known empties.

Run pattern matches fetch_all_deep.py: chunked, time-boxed, resumable. Default
chunk targets ~9 min of inline runtime, with snapshot pushes between chunks.
"""
from __future__ import annotations

import argparse
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pandas as pd
import yfinance as yf

CACHE = Path('.cache/yf')
CACHE.mkdir(parents=True, exist_ok=True)

SLOTS = (
    'growth_estimates',
    'analyst_price_targets',
    'insider_purchases',
    'recommendations_summary',
    'earnings_estimate',
)


def _safe(t: str) -> str:
    return ''.join(c if c.isalnum() or c in '-_' else '_' for c in t)


def _outpath(t: str, slot: str) -> Path:
    return CACHE / f'{_safe(t)}__{slot}.parquet'


def _deadpath(t: str, slot: str) -> Path:
    return CACHE / f'{_safe(t)}__{slot}.dead'


def _missing(cache_key: str) -> list[str]:
    """Return slots that have neither a parquet nor a .dead sentinel.
    Operates on the cache_key (on-disk name), not the live ticker symbol."""
    out = []
    for s in SLOTS:
        if _outpath(cache_key, s).exists() or _deadpath(cache_key, s).exists():
            continue
        out.append(s)
    return out


def _to_df(obj) -> pd.DataFrame | None:
    """Normalise the various return shapes yfinance produces (DataFrame,
    Series, dict) to a single-row DataFrame writable as parquet."""
    if obj is None:
        return None
    if isinstance(obj, pd.DataFrame):
        if obj.empty:
            return None
        d = obj.copy()
        d.index = d.index.astype(str)
        d.columns = [str(c) for c in d.columns]
        return d
    if isinstance(obj, pd.Series):
        if obj.empty:
            return None
        d = obj.to_frame().T
        d.columns = [str(c) for c in d.columns]
        return d
    if isinstance(obj, dict):
        if not obj:
            return None
        return pd.DataFrame([{str(k): v for k, v in obj.items()}])
    return None


def fetch_one(cache_key: str, ticker_symbol: str | None = None) -> dict[str, str]:
    """Fetch every missing slot for one ticker. `cache_key` is the on-disk
    name (used to choose the output filename); `ticker_symbol` is the real
    symbol passed to yfinance (defaults to cache_key for plain US tickers).
    Returns a per-slot status: 'ok' | 'empty' | 'fetch_error'."""
    if ticker_symbol is None:
        ticker_symbol = _cache_key_to_ticker(cache_key)
    todo = _missing(cache_key)
    if not todo:
        return {s: 'cached' for s in SLOTS}
    results: dict[str, str] = {}
    try:
        t = yf.Ticker(ticker_symbol)
    except Exception:
        for s in todo:
            results[s] = 'fetch_error'
        return results

    for slot in todo:
        try:
            obj = getattr(t, slot)
        except Exception:
            results[slot] = 'fetch_error'
            continue
        df = _to_df(obj)
        if df is None:
            _deadpath(cache_key, slot).touch()
            results[slot] = 'empty'
            continue
        try:
            df.to_parquet(_outpath(cache_key, slot), compression='snappy')
            results[slot] = 'ok'
        except Exception:
            try:
                df2 = df.astype(str)
                df2.to_parquet(_outpath(cache_key, slot), compression='snappy')
                results[slot] = 'ok'
            except Exception:
                _deadpath(cache_key, slot).touch()
                results[slot] = 'fetch_error'
    return results


# Region-suffix mapping — recovers the original ticker (e.g. 000955.SZ) from
# the on-disk cache key (000955_SZ), which encodes "." as "_". Keep in sync
# with the same map in growth_adj_value.py.
_KNOWN_SUFFIXES = {
    'T','L','DE','F','PA','TO','V','AX','SW','MI','AS','MC','ST','OL','CO','BR',
    'HE','IR','VI','LS','AT','KS','KQ','HK','TW','TWO','SI','NZ','TA','SS','SZ',
    'NS','BO','SA','MX','JO','IS','BK','JK',
}

def _cache_key_to_ticker(key: str) -> str:
    """Reverse the cache-name → symbol mapping. The on-disk name encodes
    everything that isn't [A-Za-z0-9_-] (mainly '.') as '_'. We can recover
    `<head>.<suffix>` when `<suffix>` is a known regional exchange suffix.
    Tickers without a regional suffix are returned unchanged."""
    if '_' in key:
        head, _, tail = key.rpartition('_')
        if tail in _KNOWN_SUFFIXES:
            return f'{head}.{tail}'
    return key


def universe_tickers() -> list[tuple[str, str]]:
    """Return (cache_key, ticker_symbol) pairs for every ticker that has an
    info_metrics parquet. The cache_key is the stable on-disk filename;
    the ticker_symbol is what we pass to yf.Ticker.

    Ordering: US tickers first (highest analyst-coverage payoff), then
    other markets sorted alphabetically by region suffix. Non-US analyst
    endpoints mostly return empty, so doing US first means we get all the
    actionable data within the first ~2500 fetches."""
    keys = sorted({p.name.split('__')[0]
                   for p in CACHE.glob('*__info_metrics.parquet')})
    us, other = [], []
    for k in keys:
        sym = _cache_key_to_ticker(k)
        if '.' in sym:
            other.append((k, sym))
        else:
            us.append((k, sym))
    return us + other


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--max-tickers', type=int, default=12000,
                    help='Cap per chunk.')
    ap.add_argument('--sleep', type=float, default=0.05,
                    help='Per-worker sleep — small since N workers in parallel.')
    ap.add_argument('--workers', type=int, default=8,
                    help='Concurrent yfinance sessions.')
    ap.add_argument('--us-only', action='store_true', default=True,
                    help='Skip non-US tickers (yfinance has no analyst data for them).')
    ap.add_argument('--include-non-us', dest='us_only', action='store_false')
    ap.add_argument('--progress-every', type=int, default=200)
    args = ap.parse_args()

    universe = universe_tickers()
    # SKIP non-US tickers — yfinance has zero analyst/insider coverage for them
    # (verified empirically: ~50% of fetch time was wasted on Chinese/Korean
    # tickers that always return empty + slow timeouts). The earlier full-
    # universe pass already wrote dead sentinels for the few that had data.
    if args.us_only:
        universe = [(k, s) for k, s in universe if '.' not in s]
    todo = [(k, s) for k, s in universe if _missing(k)]
    print(f'Universe size: {len(universe):,} tickers ({"US-only" if args.us_only else "all"})')
    print(f'Tickers with missing extras slots: {len(todo):,}')
    if not todo:
        print('All caught up.')
        return

    target = todo[: args.max_tickers]
    t0 = time.time()
    n_ok = n_empty = n_err = 0
    counter_lock = threading.Lock()
    progress_counter = [0]

    def worker(item):
        nonlocal n_ok, n_empty, n_err
        key, sym = item
        r = fetch_one(key, sym)
        with counter_lock:
            progress_counter[0] += 1
            i = progress_counter[0]
            for slot, status in r.items():
                if status == 'ok': n_ok += 1
                elif status == 'empty': n_empty += 1
                elif status == 'fetch_error': n_err += 1
            if i % args.progress_every == 0:
                elapsed = time.time() - t0
                rate = i / elapsed if elapsed > 0 else 0
                eta_min = (len(target) - i) / rate / 60 if rate > 0 else float('inf')
                print(f'  {i:>5,}/{len(target):,}  ok={n_ok:,} empty={n_empty:,} '
                      f'err={n_err:,} rate={rate:.1f}/s eta={eta_min:.0f}min',
                      flush=True)
        time.sleep(args.sleep)

    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        list(ex.map(worker, target))

    print(f'\nFinal: ok={n_ok:,} empty={n_empty:,} err={n_err:,} '
          f'across {len(target):,} tickers')


if __name__ == '__main__':
    main()
