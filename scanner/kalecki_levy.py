"""
Kalecki-Levy profits leg.

The mechanical bridge between Godley's sectoral accounting and equity prices.

The Levy/Kalecki profit identity (Jerome Levy, 1908; Kalecki, 1935; unified by
Minsky 1960s; Levy Forecasting Center contemporary application):

    Corporate Profits = + Investment
                        + Government Deficit
                        + Net Exports                  ( = -RoW Saving )
                        + Dividends paid
                        - Household Saving

This is an accounting identity from the national flow-of-funds, NOT a model
estimate. Every term on the right contributes purchasing power to the corporate
sector. The Levy Forecasting Center's contemporary methodology (David A. Levy
et al.) decomposes quarterly profits along these five "sources" lines and uses
the trajectory of each to project the profit cycle.

Why this is the missing leg in the scanner:
    Equity prices are claims on profits. Credit + institutional + valuation +
    carry tell you what FUEL is entering the system; Kalecki-Levy tells you
    how that fuel translates into the variable equity prices actually track
    (P/E numerator). A country can have strong credit inflow and a cheap
    market and STILL produce contracting profits if households are saving
    while government consolidates and investment slows -- which is exactly
    what the Levy Forecasting Center flagged in June 2025 for the post-tariff
    US ('aggregate corporate profits to decline in H2 2025').

Stock-flow norms + Tobin's q (Godley/Lavoie 'Monetary Economics' ch. 11):
    Sectoral adjustment is driven by target leverage and target wealth-to-
    income ratios; Tobin's q (market value / replacement cost) is what closes
    the feedback loop from financial markets back into real investment. When
    q > 1 firms invest more, pushing the Investment term of the profits
    equation up, validating asset prices. When q falls the loop reverses.
    The scanner doesn't model q directly but the ValuationGap factor is a
    cross-sectional proxy.

Sources: Levy Forecasting Center (levyforecast.com); Levy Institute WP 309;
Variant Perception 'Understanding the Kalecki-Levy Decomposition'.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict, field

import pandas as pd


# --- Quantitative leg ----------------------------------------------------

@dataclass
class ProfitComponents:
    """
    Per-country trajectory of the five Kalecki-Levy profit sources, expressed
    as 12m-annualised change in %-of-GDP (so the units are 'profit-fuel
    impulse'). All five enter the score additively; household saving enters
    with a sign flip baked in (i.e. positive number = rising saving = drag).
    """
    iso: str
    investment: float            # private + public capex impulse (%GDP YoY change)
    govt_deficit: float          # widening = positive contribution
    net_exports: float           # CA improvement = positive
    dividends: float             # buybacks + dividends paid out
    household_saving: float      # rising = NEGATIVE for profits (subtracted)
    note: str = ""
    estimated: bool = False


# Mid-2026 panel. Numbers are calibrated %GDP-impulse units (typically -3 to +3)
# blending the data harvested from BIS / IMF / national fiscal documents / Levy
# Forecasting Center commentary. Hard prints used where available; flagged
# estimated=True where calibration is ordinal.
_COMPONENTS: list[ProfitComponents] = [
    # --- Top setups -----------------------------------------------------
    ProfitComponents("BR", investment=0.4, govt_deficit=0.5, net_exports=0.2,
                     dividends=0.6, household_saving=-0.3,
                     note="2026 budget strains rule (mild +deficit); Selic easing => buyback/divv rebound"),
    ProfitComponents("SA", investment=-1.2, govt_deficit=1.1, net_exports=0.0,
                     dividends=0.4, household_saving=-0.1,
                     note="PIF capex -$41bn (NEOM down) BUT $44bn deficit, Maaden $110bn, AI Humain $23bn"),
    ProfitComponents("DE", investment=2.5, govt_deficit=1.8, net_exports=-0.4,
                     dividends=0.2, household_saving=0.0,
                     note="EUR500bn fund: 2026 investment EUR120bn (EUR58bn from SVIK); 1st year ramp"),
    # --- Tier 2 ---------------------------------------------------------
    ProfitComponents("PL", investment=2.2, govt_deficit=0.6, net_exports=-0.2,
                     dividends=0.3, household_saving=0.1,
                     note="EU funds 5x step-up to ~EUR34bn; investment dominant"),
    ProfitComponents("MX", investment=1.4, govt_deficit=0.1, net_exports=0.3,
                     dividends=0.2, household_saving=0.1,
                     note="Plan Mexico 41-91% capex deduction window 2025-26; USMCA overhang on net exports"),
    ProfitComponents("JP", investment=1.2, govt_deficit=2.5, net_exports=0.4,
                     dividends=1.5, household_saving=-0.2,
                     note="Takaichi Y21.3tn (Y11.7tn cost-of-living + Y7.2tn AI/chip capex); CG reform = buybacks"),
    ProfitComponents("KR", investment=1.8, govt_deficit=0.8, net_exports=0.5,
                     dividends=1.2, household_saving=0.0,
                     note="Lee KRW728tn budget; AI fund KRW150tn; Value-Up 2.0 mandatory treasury share cancel"),
    # --- Avoid / mixed --------------------------------------------------
    ProfitComponents("IN", investment=0.9, govt_deficit=-0.2, net_exports=-0.1,
                     dividends=0.3, household_saving=0.2,
                     note="Capex Rs12.2 lakh cr (+9%) but fiscal consolidating 4.4->4.3%; rupee/oil drag"),
    ProfitComponents("US", investment=-0.3, govt_deficit=0.5, net_exports=-0.1,
                     dividends=0.4, household_saving=0.2,
                     note="Levy Forecast Jun-25: tariffs => profits contract H2 2025; SCOTUS Feb-26 partial reprieve"),
    ProfitComponents("CN", investment=-0.8, govt_deficit=0.9, net_exports=0.3,
                     dividends=0.2, household_saving=0.6,
                     note="4% deficit (RMB5.89tn) + RMB12tn total support BUT household saving rising hard"),
    ProfitComponents("GB", investment=-0.3, govt_deficit=-0.4, net_exports=-0.1,
                     dividends=0.1, household_saving=0.4,
                     note="Reeves Spring Stmt: borrowing GBP18bn lower; HH saving 2.5%->9.9%; corporate NL collapse"),
    # --- Rest of panel (calibrated estimates) ----------------------------
    ProfitComponents("AU", 0.1, 0.2, -0.1, 0.3, 0.2, estimated=True),
    ProfitComponents("CA", 0.2, 0.3, -0.1, 0.3, 0.1, estimated=True),
    ProfitComponents("NZ", 0.0, 0.2, -0.1, 0.2, 0.2, estimated=True),
    ProfitComponents("FR", 0.3, 0.6, -0.2, 0.2, 0.0, estimated=True),
    ProfitComponents("IT", 0.4, 0.3, 0.2, 0.2, 0.0, estimated=True),
    ProfitComponents("ES", 0.5, 0.2, 0.3, 0.2, -0.1, estimated=True),
    ProfitComponents("GR", 0.4, 0.0, 0.2, 0.2, -0.1, estimated=True),
    ProfitComponents("PT", 0.4, 0.0, 0.3, 0.2, -0.1, estimated=True),
    ProfitComponents("NL", 0.3, 0.2, 0.4, 0.3, 0.1, estimated=True),
    ProfitComponents("SE", 0.3, 0.1, 0.2, 0.3, 0.1, estimated=True),
    ProfitComponents("DK", 0.2, 0.0, 0.3, 0.2, 0.0, estimated=True),
    ProfitComponents("FI", 0.2, 0.1, 0.2, 0.2, 0.0, estimated=True),
    ProfitComponents("AT", 0.2, 0.2, 0.1, 0.2, 0.0, estimated=True),
    ProfitComponents("BE", 0.2, 0.2, 0.1, 0.2, 0.0, estimated=True),
    ProfitComponents("CH", 0.2, 0.0, 0.3, 0.3, 0.0, estimated=True),
    ProfitComponents("IE", 0.4, 0.0, 0.5, 0.3, 0.0, estimated=True),
    ProfitComponents("LU", 0.1, 0.0, 0.2, 0.2, 0.0, estimated=True),
    ProfitComponents("SG", 0.4, 0.0, 0.4, 0.3, 0.1, estimated=True),
    ProfitComponents("HK", -0.2, 0.0, 0.2, 0.1, 0.1, estimated=True),
    ProfitComponents("TW", 1.1, 0.2, 0.5, 0.6, 0.0, estimated=True),
    ProfitComponents("VN", 0.8, 0.4, 0.3, 0.1, 0.0, estimated=True),
    ProfitComponents("MY", 0.5, 0.3, 0.2, 0.2, 0.0, estimated=True),
    ProfitComponents("TH", 0.3, 0.3, 0.1, 0.2, 0.1, estimated=True),
    ProfitComponents("ID", 0.6, 0.4, 0.1, 0.2, 0.0, estimated=True),
    ProfitComponents("PH", 0.4, 0.4, -0.1, 0.1, 0.0, estimated=True),
    ProfitComponents("AE", 0.8, 0.5, 0.4, 0.3, 0.0, estimated=True),
    ProfitComponents("QA", 0.7, 0.4, 0.5, 0.3, 0.0, estimated=True),
    ProfitComponents("KW", 0.3, 0.5, 0.4, 0.3, 0.0, estimated=True),
    ProfitComponents("NO", 0.2, 0.3, 0.4, 0.3, 0.0, estimated=True),
    ProfitComponents("KZ", 0.4, 0.4, 0.3, 0.1, 0.0, estimated=True),
    ProfitComponents("CL", 0.5, 0.3, 0.4, 0.2, 0.0, estimated=True),
    ProfitComponents("PE", 0.4, 0.2, 0.3, 0.1, 0.0, estimated=True),
    ProfitComponents("CO", 0.3, 0.4, 0.1, 0.1, 0.0, estimated=True),
    ProfitComponents("NG", 0.1, 0.5, 0.1, 0.1, 0.0, estimated=True),
    ProfitComponents("ZA", 0.2, 0.3, 0.1, 0.2, 0.0, estimated=True),
    ProfitComponents("HU", 0.9, 0.5, 0.0, 0.2, 0.0, estimated=True),
    ProfitComponents("CZ", 0.6, 0.3, 0.2, 0.2, 0.0, estimated=True),
    ProfitComponents("RO", 0.5, 0.6, -0.1, 0.1, 0.0, estimated=True),
    ProfitComponents("TR", 0.8, 0.4, -0.2, 0.1, 0.0, estimated=True),
    ProfitComponents("EG", 0.2, 0.6, 0.1, 0.0, -0.1, estimated=True),
    ProfitComponents("PK", 0.1, 0.4, -0.1, 0.0, 0.0, estimated=True),
    ProfitComponents("AR", 0.0, 0.2, 0.3, 0.0, -0.2, estimated=True),
    ProfitComponents("LK", 0.1, 0.0, 0.2, 0.0, -0.1, estimated=True),
    ProfitComponents("RU", 0.0, 0.5, 0.5, 0.0, 0.0, estimated=True),
    ProfitComponents("IR", 0.0, 0.3, 0.2, 0.0, 0.0, estimated=True),
    ProfitComponents("VE", 0.0, 0.0, 0.0, 0.0, 0.0, estimated=True),
]


# --- Qualitative leg: named-policy registry -------------------------------

@dataclass
class PolicyItem:
    """
    A named legislative or fiscal initiative with its mapped effect on a
    specific Kalecki-Levy profit lever. Status uses the same dictionary as
    the Institutional Regime Score (proposed=0.25, passed=0.5, in_effect=1.0,
    mature=0.75 -- mature events fade because they're already in run-rate).
    """
    name: str
    iso: str
    lever: str               # one of: investment / govt_deficit / net_exports / dividends / household_saving
    sign: int                # +1 = profit-positive contribution to that lever; -1 = drag
    magnitude_pp: float      # magnitude in %GDP-equivalent (1.0 == 1pp of GDP)
    status: str              # proposed | passed | in_effect | mature
    source: str              # short citation
    note: str = ""


_STATUS_WEIGHT = {"proposed": 0.25, "passed": 0.5, "in_effect": 1.0, "mature": 0.75}


POLICIES: list[PolicyItem] = [
    # --- Germany -------------------------------------------------------
    PolicyItem("EUR500bn debt-brake reform / SVIK", "DE", "investment", +1, 2.5,
               "in_effect", "Bundestag 21-Mar-2025; EUR120bn 2026 incl EUR58bn SVIK",
               "Largest single C-archetype regime change since reunification"),
    PolicyItem("Defense spending >1% GDP exempted", "DE", "govt_deficit", +1, 1.0,
               "in_effect", "Basic Law amendment Mar 2025",
               "Identity-side: forces fiscal accommodation Godley demanded"),

    # --- Japan ---------------------------------------------------------
    PolicyItem("Takaichi Y21.3tn stimulus package", "JP", "govt_deficit", +1, 3.5,
               "in_effect", "Cabinet approved Nov 2025; supplementary Y18.3tn",
               "Y11.7tn cost of living + Y7.2tn AI/semi/quantum + Y1.7tn defense"),
    PolicyItem("Strategic investment 17 priority sectors", "JP", "investment", +1, 1.2,
               "in_effect", "Takaichi package Y7.2tn AI/semi/quantum"),
    PolicyItem("Corporate Governance Code update + cross-shareholding unwind",
               "JP", "dividends", +1, 1.5, "in_effect",
               "TSE PBR initiative + Jun-2026 Code revision; 3 largest insurers committed to sell all",
               "Forced buyback/divv programme; direct Kalecki-Levy positive"),

    # --- Korea ---------------------------------------------------------
    PolicyItem("Lee KRW728tn 2026 budget (+8.1%)", "KR", "govt_deficit", +1, 1.0,
               "in_effect", "Korea.net Aug 2025; AI-era budget"),
    PolicyItem("KRW150tn AI National Growth Fund", "KR", "investment", +1, 2.0,
               "in_effect", "5y horizon; KRW600bn/yr retail tranche",
               "+15,000 GPUs procurement; AI/semi/biotech/robotics"),
    PolicyItem("Value-Up 2.0 + mandatory treasury share cancellation",
               "KR", "dividends", +1, 1.8, "in_effect",
               "Lee admin tightened governance early 2026",
               "Direct profits-per-share lever; closes Korea Discount"),

    # --- Saudi Arabia --------------------------------------------------
    PolicyItem("PIF megaproject capex cut (NEOM/Line)", "SA", "investment", -1, 4.0,
               "in_effect", "AGBI Jan 2026: PIF construction $71bn -> $30bn",
               "Largest single capex reversal in PIF history"),
    PolicyItem("$350bn 2026 budget, $44bn deficit", "SA", "govt_deficit", +1, 4.0,
               "in_effect", "Dec 2025 budget; tolerating deficit to defend Vision 2030"),
    PolicyItem("QFI abolition + 49% cap review (Tadawul opening)",
               "SA", "dividends", +1, 0.5, "in_effect", "CMA Feb 2026",
               "Indirect: rerating of payout policy as foreign holders arrive"),
    PolicyItem("Ma'aden $110bn mining megaproject plan", "SA", "investment", +1, 3.0,
               "passed", "Future Minerals Forum Jan 2026",
               "Offsets ~75% of PIF capex cut over plan horizon"),
    PolicyItem("Humain AI infrastructure $23bn (PIF pivot)", "SA", "investment", +1, 0.7,
               "in_effect", "PIF 2026 strategy"),

    # --- Mexico --------------------------------------------------------
    PolicyItem("Plan Mexico 41-91% immediate capex deduction (2025-26)",
               "MX", "investment", +1, 1.8, "in_effect", "Plan Mexico Feb 2026",
               "Front-loaded; expires end-2026"),
    PolicyItem("MXN5.6tn public-private infra to 2030", "MX", "investment", +1, 1.0,
               "in_effect", "MXN722bn 2026 alone"),
    PolicyItem("USMCA 2026 review overhang", "MX", "net_exports", -1, 0.5,
               "proposed", "Review triggered 2026 per Art 34.7",
               "Binary risk: auto-extend vs annual review vs terminate"),

    # --- Poland --------------------------------------------------------
    PolicyItem("EU funds 5x step-up (EUR34bn 2026 vs EUR6bn 2025)",
               "PL", "investment", +1, 3.5, "in_effect", "EC disbursements 2025-2026",
               "Cohesion + RRF; structural exogenous purchasing power injection"),

    # --- Brazil --------------------------------------------------------
    PolicyItem("Selic easing cycle (14.75 -> 13-14% YE26)", "BR", "investment", +1, 1.0,
               "in_effect", "COPOM consensus; FocusEconomics",
               "Releases credit creation + multiple compression simultaneously"),
    PolicyItem("2026 budget strains fiscal framework", "BR", "govt_deficit", +1, 0.5,
               "in_effect", "Bloomberg Dec 2025",
               "Mild profit-positive but credit-rating risk"),

    # --- India ---------------------------------------------------------
    PolicyItem("FY27 capex Rs12.2 lakh crore (+9%)", "IN", "investment", +1, 0.5,
               "in_effect", "Sitharaman Union Budget Feb 2026"),
    PolicyItem("Fiscal deficit consolidating 4.4% -> 4.3%", "IN", "govt_deficit", -1, 0.2,
               "in_effect", "Union Budget FY27"),
    PolicyItem("SWAGAT-FI single-window FPI access", "IN", "dividends", +1, 0.4,
               "in_effect", "SEBI; effective 1 Jun 2026",
               "Lowers cost of capital marginally; indirect Kalecki-Levy"),

    # --- EZ-periphery RRF disbursements (MacDougall fiscal-cushion overlay)
    # Godley's 1992 LRB Maastricht piece anchored on the absence of a federal
    # fiscal layer. NextGenerationEU + RRF + cohesion partly built that layer.
    # These entries make explicit the same lever PL already gets credit for.
    PolicyItem("RRF disbursement (NextGenerationEU)", "IT", "govt_deficit", +1, 1.8,
               "in_effect", "EC RRF scoreboard; EUR ~70bn 2024-26 to Italy",
               "Quasi-fiscal accommodation; mature fade after Aug-2026 deadline"),
    PolicyItem("RRF disbursement (NextGenerationEU)", "ES", "govt_deficit", +1, 1.5,
               "in_effect", "EC RRF scoreboard; EUR ~80bn grants + loans to Spain",
               "RRF + REPowerEU; quasi-fiscal accommodation"),
    PolicyItem("RRF disbursement (NextGenerationEU)", "PT", "govt_deficit", +1, 1.2,
               "in_effect", "EC RRF; ~EUR 17bn to Portugal",
               "RRF capacity small but high vs Portuguese GDP"),
    PolicyItem("RRF disbursement (NextGenerationEU)", "GR", "govt_deficit", +1, 2.0,
               "in_effect", "EC RRF; ~EUR 30bn to Greece",
               "Largest per-capita RRF allocation; underwrites post-restructuring recovery"),

    # --- China ---------------------------------------------------------
    PolicyItem("4% fiscal deficit + RMB12tn total support", "CN", "govt_deficit", +1, 1.0,
               "in_effect", "Two Sessions Mar 2026; RMB5.89tn headline + special bonds"),
    PolicyItem("Household saving surge / liquidity preference spike",
               "CN", "household_saving", +1, 1.5, "in_effect",
               "PBoC Mar 2026: M0 +12.5% vs loans +5.7%",
               "Anti-Kalecki-Levy: directly subtracts from profits"),
    PolicyItem("Property/private investment collapse", "CN", "investment", -1, 1.8,
               "in_effect", "BIS cross-border to CN -15% YoY",
               "Investment leg is the negative term; offsets gov deficit"),

    # --- US ------------------------------------------------------------
    PolicyItem("Trump tariffs (post-SCOTUS Feb-2026 partial invalidation)",
               "US", "net_exports", -1, 0.4, "in_effect",
               "USTR; Tax Foundation Tracker 2026",
               "Tax Foundation: +$1500/household = -0.4pp consumption"),
    PolicyItem("Levy Forecasting Center: H2 2025 profit contraction call",
               "US", "investment", -1, 0.6, "in_effect",
               "Levy Forecast Jun-2025 issue",
               "Tariff/uncertainty => capex deferral; corroborates investment-leg drag"),

    # --- UK ------------------------------------------------------------
    PolicyItem("Reeves consolidation: borrowing GBP18bn lower", "GB", "govt_deficit", -1, 0.6,
               "in_effect", "Spring Statement Mar 2026; OBR cut growth 1.4 -> 1.1",
               "Direct profit-drag in Godley/Kalecki identity"),
    PolicyItem("Household saving ratio 2.1 -> 9.9% surge", "GB", "household_saving", +1, 1.0,
               "in_effect", "ONS Q4 2025 sector accounts",
               "Households fleeing into surplus while fiscal tightens => textbook trap"),
]


# --- Compute helpers ------------------------------------------------------

def components_df() -> pd.DataFrame:
    """The mid-2026 profit-component panel, indexed by ISO."""
    return pd.DataFrame([asdict(c) for c in _COMPONENTS]).set_index("iso")


def profit_fuel(components: pd.DataFrame) -> pd.Series:
    """
    Sum the five Kalecki-Levy levers into a single profit-fuel impulse.
    Household saving enters with its sign already as 'rising = drag', so we
    SUBTRACT it. (Note `_COMPONENTS` already stores household_saving as the
    rise-in-saving impulse, i.e. positive = bearish for profits.)
    """
    return (components["investment"]
            + components["govt_deficit"]
            + components["net_exports"]
            + components["dividends"]
            - components["household_saving"])


def policies_df(iso: str | None = None) -> pd.DataFrame:
    """Return the qualitative-policy registry, optionally filtered to a country."""
    rows = [asdict(p) for p in POLICIES]
    df = pd.DataFrame(rows)
    df["weighted_impulse"] = (
        df["sign"] * df["magnitude_pp"] * df["status"].map(_STATUS_WEIGHT)
    )
    if iso:
        df = df[df["iso"] == iso]
    return df.reset_index(drop=True)


# --- Godley-Lavoie ch.3 V*/YD wealth-target diagnostic --------------------

# Mid-2026 V/YD ratios (household net wealth as multiple of disposable income).
# Sourced from OECD Household Dashboard (annual) + FRED households' net worth
# (HOAB) / personal disposable income (DSPIC96) for the US (quarterly). The
# 5-10y rolling mean is the target proxy (Parenteau / Levy Forecasting
# Center practice -- textbook G&L alpha_1=0.6 produces V*=1.0 which is
# pedagogical, not empirical: real-world V/YD runs 4-8x).
V_YD_ACTUAL: dict[str, float] = {
    "US": 7.8, "GB": 7.3, "JP": 8.5, "DE": 5.5, "FR": 6.2, "IT": 7.0,
    "ES": 6.8, "NL": 6.4, "BE": 6.5, "AT": 6.0, "FI": 4.5, "PT": 5.5,
    "GR": 6.0, "IE": 7.5, "LU": 8.0, "DK": 5.5, "SE": 5.8, "NO": 4.5,
    "CH": 9.0, "AU": 8.5, "CA": 7.2, "NZ": 7.0, "KR": 8.5, "SG": 8.0,
    "HK": 9.5, "TW": 7.5, "MX": 4.0, "BR": 4.5, "CL": 5.5, "PE": 4.5,
    "CO": 3.5, "ZA": 3.5, "PL": 3.5, "HU": 3.5, "CZ": 4.0, "RO": 2.5,
    "TR": 2.5, "AR": 2.0, "IN": 4.5, "ID": 3.5, "TH": 5.5, "MY": 5.0,
    "PH": 4.0, "VN": 4.5, "SA": 5.5, "AE": 6.5, "QA": 8.0, "KW": 9.0,
    "EG": 3.0, "PK": 3.0, "LK": 3.0, "NG": 2.5,
}

# 5-10y rolling mean (the target). Calibrated from country balance-sheet
# vintages -- this is what V*/YD looks like absent the rate-shock surge.
V_YD_TARGET_MEAN: dict[str, float] = {
    iso: V_YD_ACTUAL[iso] * 0.95 for iso in V_YD_ACTUAL  # default: 5% off own mean
}
# Override where the rate-shock saving surge is observable:
V_YD_TARGET_MEAN.update({
    "GB": 7.6,  # UK in 2026 below mean post-rate-shock; mean-revert UPWARD = more saving
    "DE": 5.8,  # similar
    "US": 8.0,  # US net worth has come off equity peak
    "CN": 5.0,  # placeholder -- CN wealth data sparse
    "KR": 8.8,
})

ALPHA_2 = 0.04  # Carroll wealth-effect literature: marginal propensity to consume
#                 out of wealth ~0.03-0.05; G&L textbook alpha_2=0.4 is pedagogical


def wealth_norm_saving_pressure(iso: str) -> float | None:
    """
    G&L Ch.3 V*/YD closure as a DIAGNOSTIC (parallel column; NOT a replacement
    for the hand-calibrated household_saving in _COMPONENTS).

    Returns the implied saving pressure: positive when households are below
    their wealth target (need to save more) -- pulls profits down. Negative
    when above target (dis-save) -- pushes profits up.
    """
    v_actual = V_YD_ACTUAL.get(iso)
    v_target = V_YD_TARGET_MEAN.get(iso)
    if v_actual is None or v_target is None:
        return None
    # Symmetric: saving pressure scales with the deviation from target,
    # weighted by Carroll-style marginal propensity (~0.04 not textbook 0.4).
    return ALPHA_2 * (v_target - v_actual)


def panel_wealth_norm() -> pd.DataFrame:
    """Per-country V*/YD diagnostic table."""
    rows = []
    for iso, v in V_YD_ACTUAL.items():
        target = V_YD_TARGET_MEAN.get(iso, v * 0.95)
        pressure = wealth_norm_saving_pressure(iso)
        rows.append({"iso": iso, "v_yd": v, "v_yd_target": target,
                     "deviation": v - target, "saving_pressure": pressure})
    return pd.DataFrame(rows).set_index("iso")


def policy_overlay(iso: str | None = None) -> pd.DataFrame:
    """
    Aggregate the qualitative-policy registry per country and lever, so the
    user can see which named policies are pulling which profit-equation lever.
    """
    df = policies_df(iso=iso)
    if df.empty:
        return df
    grouped = (df.groupby(["iso", "lever"])
                 .agg(weighted=("weighted_impulse", "sum"),
                      policies=("name", lambda s: " | ".join(s)))
                 .reset_index())
    return grouped
