#!/usr/bin/env bash
# Full rebuild pipeline after edgar_universe_extract.py completes.
#
#   1. Map EDGAR facts -> yartseva-schema us_edgar_yartseva.csv
#   2. Compute multi-year ROIC/ROIIC/Lindy + M5 engine score
#   3. Recompute ROIC/ROIIC ONE MORE TIME so cheap_per_roiic_lindy
#      picks up the now-present ev_ebitda from step 1
#   4. Re-tag archetypes (now with EDGAR fields available)
#   5. Rebuild asymmetry_global, Harvard workbook, NMS book, candidates
#
# Run once after `python edgar_universe_extract.py` finishes.

set -eu

echo "[1/5] mapping EDGAR -> yartseva schema..."
python3 edgar_to_yartseva.py

echo "[2/5] computing multi-year ROIC/ROIIC/Lindy (first pass)..."
python3 edgar_roic_roiic.py

echo "[3/5] recomputing ROIC/ROIIC with ev_ebitda available..."
python3 edgar_roic_roiic.py

echo "[4/5] re-tagging archetypes (now with EDGAR fields)..."
python3 archetype_tags.py

echo "[5a/5] rebuilding asymmetry_global..."
bash build_asymmetry_global.sh

echo "[5b/5] rebuilding workbooks..."
python3 build_harvard_workbook.py --top-n 50
python3 build_nms_book.py --top-n 100 --per-region-n 25
python3 build_nms_candidates_book.py

echo
echo "DONE. Artifacts refreshed."
