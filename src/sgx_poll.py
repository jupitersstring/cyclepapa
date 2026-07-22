#!/usr/bin/env python3
"""
sgx_poll.py — Singapore Exchange (SGX) special-situations poller.

Catches SGX-listed restructuring / scheme-of-arrangement / capital-
reorganisation events the EDGAR/US funnel can't see. Uses the free legacy
SGX infofeed (api3.sgx.com) — validated: plain GET, no auth / Akamai /
paywall. (The modern api.sgx.com/announcements API is Akamai-bot-blocked to
plain curl, so we deliberately use the legacy feed.)

The feed only serves "AnnouncementToday", so this must run DAILY to build
coverage (each run captures that day's announcements; dedup on the item key).

Output: data/inbox/<filed>/tier_s/sgx_<key>.json.

Usage:
    python -m src.sgx_poll
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import date, datetime
from pathlib import Path

try:
    import requests
except ImportError:
    print("Install requests", file=sys.stderr); sys.exit(1)

REPO = Path(__file__).resolve().parent.parent
INBOX = REPO / "data" / "inbox"
ENDPOINT = ("https://api3.sgx.com/infofeed/Apps?A=COW_CorpAnnouncement_Content"
            "&B=AnnouncementToday&C_T=-1")
HEADERS = {"User-Agent": os.environ.get(
    "EDGAR_USER_AGENT", "cyclepapa-screener research@example.com")}

# SGX CategoryCode → (sub-label, note). Special-situation-relevant only.
CATEGORIES: dict[str, tuple[str, str]] = {
    "CACT13": ("scheme", "SGX Scheme of Arrangement — court-supervised "
                         "recapitalisation / compromise with creditors."),
    "ANNC12": ("scheme", "SGX Court Meeting — convening of the scheme "
                         "creditors'/members' meeting."),
    "CACT07": ("restructuring", "SGX Corporate Debt Restructuring — "
                                "balance-sheet restructuring in progress."),
    "CACT05": ("recapitalisation", "SGX Exchange Offer / Capital "
                                   "Reorganisation — liability management."),
    "CACT20": ("spinoff", "SGX Spin-Off / Demerger."),
    "CACT16": ("self_tender", "SGX Repurchase Offer / Issuer Bid / Reverse "
                              "Rights."),
}


def fetch(retries: int = 4) -> list[dict]:
    """The infofeed body is JSON served as text/plain; parse from the first
    '{'. An empty feed returns a MALFORMED body, so guard the parse."""
    import time
    delay = 1.0
    for attempt in range(retries):
        try:
            r = requests.get(ENDPOINT, headers=HEADERS, timeout=30)
            r.raise_for_status()
            body = r.text
            i = body.find("{")
            if i < 0:
                return []
            try:
                data = json.loads(body[i:])
            except json.JSONDecodeError:
                return []          # malformed empty-feed body
            return data.get("items") or []
        except requests.RequestException as exc:
            if attempt == retries - 1:
                print(f"  ! SGX failed: {exc}", file=sys.stderr)
                return []
            time.sleep(delay); delay *= 2
    return []


def _date(item: dict) -> str:
    d = str(item.get("Date") or "")
    for fmt in ("%d %b %Y", "%d-%b-%Y", "%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(d, fmt).date().isoformat()
        except ValueError:
            continue
    return date.today().isoformat()


def normalize(item: dict, sub: str, note: str, fetched_at: str) -> dict:
    key = str(item.get("key") or item.get("id") or "")
    name = (item.get("IssuerName") or item.get("SecurityName") or "").strip()
    code = str(item.get("StockCode") or item.get("Code") or "").strip()
    url = item.get("url") or item.get("AnnouncementURL") or ""
    if url and not url.startswith("http"):
        url = "https://links.sgx.com" + url
    return {
        "tier": "tier_s",
        "query_label": f"tier_s.{sub}",
        "query_note": note,
        "cik": "",
        "ticker": f"SGX:{code}" if code else "",
        "isin": None,
        "name": name,
        "form": (item.get("Title") or item.get("CategoryName") or "")[:160],
        "form_code": "SGX-announcement",
        "accession": key,
        "filed": _date(item),
        "jurisdiction": "SG",
        "url": url,
        "source": "SGX",
        "fetched_at": fetched_at,
    }


def write_inbox(records: list[dict]) -> int:
    for r in records:
        d = INBOX / r["filed"][:10] / r["tier"]
        d.mkdir(parents=True, exist_ok=True)
        slug = re.sub(r"[^A-Za-z0-9]", "_", r["accession"] or "no-id")[:60]
        (d / f"sgx_{slug}.json").write_text(
            json.dumps(r, indent=2, sort_keys=True, default=str))
    return len(records)


def poll() -> int:
    fetched_at = datetime.utcnow().isoformat() + "Z"
    print("Polling SGX infofeed (AnnouncementToday)...")
    items = fetch()
    print(f"  {len(items)} announcements today")
    records, counts = [], {}
    for it in items:
        cat = str(it.get("CategoryCode") or "").upper()
        if cat not in CATEGORIES:
            continue
        sub, note = CATEGORIES[cat]
        records.append(normalize(it, sub, note, fetched_at))
        counts[sub] = counts.get(sub, 0) + 1
    if records:
        write_inbox(records)
        print(f"  kept {len(records)} special-situation events: "
              f"{', '.join(f'{k}={v}' for k, v in counts.items())}")
    else:
        print("  no special-situation announcements today")
    return len(records)


def main() -> int:
    argparse.ArgumentParser(description=__doc__).parse_args()
    total = poll()
    print(f"\nDone. {total} records.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
