"""Regression tests for the Pine-faithful squeeze_asym port."""
from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
import squeeze_asym as sa
def at(c,l=""):
    if not c: raise AssertionError(f"FAIL {l}")
# EMA seeding matches Pine (seed=first, alpha=2/(n+1))
at([round(x,3) for x in sa.ema([1,2,3,4],3)]==[1,1.5,2.25,3.125], "ema seed/alpha")
# true range first bar = high-low
at(sa.true_range([10,12,11],[8,9,9],[9,11,10])==[2,3,2], "tr first bar h-l")
# roc percent
at(sa.roc([100,110,121],1)==[None,10.0,10.0], "roc percent")
# rising strictly increasing
at(sa.rising([1,2,3,4],3,3) and not sa.rising([1,2,2,4],3,3), "rising strict")
# compute returns full state on adequate series; None if too short
import math
c=[100+0.4*math.sin(i/3) for i in range(60)]
h=[x*1.01 for x in c]; l=[x*0.99 for x in c]
r=sa.compute(h,l,c)
at(r is not None and r["state"] in ("squeeze","release"), "state present")
at("asymmetry" in r and 0<=r["asymmetry"]<=100, "asymmetry 0-100")
at(sa.compute([1,2,3],[1,2,3],[1,2,3]) is None, "too-short -> None")
print("test_squeeze_asym: all assertions passed")
