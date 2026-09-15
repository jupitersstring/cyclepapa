"""Regression tests for the asymmetry-assembly conjunction engine.

The load-bearing test: the engine must flag May-2024 PSIX (the recipe's
worked example) as a full assembly. If a future change breaks that, the
engine no longer detects the pattern it exists to detect.
"""
from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from asymmetry_assembly import assemble


def _ledger(**present):
    base = {c: {"present": False} for c in [
        "C1_low_expectations","C2_leveraged_survivor","C3_orphaned_drawdown",
        "C4_revealed_insider","C5_recognition_catalyst","C6_operating_inflection",
        "C7_deleveraging","C8_underused_capacity"]}
    for k, v in present.items():
        base[k] = {"present": v}
    base["C9_revealed_events"] = {"present": False, "pro": [], "counter": []}
    return base


# --- the spine gate ---------------------------------------------------
# cheap + engine + costly-action all present -> fires
full = _ledger(C1_low_expectations=True, C2_leveraged_survivor=True,
               C6_operating_inflection=True, C4_revealed_insider=True,
               C7_deleveraging=True)
r = assemble(full)
assert r["spine_met"], "spine should be met"
assert r["score"] > 0, "full spine scores > 0"

# cheap + engine but NO costly action -> gated to 0 (a candidate, not an assembly)
no_costly = _ledger(C1_low_expectations=True, C6_operating_inflection=True,
                     C2_leveraged_survivor=True)
r0 = assemble(no_costly)
assert not r0["spine_met"] and r0["score"] == 0.0, "no costly action -> 0"

# cheap + insider but NO engine -> gated to 0
no_engine = _ledger(C1_low_expectations=True, C4_revealed_insider=True)
assert assemble(no_engine)["score"] == 0.0, "no engine -> 0"

# not cheap -> gated to 0 even with everything else
no_cheap = _ledger(C2_leveraged_survivor=True, C6_operating_inflection=True,
                   C4_revealed_insider=True)
assert assemble(no_cheap)["score"] == 0.0, "not cheap -> 0"

# convergence bonus: more components -> higher score
few = assemble(_ledger(C1_low_expectations=True, C2_leveraged_survivor=True,
                       C4_revealed_insider=True))
many = assemble(_ledger(C1_low_expectations=True, C2_leveraged_survivor=True,
                        C4_revealed_insider=True, C3_orphaned_drawdown=True,
                        C6_operating_inflection=True, C7_deleveraging=True))
assert many["score"] > few["score"], "convergence raises score"

# counter-signal subtracts
led = _ledger(C1_low_expectations=True, C2_leveraged_survivor=True,
              C4_revealed_insider=True, C6_operating_inflection=True)
led["C9_revealed_events"] = {"present": False, "pro": [],
    "counter": [{"type": "dilutive_refinancing", "strength": "strong"}]}
capped = assemble(led)
assert capped["score"] <= 12.0, "severe dilution counter caps the score (NNBR case)"

print("test_asymmetry_assembly: all assertions passed")
