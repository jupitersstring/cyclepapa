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
    # Hyphen-less warrant/right/unit suffixes (RVMDW, SVMHW, KVACR, etc.).
    if len(t) >= 4 and t.endswith(("WS", "UN")) and "." not in t:
        return True, f"warrant/unit suffix ({t})"
    if len(t) >= 5 and t.endswith(("W", "R", "Z")) and t[-2].isalpha() and "." not in t:
        if t.endswith("W") or t.endswith("Z"):
            return True, f"likely warrant ({t})"
    # Known preferred 3-letter aliases. SFB/SFE etc. without "preferred" in
    # company name -- maintain a small explicit blocklist so legitimate
    # 3-letter common-equity tickers (NWS, FOX, etc.) aren't caught.
    PREFERRED_ALIASES = {
        "SFB",   # Stifel Financial Series B preferred
        "SFE",   # Stifel Financial Series E preferred
        "BANC.PRE",  # Banc of California pref E
        "BACPRL", "BACPRM", "BACPRN",  # Bank of America pref series
        "WFCPRC", "WFCPRD", "WFCPRR",  # Wells Fargo pref series
    }
    if t in PREFERRED_ALIASES:
        return True, f"known preferred alias ({t})"
    if (len(t) == 3 and t.endswith(("B", "C", "D", "E", "F"))
        and "preferred" in c):
        return True, f"preferred class ({t})"
    if any(tok in c for tok in SPAC_NAME_TOKENS):
        return True, "SPAC / blank-check name"
    if t.startswith("0001") or t.startswith("0000"):
        return True, "raw CIK (no public ticker)"
    # exchange-listed debt / preferreds ("7.875% Notes due 2028", "JR SUB NT",
    # "4.50% P"): their price is a bond's, so P/B / mcap screens are meaningless
    if c and _DEBT_NAME.search(c):
        return True, "listed note / preferred (by name)"
    return False, ""


import re as _re
_DEBT_NAME = _re.compile(
    r"\bnotes?\b(?!.*\bholdings?\b)|\bdebentures?\b|\bjr\.? sub|\bsub(?:ordinated)? n(?:o)?tes?"
    r"|\bsenior n(?:o)?tes?|\bnt\s*\d|\d(?:\.\d+)?\s?%\s*(?:p\b|pfd|pref|series|cum|fixed|notes?|sr|jr|sub|\d)"
    r"|\d(?:\.\d+)?\s?%\s*$|\bpfd\b|\bpreferred (?:stock|shares|securities)|\bdepositary shares? (?:each|representing)"
    r"|\bbaby bond|\b\d{1,2}-[a-z]{3}-20\d\d\b|\s-\s\d+(?:\.\d+)?\s*$", _re.I)
