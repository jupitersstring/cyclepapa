#!/usr/bin/env python3
"""
corroborate.py — cross-poller signal-fusion layer.

The framework's 15 pollers each write isolated inbox records. A name
appearing in ONE poller and a name appearing in FIVE are otherwise
treated identically. But an entity corroborated across multiple
INDEPENDENT sources — e.g. a credit-spread widening AND an insider
cluster-sell AND a going-concern 8-K — is a categorically stronger
signal than any single hit.

This module walks the inbox, groups records by resolved entity, counts
DISTINCT sources per entity, and:
  1. Writes output/corroboration.md — a ranked report of multi-source
     entities.
  2. Emits data/inbox/<today>/tier_s/corroborated_<key>.json for every
     entity with >= 2 distinct sources, so inbox_promote.py surfaces
     them with elevated priority (sub-label tier_s.corroborated_multi).
  3. Writes data/corroboration.json — entity → {sources, count, tiers}
     consumed by universe_screen.py to boost the triage score of
     multi-sourced names.

Entity resolution (in priority order): ticker stem → CUSIP → ISIN →
name stem (corp suffixes stripped). Same normalisation as
inbox_promote.dedup_key so the two layers agree.

Usage:
    python -m src.corroborate                  # last 14 days
    python -m src.corroborate --days-back 30
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
INBOX = REPO / "data" / "inbox"
CORROB_JSON = REPO / "data" / "corroboration.json"
CORROB_MD = REPO / "output" / "corroboration.md"

_CORP_SUFFIX = re.compile(
    r"\b(plc|ltd|limited|inc|corp|corporation|group|holdings?|sa|nv|ag|"
    r"sas|spa|kg|llc|llp|pty|pte|kk|co|nv|se|oyj|asa|ab)\b", re.I)


def stem_name(n) -> str:
    if not n:
        return ""
    if isinstance(n, (list, tuple)):
        n = " ".join(str(x) for x in n)
    n = str(n)
    s = _CORP_SUFFIX.sub("", n)
    return re.sub(r"[^A-Za-z0-9]", "", s).upper()


def stem_ticker(t) -> str:
    if not t:
        return ""
    return re.sub(r"[^A-Za-z0-9]", "", str(t).split(":")[-1]).upper()


def entity_key(rec: dict) -> str:
    """Resolve an inbox record to a stable entity key."""
    return (stem_ticker(rec.get("ticker"))
            or (rec.get("cusip") or "").upper()
            or (rec.get("isin") or "").upper()
            or stem_name(rec.get("name"))
            or "")


def display_name(rec: dict) -> str:
    n = rec.get("name")
    if isinstance(n, (list, tuple)):
        n = n[0] if n else ""
    return str(n or rec.get("ticker") or "?")


def collect_inbox(days_back: int) -> list[dict]:
    records = []
    end = date.today()
    for n in range(days_back + 1):
        day = end - timedelta(days=n)
        day_dir = INBOX / day.isoformat()
        if not day_dir.exists():
            continue
        for tier_dir in day_dir.iterdir():
            if not tier_dir.is_dir():
                continue
            for jf in tier_dir.glob("*.json"):
                try:
                    rec = json.loads(jf.read_text())
                    rec["_tier_dir"] = tier_dir.name
                    rec["_day"] = day.isoformat()
                    records.append(rec)
                except (json.JSONDecodeError, OSError):
                    continue
    return records


def build_corroboration(records: list[dict]) -> dict[str, dict]:
    """entity_key -> {sources, tiers, labels, name, days, records}."""
    by_entity: dict[str, dict] = defaultdict(
        lambda: {"sources": set(), "tiers": set(), "labels": set(),
                 "name": "", "days": set(), "n_records": 0})
    for rec in records:
        # Skip our own derived corroboration records — they are not an
        # independent primary source and would inflate the count on re-run.
        if rec.get("source") == "corroboration" or \
                rec.get("query_label") == "tier_s.corroborated_multi":
            continue
        key = entity_key(rec)
        if not key or len(key) < 3:
            continue
        e = by_entity[key]
        src = rec.get("source", "") or rec.get("_tier_dir", "")
        if src:
            e["sources"].add(src)
        e["tiers"].add(rec.get("tier", "") or rec.get("_tier_dir", ""))
        e["labels"].add(rec.get("query_label", ""))
        e["days"].add(rec.get("filed") or rec.get("_day", ""))
        e["n_records"] += 1
        if not e["name"]:
            e["name"] = display_name(rec)
    return by_entity


def emit_corroborated_inbox(entity_key: str, e: dict,
                            fetched_at: str) -> None:
    """Write an elevated inbox record for a multi-source entity."""
    filed = date.today().isoformat()
    tier_dir = INBOX / filed / "tier_s"
    tier_dir.mkdir(parents=True, exist_ok=True)
    sources = sorted(e["sources"])
    record = {
        "tier":        "tier_s",
        "query_label": "tier_s.corroborated_multi",
        "query_note":  (f"CORROBORATED across {len(sources)} independent "
                        f"sources ({', '.join(sources)}); "
                        f"{e['n_records']} total records. "
                        f"Cross-source corroboration is the framework's "
                        f"highest-conviction sourced signal."),
        "cik":         "",
        "ticker":      None,
        "isin":        None,
        "name":        e["name"],
        "form":        "Cross-source corroboration",
        "form_code":   "CORROBORATED",
        "accession":   f"corrob-{entity_key}",
        "filed":       filed,
        "jurisdiction": "",
        "url":         "",
        "n_sources":   len(sources),
        "sources":     sources,
        "tiers":       sorted(t for t in e["tiers"] if t),
        "labels":      sorted(l for l in e["labels"] if l),
        "source":      "corroboration",
        "fetched_at":  fetched_at,
    }
    path = tier_dir / f"corroborated_{entity_key}.json"
    path.write_text(json.dumps(record, indent=2, sort_keys=True, default=str))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--days-back", type=int, default=14)
    ap.add_argument("--min-sources", type=int, default=2,
                    help="Minimum distinct sources to count as corroborated")
    args = ap.parse_args()

    fetched_at = datetime.utcnow().isoformat() + "Z"
    records = collect_inbox(args.days_back)
    print(f"Walking inbox (last {args.days_back + 1} days): "
          f"{len(records)} records")
    by_entity = build_corroboration(records)
    print(f"  {len(by_entity)} distinct entities")

    # Rank by (n distinct sources, n records)
    ranked = sorted(
        by_entity.items(),
        key=lambda kv: (len(kv[1]["sources"]), kv[1]["n_records"]),
        reverse=True)

    corroborated = [(k, e) for k, e in ranked
                    if len(e["sources"]) >= args.min_sources]
    print(f"  {len(corroborated)} entities corroborated by "
          f">= {args.min_sources} distinct sources")

    # Emit elevated inbox records + persist JSON for the screener
    persist: dict[str, dict] = {}
    for k, e in corroborated:
        emit_corroborated_inbox(k, e, fetched_at)
        persist[k] = {
            "name": e["name"],
            "n_sources": len(e["sources"]),
            "sources": sorted(e["sources"]),
            "tiers": sorted(t for t in e["tiers"] if t),
            "n_records": e["n_records"],
        }
    CORROB_JSON.parent.mkdir(parents=True, exist_ok=True)
    CORROB_JSON.write_text(json.dumps(persist, indent=2, sort_keys=True))

    # Markdown report
    lines = [
        f"# Cross-source corroboration report ({date.today().isoformat()})",
        "",
        "Auto-generated by `src/corroborate.py`. Entities ranked by number "
        "of DISTINCT poller sources that independently flagged them. "
        "Multi-source corroboration is the framework's highest-conviction "
        "sourced signal — a name seen by (say) a credit-spread widening "
        "AND an insider cluster-sell AND a going-concern filing is far "
        "stronger than any single hit.",
        "",
        f"- {len(records)} inbox records over {args.days_back + 1} days",
        f"- {len(by_entity)} distinct entities",
        f"- {len(corroborated)} corroborated by >= {args.min_sources} sources",
        "",
        "## Top corroborated entities",
        "",
        "| Rank | Entity | Sources | # | Tiers | Query labels |",
        "|---:|---|---:|---:|---|---|",
    ]
    for i, (k, e) in enumerate(corroborated[:60], 1):
        srcs = ", ".join(sorted(e["sources"]))
        tiers = ", ".join(sorted(t for t in e["tiers"] if t))
        labels = ", ".join(sorted(
            l.split(".")[-1] for l in e["labels"] if l)[:6])
        lines.append(
            f"| {i} | {e['name'][:40]} | {len(e['sources'])} | "
            f"{e['n_records']} | {tiers[:30]} | {labels[:50]} |")
    CORROB_MD.parent.mkdir(parents=True, exist_ok=True)
    CORROB_MD.write_text("\n".join(lines) + "\n")

    print(f"\nWrote {CORROB_JSON}")
    print(f"Wrote {CORROB_MD}")
    print(f"\nTop corroborated entities:")
    for i, (k, e) in enumerate(corroborated[:12], 1):
        print(f"  {i:2d}. {len(e['sources'])} sources  "
              f"{e['name'][:38]:38s} [{', '.join(sorted(e['sources']))}]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
