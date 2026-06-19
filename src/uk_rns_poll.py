#!/usr/bin/env python3
"""
uk_rns_poll.py — daily FCA NSM poller for UK special-situation RNS hits.

Closes the UK leg of the comprehensive-coverage gap. The framework's
discovery pipeline previously polled only EDGAR (US filings), leaving
LSE/AIM names invisible until hand-curated into universe.md.

The FCA's National Storage Mechanism (NSM) is the canonical regulatory
storage for all UK regulated announcements (DTR 6.3 mandated). The
SPA at data.fca.org.uk is a thin shell over an Elasticsearch-backed
proxy at api.data.fca.org.uk/search. We exploit the same back-end,
using the SPA's documented criteriaObj DSL.

Headline phrases below map 1:1 to canonical RNS announcement headlines.
Filter is a case-insensitive headline-substring match (the same filter
used by the FCA SPA), so hits are precise.

Output schema matches data/inbox/<date>/<tier>/<id>.json so that
inbox_promote.py promotes UK hits the same way it promotes EDGAR hits.

Usage:
    python -m src.uk_rns_poll                     # poll today
    python -m src.uk_rns_poll --date 2026-05-15   # backfill one day
    python -m src.uk_rns_poll --days-back 7       # backfill last week
"""

from __future__ import annotations

import argparse
import json
import os
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
NSM_API = "https://api.data.fca.org.uk/search"
NSM_INDEX = "fca-nsm-searchdata"
PAGE_SIZE = 100   # NSM max per page is 1000; 100 keeps memory + latency tidy

USER_AGENT = os.environ.get(
    "NSM_USER_AGENT",
    "cyclepapa-screener research@example.com",
)

# Canonical RNS headlines → (tier, sub_query, note).
# Source: FCA Disclosure Guidance & Transparency Rules (DTR), City Code
# on Takeovers and Mergers, Listing Rules (LR), Companies Act 2006 Part 26 / 26A.
QUERIES: dict[str, dict] = {
    # ---- Tier-S: hard events (always promote) ----
    "tier_s.scheme":           {"headline": "scheme of arrangement",
                                "note": "Companies Act Part 26 scheme"},
    "tier_s.rule_2_7":         {"headline": "rule 2.7 announcement",
                                "note": "City Code firm-intention takeover offer"},
    "tier_s.recommended_offer":{"headline": "recommended cash offer",
                                "note": "agreed takeover"},
    "tier_s.rights_offering":  {"headline": "rights issue",
                                "note": "rights issue (UK)"},
    "tier_s.open_offer":       {"headline": "open offer",
                                "note": "open offer / placing+open"},
    "tier_s.restructuring":    {"headline": "restructuring plan",
                                "note": "Companies Act Part 26A plan"},
    "tier_s.exchange_offer":   {"headline": "exchange offer",
                                "note": "debt exchange offer"},
    "tier_s.tender":           {"headline": "tender offer",
                                "note": "tender offer"},
    "tier_s.consent_solicitation": {"headline": "consent solicitation",
                                    "note": "noteholder consent solicitation"},
    # ---- Tier-S early signals (still promote: Metro-style early entry) ----
    "tier_s.rule_2_4":         {"headline": "rule 2.4 announcement",
                                "note": "City Code possible-offer / PUSU clock starts"},
    "tier_s.strategic_review": {"headline": "strategic review",
                                "note": "pre-event signal; Klarman entry zone"},
    # ---- Tier-S distress events ----
    "tier_s.administration":   {"headline": "notice of intention to appoint administrators",
                                "note": "pre-pack / administration NIA"},
    "tier_s.administrators":   {"headline": "appointment of administrators",
                                "note": "administration filed"},
    "tier_s.cva":              {"headline": "company voluntary arrangement",
                                "note": "CVA proposed"},
    "tier_s.suspension":       {"headline": "suspension of listing",
                                "note": "Official List suspension"},
    "tier_s.cancellation":     {"headline": "cancellation of admission",
                                "note": "delisting / AIM cancellation"},
    # ---- Tier-B: revealed-preference cluster signals ----
    "rev_pref.pdmr_dealing":   {"headline": "director/pdmr shareholding",
                                "note": "UK insider transaction (Lakonishok-Lee analogue)"},
    "rev_pref.holdings":       {"headline": "holding(s) in company",
                                "note": "3pct holding disclosure under DTR 5"},
    "rev_pref.form_8_3":       {"headline": "form 8.3",
                                "note": "City Code disclosure of dealings in offer period"},
    # ---- Red flags ----
    "red_flag.going_concern":  {"headline": "going concern",
                                "note": "going-concern note"},
    "red_flag.profit_warning": {"headline": "trading update",
                                "note": "UK trading update — verify whether profit warning"},
}


def nsm_search(headline: str, from_offset: int = 0, size: int = PAGE_SIZE,
               retries: int = 4) -> dict:
    """Run one paged search against the FCA NSM Elasticsearch proxy."""
    body = {
        "from": from_offset,
        "size": size,
        "sort": "publication_date",
        "sortorder": "desc",
        "keyword": None,
        "criteriaObj": {
            "criteria": [
                {"name": "headline", "value": headline},
                {"name": "source",   "value": "RNS"},
            ],
        },
    }
    headers = {
        "User-Agent": USER_AGENT,
        "Content-Type": "application/json",
    }
    delay = 1.0
    for attempt in range(retries):
        try:
            r = requests.post(NSM_API, params={"index": NSM_INDEX},
                              headers=headers, data=json.dumps(body),
                              timeout=30)
            if r.status_code == 429:
                time.sleep(delay)
                delay *= 2
                continue
            r.raise_for_status()
            return r.json()
        except requests.RequestException as exc:
            if attempt == retries - 1:
                print(f"  ! NSM failed after {retries} attempts: {exc}",
                      file=sys.stderr)
                return {}
            time.sleep(delay)
            delay *= 2
    return {}


def normalize_hit(label: str, hit: dict, query_note: str,
                  fetched_at: str) -> dict:
    src = hit.get("_source", {})
    disclosure_id = src.get("disclosure_id") or hit.get("_id") or ""
    dl = src.get("download_link", "")
    url = f"https://data.fca.org.uk/artefacts/{dl}" if dl else ""
    return {
        "tier":        label.split(".")[0],
        "query_label": label,
        "query_note":  query_note,
        "cik":         "",                       # not applicable in UK
        "ticker":      src.get("symbol") or None,
        "isin":        src.get("isin") or None,
        "name":        src.get("company") or "",
        "form":        src.get("type") or "",    # RNS announcement type
        "form_code":   src.get("type_code") or "",
        "accession":   disclosure_id,
        "filed":       (src.get("publication_date") or "")[:10],
        "url":         url,
        "source":      "NSM",
        "fetched_at":  fetched_at,
    }


def write_inbox(records: list[dict]) -> dict[str, int]:
    """Write hits to data/inbox/<filed_date>/<tier>/<id>.json. Bucket by
    the filing's own publication date, not the poll date, so backfills
    land in the right per-day directory."""
    counts: dict[str, int] = {}
    for r in records:
        filed = r.get("filed") or date.today().isoformat()
        day_dir = INBOX / filed[:10]
        tier_dir = day_dir / r["tier"]
        tier_dir.mkdir(parents=True, exist_ok=True)
        slug = (r["accession"] or "no-id").replace("/", "_")
        # Add label suffix so the same disclosure can land in two tiers
        # without filename collision.
        label_suffix = r["query_label"].split(".")[-1]
        path = tier_dir / f"nsm_{slug}_{label_suffix}.json"
        path.write_text(json.dumps(r, indent=2, sort_keys=True, default=str))
        key = f"{filed[:10]}/{r['tier']}"
        counts[key] = counts.get(key, 0) + 1
    return counts


def poll_one_label(label: str, cfg: dict, cutoff: date,
                   fetched_at: str) -> list[dict]:
    """Page through NSM hits for one headline filter; stop once we
    cross the publication-date cutoff. NSM doesn't honour a date-range
    filter in its public proxy, so we use sort+cutoff instead."""
    records: list[dict] = []
    offset = 0
    while True:
        resp = nsm_search(cfg["headline"], from_offset=offset, size=PAGE_SIZE)
        hits = (resp.get("hits") or {}).get("hits") or []
        if not hits:
            break
        for h in hits:
            pub = (h.get("_source", {}).get("publication_date") or "")[:10]
            try:
                pub_d = date.fromisoformat(pub) if pub else None
            except ValueError:
                pub_d = None
            if pub_d and pub_d < cutoff:
                # Sorted desc — once we're past the cutoff, we're done.
                return records
            records.append(normalize_hit(label, h, cfg["note"], fetched_at))
        if len(hits) < PAGE_SIZE:
            break
        offset += PAGE_SIZE
        time.sleep(0.15)   # courtesy throttle
        # Safety: NSM proxy returns at most 10000 from+size
        if offset >= 9900:
            break
    return records


def poll(cutoff: date) -> int:
    """Poll all queries for hits filed >= cutoff."""
    fetched_at = datetime.utcnow().isoformat() + "Z"
    all_records: list[dict] = []
    print(f"Polling NSM for hits filed >= {cutoff.isoformat()}...")
    for label, cfg in QUERIES.items():
        recs = poll_one_label(label, cfg, cutoff, fetched_at)
        print(f"  {label:32s} {len(recs):>4d} hits  (\"{cfg['headline']}\")")
        all_records.extend(recs)
        time.sleep(0.15)
    if all_records:
        counts = write_inbox(all_records)
        print(f"\nWrote {len(all_records)} records "
              f"across {len(counts)} day/tier buckets")
        for k, v in sorted(counts.items()):
            print(f"  {k}: {v}")
    else:
        print("\nNo hits.")
    return len(all_records)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--date",
                    type=lambda s: datetime.strptime(s, "%Y-%m-%d").date(),
                    default=date.today(),
                    help="End of date window (default: today)")
    ap.add_argument("--days-back", type=int, default=1,
                    help="Window size in days (default 1 = today only)")
    args = ap.parse_args()

    cutoff = args.date - timedelta(days=args.days_back)
    total = poll(cutoff)
    print(f"\nDone. {total} records written.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
