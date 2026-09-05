#!/usr/bin/env bash
# Coverage-gap supplement: scan ONLY uncategorized tickers per country
# across the full Nano-Mega bucket range. Output files are
# <suffix>_unc_yartseva.csv. The asymmetry ranker picks them up
# alongside the existing strict CSVs.

set -u
VENV=/tmp/venv/bin/python
SCRIPT=yartseva_db.py
COUNTRIES=(
    "United States"  "United Kingdom" "Germany"  "France"   "Norway"  "Belgium"
    "Netherlands"    "Spain"          "Denmark"  "Italy"
)
SUFFIX=(
    us               uk               de         fr         no        be
    nl               es               dk         it
)

for i in "${!COUNTRIES[@]}"; do
    country="${COUNTRIES[$i]}"
    suffix="${SUFFIX[$i]}"
    out="${suffix}_unc_yartseva.csv"
    log="/tmp/${suffix}_unc_scan.log"
    echo "=== $(date +%H:%M:%S)  uncategorized scan $country -> $out  ==="
    "$VENV" "$SCRIPT" \
        --country "$country" --max 0 \
        --min-bucket "Nano Cap" --max-bucket "Mega Cap" \
        --only-uncategorized \
        --workers 2 --out "$out" \
        --top 10 --projection-n 4 \
        > "$log" 2>&1
    rc=$?
    rows=$(wc -l < "$out" 2>/dev/null || echo 0)
    echo "$(date +%H:%M:%S)  $country  exit=$rc  rows=$rows"
    rm -f "${out}.partial"
    sleep 20
done
echo "=== $(date +%H:%M:%S)  UNCATEGORIZED GAP SCAN DONE ==="
