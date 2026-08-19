"""Reconcile universe.csv against AIC's live universe.

AIC publishes ~300+ UK closed-end funds; universe.csv may lag this.
This script:
  * lists names in AIC NOT in universe.csv (potential adds)
  * lists names in universe.csv NOT in AIC (delisted? misclassified?)
  * lists names where the universe.csv name disagrees with AIC

Writes data/aic_reconcile.csv with one row per discrepancy and prints
a summary to stderr. Doesn't auto-mutate universe.csv — that's a
human call (you might intentionally exclude some AIC names).
"""
from __future__ import annotations

import argparse
import csv
import os
import sys
from pathlib import Path

import aic_scraper


HERE = Path(os.path.dirname(os.path.abspath(__file__)))


def _read_universe() -> dict[str, dict]:
    out: dict[str, dict] = {}
    with open(HERE / "universe.csv") as f:
        for row in csv.DictReader(f):
            out[row["ticker"]] = row
    return out


def reconcile() -> dict:
    aic = aic_scraper.fetch_aic_summary(use_cache=True)
    universe = _read_universe()
    universe_by_epic = {
        t.replace(".L", "").upper(): row
        for t, row in universe.items() if t.endswith(".L")
    }
    aic_epics = {sym.replace(".L", "").upper(): rec for sym, rec in aic.items()}

    missing_in_universe = []
    for epic, rec in aic_epics.items():
        if epic in universe_by_epic:
            continue
        if rec.get("market_cap_gbp_m") is None or rec["market_cap_gbp_m"] < 5:
            continue   # tiny vehicles — skip
        missing_in_universe.append({
            "ticker": f"{epic}.L",
            "name": rec.get("name") or "",
            "sector": rec.get("sector") or "",
            "market_cap_gbp_m": round(rec.get("market_cap_gbp_m") or 0, 1),
            "discount": round((rec.get("discount") or 0) * 100, 2),
            "discount_3y_avg": round((rec.get("discount_3y_avg") or 0) * 100, 2),
            "dividend_yield_pct": rec.get("dividend_yield_pct") or 0,
        })

    delisted_or_unmatched = []
    for epic, urow in universe_by_epic.items():
        if epic in aic_epics:
            continue
        delisted_or_unmatched.append({
            "ticker": f"{epic}.L",
            "name": urow.get("name") or "",
            "catalyst": urow.get("catalyst") or "",
            "notes": urow.get("notes") or "",
        })

    name_mismatches = []
    for epic, urow in universe_by_epic.items():
        if epic not in aic_epics:
            continue
        u_name = (urow.get("name") or "").strip().lower()
        a_name = (aic_epics[epic].get("name") or "").strip().lower()
        if not u_name or not a_name:
            continue
        # Strict equality is too strict; flag only when no token overlap.
        u_tokens = set(t for t in u_name.split() if len(t) > 3)
        a_tokens = set(t for t in a_name.split() if len(t) > 3)
        if u_tokens and a_tokens and not u_tokens & a_tokens:
            name_mismatches.append({
                "ticker": f"{epic}.L",
                "universe_name": urow.get("name"),
                "aic_name": aic_epics[epic].get("name"),
            })

    return {
        "missing_in_universe": missing_in_universe,
        "delisted_or_unmatched": delisted_or_unmatched,
        "name_mismatches": name_mismatches,
    }


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--out", default=str(HERE / "data" / "aic_reconcile.csv"))
    args = p.parse_args()
    r = reconcile()
    print(f"AIC -> universe missing: {len(r['missing_in_universe'])}", file=sys.stderr)
    print(f"universe -> AIC unmatched: {len(r['delisted_or_unmatched'])}", file=sys.stderr)
    print(f"name mismatches: {len(r['name_mismatches'])}", file=sys.stderr)
    # Write everything as a unified CSV with a 'kind' column
    rows = []
    for x in r["missing_in_universe"]:
        rows.append({**x, "kind": "missing_in_universe"})
    for x in r["delisted_or_unmatched"]:
        rows.append({**x, "kind": "delisted_or_unmatched"})
    for x in r["name_mismatches"]:
        rows.append({**x, "kind": "name_mismatch"})
    if not rows:
        print("Nothing to reconcile.", file=sys.stderr)
        return 0
    cols = sorted({k for r_ in rows for k in r_})
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for r_ in rows:
            w.writerow(r_)
    print(f"Wrote {args.out}", file=sys.stderr)
    # Top missing by widest discount
    miss = sorted(r["missing_in_universe"],
                  key=lambda x: -(x.get("discount") or 0))[:10]
    if miss:
        print("\nTop missing-in-universe by current discount:", file=sys.stderr)
        for m in miss:
            print(f"  {m['ticker']:<10} {m['discount']:>6.2f}%  "
                  f"{m.get('sector','?'):<8}  £{m['market_cap_gbp_m']:>6.0f}m  "
                  f"{m['name']}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
