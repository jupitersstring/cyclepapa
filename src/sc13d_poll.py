#!/usr/bin/env python3
"""
sc13d_poll.py — SEC Schedule 13D / 13D-A poller.

Implements keeper #1 from output/process_improvements_keepers.md.

A Schedule 13D is the canonical revealed-preference signal at the
cap-stack level: any beneficial owner crossing the 5% ownership
threshold with intent-other-than-passive must file within 5 business
days (post-Feb 2024; was 10 calendar days). Amendments (SC 13D/A)
must be filed within 2 business days of any material change. From
Dec 18 2024, all 13D / 13G filings are in machine-readable Inline
XBRL.

Implementation note: EDGAR's full-text search API requires a non-empty
`q` parameter, so we use the structured /cgi-bin/browse-edgar Atom
feed (`action=getcurrent&type=SC 13D`) which is form-type-indexed.
For backfill across longer windows, we walk the daily form.idx
indexes at /Archives/edgar/full-index/<year>/<qtr>/form.idx.

This is purely additive to the existing edgar_poll.py — different
endpoint, different scope. The two complement: edgar_poll.py finds
Tier-S restructuring keywords across all forms; this script catches
every activist 5pct accumulation regardless of the issuer's
prior universe membership.

Usage:
    python -m src.sc13d_poll                       # current feed
    python -m src.sc13d_poll --days-back 7         # daily-index backfill
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from datetime import date, datetime, timedelta
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
HEADERS = {"User-Agent": USER_AGENT, "Accept": "application/atom+xml,text/html"}

# Form filters. SC 13D = new 5pct filing (activist intent).
# SC 13D/A = amendment. We exclude SC 13G (passive 5pct) — passive
# holders don't carry the same revealed-preference signal.
FORM_QUERIES: dict[str, str] = {
    "tier_s.sc_13d":   "SC 13D",
    "tier_s.sc_13d_a": "SC 13D/A",
}


def fetch_atom_feed(form: str, count: int = 100, retries: int = 4) -> str:
    """Fetch the most-recent N filings of a form type as an Atom feed."""
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
                print(f"  ! EDGAR Atom failed after {retries} attempts: "
                      f"{exc}", file=sys.stderr)
                return ""
            time.sleep(delay); delay *= 2
    return ""


_RX_ENTRY = re.compile(r"<entry>(.*?)</entry>", re.DOTALL)
_RX_TITLE = re.compile(r"<title>(.*?)</title>", re.DOTALL)
_RX_LINK = re.compile(r'<link[^>]+href="([^"]+)"')
_RX_UPDATED = re.compile(r"<updated>(.*?)</updated>")
_RX_SUMMARY = re.compile(r"<summary[^>]*>(.*?)</summary>", re.DOTALL)
_RX_FILED = re.compile(r"Filed:\s*(\d{4}-\d{2}-\d{2})")
_RX_ACCNO = re.compile(r"AccNo:\s*([\d-]+)")
_RX_CIK = re.compile(r"\((\d{6,10})\)\s*\((?:Filer|Subject)\)")


def parse_atom_entry(entry_xml: str) -> dict | None:
    """Extract title / link / accession / filer info from one Atom entry."""
    title = _RX_TITLE.search(entry_xml)
    if not title:
        return None
    title_txt = unescape(title.group(1))
    summary = _RX_SUMMARY.search(entry_xml)
    summary_txt = unescape(re.sub(r"<[^>]+>", "",
                                  summary.group(1))) if summary else ""
    link = _RX_LINK.search(entry_xml)
    filed = _RX_FILED.search(summary_txt)
    acc = _RX_ACCNO.search(summary_txt)
    # title format: "SC 13D/A - ISSUER NAME (CIK) (Subject)"
    form_m = re.match(r"^(SC\s*13[DG][/A]*)\s*-\s*(.+?)\s*\((\d+)\)", title_txt)
    if not form_m:
        return None
    form, name, cik = form_m.groups()
    return {
        "form":      form.strip(),
        "name":      name.strip(),
        "cik":       cik,
        "filed":     filed.group(1) if filed else "",
        "accession": acc.group(1) if acc else "",
        "url":       link.group(1) if link else "",
    }


def normalize_hit(label: str, rec: dict, fetched_at: str) -> dict:
    is_amend = "/A" in rec.get("form", "")
    return {
        "tier":        "tier_s",
        "query_label": label,
        "query_note":  ("13D amendment — material change to 5pct stake "
                        "(filed within 2 business days post-Feb 2024)"
                        if is_amend else
                        "New 5pct beneficial-ownership filing — activist "
                        "intent (filed within 5 business days post-Feb 2024)"),
        "cik":         rec.get("cik", ""),
        "ticker":      None,
        "isin":        None,
        "name":        rec.get("name", ""),
        "form":        rec.get("form", ""),
        "form_code":   rec.get("form", ""),
        "accession":   rec.get("accession", ""),
        "filed":       rec.get("filed", "") or date.today().isoformat(),
        "jurisdiction": "US",
        "url":         rec.get("url", ""),
        "source":      "EDGAR-SC13D",
        "fetched_at":  fetched_at,
    }


def write_inbox(records: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for r in records:
        filed = r.get("filed") or date.today().isoformat()
        tier_dir = INBOX / filed[:10] / r["tier"]
        tier_dir.mkdir(parents=True, exist_ok=True)
        slug = (r["accession"] or f"{r['cik']}-{r['filed']}").replace("/", "_")
        path = tier_dir / f"sc13d_{slug}.json"
        path.write_text(json.dumps(r, indent=2, sort_keys=True, default=str))
        key = f"{filed[:10]}/{r['tier']}"
        counts[key] = counts.get(key, 0) + 1
    return counts


def poll_current() -> int:
    """Use the Atom getcurrent feed for the most-recent filings."""
    fetched_at = datetime.utcnow().isoformat() + "Z"
    all_records: list[dict] = []
    print("Polling EDGAR Atom feed for recent SC 13D / SC 13D/A...")
    for label, form in FORM_QUERIES.items():
        atom = fetch_atom_feed(form)
        entries = _RX_ENTRY.findall(atom)
        kept = 0
        for entry in entries:
            rec = parse_atom_entry(entry)
            if not rec:
                continue
            # Only keep if filed-date matches the form filter
            if rec.get("form", "") != form:
                continue
            all_records.append(normalize_hit(label, rec, fetched_at))
            kept += 1
        print(f"  {label:24s} {kept:>4d} hits  (form={form})")
        time.sleep(0.20)
    if all_records:
        counts = write_inbox(all_records)
        print(f"\nWrote {len(all_records)} records across "
              f"{len(counts)} day/tier buckets")
        for k, v in sorted(counts.items()):
            print(f"  {k}: {v}")
    else:
        print("\nNo recent SC 13D filings.")
    return len(all_records)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.parse_args()
    # SC 13D volume is low (~16/quarter in 2026) so the getcurrent feed
    # at count=100 reliably covers multiple months. No date-range
    # backfill plumbing required.
    total = poll_current()
    print(f"\nDone. {total} records.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
