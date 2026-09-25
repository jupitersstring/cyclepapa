"""Patch the risk-reward engine's build_workbook.py INSIDE the temporary
worktree only (the engine's branch is never modified), so the book reflects
the FMP overlay:
  * coverage-gap list and header counts know the FMP source,
  * cover bullet: portfolio weights are stored in PERCENT (3.00 = 3%), so the
    engine's `invested*100` printed 6002% of NAV -- normalised here,
  * cover universe count read from the ranked file instead of a hard-coded 697.
Each patch is applied only if its anchor text is found; misses are reported.
"""
import sys
from pathlib import Path

wt = Path(sys.argv[1])
p = wt / "src" / "build_workbook.py"
s = p.read_text()
patches = [
    ('if r["source"] == "PROXY"][:20]', 'if r["source"] != "REAL"][:20]'),
    ('"PROXY).  REAL uses',
     "f\"PROXY · {sum(1 for r in universe_rr if r['source']=='FMP')} FMP market-data).  REAL uses"),
    ('    invested = sum(w["weight"] for w in weights.values())',
     '    invested_raw = sum(w["weight"] for w in weights.values())\n'
     '    invested = invested_raw / 100.0 if invested_raw > 1.5 else invested_raw  # weights in percent'),
    ('for w in weights.values()) / max(invested, 0.01)',
     'for w in weights.values()) / max(invested_raw, 0.01)'),
    ('("Universe coverage: 697 named candidates screened quantitatively; "',
     '(f"Universe coverage: {sum(1 for _ in open(UNIVERSE_RR_CSV)) - 1} named candidates screened quantitatively; "'),
]
missed = []
for a, b in patches:
    if a in s:
        s = s.replace(a, b)
    else:
        missed.append(a[:50])
p.write_text(s)
print(f"engine patches: {len(patches) - len(missed)}/{len(patches)} applied" +
      (f"; missed: {missed}" if missed else ""))
