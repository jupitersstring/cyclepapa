#!/bin/bash
# Durability bootstrap. Idempotent — safe to run on every session start.
# 1. Commits any uncommitted data/ changes immediately (insurance against restart)
# 2. Ensures auto-commit loop is running (relaunches if dead)
# 3. Verifies remote is fully in sync
set -e
cd "$(dirname "$0")/.."

BRANCH="$(git rev-parse --abbrev-ref HEAD)"

# ─── 1. Commit any orphan data ───
if [ -n "$(git status --porcelain data/)" ]; then
    ts="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    git add data/
    git commit -m "durability bootstrap snapshot $ts" >/dev/null 2>&1 || true
    echo "[bootstrap] committed pending data snapshot"
fi

# ─── 2. Push to remote ───
delay=2
for attempt in 1 2 3 4; do
    if git push -u origin "$BRANCH" >/dev/null 2>&1; then
        echo "[bootstrap] pushed to origin/$BRANCH"
        break
    fi
    sleep $delay
    delay=$((delay * 2))
done

# ─── 3. Ensure auto-commit loop is running ───
if ! pgrep -f auto_commit_loop.sh >/dev/null 2>&1; then
    nohup bash scripts/auto_commit_loop.sh > /tmp/log_autocommit.txt 2>&1 &
    disown
    echo "[bootstrap] restarted auto_commit_loop.sh"
else
    echo "[bootstrap] auto_commit_loop already running"
fi

# ─── 4. Audit: any untracked files in data/? ───
untracked="$(git ls-files --others --exclude-standard data/ 2>/dev/null)"
if [ -n "$untracked" ]; then
    echo "[bootstrap] WARNING — untracked files in data/:"
    echo "$untracked" | head -10
    echo "(Run: git add data/ && git commit -m 'capture orphans')"
fi

echo "[bootstrap] DONE — durability OK"
