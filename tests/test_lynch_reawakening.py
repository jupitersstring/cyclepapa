"""Regression tests for the Lynch reawakening archetype (OHLC + squeeze_asym)."""
from __future__ import annotations
import sys, math
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from lynch_reawakening import score_ticker, roc, rsi
def at(c,l=""):
    if not c: raise AssertionError(f"FAIL {l}")
at(abs(roc([100,110],1)-0.1)<1e-9, "roc 10%")
at(roc([100],1) is None, "roc insufficient")

def mk(mc):
    return {"monthly_high":[x*1.01 for x in mc],"monthly_low":[x*0.99 for x in mc],
            "monthly_close":mc}
flat=[9+0.2*math.sin(i/3) for i in range(48)]; awaken=[9*(1.07**k) for k in range(1,13)]
reawaken=score_ticker(mk(flat+awaken))
steady=score_ticker(mk([10*(1.012**i) for i in range(80)]))
dead=score_ticker(mk([9+0.2*math.sin(i/4) for i in range(80)]))
at(reawaken["score"]>=25, "reawakening high")
at(steady["score"] < 12 and "concentrated" not in " ".join(steady["flags"]), "steady is not a reawakening")
at(reawaken["score"]>dead["score"], "reawakening>dead")
at("concentrated in one year" in " ".join(reawaken["flags"]), "concentration flag")
at(score_ticker(mk([1,2,3]))["score"]==0, "short history safe")
# close-only fallback still computes ROC (H=L=C)
at(score_ticker({"monthly":flat+awaken})["score"]>0, "close-only fallback works")
print("test_lynch_reawakening: all assertions passed")
