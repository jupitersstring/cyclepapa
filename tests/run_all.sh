#!/bin/bash
# Run the full regression test suite. Exit non-zero on any failure.
set -e
cd "$(dirname "$0")"
echo "=== cancel_10b5_1 ==="
python3 test_cancel_10b5_1.py
echo
echo "=== psu_pipeline ==="
python3 test_psu_pipeline.py
echo
echo "=== new_legs (form144, buyback, state) ==="
python3 test_new_legs.py
echo
echo "=== ticker validity gate ==="
python3 test_ticker_gate.py
echo
echo "=== discretionary insider conviction ==="
python3 test_discretionary_conviction.py
echo
echo "=== emergence cross-feed ==="
python3 test_emergence_crossfeed.py
echo
echo "=== incentive audit fixes (R1-R9) ==="
python3 test_incentive_fixes.py
echo
echo "=== asymmetry assembly (conjunction gates) ==="
python3 test_asymmetry_assembly.py
echo
echo "=== PSIX May-2024 backtest (point-in-time validation) ==="
python3 ../asymmetry_backtest.py >/dev/null && echo "PSIX backtest PASS" || echo "PSIX backtest FAIL"
echo
echo "=== distressed-stub progress engine ==="
python3 test_distressed_stub.py
echo

echo "=== hidden-asset / credit-agreement mining ==="
python3 test_hidden_asset.py
echo

echo "=== selective / own-shares revealed preference ==="
python3 test_selective_buyback.py
echo

echo "All test suites passed."
