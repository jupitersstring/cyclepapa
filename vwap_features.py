"""VWAP feature suite for the MU-style dip/breakout screen, from daily bars
(/tmp/fmp_daily), computed on daily + weekly + monthly timeframes.

Features (current-state, per ticker):

  ANCHORED YTD VWAP — anchor at the first trading day of the current year; the
  "line in the sand" for dip buys into year-end.
     dist_avwap_ytd  close/AVWAP-1 ; near_avwap_ytd |dist|<=4% ; above_avwap_ytd

  21/50/200 VWAP CROSS (rolling VWAPs) — flag when the 21-period VWAP is above
  BOTH the 50 and 200, with RECENCY (more recent cross = higher score). Monthly
  uses 7/21/50 (history rarely permits a 200-month VWAP).
     {d,w,m}_cross_up , {d,w,m}_cross_recency (bars since the cross)

  LONG CONSOLIDATION via VWAPs — the weekly & monthly VWAPs going HORIZONTAL
  (near-zero slope) and NARROW (tight cluster) for a long time = a long base.
     {w,m}_vwap_slope , {w,m}_vwap_narrow , {w,m}_vwap_flat_len

  VOLUME SPIKE — recent daily RVOL vs its trailing median.
     rvol_recent , vol_spike_recent

Composite: vwap_cross_score, vwap_consol_score, vwap_setup_score.
Writes /tmp/vwap_features.csv and data/monster/vwap_features.csv.
"""
import glob, os, sys
from datetime import datetime, timezone
import numpy as np
import pandas as pd

DAILY = "/tmp/fmp_daily"
OUT = "/tmp/vwap_features.csv"
DELIVER = "/home/user/cyclepapa/data/monster/vwap_features.csv"
YEAR_START = pd.Timestamp(datetime.now(timezone.utc).year, 1, 1)


def rvwap(df, n):
    tp = (df.High + df.Low + df.Close) / 3
    pv = (tp * df.Volume).rolling(n).sum()
    vv = df.Volume.rolling(n).sum().replace(0, np.nan)
    return pv / vv


def anchored_vwap(df, anchor):
    d = df[df.index >= anchor]
    if len(d) < 5:
        return np.nan
    tp = (d.High + d.Low + d.Close) / 3
    return float((tp * d.Volume).cumsum().iloc[-1] / d.Volume.cumsum().iloc[-1])


def cross_state(v_fast, v_mid, v_slow):
    """cross_up now + bars since the 21 went above BOTH mid and slow."""
    cu = (v_fast > v_mid) & (v_fast > v_slow)
    cu = cu.fillna(False)
    if not bool(cu.iloc[-1]):
        return 0, np.nan
    # length of current True streak = bars since the cross began
    n = 0
    for val in reversed(cu.values):
        if val:
            n += 1
        else:
            break
    return 1, n


def tf_features(df, fast, mid, slow, prefix):
    out = {}
    if len(df) < mid + 5:
        return {f"{prefix}_cross_up": 0, f"{prefix}_cross_recency": np.nan,
                f"{prefix}_vwap_slope": np.nan, f"{prefix}_vwap_narrow": np.nan,
                f"{prefix}_vwap_flat_len": 0}
    vf, vm = rvwap(df, fast), rvwap(df, mid)
    vs = rvwap(df, slow) if len(df) >= slow + 5 else vm
    cu, rec = cross_state(vf, vm, vs)
    out[f"{prefix}_cross_up"] = cu
    out[f"{prefix}_cross_recency"] = rec
    px = float(df.Close.iloc[-1])
    # narrowness: spread of the 3 VWAPs / price (tight = consolidation)
    trio = pd.concat([vf, vm, vs], axis=1)
    out[f"{prefix}_vwap_narrow"] = float((trio.max(axis=1) - trio.min(axis=1)).iloc[-1] / px) if px else np.nan
    # horizontality: slope of the mid VWAP over ~half its window, normalised
    k = max(4, mid // 2)
    if len(vm.dropna()) > k:
        slope = (vm.iloc[-1] - vm.iloc[-k]) / (vm.iloc[-k] if vm.iloc[-k] else np.nan) / k
        out[f"{prefix}_vwap_slope"] = float(slope)
        # flat length: how many recent bars the per-bar slope stayed small
        perbar = vm.pct_change()
        flat = (perbar.abs() < 0.004)
        n = 0
        for val in reversed(flat.values):
            if bool(val):
                n += 1
            else:
                break
        out[f"{prefix}_vwap_flat_len"] = n
    else:
        out[f"{prefix}_vwap_slope"] = np.nan
        out[f"{prefix}_vwap_flat_len"] = 0
    return out


def features_for(t, df):
    df = df.dropna(subset=["Close", "Volume"])
    if len(df) < 120:
        return None
    r = {"ticker": t}
    px = float(df.Close.iloc[-1])
    # anchored YTD VWAP
    av = anchored_vwap(df, YEAR_START)
    r["avwap_ytd"] = av
    r["dist_avwap_ytd"] = (px / av - 1) if av and np.isfinite(av) else np.nan
    r["near_avwap_ytd"] = int(np.isfinite(r["dist_avwap_ytd"]) and abs(r["dist_avwap_ytd"]) <= 0.04)
    r["above_avwap_ytd"] = int(np.isfinite(r["dist_avwap_ytd"]) and r["dist_avwap_ytd"] >= 0)
    # daily 21/50/200
    r.update(tf_features(df, 21, 50, 200, "d"))
    # weekly 21/50/200
    w = df.resample("W-FRI").agg(Open=("Open", "first"), High=("High", "max"),
                                 Low=("Low", "min"), Close=("Close", "last"),
                                 Volume=("Volume", "sum")).dropna(subset=["Close"])
    r.update(tf_features(w, 21, 50, 200, "w"))
    # monthly 7/21/50
    m = df.resample("ME").agg(Open=("Open", "first"), High=("High", "max"),
                              Low=("Low", "min"), Close=("Close", "last"),
                              Volume=("Volume", "sum")).dropna(subset=["Close"])
    r.update(tf_features(m, 7, 21, 50, "m"))
    # recent volume spike (daily RVOL)
    vmed = df.Volume.iloc[-64:-4].median()
    r["rvol_recent"] = float(df.Volume.iloc[-5:].max() / vmed) if vmed and vmed > 0 else np.nan
    r["vol_spike_recent"] = int(np.isfinite(r["rvol_recent"]) and r["rvol_recent"] >= 2.0)
    return r


def main():
    rows = []
    for f in glob.glob(os.path.join(DAILY, "*.csv")):
        t = os.path.basename(f)[:-4].replace("__", "/")
        try:
            df = pd.read_csv(f, index_col=0, parse_dates=True)
        except Exception:
            continue
        r = features_for(t, df)
        if r:
            rows.append(r)
    p = pd.DataFrame(rows)
    if p.empty:
        print("no daily bars yet"); return

    # composites
    def rec_score(col):
        # recent cross scores high; decays with bars since; 0 if not crossed up
        rec = p[col]
        return np.where(p[col.replace("recency", "up")] > 0, 1 / (1 + rec / 12), 0.0)
    p["vwap_cross_score"] = (0.30 * rec_score("d_cross_recency")
                             + 0.40 * rec_score("w_cross_recency")
                             + 0.30 * rec_score("m_cross_recency")).round(3)
    # consolidation: flat (low |slope|) + narrow weekly & monthly VWAPs + duration
    def flatnarrow(pref):
        slope_flat = 1 - (p[f"{pref}_vwap_slope"].abs() / 0.01).clip(0, 1)
        narrow = 1 - (p[f"{pref}_vwap_narrow"] / 0.25).clip(0, 1)
        dur = (p[f"{pref}_vwap_flat_len"] / (26 if pref == "w" else 12)).clip(0, 1)
        return (0.4 * slope_flat.fillna(0) + 0.4 * narrow.fillna(0) + 0.2 * dur).clip(0, 1)
    p["vwap_consol_score"] = (0.6 * flatnarrow("w") + 0.4 * flatnarrow("m")).round(3)
    # full setup: recent cross out of a long tight base, holding above the YTD line
    p["vwap_setup_score"] = (100 * p["vwap_cross_score"] * (0.5 + p["vwap_consol_score"])
                             * (0.8 + 0.2 * p["above_avwap_ytd"])
                             * (1 + 0.15 * p["vol_spike_recent"])).round(2)

    p.to_csv(OUT, index=False)
    os.makedirs(os.path.dirname(DELIVER), exist_ok=True)
    p.round(4).to_csv(DELIVER, index=False)
    print(f"VWAP features: {len(p)} tickers")
    print(f"  near YTD AVWAP: {int(p.near_avwap_ytd.sum())} | above: {int(p.above_avwap_ytd.sum())}")
    print(f"  weekly 21>50>200 cross-up: {int(p.w_cross_up.sum())} | monthly 7>21>50: {int(p.m_cross_up.sum())}")
    print(f"  recent vol spike: {int(p.vol_spike_recent.sum())}")


if __name__ == "__main__":
    main()
