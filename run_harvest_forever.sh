#!/usr/bin/env bash
# Resilient wrapper for edgar_full_harvest.py.
#
# Why this exists: in our container environment the python harvest gets
# killed mid-run by external signals (container reaping, OOM, idle
# timeout — we can't always tell which). The per-CIK cache means
# restarting picks up where it left off, so the right answer is just to
# keep restarting until every stage completes.
#
# Usage:
#   setsid nohup ./run_harvest_forever.sh > harvest_watchdog.log 2>&1 &
#
# The watchdog itself is fully detached, so it survives session resets.
# Each python restart writes its own log lines to the same file with a
# clear === restart === banner so progress is easy to follow.

set -u
cd "$(dirname "$0")"

LOG=edgar_harvest.log
WATCHDOG_LOG=harvest_watchdog.log
DEATHS=0
MAX_DEATHS=200   # safety bound — at 50 deaths per session this lasts days
PYTHON=python3

# When the python script exits 0 it means every stage finished. We exit
# the loop and the watchdog terminates cleanly. Any non-zero exit is
# treated as a death — sleep 10s and try again.
while true; do
    DEATHS=$((DEATHS + 1))
    if [ $DEATHS -gt $MAX_DEATHS ]; then
        echo "$(date '+%Y-%m-%d %H:%M:%S') watchdog: hit MAX_DEATHS=$MAX_DEATHS, giving up" >> "$WATCHDOG_LOG"
        exit 1
    fi
    echo "$(date '+%Y-%m-%d %H:%M:%S') watchdog: restart attempt #$DEATHS" >> "$WATCHDOG_LOG"
    echo "" >> "$LOG"
    echo "=== $(date '+%Y-%m-%d %H:%M:%S')  watchdog restart #$DEATHS ===" >> "$LOG"

    "$PYTHON" edgar_full_harvest.py --resume --workers 6 >> "$LOG" 2>&1
    RC=$?

    echo "$(date '+%Y-%m-%d %H:%M:%S') watchdog: python exited rc=$RC" >> "$WATCHDOG_LOG"

    if [ $RC -eq 0 ]; then
        # All stages reported done cleanly
        echo "$(date '+%Y-%m-%d %H:%M:%S') watchdog: harvest finished successfully" >> "$WATCHDOG_LOG"
        break
    fi

    # Give SEC a beat — also gives us a stable point to send TERM if we want
    sleep 10
done
