"""Anomaly detection on mention time series.

Two detectors:

  1. EWMA z-score on log(mentions + 1) -- the workhorse from the report.
     Flags `z > z_thresh` after a warmup period.
  2. Joint mention+sentiment shift -- requires *both* mention z > z_mentions
     and sentiment delta > z_sent to fire. Dramatically reduces false
     positives from generic news bursts.

Both functions accept a pandas Series/DataFrame and return aligned outputs.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class AnomalyParams:
    halflife_days: int = 14
    z_thresh: float = 3.0
    min_periods: int = 7


def ewma_zscore(counts: pd.Series, params: AnomalyParams | None = None) -> pd.DataFrame:
    """Exponentially weighted z-score on log(counts + 1).

    Args:
        counts: time-indexed mention counts (daily).
        params: detection parameters.

    Returns DataFrame indexed like `counts` with columns
        ['log_mentions', 'mu', 'sigma', 'z', 'anomaly'].
    """
    if params is None:
        params = AnomalyParams()

    s = counts.astype(float).fillna(0.0)
    log_s = np.log1p(s)
    ewm = log_s.ewm(halflife=params.halflife_days, min_periods=params.min_periods)
    mu = ewm.mean()
    # ewm.std() of log_s; replace 0 with NaN to avoid div-by-zero.
    sigma = log_s.ewm(halflife=params.halflife_days, min_periods=params.min_periods).std()
    sigma = sigma.replace(0.0, np.nan)
    z = (log_s - mu) / sigma
    anomaly = z > params.z_thresh
    return pd.DataFrame(
        {"log_mentions": log_s, "mu": mu, "sigma": sigma, "z": z, "anomaly": anomaly.fillna(False)}
    )


def joint_signal(
    mentions: pd.Series,
    sentiment: pd.Series,
    z_mentions: float = 2.0,
    z_sent: float = 1.5,
    halflife_days: int = 14,
    min_periods: int = 7,
) -> pd.DataFrame:
    """Joint anomaly: mention spike AND sentiment shift.

    Returns DataFrame with columns ['z_mentions', 'z_sent', 'signal'].
    """
    m = ewma_zscore(mentions, AnomalyParams(halflife_days, z_mentions, min_periods))
    # z-score of sentiment vs its own EWMA mean/std.
    sent = sentiment.astype(float).fillna(0.0)
    smu = sent.ewm(halflife=halflife_days, min_periods=min_periods).mean()
    ssig = sent.ewm(halflife=halflife_days, min_periods=min_periods).std().replace(0.0, np.nan)
    sz = (sent - smu) / ssig
    sig = (m["z"] > z_mentions) & (sz.abs() > z_sent)
    return pd.DataFrame({"z_mentions": m["z"], "z_sent": sz, "signal": sig.fillna(False)})


def breakout_ratio(counts: pd.Series, short: int = 7, long: int = 90) -> pd.Series:
    """Glimpse-style breakout: short MA / long MA.

    Detects "breakout above 2.0" per the report.
    """
    s = counts.astype(float).fillna(0.0)
    short_ma = s.rolling(short, min_periods=1).mean()
    long_ma = s.rolling(long, min_periods=long // 4).mean().replace(0.0, np.nan)
    return short_ma / long_ma
