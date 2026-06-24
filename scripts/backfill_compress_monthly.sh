#!/bin/bash
# Backfill MONTHLY compression for every market that already has a weekly
# compression file but no monthly one. Idempotent — skips completed markets.
# Run this once Yahoo's rate-limit block has lifted.
set -e
cd "$(dirname "$0")/.."

for uni in data/universes/uni_*.csv data/universes/large/uni_*_lg.csv data/universes/expanded/uni_*_x.csv; do
    [ -f "$uni" ] || continue
    bn=$(basename "$uni" .csv)
    mkt=${bn#uni_}                      # strip uni_ prefix
    out="data/compression/compress_monthly_${mkt}.csv"
    [ -f "$out" ] && [ "$(stat -c%s "$out" 2>/dev/null)" -gt 200 ] && continue
    n=$(($(wc -l < "$uni") - 1))
    [ "$n" -lt 10 ] && continue
    echo "[compress-monthly] $mkt ($n tickers)"
    cp "$uni" /tmp/screen_universe.csv
    python3 screeners/compression_monthly.py > "/tmp/log_compm_${mkt}.txt" 2>&1 || true
    cp /tmp/tech_compression.csv "$out" 2>/dev/null || true
    sleep 20
done
echo "[compress-monthly] DONE"
