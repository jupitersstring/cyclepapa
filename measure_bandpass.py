#!/usr/bin/env python3
"""
Multi-measure Ehlers bandpass inflection scanner.

Instead of bandpassing only price and volume, this builds a time series for
EACH measure we discussed and runs the Ehlers 4-band bandpass on every one,
detecting the latest zero-line inflection per measure/band, then CROSSES them:
a name where many measures inflect the same way at once is a broad regime turn.

Measure series (all derived from Close + Volume at the chosen timeframe):
  PRICE     close
  RET       weekly/period returns
  VOL       log volume
  LIQ       log dollar volume                (liquidity)
  ACCUM     accumulation line = cumsum(sign(ret)*log1p(vol))   (net accumulation/OBV)
  PARTIC    return x volume-z                 (return x volume participation)
  RVOL      rolling realized volatility       (compression/expansion shows as inflection)
  RSHARPE   rolling mean/std of returns       (rolling Sharpe)
  UPDNV     rolling up-volume / down-volume ratio
  GPR       rolling gain-to-pain ratio

For each name we report breadth: how many measures freshly inflected UP vs DOWN
(Band B1), netting to a regime-turn score. Ranked up (bullish broad turn) and
down (bearish broad turn).

Usage:
    python3 measure_bandpass.py --universe us-midcap --weekly --cached-only
    python3 measure_bandpass.py --universe us-midcap --daily --band B1 --top 25
"""
from __future__ import annotations

import argparse

import numpy as np
import pandas as pd

from volume_bandpass import download_ohlcv
from signals import ehlers_bandpass, BANDS, latest_crossing, drop_incomplete_last  # noqa: F401
from midcap_weekly_anomalies import get_universe, CAP_SOURCES  # noqa: F401

MEASURES = ["PRICE", "RET", "VOL", "LIQ", "ACCUM", "PARTIC",
            "RVOL", "RSHARPE", "UPDNV", "GPR"]

# DIRECTIONAL dimensions count toward bullish/bearish breadth (an up-cross is
# genuinely bullish). Each correlated cluster is collapsed so one driver adds at
# most +1. ACCUM/PARTIC (signed volume) carry the participation signal.
DIMENSIONS = {
    "PRICE":  ["PRICE", "RET"],        # trend / direction
    "PARTIC": ["ACCUM", "PARTIC"],     # signed participation (accumulation/distribution)
    "SHARPE": ["RSHARPE"],             # risk-adjusted trend
    "ASYM":   ["UPDNV", "GPR"],        # payoff asymmetry
}
DIM_ORDER = list(DIMENSIONS)
# NON-directional context dims: an up-cross is ambiguous (volume rises on
# distribution too; RVOL up = vol expansion either way). Shown but NOT summed.
CONTEXT_DIMS = {
    "VOLUME": ["VOL", "LIQ"],          # raw turnover (direction-agnostic)
    "VOLAT":  ["RVOL"],                # volatility regime (expansion/compression)
}
CONTEXT_ORDER = list(CONTEXT_DIMS)


# --------------------------------------------------------------------------- #
# Build all measure series for one asset
# --------------------------------------------------------------------------- #
def measure_series(close: pd.Series, volume: pd.Series, w: int) -> dict[str, np.ndarray]:
    ret = close.pct_change(fill_method=None)
    logv = np.log1p(volume)
    vz = (volume - volume.rolling(w, min_periods=w // 2).mean()) / \
         volume.rolling(w, min_periods=w // 2).std()
    vz = vz.replace([np.inf, -np.inf], np.nan)
    sign = np.sign(ret).fillna(0)

    out: dict[str, pd.Series] = {}
    out["PRICE"] = np.log(close.clip(lower=1e-9))   # log price: amplitude scale-invariant
    out["RET"] = ret
    out["VOL"] = logv
    out["LIQ"] = np.log1p(close * volume)
    out["ACCUM"] = (sign * logv).cumsum()
    out["PARTIC"] = ret * vz
    out["RVOL"] = ret.rolling(w, min_periods=w // 2).std()
    out["RSHARPE"] = ret.rolling(w, min_periods=w // 2).mean() / \
        ret.rolling(w, min_periods=w // 2).std()
    up_v = volume.where(ret > 0, 0.0).rolling(w, min_periods=w // 2).sum()
    dn_v = volume.where(ret < 0, 0.0).rolling(w, min_periods=w // 2).sum()
    out["UPDNV"] = np.log((up_v + 1) / (dn_v + 1))
    pos = ret.clip(lower=0).rolling(w, min_periods=w // 2).sum()
    neg = (-ret.clip(upper=0)).rolling(w, min_periods=w // 2).sum()
    out["GPR"] = np.log((pos + 1e-6) / (neg + 1e-6))

    return {k: v.replace([np.inf, -np.inf], np.nan).to_numpy() for k, v in out.items()}


def inflections(values: np.ndarray, recent: int, bands) -> dict[str, dict]:
    """Thin wrapper over the shared hysteresis-aware crossing detector."""
    return latest_crossing(values, recent, bands)


# --------------------------------------------------------------------------- #
# Scan one timeframe across the universe
# --------------------------------------------------------------------------- #
def scan(frames: dict, label: str, recent: int, w: int, sectors: dict,
         caps: dict, band: str, top: int, min_net: int = 1) -> pd.DataFrame:
    bands = [b for b in BANDS if (band is None or b[0] == band)]
    last_dates = {s: df.dropna().index[-1] for s, df in frames.items() if len(df.dropna())}
    if not last_dates:
        print(f"\n[{label}] no data.")
        return pd.DataFrame()
    asof = max(last_dates.values())
    tol = pd.Timedelta(days=3 if label.endswith("m") else (8 if label == "daily" else 12))

    def vote(rec, group, members, meas_dir, directional):
        votes = [meas_dir[m][0] for m in members if m in meas_dir]
        slopes = [meas_dir[m][1] for m in members if m in meas_dir]
        s = sum(votes)
        if not votes or s == 0:
            rec[group] = "±" if votes else ""
            return
        d_dir = 1 if s > 0 else -1
        rec[group] = "▲" if d_dir > 0 else "▼"
        if not directional:                 # context dims are shown, not summed
            return
        inten = sum(slopes) / len(slopes)
        if d_dir > 0:
            rec["up"] += 1; rec["score"] += inten
        else:
            rec["down"] += 1; rec["score"] -= inten

    rows = []
    for sym, df in frames.items():
        d = drop_incomplete_last(df, label, asof=asof)   # drop in-progress bar
        if len(d) < 80 or last_dates.get(sym) < (asof - tol):
            continue
        series = measure_series(d["Close"].astype(float), d["Volume"].astype(float), w)
        rec = {"symbol": sym, "sector": sectors.get(sym, "?"),
               "cap": caps.get(sym, "?"), "tf": label,
               "up": 0, "down": 0, "net": 0, "score": 0.0}
        meas_dir = {}
        for meas, vals in series.items():
            b1 = inflections(vals, recent, bands).get(band or "B1")
            if b1 and b1["fresh"] and b1.get("settled", True):  # respect settled guard
                meas_dir[meas] = (1 if b1["dir"] == "UP" else -1, abs(b1["slope_z"]))
        for dim, members in DIMENSIONS.items():       # directional -> count toward net
            vote(rec, dim, members, meas_dir, directional=True)
        for dim, members in CONTEXT_DIMS.items():     # context -> shown only
            vote(rec, dim, members, meas_dir, directional=False)
        rec["net"] = rec["up"] - rec["down"]
        if rec["up"] or rec["down"]:
            rows.append(rec)

    out = pd.DataFrame(rows)
    if out.empty:
        print(f"\n[{label}] no fresh measure inflections.")
        return out
    _report(out, label, recent, top, band or "B1", min_net)
    return out


def _report(df: pd.DataFrame, label: str, recent: int, top: int, band: str,
            min_net: int = 1) -> None:
    print(f"\n{'#'*116}\n#  {label.upper()} — DIRECTIONAL breadth (Band {band}, fresh within "
          f"{recent} bars).  Net = up-dims − down-dims (max ±{len(DIMENSIONS)})\n"
          f"#  Directional: PRICE PARTIC SHARPE ASYM.  Context (not summed): VOLUME VOLAT "
          f"(▲ here is ambiguous)\n{'#'*116}")
    cols = DIM_ORDER + CONTEXT_ORDER
    hdr = f"{'Sym':<7}{'Sector':<18}{'Net':>4}{'Up':>3}{'Dn':>3}  " + "".join(f"{c:>8}" for c in cols)
    for sign, title in [(1, f"BULLISH: ALL names with Net >= +{min_net} (dimensions inflecting UP)"),
                        (-1, f"BEARISH: ALL names with Net <= -{min_net} (dimensions inflecting DOWN)")]:
        sub = df[df["net"] * sign >= min_net].copy()
        if sub.empty:
            continue
        sub = sub.sort_values(["net", "score"], ascending=(sign < 0))
        print(f"\n=== {title}   ({len(sub)} names) ===")
        print(hdr)
        for _, r in sub.iterrows():
            print(f"{r['symbol']:<7}{str(r['sector'])[:17]:<18}{int(r['net']):>4}"
                  f"{int(r['up']):>3}{int(r['down']):>3}  "
                  + "".join(f"{str(r.get(c,'')):>8}" for c in cols))


def run(args):
    uni = get_universe(limit=args.limit, source=args.universe)
    symbols = uni["symbol"].tolist()
    sectors = dict(zip(uni["symbol"], uni["sector"]))
    caps = dict(zip(uni["symbol"], uni.get("market_cap", pd.Series(index=uni.index, dtype=str))))

    results = []
    if args.m90:
        h = download_ohlcv(symbols, period="60d", interval="90m",
                           refresh=args.refresh, cached_only=args.cached_only)
        r = scan(h, "90m", args.recent_m90, args.window_m90, sectors, caps, args.band, args.top, args.min_net)
        if not r.empty: results.append(r)
    if args.daily:
        d = download_ohlcv(symbols, period=args.period, interval="1d",
                           refresh=args.refresh, cached_only=args.cached_only)
        r = scan(d, "daily", args.recent_daily, args.window, sectors, caps, args.band, args.top, args.min_net)
        if not r.empty: results.append(r)
    if args.weekly:
        ww = download_ohlcv(symbols, period=args.period, interval="1wk",
                            refresh=args.refresh, cached_only=args.cached_only)
        r = scan(ww, "weekly", args.recent_weekly, args.window, sectors, caps, args.band, args.top, args.min_net)
        if not r.empty: results.append(r)

    if results and args.csv:
        pd.concat(results, ignore_index=True).to_csv(args.csv, index=False)
        print(f"\n[out] -> {args.csv}")


def parse_args():
    p = argparse.ArgumentParser(description="Multi-measure Ehlers bandpass inflection scanner")
    p.add_argument("--universe", choices=["sp400", *CAP_SOURCES.keys()], default="us-midcap")
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--min-net", type=int, default=1, help="show ALL names with |Net dimensions| >= this (default 1)")
    p.add_argument("--period", default="20y")
    p.add_argument("--weekly", action="store_true")
    p.add_argument("--daily", action="store_true")
    p.add_argument("--m90", action="store_true")
    p.add_argument("--band", default="B1", help="band to cross on (B1/B2/B3/B4); default B1")
    p.add_argument("--window", type=int, default=13, help="rolling window for derived measures (daily/weekly)")
    p.add_argument("--window-m90", type=int, default=20)
    p.add_argument("--recent-daily", type=int, default=5)
    p.add_argument("--recent-weekly", type=int, default=2)
    p.add_argument("--recent-m90", type=int, default=6)
    p.add_argument("--top", type=int, default=25)
    p.add_argument("--cached-only", action="store_true")
    p.add_argument("--refresh", action="store_true")
    p.add_argument("--csv", default=None)
    a = p.parse_args()
    if not (a.weekly or a.daily or a.m90):
        a.weekly = True
    return a


if __name__ == "__main__":
    run(parse_args())
