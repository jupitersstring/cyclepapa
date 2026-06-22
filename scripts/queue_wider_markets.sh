#!/bin/bash
# Run all 5 measures on each of the 18 new markets, serially, MAX_PARALLEL=1
# to avoid yfinance rate-limit storms. Skip markets with <10 tickers.
set -e
cd "$(dirname "$0")/.."

# (key, yfinance benchmark)
declare -a NEW_MARKETS=(
    # REMOVED india
    "china        000001.SS"
    "thailand     ^SET.BK"
    "brazil       ^BVSP"
    "israel       ^TA125.TA"
    "indonesia    ^JKSE"
    "southafrica  ^J203.JO"
    "ireland      ^ISEQ"
    "turkey       XU100.IS"
    "chile        ^IPSA"
    "mexico       ^MXX"
    "greece       ^GD.AT"
    "portugal     PSI20.LS"
    "argentina    ^MERV"
    "austria      ^ATX"
)

for entry in "${NEW_MARKETS[@]}"; do
    read -r mkt bench <<<"$entry"
    uni="data/universes/uni_${mkt}.csv"
    [ ! -f "$uni" ] && continue
    n=$(($(wc -l < "$uni") - 1))
    [ "$n" -lt 10 ] && { echo "[wider] $mkt: $n smid tickers, skipping"; continue; }
    # Skip if already done
    out="data/dalton/dalton_${mkt}.csv"
    if [ -f "$out" ] && [ "$(wc -l < "$out")" -gt 50 ]; then
        echo "[wider] $mkt smid already done, skipping"
        continue
    fi
    echo "============ [WIDER smid] $mkt ($n tickers) ============"
    bash scripts/run_all_screens.sh "$mkt" "$bench" > "/tmp/log_wider_${mkt}.txt" 2>&1
    sleep 60
done

# Then large
for entry in "${NEW_MARKETS[@]}"; do
    read -r mkt bench <<<"$entry"
    uni="data/universes/large/uni_${mkt}_lg.csv"
    [ ! -f "$uni" ] && continue
    n=$(($(wc -l < "$uni") - 1))
    [ "$n" -lt 5 ] && { echo "[wider lg] $mkt: $n large tickers, skipping"; continue; }
    out="data/dalton/dalton_${mkt}_lg.csv"
    if [ -f "$out" ] && [ "$(wc -l < "$out")" -gt 5 ]; then
        echo "[wider lg] $mkt already done, skipping"
        continue
    fi
    echo "============ [WIDER large] $mkt ($n tickers) ============"
    # Manually run each step for large file (run_all_screens uses smid path)
    python3 screeners/dalton_complete_screen.py --universe "$uni" --out "data/dalton/dalton_${mkt}_lg.csv" --benchmark "$bench" > "/tmp/log_wider_lg_dalton_${mkt}.txt" 2>&1
    python3 screeners/absorption_screen.py --universe "$uni" --out "data/absorption/absorp_${mkt}_lg.csv" --interval 1wk --window 12 > "/tmp/log_wider_lg_abs_${mkt}.txt" 2>&1
    python3 screeners/prebreakout_screen.py --universe "$uni" --out "data/prebreakout/prebo_${mkt}_lg.csv" > "/tmp/log_wider_lg_pre_${mkt}.txt" 2>&1
    cp "$uni" /tmp/screen_universe.csv
    python3 screeners/compression_weekly.py > "/tmp/log_wider_lg_comp_${mkt}.txt" 2>&1
    cp /tmp/tech_compression_weekly.csv "data/compression/compress_${mkt}_lg.csv" 2>/dev/null || true
    python3 scripts/pull_fundamentals.py --universe "$uni" --out "data/fundamentals/fund_${mkt}_lg.csv" --sleep 2 --checkpoint 50 > "/tmp/log_wider_lg_fund_${mkt}.txt" 2>&1
    sleep 60
done

echo "[wider] DONE all new markets"
