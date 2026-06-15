#!/usr/bin/env bash
# Lock the current caches into git in one step. Run after any expensive fetch.
set -e
cd "$(dirname "$0")"
python3 persist.py snapshot
git add -f data/ results/
git commit -q -m "snapshot caches $(date -u +%Y-%m-%dT%H:%MZ)" || { echo "nothing to snapshot"; exit 0; }
for i in 1 2 3 4; do git push origin HEAD && break || sleep $((2**i)); done
echo "[snapshot] committed + pushed"
