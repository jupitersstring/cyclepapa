#!/usr/bin/env bash
# SessionStart hook: make the analysis environment self-healing.
#  1. Install missing Python deps (sandboxes get wiped too, not just data).
#  2. Restore the cache+results snapshot from origin/cache-snapshot.
set -e
cd "$(dirname "$0")/../.."

# ---- 1. Dependencies ----
if command -v python3 >/dev/null 2>&1; then
    missing=$(python3 -c "
import importlib
for m in ('pandas','yfinance','financedatabase','pyarrow','openpyxl','scipy'):
    try: importlib.import_module(m)
    except Exception: print(m)
" 2>/dev/null || true)
    if [ -n "$missing" ]; then
        echo "[bootstrap] Installing: $(echo "$missing" | tr '\n' ' ')"
        pip install --quiet pandas yfinance financedatabase pyarrow openpyxl scipy lxml requests >/dev/null 2>&1 \
            && echo "[bootstrap] Deps installed." \
            || echo "[bootstrap] WARNING: pip install failed."
    fi
fi

# ---- 2. Cache restore ----
if [ -d .cache/yf ] && [ "$(ls .cache/yf 2>/dev/null | head -1)" ]; then
    exit 0
fi
if ! command -v python3 >/dev/null 2>&1; then exit 0; fi
python3 cache_sync.py pull 2>&1 | sed 's/^/[cache-restore] /' || true
