"""
Crypto Trend Engine — Qullamaggie + Squeeze & Release + Volatility Asymmetry.

Two methodologies are fused and applied per timeframe, then composited
across timeframes:

  1. Squeeze & Release + Volatility Asymmetry (port of malikmck's Pine v5).
     - Detects volatility contraction ("squeeze"), expansion ("release"),
       and hyper-squeezes (squeezeValue > 0 and rising N bars).
     - Asymmetry measure on a 0–100 scale (50 = balanced); we look for
       "attractive volasym" per the user spec:
         * above its MA
         * rising
         * near or above 50 but not too far (band, default [45, 70])
         * release within the last K bars following a hyper-squeeze

  2. Qullamaggie's three timeless setups
     (https://qullamaggie.com/my-3-timeless-setups-...):
       a. Breakout — leadership (top % over 1m/3m/6m), orderly
          consolidation (range tightening, higher lows), price surfing
          the rising 10/20 SMA, breakout of consolidation high, stop ≤ ADR.
       b. Episodic Pivot — gap up ≥ 10%, big volume (>= ~3x avg) on a
          stock that has not rallied 3–6 months (dormant base).
       c. Parabolic short/long — extended +50–100% in 3–5 consecutive
          days, stretched from 10/20 SMA — fades to MA bounce.

Each timeframe yields a signed trend score in [-100, +100] (positive =
long bias, negative = short / parabolic-short bias). MTF composite is
the equal-weighted average across the user-selected timeframes.

For crypto we also compute the score on the BTC-relative series
(symbol / BTC), so relative leadership against BTC is part of the rank.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

# Reuse MR's fetcher & timeframe list — same MTF grid (1m → 1mo, includes weekly).
from mr_engine import TIMEFRAMES, fetch_multitf, _true_range
from divergence import detect_divergence, bean_counter_snapshot, DIV_RECENCY


# ---------------------------------------------------------------------------
# Pine inputs — defaults mirror the supplied "S&R + Volasym" indicator
# ---------------------------------------------------------------------------

# Squeeze & Release
SR_CALC_PERIOD = 14
SR_SMOOTH_LEN = 7
SR_EMA_LEN = 14
SR_HYPER_LEN = 5

# Volatility Asymmetry
VA_PERIOD = 14
VA_SMOOTH_LEN = 7
VA_LOOKBACK = 5
VA_THRESHOLD = 5.0
VA_REF = "open"  # one of: open, prev_close, close, hl2, hlc3, ohlc4

# "Attractive volasym" criteria
VOLASYM_BAND_LOW = 45.0
VOLASYM_BAND_HIGH = 70.0
RELEASE_AFTER_SQUEEZE_WINDOW = 10   # bars: release must follow a hyper-squeeze within this window

# Qullamaggie params
QM_RET_1M_BARS = 21
QM_RET_3M_BARS = 63
QM_RET_6M_BARS = 126
QM_ADR_LEN = 20
QM_CONSOLIDATION_LEN = 20
QM_BREAKOUT_LOOKBACK = 20
QM_EP_GAP_PCT = 0.10
QM_EP_VOL_MULT = 3.0
QM_EP_DORMANT_BARS = 63
QM_EP_DORMANT_THRESH = 0.30        # |3m return| < 30% counts as "dormant"
QM_PARABOLIC_5D_PCT = 0.50         # +50% in 5 bars = extended
QM_PARABOLIC_CONSEC = 3            # 3 consecutive up bars

# Leadership thresholds (Qullamaggie: top 1-2% by 1m/3m/6m returns).
# Without a universe ranking we use absolute thresholds as a proxy.
QM_LEADER_1M = 0.30
QM_LEADER_3M = 0.50
QM_LEADER_6M = 1.00


# ---------------------------------------------------------------------------
# Indicator primitives
# ---------------------------------------------------------------------------


def _ema(s: pd.Series, length: int) -> pd.Series:
    return s.ewm(span=length, adjust=False, min_periods=length).mean()


def _ref_point(df: pd.DataFrame, kind: str) -> pd.Series:
    o, h, l, c = df["open"], df["high"], df["low"], df["close"]
    return {
        "open":        o,
        "prev_close":  c.shift(1),
        "close":       c,
        "hl2":         (h + l) / 2,
        "hlc3":        (h + l + c) / 3,
        "ohlc4":       (o + h + l + c) / 4,
    }.get(kind, o)


# ---------------------------------------------------------------------------
# Squeeze & Release  (Pine port)
# ---------------------------------------------------------------------------


@dataclass
class SRResult:
    squeeze_value: pd.Series
    squeeze_ma: pd.Series
    is_squeeze_cross: pd.Series          # crossover SV up through MA  (Pine "Squeeze")
    is_release_cross: pd.Series          # crossunder SV down through MA  (Pine "Release")
    is_hyper_squeeze: pd.Series          # SV > 0 AND rising over hyper_len bars
    release_after_squeeze: pd.Series     # release within K bars of a recent hyper-squeeze


def squeeze_release(df: pd.DataFrame, *,
                    calc_period: int = SR_CALC_PERIOD,
                    smooth_len: int = SR_SMOOTH_LEN,
                    ema_len: int = SR_EMA_LEN,
                    hyper_len: int = SR_HYPER_LEN,
                    release_window: int = RELEASE_AFTER_SQUEEZE_WINDOW,
                    enable_smoothing: bool = True) -> SRResult:
    h, l, c = df["high"], df["low"], df["close"]
    atr = _ema(_true_range(h, l, c), calc_period)
    ema_atr = _ema(atr, calc_period * 2)
    vol_indicator = ema_atr - atr
    ema_hl = _ema(h - l, calc_period * 2)
    raw = vol_indicator / ema_hl.replace(0, np.nan) * 100.0
    sv = _ema(raw, smooth_len) if enable_smoothing else raw
    sv_ma = _ema(sv, ema_len)

    cross_up = (sv > sv_ma) & (sv.shift(1) <= sv_ma.shift(1))
    cross_dn = (sv < sv_ma) & (sv.shift(1) >= sv_ma.shift(1))
    # ta.rising(sv, hyper_len): each of last hyper_len changes is positive.
    rising = pd.Series(True, index=sv.index)
    for k in range(1, hyper_len + 1):
        rising &= sv > sv.shift(k)
    hyper = (sv > 0) & rising.fillna(False)

    # release_after_squeeze: a release-cross where a hyper squeeze occurred
    # at any of the prior `release_window` bars.
    hyper_recent = hyper.rolling(release_window, min_periods=1).max().fillna(0).astype(bool)
    release_after = cross_dn & hyper_recent.shift(1).fillna(False)

    return SRResult(
        squeeze_value=sv, squeeze_ma=sv_ma,
        is_squeeze_cross=cross_up.fillna(False),
        is_release_cross=cross_dn.fillna(False),
        is_hyper_squeeze=hyper,
        release_after_squeeze=release_after,
    )


# ---------------------------------------------------------------------------
# Volatility Asymmetry  (Pine port)
# ---------------------------------------------------------------------------


@dataclass
class VolasymResult:
    value: pd.Series              # 0–100, 50 = balanced
    ma: pd.Series
    upper_event: pd.Series        # "upper asymmetry" boolean (bullish event)
    lower_event: pd.Series        # "lower asymmetry" boolean (bearish event)
    upward_roc: pd.Series
    downward_roc: pd.Series


def volatility_asymmetry(df: pd.DataFrame, *,
                         ref: str = VA_REF,
                         period: int = VA_PERIOD,
                         smooth_len: int = VA_SMOOTH_LEN,
                         lookback: int = VA_LOOKBACK,
                         threshold: float = VA_THRESHOLD,
                         enable_smoothing: bool = True) -> VolasymResult:
    h, l = df["high"], df["low"]
    rp = _ref_point(df, ref)
    upward = (h - rp).clip(lower=0)
    downward = (rp - l).clip(lower=0)
    up_atr = _ema(upward, period)
    dn_atr = _ema(downward, period)
    ratio = up_atr / (up_atr + dn_atr + 1e-4)
    val = _ema(ratio * 100.0, smooth_len) if enable_smoothing else ratio * 100.0
    val_ma = _ema(val, period)
    up_roc = up_atr.pct_change(lookback) * 100.0
    dn_roc = dn_atr.pct_change(lookback) * 100.0
    upper = (up_roc > threshold) & ((dn_roc.abs() < threshold / 2) | (dn_roc < 0))
    lower = (dn_roc > threshold) & ((up_roc.abs() < threshold / 2) | (up_roc < 0))
    return VolasymResult(
        value=val, ma=val_ma,
        upper_event=upper.fillna(False),
        lower_event=lower.fillna(False),
        upward_roc=up_roc, downward_roc=dn_roc,
    )


# ---------------------------------------------------------------------------
# Qullamaggie's three setups
# ---------------------------------------------------------------------------


@dataclass
class QMResult:
    # Leadership / prior move
    ret_1m: pd.Series
    ret_3m: pd.Series
    ret_6m: pd.Series
    adr_pct: pd.Series
    # Trend MAs (10/20/50 SMA per Qullamaggie)
    sma10: pd.Series
    sma20: pd.Series
    sma50: pd.Series
    above_10: pd.Series
    above_20: pd.Series
    above_50: pd.Series
    sma10_rising: pd.Series
    sma20_rising: pd.Series
    sma50_rising: pd.Series
    near_10: pd.Series          # close within 1 ADR of 10sma (surfing)
    near_20: pd.Series
    # Consolidation quality
    consolidating: pd.Series    # ATR contracting over last N bars
    higher_lows: pd.Series      # rolling-low making higher lows
    # Triggers
    breakout_20: pd.Series      # close > rolling 20-bar high (excl. current)
    breakout_50: pd.Series
    gap_pct: pd.Series
    ep_signal: pd.Series
    # Parabolic
    move_5d: pd.Series
    consec_up: pd.Series
    parabolic_extended: pd.Series   # candidate for short
    stretched_from_sma: pd.Series   # close > sma10 + 2 ADR (Qullamaggie's "stretched")


def qullamaggie_metrics(df: pd.DataFrame) -> QMResult:
    o, h, l, c, v = df["open"], df["high"], df["low"], df["close"], df["volume"]

    ret_1m = c.pct_change(QM_RET_1M_BARS)
    ret_3m = c.pct_change(QM_RET_3M_BARS)
    ret_6m = c.pct_change(QM_RET_6M_BARS)

    adr_pct = ((h - l) / c).rolling(QM_ADR_LEN).mean() * 100.0

    sma10 = c.rolling(10).mean()
    sma20 = c.rolling(20).mean()
    sma50 = c.rolling(50).mean()

    above_10 = (c > sma10)
    above_20 = (c > sma20)
    above_50 = (c > sma50)
    sma10_rising = sma10 > sma10.shift(5)
    sma20_rising = sma20 > sma20.shift(5)
    sma50_rising = sma50 > sma50.shift(10)

    # "Surfing" the MA: close within 1 ADR of the MA.
    adr_abs = ((h - l).rolling(QM_ADR_LEN).mean())
    near_10 = (c - sma10).abs() <= adr_abs
    near_20 = (c - sma20).abs() <= adr_abs

    # Consolidation: ATR is contracting over the last N bars AND price range
    # over those N bars is < 1.5 × ADR (range tightening).
    atr = _ema(_true_range(h, l, c), QM_CONSOLIDATION_LEN)
    atr_contracting = atr < atr.shift(QM_CONSOLIDATION_LEN)
    range_n = (h.rolling(QM_CONSOLIDATION_LEN).max() - l.rolling(QM_CONSOLIDATION_LEN).min())
    range_tight = range_n < adr_abs * 1.5 * QM_CONSOLIDATION_LEN / 10
    higher_lows = l.rolling(QM_CONSOLIDATION_LEN).min() > l.shift(QM_CONSOLIDATION_LEN).rolling(QM_CONSOLIDATION_LEN).min()
    consolidating = (atr_contracting & range_tight).fillna(False)

    # Breakout: close > rolling-N high excluding current bar.
    rolling_high_20 = h.shift(1).rolling(QM_BREAKOUT_LOOKBACK).max()
    rolling_high_50 = h.shift(1).rolling(50).max()
    breakout_20 = c > rolling_high_20
    breakout_50 = c > rolling_high_50

    # Episodic Pivot: gap up ≥ 10% with volume ≥ 3× 20-bar avg, on a
    # dormant base (|3m return| < 30%).
    gap_pct = (o / c.shift(1) - 1).fillna(0)
    vol_mult = v / v.rolling(20).mean()
    dormant = ret_3m.abs() < QM_EP_DORMANT_THRESH
    ep_signal = (gap_pct >= QM_EP_GAP_PCT) & (vol_mult >= QM_EP_VOL_MULT) & dormant.fillna(False)

    # Parabolic extended: +X% in 5 bars AND M consecutive up bars.
    move_5d = c.pct_change(5)
    up_bar = (c > c.shift(1)).astype(int)
    # consecutive-up count = running streak length
    consec_up = up_bar * (up_bar.groupby((up_bar != up_bar.shift()).cumsum()).cumcount() + 1)
    parabolic_extended = (move_5d >= QM_PARABOLIC_5D_PCT) & (consec_up >= QM_PARABOLIC_CONSEC)
    stretched_from_sma = (c - sma10) > (adr_abs * 2)

    return QMResult(
        ret_1m=ret_1m, ret_3m=ret_3m, ret_6m=ret_6m,
        adr_pct=adr_pct,
        sma10=sma10, sma20=sma20, sma50=sma50,
        above_10=above_10.fillna(False), above_20=above_20.fillna(False), above_50=above_50.fillna(False),
        sma10_rising=sma10_rising.fillna(False), sma20_rising=sma20_rising.fillna(False), sma50_rising=sma50_rising.fillna(False),
        near_10=near_10.fillna(False), near_20=near_20.fillna(False),
        consolidating=consolidating,
        higher_lows=higher_lows.fillna(False),
        breakout_20=breakout_20.fillna(False),
        breakout_50=breakout_50.fillna(False),
        gap_pct=gap_pct,
        ep_signal=ep_signal,
        move_5d=move_5d,
        consec_up=consec_up,
        parabolic_extended=parabolic_extended.fillna(False),
        stretched_from_sma=stretched_from_sma.fillna(False),
    )


# ---------------------------------------------------------------------------
# Per-timeframe composite trend score
# ---------------------------------------------------------------------------


@dataclass
class TrendScore:
    """Per-timeframe (last-bar) composite trend score and components."""
    long_score: float       # 0..100
    short_score: float      # 0..100  (parabolic short bias)
    net: float              # long - short, in [-100, 100]
    components: Dict[str, float]
    flags: Dict[str, bool]
    # The underlying methodology snapshots, latest bar.
    sr: Dict[str, float]
    volasym: Dict[str, float]
    qm: Dict[str, float]


def _last(s: pd.Series, default: float = 0.0) -> float:
    if s is None or len(s) == 0:
        return default
    v = s.iloc[-1]
    if isinstance(v, (bool, np.bool_)):
        return float(bool(v))
    if v is None or (isinstance(v, float) and (np.isnan(v) or np.isinf(v))):
        return default
    return float(v)


def trend_score(df: pd.DataFrame) -> TrendScore:
    """Compute the per-timeframe trend score for one OHLCV frame."""
    sr = squeeze_release(df)
    va = volatility_asymmetry(df)
    qm = qullamaggie_metrics(df)
    div = detect_divergence(df) if len(df) >= 30 else None

    va_val = _last(va.value, 50.0)
    va_ma  = _last(va.ma, 50.0)
    va_above = va_val > va_ma
    va_rising = va_val > _last(va.value.shift(3), va_val)
    va_in_band = VOLASYM_BAND_LOW <= va_val <= VOLASYM_BAND_HIGH

    # Was there a "release after squeeze" in the last window? Treat as a
    # bullish trigger because volatility just expanded out of contraction.
    post_release = bool(sr.release_after_squeeze.tail(RELEASE_AFTER_SQUEEZE_WINDOW).any())
    recent_hyper = bool(sr.is_hyper_squeeze.tail(RELEASE_AFTER_SQUEEZE_WINDOW).any())

    # ----- Long bias score (0..100) ----------------------------------
    comp: Dict[str, float] = {}
    flags: Dict[str, bool] = {}

    # Volasym attractiveness — 30 pts
    comp["volasym_above_ma"]   = 6.0 if va_above else 0.0
    comp["volasym_rising"]     = 6.0 if va_rising else 0.0
    comp["volasym_in_band"]    = 6.0 if va_in_band else 0.0
    comp["release_post_squeeze"] = 12.0 if post_release else 0.0

    # Leadership — 15 pts
    comp["leader_1m"] = 5.0 if _last(qm.ret_1m) >= QM_LEADER_1M else 0.0
    comp["leader_3m"] = 5.0 if _last(qm.ret_3m) >= QM_LEADER_3M else 0.0
    comp["leader_6m"] = 5.0 if _last(qm.ret_6m) >= QM_LEADER_6M else 0.0

    # Structure — 25 pts
    comp["above_10sma"] = 4.0 if _last(qm.above_10) else 0.0
    comp["above_20sma"] = 4.0 if _last(qm.above_20) else 0.0
    comp["above_50sma"] = 4.0 if _last(qm.above_50) else 0.0
    comp["sma_rising_stack"] = 4.0 if (_last(qm.sma10_rising) and _last(qm.sma20_rising) and _last(qm.sma50_rising)) else 0.0
    comp["surfing_10_20"] = 4.0 if (_last(qm.near_10) or _last(qm.near_20)) else 0.0
    comp["consolidating"] = 5.0 if _last(qm.consolidating) else 0.0

    # Triggers — 30 pts
    flags["breakout_20"] = bool(_last(qm.breakout_20))
    flags["breakout_50"] = bool(_last(qm.breakout_50))
    flags["ep_signal"]   = bool(_last(qm.ep_signal))
    flags["volasym_upper_event"] = bool(_last(va.upper_event))
    flags["volasym_lower_event"] = bool(_last(va.lower_event))
    comp["trig_breakout"] = 10.0 if flags["breakout_20"] else (5.0 if flags["breakout_50"] else 0.0)
    comp["trig_ep"]       = 12.0 if flags["ep_signal"] else 0.0
    comp["trig_va_upper"] = 8.0 if flags["volasym_upper_event"] else 0.0

    # Inflection — MFI divergence (Bean Counter) within last DIV_RECENCY bars.
    # Bullish inflection adds to long bias, bearish inflection adds to short
    # bias. Same single-TF detection as the Bean Counter; the MTF roll-up
    # happens implicitly when scores are averaged across timeframes.
    bull_inflection = bool(div.bull.tail(DIV_RECENCY).any()) if div is not None else False
    bear_inflection = bool(div.bear.tail(DIV_RECENCY).any()) if div is not None else False
    flags["inflection_bull"] = bull_inflection
    flags["inflection_bear"] = bear_inflection
    comp["inflection_bull"] = 10.0 if bull_inflection else 0.0

    long_score = float(sum(comp.values()))

    # ----- Short bias score (0..100) ---------------------------------
    short_comp: Dict[str, float] = {}
    short_comp["parabolic_extended"] = 30.0 if _last(qm.parabolic_extended) else 0.0
    short_comp["stretched_from_sma"] = 20.0 if _last(qm.stretched_from_sma) else 0.0
    short_comp["va_lower_event"]     = 20.0 if flags["volasym_lower_event"] else 0.0
    short_comp["va_below_50_falling"] = 15.0 if (va_val < 50 and not va_rising) else 0.0
    short_comp["hyper_squeeze_high"]  = 15.0 if (recent_hyper and va_val > 65) else 0.0
    short_comp["inflection_bear"]     = 10.0 if bear_inflection else 0.0

    short_score = float(sum(short_comp.values()))
    net = long_score - short_score

    components = {**{f"long.{k}": v for k, v in comp.items()},
                  **{f"short.{k}": v for k, v in short_comp.items()}}

    return TrendScore(
        long_score=long_score,
        short_score=short_score,
        net=net,
        components=components,
        flags=flags,
        sr={
            "squeeze_value": _last(sr.squeeze_value),
            "squeeze_ma": _last(sr.squeeze_ma),
            "is_squeeze_cross": bool(_last(sr.is_squeeze_cross)),
            "is_release_cross": bool(_last(sr.is_release_cross)),
            "is_hyper_squeeze": bool(_last(sr.is_hyper_squeeze)),
            "release_after_squeeze_window": post_release,
        },
        volasym={
            "value": va_val, "ma": va_ma,
            "above_ma": va_above, "rising": va_rising, "in_band": va_in_band,
        },
        qm={
            "ret_1m": _last(qm.ret_1m), "ret_3m": _last(qm.ret_3m), "ret_6m": _last(qm.ret_6m),
            "adr_pct": _last(qm.adr_pct),
            "above_10sma": _last(qm.above_10), "above_20sma": _last(qm.above_20), "above_50sma": _last(qm.above_50),
            "consolidating": _last(qm.consolidating),
            "breakout_20": _last(qm.breakout_20), "breakout_50": _last(qm.breakout_50),
            "ep_signal": _last(qm.ep_signal),
            "parabolic_extended": _last(qm.parabolic_extended),
            "stretched_from_sma": _last(qm.stretched_from_sma),
        },
    )


# ---------------------------------------------------------------------------
# Relative-to-BTC OHLCV
# ---------------------------------------------------------------------------


def make_relative(df: pd.DataFrame, ref: pd.DataFrame) -> Optional[pd.DataFrame]:
    """
    Build a relative OHLCV frame: symbol divided by `ref` (usually BTC).
    Indices are intersected; volume is carried over from the symbol (no
    meaningful ratio interpretation for volume).
    """
    idx = df.index.intersection(ref.index)
    if len(idx) < 60:
        return None
    a = df.loc[idx]
    b = ref.loc[idx]
    # Use the same bar's BTC close as the denominator for all of OHLC. This
    # is a slight approximation for intraday high/low extremes but keeps
    # OHLC internally consistent (no inversions of high < low).
    bc = b["close"].replace(0, np.nan)
    out = pd.DataFrame({
        "open":   a["open"]   / bc,
        "high":   a["high"]   / bc,
        "low":    a["low"]    / bc,
        "close":  a["close"]  / bc,
        "volume": a["volume"],
    }, index=idx).dropna()
    return out if len(out) >= 60 else None


# ---------------------------------------------------------------------------
# Multi-timeframe trend rank for a single symbol
# ---------------------------------------------------------------------------


@dataclass
class SymbolTrend:
    symbol: str
    timeframes: List[str]
    per_tf_abs: Dict[str, TrendScore]
    per_tf_rel: Dict[str, TrendScore]
    abs_net: float
    rel_net: float
    combined: float            # weighted average of abs_net and rel_net
    abs_long: float
    abs_short: float
    rel_long: float
    rel_short: float
    bar_count: Dict[str, int]


def mtf_trend(symbol: str, *,
              timeframes: Optional[List[Tuple[str, str]]] = None,
              btc_raw: Optional[Dict[str, pd.DataFrame]] = None,
              rel_weight: float = 0.5) -> Optional[SymbolTrend]:
    """
    Compute the multi-timeframe trend score for `symbol`.

    If `btc_raw` is provided (dict of {tf_label: BTC OHLCV}), the engine
    also computes the score on the BTC-relative series. The final
    `combined` score = rel_weight * rel_net + (1 - rel_weight) * abs_net.
    """
    raw = fetch_multitf(symbol, timeframes=timeframes)
    if not raw:
        return None
    tfs = list(raw.keys())

    per_abs: Dict[str, TrendScore] = {}
    per_rel: Dict[str, TrendScore] = {}
    bar_count: Dict[str, int] = {}
    for tf, df in raw.items():
        if len(df) < 60:
            continue
        bar_count[tf] = len(df)
        per_abs[tf] = trend_score(df)
        if btc_raw is not None and tf in btc_raw and symbol.upper() not in ("BTC-USD", "BTC"):
            rel = make_relative(df, btc_raw[tf])
            if rel is not None:
                per_rel[tf] = trend_score(rel)

    if not per_abs:
        return None

    abs_long = float(np.mean([s.long_score for s in per_abs.values()]))
    abs_short = float(np.mean([s.short_score for s in per_abs.values()]))
    abs_net = float(np.mean([s.net for s in per_abs.values()]))

    if per_rel:
        rel_long = float(np.mean([s.long_score for s in per_rel.values()]))
        rel_short = float(np.mean([s.short_score for s in per_rel.values()]))
        rel_net = float(np.mean([s.net for s in per_rel.values()]))
    else:
        rel_long = abs_long
        rel_short = abs_short
        rel_net = abs_net

    combined = rel_weight * rel_net + (1.0 - rel_weight) * abs_net

    return SymbolTrend(
        symbol=symbol,
        timeframes=list(per_abs.keys()),
        per_tf_abs=per_abs,
        per_tf_rel=per_rel,
        abs_net=abs_net, rel_net=rel_net, combined=combined,
        abs_long=abs_long, abs_short=abs_short,
        rel_long=rel_long, rel_short=rel_short,
        bar_count=bar_count,
    )


# ---------------------------------------------------------------------------
# Universe ranking
# ---------------------------------------------------------------------------


def rank_universe(symbols: List[str], *,
                  timeframes: Optional[List[Tuple[str, str]]] = None,
                  rel_weight: float = 0.5,
                  progress_cb=None) -> pd.DataFrame:
    """
    Score every symbol in `symbols` and return a ranked DataFrame.

    BTC is fetched once and reused as the relative-to reference for all
    other symbols. The result is sorted by `combined` desc.
    """
    btc_raw = fetch_multitf("BTC-USD", timeframes=timeframes) or {}

    rows: List[Dict[str, object]] = []
    n = len(symbols)
    for i, sym in enumerate(symbols, start=1):
        try:
            st_ = mtf_trend(sym, timeframes=timeframes, btc_raw=btc_raw, rel_weight=rel_weight)
        except Exception as e:                                   # pragma: no cover
            st_ = None
            err = type(e).__name__
        else:
            err = None
        if progress_cb is not None:
            progress_cb(i, n, sym)
        if st_ is None:
            rows.append({"symbol": sym, "error": err or "no_data"})
            continue

        # Surface a per-TF net column per timeframe so users can spot the
        # contributors. Use TF labels in the column names.
        per_tf_net = {f"abs_{tf}": st_.per_tf_abs[tf].net for tf in st_.per_tf_abs}
        per_tf_net_rel = {f"rel_{tf}": st_.per_tf_rel[tf].net for tf in st_.per_tf_rel}

        # Highlight active triggers from the highest-leverage timeframes.
        any_breakout = any(s.flags.get("breakout_20") for s in st_.per_tf_abs.values())
        any_ep       = any(s.flags.get("ep_signal") for s in st_.per_tf_abs.values())
        any_release  = any(s.sr.get("release_after_squeeze_window") for s in st_.per_tf_abs.values())
        any_va_attr  = any(s.volasym.get("above_ma") and s.volasym.get("rising") and s.volasym.get("in_band")
                            for s in st_.per_tf_abs.values())
        any_parabolic = any(s.qm.get("parabolic_extended") for s in st_.per_tf_abs.values())
        # Bean Counter inflection counts across TFs.
        bull_infl_tfs = sum(int(s.flags.get("inflection_bull", False)) for s in st_.per_tf_abs.values())
        bear_infl_tfs = sum(int(s.flags.get("inflection_bear", False)) for s in st_.per_tf_abs.values())

        rows.append({
            "symbol": sym,
            "combined": st_.combined,
            "abs_net": st_.abs_net,
            "rel_net": st_.rel_net,
            "abs_long": st_.abs_long,
            "abs_short": st_.abs_short,
            "rel_long": st_.rel_long,
            "rel_short": st_.rel_short,
            "breakout": any_breakout,
            "ep": any_ep,
            "release_after_squeeze": any_release,
            "volasym_attractive": any_va_attr,
            "parabolic_extended": any_parabolic,
            "inflection_bull_tfs": bull_infl_tfs,
            "inflection_bear_tfs": bear_infl_tfs,
            "inflection_net_tfs": bull_infl_tfs - bear_infl_tfs,
            **per_tf_net,
            **per_tf_net_rel,
        })
    df = pd.DataFrame(rows)
    if "combined" in df.columns:
        df = df.sort_values("combined", ascending=False, na_position="last").reset_index(drop=True)
    return df


# ---------------------------------------------------------------------------
# CLI demo
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(description="Crypto Trend engine — Qullamaggie + S&R + Volasym")
    p.add_argument("symbols", nargs="*", default=["BTC-USD", "ETH-USD", "SOL-USD"])
    p.add_argument("--rel-weight", type=float, default=0.5)
    args = p.parse_args()
    out = rank_universe(args.symbols, rel_weight=args.rel_weight,
                        progress_cb=lambda i, n, s: print(f"  [{i}/{n}] {s}"))
    print(out.to_string(index=False))
