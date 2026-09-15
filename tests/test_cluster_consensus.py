"""Regression test: de-correlated n_effective_firing (audit A2)."""
from __future__ import annotations
import csv, json
from pathlib import Path
ROOT=Path(__file__).parent.parent
def at(c,l=""):
    if not c: raise AssertionError(f"FAIL {l}")
rows=list(csv.DictReader((ROOT/"full_universe_consensus.csv").open()))
at("n_effective_firing" in rows[0], "column present")
# invariant: effective is always <= raw (a subset of confirmations)
viol=[r["ticker"] for r in rows if int(r["n_effective_firing"])>int(r["n_layers_firing"])]
at(not viol, f"eff<=raw for all ({len(viol)} violations)")
# correlated names show a real gap (the whole point)
gaps=[r for r in rows if int(r["n_layers_firing"])-int(r["n_effective_firing"])>=2]
at(len(gaps)>0, "some names have correlated-layer discount")
# cluster map exists and folds the known insider trio into one cluster
eff=json.loads((ROOT/"effective_layers.json").read_text())
trio={"f4_buys_pts","opportunistic_pts","discretionary_conviction_pts"}
at(any(trio.issubset(set(cl)) for cl in eff["clusters"]), "insider trio is one cluster")
print("test_cluster_consensus: all assertions passed")
