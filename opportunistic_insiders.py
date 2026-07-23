"""Cohen-Malloy-Pomorski opportunistic-vs-routine insider classifier.

NBER w16454 (Cohen, Malloy, Pomorski, JF 2012): the abnormal-return
informativeness of insider purchases is concentrated in OPPORTUNISTIC
filers (~10%/year alpha) -- those who DON'T trade the same calendar
month each year. ROUTINE filers (same-month-every-year for 3+ years)
have approximately zero predictive content.

This module reads form4_buys.json (which lists every Form 4 buy per
ticker with person + filing date), builds a per-PERSON history across
the whole universe, classifies each person as ROUTINE or OPPORTUNISTIC,
then re-aggregates per-ticker counts of opportunistic vs routine buyers.

Output: opportunistic_insiders.json
  per-ticker structure:
    {
      "n_opportunistic_buyers": int,
      "n_routine_buyers": int,
      "opportunistic_dollar": float,
      "routine_dollar": float,
      "score": float    # weighted score
    }

ADDITIVE: does not modify form4_buys.json. The existing F4 scoring
remains intact. The new score is wired as a separate layer in
full_universe_consensus.py.
"""

from __future__ import annotations

import csv
import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path

ROOT = Path("/home/user/cyclepapa")
OUT = ROOT / "opportunistic_insiders.json"


def parse_date(s):
    if not s:
        return None
    try:
        return datetime.strptime(s[:10], "%Y-%m-%d")
    except Exception:
        return None


def classify_routine(filings: list[dict]) -> bool:
    """A filer is routine if they have bought in the SAME calendar month
    in at least 3 different years. Per Cohen-Malloy-Pomorski."""
    months_by_year = defaultdict(set)
    for f in filings:
        d = parse_date(f.get("date"))
        if not d:
            continue
        months_by_year[d.month].add(d.year)
    # routine if any single month appears in >=3 distinct years
    for month, years in months_by_year.items():
        if len(years) >= 3:
            return True
    return False


def main() -> int:
    f4 = json.loads((ROOT / "form4_buys.json").read_text())
    print(f"loaded form4_buys: {len(f4)} tickers")

    # Build per-person history across ALL tickers
    person_history = defaultdict(list)  # person -> list of (ticker, filing)
    for tk, rec in f4.items():
        if not isinstance(rec, dict):
            continue
        for fil in (rec.get("filings") or []):
            person = (fil.get("person") or "").strip().upper()
            if not person:
                continue
            person_history[person].append((tk, fil))

    print(f"distinct insiders: {len(person_history)}")

    # Classify each person
    person_class = {}
    for person, fils in person_history.items():
        all_filings = [f for (_, f) in fils]
        is_routine = classify_routine(all_filings)
        person_class[person] = "ROUTINE" if is_routine else "OPPORTUNISTIC"

    n_routine = sum(1 for v in person_class.values() if v == "ROUTINE")
    n_opp = sum(1 for v in person_class.values() if v == "OPPORTUNISTIC")
    print(f"  routine:      {n_routine}")
    print(f"  opportunistic: {n_opp}")

    # Re-aggregate per ticker
    out = {}
    for tk, rec in f4.items():
        if not isinstance(rec, dict):
            continue
        opp_buyers = set()
        routine_buyers = set()
        opp_dollar = 0.0
        routine_dollar = 0.0
        for fil in (rec.get("filings") or []):
            person = (fil.get("person") or "").strip().upper()
            if not person:
                continue
            try:
                d = float(fil.get("dollar") or 0)
            except Exception:
                d = 0.0
            cls = person_class.get(person)
            if cls == "OPPORTUNISTIC":
                opp_buyers.add(person)
                opp_dollar += d
            elif cls == "ROUTINE":
                routine_buyers.add(person)
                routine_dollar += d

        # Score: opportunistic-only weighted, per Cohen-Malloy
        score = 0.0
        n_opp_buyers = len(opp_buyers)
        if n_opp_buyers >= 4:
            score += 25
        elif n_opp_buyers >= 3:
            score += 18
        elif n_opp_buyers >= 2:
            score += 10
        elif n_opp_buyers >= 1:
            score += 5
        if opp_dollar >= 5e6:
            score += 12
        elif opp_dollar >= 1e6:
            score += 6
        # small penalty if mostly routine (signal-dilution)
        if routine_dollar > opp_dollar * 2 and opp_dollar < 1e6:
            score -= 5

        out[tk] = {
            "n_opportunistic_buyers": n_opp_buyers,
            "n_routine_buyers": len(routine_buyers),
            "opportunistic_dollar": round(opp_dollar, 0),
            "routine_dollar": round(routine_dollar, 0),
            "score": round(score, 1),
        }

    OUT.write_text(json.dumps(out, indent=2))
    print(f"\nwrote {OUT} ({len(out)} tickers)")

    # Top 20
    ranked = sorted(out.items(), key=lambda x: -x[1]["score"])
    print(f"\n=== TOP 20 by opportunistic-insider score ===")
    print(f"{'TKR':<8}{'SCR':<6}{'NOPP':<5}{'NROUT':<6}{'OPP$M':<8}{'ROUT$M'}")
    for tk, v in ranked[:20]:
        print(f"{tk:<8}{v['score']:<6}{v['n_opportunistic_buyers']:<5}"
              f"{v['n_routine_buyers']:<6}"
              f"{v['opportunistic_dollar']/1e6:<8.1f}"
              f"{v['routine_dollar']/1e6:<8.1f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
