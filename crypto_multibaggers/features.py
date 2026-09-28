"""Pre-event tape measures for (token, day 0) windows.

Every measure uses data up to day -1 only. Baselines are the token's own
history over days -180..-61. Flow is signed with bulk volume classification
(BVC: buy share = Phi(r / sigma)), toxicity is a 20-day volume-weighted |OI|
(VPIN on daily bars), and a "toxic day" is one whose VPIN is above the 80th
percentile of the token's own baseline VPIN.

The "toxic" composites (toxic breakout / momentum / trend / OBV, toxic
accumulation, toxic squeeze) restrict the plain technical signal to days
carrying toxic, buy-side flow; each sits next to its plain counterpart so
the overlay can be judged directly.
"""
from __future__ import annotations

import numpy as np
from scipy.special import ndtr

from .config import BASELINE, CUSUM_LEN, MIN_BASELINE_OBS

# key -> (label, group)
FEATURES: dict[str, tuple[str, str]] = {
    # volume
    "av_mean_S": ("Abnormal volume, last 5 days", "volume"),
    "av_mean_M": ("Abnormal volume, days -20..-6", "volume"),
    "av_mean_L": ("Abnormal volume, days -60..-21", "volume"),
    "av_peak_A": ("Peak abnormal volume, 60d", "volume"),
    "n_av2_A": ("Days with volume > 2 sd, 60d", "volume"),
    "iv_mean_S": ("Idiosyncratic volume, last 5 days", "volume"),
    "iv_mean_L": ("Idiosyncratic volume, days -60..-21", "volume"),
    "uv_mean_S": ("Volume without price, last 5 days", "volume"),
    "uv_mean_A": ("Volume without price, 60d", "volume"),
    "cusum_av_120": ("Volume build-up (CUSUM, 120d)", "volume"),
    "dv_ratio_S": ("Dollar volume vs baseline, last 5 days", "volume"),
    "log_dv_base": ("Baseline dollar volume (log)", "size"),
    # flow / toxicity
    "vpin_cdf": ("Flow toxicity (VPIN percentile, 1y)", "flow"),
    "vpin_z_S": ("Flow toxicity vs baseline, last 5 days", "flow"),
    "oi_vw_L": ("Order imbalance (BVC), days -60..-21", "flow"),
    "oi_vw_S": ("Order imbalance (BVC), last 5 days", "flow"),
    "cmf20": ("Chaikin money flow, 20d", "flow"),
    "obv_A": ("OBV slope, 60d", "flow"),
    "obv_S20": ("OBV slope, 20d", "flow"),
    # price path
    "car_L": ("Abnormal return, days -60..-21", "price"),
    "car_M": ("Abnormal return, days -20..-6", "price"),
    "car_S": ("Abnormal return, last 5 days", "price"),
    "car_A": ("Abnormal return, 60d", "price"),
    "mom_30": ("Momentum, 30d", "price"),
    "mom_90": ("Momentum, 90d", "price"),
    "rs_btc_90": ("Return vs BTC, 90d", "price"),
    "vol_ratio_A": ("Volatility vs own baseline, 60d", "price"),
    "vol_ratio_S": ("Volatility vs own baseline, last 5 days", "price"),
    "n_up_jumps_A": ("Up-spikes > 2 sd, 60d", "price"),
    "n_dn_jumps_A": ("Down-spikes > 2 sd, 60d", "price"),
    "max_up_z_M": ("Largest up-day (sd), days -20..-1", "price"),
    "skew_A": ("Return skewness, 60d", "price"),
    "max_dd_A": ("Max drawdown inside 60d", "price"),
    "dd_ath": ("Drawdown from all-time high", "price"),
    "days_since_ath": ("Days since all-time high (log)", "price"),
    "dist_ma200": ("Distance from 200-day average", "price"),
    "dist_ma50": ("Distance from 50-day average", "price"),
    "brk_90": ("Close vs prior 90-day high", "price"),
    "n_high60_S20": ("New 60-day highs, last 20 days", "price"),
    "trend_t60": ("Trend strength (t-stat of 60d slope)", "price"),
    "above_ma20_A": ("Share of days above 20-day average, 60d", "price"),
    "range_pos20": ("Close location in 20-day range", "price"),
    "bbw_pct": ("Bollinger bandwidth percentile (squeeze)", "price"),
    "corr_mkt_A": ("Correlation with crypto market, 60d", "price"),
    "log_age": ("Token age (log days)", "size"),
    # liquidity
    "amihud_ratio_A": ("Illiquidity (Amihud) vs baseline", "liquidity"),
    "kyle_ratio_A": ("Price impact (Kyle lambda) vs baseline", "liquidity"),
    # toxic composites (attribution-engine style overlays)
    "toxic_breakout_S20": ("Toxic breakouts (new 60d high on toxic buy flow), 20d", "toxic"),
    "toxic_mom_A": ("Toxic momentum (return on toxic days), 60d", "toxic"),
    "toxic_mom_S20": ("Toxic momentum (return on toxic days), 20d", "toxic"),
    "toxic_trend_A": ("Toxic trend (days above 20d avg on toxic buy flow), 60d", "toxic"),
    "tobv_A": ("Toxic OBV slope, 60d", "toxic"),
    "tobv_S20": ("Toxic OBV slope, 20d", "toxic"),
    "toxic_accum_A": ("Toxic accumulation (volume without price x buy imbalance)", "toxic"),
    "toxic_squeeze": ("Toxic squeeze (tight bands x rising toxicity)", "toxic"),
    "capitulation_S": ("Capitulation (final-week volume x falling price x selling)", "toxic"),
}

# known at the close of day 0 (used only for "is this pop the start of a run?")
DAY0: dict[str, tuple[str, str]] = {
    "d0_ret": ("Day-0 return", "day0"),
    "d0_z": ("Day-0 abnormal return (sd)", "day0"),
    "d0_av": ("Day-0 abnormal volume", "day0"),
    "d0_clv": ("Day-0 close location in range", "day0"),
    "d0_wick": ("Day-0 upper wick share", "day0"),
    "d0_dv_ratio": ("Day-0 dollar volume vs baseline", "day0"),
}


def _shift(x: np.ndarray, k: int) -> np.ndarray:
    out = np.full_like(x, np.nan)
    if k > 0:
        out[k:] = x[:-k]
    elif k < 0:
        out[:k] = x[-k:]
    else:
        out[:] = x
    return out


def _gather(x: np.ndarray, t: np.ndarray, lo: int, hi: int) -> np.ndarray:
    """x[t+lo .. t+hi] for each t as a (len(t), hi-lo+1) matrix, NaN outside the series."""
    idx = t[:, None] + np.arange(lo, hi + 1)[None, :]
    ok = (idx >= 0) & (idx < len(x))
    g = x[np.clip(idx, 0, len(x) - 1)].astype(float)
    g[~ok] = np.nan
    return g


def _nanmean(a, axis=1):
    n = np.sum(~np.isnan(a), axis=axis)
    s = np.nansum(a, axis=axis)
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(n > 0, s / np.maximum(n, 1), np.nan)


def _nanstd(a, axis=1, min_n=2):
    n = np.sum(~np.isnan(a), axis=axis)
    m = _nanmean(a, axis)
    with np.errstate(invalid="ignore", divide="ignore"):
        v = np.nansum((a - m[:, None]) ** 2, axis=axis) / np.maximum(n - 1, 1)
    return np.where(n >= min_n, np.sqrt(v), np.nan)


def _rolling_mean(x: np.ndarray, w: int, min_n: int) -> np.ndarray:
    valid = ~np.isnan(x)
    s = np.concatenate([[0.0], np.cumsum(np.where(valid, x, 0.0))])
    n = np.concatenate([[0], np.cumsum(valid)])
    hi = np.arange(1, len(x) + 1)
    lo = np.maximum(hi - w, 0)
    cnt = n[hi] - n[lo]
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(cnt >= min_n, (s[hi] - s[lo]) / np.maximum(cnt, 1), np.nan)


def _rolling_max_prev(x: np.ndarray, w: int) -> np.ndarray:
    """max of x over the w days strictly before each day."""
    from numpy.lib.stride_tricks import sliding_window_view
    pad = np.concatenate([np.full(w, np.nan), x])
    win = sliding_window_view(pad, w)[: len(x)]
    with np.errstate(all="ignore"):
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            return np.nanmax(win, axis=1)


class TokenSeries:
    """Per-token arrays aligned to the panel calendar, plus derived series."""

    def __init__(self, o, h, l, c, v, mret, mlogvol, btc_lc):
        self.c = c
        self.lc = np.log(c)
        self.r = self.lc - _shift(self.lc, 1)
        self.v = np.where(v > 0, v, np.nan)
        self.lv = np.log(self.v)
        self.h, self.l = h, l
        self.m = mret
        self.mlv = mlogvol
        self.btc_lc = btc_lc
        T = len(c)
        # BVC flow on a lagged rolling sigma (series property, not event specific)
        sig = np.sqrt(_rolling_mean(self.r ** 2, 90, 30))
        sig = _shift(sig, 1)
        with np.errstate(invalid="ignore", divide="ignore"):
            zb = self.r / sig
        self.oi = np.where(np.isnan(zb), np.nan, 2 * ndtr(zb) - 1)
        sv = self.oi * self.v
        self.sv = sv
        num = _rolling_mean(np.abs(sv), 20, 10)
        den = _rolling_mean(self.v, 20, 10)
        with np.errstate(invalid="ignore", divide="ignore"):
            self.vpin = num / den
        # classic OBV increments
        self.obv_inc = np.sign(self.r) * self.v
        # moving averages / bands on close
        self.ma20 = _rolling_mean(c, 20, 15)
        sd20 = np.sqrt(np.maximum(_rolling_mean(c ** 2, 20, 15) - self.ma20 ** 2, 0))
        with np.errstate(invalid="ignore", divide="ignore"):
            self.bbw = 4 * sd20 / self.ma20
        self.ma50 = _rolling_mean(c, 50, 40)
        self.ma200 = _rolling_mean(c, 200, 150)
        self.hi60_prev = _rolling_max_prev(c, 60)
        self.new_high60 = (c >= self.hi60_prev) & ~np.isnan(self.hi60_prev)
        # all-time high so far and days since
        lc_f = np.where(np.isnan(self.lc), -np.inf, self.lc)
        self.ath = np.maximum.accumulate(lc_f)
        idx = np.arange(T)
        at_ath = lc_f >= self.ath
        last = np.where(at_ath, idx, -1)
        self.last_ath_idx = np.maximum.accumulate(last)
        first = np.argmax(~np.isnan(c)) if np.any(~np.isnan(c)) else T
        self.first_idx = first
        # Chaikin money-flow volume
        rng = h - l
        with np.errstate(invalid="ignore", divide="ignore"):
            clv = np.where(rng > 0, ((c - l) - (h - c)) / rng, 0.0)
        self.clv = clv
        self.mfv = clv * self.v
        with np.errstate(invalid="ignore", divide="ignore"):
            self.wick = np.where(rng > 0, (h - np.maximum(c, _shift(c, 1))) / rng, 0.0)


def compute(ts: TokenSeries, t: np.ndarray, day0: bool = False) -> dict[str, np.ndarray]:
    """Features for day-0 indices `t` (int array). Returns dict of arrays."""
    t = np.asarray(t, dtype=int)
    out: dict[str, np.ndarray] = {}
    b0, b1 = BASELINE

    r_b = _gather(ts.r, t, b0, b1)
    m_b = _gather(ts.m, t, b0, b1)
    ok_b = ~np.isnan(r_b) & ~np.isnan(m_b)
    n_b = ok_b.sum(1)
    rb = np.where(ok_b, r_b, 0.0)
    mb = np.where(ok_b, m_b, 0.0)
    with np.errstate(invalid="ignore", divide="ignore"):
        smm = (mb * mb).sum(1)
        beta = np.where(smm > 0, (rb * mb).sum(1) / smm, 0.0)  # market model through the origin
        beta = np.clip(beta, -1, 4)
        e_b = np.where(ok_b, r_b - beta[:, None] * m_b, np.nan)
        sig_e = _nanstd(e_b, min_n=MIN_BASELINE_OBS)
        sig_r = _nanstd(r_b, min_n=MIN_BASELINE_OBS)
    enough = n_b >= MIN_BASELINE_OBS

    def ar(lo, hi):
        r_w = _gather(ts.r, t, lo, hi)
        m_w = _gather(ts.m, t, lo, hi)
        return r_w - beta[:, None] * np.where(np.isnan(m_w), 0.0, m_w)

    ar_A = ar(-60, -1)
    z_A = ar_A / sig_e[:, None]
    for k, (lo, hi) in {"car_L": (-60, -21), "car_M": (-20, -6), "car_S": (-5, -1), "car_A": (-60, -1)}.items():
        a = ar_A[:, lo + 60: hi + 61]
        cnt = np.sum(~np.isnan(a), 1)
        out[k] = np.where(cnt >= 0.6 * (hi - lo + 1), np.nansum(a, 1), np.nan)

    # volume baseline
    lv_b = _gather(ts.lv, t, b0, b1)
    mu_v = _nanmean(lv_b)
    sd_v = _nanstd(lv_b, min_n=MIN_BASELINE_OBS)
    lv_A = _gather(ts.lv, t, -60, -1)
    av_A = (lv_A - mu_v[:, None]) / sd_v[:, None]
    out["av_mean_S"] = _nanmean(av_A[:, -5:])
    out["av_mean_M"] = _nanmean(av_A[:, 40:55])
    out["av_mean_L"] = _nanmean(av_A[:, :40])
    with np.errstate(all="ignore"):
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            out["av_peak_A"] = np.nanmax(av_A, 1)
    out["n_av2_A"] = np.sum(av_A > 2, 1).astype(float)

    # idiosyncratic volume: lv on market log volume, fitted in the baseline
    mlv_b = _gather(ts.mlv, t, b0, b1)
    ok = ~np.isnan(lv_b) & ~np.isnan(mlv_b)
    x = np.where(ok, mlv_b, np.nan)
    y = np.where(ok, lv_b, np.nan)
    xm, ym = _nanmean(x), _nanmean(y)
    with np.errstate(invalid="ignore", divide="ignore"):
        bx = np.nansum((x - xm[:, None]) * (y - ym[:, None]), 1) / np.nansum((x - xm[:, None]) ** 2, 1)
    bx = np.where(np.isfinite(bx), bx, 0.0)
    res_b = y - ym[:, None] - bx[:, None] * (x - xm[:, None])
    sd_res = _nanstd(res_b, min_n=MIN_BASELINE_OBS)
    mlv_A = _gather(ts.mlv, t, -60, -1)
    iv_A = (lv_A - ym[:, None] - bx[:, None] * (mlv_A - xm[:, None])) / sd_res[:, None]
    out["iv_mean_S"] = _nanmean(iv_A[:, -5:])
    out["iv_mean_L"] = _nanmean(iv_A[:, :40])

    # volume without price: lv on |r|, fitted in the baseline
    ar_b = np.abs(_gather(ts.r, t, b0, b1))
    ok = ~np.isnan(lv_b) & ~np.isnan(ar_b)
    x = np.where(ok, ar_b, np.nan)
    y = np.where(ok, lv_b, np.nan)
    xm, ym = _nanmean(x), _nanmean(y)
    with np.errstate(invalid="ignore", divide="ignore"):
        bu = np.nansum((x - xm[:, None]) * (y - ym[:, None]), 1) / np.nansum((x - xm[:, None]) ** 2, 1)
    bu = np.where(np.isfinite(bu), bu, 0.0)
    sd_u = _nanstd(y - ym[:, None] - bu[:, None] * (x - xm[:, None]), min_n=MIN_BASELINE_OBS)
    absr_A = np.abs(_gather(ts.r, t, -60, -1))
    uv_A = (lv_A - ym[:, None] - bu[:, None] * (absr_A - xm[:, None])) / sd_u[:, None]
    out["uv_mean_S"] = _nanmean(uv_A[:, -5:])
    out["uv_mean_A"] = _nanmean(uv_A)

    # CUSUM of abnormal volume over the last 120 days (k = 0.5)
    lv_C = _gather(ts.lv, t, -CUSUM_LEN, -1)
    av_C = (lv_C - mu_v[:, None]) / sd_v[:, None]
    s = np.zeros(len(t))
    for j in range(av_C.shape[1]):
        inc = np.where(np.isnan(av_C[:, j]), 0.0, av_C[:, j] - 0.5)
        s = np.maximum(0.0, s + inc)
    out["cusum_av_120"] = s

    v_b = _gather(ts.v, t, b0, b1)
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        dv_base = np.nanmedian(v_b, 1)
        mean_v_base = np.nanmean(v_b, 1)
    v_A = _gather(ts.v, t, -60, -1)
    with np.errstate(invalid="ignore", divide="ignore"):
        out["dv_ratio_S"] = np.log(_nanmean(v_A[:, -5:]) / dv_base)
        out["log_dv_base"] = np.log(dv_base)

    # flow: BVC order imbalance, VPIN
    oi_A = _gather(ts.oi, t, -60, -1)
    sv_A = oi_A * v_A
    with np.errstate(invalid="ignore", divide="ignore"):
        out["oi_vw_L"] = np.nansum(sv_A[:, :40], 1) / np.nansum(np.where(np.isnan(sv_A[:, :40]), np.nan, v_A[:, :40]), 1)
        out["oi_vw_S"] = np.nansum(sv_A[:, -5:], 1) / np.nansum(np.where(np.isnan(sv_A[:, -5:]), np.nan, v_A[:, -5:]), 1)
    vp_hist = _gather(ts.vpin, t, -365, -1)
    vp_last = vp_hist[:, -1]
    n_hist = np.sum(~np.isnan(vp_hist), 1)
    with np.errstate(invalid="ignore"):
        rank = np.sum(vp_hist <= vp_last[:, None], 1) / np.maximum(n_hist, 1)
    out["vpin_cdf"] = np.where((n_hist >= 120) & ~np.isnan(vp_last), rank, np.nan)
    vp_b = _gather(ts.vpin, t, b0, b1)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        vp_mu, vp_sd = np.nanmean(vp_b, 1), np.nanstd(vp_b, 1)
        thr = np.nanpercentile(vp_b, 80, axis=1) if vp_b.size else np.array([])
    vp_A = _gather(ts.vpin, t, -60, -1)
    with np.errstate(invalid="ignore", divide="ignore"):
        out["vpin_z_S"] = (_nanmean(vp_A[:, -5:]) - vp_mu) / vp_sd
    toxic = (vp_A > thr[:, None])
    buy = oi_A > 0

    # Chaikin money flow 20d
    mfv_20 = _gather(ts.mfv, t, -20, -1)
    v_20 = _gather(ts.v, t, -20, -1)
    with np.errstate(invalid="ignore", divide="ignore"):
        out["cmf20"] = np.nansum(mfv_20, 1) / np.nansum(np.where(np.isnan(mfv_20), np.nan, v_20), 1)

    # OBV and toxic OBV (normalised by baseline mean daily volume)
    obv_A = _gather(ts.obv_inc, t, -60, -1)
    with np.errstate(invalid="ignore", divide="ignore"):
        out["obv_A"] = np.nansum(obv_A, 1) / (60 * mean_v_base)
        out["obv_S20"] = np.nansum(obv_A[:, -20:], 1) / (20 * mean_v_base)
        out["tobv_A"] = np.nansum(np.where(toxic, obv_A, 0.0), 1) / (60 * mean_v_base)
        out["tobv_S20"] = np.nansum(np.where(toxic[:, -20:], obv_A[:, -20:], 0.0), 1) / (20 * mean_v_base)

    # price path
    lc_t1 = _gather(ts.lc, t, -1, -1)[:, 0]
    lc_31 = _gather(ts.lc, t, -31, -31)[:, 0]
    lc_91 = _gather(ts.lc, t, -91, -91)[:, 0]
    out["mom_30"] = lc_t1 - lc_31
    out["mom_90"] = lc_t1 - lc_91
    b_t1 = _gather(ts.btc_lc, t, -1, -1)[:, 0]
    b_91 = _gather(ts.btc_lc, t, -91, -91)[:, 0]
    out["rs_btc_90"] = out["mom_90"] - (b_t1 - b_91)
    r_A = _gather(ts.r, t, -60, -1)
    with np.errstate(invalid="ignore", divide="ignore"):
        out["vol_ratio_A"] = np.log(_nanstd(r_A, min_n=30) / sig_r)
        rms_S = np.sqrt(_nanmean(r_A[:, -5:] ** 2))
        out["vol_ratio_S"] = np.log(rms_S / sig_r)
    out["n_up_jumps_A"] = np.sum(z_A > 2, 1).astype(float)
    out["n_dn_jumps_A"] = np.sum(z_A < -2, 1).astype(float)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        out["max_up_z_M"] = np.nanmax(z_A[:, -20:], 1)
    zc = z_A - _nanmean(z_A)[:, None]
    with np.errstate(invalid="ignore", divide="ignore"):
        out["skew_A"] = _nanmean(zc ** 3) / _nanmean(zc ** 2) ** 1.5
    lc_A = _gather(ts.lc, t, -60, -1)
    run = np.fmax.accumulate(np.where(np.isnan(lc_A), -np.inf, lc_A), axis=1)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        out["max_dd_A"] = np.nanmin(np.where(np.isnan(lc_A), np.nan, lc_A - run), 1)
    ath = _gather(ts.ath, t, -1, -1)[:, 0]
    out["dd_ath"] = np.where(np.isfinite(ath), lc_t1 - ath, np.nan)
    last_ath = ts.last_ath_idx[np.clip(t - 1, 0, None)]
    out["days_since_ath"] = np.log1p(np.where(last_ath >= 0, (t - 1) - last_ath, np.nan))
    ma200 = _gather(ts.ma200, t, -1, -1)[:, 0]
    ma50 = _gather(ts.ma50, t, -1, -1)[:, 0]
    out["dist_ma200"] = lc_t1 - np.log(ma200)
    out["dist_ma50"] = lc_t1 - np.log(ma50)
    c_90 = _gather(ts.c, t, -91, -2)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        out["brk_90"] = lc_t1 - np.log(np.nanmax(c_90, 1))
    nh = _gather(ts.new_high60.astype(float), t, -20, -1)
    out["n_high60_S20"] = np.nansum(nh, 1)
    # trend t-stat
    xk = np.arange(60, dtype=float)[None, :] * np.ones((len(t), 1))
    okk = ~np.isnan(lc_A)
    n_k = okk.sum(1)
    xk = np.where(okk, xk, np.nan)
    xmn, ymn = _nanmean(xk), _nanmean(lc_A)
    sxx = np.nansum((xk - xmn[:, None]) ** 2, 1)
    sxy = np.nansum((xk - xmn[:, None]) * (lc_A - ymn[:, None]), 1)
    syy = np.nansum((lc_A - ymn[:, None]) ** 2, 1)
    with np.errstate(invalid="ignore", divide="ignore"):
        slope = sxy / sxx
        sse = np.maximum(syy - slope * sxy, 1e-12)
        out["trend_t60"] = np.where(n_k >= 30, slope / np.sqrt(sse / np.maximum(n_k - 2, 1) / sxx), np.nan)
    c_A = _gather(ts.c, t, -60, -1)
    ma20_A = _gather(ts.ma20, t, -60, -1)
    above = (c_A > ma20_A)
    out["above_ma20_A"] = np.where(n_k >= 30, np.sum(above, 1) / np.maximum(n_k, 1), np.nan)
    h20, l20 = _gather(ts.h, t, -20, -1), _gather(ts.l, t, -20, -1)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        hh, ll = np.nanmax(h20, 1), np.nanmin(l20, 1)
    c_t1 = np.exp(lc_t1)
    with np.errstate(invalid="ignore", divide="ignore"):
        out["range_pos20"] = (c_t1 - ll) / (hh - ll)
    bb_hist = _gather(ts.bbw, t, -180, -1)
    bb_last = bb_hist[:, -1]
    nb = np.sum(~np.isnan(bb_hist), 1)
    with np.errstate(invalid="ignore"):
        out["bbw_pct"] = np.where((nb >= 90) & ~np.isnan(bb_last),
                                  np.sum(bb_hist <= bb_last[:, None], 1) / np.maximum(nb, 1), np.nan)
    m_A = _gather(ts.m, t, -60, -1)
    ok = ~np.isnan(r_A) & ~np.isnan(m_A)
    ra, ma_ = np.where(ok, r_A, np.nan), np.where(ok, m_A, np.nan)
    with np.errstate(invalid="ignore", divide="ignore"):
        cov = _nanmean((ra - _nanmean(ra)[:, None]) * (ma_ - _nanmean(ma_)[:, None]))
        out["corr_mkt_A"] = cov / (np.sqrt(_nanmean((ra - _nanmean(ra)[:, None]) ** 2))
                                   * np.sqrt(_nanmean((ma_ - _nanmean(ma_)[:, None]) ** 2)))
    out["log_age"] = np.log(np.maximum(t - ts.first_idx, 1))

    # liquidity
    with np.errstate(invalid="ignore", divide="ignore"):
        ami_b = _nanmean(np.abs(r_b) / v_b * 1e6)
        ami_A = _nanmean(np.abs(r_A) / v_A * 1e6)
        out["amihud_ratio_A"] = np.log(ami_A / ami_b)
        sv_b = _gather(ts.sv, t, b0, b1) / 1e6
        lam_b = np.nansum(r_b * sv_b, 1) / np.nansum(np.where(np.isnan(r_b), np.nan, sv_b) ** 2, 1)
        svA = sv_A / 1e6
        lam_A = np.nansum(r_A * svA, 1) / np.nansum(np.where(np.isnan(r_A), np.nan, svA) ** 2, 1)
        out["kyle_ratio_A"] = np.where((lam_b > 0) & (lam_A > 0), np.log(lam_A / lam_b), np.nan)

    # toxic composites
    nh60 = _gather(ts.new_high60.astype(float), t, -60, -1) > 0
    out["toxic_breakout_S20"] = np.sum((nh60 & toxic & buy)[:, -20:], 1).astype(float)
    out["toxic_mom_A"] = np.nansum(np.where(toxic, r_A, 0.0), 1)
    out["toxic_mom_S20"] = np.nansum(np.where(toxic[:, -20:], r_A[:, -20:], 0.0), 1)
    out["toxic_trend_A"] = np.where(n_k >= 30, np.sum(above & toxic & buy, 1) / np.maximum(n_k, 1), np.nan)
    out["toxic_accum_A"] = np.clip(out["uv_mean_A"], 0, None) * np.clip(
        np.nansum(sv_A, 1) / np.nansum(np.where(np.isnan(sv_A), np.nan, v_A), 1), 0, None)
    out["toxic_squeeze"] = (1 - out["bbw_pct"]) * np.clip(out["vpin_z_S"], 0, None)
    with np.errstate(invalid="ignore", divide="ignore"):
        car_z_S = out["car_S"] / (sig_e * np.sqrt(5))
    out["capitulation_S"] = np.clip(out["av_mean_S"], 0, None) * np.clip(-car_z_S, 0, None) \
        * np.clip(-out["oi_vw_S"], 0, None)

    if day0:
        r0 = ts.r[t]
        m0 = np.where(np.isnan(ts.m[t]), 0.0, ts.m[t])
        out["d0_ret"] = np.expm1(r0)
        out["d0_z"] = (r0 - beta * m0) / sig_e
        out["d0_av"] = (ts.lv[t] - mu_v) / sd_v
        out["d0_clv"] = ts.clv[t]
        out["d0_wick"] = ts.wick[t]
        with np.errstate(invalid="ignore", divide="ignore"):
            out["d0_dv_ratio"] = np.log(ts.v[t] / dv_base)

    # auxiliaries used for matching / outcomes (not analysed as features)
    out["_beta"] = beta
    out["_sig_e"] = sig_e
    out["_sig_r"] = sig_r
    out["_n_base"] = n_b.astype(float)
    out["_dv_base"] = dv_base
    for k in list(out):
        x = np.asarray(out[k], dtype=float)
        x = np.where(np.isfinite(x), x, np.nan)
        if not k.startswith("_") and k not in ("log_age",):
            x = np.where(enough, x, np.nan)
        out[k] = x
    return out


def paths(ts: TokenSeries, t: np.ndarray, lo: int = -60, hi: int = 180) -> tuple[np.ndarray, np.ndarray]:
    """Abnormal volume and cumulative abnormal return (from day `lo`) around day 0,
    both on the event's own baseline."""
    t = np.asarray(t, dtype=int)
    b0, b1 = BASELINE
    r_b, m_b = _gather(ts.r, t, b0, b1), _gather(ts.m, t, b0, b1)
    ok = ~np.isnan(r_b) & ~np.isnan(m_b)
    rb, mb = np.where(ok, r_b, 0.0), np.where(ok, m_b, 0.0)
    with np.errstate(invalid="ignore", divide="ignore"):
        smm = (mb * mb).sum(1)
        beta = np.clip(np.where(smm > 0, (rb * mb).sum(1) / smm, 0.0), -1, 4)
    lv_b = _gather(ts.lv, t, b0, b1)
    mu_v, sd_v = _nanmean(lv_b), _nanstd(lv_b, min_n=MIN_BASELINE_OBS)
    av = (_gather(ts.lv, t, lo, hi) - mu_v[:, None]) / sd_v[:, None]
    ar = _gather(ts.r, t, lo, hi) - beta[:, None] * np.nan_to_num(_gather(ts.m, t, lo, hi))
    car = np.cumsum(np.nan_to_num(ar), axis=1)
    car[np.isnan(_gather(ts.c, t, lo, hi))] = np.nan
    return av.astype(np.float32), car.astype(np.float32)
