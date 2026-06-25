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

from midcap_weekly_anomalies import get_universe, CACHE_DIR, CAP_SOURCES  # reuse universe
from signals import ehlers_bandpass, BANDS, latest_crossing, drop_incomplete_last  # noqa: F401

warnings.filterwarnings("ignore")


# --------------------------------------------------------------------------- #
# Data download (generic interval) with on-disk pickle cache
# --------------------------------------------------------------------------- #
def download_ohlcv(symbols: list[str], period: str, interval: str,
                   refresh: bool = False,
                   seed: dict[str, pd.DataFrame] | None = None,
                   cached_only: bool = False) -> dict[str, pd.DataFrame]:
    import yfinance as yf
    from yfsession import SESSION

    os.makedirs(CACHE_DIR, exist_ok=True)
    # cache is a per-symbol dict pickle so repeated runs ACCUMULATE coverage
    # (Yahoo aggressively rate-limits large universes, so one pass is partial).
    cache = os.path.join(CACHE_DIR, f"ohlcvdict_{interval}_{period}.pkl")
    have: dict[str, pd.DataFrame] = {}
    if os.path.exists(cache) and not refresh:
        try:
            have = pd.read_pickle(cache)
        except Exception:
            have = {}

    # optionally seed from another interval's frames (e.g. the seasonal weekly cache)
    if seed:
        for s, df in seed.items():
            if s not in have and "Volume" in df:
                have[s] = df[["Close", "Volume"]].copy()

    todo = [] if cached_only else [s for s in symbols if s not in have]
    if cached_only:
        print(f"[data:{interval}] cached-only: {len(have)} available")
    else:
        print(f"[data:{interval}] cached {len(have)} | to fetch {len(todo)} / {len(symbols)}")

    batch = 30
    miss_streak = 0
    for i in range(0, len(todo), batch):
        chunk = todo[i:i + batch]
        print(f"[data:{interval}] fetch {i + 1}-{i + len(chunk)} / {len(todo)} ...")
        if i > 0:
            time.sleep(2.0)  # ease Yahoo rate limiting on large universes
        got_before = len(have)
        try:
            data = yf.download(chunk, period=period, interval=interval,
                               auto_adjust=True, progress=False, threads=True,
                               group_by="ticker", session=SESSION)
        except Exception as e:
            print(f"   batch failed: {e!r}")
            data = None
        if data is not None:
            for sym in chunk:
                try:
                    sub = data[sym] if len(chunk) > 1 else data
                    sub = sub.dropna(how="all")
                    if sub is not None and "Volume" in sub and len(sub) > 60:
                        have[sym] = sub[["Close", "Volume"]].copy()
                except Exception:
                    continue
        try:
            pd.to_pickle(have, cache)  # checkpoint after every batch
        except Exception as e:
            print(f"[data:{interval}] cache write skipped: {e!r}")
        # early-abort: if several consecutive batches add nothing, Yahoo is rate
        # limiting -> bail so the outer loop can pause and let the budget recover.
        miss_streak = 0 if len(have) > got_before else miss_streak + 1
        if miss_streak >= 5:
            print(f"[data:{interval}] rate-limited ({miss_streak} empty batches); "
                  f"stopping pass early.")
            break

    out = {s: have[s] for s in symbols if s in have and len(have[s]) > 60}
    print(f"[data:{interval}] usable: {len(out)} / {len(symbols)}")
    return out


# --------------------------------------------------------------------------- #
# Per-series band analysis
# --------------------------------------------------------------------------- #
def analyse_series(vol: pd.Series, recent: int) -> list[dict]:
    """Return one row per band describing its most recent zero-line crossing
    (uses the shared hysteresis-aware detector)."""
    vol = vol.dropna()  # seeded frames may carry NaN padding from a union index
    v = np.log1p(vol.astype(float).to_numpy())
    idx = vol.index
    n = len(v)
    rows = []
    bdict = {b[0]: b for b in BANDS}
    for name, info in latest_crossing(v, recent).items():
        flen, slen = bdict[name][1], bdict[name][2]
        ci = (n - 1) - info["bars_ago"]
        rows.append({
            "band": name, "flen_slen": f"{flen}/{slen}",
            "state": "ABOVE" if info["pb_z"] >= 0 else "BELOW",
            "direction": info["dir"], "bars_ago": int(info["bars_ago"]),
            "cross_date": idx[ci].date().isoformat(),
            "pb_last_z": info["pb_z"], "slope_z": info["slope_z"],
            "fresh": info["fresh"], "settled": info["settled"],
            "last_date": idx[-1], "n": n,
        })
    return rows


# --------------------------------------------------------------------------- #
# Pipeline
# --------------------------------------------------------------------------- #
def scan_timeframe(frames: dict, label: str, recent: int,
                   sectors: dict, top: int) -> pd.DataFrame:
    rows = []
    for sym, df in frames.items():
        # drop the in-progress bar for ALL timeframes (intraday/daily/weekly)
        vol = drop_incomplete_last(df[["Volume"]], label)["Volume"]
        for r in analyse_series(vol, recent):
            r["symbol"] = sym
            r["sector"] = sectors.get(sym, "?")
            r["tf"] = label
            rows.append(r)
    out = pd.DataFrame(rows)
    if out.empty:
        print(f"\n[{label}] no bands with sufficient history.")
        return out
    # staleness guard: a crossing is only "current" if the series trades up to
    # ~now. Delisted/acquired names end early, so their last bar looks 'fresh'
    # even though it is weeks/months old. Drop them from the fresh signal set.
    out["last_date"] = pd.to_datetime(out["last_date"])
    asof = out["last_date"].max()
    tol = {"daily": pd.Timedelta(days=8), "weekly": pd.Timedelta(days=12),
           "90m": pd.Timedelta(days=3)}.get(label, pd.Timedelta(days=8))
    out["current"] = out["last_date"] >= (asof - tol)
    stale = int((~out["current"]).sum())
    out["fresh"] = out["fresh"] & out["current"]
    print(f"\n[{label}] as-of {asof.date()}  (dropped {stale} stale/delisted rows "
          f"older than {tol.days}d)")
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

    if args.m90_only:
        args.m90 = True
    results = {}
    if args.m90:
        # 90m intraday: Yahoo caps history ~60d (~260 bars) -> only Band B1 usable.
        h = download_ohlcv(symbols, period=args.m90_period, interval="90m",
                           refresh=args.refresh)
        results["90m"] = scan_timeframe(h, "90m", args.recent_m90, sectors, args.top)
    if not args.weekly_only and not args.m90_only:
        d = download_ohlcv(symbols, period=args.daily_period, interval="1d",
                           refresh=args.refresh)
        results["daily"] = scan_timeframe(d, "daily", args.recent_daily, sectors, args.top)
    if not args.daily_only and not args.m90_only:
        # weekly shares the accumulating cache with the seasonal scanner
        # (ohlcvdict_1wk_<period>.pkl), so coverage is reused across both tools.
        w = download_ohlcv(symbols, period=args.weekly_period, interval="1wk",
                           refresh=args.refresh)
        results["weekly"] = scan_timeframe(w, "weekly", args.recent_weekly, sectors, args.top)

    if args.csv:
        parts = [v for v in results.values() if not v.empty]
        if parts:
            full = pd.concat(parts, ignore_index=True)
            full.sort_values(["tf", "band", "direction", "slope_z"]).to_csv(args.csv, index=False)
            print(f"\n[out] full crossings table -> {args.csv}")
        else:
            print("\n[out] nothing to write (no crossings).")


def parse_args():
    p = argparse.ArgumentParser(description="Volume bandpass inflection scanner (S&P MidCap 400)")
    p.add_argument("--universe", choices=["sp400", *CAP_SOURCES.keys()], default="sp400",
                   help="sp400 = S&P 400; us-<bucket> = financedatabase market-cap "
                        "buckets (us-midcap, us-smallcap, us-microcap, us-smallmicro, ...)")
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--daily-period", default="20y")
    p.add_argument("--weekly-period", default="20y")
    p.add_argument("--recent-daily", type=int, default=5, help="bars to count as 'fresh' (daily)")
    p.add_argument("--recent-weekly", type=int, default=2, help="bars to count as 'fresh' (weekly)")
    p.add_argument("--recent-m90", type=int, default=6, help="fresh window in 90m bars")
    p.add_argument("--m90-period", default="60d", help="history for 90m (Yahoo max ~60d)")
    p.add_argument("--top", type=int, default=20)
    p.add_argument("--daily-only", action="store_true")
    p.add_argument("--weekly-only", action="store_true")
    p.add_argument("--m90", action="store_true", help="include the 90-minute timeframe")
    p.add_argument("--m90-only", action="store_true", help="only the 90m timeframe")
    p.add_argument("--csv", default=None)
    p.add_argument("--refresh", action="store_true")
    return p.parse_args()


if __name__ == "__main__":
    run(parse_args())
