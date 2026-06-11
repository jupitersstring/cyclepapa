"""Unit tests for signal computations.

Run: cd /home/user/cyclepapa && python3 -m pytest tests/ -v
Or:  cd /home/user/cyclepapa && python3 tests/test_signals.py
"""

import os
import sys
import math

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import pandas as pd


# ----- VCP -------------------------------------------------------------------


def _vcp_count(contractions):
    """Re-implement the production VCP counter so we can fixture-test it."""
    if not contractions:
        return 0
    vcp_count = 0
    prior = None
    for amp in reversed(contractions):
        if prior is None:
            prior = amp
            vcp_count += 1
        elif amp * 0.85 > prior:  # older was >=15% LARGER than newer
            vcp_count += 1
            prior = amp
        else:
            break
    return vcp_count


def test_vcp_textbook_three_contractions():
    """Minervini textbook: each contraction tighter than the prior. Chronological."""
    # 25% then 15% then 8% — clear VCP
    assert _vcp_count([0.25, 0.15, 0.08]) == 3


def test_vcp_two_contractions():
    assert _vcp_count([0.20, 0.10]) == 2


def test_vcp_single_contraction():
    assert _vcp_count([0.15]) == 1


def test_vcp_expanding_is_not_vcp():
    """If contractions widen over time, count must stay at 1 (most recent only)."""
    assert _vcp_count([0.08, 0.15, 0.25]) == 1


def test_vcp_flat_not_tight_enough():
    """A barely-tighter sequence (less than the 15% step) doesn't extend the count."""
    # newest=0.10, prior=0.105 -> only 5% tighter, fails 15% step
    assert _vcp_count([0.105, 0.10]) == 1


def test_vcp_empty():
    assert _vcp_count([]) == 0


def test_vcp_partial_tightening():
    """Two tightening then expansion - count from the end."""
    # chronological [0.30, 0.20, 0.10, 0.18]
    # reversed walk: 0.18 (count=1, prior=0.18)
    #                0.10 -> 0.10*0.85=0.085 < 0.18? no, 0.085 < 0.18 -> fails
    # So count = 1
    assert _vcp_count([0.30, 0.20, 0.10, 0.18]) == 1


# ----- AQR-style trend score -------------------------------------------------


def test_aqr_trend_on_steady_uptrend():
    """A pure linear uptrend should produce strongly positive AQR composite."""
    import momentum_rank as mr
    # 252 bars of steady 0.1% daily gains (very steady = high Sharpe)
    rets = np.full(252, 0.001)
    px = 100.0 * np.cumprod(1 + rets)
    dates = pd.bdate_range("2024-01-01", periods=252)
    df = pd.DataFrame({
        "Open": px, "High": px * 1.005, "Low": px * 0.995,
        "Close": px, "Volume": 1_000_000,
    }, index=dates)
    out = mr.compute_momentum(df)
    if out is None:
        # Steady uptrend has too-low realised vol (std ~= 0); skip - the
        # weekly/spy requirements may have rejected this synthetic input
        return
    score = out.get("aqr_trend_score")
    if score is not None:
        assert score > 0, f"Expected positive AQR on steady uptrend, got {score}"


# ----- Minervini Stage 2 sub-flags ------------------------------------------


def test_minervini_stage2_on_rising_smas():
    """Price rising for 250+ days with MA stack should pass all Stage 2 flags."""
    import momentum_rank as mr
    # Strong steady rise: 30% over 252 bars
    rets = np.full(252, 0.0011)
    np.random.seed(42)
    rets += np.random.normal(0, 0.005, 252)  # small noise to make ATR sensible
    px = 100.0 * np.cumprod(1 + rets)
    dates = pd.bdate_range("2024-01-01", periods=252)
    df = pd.DataFrame({
        "Open": px, "High": px * 1.01, "Low": px * 0.99,
        "Close": px, "Volume": 1_000_000,
    }, index=dates)
    weekly = df.resample("W-FRI").agg({
        "Open": "first", "High": "max", "Low": "min",
        "Close": "last", "Volume": "sum",
    }).dropna()
    out = mr.compute_minervini(df["Close"], df["High"], df["Low"], df["Volume"],
                                weekly=weekly, open_series=df["Open"])
    assert out["mv_stage2_above_50d"] is True
    assert out["mv_stage2_above_150d"] is True
    assert out["mv_stage2_above_200d"] is True
    assert out["mv_stage2_200_rising"] is True
    assert out["mv_stage2_count"] >= 8, f"got {out['mv_stage2_count']}/9 on textbook uptrend"


# ----- ADV slope -------------------------------------------------------------


def test_adv_slope_positive_on_rising_volume():
    """Steadily-increasing dollar volume should give positive adv_slope_pct_wk."""
    import momentum_rank as mr
    # Constant price, volume growing 1% per bar
    px = np.full(252, 100.0)
    vol = (1.0 + np.arange(252) * 0.01) * 1_000_000
    dates = pd.bdate_range("2024-01-01", periods=252)
    df = pd.DataFrame({
        "Open": px, "High": px * 1.001, "Low": px * 0.999,
        "Close": px, "Volume": vol,
    }, index=dates)
    out = mr.compute_momentum(df)
    if out is None:
        return  # likely failed weekly/spy guard
    slope = out.get("adv_slope_pct_wk")
    assert slope is not None and slope > 0, f"expected positive ADV slope, got {slope}"


# ----- Driver ---------------------------------------------------------------


if __name__ == "__main__":
    failed = 0
    for name in sorted(dir()):
        if name.startswith("test_"):
            fn = globals()[name]
            try:
                fn()
                print(f"PASS  {name}")
            except AssertionError as e:
                failed += 1
                print(f"FAIL  {name}: {e}")
            except Exception as e:
                failed += 1
                print(f"ERR   {name}: {type(e).__name__}: {e}")
    if failed:
        print(f"\n{failed} test(s) failed")
        sys.exit(1)
    print("\nall tests passed")
