"""EM / additional-market universe expansion.

Widens the universe into emerging + frontier markets (China A-shares, India,
Brazil, Thailand, Indonesia, Turkey, Mexico, ...) using financedatabase for
the target list + static metadata, and Yahoo's quoteSummary API for live
valuation/price.

Two-tier fill so EVERY name adds breadth:
  1. Try Yahoo's quoteSummary API (via yahoo_session, the warmed cookie+crumb
     client) -> full valuation (EV/EBITDA, P/E, P/B, FCF, margins, growth,
     52-week change) whenever Yahoo serves the ticker.
  2. On genuine no-data / 404, write a METADATA-ONLY info_metrics from the
     financedatabase row (company, sector, industry, country, market-cap
     tier, currency). The name then counts for sector/country/breadth views
     even though Yahoo has no quote for it.

THE FIX: the old path scraped finance.yahoo.com HTML at ~1/s because we
believed query1/query2 were IP-rate-limited. They are not — they require a
warmed A1/A3/A1S cookie session + a crumb token (see yahoo_session.py). With
those, the same shared IP sustains ~18 req/s with zero failures. This fetcher
now uses that API path directly, so the 9k metadata-only rows backfill with
real valuations in minutes instead of hours.

Resumable via __em_api_tried sentinels — a re-run continues where it stopped,
safe across container reboots. A single-instance flock guard prevents parallel
copies from stepping on each other.
"""
from __future__ import annotations
import argparse, threading, time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import pandas as pd

import sys
sys.path.insert(0, str(Path(__file__).parent))
from yahoo_html_fetcher import _safe, YF_CACHE
from yahoo_session import fetch_info, get_session

TARGETS = Path('.cache/expansion/em_targets.csv')

# financedatabase market-cap tier -> a representative USD figure, so the
# metadata-only rows still sort/filter sanely in mcap-based views. Rough
# midpoints; real value overwrites this whenever Yahoo serves the ticker.
_TIER_MCAP = {
    'Large Cap': 12e9, 'Mid Cap': 4e9, 'Small Cap': 800e6,
    'Micro Cap': 150e6, 'Nano Cap': 30e6,
}

# Fields whose presence means "Yahoo actually served a real quote".
_REAL_KEYS = ('marketCap', 'trailingPE', 'priceToBook', 'enterpriseToEbitda',
              'enterpriseToRevenue', 'regularMarketPrice', 'currentPrice',
              'totalRevenue', 'freeCashflow')


def _api_tried(safe: str) -> Path:
    return YF_CACHE / f'{safe}__em_api_tried'


def _load_targets() -> pd.DataFrame:
    if not TARGETS.exists():
        return pd.DataFrame()
    return pd.read_csv(TARGETS)


def _metadata_record(row) -> dict:
    """A minimal info_metrics-shaped dict from the financedatabase row."""
    tier = str(row.get('market_cap_tier') or '')
    return {
        '_ticker': row['symbol'], '_source': 'financedatabase_meta',
        '_fetched_at': None,
        'longName': str(row.get('company') or '')[:60],
        'sector': row.get('sector') or '',
        'industry': row.get('industry') or '',
        'country': row.get('country') or '',
        'currency': row.get('currency') or '',
        'market_cap_tier': tier,
        'marketCap': _TIER_MCAP.get(tier),   # rough; real overwrites on Yahoo hit
    }


def pending() -> pd.DataFrame:
    df = _load_targets()
    if df.empty:
        return df
    keep = []
    for _, row in df.iterrows():
        safe = _safe(row['symbol'])
        # Skip if we already have REAL (non-meta) info from any source.
        p = YF_CACHE / f'{safe}__info_metrics.parquet'
        if p.exists():
            try:
                src = pd.read_parquet(p, columns=['_source']).iloc[0].get('_source')
                if src != 'financedatabase_meta':
                    continue   # already have real data (core / html / api)
            except Exception:
                # No _source column == original native fetch == real data.
                continue
        # Skip if we already gave this one an API attempt.
        if _api_tried(safe).exists():
            continue
        keep.append(row)
    return pd.DataFrame(keep)


def _acquire_single_instance_lock():
    """Ensure only ONE em_expansion process fetches at a time, no matter how
    many the supervisor/cron/forever layers launch. Returns the lock handle
    (kept open for the process lifetime) or exits quietly if another instance
    holds it."""
    import fcntl, os, sys
    lock_path = YF_CACHE.parent / 'em_expansion.lock'
    fh = open(lock_path, 'w')
    try:
        fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
        fh.write(str(os.getpid())); fh.flush()
        return fh
    except BlockingIOError:
        print('Another em_expansion instance holds the lock — exiting.', flush=True)
        sys.exit(0)


def _process(row, sess) -> str:
    """Fetch + write one target. Returns 'real' | 'meta'. The warmed session
    is thread-safe (yahoo_session serialises re-warms; GETs share the urllib3
    pool), so many workers can share it — that's what turns the ~2.5/s
    single-thread rate into the ~15/s the API actually sustains."""
    sym = row['symbol']; safe = _safe(sym)
    try:
        info = fetch_info(sym, sess)
    except Exception:
        info = {'_error': 'exception'}
    got_real = ('_error' not in info) and any(
        info.get(k) is not None for k in _REAL_KEYS)
    if got_real:
        # Merge financedatabase metadata as a floor (sector/industry Yahoo
        # sometimes lacks for EM names), then write.
        meta = _metadata_record(row)
        for k, v in meta.items():
            if k not in info or info.get(k) in (None, ''):
                info[k] = v
        try:
            pd.DataFrame([info]).to_parquet(
                YF_CACHE / f'{safe}__info_metrics.parquet', compression='snappy')
        except Exception:
            pass
        result = 'real'
    else:
        # Metadata-only fallback so the name still counts for breadth. Only
        # write when we don't already have a meta row, to avoid churn.
        p = YF_CACHE / f'{safe}__info_metrics.parquet'
        if not p.exists():
            try:
                pd.DataFrame([_metadata_record(row)]).to_parquet(
                    p, compression='snappy')
            except Exception:
                pass
        result = 'meta'
    try: _api_tried(safe).touch()   # mark tried regardless, so re-runs skip it
    except Exception: pass
    return result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--rate', type=float, default=8.0,
                    help='(legacy) accepted for supervisor compatibility; '
                         'the threaded API path self-paces')
    ap.add_argument('--workers', type=int, default=6,
                    help='concurrent API fetchers sharing one warmed session '
                         '(API sustains ~18/s; 6 is a polite share of egress)')
    ap.add_argument('--max', type=int, default=40000)
    args = ap.parse_args()

    _lock = _acquire_single_instance_lock()   # held for process lifetime
    todo = pending()
    print(f'EM expansion (API): {len(todo):,} pending targets, '
          f'{args.workers} workers', flush=True)
    if todo.empty:
        return
    todo = todo.head(args.max)
    sess = get_session()
    rows = [r for _, r in todo.iterrows()]
    n_real = n_meta = done = 0
    lock = threading.Lock()
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = [ex.submit(_process, row, sess) for row in rows]
        for fut in as_completed(futs):
            try:
                res = fut.result()
            except Exception:
                res = 'meta'
            with lock:
                done += 1
                if res == 'real': n_real += 1
                else: n_meta += 1
                if done % 200 == 0:
                    el = time.time() - t0
                    rate = done / el if el > 0 else 0
                    eta = (len(rows) - done) / rate / 60 if rate > 0 else 0
                    print(f'  {done:>6,}/{len(rows):,}  real={n_real:,} '
                          f'meta={n_meta:,} rate={rate:.2f}/s eta={eta:.0f}min',
                          flush=True)
    print(f'\nFinal: real={n_real:,} meta-only={n_meta:,} of {len(rows):,}', flush=True)


if __name__ == '__main__':
    main()
