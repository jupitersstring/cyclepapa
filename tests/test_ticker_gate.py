"""Regression tests for the centralized ticker-validity gate.

Locks in the fix for the form4_buys.json garbage leak (NONE / N/A
parse artifacts reaching the consensus universe). If this gate ever
regresses, these tests fail loudly.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from full_universe_consensus import is_valid_ticker


def assert_eq(actual, expected, label=""):
    if actual != expected:
        raise AssertionError(
            f"FAIL {label}: expected {expected!r}, got {actual!r}")
    print(f"  PASS  {label}")


def test_rejects_parse_artifacts():
    for junk in ("NONE", "N/A", "NA", "NULL", "NAN", "TBD", "UNKNOWN", ""):
        assert_eq(is_valid_ticker(junk), False,
                  f"test_rejects_{junk or 'empty'}")


def test_rejects_cik_placeholders():
    assert_eq(is_valid_ticker("CIK0001234567"), False,
              "test_rejects_cik")


def test_rejects_non_string():
    assert_eq(is_valid_ticker(None), False, "test_rejects_none_type")
    assert_eq(is_valid_ticker(12345), False, "test_rejects_int_type")


def test_accepts_real_us_tickers():
    for tk in ("AAPL", "FOUR", "BF-B", "BRK.A", "HFFG", "GO", "A"):
        assert_eq(is_valid_ticker(tk), True, f"test_accepts_{tk}")


def test_accepts_wellformed_foreign_symbol():
    # AXIA3 is a well-formed B3 symbol; gate accepts the format even
    # though it is non-US. The blocklist only kills genuine junk.
    assert_eq(is_valid_ticker("AXIA3"), True, "test_accepts_axia3_format")


def test_case_insensitive():
    assert_eq(is_valid_ticker("aapl"), True, "test_lowercase_ok")
    assert_eq(is_valid_ticker("none"), False, "test_lowercase_junk_killed")


def main():
    print("=== ticker validity gate ===")
    n = 0
    for fn in (test_rejects_parse_artifacts, test_rejects_cik_placeholders,
               test_rejects_non_string, test_accepts_real_us_tickers,
               test_accepts_wellformed_foreign_symbol, test_case_insensitive):
        fn()
        n += 1
    print(f"\n{n} test groups passed")


if __name__ == "__main__":
    main()
