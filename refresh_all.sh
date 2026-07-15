#!/bin/bash
# Idempotent full refresh of the equity-screening workbooks from the durable
# cache. Safe to re-run: it rehydrates the price cache, regenerates each
# per-universe momentum CSV OFFLINE (only when missing or older than the
# engine code), then consolidates, enriches, backfills names and rebuilds both
# workbooks. Deterministic given the cache — no network required.
#
# Usage:
#   bash refresh_all.sh          # freshen (regen universes whose CSV is stale)
#   FORCE=1 bash refresh_all.sh  # force-regenerate every universe
set -uo pipefail
cd "$(dirname "$0")"

export CYCLEPAPA_OFFLINE=1
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1
mkdir -p /tmp/mr_logs
: > /tmp/mr_logs/_refresh_progress.log

echo "[1/6] rehydrating durable cache -> /tmp"
python3 bootstrap_cache.py >/tmp/mr_logs/_bootstrap.log 2>&1

# Equity universes = every cached universe except the *-etfs feeds.
ls /tmp/cyclepapa_dl_*_daily_2y.pkl 2>/dev/null \
  | sed -E 's#.*/cyclepapa_dl_(.*)_daily_2y\.pkl#\1#' \
  | grep -vE 'etfs$' | sort > /tmp/mr_logs/_equity_unis.txt
N=$(wc -l < /tmp/mr_logs/_equity_unis.txt)
echo "[2/6] regenerating momentum CSVs for $N universes (offline, P=4)"

run_one() {
  u="$1"
  csv=$(ls -t "momentum_rank_${u}_"*.csv 2>/dev/null | head -1)
  cache="/tmp/cyclepapa_dl_${u}_daily_2y.pkl"
  # Regenerate when forced, or when the CSV is missing, or older than the
  # engine code OR the (possibly freshly-updated) price cache.
  if [ -z "${FORCE:-}" ] && [ -n "$csv" ] && [ "$csv" -nt momentum_rank.py ] \
     && { [ ! -f "$cache" ] || [ "$csv" -nt "$cache" ]; }; then
    echo "$(date +%H:%M:%S) $u SKIP(fresh)" >> /tmp/mr_logs/_refresh_progress.log
    return
  fi
  timeout 1800 python3 momentum_rank.py --universe "$u" --top 40 \
    > "/tmp/mr_logs/${u}.log" 2>&1
  rc=$?
  n=$(ls -t "momentum_rank_${u}_"*.csv 2>/dev/null | head -1)
  rows=0; [ -n "$n" ] && rows=$(($(wc -l < "$n") - 1))
  echo "$(date +%H:%M:%S) $u rc=$rc rows=$rows" >> /tmp/mr_logs/_refresh_progress.log
}
export -f run_one
export FORCE="${FORCE:-}"
xargs -P 4 -I{} bash -c 'run_one "{}"' < /tmp/mr_logs/_equity_unis.txt

fails=$(grep -E "rc=[^0]" /tmp/mr_logs/_refresh_progress.log || true)
[ -n "$fails" ] && { echo "  WARNING: some universes failed:"; echo "$fails"; }

echo "[3/6] consolidating"
python3 consolidate_global_equities.py > /tmp/mr_logs/_consolidate.log 2>&1
echo "[4/6] FX-normalising ADV (offline) + classifying security types + backfilling names"
python3 fx_normalize_adv.py   > /tmp/mr_logs/_fx.log       2>&1
python3 security_type.py      > /tmp/mr_logs/_sectype.log  2>&1
python3 backfill_names.py      > /tmp/mr_logs/_backfill.log 2>&1
echo "[5/6] building harvard_workbook.xlsx"
python3 harvard_workbook.py   > /tmp/mr_logs/_harvard.log  2>&1
echo "[6/6] building global_best_full.xlsx"
python3 global_best_full_universe.py > /tmp/mr_logs/_gbf.log 2>&1

rows=$(python3 -c "import pandas as pd; print(len(pd.read_csv('global_equities_consolidated.csv',index_col=0,low_memory=False)))" 2>/dev/null)
echo "REFRESH COMPLETE — consolidated rows: ${rows:-?}"
ls -la harvard_workbook.xlsx global_best_full.xlsx 2>/dev/null | awk '{print "  ", $5, $9}'
