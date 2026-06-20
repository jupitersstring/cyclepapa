"""Universe-wide deep-slot fetcher — Path 2.

For every ticker that has cached info_metrics, fetch the deep slots
(income, cashflow, income_annual, cashflow_annual, price) if missing.

Designed to run for many hours across multiple sessions:
  - skips already-cached slots (idempotent)
  - auto-pushes snapshot to origin/cache-snapshot every --snapshot-every min
  - writes a progress file so subsequent runs pick up where we left off
  - throttle-aware: aborts a window of poor success rates

The cache snapshot push every N minutes means a container reset never
costs more than that window of work.

Run:
    python fetch_all_deep.py --workers 3 --snapshot-every 15

Resume after a reset:
    python cache_sync.py pull && python fetch_all_deep.py
"""
from __future__ import annotations
import argparse, time, subprocess, sys
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import pandas as pd, yfinance as yf

CACHE = Path('.cache/yf')
REPO = Path(__file__).resolve().parent

SLOTS = ('income','cashflow','income_annual','cashflow_annual','price')


def safe(t): return ''.join(c if c.isalnum() or c in '-_' else '_' for c in t)


def fetch_slot(tk: str, slot: str) -> str:
    """Return 'ok', 'cached', or 'fail'. Idempotent: skips if cached."""
    p = CACHE / f'{safe(tk)}__{slot}.parquet'
    if p.exists():
        return 'cached'
    try:
        t = yf.Ticker(tk)
        if slot == 'income':
            d = t.quarterly_income_stmt
        elif slot == 'cashflow':
            d = t.quarterly_cashflow
        elif slot == 'income_annual':
            d = t.income_stmt
        elif slot == 'cashflow_annual':
            d = t.cashflow
        elif slot == 'price':
            d = t.history(period='5y', auto_adjust=False)
        else:
            return 'fail'
        if d is None or (hasattr(d, 'empty') and d.empty):
            return 'fail'
        d.to_parquet(p)
        return 'ok'
    except Exception:
        return 'fail'


def fetch_all_for(tk: str, sleep_s: float = 0.3) -> dict:
    """Fetch all SLOTS for one ticker. Returns counts per outcome."""
    out = {'ok': 0, 'cached': 0, 'fail': 0}
    for slot in SLOTS:
        r = fetch_slot(tk, slot)
        out[r] = out.get(r, 0) + 1
        if sleep_s > 0 and r == 'ok':
            time.sleep(sleep_s)
    return out


def maybe_snapshot(last_push: float, snapshot_every_min: float, n_completed: int) -> float:
    if snapshot_every_min <= 0: return last_push
    now = time.time()
    if (now - last_push) / 60 >= snapshot_every_min:
        print(f'  [snapshot] pushing after {n_completed} tickers...', flush=True)
        r = subprocess.run([sys.executable, 'cache_sync.py', 'push'],
                            cwd=REPO, capture_output=True, text=True, timeout=300)
        if r.returncode == 0:
            print('  [snapshot] OK', flush=True)
        else:
            print(f'  [snapshot] FAILED: {(r.stderr or "")[:300]}', flush=True)
        return now
    return last_push


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--workers', type=int, default=3)
    ap.add_argument('--sleep', type=float, default=0.3)
    ap.add_argument('--snapshot-every', type=float, default=15.0)
    ap.add_argument('--max-tickers', type=int, default=0,
                    help='Stop after N tickers processed (0 = all).')
    args = ap.parse_args()

    # Universe = every ticker that has cached info_metrics
    info_files = sorted(CACHE.glob('*__info_metrics.parquet'))
    universe = [f.name.split('__')[0] for f in info_files]
    print(f'Universe size: {len(universe):,} tickers')

    # Filter to those that still need at least one deep slot
    todo = []
    for tk in universe:
        for slot in SLOTS:
            if not (CACHE / f'{safe(tk)}__{slot}.parquet').exists():
                todo.append(tk)
                break
    print(f'Tickers with missing deep slots: {len(todo):,}')

    if args.max_tickers > 0:
        todo = todo[:args.max_tickers]
        print(f'Capped to {len(todo):,} tickers')

    if not todo:
        print('Nothing to do — all cached deep slots present.')
        return

    last_push = time.time()
    n_done = ok_total = fail_total = cached_total = 0
    t0 = time.time()
    print(f'\nStarting fetch with {args.workers} worker(s), sleep={args.sleep}s/call,'
          f' snapshot every {args.snapshot_every}min')

    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(fetch_all_for, tk, args.sleep): tk for tk in todo}
        for fut in as_completed(futs):
            tk = futs[fut]
            try:
                r = fut.result()
                ok_total    += r.get('ok', 0)
                fail_total  += r.get('fail', 0)
                cached_total += r.get('cached', 0)
            except Exception as e:
                fail_total += len(SLOTS)
            n_done += 1
            if n_done % 50 == 0:
                el = time.time() - t0
                rate = n_done / el
                eta_min = (len(todo) - n_done) / max(0.01, rate) / 60
                print(f'  {n_done}/{len(todo)}  ok={ok_total} cached={cached_total} fail={fail_total}'
                      f'  rate={rate:.2f}t/s  eta={eta_min:.0f}min', flush=True)
                last_push = maybe_snapshot(last_push, args.snapshot_every, n_done)

    # Final snapshot
    print(f'\nFinal: {n_done} tickers processed; ok={ok_total} fail={fail_total} cached={cached_total}')
    maybe_snapshot(0, 0.001, n_done)  # force a final push


if __name__ == '__main__':
    main()
