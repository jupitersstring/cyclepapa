#!/bin/bash
# Sequentially run the remaining markets after the first batch (US/Japan/Canada) clears.
# Smaller markets so this can run in 1 process at a time without hitting rate limits.
cd "$(dirname "$0")/.."

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

for entry in "${MARKETS[@]}"; do
    read -r mkt bench <<<"$entry"
    if [ -f "data/dalton/dalton_${mkt}.csv" ] && [ $(wc -l < "data/dalton/dalton_${mkt}.csv") -gt 50 ]; then
        echo "[$mkt] already done, skipping"
        continue
    fi
    echo "==================================================="
    echo "[$mkt] starting (benchmark=$bench)"
    echo "==================================================="
    bash scripts/run_all_screens.sh "$mkt" "$bench"
done

echo "ALL FOREIGN MARKETS DONE"
