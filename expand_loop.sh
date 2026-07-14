#!/usr/bin/env bash
# Self-supervising universe expander.
# Loops fetch_batch.py for each region until full coverage or N attempts.
# Each invocation is short (~1-2 min), so container session-kill is less likely.
# Cache snapshot pushed every 5 successful batches.
set -e
cd "$(dirname "$0")"

REGIONS=(US JP AU CA FR DE HK KR GB SE)
MAX_ATTEMPTS_PER_REGION=30
BATCH=100
SLEEP_OK=15      # between batches when OK
SLEEP_THROTTLE=180  # back off this long when fully throttled
PUSH_EVERY=5     # snapshot every N successful batches
push_counter=0

for r in "${REGIONS[@]}"; do
    echo "==================================================="
    echo "Region $r — supervisor starting"
    for i in $(seq 1 $MAX_ATTEMPTS_PER_REGION); do
        python3 fetch_batch.py --region $r --batch $BATCH --sleep 0.6
        rc=$?
        if [ $rc -eq 0 ]; then
            push_counter=$((push_counter + 1))
            if [ $((push_counter % PUSH_EVERY)) -eq 0 ]; then
                echo "Pushing snapshot..."
                python3 cache_sync.py push 2>&1 | tail -3
            fi
            sleep $SLEEP_OK
            # Quick check — is there more to do?
            remaining=$(python3 -c "
import sys; sys.path.insert(0, '.')
from per_region_rank import build_universe
from pathlib import Path
import time
def safe(t): return ''.join(c if c.isalnum() or c in '-_' else '_' for c in t)
u = build_universe('$r', 100000)
todo = [t for t in u if not (Path('.cache/yf')/f'{safe(t)}__info_metrics.parquet').exists() or (time.time()-(Path('.cache/yf')/f'{safe(t)}__info_metrics.parquet').stat().st_mtime)/86400>=10]
print(len(todo))
")
            echo "[$r] iter $i: $remaining tickers remain"
            if [ "$remaining" -eq 0 ]; then
                echo "[$r] COMPLETE."
                break
            fi
        else
            echo "[$r] iter $i throttled; backing off ${SLEEP_THROTTLE}s..."
            sleep $SLEEP_THROTTLE
        fi
    done
done

echo "All regions complete (or maxed attempts). Final snapshot..."
python3 cache_sync.py push 2>&1 | tail -3
