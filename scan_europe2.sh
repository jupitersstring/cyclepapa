#!/usr/bin/env bash
# Additional Europe sweep - Ireland, Iceland, CEE and Baltics.

set -u
VENV=/tmp/venv/bin/python
SCRIPT=yartseva_db.py
COUNTRIES=(
    Ireland Iceland "Czech Republic" Hungary Estonia Latvia Lithuania
)
SUFFIX=(
    ie       is      cz                hu      ee      lv      lt
)

for i in "${!COUNTRIES[@]}"; do
    country="${COUNTRIES[$i]}"
    suffix="${SUFFIX[$i]}"
    out="${suffix}_yartseva.csv"
    log="/tmp/${suffix}_scan.log"
    echo "=== $(date +%H:%M:%S)  scanning $country -> $out  ==="
    "$VENV" "$SCRIPT" \
        --country "$country" --max 0 \
        --min-bucket "Nano Cap" --max-bucket "Small Cap" \
        --workers 2 --out "$out" \
        --top 10 --projection-n 4 \
        > "$log" 2>&1
    rc=$?
    rows=$(wc -l < "$out" 2>/dev/null || echo 0)
    echo "$(date +%H:%M:%S)  $country  exit=$rc  rows=$rows"
    rm -f "${out}.partial"
    sleep 15
done
echo "=== $(date +%H:%M:%S)  ADDITIONAL EUROPE SCANS DONE ==="
