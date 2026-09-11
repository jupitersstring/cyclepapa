#!/usr/bin/env bash
# Flag any on-disk data file that isn't reachable from git.
#
# Exits non-zero (and prints offenders) when there is an at-risk file
# >= 100KB that is not in the index. Use this as a stop-hook /
# pre-commit guard against the failure mode from the other sandbox
# where data was gitignored and silently lost on reset.
#
# Whitelist (transient by design):
#   __pycache__/, *.pyc, *.pyo, *.log, .env, .venv/, .DS_Store,
#   pipeline.db-wal / -shm (SQLite sidecars; checkpointed)
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO"

THRESHOLD_BYTES=$((100 * 1024))
EXIT=0

while IFS= read -r f; do
    # gitignored AND on disk AND large -> at risk
    size=$(stat --printf='%s' "$f" 2>/dev/null || echo 0)
    if [ "$size" -ge "$THRESHOLD_BYTES" ]; then
        case "$f" in
            __pycache__/*|*.pyc|*.pyo|*.log|.env|.venv/*|.DS_Store| \
                pipeline.db-wal|pipeline.db-shm)
                ;;
            *)
                echo "AT-RISK $(numfmt --to=iec --suffix=B "$size") $f"
                EXIT=1
                ;;
        esac
    fi
done < <(git ls-files --others --ignored --exclude-standard 2>/dev/null)

# Also catch untracked-but-not-ignored files (someone forgot to commit)
while IFS= read -r f; do
    size=$(stat --printf='%s' "$f" 2>/dev/null || echo 0)
    if [ "$size" -ge "$THRESHOLD_BYTES" ]; then
        echo "UNTRACKED $(numfmt --to=iec --suffix=B "$size") $f"
        EXIT=1
    fi
done < <(git ls-files --others --exclude-standard 2>/dev/null)

if [ "$EXIT" -ne 0 ]; then
    echo
    echo "These files would be LOST on a sandbox reset. Either:"
    echo "  1. Track them:    git add <file> && git commit"
    echo "  2. Whitelist:     add to scripts/durability_guard.sh"
    echo "  3. Move them:     to .cache/docs/ (committed) or pipeline.db"
fi
exit $EXIT
