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
    SqueezeConfig,
    SqueezeMetrics,
    Snapshot,
    _band_score,
    assess,
    detect_bearish_convergence,
    detect_coiled_spring,
    detect_squeeze_fuel,
    from_ibkr_file,
    metrics_from_timeseries,
    parse_finra_short_interest,
    parse_ibkr_shortable_text,
    rank_candidates,
    report,
    screen_panel,
    screen_universe,
    to_csv,
    utilization_from_loan,
)


FINRA_CSV = (
    "issueSymbolIdentifier,settlementDate,issueName,currentShortShareNumber,"
    "previousShortShareNumber,averageDailyVolumeQuantity,daysToCoverQuantity\n"
    "GME,20260615,GAMESTOP CORP,45000000,40000000,7000000,6.43\n"
    "ZZZ,20260615,ZERO VOL CO,1000,1000,N/A,N/A\n"
)
FINRA_PIPE = (
    "issueSymbolIdentifier|currentShortShareNumber|previousShortShareNumber|daysToCoverQuantity\n"
    "AAA|2,500,000|2,000,000|3.50\n"
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


class TestInteractionGate(unittest.TestCase):
    def test_cheap_borrow_discounts_high_short_interest(self):
        # GRPN-like: 64.6% SI but only 1.5% fee -> structural must sink well below
        # the raw SI band (the whole point of interaction-awareness).
        a = assess(SqueezeMetrics("GRPN", short_interest_pct_float=64.6, borrow_fee_pct=1.5))
        self.assertLess(a.composite_score, 45)
        self.assertEqual(a.classification, SqueezeClass.GENUINELY_SHORT)

    def test_expensive_borrow_keeps_high_short_interest(self):
        # LCID-like: 33.6% SI with a 26.1% fee -> structural stays high.
        a = assess(SqueezeMetrics("LCID", short_interest_pct_float=33.6, borrow_fee_pct=26.1))
        self.assertGreaterEqual(a.composite_score, 85)
        self.assertEqual(a.classification, SqueezeClass.SQUEEZE_FUEL)

    def test_gate_can_be_disabled_via_config(self):
        m = SqueezeMetrics("GRPN", short_interest_pct_float=64.6, borrow_fee_pct=1.5)
        gated = assess(m).composite_score
        ungated = assess(m, SqueezeConfig(apply_interaction_gate=False)).composite_score
        self.assertGreater(ungated, gated)


class TestLayers(unittest.TestCase):
    def test_dynamics_from_rising_signals(self):
        m = SqueezeMetrics("X", short_interest_pct_float=20, borrow_fee_pct=12,
                            borrow_fee_trend_pct_pts=6, utilization_trend_pct_pts=12)
        self.assertGreaterEqual(assess(m).dynamics_score, 70)

    def test_dynamics_none_without_trends(self):
        self.assertIsNone(assess(SqueezeMetrics("X", short_interest_pct_float=20, borrow_fee_pct=12)).dynamics_score)

    def test_ignition_from_momentum_and_pain(self):
        m = SqueezeMetrics("X", short_interest_pct_float=20, borrow_fee_pct=12,
                            momentum_pct=20, price_vs_short_cost_basis_pct=40)
        self.assertGreaterEqual(assess(m).ignition_score, 80)

    def test_profitable_shorts_block_fuel(self):
        m = SqueezeMetrics("X", short_interest_pct_float=20, utilization_pct=95, borrow_fee_pct=20,
                           price_vs_short_cost_basis_pct=-25)
        self.assertFalse(assess(m).squeeze_fuel.triggered)

    def test_amplifier_low_float_and_high_dtc(self):
        base = assess(SqueezeMetrics("X", short_interest_pct_float=20, borrow_fee_pct=12)).amplifier
        amped = assess(SqueezeMetrics("X", short_interest_pct_float=20, borrow_fee_pct=12,
                                      days_to_cover=12, float_shares=8e6)).amplifier
        self.assertEqual(base, 1.0)
        self.assertAlmostEqual(amped, 1.25)  # +0.10 (DTC>10) + 0.15 (float<10M)

    def test_amplifier_is_capped(self):
        amp = assess(SqueezeMetrics("X", short_interest_pct_float=20, borrow_fee_pct=12,
                                    days_to_cover=99, float_shares=1e6),
                     SqueezeConfig(max_amplifier=1.2)).amplifier
        self.assertLessEqual(amp, 1.2)

    def test_full_stack_scores_above_structural_only(self):
        struct_only = assess(SqueezeMetrics("X", short_interest_pct_float=30, utilization_pct=92, borrow_fee_pct=15))
        self.assertEqual(struct_only.squeeze_score, struct_only.composite_score)
        full = assess(SqueezeMetrics("X", short_interest_pct_float=30, utilization_pct=92, borrow_fee_pct=15,
                                     borrow_fee_trend_pct_pts=8, momentum_pct=20,
                                     price_vs_short_cost_basis_pct=40, days_to_cover=12, float_shares=8e6))
        self.assertGreater(full.squeeze_score, full.composite_score)


class TestRankAndConfig(unittest.TestCase):
    def test_fuel_ranks_above_bearish(self):
        lcid = SqueezeMetrics("LCID", short_interest_pct_float=33.6, borrow_fee_pct=26.1)
        grpn = SqueezeMetrics("GRPN", short_interest_pct_float=64.6, borrow_fee_pct=1.5)
        ranked = rank_candidates([grpn, lcid])
        self.assertEqual(ranked[0].ticker, "LCID")
        self.assertEqual(ranked[0].classification, SqueezeClass.SQUEEZE_FUEL)
        self.assertEqual(ranked[-1].classification, SqueezeClass.GENUINELY_SHORT)

    def test_custom_cutoffs_change_classification(self):
        m = SqueezeMetrics("X", short_interest_pct_float=30, utilization_pct=80, borrow_fee_pct=5)
        order = {SqueezeClass.SQUEEZE_FUEL: 0, SqueezeClass.ELEVATED: 1, SqueezeClass.WATCH: 2,
                 SqueezeClass.GENUINELY_SHORT: 3, SqueezeClass.LOW: 4, SqueezeClass.INSUFFICIENT_DATA: 5}
        strict = assess(m, SqueezeConfig(elevated_score=99, watch_score=95))
        loose = assess(m, SqueezeConfig(elevated_score=10, watch_score=5))
        self.assertLessEqual(order[loose.classification], order[strict.classification])


class TestFinraParser(unittest.TestCase):
    def test_csv_header_driven(self):
        rows = parse_finra_short_interest(FINRA_CSV)
        self.assertEqual(set(rows), {"GME", "ZZZ"})
        self.assertEqual(rows["GME"].shares_short, 45000000)
        self.assertEqual(rows["GME"].shares_short_prior, 40000000)
        self.assertAlmostEqual(rows["GME"].days_to_cover, 6.43)
        self.assertEqual(rows["GME"].avg_daily_volume, 7000000)

    def test_na_becomes_none(self):
        rows = parse_finra_short_interest(FINRA_CSV)
        self.assertIsNone(rows["ZZZ"].days_to_cover)
        self.assertIsNone(rows["ZZZ"].avg_daily_volume)

    def test_pipe_delimiter_and_commas_in_numbers(self):
        rows = parse_finra_short_interest(FINRA_PIPE)
        self.assertEqual(rows["AAA"].shares_short, 2500000)  # thousands separators stripped
        self.assertAlmostEqual(rows["AAA"].days_to_cover, 3.5)


class TestScreenUniverse(unittest.TestCase):
    def test_merges_sources_and_computes_si_pct(self):
        ibkr = "#BOF|usa|2026.06.19|14:00:00\nGME|USD|GAMESTOP|1|X|-5|18.0|350000|\n"
        finra = ("issueSymbolIdentifier,currentShortShareNumber,previousShortShareNumber,daysToCoverQuantity\n"
                 "GME,45000000,40000000,6.43\n")
        ranked = screen_universe(ibkr_text=ibkr, finra_text=finra,
                                 float_by_symbol={"GME": 300e6}, reg_sho_symbols=["GME"])
        a = ranked[0]
        self.assertEqual(a.ticker, "GME")
        self.assertAlmostEqual(a.rule_scores["d33_short_interest_pct"], 40.0)  # 15% of float -> band 10-20
        self.assertEqual(a.constraint_score, 100.0)                            # on Reg SHO list
        self.assertEqual(a.classification, SqueezeClass.SQUEEZE_FUEL)

    def test_full_universe_is_the_union_of_sources(self):
        ibkr = "#BOF|usa|2026.06.19|14:00:00\nONLYIB|USD|X|1|X|-1|9.0|1000|\n"
        finra = "issueSymbolIdentifier,currentShortShareNumber,previousShortShareNumber\nONLYFINRA,5,4\n"
        ranked = screen_universe(ibkr_text=ibkr, finra_text=finra, float_by_symbol={"ONLYFLOAT": 1e6})
        self.assertEqual({a.ticker for a in ranked}, {"ONLYIB", "ONLYFINRA", "ONLYFLOAT"})


class TestLiteratureFeatures(unittest.TestCase):
    def test_reg_sho_and_low_inst_drive_constraint(self):
        a = assess(SqueezeMetrics("X", short_interest_pct_float=20, borrow_fee_pct=12,
                                  on_reg_sho_threshold=True, institutional_ownership_pct=10))
        self.assertEqual(a.constraint_score, 90.0)  # (100 reg-sho + 80 thin-inst) / 2
        self.assertTrue(any("Reg SHO" in n for n in a.notes))

    def test_high_institutional_ownership_zero_constraint(self):
        a = assess(SqueezeMetrics("X", short_interest_pct_float=20, borrow_fee_pct=12,
                                  institutional_ownership_pct=75))
        self.assertEqual(a.constraint_score, 0.0)

    def test_gamma_feeds_ignition(self):
        base = assess(SqueezeMetrics("X", short_interest_pct_float=20, borrow_fee_pct=12)).ignition_score
        gamma = assess(SqueezeMetrics("X", short_interest_pct_float=20, borrow_fee_pct=12,
                                      options_volume_vs_adv=7)).ignition_score
        self.assertIsNone(base)
        self.assertGreaterEqual(gamma, 80)

    def test_volume_attention_feeds_ignition(self):
        att = assess(SqueezeMetrics("X", short_interest_pct_float=20, borrow_fee_pct=12,
                                    volume_vs_avg=6)).ignition_score
        self.assertGreaterEqual(att, 80)

    def test_fee_only_without_crowded_short_is_capped(self):
        # Extreme fee, but no SI and no utilization -> can't confirm a crowded short
        # (likely an illiquid microcap) -> capped at WATCH, not ELEVATED.
        a = assess(SqueezeMetrics("MICRO", borrow_fee_pct=700.0))
        self.assertEqual(a.classification, SqueezeClass.WATCH)
        self.assertTrue(any("crowded short" in n for n in a.notes))

    def test_utilization_alone_confirms_crowded_short(self):
        # High utilization IS evidence of a crowded short -> NOT capped.
        a = assess(SqueezeMetrics("X", utilization_pct=96.0, borrow_fee_pct=40.0))
        self.assertIn(a.classification, (SqueezeClass.ELEVATED, SqueezeClass.SQUEEZE_FUEL))


class TestOverextensionAndLiquidity(unittest.TestCase):
    def test_extreme_momentum_penalises_and_downgrades(self):
        a = assess(SqueezeMetrics("SDOT", short_interest_pct_float=30, borrow_fee_pct=800,
                                  momentum_pct=5699, price=9))
        self.assertEqual(a.overextension_factor, 0.40)
        self.assertEqual(a.classification, SqueezeClass.WATCH)  # downgraded off SQUEEZE_FUEL
        self.assertTrue(any("xtended" in n or "played out" in n for n in a.notes))

    def test_moderate_momentum_not_penalised(self):
        a = assess(SqueezeMetrics("X", short_interest_pct_float=30, utilization_pct=92,
                                  borrow_fee_pct=20, momentum_pct=40))
        self.assertEqual(a.overextension_factor, 1.0)
        self.assertEqual(a.classification, SqueezeClass.SQUEEZE_FUEL)

    def test_penny_stock_liquidity_penalty(self):
        a = assess(SqueezeMetrics("CCTG", short_interest_pct_float=25, borrow_fee_pct=800, price=0.80))
        self.assertEqual(a.liquidity_factor, 0.70)
        self.assertTrue(any("Penny" in n for n in a.notes))

    def test_illiquid_dollar_volume_penalty(self):
        a = assess(SqueezeMetrics("THIN", short_interest_pct_float=25, utilization_pct=92,
                                  borrow_fee_pct=20, price=2.0, avg_daily_volume=200_000))  # $0.4M/day
        self.assertEqual(a.liquidity_factor, 0.60)

    def test_liquid_name_not_penalised(self):
        a = assess(SqueezeMetrics("BIG", short_interest_pct_float=25, utilization_pct=92,
                                  borrow_fee_pct=20, price=20, avg_daily_volume=10_000_000))  # $200M/day
        self.assertEqual(a.liquidity_factor, 1.0)
        self.assertEqual(a.overextension_factor, 1.0)

    def test_dollar_volume_property(self):
        self.assertEqual(SqueezeMetrics(price=10, avg_daily_volume=1_000_000).dollar_volume, 1e7)
        self.assertIsNone(SqueezeMetrics(price=10).dollar_volume)


class TestReport(unittest.TestCase):
    def test_report_and_csv(self):
        ranked = rank_candidates([
            SqueezeMetrics("A", short_interest_pct_float=30, utilization_pct=92, borrow_fee_pct=20,
                           price=15, avg_daily_volume=5e6),
            SqueezeMetrics("B", short_interest_pct_float=60, borrow_fee_pct=1.0),
        ])
        r = report(ranked, top=5)
        self.assertIn("Short-squeeze screen", r)
        self.assertIn("A", r)
        csv = to_csv(ranked)
        self.assertIn("ticker,classification", csv)
        self.assertIn("A,", csv)


def _spiking_series():
    return [Snapshot("w1", borrow_fee_pct=2, utilization_pct=55, short_interest_pct_float=18, price=10, volume=1e6),
            Snapshot("w2", borrow_fee_pct=5, utilization_pct=75, short_interest_pct_float=22, price=11, volume=2e6),
            Snapshot("w3", borrow_fee_pct=12, utilization_pct=92, short_interest_pct_float=27, price=12, volume=4e6)]


class TestTimeSeriesDynamics(unittest.TestCase):
    def test_collapses_to_latest_levels_plus_dynamics(self):
        m = metrics_from_timeseries("X", _spiking_series())
        self.assertEqual(m.borrow_fee_pct, 12)              # latest snapshot level
        self.assertEqual(m.utilization_pct, 92)
        self.assertAlmostEqual(m.borrow_fee_trend_pct_pts, 10)    # 12 - 2
        self.assertAlmostEqual(m.utilization_trend_pct_pts, 37)   # 92 - 55
        self.assertEqual(m.fee_percentile, 100.0)          # latest == its own max
        self.assertAlmostEqual(m.momentum_pct, 20.0)       # 10 -> 12

    def test_spiking_outscores_flat_same_snapshot(self):
        last = Snapshot("w", borrow_fee_pct=12, utilization_pct=92, short_interest_pct_float=27, price=12)
        flat = assess(metrics_from_timeseries("F", [last, last, last]))
        spik = assess(metrics_from_timeseries("S", _spiking_series()))
        self.assertGreater(spik.squeeze_score, flat.squeeze_score)

    def test_empty_series_raises(self):
        with self.assertRaises(ValueError):
            metrics_from_timeseries("X", [])

    def test_screen_panel_ranks_spiking_first(self):
        ranked = screen_panel({"S": _spiking_series(),
                               "GC": [Snapshot("w1", borrow_fee_pct=0.3, short_interest_pct_float=3, price=20)]})
        self.assertEqual(ranked[0].ticker, "S")


class TestCoiledSpring(unittest.TestCase):
    def _coiling(self):
        return [Snapshot("w1", borrow_fee_pct=2, utilization_pct=60, short_interest_pct_float=20, price=10),
                Snapshot("w2", borrow_fee_pct=8, utilization_pct=82, short_interest_pct_float=24, price=11)]

    def test_coiled_when_tightening_and_not_ignited(self):
        self.assertTrue(assess(metrics_from_timeseries("X", self._coiling())).coiled_spring.triggered)

    def test_not_coiled_when_already_ignited(self):
        ignited = list(self._coiling())
        ignited[-1] = Snapshot("w2", borrow_fee_pct=8, utilization_pct=82, short_interest_pct_float=24, price=30)
        self.assertFalse(assess(metrics_from_timeseries("X", ignited)).coiled_spring.triggered)

    def test_not_coiled_when_flat_snapshot(self):
        # crowded + expensive but NO tightening (single snapshot, no dynamics)
        a = assess(SqueezeMetrics("X", short_interest_pct_float=30, utilization_pct=92, borrow_fee_pct=20))
        self.assertFalse(a.coiled_spring.triggered)

    def test_coiled_unavailable_without_lending_signal(self):
        r = detect_coiled_spring(SqueezeMetrics("X", short_interest_pct_float=30))
        self.assertEqual(r.mode, "unavailable")

    def test_not_coiled_when_penny_falling_knife(self):
        # tightening fee + crowded, but a sub-$1 penny -> falling knife, not a coil
        series = [Snapshot("w1", borrow_fee_pct=20, short_interest_pct_float=28, price=0.80),
                  Snapshot("w2", borrow_fee_pct=39, short_interest_pct_float=28, price=0.69)]
        self.assertFalse(assess(metrics_from_timeseries("BYND", series)).coiled_spring.triggered)


if __name__ == "__main__":
    unittest.main(verbosity=2)
