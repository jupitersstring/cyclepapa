#!/usr/bin/env python3
"""
Volume Bandpass Inflection Scanner — S&P MidCap 400
===================================================

Ports the Ehlers 4-band bandpass filter (© malikmck, MPL-2.0) from Pine to
Python and runs it on *volume* instead of price, across the S&P 400 MidCap
universe, on daily and weekly timeframes.

Ehlers two-pole bandpass recursion (per band, fast length `flen`, slow `slen`):

    a1 = 5/flen ; a2 = 5/slen
    PB = (a1-a2)*s + (a2*(1-a1) - a1*(1-a2))*s[1]
         + ((1-a1)+(1-a2))*PB[1] - (1-a1)*(1-a2)*PB[2]

The four bands (fast/slow, in bars):
    Band 1: 40 / 60      Band 3: 600 / 900
    Band 2: 200 / 300    Band 4: 1200 / 2400

PB oscillates around 0. A cross of the zero line is a cycle *inflection*:
    cross ABOVE 0  -> volume cycle turning UP   (participation building)
    cross BELOW 0  -> volume cycle turning DOWN (participation fading)

The filter is applied to log volume (log1p) to stabilise variance / outliers;
zero-crossing semantics are unaffected. For each name/band/timeframe the scanner
finds the most recent zero crossing and flags names that just inflected.

Usage:
    python3 volume_bandpass.py                  # daily + weekly, full 400
    python3 volume_bandpass.py --limit 40       # quick subset
    python3 volume_bandpass.py --recent-daily 5 --recent-weekly 2 --top 20
"""
from __future__ import annotations

import argparse
import os
import sys
import time
import warnings

import numpy as np
import pandas as pd

from midcap_weekly_anomalies import get_universe, CACHE_DIR  # reuse universe

warnings.filterwarnings("ignore")

BANDS = [
    ("B1", 40, 60),
    ("B2", 200, 300),
    ("B3", 600, 900),
    ("B4", 1200, 2400),
]


# --------------------------------------------------------------------------- #
# Ehlers two-pole bandpass (faithful port of the Pine recursion w/ nz=0)
# --------------------------------------------------------------------------- #
def ehlers_bandpass(src: np.ndarray, flen: int, slen: int) -> np.ndarray:
    a1 = 5.0 / flen
    a2 = 5.0 / slen
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


# --------------------------------------------------------------------------- #
# Data download (generic interval) with on-disk pickle cache
# --------------------------------------------------------------------------- #
def download_ohlcv(symbols: list[str], period: str, interval: str,
                   refresh: bool = False) -> dict[str, pd.DataFrame]:
    import yfinance as yf

    os.makedirs(CACHE_DIR, exist_ok=True)
    cache = os.path.join(CACHE_DIR, f"ohlcv_{interval}_{period}_{len(symbols)}.pkl")
    if os.path.exists(cache) and not refresh:
        age_h = (time.time() - os.path.getmtime(cache)) / 3600
        if age_h < 24 * 7:
            print(f"[data:{interval}] cache {os.path.basename(cache)} ({age_h:.1f}h old)")
            return _split(pd.read_pickle(cache))

    frames = {}
    batch = 40
    for i in range(0, len(symbols), batch):
        chunk = symbols[i:i + batch]
        print(f"[data:{interval}] {i + 1}-{i + len(chunk)} / {len(symbols)} ...")
        try:
            data = yf.download(chunk, period=period, interval=interval,
                               auto_adjust=True, progress=False, threads=True,
                               group_by="ticker")
        except Exception as e:
            print(f"   batch failed: {e!r}")
            continue
        for sym in chunk:
            try:
                sub = data[sym] if len(chunk) > 1 else data
                sub = sub.dropna(how="all")
                if sub is not None and "Volume" in sub and len(sub) > 60:
                    frames[sym] = sub[["Close", "Volume"]].copy()
            except Exception:
                continue

    if frames:
        panel = pd.concat(frames, axis=1)
        panel.columns = pd.MultiIndex.from_tuples(list(panel.columns),
                                                   names=["symbol", "field"])
        try:
            panel.to_pickle(cache)
        except Exception as e:
            print(f"[data:{interval}] cache write skipped: {e!r}")
    print(f"[data:{interval}] usable: {len(frames)} / {len(symbols)}")
    return frames


def _split(panel: pd.DataFrame) -> dict[str, pd.DataFrame]:
    out = {}
    for sym in panel.columns.get_level_values(0).unique():
        sub = panel[sym].dropna(how="all")
        if "Volume" in sub and len(sub) > 60:
            out[sym] = sub
    return out


# --------------------------------------------------------------------------- #
# Per-series band analysis
# --------------------------------------------------------------------------- #
def analyse_series(vol: pd.Series, recent: int) -> list[dict]:
    """Return one row per band that has enough history, describing its most
    recent zero-line crossing."""
    v = np.log1p(vol.astype(float).to_numpy())
    idx = vol.index
    n = len(v)
    rows = []
    for name, flen, slen in BANDS:
        if n < slen:               # not enough history for this band to settle
            continue
        pb = ehlers_bandpass(v, flen, slen)
        # settled region: drop the first `slen` warmup bars for the std estimate
        settled = pb[slen:]
        sd = np.std(settled) if settled.size > 5 else np.std(pb)
        if not np.isfinite(sd) or sd == 0:
            continue

        # most recent zero crossing
        sign = np.sign(pb)
        cross_idx = None
        direction = None
        for t in range(n - 1, max(slen, 1), -1):
            if sign[t] != sign[t - 1] and sign[t] != 0:
                cross_idx = t
                direction = "UP" if pb[t] > pb[t - 1] else "DOWN"
                break
        if cross_idx is None:
            continue

        bars_ago = (n - 1) - cross_idx
        slope_z = (pb[-1] - pb[-2]) / sd if n >= 2 else 0.0
        rows.append({
            "band": name,
            "flen_slen": f"{flen}/{slen}",
            "state": "ABOVE" if pb[-1] >= 0 else "BELOW",
            "direction": direction,
            "bars_ago": int(bars_ago),
            "cross_date": idx[cross_idx].date().isoformat(),
            "pb_last_z": float(pb[-1] / sd),
            "slope_z": float(slope_z),
            "fresh": bars_ago <= recent,
            "settled": n >= int(1.5 * slen),
            "n": n,
        })
    return rows


# --------------------------------------------------------------------------- #
# Pipeline
# --------------------------------------------------------------------------- #
def scan_timeframe(frames: dict, label: str, recent: int,
                   sectors: dict, top: int) -> pd.DataFrame:
    rows = []
    for sym, df in frames.items():
        for r in analyse_series(df["Volume"], recent):
            r["symbol"] = sym
            r["sector"] = sectors.get(sym, "?")
            r["tf"] = label
            rows.append(r)
    out = pd.DataFrame(rows)
    if out.empty:
        print(f"\n[{label}] no bands with sufficient history.")
        return out
    _report_tf(out, label, recent, top)
    return out


def _report_tf(df: pd.DataFrame, label: str, recent: int, top: int) -> None:
    print(f"\n{'#'*100}\n#  {label.upper()} VOLUME BANDPASS — fresh zero-line "
          f"inflections (within last {recent} bars)\n{'#'*100}")
    for name, flen, slen in BANDS:
        sub = df[(df["band"] == name) & df["fresh"]]
        if sub.empty:
            continue
        ups = sub[sub["direction"] == "UP"].copy()
        dns = sub[sub["direction"] == "DOWN"].copy()
        ups["mag"] = ups["slope_z"].abs()
        dns["mag"] = dns["slope_z"].abs()
        ups = ups.sort_values("mag", ascending=False).head(top)
        dns = dns.sort_values("mag", ascending=False).head(top)
        print(f"\n--- Band {name} ({flen}/{slen} bars) --- "
              f"{len(sub)} fresh inflections "
              f"[{len(sub[~sub['settled']])} low-confidence/short-history]")
        _block("  UP-cross (volume cycle turning UP):", ups)
        _block("  DOWN-cross (volume cycle turning DOWN):", dns)


def _block(title: str, t: pd.DataFrame) -> None:
    if t.empty:
        return
    print(title)
    print(f"    {'Sym':<7}{'Sector':<24}{'cross_date':>12}{'bars_ago':>9}"
          f"{'slope_z':>9}{'pb_z':>8}{'conf':>6}")
    for _, r in t.iterrows():
        conf = "ok" if r["settled"] else "low"
        print(f"    {r['symbol']:<7}{str(r['sector'])[:23]:<24}{r['cross_date']:>12}"
              f"{r['bars_ago']:>9}{r['slope_z']:>9.2f}{r['pb_last_z']:>8.2f}{conf:>6}")


def run(args) -> None:
    uni = get_universe(limit=args.limit, source=args.universe)
    symbols = uni["symbol"].tolist()
    sectors = dict(zip(uni["symbol"], uni["sector"]))

    results = {}
    if not args.weekly_only:
        d = download_ohlcv(symbols, period=args.daily_period, interval="1d",
                           refresh=args.refresh)
        results["daily"] = scan_timeframe(d, "daily", args.recent_daily, sectors, args.top)
    if not args.daily_only:
        w = download_ohlcv(symbols, period=args.weekly_period, interval="1wk",
                           refresh=args.refresh)
        results["weekly"] = scan_timeframe(w, "weekly", args.recent_weekly, sectors, args.top)

    if args.csv:
        full = pd.concat([v for v in results.values() if not v.empty], ignore_index=True)
        full.sort_values(["tf", "band", "direction", "slope_z"]).to_csv(args.csv, index=False)
        print(f"\n[out] full crossings table -> {args.csv}")


def parse_args():
    p = argparse.ArgumentParser(description="Volume bandpass inflection scanner (S&P MidCap 400)")
    p.add_argument("--universe", choices=["sp400", "us-midcap"], default="sp400",
                   help="sp400 = S&P 400; us-midcap = all US Mid Caps (financedatabase)")
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--daily-period", default="20y")
    p.add_argument("--weekly-period", default="20y")
    p.add_argument("--recent-daily", type=int, default=5, help="bars to count as 'fresh' (daily)")
    p.add_argument("--recent-weekly", type=int, default=2, help="bars to count as 'fresh' (weekly)")
    p.add_argument("--top", type=int, default=20)
    p.add_argument("--daily-only", action="store_true")
    p.add_argument("--weekly-only", action="store_true")
    p.add_argument("--csv", default=None)
    p.add_argument("--refresh", action="store_true")
    return p.parse_args()


if __name__ == "__main__":
    run(parse_args())
