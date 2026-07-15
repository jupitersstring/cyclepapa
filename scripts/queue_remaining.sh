#!/bin/bash
# Sequentially run remaining markets, but wait until active Dalton processes
# drop below MAX_PARALLEL to avoid yfinance rate-limit storms.
cd "$(dirname "$0")/.."

MAX_PARALLEL=${MAX_PARALLEL:-3}
declare -a MARKETS=(
    "uk          ^FTSE"
    "italy       FTSEMIB.MI"
    "australia   ^AXJO"
    "taiwan      ^TWII"
    "germany     ^GDAXI"
    "korea       ^KS11"
    "france      ^FCHI"
    "hk          ^HSI"
    "sweden      ^OMXSPI"
    "singapore   ^STI"
    "switzerland ^SSMI"
    "spain       ^IBEX"
    "norway      ^OSEAX"
    "finland     ^OMXH25"
    "denmark     ^OMXC25"
    "netherlands ^AEX"
    "belgium     ^BFX"
    "nz          ^NZ50"
)

count_running() {
    pgrep -fc "dalton_complete_screen.py --universe data/universes/uni_" 2>/dev/null || echo 0
}

for entry in "${MARKETS[@]}"; do
    read -r mkt bench <<<"$entry"
    out="data/dalton/dalton_${mkt}.csv"
    if [ -f "$out" ] && [ "$(wc -l < "$out")" -gt 50 ]; then
        echo "[$mkt] already done, skipping"
        continue
    fi
    # Wait until parallel slot opens
    while [ "$(count_running)" -ge "$MAX_PARALLEL" ]; do
        sleep 60
    done
    echo "==============================================="
    echo "[$mkt] starting (benchmark=$bench, active=$(count_running))"
    echo "==============================================="
    # Run this market in background so we can move on after the slot frees again
    bash scripts/run_all_screens.sh "$mkt" "$bench" > "/tmp/log_${mkt}.txt" 2>&1 &
    sleep 30  # let the new process register in pgrep before next loop check
done

# Wait for all in-flight jobs to finish
while [ "$(count_running)" -gt 0 ]; do
    sleep 60
done
echo "ALL FOREIGN MARKETS DONE"
