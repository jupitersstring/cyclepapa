#!/usr/bin/env python3
"""
Price & Volume bandpass inflections, broken out by band length and timeframe.

For PRICE (close) and VOLUME (log volume) separately, runs the Ehlers bandpass
at each length (B1 40/60, B2 200/300, B3 600/900, B4 1200/2400) on each
timeframe (90m / daily / weekly) and lists the names whose bandpass has freshly
crossed the zero line (▲ up = cycle turning up, ▼ down = turning down).

Feasibility by timeframe (history limits which bands settle):
  90m  (~260 bars)  -> B1 only
  daily(~5000 bars) -> B1,B2,B3,B4
  weekly(~1040 bars)-> B1,B2 (B3 only for the oldest names)

Usage:
    python3 pv_inflections.py --universe us-midcap --daily --weekly --m90 --cached-only
    python3 pv_inflections.py --universe us-smallcap --weekly --top 15
"""
from __future__ import annotations

import argparse

import numpy as np
import pandas as pd

from volume_bandpass import BANDS, download_ohlcv
from pv_cross import band_crossings
from signals import drop_incomplete_last
from midcap_weekly_anomalies import get_universe, CAP_SOURCES  # noqa: F401


def scan(frames: dict, label: str, recent: int, sectors: dict, caps: dict,
         top: int) -> pd.DataFrame:
    intraday = label.endswith("m")
    last_dates = {s: df.dropna().index[-1] for s, df in frames.items() if len(df.dropna())}
    if not last_dates:
        print(f"\n[{label}] no data.")
        return pd.DataFrame()
    asof = max(last_dates.values())
    tol = pd.Timedelta(days=3 if intraday else (8 if label == "daily" else 12))

    rows = []
    for sym, df in frames.items():
        d = drop_incomplete_last(df, label, asof=asof)  # drop in-progress bar (all TFs)
        if len(d) < 60 or last_dates.get(sym) < (asof - tol):
            continue
        sources = {"PRICE": np.log(d["Close"].astype(float).clip(lower=1e-9).to_numpy()),
                   "VOLUME": np.log1p(d["Volume"].astype(float).to_numpy())}
        for src, vals in sources.items():
            for band, info in band_crossings(vals).items():
                if info["bars_ago"] > recent:
                    continue
                rows.append({"symbol": sym, "sector": sectors.get(sym, "?"),
                             "cap": caps.get(sym, "?"), "tf": label, "source": src,
                             "band": band, "dir": info["dir"],
                             "bars_ago": info["bars_ago"], "slope_z": info["slope_z"],
                             "pb_z": info["pb_z"]})
    out = pd.DataFrame(rows)
    if out.empty:
        print(f"\n[{label}] no fresh inflections.")
        return out
    _report(out, label, recent, top)
    return out


def _report(df: pd.DataFrame, label: str, recent: int, top: int) -> None:
    print(f"\n{'#'*100}\n#  {label.upper()} — price & volume bandpass inflections by band "
          f"(fresh within {recent} bars)\n{'#'*100}")
    for src in ["PRICE", "VOLUME"]:
        s0 = df[df["source"] == src]
        if s0.empty:
            continue
        print(f"\n***** {src} *****")
        for band, flen, slen in BANDS:
            sub = s0[s0["band"] == band]
            if sub.empty:
                continue
            ups = sub[sub["dir"] == "UP"].copy()
            dns = sub[sub["dir"] == "DOWN"].copy()
            ups["m"] = ups["slope_z"].abs()
            dns["m"] = dns["slope_z"].abs()
            ups = ups.sort_values("m", ascending=False).head(top)
            dns = dns.sort_values("m", ascending=False).head(top)
            print(f"  -- Band {band} ({flen}/{slen}) -- "
                  f"{(sub['dir']=='UP').sum()} up / {(sub['dir']=='DOWN').sum()} down")
            if not ups.empty:
                print("     ▲ UP  : " + ", ".join(ups["symbol"].tolist()))
            if not dns.empty:
                print("     ▼ DOWN: " + ", ".join(dns["symbol"].tolist()))


def run(args):
    uni = get_universe(limit=args.limit, source=args.universe)
    symbols = uni["symbol"].tolist()
    sectors = dict(zip(uni["symbol"], uni["sector"]))
    caps = dict(zip(uni["symbol"], uni.get("market_cap", pd.Series(index=uni.index, dtype=str))))

    results = []
    if args.m90:
        h = download_ohlcv(symbols, period="60d", interval="90m",
                           refresh=args.refresh, cached_only=args.cached_only)
        r = scan(h, "90m", args.recent_m90, sectors, caps, args.top)
        if not r.empty: results.append(r)
    if args.daily:
        d = download_ohlcv(symbols, period=args.period, interval="1d",
                           refresh=args.refresh, cached_only=args.cached_only)
        r = scan(d, "daily", args.recent_daily, sectors, caps, args.top)
        if not r.empty: results.append(r)
    if args.weekly:
        w = download_ohlcv(symbols, period=args.period, interval="1wk",
                           refresh=args.refresh, cached_only=args.cached_only)
        r = scan(w, "weekly", args.recent_weekly, sectors, caps, args.top)
        if not r.empty: results.append(r)

    if results and args.csv:
        pd.concat(results, ignore_index=True).sort_values(
            ["tf", "source", "band", "dir", "slope_z"]).to_csv(args.csv, index=False)
        print(f"\n[out] -> {args.csv}")


def parse_args():
    p = argparse.ArgumentParser(description="Price & volume bandpass inflections by band & timeframe")
    p.add_argument("--universe", choices=["sp400", *CAP_SOURCES.keys()], default="us-midcap")
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--period", default="20y")
    p.add_argument("--weekly", action="store_true")
    p.add_argument("--daily", action="store_true")
    p.add_argument("--m90", action="store_true")
    p.add_argument("--recent-daily", type=int, default=5)
    p.add_argument("--recent-weekly", type=int, default=2)
    p.add_argument("--recent-m90", type=int, default=6)
    p.add_argument("--top", type=int, default=15)
    p.add_argument("--cached-only", action="store_true")
    p.add_argument("--refresh", action="store_true")
    p.add_argument("--csv", default=None)
    a = p.parse_args()
    if not (a.weekly or a.daily or a.m90):
        a.daily = a.weekly = a.m90 = True
    return a


if __name__ == "__main__":
    run(parse_args())
