#!/usr/bin/env bash
# Global expansion sweep: 17 non-US/EU markets covering Asia-Pacific,
# Americas, MEA. Sequential, single-worker-pair, with cool-offs.
# Size-ordered ascending (smallest first) so quick wins land early.

set -u
VENV=/tmp/venv/bin/python
SCRIPT=yartseva_db.py
COUNTRIES=(
    "South Africa"  "Israel"  "New Zealand"  "Mexico"     "Turkey"
    "Singapore"     "Brazil"  "Indonesia"    "Hong Kong"  "Thailand"
    "Taiwan"        "South Korea"  "Australia"  "Canada"  "Japan"  "India"
)
SUFFIX=(
    za             il        nz             mx           tr
    sg             br        idn            hk           th
    tw             kr             au           ca         jp       in
)

for i in "${!COUNTRIES[@]}"; do
    country="${COUNTRIES[$i]}"
    suffix="${SUFFIX[$i]}"
    out="${suffix}_yartseva.csv"
    log="/tmp/${suffix}_scan.log"
    echo "=== $(date +%H:%M:%S)  scanning $country -> $out  ==="
    "$VENV" "$SCRIPT" \
        --country "$country" --max 0 \
        --min-bucket "Nano Cap" --max-bucket "Mega Cap" \
        --include-uncategorized \
        --workers 2 --out "$out" \
        --top 10 --projection-n 4 \
        > "$log" 2>&1
    rc=$?
    rows=$(wc -l < "$out" 2>/dev/null || echo 0)
    echo "$(date +%H:%M:%S)  $country  exit=$rc  rows=$rows"
    rm -f "${out}.partial"
    sleep 30
done
echo "=== $(date +%H:%M:%S)  GLOBAL EXPANSION DONE ==="
