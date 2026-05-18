"""Sentiment scoring.

Combines VADER (general-purpose, emoji/slang) + a finance-idiom overlay
(beat/miss/tendies/MOASS) + the **Loughran-McDonald** financial dictionary
(positive/negative/uncertainty/litigious counts). LM is the canonical
academic fix for the well-known problem that general lexica
mis-classify finance words ("liability", "tax", "vice" all show as
negative in Harvard-IV but are neutral in earnings-call context).

`score()` returns a single compound, but `score_full()` exposes the LM
component so downstream code (filings, news) can use it directly.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

log = logging.getLogger(__name__)

# Conservative finance-aware overlays. Values are signed adjustments applied
# on top of the VADER compound score, then clipped to [-1, 1].
FINANCE_LEXICON: dict[str, float] = {
    # Bullish
    "beat": 0.25, "beats": 0.25, "crush": 0.30, "smashed": 0.35,
    "tendies": 0.30, "moass": 0.50, "rip": 0.20, "ripping": 0.25,
    "moon": 0.30, "🚀": 0.35, "rallied": 0.20, "breakout": 0.25,
    "upgraded": 0.20, "raised guidance": 0.40, "raised pt": 0.20,
    "going long": 0.30, "calls": 0.10, "yolo": 0.15,
    # Bearish
    "miss": -0.25, "missed": -0.25, "guided down": -0.40,
    "downgraded": -0.20, "cut guidance": -0.40, "bagholder": -0.30,
    "puts": -0.10, "dump": -0.25, "bagholding": -0.30, "rugpull": -0.45,
    "delisted": -0.50, "bankruptcy": -0.60, "going short": -0.30,
    "shorting": -0.20, "tank": -0.20, "tanking": -0.25,
}


@dataclass
class SentimentScore:
    compound: float       # [-1, 1]
    pos: float
    neu: float
    neg: float
    label: str            # "bullish" | "bearish" | "neutral"
    lm_score: float = 0.0       # Loughran-McDonald polarity in [-1, 1]
    lm_uncertainty: int = 0     # raw LM uncertainty count
    lm_litigious: int = 0       # raw LM litigious count


class SentimentScorer:
    def __init__(self, lm_blend: float = 0.4) -> None:
        """`lm_blend` in [0,1]: how much of the final compound comes from
        the Loughran-McDonald polarity vs VADER+finance-overlay. 0 = VADER
        only, 1 = LM only. Default 0.4 = LM contributes ~40% on finance
        text, ~0% on emoji-heavy social text (LM scores near zero on
        non-financial text)."""
        try:
            from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
            self._vader = SentimentIntensityAnalyzer()
        except ImportError:
            log.warning("vaderSentiment not installed; sentiment will be neutral")
            self._vader = None
        self.lm_blend = float(lm_blend)

    def score(self, text: str) -> SentimentScore:
        if not text:
            return SentimentScore(0.0, 0.0, 1.0, 0.0, "neutral")
        # VADER + finance-overlay component.
        vader_compound = 0.0
        pos = neu = neg = 0.0
        if self._vader is not None:
            s = self._vader.polarity_scores(text)
            pos, neu, neg = s["pos"], s["neu"], s["neg"]
            vader_compound = s["compound"]
            lower = text.lower()
            for term, delta in FINANCE_LEXICON.items():
                if term in lower:
                    vader_compound += delta
            vader_compound = max(-1.0, min(1.0, vader_compound))
        # Loughran-McDonald component.
        try:
            from .sentiment_lm import lm_counts, lm_score
            lm_counts_d = lm_counts(text)
            lm_pol = lm_score(text)
        except ImportError:
            lm_counts_d = {"unc": 0, "lit": 0}
            lm_pol = 0.0
        # Blend: lean on LM only when the text has finance content
        # (i.e. either pos or neg LM hits). Tweets with zero LM hits
        # default to pure VADER.
        lm_hits = lm_counts_d.get("pos", 0) + lm_counts_d.get("neg", 0)
        if lm_hits == 0:
            compound = vader_compound
        else:
            compound = (1.0 - self.lm_blend) * vader_compound + self.lm_blend * lm_pol
        compound = max(-1.0, min(1.0, compound))
        if compound >= 0.20:
            label = "bullish"
        elif compound <= -0.20:
            label = "bearish"
        else:
            label = "neutral"
        return SentimentScore(
            compound=compound, pos=pos, neu=neu, neg=neg, label=label,
            lm_score=lm_pol,
            lm_uncertainty=lm_counts_d.get("unc", 0),
            lm_litigious=lm_counts_d.get("lit", 0),
        )
