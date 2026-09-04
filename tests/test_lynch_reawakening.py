"""Regression tests for the Lynch reawakening archetype."""
from __future__ import annotations
import sys, math
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from lynch_reawakening import score_ticker, roc, rsi, squeeze_state
def at(c,l=""):
    if not c: raise AssertionError(f"FAIL {l}")

# ROC + RSI primitives
at(abs(roc([100,110],1)-0.1)<1e-9, "roc 10%")
at(roc([100],1) is None, "roc insufficient -> None")
at(rsi([1,2,3,4,5,6,7,8,9,10,11,12,13,14,15])>90, "rising series high RSI")

# reawakening (dormant 4y then 12mo accelerating) scores well above controls
flat=[9+0.25*math.sin(i/3) for i in range(48)]
awaken=[9*(1.07**k) for k in range(1,13)]
reawaken=score_ticker({"monthly":flat+awaken,"weekly":[]})
steady=score_ticker({"monthly":[10*(1.012**i) for i in range(80)],"weekly":[]})
dead=score_ticker({"monthly":[9+0.2*math.sin(i/4) for i in range(80)],"weekly":[]})
at(reawaken["score"]>=25, "reawakening scores high")
at(steady["score"]==0, "steady uptrend not a reawakening")
at(reawaken["score"]>dead["score"], "reawakening > dead-flat")
at("concentrated in one year" in " ".join(reawaken["flags"]), "concentration flag")

# insufficient history -> zero, no crash
at(score_ticker({"monthly":[1,2,3],"weekly":[]})["score"]==0, "short history safe")
# squeeze primitive returns a tuple, no crash on flat data
r=squeeze_state([10]*40); at(isinstance(r,tuple) and len(r)==3, "squeeze tuple")
print("test_lynch_reawakening: all assertions passed")
