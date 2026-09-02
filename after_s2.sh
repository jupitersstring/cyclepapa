#!/bin/bash
# Queued follow-up to update_stage2plus.sh:
#   1. Wait for "STAGE2+ finished" marker in /tmp/update_s2.log
#   2. Run the Leledc W/M exhaustion scan (process-level retry)
#   3. Merge LELE columns into the master universe CSV
#   4. Rebuild the workbook (picks up the Leledc tab) and persist

set -uo pipefail
cd /home/user/cyclepapa

echo "waiting for stage2+ to finish..."
until grep -qa "STAGE2+ finished" /tmp/update_s2.log 2>/dev/null; do
  sleep 60
done
echo "stage2+ done — starting Leledc scan $(date -u)"

for i in 1 2 3 4 5 6 7 8 9 10; do
  python leledc_scan.py && break
  rc=$?
  echo "leledc attempt $i exited rc=$rc; cooling 240s then fresh process"
  sleep 240
done

echo "=== merging LELE into master ==="
python - <<'PY'
import pandas as pd
master = pd.read_csv('/tmp/master_full_universe.csv', low_memory=False)
lele = pd.read_csv('/tmp/leledc_rank.csv').drop_duplicates('ticker')
cols = [c for c in lele.columns if c not in ('region',)]
master = master.drop(columns=[c for c in cols if c in master.columns and c != 'ticker'],
                     errors='ignore')
merged = master.merge(lele[cols], on='ticker', how='left')
merged.to_csv('/tmp/master_full_universe.csv', index=False)
print(f"merged: {merged.LELE.notna().sum()} of {len(merged)} have LELE")
PY

echo "=== rebuilding workbook with Leledc tab ==="
python build_workbook.py || echo "WARN: workbook exited nonzero"

echo "=== persist ==="
python persist_results.py || echo "WARN: persist exited nonzero"
echo "=== after_s2 finished $(date -u) ==="
