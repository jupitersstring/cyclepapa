#!/usr/bin/env python3
"""
postreorg_verify.py — did the FILER itself emerge, and when?

EDGAR full-text search cannot tell "the Company emerged from Chapter 11"
from "our customer Solutia emerged from Chapter 11". Both match the query,
so the raw post-reorg cohort is polluted with issuers that merely REFERENCE
someone else's bankruptcy (Eastman Chemical → Solutia; APA, RMR, Nexstar all
false-positived this way). Worse, a genuine but ANCIENT emergence (Centrus,
2014) has no live forced-seller overhang, yet the label looks identical.

This module fetches the emergence filing's primary document and reads the
context around each emergence phrase to answer two questions the label
alone can't:

  1. Did the FILER itself emerge?  — first-person context
     ("the Company emerged", "our emergence", "the Company's reorganization")
     vs a third-party possessive ("Solutia's emergence").
  2. WHEN did it emerge?  — the date printed next to the phrase, so the
     forced-seller-overhang recency can be judged rather than assumed.

Results are cached to data/postreorg_verify.json (tracked, durable) keyed
by accession so re-runs and the poller share the verdict without refetching.

Usage (standalone, warms the cache over the current cohort):
    python -m src.postreorg_verify
    python -m src.postreorg_verify --limit 40
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

try:
    import requests
except ImportError:
    print("Install requests", file=sys.stderr); sys.exit(1)

REPO = Path(__file__).resolve().parent.parent
CACHE = REPO / "data" / "postreorg_verify.json"
UA = {"User-Agent": os.environ.get(
    "EDGAR_USER_AGENT", "cyclepapa-screener research@example.com")}

_EMERGE = re.compile(
    r"emerged from (?:chapter 11|bankruptcy)|emergence from (?:chapter 11|"
    r"bankruptcy)|fresh[- ]start (?:accounting|reporting)|plan of "
    r"reorganization became effective|upon (?:its |our |the company's )?"
    r"emergence", re.I)

# First-person = the FILER is the one that emerged.
_FIRST_PERSON = re.compile(
    r"\b(the company|the registrant|the debtors?|we|our|us|the "
    r"predecessor|the successor)\b", re.I)

# Third-party possessive right before the phrase ("Solutia's emergence",
# "Monsanto's Chapter 11") = someone ELSE emerged.
_THIRD_PARTY = re.compile(
    r"\b([A-Z][A-Za-z&.\-]+(?:\s+[A-Z][A-Za-z&.\-]+){0,3})[''’]s\s+"
    r"(?:emergence|chapter 11|reorganization|bankruptcy|plan)", re.I)
_FILER_WORDS = {"company", "registrant", "debtor", "debtors", "predecessor",
                "successor", "our", "we"}

_DATE = re.compile(
    r"((?:January|February|March|April|May|June|July|August|September|"
    r"October|November|December)\s+\d{1,2},\s+\d{4}|\b(?:19|20)\d{2}\b)")


def _primary_doc_url(cik: int, accession: str) -> str | None:
    accn = accession.replace("-", "")
    idx = (f"https://www.sec.gov/Archives/edgar/data/{cik}/{accn}/"
           f"index.json")
    try:
        j = requests.get(idx, headers=UA, timeout=20).json()
        items = j.get("directory", {}).get("item", [])
    except (requests.RequestException, ValueError, KeyError):
        return None
    docs = [d["name"] for d in items
            if d.get("name", "").lower().endswith((".htm", ".txt"))]
    # main doc = not an R-exhibit, not the filing index
    main = [d for d in docs
            if not d.startswith("R") and "index" not in d.lower()
            and not d.lower().endswith("-index.htm")]
    pick = main[0] if main else (docs[0] if docs else None)
    if not pick:
        return None
    return f"https://www.sec.gov/Archives/edgar/data/{cik}/{accn}/{pick}"


def _strip(html: str) -> str:
    text = re.sub(r"<[^>]+>", " ", html)
    text = text.replace("&#8217;", "'").replace("&#x2019;", "'") \
               .replace("&#160;", " ").replace("&nbsp;", " ")
    return re.sub(r"\s+", " ", text)


def verify(cik: int, accession: str, cache: dict | None = None,
           max_bytes: int = 1_500_000) -> dict:
    """Return {filer_emerged, emergence_date, context, doc}. Cached by
    accession. filer_emerged is None when the document can't be fetched."""
    if cache is not None and accession in cache:
        return cache[accession]
    result = {"filer_emerged": None, "emergence_date": None,
              "context": "", "doc": ""}
    url = _primary_doc_url(cik, accession)
    if not url:
        if cache is not None:
            cache[accession] = result
        return result
    result["doc"] = url
    try:
        r = requests.get(url, headers=UA, timeout=30, stream=True)
        raw = r.raw.read(max_bytes, decode_content=True) or b""
        html = raw.decode(r.encoding or "utf-8", errors="ignore")
    except (requests.RequestException, ValueError):
        if cache is not None:
            cache[accession] = result
        return result
    text = _strip(html)

    first_person = False
    third_party_only = True
    best_ctx = ""
    best_date = None
    for m in _EMERGE.finditer(text):
        lo, hi = max(0, m.start() - 140), min(len(text), m.end() + 60)
        window = text[lo:hi]
        pre = text[lo:m.start()]
        # third-party possessive immediately before the phrase?
        tp = _THIRD_PARTY.search(window)
        tp_is_other = bool(tp) and tp.group(1).split()[-1].lower() \
            not in _FILER_WORDS
        fp = bool(_FIRST_PERSON.search(pre)) or bool(re.search(
            r"\b(company|registrant|debtors?)\s+emerged", window, re.I))
        if fp and not (tp_is_other and not fp):
            first_person = True
        if not tp_is_other:
            third_party_only = False
        if fp and not best_ctx:
            best_ctx = window.strip()
            # search a wider forward window and prefer a full month-day-year
            # date (the emergence date usually prints just after the phrase).
            fwd = text[m.start():min(len(text), m.end() + 240)]
            dates = _DATE.findall(fwd)
            full = [d for d in dates if "," in d]
            if full:
                best_date = full[0]
            elif dates:
                best_date = dates[0]
    # verdict: the filer emerged if any first-person context AND it's not
    # exclusively third-party possessive mentions.
    result["filer_emerged"] = bool(first_person) and not (
        third_party_only and not first_person)
    result["emergence_date"] = best_date
    result["context"] = best_ctx[:200]
    if cache is not None:
        cache[accession] = result
    return result


def load_cache() -> dict:
    if CACHE.exists():
        try:
            return json.loads(CACHE.read_text())
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def save_cache(cache: dict) -> None:
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(json.dumps(cache, indent=2, sort_keys=True))


def main() -> int:
    from src.postreorg_score import collect_postreorg, chapter22_ciks, _norm
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    cohort = collect_postreorg()
    ch22 = chapter22_ciks()

    def genuine(r):
        l = r.get("query_label", "")
        return ("freshstart" in l or "emerged" in l or
                _norm(r.get("name", "")) in ch22)
    recs = [r for r in cohort.values() if genuine(r)]
    if args.limit:
        recs = recs[:args.limit]

    cache = load_cache()
    emerged = incidental = unknown = 0
    for i, r in enumerate(recs):
        cik = r.get("cik")
        acc = r.get("accession")
        if not (cik and acc):
            continue
        v = verify(int(cik), acc, cache)
        tk = (r.get("ticker") or "").split(":")[-1]
        flag = ("FILER-EMERGED" if v["filer_emerged"] else
                "incidental" if v["filer_emerged"] is False else "unknown")
        if v["filer_emerged"]:
            emerged += 1
        elif v["filer_emerged"] is False:
            incidental += 1
        else:
            unknown += 1
        print(f"  {tk:8} {flag:14} {v.get('emergence_date') or '':>18}  "
              f"{v.get('context','')[:70]}")
        time.sleep(0.2)
        if (i + 1) % 20 == 0:
            save_cache(cache)
    save_cache(cache)
    print(f"\nfiler-emerged: {emerged}  ·  incidental (drop): {incidental}  "
          f"·  unknown: {unknown}")
    print(f"Wrote {CACHE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
