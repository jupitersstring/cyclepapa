"""Curated list of UK investment trusts in or near managed wind-down.

These are the highest-prior candidates for the RSE-pattern accumulation
scan: trusts whose boards have either (i) put a continuation vote in
flight, (ii) commenced a realisation portfolio, (iii) announced an
orderly disposal/wind-down, or (iv) trade at deep discounts to NAV
where activist pressure typically forces the action.
"""

WIND_DOWN_UNIVERSE: dict[str, dict] = {
    # Already in managed wind-down or realisation
    "RSE.L":   {"name": "Riverstone Energy",          "status": "wind_down"},
    "DGI9.L":  {"name": "Digital 9 Infrastructure",   "status": "wind_down"},
    "HVPE.L":  {"name": "HarbourVest Global PE",      "status": "buyback"},
    "RGL.L":   {"name": "Regional REIT",              "status": "review"},
    "NESF.L":  {"name": "NextEnergy Solar",           "status": "review"},
    "HGT.L":   {"name": "HG Capital Trust",           "status": "buyback"},
    "ICGT.L":  {"name": "ICG Enterprise Trust",       "status": "buyback"},
    "PIN.L":   {"name": "Pantheon Infrastructure",    "status": "review"},
    "BCPT.L":  {"name": "Balanced Commercial Property", "status": "wind_down"},
    "BPM.L":   {"name": "B.P. Marsh & Partners",      "status": "private"},
    "GROW.L":  {"name": "Molten Ventures",            "status": "discount"},
    "AUGM.L":  {"name": "Augmentum Fintech",          "status": "discount"},
    "BSIF.L":  {"name": "Bluefield Solar Income",     "status": "discount"},
    "TRIG.L":  {"name": "TR European Growth Trust",   "status": "review"},
    "JEMI.L":  {"name": "JPMorgan Global EM Income",  "status": "discount"},
    "PSDL.L":  {"name": "Phoenix Spree Deutschland",  "status": "review"},
    "EAT.L":   {"name": "European Assets Trust",      "status": "discount"},
    "TENT.L":  {"name": "Triple Point Energy Transition", "status": "review"},
    "JLEN.L":  {"name": "JLEN Environmental Assets",  "status": "discount"},
    "NESS.L":  {"name": "Nesf SDG Wind",              "status": "discount"},
    "GHE.L":   {"name": "Gresham House Energy Storage", "status": "discount"},
    "GSF.L":   {"name": "Gore Street Energy Storage", "status": "discount"},
    # US closed-end funds with similar dynamics (NAV discount + activists)
    "SRH":     {"name": "DWS Strategic Munis",        "status": "discount"},
    "BTZ":     {"name": "BlackRock Credit Allocation","status": "discount"},
    "WMK":     {"name": "Weis Markets",               "status": "discount"},  # not a CEF -- placeholder
}
