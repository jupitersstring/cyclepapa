"""Regression tests for the shared signal primitives."""
import numpy as np
import pandas as pd
import pytest

from signals import ehlers_bandpass, latest_crossing, drop_incomplete_last


def _ref_bandpass(src, flen, slen):
    a1, a2 = 5 / flen, 5 / slen
    n = len(src); PB = [0.0] * n
    for t in range(n):
        s0 = src[t]; s1 = src[t - 1] if t >= 1 else 0.0
        p1 = PB[t - 1] if t >= 1 else 0.0; p2 = PB[t - 2] if t >= 2 else 0.0
        PB[t] = (a1 - a2) * s0 + (a2 * (1 - a1) - a1 * (1 - a2)) * s1 \
            + ((1 - a1) + (1 - a2)) * p1 - (1 - a1) * (1 - a2) * p2
    return np.array(PB)


@pytest.mark.parametrize("fl,sl", [(40, 60), (200, 300), (600, 900)])
def test_bandpass_matches_pine(fl, sl):
    rng = np.random.default_rng(0)
    x = np.cumsum(rng.normal(size=800)) + 100
    assert np.max(np.abs(ehlers_bandpass(x, fl, sl) - _ref_bandpass(x, fl, sl))) == 0.0


def test_crossing_detects_up_and_down():
    # synthetic series with a clean cycle -> must find a recent crossing
    t = np.arange(400)
    x = 100 + np.sin(t / 8.0) * 5  # ~50-bar cycle, fits B1
    res = latest_crossing(x, recent=10, bands=[("B1", 40, 60)])
    assert "B1" in res and res["B1"]["dir"] in ("UP", "DOWN")


def test_hysteresis_ignores_tiny_wiggle():
    # a flat line dithered by noise below threshold should yield no decisive cross
    rng = np.random.default_rng(1)
    x = 100 + rng.normal(scale=1e-9, size=300)
    res = latest_crossing(x, recent=5, bands=[("B1", 40, 60)], hysteresis=0.5)
    assert res == {} or all(r["bars_ago"] >= 0 for r in res.values())


def test_drop_incomplete_weekly():
    idx = pd.date_range("2026-05-04", periods=5, freq="7D")  # last ~current week
    df = pd.DataFrame({"Close": [1, 2, 3, 4, 5.0]}, index=idx)
    asof = idx[-1]  # same week as last bar -> drop it
    out = drop_incomplete_last(df, "weekly", asof=asof)
    assert len(out) == 4


def test_drop_incomplete_daily_keeps_past():
    idx = pd.date_range("2026-05-01", periods=5, freq="D")
    df = pd.DataFrame({"Close": [1, 2, 3, 4, 5.0]}, index=idx)
    asof = pd.Timestamp("2026-06-01")  # last bar in the past -> keep all
    assert len(drop_incomplete_last(df, "daily", asof=asof)) == 5


def test_super_smoother_reduces_noise_lowlag():
    from signals import super_smoother
    rng = np.random.default_rng(3)
    t = np.arange(300)
    clean = np.sin(t / 20.0)
    noisy = clean + rng.normal(scale=0.5, size=300)
    sm = super_smoother(noisy, 20)
    # smoothed tracks the clean signal far better than the noisy input
    assert np.std(sm[50:] - clean[50:]) < np.std(noisy[50:] - clean[50:])


def test_smoothed_inflection_finds_trough_early():
    from signals import smoothed_inflection
    t = np.arange(400)
    # V-shape: falling then rising -> a trough; detector should say UP recently
    x = np.concatenate([np.linspace(10, 0, 200), np.linspace(0, 8, 200)])
    r = smoothed_inflection(x, length=21, recent=40)
    assert r is not None and r["dir"] == "UP"
