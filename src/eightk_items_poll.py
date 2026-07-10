#!/usr/bin/env python3
"""
eightk_items_poll.py — precise 8-K item-code event poller.

Upgrades the framework's 8-K sourcing from blunt keyword full-text
search to precise structured item-code triggers. EDGAR's full-text
search exposes each 8-K's actual item list in the `items` field, so
we query by phrase AND verify the structured field — eliminating the
false positives where "Item 1.03" merely appears in the body text.

Each 8-K item code is a distinct special-situation type:
  1.03  Bankruptcy or receivership                    → tier_s
  2.04  Triggering event on a financial obligation
        (acceleration / default)                       → tier_s
  3.01  Notice of delisting / failure to satisfy a
        continued-listing rule (the PRE-going-dark
        deficiency signal — ~180 days before Form 15)  → tier_s
  4.02  Non-reliance on previously issued financials
        (restatement — cleanest fraud/accounting flag) → red_flag
  1.02  Termination of a material definitive agreement → red_flag
  2.06  Material impairments                            → red_flag
  5.02  Departure/appointment of directors or officers → rev_pref
        (high volume; signal-only, not auto-promoted)

Output: data/inbox/<filing-date>/<tier>/eightk_<accession>.json.
inbox_promote.py whitelists the tier_s item sub-labels.

Usage:
    python -m src.eightk_items_poll                 # today + yesterday
    python -m src.eightk_items_poll --days-back 7
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

from src.edgar_util import issuer_fields

REPO = Path(__file__).resolve().parent.parent
INBOX = REPO / "data" / "inbox"
EDGAR = "https://efts.sec.gov/LATEST/search-index"

USER_AGENT = os.environ.get(
    "EDGAR_USER_AGENT", "cyclepapa-screener research@example.com")
HEADERS = {"User-Agent": USER_AGENT, "Accept": "application/json"}

# item code → (tier, sub_label, note). Ordered high-signal first.
ITEM_MAP: dict[str, tuple[str, str, str]] = {
    "1.03": ("tier_s", "item_bankruptcy",
             "8-K Item 1.03 — bankruptcy or receivership"),
    "2.04": ("tier_s", "item_default_acceleration",
             "8-K Item 2.04 — triggering event on a financial obligation "
             "(acceleration / covenant default / put)"),
    "3.01": ("tier_s", "item_delisting_deficiency",
             "8-K Item 3.01 — delisting / continued-listing-rule failure. "
             "The PRE-going-dark deficiency signal (~180 days before a "
             "Form 15). Cure via reverse split or face delisting."),
    "4.02": ("red_flag", "item_restatement",
             "8-K Item 4.02 — non-reliance on previously issued financial "
             "statements (restatement). Cleanest accounting-integrity flag."),
    "1.02": ("red_flag", "item_material_agreement_termination",
             "8-K Item 1.02 — termination of a material definitive agreement"),
    "2.06": ("red_flag", "item_material_impairment",
             "8-K Item 2.06 — material impairment"),
    "5.02": ("rev_pref", "item_officer_director_change",
             "8-K Item 5.02 — departure/appointment of directors or officers"),
}


def fetch(item: str, start: date, end: date,
          retries: int = 4) -> list[dict]:
    params = {
        "q": f'"Item {item}"', "forms": "8-K",
        "startdt": start.isoformat(), "enddt": end.isoformat(),
    }
    url = f"{EDGAR}?{urlencode(params)}"
    delay = 1.0
    for attempt in range(retries):
        try:
            r = requests.get(url, headers=HEADERS, timeout=30)
            if r.status_code == 429:
                time.sleep(delay); delay *= 2
                continue
            r.raise_for_status()
            return r.json().get("hits", {}).get("hits", [])
        except requests.RequestException as exc:
            if attempt == retries - 1:
                print(f"  ! EDGAR failed after {retries} attempts: {exc}",
                      file=sys.stderr)
                return []
            time.sleep(delay); delay *= 2
    return []


def normalize_hit(item: str, hit: dict, fetched_at: str) -> dict:
    tier, sub, note = ITEM_MAP[item]
    src = hit.get("_source", {})
    fields = issuer_fields(src)
    accession = src.get("adsh", "")
    cik = fields["cik"] or ""
    url = (f"https://www.sec.gov/Archives/edgar/data/"
           f"{int(cik):d}/{accession.replace('-', '')}"
           if cik and accession else "")
    return {
        "tier":        tier,
        "query_label": f"{tier}.{sub}",
        "query_note":  note,
        "cik":         cik,
        "ticker":      fields["ticker"],
        "isin":        None,
        "name":        fields["name"],
        "form":        f"8-K Item {item}",
        "form_code":   f"8-K/{item}",
        "accession":   accession,
        "filed":       src.get("file_date") or "",
        "jurisdiction": "US",
        "url":         url,
        "all_items":   src.get("items") or [],
        "source":      "EDGAR-8K-items",
        "fetched_at":  fetched_at,
    }


def write_inbox(records: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for r in records:
        filed = r.get("filed") or date.today().isoformat()
        tier_dir = INBOX / filed[:10] / r["tier"]
        tier_dir.mkdir(parents=True, exist_ok=True)
        sub = r["query_label"].split(".")[-1]
        slug = (r["accession"] or "no-id").replace("/", "_")
        path = tier_dir / f"eightk_{slug}_{sub}.json"
        path.write_text(json.dumps(r, indent=2, sort_keys=True, default=str))
        key = f"{filed[:10]}/{r['tier']}"
        counts[key] = counts.get(key, 0) + 1
    return counts


def poll(days_back: int, include_5_02: bool) -> int:
    fetched_at = datetime.utcnow().isoformat() + "Z"
    end = date.today()
    start = end - timedelta(days=days_back)
    print(f"Polling EDGAR 8-K item codes "
          f"({start.isoformat()}..{end.isoformat()})...")
    all_records: list[dict] = []
    for item, (tier, sub, _) in ITEM_MAP.items():
        if item == "5.02" and not include_5_02:
            continue          # high-volume; opt-in only
        hits = fetch(item, start, end)
        verified = 0
        for h in hits:
            items = h.get("_source", {}).get("items") or []
            # Structured verification: the item must actually be present
            if item not in items:
                continue
            all_records.append(normalize_hit(item, h, fetched_at))
            verified += 1
        print(f"  Item {item:5s} {sub:34s} "
              f"{len(hits):>4d} hits / {verified:>4d} verified")
        time.sleep(0.15)
    if all_records:
        counts = write_inbox(all_records)
        print(f"\nWrote {len(all_records)} records across "
              f"{len(counts)} day/tier buckets")
    else:
        print("\nNo verified 8-K item hits in window.")
    return len(all_records)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--days-back", type=int, default=1)
    ap.add_argument("--include-5-02", action="store_true",
                    help="Include Item 5.02 (exec change) — high volume")
    args = ap.parse_args()
    total = poll(args.days_back, args.include_5_02)
    print(f"\nDone. {total} records.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
