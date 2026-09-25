"""Regression tests for atomic writes + source-health gate."""
from __future__ import annotations
import sys, json, os, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
import io_util
def at(c,l=""):
    if not c: raise AssertionError(f"FAIL {l}")

# atomic write round-trips and leaves no tmp files
with tempfile.TemporaryDirectory() as d:
    p=Path(d)/"x.json"
    io_util.write_json(p, {"a":1,"b":[2,3]})
    at(json.loads(p.read_text())=={"a":1,"b":[2,3]}, "round-trip")
    at(not [f for f in os.listdir(d) if f.endswith('.tmp')], "no tmp leftover")
    # overwrite is atomic (old readable until swap)
    io_util.write_json(p, {"c":9})
    at(json.loads(p.read_text())=={"c":9}, "overwrite")

# source-health classifies MISSING / EMPTY / MALFORMED / SPARSE distinctly
with tempfile.TemporaryDirectory() as d:
    import io_util as iu
    saved=iu.CONSUMED_SOURCES
    iu.CONSUMED_SOURCES={"good.json":(1,["k"]),"missing.json":(1,[]),
                         "empty.json":(1,[]),"bad.json":(1,[]),"sparse.json":(5,[])}
    Path(d,"good.json").write_text(json.dumps({"x":{"k":1}}))
    Path(d,"empty.json").write_text("")
    Path(d,"bad.json").write_text("{not json")
    Path(d,"sparse.json").write_text(json.dumps({"x":1}))
    probs=iu.check_sources(d)
    joined=" ".join(probs)
    at("MISSING   missing.json" in joined, "missing detected")
    at("EMPTY     empty.json" in joined, "empty detected")
    at("MALFORMED bad.json" in joined, "malformed detected")
    at("SPARSE    sparse.json" in joined, "sparse detected")
    at(not any("good.json" in p for p in probs), "good file clean")
    iu.CONSUMED_SOURCES=saved
print("test_io_util: all assertions passed")
