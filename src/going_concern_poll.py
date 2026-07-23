#!/usr/bin/env python3
"""
going_concern_poll.py — going-concern RECOVERY poller (and distress radar).

A "going concern" audit qualification is the auditor stating substantial
doubt about survival — the classic distress leading indicator. The
high-value special-situations signal is its REMOVAL: when a later 10-K/10-Q
reports that the substantial doubt has been **alleviated / resolved**, the
company has turned the corner (refinanced, recapitalised, returned to
profitability) — a recovery the market is often slow to re-rate. This is the
non-bankruptcy cousin of a post-reorg emergence.

Two signals (EDGAR full-text, paginated):
  going_concern_lifted  — doubt alleviated/resolved   (the recovery signal)
  going_concern_flag    — doubt raised                (distress radar; opt-in)

Output: data/inbox/<filed>/tier_s/gc_<accession>.json.

Usage:
    python -m src.going_concern_poll --days-back 120
    python -m src.going_concern_poll --include-flags   # also the distress side
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

from src.edgar_util import issuer_fields, fts_search_all

try:
    import requests   # noqa: F401 (used transitively by fts_search_all)
except ImportError:
    print("Install requests", file=sys.stderr); sys.exit(1)

REPO = Path(__file__).resolve().parent.parent
INBOX = REPO / "data" / "inbox"
HEADERS = {"User-Agent": os.environ.get(
    "EDGAR_USER_AGENT", "cyclepapa-screener research@example.com"),
    "Accept": "application/json"}
FORMS = "10-K,10-Q,20-F,6-K"

LIFTED_QUERIES = [
    '"substantial doubt" "alleviated"',
    '"substantial doubt" "has been resolved"',
    '"substantial doubt" "no longer exists"',
    '"conditions that raised substantial doubt" "no longer"',
]
FLAG_QUERY = '"substantial doubt" "going concern"'


def _fetch(query: str, start: date, end: date) -> list[dict]:
    params = {"q": query, "forms": FORMS,
              "startdt": start.isoformat(), "enddt": end.isoformat()}
    return fts_search_all(params, HEADERS,
                          log=lambda m: print(m, file=sys.stderr))


def normalize(hit: dict, sub: str, note: str, fetched_at: str) -> dict:
    src = hit.get("_source", {})
    f = issuer_fields(src)
    cik = f["cik"] or ""
    acc = src.get("adsh", "")
    return {
        "tier": "tier_s" if sub == "going_concern_lifted" else "rev_pref",
        "query_label": f"tier_s.{sub}" if sub == "going_concern_lifted"
        else f"red_flag.{sub}",
        "query_note": note,
        "cik": cik,
        "ticker": f["ticker"] or "",
        "isin": None,
        "name": f["name"],
        "form": src.get("form") or "",
        "form_code": src.get("form") or "",
        "accession": acc,
        "filed": src.get("file_date") or "",
        "jurisdiction": "US",
        "url": (f"https://www.sec.gov/Archives/edgar/data/{int(cik):d}/"
                f"{acc.replace('-', '')}" if cik and acc else ""),
        "source": "EDGAR-going-concern",
        "fetched_at": fetched_at,
    }


def poll(days_back: int, include_flags: bool) -> int:
    fetched_at = datetime.utcnow().isoformat() + "Z"
    end = date.today()
    start = end - timedelta(days=days_back)
    print(f"Polling EDGAR going-concern ({start.isoformat()}.."
          f"{end.isoformat()})...")
    by_acc: dict[str, dict] = {}
    for q in LIFTED_QUERIES:
        hits = _fetch(q, start, end)
        for h in hits:
            acc = h.get("_source", {}).get("adsh", "")
            if acc and acc not in by_acc:
                by_acc[acc] = normalize(
                    h, "going_concern_lifted",
                    "Going-concern doubt ALLEVIATED / RESOLVED — a survival "
                    "turnaround (refinanced / recapitalised / returned to "
                    "profit). Recovery signal the market is slow to re-rate.",
                    fetched_at)
        print(f"  lifted: {q[:44]:44} +{len(hits):>4d}")
    lifted_n = len(by_acc)
    if include_flags:
        hits = _fetch(FLAG_QUERY, start, end)
        for h in hits:
            acc = h.get("_source", {}).get("adsh", "")
            if acc and acc not in by_acc:
                by_acc[acc] = normalize(
                    h, "going_concern_flag",
                    "Going-concern doubt RAISED — distress leading indicator.",
                    fetched_at)
        print(f"  flag:   {FLAG_QUERY[:44]:44} +{len(hits):>4d}")
    records = list(by_acc.values())
    for r in records:
        if not r["filed"]:
            continue
        d = INBOX / r["filed"][:10] / r["tier"]
        d.mkdir(parents=True, exist_ok=True)
        slug = (r["accession"] or "no-id").replace("/", "_")
        (d / f"gc_{slug}.json").write_text(
            json.dumps(r, indent=2, sort_keys=True, default=str))
    print(f"\nWrote {len(records)} records "
          f"({lifted_n} going-concern-LIFTED recoveries)")
    return len(records)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--days-back", type=int, default=120)
    ap.add_argument("--include-flags", action="store_true",
                    help="also poll the distress side (high volume)")
    args = ap.parse_args()
    total = poll(args.days_back, args.include_flags)
    print(f"\nDone. {total} records.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
