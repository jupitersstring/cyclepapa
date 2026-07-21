#!/usr/bin/env python3
"""
entity_resolver.py — the ONE canonical entity-normalization layer.

Entity resolution was re-implemented, incompatibly, in at least six places
(corroborate.stem_name/stem_ticker, emergence_master._norm/_ticker_stems,
postreorg_score._norm, postreorg_verify._name_stem, reconcile._stem,
inbox_promote.stem_name/stem_ticker). Each used a different corporate-suffix
list and punctuation policy, so the SAME issuer keyed differently in each
module and cross-source matches silently failed — e.g. "Azul S.A." vs
"AZUL SA", or a name carrying a "(formerly …)" suffix.

This module is the single source of truth. Every other module now delegates
to `normalize_name()` (they keep their own thin wrapper only to adapt the
return case they historically used, so call sites are untouched).

Design (superset of all prior variants):
  - drop parenthetical suffixes: "(Spirit Airlines)", "(formerly Endo Intl)"
  - fold punctuation so "S.A." == "SA", "AT&T" == "ATT"
  - tokenize, drop corporate-form + filler stopwords, join
  - ticker handling exposes BOTH a single primary stem and the full set of
    stems (with a trailing bankruptcy 'Q' stripped: FLYYQ -> FLYY)
"""

from __future__ import annotations

import re

# Corporate-form + filler stopwords (union of every prior module's set).
STOPWORDS = {
    "inc", "corp", "corporation", "ltd", "limited", "plc", "llc", "llp",
    "lp", "lllp", "holdings", "holding", "group", "co", "company", "the",
    "sa", "sas", "nv", "ag", "se", "spa", "as", "asa", "oyj", "ab", "kg",
    "kk", "pty", "pte", "of", "and", "&",
}


def normalize_name(n) -> str:
    """Canonical issuer key (lowercase). Drop parentheticals, fold
    punctuation (S.A.->sa), tokenize, drop corporate-form stopwords, join.
    Deterministic and consistent across every consumer."""
    if isinstance(n, (list, tuple)):
        n = " ".join(map(str, n))
    s = str(n or "").lower()
    s = re.sub(r"\([^)]*\)", " ", s)         # strip parentheticals
    s = s.replace(".", "").replace("&", "and ")   # s.a.->sa ; AT&T->at and t
    toks = [t for t in re.split(r"[^a-z0-9]+", s) if t and t not in STOPWORDS]
    return "".join(toks)


def ticker_stem(t) -> str:
    """Single primary ticker stem (UPPERCASE, exchange prefix dropped, no
    Q-strip) — matches the historical corroborate/inbox_promote behavior."""
    if not t:
        return ""
    return re.sub(r"[^A-Za-z0-9]", "", str(t).split(":")[-1]).upper()


def ticker_stems(t) -> set[str]:
    """All ticker-like stems from a (possibly messy) ticker field, each also
    yielded with a trailing bankruptcy 'Q' stripped (FLYYQ -> FLYY,
    AZULQ -> AZUL). Used for tolerant cross-source ticker matching."""
    out: set[str] = set()
    for m in re.findall(r"[A-Za-z]{1,6}\d?", (t or "").split(":")[-1]):
        u = m.upper()
        out.add(u)
        if len(u) >= 4 and u.endswith("Q"):
            out.add(u[:-1])
    return {s for s in out if len(s) >= 2}


def name_match(a: str, b: str, min_prefix: int = 6) -> bool:
    """Two normalized names match if equal, or one is a prefix of the other
    (handles a name carrying an extra '(Spirit Airlines)'-style suffix)."""
    if not a or not b:
        return False
    if a == b:
        return True
    lo, hi = sorted((a, b), key=len)
    return len(lo) >= min_prefix and hi.startswith(lo)


def resolve_keys(rec: dict) -> set[str]:
    """ALL candidate lookup keys for an inbox record, so the same issuer
    collapses across sources regardless of which identifier a given source
    carries: CIK, every ticker stem, CUSIP, ISIN, and the name stem."""
    keys: set[str] = set()
    cik = rec.get("cik")
    if cik:
        try:
            keys.add(f"CIK:{int(cik)}")
        except (ValueError, TypeError):
            pass
    for st in ticker_stems(rec.get("ticker")):
        keys.add(f"T:{st}")
    for fld in ("cusip", "isin"):
        v = rec.get(fld)
        if v:
            keys.add(f"{fld.upper()}:{str(v).upper()}")
    nm = normalize_name(rec.get("name"))
    if nm:
        keys.add(f"NAME:{nm}")
    return keys


def primary_key(rec: dict) -> str:
    """The single best canonical key for an entity: CIK if present, else the
    first ticker stem, else the name stem. Mirrors emergence_master._key."""
    cik = rec.get("cik")
    if cik:
        try:
            return f"CIK:{int(cik)}"
        except (ValueError, TypeError):
            pass
    sts = sorted(ticker_stems(rec.get("ticker")))
    if sts:
        return f"T:{sts[0]}"
    nm = normalize_name(rec.get("name"))
    return f"NAME:{nm}" if nm else ""
