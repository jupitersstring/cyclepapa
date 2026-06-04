"""Minervini extension: MA respect, VCP, and mechanical analog measures.

Ten candidate measures (all on daily bars, key MAs):
  1.  MA respect + upward slope (touches vs clean breaks)
  2.  Vol asymmetry near MA (within ±2 ATR)
  3.  Spring constant (Hooke's law mean-reversion)
  4.  Damping ratio (control-theory)
  5.  Hurst exponent of (P-MA)/MA
  6.  Volume-weighted MA respect (Wyckoff/VSA)
  7.  MA crossover persistence (Donchian)
  8.  Phase coherence of returns vs MA slope
  9.  Conditional drawdown from MA
  10. Information ratio of trivial MA-following rule

MAs: EMA10, SMA20, SMA50, SMA150, SMA200.
"""

import numpy as np
import pandas as pd


# ---------- helpers ---------------------------------------------------------

def _mas(close: pd.Series) -> dict:
    return {
        "EMA10":  close.ewm(span=10, adjust=False).mean(),
        "SMA20":  close.rolling(20).mean(),
        "SMA50":  close.rolling(50).mean(),
        "SMA150": close.rolling(150).mean(),
        "SMA200": close.rolling(200).mean(),
    }


def _atr(bars: pd.DataFrame, n: int = 14) -> pd.Series:
    h, l, c = bars["High"], bars["Low"], bars["Close"]
    tr = pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
    return tr.rolling(n).mean()


# ---------- (1) MA respect + upward slope -----------------------------------

def ma_respect(bars: pd.DataFrame, ma: pd.Series,
               lookback_days: int = 60, slope_weeks: int = 8) -> dict:
    if len(bars) < lookback_days + 5 or ma.isna().all():
        return {}
    h, l, c = bars["High"], bars["Low"], bars["Close"]

    # Slope (% per week)
    n_slope = slope_weeks * 5
    if len(ma) >= n_slope + 2:
        y = ma.iloc[-n_slope:].dropna().values
        if len(y) >= 5:
            slope = float(np.polyfit(np.arange(len(y)), y, 1)[0])
            slope_pct_wk = slope * 5 / max(1e-9, float(c.iloc[-1]))
        else:
            slope_pct_wk = 0.0
    else:
        slope_pct_wk = 0.0

    window = bars.iloc[-lookback_days:]
    ma_w = ma.iloc[-lookback_days:]
    valid = (~ma_w.isna()).sum()
    if valid < 10:
        return {}

    touched = (window["Low"] <= ma_w * 1.005) & (window["Close"] > ma_w * 0.99)
    touch_count = int(touched.sum())

    below_thr = window["Close"] < ma_w * 0.98
    clean_break_count = int((below_thr & below_thr.shift(1).fillna(False)).sum())

    above = (window["Close"] > ma_w).values
    recovery_bars = []
    in_break = False
    bstart = None
    for i, v in enumerate(above):
        if not v and not in_break:
            in_break = True
            bstart = i
        elif v and in_break:
            recovery_bars.append(i - bstart)
            in_break = False
    avg_recovery = float(np.mean(recovery_bars)) if recovery_bars else 0.0

    denom = touch_count + 2 * clean_break_count
    respect_ratio = touch_count / denom if denom > 0 else 0.5

    composite = respect_ratio * (1.0 if slope_pct_wk > 0.002 else 0.5)

    return dict(
        slope_pct_wk=slope_pct_wk,
        touches=touch_count,
        clean_breaks=clean_break_count,
        respect_ratio=respect_ratio,
        avg_recovery_bars=avg_recovery,
        composite=composite,
    )


# ---------- (2) Vol asymmetry near MA ---------------------------------------

def vol_asym_near_ma(bars: pd.DataFrame, ma: pd.Series,
                      atr_mult: float = 2.0, lookback_days: int = 63) -> dict:
    if len(bars) < 30 or ma.isna().all():
        return {}
    atr = _atr(bars)
    sub = bars.iloc[-lookback_days:]
    ma_w = ma.iloc[-lookback_days:]
    atr_w = atr.iloc[-lookback_days:]

    near = (sub["Close"] - ma_w).abs() <= atr_mult * atr_w
    valid = near & ~ma_w.isna()
    if valid.sum() < 10:
        return {}
    rets = sub["Close"].pct_change()
    nr = rets[valid]
    up = nr[nr > 0].std()
    dn = nr[nr < 0].std()
    if pd.isna(up) or pd.isna(dn) or dn == 0:
        return {}
    return dict(ma_vol_asym=float(up / dn))


# ---------- (3) Spring constant (Hooke's law) ------------------------------

def spring_constant(bars: pd.DataFrame, ma: pd.Series) -> dict:
    if len(bars) < 50 or ma.isna().all():
        return {}
    c = bars["Close"]
    dev = (c - ma) / ma
    r_next = c.pct_change().shift(-1)
    df = pd.DataFrame({"dev": dev, "r": r_next}).dropna().iloc[-252:]
    if len(df) < 30 or df["dev"].std() < 1e-6:
        return {}
    # r_next = slope * dev + intercept
    slope, _ = np.polyfit(df["dev"].values, df["r"].values, 1)
    # k positive = mean-reversion (deviation predicts opposite return)
    return dict(spring_k=-float(slope))


# ---------- (4) Damping ratio ------------------------------------------------

def damping_ratio(bars: pd.DataFrame, ma: pd.Series) -> dict:
    if len(bars) < 100 or ma.isna().all():
        return {}
    dev = (bars["Close"] - ma).dropna().iloc[-252:]
    if len(dev) < 50:
        return {}
    rho1 = dev.autocorr(lag=1)
    rho2 = dev.autocorr(lag=2)
    if pd.isna(rho1) or pd.isna(rho2):
        return {}
    if abs(rho1) < 1e-6 or abs(rho2) < 1e-6:
        return {}
    ratio = abs(rho2) / abs(rho1)
    if ratio <= 0 or ratio > 1.5:
        return {}
    zeta = -np.log(ratio)
    return dict(damping_ratio=float(zeta))


# ---------- (5) Hurst exponent ----------------------------------------------

def hurst_of_dev(bars: pd.DataFrame, ma: pd.Series, max_lag: int = 20) -> dict:
    if len(bars) < 100 or ma.isna().all():
        return {}
    dev = ((bars["Close"] - ma) / ma).dropna().iloc[-252:]
    if len(dev) < 80:
        return {}
    arr = dev.values
    lags = list(range(2, min(max_lag, len(arr) // 4)))
    if len(lags) < 3:
        return {}
    tau = []
    for L in lags:
        diffs = arr[L:] - arr[:-L]
        s = np.std(diffs)
        if s <= 0:
            return {}
        tau.append(np.sqrt(s))
    H = float(np.polyfit(np.log(lags), np.log(tau), 1)[0] * 2)
    if not np.isfinite(H):
        return {}
    return dict(hurst=H)


# ---------- (6) Volume-weighted MA respect ----------------------------------

def vol_weighted_respect(bars: pd.DataFrame, ma: pd.Series,
                         lookback_days: int = 60) -> dict:
    if "Volume" not in bars.columns or len(bars) < lookback_days:
        return {}
    sub = bars.iloc[-lookback_days:]
    ma_w = ma.iloc[-lookback_days:]
    v = sub["Volume"]
    above = sub["Close"] > ma_w
    total = float(v.sum())
    if total <= 0:
        return {}
    above_v = float(v[above].sum())
    touch_bars = (sub["Low"] <= ma_w * 1.005) & (sub["Close"] > ma_w * 0.99)
    trend_bars = above & ~touch_bars

    vol_touch = float(v[touch_bars].mean()) if touch_bars.any() else 0.0
    vol_trend = float(v[trend_bars].mean()) if trend_bars.any() else 0.0
    return dict(
        vol_above_ma_ratio=above_v / total,
        touch_vol_vs_trend=(vol_touch / vol_trend) if vol_trend > 0 else None,
    )


# ---------- (7) MA crossover persistence ------------------------------------

def crossover_persistence(bars: pd.DataFrame, ma: pd.Series,
                          lookback_days: int = 252) -> dict:
    if len(bars) < 50 or ma.isna().all():
        return {}
    sub = bars.iloc[-lookback_days:]
    ma_w = ma.iloc[-lookback_days:]
    above = (sub["Close"] > ma_w).values
    if not above[-1]:
        return dict(days_above_ma_current=0, max_run_above_ma=0,
                    current_vs_max_pct=0.0)
    cur = 0
    for v in reversed(above):
        if v:
            cur += 1
        else:
            break
    max_run = 0
    run = 0
    for v in above:
        if v:
            run += 1
            max_run = max(max_run, run)
        else:
            run = 0
    return dict(
        days_above_ma_current=cur,
        max_run_above_ma=max_run,
        current_vs_max_pct=cur / max(1, max_run),
    )


# ---------- (8) Phase coherence ---------------------------------------------

def phase_coherence(bars: pd.DataFrame, ma: pd.Series, max_lag: int = 20) -> dict:
    if len(bars) < 100 or ma.isna().all():
        return {}
    ret = np.log(bars["Close"]).diff().dropna()
    slope = ma.diff().dropna()
    common = ret.index.intersection(slope.index)
    if len(common) < 80:
        return {}
    r = ret.reindex(common).values[-252:]
    m = slope.reindex(common).values[-252:]
    if len(r) < 50:
        return {}
    best_lag, best_corr = 0, -np.inf
    for lag in range(-max_lag, max_lag + 1):
        if lag >= 0:
            x, y = r[lag:], m[:len(r) - lag] if lag > 0 else m
        else:
            x, y = r[:lag], m[-lag:]
        if len(x) != len(y) or len(x) < 30:
            continue
        c = np.corrcoef(x, y)[0, 1]
        if np.isfinite(c) and c > best_corr:
            best_corr = c
            best_lag = lag
    if best_corr == -np.inf:
        return {}
    return dict(phase_lag=int(best_lag), max_correlation=float(best_corr))


# ---------- (9) Conditional drawdown from MA --------------------------------

def avg_pullback_to_ma(bars: pd.DataFrame, ma: pd.Series,
                       lookback_days: int = 252) -> dict:
    if len(bars) < lookback_days or ma.isna().all():
        return {}
    c = bars["Close"].iloc[-lookback_days:].values
    m = ma.iloc[-lookback_days:].values
    if (~np.isnan(m)).sum() < 50:
        return {}
    pullbacks = []
    peak_idx = 0
    for i in range(1, len(c)):
        if c[i] > c[peak_idx]:
            peak_idx = i
        elif not np.isnan(m[i]) and c[i] <= m[i] * 1.01 and 0 < i - peak_idx <= 40:
            pb = (c[peak_idx] - c[i]) / c[peak_idx]
            if 0 < pb < 0.5:
                pullbacks.append(pb)
            peak_idx = i
    if not pullbacks:
        return {}
    return dict(
        avg_pullback_to_ma_pct=float(np.mean(pullbacks)),
        n_pullbacks=len(pullbacks),
    )


# ---------- (10) MA-following IR --------------------------------------------

def ma_following_ir(bars: pd.DataFrame, ma: pd.Series,
                    lookback_days: int = 252) -> dict:
    if len(bars) < lookback_days + 5 or ma.isna().all():
        return {}
    sub = bars.iloc[-lookback_days:]
    ma_w = ma.iloc[-lookback_days:]
    c = sub["Close"]
    ret = c.pct_change().fillna(0)
    signal = (c.shift(1) > ma_w.shift(1)).astype(float)
    strat = signal * ret
    sd = strat.std()
    if sd == 0:
        return {}
    return dict(
        ma_strategy_sharpe=float(strat.mean() / sd * np.sqrt(252)),
        ma_strategy_total_ret=float((1 + strat).prod() - 1),
        ma_signal_active_pct=float(signal.mean()),
    )


# ---------- orchestrator ----------------------------------------------------

MEASURE_FNS = [
    ("respect",     ma_respect),
    ("vol_asym",    vol_asym_near_ma),
    ("spring",      spring_constant),
    ("damping",     damping_ratio),
    ("hurst",       hurst_of_dev),
    ("vol_resp",    vol_weighted_respect),
    ("persist",     crossover_persistence),
    ("phase",       phase_coherence),
    ("pullback",    avg_pullback_to_ma),
    ("ir",          ma_following_ir),
]


def all_minervini_metrics(daily_bars: pd.DataFrame, ticker: str = "") -> dict:
    """Run every measure for every MA. Returns flat dict."""
    if "Close" not in daily_bars.columns or len(daily_bars) < 252:
        return {}
    bars = daily_bars.dropna(subset=["Close"]).copy()
    if len(bars) < 252:
        return {}
    mas = _mas(bars["Close"])
    out = {"ticker": ticker}
    for ma_name, ma in mas.items():
        for tag, fn in MEASURE_FNS:
            try:
                r = fn(bars, ma) or {}
            except Exception:
                r = {}
            for k, v in r.items():
                out[f"{ma_name}_{tag}_{k}"] = v
    return out


# ---------- Composite score -------------------------------------------------

KEEP_KEYS = None  # populated after the testing step


def minervini_composite(metrics: dict) -> float:
    """Empirically-validated composite (0..100).

    Built from the keepers identified in test_minervini.py (winners-vs-losers
    panel test): each row is a metric name with (lo, hi, weight) for linear
    transform 0..1. Weights sum to 100. Tested t-stats ranged from 5-97.
    """
    keepers = {
        # ---- Vol-weighted MA respect (Wyckoff/VSA): the dominant separator
        "SMA200_vol_resp_vol_above_ma_ratio": (0.20, 0.95, 25),
        "SMA50_vol_resp_vol_above_ma_ratio":  (0.20, 0.85, 10),
        # ---- Clean breaks (inverse): winners ~1, losers ~50
        "SMA200_respect_clean_breaks":        (50,    1,   15),  # inverse
        "SMA50_respect_clean_breaks":         (40,    3,   10),  # inverse
        # ---- Composite respect score
        "SMA150_respect_composite":           (0.05,  0.55, 10),
        "EMA10_respect_composite":            (0.20,  0.75, 5),
        # ---- Persistence (current streak above MA)
        "SMA200_persist_max_run_above_ma":    (10,    150,  8),
        "SMA50_persist_days_above_ma_current":(2,     50,   8),
        # ---- Upward slope of EMA10
        "EMA10_respect_slope_pct_wk":         (-0.02, 0.04, 5),
        # ---- Recovery speed (inverse: faster = better)
        "SMA20_respect_avg_recovery_bars":    (15,    5,    4),  # inverse
    }
    total_w = 0.0
    total_s = 0.0
    for k, (lo, hi, w) in keepers.items():
        v = metrics.get(k)
        if v is None or (isinstance(v, float) and not np.isfinite(v)):
            continue
        if hi != lo:
            if hi > lo:
                s = (v - lo) / (hi - lo)
            else:
                # inverse axis
                s = (lo - v) / (lo - hi)
        else:
            continue
        s = float(np.clip(s, 0, 1))
        total_s += s * w
        total_w += w
    if total_w == 0:
        return float("nan")
    return float(total_s / total_w * 100)


# ---------- VCP (Volatility Contraction Pattern) detector -------------------

def vcp_metrics(bars: pd.DataFrame, lookback_days: int = 60) -> dict:
    """Minervini VCP: sequential contracting pullbacks, drying volume, tight
    close to pivot.

    Returns:
      vcp_contractions: # of detected sequential pullbacks (each shallower)
      vcp_avg_pullback_pct: average pullback depth
      vcp_volume_dryup_ratio: late-base avg-vol / early-base avg-vol (<1 = drying)
      vcp_pivot_distance_pct: distance from current close to base-high pivot
      vcp_score: 0..100 composite
    """
    if len(bars) < lookback_days + 5:
        return {}
    sub = bars.iloc[-lookback_days:]
    c = sub["Close"].values
    n = len(c)

    # Find local peaks and troughs via simple swing detection (5-bar window)
    swing = 5
    peaks, troughs = [], []
    for i in range(swing, n - swing):
        if c[i] == c[i - swing:i + swing + 1].max():
            peaks.append(i)
        if c[i] == c[i - swing:i + swing + 1].min():
            troughs.append(i)

    # Build alternating peak-trough-peak-trough sequence for contractions
    points = sorted(peaks + troughs)
    if len(points) < 4:
        return {}
    pullbacks = []
    for i in range(1, len(points)):
        prev, cur = points[i - 1], points[i]
        if c[prev] > c[cur]:
            pullbacks.append((c[prev] - c[cur]) / c[prev])

    if not pullbacks:
        return {}

    # Count of pullbacks where each is smaller than the prior
    contractions = 0
    for i in range(1, len(pullbacks)):
        if pullbacks[i] < pullbacks[i - 1]:
            contractions += 1

    avg_pullback = float(np.mean(pullbacks))

    # Volume dryup
    if "Volume" in sub.columns:
        early_vol = sub["Volume"].iloc[:lookback_days // 3].mean()
        late_vol = sub["Volume"].iloc[-lookback_days // 3:].mean()
        dryup = float(late_vol / max(1e-9, early_vol))
    else:
        dryup = None

    # Pivot distance
    base_high = float(np.max(c))
    pivot_dist = (base_high - c[-1]) / base_high

    # Score
    s = 0.0
    n_c = 0
    s += float(np.clip(contractions / 3, 0, 1)) * 0.30  # 3+ contractions = ideal
    n_c += 1
    if dryup is not None:
        s += float(np.clip(1 - dryup, 0, 0.5)) * 2 * 0.25
        n_c += 1
    # Avg pullback shallow = better (VCP base avg ~5-15%)
    s += float(np.clip(1 - avg_pullback / 0.20, 0, 1)) * 0.20
    n_c += 1
    # Close near pivot = ready to break
    s += float(np.clip(1 - pivot_dist / 0.10, 0, 1)) * 0.25
    n_c += 1

    return dict(
        vcp_contractions=contractions,
        vcp_avg_pullback_pct=avg_pullback,
        vcp_volume_dryup_ratio=dryup,
        vcp_pivot_distance_pct=float(pivot_dist),
        vcp_score=float(s * 100),
    )


def full_minervini_score(daily_bars: pd.DataFrame) -> dict:
    """Combine MA-respect composite with VCP, plus E (entry-NOW trigger)."""
    m = all_minervini_metrics(daily_bars)
    if not m:
        return {"M": float("nan"), "E": float("nan")}
    base = minervini_composite(m)
    vcp = vcp_metrics(daily_bars) or {}
    vcp_s = vcp.get("vcp_score")
    if np.isfinite(base):
        if vcp_s is not None and np.isfinite(vcp_s):
            combined = 0.60 * base + 0.40 * vcp_s
        else:
            combined = base
    else:
        combined = float("nan")
    e = entry_now(daily_bars) or {"E": float("nan")}
    return {
        "M":       float(combined),
        "M_base":  float(base) if np.isfinite(base) else None,
        "M_vcp":   float(vcp_s) if vcp_s is not None else None,
        **vcp,
        **e,
    }


# ---------- "Time is NOW" entry-trigger leg ---------------------------------

def entry_now(bars: pd.DataFrame, lookback: int = 20) -> dict:
    """Composite 0..100 score that fires when TODAY's daily bar is the
    right entry. Emphasises: volume spike, strong setup behind it, AND
    recently different / uncorrelated behavior vs the prior weeks.

    Components (weight):
      vol_spike (20):       today vol >= 2x trailing 50-day MEDIAN
      pivot_break (15):     close > prior 20-bar high
      ret_acceleration (10):last 5 daily returns >> prior 20-day mean
      behavior_shift (10):  rolling 10-day return autocorr differs >0.3 from
                            prior 40-day (regime change in own dynamics)
      close_strength (10):  close in upper 70% of day's range
      coil_break (10):      yesterday NR4/inside, today breaks high
      ma_aligned (10):      close > EMA10 > SMA20 > SMA50 (golden order)
      bb_break (10):        close > Bollinger upper band
      new_high (5):         close > 20-bar high
    """
    if len(bars) < 25:
        return {"E": float("nan")}
    c = bars["Close"]; h = bars["High"]; l = bars["Low"]; v = bars.get("Volume")
    if len(c) < 25:
        return {"E": float("nan")}

    c_now = float(c.iloc[-1])
    c_prev = float(c.iloc[-2])
    h_now = float(h.iloc[-1])
    l_now = float(l.iloc[-1])

    ema10 = c.ewm(span=10, adjust=False).mean()
    sma20 = c.rolling(20).mean()
    sma50 = c.rolling(50).mean() if len(c) >= 50 else sma20
    ema10_now = float(ema10.iloc[-1])
    sma20_now = float(sma20.iloc[-1])
    sma50_now = float(sma50.iloc[-1]) if not pd.isna(sma50.iloc[-1]) else sma20_now

    # 1. Pivot break
    prior_high = float(h.iloc[-(lookback + 1):-1].max())
    pivot_break = c_now > prior_high * 1.002

    # 2. Volume spike — vs 50-day MEDIAN (robust to past spikes)
    if v is not None and len(v.dropna()) >= 50:
        vol_now = float(v.iloc[-1])
        vol_med = float(v.iloc[-50:-1].median())
        vol_ratio = vol_now / max(1e-9, vol_med)
        # 2x median = full credit; 1.0x = 0; smooth ramp
        vol_spike = float(np.clip((vol_ratio - 1.0) / 1.0, 0, 1))
    else:
        vol_ratio = None
        vol_spike = 0.0

    # Recent acceleration: last 5 days returns vs prior 20-day avg
    ret = c.pct_change().dropna()
    if len(ret) >= 25:
        recent_avg = float(ret.iloc[-5:].mean())
        prior_avg = float(ret.iloc[-25:-5].mean())
        # Ratio of recent to prior; positive recent + 3x prior = full credit
        if prior_avg > 0 and recent_avg > prior_avg:
            ret_acc = float(np.clip((recent_avg / max(prior_avg, 1e-4) - 1) / 2, 0, 1))
        elif recent_avg > 0 and prior_avg <= 0:
            # Recent positive, prior was negative/zero — strong shift
            ret_acc = float(np.clip(recent_avg / 0.005, 0, 1))
        else:
            ret_acc = 0.0
    else:
        ret_acc = 0.0

    # Behavior shift — autocorrelation regime change in own returns
    if len(ret) >= 60:
        recent_ret = ret.iloc[-10:]
        prior_ret = ret.iloc[-50:-10]
        if recent_ret.std() > 0 and prior_ret.std() > 0:
            r_recent = float(recent_ret.autocorr(lag=1)) if len(recent_ret) > 2 else 0.0
            r_prior = float(prior_ret.autocorr(lag=1)) if len(prior_ret) > 2 else 0.0
            ac_shift = abs(r_recent - r_prior)
            # Also detect mean-shift
            mean_shift = abs(recent_ret.mean() - prior_ret.mean()) / max(prior_ret.std(), 1e-6)
            behavior_shift = float(np.clip((ac_shift * 1.5 + mean_shift * 0.5) / 1.5, 0, 1))
        else:
            behavior_shift = 0.0
    else:
        behavior_shift = 0.0

    # 3. Close strength in day's range
    rng = h_now - l_now
    close_strength = (c_now - l_now) / rng if rng > 1e-9 else 0.5
    close_strength_score = float(np.clip((close_strength - 0.5) * 2, 0, 1))

    # 4. Coil break (yesterday NR4 or inside, today breaks high)
    if len(c) >= 6:
        rngs = (h - l).iloc[-5:].values
        nr4 = rngs[-2] <= rngs[-5:-1].min() if len(rngs) >= 4 else False
        inside = (h.iloc[-2] <= h.iloc[-3]) and (l.iloc[-2] >= l.iloc[-3])
        coil_break = (nr4 or inside) and c_now > float(h.iloc[-2])
    else:
        coil_break = False

    # 5. Pullback bounce (yesterday touched EMA10, today reclaims)
    pullback_bounce = (
        float(l.iloc[-2]) <= float(ema10.iloc[-2]) * 1.01 and
        c_now > ema10_now and c_now > c_prev
    )

    # 6. MA alignment
    ma_aligned = c_now > ema10_now > sma20_now > sma50_now

    # 7. Compression
    tr = pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
    atr5 = float(tr.rolling(5).mean().iloc[-1])
    atr20 = float(tr.rolling(20).mean().iloc[-1])
    compression = (atr5 / atr20) < 0.8 if atr20 > 0 else False

    # 8. Bollinger band break
    std20 = float(c.rolling(20).std().iloc[-1])
    upper_bb = sma20_now + 2 * std20
    bb_break = c_now > upper_bb

    # 9. New 20-day high
    new_high = c_now > float(h.iloc[-21:-1].max())

    weights = {
        "vol_spike":         0.20,
        "pivot_break":       0.15,
        "ret_acceleration":  0.10,
        "behavior_shift":    0.10,
        "close_strength":    0.10,
        "coil_break":        0.10,
        "ma_aligned":        0.10,
        "bb_break":          0.10,
        "new_high":          0.05,
    }
    components = {
        "vol_spike":         vol_spike,
        "pivot_break":       float(pivot_break),
        "ret_acceleration":  ret_acc,
        "behavior_shift":    behavior_shift,
        "close_strength":    close_strength_score,
        "coil_break":        float(coil_break),
        "ma_aligned":        float(ma_aligned),
        "bb_break":          float(bb_break),
        "new_high":          float(new_high),
    }
    score = sum(weights[k] * components[k] for k in weights)

    return {
        "E":                  float(score * 100),
        "E_vol_spike":        components["vol_spike"],
        "E_pivot_break":      components["pivot_break"],
        "E_ret_acceleration": components["ret_acceleration"],
        "E_behavior_shift":   components["behavior_shift"],
        "E_close_strength":   components["close_strength"],
        "E_coil_break":       components["coil_break"],
        "E_ma_aligned":       components["ma_aligned"],
        "E_bb_break":         components["bb_break"],
        "E_new_high":         components["new_high"],
        "E_vol_ratio":        vol_ratio,
    }


def downside_resilience(stock_bars: pd.DataFrame, market_close: pd.Series,
                         lookback_days: int = 252) -> dict:
    """How well the stock holds up during MARKET drawdown days.

    Captures: "doesn't care about downside vol in the market."

    Methodology:
      - Take trailing `lookback_days` of daily returns for stock and market.
      - Filter to bottom 30% of market returns (the worst market days).
      - downside_capture = avg(stock_ret | bad market days) / avg(market_ret | bad market days)
      - DSR score (0..100):
          1.5x capture -> 0 (worst, falls harder than market)
          1.0x capture -> ~33 (matches downside)
          0.0x capture -> ~75 (immune)
         -0.5x capture -> 100 (goes up on market down days)
      - Also returns market_corr (absolute trailing-year correlation w/ market).
    """
    if stock_bars is None or stock_bars.empty:
        return {"DSR": float("nan")}
    s = stock_bars["Close"].pct_change().dropna()
    m = market_close.pct_change().dropna()
    common = s.index.intersection(m.index)
    if len(common) < 60:
        return {"DSR": float("nan")}
    common = common[-lookback_days:] if len(common) > lookback_days else common
    s = s.reindex(common); m = m.reindex(common)
    if len(s) < 60:
        return {"DSR": float("nan")}

    threshold = m.quantile(0.30)
    bad = m <= threshold
    n_bad = int(bad.sum())
    if n_bad < 10:
        return {"DSR": float("nan")}

    s_bad = float(s[bad].mean())
    m_bad = float(m[bad].mean())
    if m_bad >= 0:
        return {"DSR": float("nan")}
    capture = s_bad / m_bad

    dsr = float(np.clip((1.5 - capture) / 2.0, 0, 1)) * 100
    corr = float(s.corr(m))

    return {
        "DSR":                  dsr,
        "downside_capture":     float(capture),
        "market_corr":          float(corr),
        "n_drawdown_days":      n_bad,
        "stock_ret_drawdown_pct": float(s_bad * 100),
        "mkt_ret_drawdown_pct":   float(m_bad * 100),
    }


if __name__ == "__main__":
    print("module loaded;", len(MEASURE_FNS), "measure functions × 5 MAs")
