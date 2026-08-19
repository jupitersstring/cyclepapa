"""Regression tests for the hidden-asset / credit-agreement engine."""
from __future__ import annotations
import sys, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from credit_agreement_mine import MANDATORY_PREPAY_RX, HIDDEN_ASSETS, _valid

def at(c,l=""):
    if not c: raise AssertionError(f"FAIL {l}")

# the mandatory-prepayment structure (the SSP mechanism) must match
at(MANDATORY_PREPAY_RX.search(
   "substantially 100% of the net cash proceeds of any disposition shall be "
   "applied as a mandatory prepayment of the term loans"), "SSP-style sweep")
at(MANDATORY_PREPAY_RX.search(
   "net cash proceeds from asset sales will be used to prepay the loans"), "prepay variant")
at(not MANDATORY_PREPAY_RX.search(
   "the company may reinvest proceeds at its discretion"), "no false positive")

# hidden-asset table carries spectrum + rights classes with points
atypes = {a for _, a, _, _ in HIDDEN_ASSETS}
for a in ("spectrum", "water_rights", "mineral_rights", "broadcast_licences"):
    at(a in atypes, f"{a} present")
at(all(p > 0 for _, _, _, p in HIDDEN_ASSETS), "all asset points positive")
cats = {c for _, _, c, _ in HIDDEN_ASSETS}
for c in ("telecom","resources","energy","real_estate","financials","healthcare","tech","holdco","any"):
    at(c in cats, f"industry category {c} covered")

# ticker gate
at(_valid("SSP") and _valid("EVC"), "valid tickers")
at(not _valid("NONE"), "junk rejected")

# curated watch seeds SSP with the credit-agreement feature
w = json.loads((Path(__file__).parent.parent / "hidden_asset_watch.json").read_text())
at("SSP" in w and "spectrum" in (w["SSP"]["hidden_asset"].lower()), "SSP watch seeded")
at("mandatory" in w["SSP"]["credit_agreement_feature"].lower(), "SSP prepay feature documented")

print("test_hidden_asset: all assertions passed")
