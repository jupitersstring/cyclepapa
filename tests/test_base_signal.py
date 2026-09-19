"""Tests for the MU-style consolidation-base detector and the base-inflection screen."""
import numpy as np
import pandas as pd

from earnings_model import base_signal, screens


def _series(vals):
    return list(map(float, vals))


def test_short_history_returns_empty():
    assert base_signal.compute_base_metrics(_series(range(10))) == {}   # < 24 bars
    assert base_signal.compute_base_metrics([]) == {}


def test_coiled_base_scores_high():
    # 40 months oscillating in a tight, contracting band around 100, ending near the top
    rng = np.random.default_rng(0)
    early = 100 + rng.normal(0, 8, 20)          # wider early
    late = 100 + rng.normal(0, 3, 19)           # contracting
    closes = _series(list(early) + list(late) + [107.0])   # press the top
    m = base_signal.compute_base_metrics(closes)
    assert m["base_above_ma"] is True
    assert m["base_pos"] > 0.6                   # pressing the top of the range
    assert m["base_score"] > 0.4                 # a real base


def test_broken_out_scores_low():
    # long flat base then a vertical breakout far above the MA (the MU 'already left' case)
    base = [100.0] * 30
    breakout = [120.0, 145.0, 175.0, 210.0]      # blown out well above the 10mo MA
    m = base_signal.compute_base_metrics(_series(base + breakout))
    assert m["base_extension"] > 0.20            # extended above MA
    assert m["base_score"] < 0.30                # penalised — not a current base


def test_downtrend_scores_low():
    closes = _series([200 - 3 * i for i in range(40)])   # steady decline, below MA
    m = base_signal.compute_base_metrics(closes)
    assert m["base_above_ma"] is False
    assert m["base_score"] < 0.3


def test_attach_noop_without_overlay(tmp_path):
    df = pd.DataFrame({"symbol": ["A"], "x": [1]})
    out = base_signal.attach(df, path=tmp_path / "nope.parquet")
    assert list(out.columns) == ["symbol", "x"]


def test_base_inflection_screen_requires_base_and_inflection(tmp_path):
    ov = pd.DataFrame({
        "symbol": ["HI", "LO", "NB"],
        "base_score": [0.75, 0.75, 0.10],       # HI/LO strong base, NB no base
        "base_pos": [0.9, 0.9, 0.3], "base_len_months": [30, 30, 4],
        "base_vol_contraction": [0.3, 0.3, 1.1], "base_extension": [0.05, 0.05, 0.0],
    })
    p = tmp_path / "base_metrics.parquet"
    ov.to_parquet(p, index=False)
    base = pd.DataFrame({
        "symbol": ["HI", "LO", "NB"], "name": ["Hi", "Lo", "Nb"],
        "region": ["US"] * 3, "industry": ["Software"] * 3, "size_bucket": ["Large Cap"] * 3,
        "revenue_n_periods": [6, 6, 6], "forwardPE": [20.0, 20.0, 20.0],
        "revenue_growth": [0.2, 0.2, 0.2], "revenue_q_yoy": [0.3, 0.3, 0.3],
        "inflection_score": [0.9, 0.1, 0.9],    # HI inflecting, LO not
        "ebitda_accel_abs": [1e6, -1e6, 1e6],
    })
    df = base_signal.attach(base, path=p)
    res = screens.base_inflection(df, top=None)
    order = list(res["symbol"])
    assert "NB" not in order                     # no base -> gated out
    assert order.index("HI") < order.index("LO") # base+inflection beats base-without


def test_base_inflection_empty_without_overlay():
    base = pd.DataFrame({
        "symbol": ["A"], "name": ["A"], "region": ["US"], "industry": ["Software"],
        "size_bucket": ["Large Cap"], "revenue_n_periods": [6], "forwardPE": [20.0],
        "revenue_growth": [0.2],
    })
    assert len(screens.base_inflection(base, top=None)) == 0
