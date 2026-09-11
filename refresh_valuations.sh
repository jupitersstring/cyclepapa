#!/usr/bin/env bash
# THE canonical valuation/data refresh chain. Run this — not the steps ad hoc —
# whenever prices, ticker_yf.csv, or any level source has been updated.
#
# ORDER MATTERS and is load-bearing:
#   1. derive_missing_columns.py   gap-fills levels/ratios from EDGAR & peers
#                                  (a FILLER — it may introduce cross-basis
#                                  values, which is fine because...)
#   2. apply_ticker_yf.py          ...runs LAST as the FINAL HARMONIZER:
#                                  Yahoo-authoritative price/mcap/EV, level
#                                  reconciliation, and the derived-ratio
#                                  recompute that makes every row internally
#                                  consistent (see its header for the full
#                                  trust hierarchy). Running derive AFTER
#                                  apply re-introduces inconsistencies — the
#                                  audit gate will catch it, but don't.
#   3. archetype_tags.py           re-tag on consistent data
#   4. enrich_asymmetry_global.py  ETA / melt_demotion / ghost-nulling
#   5. methodology_audit.py        133+ checks incl. the valuation-integrity
#                                  gate (top-100 must be spotless) — HARD FAIL
#   6. scratch_mutation_test.py    the checks themselves are load-bearing
#   7. valuation_crosscheck.py     per-name top-60 report vs source — HARD FAIL
set -euo pipefail
cd "$(dirname "$0")"

echo "[1/7] derive_missing_columns (gap-fill)..."
python3 derive_missing_columns.py 2>&1 | tail -1
echo "[2/7] apply_ticker_yf (harmonize: reconcile + recompute)..."
python3 apply_ticker_yf.py 2>&1 | tail -1
echo "[3/7] archetype_tags..."
python3 archetype_tags.py > /dev/null
echo "[4/7] enrich_asymmetry_global..."
python3 enrich_asymmetry_global.py 2>&1 | grep -E "melt_demotion:|wrote enriched"
echo "[5/7] methodology_audit (gate)..."
python3 methodology_audit.py | grep -E "AUDIT —|FAIL" || true
python3 - <<'PY'
import subprocess, sys
r = subprocess.run(["python3", "methodology_audit.py"], capture_output=True)
sys.exit(r.returncode)
PY
echo "[6/7] mutation test (gate)..."
python3 scratch_mutation_test.py | grep RESULT
echo "[7/8] valuation_crosscheck top-60 (gate)..."
python3 valuation_crosscheck.py --top 60
echo "[8/8] claims_conformance (gate: we implement what we document)..."
python3 claims_conformance.py | tail -1
echo "REFRESH COMPLETE — all gates green."
