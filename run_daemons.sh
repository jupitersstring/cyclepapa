#!/usr/bin/env bash
# Daemon supervisor for cyclepapa fetchers.
#
# Idempotent: safe to run repeatedly. Inspects ps for each fetcher's
# command-line; if not running, relaunches it via nohup. Each fetcher
# resumes from where it stopped (sentinel files in .cache prevent
# duplicate work). Logs go to scratchpad/ so they survive across runs.
#
# Also runs cache_sync.py push to mirror the cache to origin/cache-snapshot
# so the next container start can restore it. The snapshot push is the
# durability anchor — without it, container reclamation loses all fetch
# progress that hasn't yet been committed to results CSVs.
#
# Designed to be invoked every 20-30 min by a CronCreate schedule so the
# session keeps everything alive while the user is away from the laptop.

set -u
cd "$(dirname "$0")"

LOG_DIR="${CLAUDE_CODE_TMPDIR:-/tmp}/cyclepapa-daemons"
mkdir -p "$LOG_DIR"

log() { printf '[%s] %s\n' "$(date -u +%H:%M:%S)" "$*"; }

# --- Self-heal: relaunch any fetcher that died ---
restart_if_dead() {
    local marker="$1"; shift
    local script="$1"; shift
    local logfile="$LOG_DIR/$(basename "$script" .py).log"
    if pgrep -f "python3 $script" > /dev/null; then
        log "ALIVE  $script"
    else
        log "DEAD   $script — relaunching: $*"
        nohup python3 "$script" "$@" >> "$logfile" 2>&1 &
        sleep 1
    fi
}

restart_if_dead edgar fill_edgar_gaps.py --sleep 0.3
restart_if_dead extras fetch_yfinance_extras.py --workers 8 --sleep 0.05
restart_if_dead xbrl fetch_xbrl_segments.py --workers 8 --sleep 0.05 --progress-every 100

# --- Snapshot push (durability) ---
log "Snapshot push starting..."
if python3 cache_sync.py push >> "$LOG_DIR/snapshot_push.log" 2>&1; then
    log "Snapshot push OK"
else
    log "Snapshot push FAILED — see $LOG_DIR/snapshot_push.log"
fi

# --- Progress report ---
log "=== Progress ==="
log "EDGAR companyfacts: $(ls .cache/edgar/CF_*.json.gz 2>/dev/null | wc -l) cached"
log "XBRL segments:      $(ls .cache/segments/*__segments.parquet 2>/dev/null | wc -l) live + $(ls .cache/segments/*__segments.dead 2>/dev/null | wc -l) dead"
for slot in growth_estimates analyst_price_targets insider_purchases recommendations_summary earnings_estimate; do
    live=$(ls .cache/yf/*__${slot}.parquet 2>/dev/null | wc -l)
    dead=$(ls .cache/yf/*__${slot}.dead 2>/dev/null | wc -l)
    log "yfinance $slot: $live live + $dead dead"
done

log "Done."
