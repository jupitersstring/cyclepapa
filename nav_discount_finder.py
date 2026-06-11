"""Wind-down / NAV-discount special-situation screener.

Two-stage workflow:
  1. Pull news from Google News RSS (and any user-supplied RSS feeds for
     special-sits newsletters / blogs) using wind-down / NAV-discount
     keywords; extract LSE-style tickers from headlines and snippets.
  2. For each candidate ticker, pull weekly OHLCV from Yahoo Finance and
     test the setup from the brief: a weekly volume spike with the
     candle sitting near the volume profile POC. MFI(18) "green"
     (rising or above 50) is reported as an optional confirmation.
"""

from __future__ import annotations

import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from html import unescape
from typing import Iterable

import numpy as np
import pandas as pd
import streamlit as st
import yfinance as yf


DEFAULT_QUERIES = [
    "managed wind-down investment trust",
    "managed wind down investment trust",
    "discount to NAV tender offer investment trust",
    "investment trust liquidation",
    "scheme of reconstruction investment trust",
    "return of capital investment trust",
    "cash exit option investment trust",
    "realisation pool investment trust",
    "continuation vote investment trust",
]

# Newsletter / blog feeds that frequently cover UK closed-end fund
# special situations. The user can edit this list in the UI.
DEFAULT_RSS_FEEDS = [
    "https://quoteddata.com/feed/",
    "https://citywire.com/investment-trust-insider/news/rss",
]

# Words appearing right next to a candidate ticker that lift confidence.
TICKER_CONTEXT_WORDS = (
    "wind", "nav", "discount", "tender", "liquidat", "realisat",
    "realiz", "scheme", "reconstruction", "continuation", "return of capital",
)

# Curated seed list of special-sits / discount-to-NAV / workout candidates.
# Grouped by status so the screener has useful defaults even when news
# extraction misses. Edit freely — the UI lets you override.
KNOWN_CANDIDATES: dict[str, list[str]] = {
    # Boards have committed to a managed wind-down / realisation: this is
    # the bullseye cohort for the "accumulation before value crystallises"
    # setup.
    "managed_wind_down": [
        "RSE.L",    # Riverstone Energy
        "ADIG.L",   # abrdn Diversified Income & Growth
        "DGI9.L",   # Digital 9 Infrastructure
        "USF.L",    # US Solar Fund
        "TENT.L",   # Triple Point Energy Transition
        "HEIT.L",   # Harmony Energy Income Trust
        "HGEN.L",   # HydrogenOne Capital Growth
        "AEET.L",   # Aquila Energy Efficiency Trust
        "AERI.L",   # Aquila European Renewables Income
        "GSEO.L",   # VH Global Sustainable Energy Opps
        "VSL.L",    # VPC Specialty Lending
        "GABI.L",   # GCP Asset Backed Income
        "RMII.L",   # RM Infrastructure Income
        "API.L",    # abrdn Property Income
        "RESI.L",   # Residential Secure Income
        "SBO.L",    # Schroder British Opportunities
        "SUPP.L",   # Schroders Capital Global Innovation (ex-Woodford)
        "MPLS.L",   # Marble Point Loan Financing
        "HOT.L",    # Henderson Opportunities Trust
        "KPC.L",    # Keystone Positive Change (Saba-driven)
        "AAS.L",    # abrdn Asia Focus
    ],
    # Strategic review, continuation vote, or active activist pressure
    # — the next-tier cohort, often the first chart to set up before a
    # wind-down decision is announced.
    "strategic_review_or_activist": [
        "CHRY.L",   # Chrysalis Investments — return-of-capital programme
        "SSIT.L",   # Seraphim Space
        "AUGM.L",   # Augmentum Fintech
        "GROW.L",   # Molten Ventures
        "HRI.L",    # Herald Investment Trust (Saba target)
        "USA.L",    # Baillie Gifford US Growth (Saba target)
        "CYN.L",    # CQS Natural Resources Growth & Income (Saba)
        "ESCT.L",   # European Smaller Companies (Saba)
        "EWI.L",    # Edinburgh Worldwide (Saba)
        "BNKR.L",   # Bankers Investment Trust (Saba)
        "TEM.L",    # Templeton Emerging Markets (Saba)
        "HOME.L",   # Home REIT (workout, suspended)
    ],
    # Listed private-equity trusts on persistent wide discounts; classic
    # setup territory when a buyback / realisation is announced.
    "listed_private_equity": [
        "HVPE.L",   # HarbourVest Global Private Equity
        "NBPE.L",   # NB Private Equity Partners
        "ICGT.L",   # ICG Enterprise Trust
        "PIN.L",    # Pantheon International
        "OCI.L",    # Oakley Capital Investments
        "APAX.L",   # Apax Global Alpha
        "CTPE.L",   # CT Private Equity Trust
        "HGT.L",    # HgCapital Trust
    ],
    # Renewables / infrastructure discount cohort — sector-wide
    # de-rating since 2022; many running buybacks, asset sales, or
    # strategic reviews.
    "renewables_infra_discount": [
        "UKW.L",    # Greencoat UK Wind
        "TRIG.L",   # Renewables Infrastructure Group
        "FSFL.L",   # Foresight Solar Fund
        "NESF.L",   # NextEnergy Solar Fund
        "BSIF.L",   # Bluefield Solar Income
        "JLEN.L",   # JLEN Environmental
        "GRID.L",   # Gresham House Energy Storage
        "FGEN.L",   # Foresight Environmental Infrastructure
        "SEIT.L",   # SDCL Energy Efficiency Income
        "HICL.L",   # HICL Infrastructure
        "INPP.L",   # International Public Partnerships
        "3IN.L",    # 3i Infrastructure
        "PINT.L",   # Pantheon Infrastructure
        "CORD.L",   # Cordiant Digital Infrastructure
    ],
    # Specialist credit / debt CEFs on workout-style discounts.
    "specialist_credit": [
        "BPCR.L",   # BioPharma Credit
        "VTA.L",    # Volta Finance
        "NCYF.L",   # CQS New City High Yield
        "TFIF.L",   # TwentyFour Income
        "SEQI.L",   # Sequoia Economic Infrastructure Income
    ],
    # REITs trading at workout-grade discounts.
    "reit_workout": [
        "SREI.L",   # Schroder REIT
        "CREI.L",   # Custodian REIT
        "RGL.L",    # Regional REIT
        "AEWU.L",   # AEW UK REIT
        "PCTN.L",   # Picton Property
        "WHR.L",    # Warehouse REIT
        "ESP.L",    # Empiric Student Property
        "HLCL.L",   # Helical
        "PSDL.L",   # Phoenix Spree Deutschland
        "RECI.L",   # Real Estate Credit Investments
    ],
    # Aircraft / shipping / leased-asset funds in distribution mode.
    "leasing_realisation": [
        "DNA2.L",   # Doric Nimrod Air Two
        "DNA3.L",   # Doric Nimrod Air Three
        "AA4.L",    # Amedeo Air Four Plus
        "DPA.L",    # DP Aircraft I
        "SHIP.L",   # Tufton Oceanic Assets
        "TMI.L",    # Taylor Maritime Investments
        "KKVL.L",   # KKV Secured Loan Fund
    ],
    # Healthcare / life-sciences CEFs on persistent discounts; several
    # have run tender / return-of-capital programmes.
    "healthcare_cefs": [
        "BBH.L",    # BB Healthcare Trust
        "IBT.L",    # International Biotechnology Trust
        "WWH.L",    # Worldwide Healthcare
        "BIOG.L",   # Biotech Growth Trust
        "RTW.L",    # RTW Biotech Opportunities
    ],
    # Single-country / EM trusts where activism or strategic review is
    # plausible.
    "em_country_funds": [
        "FCSS.L",   # Fidelity China Special Situations
        "PHI.L",    # Pacific Horizon
        "PAC.L",    # Pacific Assets
        "VOF.L",    # VinaCapital Vietnam Opportunity
        "VNH.L",    # VietNam Holding
        "BRLA.L",   # BlackRock Latin American
        "JEMI.L",   # JPMorgan Global Emerging Markets Income
        "AAIF.L",   # abrdn Asian Income
        "MYI.L",    # Murray International
    ],
    # UK small-cap and special-sits-mandated trusts (the screen looks
    # natural here — they buy this kind of setup themselves).
    "uk_smallcap_specialsits": [
        "SEC.L",    # Strategic Equity Capital
        "OIT.L",    # Odyssean Investment Trust
        "ONWD.L",   # Onward Opportunities
        "AGT.L",    # AVI Global
        "AJOT.L",   # AVI Japan Opportunity
        "RIII.L",   # Rights & Issues
        "MNL.L",    # Manchester & London
        "DIVI.L",   # Diverse Income Trust (Saba)
        "CGL.L",    # Castelnau Group (Phoenix Asset Mgmt)
    ],
    # Global multi-asset / hedge-fund-style trusts on persistent wide
    # discounts where buybacks / restructurings are the catalyst.
    "global_multi_asset_discount": [
        "PSH.L",    # Pershing Square Holdings
        "TFG.L",    # Tetragon Financial Group
        "TPOU.L",   # Third Point Investors
        "BHMG.L",   # BH Macro
        "NAS.L",    # North Atlantic Smaller Companies
        "CLDN.L",   # Caledonia Investments
        "RCP.L",    # RIT Capital Partners
    ],
    # Additional UK trusts: 2024–26 wind-downs, strategic reviews, and
    # commodity / sector specialists.
    "uk_extras": [
        "GCP.L",    # GCP Infrastructure Investments
        "GRIO.L",   # Ground Rents Income Fund (wind-down)
        "SOHO.L",   # Triple Point Social Housing
        "ANII.L",   # abrdn New India
        "ASCI.L",   # abrdn Smaller Companies Income
        "AUSC.L",   # abrdn UK Smaller Companies Growth
        "JAGI.L",   # JPMorgan Asia Growth & Income
        "JEDT.L",   # JPMorgan European Discovery
        "JMG.L",    # JPMorgan Emerging Markets
        "FEML.L",   # Fidelity Emerging Markets
        "BRFI.L",   # BlackRock Frontiers
        "MMIT.L",   # Mobius Investment Trust
        "HFEL.L",   # Henderson Far East Income
        "HHI.L",    # Henderson High Income
        "SCF.L",    # Schroder Income Growth
        "LWI.L",    # Lowland Investment
        "BRSC.L",   # BlackRock Smaller Companies
        "THRG.L",   # BlackRock Throgmorton
        "BERI.L",   # BlackRock Energy & Resources
        "BRWM.L",   # BlackRock World Mining
        "HSL.L",    # Henderson Smaller Companies
        "BUT.L",    # Brunner Investment Trust
        "SCP.L",    # Schroder UK Mid Cap
        "MRC.L",    # Mercantile Investment Trust
        "SSON.L",   # Smithson Investment Trust
        "ASL.L",    # Aberforth Smaller Companies
        "AGVI.L",   # Aberforth Geared Value & Income
        "GCL.L",    # Geiger Counter (uranium)
        "GPM.L",    # Golden Prospect Precious Metals
        "BGFD.L",   # Baillie Gifford Japan
        "JFJ.L",    # JPMorgan Japanese
    ],
    # US closed-end funds with persistent NAV discounts and / or active
    # activist (Saba, Bulldog, Karpus) campaigns.
    "us_cef_discount": [
        "BRW",      # Saba Capital Income & Opportunities
        "BIF",      # Boulder Growth & Income
        "GAM",      # General American Investors
        "CET",      # Central Securities
        "ADX",      # Adams Diversified Equity
        "PEO",      # Adams Natural Resources
        "TY",       # Tri-Continental
        "SOR",      # Source Capital
        "FUND",     # Sprott Focus Trust (ex-Royce)
        "RVT",      # Royce Value Trust
        "RMT",      # Royce Micro-Cap Trust
        "RGT",      # Royce Global Value Trust
        "GAB",      # Gabelli Equity Trust
        "GDV",      # Gabelli Dividend & Income
        "GUT",      # Gabelli Utility Trust
        "BST",      # BlackRock Science & Tech
        "BUI",      # BlackRock Utilities & Infrastructure
        "BME",      # BlackRock Health Sciences
        "BTO",      # John Hancock Financial Opps
        "ECC",      # Eagle Point Credit
        "EIC",      # Eagle Point Income
        "OXLC",     # Oxford Lane Capital
        "ASA",      # ASA Gold and Precious Metals
        "GGT",      # Gabelli Multimedia
        "MIN",      # MFS Intermediate Income
        "ASGI",     # abrdn Global Infrastructure Income
        "AOD",      # abrdn Total Dynamic Dividend
        "AWP",      # abrdn Global Premier Properties
        "FOF",      # Cohen & Steers Closed-End Opportunity
        "JLS",      # Nuveen Mortgage & Income
        "JMM",      # Nuveen Multi-Market Income
        "ETW",      # Eaton Vance Tax-Managed Global Buy-Write
        "ETV",      # Eaton Vance Tax-Managed Buy-Write Opps
        "EOI",      # Eaton Vance Enhanced Equity Income
    ],
    # Externally-managed US BDCs with persistent book-value discounts
    # — common targets for restructurings, internalisations or
    # activist pressure.
    "us_bdc_discount": [
        "BKCC",     # BlackRock Capital Investment
        "PSEC",     # Prospect Capital
        "PFLT",     # PennantPark Floating Rate
        "PNNT",     # PennantPark Investment
        "GLAD",     # Gladstone Investment
        "GAIN",     # Gladstone Investment
        "OFS",      # OFS Capital
        "PTMN",     # Portman Ridge Finance
        "LRFC",     # Logan Ridge Finance
        "MFIC",     # MidCap Financial Investment (ex-Apollo)
        "BBDC",     # Barings BDC
        "CGBD",     # Carlyle Secured Lending
        "GBDC",     # Golub Capital BDC
        "SCM",      # Stellus Capital
        "SAR",      # Saratoga Investment
        "RAND",     # Rand Capital
    ],
    # Listed European holding companies; structurally trade at large
    # discounts to NAV with periodic buyback / simplification catalysts.
    "european_holding_co": [
        "SOF.BR",       # Sofina
        "GBLB.BR",      # Groupe Bruxelles Lambert
        "ACKB.BR",      # Ackermans & van Haaren
        "MF.PA",        # Wendel
        "RF.PA",        # Eurazeo
        "BOL.PA",       # Bolloré
        "INDU-C.ST",    # Industrivärden
        "INVE-B.ST",    # Investor AB
        "KINV-B.ST",    # Kinnevik
        "LATO-B.ST",    # Latour
        "LUND-B.ST",    # Lundbergföretagen
        "AKER.OL",      # Aker
        "BONHR.OL",     # Bonheur
        "EXO.AS",       # Exor (Amsterdam-listed)
        "PRX.AS",       # Prosus (Tencent stub)
        "NPN.JO",       # Naspers (Tencent stub)
    ],
    # Australian listed investment companies (LICs) — large activist
    # ecosystem (WAM family, Sandon, Pengana, Saba). Persistent NAV
    # discounts; many continuation / wind-up campaigns.
    "australian_lics": [
        "LSF.AX",       # L1 Capital (Saba target)
        "WAM.AX",       # WAM Capital
        "WLE.AX",       # WAM Leaders
        "WGB.AX",       # WAM Global
        "WAA.AX",       # WAM Active
        "TGF.AX",       # Tribeca Global Natural Resources
        "HM1.AX",       # Hearts & Minds Investments
        "MFF.AX",       # MFF Capital Investments
        "PIA.AX",       # Pengana International Equities
        "PE1.AX",       # Pengana Private Equity
        "NCC.AX",       # NAOS Emerging Opportunities
        "NSC.AX",       # NAOS Small Cap Opportunities
        "GC1.AX",       # Glennon Small Companies
        "PL8.AX",       # Plato Income Maximiser
        "OBL.AX",       # Omni Bridgeway (litigation finance, separate setup)
        "SOL.AX",       # Washington H. Soul Pattinson (holdco)
        "AUI.AX",       # Australian United Investment
        "DUI.AX",       # Diversified United Investment
        "WHF.AX",       # Whitefield (banks LIC)
        "ARG.AX",       # Argo Investments
        "AFI.AX",       # Australian Foundation Investment
    ],
    # Canadian special situations — listed holding companies and
    # split-share corporations (split corps trade at structural NAV
    # discounts).
    "canadian_special_sits": [
        "POW.TO",       # Power Corp of Canada (sum-of-parts)
        "ONEX.TO",      # Onex Corp (PE GP at discount)
        "BAM.TO",       # Brookfield Asset Management
        "DGS.TO",       # Dividend Growth Split Corp
        "FTN.TO",       # Financial 15 Split Corp
        "LBS.TO",       # Life & Banc Split Corp
        "BSP.TO",       # Brompton Split Banc Corp
        "FFN.TO",       # NA Financial 15 Split Corp
        "LCS.TO",       # Brompton Lifeco Split Corp
    ],
    # US sum-of-parts / conglomerate discount — IAC, Liberty trackers,
    # Loews, MSG group. Structurally trade below sum-of-parts of
    # listed subsidiaries / NAV.
    "us_conglomerate_discount": [
        "IAC",          # IAC Inc (Match/Vimeo/MGM/Angi stub)
        "L",            # Loews Corp (CNA/Diamond Offshore/Boardwalk)
        "FWONK",        # Liberty Media F1 (Class K)
        "BATRA",        # Liberty Braves (Class A)
        "LBRDK",        # Liberty Broadband (Charter stub)
        "LILA",         # Liberty Latin America
        "MSGS",         # Madison Square Garden Sports
        "MSGE",         # Madison Square Garden Entertainment
        "LGF.A",        # Lions Gate Entertainment
    ],
    # Swiss-listed / EU specialist CEFs — biotech / healthcare names
    # that don't fit the UK basket but have similar discount mechanics.
    "swiss_eu_specialist": [
        "BION.SW",      # BB Biotech (large biotech CEF)
        "HBMN.SW",      # HBM Healthcare Investments
    ],
    # UK names missed previously — small but live discount or
    # mandate-driven situations.
    "uk_extras_2": [
        "MIGO.L",       # MIGO Opportunities (fund of trusts at discount)
        "ARR.L",        # Aurora Investment Trust (Phoenix Asset Mgmt)
        "JAM.L",        # JPMorgan American
        "MUT.L",        # Murray Income
        "LWDB.L",       # Law Debenture
        "BIPS.L",       # BlackRock Income & Growth (or similar)
        "FAIR.L",       # Fair Oaks Income
        "SDP.L",        # Schroder AsiaPacific
        "ATR.L",        # Asia Total Return (merger candidate)
        "NAVF.L",       # Nippon Active Value Fund
    ],
    # Listed PE GP managers that trade at discount (most premium ones
    # like KKR/Apollo/Blackstone/Ares are excluded — they trade at fair
    # value or premium so the workout setup doesn't apply).
    "listed_pe_gp_discount": [
        "BPT.L",        # Bridgepoint Group
        "EQT.ST",       # EQT AB
        "PGHN.SW",      # Partners Group (Switzerland)
        "CVC.AS",       # CVC Capital Partners
    ],
    # Korean chaebol holding companies — structural NAV-discount plays
    # vs listed subsidiaries; periodic restructure / governance reform
    # catalysts.
    "korean_holdcos": [
        "003550.KS",    # LG Corp
        "028260.KS",    # Samsung C&T
        "005380.KS",    # Hyundai Motor (stub vs Hyundai Glovis etc.)
        "005490.KS",    # POSCO Holdings
    ],
    # Japanese trading houses (sogo shosha) and SoftBank — Buffett-
    # favourite sum-of-parts discount plays; SoftBank is the
    # Alibaba/Arm/listed-stake stub trade.
    "japan_holdcos_specials": [
        "8001.T",       # Itochu Corp
        "8053.T",       # Sumitomo Corp
        "8002.T",       # Marubeni
        "9101.T",       # NYK Line (cyclical sum-of-parts)
        "9984.T",       # SoftBank Group
    ],
    # Additional European holdco / specialist names
    "european_extras": [
        "HEIO.AS",      # Heineken Holding (classic stub-discount vs HEIA)
        "ITM.MI",       # Italmobiliare
        "CIR.MI",       # CIR (De Benedetti family vehicle)
    ],
    # ---- financedatabase scanner finds ----
    # Auto-discovered via financedatabase package: name-pattern scan
    # for investment trusts, listed CEFs, split corps and LICs across
    # liquid exchanges (LSE, TOR, ASX, NMS/NAS, EBS, AMS, PAR), with
    # liquidity floor (median weekly volume > 5000) and yfinance
    # reachability check. Default catalyst is STRUCTURAL_DISCOUNT
    # unless tagged below; NAV quality auto-derived from name pattern.
    "fdb_scanner_finds": [
        "AD-UN.TO", "AIE.L", "AIQ.AX", "APL.AX", "BGCG.L", "BGEU.L",
        "BKI.AX", "BNK.TO", "BRGE.L", "BRIG.L", "CCD", "CCJI.L",
        "CD1.AX", "CD2.AX", "CD3.AX", "CHI", "CHW", "CHY", "CIC.L",
        "CPEN.SW", "CTF-UN.TO", "CTY.L", "DF.TO", "DFN.TO", "DGS-PA.TO",
        "DIG.L", "EDIN.L", "EIT-UN.TO", "ENS.TO", "FAP.TO", "FCIT.L",
        "FGG.AX", "FGT.L", "FGX.AX", "GCI.AX", "GDV-PA.TO", "GDV.TO",
        "IGC.L", "IIGF.AX", "JETG.L", "JGGI.L", "JPEL.L", "JUSC.L",
        "KKC.AX", "LBS-PA.TO", "LCS-PA.TO", "LFE.TO", "LTI.L", "MA1.AX",
        "MAET.AX", "MGCI.L", "MNKS.L", "MOT.AX", "MTE.L", "MTU.L",
        "MWY.L", "MXT.AX", "NAIT.L", "NSI.L", "OIG.L", "PCI.AX",
        "PEY.L", "PEYS.L", "PIC.AX", "PRM.TO", "PVS-PH.TO", "PVS-PJ.TO",
        "QRI.AX", "RICA.L", "RMMC.L", "RS.TO", "SAIN.L", "SJG.L",
        "SLPE.L", "SMT.L", "SOI.L", "SST.L", "SWTZ.AX", "TBLD",
        "TCF.AX", "TMPL.L", "TORO.L", "TRG.L", "TRY.L", "VIP.L", "XTD.TO",
    ],
    # ---- Second-pass FDB scanner finds (broader patterns) ----
    "fdb_scanner_v2": [
        "BEMO.L",       # Barings Emerging EMEA Opportunities
        "ESO.L",        # EPE Special Opportunities
        "MPO.L",        # Macau Property Opportunities (huge AIC discount)
        "RCOI.L",       # Riverstone Credit Opportunities Income
        "BEL.AX",       # Bentley Capital
        "CAM.AX",       # Clime Capital
        "CDM.AX",       # Cadence Capital
        "ECL.AX",       # Excelsior Capital
        "IBC.AX",       # Ironbark Capital
        "NGE.AX",       # NGE Capital
        "PGF.AX",       # PM Capital Global Opportunities Fund
        "RYD.AX",       # Ryder Capital
        "WI.V",         # Western Investment Company of Canada
    ],
    # ---- AIC sweep ----
    # Bulk-import of every UK investment company published by AIC that
    # wasn't already in the universe and clears a £20m market cap / £0.1m
    # daily traded value floor. NAV quality auto-tagged from AIC sector
    # code; catalyst defaults to STRUCTURAL_DISCOUNT.
    "aic_sweep": [
        # >40% live discount
        "MVI.L", "SERE.L", "SYNC.L", "CGI.L", "HANA.L",
        # 30-40% discount
        "GSF.L", "HAN.L", "BOOK.L", "ORIT.L", "PPET.L",
        # 20-30% discount
        "III.L", "BSRT.L", "ENRG.L", "INOV.L", "GRP.L", "LSAA.L",
        # 10-20% discount
        "BBOX.L", "AIRE.L", "ASLI.L", "THRL.L", "GOT.L", "VEIL.L",
        "IEM.L", "UEM.L", "AFL.L", "BGUK.L", "JUGI.L",
        # 5-10% discount
        "BASC.L", "JCGI.L", "IAD.L", "JIGI.L", "ATT.L", "BGS.L",
        "JMGI.L", "PCT.L", "AATG.L", "ALW.L", "PCFT.L", "SDV.L",
        "GSCT.L", "BHMU.L", "MAJE.L",
        # 0-5% discount (kept for setup-pattern screening even though
        # upside is small; mean-reversion signal still firable)
        "CTHT.L", "FEV.L", "EOT.L", "CTUK.L", "MRCH.L", "MRV.L",
        "FAS.L", "JCH.L", "AWEM.L", "CMPG.L", "JEGI.L", "CGT.L",
        "IGET.L", "AEI.L", "CVCE.L", "FSV.L", "STS.L",
        # Premiums (kept for monitoring + completeness)
        "CVCG.L", "PNL.L", "CMPI.L", "EGL.L", "CHI.L", "PCGH.L",
        "BRAI.L", "RKW.L", "SMIF.L",
    ],
}


def all_known_candidates() -> list[str]:
    seen: list[str] = []
    out: list[str] = []
    for group in KNOWN_CANDIDATES.values():
        for sym in group:
            if sym not in seen:
                seen.append(sym)
                out.append(sym)
    return out


# Patterns we trust to actually identify a ticker rather than an acronym.
_TICKER_PATTERNS = [
    re.compile(r"\(\s*(?:LSE|LON|AIM)\s*[:\-]\s*([A-Z]{2,5})\s*\)"),
    re.compile(r"\b(?:LSE|LON|AIM)\s*[:\-]\s*([A-Z]{2,5})\b"),
    re.compile(r"\(\s*([A-Z]{2,5})\.L\s*\)"),
    re.compile(r"\b([A-Z]{2,5})\.L\b"),
    re.compile(r"\bticker[:\s]+([A-Z]{2,5})\b", re.IGNORECASE),
]


def fetch_rss(url: str, max_items: int = 40) -> list[dict]:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        raw = resp.read()
    try:
        root = ET.fromstring(raw)
    except ET.ParseError:
        return []
    items: list[dict] = []
    # Handle both RSS 2.0 (<item>) and Atom (<entry>) feeds.
    nodes = list(root.iter("item")) + list(root.iter("{http://www.w3.org/2005/Atom}entry"))
    for node in nodes[:max_items]:
        title = (node.findtext("title") or node.findtext("{http://www.w3.org/2005/Atom}title") or "").strip()
        link_node = node.find("link")
        link = link_node.text.strip() if link_node is not None and link_node.text else ""
        if not link:
            atom_link = node.find("{http://www.w3.org/2005/Atom}link")
            if atom_link is not None:
                link = atom_link.attrib.get("href", "")
        published = (
            node.findtext("pubDate")
            or node.findtext("{http://www.w3.org/2005/Atom}updated")
            or node.findtext("{http://www.w3.org/2005/Atom}published")
            or ""
        ).strip()
        description = unescape(
            node.findtext("description")
            or node.findtext("{http://www.w3.org/2005/Atom}summary")
            or ""
        ).strip()
        items.append({"title": title, "link": link, "pubDate": published, "description": description})
    return items


def google_news_url(query: str) -> str:
    return (
        "https://news.google.com/rss/search?q="
        + urllib.parse.quote_plus(query)
        + "&hl=en-GB&gl=GB&ceid=GB:en"
    )


def extract_tickers(text: str) -> set[str]:
    found: set[str] = set()
    for pat in _TICKER_PATTERNS:
        for m in pat.findall(text):
            sym = m.upper()
            if sym in {"LSE", "LON", "AIM", "PLC", "LTD", "AND", "FOR", "THE"}:
                continue
            found.add(sym)
    return found


def normalise_lse_ticker(sym: str) -> str:
    sym = sym.strip().upper()
    if "." in sym:
        return sym
    return f"{sym}.L"


def weekly_volume_profile(df: pd.DataFrame, bins: int = 60) -> tuple[float | None, np.ndarray | None, np.ndarray | None]:
    """POC of a weekly volume profile, distributing each bar's volume
    uniformly across its (low, high) range."""
    if df.empty:
        return None, None, None
    lo = float(df["Low"].min())
    hi = float(df["High"].max())
    if not (np.isfinite(lo) and np.isfinite(hi)) or hi <= lo:
        return None, None, None
    edges = np.linspace(lo, hi, bins + 1)
    centers = 0.5 * (edges[:-1] + edges[1:])
    vols = np.zeros(bins)
    for low, high, vol in zip(df["Low"].to_numpy(), df["High"].to_numpy(), df["Volume"].to_numpy()):
        if not (np.isfinite(low) and np.isfinite(high) and np.isfinite(vol)) or high <= low or vol <= 0:
            continue
        lo_idx = max(0, int(np.searchsorted(edges, low, side="right") - 1))
        hi_idx = min(bins - 1, int(np.searchsorted(edges, high, side="right") - 1))
        if hi_idx < lo_idx:
            continue
        n = hi_idx - lo_idx + 1
        vols[lo_idx:hi_idx + 1] += vol / n
    if vols.sum() <= 0:
        return None, None, None
    return float(centers[int(np.argmax(vols))]), centers, vols


def money_flow_index(df: pd.DataFrame, period: int = 18) -> pd.Series:
    tp = (df["High"] + df["Low"] + df["Close"]) / 3.0
    rmf = tp * df["Volume"]
    delta = tp.diff()
    pos = rmf.where(delta > 0, 0.0)
    neg = rmf.where(delta < 0, 0.0)
    pos_sum = pos.rolling(period).sum()
    neg_sum = neg.rolling(period).sum()
    ratio = pos_sum / neg_sum.replace(0, np.nan)
    return 100 - 100 / (1 + ratio)


def screen_ticker(
    ticker: str,
    *,
    lookback_weeks: int = 260,
    profile_weeks: int = 156,
    vol_spike_mult: float = 2.0,
    poc_proximity_pct: float = 0.07,
    mfi_period: int = 18,
) -> dict:
    try:
        data = yf.download(ticker, period="5y", interval="1wk", progress=False, auto_adjust=False)
    except Exception as exc:
        return {"ticker": ticker, "error": f"download failed: {exc}"}
    if data is None or data.empty:
        return {"ticker": ticker, "error": "no data"}
    if isinstance(data.columns, pd.MultiIndex):
        data.columns = data.columns.get_level_values(0)
    data = data.dropna(subset=["Close", "Volume"]).tail(lookback_weeks)
    if len(data) < max(mfi_period + 5, 30):
        return {"ticker": ticker, "error": "insufficient bars"}

    mfi_series = money_flow_index(data, mfi_period)
    last_mfi = float(mfi_series.iloc[-1]) if pd.notna(mfi_series.iloc[-1]) else np.nan
    prev_mfi = float(mfi_series.iloc[-2]) if pd.notna(mfi_series.iloc[-2]) else np.nan
    mfi_green = (
        np.isfinite(last_mfi)
        and (last_mfi > 50.0 or (np.isfinite(prev_mfi) and last_mfi > prev_mfi))
    )

    avg_vol = data["Volume"].rolling(26).mean()
    last_vol = float(data["Volume"].iloc[-1])
    last_avg = float(avg_vol.iloc[-1]) if pd.notna(avg_vol.iloc[-1]) else np.nan
    vol_ratio = last_vol / last_avg if (np.isfinite(last_avg) and last_avg > 0) else np.nan
    vol_spike = bool(np.isfinite(vol_ratio) and vol_ratio >= vol_spike_mult)

    profile_window = data.tail(min(len(data), profile_weeks))
    poc_price, _, _ = weekly_volume_profile(profile_window)
    last_close = float(data["Close"].iloc[-1])
    if poc_price and poc_price > 0:
        poc_distance_pct = abs(last_close - poc_price) / poc_price
        near_poc = poc_distance_pct <= poc_proximity_pct
    else:
        poc_distance_pct = np.nan
        near_poc = False

    return {
        "ticker": ticker,
        "last_close": last_close,
        "vol_ratio": vol_ratio,
        "vol_spike": vol_spike,
        "poc": poc_price,
        "poc_distance_pct": poc_distance_pct,
        "near_poc": near_poc,
        "mfi": last_mfi,
        "mfi_green": bool(mfi_green),
        "setup_match": bool(vol_spike and near_poc),
    }


def _gather_candidates(news_items: Iterable[dict]) -> dict[str, list[dict]]:
    candidates: dict[str, list[dict]] = {}
    for item in news_items:
        text = f"{item.get('title','')} {item.get('description','')}"
        text_lc = text.lower()
        # Drop hits that don't even mention a wind-down/NAV-style word, to
        # cut down on regex false positives like "PLC" or "GBP".
        if not any(w in text_lc for w in TICKER_CONTEXT_WORDS):
            continue
        for sym in extract_tickers(text):
            candidates.setdefault(normalise_lse_ticker(sym), []).append(item)
    return candidates


def render_nav_discount_finder() -> None:
    """v3 Streamlit page — calls screen_v3 logic, not the legacy
    last-bar / 26-week-avg path. Layout: parameter sidebar, ranked
    table by IRR, drill-down panel per selected ticker."""
    import metadata
    import params as p
    import price_store
    import screen_core as sc
    import screen_v3 as sv3
    from aic_scraper import fetch_aic_raw, fetch_aic_summary
    from yahoo_nav_scraper import fetch_yahoo_discounts
    from dataclasses import asdict
    import pandas as pd

    st.title("Wind-down / NAV-Discount Setup Finder (v3)")
    st.caption(
        "Screens for the pre-rating setup: long base, volume profile POC, "
        "weekly volume spike + MFI(18). Ranks by recovery-adjusted IRR. "
        "Live AIC discount data for UK CEFs; Yahoo bookValue proxy for non-UK."
    )

    with st.sidebar:
        st.subheader("Universe")
        try:
            universe = metadata.load_universe()
        except metadata.UniverseError as exc:
            st.error(str(exc))
            return
        all_groups = sorted({r.group for r in universe.values() if r.group})
        selected = st.multiselect("Groups", all_groups, default=[])
        only_investable = st.checkbox("Drop names failing investability gates",
                                      value=True)
        run_signals = st.checkbox(
            "Run qualitative signal scrape (slow ~5 min)",
            value=False,
            help="Scrapes Google News for director dealings / advisor / "
                 "wind-down per top-discount UK CEF. Adjusts catalyst probability."
        )
        signal_top_n = st.number_input("Signal top-N", 10, 200, 60, step=10)
        force_refresh = st.checkbox("Force price-cache refresh", value=False)

    if selected:
        symbols = sorted({t for t, r in universe.items() if r.group in set(selected)})
    else:
        symbols = sorted(universe.keys())
    st.write(f"Screening **{len(symbols)} tickers**.")

    if not st.button("Run screen"):
        return

    # --- load feeds ---
    with st.spinner("Loading AIC discount data…"):
        aic_raw = fetch_aic_raw()
        aic_summ = fetch_aic_summary()
    aic_by_ticker = {f"{epic}.L": rec for epic, rec in aic_raw.items()}
    st.write(f"AIC live discount records: {len(aic_summ)}")

    with st.spinner("Loading Yahoo bookValue proxies…"):
        non_uk = [t for t in symbols if not t.endswith(".L")]
        yh = fetch_yahoo_discounts(non_uk) if non_uk else {}
    st.write(f"Yahoo bookValue records: {len(yh)}")

    with st.spinner("Refreshing OHLCV cache…"):
        price_store.refresh_all(symbols, ttl_hours=0 if force_refresh else 24)

    sig_map = {}
    if run_signals:
        with st.spinner(f"Scraping news signals for top {signal_top_n}…"):
            import signals as sigmod
            cands = []
            for sym in symbols:
                rec = aic_summ.get(sym)
                if not rec or rec.get("discount") is None or rec.get("name") is None:
                    continue
                if rec["discount"] < 0.05:
                    continue
                cands.append((sym, rec["name"], rec["discount"]))
            cands.sort(key=lambda r: -r[2])
            cands = cands[: int(signal_top_n)]
            sig_map = sigmod.fetch_signals_batch(
                [(t, n) for t, n, _ in cands], verbose=False)
        st.write(f"Signals scraped: {len(sig_map)}")

    # --- score ---
    results = []
    prog = st.progress(0.0)
    for i, sym in enumerate(symbols, 1):
        try:
            r = sv3.screen_one(
                sym,
                aic_record=aic_by_ticker.get(sym),
                aic_summary=aic_summ.get(sym),
                yahoo_discount=yh.get(sym),
                signal=sig_map.get(sym),
                ohlcv=price_store.get(sym),
            )
        except Exception as exc:
            r = sc.ScreenResult(ticker=sym, error=f"screen_one: {exc}")
        results.append(asdict(r))
        prog.progress(i / len(symbols))

    df = pd.DataFrame(results)
    if df.empty:
        st.info("No results.")
        return

    if only_investable and "investable" in df.columns:
        df = df[df["investable"] == True]
    df = df[df["error"].isna() & (df["composite_score"] > 0)]
    df = df.sort_values("expected_irr", ascending=False)

    show_cols = ["ticker", "name", "phase", "catalyst", "nav_quality",
                 "nav_discount_est", "discount_source", "recovery_rate",
                 "expected_total_return", "expected_duration_months",
                 "catalyst_prob_signal_adj", "signal_score",
                 "expected_irr", "setup_score", "composite_score"]
    show_cols = [c for c in show_cols if c in df.columns]
    st.subheader(f"Ranked candidates ({len(df)})")
    st.dataframe(df[show_cols].head(30))

    if len(df) > 0:
        st.subheader("Drill-down")
        choice = st.selectbox("Ticker", df["ticker"].tolist())
        row = df[df["ticker"] == choice].iloc[0]
        st.json({k: v for k, v in row.to_dict().items()
                 if not (isinstance(v, float) and pd.isna(v))})
