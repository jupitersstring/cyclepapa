#!/bin/bash
# Auto-commit + push loop. Every 5 minutes, if there are new/modified files
# under data/, stage everything, commit with a timestamp, and push. This
# protects all screener outputs from sandbox resets via the git remote.
set -e
cd "$(dirname "$0")/.."
BRANCH="$(git rev-parse --abbrev-ref HEAD)"
echo "[auto-commit] watching data/ on branch $BRANCH"

while true; do
    if [ -n "$(git status --porcelain data/)" ]; then
        ts="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
        git add data/
        git commit -m "data snapshot $ts" >/dev/null 2>&1 || true
        # Up to 4 retries with backoff for transient push failures
        delay=2
        for attempt in 1 2 3 4; do
            if git push -u origin "$BRANCH" >/dev/null 2>&1; then
                echo "[auto-commit] pushed snapshot $ts"
                break
            fi
            echo "[auto-commit] push attempt $attempt failed, sleeping ${delay}s"
            sleep $delay
            delay=$((delay * 2))
        done
    fi
    sleep 300
done
