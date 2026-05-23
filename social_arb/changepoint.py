"""Change-point detection on social signals via `ruptures`.

Spec recommends `ruptures` for CUSUM/PELT change-point detection on
low-frequency tickers where EWMA z-score is too noisy. Identifies the
exact dates where a series's mean changed structurally -- the start
of a new attention regime.

PELT (Pruned Exact Linear Time, Killick 2012) finds change points by
minimizing a penalized cost function in O(N log N). With our daily
mention/sentiment series at N ~= 700 days per ticker, it runs in
~50ms per ticker.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)


@dataclass
class ChangePoints:
    indices: list[int]            # change-point indices (zero-based)
    dates: list[pd.Timestamp]     # date at each change point
    means_between: list[float]    # mean of each segment


def find_change_points(
    series: pd.Series,
    *,
    method: str = "pelt",         # 'pelt' | 'binseg' | 'window'
    cost: str = "l2",
    penalty: float = 5.0,
    min_segment_size: int = 14,
) -> ChangePoints:
    """Detect structural change-points in a 1-D series.

    Returns dates where the series's mean shifts statistically.
    """
    try:
        import ruptures as rpt  # type: ignore
    except ImportError:
        log.warning("ruptures not installed; `pip install ruptures`")
        return ChangePoints([], [], [])
    s = series.dropna().astype(float)
    if len(s) < min_segment_size * 2:
        return ChangePoints([], [], [])
    x = s.values.reshape(-1, 1)
    if method == "pelt":
        algo = rpt.Pelt(model=cost, min_size=int(min_segment_size)).fit(x)
        bkps = algo.predict(pen=float(penalty))
    elif method == "binseg":
        algo = rpt.Binseg(model=cost, min_size=int(min_segment_size)).fit(x)
        bkps = algo.predict(pen=float(penalty))
    elif method == "window":
        algo = rpt.Window(width=int(min_segment_size), model=cost).fit(x)
        bkps = algo.predict(pen=float(penalty))
    else:
        raise ValueError(f"unknown method: {method}")
    # ruptures returns end-indices including the last one (= len). Drop it.
    breaks = [b - 1 for b in bkps[:-1] if 0 <= b - 1 < len(s)]
    means: list[float] = []
    prev = 0
    for b in breaks + [len(s)]:
        means.append(float(s.iloc[prev:b].mean()) if b > prev else float("nan"))
        prev = b
    return ChangePoints(
        indices=breaks,
        dates=[s.index[i] for i in breaks],
        means_between=means,
    )


def scan_tickers_for_changes(
    cfg,
    *,
    tickers: list[str] | None = None,
    min_total_mentions: int = 30,
    method: str = "pelt",
    penalty: float = 5.0,
    top_recent: int = 30,
) -> pd.DataFrame:
    """For each ticker with enough history, find change-points and report
    the most recent one. Sorted by recency."""
    from . import storage, ranking
    daily = ranking._per_ticker_daily(cfg)
    if daily.empty:
        return pd.DataFrame()
    target_tickers = tickers or list(daily.groupby("ticker")["mentions"].sum()
                                     .loc[lambda s: s >= min_total_mentions].index)
    rows = []
    for ticker in target_tickers:
        sub = daily[daily["ticker"] == ticker]
        if sub.empty:
            continue
        series = sub.set_index("date")["mentions"].sort_index()
        series.index = pd.to_datetime(series.index)
        series = series.asfreq("D", fill_value=0.0)
        if len(series) < 30:
            continue
        cps = find_change_points(series, method=method, penalty=penalty)
        if not cps.dates:
            continue
        last_cp_date = cps.dates[-1]
        # Segment means around the last change point.
        i = cps.indices[-1]
        before = float(series.iloc[max(0, i - 14): i].mean()) if i > 0 else 0.0
        after = float(series.iloc[i: i + 14].mean()) if i < len(series) else 0.0
        rows.append({
            "ticker": ticker,
            "last_change_point_date": last_cp_date.date(),
            "n_changes": len(cps.dates),
            "mean_14d_before": round(before, 2),
            "mean_14d_after": round(after, 2),
            "delta": round(after - before, 2),
        })
    if not rows:
        return pd.DataFrame()
    out = pd.DataFrame(rows)
    # Recency-rank: most recent change first.
    out["last_change_point_date"] = pd.to_datetime(out["last_change_point_date"])
    out = out.sort_values("last_change_point_date", ascending=False).head(int(top_recent)).reset_index(drop=True)
    return out
