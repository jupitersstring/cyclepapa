#!/bin/bash
# Auto-commit screener result CSVs at the end of each session.
# Runs after the conversation stops. Idempotent: bails cleanly if there's
# nothing to commit. Never force-pushes; only adds CSVs and the screener,
# never staged binary caches.
set -euo pipefail

# Only run in the remote sandbox — locally users manage their own commits.
if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

cd "${CLAUDE_PROJECT_DIR:-$(pwd)}"

# Stage every tracked or new result CSV + ipynb + the screener source.
git add -A -- '*.csv' '*.py' 'CLAUDE.md' '.claude/' 2>/dev/null || true

# Nothing to do?
if git diff --cached --quiet; then
  exit 0
fi

# Pull latest before committing so we don't fork.
BRANCH=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo main)
git pull --rebase --autostash origin "$BRANCH" 2>/dev/null || true

git commit -m "auto-checkpoint: session results $(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  --no-verify >/dev/null 2>&1 || exit 0

# Push with retry-on-network.
for attempt in 1 2 3 4; do
  if git push origin "$BRANCH" 2>/dev/null; then
    exit 0
  fi
  sleep $((attempt * attempt))
done
echo "stop-hook: push failed after 4 attempts" >&2
exit 0  # never block the session on push failure
