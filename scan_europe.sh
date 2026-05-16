#!/usr/bin/env bash
# Sequential Europe scan. Runs one country at a time, single-worker, to
# avoid yfinance rate-limit traps. Italy refresh included so all rows
# benefit from the latest Graham/cash-EV guard logic.

set -u
VENV=/tmp/venv/bin/python
SCRIPT=yartseva_db.py
SIZE_ORDER=(
    Italy Portugal Austria Netherlands Belgium Denmark Spain Greece Finland Switzerland Norway Sweden
)
SUFFIX=(
    italian pt        at      nl          be      dk      es    gr     fi      ch          no     se
)

for i in "${!SIZE_ORDER[@]}"; do
    country="${SIZE_ORDER[$i]}"
    suffix="${SUFFIX[$i]}"
    out="${suffix}_yartseva.csv"
    log="/tmp/${suffix}_scan.log"
    echo "=== $(date +%H:%M:%S)  scanning $country -> $out  ==="
    "$VENV" "$SCRIPT" \
        --country "$country" --max 0 \
        --min-bucket "Nano Cap" --max-bucket "Mid Cap" \
        --workers 2 --out "$out" \
        --top 10 --projection-n 4 \
        > "$log" 2>&1
    rc=$?
    rows=$(wc -l < "$out" 2>/dev/null || echo 0)
    echo "$(date +%H:%M:%S)  $country  exit=$rc  rows=$rows"
    rm -f "${out}.partial"

    # Short cool-off between countries so rate-limit headroom rebuilds.
    sleep 15
done
echo "=== $(date +%H:%M:%S)  ALL EUROPEAN SCANS DONE ==="
