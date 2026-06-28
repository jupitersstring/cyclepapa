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

# --- Self-heal: relaunch any FOREVER wrapper that died ---
# The forever wrapper itself loops on the fetcher — so this check is just
# the outer "wrapper alive?" gate. If the wrapper died (rare — only on
# SIGKILL or the container restarting), we re-launch the wrapper which
# in turn loops on the fetcher.
restart_if_dead() {
    local tag="$1"; shift
    local cmd="$1"; shift
    local logfile="$LOG_DIR/$(basename "$cmd" .py).log"
    if pgrep -f "forever.sh $tag " > /dev/null; then
        log "ALIVE  forever($tag)"
        return
    fi
    if pgrep -f "python3 $cmd" > /dev/null; then
        log "ALIVE  $cmd (forever wrapper missing — wrapping)"
    else
        log "DEAD   $tag — launching forever wrapper: $cmd $*"
    fi
    nohup bash "$(dirname "$0")/forever.sh" "$tag" python3 "$cmd" "$@" >> "$logfile" 2>&1 &
    sleep 1
}

restart_if_dead edgar fill_edgar_gaps.py --sleep 0.3
restart_if_dead extras fetch_yfinance_extras.py --workers 8 --sleep 0.05

# XBRL segment fetch — 4 parallel shards. Each shard is its own Python process
# with 8 threads, so 4×8 = 32 effective HTTP concurrency. SEC's 10 req/s limit
# is per-IP — we stay under by virtue of edgartools' per-process throttle +
# per-thread 50ms delay. Multi-process escapes the GIL bottleneck that single-
# process N-thread had (XBRL parsing is CPU-heavy).
restart_if_dead xbrl0 fetch_xbrl_segments.py --workers 8 --sleep 0.05 --progress-every 100 --shard-id 0 --shard-count 4
restart_if_dead xbrl1 fetch_xbrl_segments.py --workers 8 --sleep 0.05 --progress-every 100 --shard-id 1 --shard-count 4
restart_if_dead xbrl2 fetch_xbrl_segments.py --workers 8 --sleep 0.05 --progress-every 100 --shard-id 2 --shard-count 4
restart_if_dead xbrl3 fetch_xbrl_segments.py --workers 8 --sleep 0.05 --progress-every 100 --shard-id 3 --shard-count 4

# Yahoo HTML valuation gap-fill — runs at 1 req/s (sustainable for our
# shared-IP egress; higher trips Yahoo's per-IP throttle). Resumable via
# __yahoo_html_done sentinels so it grinds through the gap list across
# sessions without re-work. Fills US + non-US EV/EBITDA / P/E / P/B.
restart_if_dead dmexp dm_expansion_fetch.py --rate=1.5

# --- Snapshot push (durability) ---
# Run in the BACKGROUND so the supervisor returns immediately. The push
# takes several minutes (1.3 GB across 14 chunks); running it synchronously
# was blocking the cron-driven supervisor, leaving a window where dead
# daemons weren't restarted. A lock file prevents overlapping pushes.
PUSH_LOCK="$LOG_DIR/snapshot_push.lock"
if [ ! -f "$PUSH_LOCK" ] || [ "$(find "$PUSH_LOCK" -mmin +30 2>/dev/null)" ]; then
    touch "$PUSH_LOCK"
    ( python3 cache_sync.py push >> "$LOG_DIR/snapshot_push.log" 2>&1; rm -f "$PUSH_LOCK" ) &
    log "Snapshot push started in background"
else
    log "Snapshot push already running (lock held) — skipping"
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
