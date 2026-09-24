"""Recent GOVERNANCE CHANGES from 8-K filings (dated).

Proxies are annual; the governance changes that signal "the board is about
to do something about the discount" are announced by 8-K as they happen:
an activist cooperation/nomination agreement, a new CEO, the chair/CEO roles
split, the board declassified, a strategic-review or capital-allocation
committee formed, a poison pill terminated, a capital-return policy adopted.
This scanner finds them via EDGAR full-text search over a recent window and
keeps the most recent date per family. Consumed by governance_discount.py.

Output: governance_events_8k.json {ticker: {family: {date, phrase}}}.
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

import io_util
from rerate_events_8k import efts
from universe_filter import is_excluded

ROOT = Path("/home/user/cyclepapa")
OUT = ROOT / "governance_events_8k.json"

PHRASES = [
    # activist settlement -- the board has conceded seats / terms
    ("cooperation agreement", "ACTIVIST_SETTLEMENT"),
    ("nomination agreement", "ACTIVIST_SETTLEMENT"),
    ("standstill agreement", "ACTIVIST_SETTLEMENT"),
    # committees formed to act on value
    ("strategic review committee", "VALUE_COMMITTEE"),
    ("strategic alternatives committee", "VALUE_COMMITTEE"),
    ("capital allocation committee", "VALUE_COMMITTEE"),
    ("strategic review process", "VALUE_COMMITTEE"),
    # capital-return policy
    ("capital return program", "CAPITAL_RETURN_POLICY"),
    ("return excess capital", "CAPITAL_RETURN_POLICY"),
    ("return capital to shareholders", "CAPITAL_RETURN_POLICY"),
    ("modified dutch auction", "CAPITAL_RETURN_POLICY"),
    # leadership change
    ("appointed Chief Executive Officer", "CEO_CHANGE"),
    ("named Chief Executive Officer", "CEO_CHANGE"),
    ("interim Chief Executive Officer", "CEO_CHANGE"),
    # board structure
    ("separate the roles of Chair", "CHAIR_CEO_SPLIT"),
    ("separate the roles of Chairman", "CHAIR_CEO_SPLIT"),
    ("independent Chair of the Board", "CHAIR_CEO_SPLIT"),
    ("declassify the Board", "DECLASSIFY"),
    ("declassification of the Board", "DECLASSIFY"),
    ("increase the size of the Board", "BOARD_REFRESH"),
    ("board refreshment", "BOARD_REFRESH"),
    # defences removed
    ("terminate the rights agreement", "PILL_REMOVED"),
    ("redeem the rights", "PILL_REMOVED"),
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=450)
    ap.add_argument("--cap", type=int, default=80)
    ap.add_argument("--sleep", type=float, default=0.15)
    args = ap.parse_args()
    end = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    start = (datetime.now(timezone.utc) - timedelta(days=args.days)).strftime("%Y-%m-%d")
    print(f"8-K governance-change sweep {start}..{end} ({len(PHRASES)} phrases)",
          file=sys.stderr)
    per: dict[str, dict] = {}
    for phrase, fam in PHRASES:
        hits = efts(phrase, start, end, cap=args.cap)
        time.sleep(args.sleep)
        for h in hits:
            tk, dt = h["ticker"].upper(), h["date"]
            if not dt or is_excluded(tk)[0]:
                continue
            cur = per.setdefault(tk, {}).get(fam)
            if not cur or dt > cur["date"]:
                per[tk][fam] = {"date": dt, "phrase": phrase}
        print(f"  {fam:<22} '{phrase}': {len(hits)}", file=sys.stderr)
    io_util.write_json(OUT, per)
    from collections import Counter
    c = Counter(f for r in per.values() for f in r)
    print(f"wrote {OUT} ({len(per)} names with a recent governance change)")
    for f, n in c.most_common():
        print(f"  {f:<22} {n}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
