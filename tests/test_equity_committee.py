"""Regression tests for the equity-committee scanner."""
from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from equity_committee_scan import PHRASES, DENIAL_RX, _valid
def at(c,l=""):
    if not c: raise AssertionError(f"FAIL {l}")
# only bankruptcy-unambiguous phrases (no bare 'equity committee')
cls={c for _,c,_ in PHRASES}
at("official_equity_committee" in cls, "official phrase present")
at(not any("mention" in c for c in cls), "ambiguous bare mention excluded")
at(all(p>=15 for _,_,p in PHRASES), "all phrases high-signal weighted")
# denial detection (a denied motion must be catchable)
at(DENIAL_RX.search("the court denied the motion to appoint an equity committee"), "denial fires")
at(DENIAL_RX.search("motion for an official committee of equity security holders was denied"), "denial variant")
at(not DENIAL_RX.search("the official committee of equity security holders was appointed"), "appointment not a denial")
at(_valid("WW") and not _valid("NONE"), "ticker gate")
print("test_equity_committee: all assertions passed")
