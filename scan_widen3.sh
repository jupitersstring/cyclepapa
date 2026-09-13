#!/usr/bin/env bash
# Widen universe: add China (.SS/.SZ) and Romania. Sequential scans, single
# worker pair, 30s cooloff. China is large (~6800 names) so allow plenty of
# time. Skipping Bulgaria/Slovenia/Slovakia (<10 names each) and Russia
# (sanctions / untradeable from West).

set -u
PY=/usr/local/bin/python3
SCRIPT=yartseva_db.py

run_scan() {
    local country="$1"
    local out="$2"
    local min_b="${3:-Nano Cap}"
    local max_b="${4:-Mega Cap}"
    local log="/tmp/${out%.csv}_scan.log"
    echo "=== $(date +%H:%M:%S)  $country  [$min_b -> $max_b]  -> $out  ==="
    "$PY" "$SCRIPT" \
        --country "$country" --max 0 \
        --min-bucket "$min_b" --max-bucket "$max_b" \
        --include-uncategorized \
        --workers 2 --out "$out" \
        --top 10 --projection-n 4 \
        > "$log" 2>&1
    local rc=$?
    local rows=$(wc -l < "$out" 2>/dev/null || echo 0)
    echo "$(date +%H:%M:%S)  $country  exit=$rc  rows=$rows"
    rm -f "${out}.partial"
    sleep 30
}

run_scan "Romania" "ro_yartseva.csv"
run_scan "China"   "cn_yartseva.csv"

echo "=== $(date +%H:%M:%S)  WIDEN UNIVERSE DONE ==="
