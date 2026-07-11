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


# ---- institutional weighted-corroboration model -------------------------
# Event-severity weight per query-label sub-type. Hard, dated, structural
# events (a bankruptcy petition, a firm takeover offer, a plan becoming
# effective) carry far more conviction than soft/ambient signals (a
# lobbying registration, a trading update). Default 0.5 for unlisted.
EVENT_SEVERITY: dict[str, float] = {
    # hardest — a legally-binding structural event has occurred / is filed
    "item_bankruptcy": 1.0, "bankruptcy_11": 1.0, "bankruptcy_15": 1.0,
    "judicial_recovery": 1.0, "bankruptcy_br": 1.0, "civil_rehabilitation": 1.0,
    "post_reorg_plan_effective": 1.0, "post_reorg_freshstart": 1.0,
    "scheme": 0.95, "rule_2_7": 0.95, "recommended_offer": 0.95,
    "takeover_bid": 0.95, "tob": 0.95, "mbo": 0.95, "opa": 0.95,
    "merger_vote": 0.9, "plan_of_arrangement": 0.9, "delisting_form25": 0.9,
    "item_default_acceleration": 0.9, "receivership": 0.9,
    "voluntary_administration": 0.9, "administrators": 0.9,
    "rights_offering": 0.85, "exchange_offer": 0.85, "restructuring": 0.85,
    "self_tender": 0.85, "issuer_bid": 0.85, "compulsory_acquisition": 0.85,
    "item_delisting_deficiency": 0.8, "delisting": 0.8, "suspension": 0.8,
    "going_dark_12b": 0.8, "going_dark_12g": 0.8, "cancellation": 0.8,
    "proxy_contest": 0.8, "sc_13d": 0.8, "early_warning": 0.8,
    "post_reorg_emerged": 0.8,
    "capital_raising": 0.7, "capital_increase": 0.7, "third_party_allotment": 0.7,
    "material_change": 0.7, "sc_13d_a": 0.7, "material_fact": 0.65,
    "item_restatement": 0.75, "cluster_sells": 0.75,
    "strategic_review": 0.65, "rule_2_4": 0.65, "major_shareholder_change": 0.6,
    "thirteenf_new_position": 0.6, "thirteenf_add": 0.5,
    # soft / ambient signals
    "going_concern": 0.55, "credit_spread_widening": 0.5,
    "sec_comment_letter": 0.5, "buyback": 0.45, "spac_arb": 0.4,
    "ofac_designation_other": 0.4, "earnings_revision": 0.4,
}

# Source-reliability weight. A court docket / structured regulatory
# filing is more reliable than a keyword full-text hit or a lobbying
# registration (which is a weak proxy for a future event).
SOURCE_RELIABILITY: dict[str, float] = {
    "CourtListener-RECAP": 1.0, "EDGAR-SC13D": 1.0, "EDGAR-Form15": 1.0,
    "EDGAR-8K-items": 0.95, "EDGAR-forms": 0.95, "EDGAR-postreorg": 0.95,
    "SEDAR+": 0.9, "NSM": 0.9, "TDnet": 0.9, "CVM-IPE": 0.9, "ASX": 0.9,
    "EDGAR-13F": 0.85, "EDGAR-spinoff-radar": 0.85, "OFAC": 0.85,
    "EDGAR-FTS": 0.7,          # keyword full-text — noisier
    "FRED-ICE-BofA-OAS": 0.6,  # market-level, not name-level
    "LDA-Senate": 0.45,        # lobbying — weak forward proxy
}

RECENCY_HALFLIFE_DAYS = 21.0   # a signal's weight halves every 3 weeks


def _severity(label: str) -> float:
    sub = (label or "").split(".")[-1]
    return EVENT_SEVERITY.get(sub, 0.5)


def _reliability(source: str) -> float:
    return SOURCE_RELIABILITY.get(source, 0.6)


def _recency_weight(day_iso: str) -> float:
    try:
        d = date.fromisoformat((day_iso or "")[:10])
    except ValueError:
        return 0.5
    age = max(0, (date.today() - d).days)
    return 0.5 ** (age / RECENCY_HALFLIFE_DAYS)


_SM = None


def _sec_master():
    global _SM
    if _SM is None:
        try:
            from src.security_master import SecurityMaster
            _SM = SecurityMaster()
        except Exception:
            _SM = False
    return _SM or None


def entity_key(rec: dict) -> str:
    """Resolve an inbox record to a canonical entity key via the security
    master (CIK<->ticker<->CUSIP<->ISIN crosswalk), so a 13F CUSIP
    position and an 8-K ticker filing for the same issuer collapse to the
    same key. Falls back to the local stem logic if the master is
    unavailable (offline)."""
    sm = _sec_master()
    if sm is not None:
        try:
            key = sm.canonical_key(
                cik=rec.get("cik"), ticker=rec.get("ticker"),
                cusip=rec.get("cusip"), isin=rec.get("isin"),
                name=rec.get("name"))
            if key:
                return key.upper()
        except Exception:
            pass
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
    """entity_key -> aggregate with a weighted institutional conviction
    score. conviction = sum over records of
        severity(event) * reliability(source) * recency(day),
    with a diversity bonus for distinct sources so a name seen by three
    INDEPENDENT sources outranks one seen thrice by the same source."""
    by_entity: dict[str, dict] = defaultdict(
        lambda: {"sources": set(), "tiers": set(), "labels": set(),
                 "name": "", "days": set(), "n_records": 0,
                 "conviction": 0.0, "hardest": 0.0})
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
        label = rec.get("query_label", "")
        e["tiers"].add(rec.get("tier", "") or rec.get("_tier_dir", ""))
        e["labels"].add(label)
        day = rec.get("filed") or rec.get("_day", "")
        e["days"].add(day)
        e["n_records"] += 1
        sev = _severity(label)
        e["conviction"] += sev * _reliability(src) * _recency_weight(day)
        e["hardest"] = max(e["hardest"], sev)
        if not e["name"]:
            e["name"] = display_name(rec)
    # Diversity multiplier: distinct-source count amplifies conviction
    # (independent confirmation is worth more than repetition).
    for e in by_entity.values():
        n_src = len(e["sources"])
        e["diversity_mult"] = 1.0 + 0.25 * max(0, n_src - 1)
        e["conviction_score"] = round(e["conviction"] * e["diversity_mult"], 3)
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
        "conviction_score": e.get("conviction_score", 0.0),
        "hardest_event": round(e.get("hardest", 0.0), 3),
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

    # Rank by weighted conviction score (institutional), then distinct
    # sources as a tiebreak. This replaces the naive distinct-source
    # count: a name flagged by one hard, reliable, recent event
    # (bankruptcy filed today) can outrank a name flagged by three soft,
    # stale, low-reliability signals.
    ranked = sorted(
        by_entity.items(),
        key=lambda kv: (kv[1]["conviction_score"], len(kv[1]["sources"])),
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
            "conviction_score": e["conviction_score"],
            "hardest_event": round(e["hardest"], 3),
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
        "## Top corroborated entities (ranked by weighted conviction)",
        "",
        "Conviction = Σ severity(event) × reliability(source) × recency(day), "
        "× a distinct-source diversity multiplier. Entity resolution is via "
        "the security master (CIK↔ticker↔CUSIP↔ISIN), so a 13F CUSIP "
        "position and an 8-K ticker filing for the same issuer corroborate.",
        "",
        "| Rank | Entity | Conviction | Sources | # | Hardest | Query labels |",
        "|---:|---|---:|---:|---:|---:|---|",
    ]
    for i, (k, e) in enumerate(corroborated[:60], 1):
        labels = ", ".join(sorted(
            l.split(".")[-1] for l in e["labels"] if l)[:6])
        lines.append(
            f"| {i} | {e['name'][:38]} | {e['conviction_score']:.2f} | "
            f"{len(e['sources'])} | {e['n_records']} | "
            f"{e['hardest']:.2f} | {labels[:46]} |")
    CORROB_MD.parent.mkdir(parents=True, exist_ok=True)
    CORROB_MD.write_text("\n".join(lines) + "\n")

    print(f"\nWrote {CORROB_JSON}")
    print(f"Wrote {CORROB_MD}")
    print(f"\nTop corroborated entities (by weighted conviction):")
    for i, (k, e) in enumerate(corroborated[:12], 1):
        print(f"  {i:2d}. conv={e['conviction_score']:5.2f} "
              f"{len(e['sources'])}src  {e['name'][:34]:34s} "
              f"[{', '.join(sorted(e['sources']))}]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
