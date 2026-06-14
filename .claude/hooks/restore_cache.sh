#!/usr/bin/env bash
# SessionStart hook — rehydrate the ephemeral cache/ from the DURABLE, git-tracked
# data/ snapshot whenever the sandbox is fresh or wiped. This is the safety net for
# Claude-Code-on-the-web: cache/ is gitignored and dies with the container, but
# data/ (universe + fundamentals + scored + raws.tar.gz + surprises) is committed,
# so a reset is fully recoverable with zero re-fetching. No-op when cache is intact.
set -uo pipefail
cd "$(dirname "$0")/../.." || exit 0
raw_count=$(find cache/raw -name '*.json' 2>/dev/null | wc -l | tr -d ' ')
if [ ! -f cache/scored.parquet ] || [ "${raw_count:-0}" -lt 1000 ]; then
  echo "[session-start] cache missing/thin (raws=$raw_count) — restoring from durable data/ snapshot…"
  python3 scripts/snapshot.py restore || echo "[session-start] restore failed (data/ snapshot may be absent)"
else
  echo "[session-start] cache intact (raws=$raw_count) — no restore needed."
fi
