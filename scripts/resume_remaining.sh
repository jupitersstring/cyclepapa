#!/bin/bash
# Resume what didn't finish before the container restart.
set -e
cd "$(dirname "$0")/.."

# Phase 2 leftovers (Dalton rerun for sparse markets)
declare -a P2=(
    "france      ^FCHI"
    "sweden      ^OMXSPI"
    "australia   ^AXJO"
    "taiwan      ^TWII"
    "switzerland ^SSMI"
)
for entry in "${P2[@]}"; do
    read -r mkt bench <<<"$entry"
    echo "================ [P2 resume] $mkt ================"
    bash scripts/run_all_screens.sh "$mkt" "$bench" > "/tmp/log_rerun_${mkt}.txt" 2>&1
    sleep 90
done

# Phase 3 - fundamentals for all markets still empty (slow sleep)
echo "================ [P3 resume] fundamentals ================"
for f in data/universes/uni_*.csv; do
    mkt=$(basename "$f" .csv | sed 's/uni_//')
    out="data/fundamentals/fund_${mkt}.csv"
    if [ -f "$out" ] && [ "$(stat -c%s "$out")" -gt 1000 ]; then
        echo "[resume] $mkt fundamentals already populated, skipping"
        continue
    fi
    echo "  $mkt fundamentals..."
    python3 scripts/pull_fundamentals.py --universe "$f" --out "$out" --sleep 2 --checkpoint 50 \
        > "/tmp/log_fund_${mkt}.txt" 2>&1
    sleep 30
done

echo "[resume] DONE"
