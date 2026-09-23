#!/bin/bash
# Stage 2+ of the update: PSAR rescan (process-level retry) then rebuild.
# Stage 1 (legs refresh) already completed and persisted.

set -uo pipefail
cd /home/user/cyclepapa

echo "=== STAGE 2: PSAR full rescan (process-level retry) ==="
# psar_batch_scan resumes from its output file, so retries continue
# where the last attempt stopped. First attempt keeps --fresh semantics
# only if no output exists yet.
rm -f /tmp/mtf_psar_rank_full.csv
for i in 1 2 3 4 5 6 7 8 9 10; do
  python psar_batch_scan.py && break
  rc=$?
  echo "psar attempt $i exited rc=$rc; cooling 240s then fresh process"
  sleep 240
done

echo "=== STAGE 3: rebuild master + baskets + workbook ==="
python - <<'PY'
import pandas as pd
df = pd.read_csv('/tmp/mtf_psar_rank_full.csv').drop_duplicates('ticker')
def keep(t):
    t = str(t)
    if '.' not in t:
        return not (len(t) == 5 and t[-1] in ('F', 'Y'))
    return True
df = df[df.ticker.map(keep)]
df.to_csv('/tmp/mtf_psar_rank_full_clean.csv', index=False)
print(f"cleaned PSAR: {len(df)} rows")
PY
python master_full_universe.py || echo "WARN: master exited nonzero"
python build_baskets.py || echo "WARN: baskets exited nonzero"
python build_workbook.py || echo "WARN: workbook exited nonzero"

echo "=== STAGE 4: persist ==="
python persist_results.py || echo "WARN: persist exited nonzero"

echo "=== STAGE2+ finished $(date -u) ==="
