"""Edge-case tests for seasonal bucket_metrics (n=1, all-positive, zero variance)."""
import numpy as np
import pandas as pd
import pytest

from midcap_weekly_anomalies import build_features, bucket_metrics, asset_aggregates


def _frame(returns, vols=None):
    n = len(returns) + 1
    idx = pd.date_range("2005-01-07", periods=n, freq="7D")
    close = 100 * np.cumprod(np.r_[1.0, np.array(returns) + 1.0])
    vol = np.full(n, 1e6) if vols is None else np.r_[1e6, vols]
    return pd.DataFrame({"Close": close, "Volume": vol}, index=idx)


def _bucket(returns, vols=None):
    df = _frame(returns, vols)
    feats = build_features(df)
    return bucket_metrics(feats, asset_aggregates(feats))


def test_single_observation_no_crash():
    m = _bucket([0.03])
    assert m["n"] == 1
    assert np.isnan(m["std_ret"])          # std undefined for n=1
    assert np.isnan(m["sharpe"])


def test_all_positive_returns():
    m = _bucket([0.01, 0.02, 0.015, 0.03, 0.025])
    assert m["win_rate"] == 1.0
    assert m["gain_to_pain"] == 10.0       # no losers -> capped, not inf/NaN
    assert np.isnan(m["sortino"])          # no downside


def test_zero_variance_returns():
    m = _bucket([0.0, 0.0, 0.0, 0.0])
    assert m["win_rate"] == 0.0
    assert np.isnan(m["sharpe"]) or m["sharpe"] == 0.0


def test_metrics_are_finite_or_nan_never_inf():
    m = _bucket([0.02, -0.01, 0.03, -0.02, 0.04, 0.01, -0.03, 0.02])
    for k, v in m.items():
        if isinstance(v, float):
            assert not np.isinf(v), f"{k} is inf"
