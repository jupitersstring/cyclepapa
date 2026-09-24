#!/bin/bash
# Quarterly 13F roll + rebuild, in dependency order. Any failing step stops the
# chain, so a half-built DB is never rendered or snapshotted.
#
#   bash pipeline/rebuild_13f.sh           roll every fund to its newest 13F-HR, then rebuild
#   ROLL=0 bash pipeline/rebuild_13f.sh    rebuild only (no EDGAR roll)
#
# Run it once the 13F deadline (45 days after quarter end) has passed;
# validate.py fails if 10%+ of live funds still hold the previous quarter.
set -eo pipefail
cd "$(dirname "$0")/.."
step() {
  echo "=== $1"; shift
  "$@" 2>&1 | { grep -av "rate-limited" || true; } | tail -"${TAILN:-8}"
}
if [ "${ROLL:-1}" = 1 ]; then
  step roll python3 pipeline/ingest_13f.py --refresh          # newest book; old book -> prior
fi
step prior python3 pipeline/ingest_13f_prior.py               # exact preceding quarter, if missing
step nport python3 pipeline/ingest_nport.py                   # full fund books incl. non-US (N-PORT)
step splits python3 pipeline/ingest_splits.py                 # split factors for the 13F and N-PORT diffs
step build_cusip_map python3 pipeline/build_cusip_map.py
step map_cusip_fmp python3 pipeline/map_cusip_fmp.py          # FMP-proven CUSIPs, new listings
step back_apply python3 pipeline/build_cusip_map.py           # push the new mappings onto every line
step enrich_fmp python3 pipeline/enrich_fmp.py
step price_stats python3 pipeline/build_price_stats.py
step earnings python3 pipeline/ingest_fmp_earnings.py
step cluster python3 pipeline/cluster_detector.py
step unified_score python3 pipeline/unified_score.py
step conviction python3 pipeline/conviction.py
step styles_view python3 pipeline/styles_view.py
step broker_swap_radar python3 pipeline/broker_swap_radar.py
TAILN=45 step validate python3 pipeline/validate.py
step render_universe python3 pipeline/render_universe_sheet.py
step render_style python3 pipeline/render_style_workbook.py
step render_people python3 pipeline/render_people_monitor.py
step render_broadsheet python3 pipeline/render_broadsheet.py
step snapshot python3 pipeline/snapshot.py dump
echo "=== REBUILD OK"
