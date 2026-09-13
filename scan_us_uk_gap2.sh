#!/usr/bin/env bash
# Second-pass US+UK gap fill - this time properly scoped to PRIMARY
# listings only (no .F/.SG/.DU cross-listing pollution).
#
# US: 6,672 primary tickers (NMS/NYSE/AMEX/PNK format, no dot suffix)
# UK: 211 .L tickers (most are AIM/delisted but worth re-checking)

set -u
PY=/usr/local/bin/python3
SCRIPT=yartseva_db.py

run_gap2() {
    local country="$1"
    local code="$2"
    local tickers_file="$3"
    local out="${code}_gap2_yartseva.csv"
    local log="/tmp/${code}_gap2_scan.log"
    local n=$(wc -l < "$tickers_file")
    echo "=== $(date +%H:%M:%S)  $country ($n primary tickers) -> $out  ==="
    "$PY" "$SCRIPT" \
        --country "$country" \
        --tickers-file "$tickers_file" \
        --workers 3 --out "$out" \
        --top 5 --projection-n 4 \
        > "$log" 2>&1
    local rc=$?
    local rows=$(wc -l < "$out" 2>/dev/null || echo 0)
    echo "$(date +%H:%M:%S)  $country  exit=$rc  rows=$rows"
    rm -f "${out}.partial"
    sleep 30
}

# UK first (small, 211 names ~ 2 min)
run_gap2 "United Kingdom" "uk" "/tmp/uk_primary_missing.txt"
# US (big, 6,672 names ~ 30-60 min at 3 workers)
run_gap2 "United States" "us" "/tmp/us_primary_missing.txt"

echo "=== $(date +%H:%M:%S)  US+UK PRIMARY GAP FILL DONE ==="
