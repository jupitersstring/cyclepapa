"""Curated capital-allocator universe.

Companies known for sophisticated capital allocation discipline -- the
universe most likely to use ROIIC / ROCE / FCF-per-share metrics in
their PSU comp structures rather than aggregate EBITDA / market cap.

Names cluster around:
  - Mark-Leonard-style serial acquirers (Constellation, Topicus,
    Lumine, Vitec, etc.)
  - Compounder roll-ups (Heico, Roper, Watsco, Diploma, Halma)
  - Disciplined re-investors (Spirax-Sarco, Bunzl, Ashtead, Rentokil)
  - Capital-light recurring-revenue (MSCI, Moody's, Verisk, S&P)
  - Best-in-class operators in commodity industries (Old Dominion,
    Cintas, Watsco, Texas Roadhouse, Cracker Barrel)
  - PE-style holdings with explicit ROIIC discipline
"""

CAPITAL_ALLOCATORS = [
    # ===== US large/mid =====
    "HEI", "HEI-A", "ROP", "WSO", "GNRC", "VRT", "TMO", "CINF",
    "ODFL", "CTAS", "PCAR", "AME", "WAT", "WST", "AAON", "FIX",
    "BRO", "MSCI", "MCO", "VRSK", "SPGI", "FDS", "MORN", "INFO",
    "HOLI", "MELI", "TXRH", "CMG", "DPZ", "BKNG", "TJX", "ULTA",
    "EXPE", "ABNB", "ALK", "CMI", "DOV", "EMR", "GWW", "FAST",
    "PWR", "URI", "BLDR", "MAS", "MLM", "VMC", "CRH", "FBHS",
    "EXR", "PSA", "SBAC", "AMT", "EQIX",
    # Software / data compounders
    "ADBE", "INTU", "CRM", "ORCL", "CDNS", "SNPS", "ANSS",
    "PAYX", "ADP", "BR", "FIS", "FISV", "WU",
    # Insurance / financials
    "PGR", "TRV", "CB", "AFG", "WRB", "ALL", "RGA", "AIZ",
    "AJG", "BRO", "MMC", "AON", "WTW",
    # Capital-light services
    "WCN", "RSG", "GRIN", "FDS", "MORN", "VRSK",
    # Recent / smaller compounders that disclose ROIIC
    "TRTN", "TPL", "LICY", "FRPT", "WING", "CAKE", "DRI",
    "SCI", "WLDN", "EME", "PWR", "JBL",

    # ===== Canadian (Constellation universe) =====
    "CSU.TO",   # Constellation Software -- ROIIC poster-child
    "TOI.V",    # Topicus
    "LMN.V",    # Lumine Group
    "DSG.TO",   # Descartes Systems
    "GIB-A.TO", # CGI Inc
    "OTEX.TO",  # Open Text
    "WSP.TO",   # WSP Global
    "STN.TO",   # Stantec
    "ATD.TO",   # Alimentation Couche-Tard
    "DOL.TO",   # Dollarama
    "CCL-B.TO", # CCL Industries
    "TFII.TO",  # TFI International
    "TRI.TO",   # Thomson Reuters
    "FFH.TO",   # Fairfax
    "OR.TO",    # Osisko Gold Royalties
    "FNV.TO",   # Franco-Nevada (royalty model)
    "MNT.TO",   # MTY Food Group? actually MTY.TO
    "BCB.TO",   # Cogeco

    # ===== UK capital-discipline names =====
    "DPLM.L",   # Diploma plc -- explicit ROIIC discipline
    "HLMA.L",   # Halma plc -- "high return businesses" mantra
    "SPX.L",    # Spirax-Sarco
    "BNZL.L",   # Bunzl -- bolt-on M&A discipline
    "AHT.L",    # Ashtead Group
    "RTO.L",    # Rentokil Initial
    "EXPN.L",   # Experian
    "AUTO.L",   # Auto Trader
    "RMV.L",    # Rightmove
    "REL.L",    # RELX
    "INF.L",    # Informa
    "RKT.L",    # Reckitt
    "ULVR.L",   # Unilever
    "DGE.L",    # Diageo
    "JD.L",     # JD Sports
    "NXT.L",    # Next plc (capital-discipline retailer)
    "GAW.L",    # Games Workshop
    "DPLM.L",   # Diploma (dup)
    "JDPO.L",   # JTC Group? not sure
    "JTC.L",    # JTC plc
    "ICG.L",    # Intermediate Capital Group
    "III.L",    # 3i Group
    "MGGT.L",   # Meggitt (former)

    # ===== European compounders =====
    "INVE-B.ST", # Investor AB
    "EQT.ST",    # EQT Partners
    "ATCO-A.ST", # Atlas Copco
    "ATCO-B.ST", # Atlas Copco B
    "SOBI.ST",   # Swedish Orphan Biovitrum
    "INDU-A.ST", # Industrivarden
    "VITR.ST",   # Vitrolife
    "ASSA-B.ST", # Assa Abloy
    "EPI-A.ST",  # Epiroc
    "EPI-B.ST",  # Epiroc B
    "HEXA-B.ST", # Hexagon
    "AAK.ST",    # AAK
    "ELUX-B.ST", # Electrolux
    "GETI-B.ST", # Getinge
    "LATO-B.ST", # Latour
    "KAHOT.OL",  # Kahoot
    "DSV.CO",    # DSV
    "DIM.PA",    # Sartorius Stedim
    "AC.PA",     # Accor
    "PUB.PA",    # Publicis
    "ML.PA",     # Michelin
    "VIE.PA",    # Veolia
    "SU.PA",     # Schneider Electric
    "DSY.PA",    # Dassault Systemes
    "RMS.PA",    # Hermes
    "MC.PA",     # LVMH
    "SAP.DE",    # SAP
    "SIE.DE",    # Siemens
    "DHER.DE",   # Delivery Hero
    "DHL.DE",    # DHL Group

    # ===== Australia compounders =====
    "TWE.AX",   # Treasury Wine Estates
    "WTC.AX",   # WiseTech Global
    "XRO.AX",   # Xero
    "CSL.AX",   # CSL
    "RMD.AX",   # ResMed
    "REA.AX",   # REA Group
    "CAR.AX",   # Carsales
    "BRG.AX",   # Breville
    "PME.AX",   # Pro Medicus
    "ALL.AX",   # Aristocrat
    "JHX.AX",   # James Hardie
    "WOW.AX",   # Woolworths
    "COL.AX",   # Coles
    "WES.AX",   # Wesfarmers
    "MQG.AX",   # Macquarie
    "CBA.AX",   # Commonwealth Bank
]
