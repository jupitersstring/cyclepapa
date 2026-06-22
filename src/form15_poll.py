#!/usr/bin/env python3
"""
form15_poll.py — SEC Form 15 going-dark / deregistration poller.

Implements keeper #2 from output/process_improvements_keepers.md.

Form 15 filings (Forms 15-12B, 15-12G, 15-15D) trigger Section 12
deregistration. The issuer certifies under Rule 12g-4 that it has
< 300 holders (or < 500 with assets < $10m, or < 1,200 for banks).
Periodic-reporting obligations suspend *immediately* upon filing
(formal deregistration completes 90 days later). The stock typically
re-trades on the OTC Pink Sheet with a "PK" symbol suffix.

The trade setup: forced selling by SEC-registered-only mandates
creates a 30-90 day discount window. Combined with the typical
information asymmetry (filings stop, the business continues), post-
going-dark stubs occasionally trade at 50-70% of intrinsic value
until the issuer either re-emerges or is acquired (which is the
common outcome).

Atom getcurrent feed at /cgi-bin/browse-edgar — same pattern as
sc13d_poll.py. Form 15 volume is low (~50/quarter); the count=100
feed covers months.

Output: data/inbox/<filing-date>/tier_s/form15_<accession>.json
under sub-labels `tier_s.going_dark_12b`, `tier_s.going_dark_12g`,
`tier_s.going_dark_15d`.

Usage:
    python -m src.form15_poll
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from datetime import date, datetime
from html import unescape
from pathlib import Path
from urllib.parse import urlencode

try:
    import requests
except ImportError:
    print("Install requests: pip install requests", file=sys.stderr)
    sys.exit(1)

REPO = Path(__file__).resolve().parent.parent
INBOX = REPO / "data" / "inbox"
EDGAR_ATOM = "https://www.sec.gov/cgi-bin/browse-edgar"

USER_AGENT = os.environ.get(
    "EDGAR_USER_AGENT",
    "cyclepapa-screener research@example.com",
)
HEADERS = {"User-Agent": USER_AGENT,
           "Accept": "application/atom+xml,text/html"}

# Form 15-12B: termination of Section 12(b) registration (NYSE/Nasdaq-listed)
# Form 15-12G: termination of Section 12(g) registration (formerly-registered)
# Form 15-15D: termination of Section 15(d) registration (reporting-only)
FORM_QUERIES: dict[str, str] = {
    "tier_s.going_dark_12b": "15-12B",
    "tier_s.going_dark_12g": "15-12G",
    "tier_s.going_dark_15d": "15-15D",
}


def fetch_atom_feed(form: str, count: int = 100, retries: int = 4) -> str:
    url = (f"{EDGAR_ATOM}?" + urlencode({
        "action": "getcurrent", "type": form, "output": "atom",
        "count": count,
    }))
    delay = 1.0
    for attempt in range(retries):
        try:
            r = requests.get(url, headers=HEADERS, timeout=30)
            if r.status_code == 429:
                time.sleep(delay); delay *= 2
                continue
            r.raise_for_status()
            return r.text
        except requests.RequestException as exc:
            if attempt == retries - 1:
                print(f"  ! EDGAR Atom failed: {exc}", file=sys.stderr)
                return ""
            time.sleep(delay); delay *= 2
    return ""


_RX_ENTRY = re.compile(r"<entry>(.*?)</entry>", re.DOTALL)
_RX_TITLE = re.compile(r"<title>(.*?)</title>", re.DOTALL)
_RX_LINK = re.compile(r'<link[^>]+href="([^"]+)"')
_RX_SUMMARY = re.compile(r"<summary[^>]*>(.*?)</summary>", re.DOTALL)
_RX_FILED = re.compile(r"Filed:\s*(\d{4}-\d{2}-\d{2})")
_RX_ACCNO = re.compile(r"AccNo:\s*([\d-]+)")
_RX_FORM_TITLE = re.compile(
    r"^(15-\d{2}[BGD]/?A?)\s*-\s*(.+?)\s*\((\d+)\)")


def parse_atom_entry(entry_xml: str) -> dict | None:
    title = _RX_TITLE.search(entry_xml)
    if not title:
        return None
    title_txt = unescape(title.group(1))
    form_m = _RX_FORM_TITLE.match(title_txt)
    if not form_m:
        return None
    form, name, cik = form_m.groups()
    summary = _RX_SUMMARY.search(entry_xml)
    summary_txt = unescape(re.sub(r"<[^>]+>", "",
                                  summary.group(1))) if summary else ""
    filed = _RX_FILED.search(summary_txt)
    acc = _RX_ACCNO.search(summary_txt)
    link = _RX_LINK.search(entry_xml)
    return {
        "form": form.strip(),
        "name": name.strip(),
        "cik":  cik,
        "filed": filed.group(1) if filed else "",
        "accession": acc.group(1) if acc else "",
        "url":   link.group(1) if link else "",
    }


def normalize_hit(label: str, rec: dict, fetched_at: str) -> dict:
    form = rec.get("form", "")
    note = {
        "15-12B": ("Form 15-12B: termination of Section 12(b) listed-"
                   "exchange registration — exits NYSE/Nasdaq, expected "
                   "to move to OTC Pink Sheet"),
        "15-12G": ("Form 15-12G: termination of Section 12(g) "
                   "registration — held by < 300 record-holders (or "
                   "< 500 with assets < $10m); reporting suspends"),
        "15-15D": ("Form 15-15D: termination of Section 15(d) "
                   "registration — reporting-only deregistration"),
    }.get(form.split("/")[0],
          "Section 12 deregistration — periodic reporting suspends")
    note += (". Trade setup: 30-90 day forced-selling window from "
             "mandates that require SEC-registered status.")
    return {
        "tier":        "tier_s",
        "query_label": label,
        "query_note":  note,
        "cik":         rec.get("cik", ""),
        "ticker":      None,
        "isin":        None,
        "name":        rec.get("name", ""),
        "form":        form,
        "form_code":   form,
        "accession":   rec.get("accession", ""),
        "filed":       rec.get("filed", "") or date.today().isoformat(),
        "jurisdiction": "US",
        "url":         rec.get("url", ""),
        "source":      "EDGAR-Form15",
        "fetched_at":  fetched_at,
    }


def write_inbox(records: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for r in records:
        filed = r.get("filed") or date.today().isoformat()
        tier_dir = INBOX / filed[:10] / r["tier"]
        tier_dir.mkdir(parents=True, exist_ok=True)
        slug = (r["accession"] or f"{r['cik']}-{r['filed']}").replace("/", "_")
        path = tier_dir / f"form15_{slug}.json"
        path.write_text(json.dumps(r, indent=2, sort_keys=True, default=str))
        key = f"{filed[:10]}/{r['tier']}"
        counts[key] = counts.get(key, 0) + 1
    return counts


def poll() -> int:
    fetched_at = datetime.utcnow().isoformat() + "Z"
    all_records: list[dict] = []
    print("Polling EDGAR Atom feed for Form 15 going-dark filings...")
    for label, form in FORM_QUERIES.items():
        atom = fetch_atom_feed(form)
        entries = _RX_ENTRY.findall(atom)
        kept = 0
        for entry in entries:
            rec = parse_atom_entry(entry)
            if not rec:
                continue
            # Only keep filings whose form matches the requested type
            if not rec.get("form", "").startswith(form):
                continue
            all_records.append(normalize_hit(label, rec, fetched_at))
            kept += 1
        print(f"  {label:28s} {kept:>4d} hits  (form={form})")
        time.sleep(0.20)
    if all_records:
        counts = write_inbox(all_records)
        print(f"\nWrote {len(all_records)} records across "
              f"{len(counts)} day/tier buckets")
        for k, v in sorted(counts.items()):
            print(f"  {k}: {v}")
    else:
        print("\nNo recent Form 15 filings.")
    return len(all_records)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.parse_args()
    total = poll()
    print(f"\nDone. {total} records.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
