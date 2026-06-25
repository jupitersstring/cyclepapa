#!/bin/bash
# Yahoo block watcher. Polls every N minutes; when yfinance .info works again,
# kicks off the gap-fill work:
#   1. yfinance compounder research on SEC-missing US tickers + foreign markets
#   2. Resume widen_chain (Dalton/screens/fund for Greece/Portugal/Argentina/Austria,
#      plus filling fundamentals for new markets)
#   3. Run fundamentals gap-fill v3 on all tickers with null EV/EBITDA
#
# Safe to run multiple times — exits if Yahoo work is already running.
set -e
cd "$(dirname "$0")/.."

POLL_MIN=${POLL_MIN:-180}  # Each probe counts against Yahoo's rate-limit window — back WAY off (was 15)
COOLDOWN_LOCK=/tmp/yfinance_cooldown.lock

# Don't double-launch — match only direct invocations (not shell snapshots)
my_pid=$$
others=$(pgrep -a -f 'yahoo_watcher.sh$\|yahoo_watcher.sh ' 2>/dev/null | awk -v me=$my_pid '$1!=me {print $1}')
if [ -n "$others" ]; then
    echo "[watcher] another instance running (PID $others) — exiting"
    exit 0
fi
echo "[watcher pid=$my_pid] started"

check_yahoo() {
    PYTHONPATH=/home/user/cyclepapa/scripts timeout 15 python3 -c "
import yf_patch, yfinance as yf, warnings
warnings.filterwarnings('ignore')
try:
    info = yf.Ticker('AAPL').info
    rev = info.get('totalRevenue')
    if rev: print('OK'); exit(0)
    else: print('NULL'); exit(1)
except Exception as e:
    print('BLOCKED:', str(e)[:60]); exit(1)
" 2>&1
}

while true; do
    status=$(check_yahoo | tail -1)
    ts=$(date -u +%H:%M:%SZ)
    if [ "$status" = "OK" ]; then
        echo "[watcher $ts] Yahoo UNBLOCKED — launching gap-fill work"
        rm -f "$COOLDOWN_LOCK"
        break
    fi
    echo "[watcher $ts] still blocked: $status — sleep ${POLL_MIN}m"
    sleep "${POLL_MIN}m"
done

# ─── 1. yfinance compounder research — SEC-missing US (OTC, foreign-listed) ───
python3 - << 'PY'
import pandas as pd, json, os
uni = pd.read_csv('data/universes/us_nms.csv')
if os.path.exists('/tmp/sec_tickers.json'):
    with open('/tmp/sec_tickers.json') as f: d = json.load(f)
    sec_tickers = {v['ticker'].upper() for v in d.values()}
    uni['has_cik'] = uni['ticker'].str.upper().isin(sec_tickers)
    missing = uni[~uni['has_cik']]
    missing[['ticker']].to_csv('data/universes/us_nms_sec_missing.csv', index=False)
    print(f'SEC-missing US tickers (for yfinance): {len(missing)}')
PY

if [ -f data/universes/us_nms_sec_missing.csv ]; then
    n=$(($(wc -l < data/universes/us_nms_sec_missing.csv) - 1))
    if [ "$n" -gt 50 ]; then
        echo "[watcher] launching yfinance puller on $n SEC-missing US tickers"
        nohup python3 scripts/pull_compounder_research_v2.py \
            --universe data/universes/us_nms_sec_missing.csv \
            --out data/research/roic_us_nms_yf.csv \
            --workers 6 --rate 0.6 --checkpoint 50 --resume \
            > /tmp/log_yf_sec_missing.txt 2>&1 &
        disown
    fi
fi

# ─── 2. yfinance compounder research — foreign markets (UK, Germany, France, Japan, Canada, Australia) ───
for path in data/universes/uni_uk.csv data/universes/uni_germany.csv \
            data/universes/uni_france.csv data/universes/uni_japan.csv \
            data/universes/uni_canada.csv data/universes/uni_australia.csv \
            data/universes/uni_italy.csv data/universes/uni_spain.csv; do
    [ -f "$path" ] || continue
    name=$(basename "$path" .csv | sed 's/uni_//')
    out="data/research/roic_${name}_yf.csv"
    n=$(($(wc -l < "$path") - 1))
    [ "$n" -lt 50 ] && continue
    # Skip if already mostly done
    if [ -f "$out" ] && [ "$(stat -c%s "$out" 2>/dev/null)" -gt 1000000 ]; then continue; fi
    echo "[watcher] queueing $name research"
    nohup python3 scripts/pull_compounder_research_v2.py \
        --universe "$path" --out "$out" \
        --workers 4 --rate 0.5 --checkpoint 50 --resume \
        > "/tmp/log_yf_research_${name}.txt" 2>&1 &
    disown
    sleep 30  # stagger
done

# ─── 3. Resume widen_chain for missing markets (Greece, Portugal, Argentina, Austria, Israel Dalton) ───
# Backfill monthly compression for all existing markets (weekly already done)
nohup bash scripts/backfill_compress_monthly.sh > /tmp/log_compm_backfill.txt 2>&1 &
disown

nohup bash scripts/master_expand_chain.sh > /tmp/log_master_expand.txt 2>&1 &
disown

echo "[watcher] DONE — kicked off SEC-missing, foreign-research, widen_chain"
