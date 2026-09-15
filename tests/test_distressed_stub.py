"""Regression tests for the distressed-stub progress engine."""
from __future__ import annotations
import sys, re
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from distressed_stub_progress import classify, FINALITY_VERBS, SOFT_VERBS, COUNTERS

def aeq(a,b,l=""):
    if a!=b: raise AssertionError(f"FAIL {l}: {a!r} != {b!r}")
def at(c,l=""):
    if not c: raise AssertionError(f"FAIL {l}")

# classification bands (spec §8)
aeq(classify(9), "hard_value_unlock", "8+")
aeq(classify(5), "real_progress_conditional", "4-7")
aeq(classify(2), "survival_or_process_only", "1-3")
aeq(classify(-3), "delay_or_value_transfer_away", "<=0")

# finality vs soft verbs
at(FINALITY_VERBS.search("the notes were cancelled and extinguished"), "finality fires")
at(FINALITY_VERBS.search("the company emerged from Chapter 11"), "emerged fires")
at(SOFT_VERBS.search("the company intends to explore a refinancing"), "soft fires")
at(not FINALITY_VERBS.search("the company is in discussions"), "no false finality")

# counter-signals detect stub-negative events
cmap = {name: rx for name, pen, rx in COUNTERS}
at(cmap["equity_wipeout"].search("existing equity shall be cancelled with no recovery"), "wipeout")
at(cmap["priming_superpriority"].search("a superpriority DIP facility was approved"), "priming")
at(cmap["toxic_dilution"].search("convertible at a variable conversion price"), "toxic")
# penalties are negative
pens = {name: pen for name, pen, rx in COUNTERS}
at(pens["equity_wipeout"] <= -10, "wipeout is the heaviest penalty")
at(all(p < 0 for p in pens.values()), "all counters negative")

print("test_distressed_stub: all assertions passed")
