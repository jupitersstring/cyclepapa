#!/bin/bash
# Run all 5 measures on the EXPANDED US/UK/Europe universes, using
# multi-worker fundamentals for speed. Outputs land in data/{...}/<mkt>_x.csv
# so we can merge with existing data without overwriting.
set -e
cd "$(dirname "$0")/.."

# (key, yfinance benchmark)
declare -a EX_MARKETS=(
    "us           SPY"
    "uk           ^FTSE"
    "germany      ^GDAXI"
    "france       ^FCHI"
    "italy        FTSEMIB.MI"
    "spain        ^IBEX"
    "netherlands  ^AEX"
    "belgium      ^BFX"
    "switzerland  ^SSMI"
    "sweden       ^OMXSPI"
    "norway       ^OSEAX"
    "finland      ^OMXH25"
    "denmark      ^OMXC25"
    "austria      ^ATX"
    "ireland      ^ISEQ"
    "portugal     PSI20.LS"
    "greece       ^GD.AT"
)

mkdir -p data/dalton data/absorption data/prebreakout data/compression data/fundamentals

for entry in "${EX_MARKETS[@]}"; do
    read -r mkt bench <<<"$entry"
    uni="data/universes/expanded/uni_${mkt}_x.csv"
    [ ! -f "$uni" ] && continue
    n=$(($(wc -l < "$uni") - 1))
    [ "$n" -lt 10 ] && { echo "[expansion] $mkt: $n tickers, skip"; continue; }
    echo "============ [EX] $mkt ($n expanded tickers) ============"

    # Dalton (single-process — uses bulk yf.download internally)
    out_dal="data/dalton/dalton_${mkt}_x.csv"
    if [ ! -f "$out_dal" ] || [ "$(stat -c%s "$out_dal" 2>/dev/null)" -lt 1000 ]; then
        python3 screeners/dalton_complete_screen.py \
            --universe "$uni" --out "$out_dal" --benchmark "$bench" \
            > "/tmp/log_ex_dalton_${mkt}.txt" 2>&1
        rows=$(($(wc -l < "$out_dal" 2>/dev/null) - 1))
        echo "[expansion] $mkt dalton: $rows kept"
    fi

    out_abs="data/absorption/absorp_${mkt}_x.csv"
    [ ! -f "$out_abs" ] && python3 screeners/absorption_screen.py \
        --universe "$uni" --out "$out_abs" --interval 1wk --window 12 \
        > "/tmp/log_ex_abs_${mkt}.txt" 2>&1 || true

    out_pre="data/prebreakout/prebo_${mkt}_x.csv"
    [ ! -f "$out_pre" ] && python3 screeners/prebreakout_screen.py \
        --universe "$uni" --out "$out_pre" \
        > "/tmp/log_ex_pre_${mkt}.txt" 2>&1 || true

    out_comp="data/compression/compress_${mkt}_x.csv"
    if [ ! -f "$out_comp" ]; then
        cp "$uni" /tmp/screen_universe.csv
        python3 screeners/compression_weekly.py > "/tmp/log_ex_comp_${mkt}.txt" 2>&1 || true
        cp /tmp/tech_compression_weekly.csv "$out_comp" 2>/dev/null || true
    fi

    # Fundamentals (multi-worker)
    out_fund="data/fundamentals/fund_${mkt}_x.csv"
    if [ ! -f "$out_fund" ] || [ "$(stat -c%s "$out_fund" 2>/dev/null)" -lt 1000 ]; then
        python3 scripts/pull_fundamentals_mw.py \
            --universe "$uni" --out "$out_fund" \
            --workers 4 --rate 0.6 --checkpoint 100 --resume \
            > "/tmp/log_ex_fund_${mkt}.txt" 2>&1
    fi
    sleep 30  # cooldown between markets
done

echo "[expansion] DONE all markets"
