#!/usr/bin/env bash
# Full rebuild: archetypes -> master enrich -> audit gate -> all 24 books.
#
# Order matters:
#   1. archetype_tags.py        recompute every archetype + FMP overlays
#   2. enrich_asymmetry_global  refresh the master's derived columns
#                               (archetype_count, confirmation scores, ETA).
#                               The country / NMS / top-N books read these from
#                               the master, so skipping this leaves them stale.
#   3. methodology_audit        gate: must report 0 FAIL
#   4. every book               each build is attempted; any failure -> exit 1
#
# FMP columns are NOT pushed into the master: the books read them fresh from
# archetype_tags.csv (fmp_book_cols.attach_fmp / the archetype loaders).
set -uo pipefail
cd "$(dirname "$0")"

step() { echo; echo "=== $* ==="; }

step "1/4 archetype_tags"
python3 -c "import archetype_tags as a; a.compute()" > /dev/null || { echo "archetype_tags FAILED"; exit 1; }

step "2/4 enrich_asymmetry_global"
python3 enrich_asymmetry_global.py 2>&1 | tail -3 || { echo "enrich FAILED"; exit 1; }

step "3/4 methodology_audit (gate)"
audit_out=$(python3 methodology_audit.py 2>&1)
echo "$audit_out" | grep -E "METHODOLOGY AUDIT|  FAIL|  WARN"
echo "$audit_out" | grep -qE "checks, 0 FAIL" || { echo "AUDIT GATE FAILED — books not rebuilt"; exit 1; }

step "4/4 books"
failed=()
while IFS= read -r cmd; do
  [ -z "$cmd" ] && continue
  echo ">>> $cmd"
  if ! eval "timeout 3600 python3 $cmd" > /tmp/regen_book.log 2>&1; then
    echo "    FAILED (tail follows)"; tail -5 /tmp/regen_book.log; failed+=("$cmd")
  fi
done <<'BOOKS'
build_archetype_book.py
build_forensic_xr_book.py
build_truly_xr_book.py
build_segment_detail_book.py
build_harvard_workbook.py --top-n 50
build_country_workbook.py
build_nms_book.py --top-n 100 --per-region-n 25
build_nms_candidates_book.py
build_nms_candidates_book.py --midcap-plus
build_country_archetype_book.py --n 30
build_country_archetype_inflection_book.py --n 30
build_otc_archetype_book.py --n 30
top_n_by_country.py --n 30 --out-csv top_n_by_country.csv --out-xlsx top_n_by_country.xlsx
top_n_by_country.py --n 30 --sort-by inflection --out-csv top_n_by_country_inflection.csv --out-xlsx top_n_by_country_inflection.xlsx
top_n_by_country.py --n 30 --otc-mode otc --out-csv top_n_otc.csv --out-xlsx top_n_otc.xlsx
top_n_by_country.py --n 30 --high-filter any --out-csv top_n_52w_high.csv --out-xlsx top_n_52w_high.xlsx
build_country_archetype_book.py --otc-mode otc --out country_archetype_book_otc.xlsx
build_country_archetype_book.py --n 30 --high-filter any --out country_archetype_52w_high.xlsx
build_country_archetype_book.py --min-mcap 2e9 --min-names 10 --out country_archetype_midcap_plus.xlsx
build_country_archetype_book.py --max-pe 8 --max-ev 8 --out country_archetype_cheap8.xlsx
build_country_archetype_book.py --max-pb 1.05 --out country_archetype_pb_sub1.xlsx
build_country_archetype_book.py --max-ret-12m 0.0 --out country_archetype_ret12m_neg.xlsx
build_country_archetype_inflection_book.py --otc-mode otc --out country_archetype_inflection_otc.xlsx
build_country_archetype_inflection_book.py --min-mcap 2e9 --min-names 10 --out country_archetype_inflection_midcap_plus.xlsx
BOOKS

echo
if [ ${#failed[@]} -gt 0 ]; then
  echo "BOOKS FAILED (${#failed[@]}):"; printf '  %s\n' "${failed[@]}"; exit 1
fi
echo "ALL_BOOKS_OK"
