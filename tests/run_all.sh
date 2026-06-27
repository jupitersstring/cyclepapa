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
echo "All test suites passed."
