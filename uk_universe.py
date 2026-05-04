"""Curated UK (LSE main market + AIM) universe for systematic screening.

UK doesn't have an EDGAR-equivalent JSON API for proxy / 8-K text, so
the screener relies on yfinance fundamentals (.L suffix works) plus
Companies House for filing-history metadata. Activist / RSA / Rule-2.x
text-level signals require an RNS scrape that's not in scope here --
the universe is large enough that fundamentals + sector tailwind tags
already produce a meaningful ranking; the user's named picks below act
as ground truth for spot-checking.
"""

from __future__ import annotations

# Curated universe. Sector tags drive the policy / tailwind overlay:
#   ASSETMGR  - asset managers (Liontrust thesis: M&A at % AUM multiple)
#   DEFENCE   - UK defence + BAE / Chemring / QinetiQ etc.
#   BUILD     - building / construction products
#   MEDTECH   - AIM medtech + diagnostics
#   ENERGY    - North Sea oil / gas + utilities
#   OUTSOURCE - Capita / Serco / Mitie style outsourcers
#   MARINE    - marine engineering / shipping
#   FIN       - UK banks + insurers
#   RETAIL    - UK retailers
#   INDUST    - general industrials
#   CONSUMER  - consumer staples / discretionary
#   TECH      - software / tech
#   PROP      - REITs / property
#   MEDIA     - publishing / broadcasting
#   SPECIAL   - special-situation names called out by the user

UK_UNIVERSE: dict[str, dict] = {
    # User's named picks (Cat A-E from the message)
    "LIO.L":   {"sector": "ASSETMGR",  "name": "Liontrust Asset Management",            "tag": "user_pick_A"},
    "APTD.L":  {"sector": "TECH",      "name": "Aptitude Software",                     "tag": "user_pick_A"},
    "FSJ.L":   {"sector": "MARINE",    "name": "James Fisher & Sons",                   "tag": "user_pick_B"},
    "CPI.L":   {"sector": "OUTSOURCE", "name": "Capita",                                "tag": "user_pick_B"},
    "NXR.L":   {"sector": "BUILD",     "name": "Norcros",                               "tag": "user_pick_C"},
    "MGAM.L":  {"sector": "INDUST",    "name": "Morgan Advanced Materials",             "tag": "user_pick_C"},
    "SQZ.L":   {"sector": "ENERGY",    "name": "Serica Energy",                         "tag": "user_pick_D"},
    "TSTL.L":  {"sector": "MEDTECH",   "name": "Tristel",                               "tag": "user_pick_E"},
    "AMS.L":   {"sector": "MEDTECH",   "name": "Advanced Medical Solutions",            "tag": "user_pick_E"},

    # FTSE 100 / 250 — defensives and special-situation candidates
    "BA.L":    {"sector": "DEFENCE",   "name": "BAE Systems"},
    "BAB.L":   {"sector": "DEFENCE",   "name": "Babcock International"},
    "QQ.L":    {"sector": "DEFENCE",   "name": "QinetiQ"},
    "CHG.L":   {"sector": "DEFENCE",   "name": "Chemring"},
    "RR.L":    {"sector": "DEFENCE",   "name": "Rolls-Royce Holdings"},
    "MGGT.L":  {"sector": "DEFENCE",   "name": "Meggitt"},

    # Asset managers (M&A heuristic = % of AUM)
    "ABDN.L":  {"sector": "ASSETMGR",  "name": "abrdn"},
    "JUP.L":   {"sector": "ASSETMGR",  "name": "Jupiter Fund Management"},
    "SDR.L":   {"sector": "ASSETMGR",  "name": "Schroders"},
    "SLA.L":   {"sector": "ASSETMGR",  "name": "Standard Life Aberdeen"},
    "RAT.L":   {"sector": "ASSETMGR",  "name": "Rathbones"},
    "BRW.L":   {"sector": "ASSETMGR",  "name": "Brewin Dolphin"},
    "MAN.L":   {"sector": "ASSETMGR",  "name": "Man Group"},
    "POLR.L":  {"sector": "ASSETMGR",  "name": "Polar Capital"},
    "PSN.L":   {"sector": "ASSETMGR",  "name": "Persimmon"},  # mis-tagged actually housebuilder
    "QLT.L":   {"sector": "ASSETMGR",  "name": "Quilter"},
    "IPX.L":   {"sector": "ASSETMGR",  "name": "Impax Asset Management"},
    "ASHM.L":  {"sector": "ASSETMGR",  "name": "Ashmore Group"},
    "CLIG.L":  {"sector": "ASSETMGR",  "name": "City of London Investment"},
    "MGNS.L":  {"sector": "ASSETMGR",  "name": "Morgan Sindall"},  # mis-tag

    # UK outsourcers / service holdcos
    "SRP.L":   {"sector": "OUTSOURCE", "name": "Serco Group"},
    "MTO.L":   {"sector": "OUTSOURCE", "name": "Mitie Group"},
    "RTO.L":   {"sector": "OUTSOURCE", "name": "Rentokil Initial"},
    "INF.L":   {"sector": "OUTSOURCE", "name": "Informa"},

    # UK banks & insurers
    "LLOY.L":  {"sector": "FIN",       "name": "Lloyds Banking Group"},
    "NWG.L":   {"sector": "FIN",       "name": "NatWest Group"},
    "BARC.L":  {"sector": "FIN",       "name": "Barclays"},
    "HSBA.L":  {"sector": "FIN",       "name": "HSBC Holdings"},
    "STAN.L":  {"sector": "FIN",       "name": "Standard Chartered"},
    "VMUK.L":  {"sector": "FIN",       "name": "Virgin Money UK"},
    "AV.L":    {"sector": "FIN",       "name": "Aviva"},
    "LGEN.L":  {"sector": "FIN",       "name": "Legal & General"},
    "PRU.L":   {"sector": "FIN",       "name": "Prudential"},
    "DLG.L":   {"sector": "FIN",       "name": "Direct Line Insurance"},
    "ADM.L":   {"sector": "FIN",       "name": "Admiral Group"},
    "BGEO.L":  {"sector": "FIN",       "name": "Bank of Georgia"},

    # Energy / North Sea
    "HBR.L":   {"sector": "ENERGY",    "name": "Harbour Energy"},
    "ENOG.L":  {"sector": "ENERGY",    "name": "Energean"},
    "ITH.L":   {"sector": "ENERGY",    "name": "Ithaca Energy"},
    "TLW.L":   {"sector": "ENERGY",    "name": "Tullow Oil"},
    "CNE.L":   {"sector": "ENERGY",    "name": "Capricorn Energy"},
    "ENQ.L":   {"sector": "ENERGY",    "name": "EnQuest"},
    "BP.L":    {"sector": "ENERGY",    "name": "BP"},
    "SHEL.L":  {"sector": "ENERGY",    "name": "Shell"},
    "DRX.L":   {"sector": "ENERGY",    "name": "Drax Group"},
    "SSE.L":   {"sector": "ENERGY",    "name": "SSE"},
    "CNA.L":   {"sector": "ENERGY",    "name": "Centrica"},

    # Building / construction products
    "TYMN.L":  {"sector": "BUILD",     "name": "Tyman"},
    "FORT.L":  {"sector": "BUILD",     "name": "Forterra"},
    "IBST.L":  {"sector": "BUILD",     "name": "Ibstock"},
    "BREE.L":  {"sector": "BUILD",     "name": "Breedon Group"},
    "MMH.L":   {"sector": "BUILD",     "name": "Marshalls"},
    "GFRD.L":  {"sector": "BUILD",     "name": "Galliford Try"},
    "VTY.L":   {"sector": "BUILD",     "name": "Vistry Group"},
    "BWY.L":   {"sector": "BUILD",     "name": "Bellway"},
    "TW.L":    {"sector": "BUILD",     "name": "Taylor Wimpey"},
    "BDEV.L":  {"sector": "BUILD",     "name": "Barratt Developments"},
    "RDW.L":   {"sector": "BUILD",     "name": "Redrow"},

    # AIM medtech
    "PCIP.L":  {"sector": "MEDTECH",   "name": "PCI-Pal"},
    "VRP.L":   {"sector": "MEDTECH",   "name": "Verici Dx"},
    "GEN.L":   {"sector": "MEDTECH",   "name": "Genus"},
    "SBT.L":   {"sector": "MEDTECH",   "name": "Smith & Nephew"},
    "DPLM.L":  {"sector": "MEDTECH",   "name": "Diploma"},
    "RNK.L":   {"sector": "MEDTECH",   "name": "Rank Group"},  # mis-tag
    "TRX.L":   {"sector": "MEDTECH",   "name": "Tissue Regenix"},
    "EKT.L":   {"sector": "MEDTECH",   "name": "Eckoh"},

    # Marine / industrials
    "WG.L":    {"sector": "MARINE",    "name": "John Wood Group"},
    "PFC.L":   {"sector": "MARINE",    "name": "Petrofac"},
    "HBR.L":   {"sector": "MARINE",    "name": "Harbour Energy"},

    # AIM / mid-cap special situations
    "BOY.L":   {"sector": "SPECIAL",   "name": "Bodycote"},
    "VCT.L":   {"sector": "SPECIAL",   "name": "Victrex"},
    "ABF.L":   {"sector": "SPECIAL",   "name": "Associated British Foods"},
    "STJ.L":   {"sector": "SPECIAL",   "name": "St. James's Place"},
    "WEIR.L":  {"sector": "SPECIAL",   "name": "Weir Group"},
    "MRO.L":   {"sector": "SPECIAL",   "name": "Melrose Industries"},
    "SMIN.L":  {"sector": "SPECIAL",   "name": "Smiths Group"},
    "VOD.L":   {"sector": "SPECIAL",   "name": "Vodafone"},
    "BT-A.L":  {"sector": "SPECIAL",   "name": "BT Group"},

    # Retail
    "MKS.L":   {"sector": "RETAIL",    "name": "Marks & Spencer"},
    "NXT.L":   {"sector": "RETAIL",    "name": "Next"},
    "JDW.L":   {"sector": "RETAIL",    "name": "JD Wetherspoon"},
    "JD.L":    {"sector": "RETAIL",    "name": "JD Sports"},
    "ASC.L":   {"sector": "RETAIL",    "name": "ASOS"},
    "BOO.L":   {"sector": "RETAIL",    "name": "boohoo"},
    "OCDO.L":  {"sector": "RETAIL",    "name": "Ocado"},
    "DUNM.L":  {"sector": "RETAIL",    "name": "Dunelm"},
    "GRG.L":   {"sector": "RETAIL",    "name": "Greggs"},
    "BME.L":   {"sector": "RETAIL",    "name": "B&M European Value Retail"},

    # Consumer / media
    "ITV.L":   {"sector": "MEDIA",     "name": "ITV"},
    "RMV.L":   {"sector": "MEDIA",     "name": "Rightmove"},
    "AUTO.L":  {"sector": "MEDIA",     "name": "Auto Trader Group"},
    "RELX.L":  {"sector": "MEDIA",     "name": "RELX"},
    "PSON.L":  {"sector": "MEDIA",     "name": "Pearson"},
    "WPP.L":   {"sector": "MEDIA",     "name": "WPP"},
    "BVIC.L":  {"sector": "CONSUMER",  "name": "Britvic"},
    "ULVR.L":  {"sector": "CONSUMER",  "name": "Unilever"},
    "DGE.L":   {"sector": "CONSUMER",  "name": "Diageo"},
    "RKT.L":   {"sector": "CONSUMER",  "name": "Reckitt Benckiser"},
    "TATE.L":  {"sector": "CONSUMER",  "name": "Tate & Lyle"},

    # REITs / property
    "LAND.L":  {"sector": "PROP",      "name": "Land Securities"},
    "BLND.L":  {"sector": "PROP",      "name": "British Land"},
    "BBOX.L":  {"sector": "PROP",      "name": "Tritax Big Box REIT"},
    "SHB.L":   {"sector": "PROP",      "name": "Shaftesbury Capital"},
    "SGRO.L":  {"sector": "PROP",      "name": "SEGRO"},
    "DLN.L":   {"sector": "PROP",      "name": "Derwent London"},
    "GPE.L":   {"sector": "PROP",      "name": "Great Portland Estates"},
    "PHP.L":   {"sector": "PROP",      "name": "Primary Health Properties"},
    "ASLI.L":  {"sector": "PROP",      "name": "abrdn European Logistics Income"},

    # Tech
    "AVST.L":  {"sector": "TECH",      "name": "Avast"},
    "AVV.L":   {"sector": "TECH",      "name": "AVEVA"},
    "MCRO.L":  {"sector": "TECH",      "name": "Micro Focus"},
    "CCC.L":   {"sector": "TECH",      "name": "Computacenter"},
    "SOPH.L":  {"sector": "TECH",      "name": "Sophos"},
    "BCG.L":   {"sector": "TECH",      "name": "Baltic Classifieds"},
    "GAW.L":   {"sector": "TECH",      "name": "Games Workshop"},
    "DARK.L":  {"sector": "TECH",      "name": "Darktrace"},
    "KNOS.L":  {"sector": "TECH",      "name": "Kainos Group"},

    # Misc industrials / special
    "ULE.L":   {"sector": "INDUST",    "name": "Ultra Electronics"},
    "ROR.L":   {"sector": "INDUST",    "name": "Rotork"},
    "SPX.L":   {"sector": "INDUST",    "name": "Spirax-Sarco Engineering"},
    "BUR.L":   {"sector": "INDUST",    "name": "Burford Capital"},
    "HSV.L":   {"sector": "INDUST",    "name": "Homeserve"},
    "MSLH.L":  {"sector": "INDUST",    "name": "Marlowe"},
    "RWS.L":   {"sector": "INDUST",    "name": "RWS Holdings"},
}


def by_sector() -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for tk, meta in UK_UNIVERSE.items():
        out.setdefault(meta["sector"], []).append(tk)
    return out
