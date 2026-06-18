"""Unit tests for screen_core.

Each test pins behaviour that previously failed silently in the
original screener (the bug classes we found by manual audit).
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import pandas as pd
import pytest

import screen_core as core
import params


# ----- Recovery / upside math --------------------------------------

def test_compute_recovery_upside_listed_clean():
    # 30% discount, near-full recovery -> ~38% total return
    recovery, etr, pen = core.compute_recovery_upside(0.30, "LISTED_CLEAN")
    assert recovery == pytest.approx(0.97)
    assert pen == pytest.approx(1.0)
    assert etr == pytest.approx(0.97 / 0.70 - 1.0)


def test_compute_recovery_upside_private_equity_cut():
    _, etr_clean, _ = core.compute_recovery_upside(0.50, "LISTED_CLEAN")
    _, etr_pe, _ = core.compute_recovery_upside(0.50, "PRIVATE_EQUITY")
    assert etr_pe < etr_clean
    assert etr_pe == pytest.approx(0.70 / 0.50 - 1.0)


def test_compute_recovery_upside_premium_is_negative():
    _, etr, _ = core.compute_recovery_upside(-0.10, "LISTED_CLEAN")
    assert etr < 0


def test_compute_recovery_upside_default_class():
    recovery, _, _ = core.compute_recovery_upside(0.20, "FOO")
    assert recovery == params.DEFAULT_RECOVERY


def test_nav_trajectory_penalty_stable_nav_no_change():
    """Stable NAV (NAVTR1Y ~ 0) leaves recovery unchanged."""
    assert core.nav_trajectory_penalty(0.0) == pytest.approx(1.0)
    assert core.nav_trajectory_penalty(5.0) == pytest.approx(1.0)


def test_nav_trajectory_penalty_declining_nav_cuts_recovery():
    """20% NAV decline -> 0.70 multiplier on recovery."""
    p = core.nav_trajectory_penalty(-20.0)
    assert 0.65 <= p <= 0.75


def test_nav_trajectory_penalty_large_decline():
    """50% NAV decline -> heavy penalty (interpolated between -20% @
    0.70 and -100% @ 0.50; -50% lands roughly at 0.625)."""
    p = core.nav_trajectory_penalty(-50.0)
    assert 0.50 <= p <= 0.66


def test_wind_down_age_curve_fresh_announcement():
    """Day 0 wind-down: no adjustment."""
    prob, dur = core.wind_down_age_adjustment(0, "WIND_DOWN_COMMITTED")
    assert prob == pytest.approx(1.0)
    assert dur == pytest.approx(1.0)


def test_wind_down_age_curve_18m_in():
    """18 months into wind-down: duration shrinks materially."""
    prob, dur = core.wind_down_age_adjustment(18, "WIND_DOWN_COMMITTED")
    assert prob >= 1.0
    assert dur < 0.6  # less than 60% of original duration left


def test_wind_down_age_curve_non_event_unaffected():
    """Structural-discount names aren't subject to the age curve."""
    prob, dur = core.wind_down_age_adjustment(24, "STRUCTURAL_DISCOUNT")
    assert prob == 1.0 and dur == 1.0


def test_check_investability_catalyst_aware():
    """A £25m wind-down stub passes the relaxed gates; a £25m
    structural-discount name still fails."""
    rec = {"MarketCap": 25.0, "AvgValTrd1M": 0.06,
           "NetGearCum": 0, "OngoingCharge": 1.0}
    ok_wd, _ = core.check_investability("X.L", rec, catalyst="WIND_DOWN_COMMITTED")
    ok_st, _ = core.check_investability("X.L", rec, catalyst="STRUCTURAL_DISCOUNT")
    assert ok_wd is True
    assert ok_st is False


def test_daily_vol_spike_features_picks_up_single_bar():
    """A single big day in the last 30 should fire has_spike=True.
    Base needs non-zero std for vol_z to be defined."""
    import pandas as pd, numpy as np
    idx = pd.date_range("2024-01-01", periods=150, freq="D")
    rng = np.random.RandomState(0)
    vol = rng.uniform(80, 120, 150)
    # Inject one large spike in the last 30 days at high-close
    vol[140] = 10000
    df = pd.DataFrame({
        "Open": np.full(150, 100.0),
        "High": np.full(150, 102.0),
        "Low": np.full(150, 98.0),
        "Close": np.full(150, 101.5),  # closing high
        "Volume": vol,
    }, index=idx)
    max_z, dt, signed, has_spike = core.daily_vol_spike_features(df)
    assert has_spike
    assert max_z > 3.0
    assert signed > 0  # close-at-high direction


def test_daily_vol_spike_no_spike_in_quiet_data():
    import pandas as pd, numpy as np
    idx = pd.date_range("2024-01-01", periods=150, freq="D")
    df = pd.DataFrame({
        "Open": 100.0, "High": 101.0, "Low": 99.0, "Close": 100.0,
        "Volume": np.random.RandomState(0).uniform(80, 120, 150),
    }, index=idx)
    _, _, _, has_spike = core.daily_vol_spike_features(df)
    assert not has_spike


def test_phase_classifier_fires_on_daily_spike_alone():
    """Even with weak weekly directional, a daily vol_z >= 3 triggers
    BASE_ABSORBING."""
    p = _phase(directional_8w=0.1, vol_z_8w_max=0.5,
               daily_vol_z_max_30d=3.5, daily_vol_spike_directional=2.0)
    assert p == "BASE_ABSORBING"


def test_phase_classifier_daily_spike_needs_direction():
    """A daily vol_z 2.0 with neutral-close shouldn't fire (could be
    panic selling); 2.0 with strong up-close does."""
    p_neutral = _phase(directional_8w=0.0, vol_z_8w_max=0.5,
                       daily_vol_z_max_30d=2.0,
                       daily_vol_spike_directional=0.1)
    p_up = _phase(directional_8w=0.0, vol_z_8w_max=0.5,
                  daily_vol_z_max_30d=2.0,
                  daily_vol_spike_directional=1.6)
    assert p_neutral != "BASE_ABSORBING"
    assert p_up == "BASE_ABSORBING"


# ----- IRR ---------------------------------------------------------

def test_annualise_basic():
    # 21% over 12m -> 21% IRR
    assert core.annualise(0.21, 12) == pytest.approx(0.21)


def test_annualise_long_duration_compounds_down():
    # 87% over 30m -> ~30% IRR (annualised)
    irr = core.annualise(0.87, 30)
    assert 0.25 < irr < 0.32


def test_annualise_zero_duration_safe():
    assert core.annualise(0.5, 0) == 0.0


def test_annualise_total_loss_handled():
    assert core.annualise(-1.0, 12) == -1.0


# ----- Discount clamping -------------------------------------------

def test_clamp_discount_in_band_passthrough():
    assert core.clamp_discount(0.30) == 0.30


def test_clamp_discount_jema_minus_304_dropped():
    # The JEMA -304% data error must be rejected
    assert core.clamp_discount(-3.04) is None


def test_clamp_discount_premium_at_band_edge_passes():
    assert core.clamp_discount(-0.10) == -0.10


def test_clamp_discount_extreme_discount_dropped():
    # 99% is implausible (would imply 99x upside on closure)
    assert core.clamp_discount(0.99) is None


# ----- Base detection ----------------------------------------------

def _fake_ohlc(closes: list[float]) -> pd.DataFrame:
    idx = pd.date_range("2024-01-01", periods=len(closes), freq="W")
    return pd.DataFrame({
        "Open": closes, "High": [c * 1.02 for c in closes],
        "Low": [c * 0.98 for c in closes], "Close": closes,
        "Volume": [1000] * len(closes),
    }, index=idx)


def test_detect_base_returns_none_when_short():
    df = _fake_ohlc([10] * 5)
    assert core.detect_base(df) is None


def test_detect_base_finds_tight_range():
    # 30 weeks tight (5% spread) -> base detected
    closes = [100 + (i % 3) * 1.5 for i in range(30)]
    df = _fake_ohlc(closes)
    base = core.detect_base(df, range_threshold=0.10)
    assert base is not None
    assert len(base) >= 20


def test_detect_base_terminates_on_trend():
    # 20 weeks of strong uptrend should not produce a base
    closes = [100 + i * 5 for i in range(20)]
    df = _fake_ohlc(closes)
    base = core.detect_base(df, range_threshold=0.10)
    # Either None or only the most-recent tail
    assert base is None or len(base) < 15


def test_detect_base_robust_to_single_outlier():
    # 28 tight bars + 1 outlier should still give a base (IQR shrugs
    # off single bars; the v2 max/min walker would terminate here).
    closes = [100] * 25 + [200] + [100] * 4   # the spike is one bar
    df = _fake_ohlc(closes)
    base = core.detect_base(df, range_threshold=0.10)
    assert base is not None and len(base) >= 20


# ----- Directional volume -----------------------------------------

def _rng(n):
    """Deterministic small wiggle so std > 0 for vol_z denominator."""
    return [(i % 7) * 100 for i in range(n)]


def test_directional_vol_accumulation_pattern():
    # 60-bar base with ordinary volume variation; tail: 3 high-volume
    # up-closes -> positive signed sum.
    base_rows = [[100, 102, 98, 100, 1000 + v] for v in _rng(60)]
    base_rows.extend([[100, 105, 99, 104, 8000]] * 3)
    df = pd.DataFrame(base_rows, columns=["Open", "High", "Low", "Close", "Volume"])
    df.index = pd.date_range("2024-01-01", periods=len(df), freq="W")
    base = df.iloc[:-3]
    signed_sum, count, _ = core.directional_vol_score(df, base, window=8)
    assert signed_sum > 1.5, f"expected accumulation, got {signed_sum}"
    assert count >= 3


def test_directional_vol_distribution_pattern():
    base_rows = [[100, 102, 98, 100, 1000 + v] for v in _rng(60)]
    base_rows.extend([[100, 101, 95, 96, 8000]] * 3)
    df = pd.DataFrame(base_rows, columns=["Open", "High", "Low", "Close", "Volume"])
    df.index = pd.date_range("2024-01-01", periods=len(df), freq="W")
    base = df.iloc[:-3]
    signed_sum, _, _ = core.directional_vol_score(df, base, window=8)
    assert signed_sum < 0, f"expected distribution to be negative, got {signed_sum}"


# ----- Phase classifier --------------------------------------------

def _phase(**kw):
    """Helper with defaults for classify_phase()."""
    defaults = dict(
        in_base=True, base_length_weeks=30,
        vol_z_last=0.0, vol_z_8w_max=0.5,
        directional_8w=0.0, chg_13w=0.0,
        last_close=100.0, base_high=105.0, base_low=95.0,
        recent_selloff=False, mfi_low_8w=50.0,
    )
    defaults.update(kw)
    return core.classify_phase(**defaults)


def test_phase_post_rerating_at_15pct():
    assert _phase(chg_13w=0.20) == "POST_RERATING"


def test_phase_no_base_short():
    assert _phase(in_base=False, base_length_weeks=8) == "NO_BASE"


def test_phase_capitulation_pattern():
    # Selloff + vol spike + washed MFI -> CAPITULATION (CHRY archetype)
    p = _phase(recent_selloff=True, vol_z_8w_max=2.5, mfi_low_8w=18.0)
    assert p == "CAPITULATION"


def test_phase_absorbing_on_window_not_last_bar():
    # The bug we fixed: directional 8w sum is high but last bar is muted
    p = _phase(vol_z_last=0.3, vol_z_8w_max=2.5, directional_8w=3.0)
    assert p == "BASE_ABSORBING"


def test_phase_breakout_requires_above_high_and_vol():
    p = _phase(last_close=110.0, base_high=100.0, vol_z_last=2.5,
               vol_z_8w_max=2.5)
    assert p == "BASE_BREAKOUT"


# ----- Setup score decomposition -----------------------------------

def test_setup_score_excludes_catalyst():
    """Catalyst should NOT enter the setup score — it multiplies at the
    end via expected_irr instead."""
    r1 = core.ScreenResult(ticker="X", phase="BASE_ABSORBING",
                           base_length_weeks=52, base_range_pct=0.20,
                           poc=100.0, last_close=100.0, poc_distance_pct=0.0)
    r1.catalyst = "WIND_DOWN_COMMITTED"
    r1.nav_quality = "LISTED_CLEAN"
    r2 = core.ScreenResult(ticker="Y", phase="BASE_ABSORBING",
                           base_length_weeks=52, base_range_pct=0.20,
                           poc=100.0, last_close=100.0, poc_distance_pct=0.0)
    r2.catalyst = "STRUCTURAL_DISCOUNT"   # weaker catalyst
    r2.nav_quality = "PRIVATE_EQUITY"     # weaker NAV
    s1 = core.compute_setup_score(r1)
    s2 = core.compute_setup_score(r2)
    assert s1 == s2, "setup score should be identical regardless of catalyst/NAV"


def test_setup_score_broken_base_returns_zero():
    r = core.ScreenResult(ticker="X", phase="BASE_QUIET",
                          base_length_weeks=20, base_range_pct=0.80,
                          base_quantile_range_pct=0.60,  # IQR > 0.40 — broken
                          poc=100.0, last_close=100.0, poc_distance_pct=0.0)
    assert core.compute_setup_score(r) == 0.0


def test_setup_score_iqr_narrow_but_close_outside_iqr():
    """Regression for the SUPP/RMII/IEM bug: IQR is narrow (good base)
    but POC distance > IQR width. Previously scored 0 because the IQR
    was being used as the POC-edge denominator. Should now score
    meaningfully because base_range_pct is the real edge."""
    r = core.ScreenResult(
        ticker="SUPP.L", phase="BASE_ABSORBING",
        base_length_weeks=68, base_range_pct=0.55,
        base_quantile_range_pct=0.13,  # narrow IQR (not broken)
        poc=14.5, last_close=16.6,
        poc_distance_pct=0.145,  # close is 14.5% off POC — outside IQR
    )
    s = core.compute_setup_score(r)
    # Expected ~ phase_w(1.0) * poc_w(1 - 0.145/0.50) * base_w(68/52->1.0)
    assert s > 0.5, f"expected meaningful score, got {s}"


def test_setup_score_capitulation_ignores_poc_distance():
    """Phase CAPITULATION means the close has MOVED AWAY from POC
    (that's the buy signal). Setup_score must not penalise that."""
    r = core.ScreenResult(
        ticker="X", phase="CAPITULATION",
        base_length_weeks=52, base_range_pct=0.30,
        base_quantile_range_pct=0.10,
        poc=100.0, last_close=85.0, poc_distance_pct=0.15,
    )
    s = core.compute_setup_score(r)
    assert s > 0.7, f"capitulation should keep its phase weight, got {s}"


# ----- Investability gates -----------------------------------------

def test_investability_market_cap_floor():
    rec = {"MarketCap": 10.0, "AvgValTrd1M": 1.0, "NetGearCum": 0, "OngoingCharge": 1.0}
    ok, reasons = core.check_investability("X.L", rec)
    assert not ok
    assert any("market cap" in r for r in reasons)


def test_investability_gearing_ceiling():
    rec = {"MarketCap": 200.0, "AvgValTrd1M": 1.0, "NetGearCum": 200, "OngoingCharge": 1.0}
    ok, reasons = core.check_investability("X.L", rec)
    assert not ok
    assert any("gearing" in r for r in reasons)


def test_investability_non_uk_passes():
    # Non-UK ticker has no AIC record; gates are UK-specific.
    ok, reasons = core.check_investability("BRK-B", None)
    assert ok and reasons == []


# ----- Post-rerating taper -----------------------------------------

def test_post_rerating_taper_partial():
    # 16% realised against 80% target -> ~80% of return remaining
    remaining = core._post_rerating_taper(0.16, 0.80)
    assert remaining == pytest.approx(1 - 0.20)


def test_post_rerating_taper_overshoot():
    # Already exceeded target -> 0% left
    assert core._post_rerating_taper(1.0, 0.5) == 0.0
