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
DEAD_LIST = CACHE / '_dead_tickers.txt'  # Sentinels for tickers where every slot failed


def load_dead_set() -> set:
    if not DEAD_LIST.exists(): return set()
    try:
        return {ln.strip() for ln in DEAD_LIST.read_text().splitlines() if ln.strip()}
    except Exception: return set()


def mark_dead(tk: str):
    """Append ticker to dead-list (idempotent — caller can call repeatedly)."""
    try:
        with open(DEAD_LIST, 'a') as f:
            f.write(tk + '\n')
    except Exception: pass


def safe(t): return ''.join(c if c.isalnum() or c in '-_' else '_' for c in t)


# All region suffixes that we encode as `_<suffix>` in the safe cache name
KNOWN_SUFFIXES = {
    '_T','_L','_DE','_F','_PA','_TO','_V','_AX','_SW','_MI','_AS','_MC',
    '_ST','_OL','_CO','_BR','_HE','_IR','_VI','_LS','_AT','_KS','_KQ',
    '_HK','_TW','_TWO','_SI','_NZ','_TA','_SS','_SZ','_NS','_BO','_SA',
    '_MX','_JO','_IS','_BK','_JK',
}


def safe_to_ticker(safe_name: str) -> str:
    """Reverse the cache safe-name to a yfinance ticker. The only character
    we ever encode is '.' -> '_'. For non-US names the original ticker had a
    single '.' before the exchange suffix; we restore that here."""
    if '_' in safe_name:
        head, _, tail = safe_name.rpartition('_')
        if '_' + tail in KNOWN_SUFFIXES:
            return head + '.' + tail
    return safe_name


def fetch_slot(tk: str, slot: str) -> str:
    """Return 'ok', 'cached', or 'fail'. Idempotent: skips if cached.
    Writes a sentinel `__<slot>.dead` file on a failed fetch so future runs
    don't re-attempt yfinance for slots that have no data."""
    p = CACHE / f'{safe(tk)}__{slot}.parquet'
    if p.exists():
        return 'cached'
    dead = CACHE / f'{safe(tk)}__{slot}.dead'
    if dead.exists():
        return 'cached'  # treat known-dead as 'cached' so it's not re-attempted
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
            dead.touch()
            return 'fail'
        d.to_parquet(p)
        return 'ok'
    except Exception:
        dead.touch()
        return 'fail'


def fetch_all_for(tk: str, sleep_s: float = 0.3) -> dict:
    """Fetch all SLOTS for one ticker. Returns counts per outcome.
    If every slot fails AND nothing was already cached, mark the ticker dead
    so next run skips it."""
    out = {'ok': 0, 'cached': 0, 'fail': 0}
    for slot in SLOTS:
        r = fetch_slot(tk, slot)
        out[r] = out.get(r, 0) + 1
        if sleep_s > 0 and r == 'ok':
            time.sleep(sleep_s)
    if out['ok'] == 0 and out['cached'] == 0 and out['fail'] == len(SLOTS):
        mark_dead(tk)
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
    ap.add_argument('--throttle-window', type=int, default=50,
                    help='Detect throttle by looking at last N ticker outcomes.')
    ap.add_argument('--throttle-threshold', type=float, default=0.05,
                    help='If <threshold of last window had any ok, treat as throttled.')
    ap.add_argument('--throttle-pause', type=float, default=600.0,
                    help='Seconds to sleep when throttle detected.')
    args = ap.parse_args()

    # Universe = every ticker that has cached info_metrics. The CACHE file
    # name uses the safe form (dots replaced by underscores); we convert back
    # to the original yfinance ticker before calling .Ticker().
    info_files = sorted(CACHE.glob('*__info_metrics.parquet'))
    universe = [safe_to_ticker(f.name.split('__')[0]) for f in info_files]
    print(f'Universe size: {len(universe):,} tickers')

    # Skip tickers we've already proven have no deep data anywhere on yfinance
    dead = load_dead_set()
    print(f'Dead-list (proven no data): {len(dead):,} tickers — skipping these')

    # Filter to those that still need at least one deep slot AND aren't dead.
    # A ticker is "needed" if at least one slot has neither a .parquet (real data)
    # nor a .dead sentinel (proven empty).
    todo = []
    for tk in universe:
        if tk in dead: continue
        s = safe(tk)
        for slot in SLOTS:
            if not (CACHE / f'{s}__{slot}.parquet').exists() and not (CACHE / f'{s}__{slot}.dead').exists():
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
    last_window_ok = []  # rolling list of len <= throttle_window, True if any ok this ticker
    t0 = time.time()
    print(f'\nStarting fetch with {args.workers} worker(s), sleep={args.sleep}s/call,'
          f' snapshot every {args.snapshot_every}min')
    print(f'Throttle: pause {args.throttle_pause:.0f}s if <{args.throttle_threshold*100:.0f}% of '
          f'last {args.throttle_window} tickers had any successful fetch.\n')

    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(fetch_all_for, tk, args.sleep): tk for tk in todo}
        for fut in as_completed(futs):
            tk = futs[fut]
            try:
                r = fut.result()
                this_ok = r.get('ok', 0)
                ok_total    += this_ok
                fail_total  += r.get('fail', 0)
                cached_total += r.get('cached', 0)
                last_window_ok.append(this_ok > 0)
            except Exception:
                fail_total += len(SLOTS)
                last_window_ok.append(False)
            n_done += 1
            if len(last_window_ok) > args.throttle_window:
                last_window_ok = last_window_ok[-args.throttle_window:]
            if n_done % 25 == 0:
                el = time.time() - t0
                rate = n_done / el
                eta_min = (len(todo) - n_done) / max(0.01, rate) / 60
                window_ok_rate = sum(last_window_ok) / max(1, len(last_window_ok))
                print(f'  {n_done}/{len(todo)}  ok={ok_total} cached={cached_total} fail={fail_total}'
                      f'  rate={rate:.2f}t/s  eta={eta_min:.0f}min  win_ok={window_ok_rate:.0%}', flush=True)
                last_push = maybe_snapshot(last_push, args.snapshot_every, n_done)
                # Throttle detection
                if (len(last_window_ok) >= args.throttle_window and
                        window_ok_rate < args.throttle_threshold):
                    print(f'  [THROTTLE] window_ok_rate {window_ok_rate:.0%} < {args.throttle_threshold:.0%} '
                          f'— sleeping {args.throttle_pause:.0f}s', flush=True)
                    time.sleep(args.throttle_pause)
                    last_window_ok = []  # reset so we re-test after the pause
                    print(f'  [THROTTLE] resuming', flush=True)

    # Final snapshot
    print(f'\nFinal: {n_done} tickers processed; ok={ok_total} fail={fail_total} cached={cached_total}')
    maybe_snapshot(0, 0.001, n_done)  # force a final push


if __name__ == '__main__':
    main()
