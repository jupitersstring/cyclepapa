#!/bin/bash
# Long-patience resume loop for the Leledc scan: 10-minute cooldowns,
# 30 attempts (~5h). Resumes from /tmp/leledc_rank.csv. After completion,
# re-merges LELE into master, rebuilds the workbook, persists.

set -uo pipefail
cd /home/user/cyclepapa

for i in $(seq 1 30); do
  python leledc_scan.py && break
  rc=$?
  echo "leledc resume attempt $i exited rc=$rc; cooling 600s"
  sleep 600
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

echo "=== rebuilding workbook ==="
python build_workbook.py || echo "WARN: workbook exited nonzero"

echo "=== rebuilding uncorrelated basket (was empty due to rate limit) ==="
python build_baskets.py || echo "WARN: baskets exited nonzero"

echo "=== persist ==="
python persist_results.py || echo "WARN: persist exited nonzero"
echo "=== leledc_resume finished $(date -u) ==="
