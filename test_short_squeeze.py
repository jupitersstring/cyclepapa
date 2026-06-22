"""
Tests for short_squeeze.py — pure stdlib `unittest` (no pytest needed).

Run:
    python3 -m unittest test_short_squeeze -v
    python3 test_short_squeeze.py
"""

import math
import unittest

from short_squeeze import (
    BORROW_FEE_MEAN_PCT,
    BORROW_FEE_MEDIAN_PCT,
    BORROW_FEE_P95_PCT,
    SCORE_RULES,
    SqueezeClass,
    SqueezeMetrics,
    _band_score,
    assess,
    detect_bearish_convergence,
    detect_squeeze_fuel,
)


class TestReferenceConstants(unittest.TestCase):
    """The numbers we hard-code must match Schultz (2024)."""

    def test_schultz_borrow_fee_distribution(self):
        self.assertAlmostEqual(BORROW_FEE_MEAN_PCT, 2.673, places=3)
        self.assertAlmostEqual(BORROW_FEE_MEDIAN_PCT, 0.375, places=3)
        self.assertAlmostEqual(BORROW_FEE_P95_PCT, 11.0, places=3)

    def test_mean_far_above_median(self):
        # Fat right tail of "special" names: mean must dwarf the median.
        self.assertGreater(BORROW_FEE_MEAN_PCT, 5 * BORROW_FEE_MEDIAN_PCT)


class TestBandScore(unittest.TestCase):
    def test_missing_value_returns_none(self):
        self.assertIsNone(_band_score(None, [(1.0, 10.0), (math.inf, 100.0)]))
        self.assertIsNone(_band_score(float("nan"), [(1.0, 10.0), (math.inf, 100.0)]))

    def test_boundaries_are_inclusive_on_upper(self):
        bands = [(25.0, 0.0), (50.0, 15.0), (math.inf, 100.0)]
        self.assertEqual(_band_score(25.0, bands), 0.0)   # exactly on bound -> that band
        self.assertEqual(_band_score(25.01, bands), 15.0)  # just over -> next band
        self.assertEqual(_band_score(50.0, bands), 15.0)
        self.assertEqual(_band_score(999.0, bands), 100.0)  # top band

    def test_zero_and_negative(self):
        bands = [(25.0, 0.0), (math.inf, 100.0)]
        self.assertEqual(_band_score(0.0, bands), 0.0)


class TestScoreRules(unittest.TestCase):
    def test_exactly_three_primary_rules_named_as_specified(self):
        self.assertEqual(
            set(SCORE_RULES.keys()),
            {"d33_short_interest_pct", "d34_utilization_pct", "d35_borrow_rate_pct"},
        )

    def test_weights_sum_to_one(self):
        self.assertAlmostEqual(sum(r.weight for r in SCORE_RULES.values()), 1.0, places=9)

    def test_utilization_is_dominant_weight(self):
        # Schultz: utilization is THE predictor -> it must carry the most weight.
        w = {rid: r.weight for rid, r in SCORE_RULES.items()}
        self.assertGreater(w["d34_utilization_pct"], w["d35_borrow_rate_pct"])
        self.assertGreater(w["d35_borrow_rate_pct"], w["d33_short_interest_pct"])
        self.assertEqual(max(w, key=w.get), "d34_utilization_pct")

    def test_utilization_band_monotonic_and_schultz_anchored(self):
        rule = SCORE_RULES["d34_utilization_pct"]
        s_low = rule.score(SqueezeMetrics(utilization_pct=20.0))    # <=25 -> 0
        s_mid = rule.score(SqueezeMetrics(utilization_pct=80.0))
        s_hi = rule.score(SqueezeMetrics(utilization_pct=96.0))     # >95 -> 100
        self.assertEqual(s_low, 0.0)
        self.assertEqual(s_hi, 100.0)
        self.assertLess(s_low, s_mid)
        self.assertLess(s_mid, s_hi)

    def test_borrow_fee_band_anchored_to_percentiles(self):
        rule = SCORE_RULES["d35_borrow_rate_pct"]
        # GC floor (~0.375%) should score 0; a fee above the p95 (~11%) should be high.
        self.assertEqual(rule.score(SqueezeMetrics(borrow_fee_pct=BORROW_FEE_MEDIAN_PCT)), 0.0)
        self.assertGreaterEqual(rule.score(SqueezeMetrics(borrow_fee_pct=12.0)), 80.0)

    def test_short_interest_band(self):
        rule = SCORE_RULES["d33_short_interest_pct"]
        self.assertEqual(rule.score(SqueezeMetrics(short_interest_pct_float=2.0)), 0.0)
        self.assertEqual(rule.score(SqueezeMetrics(short_interest_pct_float=140.0)), 100.0)

    def test_rule_returns_none_when_metric_absent(self):
        self.assertIsNone(SCORE_RULES["d34_utilization_pct"].score(SqueezeMetrics()))


class TestBearishConvergence(unittest.TestCase):
    def test_triggers_on_high_si_low_util_low_fee(self):
        m = SqueezeMetrics(short_interest_pct_float=22.0, utilization_pct=38.0, borrow_fee_pct=0.9)
        r = detect_bearish_convergence(m)
        self.assertTrue(r.triggered)
        self.assertTrue(bool(r))  # __bool__

    def test_does_not_trigger_when_utilization_high(self):
        # Same high SI, but supply is tight -> this is squeeze territory, not bearish.
        m = SqueezeMetrics(short_interest_pct_float=22.0, utilization_pct=92.0, borrow_fee_pct=0.9)
        self.assertFalse(detect_bearish_convergence(m).triggered)

    def test_does_not_trigger_when_fee_high(self):
        m = SqueezeMetrics(short_interest_pct_float=22.0, utilization_pct=38.0, borrow_fee_pct=8.0)
        self.assertFalse(detect_bearish_convergence(m).triggered)

    def test_does_not_trigger_when_si_low(self):
        m = SqueezeMetrics(short_interest_pct_float=4.0, utilization_pct=38.0, borrow_fee_pct=0.9)
        self.assertFalse(detect_bearish_convergence(m).triggered)

    def test_boundaries_are_strict(self):
        # Exactly on the thresholds (SI=10, util=50, fee=3) must NOT trigger.
        m = SqueezeMetrics(short_interest_pct_float=10.0, utilization_pct=50.0, borrow_fee_pct=3.0)
        self.assertFalse(detect_bearish_convergence(m).triggered)

    def test_reports_missing_inputs(self):
        r = detect_bearish_convergence(SqueezeMetrics(short_interest_pct_float=22.0))
        self.assertFalse(r.triggered)
        self.assertIn("utilization_pct", r.missing)
        self.assertIn("borrow_fee_pct", r.missing)


class TestSqueezeFuel(unittest.TestCase):
    def test_triggers_on_tight_expensive_crowded(self):
        m = SqueezeMetrics(short_interest_pct_float=28.0, utilization_pct=98.0, borrow_fee_pct=42.0)
        self.assertTrue(detect_squeeze_fuel(m).triggered)

    def test_fee_trend_substitutes_for_level(self):
        # Fee only 4% (below the 10% level bar) but RISING -> still fuel.
        m = SqueezeMetrics(
            short_interest_pct_float=15.0, utilization_pct=90.0,
            borrow_fee_pct=4.0, borrow_fee_trend_pct_pts=3.0,
        )
        self.assertTrue(detect_squeeze_fuel(m).triggered)

    def test_profitable_short_vetoes_squeeze(self):
        # S3: a short that's still in profit can't be forced. Price below entry.
        m = SqueezeMetrics(
            short_interest_pct_float=28.0, utilization_pct=98.0, borrow_fee_pct=42.0,
            price_vs_short_cost_basis_pct=-20.0,
        )
        self.assertFalse(detect_squeeze_fuel(m).triggered)

    def test_low_utilization_is_not_fuel(self):
        m = SqueezeMetrics(short_interest_pct_float=28.0, utilization_pct=60.0, borrow_fee_pct=42.0)
        self.assertFalse(detect_squeeze_fuel(m).triggered)


class TestAssess(unittest.TestCase):
    def test_squeeze_fuel_archetype(self):
        m = SqueezeMetrics(
            ticker="FUEL", short_interest_pct_float=28.0, utilization_pct=98.0,
            borrow_fee_pct=42.0, borrow_fee_trend_pct_pts=15.0,
            price_vs_short_cost_basis_pct=35.0,
        )
        a = assess(m)
        self.assertEqual(a.classification, SqueezeClass.SQUEEZE_FUEL)
        self.assertGreaterEqual(a.composite_score, 70.0)
        self.assertEqual(a.coverage, 1.0)

    def test_bearish_archetype_overrides_everything(self):
        m = SqueezeMetrics(
            ticker="BEAR", short_interest_pct_float=22.0, utilization_pct=38.0, borrow_fee_pct=0.9,
        )
        a = assess(m)
        self.assertEqual(a.classification, SqueezeClass.GENUINELY_SHORT)

    def test_general_collateral_is_low(self):
        m = SqueezeMetrics(
            ticker="MEH", short_interest_pct_float=3.0, utilization_pct=12.0, borrow_fee_pct=0.35,
        )
        a = assess(m)
        self.assertEqual(a.classification, SqueezeClass.LOW)
        self.assertEqual(a.composite_score, 0.0)

    def test_missing_utilization_is_insufficient_even_with_high_si(self):
        m = SqueezeMetrics(
            ticker="BLIND", short_interest_pct_float=31.0, days_to_cover=7.0, source="yfinance",
        )
        a = assess(m)
        self.assertEqual(a.classification, SqueezeClass.INSUFFICIENT_DATA)
        self.assertLess(a.coverage, 0.6)
        self.assertTrue(any("Utilization missing" in n for n in a.notes))

    def test_composite_is_weight_renormalised_over_available_rules(self):
        # Only utilization present: composite should equal the utilization sub-score,
        # not be diluted toward zero by the missing rules.
        m = SqueezeMetrics(utilization_pct=96.0)  # util sub-score == 100
        a = assess(m)
        self.assertAlmostEqual(a.composite_score, 100.0, places=6)
        self.assertAlmostEqual(a.coverage, 0.50, places=6)

    def test_summary_is_stringable(self):
        a = assess(SqueezeMetrics(ticker="X", short_interest_pct_float=12.0,
                                  utilization_pct=88.0, borrow_fee_pct=9.0))
        self.assertIsInstance(a.summary(), str)
        self.assertIn("X", a.summary())


if __name__ == "__main__":
    unittest.main(verbosity=2)
