#!/usr/bin/env python3
"""
Shared signal primitives: the Ehlers bandpass and a single, hysteresis-aware
zero-line crossing detector used by every scanner. Consolidates three previously
divergent implementations (which produced the quadrant-vs-slope inconsistencies).
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

# (name, fast, slow) — the Ehlers 4-band lengths in bars
BANDS = [("B1", 40, 60), ("B2", 200, 300), ("B3", 600, 900), ("B4", 1200, 2400)]


def ehlers_bandpass(src: np.ndarray, flen: int, slen: int) -> np.ndarray:
    """Two-pole Ehlers bandpass (faithful port of the Pine recursion, nz=0)."""
    a1, a2 = 5.0 / flen, 5.0 / slen
    b0 = a1 - a2
    b1 = a2 * (1 - a1) - a1 * (1 - a2)
    c1 = (1 - a1) + (1 - a2)
    c2 = -(1 - a1) * (1 - a2)
    n = len(src)
    pb = np.zeros(n, dtype=float)
    for t in range(n):
        s0 = src[t]
        s1 = src[t - 1] if t >= 1 else 0.0
        p1 = pb[t - 1] if t >= 1 else 0.0
        p2 = pb[t - 2] if t >= 2 else 0.0
        pb[t] = b0 * s0 + b1 * s1 + c1 * p1 + c2 * p2
    return pb


def latest_crossing(values: np.ndarray, recent: int, bands=None,
                    hysteresis: float = 0.10) -> dict[str, dict]:
    """Most-recent *decisive* zero-line crossing per band for one series.

    A crossing counts only once the bandpass has moved beyond ``hysteresis`` * sd
    past zero in the new direction (kills one-bar wiggles). Returns dir / bars_ago
    / slope_z (normalised single-bar momentum) / pb_z / fresh / settled.
    """
    bands = bands or BANDS
    v = values[~np.isnan(values)]
    n = len(v)
    out: dict[str, dict] = {}
    for name, flen, slen in bands:
        if n < slen:
            continue
        pb = ehlers_bandpass(v, flen, slen)
        settled = pb[slen:]
        sd = np.std(settled) if settled.size > 5 else np.std(pb)
        if not np.isfinite(sd) or sd == 0:
            continue
        thr = hysteresis * sd
        # walk back to the last bar where pb decisively flipped sign (|pb|>thr)
        ci = None
        cur_sign = 0
        for t in range(n - 1, max(slen, 1), -1):
            s = 1 if pb[t] > thr else (-1 if pb[t] < -thr else 0)
            if s == 0:
                continue
            if cur_sign == 0:
                cur_sign = s
            elif s != cur_sign:
                ci = t + 1  # first decisive bar of the current regime
                break
        if ci is None:
            continue
        out[name] = {
            "dir": "UP" if pb[ci] > 0 else "DOWN",
            "bars_ago": (n - 1) - ci,
            "slope_z": float((pb[-1] - pb[-2]) / sd) if n >= 2 else 0.0,
            "pb_z": float(pb[-1] / sd),
            "fresh": (n - 1) - ci <= recent,
            "settled": n >= int(1.5 * slen),
        }
    return out


def drop_incomplete_last(df, tf: str, asof: pd.Timestamp | None = None):
    """Drop the trailing in-progress bar.

    intraday: always drop the final (partial) bar.
    daily:    drop if the last bar is today (still forming).
    weekly:   drop if the last bar falls in the current ISO week.
    """
    d = df.dropna()
    if len(d) < 2:
        return d
    last = d.index[-1]
    now = pd.Timestamp(asof) if asof is not None else pd.Timestamp.utcnow().tz_localize(None)
    last = pd.Timestamp(last).tz_localize(None) if last.tzinfo else pd.Timestamp(last)
    if tf.endswith("m") or tf.endswith("h"):
        return d.iloc[:-1]
    if tf == "daily":
        return d.iloc[:-1] if last.date() >= now.date() else d
    if tf == "weekly":
        ly, lw, _ = last.isocalendar()
        ny, nw, _ = now.isocalendar()
        return d.iloc[:-1] if (ly, lw) >= (ny, nw) else d
    return d


# --------------------------------------------------------------------------- #
# Low-lag smoothing + curvature-based EARLY inflection detection
# --------------------------------------------------------------------------- #
def super_smoother(src: np.ndarray, length: int) -> np.ndarray:
    """Ehlers 2-pole SuperSmoother — denoises with far less lag than an SMA/EMA
    of the same period, so a turn in the *level* is visible early."""
    a1 = math.exp(-1.414 * math.pi / length)
    b1 = 2 * a1 * math.cos(1.414 * math.pi / length)
    c2, c3 = b1, -a1 * a1
    c1 = 1 - c2 - c3
    n = len(src)
    f = np.zeros(n, dtype=float)
    for t in range(n):
        s = (src[t] + src[t - 1]) / 2 if t >= 1 else src[t]
        f1 = f[t - 1] if t >= 1 else src[t]
        f2 = f[t - 2] if t >= 2 else src[t]
        f[t] = c1 * s + c2 * f1 + c3 * f2
    return f


def smoothed_inflection(values: np.ndarray, length: int, recent: int) -> dict | None:
    """Most-recent inflection of a SuperSmoothed series.

    The level inflects where its velocity (1st difference of the smooth) changes
    sign — i.e. a *trough* (down→up, dir UP) or *peak* (up→down, dir DOWN). This
    leads a bandpass zero-cross: it fires at the turning point itself, not after
    the move is underway. Strength = curvature (acceleration) normalised by the
    velocity's own scale.
    """
    v = values[~np.isnan(values)]
    n = len(v)
    if n < 3 * length:
        return None
    f = super_smoother(v, length)
    vel = np.diff(f, prepend=f[0])
    acc = np.diff(vel, prepend=vel[0])
    sd = np.std(vel[length:]) if n > length + 5 else np.std(vel)
    if not np.isfinite(sd) or sd == 0:
        return None
    sgn = np.sign(vel)
    ci = None
    for t in range(n - 1, max(length, 1), -1):
        if sgn[t] != sgn[t - 1] and sgn[t] != 0:
            ci = t
            break
    if ci is None:
        return None
    bars_ago = (n - 1) - ci
    return {
        "dir": "UP" if vel[-1] > 0 else "DOWN",
        "bars_ago": bars_ago,
        "vel_z": float(vel[-1] / sd),       # current smoothed slope (normalised)
        "curv_z": float(acc[-1] / sd),      # current curvature (how sharp the turn)
        "fresh": bars_ago <= recent,
    }
