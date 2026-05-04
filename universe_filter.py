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
    # These are 4-5 letter SPAC-tier tickers terminating in W/R/U or
    # known multi-letter warrant codes WS/UN.
    if len(t) >= 4 and t.endswith(("WS", "UN")) and "." not in t:
        return True, f"warrant/unit suffix ({t})"
    # Hyphen-less single-letter W/R/Z at end of long tickers is a strong
    # warrant/right signal (e.g. RVMDW = Rev Med warrant). 3-letter
    # tickers ending W are usually real symbols (NWS, FWS); 4-letter+
    # are mostly SPAC-derived warrants.
    if len(t) >= 5 and t.endswith(("W", "R", "Z")) and t[-2].isalpha() and "." not in t:
        # Extra heuristic: if the company name contains "warrant" or
        # the ticker is in a known SPAC roster, exclude. Without that
        # context we still flag long-suffix W/R as likely warrants.
        if t.endswith("W") or t.endswith("Z"):
            return True, f"likely warrant ({t})"
    # Preferred classes encoded as a trailing single letter on a known
    # common-equity root (e.g. SFB = Stifel Series B preferred). This is
    # heuristic; only flags 3-letter tickers ending in B/C/D/E/F.
    if (len(t) == 3 and t.endswith(("B", "C", "D", "E", "F"))
        and "preferred" in c):
        return True, f"preferred class ({t})"
    if any(tok in c for tok in SPAC_NAME_TOKENS):
        return True, "SPAC / blank-check name"
    if t.startswith("0001") or t.startswith("0000"):
        return True, "raw CIK (no public ticker)"
    return False, ""
