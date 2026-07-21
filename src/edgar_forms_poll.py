#!/usr/bin/env python3
"""
edgar_forms_poll.py — multi-form EDGAR event poller (new opportunity categories).

Captures several special-situation categories the framework did not
previously source, all via EDGAR's form-type-indexed Atom feed
(getcurrent) — the same robust mechanic proven in sc13d_poll /
form15_poll. Low-volume, high-signal forms where the form TYPE is the
event:

  Proxy contests / activist solicitations  (tier_s.proxy_contest)
    DFAN14A  definitive additional soliciting material by a non-mgmt party
    DEFC14A  definitive proxy statement — contested
    PREC14A  preliminary proxy statement — contested
    DEFN14A  definitive proxy by a non-management person

  Merger / acquisition votes  (tier_s.merger_vote)  → merger arb
    DEFM14A  definitive merger proxy
    PREM14A  preliminary merger proxy

  Issuer self-tender / Dutch auction  (tier_s.self_tender)
    SC TO-I  issuer tender offer (buyback / going-private step)

  Delisting  (tier_s.delisting_form25)
    25-NSE   notification of removal from listing (the actual delisting
             event — complements the Item 3.01 deficiency early-warning
             and the Form 15 deregistration end-state)

  Accounting scrutiny  (red_flag.sec_comment_letter)
    UPLOAD   SEC staff comment letter
    CORRESP  issuer response to SEC staff

Output: data/inbox/<filing-date>/<tier>/edgarform_<accession>.json.

Usage:
    python -m src.edgar_forms_poll
    python -m src.edgar_forms_poll --count 100
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
    "EDGAR_USER_AGENT", "cyclepapa-screener research@example.com")
HEADERS = {"User-Agent": USER_AGENT,
           "Accept": "application/atom+xml,text/html"}

# form → (tier, sub_label, note)
FORM_MAP: dict[str, tuple[str, str, str]] = {
    "DFAN14A": ("tier_s", "proxy_contest",
                "DFAN14A — non-management soliciting material (activist "
                "proxy campaign in flight)"),
    "DEFC14A": ("tier_s", "proxy_contest",
                "DEFC14A — definitive CONTESTED proxy statement"),
    "PREC14A": ("tier_s", "proxy_contest",
                "PREC14A — preliminary contested proxy statement"),
    "DEFN14A": ("tier_s", "proxy_contest",
                "DEFN14A — definitive proxy by a non-management person"),
    "DEFM14A": ("tier_s", "merger_vote",
                "DEFM14A — definitive merger proxy (shareholder vote on "
                "a deal; merger-arb window)"),
    "PREM14A": ("tier_s", "merger_vote",
                "PREM14A — preliminary merger proxy"),
    "SC TO-I": ("tier_s", "self_tender",
                "SC TO-I — issuer self-tender / Dutch auction (buyback or "
                "going-private step)"),
    "25-NSE":  ("tier_s", "delisting_form25",
                "Form 25-NSE — notification of removal from listing (the "
                "delisting event itself)"),
    "8-A12B":  ("tier_s", "new_listing",
                "Form 8-A12B — registration of a class of securities for "
                "national-exchange (NYSE/Nasdaq) listing: a NEW listed "
                "equity appearing — post-reorg relisting, OTC→exchange "
                "uplisting, or spin-off/when-issued common. The mirror of "
                "the 25-NSE delisting signal, caught structurally rather "
                "than only when the emergence phrase happens to co-occur."),
    "8-A12G":  ("tier_s", "new_listing",
                "Form 8-A12G — registration of a class of securities under "
                "§12(g): a newly-reporting equity (often the OTC/relisting "
                "leg of a post-reorg or spin-off)."),
    "UPLOAD":  ("red_flag", "sec_comment_letter",
                "UPLOAD — SEC staff comment letter (accounting / disclosure "
                "scrutiny)"),
    "CORRESP": ("red_flag", "sec_comment_letter",
                "CORRESP — issuer response to SEC staff comment letter"),
}

_RX_ENTRY = re.compile(r"<entry>(.*?)</entry>", re.DOTALL)
_RX_TITLE = re.compile(r"<title>(.*?)</title>", re.DOTALL)
_RX_LINK = re.compile(r'<link[^>]+href="([^"]+)"')
_RX_SUMMARY = re.compile(r"<summary[^>]*>(.*?)</summary>", re.DOTALL)
_RX_FILED = re.compile(r"Filed:\s*(\d{4}-\d{2}-\d{2})")
_RX_ACCNO = re.compile(r"AccNo:\s*([\d-]+)")
# title format: "FORMTYPE - ISSUER NAME (CIK) (Role)". Split on the
# " - " SEPARATOR (space-hyphen-space) so form types with internal
# hyphens (25-NSE, SC TO-I) aren't mis-split. Capture the trailing role.
_RX_TITLE_PARTS = re.compile(
    r"^(.+?)\s+-\s+(.+?)\s*\((\d{6,10})\)\s*(?:\(([^)]+)\))?")


def fetch_atom(form: str, count: int, retries: int = 4) -> str:
    url = f"{EDGAR_ATOM}?" + urlencode({
        "action": "getcurrent", "type": form, "output": "atom",
        "count": count})
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
                print(f"  ! EDGAR {form} failed: {exc}", file=sys.stderr)
                return ""
            time.sleep(delay); delay *= 2
    return ""


def parse_entry(entry_xml: str, form: str) -> dict | None:
    title = _RX_TITLE.search(entry_xml)
    if not title:
        return None
    title_txt = unescape(title.group(1))
    parts = _RX_TITLE_PARTS.match(title_txt)
    if not parts:
        return None
    ftype, name, cik, role = parts.groups()
    ftype = ftype.strip()
    role = (role or "").strip().lower()
    # getcurrent may return amendments/variants; require the form prefix
    if form.upper() not in ftype.upper():
        return None
    # For delisting (25-NSE) and tender (SC TO-I/T) the exchange/bidder
    # files "by"; we want the SUBJECT company, not the filer.
    if role.startswith("filed by") or role.startswith("filer"):
        if form.upper() in ("25-NSE", "SC TO-I"):
            return None
    summary = _RX_SUMMARY.search(entry_xml)
    summary_txt = unescape(re.sub(r"<[^>]+>", "",
                                  summary.group(1))) if summary else ""
    filed = _RX_FILED.search(summary_txt)
    acc = _RX_ACCNO.search(summary_txt)
    link = _RX_LINK.search(entry_xml)
    return {
        "form": ftype.strip(),
        "name": name.strip(),
        "cik": cik,
        "filed": filed.group(1) if filed else "",
        "accession": acc.group(1) if acc else "",
        "url": link.group(1) if link else "",
    }


def normalize_hit(rec: dict, form_key: str, fetched_at: str) -> dict:
    tier, sub, note = FORM_MAP[form_key]
    return {
        "tier":        tier,
        "query_label": f"{tier}.{sub}",
        "query_note":  note,
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
        "source":      "EDGAR-forms",
        "fetched_at":  fetched_at,
    }


def write_inbox(records: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for r in records:
        filed = r.get("filed") or date.today().isoformat()
        tier_dir = INBOX / filed[:10] / r["tier"]
        tier_dir.mkdir(parents=True, exist_ok=True)
        slug = (r["accession"] or f"{r['cik']}-{r['filed']}").replace("/", "_")
        sub = r["query_label"].split(".")[-1]
        path = tier_dir / f"edgarform_{slug}_{sub}.json"
        path.write_text(json.dumps(r, indent=2, sort_keys=True, default=str))
        key = f"{filed[:10]}/{r['tier']}"
        counts[key] = counts.get(key, 0) + 1
    return counts


def poll(count: int) -> int:
    fetched_at = datetime.utcnow().isoformat() + "Z"
    all_records: list[dict] = []
    seen_acc: set[str] = set()
    print("Polling EDGAR form-type Atom feeds...")
    for form_key in FORM_MAP:
        atom = fetch_atom(form_key, count)
        kept = 0
        for entry in _RX_ENTRY.findall(atom):
            rec = parse_entry(entry, form_key)
            if not rec:
                continue
            acc = rec.get("accession", "")
            if acc and acc in seen_acc:
                continue
            seen_acc.add(acc)
            all_records.append(normalize_hit(rec, form_key, fetched_at))
            kept += 1
        print(f"  {form_key:10s} {kept:>4d} hits")
        time.sleep(0.20)
    if all_records:
        counts = write_inbox(all_records)
        print(f"\nWrote {len(all_records)} records across "
              f"{len(counts)} day/tier buckets")
    else:
        print("\nNo recent form-type hits.")
    return len(all_records)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--count", type=int, default=100)
    args = ap.parse_args()
    total = poll(args.count)
    print(f"\nDone. {total} records.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
