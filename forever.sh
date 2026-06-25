#!/usr/bin/env bash
# forever.sh — wrap a long-running command in an infinite re-launch loop.
#
# Usage:
#   ./forever.sh <log-tag> <command> [args...]
#
# Behavior:
#   1. Run the command.
#   2. When it exits (clean OR crash OR OOM), wait SLEEP_SECONDS then re-run.
#   3. Write a heartbeat file every 60s while running so external monitors
#      can detect a wedged loop (PID alive but command stuck).
#   4. Log every iteration's exit code so we can spot patterns.
#
# Designed for the cyclepapa fetchers (fill_edgar_gaps, fetch_yfinance_extras,
# fetch_xbrl_segments) which die periodically from network errors, SEC
# throttle, or yfinance timeouts. Each fetcher uses .dead sentinels so
# resume-on-restart is automatic and idempotent.

set -u

if [ "$#" -lt 2 ]; then
    echo "usage: $0 <log-tag> <command> [args...]" >&2
    exit 1
fi

TAG="$1"; shift
SLEEP_SECONDS="${SLEEP_SECONDS:-10}"
LOG_DIR="${CLAUDE_CODE_TMPDIR:-/tmp}/cyclepapa-daemons"
mkdir -p "$LOG_DIR"
HEARTBEAT="$LOG_DIR/${TAG}.heartbeat"
SUPERVISOR_LOG="$LOG_DIR/${TAG}.supervisor.log"

# Write a hint of who's wrapping what to the log
echo "[$(date -u +%FT%TZ)] forever start: $*" >> "$SUPERVISOR_LOG"

# Heartbeat updater runs as a separate background process while the main
# loop iterates. Killed when we exit.
heartbeat_pid=""
start_heartbeat() {
    (
        while true; do
            date -u +%FT%TZ > "$HEARTBEAT"
            sleep 60
        done
    ) &
    heartbeat_pid=$!
}
stop_heartbeat() {
    [ -n "$heartbeat_pid" ] && kill "$heartbeat_pid" 2>/dev/null
}
trap stop_heartbeat EXIT

start_heartbeat

iter=0
while true; do
    iter=$((iter + 1))
    echo "[$(date -u +%FT%TZ)] iter=$iter launching: $*" >> "$SUPERVISOR_LOG"
    "$@"
    code=$?
    echo "[$(date -u +%FT%TZ)] iter=$iter exited with code=$code" >> "$SUPERVISOR_LOG"
    # If the command finished successfully AND the universe is fully decided
    # the next launch will quickly print "All caught up" and exit again.
    # That's fine — we keep looping with the sleep so disk-write contention
    # doesn't spike, and resume immediately when new tickers appear.
    sleep "$SLEEP_SECONDS"
done
