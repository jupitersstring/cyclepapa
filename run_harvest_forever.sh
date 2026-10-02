#!/usr/bin/env bash
# Resilient 4-shard wrapper for edgar_full_harvest.py.
#
# Splits the 10,433-CIK universe into 4 disjoint shards by `cik % 4`.
# Each shard runs as its own python process with its own restart loop
# inside this single bash script. The shared cache directory is
# per-CIK so the shards never collide, and they each have their own
# state file (edgar_full_state.shard{N}of4.json).
#
# Wall-clock target: per-CIK fetch costs ~80-200ms, so 4 shards in
# parallel push effective throughput from ~5/s to ~15-25/s.
#
# Usage:
#   setsid nohup ./run_harvest_forever.sh > harvest_watchdog.log 2>&1 &

set -uo pipefail
cd "$(dirname "$0")"

NUM_SHARDS=4
WATCHDOG_LOG=harvest_watchdog.log
PYTHON=python3
MAX_DEATHS_PER_SHARD=200

ts() { date '+%Y-%m-%d %H:%M:%S'; }

# One restart-loop per shard, all running concurrently inside this script.
run_shard() {
    local SHARD=$1
    local LOG="edgar_harvest.shard${SHARD}.log"
    local DEATHS=0
    while true; do
        DEATHS=$((DEATHS + 1))
        if [ $DEATHS -gt $MAX_DEATHS_PER_SHARD ]; then
            echo "$(ts) shard $SHARD: MAX_DEATHS reached, exiting" >> "$WATCHDOG_LOG"
            return 1
        fi
        echo "$(ts) shard $SHARD: restart #$DEATHS" >> "$WATCHDOG_LOG"
        echo "" >> "$LOG"
        echo "=== $(ts)  shard $SHARD restart #$DEATHS ===" >> "$LOG"

        "$PYTHON" edgar_full_harvest.py --resume --workers 3 \
            --shard "$SHARD" --num-shards "$NUM_SHARDS" >> "$LOG" 2>&1
        local RC=$?
        echo "$(ts) shard $SHARD: python exited rc=$RC" >> "$WATCHDOG_LOG"

        if [ $RC -eq 0 ]; then
            echo "$(ts) shard $SHARD: done cleanly" >> "$WATCHDOG_LOG"
            return 0
        fi
        sleep 5
    done
}

# Spawn all shards in the background
PIDS=()
for SHARD in $(seq 0 $((NUM_SHARDS - 1))); do
    run_shard "$SHARD" &
    PIDS+=("$!")
    echo "$(ts) watchdog: spawned shard $SHARD as PID $!" >> "$WATCHDOG_LOG"
done

# Wait for all shards to finish (or until SIGTERM kills us)
for pid in "${PIDS[@]}"; do
    wait "$pid"
done

echo "$(ts) watchdog: all shards finished" >> "$WATCHDOG_LOG"
