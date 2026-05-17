"""Anomaly-detection unit tests."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from social_arb.anomaly import AnomalyParams, breakout_ratio, ewma_zscore, joint_signal


class AnomalyTest(unittest.TestCase):
    def test_ewma_zscore_flags_spike(self) -> None:
        rng = pd.date_range("2024-01-01", periods=120, freq="D")
        rs = np.random.default_rng(42)
        # Stationary baseline + a single huge spike on day 90.
        counts = pd.Series(rs.poisson(5, size=120), index=rng).astype(float)
        counts.iloc[90] = 1000
        out = ewma_zscore(counts, AnomalyParams(halflife_days=14, z_thresh=3.0, min_periods=7))
        self.assertTrue(out["anomaly"].iloc[90])
        # Should NOT flag random baseline days en masse.
        self.assertLess(out["anomaly"].iloc[:80].sum(), 5)

    def test_joint_signal_requires_both(self) -> None:
        rng = pd.date_range("2024-01-01", periods=120, freq="D")
        rs = np.random.default_rng(7)
        mentions = pd.Series(rs.poisson(5, size=120), index=rng).astype(float)
        sentiment = pd.Series(rs.normal(0, 0.05, size=120), index=rng)
        # Only mention spike (no sentiment shift) -- should not fire joint signal.
        mentions.iloc[80] = 500
        out = joint_signal(mentions, sentiment, z_mentions=2.0, z_sent=1.5)
        self.assertFalse(out["signal"].iloc[80])
        # Add sentiment shift on same day -- now joint should fire.
        sentiment.iloc[80] = 0.9
        out2 = joint_signal(mentions, sentiment, z_mentions=2.0, z_sent=1.5)
        self.assertTrue(out2["signal"].iloc[80])

    def test_breakout_ratio_above_two(self) -> None:
        rng = pd.date_range("2024-01-01", periods=120, freq="D")
        s = pd.Series([10.0] * 90 + [50.0] * 30, index=rng)
        ratio = breakout_ratio(s, short=7, long=90)
        self.assertGreater(ratio.iloc[-1], 2.0)


if __name__ == "__main__":
    unittest.main()
