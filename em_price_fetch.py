"""Fetch daily price history for names that have fundamentals but no prices.

The EM/API backfill (em_expansion_fetch) filled ~7.4k emerging-market names
with real valuations (info_metrics) but no price history — and the price-based
creative screens (multiple/EV compression, operating & FCF leverage, FCF-yield
setup, 52-week-high, flat+inflection) build their universe from
`.cache/yf/*__price.parquet` and need >=260 daily closes. So those EM names,
though now valued, never reach the momentum/compression screens.

This fetches their price history via Yahoo's v8 chart endpoint (yahoo_session,
the warmed cookie+crumb client) and writes a `<key>__price.parquet` in the
exact schema load_price() expects: a Date index + OHLCV + Adj Close columns.
It unlocks the full workbook — the EM universe now flows into every tab, not
just the valuation composites.

Target = every ticker with a REAL info_metrics but no price parquet yet. The
original symbol is read from the info_metrics `_ticker` field (no fragile
safe-key → symbol reversal). Resumable via `__px_tried` sentinels; threaded on
one shared session (the API handles 20+ concurrent cleanly).
"""
from __future__ import annotations
import argparse, threading, time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import pandas as pd

import sys
sys.path.insert(0, str(Path(__file__).parent))
from yahoo_session import chart, get_session

CACHE = Path('.cache/yf')


def _safe(t: str) -> str:
    return ''.join(c if c.isalnum() or c in '-_' else '_' for c in t)


def _px_path(key: str) -> Path:
    return CACHE / f'{key}__price.parquet'


def _tried_path(key: str) -> Path:
    return CACHE / f'{key}__px_tried'


def pending() -> list[tuple[str, str]]:
    """(cache_key, symbol) for every real-info name lacking a price parquet."""
    out = []
    for p in CACHE.glob('*__info_metrics.parquet'):
        key = p.name.split('__')[0]
        if _px_path(key).exists() or _tried_path(key).exists():
            continue
        try:
            row = pd.read_parquet(p).iloc[0]
        except Exception:
            continue
        src = row.get('_source')
        if src == 'financedatabase_meta':
            continue   # metadata-only: Yahoo has no quote, so no prices either
        sym = row.get('_ticker') or key
        out.append((key, str(sym)))
    return out


def _to_price_df(d: dict) -> pd.DataFrame | None:
    """Build the load_price()-compatible frame from a chart() response."""
    ts = d.get('timestamp') or []
    close = d.get('close') or []
    if not ts or not close:
        return None
    idx = pd.to_datetime(ts, unit='s')
    cols = {'Open': d.get('open'), 'High': d.get('high'), 'Low': d.get('low'),
            'Close': close, 'Adj Close': d.get('adjclose') or close,
            'Volume': d.get('volume')}
    frame = {}
    for name, vals in cols.items():
        if vals and len(vals) == len(idx):
            frame[name] = vals
    if 'Close' not in frame:
        return None
    df = pd.DataFrame(frame, index=idx)
    df.index.name = 'Date'
    df = df[pd.to_numeric(df['Close'], errors='coerce').notna()]
    return df if len(df) >= 260 else (df if len(df) >= 60 else None)


def _process(key: str, sym: str, sess) -> str:
    try:
        d = chart(sym, '2y', '1d', sess)
        df = _to_price_df(d)
    except Exception:
        df = None
    result = 'empty'
    if df is not None and not df.empty:
        try:
            df.to_parquet(_px_path(key), compression='snappy')
            result = 'ok'
        except Exception:
            result = 'empty'
    try: _tried_path(key).touch()
    except Exception: pass
    return result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--workers', type=int, default=8)
    ap.add_argument('--max', type=int, default=40000)
    args = ap.parse_args()

    # Single-instance guard: parallel price fetchers would just contend.
    import fcntl
    lock = open(CACHE.parent / 'em_price.lock', 'w')
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        print('Another em_price instance holds the lock — exiting.', flush=True)
        return

    todo = pending()[:args.max]
    print(f'EM price fetch: {len(todo):,} names need price history, '
          f'{args.workers} workers', flush=True)
    if not todo:
        return
    sess = get_session()
    n_ok = n_empty = done = 0
    plock = threading.Lock()
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = [ex.submit(_process, k, s, sess) for k, s in todo]
        for fut in as_completed(futs):
            try:
                res = fut.result()
            except Exception:
                res = 'empty'
            with plock:
                done += 1
                if res == 'ok': n_ok += 1
                else: n_empty += 1
                if done % 200 == 0:
                    el = time.time() - t0
                    rate = done / el if el > 0 else 0
                    eta = (len(todo) - done) / rate / 60 if rate > 0 else 0
                    print(f'  {done:>6,}/{len(todo):,}  ok={n_ok:,} '
                          f'empty={n_empty:,} rate={rate:.1f}/s eta={eta:.0f}min',
                          flush=True)
    print(f'\nFinal: ok={n_ok:,} empty={n_empty:,} of {len(todo):,}', flush=True)


if __name__ == '__main__':
    main()
