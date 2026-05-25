#!/bin/bash
# After recovery completes, run all measures on Large + Mega cap tickers.
set -e
cd "$(dirname "$0")/.."

# Wait until recovery_pass.sh has finished
while pgrep -f recovery_pass.sh >/dev/null 2>&1 || \
      [ "$(pgrep -fc 'python3 (screeners|scripts/pull)' 2>/dev/null)" -gt 0 ]; do
    echo "[large] waiting for recovery to finish ($(pgrep -fc 'python3 (screeners|scripts/pull)') active)"
    sleep 300
done

echo "[large] recovery done — building large+mega universes via financedatabase"
python3 scripts/build_large_universes.py 2>&1

mkdir -p data/dalton data/absorption data/prebreakout data/compression data/fundamentals

# Markets in priority order
declare -a MARKETS=(
    "us          SPY"
    "japan       ^N225"
    "uk          ^FTSE"
    "germany     ^GDAXI"
    "france      ^FCHI"
    "canada      ^GSPTSE"
    "switzerland ^SSMI"
    "australia   ^AXJO"
    "korea       ^KS11"
    "hk          ^HSI"
    "taiwan      ^TWII"
    "italy       FTSEMIB.MI"
    "spain       ^IBEX"
    "sweden      ^OMXSPI"
    "netherlands ^AEX"
    "norway      ^OSEAX"
    "singapore   ^STI"
    "denmark     ^OMXC25"
    "finland     ^OMXH25"
    "belgium     ^BFX"
    "nz          ^NZ50"
)

for entry in "${MARKETS[@]}"; do
    read -r mkt bench <<<"$entry"
    uni="data/universes/large/uni_${mkt}_lg.csv"
    if [ ! -f "$uni" ]; then
        echo "[large] $mkt: no large file, skipping"
        continue
    fi
    n=$(($(wc -l < "$uni") - 1))
    if [ "$n" -lt 5 ]; then
        echo "[large] $mkt: only $n tickers, skipping"
        continue
    fi
    echo "============ [LG] $mkt ($n large/mega) ============"

    # Dalton
    out_dal="data/dalton/dalton_${mkt}_lg.csv"
    if [ ! -f "$out_dal" ] || [ "$(stat -c%s "$out_dal")" -lt 1000 ]; then
        python3 screeners/dalton_complete_screen.py \
            --universe "$uni" --out "$out_dal" --benchmark "$bench" \
            > "/tmp/log_lg_dalton_${mkt}.txt" 2>&1
        rows=$(($(wc -l < "$out_dal" 2>/dev/null) - 1))
        echo "[large] $mkt dalton: $rows rows"
    fi

    # Absorption
    out_abs="data/absorption/absorp_${mkt}_lg.csv"
    [ ! -f "$out_abs" ] && python3 screeners/absorption_screen.py \
        --universe "$uni" --out "$out_abs" --interval 1wk --window 12 \
        > "/tmp/log_lg_abs_${mkt}.txt" 2>&1

    # Pre-breakout
    out_pre="data/prebreakout/prebo_${mkt}_lg.csv"
    [ ! -f "$out_pre" ] && python3 screeners/prebreakout_screen.py \
        --universe "$uni" --out "$out_pre" \
        > "/tmp/log_lg_pre_${mkt}.txt" 2>&1

    # Compression
    out_comp="data/compression/compress_${mkt}_lg.csv"
    if [ ! -f "$out_comp" ]; then
        cp "$uni" /tmp/screen_universe.csv
        python3 screeners/compression_weekly.py > "/tmp/log_lg_comp_${mkt}.txt" 2>&1
        cp /tmp/tech_compression_weekly.csv "$out_comp" 2>/dev/null || true
    fi

    # Fundamentals (slow)
    out_fund="data/fundamentals/fund_${mkt}_lg.csv"
    if [ ! -f "$out_fund" ] || [ "$(stat -c%s "$out_fund")" -lt 1000 ]; then
        python3 scripts/pull_fundamentals.py --universe "$uni" --out "$out_fund" \
            --sleep 2 --checkpoint 50 > "/tmp/log_lg_fund_${mkt}.txt" 2>&1
    fi

    sleep 60
done

echo "[large] DONE all markets"
