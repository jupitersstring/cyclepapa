"""Sentiment scoring.

Uses VADER (free, offline, MIT-licensed) as the workhorse and overlays a
small finance-specific lexicon: VADER mis-handles a number of finance
idioms ("beat", "miss", "guided down", "tendies", "puts"). The overlay
adjusts the compound score by a bounded delta.

For higher-quality scoring users can drop FinBERT in -- the public API is
the same: `score(text) -> SentimentScore`.
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


class SentimentScorer:
    def __init__(self) -> None:
        try:
            from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
            self._vader = SentimentIntensityAnalyzer()
        except ImportError:
            log.warning("vaderSentiment not installed; sentiment will be neutral")
            self._vader = None

    def score(self, text: str) -> SentimentScore:
        if not text:
            return SentimentScore(0.0, 0.0, 1.0, 0.0, "neutral")
        if self._vader is None:
            return SentimentScore(0.0, 0.0, 1.0, 0.0, "neutral")
        s = self._vader.polarity_scores(text)
        compound = s["compound"]
        lower = text.lower()
        for term, delta in FINANCE_LEXICON.items():
            if term in lower:
                compound += delta
        compound = max(-1.0, min(1.0, compound))
        if compound >= 0.20:
            label = "bullish"
        elif compound <= -0.20:
            label = "bearish"
        else:
            label = "neutral"
        return SentimentScore(compound, s["pos"], s["neu"], s["neg"], label)
