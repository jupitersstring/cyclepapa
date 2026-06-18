"""
Ehlers / cycle strategies for the backtest.

Each function takes an OHLCV DataFrame and returns a position series
in {-1, 0, +1} aligned to the input index. -1 = short, 0 = flat,
+1 = long. The backtest harness converts position changes into trades
at next-bar open with realistic transaction costs.

Implements the prioritised punch-list from the deep-research synthesis:
  #7  Robot Wealth dominant-cycle-tuned BP   (PF 1.04-1.44 documented)
  #4  Market-Mode-Gated BP (+ optional MMI gate)
  #6' Ehlers Loops — quadrant + rotation on price+volume bandpass
  #2  Super Passband ±RMS envelope
  #6  Volume-BP zero-cross gated by price-BP sign
  #5  4-band sign agreement
  #1  Naive zero-cross BPT (Ehlers TASC Jul 2020)
  #3  Decycler-style fast/slow HP cross
"""

from __future__ import annotations

import math
from typing import Tuple

import numpy as np
import pandas as pd

from bandpass import ehlers_bandpass, four_bandpass, DEFAULT_BANDS
from trend_engine import volatility_asymmetry, squeeze_release


# ---------------------------------------------------------------------------
# Building-block filters
# ---------------------------------------------------------------------------


def super_smoother(price: pd.Series, length: int = 10) -> pd.Series:
    """Ehlers' SuperSmoother — 2-pole low-pass IIR."""
    a1 = math.exp(-1.414 * math.pi / length)
    b1 = 2 * a1 * math.cos(1.414 * math.pi / length)
    c2 = b1
    c3 = -a1 * a1
    c1 = 1 - c2 - c3
    p = price.ffill().fillna(0).to_numpy(dtype=float)
    out = np.zeros_like(p)
    for i in range(len(p)):
        prev1 = out[i - 1] if i >= 1 else 0.0
        prev2 = out[i - 2] if i >= 2 else 0.0
        p_avg = 0.5 * (p[i] + (p[i - 1] if i >= 1 else p[i]))
        out[i] = c1 * p_avg + c2 * prev1 + c3 * prev2
    return pd.Series(out, index=price.index)


def high_pass(price: pd.Series, length: int = 48) -> pd.Series:
    """Ehlers' 2-pole high-pass filter."""
    angle = 0.707 * 2 * math.pi / length
    alpha1 = (math.cos(angle) + math.sin(angle) - 1) / math.cos(angle)
    p = price.ffill().fillna(0).to_numpy(dtype=float)
    out = np.zeros_like(p)
    coef = (1 - alpha1 / 2) ** 2
    for i in range(len(p)):
        prev1 = out[i - 1] if i >= 1 else 0.0
        prev2 = out[i - 2] if i >= 2 else 0.0
        p1 = p[i - 1] if i >= 1 else p[i]
        p2 = p[i - 2] if i >= 2 else p[i]
        out[i] = coef * (p[i] - 2 * p1 + p2) + 2 * (1 - alpha1) * prev1 - (1 - alpha1) ** 2 * prev2
    return pd.Series(out, index=price.index)


def roofing_filter(price: pd.Series, hp_len: int = 48, ss_len: int = 10) -> pd.Series:
    """Roofing filter = HP filter then SuperSmoother. Passes ~10..48 bar cycles."""
    return super_smoother(high_pass(price, hp_len), ss_len)


def hilbert_dominant_period(price: pd.Series,
                             hp_len: int = 48, ss_len: int = 10,
                             min_period: int = 8, max_period: int = 50) -> pd.Series:
    """
    Approximate Ehlers' Hilbert Transform Dominant Cycle Period using
    scipy.signal.hilbert on the roofing-filtered series. Returns a
    smoothed per-bar period clamped to [min_period, max_period].
    """
    from scipy.signal import hilbert as sp_hilbert
    roofed = roofing_filter(price, hp_len, ss_len).fillna(0).to_numpy()
    analytic = sp_hilbert(roofed)
    phase = np.unwrap(np.angle(analytic))
    dphase = np.diff(phase, prepend=phase[0])
    dphase = np.where(np.abs(dphase) < 1e-9, 1e-9, dphase)
    period = np.abs(2 * np.pi / dphase)
    period = np.clip(period, min_period, max_period)
    s = pd.Series(period, index=price.index)
    return s.rolling(5).median().bfill().ffill()


def market_meanness_index(price: pd.Series, length: int = 200) -> pd.Series:
    """
    Market Meanness Index (Financial Hacker).
    Counts how often the price reverts to its rolling median; >75 indicates
    a mean-reverting regime, <50 indicates trend.
    """
    p = price.ffill()
    med = p.rolling(length).median()
    def _count(window):
        m = np.median(window)
        # count flips: previous > m and current < m, or vice versa, in window
        diffs = np.diff(np.sign(window - m))
        return float(100.0 * np.count_nonzero(diffs) / max(1, len(window) - 1))
    return p.rolling(length).apply(_count, raw=True)


def instantaneous_trendline(price: pd.Series, alpha: float = 0.07) -> pd.Series:
    """
    Ehlers' Instantaneous Trendline (Rocket Science Ch. 9). DC gain = 1.

        Trendline[t] = (α − α²/4)·P[t] + 0.5·α²·P[t-1] − (α − 0.75·α²)·P[t-2]
                       + 2(1−α)·Trendline[t-1] − (1−α)²·Trendline[t-2]
    """
    p = price.ffill().to_numpy(dtype=float)
    out = np.copy(p)
    a2 = alpha * alpha
    for i in range(7, len(p)):
        out[i] = ((alpha - a2 / 4) * p[i]
                  + 0.5 * a2 * p[i - 1]
                  - (alpha - 0.75 * a2) * p[i - 2]
                  + 2 * (1 - alpha) * out[i - 1]
                  - (1 - alpha) ** 2 * out[i - 2])
    return pd.Series(out, index=price.index)


# ---------------------------------------------------------------------------
# Position helpers
# ---------------------------------------------------------------------------


def _state_from_events(buy: pd.Series, sell: pd.Series, *, allow_short: bool = False) -> pd.Series:
    """
    Build a forward-filled position series from buy / sell event series.
    buy = True at long-entry bars; sell = True at long-exit (or short-entry
    if allow_short).
    """
    pos = pd.Series(0, index=buy.index, dtype=int)
    cur = 0
    for i, ts in enumerate(buy.index):
        b = bool(buy.iloc[i]) if i < len(buy) else False
        s = bool(sell.iloc[i]) if i < len(sell) else False
        if b and cur != 1:
            cur = 1
        elif s and cur != -1:
            cur = -1 if allow_short else 0
        pos.iloc[i] = cur
    return pos


# ---------------------------------------------------------------------------
# Strategy #1  —  Naive zero-cross BPT (Ehlers TASC Jul 2020)
# ---------------------------------------------------------------------------


def strat_naive_zero_cross(df: pd.DataFrame, period: int = 20, bandwidth: float = 0.1) -> pd.Series:
    """Long on BP crosses 0 up, short on BP crosses 0 down. Always in market."""
    flen = max(2, int(period * (1 - bandwidth)))
    slen = max(flen + 1, int(period * (1 + bandwidth)))
    bp = ehlers_bandpass(df["close"], flen, slen)
    cross_up = (bp > 0) & (bp.shift(1) <= 0)
    cross_dn = (bp < 0) & (bp.shift(1) >= 0)
    return _state_from_events(cross_up, cross_dn, allow_short=True)


# ---------------------------------------------------------------------------
# Strategy #2  —  Super Passband ± RMS envelope
# ---------------------------------------------------------------------------


def strat_super_passband(df: pd.DataFrame,
                          flen: int = 40, slen: int = 60,
                          rms_len: int = 50) -> pd.Series:
    """
    Ehlers Super Passband (TASC Jul 2016). RMS envelope replaces the zero line.

    Long entry:  PB crosses above -RMS
    Short entry: PB crosses below +RMS
    Long exit:   PB crosses below +RMS (TP) OR below -RMS (fail)
    Short exit:  mirror
    """
    bp = ehlers_bandpass(df["close"], flen, slen)
    rms = (bp ** 2).rolling(rms_len).mean().pow(0.5).fillna(bp.std())
    long_entry = (bp > -rms) & (bp.shift(1) <= -rms.shift(1))
    short_entry = (bp < rms) & (bp.shift(1) >= rms.shift(1))
    long_exit = (bp < rms) & (bp.shift(1) >= rms.shift(1))
    short_exit = (bp > -rms) & (bp.shift(1) <= -rms.shift(1))

    pos = pd.Series(0, index=df.index, dtype=int)
    cur = 0
    for i in range(len(df)):
        if cur == 0:
            if bool(long_entry.iloc[i]): cur = 1
            elif bool(short_entry.iloc[i]): cur = -1
        elif cur == 1:
            if bool(long_exit.iloc[i]): cur = 0
            if bool(short_entry.iloc[i]): cur = -1
        elif cur == -1:
            if bool(short_exit.iloc[i]): cur = 0
            if bool(long_entry.iloc[i]): cur = 1
        pos.iloc[i] = cur
    return pos


# ---------------------------------------------------------------------------
# Strategy #3  —  Decycler-style fast/slow HP cross
# ---------------------------------------------------------------------------


def strat_decycler_cross(df: pd.DataFrame,
                          fast_len: int = 100, slow_len: int = 125) -> pd.Series:
    """Long when fast HP > slow HP; short on opposite. Ehlers Decycler Osc."""
    fast = high_pass(df["close"], fast_len)
    slow = high_pass(df["close"], slow_len)
    long_state = (fast > slow).astype(int)
    pos = (long_state * 2 - 1).astype(int)         # +1 long when fast > slow else -1
    return pos


# ---------------------------------------------------------------------------
# Strategy #4  —  Market-Mode-Gated BP  (+ optional MMI gate)
# ---------------------------------------------------------------------------


def strat_market_mode_gated(df: pd.DataFrame,
                             bp_period: int = 30, bp_bw: float = 0.3,
                             trend_thresh: float = 0.05,
                             use_mmi: bool = True, mmi_thresh: float = 75.0,
                             mmi_len: int = 200) -> pd.Series:
    """
    Ehlers Rocket Science ch.11 Market Mode + optional MMI gate.

    Cycle Mode when |SmoothPrice - Itrend| / Price < 1.5%   AND  MMI < 75.
    In Cycle Mode trade BP zero-crosses; outside Cycle Mode go flat.
    """
    c = df["close"]
    smooth = (c + 2 * c.shift(1) + 2 * c.shift(2) + c.shift(3)) / 6.0
    itrend = instantaneous_trendline(smooth)
    separation = (smooth - itrend).abs() / c
    cycle_mode = separation < trend_thresh
    if use_mmi:
        mmi = market_meanness_index(c, mmi_len)
        cycle_mode = cycle_mode & (mmi < mmi_thresh)

    flen = max(2, int(bp_period * (1 - bp_bw)))
    slen = max(flen + 1, int(bp_period * (1 + bp_bw)))
    bp = ehlers_bandpass(c, flen, slen)
    cross_up = (bp > 0) & (bp.shift(1) <= 0)
    cross_dn = (bp < 0) & (bp.shift(1) >= 0)

    pos = pd.Series(0, index=df.index, dtype=int)
    cur = 0
    for i in range(len(df)):
        in_cycle = bool(cycle_mode.iloc[i]) if not pd.isna(cycle_mode.iloc[i]) else False
        if not in_cycle:
            cur = 0
        else:
            if bool(cross_up.iloc[i]):
                cur = 1
            elif bool(cross_dn.iloc[i]):
                cur = -1
        pos.iloc[i] = cur
    return pos


# ---------------------------------------------------------------------------
# Strategy #5  —  4-band sign agreement
# ---------------------------------------------------------------------------


def strat_4band_agreement(df: pd.DataFrame, bands=DEFAULT_BANDS,
                            min_agree: int = 4) -> pd.Series:
    """
    Long when at least `min_agree` of the bandpass outputs are > 0 (and
    strictly more positive than negative); short symmetrically. Default
    min_agree=4 = require all bands to agree.
    """
    bp = four_bandpass(df["close"], bands)
    n_pos = (bp > 0).sum(axis=1)
    n_neg = (bp < 0).sum(axis=1)
    pos = pd.Series(0, index=df.index, dtype=int)
    pos[(n_pos >= min_agree) & (n_pos > n_neg)] = 1
    pos[(n_neg >= min_agree) & (n_neg > n_pos)] = -1
    return pos


# ---------------------------------------------------------------------------
# Strategy #6  —  Volume-BP zero-cross gated by price-BP sign
# ---------------------------------------------------------------------------


def strat_volume_bp_gated(df: pd.DataFrame,
                            flen: int = 40, slen: int = 60) -> pd.Series:
    """
    Long when price BP > 0 AND volume BP crosses above 0; exit when
    volume BP crosses below 0. Short the inverse.
    """
    bp_p = ehlers_bandpass(df["close"], flen, slen)
    bp_v = ehlers_bandpass(df["volume"], flen, slen)
    vol_up = (bp_v > 0) & (bp_v.shift(1) <= 0)
    vol_dn = (bp_v < 0) & (bp_v.shift(1) >= 0)
    long_entry = vol_up & (bp_p > 0)
    short_entry = vol_dn & (bp_p < 0)
    long_exit = vol_dn
    short_exit = vol_up

    pos = pd.Series(0, index=df.index, dtype=int)
    cur = 0
    for i in range(len(df)):
        if cur == 0:
            if bool(long_entry.iloc[i]): cur = 1
            elif bool(short_entry.iloc[i]): cur = -1
        elif cur == 1:
            if bool(long_exit.iloc[i]): cur = 0
            if bool(short_entry.iloc[i]): cur = -1
        elif cur == -1:
            if bool(short_exit.iloc[i]): cur = 0
            if bool(long_entry.iloc[i]): cur = 1
        pos.iloc[i] = cur
    return pos


# ---------------------------------------------------------------------------
# Strategy #6' —  Ehlers Loops (quadrant + rotation)
# ---------------------------------------------------------------------------


def strat_ehlers_loops(df: pd.DataFrame,
                        hp_len: int = 125, ss_len: int = 10,
                        rms_len: int = 50) -> pd.Series:
    """
    Ehlers Loops (TASC Jun/Jul 2022). Plot filtered-price vs filtered-volume.
    Long  in Q1 (price+, volume+) with counter-clockwise rotation (volume leads).
    Short in Q3 (price-, volume-) with counter-clockwise rotation.
    Exit on quadrant flip into the opposite corner or rotation reverse.
    """
    fp = roofing_filter(df["close"], hp_len, ss_len)
    fv = roofing_filter(df["volume"], hp_len, ss_len)
    # RMS-normalize so both axes share a scale
    rms_p = (fp ** 2).rolling(rms_len).mean().pow(0.5).replace(0, np.nan)
    rms_v = (fv ** 2).rolling(rms_len).mean().pow(0.5).replace(0, np.nan)
    np_ = (fp / rms_p).fillna(0)
    nv = (fv / rms_v).fillna(0)
    phase = np.arctan2(nv, np_)               # angle in the (price, vol) plane
    dphase = pd.Series(np.unwrap(phase.values), index=df.index).diff().fillna(0)
    ccw = dphase > 0                          # counter-clockwise = volume leads

    in_q1 = (np_ > 0) & (nv > 0)
    in_q3 = (np_ < 0) & (nv < 0)
    long_entry = in_q1 & ccw
    short_entry = in_q3 & ccw
    long_exit = (np_ < 0) | (~ccw & (nv < 0))
    short_exit = (np_ > 0) | (~ccw & (nv > 0))

    pos = pd.Series(0, index=df.index, dtype=int)
    cur = 0
    for i in range(len(df)):
        if cur == 0:
            if bool(long_entry.iloc[i]): cur = 1
            elif bool(short_entry.iloc[i]): cur = -1
        elif cur == 1:
            if bool(long_exit.iloc[i]): cur = 0
            if bool(short_entry.iloc[i]): cur = -1
        elif cur == -1:
            if bool(short_exit.iloc[i]): cur = 0
            if bool(long_entry.iloc[i]): cur = 1
        pos.iloc[i] = cur
    return pos


# ---------------------------------------------------------------------------
# Strategy #7  —  Robot Wealth dominant-cycle-tuned BP   (THE BENCHMARK)
# ---------------------------------------------------------------------------


def strat_robot_wealth_dctuned(df: pd.DataFrame,
                                 delta: float = 0.3,
                                 dom_period_arg: int = 30,
                                 max_dom_period: float = 45.0) -> pd.Series:
    """
    Robot Wealth's "dominant-cycle tuned" Ehlers bandpass strategy.
    Reverse-trigger: long when trigger crosses BELOW BP, short when ABOVE.
    Gate: only signal while DomPeriod < 45.
    """
    c = df["close"]
    dom = hilbert_dominant_period(c, hp_len=70, ss_len=10,
                                   min_period=8, max_period=50)
    # Tune BP center to DomPeriod, bandwidth = delta × center
    bp = pd.Series(0.0, index=c.index)
    p = c.ffill().fillna(0).to_numpy(dtype=float)
    d = dom.to_numpy(dtype=float)
    out = np.zeros_like(p)
    for i in range(2, len(p)):
        center = max(8.0, min(50.0, d[i]))
        flen = max(2.0, center * (1 - delta))
        slen = max(flen + 1, center * (1 + delta))
        a1 = 5.0 / flen
        a2 = 5.0 / slen
        c1 = a1 - a2
        c2 = a2 * (1 - a1) - a1 * (1 - a2)
        c3 = (1 - a1) + (1 - a2)
        c4 = (1 - a1) * (1 - a2)
        out[i] = c1 * p[i] + c2 * p[i - 1] + c3 * out[i - 1] - c4 * out[i - 2]
    bp = pd.Series(out, index=c.index)
    trigger = 0.9 * bp.shift(1)
    # Reverse rule: long when trigger crosses BELOW BP
    long_entry = (trigger < bp) & (trigger.shift(1) >= bp.shift(1))
    short_entry = (trigger > bp) & (trigger.shift(1) <= bp.shift(1))
    in_gate = dom < max_dom_period

    pos = pd.Series(0, index=df.index, dtype=int)
    cur = 0
    for i in range(len(df)):
        if not bool(in_gate.iloc[i]):
            cur = 0
        else:
            if bool(long_entry.iloc[i]):
                cur = 1
            elif bool(short_entry.iloc[i]):
                cur = -1
        pos.iloc[i] = cur
    return pos


# ---------------------------------------------------------------------------
# Strategy registry
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Strategy #8  —  TD Demark 9 / 13 exhaustion signals
# ---------------------------------------------------------------------------


def _hold_position(events: pd.Series, exit_events: pd.Series,
                    max_hold: int, direction: int) -> pd.Series:
    """
    Convert point events into a held position for up to `max_hold` bars,
    exited early on `exit_events`. Returns a series of `direction` while
    held, 0 otherwise.
    """
    n = len(events)
    pos = np.zeros(n, dtype=int)
    bars_held = 0
    in_trade = False
    for i in range(n):
        if not in_trade:
            if bool(events.iloc[i]):
                in_trade = True
                bars_held = 0
                pos[i] = direction
        else:
            bars_held += 1
            if bars_held >= max_hold or bool(exit_events.iloc[i]):
                in_trade = False
                pos[i] = 0
            else:
                pos[i] = direction
    return pd.Series(pos, index=events.index)


def strat_td9_setup(df: pd.DataFrame, max_hold: int = 10) -> pd.Series:
    """
    Long on bull 9 setup completion (sell exhaustion → reversal up).
    Short on bear 9 setup completion (buy exhaustion → reversal down).
    Hold up to `max_hold` bars, exit early on opposite setup.
    """
    from mr_engine import td_sequential
    f = td_sequential(df)
    bull_9 = f.bull_count == 9
    bear_9 = f.bear_count == 9
    longs = _hold_position(bull_9, bear_9, max_hold, +1)
    shorts = _hold_position(bear_9, bull_9, max_hold, -1)
    return (longs + shorts).clip(-1, 1)


def strat_td9_perfected(df: pd.DataFrame, max_hold: int = 10) -> pd.Series:
    """TD9 setup with Ehlers' 'perfection' confirmation (stricter)."""
    from mr_engine import td_sequential
    f = td_sequential(df)
    buy_p = f.buy_perfect.astype(bool)
    sell_p = f.sell_perfect.astype(bool)
    longs = _hold_position(buy_p, sell_p, max_hold, +1)
    shorts = _hold_position(sell_p, buy_p, max_hold, -1)
    return (longs + shorts).clip(-1, 1)


def strat_td13_countdown(df: pd.DataFrame, max_hold: int = 20) -> pd.Series:
    """
    Long on 13-countdown buy (deep sell exhaustion → strong reversal up).
    Short on 13-countdown sell. Longer hold than 9-setup (countdown
    completes after 13+9=22 bars so the resulting move is bigger).
    """
    from mr_engine import td_sequential
    f = td_sequential(df)
    cd13_buy = f.cd_buy == 13
    cd13_sell = f.cd_sell == 13
    longs = _hold_position(cd13_buy, cd13_sell, max_hold, +1)
    shorts = _hold_position(cd13_sell, cd13_buy, max_hold, -1)
    return (longs + shorts).clip(-1, 1)


def strat_td_combined(df: pd.DataFrame, max_hold: int = 10) -> pd.Series:
    """Either 9-setup OR 13-countdown completion fires the entry."""
    from mr_engine import td_sequential
    f = td_sequential(df)
    buy_event = (f.bull_count == 9) | (f.cd_buy == 13)
    sell_event = (f.bear_count == 9) | (f.cd_sell == 13)
    longs = _hold_position(buy_event, sell_event, max_hold, +1)
    shorts = _hold_position(sell_event, buy_event, max_hold, -1)
    return (longs + shorts).clip(-1, 1)


def strat_4band_td_confluence(df: pd.DataFrame, bands=DEFAULT_BANDS,
                                min_agree: int = 4, td_hold: int = 10) -> pd.Series:
    """
    Confluence: take the 4-band agreement signal, but boost (skip the
    flat) when a TD 9 setup confirms the direction within the last
    `td_hold` bars. The 4-band signal is the carrier; TD acts as an
    "OR-in" extra entry trigger so we don't miss setups that the cycle
    stack hasn't yet flagged.
    """
    from mr_engine import td_sequential
    base = strat_4band_agreement(df, bands=bands, min_agree=min_agree)
    f = td_sequential(df)
    bull_9_recent = (f.bull_count == 9).rolling(td_hold, min_periods=1).max().fillna(0).astype(bool)
    bear_9_recent = (f.bear_count == 9).rolling(td_hold, min_periods=1).max().fillna(0).astype(bool)
    # Augment: flip to long if base flat AND fresh bull-9 AND price-bp(short) > 0
    bp = four_bandpass(df["close"], bands)
    bp1 = bp.iloc[:, 0]
    augmented_long = (base == 0) & bull_9_recent & (bp1 > 0)
    augmented_short = (base == 0) & bear_9_recent & (bp1 < 0)
    out = base.copy()
    out[augmented_long] = 1
    out[augmented_short] = -1
    return out


# ---------------------------------------------------------------------------
# Strategies #10  —  Volatility Asymmetry & Squeeze/Release (Pine port)
# ---------------------------------------------------------------------------


def strat_volasym_attractive(df: pd.DataFrame,
                                band_low: float = 45.0,
                                band_high: float = 70.0) -> pd.Series:
    """
    Continuous regime: long while the asymmetry value is above its MA AND
    rising over the last 3 bars AND in the [band_low, band_high] band.
    Short while value < MA AND falling AND < band_low.
    """
    va = volatility_asymmetry(df)
    above_ma = va.value > va.ma
    rising = va.value > va.value.shift(3)
    falling = va.value < va.value.shift(3)
    in_band = (va.value >= band_low) & (va.value <= band_high)
    below_band = va.value < band_low
    long_state = above_ma & rising & in_band
    short_state = (~above_ma) & falling & below_band
    pos = pd.Series(0, index=df.index, dtype=int)
    pos[long_state.fillna(False)] = 1
    pos[short_state.fillna(False)] = -1
    return pos


def strat_volasym_event(df: pd.DataFrame, max_hold: int = 10) -> pd.Series:
    """Point trigger: upper-asymmetry event → long, lower → short."""
    va = volatility_asymmetry(df)
    longs = _hold_position(va.upper_event, va.lower_event, max_hold, +1)
    shorts = _hold_position(va.lower_event, va.upper_event, max_hold, -1)
    return (longs + shorts).clip(-1, 1)


def strat_sr_release(df: pd.DataFrame, max_hold: int = 10) -> pd.Series:
    """Long on Release cross (vol expanding); flat or short on Squeeze cross."""
    sr = squeeze_release(df)
    longs = _hold_position(sr.is_release_cross, sr.is_squeeze_cross, max_hold, +1)
    return longs.clip(-1, 1)


def strat_release_after_squeeze(df: pd.DataFrame, max_hold: int = 20) -> pd.Series:
    """
    Long after a Release cross that follows a recent Hyper Squeeze
    (release_after_squeeze event = compressed-then-expanding setup).
    """
    sr = squeeze_release(df)
    flat = pd.Series(False, index=df.index)
    longs = _hold_position(sr.release_after_squeeze, flat, max_hold, +1)
    return longs


def strat_va_sr_combined(df: pd.DataFrame, max_hold: int = 15) -> pd.Series:
    """
    Confluence: long when (a) release_after_squeeze fired within last 10
    bars AND (b) volasym above its MA AND in [45, 70] band (direction
    cue). The S&R triggers the breakout entry; volasym confirms the side.
    """
    sr = squeeze_release(df)
    va = volatility_asymmetry(df)
    release_recent = sr.release_after_squeeze.rolling(10, min_periods=1).max().fillna(0).astype(bool)
    long_event = (release_recent
                   & (va.value > va.ma)
                   & (va.value >= 45) & (va.value <= 70))
    short_event = (release_recent
                    & (va.value < va.ma)
                    & (va.value < 45))
    longs = _hold_position(long_event, short_event, max_hold, +1)
    shorts = _hold_position(short_event, long_event, max_hold, -1)
    return (longs + shorts).clip(-1, 1)


def strat_4band_va_filter(df: pd.DataFrame, bands=DEFAULT_BANDS,
                            min_agree: int = 4) -> pd.Series:
    """
    4-band agreement gated by volasym sign: only act on the cycle signal
    when volasym agrees on direction (volasym > 50 to confirm long; < 50
    to confirm short). Should reduce whipsaw from cycle false-positives.
    """
    base = strat_4band_agreement(df, bands=bands, min_agree=min_agree)
    va = volatility_asymmetry(df)
    out = base.copy()
    out[(base == 1) & (va.value < 50)] = 0
    out[(base == -1) & (va.value > 50)] = 0
    return out


STRATEGIES = {
    "1_naive_zerocross":   (strat_naive_zero_cross, {}),
    "2_super_passband":    (strat_super_passband, {}),
    "3_decycler_cross":    (strat_decycler_cross, {}),
    "4_market_mode_gated": (strat_market_mode_gated, {"use_mmi": False}),
    "4_mode_mmi_gated":    (strat_market_mode_gated, {"use_mmi": True}),
    "5_4band_agreement":   (strat_4band_agreement, {}),
    "6_volume_bp_gated":   (strat_volume_bp_gated, {}),
    "6p_ehlers_loops":     (strat_ehlers_loops, {}),
    "7_rw_dctuned_bp":     (strat_robot_wealth_dctuned, {}),
    "8a_td9_setup":        (strat_td9_setup, {}),
    "8b_td9_perfected":    (strat_td9_perfected, {}),
    "8c_td13_countdown":   (strat_td13_countdown, {}),
    "8d_td_combined":      (strat_td_combined, {}),
    "9_4band_td_confluence": (strat_4band_td_confluence, {}),
}
