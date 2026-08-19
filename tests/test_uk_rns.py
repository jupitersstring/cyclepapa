"""Regression tests for the UK RNS monitor."""
from __future__ import annotations
import sys, re
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from uk_rns_scan import ANN_RX, classify, FUND_RX, HEADLINE_MAP

def at(c,l=""):
    if not c: raise AssertionError(f"FAIL {l}")

# URL parsing extracts ticker + headline (incl. triple-dash names)
m = ANN_RX.search("/announcement/rns/henderson-far-east-income-ltd---hfel/issue-of-equity/9730621")
at(m and m.group(3)=="hfel" and m.group(4)=="issue-of-equity", "triple-dash parse")
m = ANN_RX.search("/announcement/rns/moneysupermarket-com-group--mony/transaction-in-own-shares/9730604")
at(m and m.group(3)=="mony", "standard parse")

# classification: distressed/selective outrank routine buybacks
f,c,p = classify("scheme-of-arrangement")
at(f=="distressed" and p>=10, "scheme high")
f,c,p = classify("tender-offer")
at(f=="own_shares" and p>=12, "tender high")
f,c,p = classify("transaction-in-own-shares")
at(f=="own_shares" and p<=4, "routine buyback low")
f,c,p = classify("strategic-investment")
at(f=="issuance" and p>=12, "strategic investment high")
at(classify("director-pdmr-shareholding")[0] is None, "non-recipe ignored")

# fund filter catches sponsor-branded trusts even when name truncated
at(FUND_RX.search("jpmorgan-emerging-market"), "jpmorgan trust")
at(FUND_RX.search("alliance-witan"), "witan trust")
at(FUND_RX.search("fidelity-china-special-s"), "fidelity trust")
at(not FUND_RX.search("moneysupermarket-com-group"), "operating co not a fund")
at(not FUND_RX.search("rtc-group"), "rtc not a fund")

# UK vocabulary coverage (spec jurisdiction terms)
classes = {c for _,_,c,_ in HEADLINE_MAP}
for c in ("scheme_of_arrangement","part26a_plan","cva","tender_offer","transaction_own_shares"):
    at(c in classes, f"UK class {c} present")
print("test_uk_rns: all assertions passed")
