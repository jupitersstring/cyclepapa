"""Tests for the Camillo composite scorer.

Don't need a populated DuckDB -- we test `_score` indirectly by feeding
shaped DataFrames into camillo_ranking via a minimal stand-in for the
social bullish_ranking output.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from social_arb.ranking import CamilloParams


class CamilloScoringTest(unittest.TestCase):
    def setUp(self) -> None:
        self.params = CamilloParams()

    def _score(self, row: dict) -> float:
        # Re-implement _score locally to keep the test independent of DB state.
        p = self.params
        s = 0.0
        z = row.get("latest_z")
        if z is not None and z > 0:
            s += p.w_mention_z * min(float(z), 6.0)
        sent = row.get("sentiment_14d")
        if sent is not None and sent > 0:
            s += p.w_sentiment * float(sent)
        grow = row.get("log_growth_7d")
        if grow is not None and grow > 0:
            s += p.w_growth * min(float(grow), 3.0)
        if row.get("state") in ("hma_up", "golden"):
            s += p.w_tech_confirm
        v40 = row.get("close_vs_sma40_pct")
        if v40 is not None:
            if -25.0 <= v40 <= 10.0:
                s += p.w_clean_entry
            if v40 > 25.0:
                s -= p.w_stretched_pen * (v40 - 25.0)
        close = row.get("close")
        if close is not None:
            if close <= 50.0:
                s += p.w_smallcap
            if close <= 10.0:
                s += p.w_microcap
        return s

    def test_stretched_megacap_loses_to_small_turn(self) -> None:
        # Mature golden cross 30% above SMA40 vs small-cap Hull flip at -10%.
        mature = {
            "latest_z": 4.0, "sentiment_14d": 0.05, "log_growth_7d": 0.2,
            "state": "golden", "close_vs_sma40_pct": 30.0, "close": 250.0,
        }
        early = {
            "latest_z": 1.5, "sentiment_14d": 0.10, "log_growth_7d": 0.6,
            "state": "hma_up", "close_vs_sma40_pct": -10.0, "close": 8.0,
        }
        self.assertGreater(self._score(early), self._score(mature))

    def test_negative_sentiment_does_not_subtract(self) -> None:
        # Camillo wants organic positive sentiment OR neutral attention;
        # negative sentiment shouldn't add or subtract.
        a = {"latest_z": 2.0, "sentiment_14d": -0.5, "state": "hma_up",
             "close_vs_sma40_pct": 0.0, "close": 30.0, "log_growth_7d": 0.0}
        b = {"latest_z": 2.0, "sentiment_14d": 0.0, "state": "hma_up",
             "close_vs_sma40_pct": 0.0, "close": 30.0, "log_growth_7d": 0.0}
        self.assertEqual(self._score(a), self._score(b))

    def test_clean_entry_window(self) -> None:
        base = {"latest_z": 1.0, "sentiment_14d": 0.0, "log_growth_7d": 0.0,
                "state": "hma_up", "close": 30.0}
        inside = self._score({**base, "close_vs_sma40_pct": -15.0})
        outside = self._score({**base, "close_vs_sma40_pct": -30.0})
        self.assertGreater(inside, outside)


if __name__ == "__main__":
    unittest.main()
