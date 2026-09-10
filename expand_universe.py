"""Expand universe.csv from curated source CSVs.

Reads data/us_cef_seed.csv (~150 US CEFs) and merges any tickers not
already in universe.csv with sensible defaults. Idempotent — running
twice leaves the universe unchanged.

After this, run reconcile_aic.py for an AIC-vs-universe diff and add
any UK names flagged as missing-in-universe.
"""
from __future__ import annotations

import argparse
import csv
import os
import sys
from pathlib import Path


HERE = Path(os.path.dirname(os.path.abspath(__file__)))
UNIVERSE = HERE / "universe.csv"
US_SEED = HERE / "data" / "us_cef_seed.csv"


UNIVERSE_FIELDS = [
    "ticker", "isin", "name", "group", "catalyst", "nav_quality",
    "discount_override", "aic_sector", "market_cap_gbp_m",
    "catalyst_date", "catalyst_source_url", "notes",
]


def merge_seed(seed_path: Path = US_SEED) -> tuple[int, int]:
    """Returns (added, already_present)."""
    if not seed_path.exists():
        print(f"Seed not found: {seed_path}", file=sys.stderr)
        return 0, 0
    with open(UNIVERSE) as f:
        existing = list(csv.DictReader(f))
    have = {r["ticker"] for r in existing}
    new = []
    with open(seed_path) as f:
        for row in csv.DictReader(f):
            t = row["ticker"].strip()
            if not t or t in have:
                continue
            new.append({
                "ticker": t,
                "isin": "",
                "name": row.get("name", "").strip(),
                "group": row.get("group", "us_cef_seed"),
                "catalyst": row.get("catalyst", "STRUCTURAL_DISCOUNT"),
                "nav_quality": row.get("nav_quality", "LISTED_CLEAN"),
                "discount_override": "",
                "aic_sector": "",
                "market_cap_gbp_m": "",
                "catalyst_date": "",
                "catalyst_source_url": "",
                "notes": (row.get("notes") or "").strip(),
            })
    if not new:
        return 0, len(have)
    # Append to universe.csv
    with open(UNIVERSE, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=UNIVERSE_FIELDS)
        for r in new:
            w.writerow(r)
    return len(new), len(have)


AIC_SECTOR_TO_NAV_QUALITY = {
    # PE / venture / growth
    "PE":    "PRIVATE_EQUITY",
    "GE":    "PRIVATE_EQUITY",
    "VCG":   "PRIVATE_EQUITY",
    "VG":    "PRIVATE_EQUITY",
    "USC":   "PRIVATE_EQUITY",
    "PUR":   "PROPERTY_DCF",
    "PRW":   "PROPERTY_DCF",
    "PRE":   "PROPERTY_DCF",
    "REI":   "RENEWABLES_DCF",
    "RNE":   "RENEWABLES_DCF",
    "INF":   "INFRA_DCF",
    "IS":    "DEBT_AMORTISING",
    "ICS":   "DEBT_AMORTISING",
    "DBT":   "DEBT_AMORTISING",
    "FLX":   "DEBT_AMORTISING",   # flex / multi-asset
    "HC":    "DEBT_AMORTISING",
    "AB":    "PROPERTY_DCF",      # asset-backed lending
    "DBS":   "DEBT_AMORTISING",   # debt - structured
    # Equities (default LISTED_CLEAN)
    "UE":    "LISTED_CLEAN",
    "EU":    "LISTED_CLEAN",
    "GLE":   "LISTED_CLEAN",
    "GLEI":  "LISTED_CLEAN",
    "GLEN":  "LISTED_CLEAN",
    "GLS":   "LISTED_CLEAN",
    "UKE":   "LISTED_CLEAN",
    "UKAI":  "LISTED_CLEAN",
    "UKS":   "LISTED_CLEAN",
    "JPN":   "LISTED_CLEAN",
    "ASP":   "LISTED_CLEAN",
    "EMM":   "LISTED_CLEAN",
    "EME":   "LISTED_CLEAN",
    "AS":    "LISTED_CLEAN",
    "BIO":   "LISTED_CLEAN",
    "TY":    "LISTED_CLEAN",
}


def expand_from_aic_reconcile() -> int:
    """Add AIC-reconcile missing-in-universe names to universe.csv."""
    reconcile_path = HERE / "data" / "aic_reconcile.csv"
    if not reconcile_path.exists():
        print(f"Run reconcile_aic.py first (no {reconcile_path})",
              file=sys.stderr)
        return 0
    with open(UNIVERSE) as f:
        have = {r["ticker"] for r in csv.DictReader(f)}
    to_add = []
    with open(reconcile_path) as f:
        for r in csv.DictReader(f):
            if r.get("kind") != "missing_in_universe":
                continue
            t = r["ticker"]
            if t in have:
                continue
            sector = (r.get("sector") or "").upper()
            nav_q = AIC_SECTOR_TO_NAV_QUALITY.get(sector, "LISTED_CLEAN")
            to_add.append({
                "ticker": t,
                "isin": "",
                "name": r.get("name", ""),
                "group": "aic_reconcile",
                "catalyst": "STRUCTURAL_DISCOUNT",
                "nav_quality": nav_q,
                "discount_override": "",
                "aic_sector": sector,
                "market_cap_gbp_m": r.get("market_cap_gbp_m", ""),
                "catalyst_date": "",
                "catalyst_source_url": "",
                "notes": "added via reconcile_aic",
            })
    if not to_add:
        return 0
    with open(UNIVERSE, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=UNIVERSE_FIELDS)
        for r in to_add:
            w.writerow(r)
    return len(to_add)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--seed", default=str(US_SEED))
    p.add_argument("--from-aic-reconcile", action="store_true",
                   help="Also pull data/aic_reconcile.csv missing names")
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()
    if args.dry_run:
        # Count what would be added
        seed = Path(args.seed)
        with open(UNIVERSE) as f:
            have = {r["ticker"] for r in csv.DictReader(f)}
        with open(seed) as f:
            new = sum(1 for r in csv.DictReader(f) if r["ticker"] not in have)
        print(f"Would add {new} tickers", file=sys.stderr)
        return 0
    added, existed = merge_seed(Path(args.seed))
    print(f"US seed: added {added}, {existed} already present", file=sys.stderr)
    if args.from_aic_reconcile:
        added2 = expand_from_aic_reconcile()
        print(f"AIC reconcile: added {added2}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
