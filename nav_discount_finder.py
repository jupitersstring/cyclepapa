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
    st.title("Wind-down / NAV Discount Setup Finder")
    st.caption(
        "Pulls news on managed wind-downs, NAV-discount tenders, and "
        "liquidations, then screens each candidate for a weekly volume "
        "spike near the volume-profile POC. MFI(18) green is reported "
        "as soft confirmation only."
    )

    queries_text = st.text_area(
        "Google News queries (one per line)",
        value="\n".join(DEFAULT_QUERIES),
        height=180,
    )
    feeds_text = st.text_area(
        "Additional RSS feeds — special-sits newsletters, blogs (one URL per line)",
        value="\n".join(DEFAULT_RSS_FEEDS),
        height=120,
    )
    extra_tickers = st.text_input(
        "Manually-added tickers (comma-separated, e.g. RSE.L, NBPE.L)",
        value="",
    )
    seed_groups = st.multiselect(
        "Seed candidate groups (curated UK CEF special-sits / workouts)",
        options=list(KNOWN_CANDIDATES.keys()),
        default=["managed_wind_down", "strategic_review_or_activist"],
        help="Tickers from the chosen groups are screened even if news "
             "extraction misses them.",
    )

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        vol_spike_mult = st.number_input("Vol spike × 26w avg", value=2.0, min_value=1.0, step=0.25)
    with col2:
        poc_proximity_pct = st.number_input("POC proximity (frac)", value=0.07, min_value=0.0, max_value=0.5, step=0.01)
    with col3:
        profile_weeks = st.number_input("Profile lookback (weeks)", value=156, min_value=26, max_value=520, step=26)
    with col4:
        mfi_period = st.number_input("MFI length", value=18, min_value=2, max_value=100, step=1)

    require_mfi = st.checkbox("Require MFI green (rising or > 50)", value=False)

    if not st.button("Run scan"):
        return

    queries = [q.strip() for q in queries_text.splitlines() if q.strip()]
    feeds = [f.strip() for f in feeds_text.splitlines() if f.strip()]

    all_items: list[dict] = []
    with st.spinner("Pulling Google News..."):
        for q in queries:
            try:
                for it in fetch_rss(google_news_url(q)):
                    it["source"] = f"news:{q}"
                    all_items.append(it)
            except Exception as exc:
                st.warning(f"News fetch failed for '{q}': {exc}")
    with st.spinner("Pulling newsletter / blog feeds..."):
        for url in feeds:
            try:
                for it in fetch_rss(url):
                    it["source"] = url
                    all_items.append(it)
            except Exception as exc:
                st.warning(f"Feed fetch failed for '{url}': {exc}")

    st.write(f"Retrieved {len(all_items)} news items.")

    ticker_to_news = _gather_candidates(all_items)
    for group in seed_groups:
        for sym in KNOWN_CANDIDATES.get(group, []):
            # Seeds are pre-formatted with the right Yahoo suffix
            # (UK .L, EU .PA/.BR/.ST etc., US bare). Don't force .L.
            ticker_to_news.setdefault(sym.upper(), [])
    for raw in [t.strip() for t in extra_tickers.split(",") if t.strip()]:
        ticker_to_news.setdefault(normalise_lse_ticker(raw), [])

    st.write(f"Unique candidate tickers: {len(ticker_to_news)}")
    if not ticker_to_news:
        st.info("No tickers extracted — add some manually above and re-run.")
        return

    results: list[dict] = []
    progress = st.progress(0.0)
    for i, sym in enumerate(sorted(ticker_to_news)):
        res = screen_ticker(
            sym,
            profile_weeks=int(profile_weeks),
            vol_spike_mult=float(vol_spike_mult),
            poc_proximity_pct=float(poc_proximity_pct),
            mfi_period=int(mfi_period),
        )
        res["news_count"] = len(ticker_to_news[sym])
        results.append(res)
        progress.progress((i + 1) / len(ticker_to_news))

    df = pd.DataFrame(results)
    if df.empty:
        st.info("No screened results.")
        return

    if require_mfi and "setup_match" in df:
        df["setup_match"] = df["setup_match"] & df["mfi_green"].fillna(False)

    sort_cols = [c for c in ("setup_match", "vol_ratio") if c in df.columns]
    st.subheader("All candidates")
    st.dataframe(df.sort_values(sort_cols, ascending=[False] * len(sort_cols)) if sort_cols else df)

    st.subheader("Setup matches")
    matches = df[df.get("setup_match", False) == True]
    if matches.empty:
        st.write("No tickers cleared the setup filter.")
    else:
        st.dataframe(matches)
        for _, row in matches.iterrows():
            sym = row["ticker"]
            with st.expander(f"{sym} — supporting news"):
                hits = ticker_to_news.get(sym, [])
                if not hits:
                    st.write("(manually added — no news linked)")
                for it in hits[:15]:
                    title = it.get("title", "(no title)") or "(no title)"
                    link = it.get("link", "")
                    when = it.get("pubDate", "")
                    src = it.get("source", "")
                    if link:
                        st.markdown(f"- [{title}]({link}) — {when} _{src}_")
                    else:
                        st.markdown(f"- {title} — {when} _{src}_")
