#!/usr/bin/env bash
# Phase 1 expansion: LatAm + ASEAN + MEA gaps.
# Argentina, Chile, Malaysia, Saudi Arabia, Philippines, Vietnam,
# UAE, Egypt, Colombia, Peru, Romania.
#
# China (~7K names) deferred to a separate phase given universe size.

set -u
VENV=/tmp/venv/bin/python
SCRIPT=yartseva_db.py

run_scan() {
    local country="$1"
    local out="$2"
    local min_b="${3:-Nano Cap}"
    local max_b="${4:-Mega Cap}"
    local log="/tmp/${out%.csv}_scan.log"
    echo "=== $(date +%H:%M:%S)  $country  [$min_b -> $max_b]  -> $out  ==="
    "$VENV" "$SCRIPT" \
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

# Size-ordered ascending (smallest first for quick wins)
run_scan "United Arab Emirates" "ae_yartseva.csv"
run_scan "Peru"                  "pe_yartseva.csv"
run_scan "Colombia"              "co_yartseva.csv"
run_scan "Vietnam"               "vn_yartseva.csv"
run_scan "Philippines"           "ph_yartseva.csv"
run_scan "Saudi Arabia"          "sa_yartseva.csv"
run_scan "Argentina"             "ar_yartseva.csv"
run_scan "Malaysia"              "my_yartseva.csv"
run_scan "Egypt"                 "eg_yartseva.csv"
run_scan "Chile"                 "cl_yartseva.csv"

echo "=== $(date +%H:%M:%S)  GLOBAL EXPANSION PHASE 1 DONE ==="
