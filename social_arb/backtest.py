"""Minimal event-study backtester.

Given (a) a set of signal timestamps per ticker and (b) daily prices, compute
cumulative abnormal returns over a configurable window. This is deliberately
simple -- it is the *evaluation* layer, not a trading simulator.

For multi-strategy sweeps users should wire vectorbt downstream; this module
returns DataFrames that vectorbt and pandas both consume natively.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import numpy as np
import pandas as pd

from .prices import daily_close


@dataclass
class EventStudyParams:
    pre_days: int = 5
    post_days: int = 20
    benchmark: str = "SPY"


def event_study(
    signals: pd.DataFrame,
    params: EventStudyParams | None = None,
) -> pd.DataFrame:
    """Run an event study on a frame of (ticker, signal_date) rows.

    Args:
        signals: must have columns ['ticker', 'signal_date'].

    Returns a DataFrame indexed by event_day in [-pre, +post] with columns
        ['n', 'mean_ret', 'mean_car', 'mean_alpha', 'mean_alpha_car']
    where alpha is excess return vs `params.benchmark`.
    """
    if params is None:
        params = EventStudyParams()
    if signals.empty:
        return pd.DataFrame()

    signals = signals.copy()
    signals["signal_date"] = pd.to_datetime(signals["signal_date"]).dt.tz_localize(None).dt.normalize()

    # Pull each ticker's prices once.
    tickers = sorted(signals["ticker"].unique().tolist())
    start = (signals["signal_date"].min() - pd.Timedelta(days=params.pre_days * 2 + 14)).to_pydatetime()
    end = (signals["signal_date"].max() + pd.Timedelta(days=params.post_days * 2 + 14)).to_pydatetime()
    closes: dict[str, pd.Series] = {}
    for t in tickers + [params.benchmark]:
        closes[t] = daily_close(t, start, end)

    bench = closes.get(params.benchmark, pd.Series(dtype=float))
    bench_ret = bench.pct_change()

    window = range(-params.pre_days, params.post_days + 1)
    per_event: list[pd.DataFrame] = []

    for ticker, group in signals.groupby("ticker"):
        px = closes.get(ticker)
        if px is None or px.empty:
            continue
        rets = px.pct_change()
        for _, row in group.iterrows():
            d = row["signal_date"]
            idx_pos = px.index.get_indexer([d], method="bfill")[0]
            if idx_pos < params.pre_days or idx_pos + params.post_days >= len(px):
                continue
            slc = slice(idx_pos - params.pre_days, idx_pos + params.post_days + 1)
            r = rets.iloc[slc].values
            if len(r) != params.pre_days + params.post_days + 1:
                continue
            if not bench_ret.empty:
                br = bench_ret.iloc[slc].reindex_like(rets.iloc[slc]).fillna(0.0).values
            else:
                br = np.zeros_like(r)
            per_event.append(pd.DataFrame({
                "event_day": list(window),
                "ret": r,
                "alpha": r - br,
                "ticker": ticker,
                "signal_date": d,
            }))

    if not per_event:
        return pd.DataFrame()
    combined = pd.concat(per_event, ignore_index=True)
    agg = combined.groupby("event_day").agg(
        n=("ret", "size"),
        mean_ret=("ret", "mean"),
        mean_alpha=("alpha", "mean"),
    )
    agg["mean_car"] = agg["mean_ret"].cumsum()
    agg["mean_alpha_car"] = agg["mean_alpha"].cumsum()
    return agg.reset_index()


def deflated_sharpe(sharpe: float, n_trials: int, n_obs: int) -> float:
    """Lopez de Prado (2014) deflated Sharpe ratio.

    Conservative approximation suitable for retail multiple-testing checks.
    Returns the probability that the *true* Sharpe is > 0 after correcting
    for the number of strategy variants tested.
    """
    if n_trials <= 0 or n_obs <= 1:
        return float("nan")
    # Expected max Sharpe under the null with n_trials trials.
    euler_mascheroni = 0.5772156649
    z_inv = (1 - euler_mascheroni) * _norm_ppf(1 - 1.0 / n_trials) + euler_mascheroni * _norm_ppf(
        1 - 1.0 / (n_trials * np.e)
    )
    # Standard error of Sharpe under iid normal returns.
    se = np.sqrt((1 - sharpe * z_inv + 0.5 * sharpe ** 2 * z_inv ** 2) / (n_obs - 1))
    if se <= 0:
        return float("nan")
    z = (sharpe - z_inv) / se
    return float(_norm_cdf(z))


def _norm_ppf(p: float) -> float:
    # Acklam's rational approximation (sufficient precision for backtest checks).
    from math import log, sqrt
    if p <= 0 or p >= 1:
        return float("nan")
    a = [-3.969683028665376e+01, 2.209460984245205e+02,
         -2.759285104469687e+02, 1.383577518672690e+02,
         -3.066479806614716e+01, 2.506628277459239e+00]
    b = [-5.447609879822406e+01, 1.615858368580409e+02,
         -1.556989798598866e+02, 6.680131188771972e+01,
         -1.328068155288572e+01]
    c = [-7.784894002430293e-03, -3.223964580411365e-01,
         -2.400758277161838e+00, -2.549732539343734e+00,
         4.374664141464968e+00, 2.938163982698783e+00]
    d = [7.784695709041462e-03, 3.224671290700398e-01,
         2.445134137142996e+00, 3.754408661907416e+00]
    plow = 0.02425
    phigh = 1 - plow
    if p < plow:
        q = sqrt(-2 * log(p))
        return (((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / \
               ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)
    if p > phigh:
        q = sqrt(-2 * log(1 - p))
        return -(((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / \
                ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)
    q = p - 0.5
    r = q * q
    return (((((a[0]*r+a[1])*r+a[2])*r+a[3])*r+a[4])*r+a[5])*q / \
           (((((b[0]*r+b[1])*r+b[2])*r+b[3])*r+b[4])*r+1)


def _norm_cdf(z: float) -> float:
    from math import erf, sqrt
    return 0.5 * (1 + erf(z / sqrt(2)))
