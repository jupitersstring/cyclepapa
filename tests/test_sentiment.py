"""Sentiment-scoring unit tests.

Skipped automatically when vaderSentiment isn't installed.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from social_arb.sentiment import SentimentScorer


class SentimentTest(unittest.TestCase):
    def setUp(self) -> None:
        self.scorer = SentimentScorer()
        if self.scorer._vader is None:
            self.skipTest("vaderSentiment not installed")

    def test_bullish_text(self) -> None:
        s = self.scorer.score("Earnings beat across the board, raised guidance, calls printing.")
        self.assertEqual(s.label, "bullish")
        self.assertGreater(s.compound, 0.2)

    def test_bearish_text(self) -> None:
        s = self.scorer.score("Awful miss, guided down hard, puts paid off, im a bagholder")
        self.assertEqual(s.label, "bearish")
        self.assertLess(s.compound, -0.2)

    def test_neutral_text(self) -> None:
        s = self.scorer.score("The company reported their quarterly results today.")
        self.assertIn(s.label, {"neutral", "bullish"})  # quarterly results is neutral or mildly +


if __name__ == "__main__":
    unittest.main()
