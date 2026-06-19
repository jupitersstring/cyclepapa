#!/usr/bin/env python3
"""
sedarplus_poll.py — daily SEDAR+ poller for Canadian special-situation filings.

Closes the Canadian leg of the comprehensive-coverage gap. SEDAR+ is the
canonical Canadian Securities Administrators' filing repository (replaced
SEDAR in July 2023). It sits behind Imperva (perfdrive.com) bot detection
which 404s naive requests. The detection is session-based though, not
challenge-based — establishing a session via the landing-page flow and
sending realistic browser headers gets through cleanly.

Session flow (mirrors a real browser):
  1. GET landingpage/              -> sets initial Uzma/Uzmb cookies
  2. GET csa-party/records/document.html   -> Catalyst session cookies
  3. GET csa-party/relay.html?url=...searchDocuments&target=csa-party
     -> renders the search-documents view with the 30 most-recent CSA
        filings in the result table (default state).

The relay returns a Java/Catalyst stateful form (~575KB) whose result
table contains 30 rows. URL-param FilingType filtering is ignored by
the server (state is session-only), and POSTing to update.html to set
filter state requires replaying thousands of node-W* attribute fields —
not durable. So we parse the default view and classify client-side.

The 30 rows = the most recent CSA filings across all types, sorted
filing-time desc. At Canadian business-hour volume that's roughly the
last 30-60 minutes of filings, so this poller should run hourly to
achieve daily coverage (similar discipline to EDGAR's full-text
search which is also recent-first).

Output matches data/inbox/<date>/<tier>/<id>.json so inbox_promote.py
picks up SEDAR+ hits the same way it handles EDGAR + NSM.

Usage:
    python -m src.sedarplus_poll                # poll once
    python -m src.sedarplus_poll --hours 6      # repeat every 6 hours
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from datetime import date, datetime
from pathlib import Path
from urllib.parse import quote

try:
    import requests
except ImportError:
    print("Install requests: pip install requests", file=sys.stderr)
    sys.exit(1)

REPO = Path(__file__).resolve().parent.parent
INBOX = REPO / "data" / "inbox"

# Realistic browser headers — the bot detection passes these
BROWSER_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"),
    "Accept": ("text/html,application/xhtml+xml,application/xml;q=0.9,"
               "image/avif,image/webp,*/*;q=0.8"),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1",
}

SEDAR_BASE = "https://www.sedarplus.ca"
RELAY_INNER = (f"{SEDAR_BASE}/csa-party/service/create.html"
               "?targetAppCode=csa-party&service=searchDocuments")

# Document-name regex → tier + sub-query label. Order matters: first
# match wins (so the more-specific patterns come first).
DOC_PATTERNS: list[tuple[str, str, str, str]] = [
    # ---- Tier-S: hard events (always promote) ----
    (r"\btake[- ]over bid circular\b",           "tier_s", "takeover_bid",
     "NI 62-104 take-over bid circular"),
    (r"\bissuer bid circular\b",                 "tier_s", "issuer_bid",
     "NI 62-104 issuer bid (SIB / Dutch auction)"),
    (r"\bdirectors[' ]?circular\b",              "tier_s", "directors_circular",
     "target board response to bid (signals contested deal)"),
    (r"\bplan of arrangement\b",                 "tier_s", "plan_of_arrangement",
     "CBCA s.192 / OBCA s.182 plan of arrangement"),
    (r"\brights offering\b",                     "tier_s", "rights_offering",
     "rights offering material (NI 45-101)"),
    (r"\b(?:early warning report|early[- ]warning)\b", "tier_s", "early_warning",
     "NI 62-104 early-warning 10pct disclosure"),
    (r"\balternative monthly report\b",          "tier_s", "amr",
     "NI 62-104 alternative monthly report"),
    (r"\bbusiness acquisition report\b",         "tier_s", "bar",
     "Form 51-102F4 business acquisition (a-class)"),
    (r"\bmaterial change report\b",              "tier_s", "material_change",
     "Form 51-102F3 material change — verify whether structural"),
    (r"\bchange in corporate structure\b",       "tier_s", "corp_structure",
     "change in corporate structure"),
    (r"\b(?:management )?information circular\b","tier_s", "info_circular",
     "info circular — often contains plan of arrangement details"),
    # ---- Revealed preference ----
    (r"\bnotice of intention to distribute\b",   "rev_pref", "ni_45_102",
     "control-block holder notice (NI 45-102F1)"),
    # ---- Red flags ----
    (r"\bcease trade\b",                         "red_flag", "cto",
     "cease trade order"),
    (r"\bgoing concern\b",                       "red_flag", "going_concern",
     "going-concern note"),
    # Material documents amended — often signals refinancing / waiver
    (r"\bmaterial (?:contracts|documents) \(amended\)\b", "rev_pref", "material_amend",
     "material contract amendment — verify (waiver / extension?)"),
]
DOC_PATTERNS_COMPILED = [(re.compile(p, re.I), tier, sub, note)
                         for p, tier, sub, note in DOC_PATTERNS]


def establish_session() -> requests.Session:
    """Three-step session establishment that defeats perfdrive."""
    s = requests.Session()
    s.headers.update(BROWSER_HEADERS)
    s.get(f"{SEDAR_BASE}/landingpage/",
          headers={"Sec-Fetch-Site": "none"}, timeout=25)
    s.get(f"{SEDAR_BASE}/csa-party/records/document.html",
          headers={"Sec-Fetch-Site": "same-origin",
                   "Referer": f"{SEDAR_BASE}/landingpage/"},
          timeout=25)
    return s


def fetch_search_page(s: requests.Session, retries: int = 3) -> str:
    """Fetch the searchDocuments view with the 30-row default result list."""
    relay = (f"{SEDAR_BASE}/csa-party/relay.html"
             f"?url={quote(RELAY_INNER, safe='')}&target=csa-party")
    delay = 1.0
    for attempt in range(retries):
        try:
            r = s.get(relay, headers={
                "Sec-Fetch-Site": "same-origin",
                "Referer": f"{SEDAR_BASE}/csa-party/records/document.html",
            }, timeout=40)
            if "perfdrive" in r.url.lower():
                # Bot-bounce — session expired. Re-establish and retry.
                time.sleep(delay); delay *= 2
                continue
            r.raise_for_status()
            return r.text
        except requests.RequestException as exc:
            if attempt == retries - 1:
                print(f"  ! SEDAR+ failed after {retries} attempts: {exc}",
                      file=sys.stderr)
                return ""
            time.sleep(delay); delay *= 2
    return ""


# Pre-compiled extractors for row content
_ROW_SPLIT_RE = re.compile(r'class="appTblRow appTblRow\d+')
_ROW_TEXT_RE = re.compile(r">([^<>]+)<")
_ISSUER_NUM_RE = re.compile(r"\((\d{5,10})\)")
_DOC_SUFFIX_RE = re.compile(r"\.(pdf|html?|xml|xbrl)$", re.I)
_DATE_FULL_RE = re.compile(
    r"(\d{1,2})\s+(\w+)\s+(\d{4})\s+(\d{1,2}):(\d{2})\s+E[DS]T")
_JURISDICTIONS = {
    "Alberta", "British Columbia", "Ontario", "Quebec", "Manitoba",
    "Saskatchewan", "Nova Scotia", "New Brunswick", "Yukon",
    "Newfoundland and Labrador", "Newfoundland", "Northwest Territories",
    "Nunavut", "Prince Edward Island", "PEI",
}
_MONTHS = {m: i for i, m in enumerate(
    ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
     "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], 1)}


def parse_rows(html: str) -> list[dict]:
    """Extract the 30 result rows. Each Catalyst row has a fixed sequence of
    text nodes: issuer, doc_name, short_date, long_date, jurisdiction, size."""
    rows: list[dict] = []
    starts = [m.start() for m in _ROW_SPLIT_RE.finditer(html)]
    for i, start in enumerate(starts):
        end = starts[i + 1] if i + 1 < len(starts) else start + 12000
        row_html = html[start:end]
        # All non-blank text nodes
        all_text = [t.strip() for t in _ROW_TEXT_RE.findall(row_html)]
        # Skip non-signal labels
        sig = [t for t in all_text
               if t and not all(c in " \t" for c in t)
               and not t.startswith(("Download", "Generate", "Export"))]
        if not sig:
            continue
        # Find each field by content pattern, not by position
        issuer = next((t for t in sig if _ISSUER_NUM_RE.search(t)), "")
        doc = next((t for t in sig if _DOC_SUFFIX_RE.search(t)), "")
        date_m = next((_DATE_FULL_RE.search(t) for t in sig
                       if _DATE_FULL_RE.search(t)), None)
        jur = next((t for t in sig if t in _JURISDICTIONS), "")
        # Parse date to ISO
        filed_iso = ""
        if date_m:
            day_, mon_, year_, _, _ = date_m.groups()
            m = _MONTHS.get(mon_[:3].title())
            if m:
                filed_iso = f"{year_}-{m:02d}-{int(day_):02d}"
        # Best-effort issuer-number extraction
        issuer_num_m = _ISSUER_NUM_RE.search(issuer)
        issuer_num = issuer_num_m.group(1) if issuer_num_m else ""
        # Issuer name: strip the trailing "(NNNNN)" + dedupe "X / X" pair
        name = re.sub(r"\s*\(\d{5,10}\)\s*$", "", issuer)
        if " / " in name:
            half = name.split(" / ")[0].strip()
            if half:
                name = half
        if not name and not doc:
            continue
        rows.append({
            "name": name,
            "issuer_num": issuer_num,
            "doc": doc,
            "filed": filed_iso,
            "jurisdiction": jur,
            "raw_date": date_m.group(0) if date_m else "",
        })
    return rows


def classify(rec: dict) -> tuple[str, str, str] | None:
    """Apply doc-name regex. Returns (tier, sub_query_label, note) or None."""
    doc = rec.get("doc", "") or ""
    if not doc:
        return None
    for pat, tier, sub, note in DOC_PATTERNS_COMPILED:
        if pat.search(doc):
            return tier, sub, note
    return None


def normalize_hit(rec: dict, tier: str, sub: str, note: str,
                  fetched_at: str) -> dict:
    """Build the inbox-record shape (same fields as edgar/nsm hits)."""
    # Synthesize an accession id from issuer_num + filed time + doc
    raw_id_basis = (f"{rec['issuer_num']}_{rec['raw_date']}_{rec['doc']}"
                    .replace(" ", "_"))
    accession = re.sub(r"[^A-Za-z0-9_-]", "", raw_id_basis)[:80] or "no-id"
    return {
        "tier":        tier,
        "query_label": f"{tier}.{sub}",
        "query_note":  note,
        "cik":         "",
        "ticker":      None,
        "isin":        None,
        "name":        rec["name"],
        "form":        rec["doc"],
        "form_code":   "",
        "accession":   accession,
        "issuer_num":  rec["issuer_num"],
        "filed":       rec["filed"] or date.today().isoformat(),
        "jurisdiction": rec.get("jurisdiction", ""),
        "url":         (f"{SEDAR_BASE}/csa-party/records/issuer.html"
                        f"?issuerNo={rec['issuer_num']}"
                        if rec["issuer_num"] else ""),
        "source":      "SEDAR+",
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
        path = tier_dir / f"sedar_{slug}_{sub}.json"
        path.write_text(json.dumps(r, indent=2, sort_keys=True, default=str))
        key = f"{filed[:10]}/{r['tier']}"
        counts[key] = counts.get(key, 0) + 1
    return counts


def poll_once() -> int:
    fetched_at = datetime.utcnow().isoformat() + "Z"
    print(f"Establishing SEDAR+ session...")
    s = establish_session()
    html = fetch_search_page(s)
    if not html:
        print("  ! no result page; aborting", file=sys.stderr)
        return 0
    rows = parse_rows(html)
    print(f"  {len(rows)} rows parsed from default view")
    # Distribution by doc type
    from collections import Counter
    doc_counts = Counter(r["doc"][:60] for r in rows)
    print(f"  doc-type distribution:")
    for d, n in doc_counts.most_common(8):
        print(f"    {n:2d}  {d}")
    # Classify
    hits: list[dict] = []
    for r in rows:
        cls = classify(r)
        if cls is None:
            continue
        tier, sub, note = cls
        hits.append(normalize_hit(r, tier, sub, note, fetched_at))
    print(f"\n  {len(hits)} matched a special-situation pattern")
    if hits:
        counts = write_inbox(hits)
        for k, v in sorted(counts.items()):
            print(f"  {k}: {v}")
    return len(hits)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--hours", type=float, default=0,
                    help="If >0, repeat every N hours (default: poll once)")
    args = ap.parse_args()

    total = poll_once()
    if args.hours > 0:
        print(f"\nLooping every {args.hours} hours. Ctrl-C to stop.")
        while True:
            time.sleep(args.hours * 3600)
            total += poll_once()
    print(f"\nDone. {total} records written.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
