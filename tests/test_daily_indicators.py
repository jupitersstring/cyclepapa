"""Unit tests for the daily indicator stack."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from social_arb.technicals_daily import (
    daily_signals_for, detect_gaps, rsi_wilder, volume_zscore,
)


class DailyIndicatorTest(unittest.TestCase):
    def test_rsi_bounds_and_oversold(self) -> None:
        # Pure downtrend -> RSI should saturate near 0.
        idx = pd.date_range("2024-01-01", periods=60, freq="D")
        s = pd.Series(np.linspace(100, 50, 60), index=idx)
        r = rsi_wilder(s, 14)
        last = float(r.dropna().iloc[-1])
        self.assertGreaterEqual(last, 0.0)
        self.assertLess(last, 30.0)

    def test_rsi_overbought_uptrend(self) -> None:
        idx = pd.date_range("2024-01-01", periods=60, freq="D")
        s = pd.Series(np.linspace(50, 100, 60), index=idx)
        r = rsi_wilder(s, 14)
        last = float(r.dropna().iloc[-1])
        self.assertGreater(last, 70.0)
        self.assertLessEqual(last, 100.0)

    def test_volume_zscore_spike(self) -> None:
        rs = np.random.default_rng(0)
        v = pd.Series(rs.poisson(1_000_000, size=60))
        v.iloc[-1] = 20_000_000  # extreme spike
        z = volume_zscore(v, 30)
        self.assertGreater(float(z.iloc[-1]), 3.0)

    def test_gap_detection(self) -> None:
        c = pd.Series([100.0, 101.0, 100.5, 110.0, 110.5])
        gaps = detect_gaps(c, threshold_pct=5.0)
        self.assertTrue(bool(gaps.iloc[3]))
        self.assertFalse(bool(gaps.iloc[1]))

    def test_daily_signals_shape(self) -> None:
        idx = pd.date_range("2023-01-01", periods=260, freq="D")
        c = pd.Series(np.linspace(50, 100, 260), index=idx)
        v = pd.Series(np.ones(260) * 1e6, index=idx)
        df = daily_signals_for(c, v)
        self.assertIn("rsi_14", df.columns)
        self.assertIn("sma_200", df.columns)
        self.assertIn("vol_z_30", df.columns)
        self.assertIn("gap", df.columns)


if __name__ == "__main__":
    unittest.main()
