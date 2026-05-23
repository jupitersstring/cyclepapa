#!/bin/bash
# Run all remaining work in strict serial mode (one yfinance client at a time)
# so we don't keep tripping rate limits.
#
# Phase 1: Dalton + weekly screens for markets NOT yet started
# Phase 2: Rerun Dalton for rate-limit-damaged markets (capture < 20%)
# Phase 3: Rerun all fundamentals with long sleep
set -e
cd "$(dirname "$0")/.."

# Wait for any currently running yfinance work to clear
while pgrep -fc 'python3 (screeners|scripts)' >/dev/null 2>&1 && \
      [ "$(pgrep -fc 'python3 (screeners|scripts)' 2>/dev/null)" -gt 0 ]; do
    echo "[serial] waiting for in-flight processes ($(pgrep -fc 'python3 (screeners|scripts)') active)"
    sleep 60
done

echo "[serial] queue clear, starting phase 1"

# ─── PHASE 1: unstarted markets ───
declare -a NEW_MARKETS=(
    "spain       ^IBEX"
    "switzerland ^SSMI"
    "norway      ^OSEAX"
    "finland     ^OMXH25"
    "denmark     ^OMXC25"
    "netherlands ^AEX"
    "belgium     ^BFX"
    "nz          ^NZ50"
    "singapore   ^STI"
)
for entry in "${NEW_MARKETS[@]}"; do
    read -r mkt bench <<<"$entry"
    if [ -f "data/dalton/dalton_${mkt}.csv" ] && [ "$(wc -l < "data/dalton/dalton_${mkt}.csv")" -gt 50 ]; then
        echo "[serial] $mkt already done, skipping"
        continue
    fi
    echo "================== [P1] $mkt =================="
    bash scripts/run_all_screens.sh "$mkt" "$bench" > "/tmp/log_${mkt}.txt" 2>&1
    sleep 60  # cooldown between markets
done

# ─── PHASE 2: rerun rate-limit-damaged Dalton runs ───
declare -a RERUN_MARKETS=(
    "uk          ^FTSE"
    "italy       FTSEMIB.MI"
    "germany     ^GDAXI"
    "france      ^FCHI"
    "sweden      ^OMXSPI"
    "australia   ^AXJO"
    "taiwan      ^TWII"
)
for entry in "${RERUN_MARKETS[@]}"; do
    read -r mkt bench <<<"$entry"
    echo "================== [P2 rerun] $mkt =================="
    bash scripts/run_all_screens.sh "$mkt" "$bench" > "/tmp/log_rerun_${mkt}.txt" 2>&1
    sleep 90  # longer cooldown — we already know these are sensitive
done

# ─── PHASE 3: rerun all fundamentals with slow sleep ───
echo "================== [P3] Fundamentals (slow) =================="
for f in data/universes/uni_*.csv; do
    mkt=$(basename "$f" .csv | sed 's/uni_//')
    out="data/fundamentals/fund_${mkt}.csv"
    if [ -f "$out" ] && [ "$(stat -c%s "$out")" -gt 1000 ]; then
        echo "[serial] $mkt fundamentals already populated, skipping"
        continue
    fi
    echo "  $mkt fundamentals..."
    python3 scripts/pull_fundamentals.py --universe "$f" --out "$out" --sleep 2 --checkpoint 50 \
        > "/tmp/log_fund_${mkt}.txt" 2>&1
    sleep 30
done

echo "[serial] DONE all phases"
