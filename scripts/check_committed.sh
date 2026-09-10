#!/usr/bin/env bash
# Refuses to exit a session with uncommitted runtime data.
# Wire into ~/.claude/settings.json as a Stop hook:
#   "Stop": [{"hooks": [{"type":"command","command":"./scripts/check_committed.sh"}]}]

set -u

cd "$(dirname "$0")/.." || exit 1

# Lines that look like untracked / modified data files we care about
risky=$(git status --porcelain | grep -E '^(\?\?| M| A|MM) (data/|results_.*\.csv|top30_.*\.csv|signals_history\.csv|universe\.csv)' || true)

if [ -n "$risky" ]; then
    echo "::error:: DATA_PERSISTENCE.md violated — uncommitted runtime data:"
    echo "$risky" | head -20
    echo
    echo "Run:  git add -A && git commit -m 'snapshot' && git push"
    echo "Refusing to end session — this data does not survive sandbox reset."
    exit 1
fi
