#!/bin/bash
# The scheduled run (a fresh checkout each time): rebuild the database from
# the committed snapshot, then the quarterly 13F roll when a new quarter's
# books are due (roll_due.py), else the daily refresh. Either ends with the
# four books rendered and the snapshot dumped; commit and push afterwards so
# the next run's "What Changed" compares against this one.
#
#   bash pipeline/run_scheduled.sh
set -eo pipefail
cd "$(dirname "$0")/.."
if [ -z "${FMP_API_KEY:-}" ] && [ ! -s data/.fmp_key ]; then
  echo "FATAL: no FMP key — set FMP_API_KEY in the environment (or data/.fmp_key)"; exit 1
fi
[ -s data/cyclepapa.db ] || python3 pipeline/snapshot.py restore | tail -3
if python3 pipeline/roll_due.py; then
  bash pipeline/rebuild_13f.sh
else
  bash pipeline/refresh_daily.sh
fi
