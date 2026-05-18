"""Loughran-McDonald lexicon unit tests."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from social_arb.sentiment_lm import (
    LM_NEGATIVE, LM_POSITIVE, lm_counts, lm_intensity, lm_score,
)


class LoughranMcDonaldTest(unittest.TestCase):
    def test_positive_text(self) -> None:
        text = "We exceeded guidance and grew earnings to a record. Strong margin improvement."
        c = lm_counts(text)
        self.assertGreater(c["pos"], 0)
        self.assertGreater(lm_score(text), 0.2)

    def test_negative_text(self) -> None:
        text = "Earnings missed badly, we are facing a significant lawsuit and material impairment."
        c = lm_counts(text)
        self.assertGreater(c["neg"], c["pos"])
        self.assertLess(lm_score(text), -0.2)

    def test_uncertainty_litigious(self) -> None:
        text = "The plaintiff's lawsuit could possibly result in a substantial settlement; "\
               "outcome is uncertain."
        c = lm_counts(text)
        self.assertGreater(c["lit"], 0)
        self.assertGreater(c["unc"], 0)

    def test_neutral_text_low_intensity(self) -> None:
        # Pure consumer-product description with no LM hits.
        text = "The new product comes in five colors and ships next week."
        i = lm_intensity(text)
        self.assertLess(i, 30.0)  # very low hit rate per 1k tokens

    def test_lexicon_size(self) -> None:
        self.assertGreater(len(LM_POSITIVE), 80)
        self.assertGreater(len(LM_NEGATIVE), 400)


if __name__ == "__main__":
    unittest.main()
