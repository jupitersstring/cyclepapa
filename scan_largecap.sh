#!/usr/bin/env bash
# Mid + Large + Mega cap sweep across US + Europe.

set -u
VENV=/tmp/venv/bin/python
SCRIPT=yartseva_db.py

# US first (biggest, 2031 tickers).
echo "=== $(date +%H:%M:%S)  scanning United States Mid+Large+Mega -> us_largecap_yartseva.csv  ==="
"$VENV" "$SCRIPT" \
    --country "United States" --max 0 \
    --min-bucket "Mid Cap" --max-bucket "Mega Cap" \
    --workers 3 --out us_largecap_yartseva.csv \
    --top 15 --projection-n 4 \
    > /tmp/us_large_scan.log 2>&1
rc=$?
rows=$(wc -l < us_largecap_yartseva.csv 2>/dev/null || echo 0)
echo "$(date +%H:%M:%S)  United States Mid+  exit=$rc  rows=$rows"
rm -f us_largecap_yartseva.csv.partial

# European countries (smaller universes).
COUNTRIES=(
    "United Kingdom" "Germany" "France" "Italy" "Switzerland" "Netherlands"
    "Spain" "Belgium" "Sweden" "Norway" "Denmark" "Finland" "Austria"
    "Greece" "Portugal" "Ireland"
)
SUFFIX=(
    uk         de        fr       it      ch         nl
    es        be        se      no      dk        fi      at
    gr        pt        ie
)

for i in "${!COUNTRIES[@]}"; do
    country="${COUNTRIES[$i]}"
    suffix="${SUFFIX[$i]}"
    out="${suffix}_largecap_yartseva.csv"
    log="/tmp/${suffix}_large_scan.log"
    echo "=== $(date +%H:%M:%S)  scanning $country Mid+Large+Mega -> $out  ==="
    "$VENV" "$SCRIPT" \
        --country "$country" --max 0 \
        --min-bucket "Mid Cap" --max-bucket "Mega Cap" \
        --workers 2 --out "$out" \
        --top 10 --projection-n 4 \
        > "$log" 2>&1
    rc=$?
    rows=$(wc -l < "$out" 2>/dev/null || echo 0)
    echo "$(date +%H:%M:%S)  $country  exit=$rc  rows=$rows"
    rm -f "${out}.partial"
    sleep 15
done

echo "=== $(date +%H:%M:%S)  LARGECAP SWEEP DONE ==="
