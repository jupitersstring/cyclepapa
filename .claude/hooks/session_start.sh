#!/usr/bin/env bash
# SessionStart hook — self-bootstrap the cyclepapa environment on a fresh (or
# resumed) Claude Code on the web container. A container reset wipes deps AND
# data, so this restores everything needed to run the pipeline without manual
# recovery:
#
#   1. Python deps — from the PINNED requirements.txt (pandas 2.x etc.), so a
#      fresh container doesn't pull the latest pandas 3.x and run ~2x slower.
#   2. Cache + results — restored from origin/cache-snapshot, but ONLY when the
#      working tree is missing them (never re-pull ~1.4 GB on a plain resume).
#   3. Fetch daemons — started/healed via run_daemons.sh, but ONLY once the
#      cache is actually present. Starting them on an empty cache would let the
#      periodic snapshot push overwrite the good snapshot with a sparse one.
#      (cache_sync.py push also guards against that, so this is belt+braces.)
#
# Best-effort and idempotent: NO `set -e` (a failing sub-step must not abort the
# rest of the bootstrap), each step guarded, safe to re-run. Non-interactive.
set -uo pipefail
cd "$(dirname "$0")/../.."

log() { echo "[session-start] $*"; }

# Remote (Claude Code on the web) only — never touch a developer's local checkout.
if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
    log "local session — skipping bootstrap."
    exit 0
fi

# --- 1. Python deps (pinned) --------------------------------------------------
if [ -f requirements.txt ]; then
    log "installing pinned deps from requirements.txt ..."
    pip install -q -r requirements.txt \
        && log "deps ready." \
        || log "WARNING: pip install returned non-zero (continuing)."
fi

# --- 2. Cache restore (only when missing) -------------------------------------
count_tickers() {
    local c=0
    [ -d .cache/yf ] && c=$(find .cache/yf -name '*__info_metrics.parquet' 2>/dev/null \
        | head -500 | wc -l | tr -d ' ')
    echo "${c:-0}"
}
n=$(count_tickers)
if [ "$n" -lt 100 ]; then
    log "cache sparse (${n} tickers) — restoring from origin/cache-snapshot ..."
    if [ -f cache_sync.py ]; then
        # The git proxy can flap; retry with backoff.
        for attempt in 1 2 3; do
            if python3 cache_sync.py pull 2>&1 | sed 's/^/[session-start]   /'; then
                break
            fi
            log "restore attempt ${attempt} failed; retrying in $((attempt*5))s ..."
            sleep $((attempt*5))
        done
    fi
    n=$(count_tickers)   # re-count after restore
else
    log "cache already populated (${n}+ tickers) — skipping restore."
fi

# --- 3. Fetch daemons (only if the cache is real) -----------------------------
# Guard on a populated cache so a failed restore never leads to the daemons
# snapshotting an empty cache over the good one.
if [ "$n" -ge 100 ] && [ -f run_daemons.sh ]; then
    log "starting / healing fetch daemons ..."
    bash run_daemons.sh >/dev/null 2>&1 \
        && log "daemons up." \
        || log "WARNING: run_daemons.sh returned non-zero (continuing)."
elif [ "$n" -lt 100 ]; then
    log "cache still sparse after restore — NOT starting daemons (protects the snapshot)."
fi

log "bootstrap complete."
exit 0
