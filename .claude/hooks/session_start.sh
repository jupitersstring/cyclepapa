#!/usr/bin/env bash
# SessionStart hook: ensures cache+results are restored from origin/cache-snapshot
# if the local working tree is missing them. Idempotent and silent on success.
set -euo pipefail

cd "$(dirname "$0")/../.."

# If the cache directory already has substantial content, do nothing.
if [ -d .cache/yf ]; then
    n=$(find .cache/yf -name '*__info_metrics.parquet' 2>/dev/null | head -200 | wc -l)
    if [ "$n" -gt 50 ]; then
        echo "[session-start] .cache/yf already populated ($n+ tickers) — no restore needed."
        exit 0
    fi
fi

# Try to restore. If no snapshot exists yet, that's fine — exit 0.
if [ -f cache_sync.py ]; then
    echo "[session-start] Restoring .cache/ + results from origin/cache-snapshot..."
    python3 cache_sync.py pull || echo "[session-start] No snapshot to pull (first run)."
fi

exit 0
