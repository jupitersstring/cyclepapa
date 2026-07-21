#!/usr/bin/env python3
"""
postreorg_poll.py — post-reorganization / fresh-start equity poller.

Closes the framework's largest CATEGORY gap. PACER (pacer_poll.py)
catches companies ENTERING Chapter 11. Nothing catches them EMERGING.
But post-reorg equities — fresh-start companies that exit bankruptcy
and begin trading (often OTC), with no analyst coverage and forced-
seller creditors dumping stock received under the plan — are one of
the richest special-situations categories in the literature
(Greenblatt's "You Can Be a Stock Market Genius", Whitman, the whole
distressed-to-equity playbook).

We source emergence via EDGAR full-text search for the canonical
8-K emergence language — "emerged from Chapter 11", "Plan of
Reorganization became effective", "fresh-start accounting" — which
issuers file when they exit. This is additive to the existing EDGAR
infrastructure; a different query set than edgar_poll.py.

Output: data/inbox/<filing-date>/tier_s/postreorg_<accession>.json,
sub-label tier_s.post_reorg. inbox_promote.py whitelists it so
emergent names flow into universe.md — the payoff end of the
distressed funnel that the framework has been blind to.

Usage:
    python -m src.postreorg_poll                   # last 90 days
    python -m src.postreorg_poll --days-back 180
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
from urllib.parse import urlencode

from src.edgar_util import issuer_fields, fts_search_all

try:
    import requests
except ImportError:
    print("Install requests: pip install requests", file=sys.stderr)
    sys.exit(1)

REPO = Path(__file__).resolve().parent.parent
INBOX = REPO / "data" / "inbox"
EDGAR = "https://efts.sec.gov/LATEST/search-index"

USER_AGENT = os.environ.get(
    "EDGAR_USER_AGENT", "cyclepapa-screener research@example.com")
HEADERS = {"User-Agent": USER_AGENT, "Accept": "application/json"}

# Emergence phrase set — evidence-graded by the emergence-catch audit
# (live EDGAR precision/recall test on ~40 candidate phrases). Each entry is
# (phrase, canonical-sublabel, tier). STRONG = precise, event-marking phrases
# a downstream verifier can largely trust. RECALL = the wide net (lower
# precision), kept because catching the EVENT matters and precision is
# handled downstream (filer-emergence verification + the six-question screen).
# Phrases the audit found to be pure noise are intentionally excluded:
#   "the Plan became effective"   → matches annual incentive/equity plans
#   "consummated its Plan of Reorganization" → 0 hits
#   unhyphenated "fresh start ..." → redundant with the hyphenated forms
EMERGENCE_PHRASES: list[tuple[str, str, str]] = [
    # --- STRONG ---
    ('"emergence from Chapter 11"',                       "emerged",       "strong"),
    ('"fresh-start accounting"',                          "freshstart",    "strong"),
    ('"Effective Date of the Plan of Reorganization"',    "plan_effective","strong"),
    ('"consummation of the Plan of Reorganization"',      "plan_effective","strong"),
    ('"Plan of Reorganization became effective"',         "plan_effective","strong"),
    ('"applied fresh-start"',                             "freshstart",    "strong"),
    ('"adopted fresh-start"',                             "freshstart",    "strong"),
    # --- RECALL (wide net) ---
    ('"emerged from Chapter 11"',                         "emerged",       "recall"),
    ('"emerges from Chapter 11"',                         "emerged",       "recall"),
    ('"emergence from bankruptcy"',                       "emerged",       "recall"),
    ('"emerged from bankruptcy"',                         "emerged",       "recall"),
    ('"successfully emerged"',                            "emerged",       "recall"),
    ('"successfully emerges"',                            "emerged",       "recall"),
    ('"upon emergence"',                                  "emerged",       "recall"),
    ('"post-emergence"',                                  "emerged",       "recall"),
    ('"Plan Effective Date"',                             "plan_effective","recall"),
    ('"consummation of the Plan"',                        "plan_effective","recall"),
    ('"consummated the Plan"',                            "plan_effective","recall"),
    ('"fresh-start reporting"',                           "freshstart",    "recall"),
    ('"application of fresh start"',                      "freshstart",    "recall"),
    ('"emergence date"',                                  "emerged",       "recall"),
    ('"completes Chapter 11 reorganization"',             "emerged",       "recall"),
    ('"completion of the Chapter 11"',                    "emerged",       "recall"),
]

# Forms broadened per the audit. Critically adds 6-K + 20-F: foreign private
# issuers (Seadrill, Valaris, Noble) announce emergence on those, NOT 8-K/
# 10-K, so the old form set was structurally blind to them. S-1/424B3 catch
# post-emergence resale registration; 8-A12B the relisting of new common.
FORMS = "8-K,10-K,10-Q,6-K,20-F,S-1,424B3,8-A12B,8-A12G"

_NOTE = {
    "freshstart":
        "Fresh-start accounting (ASC 852) — adopted ONLY upon Chapter 11 "
        "emergence, so a post-reorg entity by definition. Uncovered equity, "
        "forced-seller creditors, clean cap stack.",
    "emerged":
        "Emergence from Chapter 11 — post-reorg equity now trading. Verify "
        "float, creditor overhang, and the coverage vacuum.",
    "plan_effective":
        "Plan of Reorganization effective / consummated — the emergence "
        "event. New equity distributed to creditors; watch the forced-"
        "selling window.",
}


def fetch(query: str, start: date, end: date,
          retries: int = 4) -> list[dict]:
    """ALL hits for a query, paginating through EDGAR's 10-per-page full-
    text search (shared paginator). Without this we silently caught only
    the first 10 records per query per run — the cardinal under-catch."""
    params = {
        "q": query, "forms": FORMS,
        "startdt": start.isoformat(), "enddt": end.isoformat(),
    }
    return fts_search_all(params, HEADERS, retries=retries,
                          log=lambda m: print(m, file=sys.stderr))


def normalize_hit(label: str, tier: str, phrase: str, hit: dict,
                  fetched_at: str) -> dict:
    src = hit.get("_source", {})
    accession = src.get("adsh", "")
    fields = issuer_fields(src)
    cik = fields["cik"] or ""
    name = fields["name"]
    ticker = fields["ticker"] or ""
    url = (f"https://www.sec.gov/Archives/edgar/data/"
           f"{int(cik):d}/{accession.replace('-', '')}"
           if cik and accession else "")
    items = src.get("items") or []
    # 8-K Item 1.03 (Bankruptcy or Receivership) present = structural
    # confirmation this is a genuine bankruptcy/emergence 8-K (the audit's
    # key precision filter — genuine emergence 8-Ks carry Item 1.03).
    has_103 = any(str(it).startswith("1.03") for it in items)
    # A 5-letter ticker ending in Q signals a security STILL IN bankruptcy
    # (not yet emerged) — forward-looking "upon emergence" language, not the
    # event. Flag so downstream treats it as pending, not emerged.
    tk = ticker.split(":")[-1]
    pre_emergence = bool(re.match(r"^[A-Z]{3,4}Q$", tk))
    return {
        "tier":          "tier_s",
        "query_label":   f"tier_s.post_reorg_{label}",
        "query_note":    _NOTE.get(label, "Post-reorganization signal."),
        "emergence_tier": tier,
        "matched_phrase": phrase.strip('"'),
        "item_1_03":     has_103,
        "pre_emergence": pre_emergence,
        "cik":           cik,
        "ticker":        ticker,
        "isin":          None,
        "name":          name,
        "form":          src.get("form") or "",
        "form_code":     src.get("form") or "",
        "items":         items,
        "accession":     accession,
        "filed":         src.get("file_date") or "",
        "jurisdiction":  "US",
        "url":           url,
        "source":        "EDGAR-postreorg",
        "fetched_at":    fetched_at,
    }


def write_inbox(records: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for r in records:
        filed = r.get("filed") or date.today().isoformat()
        tier_dir = INBOX / filed[:10] / r["tier"]
        tier_dir.mkdir(parents=True, exist_ok=True)
        slug = (r["accession"] or "no-id").replace("/", "_")
        path = tier_dir / f"postreorg_{slug}.json"
        path.write_text(json.dumps(r, indent=2, sort_keys=True, default=str))
        key = f"{filed[:10]}/{r['tier']}"
        counts[key] = counts.get(key, 0) + 1
    return counts


def poll(days_back: int) -> int:
    fetched_at = datetime.utcnow().isoformat() + "Z"
    end = date.today()
    start = end - timedelta(days=days_back)
    print(f"Polling EDGAR for post-reorg emergence "
          f"({start.isoformat()}..{end.isoformat()}) — "
          f"{len(EMERGENCE_PHRASES)} phrases × {FORMS.count(',')+1} forms...")
    # Dedup by accession across all phrases; keep the record from the
    # STRONGEST tier that matched it (strong > recall), and note every phrase.
    by_acc: dict[str, dict] = {}
    tier_rank = {"strong": 1, "recall": 0}
    strong_n = recall_n = 0
    for phrase, label, tier in EMERGENCE_PHRASES:
        hits = fetch(phrase, start, end)
        kept = 0
        for h in hits:
            acc = h.get("_source", {}).get("adsh", "")
            if not acc:
                continue
            rec = normalize_hit(label, tier, phrase, h, fetched_at)
            prev = by_acc.get(acc)
            if prev is None:
                by_acc[acc] = rec
                kept += 1
            else:
                # upgrade tier if this phrase is stronger; accumulate phrases
                prev.setdefault("also_matched", [])
                prev["also_matched"].append(phrase.strip('"'))
                if tier_rank[tier] > tier_rank.get(prev["emergence_tier"], 0):
                    rec["also_matched"] = prev.get("also_matched", [])
                    by_acc[acc] = rec
        if tier == "strong":
            strong_n += kept
        else:
            recall_n += kept
        print(f"  [{tier:6}] {label:14s} {phrase[:44]:44s} +{kept:>3d} new")
        time.sleep(0.12)
    all_records = list(by_acc.values())
    if all_records:
        counts = write_inbox(all_records)
        n_103 = sum(1 for r in all_records if r.get("item_1_03"))
        n_pre = sum(1 for r in all_records if r.get("pre_emergence"))
        print(f"\nWrote {len(all_records)} unique records "
              f"(strong-tier first-catch {strong_n}, recall {recall_n}) "
              f"across {len(counts)} day/tier buckets")
        print(f"  {n_103} carry 8-K Item 1.03 (structural confirmation); "
              f"{n_pre} are Q-suffix (still-in-bankruptcy, pending emergence)")
    else:
        print("\nNo post-reorg emergence signals in window.")
    return len(all_records)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--days-back", type=int, default=90)
    args = ap.parse_args()
    total = poll(args.days_back)
    print(f"\nDone. {total} records.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
