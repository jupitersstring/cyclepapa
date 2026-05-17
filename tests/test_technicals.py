"""Tests for the technical-analysis primitives.

We exercise the math without hitting yfinance.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from social_arb.technicals import hma, sma, to_weekly, wma


class TechnicalsTest(unittest.TestCase):
    def test_wma_matches_known_value(self) -> None:
        # WMA(3) of [1,2,3] with weights (1,2,3)/6 = (1+4+9)/6 = 14/6
        s = pd.Series([1.0, 2.0, 3.0])
        out = wma(s, 3)
        self.assertAlmostEqual(float(out.iloc[-1]), 14.0 / 6.0, places=6)

    def test_hma_reduces_lag_vs_sma(self) -> None:
        # Step input -- HMA should track the step faster than SMA.
        s = pd.Series([0.0] * 20 + [10.0] * 20)
        h = hma(s, 9)
        m = sma(s, 9)
        # 5 bars after the step, HMA should be closer to 10 than SMA.
        idx = 20 + 5
        self.assertGreater(float(h.iloc[idx]), float(m.iloc[idx]))

    def test_to_weekly_resamples_to_friday(self) -> None:
        idx = pd.date_range("2024-01-01", periods=30, freq="D")
        s = pd.Series(np.arange(30, dtype=float), index=idx)
        w = to_weekly(s)
        # All resulting timestamps are Fridays.
        self.assertTrue((w.index.dayofweek == 4).all())
        # Number of weekly bars should be ~30/7 = 4-5.
        self.assertIn(len(w), {4, 5})


if __name__ == "__main__":
    unittest.main()
