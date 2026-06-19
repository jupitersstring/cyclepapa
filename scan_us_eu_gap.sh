#!/usr/bin/env bash
# US + EU gap-fill scan. 18,857 tickers across 10 countries via the
# --tickers-file mode I added to yartseva_db.py. Sequential, smallest
# countries first so quick wins land early; US is the slow elephant.
#
# Estimated runtime: 2.5-3 hours at 2 workers (~2 tickers/sec with yfinance
# rate limit + 404 misses).

set -u
PY=/usr/local/bin/python3
SCRIPT=yartseva_db.py

run_gap() {
    local country="$1"
    local code="$2"
    local tickers_file="/tmp/${code}_missing_tickers.txt"
    local out="${code}_gap_yartseva.csv"
    local log="/tmp/${code}_gap_scan.log"
    if [ ! -f "$tickers_file" ]; then
        echo "$(date +%H:%M:%S)  $country  skipping - no tickers file"
        return
    fi
    local n=$(wc -l < "$tickers_file")
    echo "=== $(date +%H:%M:%S)  $country ($n tickers) -> $out  ==="
    "$PY" "$SCRIPT" \
        --country "$country" \
        --tickers-file "$tickers_file" \
        --workers 2 --out "$out" \
        --top 5 --projection-n 4 \
        > "$log" 2>&1
    local rc=$?
    local rows=$(wc -l < "$out" 2>/dev/null || echo 0)
    echo "$(date +%H:%M:%S)  $country  exit=$rc  rows=$rows"
    rm -f "${out}.partial"
    sleep 30
}

# Smallest first
run_gap "Austria"        "at"
run_gap "Belgium"        "be"
run_gap "Ireland"        "ie"
run_gap "Netherlands"    "nl"
run_gap "Switzerland"    "ch"
run_gap "Italy"          "it"
run_gap "France"         "fr"
run_gap "Germany"        "de"
run_gap "United Kingdom" "uk"
run_gap "United States"  "us"   # big one last

echo "=== $(date +%H:%M:%S)  US+EU GAP FILL DONE ==="
