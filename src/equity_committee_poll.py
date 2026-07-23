#!/usr/bin/env python3
"""
equity_committee_poll.py — the Hertz-signal tracker (equity committees +
plan competition), via CourtListener RECAP.

The case-study record's cleanest discriminator between a Hertz (old common
paid ~$8 after trading ~$1) and a Sears-class zero is mechanical:

  1. An OFFICIAL COMMITTEE OF EQUITY SECURITY HOLDERS was appointed — the
     court signaling the estate may be SOLVENT (equity is in the money
     enough to deserve representation). Rare (~a handful/yr) and decisive.
     GGP, Hertz and Texaco-class solvent debtors all had one.
  2. COMPETING PLANS / a plan auction — multiple sponsors bidding for the
     estate raises every class's recovery (Hertz: Knighthead/Certares vs
     Centerbridge/Warburg took old equity from ~$1 to ~$8).

This poller searches the RECAP docket record for both, filtered to
bankruptcy courts and commercial names. These are the ONLY conditions under
which in-case OLD common is investable per the framework's rules (T1 in
docs/POSTREORG_CASE_STUDIES.md); absent both, old equity is a donation.

Output: data/inbox/<filed>/tier_s/eqcmte_<id>.json —
  tier_s.equity_committee / tier_s.plan_competition

Usage:
    python -m src.equity_committee_poll --days-back 365
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path

try:
    import requests
except ImportError:
    print("Install requests", file=sys.stderr); sys.exit(1)

from src.pacer_poll import is_commercial

REPO = Path(__file__).resolve().parent.parent
INBOX = REPO / "data" / "inbox"
API = "https://www.courtlistener.com/api/rest/v4/search/"
UA = {"User-Agent": os.environ.get(
    "EDGAR_USER_AGENT", "cyclepapa-screener research@example.com"),
    "Accept": "application/json"}

# (query, sub-label, precise?, note)
QUERIES = [
    ('"official committee of equity security holders"', "equity_committee",
     True,
     "OFFICIAL EQUITY COMMITTEE appointed — the court signaling the estate "
     "may be solvent (the GGP/Hertz precondition). In-case old common is "
     "only investable when this (or a plan auction) is present."),
    ('"equity committee"', "equity_committee", False,
     "Equity-committee reference on the docket (recall net — verify an "
     "OFFICIAL committee was actually appointed)."),
    ('"competing plan"', "plan_competition", False,
     "COMPETING PLANS on the docket — a plan auction in the making; "
     "competition among sponsors raises every class's recovery (Hertz)."),
]


def fetch(query: str, filed_after: str, pages: int = 3) -> list[dict]:
    out: list[dict] = []
    for page in range(1, pages + 1):
        params = {"type": "r", "q": query, "order_by": "dateFiled desc",
                  "filed_after": filed_after, "page": str(page),
                  "page_size": "50"}
        nxt = None
        delay = 1.0
        for attempt in range(3):
            try:
                r = requests.get(API, params=params, headers=UA, timeout=30)
                if r.status_code == 429:
                    time.sleep(delay); delay *= 2; continue
                r.raise_for_status()
                j = r.json()
                out += j.get("results", [])
                nxt = j.get("next")
                break
            except (requests.RequestException, ValueError):
                if attempt == 2:
                    break
                time.sleep(delay); delay *= 2
        if not nxt:
            break
        time.sleep(0.2)
    return out


def poll(days_back: int) -> int:
    fetched_at = datetime.utcnow().isoformat() + "Z"
    filed_after = (date.today() - timedelta(days=days_back)).isoformat()
    print(f"Polling CourtListener for equity committees / plan competition "
          f"since {filed_after}...")
    seen: set[str] = set()
    records: list[dict] = []
    for query, sub, precise, note in QUERIES:
        hits = fetch(query, filed_after)
        kept = 0
        for h in hits:
            court = str(h.get("court_id") or "")
            name = str(h.get("caseName") or "")
            # bankruptcy courts only (court_id ends in 'b'), commercial names
            # only — kills the health-plan / adversary-case noise.
            if not court.endswith("b") or not is_commercial(name):
                continue
            did = str(h.get("docket_id") or h.get("id") or "")
            key = f"{did}:{sub}"
            if not did or key in seen:
                continue
            seen.add(key)
            records.append({
                "tier": "tier_s",
                "query_label": f"tier_s.{sub}",
                "query_note": note,
                "precise_match": precise,
                "cik": "", "ticker": "", "isin": None,
                "name": name,
                "form": court,
                "form_code": "RECAP-docket",
                "accession": did,
                "filed": (h.get("dateFiled") or filed_after)[:10],
                "jurisdiction": "US",
                "url": ("https://www.courtlistener.com" +
                        str(h.get("docket_absolute_url") or "")),
                "source": "CourtListener-eqcommittee",
                "fetched_at": fetched_at,
            })
            kept += 1
        tag = "precise" if precise else "recall "
        print(f"  [{tag}] {sub:18s} {kept:>3d} commercial bankruptcy dockets")
        time.sleep(0.3)
    for r in records:
        d = INBOX / r["filed"][:10] / r["tier"]
        d.mkdir(parents=True, exist_ok=True)
        (d / f"eqcmte_{r['accession']}_{r['query_label'].split('.')[-1]}.json"
         ).write_text(json.dumps(r, indent=2, sort_keys=True, default=str))
    if records:
        print(f"\nWrote {len(records)} records. Equity-committee names are "
              f"the ONLY cases where in-case old common is investable.")
    else:
        print("\nNo equity-committee / plan-competition dockets in window.")
    return len(records)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--days-back", type=int, default=365)
    args = ap.parse_args()
    total = poll(args.days_back)
    print(f"\nDone. {total} records.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
