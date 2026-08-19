"""Auto-tag universe.csv catalyst from RNS history.

Walks data/investegate/*.json and infers a catalyst tag from the RNS
category mix per ticker:

  >=2 winddown filings OR >=2 capdistribution     -> WIND_DOWN_COMMITTED
  >=1 winddown                                    -> WIND_DOWN_LIKELY
  >=2 tender filings                              -> RETURN_OF_CAPITAL_LIVE
  >=1 review + >=1 advisor                        -> STRATEGIC_REVIEW
  >=3 review on its own                           -> STRATEGIC_REVIEW
  >=8 buyback in last 12m + structural-discount   -> DCM_ACTIVE

Only ticks where universe.csv currently has empty / STRUCTURAL_DISCOUNT
get auto-tagged. Existing event tags are preserved. Writes
data/auto_tag_audit.csv with the inferred change for each row.

Apply with --apply; --dry-run is default.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

HERE = Path(os.path.dirname(os.path.abspath(__file__)))
INV_DIR = HERE / "data" / "investegate"
UNIVERSE = HERE / "universe.csv"


def _classify(epic: str) -> tuple[str | None, str]:
    """Return (catalyst_or_None, reason). None means no auto-tag."""
    fp = INV_DIR / f"{epic}.json"
    if not fp.exists():
        return None, "no_rns_data"
    try:
        items = json.loads(fp.read_text())
    except Exception:
        return None, "rns_parse_error"
    # Count per category in last 18 months
    cutoff = datetime.now(timezone.utc) - timedelta(days=540)
    counts: dict[str, int] = {}
    most_recent_date = None
    for a in items:
        d = a.get("date") or ""
        if not d:
            continue
        try:
            dt = datetime.fromisoformat(d).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
        if dt < cutoff:
            continue
        cat = a.get("category", "other")
        counts[cat] = counts.get(cat, 0) + 1
        if most_recent_date is None or d > most_recent_date:
            most_recent_date = d
    wd = counts.get("winddown", 0)
    tender = counts.get("tender", 0)
    review = counts.get("review", 0)
    advisor = counts.get("advisor", 0)
    capdist = counts.get("capdistribution", 0)
    buyback = counts.get("buyback", 0)
    if wd >= 2 or capdist >= 2:
        return "WIND_DOWN_COMMITTED", f"wd={wd},capdist={capdist}"
    if wd >= 1:
        return "WIND_DOWN_LIKELY", f"wd={wd}"
    if tender >= 2:
        return "RETURN_OF_CAPITAL_LIVE", f"tender={tender}"
    if (review >= 1 and advisor >= 1) or review >= 3:
        return "STRATEGIC_REVIEW", f"review={review},advisor={advisor}"
    if buyback >= 8:
        return "DCM_ACTIVE", f"buyback={buyback}"
    return None, "no_signal"


def run(apply: bool) -> int:
    with open(UNIVERSE) as f:
        rows = list(csv.DictReader(f))
    fields = list(rows[0].keys()) if rows else []
    suggestions = []
    for r in rows:
        t = r["ticker"]
        if not t.endswith(".L"):
            continue
        epic = t[:-2].upper()
        current = (r.get("catalyst") or "").strip()
        # Only auto-tag empty / STRUCTURAL_DISCOUNT
        if current and current != "STRUCTURAL_DISCOUNT":
            continue
        new_tag, reason = _classify(epic)
        if new_tag is None or new_tag == current:
            continue
        suggestions.append({
            "ticker": t,
            "name": r.get("name", ""),
            "from": current or "(empty)",
            "to": new_tag,
            "reason": reason,
        })
    print(f"{len(suggestions)} auto-tag suggestions", file=sys.stderr)
    out_path = HERE / "data" / "auto_tag_audit.csv"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["ticker", "name", "from", "to", "reason"])
        w.writeheader()
        for s in suggestions:
            w.writerow(s)
    print(f"Wrote {out_path}", file=sys.stderr)
    by_target = {}
    for s in suggestions:
        by_target.setdefault(s["to"], []).append(s["ticker"])
    print("\nBy target catalyst:", file=sys.stderr)
    for tag, ts in sorted(by_target.items(), key=lambda kv: -len(kv[1])):
        print(f"  {tag:<28} {len(ts):>3}  e.g. {', '.join(ts[:5])}", file=sys.stderr)

    if not apply:
        print("\nRun with --apply to update universe.csv", file=sys.stderr)
        return 0

    by_ticker = {s["ticker"]: s["to"] for s in suggestions}
    for r in rows:
        if r["ticker"] in by_ticker:
            r["catalyst"] = by_ticker[r["ticker"]]
            existing_notes = (r.get("notes") or "").strip()
            note = "auto-tagged from RNS"
            if note not in existing_notes:
                r["notes"] = (existing_notes + "; " + note).strip("; ")
    with open(UNIVERSE, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow(r)
    print(f"Applied {len(suggestions)} updates to {UNIVERSE}", file=sys.stderr)
    return 0


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--apply", action="store_true")
    args = p.parse_args()
    return run(apply=args.apply)


if __name__ == "__main__":
    sys.exit(main())
