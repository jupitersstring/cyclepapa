"""Regression tests for net-buyback quality scoring."""
from __future__ import annotations
import sys, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
# validate the live output's invariants (engine ran in this session)
d=json.load(open(Path(__file__).parent.parent/"net_buyback.json"))
def at(c,l=""):
    if not c: raise AssertionError(f"FAIL {l}")
at(len(d)>100, "has results")
# net-shrinking names score positive, diluting names negative
for tk,v in d.items():
    if v["net_buyback_yield"]>=0.10: at(v["score"]>0, f"{tk} shrink->positive")
    if v["net_buyback_yield"]<=-0.10: at(v["score"]<0, f"{tk} dilute->negative")
    # reverse-split guard: no name retained with >=35% reduction
    at(v["net_buyback_yield"]<0.35, f"{tk} split-artifact excluded")
# cheap shrinkers get the cheapness bonus (score 22 tier exists)
at(any(v["score"]>=20 and v.get("cheap") for v in d.values()), "cheap-shrink tier")
# dilution anti-signal present (naive screens miss this)
at(any(v["score"]<0 for v in d.values()), "net dilution penalised")
print("test_net_buyback: all assertions passed")
