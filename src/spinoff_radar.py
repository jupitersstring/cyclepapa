#!/usr/bin/env python3
"""
spinoff_radar.py — Form 10-12B early-warning detector.

Per the sourcing playbook: Form 10-12B is the single best spinoff
early-warning. The information statement appears 3-6 months before
completion (Allegion: filed ~Jun 17 2013 ahead of distribution).
Not all spinoffs file 10-12B — supplement with 8-K full-text search
for 'spin-off', 'separation', 'Form 10'.

Uses EDGAR full-text JSON API (free, 2001-present, boolean filterable).
Writes hits to data/inbox/<YYYY-MM-DD>/spinoff/<accession>.json.

Usage:
    python -m src.spinoff_radar                       # today
    python -m src.spinoff_radar --days-back 30        # backfill last 30 days
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
from src.edgar_util import issuer_fields

try:
    import requests
except ImportError:
    print("Install requests: pip install requests", file=sys.stderr)
    sys.exit(1)

REPO = Path(__file__).resolve().parent.parent
INBOX = REPO / "data" / "inbox"
EDGAR = "https://efts.sec.gov/LATEST/search-index"

USER_AGENT = os.environ.get(
    "EDGAR_USER_AGENT",
    "cyclepapa-spinoff-radar research@example.com",
)
HEADERS = {"User-Agent": USER_AGENT}

# Per the playbook: the canonical spinoff registration forms plus
# 8-K full-text fallback for filings that don't use 10-12B (often
# foreign-domiciled separations).
SPINOFF_QUERIES: dict[str, dict] = {
    "form_10_12b": {
        "forms": "10-12B,10-12B/A,10-12G,10-12G/A",
        "q": "",
        "_note": "Spinoff registration — 3-6 month early warning",
    },
    "form_8k_spin": {
        "forms": "8-K",
        "q": '"spin-off" OR "spinoff" OR "separation transaction"',
        "_note": "8-K catch-all for spinoffs that skip 10-12B",
    },
    "form_8k_distribute": {
        "forms": "8-K",
        "q": '"distribution of common stock" AND ("subsidiary" OR "Form 10")',
        "_note": "Distribution language — late-stage spinoff signal",
    },
    "form_s1_spin": {
        "forms": "S-1,S-1/A",
        "q": '"spin-off" OR "spinoff"',
        "_note": "S-1 used in some carve-out IPO+spinoff structures",
    },
    "form_proxy_spin": {
        "forms": "DEF 14A,PRE 14A",
        "q": '"separation" AND ("vote" OR "approval")',
        "_note": "Shareholder vote on separation",
    },
    "reverse_morris_trust": {
        "forms": "8-K,10-12B",
        "q": '"reverse morris trust" OR "tax-free reorganization"',
        "_note": "RMT — spinoff immediately merged with 3rd party",
    },
}


def fetch_one_day(query_label: str, query_def: dict, day: date,
                  retries: int = 4) -> list[dict]:
    iso = day.isoformat()
    params = {
        "forms": query_def["forms"],
        "dateRange": "custom",
        "startdt": iso,
        "enddt": iso,
    }
    q = query_def.get("q", "").strip()
    if q:
        params["q"] = q

    url = f"{EDGAR}?{urlencode(params)}"
    delay = 1.0
    for attempt in range(retries):
        try:
            r = requests.get(url, headers=HEADERS, timeout=30)
            if r.status_code == 429:
                time.sleep(delay)
                delay *= 2
                continue
            r.raise_for_status()
            return r.json().get("hits", {}).get("hits", [])
        except requests.RequestException as exc:
            if attempt == retries - 1:
                print(f"  ! failed after {retries} attempts: {exc}",
                      file=sys.stderr)
                return []
            time.sleep(delay)
            delay *= 2
    return []


def normalize_hit(label: str, hit: dict, query_def: dict,
                  fetched_at: str) -> dict:
    src = hit.get("_source", {})
    accession = src.get("adsh", "")
    fields = issuer_fields(src)
    cik = fields["cik"] or ""
    url = (
        f"https://www.sec.gov/Archives/edgar/data/"
        f"{int(cik):d}/{accession.replace('-', '')}"
        if cik and accession else ""
    )
    return {
        "tier": "spinoff",
        "query_label": label,
        "query_note": query_def.get("_note", ""),
        "cik": cik,
        "ticker": fields["ticker"],
        "name": fields["name"],
        "form": src.get("form"),
        "accession": accession,
        "filed": src.get("file_date"),
        "url": url,
        "source": "EDGAR-spinoff-radar",
        "fetched_at": fetched_at,
    }


def write_inbox(day: date, records: list[dict]) -> Path:
    day_dir = INBOX / day.isoformat() / "spinoff"
    day_dir.mkdir(parents=True, exist_ok=True)
    for r in records:
        slug = (r["accession"] or "no-accession").replace("/", "_")
        path = day_dir / f"{slug}.json"
        path.write_text(json.dumps(r, indent=2, sort_keys=True, default=str))
    return day_dir


def poll(day: date) -> int:
    fetched_at = datetime.utcnow().isoformat() + "Z"
    all_records: list[dict] = []
    seen_accessions: set[str] = set()  # dedupe across query overlap
    print(f"Polling EDGAR for spinoff signals on {day.isoformat()}...")
    for label, q_def in SPINOFF_QUERIES.items():
        hits = fetch_one_day(label, q_def, day)
        new_hits = 0
        for h in hits:
            r = normalize_hit(label, h, q_def, fetched_at)
            if r["accession"] in seen_accessions:
                continue
            seen_accessions.add(r["accession"])
            all_records.append(r)
            new_hits += 1
        print(f"  {label}: {len(hits)} hits ({new_hits} new)")
        time.sleep(0.15)
    if all_records:
        out = write_inbox(day, all_records)
        print(f"Wrote {len(all_records)} unique spinoff records to {out}")
    else:
        print("No spinoff signals.")
    return len(all_records)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--date",
                    type=lambda s: datetime.strptime(s, "%Y-%m-%d").date(),
                    default=date.today())
    ap.add_argument("--days-back", type=int, default=0,
                    help="Backfill range ending at --date")
    args = ap.parse_args()

    total = 0
    if args.days_back > 0:
        for n in range(args.days_back, -1, -1):
            day = args.date - timedelta(days=n)
            total += poll(day)
    else:
        total += poll(args.date)
    print(f"Done. {total} unique spinoff records.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
