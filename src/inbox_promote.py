#!/usr/bin/env python3
"""
inbox_promote.py — close the loop from automated pollers to universe.md.

The framework's pollers (edgar_poll.py, spinoff_radar.py, cluster_buys.py)
write hits to data/inbox/<date>/<tier>/<accession>.json.

Until now those hits were a research queue with no automated path back
into universe.md. The "universe" was hand-curated and so the framework's
selections were comprehensive only of what was written down — exactly
the gap the user flagged.

This script closes the loop:

  pollers → data/inbox/ → inbox_promote.py → universe.md
                                            → src/yaml_skeleton.py
                                            → data/candidates/<TICKER>.yaml

Run daily as part of `make all`. Dedups against:
- existing universe.md rows (by ticker stem)
- existing data/candidates/*.yaml (by ticker stem)
- prior inbox entries (by accession ID hash)

Promotes inbox hits matching framework criteria to a new section in
universe.md tagged "### Auto-promoted from pollers (YYYY-MM-DD)" so
the provenance is visible. Honest about source: each row notes the
filing form + accession + filed date.

Usage:
    python -m src.inbox_promote                    # process today's inbox
    python -m src.inbox_promote --days-back 7      # process last week
    python -m src.inbox_promote --dry-run          # preview only
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

try:
    import yaml
except ImportError:
    print("Install PyYAML", file=sys.stderr)
    sys.exit(1)

REPO = Path(__file__).resolve().parent.parent
INBOX_DIR = REPO / "data" / "inbox"
UNIVERSE_MD = REPO / "universe.md"
CANDIDATES_DIR = REPO / "data" / "candidates"
PROMOTED_LOG = REPO / "data" / "inbox_promoted.json"


# Form-type → bucket / archetype priors for auto-classification
FORM_TO_BUCKET = {
    "10-12B": "A", "10-12B/A": "A",        # spinoff
    "SC 13D": "A", "SC 13D/A": "A",        # activist
    "SC TO-T": "C", "SC TO-I": "C",        # tender
    "DEFM14A": "A", "PREM14A": "A",        # merger proxy
    "8-K": "A",                            # default
    "S-4": "A",                            # stock-deal merger
}

FORM_TO_ARCHETYPE = {
    "10-12B": "F", "10-12B/A": "F",
    "SC 13D": "H", "SC 13D/A": "H",
    "SC TO-T": "C", "SC TO-I": "C",
    "DEFM14A": "C", "PREM14A": "C",
    "8-K": "C",
    "S-4": "C",
}

# Filter thresholds — only promote if the issuer looks like a real
# special-situation candidate, not just any 8-K filer.
PROMOTE_TIERS = {"tier_s", "spinoff"}     # always promote
PROMOTE_TIER_S_TIGHT = {                  # tier_s sub-queries that promote
    # ---- EDGAR labels (edgar_poll.py) ----
    "rights_offering", "backstop_agreement", "exchange_offer",
    "consent_solicitation", "lien_release", "scheme", "tender",
    # ---- NSM labels (uk_rns_poll.py) ----
    "rule_2_7", "recommended_offer", "open_offer", "restructuring",
    "rule_2_4", "administration", "administrators", "cva",
    "suspension", "cancellation", "strategic_review",
    # ---- SEDAR+ labels (sedarplus_poll.py) ----
    "takeover_bid", "issuer_bid", "directors_circular",
    "plan_of_arrangement", "early_warning", "amr", "bar",
    "material_change", "corp_structure", "info_circular",
    # ---- TDnet labels (jpx_tdnet_poll.py) ----
    "tob", "mbo", "share_exchange", "share_transfer", "demerger",
    "merger_absorption", "civil_rehabilitation", "corporate_reorganization",
    "special_liquidation", "delisting", "major_shareholder_change",
    "controlling_shareholder", "third_party_allotment", "public_offering",
    # ---- PACER / CourtListener labels (pacer_poll.py) ----
    "bankruptcy_11", "bankruptcy_15",
    # ---- Brazilian CVM labels (cvm_poll.py) ----
    "judicial_recovery", "extrajudicial_recovery", "bankruptcy_br",
    "opa", "merger", "capital_increase", "corp_reorg",
    "material_fact", "stock_split",
    # ---- ASX labels (asx_poll.py) ----
    "takeover_bid", "target_statement", "off_market_offer",
    "compulsory_acquisition", "capital_raising",
    "voluntary_administration", "receivership",
}


def load_existing_universe_tickers() -> set[str]:
    """Pull every ticker stem + name stem currently in universe.md.
    Name stems use the same normalization as inbox records so dedup is
    consistent across the two sources."""
    out = set()
    if not UNIVERSE_MD.exists():
        return out
    text = UNIVERSE_MD.read_text()
    in_table = False
    for line in text.splitlines():
        stripped = line.strip()
        if all(c in "-:| " for c in stripped) and "|" in stripped:
            in_table = True
            continue
        if not stripped.startswith("|"):
            in_table = False
            continue
        if not in_table:
            continue
        cells = [c.strip() for c in stripped.strip("|").split("|")]
        if len(cells) < 2:
            continue
        name_cell = cells[0]
        ticker_cell = cells[1] if len(cells) > 1 else ""
        if ticker_cell:
            t_stem = stem_ticker(ticker_cell.split()[0])
            if t_stem:
                out.add(t_stem)
        if name_cell:
            n_stem = stem_name(name_cell)
            if n_stem:
                out.add(n_stem)
    return out


def load_existing_yaml_tickers() -> set[str]:
    """Ticker stems AND name stems already covered by a YAML."""
    out = set()
    for path in CANDIDATES_DIR.glob("*.yaml"):
        with path.open() as f:
            d = yaml.safe_load(f) or {}
        t = d.get("ticker")
        if t:
            stem = stem_ticker(str(t))
            if stem:
                out.add(stem)
        n = d.get("name")
        if n:
            n_stem = stem_name(str(n))
            if n_stem:
                out.add(n_stem)
    return out


def load_promoted_log() -> dict:
    if not PROMOTED_LOG.exists():
        return {"promoted_accessions": []}
    with PROMOTED_LOG.open() as f:
        return json.load(f)


def save_promoted_log(log: dict) -> None:
    PROMOTED_LOG.parent.mkdir(parents=True, exist_ok=True)
    with PROMOTED_LOG.open("w") as f:
        json.dump(log, f, indent=2, sort_keys=True)


def collect_inbox(days_back: int) -> list[dict]:
    """Walk data/inbox/<date>/<tier>/*.json from today minus N days."""
    records = []
    end = date.today()
    for n in range(days_back + 1):
        day = end - timedelta(days=n)
        day_dir = INBOX_DIR / day.isoformat()
        if not day_dir.exists():
            continue
        for tier_dir in day_dir.iterdir():
            if not tier_dir.is_dir():
                continue
            for json_path in tier_dir.glob("*.json"):
                try:
                    with json_path.open() as f:
                        rec = json.load(f)
                    rec["_tier_dir"] = tier_dir.name
                    rec["_day"] = day.isoformat()
                    records.append(rec)
                except (json.JSONDecodeError, OSError):
                    continue
    return records


def should_promote(rec: dict) -> bool:
    """Filter: is this inbox hit worth promoting to universe.md?"""
    tier = rec.get("tier", "")
    query_label = rec.get("query_label", "")
    # Spinoff radar hits — always promote
    if rec.get("_tier_dir") == "spinoff" or tier == "spinoff":
        return True
    # Tier-S restructuring hits — always promote
    if tier == "tier_s":
        # tighter filter on which Tier-S sub-queries
        sub = query_label.split(".")[-1] if "." in query_label else query_label
        if sub in PROMOTE_TIER_S_TIGHT:
            return True
    # Skip red flags (going-concern alone isn't a promote-worthy event)
    if tier == "red_flag":
        return False
    return False


def stem_ticker(t: str | None) -> str:
    if not t:
        return ""
    return re.sub(r"[^A-Za-z0-9]", "", t.split(":")[-1]).upper()


def stem_name(n: str | None) -> str:
    """Normalize an issuer name to a dedup key. Strips corp suffixes and
    punctuation so 'Van Elle Holdings PLC' and 'Van Elle Holdings plc' match."""
    if not n:
        return ""
    s = re.sub(r"\b(plc|ltd|limited|inc|corp|corporation|group|holdings|sa|nv|ag|"
               r"sas|spa|kg|llc|llp|pty|pte|kk|inc\.|co)\b", "", n, flags=re.I)
    return re.sub(r"[^A-Za-z0-9]", "", s).upper()


def dedup_key(rec: dict) -> str:
    """Best identifier for the issuer behind a hit. UK NSM records often
    have no ticker, so fall back to ISIN, then name stem, then accession."""
    return (stem_ticker(rec.get("ticker"))
            or (rec.get("isin") or "").upper()
            or stem_name(rec.get("name"))
            or rec.get("accession") or "")


def identifier_for_row(rec: dict) -> str:
    """Human-readable identifier for the universe.md Ticker column."""
    if rec.get("ticker"):
        return str(rec["ticker"])
    if rec.get("isin"):
        return f"ISIN:{rec['isin']}"
    if rec.get("cik"):
        return f"CIK:{rec['cik']}"
    return "—"


def build_row(rec: dict) -> str:
    """Build a markdown table row for the promoted inbox hit."""
    name = rec.get("name") or rec.get("ticker") or "?"
    ticker = identifier_for_row(rec)
    form = rec.get("form", "?")
    accession = rec.get("accession", "?")
    filed = rec.get("filed") or rec.get("_day", "?")
    query_note = rec.get("query_note") or rec.get("query_label", "")
    notes = (
        f"Auto-promoted from {form} filing {filed} (acc {accession}); "
        f"{query_note}; verify primary doc before scoring"
    )
    return f"| {name} | {ticker} | ○ | A | {notes} |"


def append_to_universe(rows: list[str], section_label: str,
                      dry_run: bool) -> int:
    """Append a fresh '### Auto-promoted...' section to universe.md."""
    if not rows:
        return 0
    section = (
        f"\n### Auto-promoted from pollers ({section_label})\n\n"
        "Inserted by `src/inbox_promote.py`. Each row carries its source "
        "form + accession in the notes column. Re-score via the universe "
        "screen and verify against primary docs before YAML build-out.\n\n"
        "| Name | Ticker | Conf. | Bucket | Notes |\n"
        "|---|---|---|---|---|\n"
        + "\n".join(rows)
        + "\n"
    )
    if dry_run:
        print(section)
        return len(rows)
    with UNIVERSE_MD.open("a") as f:
        f.write(section)
    return len(rows)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--days-back", type=int, default=1,
                    help="Process inbox days going back N (default 1 = today)")
    ap.add_argument("--dry-run", action="store_true",
                    help="Preview without writing universe.md")
    args = ap.parse_args()

    print(f"Loading existing universe.md tickers...")
    existing = load_existing_universe_tickers() | load_existing_yaml_tickers()
    print(f"  {len(existing)} existing ticker stems known")

    log = load_promoted_log()
    promoted_set = set(log.get("promoted_accessions", []))

    print(f"Walking inbox (last {args.days_back + 1} day(s))...")
    records = collect_inbox(args.days_back)
    print(f"  {len(records)} inbox records found")

    promote_now: list[dict] = []
    skip_dup_ticker = 0
    skip_dup_accession = 0
    skip_filter = 0
    for rec in records:
        accession = rec.get("accession", "")
        if accession and accession in promoted_set:
            skip_dup_accession += 1
            continue
        if not should_promote(rec):
            skip_filter += 1
            continue
        # Dedup against universe.md + YAMLs by ticker OR name stem.
        # NSM hits often have no ticker, so fall back to name stem to
        # catch the same issuer already curated under a different identifier.
        ticker = stem_ticker(rec.get("ticker"))
        name = stem_name(rec.get("name"))
        if (ticker and ticker in existing) or (name and name in existing):
            skip_dup_ticker += 1
            continue
        promote_now.append(rec)

    print(f"\nClassification:")
    print(f"  promote: {len(promote_now)}")
    print(f"  skip (already promoted): {skip_dup_accession}")
    print(f"  skip (ticker already in universe/YAMLs): {skip_dup_ticker}")
    print(f"  skip (filter didn't match): {skip_filter}")

    # Dedup within this batch. For NSM rows that have no ticker,
    # dedup_key falls back to ISIN then name stem so the same issuer
    # with multiple event-type hits collapses to one row.
    seen_in_batch = set()
    deduped = []
    for rec in promote_now:
        key = dedup_key(rec)
        if key in seen_in_batch:
            continue
        seen_in_batch.add(key)
        deduped.append(rec)

    rows = [build_row(rec) for rec in deduped]
    section_label = date.today().isoformat()
    n = append_to_universe(rows, section_label, args.dry_run)

    if n and not args.dry_run:
        for rec in deduped:
            accession = rec.get("accession")
            if accession:
                promoted_set.add(accession)
        log["promoted_accessions"] = sorted(promoted_set)
        log["last_run"] = datetime.utcnow().isoformat() + "Z"
        save_promoted_log(log)

    print(f"\nPromoted {n} new rows to universe.md "
          f"(dry-run={args.dry_run}).")
    if n:
        print(
            f"Next step: run `make universe` to re-rank, then "
            f"`python -m src.yaml_skeleton --min-score 0.55` to "
            f"generate skeleton YAMLs for any new T0/T1 names."
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
