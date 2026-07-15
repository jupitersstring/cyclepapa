#!/bin/bash
# Chained final pipeline:
#   1. Wait for recovery to finish (almost done — netherlands left)
#   2. Backfill fundamentals for markets where fund rows < 50% of dalton rows
#   3. Build Large+Mega universes via financedatabase
#   4. Run all 5 measures on Large+Mega
set -e
cd "$(dirname "$0")/.."

# ─── 1. Wait for recovery ───
while pgrep -f recovery_pass.sh >/dev/null 2>&1; do
    echo "[final] recovery still running"
    sleep 300
done
while [ "$(pgrep -fc 'python3 (screeners|scripts/pull)' 2>/dev/null)" -gt 0 ]; do
    echo "[final] yfinance process still active"
    sleep 120
done
echo "[final] recovery done"

# ─── 2. Backfill sparse fundamentals ───
echo "[final] === fund backfill pass ==="
for f in data/fundamentals/fund_*.csv; do
    [ -f "$f" ] || continue
    bn=$(basename "$f" .csv)
    case "$bn" in *_recovery|*_lg) continue;; esac
    mkt=${bn#fund_}
    dal="data/dalton/dalton_${mkt}.csv"
    uni="data/universes/uni_${mkt}.csv"
    [ ! -f "$dal" ] || [ ! -f "$uni" ] && continue
    fund_n=$(($(wc -l < "$f") - 1))
    dal_n=$(($(wc -l < "$dal") - 1))
    [ "$dal_n" -lt 50 ] && continue
    if [ "$fund_n" -lt $((dal_n / 2)) ]; then
        echo "[final] backfilling $mkt fund ($fund_n / $dal_n dalton rows)"
        tmp_out="data/fundamentals/fund_${mkt}_backfill.csv"
        python3 scripts/pull_fundamentals.py --universe "$uni" --out "$tmp_out" \
            --sleep 2 --checkpoint 50 > "/tmp/log_backfill_${mkt}.txt" 2>&1
        # Merge into main
        python3 -c "
import pandas as pd
try: a = pd.read_csv('$f')
except: a = pd.DataFrame()
b = pd.read_csv('$tmp_out')
m = pd.concat([a, b], ignore_index=True).drop_duplicates(subset='ticker', keep='first')
m.to_csv('$f', index=False)
print(f'  $mkt fund: {len(a)} + {len(b)} -> {len(m)}')
"
        sleep 60
    fi
done

# ─── 3. Build Large+Mega universes ───
echo "[final] === building Large+Mega universes ==="
python3 scripts/build_large_universes.py 2>&1

# ─── 4. Run all measures on Large+Mega ───
echo "[final] === running Large+Mega pipeline ==="
mkdir -p data/dalton data/absorption data/prebreakout data/compression data/fundamentals

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
    if [ ! -f "$uni" ]; then continue; fi
    n=$(($(wc -l < "$uni") - 1))
    if [ "$n" -lt 5 ]; then echo "[final] $mkt: $n large, skipping"; continue; fi
    echo "============ [LG] $mkt ($n large/mega) ============"

    out_dal="data/dalton/dalton_${mkt}_lg.csv"
    if [ ! -f "$out_dal" ] || [ "$(stat -c%s "$out_dal")" -lt 1000 ]; then
        python3 screeners/dalton_complete_screen.py \
            --universe "$uni" --out "$out_dal" --benchmark "$bench" \
            > "/tmp/log_lg_dalton_${mkt}.txt" 2>&1
    fi

    out_abs="data/absorption/absorp_${mkt}_lg.csv"
    [ ! -f "$out_abs" ] && python3 screeners/absorption_screen.py \
        --universe "$uni" --out "$out_abs" --interval 1wk --window 12 \
        > "/tmp/log_lg_abs_${mkt}.txt" 2>&1

    out_pre="data/prebreakout/prebo_${mkt}_lg.csv"
    [ ! -f "$out_pre" ] && python3 screeners/prebreakout_screen.py \
        --universe "$uni" --out "$out_pre" \
        > "/tmp/log_lg_pre_${mkt}.txt" 2>&1

    out_comp="data/compression/compress_${mkt}_lg.csv"
    if [ ! -f "$out_comp" ]; then
        cp "$uni" /tmp/screen_universe.csv
        python3 screeners/compression_weekly.py > "/tmp/log_lg_comp_${mkt}.txt" 2>&1
        cp /tmp/tech_compression_weekly.csv "$out_comp" 2>/dev/null || true
    fi

    out_fund="data/fundamentals/fund_${mkt}_lg.csv"
    if [ ! -f "$out_fund" ] || [ "$(stat -c%s "$out_fund")" -lt 1000 ]; then
        python3 scripts/pull_fundamentals.py --universe "$uni" --out "$out_fund" \
            --sleep 2 --checkpoint 50 > "/tmp/log_lg_fund_${mkt}.txt" 2>&1
    fi

    sleep 60
done

echo "[final] DONE — fund-backfill + large+mega complete"
