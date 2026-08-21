"""Regression tests for bounded catalyst decay."""
from __future__ import annotations
import sys
from datetime import datetime, timezone
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
import catalyst_decay as cd

def at(c,l=""):
    if not c: raise AssertionError(f"FAIL {l}")

T=datetime(2026,8,20,tzinfo=timezone.utc)
# bounded: fresh=1.0, decays toward floor, never below, never above
at(cd.decay_multiplier("2026-08-20",180,0.4,T)==1.0, "fresh=1.0")
at(abs(cd.decay_multiplier("2026-02-21",180,0.4,T)-0.7)<0.02, "1 half-life ~0.7")
at(abs(cd.decay_multiplier("2020-01-01",180,0.4,T)-0.4)<0.01, "old -> floor")
at(cd.decay_multiplier(None,180,0.4,T)==1.0, "no date -> 1.0 (no silent penalty)")
at(cd.decay_multiplier("2099-01-01",180,0.4,T)==1.0, "future -> 1.0")
# monotonic decreasing with age
ms=[cd.decay_multiplier(f"2026-0{m}-01",180,0.4,T) for m in (8,6,4,2)]
at(all(ms[i]>=ms[i+1] for i in range(len(ms)-1)), "monotonic decay")
# apply: policy layers decay, non-policy layers unchanged
at(cd.apply("distressed_stub",8.0,"2026-02-01")<8.0, "policy layer decays")
at(cd.apply("psu",30.0,"2020-01-01")==30.0, "non-policy unchanged")
at(cd.apply("distressed_stub",0.0,"2020-01-01")==0.0, "zero stays zero")
# record_date pulls from multiple schemas
at(cd.record_date("x",{"date":"2026-01-01"})=="2026-01-01", "date field")
at(cd.record_date("x",{"events":[{"date":"2026-01-01"},{"date":"2026-03-01"}]})=="2026-03-01", "latest event date")
print("test_catalyst_decay: all assertions passed")
