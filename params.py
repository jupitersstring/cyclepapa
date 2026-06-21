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
    "OPEN_END_CONVERSION_PROPOSED": 12,  # Saba-style quick exit at NAV
    "WIND_DOWN_COMMITTED":          30,
    "WIND_DOWN_LIKELY":             36,
    "RETURN_OF_CAPITAL_LIVE":       18,
    "STRATEGIC_REVIEW":             15,
    "ACTIVIST_TARGET":               9,
    "DCM_ACTIVE":                   24,  # discount-control mechanism live
    "STRUCTURAL_DISCOUNT":          36,
    "DISTRESSED":                   24,
}
DEFAULT_DURATION_MONTHS = 30


# ----------------------------------------------------------------------
# Base probability the catalyst fires meaningfully within its expected
# duration. Multiplied by signal-derived adjustment (see
# qualitative_signals.py) at run time.

CATALYST_PROB_BASE: dict[str, float] = {
    # New: open-end conversion (Saba's preferred exit) — formal proposal
    # to convert to OEIC/UT removes the discount instantly. Very high P.
    "OPEN_END_CONVERSION_PROPOSED": 0.85,
    "WIND_DOWN_COMMITTED":          0.80,
    "WIND_DOWN_LIKELY":             0.60,
    "RETURN_OF_CAPITAL_LIVE":       0.70,
    "STRATEGIC_REVIEW":             0.50,
    "ACTIVIST_TARGET":              0.45,
    # New: DCM_ACTIVE = formal discount control mechanism (zero-discount
    # policy, conditional annual tender, performance-conditional tender).
    # Structurally caps discount widening; mid-tier probability of
    # meaningful narrowing.
    "DCM_ACTIVE":                   0.35,
    "STRUCTURAL_DISCOUNT":          0.20,
    "DISTRESSED":                   0.20,
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

# Catalyst-class-specific relaxations. Wind-down stubs are *meant*
# to be illiquid — applying the standard daily-value floor blanks
# them out by construction (the USF.L miss). For committed wind-
# downs we drop the daily value floor and mcap floor materially;
# the trade is buy-and-wait, not enter-and-exit.
INVESTABILITY_GATES_BY_CATALYST: dict[str, dict] = {
    # Wind-down stubs DRY UP — that's part of the catalyst. Live
    # observation: AEET £0.01m, RMII £0.04m, SBO £0.04m. We've
    # already relaxed the floor for these — relax further so we
    # don't gate out the very names the catalyst is designed to
    # crystallise. Anything below the MICRO threshold below ends
    # up in a separate MICRO sleeve.
    "WIND_DOWN_COMMITTED": {
        "min_market_cap_gbp_m":   20.0,
        "min_daily_value_gbp_m":   0.03,
        "max_net_gearing_pct":   200.0,
        "max_ongoing_charge":      6.0,
    },
    "WIND_DOWN_LIKELY": {
        "min_market_cap_gbp_m":   25.0,
        "min_daily_value_gbp_m":   0.03,
        "max_net_gearing_pct":   200.0,
        "max_ongoing_charge":      5.5,
    },
    "RETURN_OF_CAPITAL_LIVE": {
        "min_market_cap_gbp_m":   30.0,
        "min_daily_value_gbp_m":   0.05,
        "max_net_gearing_pct":   175.0,
        "max_ongoing_charge":      5.0,
    },
}

# MICRO sleeve gates — even more permissive, for committed event
# catalysts only. Names that fail the standard wind-down gates but
# pass these end up flagged as MICRO instead of dropped silently.
# Position size guidance: ≤1% of portfolio per name; assemble over
# multiple sessions; expect bid-offer slippage.
MICRO_GATES = {
    "min_market_cap_gbp_m":    8.0,
    "min_daily_value_gbp_m":   0.005,
    "max_net_gearing_pct":   250.0,
    "max_ongoing_charge":      8.0,
}


# ----------------------------------------------------------------------
# NAV trajectory factor. Two-sided multiplier on recovery_rate:
# negative NAVTR1Y penalises (asset sales below book), positive
# NAVTR1Y CREDITS (compounding NAV growth is itself part of return —
# AVI's published estimate is ~75% of holding-co returns come from
# NAV growth, not discount narrowing).

NAV_DECLINE_PENALTY = {
    # NAVTR1Y bucket -> multiplier on recovery (or upper-bound on
    # closure prize when NAV is growing — pinned at 1.15 so we don't
    # double-count NAV growth that should appear in price too)
    -1.00: 0.50,
    -0.20: 0.70,
    -0.10: 0.85,
    -0.05: 0.95,
     0.00: 1.00,
     0.05: 1.05,
     0.10: 1.10,
     0.20: 1.15,
    +1.00: 1.15,    # cap at +15% bonus regardless of NAV growth magnitude
}


# ----------------------------------------------------------------------
# Time-since-announcement adjustment for committed wind-downs.
# A wind-down announced 18 months ago is closer to crystallisation
# than one announced last month — probability should rise and
# remaining duration should shrink. Both effects raise IRR on stale
# wind-downs (the SEIT vs USF case).

WIND_DOWN_AGE_CURVE = {
    # months_since_announcement -> (prob_multiplier, duration_multiplier)
    # Interpolated linearly between rows.
    0:   (1.00, 1.00),
    6:   (1.05, 0.85),
    12:  (1.10, 0.65),
    18:  (1.10, 0.45),
    24:  (1.10, 0.30),
    36:  (0.95, 0.20),   # if it hasn't fired by 36m, slippage risk rises
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
