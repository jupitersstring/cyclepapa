#!/usr/bin/env bash
# Final widen sweep - the smaller European markets where uncategorized
# (real but unclassified by financedatabase) tickers were being missed.
# Pollution guard inside get_universe auto-rejects Austria.

set -u
VENV=/tmp/venv/bin/python
SCRIPT=yartseva_db.py
COUNTRIES=(
    Ireland     Belgium  Netherlands Spain  Switzerland Finland  Greece
    "Czech Republic" Hungary
)
SUFFIX=(
    ie          be       nl          es     ch          fi       gr
    cz                hu
)

for i in "${!COUNTRIES[@]}"; do
    country="${COUNTRIES[$i]}"
    suffix="${SUFFIX[$i]}"
    out="${suffix}_yartseva.csv"
    log="/tmp/${suffix}_wide2_scan.log"
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
echo "=== $(date +%H:%M:%S)  FINAL WIDEN SCANS DONE ==="
