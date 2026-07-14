#!/usr/bin/env bash
# Watchdog: keeps fetch_all_deep.py running until the universe is complete.
# Restarts on any exit. Stops only when the fetcher reports nothing to do.
# Pushes a final snapshot when the universe is fully covered.

set -u
cd "$(dirname "$0")"

LOG=run_alldeep_watchdog.log
exec >> "$LOG" 2>&1
echo "=========================================="
echo "Watchdog started at $(date -u)"
echo "=========================================="

attempt=0
while true; do
    attempt=$((attempt + 1))
    echo ""
    echo "--- attempt $attempt ($(date -u)) ---"
    python3 fetch_all_deep.py --workers 2 --sleep 0.8 --snapshot-every 2 \
        --throttle-window 100 --throttle-threshold 0.0 --throttle-pause 60 \
        2>&1 | tail -50
    rc=$?
    echo "fetch_all_deep exited rc=$rc"
    # If clean exit AND log shows "Nothing to do" or "all cached", stop.
    if [ $rc -eq 0 ]; then
        # Check whether universe is complete (fetcher prints "Nothing to do — all cached")
        # by re-running with --max-tickers 1 and checking todo count
        todo=$(python3 -c "
import sys; sys.path.insert(0, '.')
from fetch_all_deep import safe, safe_to_ticker, SLOTS
from pathlib import Path
CACHE = Path('.cache/yf')
info = sorted(CACHE.glob('*__info_metrics.parquet'))
universe = [safe_to_ticker(f.name.split('__')[0]) for f in info]
todo = 0
for tk in universe:
    for slot in SLOTS:
        if not (CACHE / f'{safe(tk)}__{slot}.parquet').exists():
            todo += 1; break
print(todo)
" 2>/dev/null || echo 999999)
        echo "Remaining tickers: $todo"
        if [ "$todo" -lt 50 ]; then
            echo "Universe substantially complete — pushing final snapshot and exiting."
            python3 cache_sync.py push 2>&1 | tail -3
            break
        fi
    fi
    # Brief pause before restart so we don't spin if something is fundamentally broken
    sleep 10
done

echo "Watchdog exiting at $(date -u)"
