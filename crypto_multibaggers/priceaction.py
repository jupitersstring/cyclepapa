"""Qualitative price action, made measurable.

Three schools, each as daily series computed from data up to and including
that day (so they can be read at day -1, on the pop day, or traded):

* Schabacker (Technical Analysis and Stock Market Profits, 1932; Edwards &
  Magee): rectangles, ascending / symmetrical triangles, falling wedges,
  double bottoms, inverse head and shoulders, flags, downtrend-line breaks,
  six-month resistance breaks, breakaway gaps and island bottoms, with
  volume confirmation.
* Japanese (Nison; Hosoda): candlestick reversal and continuation patterns,
  windows, Ichimoku Kinko Hyo (cloud position, TK cross, future cloud,
  Chikou, the "sanyaku" three-signal buy), Heikin-Ashi, three-line break and
  Renko.
* Dalton (Mind Over Markets; Markets in Profile), adapted to daily bars:
  value area and POC from a 20-day volume-weighted price distribution (each
  day's volume spread evenly over its range; the 70% value area is +/-1.04
  sd), value migration, acceptance above value, balance (bracket) duration
  and breakouts, one-timeframing, excess and poor extremes, trend days and
  range extension. Intraday constructs (initial balance, open types) need
  intraday data and are left out.

Crypto trades around the clock, so a "window" (gap) here is a day whose range
does not overlap the previous day's.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

# key -> (label, school, how it is read around day 0)
#   state : value on day -1        recent : any occurrence in days -10..-1
#   day0  : value on day 0         cont   : continuous value on day -1
PA_FEATURES: dict[str, tuple[str, str, str]] = {
    # Schabacker
    "sch_rect": ("Rectangle (congestion) in force", "Schabacker", "state"),
    "sch_rect_bo": ("Rectangle breakout on volume", "Schabacker", "recent"),
    "sch_tri": ("Ascending / symmetrical triangle in force", "Schabacker", "state"),
    "sch_tri_bo": ("Triangle breakout", "Schabacker", "recent"),
    "sch_wedge": ("Falling wedge in force", "Schabacker", "state"),
    "sch_wedge_bo": ("Falling-wedge breakout", "Schabacker", "recent"),
    "sch_dbl_setup": ("Double bottom formed, awaiting breakout", "Schabacker", "state"),
    "sch_dbl_bo": ("Double-bottom breakout", "Schabacker", "recent"),
    "sch_ihs_setup": ("Inverse head and shoulders formed", "Schabacker", "state"),
    "sch_ihs_bo": ("Inverse head-and-shoulders breakout", "Schabacker", "recent"),
    "sch_flag_bo": ("Flag / pennant breakout", "Schabacker", "recent"),
    "sch_dtl_bo": ("Downtrend-line break", "Schabacker", "recent"),
    "sch_res_bo": ("Six-month resistance break", "Schabacker", "recent"),
    "sch_breakaway": ("Breakaway gap out of congestion", "Schabacker", "recent"),
    "sch_island": ("Island bottom", "Schabacker", "recent"),
    "sch_rounding": ("Rounding bottom (saucer) score", "Schabacker", "cont"),
    "sch_any_bo": ("Any Schabacker breakout", "Schabacker", "recent"),
    # Japanese
    "jp_bull5": ("Bullish candle patterns, last 5 days", "Japanese", "cont"),
    "jp_bear5": ("Bearish candle patterns, last 5 days", "Japanese", "cont"),
    "jp_engulf": ("Bullish engulfing", "Japanese", "recent"),
    "jp_hammer": ("Hammer / inverted hammer after a decline", "Japanese", "recent"),
    "jp_morning": ("Morning star", "Japanese", "recent"),
    "jp_piercing": ("Piercing line", "Japanese", "recent"),
    "jp_3ws": ("Three white soldiers", "Japanese", "recent"),
    "jp_harami": ("Bullish harami", "Japanese", "recent"),
    "jp_window_up": ("Rising window", "Japanese", "recent"),
    "jp_shooting": ("Shooting star / hanging man", "Japanese", "recent"),
    "jp_bear_engulf": ("Bearish engulfing", "Japanese", "recent"),
    "jp_evening": ("Evening star / dark cloud cover", "Japanese", "recent"),
    "jp_3bc": ("Three black crows", "Japanese", "recent"),
    "ichi_cloud": ("Ichimoku: price vs cloud (+1 above, -1 below)", "Japanese", "cont"),
    "ichi_tk": ("Ichimoku: Tenkan above Kijun", "Japanese", "state"),
    "ichi_future": ("Ichimoku: future cloud bullish", "Japanese", "state"),
    "ichi_chikou": ("Ichimoku: Chikou above price 26 days ago", "Japanese", "state"),
    "ichi_sanyaku": ("Ichimoku: sanyaku kouten (all bullish)", "Japanese", "state"),
    "ichi_kumo_bo": ("Ichimoku: cloud breakout", "Japanese", "recent"),
    "ichi_tk_cross": ("Ichimoku: bullish TK cross", "Japanese", "recent"),
    "ichi_kijun_dist": ("Ichimoku: distance above Kijun (ATR)", "Japanese", "cont"),
    "ha_streak": ("Heikin-Ashi streak (+ bullish, - bearish)", "Japanese", "cont"),
    "ha_turn": ("Heikin-Ashi turn to bullish", "Japanese", "recent"),
    "tlb_state": ("Three-line break colour (+1 white)", "Japanese", "cont"),
    "tlb_turn": ("Three-line break turned white", "Japanese", "recent"),
    "renko_run": ("Renko run (+ up bricks, - down)", "Japanese", "cont"),
    "renko_turn": ("Renko turned up", "Japanese", "recent"),
    # Dalton
    "dal_pos": ("Close vs 20-day value (0 = POC, +/-0.5 = VA edge)", "Dalton", "cont"),
    "dal_migration": ("Value migration: 5-day POC vs prior value", "Dalton", "cont"),
    "dal_higher_value": ("Higher, non-overlapping value", "Dalton", "state"),
    "dal_accept": ("Acceptance: closes above prior value high, 5 days", "Dalton", "cont"),
    "dal_balance": ("Balance: days closing inside value", "Dalton", "cont"),
    "dal_balance_bo": ("Breakout from balance", "Dalton", "recent"),
    "dal_otf": ("One-timeframing up (consecutive higher lows)", "Dalton", "cont"),
    "dal_otf_dn": ("One-timeframing down (consecutive lower highs)", "Dalton", "cont"),
    "dal_excess_low": ("Excess (buying tail) at the 20-day low", "Dalton", "state"),
    "dal_poor_high": ("Poor high (no tail) at the 20-day high", "Dalton", "state"),
    "dal_trend_days": ("Up trend days, last 20", "Dalton", "cont"),
    "dal_va_width": ("Value-area width vs its 1-year median", "Dalton", "cont"),
    "dal_initiative": ("Initiative buying: open in value, close above it", "Dalton", "recent"),
}

# read on the pop day itself (known at that day's close)
PA_DAY0: dict[str, tuple[str, str, str]] = {
    "d0_sch_any_bo": ("Pop day completes a Schabacker breakout", "Schabacker", "day0"),
    "d0_sch_res_bo": ("Pop day breaks six-month resistance", "Schabacker", "day0"),
    "d0_sch_vol": ("Pop-day volume vs 20-day median", "Schabacker", "day0"),
    "d0_jp_marubozu": ("Pop day is a white marubozu (body >= 85% of range)", "Japanese", "day0"),
    "d0_jp_window": ("Pop day opens a rising window", "Japanese", "day0"),
    "d0_ichi_kumo_bo": ("Pop day breaks above the cloud", "Japanese", "day0"),
    "d0_ichi_sanyaku": ("Pop day closes with all Ichimoku signals bullish", "Japanese", "day0"),
    "d0_dal_trend_day": ("Pop day is a trend day (opens low, closes high, wide)", "Dalton", "day0"),
    "d0_dal_balance_bo": ("Pop day breaks out of balance", "Dalton", "day0"),
    "d0_dal_initiative": ("Pop day: open inside value, close above it", "Dalton", "day0"),
    "d0_dal_range_ext": ("Pop-day range vs 20-day average range", "Dalton", "day0"),
}

RECENT = 10


def _run_length(b: np.ndarray) -> np.ndarray:
    """Length of the current run of True values ending at each day."""
    out = np.zeros(len(b))
    run = 0
    for i, x in enumerate(b):
        run = run + 1 if x else 0
        out[i] = run
    return out


def _signed_streak(bull: np.ndarray, valid: np.ndarray) -> np.ndarray:
    out = np.full(len(bull), np.nan)
    run = 0
    for i in range(len(bull)):
        if not valid[i]:
            run = 0
            continue
        if bull[i]:
            run = run + 1 if run > 0 else 1
        else:
            run = run - 1 if run < 0 else -1
        out[i] = run
    return out


def _rolling_ols(y: pd.Series, w: int, minp: int) -> pd.Series:
    x = pd.Series(np.arange(len(y), dtype=float), index=y.index).where(y.notna())
    mx, my = x.rolling(w, min_periods=minp).mean(), y.rolling(w, min_periods=minp).mean()
    cov = (x * y).rolling(w, min_periods=minp).mean() - mx * my
    var = (x * x).rolling(w, min_periods=minp).mean() - mx * mx
    return cov / var


def series(o, h, l, c, v) -> dict[str, np.ndarray]:
    """All factors as daily series for one coin (numpy arrays of equal length)."""
    n = len(c)
    O, H, L, C, V = (pd.Series(np.asarray(x, float)) for x in (o, h, l, c, v))
    V = V.where(V > 0)
    lc = np.log(C)
    valid = C.notna().to_numpy()
    S: dict[str, np.ndarray] = {}

    tr = pd.concat([H - L, (H - C.shift(1)).abs(), (L - C.shift(1)).abs()], axis=1).max(axis=1, skipna=False)
    atr20 = tr.rolling(20, min_periods=15).mean()
    atrp = atr20 / C
    vmed20 = V.rolling(20, min_periods=10).median().shift(1)
    vol_ratio = V / vmed20
    rng = (H - L).where(H > L)
    avg_rng20 = rng.rolling(20, min_periods=15).mean()
    sma10 = C.rolling(10, min_periods=8).mean()

    # ------------------------------------------------------------ Schabacker
    hi20, lo20 = H.rolling(20, min_periods=15).max(), L.rolling(20, min_periods=15).min()
    rng20 = np.log(hi20 / lo20)
    rng_med = rng20.rolling(250, min_periods=120).median()
    net20 = (lc - lc.shift(19)).abs()
    rect = (rng20 <= 0.75 * rng_med) & (net20 <= 0.5 * rng20)
    rect_bo = rect.shift(1, fill_value=False) & (C > hi20.shift(1)) & (vol_ratio >= 1.5)
    S["sch_rect"] = rect.to_numpy(float)
    S["sch_rect_bo"] = rect_bo.to_numpy(float)

    sH = _rolling_ols(np.log(H), 30, 25) * 30 / atrp          # move of the highs over 30 days, in ATRs
    sL = _rolling_ols(np.log(L), 30, 25) * 30 / atrp
    tri = ((sH.abs() < 1.0) & (sL > 1.5)) | ((sH < -1.0) & (sL > 1.0))
    wedge = (sH < -1.5) & (sL < -0.5) & (sH < sL - 1.0)
    hi10p = H.rolling(10, min_periods=8).max().shift(1)
    S["sch_tri"] = tri.to_numpy(float)
    S["sch_tri_bo"] = (tri.shift(1, fill_value=False) & (C > hi10p)).to_numpy(float)
    S["sch_wedge"] = wedge.to_numpy(float)
    S["sch_wedge_bo"] = (wedge.shift(1, fill_value=False) & (C > hi10p)).to_numpy(float)

    # swing pivots (k = 5 days each side; a pivot at s is known at s + 5)
    k = 5
    h_, l_, c_ = H.to_numpy(), L.to_numpy(), C.to_numpy()
    lmin = L.rolling(2 * k + 1, center=True, min_periods=2 * k + 1).min().to_numpy()
    hmax = H.rolling(2 * k + 1, center=True, min_periods=2 * k + 1).max().to_numpy()
    lows = np.where(l_ == lmin)[0]
    highs = np.where(h_ == hmax)[0]
    dbl_bo, dbl_setup = np.zeros(n), np.zeros(n)
    ihs_bo, ihs_setup = np.zeros(n), np.zeros(n)
    dtl_bo = np.zeros(n)
    with np.errstate(invalid="ignore", divide="ignore"):
        for j in range(1, len(lows)):                                     # double bottom
            s1, s2 = lows[j - 1], lows[j]
            if not 10 <= s2 - s1 <= 120 or abs(l_[s2] / l_[s1] - 1) > 0.06:
                continue
            mids = highs[(highs > s1) & (highs < s2)]
            if not len(mids):
                continue
            neck = np.nanmax(h_[mids])
            if not neck >= 1.10 * max(l_[s1], l_[s2]):
                continue
            for t in range(s2 + k, min(n, s2 + 60)):
                if c_[t] > neck:
                    dbl_bo[t] = 1
                    break
                dbl_setup[t] = 1
        for j in range(2, len(lows)):                                     # inverse head and shoulders
            s1, s2, s3 = lows[j - 2], lows[j - 1], lows[j]
            if s3 - s1 > 150 or s2 - s1 < 5 or s3 - s2 < 5:
                continue
            if not (l_[s2] < 0.95 * min(l_[s1], l_[s3]) and abs(l_[s3] / l_[s1] - 1) <= 0.12):
                continue
            a_ = highs[(highs > s1) & (highs < s2)]
            b_ = highs[(highs > s2) & (highs < s3)]
            if not len(a_) or not len(b_):
                continue
            a, b = a_[np.nanargmax(h_[a_])], b_[np.nanargmax(h_[b_])]
            slope = (np.log(h_[b]) - np.log(h_[a])) / (b - a)
            for t in range(s3 + k, min(n, s3 + 60)):
                if np.log(c_[t]) > np.log(h_[b]) + slope * (t - b):
                    ihs_bo[t] = 1
                    break
                ihs_setup[t] = 1
        for j in range(1, len(highs)):                                    # downtrend line through two lower highs
            b = highs[j]
            prior = highs[(highs < b) & (highs >= b - 150)]
            if not len(prior):
                continue
            a = prior[np.nanargmax(h_[prior])]
            if not h_[a] > 1.05 * h_[b]:
                continue
            slope = (np.log(h_[b]) - np.log(h_[a])) / (b - a)
            stop = min(n, b + 120, (highs[j + 1] + k) if j + 1 < len(highs) else n)
            for t in range(b + k, stop):
                line_t = np.log(h_[b]) + slope * (t - b)
                if np.log(c_[t]) > line_t and np.log(c_[t - 1]) <= line_t - slope:
                    dtl_bo[t] = 1
                    break
    S["sch_dbl_setup"], S["sch_dbl_bo"] = dbl_setup, dbl_bo
    S["sch_ihs_setup"], S["sch_ihs_bo"] = ihs_setup, ihs_bo
    S["sch_dtl_bo"] = dtl_bo

    pole = lc.shift(6) - lc.shift(16)
    flag_rng = np.log(H.rolling(5, min_periods=4).max().shift(1) / L.rolling(5, min_periods=4).min().shift(1))
    drift = lc.shift(1) - lc.shift(6)
    vpole, vflag = V.rolling(10, min_periods=7).mean().shift(6), V.rolling(5, min_periods=4).mean().shift(1)
    flag_prev = (pole >= np.log(1.3)) & (flag_rng <= 0.5 * pole) & (drift <= 0.03) & (vflag < vpole)
    S["sch_flag_bo"] = (flag_prev & (C > H.rolling(5, min_periods=4).max().shift(1))).to_numpy(float)

    res = C.rolling(170, min_periods=120).max().shift(11)
    S["sch_res_bo"] = ((C > res) & (C.shift(1) <= res)).to_numpy(float)
    win_up, win_dn = (L > H.shift(1)), (H < L.shift(1))
    S["sch_breakaway"] = (rect.shift(1, fill_value=False) & win_up & (C > hi20.shift(1))).to_numpy(float)
    S["sch_island"] = (win_up & (win_dn.astype(float).rolling(15, min_periods=1).max().shift(1) > 0)).to_numpy(float)

    # rounding bottom: quadratic fit to 120 days of log closes (fixed design -> convolutions)
    W = 120
    x = np.linspace(-1, 1, W)
    y = lc.to_numpy()
    m = ~np.isnan(y)
    y0 = np.where(m, y, 0.0)
    conv = lambda a, kk: np.convolve(a, kk[::-1], mode="full")[:n]
    S0, S1, S2 = conv(y0, np.ones(W)), conv(y0, x), conv(y0, x ** 2)
    SYY = conv(y0 ** 2, np.ones(W))
    cnt = conv(m.astype(float), np.ones(W))
    A = np.array([[W, x.sum(), (x ** 2).sum()], [x.sum(), (x ** 2).sum(), (x ** 3).sum()],
                  [(x ** 2).sum(), (x ** 3).sum(), (x ** 4).sum()]])
    Ai = np.linalg.inv(A)
    beta = np.stack([S0, S1, S2], 1) @ Ai.T                                  # a, b, c per day
    sse = SYY - np.einsum("ij,ij->i", beta, np.stack([S0, S1, S2], 1))
    sst = SYY - S0 ** 2 / W
    with np.errstate(invalid="ignore", divide="ignore"):
        r2 = 1 - sse / sst
        tc = beta[:, 2] / np.sqrt(np.maximum(sse, 1e-12) / (W - 3) * Ai[2, 2])
        xv = -beta[:, 1] / (2 * beta[:, 2])
        yv = beta[:, 0] + beta[:, 1] * xv + beta[:, 2] * xv ** 2
        yend = beta[:, 0] + beta[:, 1] + beta[:, 2]
    ok = (cnt >= W) & (beta[:, 2] > 0) & (np.abs(xv) <= 0.5) & (r2 >= 0.5) & (yend - yv >= np.log(1.15))
    S["sch_rounding"] = np.where(cnt >= W, np.where(ok, np.clip(tc, 0, 50), 0.0), np.nan)

    any_bo = (S["sch_rect_bo"] + S["sch_tri_bo"] + S["sch_wedge_bo"] + S["sch_dbl_bo"] + S["sch_ihs_bo"]
              + S["sch_flag_bo"] + S["sch_dtl_bo"] + S["sch_res_bo"] + S["sch_breakaway"]) > 0
    S["sch_any_bo"] = any_bo.astype(float)
    S["sch_vol"] = vol_ratio.to_numpy()

    # ------------------------------------------------------------ Japanese candles
    body = C - O
    absb = body.abs()
    white, black = body > 0, body < 0
    ub, lb = H - np.maximum(O, C), np.minimum(O, C) - L
    down, up = C.shift(1) < sma10.shift(1), C.shift(1) > sma10.shift(1)
    longb = absb >= 0.5 * rng
    hammer_shape = (lb >= 0.6 * rng) & (ub <= 0.15 * rng) & (absb <= 0.35 * rng)
    star_shape = (ub >= 0.6 * rng) & (lb <= 0.15 * rng) & (absb <= 0.35 * rng)
    mid_prev = (O.shift(1) + C.shift(1)) / 2
    pats_bull = {
        "jp_engulf": black.shift(1, fill_value=False) & white & (C >= O.shift(1)) & (absb > absb.shift(1)),
        "jp_hammer": down & (hammer_shape | star_shape),
        "jp_morning": (black.shift(2, fill_value=False) & longb.shift(2, fill_value=False)
                       & (absb.shift(1) <= 0.3 * rng.shift(1)) & white & longb
                       & (C > (O.shift(2) + C.shift(2)) / 2) & (C.shift(3) < sma10.shift(3))),
        "jp_piercing": down & black.shift(1, fill_value=False) & longb.shift(1, fill_value=False) & white
                       & (C > mid_prev) & (C < O.shift(1)),
        "jp_3ws": (white & white.shift(1, fill_value=False) & white.shift(2, fill_value=False)
                   & (C > C.shift(1)) & (C.shift(1) > C.shift(2)) & longb & longb.shift(1, fill_value=False)
                   & longb.shift(2, fill_value=False) & (ub <= 0.3 * rng) & (ub.shift(1) <= 0.3 * rng.shift(1))),
        "jp_harami": down & black.shift(1, fill_value=False) & longb.shift(1, fill_value=False) & white
                     & (np.maximum(O, C) <= O.shift(1)) & (np.minimum(O, C) >= C.shift(1)),
        "jp_window_up": win_up,
    }
    pats_bear = {
        "jp_shooting": up & (star_shape | hammer_shape),
        "jp_bear_engulf": white.shift(1, fill_value=False) & black & (C <= O.shift(1)) & (absb > absb.shift(1)),
        "jp_evening": up & ((white.shift(2, fill_value=False) & longb.shift(2, fill_value=False)
                              & (absb.shift(1) <= 0.3 * rng.shift(1)) & black & longb
                              & (C < (O.shift(2) + C.shift(2)) / 2))
                             | (white.shift(1, fill_value=False) & longb.shift(1, fill_value=False) & black
                                & (C < mid_prev) & (C > O.shift(1)))),
        "jp_3bc": (black & black.shift(1, fill_value=False) & black.shift(2, fill_value=False)
                   & (C < C.shift(1)) & (C.shift(1) < C.shift(2)) & longb & longb.shift(1, fill_value=False)
                   & longb.shift(2, fill_value=False)),
        "jp_window_dn": win_dn,
    }
    for kk, p in {**pats_bull, **pats_bear}.items():
        S[kk] = p.fillna(False).to_numpy(float)
    bull = sum(pd.Series(S[kk]) for kk in pats_bull)
    bear = sum(pd.Series(S[kk]) for kk in pats_bear)
    S["jp_bull5"] = bull.rolling(5, min_periods=3).sum().to_numpy()
    S["jp_bear5"] = bear.rolling(5, min_periods=3).sum().to_numpy()
    S["jp_marubozu"] = (white & (absb >= 0.85 * rng)).to_numpy(float)

    # Ichimoku (9 / 26 / 52)
    tenkan = (H.rolling(9, min_periods=9).max() + L.rolling(9, min_periods=9).min()) / 2
    kijun = (H.rolling(26, min_periods=26).max() + L.rolling(26, min_periods=26).min()) / 2
    spanA = (tenkan + kijun) / 2
    spanB = (H.rolling(52, min_periods=52).max() + L.rolling(52, min_periods=52).min()) / 2
    top = np.maximum(spanA.shift(26), spanB.shift(26))
    bot = np.minimum(spanA.shift(26), spanB.shift(26))
    cloud = pd.Series(np.where(C > top, 1.0, np.where(C < bot, -1.0, 0.0))).where(top.notna() & C.notna())
    tk = (tenkan > kijun).where(kijun.notna())
    fut = (spanA > spanB).where(spanB.notna())
    chik = (C > C.shift(26)).where(C.shift(26).notna())
    sanyaku = (cloud == 1) & (tk == 1) & (fut == 1) & (chik == 1)
    S["ichi_cloud"] = cloud.to_numpy()
    S["ichi_tk"], S["ichi_future"], S["ichi_chikou"] = (x_.astype(float).to_numpy() for x_ in (tk, fut, chik))
    S["ichi_sanyaku"] = sanyaku.to_numpy(float)
    S["ichi_kumo_bo"] = ((cloud == 1) & (cloud.shift(1) < 1)).to_numpy(float)
    S["ichi_tk_cross"] = ((tk == 1) & (tk.shift(1) == 0)).to_numpy(float)
    S["ichi_kijun_dist"] = ((C - kijun) / atr20).to_numpy()
    S["kijun"] = kijun.to_numpy()

    # Heikin-Ashi
    ha_c = ((O + H + L + C) / 4).to_numpy()
    o_ = O.to_numpy()
    ha_o = np.full(n, np.nan)
    for i in range(n):
        if np.isnan(ha_c[i]):
            continue
        ha_o[i] = (o_[i] + c_[i]) / 2 if (i == 0 or np.isnan(ha_o[i - 1]) or np.isnan(ha_c[i - 1])) \
            else (ha_o[i - 1] + ha_c[i - 1]) / 2
    ha_bull = ha_c > ha_o
    S["ha_streak"] = _signed_streak(ha_bull, ~np.isnan(ha_o))
    hs = pd.Series(S["ha_streak"])
    S["ha_turn"] = ((hs == 1) & (hs.shift(1) <= -3)).to_numpy(float)

    # three-line break on closes
    tlb_state, tlb_turn = np.full(n, np.nan), np.zeros(n)
    lines: list[tuple[float, float, int]] = []          # (top, bottom, colour)
    ref = np.nan
    for i in range(n):
        ci = c_[i]
        if np.isnan(ci):
            continue
        if not lines:
            if np.isnan(ref):
                ref = ci
            elif ci != ref:
                lines.append((max(ci, ref), min(ci, ref), 1 if ci > ref else -1))
        else:
            topl, botl, col = lines[-1]
            last3 = lines[-3:]
            if col == 1:
                if ci > topl:
                    lines.append((ci, topl, 1))
                elif ci < min(b for _, b, _ in last3):
                    lines.append((botl, ci, -1))
            else:
                if ci < botl:
                    lines.append((botl, ci, -1))
                elif ci > max(t for t, _, _ in last3):
                    lines.append((ci, topl, 1))
                    tlb_turn[i] = 1
            lines = lines[-3:]
        if lines:
            tlb_state[i] = lines[-1][2]
    S["tlb_state"], S["tlb_turn"] = tlb_state, tlb_turn

    # Renko on log closes: 10% bricks, reversal needs two bricks
    b_ = np.log(1.10)
    renko, rturn = np.full(n, np.nan), np.zeros(n)
    base, direction, run = np.nan, 0, 0
    lcv = lc.to_numpy()
    for i in range(n):
        y_ = lcv[i]
        if np.isnan(y_):
            continue
        if np.isnan(base):
            base = y_
            continue
        while True:
            if direction >= 0 and y_ >= base + b_:
                base += b_
                run = run + 1 if direction == 1 else 1
                direction = 1
            elif direction <= 0 and y_ <= base - b_:
                base -= b_
                run = run + 1 if direction == -1 else 1
                direction = -1
            elif direction == 1 and y_ <= base - 2 * b_:
                base -= 2 * b_
                direction, run = -1, 1
            elif direction == -1 and y_ >= base + 2 * b_:
                base += 2 * b_
                direction, run = 1, 1
                rturn[i] = 1
            else:
                break
        renko[i] = direction * run
    S["renko_run"], S["renko_turn"] = renko, rturn

    # ------------------------------------------------------------ Dalton (daily-bar adaptation)
    tp = (H + L + C) / 3
    within = (H - L) ** 2 / 12

    def comp(w, lag):
        mp = max(3, int(0.75 * w))
        sv = V.rolling(w, min_periods=mp).sum()
        s1 = (tp * V).rolling(w, min_periods=mp).sum()
        s2 = ((tp ** 2 + within) * V).rolling(w, min_periods=mp).sum()
        mu = (s1 / sv).shift(lag)
        sd = np.sqrt(((s2 / sv) - (s1 / sv) ** 2).clip(lower=0)).shift(lag)
        return mu, mu - 1.04 * sd, mu + 1.04 * sd

    poc20, val20, vah20 = comp(20, 0)
    pocp, valp, vahp = comp(20, 5)          # prior value: days t-24..t-5
    poc5, val5, vah5 = comp(5, 0)
    width = vah20 - val20
    S["dal_pos"] = ((C - poc20) / width).to_numpy()
    S["dal_migration"] = ((poc5 - pocp) / (vahp - valp)).to_numpy()
    S["dal_higher_value"] = (val5 > vahp).where(vahp.notna()).astype(float).to_numpy()
    S["dal_accept"] = (C > vahp).astype(float).where(vahp.notna()).rolling(5, min_periods=3).sum().to_numpy()
    inside = ((C >= val20.shift(1)) & (C <= vah20.shift(1))).to_numpy()
    bal = _run_length(inside)
    S["dal_balance"] = np.where(val20.shift(1).notna(), bal, np.nan)
    bal_prev = pd.Series(bal).shift(1)
    S["dal_balance_bo"] = ((bal_prev >= 10) & (C > vah20.shift(1)) & (C > H.rolling(10, min_periods=8).max().shift(1))
                           ).to_numpy(float)
    S["dal_otf"] = _run_length(((L > L.shift(1)) & C.notna()).to_numpy())
    S["dal_otf_dn"] = _run_length(((H < H.shift(1)) & C.notna()).to_numpy())
    lshare, ushare = (lb / rng), (ub / rng)
    set_low = (L <= lo20) & lo20.notna()
    set_high = (H >= hi20) & hi20.notna()
    S["dal_excess_low"] = (lshare.where(set_low).ffill(limit=19) >= 0.4).astype(float).to_numpy()
    S["dal_poor_high"] = (ushare.where(set_high).ffill(limit=19) <= 0.1).astype(float).to_numpy()
    tday = (rng >= 1.5 * avg_rng20.shift(1)) & ((C - L) / rng >= 0.85) & ((O - L) / rng <= 0.35)
    S["dal_trend_day"] = tday.to_numpy(float)
    S["dal_trend_days"] = tday.astype(float).rolling(20, min_periods=15).sum().to_numpy()
    rw = width / poc20
    S["dal_va_width"] = (rw / rw.rolling(250, min_periods=120).median()).to_numpy()
    S["dal_initiative"] = ((O >= val20.shift(1)) & (O <= vah20.shift(1)) & (C > vah20.shift(1))).to_numpy(float)
    S["dal_range_ext"] = (rng / avg_rng20.shift(1)).to_numpy()

    # shared for trading rules
    S["atr20"] = atr20.to_numpy()
    S["donchian55"] = (C > C.rolling(55, min_periods=50).max().shift(1)).to_numpy(float)
    S["vol_ratio"] = vol_ratio.to_numpy()
    for kk in list(S):
        S[kk] = np.where(valid, S[kk], np.nan) if kk not in ("kijun", "atr20") else S[kk]
    return S


def sample(S: dict[str, np.ndarray], t: np.ndarray, day0: bool = False) -> dict[str, np.ndarray]:
    """Read the factors around day-0 indices t."""
    t = np.asarray(t, int)
    n = len(next(iter(S.values())))
    prev = np.clip(t - 1, 0, n - 1)
    out = {}
    for key, (_, _, how) in PA_FEATURES.items():
        x = S[key]
        if how in ("state", "cont"):
            out[key] = np.where(t - 1 >= 0, x[prev], np.nan)
        elif how == "recent":
            idx = t[:, None] + np.arange(-RECENT, 0)[None, :]
            ok = (idx >= 0) & (idx < n)
            g = np.where(ok, x[np.clip(idx, 0, n - 1)], np.nan)
            with np.errstate(all="ignore"):
                import warnings
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore", RuntimeWarning)
                    out[key] = np.nanmax(g, axis=1)
    if day0:
        tt = np.clip(t, 0, n - 1)
        inb = t < n
        d0 = {"d0_sch_any_bo": "sch_any_bo", "d0_sch_res_bo": "sch_res_bo", "d0_sch_vol": "sch_vol",
              "d0_jp_marubozu": "jp_marubozu", "d0_jp_window": "jp_window_up", "d0_ichi_kumo_bo": "ichi_kumo_bo",
              "d0_ichi_sanyaku": "ichi_sanyaku", "d0_dal_trend_day": "dal_trend_day",
              "d0_dal_balance_bo": "dal_balance_bo", "d0_dal_initiative": "dal_initiative",
              "d0_dal_range_ext": "dal_range_ext"}
        for key, src in d0.items():
            out[key] = np.where(inb, S[src][tt], np.nan)
    return out
