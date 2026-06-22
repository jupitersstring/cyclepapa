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
    Confidence,
    IbkrShortRow,
    SqueezeClass,
    SqueezeMetrics,
    _band_score,
    assess,
    detect_bearish_convergence,
    detect_squeeze_fuel,
    from_ibkr_file,
    parse_ibkr_shortable_text,
    utilization_from_loan,
)


IBKR_SAMPLE = """#BOF|usa|2024.05.01|22:15:38
SYM|CUR|NAME|CON|ISIN|REBATERATE|FEERATE|AVAILABLE|
AAPL|USD|APPLE INC|265598|XXXXXXX1005|4.5000|0.2500|>10000000|
GME|USD|GAMESTOP CORP-CLASS A|321524569|XXXXXXX1099|-12.5000|18.0000|350000|
TINY|USD|TINY HARD TO BORROW CORP|999999|XXXXXXX9999|-30.0000|33.0000|0|
WEIRD|USD|MISSING FEE CORP|111|XXXXXXX1111|||500|

GARBAGE_NO_PIPES_HERE
#EOF|5
"""


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

    def test_unavailable_when_no_util_and_no_fee(self):
        # SI present but neither utilization nor fee -> detector cannot run at all.
        r = detect_bearish_convergence(SqueezeMetrics(short_interest_pct_float=22.0))
        self.assertFalse(r.triggered)
        self.assertEqual(r.mode, "unavailable")

    def test_strict_mode_uses_utilization(self):
        r = detect_bearish_convergence(
            SqueezeMetrics(short_interest_pct_float=22.0, utilization_pct=38.0, borrow_fee_pct=0.9)
        )
        self.assertEqual(r.mode, "strict")

    def test_proxy_mode_without_utilization(self):
        # Cheap fee, no utilization -> proxy still fires (cheap borrow => ample supply).
        r = detect_bearish_convergence(SqueezeMetrics(short_interest_pct_float=20.0, borrow_fee_pct=0.8))
        self.assertTrue(r.triggered)
        self.assertEqual(r.mode, "proxy")


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

    def test_headline_only_is_capped_to_watch_at_low_confidence(self):
        # SI% only (no fee, no util): high SI alone must NOT be promoted to a
        # squeeze call. Capped at WATCH, LOW confidence.
        m = SqueezeMetrics(
            ticker="BLIND", short_interest_pct_float=31.0, days_to_cover=7.0, source="yfinance",
        )
        a = assess(m)
        self.assertEqual(a.confidence, Confidence.LOW)
        self.assertEqual(a.classification, SqueezeClass.WATCH)
        self.assertLess(a.coverage, 0.6)
        self.assertTrue(any("No utilization" in n for n in a.notes))
        self.assertTrue(any("Capped at WATCH" in n for n in a.notes))

    def test_insufficient_data_only_when_nothing_scorable(self):
        a = assess(SqueezeMetrics(ticker="EMPTY"))
        self.assertEqual(a.classification, SqueezeClass.INSUFFICIENT_DATA)
        self.assertIsNone(a.composite_score)

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


class TestDegradedMode(unittest.TestCase):
    """Behaviour when utilization (and maybe fee) are unavailable — the
    'build without IBKR' regime."""

    def test_confidence_high_when_utilization_present(self):
        a = assess(SqueezeMetrics(short_interest_pct_float=12.0, utilization_pct=88.0, borrow_fee_pct=9.0))
        self.assertEqual(a.confidence, Confidence.HIGH)

    def test_confidence_medium_when_only_fee(self):
        a = assess(SqueezeMetrics(short_interest_pct_float=12.0, borrow_fee_pct=9.0))
        self.assertEqual(a.confidence, Confidence.MEDIUM)

    def test_confidence_low_when_only_si(self):
        a = assess(SqueezeMetrics(short_interest_pct_float=12.0))
        self.assertEqual(a.confidence, Confidence.LOW)

    def test_squeeze_fuel_proxy_reaches_call_at_medium(self):
        # Hot, rising fee, elevated SI, but no utilization -> proxy fuel, MEDIUM.
        m = SqueezeMetrics(short_interest_pct_float=26.0, borrow_fee_pct=28.0, borrow_fee_trend_pct_pts=9.0)
        r = detect_squeeze_fuel(m)
        self.assertTrue(r.triggered)
        self.assertEqual(r.mode, "proxy")
        a = assess(m)
        self.assertEqual(a.classification, SqueezeClass.SQUEEZE_FUEL)
        self.assertEqual(a.confidence, Confidence.MEDIUM)

    def test_bearish_proxy_overrides_at_medium(self):
        m = SqueezeMetrics(short_interest_pct_float=20.0, borrow_fee_pct=0.8)
        a = assess(m)
        self.assertEqual(a.classification, SqueezeClass.GENUINELY_SHORT)
        self.assertEqual(a.confidence, Confidence.MEDIUM)

    def test_squeeze_fuel_unavailable_without_si(self):
        r = detect_squeeze_fuel(SqueezeMetrics(utilization_pct=95.0, borrow_fee_pct=30.0))
        self.assertEqual(r.mode, "unavailable")
        self.assertFalse(r.triggered)


class TestUtilizationFromLoan(unittest.TestCase):
    def test_basic_ratio(self):
        self.assertAlmostEqual(utilization_from_loan(90.0, 100.0), 90.0)
        self.assertAlmostEqual(utilization_from_loan(1_000_000, 4_000_000), 25.0)

    def test_zero_or_negative_denominator_returns_none(self):
        self.assertIsNone(utilization_from_loan(10.0, 0.0))
        self.assertIsNone(utilization_from_loan(10.0, -5.0))


class TestIbkrParser(unittest.TestCase):
    def setUp(self):
        self.rows = parse_ibkr_shortable_text(IBKR_SAMPLE)

    def test_skips_comments_header_and_garbage(self):
        self.assertEqual(set(self.rows), {"AAPL", "GME", "TINY", "WEIRD"})

    def test_returns_ibkr_short_row(self):
        self.assertIsInstance(self.rows["GME"], IbkrShortRow)

    def test_fee_and_rebate_parsed(self):
        self.assertAlmostEqual(self.rows["GME"].fee_rate_pct, 18.0)
        self.assertAlmostEqual(self.rows["GME"].rebate_rate_pct, -12.5)
        self.assertAlmostEqual(self.rows["AAPL"].fee_rate_pct, 0.25)

    def test_trailing_pipe_does_not_eat_available(self):
        # With the trailing '|', a naive split would put '' last; AVAILABLE must survive.
        self.assertAlmostEqual(self.rows["GME"].available, 350000.0)

    def test_greater_than_availability(self):
        self.assertAlmostEqual(self.rows["AAPL"].available, 10000000.0)
        self.assertEqual(self.rows["AAPL"].available_raw, ">10000000")

    def test_zero_availability(self):
        self.assertEqual(self.rows["TINY"].available, 0.0)

    def test_missing_fee_is_none_not_crash(self):
        self.assertIsNone(self.rows["WEIRD"].fee_rate_pct)
        self.assertAlmostEqual(self.rows["WEIRD"].available, 500.0)

    def test_bof_timestamp_captured(self):
        self.assertEqual(self.rows["GME"].as_of, "2024.05.01 22:15:38")

    def test_from_ibkr_file_builds_metrics(self):
        m = from_ibkr_file("gme", text=IBKR_SAMPLE, short_interest_pct_float=24.0, days_to_cover=4.0)
        self.assertEqual(m.ticker, "GME")
        self.assertAlmostEqual(m.borrow_fee_pct, 18.0)
        self.assertAlmostEqual(m.shortable_shares_available, 350000.0)
        self.assertEqual(m.source, "ibkr_file")
        self.assertIsNone(m.utilization_pct)  # not in the file

    def test_from_ibkr_file_then_assess_is_medium_squeeze_fuel(self):
        m = from_ibkr_file("GME", text=IBKR_SAMPLE, short_interest_pct_float=24.0)
        a = assess(m)
        self.assertEqual(a.confidence, Confidence.MEDIUM)
        self.assertEqual(a.classification, SqueezeClass.SQUEEZE_FUEL)

    def test_zero_shortable_adds_tightness_note(self):
        a = assess(from_ibkr_file("TINY", text=IBKR_SAMPLE))
        self.assertTrue(any("0 shortable shares" in n for n in a.notes))

    def test_missing_ticker_raises_keyerror(self):
        with self.assertRaises(KeyError):
            from_ibkr_file("NOPE", text=IBKR_SAMPLE)


if __name__ == "__main__":
    unittest.main(verbosity=2)
