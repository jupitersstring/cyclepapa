"""Phase 3 calibration tests: BH correction + event-study primitives."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from social_arb.calibration import (
    benjamini_hochberg, evaluate_events, summarize_horizon,
)


class BenjaminiHochbergTest(unittest.TestCase):
    def test_monotone_in_p_value(self) -> None:
        """BH q-values are non-decreasing in sorted p-value order."""
        p = np.array([0.001, 0.01, 0.03, 0.05, 0.2, 0.5, 0.9])
        q = benjamini_hochberg(p, fdr=0.10)
        sorted_q = q[np.argsort(p)]
        self.assertTrue(all(sorted_q[i] <= sorted_q[i + 1] for i in range(len(sorted_q) - 1)))

    def test_q_bounded_in_unit_interval(self) -> None:
        p = np.array([0.001, 0.5, 0.99, 1.0])
        q = benjamini_hochberg(p)
        self.assertTrue((q >= 0).all() and (q <= 1).all())

    def test_known_bh_example(self) -> None:
        """Worked example from Benjamini-Hochberg (1995).
        p = [0.0001, 0.0004, 0.0019, 0.0095, 0.0201, 0.0278, 0.0298,
             0.0344, 0.0459, 0.3240, 0.4262, 0.5719, 0.6528, 0.7590, 1.000]
        At FDR=0.05, BH rejects the first 4. Verify q[0..3] are smallest."""
        p = np.array([0.0001, 0.0004, 0.0019, 0.0095, 0.0201, 0.0278, 0.0298,
                      0.0344, 0.0459, 0.3240, 0.4262, 0.5719, 0.6528, 0.7590, 1.000])
        q = benjamini_hochberg(p, fdr=0.05)
        rejected = q <= 0.05
        # First 4 should be clearly rejected; tail should not.
        self.assertTrue(rejected[0:4].all())
        self.assertFalse(rejected[10:].any())


class SummarizeHorizonTest(unittest.TestCase):
    def test_positive_drift_reports_positive_mean(self) -> None:
        cars = pd.Series([0.01, 0.02, 0.03, 0.01, 0.04, 0.02])
        s = summarize_horizon(cars, n_trials=1)
        self.assertGreater(s["mean_car"], 0)
        self.assertGreater(s["hit_rate"], 0.9)
        self.assertGreater(s["t_stat"], 0)
        self.assertLess(s["p_value"], 0.05)

    def test_empty_returns_nan_safe(self) -> None:
        s = summarize_horizon(pd.Series(dtype=float), n_trials=1)
        self.assertEqual(s["n"], 0)
        self.assertTrue(np.isnan(s["mean_car"]))


class EvaluateEventsTest(unittest.TestCase):
    def test_horizon_lookup_is_forward_only(self) -> None:
        """Forward CAR must use the day AFTER event_date as entry, never
        the same day (look-ahead-bias guard)."""
        idx = pd.date_range("2024-01-01", periods=30, freq="B")
        # Construct a series where price doubles on the event day so any
        # look-ahead would inflate CAR by 100%. The event-day price is
        # NOT supposed to be the entry.
        px = pd.Series(np.ones(30) * 100.0, index=idx)
        px.iloc[5] = 200.0  # spike on event day
        px.iloc[6:] = 100.0  # back to 100 next day
        prices = pd.DataFrame({"AAA": px})
        bench = pd.Series(np.ones(30) * 100.0, index=idx, name="SPY")
        events = pd.DataFrame([{"date": idx[5], "ticker": "AAA"}])
        cars = evaluate_events(events, prices, bench, forward_days=(5,))
        # Entry should be idx[6] (the day AFTER event) at price 100;
        # exit at idx[6+5] = idx[11] also at 100 -> car = 0, NOT 0.5.
        self.assertEqual(list(cars[5]), [0.0])


if __name__ == "__main__":
    unittest.main()
