"""
MFI Divergence detector + "Mary Mount Bean Counter" MTF roll-up.

Direct port of two Pine indicators:
  - "MFI Divs v2" (Libertus / malikmck) — per-bar MFI divergence detector
    with Stochastic OB/OS confirmation.
  - "Mary Mount – Bean Counter" — MTF wrapper that counts bullish and
    bearish divergences across timeframes and tracks the diff.

Used by BOTH legs:
  - MR engine — as the "Net Divergence" measure (added to the ticked rank
    set per user request).
  - Trend engine — as "Inflection" components (turning-point context that
    nudges the trend score's net up for bullish inflections, down for
    bearish inflections).

Timeframes: we use the same 8-TF grid as the rest of the engine
(1m, 5m, 15m, 1h, 4h, 1d, 1w, 1mo). Weekly is included by default per
the user's "add weekly to the Bean Counter" instruction.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional, Tuple

import numpy as np
import pandas as pd


# Pine defaults
DIV_LEN       = 13     # MFI length
DIV_OB        = 75     # stoch OB
DIV_OS        = 25     # stoch OS
DIV_PERIOD_K  = 14     # stoch period
DIV_SMOOTH_K  = 3      # stoch smoothing
DIV_LOOKBACK  = 10     # divergence pivot lookback
DIV_MA_LEN    = 5      # bean counter MA length

# Snapshot recency: a divergence within this many bars on a TF counts as
# "active" for the snapshot rank. Pine's MTF uses just the latest bar
# (recency=1); we default to a small recency window since the ranker
# triggers on signals that are still relevant, not strictly on-bar.
DIV_RECENCY   = 3


# ---------------------------------------------------------------------------
# Indicator primitives
# ---------------------------------------------------------------------------


def mfi(df: pd.DataFrame, length: int = DIV_LEN) -> pd.Series:
    """
    Standard Money Flow Index on HLC3 — matches Pine's `ta.mfi(hlc3, len)`.
    """
    tp = (df["high"] + df["low"] + df["close"]) / 3.0
    raw = tp * df["volume"]
    pos = raw.where(tp > tp.shift(1), 0.0)
    neg = raw.where(tp < tp.shift(1), 0.0)
    pos_sum = pos.rolling(length).sum()
    neg_sum = neg.rolling(length).sum()
    mfr = pos_sum / neg_sum.replace(0, np.nan)
    return (100.0 - 100.0 / (1.0 + mfr)).fillna(50.0)


def stoch_smoothed(df: pd.DataFrame,
                   period_k: int = DIV_PERIOD_K,
                   smooth_k: int = DIV_SMOOTH_K) -> pd.Series:
    """SMA-smoothed Stochastic %K — matches Pine `ta.sma(ta.stoch(...), smoothK)`."""
    lo = df["low"].rolling(period_k).min()
    hi = df["high"].rolling(period_k).max()
    raw_k = 100.0 * (df["close"] - lo) / (hi - lo).replace(0, np.nan)
    return raw_k.rolling(smooth_k).mean()


# ---------------------------------------------------------------------------
# Divergence detection
# ---------------------------------------------------------------------------


@dataclass
class DivResult:
    bull: pd.Series          # 0/1 — bullish divergence (OS-confirmed)
    bear: pd.Series          # 0/1 — bearish divergence (OB-confirmed)
    mfi_value: pd.Series
    stoch_value: pd.Series


def detect_divergence(df: pd.DataFrame, *,
                      length: int = DIV_LEN,
                      ob: int = DIV_OB, os: int = DIV_OS,
                      period_k: int = DIV_PERIOD_K,
                      smooth_k: int = DIV_SMOOTH_K,
                      lookback: int = DIV_LOOKBACK) -> DivResult:
    """
    Port of the Pine divergence detector. Returns per-bar 0/1 booleans for
    bullish and bearish divergence confirmed by Stochastic OS / OB.
    """
    mfi_v = mfi(df, length)
    stoch_v = stoch_smoothed(df, period_k, smooth_k)
    n = len(df)
    close = df["close"].to_numpy(dtype=float)
    mfi_arr = mfi_v.to_numpy(dtype=float)

    max_px = np.nan
    max_mfi = np.nan
    min_px = np.nan
    min_mfi = np.nan
    max_px_arr = np.full(n, np.nan)
    max_mfi_arr = np.full(n, np.nan)
    min_px_arr = np.full(n, np.nan)
    min_mfi_arr = np.full(n, np.nan)

    for i in range(n):
        if i >= lookback - 1:
            window = mfi_arr[i - lookback + 1: i + 1]
            if np.all(np.isnan(window)):
                hb = lb = -1
            else:
                # bars-ago of highest/lowest MFI in the window (0 = current bar)
                hb = (lookback - 1) - int(np.nanargmax(window))
                lb = (lookback - 1) - int(np.nanargmin(window))
            if hb == 0:
                max_px = close[i]
                max_mfi = mfi_arr[i]
            if lb == 0:
                min_px = close[i]
                min_mfi = mfi_arr[i]

        # Extend running extremes only in the favored direction (Pine
        # behavior: max ratchets up, min ratchets down — until a new
        # pivot resets it).
        if not np.isnan(max_px) and close[i] > max_px:
            max_px = close[i]
        if not np.isnan(max_mfi) and mfi_arr[i] > max_mfi:
            max_mfi = mfi_arr[i]
        if not np.isnan(min_px) and close[i] < min_px:
            min_px = close[i]
        if not np.isnan(min_mfi) and mfi_arr[i] < min_mfi:
            min_mfi = mfi_arr[i]

        max_px_arr[i] = max_px
        max_mfi_arr[i] = max_mfi
        min_px_arr[i] = min_px
        min_mfi_arr[i] = min_mfi

    max_px_s = pd.Series(max_px_arr, index=df.index)
    max_mfi_s = pd.Series(max_mfi_arr, index=df.index)
    min_px_s = pd.Series(min_px_arr, index=df.index)
    min_mfi_s = pd.Series(min_mfi_arr, index=df.index)

    div_bear_raw = (
        (max_px_s.shift(1) > max_px_s.shift(2))
        & (mfi_v.shift(1) < max_mfi_s)
        & (mfi_v <= mfi_v.shift(1))
    )
    div_bull_raw = (
        (min_px_s.shift(1) < min_px_s.shift(2))
        & (mfi_v.shift(1) > min_mfi_s)
        & (mfi_v >= mfi_v.shift(1))
    )

    is_ob = (stoch_v.shift(1) > ob) | (stoch_v > ob)
    is_os = (stoch_v.shift(1) < os) | (stoch_v < os)

    bull = (div_bull_raw & is_os).fillna(False).astype(int)
    bear = (div_bear_raw & is_ob).fillna(False).astype(int)

    return DivResult(bull=bull, bear=bear, mfi_value=mfi_v, stoch_value=stoch_v)


# ---------------------------------------------------------------------------
# Bean Counter (MTF)
# ---------------------------------------------------------------------------


@dataclass
class BeanCounterSnapshot:
    """Latest-bar Bean Counter rollup across timeframes."""
    per_tf: Dict[str, Dict[str, int]]   # {tf: {bull: 0/1, bear: 0/1}}
    bull_count: int
    bear_count: int
    diff: int                            # bull - bear
    bull_prop: float                     # bull_count / n_tfs * 100
    bear_prop: float
    diff_prop: float                     # bull_prop - bear_prop


def bean_counter_snapshot(per_tf_dfs: Dict[str, pd.DataFrame], *,
                          recency: int = DIV_RECENCY,
                          min_bars: int = 30) -> BeanCounterSnapshot:
    """
    Compute the Bean Counter snapshot. A divergence on TF `tf` counts if it
    fired anywhere in the last `recency` bars of that timeframe. The 8-TF
    grid we use (1m, 5m, 15m, 1h, 4h, 1d, 1w, 1mo) includes Weekly per the
    user's request to add weekly to the Bean Counter.
    """
    per_tf: Dict[str, Dict[str, int]] = {}
    bull_total = 0
    bear_total = 0
    n_eff = 0
    for tf, df in per_tf_dfs.items():
        if len(df) < min_bars:
            continue
        d = detect_divergence(df)
        b = int(bool(d.bull.tail(recency).any()))
        s = int(bool(d.bear.tail(recency).any()))
        per_tf[tf] = {"bull": b, "bear": s}
        bull_total += b
        bear_total += s
        n_eff += 1
    if n_eff == 0:
        return BeanCounterSnapshot(per_tf={}, bull_count=0, bear_count=0,
                                   diff=0, bull_prop=0.0, bear_prop=0.0,
                                   diff_prop=0.0)
    return BeanCounterSnapshot(
        per_tf=per_tf,
        bull_count=bull_total,
        bear_count=bear_total,
        diff=bull_total - bear_total,
        bull_prop=bull_total / n_eff * 100.0,
        bear_prop=bear_total / n_eff * 100.0,
        diff_prop=(bull_total - bear_total) / n_eff * 100.0,
    )


def bean_counter_history(per_tf_dfs: Dict[str, pd.DataFrame], *,
                          ma_len: int = DIV_MA_LEN,
                          min_bars: int = 30) -> Optional[pd.DataFrame]:
    """
    Build a historical Bean Counter on the highest-frequency grid. Each
    lower-TF divergence series is forward-filled (0/1 step) onto the
    highest-freq index, then summed across TFs. Output columns:
    `bull_count`, `bear_count`, `diff`, plus MA-smoothed versions.
    """
    usable: Dict[str, DivResult] = {}
    for tf, df in per_tf_dfs.items():
        if len(df) < min_bars:
            continue
        usable[tf] = detect_divergence(df)
    if not usable:
        return None
    base_tf = max(usable.keys(), key=lambda tf: len(per_tf_dfs[tf].index))
    base_idx = per_tf_dfs[base_tf].index

    def _align(s: pd.Series) -> pd.Series:
        return s.reindex(base_idx, method="ffill").fillna(0)

    bull_sum = sum(_align(usable[tf].bull) for tf in usable)
    bear_sum = sum(_align(usable[tf].bear) for tf in usable)
    out = pd.DataFrame(index=base_idx)
    out["bull_count"] = bull_sum
    out["bear_count"] = bear_sum
    out["diff"] = out["bull_count"] - out["bear_count"]
    out["bull_ma"] = out["bull_count"].rolling(ma_len).mean()
    out["bear_ma"] = out["bear_count"].rolling(ma_len).mean()
    out["diff_ma"] = out["diff"].rolling(ma_len).mean()
    return out
