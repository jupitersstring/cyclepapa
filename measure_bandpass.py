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

from volume_bandpass import ehlers_bandpass, BANDS, download_ohlcv
from midcap_weekly_anomalies import get_universe, CAP_SOURCES  # noqa: F401

MEASURES = ["PRICE", "RET", "VOL", "LIQ", "ACCUM", "PARTIC",
            "RVOL", "RSHARPE", "UPDNV", "GPR"]


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
    out["PRICE"] = close
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


# --------------------------------------------------------------------------- #
# Latest zero-line inflection of one (cleaned) series for the given bands
# --------------------------------------------------------------------------- #
def inflections(values: np.ndarray, recent: int, bands) -> dict[str, dict]:
    v = values[~np.isnan(values)]
    n = len(v)
    res: dict[str, dict] = {}
    for name, flen, slen in bands:
        if n < slen:
            continue
        pb = ehlers_bandpass(v, flen, slen)
        sd = np.std(pb[slen:]) if pb[slen:].size > 5 else np.std(pb)
        if not np.isfinite(sd) or sd == 0:
            continue
        sgn = np.sign(pb)
        ci = None
        for t in range(n - 1, max(slen, 1), -1):
            if sgn[t] != sgn[t - 1] and sgn[t] != 0:
                ci = t
                break
        if ci is None:
            continue
        bars_ago = (n - 1) - ci
        res[name] = {
            "dir": "UP" if pb[ci] > 0 else "DOWN",
            "bars_ago": bars_ago,
            "slope_z": float((pb[-1] - pb[-2]) / sd) if n >= 2 else 0.0,
            "fresh": bars_ago <= recent,
        }
    return res


# --------------------------------------------------------------------------- #
# Scan one timeframe across the universe
# --------------------------------------------------------------------------- #
def scan(frames: dict, label: str, recent: int, w: int, sectors: dict,
         caps: dict, band: str, top: int) -> pd.DataFrame:
    bands = [b for b in BANDS if (band is None or b[0] == band)]
    intraday = label.endswith("m")
    last_dates = {s: df.dropna().index[-1] for s, df in frames.items() if len(df.dropna())}
    if not last_dates:
        print(f"\n[{label}] no data.")
        return pd.DataFrame()
    asof = max(last_dates.values())
    tol = pd.Timedelta(days=3 if intraday else (8 if label == "daily" else 12))

    rows = []
    for sym, df in frames.items():
        d = df.dropna()
        if intraday and len(d) > 1:
            d = d.iloc[:-1]
        if len(d) < 80 or last_dates.get(sym) < (asof - tol):
            continue
        series = measure_series(d["Close"].astype(float), d["Volume"].astype(float), w)
        rec = {"symbol": sym, "sector": sectors.get(sym, "?"),
               "cap": caps.get(sym, "?"), "tf": label,
               "up": 0, "down": 0, "net": 0, "score": 0.0}
        for meas, vals in series.items():
            infl = inflections(vals, recent, bands)
            b1 = infl.get(band or "B1")
            rec[meas] = ""
            if b1 and b1["fresh"]:
                arrow = "▲" if b1["dir"] == "UP" else "▼"
                rec[meas] = arrow
                if b1["dir"] == "UP":
                    rec["up"] += 1
                    rec["score"] += abs(b1["slope_z"])
                else:
                    rec["down"] += 1
                    rec["score"] -= abs(b1["slope_z"])
        rec["net"] = rec["up"] - rec["down"]
        if rec["up"] or rec["down"]:
            rows.append(rec)

    out = pd.DataFrame(rows)
    if out.empty:
        print(f"\n[{label}] no fresh measure inflections.")
        return out
    _report(out, label, recent, top, band or "B1")
    return out


def _report(df: pd.DataFrame, label: str, recent: int, top: int, band: str) -> None:
    print(f"\n{'#'*120}\n#  {label.upper()} — MULTI-MEASURE bandpass inflections "
          f"(Band {band}, fresh within {recent} bars).  ▲=up-cross ▼=down-cross\n{'#'*120}")
    cols = MEASURES
    hdr = f"{'Sym':<7}{'Sector':<20}{'Net':>4}{'Up':>3}{'Dn':>3}  " + "".join(f"{c[:5]:>6}" for c in cols)
    for sign, title in [(1, "BULLISH broad turns (most measures inflecting UP)"),
                        (-1, "BEARISH broad turns (most measures inflecting DOWN)")]:
        sub = df[df["net"] * sign > 0].copy()
        if sub.empty:
            continue
        sub = sub.sort_values("net" if sign > 0 else "net",
                              ascending=(sign < 0))
        sub = sub.sort_values("score", ascending=(sign < 0)).head(top)
        print(f"\n=== {title} ===")
        print(hdr)
        for _, r in sub.iterrows():
            print(f"{r['symbol']:<7}{str(r['sector'])[:19]:<20}{int(r['net']):>4}"
                  f"{int(r['up']):>3}{int(r['down']):>3}  "
                  + "".join(f"{str(r.get(c,'')):>6}" for c in cols))


def run(args):
    uni = get_universe(limit=args.limit, source=args.universe)
    symbols = uni["symbol"].tolist()
    sectors = dict(zip(uni["symbol"], uni["sector"]))
    caps = dict(zip(uni["symbol"], uni.get("market_cap", pd.Series(index=uni.index, dtype=str))))

    results = []
    if args.m90:
        h = download_ohlcv(symbols, period="60d", interval="90m",
                           refresh=args.refresh, cached_only=args.cached_only)
        r = scan(h, "90m", args.recent_m90, args.window_m90, sectors, caps, args.band, args.top)
        if not r.empty: results.append(r)
    if args.daily:
        d = download_ohlcv(symbols, period=args.period, interval="1d",
                           refresh=args.refresh, cached_only=args.cached_only)
        r = scan(d, "daily", args.recent_daily, args.window, sectors, caps, args.band, args.top)
        if not r.empty: results.append(r)
    if args.weekly:
        ww = download_ohlcv(symbols, period=args.period, interval="1wk",
                            refresh=args.refresh, cached_only=args.cached_only)
        r = scan(ww, "weekly", args.recent_weekly, args.window, sectors, caps, args.band, args.top)
        if not r.empty: results.append(r)

    if results and args.csv:
        pd.concat(results, ignore_index=True).to_csv(args.csv, index=False)
        print(f"\n[out] -> {args.csv}")


def parse_args():
    p = argparse.ArgumentParser(description="Multi-measure Ehlers bandpass inflection scanner")
    p.add_argument("--universe", choices=["sp400", *CAP_SOURCES.keys()], default="us-midcap")
    p.add_argument("--limit", type=int, default=None)
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
