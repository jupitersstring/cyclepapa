#!/bin/bash
# Run all 6 measures on one market and write to data/.
# Args: <market_key> <yf_benchmark>   e.g.  bash run_all_screens.sh us SPY
set -e
cd "$(dirname "$0")/.."

mkt="$1"
bench="$2"
uni="data/universes/uni_${mkt}.csv"

if [ ! -f "$uni" ]; then
    echo "Universe not found: $uni"; exit 1
fi

mkdir -p data/dalton data/absorption data/compression data/prebreakout data/td_seq data/fundamentals

echo "[$mkt] === Dalton complete ==="
python3 screeners/dalton_complete_screen.py \
    --universe "$uni" --out "data/dalton/dalton_${mkt}.csv" \
    --benchmark "$bench" 2>&1 | tail -20

echo "[$mkt] === Absorption ==="
python3 screeners/absorption_screen.py \
    --universe "$uni" --out "data/absorption/absorp_${mkt}.csv" \
    --interval 1wk --window 12 2>&1 | tail -5

echo "[$mkt] === Pre-breakout ==="
python3 screeners/prebreakout_screen.py \
    --universe "$uni" --out "data/prebreakout/prebo_${mkt}.csv" 2>&1 | tail -5

# Compression screener has hardcoded universe path — feed it
echo "[$mkt] === Compression weekly ==="
cp "$uni" /tmp/screen_universe.csv
python3 screeners/compression_weekly.py 2>&1 | tail -5
cp /tmp/tech_compression_weekly.csv "data/compression/compress_${mkt}.csv" 2>/dev/null || true

echo "[$mkt] === Compression monthly ==="
cp "$uni" /tmp/screen_universe.csv
python3 screeners/compression_monthly.py 2>&1 | tail -5
cp /tmp/tech_compression.csv "data/compression/compress_monthly_${mkt}.csv" 2>/dev/null || true

echo "[$mkt] === Fundamentals ==="
python3 scripts/pull_fundamentals.py --universe "$uni" --out "data/fundamentals/fund_${mkt}.csv" 2>&1 | tail -5

echo "[$mkt] DONE ALL SCREENS"
