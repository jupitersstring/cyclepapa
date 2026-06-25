"""
short_squeeze.py — A systematic, research-grounded framework for scoring
SHORT-SQUEEZE CANDIDATES and, just as importantly, for *disqualifying* names
where the short side is comfortable (a bearish tell, not a squeeze setup).

WHY THIS EXISTS
---------------
"High short interest" is a famously poor stand-alone signal: on average,
heavily-shorted stocks UNDER-perform — short sellers are informed more often
than not (Boehmer, Jones & Zhang 2008; Asquith, Pathak & Ritter 2005;
Cohen, Diether & Malloy 2007; Drechsler & Drechsler 2014). A squeeze is the
tail, not the base case. To find the tail you have to look at the *plumbing of
the stock-loan market*, not just the headline short-interest number.

The single most important empirical result this framework is built on:

    Paul Schultz, "Short Squeezes and Their Consequences,"
    Journal of Financial and Quantitative Analysis (JFQA) 59(1): 68-96,
    print Feb 2024 (online Jan 2023; SSRN WP Feb 2022). Data: IHS Markit,
    2006-2019.

Schultz's headline finding: UTILIZATION — the fraction of *lendable* shares
that are actually out on loan (shares on loan / shares available to lend) — is
the single strongest predictor of squeezes, ahead of short-interest %,
days-to-cover, and the borrow fee taken alone. Frequencies he reports:

    utilization <= 25%  ->  an "all-lender" squeeze ~once every 40 YEARS
    utilization >= 90%  ->  an "all-lender" squeeze ~once every 11 DAYS
    borrow fee  > 10%   ->  a "current-lender" squeeze ~once every 25 days

Borrow-fee (loan-fee) distribution in Schultz's sample:
    mean = 2.673%/yr, 25th pct = median = ~0.375%/yr (the ~37.5bp GC floor),
    95th pct = 11.0%/yr.
The mean sits far above the median: the typical stock is "general collateral"
(GC) at the floor, and a thin right tail of "special" names drags the mean up.

THE TWO DETECTORS
-----------------
1. BEARISH CONVERGENCE ("genuinely short" / squeeze DISqualifier):
       short_interest_% > 10  AND  utilization < 50%  AND  borrow_fee < 3%
   Lots of shorts, yet borrow is ample (low utilization) and cheap (low fee).
   The short side is comfortable and uncrowded — sophisticated capital that is
   genuinely short on fundamentals and CANNOT be easily forced to cover. This
   is a bearish tell, NOT a squeeze candidate. (Nuance: the academically
   *strongest* predictable underperformance actually lives in EXPENSIVE-to-
   borrow names — Drechsler & Drechsler 2014 — so read this convergence
   primarily as "low squeeze risk," and only secondarily as "bearish.")

2. SQUEEZE FUEL (the fragile short side):
       high & rising utilization  AND  high/spiking borrow fee  AND  elevated
       SI  AND  (ideally) the shorts are under water.
   Borrow is scarce and expensive, the trade is crowded, and — per S3 Partners
   (Ihor Dusaniwsky) — a short that is still PROFITABLE cannot be squeezed; you
   need net-of-financing mark-to-market LOSSES to force covering.

DATA REALITY (read this before you trust a score)
-------------------------------------------------
The two most predictive inputs are UTILIZATION and BORROW FEE. yfinance gives you
short_interest % of float, shares short, and days-to-cover only. The rest:
  * BORROW FEE + shortable availability — FREE, NO ACCOUNT: `from_ibkr_file()`
    parses IBKR's public ftp://shortstock@ftp3.interactivebrokers.com/<cc>.txt
    (-> MEDIUM confidence on its own);
  * UTILIZATION — IBKR's Orbisa dashboard (real-time, FREE with an account, but
    GUI-only -> pass it via utilization_pct=... for HIGH confidence); or Ortex
    (limited free tier; paid ~$39-50/mo); Nasdaq / S&P (IHS) Markit / FIS Astec paid.
If you have none of these, run DEGRADED: the engine still scores and classifies,
but reports `confidence = MEDIUM` (borrow fee but no utilization) or `LOW`
(neither — SI%/days-to-cover only), and the detectors switch to a borrow-fee
proxy (cheap fee strongly implies ample supply). It returns INSUFFICIENT_DATA
only when there is nothing scorable at all. Wire a lending feed and it
auto-upgrades to strict detectors and HIGH confidence. Note FINRA short interest
is bi-monthly, published 7 business days after settlement — stale by
construction; utilization and fee are daily.

This module has NO third-party dependencies in its core (so the scoring engine
and tests run on a bare Python 3.x). yfinance and streamlit are imported lazily
only inside their adapters.

References are collected in CITATIONS at the bottom of this file and discussed
in SHORT_SQUEEZE_FRAMEWORK.md.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Dict, Iterable, List, Optional, Tuple

__all__ = [
    "SqueezeMetrics",
    "ScoreRule",
    "SCORE_RULES",
    "DetectorResult",
    "detect_bearish_convergence",
    "detect_squeeze_fuel",
    "detect_coiled_spring",
    "SqueezeClass",
    "Confidence",
    "SqueezeAssessment",
    "SqueezeConfig",
    "DEFAULT_CONFIG",
    "assess",
    "rank_candidates",
    "from_yfinance",
    "screen_yfinance",
    "utilization_from_loan",
    "parse_ibkr_shortable_text",
    "fetch_ibkr_shortable_text",
    "from_ibkr_file",
    "IbkrShortRow",
    "parse_finra_short_interest",
    "FinraShortRow",
    "screen_universe",
    "screen_yfinance",
    "Snapshot",
    "metrics_from_timeseries",
    "screen_panel",
    "to_snapshot_csv",
    "parse_snapshot_csv",
    "build_panel",
    "load_panel",
    "report",
    "to_csv",
    "BORROW_FEE_MEAN_PCT",
    "BORROW_FEE_MEDIAN_PCT",
    "BORROW_FEE_P95_PCT",
]

# ---------------------------------------------------------------------------
# Empirical reference constants (Schultz 2024, IHS Markit 2006-2019).
# Percentages are expressed in PERCENT units (2.673 == 2.673%/yr), to match
# how borrow fees / utilization / short interest are quoted in practice.
# ---------------------------------------------------------------------------
BORROW_FEE_MEDIAN_PCT: float = 0.375   # ~37.5 bp/yr — the general-collateral floor
BORROW_FEE_MEAN_PCT: float = 2.673     # mean annual loan fee
BORROW_FEE_P95_PCT: float = 11.0       # 95th percentile annual loan fee
GENERAL_COLLATERAL_FEE_PCT: float = 0.50  # practical "this is just GC" ceiling


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------
@dataclass
class SqueezeMetrics:
    """A point-in-time snapshot of the short-side state of one security.

    Only the three primary signals matter for the core score; everything else
    is optional context used by the detectors and for confidence weighting.
    All percentages are in PERCENT units (e.g. utilization 92.5 means 92.5%,
    borrow_fee_pct 18.0 means 18%/yr, short_interest_pct_float 27.0 means 27%).
    """

    ticker: str = ""

    # --- primary signals (the three SCORE_RULES d33/d34/d35) ---
    short_interest_pct_float: Optional[float] = None   # SI as % of FLOAT (d33)
    utilization_pct: Optional[float] = None            # shares on loan / lendable (d34)
    borrow_fee_pct: Optional[float] = None             # cost-to-borrow, %/yr (d35)

    # --- supporting context ---
    days_to_cover: Optional[float] = None              # shares short / avg daily vol
    short_interest_pct_shares_out: Optional[float] = None
    float_shares: Optional[float] = None
    shares_short: Optional[float] = None
    shares_short_prior: Optional[float] = None         # for SI trend
    avg_daily_volume: Optional[float] = None
    shortable_shares_available: Optional[float] = None  # IBKR shortable qty (0 => tight)

    # --- rate-of-change context (squeeze setups are about *acceleration*) ---
    utilization_trend_pct_pts: Optional[float] = None  # change in utilization (pct points)
    borrow_fee_trend_pct_pts: Optional[float] = None   # change in fee (pct points)
    fee_percentile: Optional[float] = None             # borrow fee vs its OWN history, 0-100 (regime/breakout)
    utilization_percentile: Optional[float] = None     # utilization vs its OWN history, 0-100

    # --- short-side P&L proxy (S3 insight) ---
    # Percent the current price sits ABOVE the estimated average short entry.
    # > 0  => the average short is under water (squeezable).
    # < 0  => shorts are still in profit (cannot be forced out -> not a squeeze).
    price_vs_short_cost_basis_pct: Optional[float] = None

    # --- price momentum / ignition (the catalyst proxy) ---
    # Percent the price sits above a reference (e.g. 50-day MA), or a trailing
    # return. Positive => upward pressure that can ignite covering.
    momentum_pct: Optional[float] = None

    # --- short-sale-constraint & gamma signals (literature-grounded, obtainable) ---
    institutional_ownership_pct: Optional[float] = None  # low => thin lendable supply (Asquith)
    on_reg_sho_threshold: Optional[bool] = None          # persistent fails-to-deliver (Reg SHO list)
    failures_to_deliver: Optional[float] = None          # FTD shares (SEC, context)
    options_volume_vs_adv: Optional[float] = None        # options vol / avg daily share vol (>=5 => MM hedging)
    volume_vs_avg: Optional[float] = None                # today's share volume / ADV (investor-attention proxy)
    price: Optional[float] = None                        # last price (penny-stock / liquidity guard)

    as_of: Optional[str] = None
    source: str = "manual"

    # ---- derived helpers ----
    @property
    def short_interest_trend_pct_pts(self) -> Optional[float]:
        """Change in shares short vs prior report, as a % of the prior level."""
        if self.shares_short is None or not self.shares_short_prior:
            return None
        return 100.0 * (self.shares_short - self.shares_short_prior) / self.shares_short_prior

    @property
    def dollar_volume(self) -> Optional[float]:
        """Average daily traded value (price x average volume) — a liquidity gauge."""
        if self.price is None or self.avg_daily_volume is None:
            return None
        return float(self.price) * float(self.avg_daily_volume)


# ---------------------------------------------------------------------------
# Scoring rules
# ---------------------------------------------------------------------------
def _band_score(value: Optional[float], bands: List[Tuple[float, float]]) -> Optional[float]:
    """Map a value to a 0-100 sub-score via ascending (upper_bound, score) bands.

    A value v gets the score of the first band whose upper bound is >= v.
    The final band should use math.inf as its upper bound. Returns None if the
    value is missing, so the engine can exclude the rule and lower coverage.
    """
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    for upper, score in bands:
        if value <= upper:
            return float(score)
    return float(bands[-1][1])


@dataclass(frozen=True)
class ScoreRule:
    """A single, weighted, citable scoring rule over one SqueezeMetrics field.

    `bands` are ascending (upper_bound_inclusive, score_0_to_100) pairs. The
    `weight` is the rule's share of the composite (the three primary weights
    sum to 1.0). `metric` is the SqueezeMetrics attribute name the rule reads.
    """

    id: str
    title: str
    metric: str
    weight: float
    bands: List[Tuple[float, float]]
    rationale: str
    citations: List[str] = field(default_factory=list)

    def value(self, m: SqueezeMetrics) -> Optional[float]:
        return getattr(m, self.metric, None)

    def score(self, m: SqueezeMetrics) -> Optional[float]:
        return _band_score(self.value(m), self.bands)


# Weights encode Schultz's ranking: utilization dominates, the fee is next, and
# raw short-interest % is the weakest of the three (it is the headline number
# everyone quotes and the one with the least incremental predictive value).
SCORE_RULES: Dict[str, ScoreRule] = {
    "d33_short_interest_pct": ScoreRule(
        id="d33_short_interest_pct",
        title="Short interest (% of float)",
        metric="short_interest_pct_float",
        weight=0.20,
        # <5 none | 5-10 low | 10-20 elevated | 20-30 high | 30-50 very high | >50 extreme
        bands=[(5.0, 0.0), (10.0, 20.0), (20.0, 40.0), (30.0, 60.0), (50.0, 80.0), (math.inf, 100.0)],
        rationale=(
            "Necessary but weak alone. Heavily-shorted stocks under-perform on "
            "average (shorts are informed), so SI% is mostly a bearish tilt, not "
            "a squeeze signal. It only becomes squeeze fuel when borrow is scarce "
            "and dear. Lowest weight of the three primary signals."
        ),
        citations=["Boehmer-Jones-Zhang 2008", "Asquith-Pathak-Ritter 2005", "Schultz 2024"],
    ),
    "d34_utilization_pct": ScoreRule(
        id="d34_utilization_pct",
        title="Utilization (% of lendable shares on loan)",
        metric="utilization_pct",
        weight=0.50,
        # Schultz: <=25% -> squeeze ~1/40yr ; >=90% -> ~1/11 days. Steep, convex.
        bands=[(25.0, 0.0), (50.0, 15.0), (70.0, 35.0), (85.0, 60.0), (95.0, 85.0), (math.inf, 100.0)],
        rationale=(
            "THE signal. Utilization = shares on loan / shares available to lend. "
            "It measures how exhausted the lendable supply is — i.e. how little "
            "room shorts have left. Schultz (2024) finds it the single strongest "
            "predictor of squeezes: squeeze frequency rises ~1/40yr at <=25% to "
            "~1/11 days at >=90%. Highest weight."
        ),
        citations=["Schultz 2024 JFQA 59(1):68-96"],
    ),
    "d35_borrow_rate_pct": ScoreRule(
        id="d35_borrow_rate_pct",
        title="Borrow rate / cost-to-borrow (%/yr)",
        metric="borrow_fee_pct",
        weight=0.30,
        # Distribution: median ~0.375%, mean 2.673%, p95 11.0%. >10% -> current-
        # lender squeeze ~1/25 days. Bands anchored to those percentiles.
        bands=[(0.5, 0.0), (1.0, 10.0), (3.0, 25.0), (10.0, 55.0), (25.0, 80.0), (math.inf, 100.0)],
        rationale=(
            "The PRICE of the short. ~Half of stocks sit at the ~0.375%/yr GC "
            "floor; the mean (2.673%) is dragged up by a thin tail of 'special' "
            "names; the 95th percentile is ~11%. A fee above ~10% is firmly in "
            "the special tail (Schultz: current-lender squeeze ~1/25 days). "
            "A SPIKING fee matters more than the level — see borrow_fee_trend."
        ),
        citations=["Schultz 2024", "D'Avolio 2002"],
    ),
}

# Sanity: the three primary weights are meant to sum to 1.0.
assert abs(sum(r.weight for r in SCORE_RULES.values()) - 1.0) < 1e-9


# ---------------------------------------------------------------------------
# Detectors (composite, threshold-based)
# ---------------------------------------------------------------------------
@dataclass
class DetectorResult:
    name: str
    triggered: bool
    reason: str
    mode: str = "strict"          # "strict" (utilization-based), "proxy" (fee-based), "unavailable"
    missing: List[str] = field(default_factory=list)  # required inputs that were None

    def __bool__(self) -> bool:  # so `if result:` works
        return self.triggered


# Threshold constants for the detectors (single source of truth, easy to tune).
BEARISH_SI_MIN = 10.0          # short interest % of float must exceed this
BEARISH_UTIL_MAX = 50.0        # utilization must be BELOW this (ample borrow)
BEARISH_FEE_MAX = 3.0          # borrow fee must be BELOW this (cheap borrow)

FUEL_UTIL_MIN = 85.0           # utilization at/above this = supply nearly gone
FUEL_SI_MIN = 10.0             # elevated short interest
FUEL_FEE_MIN = 10.0            # fee in the "special" tail (Schultz ~p95 region)

# Coiled-spring (good risk/reward) detector — needs DYNAMIC (time-series) data:
# crowded short + borrow tightening in real time + price not yet ignited.
COILED_SI_MIN = 15.0           # a meaningfully crowded short, OR
COILED_UTIL_MIN = 80.0         # high utilization
COILED_PCTILE = 80.0           # fee/util at its own historical highs (breakout)
COILED_MOM_MAX = 30.0          # price has NOT yet run (the asymmetric R/R edge)
COILED_MOM_MIN = -20.0         # ...but not CRASHING (a falling knife is not a coil)
COILED_MIN_PRICE = 1.0         # must be tradeable (a penny stock is a falling knife, not a coil)
COILED_FEE_MIN = 5.0           # borrow already meaningfully special (a cheap GC fee "rising" is noise)


def detect_bearish_convergence(m: SqueezeMetrics) -> DetectorResult:
    """Genuinely-short / squeeze-DISqualifier detector.

        strict (utilization available):  SI% > 10  AND  util < 50%  AND  fee < 3%
        proxy  (no utilization):         SI% > 10  AND  fee < 3%   (cheap borrow
                                         strongly implies ample supply / low util)
        proxy  (no fee):                 SI% > 10  AND  util < 50%

    High short interest with ample (low-utilization) and cheap (low-fee) borrow
    means the short side is comfortable and uncrowded: sophisticated capital that
    is genuinely short on fundamentals and not at risk of being forced out. Treat
    as a bearish tell and explicitly NOT a squeeze candidate. The proxy modes
    keep the detector working when a securities-lending feed is unavailable
    (see module docstring) — at lower confidence.
    """
    si, util, fee = m.short_interest_pct_float, m.utilization_pct, m.borrow_fee_pct
    if si is None or (util is None and fee is None):
        return DetectorResult(
            "bearish_convergence", False,
            "Cannot evaluate: need SI% and at least one of utilization / borrow fee.",
            mode="unavailable",
            missing=["short_interest_pct_float | utilization_pct | borrow_fee_pct"],
        )

    si_ok = si > BEARISH_SI_MIN
    if util is not None and fee is not None:
        mode = "strict"
        triggered = si_ok and (util < BEARISH_UTIL_MAX) and (fee < BEARISH_FEE_MAX)
        cond = f"util {util:.1f}%<{BEARISH_UTIL_MAX:g} & fee {fee:.2f}%<{BEARISH_FEE_MAX:g}"
    elif fee is not None:  # no utilization: cheap fee => ample supply
        mode = "proxy"
        triggered = si_ok and (fee < BEARISH_FEE_MAX)
        cond = f"fee {fee:.2f}%<{BEARISH_FEE_MAX:g} (util unknown; cheap borrow implies ample supply)"
    else:  # have utilization, no fee
        mode = "proxy"
        triggered = si_ok and (util < BEARISH_UTIL_MAX)
        cond = f"util {util:.1f}%<{BEARISH_UTIL_MAX:g} (fee unknown)"

    tag = "" if mode == "strict" else " [proxy]"
    if triggered:
        reason = (
            f"SI {si:.1f}%>{BEARISH_SI_MIN:g} and {cond}: borrow ample & cheap -> "
            f"comfortable, uncrowded short -> genuinely short (bearish), NOT a "
            f"squeeze setup.{tag}"
        )
    else:
        reason = f"Not genuinely-short ({mode}): SI {si:.1f}%, {cond}."
    return DetectorResult("bearish_convergence", triggered, reason, mode=mode)


def detect_squeeze_fuel(m: SqueezeMetrics) -> DetectorResult:
    """Fragile-short / squeeze-fuel detector.

        strict (utilization available):
            util >= 85%  AND  SI% >= 10%  AND  (fee >= 10%  OR fee rising)
            AND shorts NOT clearly in profit.
        proxy  (no utilization):
            (fee >= 10%  OR fee rising)  AND  SI% >= 10%  AND not in profit.
        proxy  (no fee):
            util >= 85%  AND  SI% >= 10%  AND not in profit.

    The borrow-fee condition is met by a high LEVEL or a positive TREND, because
    an accelerating fee is often the earliest tell that supply is running out.
    S3 gate: a still-profitable short cannot be squeezed (it needs MTM losses).
    """
    si, util, fee = m.short_interest_pct_float, m.utilization_pct, m.borrow_fee_pct
    if si is None or (util is None and fee is None):
        return DetectorResult(
            "squeeze_fuel", False,
            "Cannot evaluate: need SI% and at least one of utilization / borrow fee.",
            mode="unavailable",
            missing=["short_interest_pct_float | utilization_pct | borrow_fee_pct"],
        )

    fee_rising = (m.borrow_fee_trend_pct_pts or 0.0) > 0.0
    fee_hot = (fee is not None and fee >= FUEL_FEE_MIN) or fee_rising
    shorts_in_profit = (
        m.price_vs_short_cost_basis_pct is not None
        and m.price_vs_short_cost_basis_pct < 0.0
    )
    si_ok = si >= FUEL_SI_MIN
    util_tight = util is not None and util >= FUEL_UTIL_MIN

    if util is not None and fee is not None:
        mode = "strict"
        triggered = util_tight and si_ok and fee_hot and not shorts_in_profit
    elif util is not None:  # no fee
        mode = "proxy"
        triggered = util_tight and si_ok and not shorts_in_profit
    else:  # no utilization, have fee
        mode = "proxy"
        triggered = fee_hot and si_ok and not shorts_in_profit

    bits = [
        f"util {('%.1f%%' % util) if util is not None else 'n/a'}" + (" tight" if util_tight else ""),
        f"SI {si:.1f}% {'>=' if si_ok else '<'} {FUEL_SI_MIN:g}%",
        f"fee {('%.2f%%' % fee) if fee is not None else 'n/a'} {'hot' if fee_hot else 'cool'}"
        + (" (rising)" if fee_rising else ""),
    ]
    if shorts_in_profit:
        bits.append(
            f"shorts in profit ({m.price_vs_short_cost_basis_pct:.1f}% below entry) -> can't be forced"
        )
    tag = "" if mode == "strict" else " [proxy]"
    reason = ("SQUEEZE FUEL: " if triggered else "Not (yet) squeeze fuel: ") + "; ".join(bits) + tag
    return DetectorResult("squeeze_fuel", triggered, reason, mode=mode)


def detect_coiled_spring(m: SqueezeMetrics) -> DetectorResult:
    """Good RISK/REWARD footprint (needs DYNAMIC / time-series data): a crowded
    short whose borrow is TIGHTENING in real time (rising — or at its own historical
    high — fee / utilization / short interest) but whose price has NOT yet ignited.

    'Short squeezes reward early conviction and punish late speculation' — the
    asymmetric pre-ignition entry. Grounded in Cohen-Diether-Malloy (the *change*
    in shorting demand, not the level, predicts), D'Avolio (a spiking fee precedes
    forced covering), and the GME footprint (borrow maxed + gamma ramp building
    *before* the parabolic move). Once price has run it is no longer coiled — that
    is the overextension penalty's job. Requires a lending signal + a dynamic input.
    """
    si, util = m.short_interest_pct_float, m.utilization_pct
    if util is None and m.borrow_fee_pct is None:
        return DetectorResult("coiled_spring", False,
                              "No lending signal — cannot assess the footprint.", mode="unavailable")
    crowded = (si is not None and si >= COILED_SI_MIN) or (util is not None and util >= COILED_UTIL_MIN)
    fee = m.borrow_fee_pct
    under_pressure = (fee is not None and fee >= COILED_FEE_MIN) or (util is not None and util >= COILED_UTIL_MIN)
    tightening_bits: List[str] = []
    if (m.borrow_fee_trend_pct_pts or 0.0) > 0.0:
        tightening_bits.append("fee rising")
    if (m.utilization_trend_pct_pts or 0.0) > 0.0:
        tightening_bits.append("util rising")
    if (m.short_interest_trend_pct_pts or 0.0) > 0.0:
        tightening_bits.append("SI rising")
    if (m.fee_percentile or 0.0) >= COILED_PCTILE:
        tightening_bits.append(f"fee at {m.fee_percentile:.0f}th pctile")
    if (m.utilization_percentile or 0.0) >= COILED_PCTILE:
        tightening_bits.append(f"util at {m.utilization_percentile:.0f}th pctile")
    tightening = bool(tightening_bits)
    mom = m.momentum_pct
    not_ignited = (mom is None) or (COILED_MOM_MIN <= mom < COILED_MOM_MAX)
    tradeable = (m.price is None) or (m.price >= COILED_MIN_PRICE)
    triggered = crowded and under_pressure and tightening and not_ignited and tradeable

    if not tightening:
        reason = "Not coiling — no tightening in the dynamics (need a time series)."
    elif not crowded:
        reason = "Tightening but not crowded enough (low SI / utilization)."
    elif not under_pressure:
        reason = "Borrow still cheap (general collateral) — rising, but not under real pressure yet."
    elif not tradeable:
        reason = f"Tightening but untradeable (${m.price:.2f} penny) — a falling knife, not a coil."
    elif mom is not None and mom < COILED_MOM_MIN:
        reason = f"Tightening but price crashing ({mom:+.0f}%) — falling knife / winning short, not a coil."
    elif mom is not None and mom >= COILED_MOM_MAX:
        reason = f"Already moving (+{mom:.0f}%) — past the asymmetric entry (poor R/R)."
    else:
        reason = ("COILED SPRING (good R/R): crowded + tightening (" + ", ".join(tightening_bits)
                  + ") + tradeable + price not yet ignited — the pre-ignition entry.")
    return DetectorResult("coiled_spring", triggered, reason)


# ---------------------------------------------------------------------------
# Scoring engine
# ---------------------------------------------------------------------------
class SqueezeClass(str, Enum):
    GENUINELY_SHORT = "GENUINELY_SHORT"      # bearish convergence: avoid as a squeeze
    SQUEEZE_FUEL = "SQUEEZE_FUEL"            # fragile short side, primed
    ELEVATED = "ELEVATED"                    # high score, watch
    WATCH = "WATCH"                          # middling
    LOW = "LOW"                              # nothing here
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"  # nothing scorable at all (no SI%, no fee, no util)


class Confidence(str, Enum):
    """How much to trust the call, driven by which inputs were available.

    HIGH   = utilization present (the dominant predictor; strict detectors).
    MEDIUM = no utilization but borrow fee present (fee-proxy detectors).
    LOW    = neither utilization nor fee — SI%/days-to-cover only (headline regime).
    """
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


@dataclass
class SqueezeAssessment:
    ticker: str
    squeeze_score: Optional[float]               # 0-100 FINAL score (struct+dynamics+ignition)*amp
    composite_score: Optional[float]             # 0-100 structural (lending) score, interaction-aware
    classification: SqueezeClass
    confidence: Confidence                       # HIGH/MEDIUM/LOW by data availability
    rule_scores: Dict[str, Optional[float]]
    coverage: float                              # 0-1: weight of structural rules we could score
    bearish_convergence: DetectorResult
    squeeze_fuel: DetectorResult
    dynamics_score: Optional[float] = None       # 0-100 acceleration (rising util/fee/SI)
    ignition_score: Optional[float] = None       # 0-100 spark (momentum + gamma + shorts under water)
    constraint_score: Optional[float] = None     # 0-100 short-sale constraint (Reg SHO / low inst own)
    amplifier: float = 1.0                       # 1.0-1.3 (low float, high days-to-cover)
    overextension_factor: float = 1.0            # <=1.0 penalty for already-squeezed names
    liquidity_factor: float = 1.0                # <=1.0 penalty for untradeable microcaps
    coiled_spring: Optional[DetectorResult] = None  # good R/R footprint (tightening + pre-ignition)
    notes: List[str] = field(default_factory=list)

    def summary(self) -> str:
        sq = "n/a" if self.squeeze_score is None else f"{self.squeeze_score:5.1f}"
        st = "n/a" if self.composite_score is None else f"{self.composite_score:.0f}"
        extra = []
        if self.dynamics_score is not None:
            extra.append(f"dyn={self.dynamics_score:.0f}")
        if self.ignition_score is not None:
            extra.append(f"ign={self.ignition_score:.0f}")
        if self.constraint_score is not None:
            extra.append(f"con={self.constraint_score:.0f}")
        if abs(self.amplifier - 1.0) > 1e-9:
            extra.append(f"amp={self.amplifier:.2f}")
        if self.overextension_factor < 1.0:
            extra.append(f"ox={self.overextension_factor:.2f}")
        if self.liquidity_factor < 1.0:
            extra.append(f"liq={self.liquidity_factor:.2f}")
        extra_s = ("  " + " ".join(extra)) if extra else ""
        lines = [
            f"{self.ticker or '(unknown)':<8} {self.classification.value:<18} "
            f"score={sq}  conf={self.confidence.value:<6} struct={st}{extra_s} "
            f"coverage={self.coverage:.0%}",
        ]
        for rid, rule in SCORE_RULES.items():
            sc = self.rule_scores.get(rid)
            shown = " -- " if sc is None else f"{sc:5.1f}"
            lines.append(f"    {rid:<24} w={rule.weight:.2f}  {shown}")
        if self.bearish_convergence.triggered:
            lines.append(f"    [bearish-convergence] {self.bearish_convergence.reason}")
        if self.squeeze_fuel.triggered:
            lines.append(f"    [squeeze-fuel] {self.squeeze_fuel.reason}")
        if self.coiled_spring is not None and self.coiled_spring.triggered:
            lines.append(f"    [coiled-spring | good R/R] {self.coiled_spring.reason}")
        for n in self.notes:
            lines.append(f"    note: {n}")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tunable configuration (re-fit these on your own lending history if you can).
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class SqueezeConfig:
    # Interaction gate: short interest only counts as squeeze fuel when the
    # lending market is tight (Schultz's fee x utilization double-sort). The SI
    # sub-score is scaled to effective_si = si * (floor + (1-floor)*tightness),
    # tightness in [0,1] from the utilization/fee sub-scores. Applied only when
    # at least one lending signal (util or fee) is present.
    apply_interaction_gate: bool = True
    interaction_floor: float = 0.25
    # Final blend over the available layers (renormalised over those present).
    w_structural: float = 0.55
    w_dynamics: float = 0.15
    w_ignition: float = 0.15
    w_constraint: float = 0.15   # short-sale constraint: Reg SHO / low institutional ownership
    # Constraint layer thresholds (institutional ownership, %).
    inst_own_thin_pct: float = 20.0
    inst_own_low_pct: float = 40.0
    # Gamma/options (feeds ignition): options volume / ADV at or above -> MM hedging.
    gamma_oi_hot: float = 5.0
    # Amplifier (multiplicative on the final score): low float + high days-to-cover.
    max_amplifier: float = 1.30
    dtc_amp_med: float = 5.0        # days-to-cover above this -> +0.05
    dtc_amp_high: float = 10.0      #                         -> +0.10
    float_amp_low: float = 50e6     # float below this -> +0.05
    float_amp_small: float = 20e6   #                  -> +0.10
    float_amp_micro: float = 10e6   #                  -> +0.15
    # Classification cutoffs (on the final squeeze score).
    elevated_score: float = 70.0
    watch_score: float = 40.0
    low_coverage_advisory: float = 0.60
    # Overextension penalty (already-squeezed / mean-reversion): extreme recent
    # momentum means you are late; the move has largely happened. x final score.
    overext_mild_pct: float = 100.0      # > +100% in the window -> x0.80
    overext_strong_pct: float = 300.0    # > +300% -> x0.60
    overext_extreme_pct: float = 1000.0  # > +1000% -> x0.40
    # Liquidity / tradability guard: a squeeze you cannot trade is not actionable
    # (manipulation risk). x final score.
    illiquid_dollar_vol: float = 1e6     # < $1M/day traded value -> x0.60
    thin_dollar_vol: float = 5e6         # < $5M/day -> x0.85
    penny_price: float = 1.0             # price < $1 (and no dollar-volume) -> x0.70


DEFAULT_CONFIG = SqueezeConfig()

# Back-compat module aliases (older callers import these directly).
LOW_COVERAGE_ADVISORY = DEFAULT_CONFIG.low_coverage_advisory
ELEVATED_SCORE = DEFAULT_CONFIG.elevated_score
WATCH_SCORE = DEFAULT_CONFIG.watch_score


def _structural_score(
    rule_scores: Dict[str, Optional[float]], cfg: SqueezeConfig
) -> Tuple[Optional[float], float]:
    """Interaction-aware lending score + coverage (summed weight of rules scored).

    Discounts the short-interest sub-score when borrow is loose/cheap, so a
    crowded-but-comfortable short (high SI, low util/fee) scores LOW instead of
    riding its headline short interest. The discount needs *evidence* of comfort
    (a lending signal); with neither util nor fee we don't discount (the LOW-
    confidence WATCH cap handles the blind case instead).
    """
    util = rule_scores.get("d34_utilization_pct")
    fee = rule_scores.get("d35_borrow_rate_pct")
    si = rule_scores.get("d33_short_interest_pct")

    eff_si = si
    if si is not None and cfg.apply_interaction_gate and (util is not None or fee is not None):
        norms = [v / 100.0 for v in (util, fee) if v is not None]
        tightness = max(norms) if norms else 0.0
        eff_si = si * (cfg.interaction_floor + (1.0 - cfg.interaction_floor) * tightness)

    num = den = 0.0
    for rid, val in (("d34_utilization_pct", util),
                     ("d35_borrow_rate_pct", fee),
                     ("d33_short_interest_pct", eff_si)):
        if val is not None:
            w = SCORE_RULES[rid].weight
            num += w * val
            den += w
    return ((num / den) if den > 0 else None), den


def _dynamics_score(m: SqueezeMetrics, cfg: SqueezeConfig) -> Optional[float]:
    """Acceleration + regime: rising utilization / fee / short interest, and values
    breaking out to their OWN historical highs (percentile-vs-history, the signal a
    time series unlocks — Ortex/S3 stress rate-of-change; Cohen-Diether-Malloy:
    rising shorting demand predicts lower returns). None if no dynamic inputs."""
    subs = []
    if m.borrow_fee_trend_pct_pts is not None:
        subs.append(_band_score(m.borrow_fee_trend_pct_pts, [(0.0, 0.0), (2.0, 40.0), (5.0, 70.0), (math.inf, 100.0)]))
    if m.utilization_trend_pct_pts is not None:
        subs.append(_band_score(m.utilization_trend_pct_pts, [(0.0, 0.0), (5.0, 40.0), (10.0, 70.0), (math.inf, 100.0)]))
    if m.short_interest_trend_pct_pts is not None:
        subs.append(_band_score(m.short_interest_trend_pct_pts, [(0.0, 0.0), (10.0, 30.0), (25.0, 60.0), (math.inf, 100.0)]))
    # regime / breakout vs own history (a fee at its own 95th pctile is a tell)
    if m.fee_percentile is not None:
        subs.append(_band_score(m.fee_percentile, [(50.0, 0.0), (80.0, 40.0), (95.0, 70.0), (math.inf, 100.0)]))
    if m.utilization_percentile is not None:
        subs.append(_band_score(m.utilization_percentile, [(50.0, 0.0), (80.0, 40.0), (95.0, 70.0), (math.inf, 100.0)]))
    subs = [s for s in subs if s is not None]
    return (sum(subs) / len(subs)) if subs else None


def _ignition_score(m: SqueezeMetrics, cfg: SqueezeConfig) -> Optional[float]:
    """The spark: upward price momentum, shorts under water (S3: a profitable short
    cannot be squeezed), gamma — heavy call buying (options volume >> ADV) forces
    dealer delta-hedging (GME/AMC) — and investor attention (abnormal share volume,
    the 2026 rare-events study). None if no ignition input is provided."""
    subs = []
    if m.momentum_pct is not None:
        subs.append(_band_score(m.momentum_pct, [(0.0, 0.0), (5.0, 30.0), (15.0, 60.0), (math.inf, 100.0)]))
    if m.price_vs_short_cost_basis_pct is not None:
        subs.append(_band_score(m.price_vs_short_cost_basis_pct, [(0.0, 0.0), (10.0, 40.0), (30.0, 70.0), (math.inf, 100.0)]))
    if m.options_volume_vs_adv is not None:
        subs.append(_band_score(m.options_volume_vs_adv,
                                [(1.0, 0.0), (cfg.gamma_oi_hot * 0.6, 40.0), (cfg.gamma_oi_hot, 80.0), (math.inf, 100.0)]))
    if m.volume_vs_avg is not None:
        subs.append(_band_score(m.volume_vs_avg, [(1.5, 0.0), (3.0, 30.0), (5.0, 60.0), (math.inf, 100.0)]))
    subs = [s for s in subs if s is not None]
    return (sum(subs) / len(subs)) if subs else None


def _constraint_score(m: SqueezeMetrics, cfg: SqueezeConfig) -> Optional[float]:
    """Short-sale constraint / thin lendable supply. Reg SHO threshold membership
    (persistent fails-to-deliver) and low institutional ownership (Asquith-Pathak-
    Ritter: high SI + low institutional ownership underperforms; thin float is
    easier to squeeze). The 2026 rare-events study finds institutional ownership
    *reduces* squeeze odds — so high ownership scores 0 here. None if no input."""
    subs = []
    if m.on_reg_sho_threshold is not None:
        subs.append(100.0 if m.on_reg_sho_threshold else 0.0)
    if m.institutional_ownership_pct is not None:
        io = m.institutional_ownership_pct
        subs.append(80.0 if io < cfg.inst_own_thin_pct else (40.0 if io < cfg.inst_own_low_pct else 0.0))
    return (sum(subs) / len(subs)) if subs else None


def _amplifier(m: SqueezeMetrics, cfg: SqueezeConfig) -> float:
    """Low float and a high days-to-cover make every other signal more explosive
    (VW, KOSS). Multiplicative, capped at cfg.max_amplifier."""
    amp = 1.0
    if m.days_to_cover is not None:
        if m.days_to_cover > cfg.dtc_amp_high:
            amp += 0.10
        elif m.days_to_cover > cfg.dtc_amp_med:
            amp += 0.05
    if m.float_shares is not None and m.float_shares > 0:
        if m.float_shares < cfg.float_amp_micro:
            amp += 0.15
        elif m.float_shares < cfg.float_amp_small:
            amp += 0.10
        elif m.float_shares < cfg.float_amp_low:
            amp += 0.05
    return min(amp, cfg.max_amplifier)


def _overextension_factor(m: SqueezeMetrics, cfg: SqueezeConfig) -> float:
    """Penalise already-squeezed names: extreme recent momentum means the move has
    largely happened and mean-reversion risk dominates (squeezes round-trip)."""
    mom = m.momentum_pct
    if mom is None or mom <= cfg.overext_mild_pct:
        return 1.0
    if mom <= cfg.overext_strong_pct:
        return 0.80
    if mom <= cfg.overext_extreme_pct:
        return 0.60
    return 0.40


def _liquidity_factor(m: SqueezeMetrics, cfg: SqueezeConfig) -> Tuple[float, Optional[str]]:
    """Penalise untradeable names. A squeeze you cannot trade (thin dollar volume,
    or a sub-$1 penny stock) is not actionable and is manipulation-prone."""
    dv = m.dollar_volume
    if dv is not None:
        if dv < cfg.illiquid_dollar_vol:
            return 0.60, f"Illiquid: ~${dv / 1e6:.1f}M/day traded value — untradeable / manipulation risk."
        if dv < cfg.thin_dollar_vol:
            return 0.85, f"Thin liquidity: ~${dv / 1e6:.1f}M/day traded value."
        return 1.0, None
    if m.price is not None and m.price < cfg.penny_price:
        return 0.70, f"Penny stock (${m.price:.2f}) — manipulation-prone; confirm tradable size."
    return 1.0, None


def assess(m: SqueezeMetrics, config: SqueezeConfig = DEFAULT_CONFIG) -> SqueezeAssessment:
    """Score a name with the layered model and classify it.

    Layers (each 0-100, blended over those available) x context factors:
        structural - interaction-aware lending fragility (d33/d34/d35)
        dynamics   - acceleration (rising utilization / fee / short interest)
        ignition   - the spark (momentum + gamma + attention + shorts under water)
        constraint - Reg SHO / fails-to-deliver + low institutional ownership
      x amplifier (low float, high DTC) x overextension (already-squeezed) x
        liquidity (untradeable microcap)

    Classification (detectors are authoritative; otherwise on the final score):
        bearish convergence  -> GENUINELY_SHORT  (overrides everything)
        squeeze-fuel fires   -> SQUEEZE_FUEL
        score >= elevated    -> ELEVATED
        score >= watch       -> WATCH
        scorable             -> LOW
        nothing scorable     -> INSUFFICIENT_DATA
    A LOW-confidence call (no util, no fee) is capped at WATCH. `confidence` is
    HIGH with utilization, MEDIUM with only fee, LOW with neither. A missing
    input lowers coverage; it never silently counts as zero.
    """
    cfg = config
    notes: List[str] = []

    rule_scores: Dict[str, Optional[float]] = {rid: rule.score(m) for rid, rule in SCORE_RULES.items()}
    structural, coverage = _structural_score(rule_scores, cfg)
    dynamics = _dynamics_score(m, cfg)
    ignition = _ignition_score(m, cfg)
    constraint = _constraint_score(m, cfg)
    amplifier = _amplifier(m, cfg)
    overext = _overextension_factor(m, cfg)
    liq_factor, liq_note = _liquidity_factor(m, cfg)

    if structural is None:
        squeeze: Optional[float] = None
    else:
        parts = [(cfg.w_structural, structural)]
        if dynamics is not None:
            parts.append((cfg.w_dynamics, dynamics))
        if ignition is not None:
            parts.append((cfg.w_ignition, ignition))
        if constraint is not None:
            parts.append((cfg.w_constraint, constraint))
        base = sum(w * v for w, v in parts) / sum(w for w, _ in parts)
        squeeze = max(0.0, min(100.0, base * amplifier * overext * liq_factor))

    bearish = detect_bearish_convergence(m)
    fuel = detect_squeeze_fuel(m)
    coiled = detect_coiled_spring(m)

    # confidence is governed by the BEST predictor we actually have
    if m.utilization_pct is not None:
        confidence = Confidence.HIGH
    elif m.borrow_fee_pct is not None:
        confidence = Confidence.MEDIUM
    else:
        confidence = Confidence.LOW

    if m.utilization_pct is None:
        notes.append(
            "No utilization — the single best predictor (Schultz 2024). Running in "
            "degraded mode; detectors fall back to a borrow-fee proxy. Wire IBKR "
            "(free with an account) or Ortex (free tier) to upgrade to HIGH confidence."
        )
    if m.borrow_fee_pct is None:
        notes.append("No borrow fee — cannot judge how 'special' the name is.")
    if m.utilization_pct is None and m.borrow_fee_pct is None:
        notes.append(
            "Headline-only regime (SI%/days-to-cover): best used to AVOID crowded "
            "shorts, not to confirm a squeeze. Treat any squeeze call as a hypothesis."
        )
    if 0.0 < coverage < cfg.low_coverage_advisory:
        notes.append(f"Low coverage ({coverage:.0%}) — score rests on few inputs.")
    if dynamics is None and ignition is None and constraint is None:
        notes.append(
            "No dynamics/ignition/constraint inputs (trends, momentum, FTDs) — scoring "
            "the structural setup only. A coiled setup still needs acceleration + a catalyst."
        )
    if m.on_reg_sho_threshold:
        notes.append(
            "On the Reg SHO threshold list — persistent fails-to-deliver (a short-sale-"
            "constraint / squeeze-relevant flag)."
        )
    if m.source == "yfinance":
        notes.append(
            "yfinance supplies SI% and days-to-cover only; FINRA SI is stale "
            "(bi-monthly, published 7 business days after settlement)."
        )

    if m.shortable_shares_available is not None and m.shortable_shares_available <= 0:
        notes.append(
            "IBKR reports 0 shortable shares — borrow effectively unavailable now "
            "(a real-time tightness signal; utilization likely high)."
        )
    if overext < 1.0:
        notes.append(
            f"Overextended: up {m.momentum_pct:+.0f}% recently — much of the move may be "
            f"done (squeezes round-trip); score x{overext:.2f}."
        )
    if liq_note:
        notes.append(liq_note)
    if coiled.triggered:
        notes.append(coiled.reason)

    # --- classify on the final squeeze score (detectors are authoritative) ---
    if bearish.triggered:
        cls = SqueezeClass.GENUINELY_SHORT
    elif squeeze is None:
        cls = SqueezeClass.INSUFFICIENT_DATA
    elif fuel.triggered:
        cls = SqueezeClass.SQUEEZE_FUEL
    elif squeeze >= cfg.elevated_score:
        cls = SqueezeClass.ELEVATED
    elif squeeze >= cfg.watch_score:
        cls = SqueezeClass.WATCH
    else:
        cls = SqueezeClass.LOW

    # Headline-only (LOW confidence) cannot justify a squeeze call: high SI alone
    # is a bearish-leaning signal, not squeeze fuel. Cap the optimism at WATCH.
    if confidence == Confidence.LOW and cls in (SqueezeClass.ELEVATED, SqueezeClass.SQUEEZE_FUEL):
        cls = SqueezeClass.WATCH
        notes.append(
            "Capped at WATCH: no lending-market signal (fee/util); high SI alone "
            "is bearish-leaning, not a squeeze."
        )

    # A squeeze needs a CROWDED SHORT. With neither short interest nor utilization,
    # a high borrow fee alone cannot confirm one (it is often just an illiquid
    # microcap with no lendable supply) — cap the optimism at WATCH.
    if (m.short_interest_pct_float is None and m.utilization_pct is None
            and cls in (SqueezeClass.ELEVATED, SqueezeClass.SQUEEZE_FUEL)):
        cls = SqueezeClass.WATCH
        notes.append(
            "High borrow fee but short interest AND utilization both unknown — "
            "cannot confirm a crowded short (often an illiquid microcap); capped at WATCH."
        )

    # Already-squeezed: a huge recent move means the event has largely happened,
    # so the setup is no longer "fuel" — downgrade off the squeeze tiers.
    if overext <= 0.6 and cls in (SqueezeClass.SQUEEZE_FUEL, SqueezeClass.ELEVATED):
        cls = SqueezeClass.WATCH
        notes.append(
            "Downgraded to WATCH: already extended — the squeeze (if any) has largely played out."
        )

    return SqueezeAssessment(
        ticker=m.ticker,
        squeeze_score=squeeze,
        composite_score=structural,
        classification=cls,
        confidence=confidence,
        rule_scores=rule_scores,
        coverage=coverage,
        bearish_convergence=bearish,
        squeeze_fuel=fuel,
        dynamics_score=dynamics,
        ignition_score=ignition,
        constraint_score=constraint,
        amplifier=amplifier,
        overextension_factor=overext,
        liquidity_factor=liq_factor,
        coiled_spring=coiled,
        notes=notes,
    )


def rank_candidates(
    metrics: List[SqueezeMetrics], config: SqueezeConfig = DEFAULT_CONFIG
) -> List[SqueezeAssessment]:
    """Assess and rank a batch: squeeze fuel first, then by final score; bearish
    (genuinely-short) names sink toward the bottom — they are not candidates."""
    order = {
        SqueezeClass.SQUEEZE_FUEL: 0, SqueezeClass.ELEVATED: 1, SqueezeClass.WATCH: 2,
        SqueezeClass.GENUINELY_SHORT: 3, SqueezeClass.LOW: 4, SqueezeClass.INSUFFICIENT_DATA: 5,
    }
    out = [assess(m, config) for m in metrics]
    out.sort(key=lambda a: (order[a.classification], -(a.squeeze_score or 0.0)))
    return out


# ---------------------------------------------------------------------------
# Adapters (lazy imports; never required by the core)
# ---------------------------------------------------------------------------
def from_yfinance(
    ticker: str,
    *,
    utilization_pct: Optional[float] = None,
    borrow_fee_pct: Optional[float] = None,
    borrow_fee_trend_pct_pts: Optional[float] = None,
    utilization_trend_pct_pts: Optional[float] = None,
    on_reg_sho_threshold: Optional[bool] = None,
    options_volume_vs_adv: Optional[float] = None,
) -> SqueezeMetrics:
    """Build SqueezeMetrics from yfinance, injecting the lending data you supply.

    Auto-populates short interest (% of float and % of shares out), days-to-cover,
    float, shares short (+ prior, for the SI-trend), average volume, INSTITUTIONAL
    OWNERSHIP (heldPercentInstitutions) and an INVESTOR-ATTENTION proxy (today's
    volume / average volume). yfinance does NOT carry utilization or borrow fee —
    pass those from your stock-loan vendor; Reg SHO membership and options/gamma
    are passed in too. Requires `pip install yfinance`.
    """
    import yfinance as yf  # lazy

    info = yf.Ticker(ticker).get_info()

    def pct(x: Optional[float]) -> Optional[float]:
        return None if x is None else float(x) * 100.0

    avg_vol = info.get("averageVolume") or info.get("averageDailyVolume10Day")
    cur_vol = info.get("regularMarketVolume") or info.get("volume")
    vol_vs_avg = (float(cur_vol) / float(avg_vol)) if (cur_vol and avg_vol) else None

    return SqueezeMetrics(
        ticker=ticker.upper(),
        short_interest_pct_float=pct(info.get("shortPercentOfFloat")),
        short_interest_pct_shares_out=pct(info.get("sharesPercentSharesOut")),
        utilization_pct=utilization_pct,
        borrow_fee_pct=borrow_fee_pct,
        borrow_fee_trend_pct_pts=borrow_fee_trend_pct_pts,
        utilization_trend_pct_pts=utilization_trend_pct_pts,
        days_to_cover=info.get("shortRatio"),
        float_shares=info.get("floatShares"),
        shares_short=info.get("sharesShort"),
        shares_short_prior=info.get("sharesShortPriorMonth"),
        avg_daily_volume=avg_vol,
        institutional_ownership_pct=pct(info.get("heldPercentInstitutions")),
        volume_vs_avg=vol_vs_avg,
        price=info.get("currentPrice") or info.get("regularMarketPrice"),
        on_reg_sho_threshold=on_reg_sho_threshold,
        options_volume_vs_adv=options_volume_vs_adv,
        source="yfinance",
    )


_YF_LENDING_KEYS = frozenset({
    "utilization_pct", "borrow_fee_pct", "borrow_fee_trend_pct_pts",
    "utilization_trend_pct_pts", "options_volume_vs_adv",
})


def screen_yfinance(
    tickers: Iterable[str],
    *,
    lending_by_symbol: Optional[Dict[str, Dict[str, float]]] = None,
    reg_sho_symbols: Optional[Iterable[str]] = None,
    config: SqueezeConfig = DEFAULT_CONFIG,
    top: Optional[int] = None,
) -> List[SqueezeAssessment]:
    """Pull each ticker from yfinance, inject any lending data you have, and rank.

    `lending_by_symbol` maps SYMBOL -> {utilization_pct:, borrow_fee_pct:, ...} for
    the paywalled fields. One yfinance call per ticker (slow) — best for a curated
    watchlist; use screen_universe() for the whole market. Requires yfinance.
    """
    lending = {k.upper(): v for k, v in (lending_by_symbol or {}).items()}
    reg = {s.strip().upper() for s in (reg_sho_symbols or [])}
    have_reg = reg_sho_symbols is not None
    metrics: List[SqueezeMetrics] = []
    for t in tickers:
        ld = {k: v for k, v in lending.get(t.upper(), {}).items() if k in _YF_LENDING_KEYS}
        metrics.append(from_yfinance(
            t, on_reg_sho_threshold=((t.upper() in reg) if have_reg else None), **ld))
    ranked = rank_candidates(metrics, config)
    return ranked[:top] if top else ranked


# ---------------------------------------------------------------------------
# IBKR public shortable-stock file ("usa.txt") parser — free, no account.
# Format (pipe-delimited, one stock per line, usually a TRAILING pipe):
#   #BOF|usa|YYYY.MM.DD|HH:MM:SS                      <- metadata (timestamp kept)
#   SYM|CUR|NAME|CON|ISIN|REBATERATE|FEERATE|AVAILABLE|
#   GME|USD|GAMESTOP CORP|321524569|XXXXXXX1099|-12.5|18.0|350000|
#   #EOF|<count>
# FEERATE is the annualized borrow fee in %. AVAILABLE is shortable-share
# quantity (">10000000" = abundant general collateral; 0 = none/tight).
# ---------------------------------------------------------------------------
IBKR_FTP_HOST = "ftp3.interactivebrokers.com"
IBKR_FTP_USER = "shortstock"  # public; no password required


@dataclass
class IbkrShortRow:
    symbol: str
    fee_rate_pct: Optional[float]       # FEERATE — annualized borrow fee, %
    rebate_rate_pct: Optional[float]    # REBATERATE
    available: Optional[float]          # shortable shares available (None if unparseable)
    available_raw: str = ""             # original token, e.g. ">10000000"
    as_of: Optional[str] = None


def _parse_float(token: str) -> Optional[float]:
    try:
        return float(token.strip())
    except (ValueError, AttributeError):
        return None


def _parse_available(token: str) -> Tuple[Optional[float], str]:
    raw = (token or "").strip()
    if not raw or raw.upper() in {"NA", "N/A", "NONE", "-"}:
        return None, raw
    cleaned = raw.lstrip(">").replace(",", "").strip()  # ">10000000" -> "10000000"
    try:
        return float(cleaned), raw
    except ValueError:
        return None, raw


def parse_ibkr_shortable_text(text: str) -> Dict[str, IbkrShortRow]:
    """Parse the IBKR shortable file text into {SYMBOL: IbkrShortRow}.

    Pure function (no I/O) so it is fully testable offline. Robust to the
    trailing pipe, to a 'SYM|...' column-name header row, and to '#'-comment
    lines; columns are read positionally from the end (AVAILABLE, FEERATE,
    REBATERATE) so extra leading columns don't break it.
    """
    as_of: Optional[str] = None
    out: Dict[str, IbkrShortRow] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith("#"):
            if line.upper().startswith("#BOF"):
                parts = line.split("|")
                if len(parts) >= 4:
                    as_of = f"{parts[2]} {parts[3]}".strip()
                elif len(parts) >= 3:
                    as_of = parts[2].strip()
            continue
        parts = line.split("|")
        if parts and parts[-1] == "":   # drop the single trailing-pipe empty field
            parts = parts[:-1]
        if len(parts) < 4:
            continue
        sym = parts[0].strip().upper()
        if not sym or sym == "SYM":      # skip a column-name header row if present
            continue
        available, available_raw = _parse_available(parts[-1])
        out[sym] = IbkrShortRow(
            symbol=sym,
            fee_rate_pct=_parse_float(parts[-2]),
            rebate_rate_pct=_parse_float(parts[-3]),
            available=available,
            available_raw=available_raw,
            as_of=as_of,
        )
    return out


def fetch_ibkr_shortable_text(country: str = "usa", *, timeout: float = 30.0) -> str:  # pragma: no cover - network
    """Download the IBKR public shortable file over anonymous FTP (no account).

    Equivalent to ftp://shortstock@ftp3.interactivebrokers.com/<country>.txt .
    Stdlib only (ftplib); the file is refreshed several times per business day.
    """
    from ftplib import FTP  # lazy, stdlib

    lines: List[str] = []
    ftp = FTP(IBKR_FTP_HOST, timeout=timeout)
    try:
        ftp.login(user=IBKR_FTP_USER)  # no password
        ftp.retrlines(f"RETR {country}.txt", lines.append)
    finally:
        try:
            ftp.quit()
        except Exception:
            ftp.close()
    return "\n".join(lines)


def from_ibkr_file(
    ticker: str,
    *,
    text: Optional[str] = None,
    country: str = "usa",
    short_interest_pct_float: Optional[float] = None,
    days_to_cover: Optional[float] = None,
    utilization_pct: Optional[float] = None,
) -> SqueezeMetrics:
    """Build SqueezeMetrics for `ticker` from the IBKR shortable file.

    Populates borrow_fee_pct and shortable availability -> MEDIUM confidence with
    NO account needed. Pass `text` to parse an already-downloaded file (offline /
    testable); otherwise it is fetched over FTP. Short interest and days-to-cover
    are not in this file — inject them (e.g. from yfinance) if you have them.
    Utilization is GUI-only at IBKR (Orbisa) — pass it manually for HIGH confidence.

    Raises KeyError if the ticker is not present in the file.
    """
    if text is None:
        text = fetch_ibkr_shortable_text(country)
    rows = parse_ibkr_shortable_text(text)
    row = rows.get(ticker.strip().upper())
    if row is None:
        raise KeyError(
            f"{ticker!r} not in IBKR {country}.txt shortable file "
            f"({len(rows)} symbols parsed) — IBKR lists only currently-shortable names."
        )
    return SqueezeMetrics(
        ticker=row.symbol,
        short_interest_pct_float=short_interest_pct_float,
        utilization_pct=utilization_pct,
        borrow_fee_pct=row.fee_rate_pct,
        days_to_cover=days_to_cover,
        shortable_shares_available=row.available,
        as_of=row.as_of,
        source="ibkr_file",
    )


# ---------------------------------------------------------------------------
# FINRA bulk short-interest parser + full-universe screen.
# FINRA publishes consolidated equity short interest (free, bi-monthly): per
# security currentShortShareNumber, previousShortShareNumber, daysToCover and
# average daily volume. Combine with the IBKR file (fee) + a float map to score
# the WHOLE shortable universe, not a hand-picked watchlist.
# ---------------------------------------------------------------------------
@dataclass
class FinraShortRow:
    symbol: str
    shares_short: Optional[float]
    shares_short_prior: Optional[float]
    days_to_cover: Optional[float]
    avg_daily_volume: Optional[float]
    settlement_date: Optional[str] = None


def _num(token: Optional[str]) -> Optional[float]:
    if token is None:
        return None
    t = token.strip().replace(",", "")
    if not t or t.upper() in {"N/A", "NA", "NULL", "-"}:
        return None
    try:
        return float(t)
    except ValueError:
        return None


def _at(parts: List[str], idx: Optional[int]) -> Optional[str]:
    return parts[idx] if (idx is not None and 0 <= idx < len(parts)) else None


def parse_finra_short_interest(text: str) -> Dict[str, FinraShortRow]:
    """Parse a FINRA consolidated equity short-interest export (CSV or pipe).

    Header-driven: columns are matched by name substring, so column order and
    extra columns don't matter. Recognises issueSymbolIdentifier / symbol,
    currentShortShareNumber, previousShortShareNumber, daysToCoverQuantity,
    averageDailyVolumeQuantity and settlementDate. Pure function — testable offline.
    """
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if not lines:
        return {}
    header = lines[0]
    delim = "|" if ("|" in header and header.count("|") >= header.count(",")) else ","
    cols = [c.strip().lower() for c in header.split(delim)]

    def find(*needles: str) -> Optional[int]:
        for i, c in enumerate(cols):
            if all(n in c for n in needles):
                return i
        return None

    i_sym = find("symbol")
    i_cur = find("currentshort")
    if i_cur is None:
        i_cur = find("short", "share")
    i_prev = find("previousshort")
    if i_prev is None:
        i_prev = find("previous", "short")
    i_dtc = find("daystocover")
    i_adv = find("averagedaily")
    if i_adv is None:
        i_adv = find("avgdaily")
    i_date = find("settlement")
    if i_sym is None or i_cur is None:
        return {}

    out: Dict[str, FinraShortRow] = {}
    for line in lines[1:]:
        parts = line.split(delim)
        sym = (_at(parts, i_sym) or "").strip().upper()
        if not sym or sym == cols[i_sym].strip().upper():
            continue
        date = _at(parts, i_date)
        out[sym] = FinraShortRow(
            symbol=sym,
            shares_short=_num(_at(parts, i_cur)),
            shares_short_prior=_num(_at(parts, i_prev)),
            days_to_cover=_num(_at(parts, i_dtc)),
            avg_daily_volume=_num(_at(parts, i_adv)),
            settlement_date=(date.strip() if date else None),
        )
    return out


def screen_universe(
    *,
    ibkr_text: Optional[str] = None,
    finra_text: Optional[str] = None,
    float_by_symbol: Optional[Dict[str, float]] = None,
    reg_sho_symbols: Optional[Iterable[str]] = None,
    institutional_ownership_by_symbol: Optional[Dict[str, float]] = None,
    price_by_symbol: Optional[Dict[str, float]] = None,
    momentum_by_symbol: Optional[Dict[str, float]] = None,
    config: SqueezeConfig = DEFAULT_CONFIG,
    top: Optional[int] = None,
) -> List[SqueezeAssessment]:
    """Score and rank the FULL shortable universe from free bulk files.

    Merge the IBKR shortable file (borrow fee + availability, full universe), the
    FINRA consolidated short-interest file (shares short + prior + days-to-cover,
    full universe), an optional float map (turns shares short into SI% of float,
    enabling the d33 rule and the detectors), the Reg SHO threshold list, and an
    optional institutional-ownership map. Returns rank_candidates() over every
    symbol seen. All offline/testable — you supply the downloaded text.
    """
    ibkr = parse_ibkr_shortable_text(ibkr_text) if ibkr_text else {}
    finra = parse_finra_short_interest(finra_text) if finra_text else {}
    floats = {k.upper(): v for k, v in (float_by_symbol or {}).items()}
    inst = {k.upper(): v for k, v in (institutional_ownership_by_symbol or {}).items()}
    prices = {k.upper(): v for k, v in (price_by_symbol or {}).items()}
    moms = {k.upper(): v for k, v in (momentum_by_symbol or {}).items()}
    reg = {s.strip().upper() for s in (reg_sho_symbols or [])}
    have_reg = reg_sho_symbols is not None

    metrics: List[SqueezeMetrics] = []
    for sym in sorted(set(ibkr) | set(finra) | set(floats)):
        ib = ibkr.get(sym)
        fi = finra.get(sym)
        flo = floats.get(sym)
        ss = fi.shares_short if fi else None
        si_pct = (100.0 * ss / flo) if (ss and flo) else None
        metrics.append(SqueezeMetrics(
            ticker=sym,
            short_interest_pct_float=si_pct,
            borrow_fee_pct=(ib.fee_rate_pct if ib else None),
            days_to_cover=(fi.days_to_cover if fi else None),
            shares_short=ss,
            shares_short_prior=(fi.shares_short_prior if fi else None),
            avg_daily_volume=(fi.avg_daily_volume if fi else None),
            float_shares=flo,
            shortable_shares_available=(ib.available if ib else None),
            institutional_ownership_pct=inst.get(sym),
            price=prices.get(sym),
            momentum_pct=moms.get(sym),
            on_reg_sho_threshold=((sym in reg) if have_reg else None),
            as_of=(ib.as_of if ib else (fi.settlement_date if fi else None)),
            source="universe",
        ))
    ranked = rank_candidates(metrics, config)
    return ranked[:top] if top else ranked


# ---------------------------------------------------------------------------
# Time-series / dynamic context: collapse a history of snapshots into one
# assess-ready metric carrying trends + regime (percentile-vs-own-history) +
# momentum + volume surge. This is what makes the dynamics layer fire on real
# data — a fee at its own 95th percentile and rising is far more squeeze-prone
# than the same level sitting flat. Free history: FINRA (SI, bi-monthly), an
# archived IBKR usa.txt (fee + availability, daily), SEC FTDs, yfinance
# (price/volume). Paid daily & exportable: Ortex / Fintel utilization + CTB.
# ---------------------------------------------------------------------------
@dataclass
class Snapshot:
    """One dated observation in a metric time series (any subset of fields)."""
    date: str = ""
    short_interest_pct_float: Optional[float] = None
    utilization_pct: Optional[float] = None
    borrow_fee_pct: Optional[float] = None
    price: Optional[float] = None
    volume: Optional[float] = None


def _pct_rank(series: List[float], value: float) -> float:
    """Percentile (0-100) of `value` within `series`."""
    return (100.0 * sum(1 for x in series if x <= value) / len(series)) if series else 0.0


def metrics_from_timeseries(
    ticker: str, snapshots: List[Snapshot], *, base: Optional[SqueezeMetrics] = None
) -> SqueezeMetrics:
    """Collapse a time-ASCENDING list of Snapshots into one assess-ready metric:
    the latest levels (the SNAPSHOT) plus the DYNAMIC context computed from the
    history — fee/utilization trend (level change) and percentile-vs-own-history,
    short-interest % change, price momentum, and a volume surge (attention). `base`
    supplies static extras (float, institutional ownership, Reg SHO) to keep.
    """
    snaps = list(snapshots)
    if not snaps:
        raise ValueError("metrics_from_timeseries: empty series")
    last = snaps[-1]

    def col(attr: str) -> List[float]:
        return [getattr(s, attr) for s in snaps if getattr(s, attr) is not None]

    kw: Dict[str, object] = {"ticker": ticker, "source": "timeseries", "as_of": last.date or None}
    for attr in ("short_interest_pct_float", "utilization_pct", "borrow_fee_pct", "price"):
        v = getattr(last, attr)
        if v is not None:
            kw[attr] = v

    fees = col("borrow_fee_pct")
    if len(fees) >= 2:
        kw["borrow_fee_trend_pct_pts"] = fees[-1] - fees[0]
        kw["fee_percentile"] = _pct_rank(fees, fees[-1])
    utils = col("utilization_pct")
    if len(utils) >= 2:
        kw["utilization_trend_pct_pts"] = utils[-1] - utils[0]
        kw["utilization_percentile"] = _pct_rank(utils, utils[-1])
    sis = col("short_interest_pct_float")
    if len(sis) >= 2 and sis[0] > 0:
        # carry the SI % change through the shares_short trend property
        kw["shares_short"], kw["shares_short_prior"] = sis[-1], sis[0]
    prices = col("price")
    if len(prices) >= 2 and prices[0] > 0:
        kw["momentum_pct"] = 100.0 * (prices[-1] - prices[0]) / prices[0]
    vols = col("volume")
    if len(vols) >= 4:
        trailing = sum(vols[:-1]) / len(vols[:-1])
        if trailing > 0:
            kw["volume_vs_avg"] = vols[-1] / trailing
            kw.setdefault("avg_daily_volume", trailing)

    return replace(base, **kw) if base is not None else SqueezeMetrics(**kw)


def screen_panel(
    histories: Dict[str, List[Snapshot]], *,
    base_by_symbol: Optional[Dict[str, SqueezeMetrics]] = None,
    config: SqueezeConfig = DEFAULT_CONFIG, top: Optional[int] = None,
) -> List[SqueezeAssessment]:
    """Rank a PANEL of time series (snapshot + dynamic context per name).
    `histories` maps SYMBOL -> time-ascending list[Snapshot]; `base_by_symbol`
    maps SYMBOL -> a SqueezeMetrics with static extras (float, Reg SHO, etc.)."""
    base = {k.upper(): v for k, v in (base_by_symbol or {}).items()}
    metrics = [metrics_from_timeseries(sym, snaps, base=base.get(sym.upper()))
               for sym, snaps in histories.items()]
    ranked = rank_candidates(metrics, config)
    return ranked[:top] if top else ranked


# --- daily snapshot CSVs: accumulate one per day, then load_panel() them ---
SNAPSHOT_HEADER = "date,ticker,short_interest_pct_float,utilization_pct,borrow_fee_pct,price"


def _csv_num(x: Optional[float]) -> str:
    return "" if x is None else f"{x:g}"


def to_snapshot_csv(metrics: List[SqueezeMetrics], date: str) -> str:
    """One day's screen -> a compact snapshot CSV (date, ticker, SI%, util, fee,
    price). Write one file per day; load_panel() turns a stack of them into the
    time-series panel that powers the coiling/dynamics reads."""
    lines = [SNAPSHOT_HEADER]
    for m in metrics:
        lines.append(",".join([date, m.ticker, _csv_num(m.short_interest_pct_float),
                               _csv_num(m.utilization_pct), _csv_num(m.borrow_fee_pct),
                               _csv_num(m.price)]))
    return "\n".join(lines) + "\n"


def parse_snapshot_csv(text: str) -> List[Tuple[str, str, Snapshot]]:
    """Parse a snapshot CSV into (date, ticker, Snapshot) rows. Pure / testable."""
    out: List[Tuple[str, str, Snapshot]] = []
    lines = [ln for ln in text.splitlines() if ln.strip()]
    for line in lines[1:]:  # skip header
        p = line.split(",")
        if len(p) < 2 or not p[1].strip():
            continue

        def g(i: int) -> Optional[float]:
            try:
                return float(p[i]) if (i < len(p) and p[i].strip()) else None
            except ValueError:
                return None

        date, tkr = p[0].strip(), p[1].strip().upper()
        out.append((date, tkr, Snapshot(date=date, short_interest_pct_float=g(2),
                                        utilization_pct=g(3), borrow_fee_pct=g(4), price=g(5))))
    return out


def build_panel(rows: List[Tuple[str, str, Snapshot]]) -> Dict[str, List[Snapshot]]:
    """Group (date, ticker, Snapshot) rows into {ticker: [Snapshot...]} ordered by
    date (ISO date strings sort chronologically)."""
    by: Dict[str, List[Tuple[str, Snapshot]]] = {}
    for date, tkr, snap in rows:
        by.setdefault(tkr, []).append((date, snap))
    panel: Dict[str, List[Snapshot]] = {}
    for tkr, items in by.items():
        items.sort(key=lambda x: x[0])
        panel[tkr] = [s for _, s in items]
    return panel


def load_panel(snapshot_csv_texts: Iterable[str]) -> Dict[str, List[Snapshot]]:
    """Combine many daily snapshot CSVs into a panel for screen_panel()."""
    rows: List[Tuple[str, str, Snapshot]] = []
    for text in snapshot_csv_texts:
        rows.extend(parse_snapshot_csv(text))
    return build_panel(rows)


def utilization_from_loan(shares_on_loan: float, shares_available_to_lend: float) -> Optional[float]:
    """Utilization % = shares on loan / shares available to lend, in percent.

    Handy if a data source gives you the two raw quantities rather than the ratio
    (e.g. you read 'Shares on Loan' and the lendable inventory off a dashboard).
    Returns None if the denominator is non-positive.
    """
    if not shares_available_to_lend or shares_available_to_lend <= 0:
        return None
    return 100.0 * float(shares_on_loan) / float(shares_available_to_lend)


def render_streamlit_panel() -> None:  # pragma: no cover - UI glue
    """Optional drop-in panel for the existing Streamlit app (`cycle`).

    Lets a user type a ticker, pull SI%/days-to-cover from yfinance, manually
    enter utilization & borrow fee from their lending vendor, and see the score
    and both detector verdicts. Requires streamlit (and yfinance for the pull).
    """
    import streamlit as st  # lazy

    st.subheader("Short-Squeeze Candidate Screener")
    st.caption(
        "Utilization and borrow fee are the predictive signals and are NOT on "
        "free feeds — enter them from Ortex / S3 / your prime broker."
    )
    ticker = st.text_input("Ticker", value="GME", key="sq_ticker").strip().upper()
    col1, col2, col3 = st.columns(3)
    si = col1.number_input("Short interest (% float)", 0.0, 1000.0, 20.0, 0.5)
    util = col2.number_input("Utilization (%)", 0.0, 100.0, 90.0, 1.0)
    fee = col3.number_input("Borrow fee (%/yr)", 0.0, 1000.0, 12.0, 0.25)
    fee_trend = st.slider("Borrow-fee change (pct pts)", -50.0, 50.0, 0.0, 0.5)
    pnl = st.slider("Price vs short cost basis (% above entry)", -90.0, 300.0, 0.0, 1.0)

    m = SqueezeMetrics(
        ticker=ticker,
        short_interest_pct_float=si,
        utilization_pct=util,
        borrow_fee_pct=fee,
        borrow_fee_trend_pct_pts=fee_trend,
        price_vs_short_cost_basis_pct=pnl,
        source="manual",
    )
    a = assess(m)
    st.metric("Classification", a.classification.value,
              delta=None if a.composite_score is None else f"score {a.composite_score:.0f}/100")
    st.code(a.summary())


# ---------------------------------------------------------------------------
# Citations (see SHORT_SQUEEZE_FRAMEWORK.md for the full annotated bibliography)
# ---------------------------------------------------------------------------
CITATIONS: Dict[str, str] = {
    "Schultz 2024": (
        "Schultz, P. (2024). Short Squeezes and Their Consequences. JFQA "
        "59(1): 68-96. (Online Jan 2023; SSRN WP 4025226, Feb 2022.) "
        "Utilization is the single best predictor; borrow-fee mean 2.673%, "
        "median ~0.375%, p95 11.0%."
    ),
    "D'Avolio 2002": (
        "D'Avolio, G. (2002). The Market for Borrowing Stock. JFE 66(2-3): "
        "271-306. ~91% GC at ~17bp; ~9% special averaging 4.30%."
    ),
    "Asquith-Pathak-Ritter 2005": (
        "Asquith, Pathak & Ritter (2005). Short interest, institutional "
        "ownership, and stock returns. JFE 78(2): 243-276. High SI + low "
        "institutional ownership under-performs (-215bp/mo EW)."
    ),
    "Boehmer-Jones-Zhang 2008": (
        "Boehmer, Jones & Zhang (2008). Which Shorts Are Informed? JF 63(2): "
        "491-527. Heavily-shorted under-perform lightly-shorted ~1.16% over 20 days."
    ),
    "Cohen-Diether-Malloy 2007": (
        "Cohen, Diether & Malloy (2007). Supply and Demand Shifts in the "
        "Shorting Market. JF 62(5). A shorting-demand increase predicts "
        "~-2.98% abnormal return next month."
    ),
    "Drechsler-Drechsler 2014": (
        "Drechsler & Drechsler (2014). The Shorting Premium and Asset-Pricing "
        "Anomalies. NBER WP 20282. Anomalies concentrate in expensive-to-short "
        "names; cheap-minus-expensive earns ~1.4%/mo."
    ),
    "Engelberg-Reed-Ringgenberg 2018": (
        "Engelberg, Reed & Ringgenberg (2018). Short-Selling Risk. JF 73(2). "
        "Recall/fee-spike risk is priced and deters arbitrage."
    ),
    "S3 Partners": (
        "S3 Partners / I. Dusaniwsky. Crowded Score + Squeeze Score (70-100 "
        "squeezable, >90 high risk); a profitable short can't be squeezed."
    ),
    "Ortex": "Ortex. Short Squeeze Score (Types 1-3) over SI, utilization, CTB, price and their rates of change.",
    "Fintel": "Fintel. Short Squeeze Score 0-100 (50 = average) over SI, % float, days-to-cover, borrow fee, float, volume.",
}


# ---------------------------------------------------------------------------
# Zero-dependency demo
# ---------------------------------------------------------------------------
def _r(x: Optional[float]) -> str:
    return "" if x is None else f"{x:.1f}"


def report(assessments: List["SqueezeAssessment"], *, top: int = 25) -> str:
    """Human-readable ranked report: bucket counts, the top-N candidates, and the
    bearish (genuinely-short) list. Pass an already-ranked list (rank_candidates /
    screen_universe / screen_yfinance)."""
    from collections import Counter
    counts = Counter(a.classification.value for a in assessments)
    lines = [
        f"Short-squeeze screen — {len(assessments)} names  |  "
        + "  ".join(f"{k}={v}" for k, v in counts.most_common()),
        "-" * 78,
        f"{'#':>3}  {'TKR':<7}{'CLASS':<16}{'score':>5} {'conf':<7}{'struct':>6}  flags",
    ]
    for i, a in enumerate(assessments[:top], 1):
        flag = ""
        if a.coiled_spring is not None and a.coiled_spring.triggered:
            flag += " |COILED good-R/R|"
        if a.overextension_factor < 1.0:
            flag += " [overextended]"
        if a.liquidity_factor < 1.0:
            flag += " [illiquid]"
        lines.append(f"{i:>3}  {a.ticker:<7}{a.classification.value:<16}{_r(a.squeeze_score):>5} "
                     f"{a.confidence.value:<7}{_r(a.composite_score):>6}{flag}")
    bearish = [a.ticker for a in assessments if a.classification == SqueezeClass.GENUINELY_SHORT]
    if bearish:
        lines += ["", f"GENUINELY_SHORT (cheap borrow -> bearish/avoid, {len(bearish)}): "
                  + ", ".join(bearish[:40]) + (" ..." if len(bearish) > 40 else "")]
    return "\n".join(lines)


def to_csv(assessments: List["SqueezeAssessment"]) -> str:
    """All assessments as CSV text (for a spreadsheet / further analysis)."""
    import csv as _csv
    import io as _io
    buf = _io.StringIO()
    w = _csv.writer(buf)
    w.writerow(["ticker", "classification", "confidence", "squeeze_score", "structural",
                "dynamics", "ignition", "constraint", "amplifier", "overext", "liquidity",
                "coverage", "bearish_convergence", "squeeze_fuel"])
    for a in assessments:
        w.writerow([a.ticker, a.classification.value, a.confidence.value,
                    _r(a.squeeze_score), _r(a.composite_score), _r(a.dynamics_score),
                    _r(a.ignition_score), _r(a.constraint_score), round(a.amplifier, 3),
                    round(a.overextension_factor, 3), round(a.liquidity_factor, 3),
                    round(a.coverage, 3), a.bearish_convergence.triggered, a.squeeze_fuel.triggered])
    return buf.getvalue()


def _demo() -> None:
    """Illustrate the framework on four archetypes — runs with no dependencies."""
    examples = [
        # --- HIGH confidence (utilization available) ---
        # 1. Crowded, expensive, supply gone, shorts under water -> SQUEEZE FUEL.
        SqueezeMetrics(
            ticker="FUEL", short_interest_pct_float=28.0, utilization_pct=98.0,
            borrow_fee_pct=42.0, borrow_fee_trend_pct_pts=15.0,
            price_vs_short_cost_basis_pct=35.0, days_to_cover=6.0,
        ),
        # 2. Lots of shorts but ample cheap borrow -> GENUINELY SHORT (bearish).
        SqueezeMetrics(
            ticker="BEAR", short_interest_pct_float=22.0, utilization_pct=38.0,
            borrow_fee_pct=0.9, days_to_cover=3.0,
        ),
        # 3. General-collateral nothing-burger -> LOW.
        SqueezeMetrics(
            ticker="MEH", short_interest_pct_float=3.0, utilization_pct=12.0,
            borrow_fee_pct=0.35, days_to_cover=1.2,
        ),
        # --- DEGRADED: no utilization (the "build without IBKR" regime) ---
        # 4. Hot, rising fee but no utilization -> SQUEEZE FUEL [proxy], MEDIUM conf.
        SqueezeMetrics(
            ticker="FEEPRX", short_interest_pct_float=26.0, borrow_fee_pct=28.0,
            borrow_fee_trend_pct_pts=9.0, days_to_cover=5.0,
        ),
        # 5. Cheap fee, no utilization -> GENUINELY SHORT [proxy], MEDIUM conf.
        SqueezeMetrics(
            ticker="BEARPX", short_interest_pct_float=20.0, borrow_fee_pct=0.8,
            days_to_cover=2.5,
        ),
        # 6. yfinance-only headline regime: high SI%, no lending data -> LOW conf best-effort.
        SqueezeMetrics(
            ticker="BLIND", short_interest_pct_float=31.0, days_to_cover=7.0,
            source="yfinance",
        ),
    ]
    print("Short-squeeze framework — reference constants (Schultz 2024):")
    print(f"  borrow fee  mean={BORROW_FEE_MEAN_PCT}%  median={BORROW_FEE_MEDIAN_PCT}%  p95={BORROW_FEE_P95_PCT}%\n")
    for m in examples:
        print(assess(m).summary())
        print()

    # --- IBKR public-file parser (offline sample; the real file needs no account) ---
    sample = (
        "#BOF|usa|2024.05.01|22:15:38\n"
        "SYM|CUR|NAME|CON|ISIN|REBATERATE|FEERATE|AVAILABLE|\n"
        "GME|USD|GAMESTOP CORP|321524569|XXXXXXX1099|-12.5|18.0|350000|\n"
        "AAPL|USD|APPLE INC|265598|XXXXXXX1005|4.5|0.25|>10000000|\n"
    )
    rows = parse_ibkr_shortable_text(sample)
    print("IBKR usa.txt parser (offline sample):")
    for sym, r in rows.items():
        fee = "n/a" if r.fee_rate_pct is None else f"{r.fee_rate_pct:6.2f}%"
        print(f"  {sym:<6} fee={fee}  available={r.available_raw}  as_of={r.as_of}")
    print()
    # GME fee from the file + short interest injected from elsewhere -> MEDIUM conf.
    print(assess(from_ibkr_file("GME", text=sample,
                                short_interest_pct_float=24.0, days_to_cover=4.0)).summary())

    # --- rank_candidates(): a mini leaderboard (the layered v2 model) ---
    universe = [
        SqueezeMetrics("HOT", short_interest_pct_float=30, utilization_pct=93, borrow_fee_pct=22,
                       borrow_fee_trend_pct_pts=8, utilization_trend_pct_pts=12, momentum_pct=18,
                       price_vs_short_cost_basis_pct=25, days_to_cover=11, float_shares=8e6),
        SqueezeMetrics("LCID", short_interest_pct_float=33.6, borrow_fee_pct=26.1, days_to_cover=4.3),
        SqueezeMetrics("IBRX", short_interest_pct_float=33.5, borrow_fee_pct=3.5, days_to_cover=7.6),
        SqueezeMetrics("GRPN", short_interest_pct_float=64.6, borrow_fee_pct=1.5, days_to_cover=6.3),
    ]
    print("\nrank_candidates() leaderboard (layered model):")
    for a in rank_candidates(universe):
        print(f"  {a.ticker:<6}{a.classification.value:<17} score={a.squeeze_score:5.1f} "
              f"struct={a.composite_score:5.1f} conf={a.confidence.value}")

    # --- screen_universe(): rank the whole shortable universe from bulk files ---
    ibkr_bulk = ("#BOF|usa|2026.06.19|14:00:00\n"
                 "GME|USD|GAMESTOP|1|X|-5|18.0|350000|\n"
                 "LCID|USD|LUCID|2|X|-20|26.1|0|\n")
    finra_bulk = ("issueSymbolIdentifier,currentShortShareNumber,previousShortShareNumber,daysToCoverQuantity\n"
                  "GME,45000000,40000000,6.43\nLCID,300000000,280000000,4.30\n")
    print("\nscreen_universe() (bulk IBKR + FINRA + float + Reg SHO):")
    for a in screen_universe(ibkr_text=ibkr_bulk, finra_text=finra_bulk,
                             float_by_symbol={"GME": 300e6, "LCID": 2e9},
                             reg_sho_symbols=["GME"], top=5):
        print(f"  {a.ticker:<6}{a.classification.value:<17} score={a.squeeze_score:5.1f} "
              f"conf={a.confidence.value} con={a.constraint_score}")


def _read(path: Optional[str]) -> Optional[str]:  # pragma: no cover - CLI glue
    return open(path, encoding="utf-8", errors="replace").read() if path else None


def _load_map(path: Optional[str]) -> Optional[Dict[str, float]]:  # pragma: no cover - CLI glue
    """Load a 'SYMBOL,VALUE' file (floats or prices) into a dict."""
    if not path:
        return None
    out: Dict[str, float] = {}
    for line in open(path, encoding="utf-8", errors="replace"):
        parts = line.replace(",", " ").split()
        if len(parts) >= 2:
            try:
                out[parts[0].strip().upper()] = float(parts[1])
            except ValueError:
                continue
    return out


def _main(argv: Optional[List[str]] = None) -> None:  # pragma: no cover - CLI glue
    import argparse
    p = argparse.ArgumentParser(description="Short-squeeze candidate screener.")
    sub = p.add_subparsers(dest="cmd")
    sc = sub.add_parser("screen", help="rank the universe from free bulk files")
    sc.add_argument("--ibkr", help="IBKR usa.txt (borrow fee + availability)")
    sc.add_argument("--finra", help="FINRA short-interest export (CSV or pipe)")
    sc.add_argument("--floats", help="'SYMBOL,FLOAT_SHARES' file")
    sc.add_argument("--prices", help="'SYMBOL,PRICE' file")
    sc.add_argument("--momentum", help="'SYMBOL,PCT_1M_CHANGE' file (overextension penalty)")
    sc.add_argument("--reg-sho", dest="reg_sho", help="Reg SHO threshold symbols, one per line")
    sc.add_argument("--top", type=int, default=25)
    sc.add_argument("--csv", help="write all assessments to this CSV path")
    sub.add_parser("demo", help="run the offline demo")
    args = p.parse_args(argv)

    if args.cmd == "screen":
        reg = None
        if args.reg_sho:
            reg = [s.strip() for s in open(args.reg_sho, encoding="utf-8", errors="replace") if s.strip()]
        ranked = screen_universe(
            ibkr_text=_read(args.ibkr), finra_text=_read(args.finra),
            float_by_symbol=_load_map(args.floats), price_by_symbol=_load_map(args.prices),
            momentum_by_symbol=_load_map(args.momentum), reg_sho_symbols=reg)
        print(report(ranked, top=args.top))
        if args.csv:
            open(args.csv, "w", encoding="utf-8").write(to_csv(ranked))
            print(f"\nWrote {len(ranked)} rows to {args.csv}")
    else:
        _demo()


if __name__ == "__main__":
    _main()
