"""Regression tests for the selective / own-shares revealed-preference scanner."""
from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from selective_buyback_scan import SELECTIVE, FROM_HOLDER_RX, BELOW_MARKET_RX, PREMIUM_MARKET_RX, _valid

def at(c,l=""):
    if not c: raise AssertionError(f"FAIL {l}")

# selective classes present; block-from-holder is the highest-weighted
w = {cls: pts for _, cls, pts in SELECTIVE}
at(w["block_from_holder"] >= max(w[c] for c in w if c not in ("block_from_holder",)), "block-from-holder highest")
# routine ASR is DOWN-weighted vs genuine selective classes
at(w["asr"] < w["privately_negotiated"], "ASR < privately negotiated")
at(w["repurchase_agreement"] < w["dutch_auction"], "generic agreement < dutch auction")

# block-from-holder detection
at(FROM_HOLDER_RX.search("the Company agreed to repurchase 2,000,000 shares from Starboard Value LP"), "from holder")
at(not FROM_HOLDER_RX.search("the Company will repurchase shares in the open market"), "open market not a block")

# opportunistic pricing (discount good, premium less revealing)
at(BELOW_MARKET_RX.search("the shares were repurchased at a discount to the closing price"), "discount")
at(PREMIUM_MARKET_RX.search("repurchased at a premium to market"), "premium")

at(_valid("ZIP") and not _valid("NONE"), "ticker gate")
print("test_selective_buyback: all assertions passed")
