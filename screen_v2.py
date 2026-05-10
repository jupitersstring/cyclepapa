"""Corrected setup screener.

Methodological fixes vs v1:
  * Base detection: walk backward from the latest bar to find the
    longest contiguous stretch where (max-min)/mean stays below a
    range threshold (default 30%). The volume profile and POC are
    computed *only* over this base — not over the entire chart, which
    biased v1's POC into trends.
  * Phase classification: BASE_QUIET / BASE_ABSORBING / BASE_BREAKOUT
    / POST_RERATING / DECLINING / NO_BASE — the setup we want is
    BASE_ABSORBING (flat price, vol building) or fresh BASE_BREAKOUT.
  * Volume z-score relative to the base's own mean and std, not a
    fixed 26w average. This avoids flagging mechanical block trades
    after a tender as accumulation.
  * 13-week price-change filter to exclude names that have already
    re-rated.
  * Distribution events flagged via dividend/cap-return data so we
    don't read post-distribution price drift as a base entry.
  * Catalyst and NAV-quality tags joined into the output so ranking
    reflects the trade's *type*, not just its chart shape.
"""

from __future__ import annotations

import argparse
import sys
import time
from dataclasses import dataclass

import numpy as np
import pandas as pd
import yfinance as yf

from nav_discount_finder import (
    KNOWN_CANDIDATES,
    all_known_candidates,
    money_flow_index,
)

# Live UK discount data from AIC. Loaded lazily on first call.
_AIC_DISCOUNTS: dict[str, float] | None = None

# Live US-ish discount data from Yahoo bookValue. Loaded once for all
# screened tickers.
_YAHOO_DISCOUNTS: dict[str, float] | None = None


def _load_aic_discounts() -> dict[str, float]:
    global _AIC_DISCOUNTS
    if _AIC_DISCOUNTS is not None:
        return _AIC_DISCOUNTS
    try:
        from aic_scraper import fetch_aic_discounts
        _AIC_DISCOUNTS = fetch_aic_discounts()
        print(f"[aic] loaded {len(_AIC_DISCOUNTS)} live UK discount records",
              file=__import__("sys").stderr)
    except Exception as exc:
        print(f"[aic] live data unavailable, using hardcoded estimates: {exc}",
              file=__import__("sys").stderr)
        _AIC_DISCOUNTS = {}
    return _AIC_DISCOUNTS


def _load_yahoo_discounts(tickers: list[str]) -> dict[str, float]:
    """Lazily load Yahoo bookValue-implied discounts for non-UK tickers."""
    global _YAHOO_DISCOUNTS
    if _YAHOO_DISCOUNTS is not None:
        return _YAHOO_DISCOUNTS
    try:
        from yahoo_nav_scraper import fetch_yahoo_discounts
        # Only fetch for tickers without an LSE-style suffix
        # (AIC already covers UK; Yahoo bookValue is the US fallback).
        non_uk = [t for t in tickers if not t.endswith(".L")]
        _YAHOO_DISCOUNTS = fetch_yahoo_discounts(non_uk)
        print(f"[yahoo] resolved {len(_YAHOO_DISCOUNTS)} non-UK "
              f"bookValue-implied discounts out of {len(non_uk)} attempted",
              file=__import__("sys").stderr)
    except Exception as exc:
        print(f"[yahoo] live data unavailable: {exc}",
              file=__import__("sys").stderr)
        _YAHOO_DISCOUNTS = {}
    return _YAHOO_DISCOUNTS


# ---------------------------------------------------------------------------
# Catalyst + NAV-quality metadata. WIND_DOWN_COMMITTED is the strongest
# pre-rating bucket only when the chart hasn't moved yet — by definition
# many of these will be POST_RERATING.

CATALYST: dict[str, str] = {
    # Confirmed managed wind-down / realisation
    "RSE.L": "WIND_DOWN_COMMITTED",
    "ADIG.L": "WIND_DOWN_COMMITTED",
    "DGI9.L": "WIND_DOWN_COMMITTED",
    "USF.L": "WIND_DOWN_COMMITTED",
    "TENT.L": "WIND_DOWN_COMMITTED",
    "HEIT.L": "WIND_DOWN_COMMITTED",
    "HGEN.L": "WIND_DOWN_COMMITTED",
    "AEET.L": "WIND_DOWN_COMMITTED",
    "AERI.L": "WIND_DOWN_COMMITTED",
    "GSEO.L": "WIND_DOWN_COMMITTED",
    "VSL.L": "WIND_DOWN_COMMITTED",
    "GABI.L": "WIND_DOWN_COMMITTED",
    "RMII.L": "WIND_DOWN_COMMITTED",
    "API.L": "WIND_DOWN_COMMITTED",
    "RESI.L": "WIND_DOWN_COMMITTED",
    "SBO.L": "WIND_DOWN_COMMITTED",
    "SUPP.L": "WIND_DOWN_COMMITTED",
    "MPLS.L": "WIND_DOWN_COMMITTED",
    "HOT.L": "WIND_DOWN_COMMITTED",
    "KPC.L": "WIND_DOWN_COMMITTED",
    "AAS.L": "WIND_DOWN_COMMITTED",
    "GRIO.L": "WIND_DOWN_COMMITTED",
    "TMI.L": "WIND_DOWN_LIKELY",  # capital-return programme; status debated
    # Strategic review / continuation pending — pre-rating territory
    "GCP.L": "STRATEGIC_REVIEW",
    "FGEN.L": "STRATEGIC_REVIEW",
    "SOHO.L": "STRATEGIC_REVIEW",
    "CHRY.L": "RETURN_OF_CAPITAL_LIVE",
    "SSIT.L": "STRATEGIC_REVIEW",
    "AUGM.L": "STRATEGIC_REVIEW",
    "GROW.L": "STRATEGIC_REVIEW",
    # Active activist / Saba campaigns
    "HRI.L": "ACTIVIST_TARGET",
    "USA.L": "ACTIVIST_TARGET",
    "CYN.L": "ACTIVIST_TARGET",
    "ESCT.L": "ACTIVIST_TARGET",
    "EWI.L": "ACTIVIST_TARGET",
    "BNKR.L": "ACTIVIST_TARGET",
    "TEM.L": "ACTIVIST_TARGET",
    "DIVI.L": "ACTIVIST_TARGET",
    "HOME.L": "DISTRESSED",
    # Structural / quality discount, no specific event
    "HVPE.L": "STRUCTURAL_DISCOUNT",
    "NBPE.L": "STRUCTURAL_DISCOUNT",
    "ICGT.L": "STRUCTURAL_DISCOUNT",
    "PIN.L": "STRUCTURAL_DISCOUNT",
    "OCI.L": "STRUCTURAL_DISCOUNT",
    "APAX.L": "STRUCTURAL_DISCOUNT",
    "CTPE.L": "STRUCTURAL_DISCOUNT",
    "HGT.L": "STRUCTURAL_DISCOUNT",
    "UKW.L": "STRUCTURAL_DISCOUNT",
    "TRIG.L": "STRUCTURAL_DISCOUNT",
    "FSFL.L": "STRUCTURAL_DISCOUNT",
    "NESF.L": "STRUCTURAL_DISCOUNT",
    "BSIF.L": "STRUCTURAL_DISCOUNT",
    "JLEN.L": "STRUCTURAL_DISCOUNT",
    "GRID.L": "STRUCTURAL_DISCOUNT",
    "SEIT.L": "STRUCTURAL_DISCOUNT",
    "HICL.L": "STRUCTURAL_DISCOUNT",
    "INPP.L": "STRUCTURAL_DISCOUNT",
    "3IN.L": "STRUCTURAL_DISCOUNT",
    "PINT.L": "STRUCTURAL_DISCOUNT",
    "CORD.L": "STRUCTURAL_DISCOUNT",
    "BPCR.L": "STRUCTURAL_DISCOUNT",
    "VTA.L": "STRUCTURAL_DISCOUNT",
    "NCYF.L": "STRUCTURAL_DISCOUNT",
    "TFIF.L": "STRUCTURAL_DISCOUNT",
    "SEQI.L": "STRUCTURAL_DISCOUNT",
    "SREI.L": "STRUCTURAL_DISCOUNT",
    "CREI.L": "STRUCTURAL_DISCOUNT",
    "RGL.L": "STRUCTURAL_DISCOUNT",
    "AEWU.L": "STRUCTURAL_DISCOUNT",
    "PCTN.L": "STRUCTURAL_DISCOUNT",
    "WHR.L": "STRUCTURAL_DISCOUNT",
    "ESP.L": "STRUCTURAL_DISCOUNT",
    "HLCL.L": "STRUCTURAL_DISCOUNT",
    "PSDL.L": "STRUCTURAL_DISCOUNT",
    "RECI.L": "STRUCTURAL_DISCOUNT",
    "VOF.L": "STRUCTURAL_DISCOUNT",
    "VNH.L": "STRUCTURAL_DISCOUNT",
    "PSH.L": "STRUCTURAL_DISCOUNT",
    "TFG.L": "STRUCTURAL_DISCOUNT",
    "TPOU.L": "STRUCTURAL_DISCOUNT",
    "BHMG.L": "STRUCTURAL_DISCOUNT",
    "NAS.L": "STRUCTURAL_DISCOUNT",
    "CLDN.L": "STRUCTURAL_DISCOUNT",
    "RCP.L": "STRUCTURAL_DISCOUNT",
    "AGT.L": "STRUCTURAL_DISCOUNT",
    "AJOT.L": "STRUCTURAL_DISCOUNT",
    "ONWD.L": "STRUCTURAL_DISCOUNT",
    "OIT.L": "STRUCTURAL_DISCOUNT",
    "SEC.L": "STRUCTURAL_DISCOUNT",
    # Australian LICs
    "LSF.AX": "ACTIVIST_TARGET",         # Saba campaign
    "WAM.AX": "STRUCTURAL_DISCOUNT",
    "WLE.AX": "STRUCTURAL_DISCOUNT",
    "WGB.AX": "STRUCTURAL_DISCOUNT",
    "WAA.AX": "STRUCTURAL_DISCOUNT",
    "TGF.AX": "STRATEGIC_REVIEW",         # discount-control / wind-up
    "HM1.AX": "STRUCTURAL_DISCOUNT",
    "MFF.AX": "STRUCTURAL_DISCOUNT",
    "PIA.AX": "STRATEGIC_REVIEW",         # restructure history
    "PE1.AX": "STRUCTURAL_DISCOUNT",
    "NCC.AX": "STRUCTURAL_DISCOUNT",
    "NSC.AX": "STRUCTURAL_DISCOUNT",
    "GC1.AX": "STRUCTURAL_DISCOUNT",
    "PL8.AX": "STRUCTURAL_DISCOUNT",
    "OBL.AX": "STRUCTURAL_DISCOUNT",
    "SOL.AX": "STRUCTURAL_DISCOUNT",
    "AUI.AX": "STRUCTURAL_DISCOUNT",
    "DUI.AX": "STRUCTURAL_DISCOUNT",
    "WHF.AX": "STRUCTURAL_DISCOUNT",
    "ARG.AX": "STRUCTURAL_DISCOUNT",
    "AFI.AX": "STRUCTURAL_DISCOUNT",
    # Canadian special sits
    "POW.TO": "STRUCTURAL_DISCOUNT",
    "ONEX.TO": "STRUCTURAL_DISCOUNT",
    "BAM.TO": "STRUCTURAL_DISCOUNT",
    "DGS.TO": "STRUCTURAL_DISCOUNT",
    "FTN.TO": "STRUCTURAL_DISCOUNT",
    "LBS.TO": "STRUCTURAL_DISCOUNT",
    "BSP.TO": "STRUCTURAL_DISCOUNT",
    "FFN.TO": "STRUCTURAL_DISCOUNT",
    "LCS.TO": "STRUCTURAL_DISCOUNT",
    # US sum-of-parts / conglomerate
    "IAC": "STRUCTURAL_DISCOUNT",
    "L": "STRUCTURAL_DISCOUNT",
    "FWONK": "STRUCTURAL_DISCOUNT",
    "BATRA": "STRUCTURAL_DISCOUNT",
    "LBRDK": "STRUCTURAL_DISCOUNT",
    "LILA": "STRUCTURAL_DISCOUNT",
    "MSGS": "STRUCTURAL_DISCOUNT",
    "MSGE": "STRUCTURAL_DISCOUNT",
    "LGF.A": "STRUCTURAL_DISCOUNT",
    # Swiss / EU specialist
    "BION.SW": "STRUCTURAL_DISCOUNT",
    "HBMN.SW": "STRUCTURAL_DISCOUNT",
    # UK extras 2
    "MIGO.L": "STRUCTURAL_DISCOUNT",
    "ARR.L": "STRUCTURAL_DISCOUNT",
    "JAM.L": "STRUCTURAL_DISCOUNT",
    "MUT.L": "STRUCTURAL_DISCOUNT",
    "LWDB.L": "STRUCTURAL_DISCOUNT",
    "BIPS.L": "STRUCTURAL_DISCOUNT",
    "FAIR.L": "STRUCTURAL_DISCOUNT",
    "SDP.L": "STRATEGIC_REVIEW",          # merger candidate
    "ATR.L": "STRATEGIC_REVIEW",          # merger candidate
    "NAVF.L": "ACTIVIST_TARGET",          # itself runs activist mandate
    # Listed PE GP at discount
    "BPT.L": "STRUCTURAL_DISCOUNT",
    "EQT.ST": "STRUCTURAL_DISCOUNT",
    "PGHN.SW": "STRUCTURAL_DISCOUNT",
    "CVC.AS": "STRUCTURAL_DISCOUNT",
    # Korean chaebol holdcos
    "003550.KS": "STRUCTURAL_DISCOUNT",   # LG Corp
    "028260.KS": "STRUCTURAL_DISCOUNT",   # Samsung C&T
    "005380.KS": "STRUCTURAL_DISCOUNT",   # Hyundai Motor
    "005490.KS": "STRUCTURAL_DISCOUNT",   # POSCO Holdings
    # Japanese trading houses / SoftBank
    "8001.T": "STRUCTURAL_DISCOUNT",
    "8053.T": "STRUCTURAL_DISCOUNT",
    "8002.T": "STRUCTURAL_DISCOUNT",
    "9101.T": "STRUCTURAL_DISCOUNT",
    "9984.T": "STRUCTURAL_DISCOUNT",
    # European extras
    "HEIO.AS": "STRUCTURAL_DISCOUNT",
    "ITM.MI": "STRUCTURAL_DISCOUNT",
    "CIR.MI": "STRUCTURAL_DISCOUNT",
    # FDB scanner finds — default to STRUCTURAL_DISCOUNT
    **{t: "STRUCTURAL_DISCOUNT" for t in [
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
    ]},
}

# Catalyst-implied discount-narrowing rule of thumb. These are
# illustrative averages — actual narrowing depends on starting
# discount (which the screener doesn't know) and execution. Used
# as a proxy when ranking "greatest upside".
CATALYST_IMPLIED_UPSIDE: dict[str, float] = {
    "WIND_DOWN_COMMITTED": 0.20,
    "WIND_DOWN_LIKELY": 0.18,
    "RETURN_OF_CAPITAL_LIVE": 0.15,
    "STRATEGIC_REVIEW": 0.15,
    "ACTIVIST_TARGET": 0.15,
    "STRUCTURAL_DISCOUNT": 0.08,
    "DISTRESSED": 0.05,  # high variance, mostly skip
}


# True "upside" for this strategy = discount-to-NAV closure.
# DISCOUNT_ESTIMATE is the *current discount* (positive = discount,
# negative = premium) per ticker, sourced from public-information
# averages over my training period. These are NOT live numbers —
# refresh from theaic.co.uk / QuotedData / CEFConnect / AIC API
# before sizing. Names not in this dict default to 0.10 (10%) to
# avoid implying false precision.
DISCOUNT_ESTIMATE: dict[str, float] = {
    # UK closed-end funds (typical mid-2024 -> early-2026 ranges)
    "RSE.L": 0.20, "ADIG.L": 0.30, "DGI9.L": 0.40, "USF.L": 0.25,
    "TENT.L": 0.30, "HEIT.L": 0.40, "HGEN.L": 0.45, "AEET.L": 0.30,
    "AERI.L": 0.35, "GSEO.L": 0.35, "VSL.L": 0.20, "GABI.L": 0.20,
    "RMII.L": 0.20, "API.L": 0.15, "RESI.L": 0.30, "SBO.L": 0.40,
    "SUPP.L": 0.50, "MPLS.L": 0.30, "HOT.L": 0.10, "KPC.L": 0.15,
    "AAS.L": 0.15, "TMI.L": 0.20, "GCP.L": 0.30, "FGEN.L": 0.30,
    "SOHO.L": 0.30, "CHRY.L": 0.35, "SSIT.L": 0.25, "AUGM.L": 0.30,
    "GROW.L": 0.30, "HRI.L": 0.13, "USA.L": 0.13, "CYN.L": 0.12,
    "ESCT.L": 0.12, "EWI.L": 0.13, "BNKR.L": 0.12, "TEM.L": 0.11,
    "DIVI.L": 0.13, "HOME.L": 0.50,  # workout, NAV unreliable
    "HVPE.L": 0.35, "NBPE.L": 0.25, "ICGT.L": 0.30, "PIN.L": 0.25,
    "OCI.L": 0.30, "APAX.L": 0.30, "CTPE.L": 0.30, "HGT.L": 0.10,
    "UKW.L": 0.18, "TRIG.L": 0.22, "FSFL.L": 0.22, "NESF.L": 0.22,
    "BSIF.L": 0.18, "JLEN.L": 0.22, "GRID.L": 0.30, "SEIT.L": 0.30,
    "HICL.L": 0.18, "INPP.L": 0.18, "3IN.L": 0.10, "PINT.L": 0.13,
    "CORD.L": 0.30, "BPCR.L": 0.10, "VTA.L": 0.10, "NCYF.L": 0.05,
    "TFIF.L": 0.05, "SEQI.L": 0.10, "RECI.L": 0.13, "SREI.L": 0.30,
    "CREI.L": 0.20, "RGL.L": 0.50, "AEWU.L": 0.10, "PCTN.L": 0.30,
    "WHR.L": 0.15, "ESP.L": 0.20, "HLCL.L": 0.40, "PSDL.L": 0.30,
    "VOF.L": 0.20, "VNH.L": 0.15,
    "PSH.L": 0.30, "TFG.L": 0.45, "TPOU.L": 0.20, "BHMG.L": 0.05,
    "NAS.L": 0.25, "CLDN.L": 0.30, "RCP.L": 0.25, "AGT.L": 0.08,
    "AJOT.L": 0.07, "ONWD.L": 0.10, "OIT.L": 0.07, "SEC.L": 0.13,
    "BBH.L": 0.08, "IBT.L": 0.10, "WWH.L": 0.07, "BIOG.L": 0.10,
    "RTW.L": 0.10, "FCSS.L": 0.13, "PHI.L": 0.10, "PAC.L": 0.10,
    "BRLA.L": 0.13, "JEMI.L": 0.10, "AAIF.L": 0.13, "MYI.L": 0.07,
    "MIGO.L": 0.05, "ARR.L": 0.05, "JAM.L": 0.07, "MUT.L": 0.08,
    "LWDB.L": 0.05, "BIPS.L": 0.05, "FAIR.L": 0.20, "SDP.L": 0.08,
    "ATR.L": 0.08, "NAVF.L": 0.05,
    # Australian LICs
    "LSF.AX": 0.20, "WAM.AX": 0.05, "WLE.AX": 0.05, "WGB.AX": 0.10,
    "WAA.AX": 0.05, "TGF.AX": 0.20, "HM1.AX": 0.20, "MFF.AX": 0.10,
    "PIA.AX": 0.20, "PE1.AX": 0.20, "NCC.AX": 0.10, "NSC.AX": 0.10,
    "GC1.AX": 0.15, "PL8.AX": 0.05, "OBL.AX": 0.10, "SOL.AX": 0.05,
    "AUI.AX": 0.10, "DUI.AX": 0.10, "WHF.AX": 0.13, "ARG.AX": 0.05,
    "AFI.AX": 0.05,
    # Canadian
    "POW.TO": 0.25, "ONEX.TO": 0.30, "BAM.TO": 0.10,
    "DGS.TO": 0.05, "FTN.TO": 0.05, "LBS.TO": 0.05, "BSP.TO": 0.05,
    "FFN.TO": 0.05, "LCS.TO": 0.05,
    # US conglomerate
    "IAC": 0.30, "L": 0.20, "FWONK": 0.15, "BATRA": 0.15,
    "LBRDK": 0.20, "LILA": 0.30, "MSGS": 0.20, "MSGE": 0.30,
    "LGF.A": 0.15,
    # Swiss/EU specialist
    "BION.SW": 0.20, "HBMN.SW": 0.18,
    # Listed PE GP
    "BPT.L": 0.30, "EQT.ST": 0.10, "PGHN.SW": 0.0, "CVC.AS": 0.10,
    # Korean chaebol holdcos (large structural discounts)
    "003550.KS": 0.55, "028260.KS": 0.50, "005380.KS": 0.45, "005490.KS": 0.40,
    # Japanese sogo shosha + SoftBank
    "8001.T": 0.10, "8053.T": 0.10, "8002.T": 0.15, "9101.T": 0.30,
    "9984.T": 0.50,
    # European extras
    "HEIO.AS": 0.15, "ITM.MI": 0.40, "CIR.MI": 0.40,
    # EU holdco
    "SOF.BR": 0.30, "GBLB.BR": 0.30, "ACKB.BR": 0.20, "MF.PA": 0.40,
    "RF.PA": 0.40, "BOL.PA": 0.30, "INDU-C.ST": 0.20, "INVE-B.ST": 0.20,
    "KINV-B.ST": 0.30, "LATO-B.ST": 0.10, "LUND-B.ST": 0.20,
    "AKER.OL": 0.30, "BONHR.OL": 0.30, "EXO.AS": 0.40, "PRX.AS": 0.40,
    "NPN.JO": 0.40,
    # US CEFs / BDCs — typical discounts smaller
    "BRW": 0.05, "BIF": 0.13, "GAM": 0.13, "CET": 0.15, "ADX": 0.13,
    "PEO": 0.15, "TY": 0.13, "SOR": 0.10, "FUND": 0.13, "RVT": 0.10,
    "RMT": 0.08, "RGT": 0.13, "GAB": 0.10, "GDV": 0.10, "GUT": -0.10,
    "BST": 0.05, "BUI": 0.05, "BME": 0.05, "BTO": 0.10, "ECC": -0.05,
    "EIC": 0.05, "OXLC": 0.0, "ASA": 0.10, "GGT": 0.13, "MIN": 0.10,
    "ASGI": 0.13, "AOD": 0.05, "AWP": 0.10, "FOF": 0.05, "JLS": 0.10,
    "JMM": 0.10, "ETW": 0.05, "ETV": 0.05, "EOI": 0.05,
    "BKCC": 0.10, "PSEC": 0.30, "PFLT": 0.05, "PNNT": 0.20,
    "GLAD": -0.05, "GAIN": -0.05, "OFS": 0.20, "PTMN": 0.20,
    "LRFC": 0.20, "MFIC": 0.20, "BBDC": 0.10, "CGBD": 0.05,
    "GBDC": 0.0, "SCM": 0.10, "SAR": 0.05, "RAND": 0.20,
}


# Catalyst realisation probability — likelihood that within ~12-18m
# the catalyst actually narrows the discount meaningfully. Reflects
# event clarity, not magnitude. Combined with discount to give
# expected upside.
CATALYST_REALISATION_PROBABILITY: dict[str, float] = {
    "WIND_DOWN_COMMITTED": 0.80,
    "WIND_DOWN_LIKELY": 0.60,
    "RETURN_OF_CAPITAL_LIVE": 0.70,
    "STRATEGIC_REVIEW": 0.50,
    "ACTIVIST_TARGET": 0.45,
    "STRUCTURAL_DISCOUNT": 0.20,
    "DISTRESSED": 0.20,
}

# NAV reliability — listed-asset trusts have observable NAV; private/
# infrastructure/biotech NAVs are model-driven and often overstated.
NAV_QUALITY: dict[str, str] = {
    # Listed equity portfolios — clean
    **{t: "LISTED_CLEAN" for t in [
        "NAS.L", "CLDN.L", "RCP.L", "AGT.L", "AJOT.L", "ONWD.L", "SEC.L",
        "OIT.L", "DIVI.L", "HRI.L", "USA.L", "CYN.L", "ESCT.L", "EWI.L",
        "BNKR.L", "TEM.L", "VOF.L", "VNH.L", "BRFI.L", "PHI.L", "PAC.L",
        "MYI.L", "AAIF.L", "JEMI.L", "JMG.L", "FEML.L", "MMIT.L", "FCSS.L",
        "PSH.L", "TPOU.L", "BHMG.L", "ANII.L", "JAGI.L", "JEDT.L", "BRSC.L",
        "THRG.L", "BRWM.L", "BERI.L", "HFEL.L", "SCF.L", "LWI.L", "HHI.L",
        "MRC.L", "BUT.L", "HSL.L", "SCP.L", "SSON.L", "ASL.L", "AGVI.L",
        "BGFD.L", "JFJ.L", "RIII.L", "MNL.L", "KPC.L", "HOT.L", "AUSC.L",
        "ASCI.L", "BBH.L", "IBT.L", "WWH.L", "BIOG.L", "RTW.L", "BRLA.L",
    ]},
    # Debt amortising — pulls to par
    **{t: "DEBT_AMORTISING" for t in [
        "GCP.L", "GABI.L", "RMII.L", "VSL.L", "BPCR.L", "VTA.L", "NCYF.L",
        "TFIF.L", "SEQI.L", "MPLS.L", "RECI.L",
    ]},
    # Infrastructure DCF — model but audited
    **{t: "INFRA_DCF" for t in [
        "HICL.L", "INPP.L", "3IN.L", "PINT.L", "CORD.L", "DGI9.L",
    ]},
    # Renewables / energy infra — model + asset-specific risk
    **{t: "RENEWABLES_DCF" for t in [
        "UKW.L", "TRIG.L", "FSFL.L", "NESF.L", "BSIF.L", "JLEN.L",
        "GRID.L", "SEIT.L", "FGEN.L", "GSEO.L", "HEIT.L", "HGEN.L",
        "AEET.L", "AERI.L", "USF.L", "TENT.L",
    ]},
    # Property — model-driven, can be optimistic in stressed markets
    **{t: "PROPERTY_DCF" for t in [
        "API.L", "RESI.L", "SREI.L", "CREI.L", "RGL.L", "AEWU.L",
        "PCTN.L", "WHR.L", "ESP.L", "HLCL.L", "PSDL.L", "SOHO.L", "GRIO.L",
    ]},
    # Private equity — model-driven, illiquid
    **{t: "PRIVATE_EQUITY" for t in [
        "HVPE.L", "NBPE.L", "ICGT.L", "PIN.L", "OCI.L", "APAX.L",
        "CTPE.L", "HGT.L", "SBO.L", "SUPP.L", "CHRY.L", "SSIT.L",
        "AUGM.L", "GROW.L",
    ]},
    # Real assets — vessels, aircraft (observable secondary market)
    **{t: "REAL_ASSET_OBSERVABLE" for t in [
        "TMI.L", "SHIP.L", "DNA2.L", "DNA3.L", "AA4.L", "DPA.L",
    ]},
    # Distressed / unreliable
    **{t: "DISTRESSED" for t in ["HOME.L", "ADIG.L", "AAS.L", "KKVL.L"]},
    # New universe additions
    **{t: "LISTED_CLEAN" for t in [
        # Australian LICs (mostly listed equity portfolios)
        "LSF.AX", "WAM.AX", "WLE.AX", "WGB.AX", "WAA.AX", "HM1.AX",
        "MFF.AX", "PIA.AX", "NCC.AX", "NSC.AX", "GC1.AX", "PL8.AX",
        "AUI.AX", "DUI.AX", "WHF.AX", "ARG.AX", "AFI.AX",
        # UK extras 2 (listed-equity trusts)
        "MIGO.L", "ARR.L", "JAM.L", "MUT.L", "LWDB.L", "BIPS.L",
        "SDP.L", "ATR.L",
        # Swiss specialist (listed biotech/healthcare)
        "BION.SW", "HBMN.SW",
        # US conglomerate (listed subsidiary stubs)
        "FWONK", "BATRA", "LBRDK", "LILA", "MSGS", "MSGE", "LGF.A",
    ]},
    **{t: "REAL_ASSET_OBSERVABLE" for t in [
        "TGF.AX",  # Tribeca Natural Resources
    ]},
    **{t: "PRIVATE_EQUITY" for t in [
        "PE1.AX",       # Pengana Private Equity
        "ONEX.TO",      # Onex
        "BAM.TO",       # Brookfield AM
        "POW.TO",       # Power Corp (mixed listed/private)
        "SOL.AX",       # Soul Patts (mixed listed/private)
        "OBL.AX",       # Omni Bridgeway (litigation, model-driven)
        "FAIR.L",       # Fair Oaks (CLO equity, model)
    ]},
    # Canadian split corps — debt-amortising-ish capital structure
    **{t: "DEBT_AMORTISING" for t in [
        "DGS.TO", "FTN.TO", "LBS.TO", "BSP.TO", "FFN.TO", "LCS.TO",
    ]},
    # IAC and Loews — sum-of-parts of mostly-listed subsidiaries
    "IAC": "LISTED_CLEAN",
    "L": "LISTED_CLEAN",
    # FDB scanner finds — auto-tagged by name-pattern heuristic
    **{t: "DEBT_AMORTISING" for t in [
        "AD-UN.TO", "CCD", "CHI", "CHW", "CHY", "CTF-UN.TO", "EIT-UN.TO",
        "FGT.L", "GCI.AX", "KKC.AX", "MGCI.L", "MXT.AX", "NAIT.L",
        "PCI.AX", "QRI.AX", "SOI.L", "TBLD", "TCF.AX", "TORO.L", "VIP.L",
        "MOT.AX",  # MCP Income Opps
    ]},
    **{t: "LISTED_CLEAN" for t in [
        "AIE.L", "AIQ.AX", "APL.AX", "BGCG.L", "BGEU.L", "BKI.AX",
        "BRIG.L", "BRGE.L", "CCJI.L", "CIC.L", "CTY.L", "DIG.L",
        "EDIN.L", "FAP.TO", "FCIT.L", "FGG.AX", "FGX.AX", "IGC.L",
        "IIGF.AX", "JETG.L", "JGGI.L", "JUSC.L", "LTI.L", "MA1.AX",
        "MAET.AX", "MNKS.L", "MTE.L", "MTU.L", "MWY.L", "NSI.L",
        "OIG.L", "PIC.AX", "RICA.L", "RMMC.L", "SAIN.L", "SJG.L",
        "SMT.L", "SST.L", "SWTZ.AX", "TMPL.L", "TRG.L",
    ]},
    **{t: "PRIVATE_EQUITY" for t in [
        "BNK.TO", "CD1.AX", "CD2.AX", "CD3.AX", "CPEN.SW",
        "DF.TO", "DFN.TO", "DGS-PA.TO", "ENS.TO", "GDV-PA.TO", "GDV.TO",
        "JPEL.L", "LBS-PA.TO", "LCS-PA.TO", "LFE.TO", "PEY.L", "PEYS.L",
        "PRM.TO", "PVS-PH.TO", "PVS-PJ.TO", "SLPE.L", "XTD.TO",
    ]},
    **{t: "PROPERTY_DCF" for t in ["RS.TO", "TRY.L"]},
}


# ---------------------------------------------------------------------------

@dataclass
class ScreenResult:
    ticker: str
    error: str | None = None
    last_close: float | None = None
    base_start: pd.Timestamp | None = None
    base_length_weeks: int | None = None
    base_range_pct: float | None = None  # (max-min)/mean
    base_low: float | None = None
    base_high: float | None = None
    poc: float | None = None
    poc_distance_pct: float | None = None
    chg_13w_pct: float | None = None
    chg_26w_pct: float | None = None
    last_vol: float | None = None
    base_vol_mean: float | None = None
    vol_z: float | None = None  # latest vol vs base mean/std
    spike_in_base: bool = False  # vol spike printed inside the base, not after a breakout
    mfi: float | None = None
    mfi_rising: bool | None = None
    distribution_recent: bool = False  # > 5% drop in close on a single bar suggests cap return / distribution
    phase: str = "UNKNOWN"
    catalyst: str | None = None
    nav_quality: str | None = None
    score: float = 0.0
    # Upside metrics
    room_to_base_high_pct: float | None = None  # technical room within base (NOT real upside)
    room_to_5y_high_pct: float | None = None    # (5y_high - close)/close
    nav_discount_est: float | None = None       # current discount-to-NAV (estimate)
    discount_closure_upside: float | None = None  # discount/(1-discount) — return if discount fully closes
    catalyst_realisation_prob: float | None = None  # P(catalyst fires within ~12-18m)
    expected_upside: float | None = None        # discount_closure_upside * catalyst_realisation_prob
    catalyst_upside_est: float | None = None    # legacy: rule-of-thumb % narrowing per catalyst
    upside_combined: float | None = None        # legacy
    value_score: float = 0.0                    # score * (1 + expected_upside)
    discount_source: str | None = None          # "aic_live" or "estimate"


def detect_base(df: pd.DataFrame, max_lookback: int = 208,
                range_threshold: float = 0.30,
                min_length: int = 13) -> pd.DataFrame:
    """Return the slice of df representing the longest recent
    contiguous base where rolling range/mean <= threshold."""
    n = len(df)
    if n < min_length:
        return df
    closes = df["Close"].to_numpy()
    end = n
    start = end - 1
    upper = max(0, n - max_lookback)
    while start > upper:
        candidate = start - 1
        window = closes[candidate:end]
        rng = (window.max() - window.min()) / window.mean()
        if rng > range_threshold:
            break
        start = candidate
    if end - start < min_length:
        # widen threshold once for shorter tighter bases (small rangebound trusts)
        return df.tail(min_length)
    return df.iloc[start:end]


def base_volume_profile(base: pd.DataFrame, bins: int = 60):
    """POC computed *only* on the base period."""
    if base.empty:
        return None
    lo = float(base["Low"].min())
    hi = float(base["High"].max())
    if not (np.isfinite(lo) and np.isfinite(hi)) or hi <= lo:
        return None
    edges = np.linspace(lo, hi, bins + 1)
    centers = 0.5 * (edges[:-1] + edges[1:])
    vols = np.zeros(bins)
    for low, high, vol in zip(base["Low"].to_numpy(), base["High"].to_numpy(),
                              base["Volume"].to_numpy()):
        if not (np.isfinite(low) and np.isfinite(high) and np.isfinite(vol)):
            continue
        if high <= low or vol <= 0:
            continue
        lo_idx = max(0, int(np.searchsorted(edges, low, side="right") - 1))
        hi_idx = min(bins - 1, int(np.searchsorted(edges, high, side="right") - 1))
        if hi_idx < lo_idx:
            continue
        n = hi_idx - lo_idx + 1
        vols[lo_idx:hi_idx + 1] += vol / n
    if vols.sum() <= 0:
        return None
    return float(centers[int(np.argmax(vols))])


def classify_phase(*, in_base: bool, vol_z: float | None,
                   chg_13w: float | None, last_close: float, base_high: float,
                   base_low: float, distribution_recent: bool) -> str:
    if distribution_recent:
        return "DISTRIBUTION_DRIVEN"
    if chg_13w is not None and chg_13w > 0.15:
        return "POST_RERATING"
    if not in_base:
        if chg_13w is not None and chg_13w < -0.15:
            return "DOWNTREND"
        return "NO_BASE"
    # in-base
    above_high = last_close > base_high * 1.03
    if above_high and vol_z is not None and vol_z >= 2.0:
        return "BASE_BREAKOUT"
    if vol_z is not None and vol_z >= 1.5:
        return "BASE_ABSORBING"
    if chg_13w is not None and chg_13w < -0.08:
        return "BASE_DECLINING"
    return "BASE_QUIET"


def screen_one(ticker: str, *, max_lookback: int = 208,
               range_threshold: float = 0.30, mfi_period: int = 18) -> ScreenResult:
    res = ScreenResult(ticker=ticker)
    res.catalyst = CATALYST.get(ticker)
    res.nav_quality = NAV_QUALITY.get(ticker)
    try:
        # auto_adjust=True back-adjusts for splits AND dividends, which
        # makes capital-return distributions invisible to price (correct
        # — investor got cash for the difference) and removes spurious
        # 99% drops from splits.
        data = yf.download(ticker, period="5y", interval="1wk",
                           progress=False, auto_adjust=True)
    except Exception as exc:
        res.error = f"download: {exc}"
        return res
    if data is None or data.empty:
        res.error = "no data"
        return res
    if isinstance(data.columns, pd.MultiIndex):
        data.columns = data.columns.get_level_values(0)
    data = data.dropna(subset=["Close", "Volume"])
    # Hygiene: yfinance occasionally returns Low=0 prints from bad
    # ticks. Clamp to bar's open/close to avoid contaminating range
    # statistics.
    bad_lows = (data["Low"] <= 0) | (data["Low"].isna())
    if bad_lows.any():
        data.loc[bad_lows, "Low"] = data.loc[bad_lows, ["Open", "Close"]].min(axis=1)
    if len(data) < 30:
        res.error = "insufficient bars"
        return res

    res.last_close = float(data["Close"].iloc[-1])

    base = detect_base(data, max_lookback=max_lookback,
                       range_threshold=range_threshold)
    res.base_start = base.index[0]
    res.base_length_weeks = len(base)
    # Use Close-based range to avoid one-off bad Low/High prints.
    base_close = base["Close"]
    base_lo = float(base_close.min())
    base_hi = float(base_close.max())
    base_close_mean = float(base_close.mean())
    res.base_low = base_lo
    res.base_high = base_hi
    res.base_range_pct = (base_hi - base_lo) / base_close_mean if base_close_mean > 0 else None

    poc = base_volume_profile(base)
    res.poc = poc
    if poc and poc > 0:
        res.poc_distance_pct = abs(res.last_close - poc) / poc

    if len(data) >= 14:
        res.chg_13w_pct = float(data["Close"].iloc[-1] / data["Close"].iloc[-14] - 1)
    if len(data) >= 27:
        res.chg_26w_pct = float(data["Close"].iloc[-1] / data["Close"].iloc[-27] - 1)

    base_vol = base["Volume"].astype(float)
    res.last_vol = float(data["Volume"].iloc[-1])
    res.base_vol_mean = float(base_vol.mean()) if len(base_vol) else None
    if len(base_vol) >= 5 and base_vol.std() > 0:
        res.vol_z = (res.last_vol - base_vol.mean()) / base_vol.std()

    # Distribution-driven price drop heuristic: any single weekly close
    # decline > 8% in the last 6 weeks is suspicious for a cap-return
    # event we may not want to read as natural price action.
    recent = data["Close"].iloc[-6:]
    if len(recent) >= 2:
        weekly_chg = recent.pct_change().dropna()
        res.distribution_recent = bool((weekly_chg < -0.08).any())

    in_base = res.last_close >= base_lo * 0.95 and res.last_close <= base_hi * 1.05

    res.phase = classify_phase(
        in_base=in_base, vol_z=res.vol_z, chg_13w=res.chg_13w_pct,
        last_close=res.last_close, base_high=base_hi, base_low=base_lo,
        distribution_recent=res.distribution_recent,
    )

    # Spike-in-base means vol_z high while still inside the base
    # range — i.e. accumulation, not breakout-after-the-fact.
    res.spike_in_base = (
        res.vol_z is not None and res.vol_z >= 1.5
        and in_base and not res.distribution_recent
    )

    mfi_series = money_flow_index(data, mfi_period)
    if len(mfi_series.dropna()) >= 2:
        res.mfi = float(mfi_series.iloc[-1])
        res.mfi_rising = float(mfi_series.iloc[-1]) > float(mfi_series.iloc[-2])

    # Technical metrics (not the same as fundamental upside)
    if res.last_close and base_hi:
        res.room_to_base_high_pct = (base_hi - res.last_close) / res.last_close
    if res.last_close and len(data) >= 26:
        full_high = float(data["High"].iloc[-min(260, len(data)):].max())
        res.room_to_5y_high_pct = (full_high - res.last_close) / res.last_close

    # Real fundamental upside = closing the discount-to-NAV.
    # discount of d => price * (1/(1-d)) at NAV => upside = d/(1-d)
    # Priority: live AIC (UK CEFs) > live Yahoo bookValue (US CEFs/BDCs)
    # > hardcoded estimate.
    aic_discounts = _load_aic_discounts()
    if ticker in aic_discounts:
        discount = aic_discounts[ticker]
        res.discount_source = "aic_live"
    elif ticker in (_YAHOO_DISCOUNTS or {}):
        discount = _YAHOO_DISCOUNTS[ticker]
        res.discount_source = "yahoo_live"
    else:
        discount = DISCOUNT_ESTIMATE.get(ticker, 0.10)
        res.discount_source = "estimate"
    res.nav_discount_est = discount
    if discount < 1.0:
        res.discount_closure_upside = discount / (1.0 - discount) if discount > -0.99 else 0.0
    else:
        res.discount_closure_upside = 0.0
    # Probability the catalyst actually closes (or meaningfully
    # narrows) the discount over a ~12-18m horizon.
    prob = CATALYST_REALISATION_PROBABILITY.get(res.catalyst, 0.20)
    res.catalyst_realisation_prob = prob
    res.expected_upside = (res.discount_closure_upside or 0.0) * prob

    # Legacy fields kept for backward compatibility with prior tables.
    res.catalyst_upside_est = CATALYST_IMPLIED_UPSIDE.get(res.catalyst, 0.05)
    candidates = [v for v in (res.room_to_base_high_pct, res.catalyst_upside_est) if v is not None]
    res.upside_combined = max(0.0, max(candidates)) if candidates else 0.0

    res.score = compute_score(res)
    res.value_score = res.score * (1.0 + (res.expected_upside or 0.0))
    return res


def compute_score(r: ScreenResult) -> float:
    if r.error or not r.poc or r.last_close is None:
        return 0.0

    # Phase weight
    phase_w = {
        "BASE_ABSORBING": 1.00,
        "BASE_BREAKOUT": 0.80,
        "BASE_QUIET": 0.55,
        "BASE_DECLINING": 0.35,
        "POST_RERATING": 0.05,
        "DISTRIBUTION_DRIVEN": 0.05,
        "DOWNTREND": 0.10,
        "NO_BASE": 0.10,
    }.get(r.phase, 0.10)

    # Catalyst weight (pre-rating pathways score higher)
    cat_w = {
        "STRATEGIC_REVIEW": 1.00,
        "ACTIVIST_TARGET": 0.90,
        "RETURN_OF_CAPITAL_LIVE": 0.80,
        "WIND_DOWN_LIKELY": 0.75,
        "WIND_DOWN_COMMITTED": 0.55,  # committed but often post-event on chart
        "STRUCTURAL_DISCOUNT": 0.40,
        "DISTRESSED": 0.10,
    }.get(r.catalyst, 0.30)

    # NAV reliability weight
    nav_w = {
        "LISTED_CLEAN": 1.00,
        "REAL_ASSET_OBSERVABLE": 0.90,
        "DEBT_AMORTISING": 0.85,
        "INFRA_DCF": 0.75,
        "RENEWABLES_DCF": 0.55,
        "PROPERTY_DCF": 0.55,
        "PRIVATE_EQUITY": 0.40,
        "DISTRESSED": 0.15,
    }.get(r.nav_quality, 0.50)

    # POC proximity scaled by base width — full credit when on POC,
    # zero when at the edge of the base. This stops names whose
    # accumulation has happened lower (price drifting up off POC) from
    # scoring zero just because they're > 10% off POC.
    pd_pct = r.poc_distance_pct or 1.0
    edge = max(r.base_range_pct or 0.10, 0.10)
    poc_w = max(0.0, 1.0 - (pd_pct / edge))

    # Base length — longer base = bigger setup
    bl = r.base_length_weeks or 0
    base_w = min(1.0, bl / 52)  # full credit at 1y+ base

    # Penalise post-rerating outright
    if r.phase == "POST_RERATING":
        return 0.0

    return phase_w * cat_w * nav_w * poc_w * base_w


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--range-threshold", type=float, default=0.30)
    parser.add_argument("--max-lookback", type=int, default=208)
    parser.add_argument("--mfi-period", type=int, default=18)
    parser.add_argument("--top", type=int, default=25)
    parser.add_argument("--tickers", nargs="*", default=None)
    parser.add_argument("--groups", nargs="*", default=None)
    args = parser.parse_args()

    if args.tickers:
        symbols = [t.upper() if "." in t else f"{t.upper()}.L" for t in args.tickers]
    elif args.groups:
        symbols = []
        for g in args.groups:
            for sym in KNOWN_CANDIDATES.get(g, []):
                if sym not in symbols:
                    symbols.append(sym)
    else:
        symbols = all_known_candidates()

    print(f"Screening {len(symbols)} tickers (range_threshold={args.range_threshold}, "
          f"max_lookback={args.max_lookback}, mfi={args.mfi_period})", file=sys.stderr)

    # Pre-load discount data sources once so they're cached for screen_one calls
    _load_aic_discounts()
    _load_yahoo_discounts(symbols)

    results: list[ScreenResult] = []
    for i, sym in enumerate(symbols, 1):
        r = screen_one(sym, max_lookback=args.max_lookback,
                       range_threshold=args.range_threshold,
                       mfi_period=args.mfi_period)
        results.append(r)
        tag = r.phase if not r.error else "ERR"
        print(f"  [{i:3d}/{len(symbols)}] {sym:<10} {tag:<22} "
              f"base={r.base_length_weeks or 0:>3}w "
              f"chg13={(r.chg_13w_pct or 0)*100:+5.1f}% "
              f"poc_d={(r.poc_distance_pct or 0)*100:5.1f}% "
              f"vol_z={r.vol_z if r.vol_z is not None else float('nan'):+5.2f} "
              f"score={r.score:.3f}",
              file=sys.stderr)
        time.sleep(0.1)

    df = pd.DataFrame([r.__dict__ for r in results])

    def show(title: str, frame: pd.DataFrame, n: int = 15,
             extra_cols: list[str] | None = None) -> None:
        print(f"\n=== {title} ({len(frame)}) ===")
        if frame.empty:
            print("(none)")
            return
        cols = ["ticker", "phase", "catalyst", "nav_quality",
                "base_length_weeks", "base_range_pct", "chg_13w_pct",
                "poc_distance_pct", "vol_z", "mfi", "score"]
        if extra_cols:
            cols = cols + extra_cols
        cols = [c for c in cols if c in frame.columns]
        print(frame[cols].head(n).to_string(index=False))

    df_ranked = df[df["error"].isna()].sort_values("score", ascending=False)

    show("TIER 1 — BASE_ABSORBING (flat tape, vol building, on POC)",
         df_ranked[df_ranked["phase"] == "BASE_ABSORBING"], args.top)

    show("TIER 2 — BASE_BREAKOUT (just broken from base on vol)",
         df_ranked[df_ranked["phase"] == "BASE_BREAKOUT"], args.top)

    show("TIER 3 — BASE_QUIET (long base, on POC, awaiting vol bar)",
         df_ranked[df_ranked["phase"] == "BASE_QUIET"], args.top)

    show("TIER 4 — BASE_DECLINING (still finding the low)",
         df_ranked[df_ranked["phase"] == "BASE_DECLINING"], args.top)

    show("EXCLUDED — POST_RERATING (already moved 13w, late entry)",
         df[df["phase"] == "POST_RERATING"].sort_values("chg_13w_pct", ascending=False),
         args.top)

    show("EXCLUDED — DISTRIBUTION_DRIVEN (single-bar drop suggests cap-return)",
         df[df["phase"] == "DISTRIBUTION_DRIVEN"], args.top)

    show("OVERALL TOP BY SCORE",
         df_ranked.head(args.top), args.top)

    # ---------------- Upside-ranked views (corrected) ----------------
    # Real upside = discount-to-NAV closure x probability.
    # `expected_upside = discount/(1-discount) * P(catalyst fires)`.
    upside_extras = ["nav_discount_est", "discount_source",
                     "discount_closure_upside",
                     "catalyst_realisation_prob", "expected_upside",
                     "value_score"]

    show("HIGHEST EXPECTED UPSIDE x SETUP "
         "(value_score = setup_score * (1 + expected_upside))",
         df_ranked.sort_values("value_score", ascending=False).head(args.top),
         args.top, extra_cols=upside_extras)

    setups_only = df_ranked[
        df_ranked["phase"].isin(["BASE_ABSORBING", "BASE_BREAKOUT", "BASE_QUIET"])
        & (df_ranked["base_range_pct"] <= 0.50)
    ]
    show("HIGHEST EXPECTED UPSIDE WITH ACTIVE SETUP "
         "(only ABSORBING / BREAKOUT / QUIET phases)",
         setups_only.sort_values("expected_upside", ascending=False).head(args.top),
         args.top, extra_cols=upside_extras)

    show("HIGHEST RAW DISCOUNT-CLOSURE UPSIDE "
         "(NAV closure if catalyst fully fires; ignores probability)",
         setups_only.sort_values("discount_closure_upside",
                                 ascending=False).head(args.top),
         args.top, extra_cols=upside_extras)

    return 0


if __name__ == "__main__":
    sys.exit(main())
