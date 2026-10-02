#!/usr/bin/env bash
# Fill nano/micro coverage gaps via uncategorized-pool scans.
# Most financedatabase tickers have no market_cap_bucket assigned -
# many real nano/micro caps live in that uncategorized pool.
#
# Two passes:
#   1. EU coverage gaps - 13 countries with no prior uncategorized scan
#   2. US deep dive - re-scan with --only-uncategorized to pull the
#      10K+ uncategorized US pool (will overwrite small existing us_unc)

set -u
VENV=/tmp/venv/bin/python
SCRIPT=yartseva_db.py

run_unc() {
    local country="$1"
    local out="$2"
    local extra="${3:---include-uncategorized}"
    local log="/tmp/${out%.csv}_scan.log"
    echo "=== $(date +%H:%M:%S)  $country  unc -> $out  ==="
    "$VENV" "$SCRIPT" \
        --country "$country" --max 0 \
        --min-bucket "Nano Cap" --max-bucket "Small Cap" \
        $extra \
        --workers 2 --out "$out" \
        --top 10 --projection-n 4 \
        > "$log" 2>&1
    local rc=$?
    local rows=$(wc -l < "$out" 2>/dev/null || echo 0)
    echo "$(date +%H:%M:%S)  $country  exit=$rc  rows=$rows"
    rm -f "${out}.partial"
    sleep 30
}

# Phase 1: EU gap fills (uncategorized pool with bucketed names included).
# Targets: countries where the uncategorized count > strict bucket count
# AND no prior _unc file exists.
run_unc "Austria"        "at_unc_yartseva.csv"
run_unc "Switzerland"    "ch_unc_yartseva.csv"
run_unc "Sweden"         "se_unc_yartseva.csv"
run_unc "Finland"        "fi_unc_yartseva.csv"
run_unc "Portugal"       "pt_unc_yartseva.csv"
run_unc "Greece"         "gr_unc_yartseva.csv"
run_unc "Ireland"        "ie_unc_yartseva.csv"
run_unc "Poland"         "pl_unc_yartseva.csv"
run_unc "Czech Republic" "cz_unc_yartseva.csv"
run_unc "Hungary"        "hu_unc_yartseva.csv"
run_unc "Estonia"        "ee_unc_yartseva.csv"
run_unc "Latvia"         "lv_unc_yartseva.csv"
run_unc "Lithuania"      "lt_unc_yartseva.csv"

# Phase 2: US deep dive - pull the 10K uncategorized US pool. The existing
# us_unc file has only 165 rows; this re-scan should multiply that
# substantially. Use --only-uncategorized to skip the already-covered
# strict buckets (already in us_nano_micro_small_yartseva).
run_unc "United States"  "us_unc_deep_yartseva.csv" "--only-uncategorized"

echo "=== $(date +%H:%M:%S)  GAP FILL DONE ==="
