#!/usr/bin/env bash
# Re-run Malaysia + Egypt after pollution-guard patch.
set -u
VENV=/tmp/venv/bin/python
SCRIPT=yartseva_db.py

run_scan() {
    local country="$1"
    local out="$2"
    local log="/tmp/${out%.csv}_scan.log"
    echo "=== $(date +%H:%M:%S)  $country  -> $out  ==="
    "$VENV" "$SCRIPT" \
        --country "$country" --max 0 \
        --min-bucket "Nano Cap" --max-bucket "Mega Cap" \
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

run_scan "Malaysia" "my_yartseva.csv"
run_scan "Egypt"    "eg_yartseva.csv"

echo "=== $(date +%H:%M:%S)  MY+EG RESCUE DONE ==="
