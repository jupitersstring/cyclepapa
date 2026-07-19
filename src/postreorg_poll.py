#!/usr/bin/env python3
"""
postreorg_poll.py — post-reorganization / fresh-start equity poller.

Closes the framework's largest CATEGORY gap. PACER (pacer_poll.py)
catches companies ENTERING Chapter 11. Nothing catches them EMERGING.
But post-reorg equities — fresh-start companies that exit bankruptcy
and begin trading (often OTC), with no analyst coverage and forced-
seller creditors dumping stock received under the plan — are one of
the richest special-situations categories in the literature
(Greenblatt's "You Can Be a Stock Market Genius", Whitman, the whole
distressed-to-equity playbook).

We source emergence via EDGAR full-text search for the canonical
8-K emergence language — "emerged from Chapter 11", "Plan of
Reorganization became effective", "fresh-start accounting" — which
issuers file when they exit. This is additive to the existing EDGAR
infrastructure; a different query set than edgar_poll.py.

Output: data/inbox/<filing-date>/tier_s/postreorg_<accession>.json,
sub-label tier_s.post_reorg. inbox_promote.py whitelists it so
emergent names flow into universe.md — the payoff end of the
distressed funnel that the framework has been blind to.

Usage:
    python -m src.postreorg_poll                   # last 90 days
    python -m src.postreorg_poll --days-back 180
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.parse import urlencode

from src.edgar_util import issuer_fields, fts_search_all

try:
    import requests
except ImportError:
    print("Install requests: pip install requests", file=sys.stderr)
    sys.exit(1)

REPO = Path(__file__).resolve().parent.parent
INBOX = REPO / "data" / "inbox"
EDGAR = "https://efts.sec.gov/LATEST/search-index"

USER_AGENT = os.environ.get(
    "EDGAR_USER_AGENT", "cyclepapa-screener research@example.com")
HEADERS = {"User-Agent": USER_AGENT, "Accept": "application/json"}

# Emergence-signalling phrases → sub-query label. Fresh-start accounting
# is the strongest (definitionally a post-reorg entity); emergence /
# plan-effective language captures the event announcement.
QUERIES: dict[str, str] = {
    "post_reorg_freshstart":
        '"fresh-start accounting" OR "fresh start reporting" '
        'OR "fresh-start reporting"',
    "post_reorg_emerged":
        '"emerged from Chapter 11" OR "emergence from Chapter 11" '
        'OR "successfully emerged"',
    # NB: the bare phrase "Effective Date of the Plan" also matches employee
    # STOCK-plan / benefit-plan effective dates (GoDaddy, Skyworks, Federated
    # Hermes all false-positived on it), so require the "of Reorganization"
    # qualifier — a genuine Chapter 11 emergence, not a benefit plan.
    "post_reorg_plan_effective":
        '"Plan of Reorganization became effective" '
        'OR "Effective Date of the Plan of Reorganization" '
        'OR "Plan of Reorganization became effective on"',
}
FORMS = "8-K,10-K,10-Q,8-A12B,8-A12G"


def fetch(query: str, start: date, end: date,
          retries: int = 4) -> list[dict]:
    """ALL hits for a query, paginating through EDGAR's 10-per-page full-
    text search (shared paginator). Without this we silently caught only
    the first 10 records per query per run — the cardinal under-catch."""
    params = {
        "q": query, "forms": FORMS,
        "startdt": start.isoformat(), "enddt": end.isoformat(),
    }
    return fts_search_all(params, HEADERS, retries=retries,
                          log=lambda m: print(m, file=sys.stderr))


def normalize_hit(label: str, hit: dict, fetched_at: str) -> dict:
    src = hit.get("_source", {})
    accession = src.get("adsh", "")
    fields = issuer_fields(src)
    cik = fields["cik"] or ""
    name = fields["name"]
    url = (f"https://www.sec.gov/Archives/edgar/data/"
           f"{int(cik):d}/{accession.replace('-', '')}"
           if cik and accession else "")
    note = {
        "post_reorg_freshstart":
            "Fresh-start accounting — a post-emergence entity by "
            "definition. Uncovered equity, forced-seller creditors, "
            "clean cap stack. Classic distressed-to-equity setup.",
        "post_reorg_emerged":
            "Emerged from Chapter 11 — post-reorg equity now trading. "
            "Verify float, creditor overhang, and coverage vacuum.",
        "post_reorg_plan_effective":
            "Plan of Reorganization effective — emergence event. "
            "New equity distributed to creditors; watch for forced "
            "selling window.",
    }.get(label, "Post-reorganization emergence signal.")
    return {
        "tier":        "tier_s",
        "query_label": f"tier_s.{label}",
        "query_note":  note,
        "cik":         cik,
        "ticker":      fields["ticker"],
        "isin":        None,
        "name":        name,
        "form":        src.get("form") or "",
        "form_code":   src.get("form") or "",
        "accession":   accession,
        "filed":       src.get("file_date") or "",
        "jurisdiction": "US",
        "url":         url,
        "source":      "EDGAR-postreorg",
        "fetched_at":  fetched_at,
    }


def write_inbox(records: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for r in records:
        filed = r.get("filed") or date.today().isoformat()
        tier_dir = INBOX / filed[:10] / r["tier"]
        tier_dir.mkdir(parents=True, exist_ok=True)
        slug = (r["accession"] or "no-id").replace("/", "_")
        path = tier_dir / f"postreorg_{slug}.json"
        path.write_text(json.dumps(r, indent=2, sort_keys=True, default=str))
        key = f"{filed[:10]}/{r['tier']}"
        counts[key] = counts.get(key, 0) + 1
    return counts


def poll(days_back: int) -> int:
    fetched_at = datetime.utcnow().isoformat() + "Z"
    end = date.today()
    start = end - timedelta(days=days_back)
    print(f"Polling EDGAR for post-reorg emergence "
          f"({start.isoformat()}..{end.isoformat()})...")
    all_records: list[dict] = []
    seen_acc: set[str] = set()
    for label, query in QUERIES.items():
        hits = fetch(query, start, end)
        kept = 0
        for h in hits:
            acc = h.get("_source", {}).get("adsh", "")
            if acc and acc in seen_acc:
                continue
            seen_acc.add(acc)
            all_records.append(normalize_hit(label, h, fetched_at))
            kept += 1
        print(f"  {label:28s} {kept:>4d} unique hits")
        time.sleep(0.15)
    if all_records:
        counts = write_inbox(all_records)
        print(f"\nWrote {len(all_records)} records across "
              f"{len(counts)} day/tier buckets")
    else:
        print("\nNo post-reorg emergence signals in window.")
    return len(all_records)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--days-back", type=int, default=90)
    args = ap.parse_args()
    total = poll(args.days_back)
    print(f"\nDone. {total} records.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
