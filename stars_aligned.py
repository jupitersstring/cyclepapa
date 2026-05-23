"""
Stars Aligned — D/W/M Bullish Confluence Rank (four schools)

Synthesises four setup schools per timeframe (D / W / M):
  - Weinstein   (W_T): Stage 2 leadership / regime
  - Qullamaggie (Q_T): max(breakout, episodic pivot, parabolic-long-bounce)
  - DeMark      (D_T): exhaustion + bullish confirmation timing
  - Darvas      (DA_T): pyramiding box-top breakout from confirmed boxes

Confluence_T = 0.70 * geomean(W^0.25 Q^0.30 D^0.20 DA^0.25) * 100
             + 0.30 * min(W, Q, D, DA)

Setup ranks (DailyRank / WeeklyRank / MonthlyRank) per user spec.

Labels: A+ / A / B / C / Reject (hard vetoes).

Usage: python3 stars_aligned.py [region]
"""

import sys
import warnings

import numpy as np
import pandas as pd

from screen import (
    REGIONS, fetch_universe, fetch_ohlc, fetch_fx, currency_for_ticker,
)

warnings.filterwarnings("ignore")

ATR_MAX_STOP = 1.5


# ---------- DeMark TD Sequential -------------------------------------------

def _setup_count(close: pd.Series, side: str) -> np.ndarray:
    n = len(close); out = np.zeros(n); arr = close.values
    for i in range(4, n):
        cond = (arr[i] < arr[i-4]) if side == "buy" else (arr[i] > arr[i-4])
        out[i] = (out[i-1] + 1) if cond and out[i-1] < 9 else (1 if cond else 0)
    return out


def _trend_line(setup9, ref_extrema, close, side):
    n = len(close); out = np.zeros(n)
    cl = close.values; ext = ref_extrema.values
    for i in range(n):
        prev = out[i-1] if i > 0 else 0.0
        if setup9[i] == 9:
            out[i] = ext[i]
        elif side == "high" and cl[i] > prev:
            out[i] = 0.0
        elif side == "low" and prev > 0 and cl[i] < prev:
            out[i] = 0.0
        else:
            out[i] = prev
    return out


def _countdown(close, high, low, buy_setup, sell_setup, high_tl, low_tl):
    n = len(close); bcd = np.zeros(n); scd = np.zeros(n)
    bcd8 = np.zeros(n); scd8 = np.zeros(n)
    cl = close.values; hi = high.values; lo = low.values
    for i in range(2, n):
        prev_b, prev_s = bcd[i-1], scd[i-1]
        prev_b8, prev_s8 = bcd8[i-1], scd8[i-1]
        is_bcd = cl[i] < lo[i-2]; is_scd = cl[i] > hi[i-2]
        non_q_b = is_bcd and abs(prev_b) == 12 and lo[i] > prev_b8
        non_q_s = is_scd and abs(prev_s) == 12 and hi[i] < prev_s8
        if buy_setup[i] == 9:
            bcd[i] = 1 if is_bcd else 0
        elif sell_setup[i] == 9 or high_tl[i] == 0:
            bcd[i] = 14
        elif non_q_b:
            bcd[i] = -12
        elif is_bcd:
            bcd[i] = abs(prev_b) + 1
        else:
            bcd[i] = -abs(prev_b)
        bcd8[i] = cl[i] if bcd[i] == 8 else prev_b8
        if sell_setup[i] == 9:
            scd[i] = 1 if is_scd else 0
        elif buy_setup[i] == 9 or low_tl[i] == 0:
            scd[i] = 14
        elif non_q_s:
            scd[i] = -12
        elif is_scd:
            scd[i] = abs(prev_s) + 1
        else:
            scd[i] = -abs(prev_s)
        scd8[i] = cl[i] if scd[i] == 8 else prev_s8
    return bcd, scd


def td_sequential(bars: pd.DataFrame) -> dict:
    if len(bars) < 30:
        return {}
    c = bars["Close"]; h = bars["High"]; l = bars["Low"]
    buy_setup = _setup_count(c, "buy")
    sell_setup = _setup_count(c, "sell")
    high_tl = _trend_line(buy_setup, h.rolling(9).max(), c, "high")
    low_tl = _trend_line(sell_setup, l.rolling(9).min(), c, "low")
    bcd, scd = _countdown(c, h, l, buy_setup, sell_setup, high_tl, low_tl)
    perfected_buy9 = False
    for k in range(max(8, len(buy_setup) - 5), len(buy_setup)):
        if buy_setup[k] == 9:
            perfected_buy9 = perfected_buy9 or (
                min(l.iloc[k-1], l.iloc[k]) <= min(l.iloc[k-3], l.iloc[k-2])
            )
    last_idx = len(buy_setup) - 1
    def bars_since(arr, target):
        return next(
            (last_idx - i for i in range(last_idx, max(-1, last_idx - 9), -1) if arr[i] == target),
            None,
        )
    return dict(
        buy_setup_now=int(buy_setup[-1]),
        sell_setup_now=int(sell_setup[-1]),
        perfected_buy9_recent=bool(perfected_buy9),
        bars_since_buy9=bars_since(buy_setup, 9),
        bars_since_buy13=bars_since(bcd, 13),
        bars_since_sell9=bars_since(sell_setup, 9),
        bars_since_sell13=bars_since(scd, 13),
        bullish_flip=bool(c.iloc[-1] > c.iloc[-5]) if len(c) > 5 else False,
        range_flip=bool(c.iloc[-1] > h.iloc[-3]) if len(c) > 3 else False,
        close_gt_swing=bool(c.iloc[-1] > h.iloc[-20:].max() * 0.999) if len(c) >= 20 else False,
        tdst_resistance=float(high_tl[-1]),
        tdst_support=float(low_tl[-1]),
        close_below_tdst_support=bool(low_tl[-1] > 0 and c.iloc[-1] < low_tl[-1]),
    )


# ---------- Darvas Box ------------------------------------------------------

def darvas_boxes(bars: pd.DataFrame, max_lookback: int = 252, confirm_days: int = 3) -> dict:
    """Boxes confirmed by 3-day non-penetration rule (Darvas pp.195-197)."""
    if len(bars) < 30:
        return {"boxes": [], "n_boxes": 0}
    sub = bars.iloc[-max_lookback:].copy()
    h = sub["High"].values; l = sub["Low"].values
    n = len(sub); boxes = []
    i = 0
    while i < n:
        top_candidate, top_idx, confirm, j = h[i], i, 0, i + 1
        while j < n and confirm < confirm_days:
            if h[j] > top_candidate:
                top_candidate, top_idx, confirm = h[j], j, 0
            else:
                confirm += 1
            j += 1
        if confirm < confirm_days:
            break
        k = top_idx + 1
        bottom_candidate = l[k] if k < n else l[top_idx]
        bottom_idx = k if k < n else top_idx
        confirm_b = 0
        while k < n and confirm_b < confirm_days:
            if l[k] < bottom_candidate:
                bottom_candidate, bottom_idx, confirm_b = l[k], k, 0
            elif h[k] > top_candidate:
                break
            else:
                confirm_b += 1
            k += 1
        if confirm_b >= confirm_days:
            boxes.append(dict(top=float(top_candidate), bottom=float(bottom_candidate),
                              top_idx=int(top_idx), bottom_idx=int(bottom_idx)))
        i = max(k, top_idx + 1)

    ascending = all(
        boxes[i]["bottom"] >= boxes[i-1]["bottom"] * 0.98
        for i in range(1, len(boxes))
    ) if len(boxes) >= 2 else (len(boxes) == 1)
    px = float(bars["Close"].iloc[-1])
    last_high_252 = float(bars["High"].iloc[-min(252, len(bars)):].max())
    last_box = boxes[-1] if boxes else None
    in_last_box = bool(last_box and last_box["bottom"] <= px <= last_box["top"] * 1.05) if last_box else False
    dist_to_box_top = ((last_box["top"] / px) - 1) if last_box else np.nan
    above_historic_high = bool(px >= last_high_252 * 0.995)
    return dict(
        boxes=boxes, n_boxes=len(boxes),
        ascending_pyramid=bool(ascending), last_box=last_box,
        in_last_box=in_last_box,
        dist_to_box_top=float(dist_to_box_top) if not np.isnan(dist_to_box_top) else None,
        above_historic_high=above_historic_high,
    )


def darvas_score(bars: pd.DataFrame, tf: str) -> dict:
    min_bars = {"D": 60, "W": 30, "M": 12}[tf]
    if len(bars) < min_bars:
        return {"DA": np.nan}
    lookback = {"D": 252, "W": 156, "M": 60}[tf]
    box = darvas_boxes(bars, max_lookback=lookback)
    if box["n_boxes"] == 0:
        return {"DA": 30.0, **box}
    last = box["last_box"]
    px = float(bars["Close"].iloc[-1])
    pyramid = float(box["ascending_pyramid"])
    boxes_n = float(np.clip(box["n_boxes"] / 3, 0, 1))
    in_box = float(box["in_last_box"])
    at_breakout = (
        1.0 if px >= last["top"] * 0.995 else
        np.clip(1 - (last["top"] / px - 1) / 0.05, 0, 1)
    )
    historic_high = float(box["above_historic_high"])
    stop = last["bottom"]
    h = bars["High"]; l = bars["Low"]; c = bars["Close"]
    tr = pd.concat([(h - l).abs(), (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
    atr = tr.rolling(14).mean().iloc[-1]
    risk = float(np.clip(1 - max(0, (px - stop)) / max(1e-9, atr * ATR_MAX_STOP), 0, 1))
    DA = 100 * (
        0.20 * pyramid + 0.15 * boxes_n + 0.20 * at_breakout +
        0.15 * historic_high + 0.15 * in_box + 0.15 * risk
    )
    return dict(
        DA=float(DA), pyramid=pyramid, boxes_n=boxes_n, at_breakout=float(at_breakout),
        historic_high=historic_high, in_box=in_box, risk_darvas=risk,
        box_top=last["top"], box_bottom=last["bottom"],
        dist_to_box_top=box["dist_to_box_top"], n_boxes=box["n_boxes"],
        ascending_pyramid=box["ascending_pyramid"],
    )


# ---------- Weinstein Stage 2 ----------------------------------------------

def weinstein_score(bars: pd.DataFrame, idx_close: pd.Series, tf: str) -> dict:
    ma_long_n, ma_short_n = {"D": (150, 50), "W": (30, 10), "M": (10, 3)}[tf]
    c = bars["Close"]; h = bars["High"]; v = bars.get("Volume")
    if len(c) < ma_long_n + 10:
        return {"W": np.nan}
    ma_long = c.rolling(ma_long_n).mean()
    ma_short = c.rolling(ma_short_n).mean()
    ma_long_slope = ma_long.diff(5).iloc[-1]
    px = float(c.iloc[-1])
    higher_highs = c.iloc[-30:].max() > c.iloc[-60:-30].max() if len(c) >= 60 else True
    higher_lows = c.iloc[-30:].min() > c.iloc[-60:-30].min() if len(c) >= 60 else True
    trend = np.mean([
        px > ma_long.iloc[-1], ma_long_slope > 0,
        ma_short.iloc[-1] > ma_long.iloc[-1], px > ma_short.iloc[-1],
        higher_highs and higher_lows,
    ])
    look = min(50, len(c) - 1)
    resistance = c.iloc[-look-1:-1].max()
    close_pos = (px - c.iloc[-20:].min()) / max(1e-9, c.iloc[-20:].max() - c.iloc[-20:].min())
    base_length_ok = (c.iloc[-look:].std() / max(1e-9, c.iloc[-look:].mean())) < 0.15
    base_depth_ok = (c.iloc[-look:].max() / max(1e-9, c.iloc[-look:].min()) - 1) < 0.50
    not_extended = px <= resistance * 1.10
    breakout = np.mean([
        px > resistance * 0.995, close_pos > 0.65,
        bool(base_length_ok), bool(base_depth_ok), not_extended,
    ])
    if len(c) >= 130 and len(idx_close) >= 130:
        common = c.index.intersection(idx_close.index)
        rs_series = (c.reindex(common) / idx_close.reindex(common)).dropna()
        if len(rs_series) >= 130:
            roc13 = rs_series.iloc[-1] / rs_series.iloc[-65] - 1
            roc26 = rs_series.iloc[-1] / rs_series.iloc[-130] - 1
            rs_score = float(np.clip(0.5 * (1 if roc13 > 0 else 0) +
                                      0.5 * (1 if roc26 > 0 else 0), 0, 1))
        else:
            rs_score = 0.5
    else:
        rs_score = 0.5
    if v is not None and len(v.dropna()) >= 20:
        vol_score = float(np.clip(v.iloc[-1] / max(1e-9, v.iloc[-20:].mean()) / 2, 0, 1))
    else:
        vol_score = 0.5
    high_252 = c.iloc[-252:].max() if len(c) >= 252 else c.max()
    no_overhead = float(np.clip(1 + ((px / high_252) - 1) * 6, 0, 1))
    group_score = 0.5
    W = 100 * (
        0.25 * trend + 0.20 * breakout + 0.20 * rs_score +
        0.15 * vol_score + 0.10 * group_score + 0.10 * no_overhead
    )
    return dict(
        W=float(W), trend=float(trend), breakout=float(breakout),
        rs=rs_score, vol=vol_score, no_overhead=float(no_overhead),
        above_ma_long=bool(px > ma_long.iloc[-1]),
        ma_long_slope_pos=bool(ma_long_slope > 0),
        rs_positive=bool(rs_score >= 0.5),
        breakout_volume_ok=bool(vol_score >= 0.4),
    )


# ---------- Qullamaggie ----------------------------------------------------

def _detect_stair_steps(close: pd.Series, tf: str) -> dict:
    if tf == "D":
        thrust_lookback, base_min, base_max = range(15, 90), 10, 60
    elif tf == "W":
        thrust_lookback, base_min, base_max = range(4, 26), 3, 12
    else:
        thrust_lookback, base_min, base_max = range(3, 12), 2, 6
    if len(close) < max(thrust_lookback) + base_max + 5:
        return dict(thrust=0.0, base_len=0, base_tightness=0.0)
    best = dict(thrust=0.0, base_len=0, base_tightness=0.0)
    for base_len in range(base_min, base_max + 1):
        if len(close) < base_len + max(thrust_lookback) + 5:
            continue
        base = close.iloc[-base_len:]
        rng = (base.max() / base.min() - 1) if base.min() > 0 else 1
        if rng > 0.35:
            continue
        pre = close.iloc[-base_len - max(thrust_lookback):-base_len]
        if len(pre) < 5:
            continue
        thrust = pre.iloc[-1] / pre.min() - 1
        if thrust > best["thrust"]:
            best = dict(thrust=float(thrust), base_len=int(base_len),
                        base_tightness=float(1 - rng / 0.35))
    return best


def qullamaggie_score(bars: pd.DataFrame, idx_close: pd.Series, tf: str) -> dict:
    c = bars["Close"]; h = bars["High"]; l = bars["Low"]; v = bars.get("Volume")
    min_bars = {"D": 100, "W": 30, "M": 18}[tf]
    if len(c) < min_bars:
        return {"Q": np.nan, "QBO": np.nan, "QEP": np.nan, "QPL": np.nan}
    px = float(c.iloc[-1])

    def roc(n):
        return (c.iloc[-1] / c.iloc[-n] - 1) if len(c) > n else np.nan
    if tf == "D":
        roc_1, roc_2, roc_3 = roc(21), roc(63), roc(126)
    elif tf == "W":
        roc_1, roc_2, roc_3 = roc(4), roc(13), roc(26)
    else:
        roc_1, roc_2, roc_3 = roc(1), roc(3), roc(6)
    leader = np.mean([
        float(np.clip(roc_1 / 0.10, 0, 1)) if not np.isnan(roc_1) else 0.5,
        float(np.clip(roc_2 / 0.30, 0, 1)) if not np.isnan(roc_2) else 0.5,
        float(np.clip(roc_3 / 0.50, 0, 1)) if not np.isnan(roc_3) else 0.5,
    ])

    step = _detect_stair_steps(c, tf)
    prior_thrust = float(np.clip(step["thrust"] / 0.30, 0, 1))
    base_len = max(step["base_len"], {"D": 20, "W": 6, "M": 4}[tf])
    win = c.iloc[-base_len:]
    higher_lows = (win.diff().clip(lower=0) > 0).sum() / max(1, len(win) - 1) if len(win) >= 4 else 0.5
    if v is not None and len(v.dropna()) >= base_len * 2:
        v_recent = v.iloc[-base_len:].mean()
        v_prior = v.iloc[-base_len*2:-base_len].mean()
        vol_dryup = float(np.clip((v_prior / max(1e-9, v_recent) - 1) / 0.30, 0, 1))
    else:
        vol_dryup = 0.5
    consolidation = np.mean([step["base_tightness"], higher_lows, vol_dryup])

    if len(c) >= 50:
        ma10 = c.rolling(10).mean().iloc[-1]
        ma20 = c.rolling(20).mean().iloc[-1]
        ma50 = c.rolling(50).mean().iloc[-1]
        ma_surf = np.mean([px > ma10, px > ma20, ma10 > ma20, px > ma50])
    else:
        ma_surf = 0.5

    pivot = c.iloc[-base_len-1:-1].max() if len(c) > base_len + 1 else c.iloc[-1]
    close_near_high = (px - l.iloc[-5:].min()) / max(1e-9, h.iloc[-5:].max() - l.iloc[-5:].min())
    if v is not None and len(v.dropna()) >= 20:
        vol_exp = float(np.clip(v.iloc[-1] / max(1e-9, v.iloc[-20:].mean()), 0, 2) / 2)
    else:
        vol_exp = 0.5
    trigger = np.mean([
        float(px > pivot * 0.995), float(close_near_high), vol_exp,
    ])

    tr = pd.concat([(h - l).abs(), (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
    atr = tr.rolling(14).mean().iloc[-1]
    stop = l.iloc[-3:].min()
    risk = float(np.clip(1 - max(0, (px - stop)) / max(1e-9, atr * ATR_MAX_STOP), 0, 1))

    QBO = 100 * (
        0.20 * leader + 0.20 * prior_thrust + 0.20 * consolidation +
        0.15 * ma_surf + 0.15 * trigger + 0.10 * risk
    )

    QEP = 0.0
    if tf == "D" and len(c) >= 2:
        open_ = bars["Open"].iloc[-1] if "Open" in bars.columns else c.iloc[-1]
        gap = float(open_ / c.iloc[-2] - 1)
        gap_ok = float(np.clip(gap / 0.10, 0, 1))
        if v is not None and len(v.dropna()) >= 50:
            vol_shock = float(np.clip(v.iloc[-1] / max(1e-9, v.iloc[-50:].mean()) / 3, 0, 1))
        else:
            vol_shock = 0.0
        if "Open" in bars.columns:
            recent_gaps = bars["Open"].iloc[-60:-1] / c.iloc[-61:-2].values - 1
            recent_ep_count = int((recent_gaps >= 0.10).sum())
        else:
            recent_ep_count = 0
        ep_penalty = 1 - np.clip(recent_ep_count / 3, 0, 1) * 0.5
        QEP = 100 * ep_penalty * (
            0.25 * gap_ok + 0.25 * vol_shock + 0.15 * 0.5 +
            0.15 * consolidation + 0.10 * trigger + 0.10 * risk
        )

    QPL = 0.0
    if tf == "D" and len(c) >= 15:
        drawdown = px / c.iloc[-15:-1].max() - 1
        if drawdown < -0.40:
            green_today = c.iloc[-1] > c.iloc[-2]
            volume_up = (v.iloc[-1] / v.iloc[-20:].mean()) > 1.5 if v is not None else False
            QPL = 100 * (
                0.40 * float(green_today) + 0.30 * float(volume_up) +
                0.30 * float(np.clip(-drawdown / 0.50, 0, 1))
            )

    return dict(
        Q=float(max(QBO, QEP, QPL)), QBO=float(QBO), QEP=float(QEP), QPL=float(QPL),
        leader=float(leader), prior_thrust=float(prior_thrust),
        consolidation=float(consolidation), ma_surf=float(ma_surf),
        trigger=float(trigger), risk=float(risk),
        stop=float(stop), atr=float(atr),
        stop_distance_atr=float((px - stop) / max(1e-9, atr)),
        stair_step_thrust=step["thrust"], stair_step_base_len=step["base_len"],
    )


# ---------- DeMark Score ---------------------------------------------------

def demark_score(bars: pd.DataFrame, tf: str) -> dict:
    td = td_sequential(bars)
    if not td:
        return {"D": np.nan}
    c = bars["Close"]
    px = float(c.iloc[-1])
    if td["bars_since_buy13"] is not None and td["bars_since_buy13"] <= 8:
        buy_ex = 1.0
    elif td["perfected_buy9_recent"] and td["bars_since_buy9"] is not None and td["bars_since_buy9"] <= 5:
        buy_ex = 0.75
    elif td["buy_setup_now"] >= 6:
        buy_ex = 0.4 + (td["buy_setup_now"] - 6) * 0.1
    else:
        buy_ex = 0.0
    if len(c) > 4:
        bull_confirm = np.mean([
            float(c.iloc[-1] > c.iloc[-5]), float(td["range_flip"]),
            float(td["close_gt_swing"]),
            float(c.iloc[-1] > c.rolling(20).mean().iloc[-1]) if len(c) >= 20 else 0.5,
        ])
    else:
        bull_confirm = 0.0
    tdst_ctx = np.mean([
        float(not td["close_below_tdst_support"]),
        float(td["tdst_resistance"] == 0 or px > td["tdst_resistance"]),
    ])
    sl_break = float(c.iloc[-1] >= c.iloc[-25:-5].max()) if len(c) >= 25 else 0.5
    h = bars["High"]; l = bars["Low"]
    tr = pd.concat([(h - l).abs(), (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
    atr = tr.rolling(14).mean().iloc[-1]
    rr = float(np.clip((c.iloc[-20:].max() - px) / max(1e-9, atr * 2.0), 0, 1))
    lookback_sell = {"D": 9, "W": 6, "M": 4}[tf]
    sell_blocked = (
        (td["bars_since_sell13"] is not None and td["bars_since_sell13"] <= lookback_sell) or
        (td["bars_since_sell9"] is not None and td["bars_since_sell9"] <= lookback_sell)
    )
    no_sell_ex = 0.0 if sell_blocked else 1.0
    D = 100 * (
        0.30 * buy_ex + 0.25 * bull_confirm + 0.15 * tdst_ctx +
        0.15 * sl_break + 0.10 * rr + 0.05 * no_sell_ex
    )
    return dict(
        D=float(D), buy_exhaustion=float(buy_ex), bull_confirm=float(bull_confirm),
        tdst_ctx=float(tdst_ctx), supply_line_break=float(sl_break),
        no_sell_exhaustion=float(no_sell_ex), **td,
    )


# ---------- Confluence + Ranks --------------------------------------------

def confluence(W, Q, D, DA):
    if any(np.isnan([W, Q, D, DA])):
        return np.nan
    w, q, d, a = W / 100, Q / 100, D / 100, DA / 100
    eps = 1e-6
    geo = 100 * (max(w, eps) ** 0.25 * max(q, eps) ** 0.30 *
                 max(d, eps) ** 0.20 * max(a, eps) ** 0.25)
    return 0.70 * geo + 0.30 * min(W, Q, D, DA)


def stars_label(rank, C_D, C_W, C_M, W_T, Q_T, D_T, DA_T, vetoes):
    if vetoes:
        return "Reject"
    schools = [W_T, Q_T, D_T, DA_T]
    if rank > 70 and C_D > 70 and C_W > 70 and C_M > 70 and all(s > 65 for s in schools):
        return "A+"
    if rank > 75 and min(schools) >= 60:
        return "A"
    if rank > 65 and 50 <= min(schools) <= 60:
        return "B"
    return "C"


def collect_vetoes(w, q, d, da, tf):
    vs = []
    if not w.get("above_ma_long", True):
        vs.append("below MA-long")
    if not w.get("ma_long_slope_pos", True):
        vs.append("MA-long declining")
    if w.get("rs", 1) < 0.4:
        vs.append("weak RS")
    if tf in ("D", "W") and not w.get("breakout_volume_ok", True):
        vs.append("low breakout volume")
    if tf == "D" and q.get("stop_distance_atr", 0) > ATR_MAX_STOP:
        vs.append("stop > 1.5 ATR")
    if d.get("bars_since_sell13") is not None and d["bars_since_sell13"] <= 3:
        vs.append("fresh TD Sell 13")
    if d.get("bars_since_sell9") is not None and d["bars_since_sell9"] <= 3:
        vs.append("fresh TD Sell 9")
    return vs


def per_ticker_bars(daily, ticker, freq):
    try:
        sub = pd.DataFrame({
            "Open": daily["Open"][ticker],
            "High": daily["High"][ticker],
            "Low": daily["Low"][ticker],
            "Close": daily["Close"][ticker],
            "Volume": daily["Volume"][ticker] if "Volume" in daily.columns.get_level_values(0) else np.nan,
        }).dropna(subset=["Close"])
    except (KeyError, AttributeError):
        return pd.DataFrame()
    if freq is None:
        return sub
    agg = {"Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum"}
    return sub.resample(freq).agg(agg).dropna(subset=["Close"])


def evaluate(daily, idx_close, ticker, fx):
    rows = {}
    for tf, freq in [("D", None), ("W", "W-FRI"), ("M", "ME")]:
        bars = per_ticker_bars(daily, ticker, freq)
        if bars.empty or len(bars) < 30:
            return None
        idx_bars = idx_close if freq is None else idx_close.resample(freq).last().dropna()
        W = weinstein_score(bars, idx_bars, tf)
        Q = qullamaggie_score(bars, idx_bars, tf)
        D = demark_score(bars, tf)
        DA = darvas_score(bars, tf)
        C = confluence(W.get("W", np.nan), Q.get("Q", np.nan),
                       D.get("D", np.nan), DA.get("DA", np.nan))
        rows[tf] = dict(
            W=W.get("W", np.nan), Q=Q.get("Q", np.nan),
            D=D.get("D", np.nan), DA=DA.get("DA", np.nan),
            C=C, W_dict=W, Q_dict=Q, D_dict=D, DA_dict=DA,
        )
    C_D, C_W, C_M = rows["D"]["C"], rows["W"]["C"], rows["M"]["C"]
    if any(np.isnan([C_D, C_W, C_M])):
        return None
    daily_rank = 0.50 * C_D + 0.30 * C_W + 0.20 * C_M
    weekly_rank = 0.20 * C_D + 0.50 * C_W + 0.30 * C_M
    monthly_rank = 0.10 * C_D + 0.25 * C_W + 0.65 * C_M
    vetoes = {tf: collect_vetoes(rows[tf]["W_dict"], rows[tf]["Q_dict"],
                                  rows[tf]["D_dict"], rows[tf]["DA_dict"], tf)
              for tf in "DWM"}
    return dict(
        ticker=ticker,
        W_D=rows["D"]["W"], Q_D=rows["D"]["Q"], D_D=rows["D"]["D"], DA_D=rows["D"]["DA"], C_D=C_D,
        W_W=rows["W"]["W"], Q_W=rows["W"]["Q"], D_W=rows["W"]["D"], DA_W=rows["W"]["DA"], C_W=C_W,
        W_M=rows["M"]["W"], Q_M=rows["M"]["Q"], D_M=rows["M"]["D"], DA_M=rows["M"]["DA"], C_M=C_M,
        daily_rank=daily_rank, weekly_rank=weekly_rank, monthly_rank=monthly_rank,
        daily_gate=(C_W >= 55) and (C_M >= 45),
        weekly_gate=(C_W >= 65) and (C_M >= 55),
        monthly_gate=(C_M >= 70),
        daily_label=stars_label(daily_rank, C_D, C_W, C_M,
                                rows["D"]["W"], rows["D"]["Q"], rows["D"]["D"], rows["D"]["DA"], vetoes["D"]),
        weekly_label=stars_label(weekly_rank, C_D, C_W, C_M,
                                 rows["W"]["W"], rows["W"]["Q"], rows["W"]["D"], rows["W"]["DA"], vetoes["W"]),
        monthly_label=stars_label(monthly_rank, C_D, C_W, C_M,
                                  rows["M"]["W"], rows["M"]["Q"], rows["M"]["D"], rows["M"]["DA"], vetoes["M"]),
        vetoes_d=";".join(vetoes["D"]),
        vetoes_w=";".join(vetoes["W"]),
        vetoes_m=";".join(vetoes["M"]),
        n_boxes_w=rows["W"]["DA_dict"].get("n_boxes", 0),
        pyramid_w=int(rows["W"]["DA_dict"].get("ascending_pyramid", 0)),
        thrust_w=rows["W"]["Q_dict"].get("stair_step_thrust", 0),
    )


def main():
    region = (sys.argv[1] if len(sys.argv) > 1 else "us-small").lower()
    if region not in REGIONS:
        raise SystemExit(f"Unknown region {region!r}; choose from {list(REGIONS)}.")
    cfg = REGIONS[region]
    index = cfg["index"]
    print(f"\n>>> Region: {region} ({cfg['label']}); index = {index}", file=sys.stderr)

    universe, _ = fetch_universe(region)
    daily = fetch_ohlc(universe + [index], period="36mo")
    if index not in daily["Close"].columns:
        raise SystemExit(f"Index {index} missing from data.")
    idx_close = daily["Close"][index]
    tickers = [t for t in universe if t in daily["Close"].columns]

    needed_ccys = {currency_for_ticker(t) for t in tickers}
    fx = {}
    if currency_for_ticker(index) == "USD" and any(c != "USD" for c in needed_ccys):
        fx = fetch_fx(needed_ccys, period="36mo")

    rows = []
    for i, t in enumerate(tickers):
        try:
            r = evaluate(daily, idx_close, t, fx)
        except Exception:
            r = None
        if r is not None:
            rows.append(r)
        if (i + 1) % 100 == 0:
            print(f"  evaluated {i+1}/{len(tickers)}", file=sys.stderr)

    df = pd.DataFrame(rows)
    if df.empty:
        print("No tickers evaluated.")
        return

    cols_summary = [
        "ticker", "C_D", "C_W", "C_M",
        "W_W", "Q_W", "D_W", "DA_W",
        "daily_rank", "weekly_rank", "monthly_rank",
        "daily_label", "weekly_label", "monthly_label",
        "n_boxes_w", "pyramid_w", "thrust_w",
    ]
    print(f"\nEvaluated {len(df)} tickers.")

    for tf, rank_col, gate_col, label_col in [
        ("Daily",   "daily_rank",   "daily_gate",   "daily_label"),
        ("Weekly",  "weekly_rank",  "weekly_gate",  "weekly_label"),
        ("Monthly", "monthly_rank", "monthly_gate", "monthly_label"),
    ]:
        eligible = df[df[gate_col] & (df[label_col] != "Reject")].copy()
        eligible = eligible.sort_values(rank_col, ascending=False)
        print(f"\n=== {tf} setup top 20 ({len(eligible)} pass gate, not vetoed) ===")
        print(eligible[cols_summary].head(20).to_string(index=False, float_format=lambda x: f"{x:.1f}"))

    aplus = df[(df.daily_label == "A+") | (df.weekly_label == "A+") | (df.monthly_label == "A+")]
    if not aplus.empty:
        print(f"\n=== STARS ALIGNED A+ ({len(aplus)} names) ===")
        print(aplus[cols_summary].to_string(index=False, float_format=lambda x: f"{x:.1f}"))

    out_path = f"/tmp/stars_aligned_{region}.csv"
    df.to_csv(out_path, index=False)
    print(f"\nFull results: {out_path}")


if __name__ == "__main__":
    main()
