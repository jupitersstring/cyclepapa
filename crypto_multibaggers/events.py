"""Re-rating triggers, multibagger outcomes and matched placebo windows.

Day 0 is the first tradable reaction: a day whose market-model abnormal
return is at least 3 baseline sigmas and +15% raw, with no other such day for
the token in the previous 60 days. Outcomes are measured from the day -1
close; the multiple uses a trailing 5-day median close so a single print
cannot make a multibagger.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .config import (BASELINE, JUMP_MIN_RET, JUMP_Z, MIN_BASELINE_OBS, N_PLACEBO,
                     PLACEBO_EXCLUSION, POST, REFRACTORY, TIERS)

MIN_DV_BASE = 20_000.0      # baseline median USD volume for a tradeable tape
MIN_AGE = 121               # days of history before day 0 (60 baseline quotes + the 60-day window)
MAX_D0 = np.log(5.0)        # day-0 moves above +400% are treated as data splices


def baseline_frames(p: dict[str, pd.DataFrame], mkt: pd.DataFrame, syms: list[str]) -> dict[str, pd.DataFrame]:
    """Rolling (lagged) baseline estimates for every token-day: beta, residual
    sigma, abnormal-return z, baseline USD volume, age and eligibility."""
    c = p["close"][syms]
    v = p["volume"][syms]
    r = np.log(c).diff()
    m = mkt["mret"].reindex(c.index)
    W, lag = BASELINE[1] - BASELINE[0] + 1, -BASELINE[1]
    ok = r.notna() & m.notna().to_numpy()[:, None]
    M = pd.DataFrame(np.repeat(m.to_numpy()[:, None], len(syms), 1), index=c.index, columns=syms)
    rr_, mm_ = r.where(ok), M.where(ok)

    def rs(x):
        return x.rolling(W, min_periods=1).sum().shift(lag)

    n = ok.rolling(W, min_periods=1).sum().shift(lag)
    s_rm, s_mm, s_r, s_m, s_rr = rs(rr_ * mm_), rs(mm_ * mm_), rs(rr_), rs(mm_), rs(rr_ * rr_)
    beta = (s_rm / s_mm).clip(-1, 4).fillna(0.0)
    mean_e = (s_r - beta * s_m) / n
    e2 = (s_rr - 2 * beta * s_rm + beta ** 2 * s_mm) / n
    sig_e = np.sqrt((e2 - mean_e ** 2).clip(lower=0) * n / (n - 1))
    ar = r - beta * M.fillna(0.0)
    z = ar / sig_e
    sig_r = r.rolling(W, min_periods=MIN_BASELINE_OBS).std().shift(lag)
    dv_base = v.where(v > 0).rolling(W, min_periods=MIN_BASELINE_OBS).median().shift(lag)
    first = c.notna().cummax()
    age = first.cumsum().where(first)
    elig = (n >= MIN_BASELINE_OBS) & (dv_base >= MIN_DV_BASE) & (age >= MIN_AGE) & c.shift(1).notna()
    # the day -1 close must agree with the week before it (no bad print as the reference)
    lc = np.log(c)
    ref_ok = (lc.shift(1) - lc.shift(2).rolling(5, min_periods=3).median()).abs() < np.log(2.5)
    return {"r": r, "ar": ar, "z": z, "sig_e": sig_e, "sig_r": sig_r, "dv_base": dv_base,
            "age": age, "elig": elig, "beta": beta, "ref_ok": ref_ok}


def detect_triggers(bf: dict[str, pd.DataFrame]) -> tuple[pd.DataFrame, pd.DataFrame]:
    raw = bf["elig"] & bf["ref_ok"] & (bf["z"] >= JUMP_Z) & (bf["r"] >= np.log1p(JUMP_MIN_RET)) & (bf["r"] < MAX_D0)
    raw_any = (bf["z"] >= JUMP_Z) & (bf["r"] >= np.log1p(JUMP_MIN_RET))   # quiet-period check ignores eligibility
    prior = raw_any.astype(float).rolling(REFRACTORY, min_periods=1).max().shift(1).fillna(0)
    ev = raw & (prior == 0)
    return ev, raw_any


def outcomes(c: np.ndarray, t: np.ndarray) -> dict[str, np.ndarray]:
    """Forward outcomes for day-0 indices t on one token's close series."""
    T = len(c)
    med5 = pd.Series(c).rolling(5, min_periods=3).median().to_numpy()
    p_ref = c[t - 1]
    out = {k: np.full(len(t), np.nan) for k in
           ["mult_90", "mult_180", "mult_365", "mult_180_entry", "days_to_peak", "r_1", "r_20", "r_60", "r_180",
            "maxdd_180", "last_obs_day"]}
    last_valid = np.where(~np.isnan(c))[0]
    last_valid = last_valid[-1] if len(last_valid) else -1
    for i, ti in enumerate(t):
        if np.isnan(p_ref[i]):
            continue
        for h in (90, 180, 365):
            seg = med5[ti + 1: min(ti + h + 1, T)]
            if len(seg) and np.any(~np.isnan(seg)):
                out[f"mult_{h}"][i] = np.nanmax(seg) / p_ref[i]
                if h == 180:
                    out["days_to_peak"][i] = int(np.nanargmax(seg)) + 1
        e = c[ti + 1] if ti + 1 < T else np.nan
        seg = med5[ti + 2: min(ti + 181, T)]
        if not np.isnan(e) and len(seg) and np.any(~np.isnan(seg)):
            out["mult_180_entry"][i] = np.nanmax(seg) / e
        for h in (1, 20, 60, 180):
            lo, hi = ti + max(h - 5, 0), min(ti + h, T - 1)
            seg = c[lo: hi + 1] if hi >= lo else np.array([])
            v = seg[~np.isnan(seg)]
            if len(v):
                out[f"r_{h}"][i] = np.log(v[-1] / p_ref[i])
            elif ti + h <= T - 1 and last_valid < ti + h:     # token stopped trading: take its last print
                lv = c[:ti + h + 1][~np.isnan(c[:ti + h + 1])]
                out[f"r_{h}"][i] = np.log(lv[-1] / p_ref[i]) if len(lv) else np.nan
        seg = c[ti: min(ti + 181, T)]
        if np.any(~np.isnan(seg)):
            run = np.fmax.accumulate(np.where(np.isnan(seg), -np.inf, seg))
            out["maxdd_180"][i] = np.nanmin(np.where(np.isnan(seg), np.nan, seg / run - 1))
        out["last_obs_day"][i] = last_valid - ti
    return out


def tier(mult: float) -> str:
    if np.isnan(mult):
        return "n/a"
    for thr, name in TIERS:
        if mult >= thr:
            return name
    return "<2x"


def sample_placebos(ev: pd.DataFrame, bf: dict[str, pd.DataFrame], raw_any: pd.DataFrame,
                    seed: int = 7) -> pd.DataFrame:
    """For each event: N_PLACEBO windows on the same calendar day from tokens with
    no trigger within +/-60 days, nearest in baseline USD volume, volatility and age."""
    rng = np.random.default_rng(seed)
    near = raw_any.astype(float).rolling(2 * PLACEBO_EXCLUSION + 1, center=True, min_periods=1).max() > 0
    pool_ok = bf["elig"] & ~near
    X = {k: np.log(bf[k].where(bf[k] > 0)) for k in ("dv_base", "sig_r", "age")}
    sd = {k: np.nanstd(X[k].where(bf["elig"]).to_numpy()) for k in X}
    rows = []
    cols = np.array(bf["elig"].columns)
    for d, grp in ev.groupby("date"):
        i = bf["elig"].index.get_loc(d)
        cand = np.where(pool_ok.iloc[i].to_numpy())[0]
        if len(cand) == 0:
            continue
        cx = np.column_stack([X[k].iloc[i].to_numpy()[cand] / sd[k] for k in X])
        good = np.all(np.isfinite(cx), 1)
        cand, cx = cand[good], cx[good]
        used = set()
        for _, e in grp.sample(frac=1, random_state=int(rng.integers(1 << 31))).iterrows():
            j = bf["elig"].columns.get_loc(e["symbol"])
            ex = np.array([X[k].iat[i, j] / sd[k] for k in X])
            if not np.all(np.isfinite(ex)):
                continue
            dist = np.sqrt(((cx - ex) ** 2).sum(1))
            order = np.argsort(dist)
            k = 0
            for o in order:
                if cand[o] in used or cols[cand[o]] == e["symbol"]:
                    continue
                used.add(cand[o])
                rows.append({"symbol": cols[cand[o]], "date": d, "event_id": e["event_id"], "match_dist": dist[o]})
                k += 1
                if k == N_PLACEBO:
                    break
    return pd.DataFrame(rows)
