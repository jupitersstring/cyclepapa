#!/usr/bin/env python3
"""
Price x Volume bandpass-inflection CROSS scanner.

For each name, timeframe and cap bucket, runs the Ehlers 4-band bandpass on
BOTH price (Close) and volume (log volume), finds the most recent zero-line
inflection of each, and CROSSES them: names where price *and* volume both
inflect (freshly) are classified into quadrants —

    Price UP   + Volume UP   -> ACCUMULATION   (confirmed strength; bullish)
    Price DOWN + Volume UP   -> CAPITULATION   (heavy selling / distribution)
    Price UP   + Volume DOWN -> WEAK RALLY      (unconfirmed; low conviction)
    Price DOWN + Volume DOWN -> QUIET DECLINE   (selling drying up)

Usage:
    python3 pv_cross.py --universe us-midcap                 # daily + weekly
    python3 pv_cross.py --universe us-smallcap --weekly-only
    python3 pv_cross.py --universe us-microcap --band B1 --top 25
"""
from __future__ import annotations

import argparse

import numpy as np
import pandas as pd

from volume_bandpass import (ehlers_bandpass, BANDS, download_ohlcv)
from midcap_weekly_anomalies import get_universe, CAP_SOURCES  # noqa: F401

QUAD = {
    ("UP", "UP"): "ACCUMULATION",
    ("DOWN", "UP"): "CAPITULATION",
    ("UP", "DOWN"): "WEAK RALLY",
    ("DOWN", "DOWN"): "QUIET DECLINE",
}


# --------------------------------------------------------------------------- #
# Generic per-series band crossing analysis
# --------------------------------------------------------------------------- #
def band_crossings(values: np.ndarray) -> dict[str, dict]:
    """Most-recent zero-line crossing per band for a (transformed) series."""
    n = len(values)
    out: dict[str, dict] = {}
    for name, flen, slen in BANDS:
        if n < slen:
            continue
        pb = ehlers_bandpass(values, flen, slen)
        settled = pb[slen:]
        sd = np.std(settled) if settled.size > 5 else np.std(pb)
        if not np.isfinite(sd) or sd == 0:
            continue
        sign = np.sign(pb)
        ci = None
        for t in range(n - 1, max(slen, 1), -1):
            if sign[t] != sign[t - 1] and sign[t] != 0:
                ci = t
                break
        if ci is None:
            continue
        out[name] = {
            "dir": "UP" if pb[ci] > 0 else "DOWN",
            "bars_ago": (n - 1) - ci,
            "slope_z": float((pb[-1] - pb[-2]) / sd) if n >= 2 else 0.0,
            "pb_z": float(pb[-1] / sd),
            "settled": n >= int(1.5 * slen),
        }
    return out


# --------------------------------------------------------------------------- #
# Cross price vs volume for one timeframe
# --------------------------------------------------------------------------- #
def cross_timeframe(frames: dict, label: str, recent: int, sectors: dict,
                    caps: dict, top: int, band_filter: str | None) -> pd.DataFrame:
    # determine as-of date for staleness guard
    last_dates = {s: df.dropna().index[-1] for s, df in frames.items() if len(df.dropna())}
    if not last_dates:
        print(f"\n[{label}] no data.")
        return pd.DataFrame()
    asof = max(last_dates.values())
    tol = pd.Timedelta(days=8 if label == "daily" else 12)

    rows = []
    for sym, df in frames.items():
        d = df.dropna()
        if len(d) < 60 or last_dates.get(sym) < (asof - tol):
            continue  # stale / delisted
        close = d["Close"].astype(float).to_numpy()
        logv = np.log1p(d["Volume"].astype(float).to_numpy())
        pc = band_crossings(close)
        vc = band_crossings(logv)
        for band in pc.keys() & vc.keys():
            p, v = pc[band], vc[band]
            if p["bars_ago"] > recent or v["bars_ago"] > recent:
                continue
            rows.append({
                "symbol": sym, "sector": sectors.get(sym, "?"),
                "cap": caps.get(sym, "?"), "tf": label, "band": band,
                "price_dir": p["dir"], "vol_dir": v["dir"],
                "quadrant": QUAD[(p["dir"], v["dir"])],
                "price_slope_z": p["slope_z"], "vol_slope_z": v["slope_z"],
                "price_pb_z": p["pb_z"], "vol_pb_z": v["pb_z"],
                "price_bars": p["bars_ago"], "vol_bars": v["bars_ago"],
                "settled": p["settled"] and v["settled"],
                "mag": abs(p["slope_z"]) + abs(v["slope_z"]),
            })
    out = pd.DataFrame(rows)
    if out.empty:
        print(f"\n[{label}] no fresh price+volume crosses.")
        return out
    if band_filter:
        out = out[out["band"] == band_filter]
    _report(out, label, recent, top)
    return out


def _report(df: pd.DataFrame, label: str, recent: int, top: int) -> None:
    print(f"\n{'#'*104}\n#  {label.upper()} — PRICE x VOLUME bandpass CROSS "
          f"(both inflected within {recent} bars; as-of staleness-filtered)\n{'#'*104}")
    for band, _, _ in BANDS:
        sub = df[df["band"] == band]
        if sub.empty:
            continue
        print(f"\n=== Band {band} === ({len(sub)} crosses)")
        for quad in ["ACCUMULATION", "CAPITULATION", "WEAK RALLY", "QUIET DECLINE"]:
            q = sub[sub["quadrant"] == quad].sort_values("mag", ascending=False).head(top)
            if q.empty:
                continue
            print(f"  {quad}  (price {q.iloc[0]['price_dir']} + volume {q.iloc[0]['vol_dir']}):")
            print(f"    {'Sym':<7}{'Sector':<22}{'Cap':<10}{'Pslope':>8}{'Vslope':>8}"
                  f"{'Pbars':>6}{'Vbars':>6}{'conf':>6}")
            for _, r in q.iterrows():
                print(f"    {r['symbol']:<7}{str(r['sector'])[:21]:<22}"
                      f"{str(r['cap'])[:9]:<10}{r['price_slope_z']:>8.2f}"
                      f"{r['vol_slope_z']:>8.2f}{r['price_bars']:>6}{r['vol_bars']:>6}"
                      f"{('ok' if r['settled'] else 'low'):>6}")


# --------------------------------------------------------------------------- #
def run(args):
    uni = get_universe(limit=args.limit, source=args.universe)
    symbols = uni["symbol"].tolist()
    sectors = dict(zip(uni["symbol"], uni["sector"]))
    caps = dict(zip(uni["symbol"], uni.get("market_cap", pd.Series(index=uni.index, dtype=str))))

    results = []
    if not args.weekly_only:
        d = download_ohlcv(symbols, period=args.daily_period, interval="1d", refresh=args.refresh)
        r = cross_timeframe(d, "daily", args.recent_daily, sectors, caps, args.top, args.band)
        if not r.empty:
            results.append(r)
    if not args.daily_only:
        w = download_ohlcv(symbols, period=args.weekly_period, interval="1wk", refresh=args.refresh)
        r = cross_timeframe(w, "weekly", args.recent_weekly, sectors, caps, args.top, args.band)
        if not r.empty:
            results.append(r)

    if results and args.csv:
        pd.concat(results, ignore_index=True).sort_values(
            ["tf", "band", "quadrant", "mag"], ascending=[True, True, True, False]
        ).to_csv(args.csv, index=False)
        print(f"\n[out] full cross table -> {args.csv}")


def parse_args():
    p = argparse.ArgumentParser(description="Price x Volume bandpass cross scanner")
    p.add_argument("--universe", choices=["sp400", *CAP_SOURCES.keys()], default="us-midcap")
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--daily-period", default="20y")
    p.add_argument("--weekly-period", default="20y")
    p.add_argument("--recent-daily", type=int, default=5)
    p.add_argument("--recent-weekly", type=int, default=2)
    p.add_argument("--band", default=None, help="restrict to a single band e.g. B1")
    p.add_argument("--top", type=int, default=20)
    p.add_argument("--daily-only", action="store_true")
    p.add_argument("--weekly-only", action="store_true")
    p.add_argument("--csv", default=None)
    p.add_argument("--refresh", action="store_true")
    return p.parse_args()


if __name__ == "__main__":
    run(parse_args())
