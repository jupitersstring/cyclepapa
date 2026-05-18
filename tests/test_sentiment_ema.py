"""Sentiment-EMA momentum unit test."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


class SentimentEMATest(unittest.TestCase):
    def test_synthetic_uptrend_triggers_cross(self) -> None:
        # We test the same arithmetic the scan uses, locally, without needing
        # a populated DB.
        n = 80
        idx = pd.date_range("2024-01-01", periods=n, freq="D")
        # First 40 days flat at -0.2, next 40 days monotonically rising to +0.5.
        sent = pd.Series(
            np.concatenate([np.full(40, -0.2), np.linspace(-0.2, 0.5, 40)]),
            index=idx,
        )
        ema_s = sent.ewm(span=10, adjust=False, min_periods=5).mean()
        ema_l = sent.ewm(span=25, adjust=False, min_periods=12).mean()
        spread = ema_s - ema_l
        cross_up = (spread > 0) & (spread.shift(1) <= 0)
        # At least one bullish cross should fire in the uptrend window.
        self.assertTrue(bool(cross_up.iloc[40:].any()))
        # Final spread should be positive (short EMA leading long).
        self.assertGreater(float(spread.iloc[-1]), 0.0)


if __name__ == "__main__":
    unittest.main()
