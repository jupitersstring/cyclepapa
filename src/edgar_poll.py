#!/usr/bin/env python3
"""
edgar_poll.py — daily SEC EDGAR full-text poller for Tier-S/A/B regex hits.

Addresses methodology_review.md §4.3 (make the discovery pipeline real).
Writes hits to data/inbox/<YYYY-MM-DD>/<tier>/<accession>.json so the
audit trail is rebuildable point-in-time.

Usage:
    python -m src.edgar_poll                       # poll today
    python -m src.edgar_poll --date 2026-05-15     # backfill one day
    python -m src.edgar_poll --days-back 7         # backfill last week
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

try:
    import requests
except ImportError:
    print("Install requests: pip install requests", file=sys.stderr)
    sys.exit(1)

REPO = Path(__file__).resolve().parent.parent
INBOX = REPO / "data" / "inbox"
EDGAR = "https://efts.sec.gov/LATEST/search-index"

# Identify ourselves per EDGAR usage rules. Override via env var.
USER_AGENT = os.environ.get(
    "EDGAR_USER_AGENT",
    "cyclepapa-screener research@example.com"
)
HEADERS = {"User-Agent": USER_AGENT}

# Tiered queries per methodology §1.3 / §1.7
QUERIES: dict[str, str] = {
    "tier_s.rights_offering":      '"rights offering" OR "rights issue"',
    "tier_s.backstop":             '"backstop agreement" OR "backstop commitment"',
    "tier_s.exchange_offer":       '"exchange offer"',
    "tier_s.consent_solicitation": '"consent solicitation"',
    "tier_s.lien_release":         '"UCC termination" OR "lien release"',
    "tier_s.scheme":               '"scheme of arrangement" OR "restructuring plan"',
    "tier_s.tender":               '"tender offer" AND ("debt" OR "notes")',
    "red_flag.going_concern":      '"substantial doubt" AND "going concern"',
    "red_flag.advisor":            '"strategic alternatives" OR "financial advisor"',
    "rev_pref.insider_buy":        '"director purchase" OR "section 16 acquisition"',
}

FORMS = "8-K,6-K,S-1,S-3,424B5,T-3,SC 13D,SC 13G,DEF 14A,4"


def fetch_one_day(query: str, day: date, retries: int = 4) -> list[dict]:
    iso = day.isoformat()
    params = {
        "q": query, "forms": FORMS,
        "dateRange": "custom", "startdt": iso, "enddt": iso,
    }
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
                print(f"  ! failed after {retries} attempts: {exc}", file=sys.stderr)
                return []
            time.sleep(delay)
            delay *= 2
    return []


def normalize_hit(label: str, hit: dict, query: str, fetched_at: str) -> dict:
    src = hit.get("_source", {})
    ciks = src.get("ciks", [])
    accession = src.get("adsh", "")
    cik = ciks[0] if ciks else ""
    url = (
        f"https://www.sec.gov/Archives/edgar/data/"
        f"{int(cik):d}/{accession.replace('-', '')}"
        if cik and accession else ""
    )
    return {
        "tier": label.split(".")[0],
        "query_label": label,
        "query": query,
        "cik": cik,
        "ticker": (src.get("tickers") or [None])[0],
        "name": src.get("display_names") or src.get("name") or "",
        "form": src.get("form"),
        "accession": accession,
        "filed": src.get("file_date"),
        "url": url,
        "fetched_at": fetched_at,
    }


def write_inbox(day: date, records: list[dict]) -> Path:
    day_dir = INBOX / day.isoformat()
    day_dir.mkdir(parents=True, exist_ok=True)
    for r in records:
        tier_dir = day_dir / r["tier"]
        tier_dir.mkdir(exist_ok=True)
        # Stable filename per accession so re-runs are idempotent
        slug = (r["accession"] or "no-accession").replace("/", "_")
        path = tier_dir / f"{slug}.json"
        path.write_text(json.dumps(r, indent=2, sort_keys=True, default=str))
    return day_dir


def poll(day: date) -> int:
    fetched_at = datetime.utcnow().isoformat() + "Z"
    all_records: list[dict] = []
    print(f"Polling EDGAR for {day.isoformat()}...")
    for label, query in QUERIES.items():
        hits = fetch_one_day(query, day)
        print(f"  {label}: {len(hits)} hits")
        for h in hits:
            all_records.append(normalize_hit(label, h, query, fetched_at))
        # EDGAR fair-use throttle
        time.sleep(0.15)
    if all_records:
        out = write_inbox(day, all_records)
        print(f"Wrote {len(all_records)} records to {out}")
    else:
        print("No hits.")
    return len(all_records)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--date", type=lambda s: datetime.strptime(s, "%Y-%m-%d").date(),
                    default=date.today())
    ap.add_argument("--days-back", type=int, default=0,
                    help="If set, poll a range of days ending at --date.")
    args = ap.parse_args()

    total = 0
    if args.days_back > 0:
        for n in range(args.days_back, -1, -1):
            day = args.date - timedelta(days=n)
            total += poll(day)
    else:
        total += poll(args.date)
    print(f"Done. {total} records.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
