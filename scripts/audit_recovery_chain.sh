#!/bin/bash
# Post-audit data-recovery chain (SEC-only, no Yahoo needed):
#   1. wait for derive_us_pb_pe to finish
#   2. run backlog_screen resume (retries 6-K/error-affected no-data rows)
#   3. re-run backfill_meta (merges recovered EV/net_debt/backlog) + rebuild workbooks
#   4. commit + push
set -e
cd "$(dirname "$0")/.."
export EDGAR_IDENTITY="cyclepapa research cm2whv9sg2@privaterelay.appleid.com"
export REQUESTS_CA_BUNDLE=/root/.ccr/ca-bundle.crt SSL_CERT_FILE=/root/.ccr/ca-bundle.crt

echo "[chain] waiting for derive_us_pb_pe…"
while pgrep -f derive_us_pb_pe.py >/dev/null 2>&1; do sleep 15; done
echo "[chain] derive done: $(($(wc -l < data/research/derived_us_pb_pe.csv) - 1)) rows"

echo "[chain] backlog resume (retry no-data rows for 6-K + error recovery)…"
python3 scripts/backlog_screen.py --universe data/universes/sec_all.csv \
    --out data/research/backlog_us.csv --workers 6 --rate 7 --checkpoint 200 --resume \
    > /tmp/log_backlog.txt 2>&1 || true
echo "[chain] backlog rows: $(($(wc -l < data/research/backlog_us.csv) - 1))"

echo "[chain] rebuild synthesis + workbooks…"
python3 scripts/backfill_meta.py            > /tmp/log_backfill.txt 2>&1 || true
python3 scripts/build_workbook_harvard.py   > /tmp/log_wb_h.txt 2>&1 || true
python3 scripts/build_archetypes_harvard.py > /tmp/log_arch_h.txt 2>&1 || true
grep -E "cap_tier still|ev_total now|computed backlog_to_ev|gaps after" /tmp/log_backfill.txt || true

git add data/ scripts/ 2>/dev/null || true
git commit -q -m "audit recovery: rebuild with IFRS/40-F/6-K filers + recovered EV/net_debt" 2>&1 | tail -1 || true
delay=2
for a in 1 2 3 4; do
    git push -u origin "$(git rev-parse --abbrev-ref HEAD)" >/dev/null 2>&1 && break
    sleep $delay; delay=$((delay*2))
done
echo "[chain] DONE"
