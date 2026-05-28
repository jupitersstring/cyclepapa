#!/usr/bin/env python3
"""
S&P MidCap 400 — Weekly Seasonal Anomaly Scanner
================================================

For each asset and each *week-of-year*, this collects all historical
observations of that same calendar week across years and computes a rich set of
"conditional state" anomaly metrics (not just average return):

  - Return quality .... mean, median, Sharpe, Sortino, robust Sharpe, t-stat
  - Payoff asymmetry .. gain-to-pain, tail ratio, skew, worst week
  - Reliability ....... win rate, sample size, sub-period stability
  - Volume confirm .... relative volume, return x volume_z, net accumulation,
                        volume-adjusted gain-to-pain
  - Volatility state .. realized-vol anomaly, compression score
  - Forward effect .... post-window 4-week drift (persistence)
  - Liquidity ......... median dollar volume + cross-sectional percentile

Everything is penalised for small samples (sqrt(n/(n+K))) and for instability
across sub-periods, then z-scored cross-sectionally and blended into a composite
score (separately for long and short interpretations).

Universe: S&P 400 MidCap constituents (Wikipedia, with a static fallback).
Data:     yfinance weekly bars.

Usage:
    python3 midcap_weekly_anomalies.py                 # current week, full 400
    python3 midcap_weekly_anomalies.py --limit 50      # quick subset
    python3 midcap_weekly_anomalies.py --target-week 22 --top 30
"""
from __future__ import annotations

import argparse
import io
import os
import sys
import time
import warnings
from dataclasses import dataclass

import numpy as np
import pandas as pd
import requests

warnings.filterwarnings("ignore")

CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".cache")
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AnomalyScanner/1.0"}
WIKI_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_400_companies"

SAMPLE_K = 20.0  # shrinkage constant for the sample-size penalty


# --------------------------------------------------------------------------- #
# Universe
# --------------------------------------------------------------------------- #
def get_universe(limit: int | None = None) -> pd.DataFrame:
    """Return DataFrame[symbol, security, sector] of S&P 400 MidCap names."""
    try:
        r = requests.get(WIKI_URL, headers=UA, timeout=30)
        r.raise_for_status()
        table = pd.read_html(io.StringIO(r.text))[0]
        df = pd.DataFrame(
            {
                "symbol": table["Symbol"].astype(str).str.replace(".", "-", regex=False),
                "security": table["Security"].astype(str),
                "sector": table["GICS Sector"].astype(str),
            }
        )
        df = df.drop_duplicates("symbol").reset_index(drop=True)
        print(f"[universe] fetched {len(df)} S&P 400 MidCap constituents from Wikipedia")
    except Exception as e:  # pragma: no cover - network fallback
        print(f"[universe] Wikipedia fetch failed ({e!r}); using static fallback")
        df = pd.DataFrame(
            {"symbol": _FALLBACK, "security": _FALLBACK, "sector": "Unknown"}
        )
    if limit:
        df = df.head(limit).reset_index(drop=True)
    return df


_FALLBACK = [
    "JBL", "DKS", "WSM", "RPM", "EME", "MANH", "WMS", "CASY", "BURL", "FIX",
    "USFD", "RGA", "PSTG", "EWBC", "GGG", "CSL", "WCC", "DOCU", "CW", "ATR",
]


# --------------------------------------------------------------------------- #
# Data download (yfinance) with on-disk cache
# --------------------------------------------------------------------------- #
def download_weekly(symbols: list[str], years: int, refresh: bool = False) -> dict[str, pd.DataFrame]:
    """Download weekly OHLCV for symbols, caching the combined frame to parquet."""
    import yfinance as yf

    os.makedirs(CACHE_DIR, exist_ok=True)
    cache = os.path.join(CACHE_DIR, f"weekly_{years}y_{len(symbols)}.pkl")
    if os.path.exists(cache) and not refresh:
        age_h = (time.time() - os.path.getmtime(cache)) / 3600
        if age_h < 24 * 7:
            print(f"[data] using cache {os.path.basename(cache)} ({age_h:.1f}h old)")
            raw = pd.read_pickle(cache)
            return _split_panel(raw)

    period = f"{years}y"
    frames = {}
    batch = 40
    for i in range(0, len(symbols), batch):
        chunk = symbols[i : i + batch]
        print(f"[data] downloading {i + 1}-{i + len(chunk)} / {len(symbols)} ...")
        try:
            data = yf.download(
                chunk, period=period, interval="1wk",
                auto_adjust=True, progress=False, threads=True, group_by="ticker",
            )
        except Exception as e:
            print(f"   batch failed: {e!r}")
            continue
        for sym in chunk:
            try:
                sub = data[sym] if len(chunk) > 1 else data
                sub = sub.dropna(how="all")
                if sub is not None and len(sub) > 52:
                    frames[sym] = sub[["Close", "High", "Low", "Open", "Volume"]].copy()
            except Exception:
                continue

    if frames:
        panel = pd.concat(frames, axis=1)
        panel.columns = pd.MultiIndex.from_tuples(
            [(s, f) for s, f in panel.columns], names=["symbol", "field"]
        )
        try:
            panel.to_pickle(cache)
        except Exception as e:
            print(f"[data] cache write skipped: {e!r}")
    print(f"[data] usable price histories: {len(frames)} / {len(symbols)}")
    return frames


def _split_panel(panel: pd.DataFrame) -> dict[str, pd.DataFrame]:
    out = {}
    for sym in panel.columns.get_level_values(0).unique():
        sub = panel[sym].dropna(how="all")
        if len(sub) > 52:
            out[sym] = sub
    return out


# --------------------------------------------------------------------------- #
# Per-asset feature engineering
# --------------------------------------------------------------------------- #
def build_features(df: pd.DataFrame) -> pd.DataFrame:
    """Compute weekly return, volume z-score, dollar volume and forward drift."""
    out = pd.DataFrame(index=df.index)
    close = df["Close"].astype(float)
    vol = df["Volume"].astype(float)

    out["ret"] = close.pct_change(fill_method=None)
    out["dollar_vol"] = close * vol

    roll_mean = vol.rolling(52, min_periods=26).mean()
    roll_std = vol.rolling(52, min_periods=26).std()
    out["vol_z"] = ((vol - roll_mean) / roll_std).replace([np.inf, -np.inf], np.nan)

    # forward 4-week cumulative return measured *after* the current week
    out["fwd4"] = close.shift(-4) / close - 1.0

    out["woy"] = df.index.isocalendar().week.astype(int).values
    out["year"] = df.index.year
    return out.dropna(subset=["ret"])


# --------------------------------------------------------------------------- #
# Bucket metrics (one week-of-year, one asset)
# --------------------------------------------------------------------------- #
def _safe(x):
    return float(x) if np.isfinite(x) else np.nan


def bucket_metrics(g: pd.DataFrame) -> dict:
    r = g["ret"].to_numpy()
    vz = g["vol_z"].fillna(0).to_numpy()
    dv = g["dollar_vol"].to_numpy()
    fwd = g["fwd4"].dropna().to_numpy()
    n = len(r)
    m: dict[str, float] = {"n": n}

    mean = np.mean(r)
    std = np.std(r, ddof=1) if n > 1 else np.nan
    m["mean_ret"] = _safe(mean)
    m["median_ret"] = _safe(np.median(r))
    m["sharpe"] = _safe(mean / std) if std and std > 0 else np.nan
    m["win_rate"] = _safe(np.mean(r > 0))
    m["worst"] = _safe(np.min(r))

    # robust Sharpe (median / MAD)
    mad = np.median(np.abs(r - np.median(r)))
    m["robust_sharpe"] = _safe(np.median(r) / mad) if mad > 0 else np.nan

    # Sortino
    downside = r[r < 0]
    dd = np.sqrt(np.mean(downside ** 2)) if downside.size else np.nan
    m["sortino"] = _safe(mean / dd) if dd and dd > 0 else np.nan

    # t-stat
    m["t_stat"] = _safe(mean / (std / np.sqrt(n))) if std and std > 0 and n > 1 else np.nan

    # gain-to-pain
    pos, neg = r[r > 0].sum(), -r[r < 0].sum()
    m["gain_to_pain"] = _safe(pos / neg) if neg > 0 else (np.nan if pos == 0 else 10.0)

    # tail ratio / skew
    if n >= 5:
        hi = np.mean(r[r >= np.quantile(r, 0.8)])
        lo = np.mean(r[r <= np.quantile(r, 0.2)])
        m["tail_ratio"] = _safe(hi / abs(lo)) if lo < 0 else np.nan
        m["skew"] = _safe(pd.Series(r).skew())
    else:
        m["tail_ratio"] = np.nan
        m["skew"] = np.nan

    # volume confirmation
    m["rel_volume"] = _safe(np.exp(np.mean(np.log1p(np.clip(vz, -0.99, None)))))  # not used directly
    m["ret_x_vol"] = _safe(np.mean(r * vz))
    acc = np.mean(np.maximum(r, 0) * vz)
    dist = np.mean(np.abs(np.minimum(r, 0)) * vz)
    m["net_accumulation"] = _safe(acc - dist)

    # volume-adjusted gain-to-pain (positive volume weight only)
    w = np.maximum(vz, 0)
    va_pos = np.sum(np.maximum(r, 0) * w)
    va_neg = -np.sum(np.minimum(r, 0) * w)
    m["va_gpr"] = _safe(va_pos / va_neg) if va_neg > 0 else (np.nan if va_pos == 0 else 10.0)

    # liquidity
    m["dollar_vol"] = _safe(np.median(dv))

    # forward persistence (post-window 4w drift)
    m["persistence"] = _safe(np.mean(fwd)) if fwd.size else np.nan

    # sub-period stability: sign agreement of chunk means vs overall mean
    k = min(3, n // 2)
    if k >= 2 and mean != 0:
        chunks = np.array_split(r, k)
        agree = np.mean([np.sign(np.mean(c)) == np.sign(mean) for c in chunks])
        m["stability"] = _safe(agree)
    else:
        m["stability"] = 0.5

    m["sample_penalty"] = float(np.sqrt(n / (n + SAMPLE_K)))
    return m


# --------------------------------------------------------------------------- #
# Scoring
# --------------------------------------------------------------------------- #
def _z(s: pd.Series) -> pd.Series:
    sd = s.std(ddof=0)
    return (s - s.mean()) / sd if sd and sd > 0 else s * 0.0


def score_table(rows: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(rows)
    if df.empty:
        return df

    # cross-sectional liquidity percentile (over all asset-week rows)
    df["liquidity_pct"] = df["dollar_vol"].rank(pct=True)

    # tradable Sharpe = Sharpe * liquidity_pct * sample_penalty * stability
    df["tradable_sharpe"] = (
        df["sharpe"].fillna(0)
        * df["liquidity_pct"]
        * df["sample_penalty"]
        * df["stability"]
    )

    z_ts = _z(df["tradable_sharpe"])
    z_gpr = _z(df["va_gpr"].clip(upper=10).fillna(df["va_gpr"].median()))
    z_na = _z(df["net_accumulation"].fillna(0))
    z_pers = _z(df["persistence"].fillna(0))
    z_liq = _z(np.log1p(df["dollar_vol"].fillna(0)))

    df["composite_long"] = (
        0.30 * z_ts + 0.25 * z_gpr + 0.20 * z_na + 0.15 * z_pers + 0.10 * z_liq
    )
    df["composite_short"] = (
        0.30 * (-z_ts) + 0.25 * (-z_gpr) + 0.20 * (-z_na) + 0.15 * (-z_pers) + 0.10 * z_liq
    )
    df["direction"] = np.where(df["composite_long"] >= df["composite_short"], "LONG", "SHORT")
    df["score"] = df[["composite_long", "composite_short"]].max(axis=1)
    return df


# --------------------------------------------------------------------------- #
# Pipeline
# --------------------------------------------------------------------------- #
def run(args) -> None:
    universe = get_universe(limit=args.limit)
    symbols = universe["symbol"].tolist()
    sector_map = dict(zip(universe["symbol"], universe["sector"]))
    name_map = dict(zip(universe["symbol"], universe["security"]))

    frames = download_weekly(symbols, years=args.years, refresh=args.refresh)
    if not frames:
        print("No data downloaded — aborting.")
        sys.exit(1)

    target = args.target_week or pd.Timestamp(args.today).isocalendar().week
    print(f"\n[scan] target week-of-year = {target} "
          f"(min {args.min_years} yrs of history per bucket)\n")

    rows = []
    for sym, df in frames.items():
        feats = build_features(df)
        g = feats[feats["woy"] == target]
        if len(g) < args.min_years:
            continue
        m = bucket_metrics(g)
        m["symbol"] = sym
        m["sector"] = sector_map.get(sym, "?")
        m["name"] = name_map.get(sym, sym)
        m["years"] = f"{int(g['year'].min())}-{int(g['year'].max())}"
        rows.append(m)

    if not rows:
        print("No buckets met the minimum-history threshold.")
        return

    scored = score_table(rows)
    _report(scored, target, args.top)
    if args.csv:
        scored.sort_values("score", ascending=False).to_csv(args.csv, index=False)
        print(f"\n[out] full table written to {args.csv}")


# --------------------------------------------------------------------------- #
# Reporting
# --------------------------------------------------------------------------- #
def _fmt_pct(x):
    return f"{x*100:+.1f}%" if pd.notna(x) else "  -  "


def _report(df: pd.DataFrame, week: int, top: int) -> None:
    longs = df[df["direction"] == "LONG"].sort_values("score", ascending=False).head(top)
    shorts = df[df["direction"] == "SHORT"].sort_values("score", ascending=False).head(top)

    def block(title, t):
        print(f"\n{'='*108}\n{title}\n{'='*108}")
        hdr = (f"{'Sym':<7}{'Sector':<22}{'Score':>7}{'Shrp':>7}{'GPR':>7}"
               f"{'NetAcc':>9}{'Fwd4w':>8}{'Win%':>7}{'AvgRet':>9}{'$Vol pct':>9}{'n':>4}")
        print(hdr)
        print("-" * 108)
        for _, r in t.iterrows():
            print(
                f"{r['symbol']:<7}{str(r['sector'])[:21]:<22}{r['score']:>7.2f}"
                f"{(r['sharpe'] if pd.notna(r['sharpe']) else 0):>7.2f}"
                f"{(min(r['va_gpr'],10) if pd.notna(r['va_gpr']) else 0):>7.2f}"
                f"{(r['net_accumulation'] if pd.notna(r['net_accumulation']) else 0):>9.3f}"
                f"{_fmt_pct(r['persistence']):>8}"
                f"{(r['win_rate']*100 if pd.notna(r['win_rate']) else 0):>6.0f}%"
                f"{_fmt_pct(r['mean_ret']):>9}"
                f"{r['liquidity_pct']:>8.0%}"
                f"{int(r['n']):>4}"
            )

    print(f"\n###  S&P 400 MidCap — Week-of-Year {week} seasonal anomalies  ###")
    print(f"###  {len(df)} names had >= min history this week.  "
          f"Score = cross-sectional composite (tradable Sharpe + vol-adj gain/pain "
          f"+ net accumulation + persistence + liquidity).")
    block(f"TOP {len(longs)} BULLISH seasonal anomalies (LONG)", longs)
    block(f"TOP {len(shorts)} BEARISH seasonal anomalies (SHORT)", shorts)


def parse_args():
    p = argparse.ArgumentParser(description="S&P MidCap 400 weekly seasonal anomaly scanner")
    p.add_argument("--limit", type=int, default=None, help="cap universe size (testing)")
    p.add_argument("--years", type=int, default=20, help="years of weekly history")
    p.add_argument("--target-week", type=int, default=None, help="ISO week-of-year to scan")
    p.add_argument("--today", default="2026-05-28", help="reference date for current week")
    p.add_argument("--min-years", type=int, default=8, help="min historical obs per bucket")
    p.add_argument("--top", type=int, default=25, help="rows per direction to print")
    p.add_argument("--csv", default=None, help="optional path to write full table")
    p.add_argument("--refresh", action="store_true", help="ignore cache, re-download")
    return p.parse_args()


if __name__ == "__main__":
    run(parse_args())
