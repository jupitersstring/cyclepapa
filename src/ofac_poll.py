#!/usr/bin/env python3
"""
ofac_poll.py — OFAC Recent Actions poller (sanctions-restructuring calendar).

Implements keeper #5 from output/process_improvements_keepers.md.

The U.S. Treasury's Office of Foreign Assets Control publishes recent
sanctions actions at https://ofac.treasury.gov/recent-actions. Each
action is a dated event with a one-line title and a link to the
detail page. Pagination via ?page=N returns 7 items per page.

OFAC General Licenses (GLs) create dated transaction windows that
authorise otherwise-prohibited dealings — humanitarian carve-outs,
energy stabilisation (Venezuela 2024), Russia sovereign-debt wind-
down, etc. Designations add entities/individuals to the SDN list;
removals open up previously-frozen exposures. Each event class is
a sourcing signal for restructuring-adjacent equity / debt.

Filter classes:
- "General License" / "GL " issuance → tier_s.ofac_license
- "Designations Removals" / "Removed" → tier_s.ofac_removal
- "Designation" / "Designations" → red_flag.ofac_designation
- "Notice" / "Guidance" → red_flag.ofac_guidance (lower priority)

Output: data/inbox/<filing-date>/<tier>/ofac_<date>_<slug>.json.

Usage:
    python -m src.ofac_poll                       # most recent 4 pages
    python -m src.ofac_poll --pages 10            # deeper backfill
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import date, datetime
from html import unescape
from pathlib import Path

try:
    import requests
except ImportError:
    print("Install requests: pip install requests", file=sys.stderr)
    sys.exit(1)

REPO = Path(__file__).resolve().parent.parent
INBOX = REPO / "data" / "inbox"
OFAC_RECENT = "https://ofac.treasury.gov/recent-actions"

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"),
    "Accept": "text/html,application/xhtml+xml",
}

# Classification patterns. Order matters (first match wins). The
# discriminating phrase is in OFAC's own title text.
TITLE_PATTERNS: list[tuple[str, str, str, str]] = [
    (r"\bgeneral license\b|\bissuance of\b.*\bgeneral license",
     "tier_s", "ofac_license_issuance",
     "OFAC General License issued — dated transaction window"),
    (r"\bdesignations? removals?\b|\bdelisted from the SDN\b|"
     r"\bdesignations? removal\b",
     "tier_s", "ofac_designation_removal",
     "OFAC SDN removal — previously-frozen exposure may now trade"),
    (r"\bcounter terrorism designations?\b",
     "red_flag", "ofac_designation_ct",
     "OFAC counter-terrorism designation — new SDN entries"),
    (r"\biran[- ]related (?:designations?|sanctions)\b",
     "red_flag", "ofac_designation_iran",
     "OFAC Iran-related designation"),
    (r"\brussia[- ]related (?:designations?|sanctions)\b",
     "red_flag", "ofac_designation_russia",
     "OFAC Russia-related designation"),
    (r"\bcuba (?:designations?|sanctions|frequently asked|faq)",
     "red_flag", "ofac_action_cuba",
     "OFAC Cuba-related action"),
    (r"\bvenezuela[- ]?related\b",
     "tier_s", "ofac_venezuela",
     "OFAC Venezuela-related action — energy-sector windows"),
    (r"\bnon[- ]proliferation\b",
     "red_flag", "ofac_nonproliferation",
     "OFAC non-proliferation designation"),
    (r"\b(?:designations?|sanctions)\b",
     "red_flag", "ofac_designation_other",
     "OFAC designation / sanctions update"),
    (r"\b(?:notice|guidance|faq|frequently asked)\b",
     "red_flag", "ofac_guidance",
     "OFAC notice / guidance — review for affected universe.md names"),
]
TITLE_PATTERNS_COMPILED = [(re.compile(p, re.I), t, s, n)
                           for p, t, s, n in TITLE_PATTERNS]

_RX_ITEM = re.compile(
    r'<a[^>]+href="(/recent-actions/(\d{8}))"[^>]*>([^<]+)</a>')


def fetch_page(page: int, retries: int = 3) -> str:
    url = f"{OFAC_RECENT}?page={page}"
    delay = 1.0
    for attempt in range(retries):
        try:
            r = requests.get(url, headers=HEADERS, timeout=30)
            r.raise_for_status()
            return r.text
        except requests.RequestException as exc:
            if attempt == retries - 1:
                print(f"  ! OFAC page {page} failed: {exc}", file=sys.stderr)
                return ""
            time.sleep(delay); delay *= 2
    return ""


def parse_page(html: str) -> list[dict]:
    """Each /recent-actions item: (yyyymmdd, title). Dedup by date."""
    seen: dict[str, str] = {}
    for href, yyyymmdd, txt in _RX_ITEM.findall(html):
        title = unescape(txt).strip()
        # OFAC sometimes lists the same date with multiple link blocks
        # (one per sub-action); take the longest title.
        if yyyymmdd not in seen or len(title) > len(seen[yyyymmdd]):
            seen[yyyymmdd] = title
    items: list[dict] = []
    for date_str, title in seen.items():
        try:
            d = date(int(date_str[0:4]), int(date_str[4:6]), int(date_str[6:8]))
        except ValueError:
            continue
        items.append({
            "date": d.isoformat(),
            "title": title,
            "url": f"https://ofac.treasury.gov/recent-actions/{date_str}",
        })
    return items


def classify(item: dict) -> tuple[str, str, str] | None:
    title = item.get("title", "")
    for pat, tier, sub, note in TITLE_PATTERNS_COMPILED:
        if pat.search(title):
            return tier, sub, note
    return None


def normalize_hit(item: dict, tier: str, sub: str, note: str,
                  fetched_at: str) -> dict:
    slug = re.sub(r"[^A-Za-z0-9_-]+", "_", item["title"])[:80]
    return {
        "tier":        tier,
        "query_label": f"{tier}.{sub}",
        "query_note":  note,
        "cik":         "",
        "ticker":      None,
        "isin":        None,
        "name":        item["title"][:200],
        "form":        "OFAC Recent Action",
        "form_code":   "OFAC",
        "accession":   f"ofac-{item['date'].replace('-', '')}-{slug[:30]}",
        "filed":       item["date"],
        "jurisdiction": "US-OFAC",
        "url":         item["url"],
        "source":      "OFAC",
        "fetched_at":  fetched_at,
    }


def write_inbox(records: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for r in records:
        filed = r.get("filed") or date.today().isoformat()
        tier_dir = INBOX / filed[:10] / r["tier"]
        tier_dir.mkdir(parents=True, exist_ok=True)
        slug = (r["accession"] or "no-id").replace("/", "_")
        path = tier_dir / f"ofac_{slug}.json"
        path.write_text(json.dumps(r, indent=2, sort_keys=True, default=str))
        key = f"{filed[:10]}/{r['tier']}"
        counts[key] = counts.get(key, 0) + 1
    return counts


def poll(pages: int = 4) -> int:
    fetched_at = datetime.utcnow().isoformat() + "Z"
    all_items: list[dict] = []
    print(f"Polling OFAC recent-actions ({pages} pages = ~{pages * 7} items)...")
    seen_dates: set[str] = set()
    for page in range(pages):
        html = fetch_page(page)
        if not html:
            break
        items = parse_page(html)
        new = [it for it in items if it["date"] not in seen_dates]
        seen_dates.update(it["date"] for it in new)
        all_items.extend(new)
        time.sleep(0.20)
    print(f"  {len(all_items)} unique action-date items retrieved")

    hits: list[dict] = []
    from collections import Counter
    classified: Counter[str] = Counter()
    for it in all_items:
        cls = classify(it)
        if cls is None:
            continue
        tier, sub, note = cls
        classified[sub] += 1
        hits.append(normalize_hit(it, tier, sub, note, fetched_at))
    print(f"  {len(hits)} matched a sanctions / GL pattern:")
    for sub, n in classified.most_common():
        print(f"    {sub:30s} {n}")

    if hits:
        counts = write_inbox(hits)
        for k, v in sorted(counts.items()):
            print(f"  {k}: {v}")
    return len(hits)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pages", type=int, default=4,
                    help="Number of pages to walk (default 4 = ~28 most "
                         "recent actions)")
    args = ap.parse_args()
    total = poll(args.pages)
    print(f"\nDone. {total} records.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
