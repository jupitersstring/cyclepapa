"""Pattern detectors and scoring for PSU comp structures.

The thesis (yetanothervalueblog "Corporate Dark Arts Gone Awry" + Munger
on incentives): a PSU grant *is* a directional bet by the comp committee
on what management will do. Read the bet, then ask whether it leaves
common shareholders on the same side as the CEO.

Most-asymmetric setup for a common investor:
    has_psu_program      = True
    per_share_metrics    = [TSR, EPS, FCF/share, ROIC, ...]
    aggregate_metrics    = []                       # no market-cap / EBITDA
                                                    # gaming risk
    stock_price_hurdles  = deeply OTM (>1.5x current)
    discretionary_lang   = False                    # board can't override
    retirement_lang      = False                    # CEO won't milk-and-exit

That setup says: the board has wired the CEO into a lottery ticket they
can only win by driving real per-share value, and they cannot escape via
dilutive M&A, EBITDA games, or a rescue bonus. The comp committee, in
other words, has already priced a transformation -- and the common can
ride alongside.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


# ---------------------------------------------------------------------------
# Pattern bank
# ---------------------------------------------------------------------------

PSU_KEYWORDS = re.compile(
    r"\b("
    r"performance share units?|performance[- ]based stock units?|"
    r"performance stock units?|"
    r"PSUs?|PRSUs?|"
    r"performance[- ]vested|performance[- ]conditioned|"
    r"performance[- ]vesting (?:awards?|RSUs?|units?)|"
    r"market[- ]based (?:RSUs?|awards?|units?)|"
    r"market[- ]conditioned (?:awards?|RSUs?|units?)|"
    r"price[- ]vested (?:awards?|RSUs?|options?)|"
    r"performance restricted stock units?|"
    r"performance[- ]based restricted stock|"
    r"long[- ]term (?:performance|incentive) (?:awards?|units?)|"
    # UK terminology
    r"long[- ]term incentive plan|LTIP|"
    r"performance share plan|PSP|"
    r"deferred share (?:bonus|plan)|"
    r"matching shares plan|"
    r"performance rights"
    r")\b",
    re.I,
)

# "Aggregate" metrics: dilutable / scalable without per-share value creation.
AGGREGATE_PATTERNS = [
    (re.compile(r"\bmarket cap(italization)?\b", re.I), "market_cap"),
    (re.compile(r"\b(adjusted )?EBITDA\b(?![^.]{0,40}per share)", re.I), "absolute_ebitda"),
    (re.compile(r"\btotal revenues?\b(?![^.]{0,40}per share)", re.I), "absolute_revenue"),
    (re.compile(r"\bnet income\b(?![^.]{0,40}per share)", re.I), "absolute_net_income"),
    (re.compile(r"\bnet sales\b(?![^.]{0,40}per share)", re.I), "absolute_sales"),
    (re.compile(r"\boperating income\b(?![^.]{0,40}per share)", re.I), "absolute_op_income"),
]

# Per-share / return-on-capital metrics: shareholder-aligned.
PER_SHARE_PATTERNS = [
    (re.compile(r"\bearnings per share\b|\bdiluted EPS\b|(?<![A-Z])\bEPS\b", re.I), "eps"),
    (re.compile(r"\b(free cash flow|FCF) per share\b", re.I), "fcf_per_share"),
    (re.compile(r"\b(adjusted )?total shareholder return\b|(?<![A-Z])\bTSR\b", re.I), "tsr"),
    # ROIIC = Return on Incremental Invested Capital (capital-allocator
    # signature -- forces management to earn returns on NEW capital).
    # Rarer than ROIC; firms that use it (Constellation Software,
    # Diploma plc, etc.) are signalling deliberate capital discipline.
    (re.compile(
        r"\bROIIC\b|"
        r"\breturn on incremental invested capital\b|"
        r"\breturn on incremental capital\b|"
        r"\bincremental ROIC\b|"
        r"\bmarginal ROIC\b|"
        r"\bincremental return on (invested )?capital\b",
        re.I), "roiic"),
    (re.compile(r"\breturn on invested capital\b|(?<![A-Z])\bROIC\b", re.I), "roic"),
    (re.compile(r"\breturn on capital employed\b|(?<![A-Z])\bROCE\b", re.I), "roce"),
    (re.compile(r"\breturn on equity\b|(?<![A-Z])\bROE\b", re.I), "roe"),
    (re.compile(r"\brevenue per share\b|\bbook value per share\b", re.I), "other_per_share"),
    (re.compile(r"\bcash flow return on (invested capital|investment)\b|\bCFROI\b", re.I), "cfroi"),
]

# "$X stock price" or "$X per share" hurdles for vesting.
STOCK_PRICE_HURDLE = re.compile(
    r"(?:stock|share) price[^.\n]{0,40}?\$([0-9]+(?:\.[0-9]+)?)",
    re.I,
)
GENERIC_PRICE_TARGET = re.compile(
    r"\$([0-9]+(?:\.[0-9]+)?)\s*per share",
    re.I,
)
# VWAP-anchored hurdles -- common in tranched inducement grants.
VWAP_HURDLE = re.compile(
    r"(?:VWAP|volume[- ]weighted average price)[^.\n]{0,80}?\$([0-9]+(?:\.[0-9]+)?)",
    re.I,
)
VWAP_HURDLE_REVERSE = re.compile(
    r"\$([0-9]+(?:\.[0-9]+)?)\s+(?:VWAP|volume[- ]weighted)",
    re.I,
)
# "trailing 45-day average / highest 60-day average / X-day moving average"
TRAILING_AVG_HURDLE = re.compile(
    r"(?:trailing|highest|moving|average)[^.\n]{0,80}?\$([0-9]+(?:\.[0-9]+)?)",
    re.I,
)
# "threshold / target / maximum at $X / $Y / $Z" -- inducement-grant style.
THRESHOLD_TARGET_MAX = re.compile(
    r"(?:threshold|target|maximum)[^.\n]{0,40}?\$([0-9]+(?:\.[0-9]+)?)",
    re.I,
)
# Multi-tranche dollar ladders: "$8 / $20", "$15, $30, $45",
# "$1.50, $2.25, $3.00, $3.75 and $4.50" -- accept comma, slash or
# bare "and" as the connector.
PRICE_LADDER = re.compile(
    r"(\$[0-9]+(?:\.[0-9]+)?)"
    r"(?:\s*(?:[/,]\s*(?:and\s+)?|\s+and\s+)\s*\$[0-9]+(?:\.[0-9]+)?){1,8}",
    re.I,
)
# "$X hurdle" / "$X share price target" / "vest at $X" -- reverse phrasing
# where the dollar comes before the noun.
PRE_POSITIONAL_HURDLE = re.compile(
    r"\$([0-9]+(?:\.[0-9]+)?)\s+(?:stock\s+price\s+)?(?:hurdle|target|threshold|"
    r"per\s+share|VWAP|trailing|share\s+price)",
    re.I,
)
VEST_AT_PRICE = re.compile(
    r"vest(?:ing|s)?\s+(?:at|upon|when)[^.\n]{0,40}?\$([0-9]+(?:\.[0-9]+)?)",
    re.I,
)

# Hurdle-table trigger: many proxies/8-Ks render PSU ladders as tables that
# survive HTML-to-text conversion as one $-value per line. A purely
# in-line ladder regex misses these. After a trigger phrase, collect every
# plausible $-amount within the next ~4000 chars.
HURDLE_TABLE_TRIGGER = re.compile(
    r"("
    r"achievement of (?:the following|specified|certain)?\s*(?:specified\s+)?"
    r"(?:stock|share) price"
    r"|achievement of the following"
    r"|the following (?:stock|share) price"
    r"|the following (?:price )?(?:hurdles?|targets?|thresholds?|levels?|tranches?)"
    r"|the following (?:VWAP|volume[- ]weighted average price)"
    r"|vest(?:ing|s)? (?:in (?:the )?)?(?:\w+\s+)?(?:equal )?tranches?"
    r"|vest(?:ing|s)? upon (?:the )?(?:achievement|attainment)"
    r"|tranches based on (?:the )?achievement"
    r"|price (?:hurdles?|targets?|thresholds?) (?:are|of|set|equal)"
    r"|performance hurdles? (?:are|of|set)"
    r"|VWAP (?:hurdles?|of|equal|targets?)"
    r"|weighted average (?:closing )?price[^.]{0,200}?(?:equal|exceed|reach)"
    r"|highest (?:\d+[- ])?day average"
    r"|trailing \d+[- ]day"
    r"|share price targets? are|stock price targets? are"
    r"|if the (?:Company.s )?(?:stock|share) price reaches?"
    r"|(?:upon|when) the (?:Company.s )?(?:stock|share) price (?:exceeds|reaches|achieves)"
    r"|price[- ]vesting conditions?"
    r"|the price thresholds? are"
    r"|vest(?:ing|s)? based on (?:stock|share) price"
    r"|provided (?:that )?the (?:stock|share) price (?:reaches|exceeds|achieves)"
    r")",
    re.I,
)
DOLLAR_AMT = re.compile(r"\$\s*([0-9]+(?:\.[0-9]+)?)")

# % share-price appreciation -- e.g. Penguin Solutions: "25% / 50% / 75% /
# 100% share price appreciation". Convert to implied $ hurdles using the
# current price as a proxy for grant-date baseline (best-effort).
APPRECIATION_LADDER = re.compile(
    r"((?:[0-9]{1,3}\s*%\s*[/,]?\s*(?:and\s+)?){2,})"
    r"\s*(?:share\s+price\s+)?appreciation",
    re.I,
)
# "% share price appreciation" — Penguin Solutions style.
APPRECIATION_PCT = re.compile(
    r"([0-9]{1,3})\s*%\s*(?:share\s+price\s+)?appreciation",
    re.I,
)
# Plain "$X share price hurdle" / "stock price target of $X"
STOCK_PRICE_TARGET = re.compile(
    r"(?:price\s+target|price\s+hurdle|hurdle (?:of|at)|target (?:of|at)|"
    r"reach[a-z]*\s*(?:a\s+)?\$|exceed[a-z]*\s+\$)\s*\$?([0-9]+(?:\.[0-9]+)?)",
    re.I,
)

DISCRETIONARY = re.compile(
    r"\b(discretionary bonus|special bonus|notwithstanding the formula|"
    r"committee[- ]determined|in its sole discretion|exercise(d)? discretion)\b",
    re.I,
)

RETIREMENT = re.compile(
    r"\b(retire|retirement|step(ping)? down|transition agreement|"
    r"departing|outgoing|succession plan)\b",
    re.I,
)

REPRICING = re.compile(
    r"\b(repric(e|ing|ed)|exchange offer|modif(y|ied|ication) of (the )?award|"
    r"reset of performance|adjust(ed)? targets?|recalibrat)\b",
    re.I,
)

FRONT_LOADED = re.compile(
    r"\b(front[- ]loaded|one[- ]time grant|special grant|transformational award|"
    r"mega[- ]grant|inducement award)\b",
    re.I,
)


# ---------------------------------------------------------------------------
# Feature extraction
# ---------------------------------------------------------------------------

@dataclass
class PSUFeatures:
    ticker: str
    has_psu_program: bool = False
    aggregate_metrics: list[str] = field(default_factory=list)
    per_share_metrics: list[str] = field(default_factory=list)
    stock_price_hurdles: list[float] = field(default_factory=list)
    discretionary_language: bool = False
    retirement_language: bool = False
    repricing_language: bool = False
    front_loaded_language: bool = False
    snippet: str = ""


def _psu_windows(text: str, before: int = 600, after: int = 1500) -> str:
    """Concatenated text windows around every PSU mention. Flags evaluated
    only inside these windows do not pick up unrelated boilerplate (e.g.
    director-retirement age policy, repricing of *option* plans not PSUs)
    elsewhere in the proxy."""
    spans: list[tuple[int, int]] = []
    for m in PSU_KEYWORDS.finditer(text):
        spans.append((max(0, m.start() - before), min(len(text), m.end() + after)))
    if not spans:
        return ""
    spans.sort()
    merged: list[list[int]] = []
    for s, e in spans:
        if merged and s <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], e)
        else:
            merged.append([s, e])
    return "\n".join(text[s:e] for s, e in merged)


def extract_features(ticker: str, comp_text: str) -> PSUFeatures:
    f = PSUFeatures(ticker=ticker)
    f.has_psu_program = bool(PSU_KEYWORDS.search(comp_text))

    # Metric detection across the full comp section -- aggregate vs
    # per-share metrics often live in performance-metric tables that the
    # narrow PSU window misses.
    seen_agg: set[str] = set()
    for pat, name in AGGREGATE_PATTERNS:
        if name in seen_agg:
            continue
        if pat.search(comp_text):
            f.aggregate_metrics.append(name)
            seen_agg.add(name)

    seen_ps: set[str] = set()
    for pat, name in PER_SHARE_PATTERNS:
        if name in seen_ps:
            continue
        if pat.search(comp_text):
            f.per_share_metrics.append(name)
            seen_ps.add(name)

    # Hurdle parsing -- localized to PSU paragraphs only. Non-PSU "stock
    # price" mentions (e.g. fee schedules, beneficial ownership tables)
    # would otherwise pollute the upside-kicker score. Multiple regexes
    # cover the common inducement-grant hurdle phrasings: VWAP-anchored,
    # trailing-average, threshold/target/maximum ladders, multi-dollar
    # tranches like "$15 / $30 / $45".
    psu_window = _psu_windows(comp_text)
    base = psu_window if psu_window else comp_text

    found: list[float] = []
    for pat in (STOCK_PRICE_HURDLE, GENERIC_PRICE_TARGET,
                VWAP_HURDLE, VWAP_HURDLE_REVERSE,
                THRESHOLD_TARGET_MAX, STOCK_PRICE_TARGET,
                PRE_POSITIONAL_HURDLE, VEST_AT_PRICE):
        found.extend(float(x) for x in pat.findall(base))

    # Trigger-window extraction for table-rendered ladders. Wider window
    # (4000 chars) handles verbose phrasings like "the weighted average
    # price ... over 30 consecutive trading days is equal to or greater
    # than $50". We harvest every plausible $-amount and let downstream
    # de-duplication keep the unique tranche values.
    for m in HURDLE_TABLE_TRIGGER.finditer(base):
        window = base[m.end(): m.end() + 4000]
        for d in DOLLAR_AMT.findall(window):
            try:
                v = float(d)
                if 1.0 <= v <= 10000.0:
                    found.append(v)
            except ValueError:
                pass

    # Multi-tranche ladders: extract every $-amount inside the run.
    for m in PRICE_LADDER.finditer(base):
        for v in re.findall(r"\$([0-9]+(?:\.[0-9]+)?)", m.group(0)):
            try:
                found.append(float(v))
            except ValueError:
                pass

    # Drop fee-table / par-value noise (<$1) and obvious dividends/strikes.
    hurdles = sorted({round(h, 2) for h in found if 1.0 <= h <= 10000.0})
    f.stock_price_hurdles = hurdles

    # Risk flags evaluated only inside PSU windows -- generic governance
    # boilerplate elsewhere in the proxy should not falsely cut the score.
    flag_text = psu_window if psu_window else comp_text
    f.discretionary_language = bool(DISCRETIONARY.search(flag_text))
    f.retirement_language = bool(RETIREMENT.search(flag_text))
    f.repricing_language = bool(REPRICING.search(flag_text))
    f.front_loaded_language = bool(FRONT_LOADED.search(flag_text))

    m = PSU_KEYWORDS.search(comp_text)
    if m:
        a, b = max(0, m.start() - 400), min(len(comp_text), m.end() + 1200)
        f.snippet = comp_text[a:b].strip()
    return f


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

@dataclass
class PSUScore:
    alignment: float            # 0-100. Are the metrics shareholder-aligned?
    upside_kicker: float        # 0-100. How OTM are the price hurdles?
    transformation_signal: bool # The Munger-aligned asymmetric setup
    asymmetry: float            # 0-100. alignment x upside, with penalties
    flags: list[str]


def score(features: PSUFeatures, current_price: float | None) -> PSUScore:
    flags: list[str] = []

    # ------ Alignment --------------------------------------------------
    align = 50.0
    if features.per_share_metrics:
        align += 12 * min(3, len(features.per_share_metrics))
        flags.append("Per-share / return metrics: " + ", ".join(features.per_share_metrics))
    if features.aggregate_metrics:
        align -= 10 * min(3, len(features.aggregate_metrics))
        flags.append("Aggregate metrics (dilution risk): "
                     + ", ".join(features.aggregate_metrics))
    if features.discretionary_language:
        align -= 18
        flags.append("Discretionary / committee-override language present")
    if features.repricing_language:
        align -= 12
        flags.append("Repricing / target-reset language present")
    if features.retirement_language and any(
        m in features.aggregate_metrics
        for m in ("absolute_ebitda", "absolute_op_income", "absolute_net_income")
    ):
        align -= 15
        flags.append("Retirement + absolute earnings target -> milk-and-exit risk")
    align = max(0.0, min(100.0, align))

    # ------ Upside kicker (depth of OTM hurdles) -----------------------
    upside = 0.0
    if features.stock_price_hurdles and current_price and current_price > 0:
        max_hurdle = max(features.stock_price_hurdles)
        moneyness = max_hurdle / current_price
        if moneyness > 1.0:
            # 1.0x current -> 0; 2.0x -> 50; 3.0x+ -> 100.
            upside = max(0.0, min(100.0, (moneyness - 1.0) * 50.0))
            flags.append(
                f"Top vest hurdle ${max_hurdle:.2f} = {moneyness:.2f}x current price"
            )
        elif moneyness <= 1.0:
            flags.append(
                f"Top hurdle ${max_hurdle:.2f} already in the money "
                f"({moneyness:.2f}x); minimal kicker"
            )

    # ------ Transformation setup --------------------------------------
    transformation = bool(
        features.has_psu_program
        and features.per_share_metrics
        and features.stock_price_hurdles
        and current_price
        and max(features.stock_price_hurdles) / current_price >= 1.5
        and not features.discretionary_language
        and not features.retirement_language
        and not features.repricing_language
    )
    if transformation:
        flags.append(
            "TRANSFORMATION SETUP: per-share metrics + deep OTM hurdles + "
            "no override / milking risk -- comp committee priced for breakout"
        )
    if features.front_loaded_language:
        flags.append("Front-loaded / inducement grant language present")

    # ------ Composite -------------------------------------------------
    if upside > 0:
        asym = (align * upside) / 100.0
    else:
        # No usable price hurdle: anchor to alignment alone, dampened.
        asym = align * 0.5
    if transformation:
        asym = min(100.0, asym * 1.15)
    if features.discretionary_language or features.repricing_language:
        asym *= 0.85

    return PSUScore(
        alignment=round(align, 1),
        upside_kicker=round(upside, 1),
        transformation_signal=transformation,
        asymmetry=round(asym, 1),
        flags=flags,
    )
