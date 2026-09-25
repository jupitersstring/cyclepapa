"""Regression tests for the security master (store.py / store_build.py).

Each case is a defect an audit found, or a rule that broke once:
  * live companies must never be typed bankrupt because an unrelated '...Q' ticker
    exists (BACQ is not Bank of America) or because the issuer's OLD Q line survives
    after emergence (CORZ), or because a baby bond happens to end in Q (RWTQ)
  * notes / preferreds / funds / SPACs are not common equity
  * every identifier style the books use resolves to the same security
  * share lines of one issuer group together by CIK; different issuers don't
Skipped (not failed) when the store has not been built on this machine.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import store  # noqa: E402


def main() -> int:
    if not store.DB.exists():
        print("SKIP: data/cyclepapa.db not built (run store_build.py)")
        return 0
    fails = 0

    def check(label, got, want):
        nonlocal fails
        ok = got == want
        fails += not ok
        print(f"{'ok  ' if ok else 'FAIL'} {label}: {got!r}" + ("" if ok else f" (want {want!r})"))

    for t in ("BAC", "GE", "IBM", "HCA", "DUK", "CORZ", "RWT", "AAPL"):
        check(f"{t} is common", store.sec_type_of(t), "common")
    for t, want in (("CUBB", "note_pref"), ("SWZ", "fund"), ("CCXI", "spac"), ("NOTVQ", "bankrupt")):
        check(f"{t} type", store.sec_type_of(t), want)
    for ident, want in (("EPA:LOCAL", "LOCAL.PA"), ("HKEX:00005.HK", "0005.HK"), ("UREE", "USAR"),
                        ("CIK0000859737", "HOLX"), ("NASDAQ:AAPL", "AAPL")):
        check(f"resolve {ident}", store.resolve(ident), want)
    check("FMS and FMCQF are one issuer", store.issuer_key("FMS") == store.issuer_key("FMCQF"), True)
    check("GOOG and GOOGL are one issuer", store.issuer_key("GOOG") == store.issuer_key("GOOGL"), True)
    check("MSGS and MSGE are different issuers", store.issuer_key("MSGS") != store.issuer_key("MSGE"), True)
    print(f"\n{fails} failure(s)")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
