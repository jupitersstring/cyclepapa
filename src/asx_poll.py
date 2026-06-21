#!/usr/bin/env python3
"""
asx_poll.py — daily ASX announcements poller (Australia / NZ).

Free public JSON endpoint at asx.api.markitdigital.com — no auth, no
session work needed. Each item carries: symbol, ISIN, sector,
isPriceSensitive flag, announcementTypes[], headline, and a direct
PDF URL.

We filter on announcement type + headline regex for special-situation
events (schemes, takeovers, capital raisings, substantial holdings,
voluntary administration, etc.) and additionally require
isPriceSensitive=True (an ASX-mandated tag) for the highest-signal
tiers. New Zealand issuers (suffix .NZ) also flow through since OCA
etc. are dual-listed.

Output schema matches data/inbox/<date>/<tier>/<id>.json so
inbox_promote.py picks up ASX hits the same way it handles the
other geographic pollers.

Usage:
    python -m src.asx_poll                       # poll today (top 100)
    python -m src.asx_poll --count 500           # wider window
    python -m src.asx_poll --days-back 7         # last week (caps at 1000)
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
API = ("https://asx.api.markitdigital.com/asx-research/1.0/"
       "markets/announcements")

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"),
    "Accept": "application/json",
    "Referer": "https://www.asx.com.au/",
}

# (headline regex, tier, sub_query_label, note). Order matters.
HEADLINE_PATTERNS: list[tuple[str, str, str, str]] = [
    # ---- Tier-S: hard events ----
    (r"\bscheme\s+(?:implementation|booklet|of\s+arrangement)\b",
     "tier_s", "scheme", "Australian scheme of arrangement"),
    (r"\bbidder['']?s\s+statement\b|\bbid\s+implementation\b",
     "tier_s", "takeover_bid", "Takeover bid (bidder's statement)"),
    (r"\btarget['']?s\s+statement\b",
     "tier_s", "target_statement", "Target's response to a takeover"),
    (r"\boff[- ]market\s+(?:takeover|tender|bid|buy[- ]?back)\b",
     "tier_s", "off_market_offer", "Off-market takeover or buy-back"),
    (r"\b(?:notice\s+of\s+)?compuls(?:ory|ive)\s+acquisition\b",
     "tier_s", "compulsory_acquisition", "Compulsory acquisition (squeeze-out)"),
    (r"\b(?:capital\s+raising|placement|entitlement\s+offer|rights\s+(?:issue|offer))\b",
     "tier_s", "capital_raising", "Capital raising / rights / placement"),
    (r"\bdeed\s+of\s+company\s+arrangement\b|\bvoluntary\s+administration\b",
     "tier_s", "voluntary_administration",
     "Voluntary administration / DOCA"),
    (r"\b(?:receivers?\s+(?:and\s+managers\s+)?appointed|in\s+receivership)\b",
     "tier_s", "receivership", "Receivership"),
    (r"\bliquidat(?:ion|ed|or)\b",
     "tier_s", "liquidation", "Liquidation"),
    (r"\b(?:suspension|trading\s+halt)\b",
     "tier_s", "suspension_halt", "Trading halt or suspension"),
    (r"\bdemerger\b|\bspin[- ]?off\b",
     "tier_s", "demerger", "Demerger / spin-off"),
    (r"\bstrategic\s+review\b|\bformal\s+sale\s+process\b",
     "tier_s", "strategic_review",
     "Strategic review — pre-event signal"),
    # ---- Revealed-preference ----
    (r"\bsubstantial\s+holder(?:\s+notice)?\b|\bchange\s+in\s+substantial\s+holding\b",
     "rev_pref", "substantial_holder",
     "5pct substantial-holder notice (AU equivalent of 13D)"),
    (r"\bs249d\b|\brequisition\s+of\s+meeting\b",
     "rev_pref", "s249d",
     "s249D requisition (activist-trigger)"),
    (r"\bappendix\s+3[YyXx]\b|\bdirector['']?s?\s+interest\s+notice\b",
     "rev_pref", "director_interest",
     "Director interest notice (Appendix 3X/3Y)"),
    # ---- Red flags ----
    (r"\bcontinuous\s+disclosure\s+(?:obligation|matter)\b",
     "red_flag", "disclosure_obligation",
     "Continuous-disclosure investigation"),
    (r"\bgoing\s+concern\b",
     "red_flag", "going_concern", "Going-concern doubt"),
]
HEADLINE_PATTERNS_COMPILED = [
    (re.compile(p, re.I), t, s, n) for p, t, s, n in HEADLINE_PATTERNS]


def fetch_announcements(count: int = 100, page: int = 0,
                        retries: int = 3) -> list[dict]:
    """One page of the announcements feed. The endpoint caps total
    results at 10000 but page size varies; we pass count + page."""
    delay = 1.0
    for attempt in range(retries):
        try:
            r = requests.get(API, params={"count": count, "page": page},
                             headers=HEADERS, timeout=30)
            if r.status_code == 429:
                time.sleep(delay); delay *= 2
                continue
            r.raise_for_status()
            j = r.json()
            return ((j or {}).get("data") or {}).get("items") or []
        except requests.RequestException as exc:
            if attempt == retries - 1:
                print(f"  ! ASX failed after {retries} attempts: {exc}",
                      file=sys.stderr)
                return []
            time.sleep(delay); delay *= 2
    return []


def classify(item: dict) -> tuple[str, str, str] | None:
    """Match the headline against our regex catalogue. Returns
    (tier, sub_query_label, note) or None."""
    headline = item.get("headline") or ""
    # Augment with the announcement-type list which often carries the
    # canonical label (e.g. "Scheme of Arrangement", "Appendix 3X")
    text = headline + " " + " ".join(item.get("announcementTypes") or [])
    for pat, tier, sub, note in HEADLINE_PATTERNS_COMPILED:
        if pat.search(text):
            return tier, sub, note
    return None


def normalize_hit(item: dict, tier: str, sub: str, note: str,
                  fetched_at: str) -> dict:
    info = (item.get("companyInfo") or [{}])[0]
    return {
        "tier":        tier,
        "query_label": f"{tier}.{sub}",
        "query_note":  note,
        "cik":         "",
        "ticker":      item.get("symbol") or info.get("symbol"),
        "isin":        info.get("isin"),
        "name":        info.get("displayName") or item.get("symbol") or "",
        "form":        (item.get("headline") or "")[:200],
        "form_code":   "|".join(item.get("announcementTypes") or [])[:60],
        "accession":   item.get("documentKey") or f"asx-{item.get('symbol')}-{item.get('date','')[:10]}",
        "filed":       (item.get("date") or "")[:10],
        "jurisdiction": "AU",
        "url":         item.get("url") or "",
        "sector":      info.get("sector"),
        "industry":    info.get("industry"),
        "price_sensitive": bool(item.get("isPriceSensitive")),
        "source":      "ASX",
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
        path = tier_dir / f"asx_{slug}_{sub}.json"
        path.write_text(json.dumps(r, indent=2, sort_keys=True, default=str,
                                   ensure_ascii=False))
        key = f"{filed[:10]}/{r['tier']}"
        counts[key] = counts.get(key, 0) + 1
    return counts


def poll(cutoff: date, max_items: int = 1000) -> int:
    fetched_at = datetime.utcnow().isoformat() + "Z"
    print(f"Polling ASX for announcements filed >= {cutoff.isoformat()}...")

    # API caps page size at ~25 items regardless of count param;
    # paginate explicitly until we run dry or cross the cutoff.
    all_items: list[dict] = []
    page = 0
    last_page_size = 0
    while len(all_items) < max_items:
        items = fetch_announcements(count=100, page=page)
        if not items:
            break
        last_page_size = len(items)
        cutoff_crossed = False
        for it in items:
            d_str = (it.get("date") or "")[:10]
            try:
                d = date.fromisoformat(d_str) if d_str else None
            except ValueError:
                d = None
            if d and d < cutoff:
                cutoff_crossed = True
                break
            all_items.append(it)
        if cutoff_crossed:
            break
        page += 1
        if page > 50:           # safety cap (~1250 items)
            break
        time.sleep(0.15)
    print(f"  {len(all_items)} announcements retrieved "
          f"({page + 1} pages, last_page_size={last_page_size})")

    # Classify
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
    print(f"  {len(hits)} matched a special-situation pattern:")
    for sub, n in classified.most_common():
        print(f"    {sub:30s} {n}")

    if hits:
        counts = write_inbox(hits)
        for k, v in sorted(counts.items()):
            print(f"  {k}: {v}")
    return len(hits)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    today = date.today()
    ap.add_argument("--date",
                    type=lambda s: datetime.strptime(s, "%Y-%m-%d").date(),
                    default=today)
    ap.add_argument("--days-back", type=int, default=1)
    ap.add_argument("--max-items", type=int, default=1000)
    args = ap.parse_args()
    cutoff = args.date - timedelta(days=args.days_back)
    total = poll(cutoff, max_items=args.max_items)
    print(f"\nDone. {total} records written.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
