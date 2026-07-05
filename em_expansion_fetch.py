"""EM / additional-market universe expansion.

Widens the universe into emerging + frontier markets (China A-shares, India,
Brazil, Thailand, Indonesia, Turkey, Mexico, ...) using financedatabase for
the target list + static metadata, and the Yahoo HTML frontend for live
valuation/price where Yahoo serves the ticker.

Two-tier fill so EVERY name adds breadth:
  1. Try finance.yahoo.com HTML  -> full valuation (EV/EBITDA, P/E, P/B) +
     price-summary (52-week change) when served.
  2. On 404 / no-data, write a METADATA-ONLY info_metrics from the
     financedatabase row (company, sector, industry, country, market-cap
     tier, currency). The name then counts for sector/country/breadth views
     even though Yahoo has no quote for it.

Yahoo is the only live-fundamentals path that works from this IP-throttled
shared egress (Stooq is bot-gated; the query1/2 API is 429-blocked), so we
pace at a sustainable rate. Resumable via __em_tried sentinels — a re-run
continues where it stopped, safe across container reboots.
"""
from __future__ import annotations
import argparse, time
from pathlib import Path

import pandas as pd

import sys
sys.path.insert(0, str(Path(__file__).parent))
from yahoo_html_fetcher import fetch_quote_html, warm_session, _safe, YF_CACHE

TARGETS = Path('.cache/expansion/em_targets.csv')

# financedatabase market-cap tier -> a representative USD figure, so the
# metadata-only rows still sort/filter sanely in mcap-based views. Rough
# midpoints; real value overwrites this whenever Yahoo serves the ticker.
_TIER_MCAP = {
    'Large Cap': 12e9, 'Mid Cap': 4e9, 'Small Cap': 800e6,
    'Micro Cap': 150e6, 'Nano Cap': 30e6,
}


def _tried(safe: str) -> Path:
    return YF_CACHE / f'{safe}__em_tried'


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
        # Skip if we already have REAL (non-meta) info, or already tried
        p = YF_CACHE / f'{safe}__info_metrics.parquet'
        if p.exists():
            try:
                src = pd.read_parquet(p).iloc[0].get('_source')
                if src != 'financedatabase_meta':
                    continue   # already have real data
            except Exception:
                continue
        if _tried(safe).exists():
            continue
        keep.append(row)
    return pd.DataFrame(keep)


def _acquire_single_instance_lock():
    """Ensure only ONE em_expansion process fetches at a time, no matter how
    many the supervisor/cron/forever layers launch. Concurrent Yahoo fetchers
    saturate the shared-IP throttle (yield collapses ~2%), so this lock is the
    difference between working and not. Returns the lock handle (kept open for
    the process lifetime) or exits quietly if another instance holds it."""
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--rate', type=float, default=1.2)
    ap.add_argument('--max', type=int, default=40000)
    ap.add_argument('--refresh-every', type=int, default=25)
    args = ap.parse_args()

    _lock = _acquire_single_instance_lock()   # held for process lifetime
    todo = pending()
    print(f'EM expansion: {len(todo):,} pending targets', flush=True)
    if todo.empty:
        return
    todo = todo.head(args.max)
    sess = warm_session()
    sleep = 1.0 / args.rate if args.rate > 0 else 0
    n_real = n_meta = 0
    consec = throttle = 0
    t0 = time.time()
    for i, (_, row) in enumerate(todo.iterrows(), 1):
        sym = row['symbol']; safe = _safe(sym)
        info = fetch_quote_html(sym, sess)
        err = info.get('_error')
        got_real = (not err) and any(
            info.get(k) is not None for k in
            ('marketCap', 'trailingPE', 'priceToBook', 'enterpriseToEbitda',
             'regularMarketPrice'))
        if got_real:
            # Merge financedatabase metadata as a floor (sector/industry that
            # Yahoo sometimes lacks for EM names), then write.
            meta = _metadata_record(row)
            for k, v in meta.items():
                if k not in info or info.get(k) in (None, ''):
                    info[k] = v
            try:
                pd.DataFrame([info]).to_parquet(
                    YF_CACHE / f'{safe}__info_metrics.parquet', compression='snappy')
                n_real += 1
            except Exception:
                pass
            consec = throttle = 0
        else:
            # Metadata-only fallback so the name still counts for breadth
            try:
                pd.DataFrame([_metadata_record(row)]).to_parquet(
                    YF_CACHE / f'{safe}__info_metrics.parquet', compression='snappy')
                n_meta += 1
            except Exception:
                pass
            if err in ('timeout',) or (err and 'http_429' in err):
                throttle += 1; consec += 1
            else:
                throttle = 0; consec += 1
            if throttle >= 5:
                time.sleep(30); sess = warm_session(); throttle = consec = 0
            elif consec >= args.refresh_every:
                sess = warm_session(); consec = 0; time.sleep(2)
        # Mark tried regardless
        try: _tried(safe).touch()
        except Exception: pass
        if i % 100 == 0:
            el = time.time() - t0
            rate = i / el if el > 0 else 0
            eta = (len(todo) - i) / rate / 60 if rate > 0 else 0
            print(f'  {i:>6,}/{len(todo):,}  real={n_real:,} meta={n_meta:,} '
                  f'rate={rate:.2f}/s eta={eta:.0f}min', flush=True)
        time.sleep(sleep)
    print(f'\nFinal: real={n_real:,} meta-only={n_meta:,} of {len(todo):,}', flush=True)


if __name__ == '__main__':
    main()
