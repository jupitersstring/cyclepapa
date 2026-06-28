"""DM universe expansion — fetch Developed-Market tickers we don't yet have.

Works through .cache/expansion/dm_targets.csv (Large→Mid→Small priority,
from financedatabase) and fetches each missing ticker's valuation +
price-summary snapshot via the Yahoo HTML scraper (the only Yahoo path that
works from our IP-throttled shared egress — the query1/2 API is 429-blocked).

Each fetched ticker gets a `<safe>__info_metrics.parquet` with the same
schema as the core universe: marketCap, EV/EBITDA, P/E, P/B, EV/Sales,
sector/industry/country, plus the price-summary fields (regularMarketPrice,
52WeekChange, 200-DMA) that feed the price-performance screens.

RESUMABLE: skips tickers that already have info_metrics OR a __dm_tried
sentinel (written after every attempt, success or 404). A re-run continues
exactly where it stopped — safe across container reboots since the targets
list + sentinels live under .cache/ (snapshotted to origin).

Paced at 1 req/s (sustainable for the shared IP). Large-caps first so the
most investable names land soonest.
"""
from __future__ import annotations
import argparse, time
from pathlib import Path

import pandas as pd

import sys
sys.path.insert(0, str(Path(__file__).parent))
from yahoo_html_fetcher import fetch_quote_html, warm_session, _safe, YF_CACHE

TARGETS = Path('.cache/expansion/dm_targets.csv')


def _tried(safe: str) -> Path:
    return YF_CACHE / f'{safe}__dm_tried'


def pending_targets() -> list[str]:
    """Symbols from the target list that have neither info_metrics nor a
    __dm_tried sentinel — i.e. still to attempt."""
    if not TARGETS.exists():
        return []
    df = pd.read_csv(TARGETS)
    out = []
    for sym in df['symbol'].tolist():
        if not isinstance(sym, str):
            continue
        safe = _safe(sym)
        if (YF_CACHE / f'{safe}__info_metrics.parquet').exists():
            continue
        if _tried(safe).exists():
            continue
        out.append(sym)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--rate', type=float, default=1.0, help='requests/sec')
    ap.add_argument('--max', type=int, default=30000)
    ap.add_argument('--refresh-every', type=int, default=25,
                    help='re-warm session after this many consecutive failures')
    args = ap.parse_args()

    todo = pending_targets()
    print(f'DM expansion: {len(todo):,} pending targets', flush=True)
    if not todo:
        print('All caught up.')
        return
    todo = todo[: args.max]
    sess = warm_session()
    sleep = 1.0 / args.rate if args.rate > 0 else 0
    n_ok = n_fail = 0
    consec = throttle = 0
    t0 = time.time()
    for i, sym in enumerate(todo, 1):
        safe = _safe(sym)
        info = fetch_quote_html(sym, sess)
        err = info.get('_error')
        if err:
            n_fail += 1
            consec += 1
            if err in ('timeout',) or 'http_429' in err:
                throttle += 1
            else:
                throttle = 0
            # 404 is permanent → mark tried so we don't retry it
            if 'http_404' in err:
                try: _tried(safe).touch()
                except Exception: pass
            if throttle >= 5:
                time.sleep(30); sess = warm_session(); throttle = 0; consec = 0
            elif consec >= args.refresh_every:
                sess = warm_session(); consec = 0; time.sleep(2)
        else:
            consec = throttle = 0
            got = any(info.get(k) is not None for k in
                      ('marketCap','trailingPE','priceToBook','enterpriseToEbitda',
                       'regularMarketPrice'))
            if got:
                try:
                    pd.DataFrame([info]).to_parquet(
                        YF_CACHE / f'{safe}__info_metrics.parquet', compression='snappy')
                    n_ok += 1
                except Exception:
                    pass
            # Mark tried regardless (200 response = decided)
            try: _tried(safe).touch()
            except Exception: pass
        if i % 50 == 0:
            el = time.time() - t0
            rate = i / el if el > 0 else 0
            eta = (len(todo) - i) / rate / 60 if rate > 0 else 0
            print(f'  {i:>6,}/{len(todo):,}  ok={n_ok:,} fail={n_fail:,} '
                  f'rate={rate:.2f}/s eta={eta:.0f}min', flush=True)
        time.sleep(sleep)
    print(f'\nFinal: ok={n_ok:,} fail={n_fail:,} of {len(todo):,}', flush=True)


if __name__ == '__main__':
    main()
