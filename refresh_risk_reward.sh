#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# refresh_risk_reward.sh -- rebuild the companion risk-reward book on the
# CURRENT engine, so both usual-universe books stay in sync.
#
# The risk-reward engine lives on branch `claude/risk-reward-crossfeed`
# (portfolio/sizing: reward/risk ranking, waterfall Monte Carlo, sizing). Its
# only coupling to this engine is a read-only snapshot in data/psu_engine/:
#   full_universe_consensus.csv + discretionary_insider_conviction.json
# This script:
#   1. checks that branch out into a temporary worktree (never touches it),
#   2. drops in this engine's current snapshot files,
#   3. builds the book (python3 -m src.build_workbook),
#   4. saves it here as cyclepapa_risk_reward_workbook.xlsx.
# Nothing is committed or pushed to the risk-reward branch.
# ---------------------------------------------------------------------------
set -uo pipefail
cd "$(dirname "$0")"
REPO="$(pwd)"
BRANCH="claude/risk-reward-crossfeed"
OUT="$REPO/cyclepapa_risk_reward_workbook.xlsx"

git fetch -q origin "$BRANCH" || { echo "fetch of $BRANCH failed"; exit 1; }
WT="$(mktemp -d)"
trap 'git -C "$REPO" worktree remove --force "$WT" >/dev/null 2>&1; rm -rf "$WT"; git -C "$REPO" worktree prune' EXIT
git worktree add -q --detach "$WT" "origin/$BRANCH" || { echo "worktree add failed"; exit 1; }

SNAP="$WT/data/psu_engine"
mkdir -p "$SNAP"
cp full_universe_consensus.csv discretionary_insider_conviction.json "$SNAP/"
NAMES=$(($(wc -l < full_universe_consensus.csv) - 1))
cat > "$SNAP/SNAPSHOT.md" <<EOF
# PSU-engine snapshot (read-only cross-feed)

Source: cyclepapa branch claude/create-new-feature-Oopqq @ $(git rev-parse --short HEAD) ($(date -u +%Y-%m-%d)).
full_universe_consensus.csv ($NAMES names) + discretionary_insider_conviction.json.
Written by refresh_risk_reward.sh.
EOF

( cd "$WT" && python3 -m src.build_workbook ) || { echo "risk-reward build failed"; exit 1; }
cp "$WT/output/cyclepapa_risk_reward_workbook.xlsx" "$OUT"
echo "saved $OUT"
