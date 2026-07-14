"""Spawn fetch_all_deep as a proper POSIX daemon (double-fork) so it survives
parent process exit. The container has been killing nohup/setsid background
bash jobs; a proper daemon survives because PPID becomes 1 (init).

Loops fetch_all_deep.py forever, restarting on any exit, until <50 tickers
remain in the todo set.
"""
from __future__ import annotations
import os, sys, time, subprocess, signal
from pathlib import Path

REPO = Path(__file__).resolve().parent
LOG = REPO / 'run_alldeep_daemon.log'
PIDFILE = REPO / 'fetch_daemon.pid'


def daemonize():
    """Standard double-fork to detach from parent session."""
    pid = os.fork()
    if pid > 0:
        # First parent — exit immediately
        sys.exit(0)
    os.setsid()
    pid = os.fork()
    if pid > 0:
        # Second parent — exit
        sys.exit(0)
    # Grandchild — true daemon
    os.umask(0)
    os.chdir(REPO)
    # Redirect stdio to log file
    sys.stdout.flush(); sys.stderr.flush()
    with open(LOG, 'ab', buffering=0) as f:
        os.dup2(f.fileno(), sys.stdout.fileno())
        os.dup2(f.fileno(), sys.stderr.fileno())
    sys.stdin = open(os.devnull, 'r')
    # Write PID file
    PIDFILE.write_text(str(os.getpid()) + '\n')


def remaining_count() -> int:
    try:
        from fetch_all_deep import safe, safe_to_ticker, SLOTS, CACHE
        info = sorted(CACHE.glob('*__info_metrics.parquet'))
        universe = [safe_to_ticker(f.name.split('__')[0]) for f in info]
        n = 0
        for tk in universe:
            for slot in SLOTS:
                if not (CACHE / f'{safe(tk)}__{slot}.parquet').exists():
                    n += 1; break
        return n
    except Exception:
        return -1


def main_loop():
    print(f'=== daemon started pid={os.getpid()} at {time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())} ===',
          flush=True)
    attempt = 0
    while True:
        attempt += 1
        print(f'\n--- attempt {attempt} at {time.strftime("%H:%M:%S")} ---', flush=True)
        try:
            r = subprocess.run([
                sys.executable, 'fetch_all_deep.py',
                '--workers', '2', '--sleep', '0.8', '--snapshot-every', '2',
                '--throttle-window', '100', '--throttle-threshold', '0.0',
                '--throttle-pause', '60',
            ], cwd=REPO, capture_output=True, text=True, timeout=86400)
            print(f'fetch_all_deep rc={r.returncode}', flush=True)
            # Show last 20 lines of fetcher output
            for line in (r.stdout or '').splitlines()[-20:]:
                print(f'  {line}', flush=True)
        except subprocess.TimeoutExpired:
            print('fetch_all_deep hit 24h timeout', flush=True)
        except Exception as e:
            print(f'fetch_all_deep raised: {e}', flush=True)

        rem = remaining_count()
        print(f'Remaining: {rem}', flush=True)
        if 0 <= rem < 50:
            print('Universe substantially complete — pushing final snapshot and exiting.', flush=True)
            subprocess.run([sys.executable, 'cache_sync.py', 'push'], cwd=REPO)
            break
        # Brief pause before next attempt
        time.sleep(5)
    if PIDFILE.exists():
        try: PIDFILE.unlink()
        except: pass


if __name__ == '__main__':
    if '--no-daemon' in sys.argv:
        main_loop()
    else:
        daemonize()
        main_loop()
