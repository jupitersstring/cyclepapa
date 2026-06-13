"""
Unit-bias removal pipeline.

Every raw series enters as a flow-as-%-of-GDP (or %-of-broad-money for monetary
aggregates). It is then put through:

    level (%GDP)
      -> annualised change over a window      (impulse, the first derivative)
      -> acceleration                          (the second derivative -- markets
                                                 turn on the change in the change)
      -> z-score vs the country's own history  (so 'fast' is comparable across
                                                 economies of different volatility)
      -> cross-sectional percentile            (rank across the panel)

This keeps every input in a comparable, dimensionless space. Composite scores
live in z / percentile units, never in dollars or raw percent.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def annualised_change(series: pd.Series, window: int) -> pd.Series:
    """Change over `window` periods, annualised. `series` is %GDP (a level)."""
    periods_per_year = _infer_periods_per_year(series)
    raw = series.diff(window)
    return raw * (periods_per_year / window)


def acceleration(series: pd.Series, window: int) -> pd.Series:
    """Second derivative: change in the annualised-change."""
    return annualised_change(series, window).diff(window)


def zscore(series: pd.Series, min_periods: int = 8) -> pd.Series:
    """Expanding z-score vs the series' own history (no look-ahead)."""
    mean = series.expanding(min_periods=min_periods).mean()
    std = series.expanding(min_periods=min_periods).std()
    return (series - mean) / std.replace(0, np.nan)


def zscore_static(value: float, history: np.ndarray) -> float:
    """Z-score of a single value against a historical sample."""
    history = np.asarray(history, dtype=float)
    sd = history.std()
    if sd == 0 or np.isnan(sd):
        return 0.0
    return float((value - history.mean()) / sd)


def cross_sectional_percentile(values: pd.Series) -> pd.Series:
    """Rank a cross-section into [0, 1] percentiles."""
    return values.rank(pct=True)


def diffusion_index(frame: pd.DataFrame) -> pd.Series:
    """Share of sub-indicators improving (>0) per row. Diffusion leads levels."""
    return (frame > 0).mean(axis=1)


def clip_z(value: float, lo: float = -3.0, hi: float = 3.0) -> float:
    """Winsorise a z-score to keep outliers from dominating the composite."""
    return float(np.clip(value, lo, hi))


def _infer_periods_per_year(series: pd.Series) -> int:
    """Best-effort inference of sampling frequency from a DatetimeIndex."""
    if not isinstance(series.index, pd.DatetimeIndex) or len(series) < 3:
        return 4  # default to quarterly, the BoP/flow-of-funds cadence
    days = np.median(np.diff(series.index.values).astype("timedelta64[D]").astype(int))
    if days <= 9:
        return 52
    if days <= 45:
        return 12
    if days <= 135:
        return 4
    return 1
