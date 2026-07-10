#!/usr/bin/env python3
"""
EARLY inflection screener — catch the turn at the trough, before the cross.

For each name (cached daily bars) it SuperSmooths the log price at two scales
(fast ~ a fortnight, slow ~ a month) and finds the most-recent inflection of the
*level* (smoothed velocity crossing zero = a trough/peak). That fires at the
turning point itself, ahead of a bandpass zero-cross.

Signal quality:
  * fresh on BOTH scales, same direction  -> confirmed early turn
  * curvature (acceleration) ranks how sharp the turn is
  * a name is "early-UP" when slow velocity just turned up (trough) AND fast
    curvature > 0 (accelerating) -- i.e. bottoming with upward thrust

Aggregated to yfinance/financedatabase industries to show where rotation is
*beginning* (earliest read) vs the realised-flow rotation_screener.

Usage:
  python3 early_inflection.py                          # default cuts
  python3 early_inflection.py --fast 10 --slow 21 --recent 5 --top 30
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os

import numpy as np
import pandas as pd

from midcap_weekly_anomalies import get_universe, CACHE_DIR
from signals import drop_incomplete_last, smoothed_inflection
from rotation_screener import fd_labels, IND_CACHE

RESULTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results")


def run(args):
    syms, seen = [], set()
    for u in args.universes:
        for s in get_universe(source=u)["symbol"]:
            if s not in seen:
                seen.add(s); syms.append(s)
    cache = pd.read_pickle(os.path.join(CACHE_DIR, "ohlcvdict_1d_20y.pkl"))
    frames = {s: cache[s] for s in syms if s in cache}
    last = {s: d.dropna().index[-1] for s, d in frames.items() if len(d.dropna())}
    asof = max(last.values()); tol = pd.Timedelta(days=8)

    rows = []
    for sym, df in frames.items():
        d = drop_incomplete_last(df, "daily", asof=asof)
        c = d["Close"].astype(float)
        if len(c) < 3 * args.slow or last[sym] < asof - tol or c.iloc[-1] < 0.5:
            continue
        lp = np.log(c.clip(lower=1e-9).to_numpy())
        fast = smoothed_inflection(lp, args.fast, args.recent)
        slow = smoothed_inflection(lp, args.slow, args.recent)
        if not slow:
            continue
        dvol = float((c * d["Volume"].astype(float)).iloc[-21:].median())
        rows.append({
            "symbol": sym, "dvol": dvol,
            "slow_dir": slow["dir"], "slow_bars": slow["bars_ago"],
            "slow_vel": slow["vel_z"], "slow_curv": slow["curv_z"],
            "fast_dir": fast["dir"] if fast else "", "fast_bars": fast["bars_ago"] if fast else np.nan,
            "fast_curv": fast["curv_z"] if fast else np.nan,
            "fast_fresh": bool(fast and fast["fresh"]),
            "slow_fresh": slow["fresh"],
        })
    feat = pd.DataFrame(rows).set_index("symbol")
    # early-turn classification
    feat["early_up"] = (feat["slow_dir"] == "UP") & feat["slow_fresh"] & (feat["fast_curv"] > 0)
    feat["early_down"] = (feat["slow_dir"] == "DOWN") & feat["slow_fresh"] & (feat["fast_curv"] < 0)
    feat["confirmed"] = ((feat["slow_dir"] == feat["fast_dir"]) & feat["slow_fresh"]
                         & feat["fast_fresh"])
    # earliness/strength: fresher + sharper curvature ranks higher
    feat["turn_score"] = (feat["slow_curv"].abs() * (1.0 / (1 + feat["slow_bars"]))
                          * np.sign(feat["slow_curv"]))

    # industry labels (cached yf + fd fallback)
    ind = json.load(open(IND_CACHE)) if os.path.exists(IND_CACHE) else {}
    fdl = fd_labels()
    def lab(s):
        y = ind.get(s) or {}; f = fdl.get(s, (None, None))
        return (y.get("sector") or f[0] or "Unknown", y.get("industry") or f[1] or "Unknown")
    feat["sector"], feat["industry"] = zip(*[lab(s) for s in feat.index])

    _report(feat, args, asof)
    out = os.path.join(RESULTS, f"early_inflection_{dt.date.today().isoformat()}.csv")
    feat.reset_index().to_csv(out, index=False)
    print(f"\n[out] -> {out}")


def _report(feat, args, asof):
    print(f"\n{'#'*104}\n#  EARLY INFLECTION SCREEN  as-of {asof.date()}  |  {len(feat)} names  |  "
          f"SuperSmoother fast={args.fast} slow={args.slow}, fresh<= {args.recent}d\n{'#'*104}")

    def tbl(title, sub, asc):
        sub = sub.sort_values("turn_score", ascending=asc).head(args.top)
        print(f"\n=== {title}  ({len(sub)} shown) ===")
        print(f"{'Sym':<8}{'Industry':<30}{'slowBars':>9}{'slowVel':>8}{'slowCurv':>9}"
              f"{'fastCurv':>9}{'conf':>6}")
        for s, r in sub.iterrows():
            print(f"{s:<8}{str(r['industry'])[:29]:<30}{int(r['slow_bars']):>9}"
                  f"{r['slow_vel']:>8.2f}{r['slow_curv']:>9.3f}{r['fast_curv']:>9.3f}"
                  f"{('yes' if r['confirmed'] else ''):>6}")

    up = feat[feat["early_up"]]
    dn = feat[feat["early_down"]]
    tbl("EARLY-UP — smoothed level just troughed & accelerating (be early LONG)", up, asc=False)
    tbl("EARLY-DOWN — smoothed level just peaked & rolling over (be early SHORT)", dn, asc=True)

    # industry-level earliness: net fresh up vs down inflections, $vol-weighted
    rows = []
    for indn, g in feat.groupby("industry"):
        if len(g) < args.min_industry or indn == "Unknown":
            continue
        w = np.sqrt(g["dvol"].clip(lower=1.0))
        up_share = (g["early_up"].astype(float) * w).sum() / w.sum()
        dn_share = (g["early_down"].astype(float) * w).sum() / w.sum()
        rows.append({"industry": indn[:34], "sector": g["sector"].mode().iat[0][:18],
                     "n": len(g), "up%": up_share, "down%": dn_share,
                     "net": up_share - dn_share})
    idf = pd.DataFrame(rows)
    if not idf.empty:
        print(f"\n=== INDUSTRIES INFLECTING UP EARLIEST (net fresh up-turns, $vol-wtd) ===")
        print(f"{'Industry':<35}{'Sector':<19}{'n':>4}{'up%':>7}{'down%':>7}{'net':>7}")
        for _, r in idf.sort_values("net", ascending=False).head(args.top).iterrows():
            print(f"{r['industry']:<35}{r['sector']:<19}{r['n']:>4}"
                  f"{r['up%']*100:>6.0f}%{r['down%']*100:>6.0f}%{r['net']*100:>6.0f}%")
        print(f"\n=== INDUSTRIES INFLECTING DOWN EARLIEST ===")
        for _, r in idf.sort_values("net").head(args.top).iterrows():
            print(f"{r['industry']:<35}{r['sector']:<19}{r['n']:>4}"
                  f"{r['up%']*100:>6.0f}%{r['down%']*100:>6.0f}%{r['net']*100:>6.0f}%")


def parse_args():
    p = argparse.ArgumentParser(description="Early (smoothed-inflection) rotation screener")
    p.add_argument("--universes", nargs="+",
                   default=["us-midcap", "us-smallcap", "us-microcap", "uk-allcap"])
    p.add_argument("--fast", type=int, default=10)
    p.add_argument("--slow", type=int, default=21)
    p.add_argument("--recent", type=int, default=5, help="bars since inflection to call it 'fresh'")
    p.add_argument("--top", type=int, default=25)
    p.add_argument("--min-industry", type=int, default=4)
    return p.parse_args()


if __name__ == "__main__":
    run(parse_args())
