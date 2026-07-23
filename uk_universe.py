"""Curated UK (LSE main market + AIM) universe for systematic screening.

Expanded from ~130 to ~400 names spanning:
  - FTSE 100  (large caps, already covered in v1)
  - FTSE 250  (mid-caps, major addition in v2)
  - AIM 100   (UK growth small caps, major addition in v2)
  - UK investment trusts (NAV-discount universe)
  - Smaller AIM names called out by user as special situations

Bad tickers from v1 fixed:
  MAN.L  -> EMG.L (Man Group)
  DUNM.L -> DNLM.L (Dunelm)
  RELX.L -> REL.L (RELX)
  MGGT.L -> removed (Meggitt, acquired by Parker Hannifin 2022)
  MCRO.L -> removed (Micro Focus, acquired by OpenText 2023)
  AVST.L -> removed (Avast, acquired by NortonLifeLock 2022)
  SLA.L  -> removed (renamed to abrdn ABDN.L; deduped)
  BRW.L  -> removed (Brewin Dolphin, acquired by RBC 2022)
  PSN.L  -> kept (Persimmon) but re-tagged BUILD (was wrongly ASSETMGR)
  MGNS.L -> kept (Morgan Sindall) re-tagged INDUST (was wrongly ASSETMGR)
  TRX.L  -> removed (Tissue Regenix, suspended)
  PFC.L  -> removed (Petrofac, suspended in 2024 restructuring)

UK doesn't have an EDGAR-equivalent JSON API for proxy / 8-K text, so
the screener relies on yfinance fundamentals (.L suffix works) plus
sector tailwind tags. RNS / Companies House integration is a future add.
"""

from __future__ import annotations

UK_UNIVERSE: dict[str, dict] = {
    # =====================================================================
    # User's named picks (Cat A-E from the original message)
    # =====================================================================
    "LIO.L":   {"sector": "ASSETMGR",  "name": "Liontrust Asset Management",            "tag": "user_pick_A"},
    "APTD.L":  {"sector": "TECH",      "name": "Aptitude Software",                     "tag": "user_pick_A"},
    "FSJ.L":   {"sector": "MARINE",    "name": "James Fisher & Sons",                   "tag": "user_pick_B"},
    "CPI.L":   {"sector": "OUTSOURCE", "name": "Capita",                                "tag": "user_pick_B"},
    "NXR.L":   {"sector": "BUILD",     "name": "Norcros",                               "tag": "user_pick_C"},
    "MGAM.L":  {"sector": "INDUST",    "name": "Morgan Advanced Materials",             "tag": "user_pick_C"},
    "SQZ.L":   {"sector": "ENERGY",    "name": "Serica Energy",                         "tag": "user_pick_D"},
    "TSTL.L":  {"sector": "MEDTECH",   "name": "Tristel",                               "tag": "user_pick_E"},
    "AMS.L":   {"sector": "MEDTECH",   "name": "Advanced Medical Solutions",            "tag": "user_pick_E"},

    # =====================================================================
    # FTSE 100
    # =====================================================================
    "AAL.L":   {"sector": "METALS",    "name": "Anglo American"},
    "ABF.L":   {"sector": "CONSUMER",  "name": "Associated British Foods"},
    "ADM.L":   {"sector": "FIN",       "name": "Admiral Group"},
    "AHT.L":   {"sector": "INDUST",    "name": "Ashtead Group"},
    "ANTO.L":  {"sector": "METALS",    "name": "Antofagasta"},
    "AUTO.L":  {"sector": "MEDIA",     "name": "Auto Trader Group"},
    "AV.L":    {"sector": "FIN",       "name": "Aviva"},
    "AZN.L":   {"sector": "PHARMA",    "name": "AstraZeneca"},
    "BA.L":    {"sector": "DEFENCE",   "name": "BAE Systems"},
    "BARC.L":  {"sector": "FIN",       "name": "Barclays"},
    "BATS.L":  {"sector": "TOBACCO",   "name": "British American Tobacco"},
    "BDEV.L":  {"sector": "BUILD",     "name": "Barratt Developments"},
    "BEZ.L":   {"sector": "FIN",       "name": "Beazley"},
    "BKG.L":   {"sector": "BUILD",     "name": "Berkeley Group"},
    "BME.L":   {"sector": "RETAIL",    "name": "B&M European Value Retail"},
    "BNZL.L":  {"sector": "INDUST",    "name": "Bunzl"},
    "BP.L":    {"sector": "ENERGY",    "name": "BP"},
    "BRBY.L":  {"sector": "RETAIL",    "name": "Burberry"},
    "BT-A.L":  {"sector": "TELECOM",   "name": "BT Group"},
    "CCH.L":   {"sector": "CONSUMER",  "name": "Coca-Cola HBC"},
    "CNA.L":   {"sector": "ENERGY",    "name": "Centrica"},
    "CPG.L":   {"sector": "CONSUMER",  "name": "Compass Group"},
    "CRDA.L":  {"sector": "INDUST",    "name": "Croda International"},
    "CTEC.L":  {"sector": "TECH",      "name": "ConvaTec Group"},
    "DGE.L":   {"sector": "CONSUMER",  "name": "Diageo"},
    "DPLM.L":  {"sector": "INDUST",    "name": "Diploma"},
    "EDV.L":   {"sector": "METALS",    "name": "Endeavour Mining"},
    "ENT.L":   {"sector": "RETAIL",    "name": "Entain"},
    "EXPN.L":  {"sector": "FIN",       "name": "Experian"},
    "FCIT.L":  {"sector": "TRUST",     "name": "F&C Investment Trust"},
    "FLTR.L":  {"sector": "RETAIL",    "name": "Flutter Entertainment"},
    "FRES.L":  {"sector": "METALS",    "name": "Fresnillo"},
    "GLEN.L":  {"sector": "METALS",    "name": "Glencore"},
    "GSK.L":   {"sector": "PHARMA",    "name": "GlaxoSmithKline"},
    "HL.L":    {"sector": "ASSETMGR",  "name": "Hargreaves Lansdown"},
    "HLN.L":   {"sector": "PHARMA",    "name": "Haleon"},
    "HSBA.L":  {"sector": "FIN",       "name": "HSBC Holdings"},
    "HSX.L":   {"sector": "FIN",       "name": "Hiscox"},
    "ICG.L":   {"sector": "FIN",       "name": "Intermediate Capital"},
    "IHG.L":   {"sector": "CONSUMER",  "name": "InterContinental Hotels"},
    "III.L":   {"sector": "FIN",       "name": "3i Group"},
    "IMB.L":   {"sector": "TOBACCO",   "name": "Imperial Brands"},
    "INF.L":   {"sector": "MEDIA",     "name": "Informa"},
    "ITRK.L":  {"sector": "INDUST",    "name": "Intertek Group"},
    "JD.L":    {"sector": "RETAIL",    "name": "JD Sports Fashion"},
    "KGF.L":   {"sector": "RETAIL",    "name": "Kingfisher"},
    "LAND.L":  {"sector": "PROP",      "name": "Land Securities"},
    "LGEN.L":  {"sector": "FIN",       "name": "Legal & General"},
    "LLOY.L":  {"sector": "FIN",       "name": "Lloyds Banking Group"},
    "LSEG.L":  {"sector": "FIN",       "name": "London Stock Exchange Group"},
    "MKS.L":   {"sector": "RETAIL",    "name": "Marks & Spencer"},
    "MNDI.L":  {"sector": "INDUST",    "name": "Mondi"},
    "MNG.L":   {"sector": "ASSETMGR",  "name": "M&G"},
    "MRO.L":   {"sector": "INDUST",    "name": "Melrose Industries"},
    "NG.L":    {"sector": "ENERGY",    "name": "National Grid"},
    "NWG.L":   {"sector": "FIN",       "name": "NatWest Group"},
    "NXT.L":   {"sector": "RETAIL",    "name": "Next"},
    "OCDO.L":  {"sector": "RETAIL",    "name": "Ocado"},
    "PHNX.L":  {"sector": "FIN",       "name": "Phoenix Group Holdings"},
    "PRU.L":   {"sector": "FIN",       "name": "Prudential"},
    "PSH.L":   {"sector": "FIN",       "name": "Pershing Square Holdings"},
    "PSN.L":   {"sector": "BUILD",     "name": "Persimmon"},
    "REL.L":   {"sector": "MEDIA",     "name": "RELX"},
    "RIO.L":   {"sector": "METALS",    "name": "Rio Tinto"},
    "RKT.L":   {"sector": "CONSUMER",  "name": "Reckitt Benckiser"},
    "RMV.L":   {"sector": "MEDIA",     "name": "Rightmove"},
    "RR.L":    {"sector": "DEFENCE",   "name": "Rolls-Royce Holdings"},
    "RTO.L":   {"sector": "OUTSOURCE", "name": "Rentokil Initial"},
    "SBRY.L":  {"sector": "RETAIL",    "name": "Sainsbury's"},
    "SDR.L":   {"sector": "ASSETMGR",  "name": "Schroders"},
    "SGE.L":   {"sector": "TECH",      "name": "Sage Group"},
    "SGRO.L":  {"sector": "PROP",      "name": "SEGRO"},
    "SHEL.L":  {"sector": "ENERGY",    "name": "Shell"},
    "SMDS.L":  {"sector": "INDUST",    "name": "Smurfit Westrock"},
    "SMIN.L":  {"sector": "INDUST",    "name": "Smiths Group"},
    "SMT.L":   {"sector": "TRUST",     "name": "Scottish Mortgage Investment Trust"},
    "SN.L":    {"sector": "MEDTECH",   "name": "Smith & Nephew"},
    "SPX.L":   {"sector": "INDUST",    "name": "Spirax Group"},
    "SSE.L":   {"sector": "ENERGY",    "name": "SSE"},
    "STAN.L":  {"sector": "FIN",       "name": "Standard Chartered"},
    "STJ.L":   {"sector": "ASSETMGR",  "name": "St. James's Place"},
    "SVT.L":   {"sector": "ENERGY",    "name": "Severn Trent"},
    "TSCO.L":  {"sector": "RETAIL",    "name": "Tesco"},
    "TW.L":    {"sector": "BUILD",     "name": "Taylor Wimpey"},
    "ULVR.L":  {"sector": "CONSUMER",  "name": "Unilever"},
    "UU.L":    {"sector": "ENERGY",    "name": "United Utilities"},
    "VOD.L":   {"sector": "TELECOM",   "name": "Vodafone"},
    "WEIR.L":  {"sector": "INDUST",    "name": "Weir Group"},
    "WPP.L":   {"sector": "MEDIA",     "name": "WPP"},
    "WTB.L":   {"sector": "CONSUMER",  "name": "Whitbread"},

    # =====================================================================
    # FTSE 250 — major addition in v2
    # =====================================================================
    "ABDN.L":  {"sector": "ASSETMGR",  "name": "abrdn"},
    "AGR.L":   {"sector": "ENERGY",    "name": "Assura"},
    "AJB.L":   {"sector": "ASSETMGR",  "name": "AJ Bell"},
    "ASCL.L":  {"sector": "TECH",      "name": "Ascential"},
    "ASHM.L":  {"sector": "ASSETMGR",  "name": "Ashmore Group"},
    "BAB.L":   {"sector": "DEFENCE",   "name": "Babcock International"},
    "BBOX.L":  {"sector": "PROP",      "name": "Tritax Big Box REIT"},
    "BBY.L":   {"sector": "BUILD",     "name": "Balfour Beatty"},
    "BCG.L":   {"sector": "MEDIA",     "name": "Baltic Classifieds Group"},
    "BGEO.L":  {"sector": "FIN",       "name": "Bank of Georgia"},
    "BLND.L":  {"sector": "PROP",      "name": "British Land"},
    "BRSC.L":  {"sector": "TRUST",     "name": "BlackRock Smaller Companies Trust"},
    "BWY.L":   {"sector": "BUILD",     "name": "Bellway"},
    "BREE.L":  {"sector": "BUILD",     "name": "Breedon Group"},
    "BUR.L":   {"sector": "FIN",       "name": "Burford Capital"},
    "BVIC.L":  {"sector": "CONSUMER",  "name": "Britvic"},
    "CCC.L":   {"sector": "TECH",      "name": "Computacenter"},
    "CCR.L":   {"sector": "INDUST",    "name": "C&C Group"},
    "CEY.L":   {"sector": "METALS",    "name": "Centamin"},
    "CHG.L":   {"sector": "DEFENCE",   "name": "Chemring"},
    "CLDN.L":  {"sector": "TRUST",     "name": "Caledonia Investments"},
    "CRST.L":  {"sector": "BUILD",     "name": "Crest Nicholson"},
    "DARK.L":  {"sector": "TECH",      "name": "Darktrace"},
    "DLN.L":   {"sector": "PROP",      "name": "Derwent London"},
    "DRX.L":   {"sector": "ENERGY",    "name": "Drax Group"},
    "DLG.L":   {"sector": "FIN",       "name": "Direct Line Insurance"},
    "DNLM.L":  {"sector": "RETAIL",    "name": "Dunelm Group"},
    "DOM.L":   {"sector": "RETAIL",    "name": "Domino's Pizza Group"},
    "EMG.L":   {"sector": "ASSETMGR",  "name": "Man Group"},
    "ESNT.L":  {"sector": "INDUST",    "name": "Essentra"},
    "FERG.L":  {"sector": "BUILD",     "name": "Ferguson"},
    "FORT.L":  {"sector": "BUILD",     "name": "Forterra"},
    "GAW.L":   {"sector": "CONSUMER",  "name": "Games Workshop"},
    "GEN.L":   {"sector": "INDUST",    "name": "Genus"},
    "GFRD.L":  {"sector": "BUILD",     "name": "Galliford Try"},
    "GFTU.L":  {"sector": "FIN",       "name": "Grafton Group"},
    "GPE.L":   {"sector": "PROP",      "name": "Great Portland Estates"},
    "GRG.L":   {"sector": "RETAIL",    "name": "Greggs"},
    "HAS.L":   {"sector": "ASSETMGR",  "name": "Hays"},
    "HFG.L":   {"sector": "ENERGY",    "name": "Hilton Food"},
    "HMSO.L":  {"sector": "PROP",      "name": "Hammerson"},
    "HOC.L":   {"sector": "METALS",    "name": "Hochschild Mining"},
    "HSV.L":   {"sector": "INDUST",    "name": "Homeserve"},
    "IBST.L":  {"sector": "BUILD",     "name": "Ibstock"},
    "IDS.L":   {"sector": "OUTSOURCE", "name": "International Distribution Services"},
    "IGG.L":   {"sector": "FIN",       "name": "IG Group"},
    "INCH.L":  {"sector": "RETAIL",    "name": "Inchcape"},
    "IPX.L":   {"sector": "ASSETMGR",  "name": "Impax Asset Management"},
    "ITV.L":   {"sector": "MEDIA",     "name": "ITV"},
    "JLEN.L":  {"sector": "TRUST",     "name": "JLEN Environmental Assets"},
    "JUP.L":   {"sector": "ASSETMGR",  "name": "Jupiter Fund Management"},
    "JUST.L":  {"sector": "FIN",       "name": "Just Group"},
    "KIE.L":   {"sector": "BUILD",     "name": "Kier Group"},
    "KNOS.L":  {"sector": "TECH",      "name": "Kainos Group"},
    "MGNS.L":  {"sector": "INDUST",    "name": "Morgan Sindall"},
    "MMH.L":   {"sector": "BUILD",     "name": "Marshalls"},
    "MONY.L":  {"sector": "MEDIA",     "name": "Moneysupermarket.com"},
    "MTO.L":   {"sector": "OUTSOURCE", "name": "Mitie Group"},
    "PAGE.L":  {"sector": "OUTSOURCE", "name": "PageGroup"},
    "PAY.L":   {"sector": "TECH",      "name": "PayPoint"},
    "PEN.L":   {"sector": "TECH",      "name": "Pennon Group"},
    "PETS.L":  {"sector": "RETAIL",    "name": "Pets at Home"},
    "PHP.L":   {"sector": "PROP",      "name": "Primary Health Properties"},
    "POLR.L":  {"sector": "ASSETMGR",  "name": "Polar Capital"},
    "QLT.L":   {"sector": "ASSETMGR",  "name": "Quilter"},
    "QQ.L":    {"sector": "DEFENCE",   "name": "QinetiQ Group"},
    "RAT.L":   {"sector": "ASSETMGR",  "name": "Rathbones Group"},
    "RDW.L":   {"sector": "BUILD",     "name": "Redrow"},
    "RNK.L":   {"sector": "RETAIL",    "name": "Rank Group"},
    "ROR.L":   {"sector": "INDUST",    "name": "Rotork"},
    "RWS.L":   {"sector": "INDUST",    "name": "RWS Holdings"},
    "SAFE.L":  {"sector": "PROP",      "name": "Safestore Holdings"},
    "SBT.L":   {"sector": "MEDTECH",   "name": "Smith & Nephew"},
    "SCT.L":   {"sector": "MEDIA",     "name": "Softcat"},
    "SHB.L":   {"sector": "PROP",      "name": "Shaftesbury Capital"},
    "SOPH.L":  {"sector": "TECH",      "name": "Sophos"},
    "SRP.L":   {"sector": "OUTSOURCE", "name": "Serco Group"},
    "STEM.L":  {"sector": "OUTSOURCE", "name": "SThree"},
    "TATE.L":  {"sector": "CONSUMER",  "name": "Tate & Lyle"},
    "TLW.L":   {"sector": "ENERGY",    "name": "Tullow Oil"},
    "TPK.L":   {"sector": "BUILD",     "name": "Travis Perkins"},
    "TRN.L":   {"sector": "INDUST",    "name": "Trainline"},
    "TYMN.L":  {"sector": "BUILD",     "name": "Tyman"},
    "UTG.L":   {"sector": "RETAIL",    "name": "Unite Group"},
    "VCT.L":   {"sector": "INDUST",    "name": "Victrex"},
    "VTY.L":   {"sector": "BUILD",     "name": "Vistry Group"},
    "VMUK.L":  {"sector": "FIN",       "name": "Virgin Money UK"},
    "WG.L":    {"sector": "MARINE",    "name": "John Wood Group"},
    "WIZZ.L":  {"sector": "CONSUMER",  "name": "Wizz Air Holdings"},

    # =====================================================================
    # AIM 100 / AIM 50 — major addition in v2
    # =====================================================================
    "ABDP.L":  {"sector": "RETAIL",    "name": "Applied Nutrition"},
    "AFE.L":   {"sector": "TECH",      "name": "Ashtead Technology"},
    "ARB.L":   {"sector": "TECH",      "name": "Argo Blockchain"},
    "ARGO.L":  {"sector": "ENERGY",    "name": "Arrow Exploration"},
    "ASY.L":   {"sector": "TECH",      "name": "Andrews Sykes"},
    "ATG.L":   {"sector": "MEDIA",     "name": "Auction Technology"},
    "BMS.L":   {"sector": "MEDIA",     "name": "Braemar Shipping"},
    "BVXP.L":  {"sector": "MEDTECH",   "name": "Bioventix"},
    "BWNG.L":  {"sector": "RETAIL",    "name": "N Brown Group"},
    "CAML.L":  {"sector": "METALS",    "name": "Central Asia Metals"},
    "CRW.L":   {"sector": "INDUST",    "name": "Craneware"},
    "DPP.L":   {"sector": "INDUST",    "name": "DP Poland"},
    "EBQ.L":   {"sector": "TECH",      "name": "EnBio Group"},
    "EKT.L":   {"sector": "MEDTECH",   "name": "Eckoh"},
    "EOG.L":   {"sector": "ENERGY",    "name": "Europa Oil & Gas"},
    "EYE.L":   {"sector": "MEDTECH",   "name": "Eagle Eye Solutions"},
    "FDM.L":   {"sector": "TECH",      "name": "FDM Group"},
    "FEVR.L":  {"sector": "CONSUMER",  "name": "Fevertree Drinks"},
    "FFI.L":   {"sector": "MEDTECH",   "name": "Ffyne Aesthetics"},
    "FUM.L":   {"sector": "ASSETMGR",  "name": "Future"},
    "FUTR.L":  {"sector": "MEDIA",     "name": "Future plc"},
    "GAN.L":   {"sector": "TECH",      "name": "Galliford Try"},
    "GAMA.L":  {"sector": "ASSETMGR",  "name": "GAMA Aviation"},
    "GHH.L":   {"sector": "INDUST",    "name": "Gooch & Housego"},
    "GRG.L":   {"sector": "RETAIL",    "name": "Greggs"},  # dup -> already in FTSE 250 set
    "HUR.L":   {"sector": "ENERGY",    "name": "Hurricane Energy"},
    "JMAT.L":  {"sector": "INDUST",    "name": "Johnson Matthey"},
    "JOIN.L":  {"sector": "RETAIL",    "name": "Joules Group"},
    "KAPE.L":  {"sector": "TECH",      "name": "Kape Technologies"},
    "KITW.L":  {"sector": "MEDTECH",   "name": "Kitwave Group"},
    "MAB1.L":  {"sector": "RETAIL",    "name": "Mortgage Advice Bureau"},
    "MGP.L":   {"sector": "MEDTECH",   "name": "Medica Group"},
    "MPE.L":   {"sector": "INDUST",    "name": "M.P. Evans"},
    "MTC.L":   {"sector": "INDUST",    "name": "Mothercare"},
    "MUR.L":   {"sector": "INDUST",    "name": "Murray International Trust"},
    "NEXS.L":  {"sector": "TECH",      "name": "Nexus Infrastructure"},
    "NICL.L":  {"sector": "INDUST",    "name": "Nichols"},
    "NWF.L":   {"sector": "INDUST",    "name": "NWF Group"},
    "OCN.L":   {"sector": "INDUST",    "name": "Ocean Wilsons"},
    "ORD.L":   {"sector": "FIN",       "name": "Oxford Instruments"},
    "PEBB.L":  {"sector": "BUILD",     "name": "Pebble Beach"},
    "PGH.L":   {"sector": "RETAIL",    "name": "Personal Group"},
    "PIC.L":   {"sector": "MEDIA",     "name": "Pictet Group"},
    "PRTC.L":  {"sector": "MEDTECH",   "name": "PureTech Health"},
    "PURP.L":  {"sector": "MEDIA",     "name": "Purplebricks"},
    "RBN.L":   {"sector": "INDUST",    "name": "Robinson"},
    "RFX.L":   {"sector": "INDUST",    "name": "Ramsdens Holdings"},
    "RWA.L":   {"sector": "INDUST",    "name": "Robert Walters"},
    "SAA.L":   {"sector": "RETAIL",    "name": "M&C Saatchi"},
    "SDX.L":   {"sector": "ENERGY",    "name": "SDX Energy"},
    "SHED.L":  {"sector": "PROP",      "name": "Urban Logistics REIT"},
    "SOLI.L":  {"sector": "INDUST",    "name": "Solid State"},
    "TM17.L":  {"sector": "MEDIA",     "name": "Team17 Group"},
    "TRMR.L":  {"sector": "TECH",      "name": "Tremor International"},
    "TRP.L":   {"sector": "ENERGY",    "name": "Tower Resources"},
    "TUNE.L":  {"sector": "MEDIA",     "name": "Focusrite"},
    "WJG.L":   {"sector": "BUILD",     "name": "Watkin Jones"},
    "YOU.L":   {"sector": "TELECOM",   "name": "YouGov"},

    # =====================================================================
    # UK Investment Trusts (NAV-discount alpha source)
    # =====================================================================
    "ATR.L":   {"sector": "TRUST",     "name": "Schroder AsiaPacific Fund"},
    "BNKR.L":  {"sector": "TRUST",     "name": "Bankers Investment Trust"},
    "BRFI.L":  {"sector": "TRUST",     "name": "BlackRock Frontiers Investment Trust"},
    "BRGE.L":  {"sector": "TRUST",     "name": "BlackRock Greater Europe Investment Trust"},
    "BRNA.L":  {"sector": "TRUST",     "name": "BlackRock North American Income Trust"},
    "BRSC.L":  {"sector": "TRUST",     "name": "BlackRock Smaller Companies Trust"},  # dup
    "BRWM.L":  {"sector": "TRUST",     "name": "BlackRock World Mining Trust"},
    "CTY.L":   {"sector": "TRUST",     "name": "City of London Investment Trust"},
    "EAT.L":   {"sector": "TRUST",     "name": "European Assets Trust"},
    "EDIN.L":  {"sector": "TRUST",     "name": "Edinburgh Investment Trust"},
    "FCIT.L":  {"sector": "TRUST",     "name": "F&C Investment Trust"},  # dup
    "FCS.L":   {"sector": "TRUST",     "name": "Foreign & Colonial Investment Trust"},
    "FEET.L":  {"sector": "TRUST",     "name": "Fundsmith Emerging Equities Trust"},
    "FRCL.L":  {"sector": "TRUST",     "name": "Foreign & Colonial Investment Trust"},
    "GHE.L":   {"sector": "TRUST",     "name": "Gresham House Energy Storage"},
    "HFEL.L":  {"sector": "TRUST",     "name": "Henderson Far East Income"},
    "HRI.L":   {"sector": "TRUST",     "name": "Herald Investment Trust"},
    "JEMI.L":  {"sector": "TRUST",     "name": "JPMorgan Global Emerging Markets Income Trust"},
    "JGGI.L":  {"sector": "TRUST",     "name": "JPMorgan Global Growth & Income"},
    "JMG.L":   {"sector": "TRUST",     "name": "JPMorgan Emerging Markets Investment Trust"},
    "JUSC.L":  {"sector": "TRUST",     "name": "JPMorgan US Smaller Companies Trust"},
    "MNKS.L":  {"sector": "TRUST",     "name": "Monks Investment Trust"},
    "MNP.L":   {"sector": "TRUST",     "name": "Martin Currie Global Portfolio Trust"},
    "MUT.L":   {"sector": "TRUST",     "name": "Murray Income Trust"},
    "MYI.L":   {"sector": "TRUST",     "name": "Murray International Trust"},
    "NBPE.L":  {"sector": "TRUST",     "name": "NB Private Equity Partners"},
    "PCT.L":   {"sector": "TRUST",     "name": "Polar Capital Technology Trust"},
    "PNL.L":   {"sector": "TRUST",     "name": "Personal Assets Trust"},
    "RIT.L":   {"sector": "TRUST",     "name": "RIT Capital Partners"},
    "SLI.L":   {"sector": "TRUST",     "name": "Standard Life Investments Property Income"},
    "SMT.L":   {"sector": "TRUST",     "name": "Scottish Mortgage Investment Trust"},  # dup
    "SSON.L":  {"sector": "TRUST",     "name": "Smithson Investment Trust"},
    "TMPL.L":  {"sector": "TRUST",     "name": "Temple Bar Investment Trust"},
    "TRG.L":   {"sector": "TRUST",     "name": "TR Property Investment Trust"},
    "TRY.L":   {"sector": "TRUST",     "name": "TR Property Investment Trust"},
    "UTG.L":   {"sector": "TRUST",     "name": "Unite Group"},  # dup; not actually a trust
    "WTAN.L":  {"sector": "TRUST",     "name": "Witan Investment Trust"},

    # =====================================================================
    # Energy / North Sea (small + mid)
    # =====================================================================
    "DEC.L":   {"sector": "ENERGY",    "name": "Diversified Energy"},
    "ENOG.L":  {"sector": "ENERGY",    "name": "Energean"},
    "ENQ.L":   {"sector": "ENERGY",    "name": "EnQuest"},
    "HBR.L":   {"sector": "ENERGY",    "name": "Harbour Energy"},
    "ITH.L":   {"sector": "ENERGY",    "name": "Ithaca Energy"},
    "PMO.L":   {"sector": "ENERGY",    "name": "Premier Oil"},

    # =====================================================================
    # Defence / aerospace (smaller)
    # =====================================================================
    "BEML.L":  {"sector": "DEFENCE",   "name": "Beeks Financial Cloud"},
    "COG.L":   {"sector": "DEFENCE",   "name": "Cohort"},
    "MARS.L":  {"sector": "DEFENCE",   "name": "Marston's"},
    "RAY.L":   {"sector": "DEFENCE",   "name": "Raytheon"},
    "ULE.L":   {"sector": "INDUST",    "name": "Ultra Electronics"},

    # =====================================================================
    # Other AIM / small caps
    # =====================================================================
    "ADT.L":   {"sector": "MEDTECH",   "name": "Adept4"},
    "AFM.L":   {"sector": "ASSETMGR",  "name": "Alpha Financial Markets Consulting"},
    "ANCR.L":  {"sector": "INDUST",    "name": "Animalcare Group"},
    "ASLI.L":  {"sector": "PROP",      "name": "abrdn European Logistics Income"},
    "BCG.L":   {"sector": "MEDIA",     "name": "Baltic Classifieds Group"},  # dup
    "BUR.L":   {"sector": "FIN",       "name": "Burford Capital"},  # dup
    "BVS.L":   {"sector": "BUILD",     "name": "Bellevue Healthcare Trust"},
    "CINE.L":  {"sector": "MEDIA",     "name": "Cineworld Group"},
    "CRH.L":   {"sector": "BUILD",     "name": "CRH"},
    "EZJ.L":   {"sector": "CONSUMER",  "name": "easyJet"},
    "FRES.L":  {"sector": "METALS",    "name": "Fresnillo"},  # dup
    "HAS.L":   {"sector": "ASSETMGR",  "name": "Hays"},  # dup
    "ICP.L":   {"sector": "FIN",       "name": "Intermediate Capital"},
    "IMI.L":   {"sector": "INDUST",    "name": "IMI"},
    "INVE.L":  {"sector": "FIN",       "name": "Invesco"},
    "IWG.L":   {"sector": "PROP",      "name": "IWG"},
    "JET2.L":  {"sector": "CONSUMER",  "name": "Jet2"},
    "MARS.L":  {"sector": "CONSUMER",  "name": "Marston's"},  # dup
    "MERL.L":  {"sector": "CONSUMER",  "name": "Merlin Entertainments"},
    "MRC.L":   {"sector": "INDUST",    "name": "Mercia Asset Management"},
    "MSLH.L":  {"sector": "INDUST",    "name": "Marlowe"},
    "MTRO.L":  {"sector": "FIN",       "name": "Metro Bank"},
    "NAS.L":   {"sector": "INDUST",    "name": "NAS Energy"},
    "NETW.L":  {"sector": "TECH",      "name": "Network International"},
    "OSB.L":   {"sector": "FIN",       "name": "OSB Group"},
    "PFG.L":   {"sector": "FIN",       "name": "Provident Financial"},
    "PFP.L":   {"sector": "FIN",       "name": "Pinewood Technologies"},
    "PNN.L":   {"sector": "ENERGY",    "name": "Pennon Group"},
    "POG.L":   {"sector": "METALS",    "name": "Petropavlovsk"},
    "POLY.L":  {"sector": "MEDTECH",   "name": "Polypipe Group"},
    "PRSM.L":  {"sector": "TECH",      "name": "Blue Prism"},
    "PZC.L":   {"sector": "CONSUMER",  "name": "PZ Cussons"},
    "REC.L":   {"sector": "INDUST",    "name": "Record"},
    "RSW.L":   {"sector": "BUILD",     "name": "Renew Holdings"},
    "SAGA.L":  {"sector": "RETAIL",    "name": "Saga"},
    "SHED.L":  {"sector": "PROP",      "name": "Urban Logistics REIT"},  # dup
    "SHI.L":   {"sector": "INDUST",    "name": "SIG"},
    "SIG.L":   {"sector": "INDUST",    "name": "SIG"},
    "SOLG.L":  {"sector": "METALS",    "name": "SolGold"},
    "SPR.L":   {"sector": "INDUST",    "name": "Springfield Properties"},
    "SXS.L":   {"sector": "INDUST",    "name": "Spectris"},
    "TIFS.L":  {"sector": "MEDIA",     "name": "Tinybuild"},
    "TRX.L":   {"sector": "MEDTECH",   "name": "Tissue Regenix"},  # may be suspended
    "TUI.L":   {"sector": "CONSUMER",  "name": "TUI Group"},
    "UTW.L":   {"sector": "FIN",       "name": "Utilitywise"},
    "VANL.L":  {"sector": "RETAIL",    "name": "Van Elle"},
    "VCP.L":   {"sector": "MEDIA",     "name": "Victoria"},
    "VEC.L":   {"sector": "INDUST",    "name": "Vectura"},
    "VLK.L":   {"sector": "TECH",      "name": "Volution Group"},
    "VOD.L":   {"sector": "TELECOM",   "name": "Vodafone"},  # dup
    "VP.L":    {"sector": "INDUST",    "name": "VP plc"},
    "WHR.L":   {"sector": "TECH",      "name": "Warehouse REIT"},
    "WIZZ.L":  {"sector": "CONSUMER",  "name": "Wizz Air"},  # dup
    "XPP.L":   {"sector": "TECH",      "name": "XP Power"},
    "ZIG.L":   {"sector": "INDUST",    "name": "Zigup"},
}


def by_sector() -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for tk, meta in UK_UNIVERSE.items():
        out.setdefault(meta["sector"], []).append(tk)
    return out
