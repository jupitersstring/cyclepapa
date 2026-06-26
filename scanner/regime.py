"""
Regime overlay -- features the core composite cannot see by itself.

This module synthesises five practitioner / academic frameworks into a single
overlay that *qualifies* the Opportunity score rather than replacing it:

    1. Keen credit-ACCELERATOR (not impulse) -- second derivative of credit/GDP.
       'An impulse comes and goes; acceleration is always with you.'
       (Keen, profstevekeen.substack.com; INET 'How He Saw It Coming', 2025.)

    2. Dalio debt-cycle STAGE -- each country sits in one of six stages of
       the long-term debt cycle. The same Opportunity score means different
       things at different stages (a bull score in 'bubble' is a fade; a
       bull score in 'early' is to be ridden).
       (Dalio, *Principles for Navigating Big Debt Crises*; 48 case studies.)

    3. Marathon CAPEX-SQUEEZE -- a multi-year contraction in a sector's
       investment is the contrarian bull signal because survivors get
       pricing power. Inverts the Kalecki-Levy Investment leg over a long
       window. (Chancellor ed., *Capital Returns*, Marathon 2002-15.)

    4. Napier FINANCIAL-REPRESSION index -- real deposit-rate compression
       proxies how aggressively governments are deploying captive savings.
       Positive for C-archetype where 'national capitalism' is directing
       savings to defense/energy/reshoring.
       (Napier, 'We Are Headed Towards a System of National Capitalism',
       themarket.ch; Hidden Forces 2024-2025.)

    5. NBFI sub-sector CONCENTRATION FLAG -- aggregate sectoral balances
       hide sub-sector leverage (LDI/insurance/pension). UK gilt crisis 2022
       is the canonical case study where aggregate net-lending position
       said 'household surplus' but LDI repo/swap concentration was the
       binding fragility.
       (BoE WP 'Anatomy of the 2022 Gilt Market Crisis', 2023; IMF SIP 2023.)

Implementation: this module exposes one entrypoint, `overlay(panel)`, returning
a DataFrame keyed by ISO with the five overlay columns. The composite scorer
joins these onto the scored table and applies Dalio-stage-conditional
adjustments to the regime threshold.
"""

from __future__ import annotations

from typing import Literal

import pandas as pd


# --- 1. Keen credit accelerator -------------------------------------------

def keen_accelerator(credit_impulse_now: float, credit_impulse_prior: float
                     ) -> float:
    """
    Second derivative of credit-to-GDP: the *change* in the credit impulse.
    For the static panel we take the current vs prior reading as a proxy.
    """
    return credit_impulse_now - credit_impulse_prior


# --- 2. Dalio debt-cycle stage --------------------------------------------

DebtStage = Literal[
    "early",                  # leverage low, output gap closing, productive credit
    "expansion",              # broad-based credit growth, contained debt-to-GDP
    "bubble",                 # asset-price growth > profit growth; speculative finance
    "top",                    # debt-service ratios peak; central bank tightening bites
    "depression",             # private-sector forced deleverage; output gap opens
    "beautiful_deleveraging", # nominal growth restored via fiscal + currency easing
    "new_equilibrium",        # debt-to-GDP stabilised; new cycle beginning
]

# Mid-2026 stage assignments. Calibrated from sectoral-balance position +
# institutional regime + Kalecki-Levy profit fuel + valuation pressure.
DALIO_STAGE: dict[str, DebtStage] = {
    "US": "top",                       # late-cycle equities, fiscal dominance, profit pressure
    "GB": "depression",                # forced household NAFA, fiscal tightening, corporate NL collapse
    "DE": "beautiful_deleveraging",    # debt brake unwound; fiscal regime change; new fuel
    "JP": "beautiful_deleveraging",    # Takaichi fiscal pivot; BoJ normalisation in sync
    "KR": "expansion",                 # AI capex + Value-Up 2.0 leverage low
    "FR": "top",                       # rising debt + EMU constraint
    "IT": "new_equilibrium",           # post-deleveraging EMU periphery
    "ES": "new_equilibrium",
    "PT": "new_equilibrium",
    "GR": "new_equilibrium",
    "AU": "top",                       # household leverage at extremes
    "CA": "top",
    "NZ": "top",
    "CH": "expansion",
    "NL": "expansion",
    "SE": "top",                       # housing-credit excess
    "DK": "expansion",
    "FI": "expansion",
    "AT": "expansion",
    "BE": "expansion",
    "IE": "expansion",
    "LU": "expansion",
    "SG": "expansion",
    "HK": "depression",                # property bubble unwinding
    "TW": "bubble",                    # semis cycle blow-off potential
    "CN": "depression",                # private-sector deleveraging, M0 hoarding
    "VN": "expansion",
    "MY": "expansion",
    "TH": "expansion",
    "ID": "early",
    "PH": "early",
    "IN": "bubble",                    # 75% valuation premium, FPI rotation away
    "BR": "early",                     # post-deleveraging, Selic easing starting
    "MX": "early",
    "PL": "expansion",                 # EU funds-driven, mid-cycle
    "HU": "expansion",
    "CZ": "expansion",
    "RO": "expansion",
    "TR": "bubble",                    # debt-led construction regime (Yusufoglu SFC 2026)
    "EG": "depression",
    "PK": "depression",
    "AR": "beautiful_deleveraging",    # Milei stabilisation phase
    "ZA": "new_equilibrium",
    "LK": "beautiful_deleveraging",    # post-restructuring
    "SA": "expansion",                 # Vision 2030 capex deployment
    "AE": "expansion",
    "QA": "expansion",
    "KW": "new_equilibrium",
    "NO": "new_equilibrium",
    "KZ": "expansion",
    "CL": "new_equilibrium",
    "PE": "new_equilibrium",
    "CO": "new_equilibrium",
    "NG": "depression",
    "RU": "depression",
    "IR": "depression",
    "VE": "depression",
}


# Stage-conditional bull-regime threshold tightening. Stages where bull
# scores deserve scepticism get a higher threshold; stages where they
# deserve trust get a lower one.
STAGE_THRESHOLD_TILT: dict[DebtStage, float] = {
    "early": -0.10,                    # easier to label bull -- robust setup
    "expansion": 0.00,
    "bubble": +0.30,                   # need MUCH higher score to call bull
    "top": +0.20,
    "depression": -0.10,               # contrarian recovery setups
    "beautiful_deleveraging": -0.15,   # this is the sweet spot historically
    "new_equilibrium": 0.00,
}


# --- 3. Marathon capex-squeeze --------------------------------------------

# Sectors / countries where multi-year capex contraction is now producing
# pricing power for survivors. Encoded as a single per-country bullish
# overlay value in standard deviation units of historical capex/GDP shortfall.
MARATHON_CAPEX_SQUEEZE: dict[str, float] = {
    "SA": 1.5,   # mining (Maaden) + giga-project recalibration freeing cash
    "GB": 1.2,   # North Sea energy + utilities cap-X under-investment cycle
    "NO": 1.0,   # oil/gas under-investment; Equinor pricing power
    "JP": 0.8,   # semi-equipment incumbents post-2018 capex bust
    "US": 0.5,   # shale discipline post-2014, refining capacity tight
    "CL": 1.3,   # copper supply constraint
    "PE": 1.1,   # copper/zinc
    "AU": 0.6,   # iron ore + battery metals
    "ZA": 0.7,   # PGMs (platinum/palladium), gold
    "CA": 0.5,   # oil sands incumbents
    # Negative numbers = capex OVER-investment; pricing power compressing
    "CN": -1.5,  # property + EV over-build
    "TW": -0.8,  # semis over-capex risk H2 2026
    "KR": -0.5,  # memory/HBM cycle elevated capex
    "IN": -0.4,
    "DE": -0.3,  # over-build risk from EUR500bn fund (forward-looking)
}


# --- 4. Napier financial-repression index ---------------------------------

# Score 0-3: how aggressively are national savings being directed to
# national-capitalism priorities (defense, energy, reshoring, AI sovereignty)?
NAPIER_REPRESSION: dict[str, float] = {
    "DE": 2.5,   # debt brake + defense exemption = forced national-capitalism
    "JP": 2.5,   # Takaichi Y21.3tn = forced capital direction
    "KR": 2.2,   # KRW150tn AI sovereign fund
    "FR": 2.0,   # rising defense + industrial policy
    "SA": 2.5,   # PIF directed allocation
    "AE": 2.0,
    "GB": 1.5,   # Reeves consolidation BUT defense exemption + green industrial
    "US": 2.0,   # CHIPS / IRA / tariff-induced reshoring
    "IT": 1.5,
    "ES": 1.3,
    "PL": 2.0,   # EU-fund-channelled directed investment
    "IN": 2.0,   # production-linked incentive schemes
    "CN": 3.0,   # most repressed system in the panel
    "BR": 1.0,
    "MX": 1.2,
    "TR": 2.5,   # state-directed credit
    "TW": 1.0,
}


# --- 5. NBFI sub-sector concentration -- continuous score ----------------

# Continuous NBFI leverage / sub-sector concentration, 0-3. Sourced from
# FSB Global Monitoring Report on Non-Bank Financial Intermediation (annual),
# ESRB EU Shadow Banking Monitor (quarterly, EU only), IMF GFSR NBFI tables.
# Acknowledged staleness: FSB lags ~9 months, IMF GFSR semi-annual; treat
# as a structural fragility score not a real-time fragility gauge.
# Score interpretation:
#   3.0  systemic concentration (UK LDI-style: aggregate balance hides binding sub-sector)
#   2.0  notable concentration (Netherlands pension swap book; Korea PF-RE trust)
#   1.0  modest concentration (typical OECD: large but well-collateralised)
#   0.0  minimal concentration
NBFI_LEVERAGE_SCORE: dict[str, float] = {
    "GB": 3.0,   # LDI / pension repo -- canonical 2022 case
    "NL": 2.5,   # pension-fund swap concentration; relative-to-GDP large
    "IE": 2.5,   # UCITS / MMF plumbing; assets > 1500% modified GNI
    "LU": 2.5,   # fund-domicile distortion
    "JP": 2.0,   # life-insurer + GPIF FX-hedged duration
    "KR": 2.0,   # real-estate-PF + securities-finance trust funds
    "CH": 2.0,   # private-bank levered loans + commodities trade finance
    "HK": 2.0,   # USD-pegged property finance leverage
    "SG": 1.5,   # entrepot finance, more conservative regulation
    "AU": 1.5,   # super-fund swap-book size
    "CA": 1.5,
    "US": 1.5,   # OFI tail-risk but onshore SEC supervision
    "DE": 1.0,
    "FR": 1.2,
    "IT": 1.0, "ES": 1.0, "BE": 1.0,
    "DK": 1.0, "SE": 1.0, "FI": 1.0, "NO": 1.0, "AT": 1.0,
    "TW": 1.0, "MY": 1.0, "TH": 1.0, "ID": 0.7, "PH": 0.7, "VN": 0.7,
    "BR": 0.7, "MX": 0.7, "ZA": 0.7, "CL": 0.5, "PE": 0.5, "CO": 0.5,
    "PL": 0.7, "HU": 0.7, "CZ": 0.7, "RO": 0.5,
    "IN": 0.5, "CN": 1.0,  # CN OFI big but mostly bank-equivalent
    "TR": 0.8, "EG": 0.4, "AR": 0.3, "PK": 0.3, "LK": 0.3, "NG": 0.3,
    "SA": 0.5, "AE": 0.7, "QA": 0.5, "KW": 0.3,
    "NZ": 1.0, "GR": 0.5, "PT": 0.5,
    "KZ": 0.3, "RU": 0.5, "IR": 0.3, "VE": 0.3,
}

# Backwards-compat alias for the text-string version. Used by the dashboard
# tooltip; the continuous score above is the one entering composite.
NBFI_FRAGILE: dict[str, str] = {
    "GB": "LDI / pension repo (2022 gilt crisis case study)",
    "NL": "pension fund swap concentration",
    "IE": "fund-domicile distortion; MMF/UCITS plumbing risk",
    "JP": "life insurer / GPIF FX-hedged duration",
    "CH": "private-bank levered-loan exposure",
    "LU": "fund domicile",
    "KR": "real-estate-PF + securities-finance trust funds",
    "HK": "USD-pegged property finance leverage",
}


def overlay(panel: pd.DataFrame, components: pd.DataFrame | None = None
            ) -> pd.DataFrame:
    """
    Build the regime overlay for every country in `panel`.
    Returns a DataFrame indexed by ISO with five overlay columns.
    """
    out = pd.DataFrame(index=panel.index)

    # 1. Keen accelerator -- in the static panel we don't have a prior
    # reading, so we proxy with credit_impulse minus a baseline of 0.
    # When wired live this becomes credit_impulse_now - credit_impulse_prior.
    if "credit_impulse" in panel.columns:
        out["keen_accel"] = panel["credit_impulse"] - 0.5  # 0.5 = long-run average

    # 2. Dalio stage
    out["dalio_stage"] = pd.Series(DALIO_STAGE).reindex(out.index).fillna("expansion")
    out["stage_threshold_tilt"] = out["dalio_stage"].map(STAGE_THRESHOLD_TILT).fillna(0.0)

    # 3. Marathon capex squeeze
    out["marathon_squeeze"] = pd.Series(MARATHON_CAPEX_SQUEEZE).reindex(out.index).fillna(0.0)

    # 4. Napier repression
    out["napier_repression"] = pd.Series(NAPIER_REPRESSION).reindex(out.index).fillna(0.5)

    # 5. NBFI flag -- continuous leverage/concentration score
    out["nbfi_fragile"] = out.index.map(lambda i: NBFI_FRAGILE.get(i, ""))
    out["nbfi_leverage"] = pd.Series(NBFI_LEVERAGE_SCORE).reindex(out.index).fillna(0.5)
    # Boolean kept for backwards compatibility with the dashboard
    out["nbfi_flag"] = (out["nbfi_leverage"] >= 2.0).astype(int)

    return out


def stage_adjusted_regime(opportunity: float, dalio_stage: str,
                          bull: float = 0.15, bear: float = -0.15) -> str:
    """
    Re-label regime using the Dalio stage to shift thresholds. A bull score
    in 'bubble' or 'top' needs to clear a higher bar; the same score in
    'early' or 'beautiful_deleveraging' is more trustworthy.
    """
    tilt = STAGE_THRESHOLD_TILT.get(dalio_stage, 0.0)
    if opportunity >= bull + tilt:
        return "bull"
    if opportunity <= bear - abs(tilt) * 0.5:
        return "bear"
    return "neutral"
