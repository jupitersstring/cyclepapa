#!/usr/bin/env python3
"""
Rotation screener — where is the money flowing?

For every name (cached daily bars; no network needed for prices):

  Price action   : % return over 5d (intra-week), 10d (fortnight), 21d (month)
  "Sharpe action": (Close_t - Close_{t-k}) / ATR14 — the move measured in ATR
                   units (unit-free risk-adjusted thrust). ATR uses the
                   close-to-close proxy |dClose| since the cache lacks H/L.

All six features are cross-sectionally z-scored (winsorized) to remove unit
bias, then:

  * K-MEANS clusters names with similar multi-horizon action (k configurable)
  * a 63-day return CORRELATION matrix tightens each cluster (avg intra-corr,
    most-correlated pairs inside the leading clusters)
  * industry labels (yfinance `info['industry']`, persistently cached, with
    financedatabase fallback) aggregate the flow:
       blend  = 0.5*z5 + 0.3*z10 + 0.2*z21      (recent-weighted, $vol-weighted)
       accel  = z5 - z21                        (>0 = money arriving NOW)

Usage:
  python3 rotation_screener.py                                 # default cuts
  python3 rotation_screener.py --universes us-midcap uk-allcap --k 10
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import time
import warnings

import numpy as np
import pandas as pd

from midcap_weekly_anomalies import get_universe, CACHE_DIR
from signals import drop_incomplete_last

warnings.filterwarnings("ignore")
RESULTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results")
IND_CACHE = os.path.join(CACHE_DIR, "industry_labels.json")
HORIZONS = (5, 10, 21)


# --------------------------------------------------------------------------- #
# Industry labels: yfinance (persistently cached) with financedatabase fallback
# --------------------------------------------------------------------------- #
def fd_labels(countries=("United States", "United Kingdom")) -> dict[str, tuple]:
    import financedatabase as fd
    out = {}
    eq = fd.Equities()
    for c in countries:
        df = eq.select(country=c)
        for t, r in df.iterrows():
            s = str(t).replace(".", "-") if not str(t).endswith(".L") else str(t)
            out[s] = (r.get("sector"), r.get("industry"))
    return out


def yf_label_fill(symbols, cache: dict, max_fetch=150) -> dict:
    """Fetch genuine yfinance industry labels for up to max_fetch missing names."""
    import yfinance as yf
    todo = [s for s in symbols if s not in cache][:max_fetch]
    for s in todo:
        try:
            info = yf.Ticker(s).info or {}
            cache[s] = {"sector": info.get("sector"), "industry": info.get("industry")}
        except Exception:
            cache[s] = {"sector": None, "industry": None}
        time.sleep(0.3)
    return cache


# --------------------------------------------------------------------------- #
# Features
# --------------------------------------------------------------------------- #
def build_features(frames: dict, min_bars=80) -> pd.DataFrame:
    last_dates = {s: d.dropna().index[-1] for s, d in frames.items() if len(d.dropna())}
    asof = max(last_dates.values())
    tol = pd.Timedelta(days=8)
    rows, rets = [], {}
    for sym, df in frames.items():
        d = drop_incomplete_last(df, "daily", asof=asof)
        if len(d) < min_bars or last_dates[sym] < asof - tol:
            continue
        c = d["Close"].astype(float)
        if c.iloc[-1] < 0.5:                       # exclude sub-$0.50 noise
            continue
        atr = c.diff().abs().rolling(14).mean().iloc[-1]   # close-to-close ATR proxy
        if not np.isfinite(atr) or atr <= 0:
            continue
        rec = {"symbol": sym,
               "dvol": float((c * d["Volume"].astype(float)).iloc[-21:].median())}
        for k in HORIZONS:
            rec[f"ret_{k}d"] = float(c.iloc[-1] / c.iloc[-1 - k] - 1.0)
            rec[f"atrmove_{k}d"] = float((c.iloc[-1] - c.iloc[-1 - k]) / atr)
        rows.append(rec)
        rets[sym] = c.pct_change().iloc[-63:].to_numpy()   # for correlation
    feat = pd.DataFrame(rows).set_index("symbol")
    R = pd.DataFrame({s: pd.Series(v) for s, v in rets.items()
                      if len(v) == 63 and np.isfinite(v).all()})
    return feat, R, asof


def zscore(df: pd.DataFrame, cols, clip=4.0) -> pd.DataFrame:
    """Robust cross-sectional z (median/MAD): heavy-tailed ATR-moves would
    otherwise inflate the std and compress everyone else's z toward 0."""
    for c in cols:
        med = df[c].median()
        mad = (df[c] - med).abs().median() * 1.4826 or 1.0
        df["z_" + c] = ((df[c] - med) / mad).clip(-clip, clip)
    return df


# --------------------------------------------------------------------------- #
def run(args):
    # 1) universe + cached daily prices
    syms, seen = [], set()
    for u in args.universes:
        for s in get_universe(source=u)["symbol"]:
            if s not in seen:
                seen.add(s); syms.append(s)
    cache = pd.read_pickle(os.path.join(CACHE_DIR, "ohlcvdict_1d_20y.pkl"))
    frames = {s: cache[s] for s in syms if s in cache}
    feat, R, asof = build_features(frames)
    print(f"[rotation] {len(feat)} names with fresh daily data (as-of {asof.date()})")

    # 2) normalized features
    cols = [f"ret_{k}d" for k in HORIZONS] + [f"atrmove_{k}d" for k in HORIZONS]
    feat = zscore(feat, cols)
    zc = ["z_" + c for c in cols]
    feat["blend"] = (0.5 * feat["z_atrmove_5d"] + 0.3 * feat["z_atrmove_10d"]
                     + 0.2 * feat["z_atrmove_21d"])
    feat["accel"] = feat["z_atrmove_5d"] - feat["z_atrmove_21d"]

    # 3) industry labels: yfinance cache + fd fallback
    ind_cache = json.load(open(IND_CACHE)) if os.path.exists(IND_CACHE) else {}
    fdl = fd_labels()
    if args.yf_labels:
        # fetch genuine yfinance labels for the most signal-bearing names
        hot = feat.reindex(feat["blend"].abs().sort_values(ascending=False).index)
        ind_cache = yf_label_fill(hot.index[:args.yf_labels], ind_cache,
                                  max_fetch=args.yf_labels)
        json.dump(ind_cache, open(IND_CACHE, "w"))
    def label(s):
        y = ind_cache.get(s) or {}
        f = fdl.get(s, (None, None))
        return (y.get("sector") or f[0] or "Unknown",
                y.get("industry") or f[1] or "Unknown")
    feat["sector"], feat["industry"] = zip(*[label(s) for s in feat.index])

    # 4) k-means on the 6 z-features
    from sklearn.cluster import KMeans
    X = feat[zc].to_numpy()
    km = KMeans(n_clusters=args.k, n_init=10, random_state=0).fit(X)
    feat["cluster"] = km.labels_

    # 5) correlation tightening
    C = R.corr() if len(R.columns) else pd.DataFrame()

    _report(feat, C, args, asof)
    out = os.path.join(RESULTS, f"rotation_{dt.date.today().isoformat()}.csv")
    feat.reset_index().to_csv(out, index=False)
    print(f"\n[out] per-ticker table -> {out}")


# --------------------------------------------------------------------------- #
def _report(feat, C, args, asof):
    w = np.sqrt(feat["dvol"].clip(lower=1.0))      # money-flow weighting

    def wavg(g, col):
        ww = np.sqrt(g["dvol"].clip(lower=1.0))
        return float((g[col] * ww).sum() / ww.sum())

    # ---- industry flow ---------------------------------------------------- #
    rows = []
    for ind, g in feat.groupby("industry"):
        if len(g) < args.min_industry or ind == "Unknown":
            continue
        rows.append({"industry": ind[:34], "sector": g["sector"].mode().iat[0][:18],
                     "n": len(g),
                     "z5": wavg(g, "z_atrmove_5d"), "z10": wavg(g, "z_atrmove_10d"),
                     "z21": wavg(g, "z_atrmove_21d"), "blend": wavg(g, "blend"),
                     "accel": wavg(g, "accel")})
    ind = pd.DataFrame(rows).sort_values("blend", ascending=False)

    def block(title, t):
        print(f"\n=== {title} ===")
        print(f"{'Industry':<35}{'Sector':<19}{'n':>4}{'z5':>7}{'z10':>7}{'z21':>7}{'blend':>7}{'accel':>7}")
        for _, r in t.iterrows():
            print(f"{r['industry']:<35}{r['sector']:<19}{r['n']:>4}"
                  f"{r['z5']:>7.2f}{r['z10']:>7.2f}{r['z21']:>7.2f}"
                  f"{r['blend']:>7.2f}{r['accel']:>7.2f}")

    print(f"\n{'#'*100}\n#  ROTATION SCREEN  as-of {asof.date()}  |  {len(feat)} names  |  "
          f"$vol-weighted, ATR-normalised (close-to-close proxy)\n{'#'*100}")
    block(f"MONEY FLOWING IN — top {args.top} industries by blended ATR-thrust", ind.head(args.top))
    block(f"MONEY FLOWING OUT — bottom {args.top}", ind.tail(args.top).iloc[::-1])
    block(f"ROTATION ARRIVING NOW — top accel (5d z − 21d z)",
          ind.sort_values("accel", ascending=False).head(args.top))

    # ---- clusters ---------------------------------------------------------- #
    print(f"\n=== K-MEANS CLUSTERS (k={args.k}) on normalised 6-feature action ===")
    print(f"{'Cl':>3}{'n':>5}{'z5':>7}{'z10':>7}{'z21':>7}{'corr':>6}  top industries | leaders")
    summary = []
    for cl, g in feat.groupby("cluster"):
        ic = np.nan
        cs = [s for s in g.index if s in C.columns]
        if len(cs) >= 3:
            sub = C.loc[cs, cs].to_numpy()
            ic = float(np.nanmean(sub[np.triu_indices(len(cs), 1)]))
        summary.append((cl, g, ic))
    summary.sort(key=lambda x: -wavg(x[1], "blend"))
    for cl, g, ic in summary:
        tops = g["industry"].value_counts().head(3).index.tolist()
        lead = g.sort_values("blend", ascending=False).index[:6].tolist()
        print(f"{cl:>3}{len(g):>5}{wavg(g,'z_atrmove_5d'):>7.2f}{wavg(g,'z_atrmove_10d'):>7.2f}"
              f"{wavg(g,'z_atrmove_21d'):>7.2f}{(f'{ic:.2f}' if ic==ic else '  -'):>6}  "
              f"{', '.join(t[:22] for t in tops)} | {', '.join(lead)}")

    # ---- most correlated pairs inside the two leading clusters ------------- #
    if len(C.columns):
        print("\n=== MOST-CORRELATED PAIRS inside the 2 leading clusters (63d returns) ===")
        for cl, g, ic in summary[:2]:
            cs = [s for s in g.index if s in C.columns]
            if len(cs) < 4:
                continue
            arr = C.loc[cs, cs].to_numpy().copy()
            np.fill_diagonal(arr, np.nan)
            sub = pd.DataFrame(arr, index=cs, columns=cs)
            pairs = sub.stack().sort_values(ascending=False)
            seenp, shown = set(), []
            for (a, b), v in pairs.items():
                if (b, a) in seenp:
                    continue
                seenp.add((a, b)); shown.append(f"{a}~{b} {v:.2f}")
                if len(shown) >= args.pairs:
                    break
            print(f"  cluster {cl}: " + "  ".join(shown))


def parse_args():
    p = argparse.ArgumentParser(description="Multi-horizon rotation screener (price + ATR-thrust, k-means, correlation, industry flow)")
    p.add_argument("--universes", nargs="+",
                   default=["us-midcap", "us-smallcap", "us-microcap", "uk-allcap"])
    p.add_argument("--k", type=int, default=8)
    p.add_argument("--top", type=int, default=15)
    p.add_argument("--pairs", type=int, default=8)
    p.add_argument("--min-industry", type=int, default=4, help="min names per industry row")
    p.add_argument("--yf-labels", type=int, default=0,
                   help="fetch genuine yfinance industry labels for the N most signal-bearing names (cached)")
    return p.parse_args()


if __name__ == "__main__":
    run(parse_args())
