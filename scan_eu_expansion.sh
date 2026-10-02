#!/usr/bin/env bash
# Fill remaining European gaps:
#   1. Poland & Iceland - both nano/micro/small AND large cap (no prior scan)
#   2. CEE large-caps (CZ/HU/EE/LV/LT) - small cap already exists
#
# Sequential, single worker pair, 30s cool-off between scans (rate-limit safe).

set -u
VENV=/tmp/venv/bin/python
SCRIPT=yartseva_db.py

run_scan() {
    local country="$1"
    local out="$2"
    local min_b="$3"
    local max_b="$4"
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

# Poland - full nano-to-small + largecap
run_scan "Poland"      "pl_yartseva.csv"          "Nano Cap" "Small Cap"
run_scan "Poland"      "pl_largecap_yartseva.csv" "Mid Cap"  "Mega Cap"

# Iceland - full nano-to-small + largecap
run_scan "Iceland"     "is_yartseva.csv"          "Nano Cap" "Small Cap"
run_scan "Iceland"     "is_largecap_yartseva.csv" "Mid Cap"  "Mega Cap"

# CEE large-cap fills (small/micro/nano already scanned previously)
run_scan "Czech Republic" "cz_largecap_yartseva.csv" "Mid Cap" "Mega Cap"
run_scan "Hungary"        "hu_largecap_yartseva.csv" "Mid Cap" "Mega Cap"
run_scan "Estonia"        "ee_largecap_yartseva.csv" "Mid Cap" "Mega Cap"
run_scan "Latvia"         "lv_largecap_yartseva.csv" "Mid Cap" "Mega Cap"
run_scan "Lithuania"      "lt_largecap_yartseva.csv" "Mid Cap" "Mega Cap"

echo "=== $(date +%H:%M:%S)  EU EXPANSION DONE ==="
