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
import time
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


def _missing(ticker: str) -> list[str]:
    """Return slots that have neither a parquet nor a .dead sentinel."""
    out = []
    for s in SLOTS:
        if _outpath(ticker, s).exists() or _deadpath(ticker, s).exists():
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


def fetch_one(ticker: str) -> dict[str, str]:
    """Fetch every missing slot for one ticker. Returns a per-slot status:
    'ok', 'empty', 'fetch_error'."""
    todo = _missing(ticker)
    if not todo:
        return {s: 'cached' for s in SLOTS}
    results: dict[str, str] = {}
    try:
        t = yf.Ticker(ticker)
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
            _deadpath(ticker, slot).touch()
            results[slot] = 'empty'
            continue
        try:
            df.to_parquet(_outpath(ticker, slot), compression='snappy')
            results[slot] = 'ok'
        except Exception:
            # Schema-mismatch / unhashable columns -> stringify and retry
            try:
                df2 = df.astype(str)
                df2.to_parquet(_outpath(ticker, slot), compression='snappy')
                results[slot] = 'ok'
            except Exception:
                _deadpath(ticker, slot).touch()
                results[slot] = 'fetch_error'
    return results


def universe_tickers() -> list[str]:
    """Same definition as fetch_all_deep.py: every ticker that has an
    info_metrics parquet (i.e. lives in our screened universe)."""
    return sorted({p.name.split('__')[0]
                   for p in CACHE.glob('*__info_metrics.parquet')})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--max-tickers', type=int, default=2000,
                    help='Cap per chunk so we fit in the inline timeout.')
    ap.add_argument('--sleep', type=float, default=0.4,
                    help='Sleep between tickers (rate-limit friendly).')
    ap.add_argument('--progress-every', type=int, default=100)
    args = ap.parse_args()

    universe = universe_tickers()
    todo = [t for t in universe if _missing(t)]
    print(f'Universe size: {len(universe):,} tickers')
    print(f'Tickers with missing extras slots: {len(todo):,}')
    if not todo:
        print('All caught up.')
        return

    target = todo[: args.max_tickers]
    t0 = time.time()
    n_ok = n_empty = n_err = 0
    for i, tk in enumerate(target, 1):
        r = fetch_one(tk)
        for slot, status in r.items():
            if status == 'ok':
                n_ok += 1
            elif status == 'empty':
                n_empty += 1
            elif status == 'fetch_error':
                n_err += 1
        if i % args.progress_every == 0:
            elapsed = time.time() - t0
            rate = i / elapsed if elapsed > 0 else 0
            eta_min = (len(target) - i) / rate / 60 if rate > 0 else float('inf')
            print(f'  {i:>5,}/{len(target):,}  ok={n_ok:,}  empty={n_empty:,}  '
                  f'err={n_err:,}  rate={rate:.1f}/s  eta={eta_min:.0f}min')
        time.sleep(args.sleep)

    print(f'\nFinal: ok={n_ok:,} empty={n_empty:,} err={n_err:,} '
          f'across {len(target):,} tickers')


if __name__ == '__main__':
    main()
