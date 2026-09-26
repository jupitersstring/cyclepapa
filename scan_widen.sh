#!/usr/bin/env bash
# Widen-uncategorized supplementary sweep. Re-scans countries where
# financedatabase has many tickers without a market_cap bucket assigned
# (UK has 796 such tickers - 5x the original universe).

set -u
VENV=/tmp/venv/bin/python
SCRIPT=yartseva_db.py
# (country, output suffix) pairs
COUNTRIES=(
    "United Kingdom" "Denmark"  "Norway"  "France"  "Germany"  "Italy"   "Sweden"
)
SUFFIX=(
    uk               dk        no       fr        de         italian   se
)

for i in "${!COUNTRIES[@]}"; do
    country="${COUNTRIES[$i]}"
    suffix="${SUFFIX[$i]}"
    out="${suffix}_yartseva.csv"
    log="/tmp/${suffix}_wide_scan.log"
    echo "=== $(date +%H:%M:%S)  widened scan $country -> $out  ==="
    "$VENV" "$SCRIPT" \
        --country "$country" --max 0 \
        --min-bucket "Nano Cap" --max-bucket "Small Cap" \
        --include-uncategorized \
        --workers 2 --out "$out" \
        --top 10 --projection-n 4 \
        > "$log" 2>&1
    rc=$?
    rows=$(wc -l < "$out" 2>/dev/null || echo 0)
    echo "$(date +%H:%M:%S)  $country  exit=$rc  rows=$rows"
    rm -f "${out}.partial"
    sleep 15
done
echo "=== $(date +%H:%M:%S)  WIDENED SCANS DONE ==="
