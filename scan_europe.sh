#!/usr/bin/env bash
# Sequential Europe scan. Runs each country's yartseva snapshot one at a
# time so yfinance rate-limits don't trip. Starts only after a previous
# France scan process exits.

set -u
VENV=/tmp/venv/bin/python
SCRIPT=yartseva_db.py
SIZE_ORDER=(
    Portugal Austria Netherlands Belgium Denmark Spain Greece Finland Switzerland Norway Sweden
)
SUFFIX=(
    pt        at      nl          be      dk      es    gr     fi      ch          no     se
)

# Wait for previous France process to exit (pid passed in $1 if given)
if [ -n "${1:-}" ]; then
    while kill -0 "$1" 2>/dev/null; do sleep 30; done
fi

for i in "${!SIZE_ORDER[@]}"; do
    country="${SIZE_ORDER[$i]}"
    suffix="${SUFFIX[$i]}"
    out="${suffix}_yartseva.csv"
    log="/tmp/${suffix}_scan.log"
    echo "=== $(date +%H:%M:%S)  scanning $country -> $out  ==="
    "$VENV" "$SCRIPT" \
        --country "$country" --max 0 \
        --min-bucket "Nano Cap" --max-bucket "Mid Cap" \
        --workers 3 --out "$out" \
        --top 10 --projection-n 4 \
        > "$log" 2>&1
    rc=$?
    rows=$(wc -l < "$out" 2>/dev/null || echo 0)
    echo "$(date +%H:%M:%S)  $country  exit=$rc  rows=$rows"
    rm -f "${out}.partial"
done
echo "=== $(date +%H:%M:%S)  ALL EUROPEAN SCANS DONE ==="
