"""Canonical manager identity for fund-name VARIANTS.

The roster and research sheets refer to the same manager under several string
variants — "CAS Investment Partners", "CAS Investment Partners (Cliff ",
"CAS Investment Partners Sosin" — and fund_positions carries all of them.
Counting DISTINCT fund strings therefore multi-counts one manager (NVDA's
top-pick count was 52 raw strings but only 37 real managers). 13F holdings were
deduped at the CIK level; this collapses the curated-position side the same way.

canon(fund) -> canonical manager key: strips the parenthetical PM name (incl.
an unclosed trailing parenthetical), anything after a 2+ space gap (style/PM
suffixes), trailing punctuation, and a trailing corporate suffix token.
552 distinct fund strings -> 445 canonical managers (equals the roster count).
"""
import re

def canon(fund):
    c = re.sub(r"\(.*?(\)|$)", "", fund or "")   # parenthetical, incl. unclosed at end
    c = re.split(r"\s{2,}|\s/\s", c)[0]         # drop "  Manager" / " / BLR Partners"-style suffixes
    c = re.sub(r"\s+", " ", c).strip().rstrip(",&").strip().upper()
    c = re.sub(r"\b(LLC|LP|L\.P\.|LLP|LTD|INC|CORP)\.?$", "", c).strip()
    return c or (fund or "").upper()
