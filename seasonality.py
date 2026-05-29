"""
Weekly seasonality / calendar-anomaly engine.

For each asset and each week-of-year, compute the historical anomaly
metrics laid out in the user's framework:

  - Return-quality: mean, median, Sharpe, Sortino, t-stat, skew, win-rate
  - Payoff asymmetry: gain-to-pain (GPR), tail ratio, max loss
  - Volume confirmation: relative volume, return × vol_z, VA Sharpe,
    Volume-Adjusted GPR, Net Accumulation/Distribution
  - Volatility state: realized vol z-score, compression score
  - Liquidity: median dollar volume, cross-sectional percentile
  - Forward effect: mean next-1w / next-4w return after the window
  - Robustness: sample-size penalty √(n / (n + k)), subperiod stability

Per the user's preferred composite:

  Final = 0.30 × z(Tradable_Sharpe)
        + 0.25 × z(Volume_Adjusted_GPR)
        + 0.20 × z(Net_Accumulation)
        + 0.15 × z(Persistence)
        + 0.10 × z(Liquidity)

where  Tradable_Sharpe = Sharpe × √(n/(n+k)) × stability × liquidity_pct,
and  z(·)  is the cross-sectional z-score across the universe for that week.

For shorts, invert the return-linked components.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd


SAMPLE_SHRINKAGE_K = 20             # k in √(n / (n + k))
VOL_BASELINE_WINDOW = 52            # 1y rolling baseline for volume z-score
VOL_BASELINE_MIN = 10
PERSISTENCE_HORIZONS = (1, 4)       # forward weeks for persistence
N_SUBPERIODS = 2                    # stability via split-half Sharpe


# ---------------------------------------------------------------------------
# Building blocks
# ---------------------------------------------------------------------------


def _sharpe(returns: pd.Series) -> float:
    s = returns.std()
    return float(returns.mean() / s) if s > 0 else 0.0


def _sortino(returns: pd.Series) -> float:
    downside = returns[returns < 0]
    sd = downside.std() if len(downside) > 1 else returns.std()
    return float(returns.mean() / sd) if sd > 0 else 0.0


def _gain_to_pain(returns: pd.Series) -> float:
    pos = float(returns[returns > 0].sum())
    neg = float(returns[returns < 0].sum())
    if neg == 0:
        return float("inf") if pos > 0 else float("nan")
    return pos / abs(neg)


def _t_stat(returns: pd.Series) -> float:
    n = len(returns)
    if n < 2:
        return 0.0
    se = returns.std() / np.sqrt(n) if returns.std() > 0 else 0.0
    return float(returns.mean() / se) if se > 0 else 0.0


def _stability_sharpe(returns: pd.Series, n_sub: int = N_SUBPERIODS) -> float:
    """1 − CV of Sharpe across n_sub equal sub-periods, clipped to [0, 1]."""
    if len(returns) < n_sub * 3:
        return 0.5
    splits = np.array_split(returns.values, n_sub)
    sharpes = [(np.mean(s) / np.std(s)) if np.std(s) > 0 else 0.0 for s in splits]
    mean_s = float(np.mean(sharpes))
    std_s = float(np.std(sharpes))
    if abs(mean_s) < 1e-9:
        return 0.0
    cv = std_s / abs(mean_s)
    return float(np.clip(1.0 - cv, 0.0, 1.0))


# ---------------------------------------------------------------------------
# Per-asset weekly metrics
# ---------------------------------------------------------------------------


def weekly_metrics(weekly_df: pd.DataFrame) -> pd.DataFrame:
    """
    Compute per-week-of-year seasonality metrics from a weekly OHLCV
    DataFrame indexed by date (columns lower-case: close, volume).

    Returns a DataFrame indexed by week_of_year (1..53).
    """
    if not {"close", "volume"}.issubset(weekly_df.columns) or len(weekly_df) < 60:
        return pd.DataFrame()

    df = weekly_df[["close", "volume"]].dropna().copy()
    df["return"] = df["close"].pct_change()
    df["dollar_vol"] = df["close"] * df["volume"]
    df["vol_mean"] = df["volume"].rolling(VOL_BASELINE_WINDOW, min_periods=VOL_BASELINE_MIN).mean()
    df["vol_std"] = df["volume"].rolling(VOL_BASELINE_WINDOW, min_periods=VOL_BASELINE_MIN).std()
    df["vol_z"] = (df["volume"] - df["vol_mean"]) / df["vol_std"].replace(0, np.nan)
    df["week_of_year"] = df.index.isocalendar().week.astype(int)
    df["realized_vol_4w"] = df["return"].rolling(4).std()
    for h in PERSISTENCE_HORIZONS:
        df[f"fwd_{h}w_return"] = df["close"].pct_change(h).shift(-h)

    rows = []
    for woy in sorted(df["week_of_year"].unique()):
        grp = df[df["week_of_year"] == woy]
        rets = grp["return"].dropna()
        n = len(rets)
        if n < 3:
            continue

        # Aligned (return, vol_z) pairs for volume-adjusted metrics.
        rv = grp[["return", "vol_z"]].dropna()
        ra = rv["return"]
        vz = rv["vol_z"]
        vz_pos = vz.clip(lower=0)

        # Basic return quality
        sharpe = _sharpe(rets)
        sortino = _sortino(rets)
        gpr = _gain_to_pain(rets)
        win_rate = float((rets > 0).mean())
        mean_ret = float(rets.mean())
        median_ret = float(rets.median())
        skew = float(rets.skew()) if n > 3 else 0.0
        tstat = _t_stat(rets)

        # Tail / asymmetry
        top20 = rets.nlargest(max(1, n // 5)).mean()
        bot20 = rets.nsmallest(max(1, n // 5)).mean()
        tail_ratio = float(top20 / abs(bot20)) if bot20 < 0 else float("inf")
        max_loss = float(rets.min())

        # Volume-adjusted
        if len(ra) >= 3:
            ra_pos = ra.clip(lower=0)
            ra_neg = (-ra.clip(upper=0))
            accumulation = float((ra_pos * vz_pos).mean())
            distribution = float((ra_neg * vz_pos).mean())
            net_accumulation = accumulation - distribution
            ret_x_volz = float((ra * vz).mean())
            # VA Sharpe — uses log1p(max(vz, 0)) so quiet weeks don't contribute
            va_num = float((ra * np.log1p(vz_pos)).mean())
            va_sharpe = va_num / rets.std() if rets.std() > 0 else 0.0
            pos_sum = float((ra_pos * vz_pos).sum())
            neg_sum = float((ra_neg * vz_pos).sum())
            va_gpr = pos_sum / neg_sum if neg_sum > 0 else (float("inf") if pos_sum > 0 else float("nan"))
        else:
            accumulation = distribution = net_accumulation = 0.0
            ret_x_volz = va_sharpe = 0.0
            va_gpr = float("nan")

        # Volatility state
        vol_obs = grp["realized_vol_4w"].dropna()
        rv_baseline_mean = df["realized_vol_4w"].mean()
        rv_baseline_std = df["realized_vol_4w"].std() or 1.0
        vol_anomaly_z = float(((vol_obs.mean() - rv_baseline_mean) / rv_baseline_std)) if len(vol_obs) else 0.0
        compression_score = -vol_anomaly_z

        # Persistence (mean forward returns at end of this week)
        fwd1 = grp["fwd_1w_return"].dropna()
        fwd4 = grp["fwd_4w_return"].dropna()
        persistence_1w = float(fwd1.mean()) if len(fwd1) else 0.0
        persistence_4w = float(fwd4.mean()) if len(fwd4) else 0.0

        # Liquidity
        liquidity = float(grp["dollar_vol"].median())

        # Robustness
        sample_penalty = float(np.sqrt(n / (n + SAMPLE_SHRINKAGE_K)))
        stability = _stability_sharpe(rets)

        rows.append({
            "week_of_year": int(woy),
            "n_obs": n,
            "mean_return": mean_ret, "median_return": median_ret,
            "win_rate": win_rate, "skew": skew, "t_stat": tstat,
            "sharpe": sharpe, "sortino": sortino, "gpr": gpr,
            "tail_ratio": tail_ratio, "max_loss": max_loss,
            "accumulation": accumulation, "distribution": distribution,
            "net_accumulation": net_accumulation,
            "ret_x_volz": ret_x_volz, "va_sharpe": va_sharpe, "va_gpr": va_gpr,
            "vol_anomaly_z": vol_anomaly_z, "compression_score": compression_score,
            "persistence_1w": persistence_1w, "persistence_4w": persistence_4w,
            "liquidity": liquidity,
            "sample_penalty": sample_penalty, "stability": stability,
        })
    return pd.DataFrame(rows).set_index("week_of_year")


# ---------------------------------------------------------------------------
# Cross-sectional composite for a given week-of-year
# ---------------------------------------------------------------------------


def _safe_z(s: pd.Series) -> pd.Series:
    s = s.replace([np.inf, -np.inf], np.nan)
    std = s.std()
    if std == 0 or np.isnan(std):
        return pd.Series(0.0, index=s.index)
    return ((s - s.mean()) / std).fillna(0.0)


def composite_for_week(per_asset_metrics: Dict[str, pd.DataFrame],
                        week_of_year: int,
                        invert_for_short: bool = False) -> pd.DataFrame:
    """
    Build the cross-sectional composite anomaly score for `week_of_year`.

    For each asset, pulls the row for `week_of_year`, z-scores key metrics
    across the universe, and applies the user's composite weighting.
    """
    rows = []
    for sym, m in per_asset_metrics.items():
        if week_of_year not in m.index:
            continue
        r = m.loc[week_of_year].to_dict()
        r["symbol"] = sym
        rows.append(r)
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows).set_index("symbol")

    df["liquidity_pct"] = df["liquidity"].rank(pct=True)
    df["tradable_sharpe"] = (
        df["sharpe"] * df["sample_penalty"] * df["stability"] * df["liquidity_pct"]
    )

    df["va_gpr_capped"] = df["va_gpr"].replace([np.inf, -np.inf], np.nan)
    df["va_gpr_capped"] = df["va_gpr_capped"].fillna(df["va_gpr_capped"].median())

    df["gpr_capped"] = df["gpr"].replace([np.inf, -np.inf], np.nan)
    df["gpr_capped"] = df["gpr_capped"].fillna(df["gpr_capped"].median())

    df["z_tradable_sharpe"] = _safe_z(df["tradable_sharpe"])
    df["z_va_gpr"]          = _safe_z(df["va_gpr_capped"])
    df["z_net_accum"]       = _safe_z(df["net_accumulation"])
    df["z_persistence"]     = _safe_z(df["persistence_4w"])
    df["z_liquidity"]       = _safe_z(np.log1p(df["liquidity"]))

    df["composite"] = (
        0.30 * df["z_tradable_sharpe"]
        + 0.25 * df["z_va_gpr"]
        + 0.20 * df["z_net_accum"]
        + 0.15 * df["z_persistence"]
        + 0.10 * df["z_liquidity"]
    )
    if invert_for_short:
        df["composite"] = -df["composite"]

    return df.sort_values("composite", ascending=False)


# ---------------------------------------------------------------------------
# Walk-forward style: which assets currently have a strong active anomaly?
# ---------------------------------------------------------------------------


def current_week_of_year(reference: Optional[pd.Timestamp] = None) -> int:
    ts = reference if reference is not None else pd.Timestamp.now()
    return int(ts.isocalendar().week)
