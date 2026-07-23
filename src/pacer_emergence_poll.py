#!/usr/bin/env python3
"""
pacer_emergence_poll.py — court-side EMERGENCE poller (plan confirmation +
effective date), via CourtListener RECAP.

pacer_poll catches Chapter 11 ENTRY (the petition). This catches the EXIT
from the docket side: the bankruptcy court's **order confirming the plan of
reorganization** and the **notice of effective date** — the exact, dated
emergence moment, earlier and more authoritative than inferring it from an
8-K's prose. GoHealth's effective-date docket entry, for example, is right
here on the court record.

Free CourtListener v4 search API (same posture as pacer_poll). Filtered to
commercial company names so the flood of small-LLC bankruptcies is excluded.

Output: data/inbox/<filed>/tier_s/paceremg_<id>.json —
  tier_s.post_reorg_emerged  (effective-date = emerged)
  tier_s.plan_confirmed      (confirmation order; ~2 wks before effectiveness)

Usage:
    python -m src.pacer_emergence_poll --days-back 120
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

# (query, sub-label, note). Effective-date = emerged; confirmation precedes it.
QUERIES = [
    ('"notice of effective date"', "post_reorg_emerged",
     "Court NOTICE OF EFFECTIVE DATE — the plan of reorganization has become "
     "effective: the exact, dated emergence moment on the bankruptcy docket."),
    ('"order confirming" "plan of reorganization"', "plan_confirmed",
     "Court ORDER CONFIRMING the plan of reorganization — confirmation "
     "precedes the effective date by ~2 weeks; emergence is imminent."),
]


def fetch(query: str, filed_after: str, pages: int = 3) -> list[dict]:
    out: list[dict] = []
    for page in range(1, pages + 1):
        params = {"type": "r", "q": query, "order_by": "dateFiled desc",
                  "filed_after": filed_after, "page": str(page),
                  "page_size": "50"}
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
                    nxt = None
                    break
                time.sleep(delay); delay *= 2
        if not nxt:
            break
        time.sleep(0.2)
    return out


def poll(days_back: int) -> int:
    fetched_at = datetime.utcnow().isoformat() + "Z"
    filed_after = (date.today() - timedelta(days=days_back)).isoformat()
    print(f"Polling CourtListener for emergence dockets since "
          f"{filed_after}...")
    seen: set[str] = set()
    records: list[dict] = []
    for query, sub, note in QUERIES:
        hits = fetch(query, filed_after)
        kept = 0
        for h in hits:
            name = str(h.get("caseName") or "")
            if not is_commercial(name):
                continue        # drop individual / small-LLC bankruptcies
            did = str(h.get("docket_id") or h.get("id") or "")
            key = f"{did}:{sub}"
            if not did or key in seen:
                continue
            seen.add(key)
            records.append({
                "tier": "tier_s",
                "query_label": f"tier_s.{sub}",
                "query_note": note,
                "cik": "",
                "ticker": "",
                "isin": None,
                "name": name,
                "form": (h.get("court") or h.get("court_id") or "")[:80],
                "form_code": "RECAP-docket",
                "accession": did,
                "filed": (h.get("dateFiled") or filed_after)[:10],
                "jurisdiction": "US",
                "url": ("https://www.courtlistener.com" +
                        str(h.get("docket_absolute_url") or "")),
                "source": "CourtListener-emergence",
                "fetched_at": fetched_at,
            })
            kept += 1
        print(f"  {sub:22s} {kept:>4d} commercial emergence dockets")
        time.sleep(0.3)
    if records:
        for r in records:
            d = INBOX / r["filed"][:10] / r["tier"]
            d.mkdir(parents=True, exist_ok=True)
            (d / f"paceremg_{r['accession']}_{r['query_label'].split('.')[-1]}"
                 f".json").write_text(
                json.dumps(r, indent=2, sort_keys=True, default=str))
        print(f"\nWrote {len(records)} court-side emergence records")
    else:
        print("\nNo commercial emergence dockets in window.")
    return len(records)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--days-back", type=int, default=120)
    args = ap.parse_args()
    total = poll(args.days_back)
    print(f"\nDone. {total} records.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
