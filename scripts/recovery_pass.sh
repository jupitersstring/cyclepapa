#!/bin/bash
# Recovery pass: run Dalton + fundamentals on tickers that were skipped due to
# yfinance rate limits in earlier passes. Merges results back into the main
# data/{dalton,fundamentals}/<market>.csv files.
#
# Waits for the current resume_remaining.sh to finish before starting.
set -e
cd "$(dirname "$0")/.."

# Wait for in-flight screener/fund work to finish
while [ "$(pgrep -fc 'python3 (screeners|scripts/pull_fund)' 2>/dev/null)" -gt 0 ]; do
    cnt=$(pgrep -fc 'python3 (screeners|scripts/pull_fund)' 2>/dev/null)
    echo "[recovery] waiting for in-flight ($cnt active)"
    sleep 120
done

echo "[recovery] queue clear, starting recovery"

# Markets in priority order (biggest gaps first)
declare -a MARKETS=(
    "us          SPY"
    "japan       ^N225"
    "canada      ^GSPTSE"
    "korea       ^KS11"
    "germany     ^GDAXI"
    "taiwan      ^TWII"
    "hk          ^HSI"
    "australia   ^AXJO"
    "sweden      ^OMXSPI"
    "france      ^FCHI"
    "switzerland ^SSMI"
    "italy       FTSEMIB.MI"
    "norway      ^OSEAX"
    "uk          ^FTSE"
    "singapore   ^STI"
    "denmark     ^OMXC25"
    "finland     ^OMXH25"
    "spain       ^IBEX"
    "nz          ^NZ50"
    "belgium     ^BFX"
    "netherlands ^AEX"
)

for entry in "${MARKETS[@]}"; do
    read -r mkt bench <<<"$entry"
    rec_uni="data/universes/recovery/uni_${mkt}_missed.csv"
    if [ ! -f "$rec_uni" ]; then
        echo "[recovery] $mkt: no missed file, skipping"
        continue
    fi
    miss_n=$(($(wc -l < "$rec_uni") - 1))
    if [ "$miss_n" -lt 20 ]; then
        echo "[recovery] $mkt: only $miss_n missed, skipping"
        continue
    fi
    echo "============== [REC] $mkt ($miss_n missed) =============="

    # Skip if recovery files already exist (resuming after restart)
    rec_out="data/dalton/dalton_${mkt}_recovery.csv"
    fund_rec="data/fundamentals/fund_${mkt}_recovery.csv"
    if [ -f "$rec_out" ] && [ -f "$fund_rec" ] && \
       [ "$(stat -c%s "$rec_out")" -gt 1000 ] && \
       [ "$(stat -c%s "$fund_rec")" -gt 1000 ]; then
        echo "[recovery] $mkt: recovery files already populated, skipping"
        continue
    fi

    # Dalton on missed only
    python3 screeners/dalton_complete_screen.py \
        --universe "$rec_uni" --out "$rec_out" --benchmark "$bench" \
        > "/tmp/log_rec_dalton_${mkt}.txt" 2>&1
    rec_rows=$(($(wc -l < "$rec_out" 2>/dev/null) - 1))
    [ "$rec_rows" -lt 0 ] && rec_rows=0
    echo "[recovery] $mkt dalton: recovered $rec_rows new rows"

    # Merge dedupe into main
    main="data/dalton/dalton_${mkt}.csv"
    if [ -f "$main" ] && [ "$rec_rows" -gt 0 ]; then
        python3 -c "
import pandas as pd
a = pd.read_csv('$main')
b = pd.read_csv('$rec_out')
m = pd.concat([a, b], ignore_index=True).drop_duplicates(subset='ticker', keep='first')
m.to_csv('$main', index=False)
print(f'  merged main: {len(a)} + recovered: {len(b)} -> {len(m)} unique')
" 2>&1
    fi

    # Fundamentals on missed (serial, slow)
    fund_rec="data/fundamentals/fund_${mkt}_recovery.csv"
    fund_main="data/fundamentals/fund_${mkt}.csv"
    python3 scripts/pull_fundamentals.py --universe "$rec_uni" --out "$fund_rec" \
        --sleep 2 --checkpoint 50 > "/tmp/log_rec_fund_${mkt}.txt" 2>&1
    fund_rows=$(($(wc -l < "$fund_rec" 2>/dev/null) - 1))
    [ "$fund_rows" -lt 0 ] && fund_rows=0
    echo "[recovery] $mkt fund: recovered $fund_rows rows"

    # Merge fundamentals
    if [ -f "$fund_main" ] && [ "$fund_rows" -gt 0 ]; then
        python3 -c "
import pandas as pd
import os
try:
    a = pd.read_csv('$fund_main')
except Exception:
    a = pd.DataFrame()
b = pd.read_csv('$fund_rec')
m = pd.concat([a, b], ignore_index=True).drop_duplicates(subset='ticker', keep='first')
m.to_csv('$fund_main', index=False)
print(f'  merged fund: {len(a)} + recovered: {len(b)} -> {len(m)} unique')
" 2>&1
    fi

    sleep 60  # cooldown between markets
done

echo "[recovery] DONE all markets"
