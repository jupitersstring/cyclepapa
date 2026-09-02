#!/bin/bash
# Full pipeline update: refresh every data leg with current prices, then
# rebuild master, baskets, and the workbook, persisting at each stage.
#
#   Stage 1  refresh_legs.py        E + ADV + DSR (regional benchmarks), all 20K rows
#   Stage 2  psar_batch_scan.py     fresh MTF PSAR scan, full native universe
#   Stage 3  post-process:
#              is_clean filter -> /tmp/mtf_psar_rank_full_clean.csv
#              master_full_universe.py
#              build_baskets.py
#              build_workbook.py
#   Stage 4  persist_results.py     final commit + push
#
# Run: nohup bash update_all.sh > /tmp/update_all.log 2>&1 &

set -uo pipefail
cd /home/user/cyclepapa

echo "=== UPDATE ALL: started $(date -u) ==="

# Initial cooldown if Yahoo recently rate-limited us (cheap probe)
for i in 1 2 3 4 5 6; do
  if python - <<'PY' 2>/dev/null
import yfinance as yf, sys
d = yf.download("SPY", period="5d", interval="1d", progress=False)
sys.exit(0 if len(d) > 0 else 1)
PY
  then echo "yahoo probe OK"; break
  else echo "yahoo rate-limited; cooling 300s (attempt $i)"; sleep 300
  fi
done

echo "=== STAGE 1: refresh legs (E/ADV/DSR) ==="
# Fresh update run: clear the per-run region done-file so all regions
# actually refresh (it exists to make RETRIES within one run resumable).
rm -f /tmp/refresh_legs_done.txt
# Process-level retry: each attempt gets a fresh yfinance session, which is
# what actually clears Yahoo rate limits (they key on session cookies).
# Region done-file makes every attempt resume where the last stopped.
for i in 1 2 3 4 5 6 7 8; do
  python refresh_legs.py && break
  rc=$?
  echo "refresh_legs attempt $i exited rc=$rc; cooling 240s then fresh process"
  sleep 240
done

echo "=== STAGE 2: PSAR full rescan ==="
python psar_batch_scan.py --fresh || echo "WARN: psar_batch_scan exited nonzero"

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

echo "=== UPDATE ALL: finished $(date -u) ==="
