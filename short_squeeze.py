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
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple

__all__ = [
    "SqueezeMetrics",
    "ScoreRule",
    "SCORE_RULES",
    "DetectorResult",
    "detect_bearish_convergence",
    "detect_squeeze_fuel",
    "SqueezeClass",
    "Confidence",
    "SqueezeAssessment",
    "assess",
    "from_yfinance",
    "utilization_from_loan",
    "parse_ibkr_shortable_text",
    "fetch_ibkr_shortable_text",
    "from_ibkr_file",
    "IbkrShortRow",
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

    # --- short-side P&L proxy (S3 insight) ---
    # Percent the current price sits ABOVE the estimated average short entry.
    # > 0  => the average short is under water (squeezable).
    # < 0  => shorts are still in profit (cannot be forced out -> not a squeeze).
    price_vs_short_cost_basis_pct: Optional[float] = None

    as_of: Optional[str] = None
    source: str = "manual"

    # ---- derived helpers ----
    @property
    def short_interest_trend_pct_pts(self) -> Optional[float]:
        """Change in shares short vs prior report, as a % of the prior level."""
        if self.shares_short is None or not self.shares_short_prior:
            return None
        return 100.0 * (self.shares_short - self.shares_short_prior) / self.shares_short_prior


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
    composite_score: Optional[float]            # 0-100, weighted over AVAILABLE rules
    classification: SqueezeClass
    confidence: Confidence                       # HIGH/MEDIUM/LOW by data availability
    rule_scores: Dict[str, Optional[float]]
    coverage: float                              # 0-1: weight of rules we could score
    bearish_convergence: DetectorResult
    squeeze_fuel: DetectorResult
    notes: List[str] = field(default_factory=list)

    def summary(self) -> str:
        cs = "n/a" if self.composite_score is None else f"{self.composite_score:5.1f}"
        lines = [
            f"{self.ticker or '(unknown)':<8} {self.classification.value:<18} "
            f"score={cs}  conf={self.confidence.value:<6} coverage={self.coverage:.0%}",
        ]
        for rid, rule in SCORE_RULES.items():
            sc = self.rule_scores.get(rid)
            shown = " -- " if sc is None else f"{sc:5.1f}"
            lines.append(f"    {rid:<24} w={rule.weight:.2f}  {shown}")
        if self.bearish_convergence.triggered:
            lines.append(f"    [bearish-convergence] {self.bearish_convergence.reason}")
        if self.squeeze_fuel.triggered:
            lines.append(f"    [squeeze-fuel] {self.squeeze_fuel.reason}")
        for n in self.notes:
            lines.append(f"    note: {n}")
        return "\n".join(lines)


# Below this coverage we still produce a call, but flag it (advisory only).
LOW_COVERAGE_ADVISORY = 0.60
ELEVATED_SCORE = 70.0
WATCH_SCORE = 40.0


def assess(m: SqueezeMetrics) -> SqueezeAssessment:
    """Run the three rules + both detectors and produce a classified assessment.

    The composite score is a weight-renormalised average over the rules we can
    actually evaluate, so a missing input lowers coverage rather than silently
    counting as zero. Classification order of precedence:

        1. bearish convergence triggered            -> GENUINELY_SHORT
        2. squeeze-fuel triggered & score elevated  -> SQUEEZE_FUEL
        3. score >= ELEVATED                         -> ELEVATED
        4. score >= WATCH                            -> WATCH
        5. something scorable                        -> LOW
        6. nothing scorable at all                   -> INSUFFICIENT_DATA

    `confidence` (HIGH/MEDIUM/LOW) reflects which inputs were available:
    utilization present -> HIGH; only borrow fee -> MEDIUM; neither -> LOW. A
    missing input never silently counts as zero; it lowers coverage instead.
    """
    notes: List[str] = []

    rule_scores: Dict[str, Optional[float]] = {}
    num = 0.0
    den = 0.0
    for rid, rule in SCORE_RULES.items():
        sc = rule.score(m)
        rule_scores[rid] = sc
        if sc is not None:
            num += rule.weight * sc
            den += rule.weight
    coverage = den  # weights sum to 1.0, so accumulated weight == coverage
    composite = (num / den) if den > 0 else None

    bearish = detect_bearish_convergence(m)
    fuel = detect_squeeze_fuel(m)

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
    if 0.0 < coverage < LOW_COVERAGE_ADVISORY:
        notes.append(f"Low coverage ({coverage:.0%}) — score rests on few inputs.")
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

    # --- classify (best-effort; INSUFFICIENT_DATA only when nothing is scorable) ---
    if bearish.triggered:
        cls = SqueezeClass.GENUINELY_SHORT
    elif composite is None:
        cls = SqueezeClass.INSUFFICIENT_DATA
    elif fuel.triggered and composite >= ELEVATED_SCORE:
        cls = SqueezeClass.SQUEEZE_FUEL
    elif composite >= ELEVATED_SCORE:
        cls = SqueezeClass.ELEVATED
    elif composite >= WATCH_SCORE:
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

    return SqueezeAssessment(
        ticker=m.ticker,
        composite_score=composite,
        classification=cls,
        confidence=confidence,
        rule_scores=rule_scores,
        coverage=coverage,
        bearish_convergence=bearish,
        squeeze_fuel=fuel,
        notes=notes,
    )


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
) -> SqueezeMetrics:
    """Build SqueezeMetrics from yfinance, injecting lending data you supply.

    yfinance exposes short interest, % of float, and days-to-cover, but NOT
    utilization or borrow fee. Pass those in from your stock-loan vendor /
    prime broker if you have them; otherwise they stay None and the engine will
    flag the gap. Requires `pip install yfinance`.
    """
    import yfinance as yf  # lazy

    info = yf.Ticker(ticker).get_info()

    def pct(x: Optional[float]) -> Optional[float]:
        return None if x is None else float(x) * 100.0

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
        avg_daily_volume=info.get("averageVolume"),
        source="yfinance",
    )


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


if __name__ == "__main__":
    _demo()
