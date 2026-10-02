"""Canonical manager identity for fund-name VARIANTS.

The roster and research sheets refer to the same manager under several string
variants — "CAS Investment Partners", "CAS Investment Partners (Cliff ",
"CAS Investment Partners Sosin" — and fund_positions carries all of them.
Counting DISTINCT fund strings therefore multi-counts one manager (NVDA's
top-pick count was 52 raw strings but only 37 real managers). 13F holdings were
deduped at the CIK level; this collapses the curated-position side the same way.

canon(fund) -> canonical manager key: strips the parenthetical PM name (incl.
an unclosed trailing parenthetical), anything after a 2+ space gap (style/PM
suffixes), trailing punctuation, a trailing corporate suffix token, a word cut
by the roster's 31-character limit, and trailing form words (Capital,
Management, Partners...). 780 name strings -> 625 managers (September 2026).
"""
import re

# trailing words that name a firm's form, not the firm: "Pershing Square
# Capital Management" and "Pershing Square" are one manager
_GENERIC = {"MANAGEMENT", "ADVISORS", "ADVISERS", "PARTNERS", "CAPITAL", "GROUP", "INVESTMENTS",
            "INVESTMENT", "ASSET", "FUND", "FUNDS", "HOLDINGS", "LLC", "LP", "LTD", "INC", "CO",
            "COMPANY", "TRUST", "INVESTORS"}

def canon(fund):
    raw = fund or ""
    c = re.sub(r"\(.*?(\)|$)", "", raw)          # parenthetical, incl. unclosed at end
    c = re.split(r"\s{2,}|\s/\s", c)[0]         # drop "  Manager" / " / BLR Partners"-style suffixes
    c = re.sub(r"\s+", " ", c).strip().rstrip(",&").strip().upper()
    c = re.sub(r"\b(LLC|LP|L\.P\.|LLP|LTD|INC|CORP)\.?$", "", c).strip()
    c = c or raw.upper()
    w = c.split()
    # roster names are cut at 31 characters, mid-word: "Pershing Square Capital
    # Managem" must meet "Pershing Square Capital Management" (the research
    # notes' spelling), or one manager counts twice in S3 / S4
    if len(raw) == 31 and len(w) > 1 and "(" not in raw and not re.search(r"\s$", raw):
        w = w[:-1]
    # peel form words, but never below a 4-character key ("D1 Capital
    # Partners" and "D1 Capital" both stop at "D1 CAPITAL")
    while len(w) > 1 and w[-1] in _GENERIC and len(" ".join(w[:-1])) >= 4:
        w = w[:-1]
    return " ".join(w)
