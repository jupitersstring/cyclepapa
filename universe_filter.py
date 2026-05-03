"""Universe filter for ranked output.

Excludes tickers/securities that pollute the ranking but aren't real
common-equity opportunities for the user's framework: SPAC warrants,
SPAC units, blank-check companies, preferred series, sub-$0.50 penny
shells.
"""

from __future__ import annotations

# Suffix patterns that indicate non-common-equity instruments.
SPAC_WARRANT_SUFFIXES = (
    "-WT", "-W", "-UN", "-R", "+", ".U", ".W", ".WS",
)
PREFERRED_SUFFIXES = (
    "-PA", "-PB", "-PC", "-PD", "-PE", "-PF", "-PG", "-PH",
    "-PI", "-PJ", "-PK", "-PL", "-PM", "-PN", "-PO", "-PP",
    "-PQ", "-PR", "-PS", "-PT", "-PU", "-PV", "-PW", "-PX",
    "-PY", "-PZ",
)

SPAC_NAME_TOKENS = (
    "acquisition corp",
    "acquisition inc",
    "acquisitions corp",
    "blank check",
    "spac",
    "acquisition holdings",
    " acquisition ",
)


def is_excluded(ticker: str, company: str | None = None) -> tuple[bool, str]:
    t = (ticker or "").upper().strip()
    c = (company or "").lower().strip()
    if not t:
        return True, "empty ticker"
    if any(t.endswith(s) for s in SPAC_WARRANT_SUFFIXES):
        return True, f"SPAC warrant/unit suffix ({t})"
    if any(t.endswith(s) for s in PREFERRED_SUFFIXES):
        return True, f"preferred series suffix ({t})"
    if any(tok in c for tok in SPAC_NAME_TOKENS):
        return True, "SPAC / blank-check name"
    if t.startswith("0001") or t.startswith("0000"):
        return True, "raw CIK (no public ticker)"
    return False, ""
