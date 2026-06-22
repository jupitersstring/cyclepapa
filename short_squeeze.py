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
The two most predictive inputs — UTILIZATION and BORROW FEE — are securities-
lending data. They are NOT available from free retail feeds. yfinance gives you
short_interest % of float, shares short, and days-to-cover (short ratio) only.
Utilization and borrow fee require a stock-loan data vendor (Ortex, S3 Partners,
FIS Astec, S&P/IHS Markit, or your prime broker / IBKR). `from_yfinance()`
therefore populates SI% and days-to-cover and leaves utilization/fee as None,
and the engine will loudly flag that it is "flying blind on the dominant
predictor." Also note FINRA short interest is reported twice a month and
published on the 7th business day after the settlement date — it is stale by
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
    "SqueezeAssessment",
    "assess",
    "from_yfinance",
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

        SI% > 10  AND  utilization < 50%  AND  borrow_fee < 3%

    High short interest with ample (low-utilization) and cheap (low-fee) borrow
    means the short side is comfortable and uncrowded: sophisticated capital
    that is genuinely short on fundamentals and not at risk of being forced out.
    Treat as a bearish tell and explicitly NOT a squeeze candidate.
    """
    missing = [
        name
        for name, v in (
            ("short_interest_pct_float", m.short_interest_pct_float),
            ("utilization_pct", m.utilization_pct),
            ("borrow_fee_pct", m.borrow_fee_pct),
        )
        if v is None
    ]
    if missing:
        return DetectorResult(
            "bearish_convergence", False,
            "Cannot evaluate: missing " + ", ".join(missing), missing,
        )

    si, util, fee = m.short_interest_pct_float, m.utilization_pct, m.borrow_fee_pct
    triggered = (si > BEARISH_SI_MIN) and (util < BEARISH_UTIL_MAX) and (fee < BEARISH_FEE_MAX)
    if triggered:
        reason = (
            f"SI {si:.1f}% > {BEARISH_SI_MIN:g}% but utilization {util:.1f}% < "
            f"{BEARISH_UTIL_MAX:g}% and borrow {fee:.2f}% < {BEARISH_FEE_MAX:g}%: "
            "borrow is ample and cheap -> comfortable, uncrowded short -> "
            "genuinely short (bearish), NOT a squeeze setup."
        )
    else:
        reason = (
            f"Not genuinely-short: need SI>{BEARISH_SI_MIN:g} & util<"
            f"{BEARISH_UTIL_MAX:g} & fee<{BEARISH_FEE_MAX:g}; got "
            f"SI={si:.1f}, util={util:.1f}, fee={fee:.2f}."
        )
    return DetectorResult("bearish_convergence", triggered, reason)


def detect_squeeze_fuel(m: SqueezeMetrics) -> DetectorResult:
    """Fragile-short / squeeze-fuel detector.

        utilization >= 85%  AND  short_interest% >= 10%
        AND ( borrow_fee >= 10%  OR  borrow_fee rising )
        AND  shorts are NOT clearly in profit (S3: a profitable short can't be
             squeezed; you need mark-to-market losses to force covering).

    The borrow-fee condition is satisfied by a high LEVEL or a positive TREND,
    because an accelerating fee is often the earliest tell that supply is about
    to run out.
    """
    missing = [
        name
        for name, v in (
            ("short_interest_pct_float", m.short_interest_pct_float),
            ("utilization_pct", m.utilization_pct),
            ("borrow_fee_pct", m.borrow_fee_pct),
        )
        if v is None
    ]
    if missing:
        return DetectorResult(
            "squeeze_fuel", False,
            "Cannot evaluate: missing " + ", ".join(missing), missing,
        )

    si, util, fee = m.short_interest_pct_float, m.utilization_pct, m.borrow_fee_pct
    fee_rising = (m.borrow_fee_trend_pct_pts or 0.0) > 0.0
    fee_hot = (fee >= FUEL_FEE_MIN) or fee_rising
    # Shorts profitable => not squeezable. Only veto when we actually have the
    # P&L proxy and it says shorts are comfortably in the money.
    shorts_in_profit = (
        m.price_vs_short_cost_basis_pct is not None
        and m.price_vs_short_cost_basis_pct < 0.0
    )

    triggered = (
        util >= FUEL_UTIL_MIN
        and si >= FUEL_SI_MIN
        and fee_hot
        and not shorts_in_profit
    )

    bits = [
        f"util {util:.1f}% {'>=' if util >= FUEL_UTIL_MIN else '<'} {FUEL_UTIL_MIN:g}%",
        f"SI {si:.1f}% {'>=' if si >= FUEL_SI_MIN else '<'} {FUEL_SI_MIN:g}%",
        f"fee {fee:.2f}% {'hot' if fee_hot else 'cool'}"
        + (" (rising)" if fee_rising else ""),
    ]
    if shorts_in_profit:
        bits.append(
            f"shorts still in profit ({m.price_vs_short_cost_basis_pct:.1f}% below entry) -> can't be forced"
        )
    reason = ("SQUEEZE FUEL: " if triggered else "Not (yet) squeeze fuel: ") + "; ".join(bits)
    return DetectorResult("squeeze_fuel", triggered, reason)


# ---------------------------------------------------------------------------
# Scoring engine
# ---------------------------------------------------------------------------
class SqueezeClass(str, Enum):
    GENUINELY_SHORT = "GENUINELY_SHORT"      # bearish convergence: avoid as a squeeze
    SQUEEZE_FUEL = "SQUEEZE_FUEL"            # fragile short side, primed
    ELEVATED = "ELEVATED"                    # high score, watch
    WATCH = "WATCH"                          # middling
    LOW = "LOW"                              # nothing here
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"  # missing the dominant predictor


@dataclass
class SqueezeAssessment:
    ticker: str
    composite_score: Optional[float]            # 0-100, weighted over AVAILABLE rules
    classification: SqueezeClass
    rule_scores: Dict[str, Optional[float]]
    coverage: float                              # 0-1: weight of rules we could score
    bearish_convergence: DetectorResult
    squeeze_fuel: DetectorResult
    notes: List[str] = field(default_factory=list)

    def summary(self) -> str:
        cs = "n/a" if self.composite_score is None else f"{self.composite_score:5.1f}"
        lines = [
            f"{self.ticker or '(unknown)':<8} {self.classification.value:<18} "
            f"score={cs}  coverage={self.coverage:.0%}",
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


# Coverage below this (i.e. we are missing too much weight, in practice the
# utilization rule) means we cannot responsibly call something a squeeze.
MIN_COVERAGE_FOR_CALL = 0.60
ELEVATED_SCORE = 70.0
WATCH_SCORE = 40.0


def assess(m: SqueezeMetrics) -> SqueezeAssessment:
    """Run the three rules + both detectors and produce a classified assessment.

    The composite score is a weight-renormalised average over the rules we can
    actually evaluate, so a missing input lowers coverage rather than silently
    counting as zero. Classification order of precedence:

        1. bearish convergence triggered            -> GENUINELY_SHORT
        2. missing the dominant predictor (util)    -> INSUFFICIENT_DATA
        3. squeeze-fuel triggered & score elevated  -> SQUEEZE_FUEL
        4. score >= ELEVATED                         -> ELEVATED
        5. score >= WATCH                            -> WATCH
        6. otherwise                                 -> LOW
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

    util_missing = m.utilization_pct is None
    if util_missing:
        notes.append(
            "Utilization missing — the single best predictor (Schultz 2024). "
            "Score is unreliable without a securities-lending feed (Ortex/S3/IBKR)."
        )
    if m.borrow_fee_pct is None:
        notes.append("Borrow fee missing — cannot judge how 'special' the name is.")
    if m.source == "yfinance":
        notes.append(
            "yfinance supplies SI% and days-to-cover only; utilization & borrow "
            "fee must come from a stock-loan vendor. FINRA SI is also stale "
            "(bi-monthly, published 7 business days after settlement)."
        )

    # --- classify ---
    if bearish.triggered:
        cls = SqueezeClass.GENUINELY_SHORT
    elif composite is None or coverage < MIN_COVERAGE_FOR_CALL or util_missing:
        cls = SqueezeClass.INSUFFICIENT_DATA
    elif fuel.triggered and composite >= ELEVATED_SCORE:
        cls = SqueezeClass.SQUEEZE_FUEL
    elif composite >= ELEVATED_SCORE:
        cls = SqueezeClass.ELEVATED
    elif composite >= WATCH_SCORE:
        cls = SqueezeClass.WATCH
    else:
        cls = SqueezeClass.LOW

    return SqueezeAssessment(
        ticker=m.ticker,
        composite_score=composite,
        classification=cls,
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
        # 4. yfinance-only: high SI%, but no lending data -> INSUFFICIENT_DATA.
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


if __name__ == "__main__":
    _demo()
