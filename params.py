"""Central parameter tables for the screener.

All hand-curated priors live here. Each constant has a one-line
rationale and should be calibrated against the historical event-study
backtest (see backtest.py) once enough events have been logged.
"""

from __future__ import annotations

# ----------------------------------------------------------------------
# Recovery rate per NAV-quality class — fraction of stated NAV the
# market should expect to recover if the catalyst fires. Encodes the
# market's NAV-write-down forecast directly into upside, so a 50%
# discount on a private-equity book doesn't pretend to a 100% closure
# return.

RECOVERY_RATE: dict[str, float] = {
    "LISTED_CLEAN":          0.97,
    "DEBT_AMORTISING":       0.95,
    "REAL_ASSET_OBSERVABLE": 0.90,
    "INFRA_DCF":             0.85,
    "RENEWABLES_DCF":        0.80,
    "PROPERTY_DCF":          0.80,
    "PRIVATE_EQUITY":        0.70,
    "DISTRESSED":            0.40,
}
DEFAULT_RECOVERY = 0.85


# ----------------------------------------------------------------------
# Expected catalyst duration in months — used to convert total-return
# upside to annualised IRR. Reflects how long the catalyst typically
# takes to crystallise from where we are now.

CATALYST_DURATION_MONTHS: dict[str, int] = {
    "WIND_DOWN_COMMITTED":    30,
    "WIND_DOWN_LIKELY":       36,
    "RETURN_OF_CAPITAL_LIVE": 18,
    "STRATEGIC_REVIEW":       15,
    "ACTIVIST_TARGET":         9,
    "STRUCTURAL_DISCOUNT":    36,
    "DISTRESSED":             24,
}
DEFAULT_DURATION_MONTHS = 30


# ----------------------------------------------------------------------
# Base probability the catalyst fires meaningfully within its expected
# duration. Multiplied by signal-derived adjustment (see
# qualitative_signals.py) at run time.

CATALYST_PROB_BASE: dict[str, float] = {
    "WIND_DOWN_COMMITTED":    0.80,
    "WIND_DOWN_LIKELY":       0.60,
    "RETURN_OF_CAPITAL_LIVE": 0.70,
    "STRATEGIC_REVIEW":       0.50,
    "ACTIVIST_TARGET":        0.45,
    "STRUCTURAL_DISCOUNT":    0.20,
    "DISTRESSED":             0.20,
}
DEFAULT_PROB_BASE = 0.25


# ----------------------------------------------------------------------
# Setup-score weights — technical features only. Catalyst weighting is
# applied once at the end (expected_return × annualised), not inside
# the setup score, to avoid double-counting.

PHASE_WEIGHT: dict[str, float] = {
    "BASE_ABSORBING":      1.00,
    "BASE_BREAKOUT":       0.85,
    "CAPITULATION":        0.80,  # selloff + vol spike + washed MFI + insider buy
    "BASE_QUIET":          0.55,
    "BASE_DECLINING":      0.30,
    "RECENT_SELLOFF":      0.30,  # was DISTRIBUTION_DRIVEN — no longer hard-excluded
    "DOWNTREND":           0.10,
    "NO_BASE":             0.10,
    "POST_RERATING":       0.05,  # tapered, not hard zero
}


# ----------------------------------------------------------------------
# Investability gates. Hard filters applied before scoring — anything
# failing these is dropped to a separate "uninvestable" bucket
# regardless of upside.

INVESTABILITY_GATES = {
    "min_market_cap_gbp_m":   50.0,   # £50m floor
    "min_daily_value_gbp_m":   0.25,  # £250k daily traded
    "max_net_gearing_pct":   150.0,   # 150% net gearing ceiling
    "max_ongoing_charge":      3.5,   # ongoing-charge ceiling
}


# ----------------------------------------------------------------------
# Discount sanity band — clamp obviously-broken values from upstream
# feeds (e.g. JEMA −304%).

DISCOUNT_MIN = -0.50
DISCOUNT_MAX =  0.85


# ----------------------------------------------------------------------
# Signal layer parameters.

SIGNAL_HALF_LIFE_DAYS = 30  # exponential decay on news hits
SIGNAL_LOOKBACK_DAYS  = 120

# Per-ticker exclusion lists for known noise sources surfaced by the
# forensic audit. Headlines containing any of these terms (case-
# insensitive) are dropped from that ticker's signal count.
SIGNAL_EXCLUSIONS: dict[str, list[str]] = {
    "PSH.L":  ["PSUS", "Pershing Square Inc", "Pershing Square USA",
               "Ackman fund debut", "NYSE: PS"],
    "OCI.L":  ["Conduit Holdings"],
    "III.L":  ["3i Infrastructure"],   # different trust
    "NAS.L":  ["NASA", "Nasdaq"],
    "RIT.L":  ["RIT Bank", "Recreational"],
}

# Direction verbs used to classify director dealings — negative
# direction means we exclude the headline.
NEGATIVE_DIRECTOR_VERBS = (
    "termination", "terminated", "resign", "resigned", "steps down",
    "stepped down", "departure", "departs", "sells", "sold", "disposal",
    "disposed", "leaves",
)
POSITIVE_DIRECTOR_VERBS = (
    "buys", "bought", "purchase", "purchased", "acquires", "acquired",
    "increases stake", "raises stake", "ups stake", "boosts holding",
)
