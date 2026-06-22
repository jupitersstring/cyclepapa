#!/usr/bin/env python3
"""
lobbying_poll.py — US Senate LDA (Lobbying Disclosure Act) poller.

Implements keeper #7 from output/process_improvements_keepers.md.

The Senate maintains a documented JSON API at lda.senate.gov/api/v1/
that returns ~30k disclosure filings per year — each lobbying
registration (RR) and quarterly report (Q1-Q4) by every registered
lobbyist on behalf of every paying client. Issue-code-tagged with
"Budget/Appropriations", "Banking", "Energy/Nuclear", etc.

Signal: when a target issuer hires lobbyists on a policy area that
affects their own restructuring (e.g. a uranium issuer registering on
"Energy/Nuclear", or a bank registering on "Banking"), it's a pre-
anchor signal 1-3 quarters ahead of the actual policy event (loan
term sheet, regulatory clearance, etc.). Particularly valuable for
A2 sovereign-industrial-policy archetypes.

Filter:
- Last 7 days of filings (default)
- General-issue codes in the SPECIAL_SITS_ISSUES allow-list
- OR client name fuzzy-matches a universe.md ticker stem

Output: data/inbox/<filing-date>/rev_pref/lobbying_<uuid>.json.

Usage:
    python -m src.lobbying_poll                    # last 7 days
    python -m src.lobbying_poll --days-back 30
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path

try:
    import requests
except ImportError:
    print("Install requests: pip install requests", file=sys.stderr)
    sys.exit(1)

REPO = Path(__file__).resolve().parent.parent
INBOX = REPO / "data" / "inbox"
UNIVERSE_MD = REPO / "universe.md"

API_BASE = "https://lda.senate.gov/api/v1/filings/"
HEADERS = {
    "User-Agent": "cyclepapa-screener research@example.com",
    "Accept": "application/json",
}

# General issue codes that map to our archetypes. Filings tagged with
# these codes generate inbox records regardless of universe match.
SPECIAL_SITS_ISSUES = {
    "Energy/Nuclear",          # uranium, lithium, critical minerals (A2)
    "Banking",                 # bank restructurings (A1/H)
    "Bankruptcy",              # any debtor disclosure
    "Foreign Relations",       # sanctions / OFAC adjacent
    "Trade",                   # CFIUS / tariff-related
    "Manufacturing",           # industrial policy (A2)
    "Defense",                 # DoD industrial policy (A2)
    "Pharmaceuticals/Health Products",  # specialty pharma restructuring
    "Telecommunications",      # FCC spectrum / restructurings
    "Transportation",          # airline / shipping restructurings
    "Aerospace",
    "Mining/Natural Resources",
    "Utilities",
}

# Sub-query mapping for inbox classification
ISSUE_TO_SUB = {
    "Energy/Nuclear":     "lobbying_energy",
    "Banking":            "lobbying_banking",
    "Bankruptcy":         "lobbying_bankruptcy",
    "Foreign Relations":  "lobbying_sanctions",
    "Trade":              "lobbying_trade",
    "Manufacturing":      "lobbying_industrial",
    "Defense":            "lobbying_defense",
    "Pharmaceuticals/Health Products": "lobbying_pharma",
    "Telecommunications": "lobbying_telecom",
    "Transportation":     "lobbying_transport",
    "Aerospace":          "lobbying_aerospace",
    "Mining/Natural Resources": "lobbying_mining",
    "Utilities":          "lobbying_utilities",
}


def fetch_page(filing_year: int, ordering: str = "-dt_posted",
               page: int = 1, page_size: int = 100,
               retries: int = 3) -> dict:
    params = {
        "filing_year": filing_year,
        "ordering": ordering,
        "page": page,
        "page_size": page_size,
    }
    delay = 1.0
    for attempt in range(retries):
        try:
            r = requests.get(API_BASE, params=params, headers=HEADERS,
                             timeout=30)
            if r.status_code == 429:
                time.sleep(delay); delay *= 2
                continue
            r.raise_for_status()
            return r.json()
        except requests.RequestException as exc:
            if attempt == retries - 1:
                print(f"  ! LDA page {page} failed: {exc}", file=sys.stderr)
                return {}
            time.sleep(delay); delay *= 2
    return {}


def load_universe_name_stems() -> set[str]:
    """Pull ticker + name stems from universe.md for client cross-ref."""
    out: set[str] = set()
    if not UNIVERSE_MD.exists():
        return out
    text = UNIVERSE_MD.read_text()
    # Match rows: | Name | Ticker | ...
    for line in text.splitlines():
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) < 2:
            continue
        name, ticker = cells[0], cells[1]
        if name and name.lower() != "name":
            first_word = re.sub(r"[^A-Za-z0-9]", "",
                                name.split()[0] if name else "").upper()
            if len(first_word) >= 4:
                out.add(first_word)
        if ticker and ":" in ticker:
            stem = re.sub(r"[^A-Za-z0-9]", "",
                          ticker.split(":")[-1]).upper()
            if len(stem) >= 2:
                out.add(stem)
    return out


def fuzzy_match_client(client_name: str, stems: set[str]) -> str | None:
    """Return matched stem if client_name's first word is in universe stems."""
    if not client_name:
        return None
    first = re.sub(r"[^A-Za-z0-9]", "",
                   client_name.split()[0] if client_name else "").upper()
    if first and first in stems:
        return first
    # Also try full-name token match
    for token in re.findall(r"\b[A-Z][A-Z0-9]{3,}\b", client_name.upper()):
        if token in stems:
            return token
    return None


def normalize_filing(filing: dict, fetched_at: str,
                     universe_match: str | None = None) -> dict:
    client = (filing.get("client") or {})
    client_name = client.get("name", "") or ""
    registrant = (filing.get("registrant") or {})
    activities = filing.get("lobbying_activities") or []
    issue_codes = [a.get("general_issue_code_display", "")
                   for a in activities]
    issues_text = " · ".join(c for c in issue_codes if c)[:200]
    # Pick the FIRST matching issue for sub-query
    sub = None
    note = ""
    for code in issue_codes:
        if code in ISSUE_TO_SUB:
            sub = ISSUE_TO_SUB[code]
            note = (f"LDA filing — {client_name[:60]} engaged "
                    f"{registrant.get('name','?')[:40]} for "
                    f"{code} ({filing.get('filing_period_display','')})")
            break
    if sub is None:
        # If we matched by universe name but not issue, default
        sub = "lobbying_universe_match"
        note = (f"LDA filing — {client_name[:60]} engaged "
                f"{registrant.get('name','?')[:40]} on "
                f"{issues_text[:80]} (universe-name match: "
                f"{universe_match or '?'})")

    income = filing.get("income")
    expenses = filing.get("expenses")
    filed_iso = (filing.get("dt_posted") or "")[:10]

    return {
        "tier":        "rev_pref",
        "query_label": f"rev_pref.{sub}",
        "query_note":  note,
        "cik":         "",
        "ticker":      None,
        "isin":        None,
        "name":        client_name,
        "form":        filing.get("filing_type_display", ""),
        "form_code":   filing.get("filing_type", ""),
        "accession":   filing.get("filing_uuid", ""),
        "filed":       filed_iso or date.today().isoformat(),
        "jurisdiction": "US",
        "url":         filing.get("filing_document_url", ""),
        "income":      income,
        "expenses":    expenses,
        "issues":      issues_text,
        "registrant":  registrant.get("name", "")[:120],
        "universe_match": universe_match,
        "source":      "LDA-Senate",
        "fetched_at":  fetched_at,
    }


def write_inbox(records: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for r in records:
        filed = r.get("filed") or date.today().isoformat()
        tier_dir = INBOX / filed[:10] / r["tier"]
        tier_dir.mkdir(parents=True, exist_ok=True)
        slug = (r["accession"] or "no-id").replace("/", "_")[:60]
        path = tier_dir / f"lobbying_{slug}.json"
        path.write_text(json.dumps(r, indent=2, sort_keys=True, default=str))
        key = f"{filed[:10]}/{r['tier']}"
        counts[key] = counts.get(key, 0) + 1
    return counts


def poll(days_back: int) -> int:
    fetched_at = datetime.utcnow().isoformat() + "Z"
    cutoff = datetime.utcnow().date() - timedelta(days=days_back)
    print(f"Polling Senate LDA for filings posted >= {cutoff.isoformat()}...")

    stems = load_universe_name_stems()
    print(f"  {len(stems)} universe name/ticker stems for cross-reference")

    matched: list[dict] = []
    page = 1
    seen_past_cutoff = False
    while not seen_past_cutoff and page <= 20:    # safety cap
        resp = fetch_page(filing_year=cutoff.year, page=page, page_size=100)
        results = (resp or {}).get("results") or []
        if not results:
            break
        for filing in results:
            posted_iso = (filing.get("dt_posted") or "")[:10]
            try:
                posted_d = date.fromisoformat(posted_iso) if posted_iso else None
            except ValueError:
                posted_d = None
            if posted_d and posted_d < cutoff:
                seen_past_cutoff = True
                break

            activities = filing.get("lobbying_activities") or []
            issue_codes = {a.get("general_issue_code_display", "")
                           for a in activities}
            in_issue_filter = bool(issue_codes & SPECIAL_SITS_ISSUES)

            client_name = (filing.get("client") or {}).get("name", "")
            universe_match = fuzzy_match_client(client_name, stems)

            if in_issue_filter or universe_match:
                rec = normalize_filing(filing, fetched_at, universe_match)
                matched.append(rec)
        page += 1
        time.sleep(0.20)

    print(f"  {len(matched)} filings matched issue filter or universe name")
    if matched:
        counts = write_inbox(matched)
        for k, v in sorted(counts.items()):
            print(f"  {k}: {v}")
    return len(matched)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--days-back", type=int, default=7)
    args = ap.parse_args()
    total = poll(args.days_back)
    print(f"\nDone. {total} records.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
