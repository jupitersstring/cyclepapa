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
US_EXCH = {"NYQ", "NMS", "NGM", "NCM", "ASE"}  # NYSE, Nasdaq GS/GM/CM, NYSE American
import re as _re

# Region registry: code -> (country, {primary exchanges}, currency, yahoo suffix).
# financedatabase already stores tickers with the yahoo suffix (.TO/.DE/.PA/...).
REGIONS = {
    "us": ("United States", US_EXCH, "USD", None),     # US strips '.' -> '-'
    "uk": ("United Kingdom", {"LSE"}, "GBP", "L"),
    "ca": ("Canada", {"TOR"}, "CAD", "TO"),
    "de": ("Germany", {"GER"}, "EUR", "DE"),
    "fr": ("France", {"PAR"}, "EUR", "PA"),
    "nl": ("Netherlands", {"AMS"}, "EUR", "AS"),
    "au": ("Australia", {"ASX"}, "AUD", "AX"),
}
_TICKER_RE = _re.compile(r"^[A-Z]{1,5}(-[A-Z])?$")            # US common stock

_CAPS = {"megacap": ["Mega Cap"], "largecap": ["Large Cap"], "midcap": ["Mid Cap"],
         "smallcap": ["Small Cap"], "microcap": ["Micro Cap"], "nanocap": ["Nano Cap"],
         "smallmicro": ["Small Cap", "Micro Cap"],
         "allcap": ["Mega Cap", "Large Cap", "Mid Cap", "Small Cap", "Micro Cap"]}

# map of --universe source -> (region code, market_cap bucket(s))
CAP_SOURCES = {f"{rc}-{ck}": (rc, caps) for rc in REGIONS for ck, caps in _CAPS.items()}


def get_fd_universe(region: str, caps: list[str], limit: int | None = None) -> pd.DataFrame:
    """Equities in a financedatabase market_cap bucket for a region, filtered to
    its primary exchange(s)/currency with clean tickers. Non-US regions keep the
    yahoo suffix (.L/.TO/.DE/...); US strips '.' to '-' for share classes."""
    country, exch, ccy, suffix = REGIONS[region]
    tick_re = _TICKER_RE if suffix is None else _re.compile(
        rf"^[A-Z0-9]{{1,5}}(-[A-Z])?\.{suffix}$")
    try:
        import financedatabase as fd

        df = fd.Equities().select(country=country)
        sel = df[df["market_cap"].isin(caps)].copy()
        sel = sel[sel["exchange"].isin(exch) & (sel["currency"] == ccy)]
        sel = sel[[bool(tick_re.match(str(t))) for t in sel.index]]
        sel = sel[~sel.index.duplicated()]
        symbols = [str(t).replace(".", "-") if suffix is None else str(t) for t in sel.index]
        symbols = list(dict.fromkeys(symbols))
        out = pd.DataFrame({
            "symbol": symbols,
            "security": sel["name"].fillna(sel.index.to_series()).astype(str).values,
            "sector": sel["sector"].fillna("Unknown").astype(str).values,
            "market_cap": sel["market_cap"].astype(str).values,
        }).reset_index(drop=True)
        print(f"[universe] {len(out)} {country} equities from financedatabase "
              f"({'+'.join(caps)})")
    except Exception as e:  # pragma: no cover
        print(f"[universe] financedatabase unavailable ({e!r}); using S&P 400")
        return get_universe(limit=limit)
    if limit:
        out = out.head(limit).reset_index(drop=True)
    return out


def get_us_universe(caps: list[str], limit: int | None = None) -> pd.DataFrame:
    return get_fd_universe("us", caps, limit)


def get_universe(limit: int | None = None, source: str = "sp400") -> pd.DataFrame:
    """Return DataFrame[symbol, security, sector].

    source="sp400"        -> S&P 400 MidCap (Wikipedia)
    source="us-<bucket>"  -> financedatabase market-cap bucket(s); see CAP_SOURCES
    """
    if source in CAP_SOURCES:
        region, caps = CAP_SOURCES[source]
        return get_fd_universe(region, caps, limit=limit)
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
    """Download weekly Close+Volume for symbols. Uses a shared, incremental,
    per-symbol dict cache (same file the volume scanner uses) that checkpoints
    after every batch, so repeated runs ACCUMULATE coverage despite Yahoo's
    aggressive rate limiting on large universes. (build_features only needs
    Close and Volume.)"""
    import yfinance as yf

    os.makedirs(CACHE_DIR, exist_ok=True)
    cache = os.path.join(CACHE_DIR, f"ohlcvdict_1wk_{years}y.pkl")
    have: dict[str, pd.DataFrame] = {}
    if os.path.exists(cache) and not refresh:
        try:
            have = pd.read_pickle(cache)
        except Exception:
            have = {}

    todo = [s for s in symbols if s not in have]
    print(f"[data] weekly cache {len(have)} | to fetch {len(todo)} / {len(symbols)}")

    period = f"{years}y"
    batch = 30
    for i in range(0, len(todo), batch):
        chunk = todo[i : i + batch]
        print(f"[data] fetch {i + 1}-{i + len(chunk)} / {len(todo)} ...")
        if i > 0:
            time.sleep(2.0)
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
                if sub is not None and "Volume" in sub and len(sub) > 52:
                    have[sym] = sub[["Close", "Volume"]].copy()
            except Exception:
                continue
        try:
            pd.to_pickle(have, cache)
        except Exception as e:
            print(f"[data] cache write skipped: {e!r}")

    out = {s: have[s] for s in symbols if s in have and len(have[s]) > 52}
    print(f"[data] usable price histories: {len(out)} / {len(symbols)}")
    return out


# --------------------------------------------------------------------------- #
# Per-asset feature engineering
# --------------------------------------------------------------------------- #
def build_features(df: pd.DataFrame) -> pd.DataFrame:
    """Weekly return, volume z-score, dollar volume, raw volume and forward
    1/2/4/8-week drift."""
    df = df[["Close", "Volume"]].dropna()  # guard against union-index NaN padding
    out = pd.DataFrame(index=df.index)
    close = df["Close"].astype(float)
    vol = df["Volume"].astype(float)

    out["ret"] = close.pct_change(fill_method=None)
    out["vol"] = vol
    out["dollar_vol"] = close * vol

    roll_mean = vol.rolling(52, min_periods=26).mean()
    roll_std = vol.rolling(52, min_periods=26).std()
    out["vol_z"] = ((vol - roll_mean) / roll_std).replace([np.inf, -np.inf], np.nan)

    # forward cumulative returns measured *after* the current week
    for h in (1, 2, 4, 8):
        out[f"fwd{h}"] = close.shift(-h) / close - 1.0

    out["woy"] = df.index.isocalendar().week.astype(int).values
    out["year"] = df.index.year
    return out.dropna(subset=["ret"])


def asset_aggregates(feats: pd.DataFrame) -> dict:
    """Whole-history baselines an asset's buckets are compared against."""
    r = feats["ret"].to_numpy()
    return {
        "ret_std": float(np.std(r, ddof=1)) if len(r) > 1 else np.nan,
        "vol_mean": float(feats["vol"].mean()),
        "dollar_vol_mean": float(feats["dollar_vol"].mean()),
    }


# --------------------------------------------------------------------------- #
# Bucket metrics (one week-of-year, one asset)
# --------------------------------------------------------------------------- #
def _safe(x):
    return float(x) if np.isfinite(x) else np.nan


def bucket_metrics(g: pd.DataFrame, agg: dict) -> dict:
    """Full catalog of seasonal-state measures for one asset / week-of-year."""
    g = g.sort_values("year")
    r = g["ret"].to_numpy()
    vz = g["vol_z"].fillna(0).to_numpy()
    vol = g["vol"].to_numpy()
    dv = g["dollar_vol"].to_numpy()
    fwd4 = g["fwd4"].to_numpy()
    n = len(r)
    m: dict[str, float] = {"n": n}

    mean = float(np.mean(r))
    std = float(np.std(r, ddof=1)) if n > 1 else np.nan

    # ---- return quality -------------------------------------------------- #
    m["mean_ret"] = _safe(mean)
    m["median_ret"] = _safe(np.median(r))
    m["std_ret"] = _safe(std)
    m["sharpe"] = _safe(mean / std) if std and std > 0 else np.nan
    m["win_rate"] = _safe(np.mean(r > 0))
    m["positive_median"] = 1.0 if np.median(r) > 0 else 0.0
    mad = np.median(np.abs(r - np.median(r)))
    m["robust_sharpe"] = _safe(np.median(r) / mad) if mad > 0 else np.nan
    downside = r[r < 0]
    dd = np.sqrt(np.mean(downside ** 2)) if downside.size else np.nan
    m["downside_dev"] = _safe(dd)
    m["sortino"] = _safe(mean / dd) if dd and dd > 0 else np.nan
    m["t_stat"] = _safe(mean / (std / np.sqrt(n))) if std and std > 0 and n > 1 else np.nan

    # ---- payoff asymmetry ------------------------------------------------ #
    pos, neg = r[r > 0].sum(), -r[r < 0].sum()
    m["gain_to_pain"] = _safe(pos / neg) if neg > 0 else (np.nan if pos == 0 else 10.0)
    m["worst"] = _safe(np.min(r))
    m["best"] = _safe(np.max(r))
    m["skew"] = _safe(pd.Series(r).skew()) if n >= 3 else np.nan
    m["kurtosis"] = _safe(pd.Series(r).kurt()) if n >= 4 else np.nan
    if n >= 5:
        hi = r[r >= np.quantile(r, 0.8)]
        lo = r[r <= np.quantile(r, 0.2)]
        m["tail_ratio"] = _safe(np.mean(hi) / abs(np.mean(lo))) if np.mean(lo) < 0 else np.nan
        # expected-shortfall ratio: mean upside tail / |mean downside tail|
        m["es_ratio"] = _safe(np.mean(hi) / abs(np.mean(lo))) if np.mean(lo) < 0 else np.nan
    else:
        m["tail_ratio"] = m["es_ratio"] = np.nan
    # max drawdown of the equity curve formed by bucket returns ordered by year
    eq = np.cumprod(1 + r)
    m["max_drawdown"] = _safe(float(np.min(eq / np.maximum.accumulate(eq) - 1)))

    # ---- volume confirmation -------------------------------------------- #
    rel = vol / agg["vol_mean"] if agg.get("vol_mean") else np.full(n, np.nan)
    m["rel_volume"] = _safe(np.nanmean(rel))                 # in-window / overall
    m["vol_z_mean"] = _safe(np.mean(vz))
    m["vol_elevated_rate"] = _safe(np.mean(vz > 0))
    m["ret_x_vol"] = _safe(np.mean(r * vz))
    acc = np.mean(np.maximum(r, 0) * vz)
    dist = np.mean(np.abs(np.minimum(r, 0)) * vz)
    m["accumulation"] = _safe(acc)
    m["distribution"] = _safe(dist)
    m["net_accumulation"] = _safe(acc - dist)
    w = np.maximum(vz, 0)
    va_pos = np.sum(np.maximum(r, 0) * w)
    va_neg = -np.sum(np.minimum(r, 0) * w)
    m["va_gpr"] = _safe(va_pos / va_neg) if va_neg > 0 else (np.nan if va_pos == 0 else 10.0)
    # volume-confirmed Sharpe: mean(ret x log(1+rel_vol)) / std
    m["vc_sharpe"] = _safe(np.mean(r * np.log1p(np.clip(rel, 0, None))) / std) if std and std > 0 else np.nan
    up_v, dn_v = vol[r > 0].sum(), vol[r < 0].sum()
    m["up_down_vol_ratio"] = _safe(up_v / dn_v) if dn_v > 0 else (np.nan if up_v == 0 else 10.0)
    m["vol_concentration"] = _safe(np.max(vol) / np.sum(vol)) if np.sum(vol) > 0 else np.nan

    # ---- volatility state ------------------------------------------------ #
    m["realized_vol_anomaly"] = _safe(std / agg["ret_std"]) if agg.get("ret_std") else np.nan
    up_r, dn_r = r[r > 0], r[r < 0]
    uv = np.std(up_r) if up_r.size > 1 else np.nan
    dv_ = np.std(dn_r) if dn_r.size > 1 else np.nan
    m["upside_vol"] = _safe(uv)
    m["downside_vol"] = _safe(dv_)
    m["vol_asymmetry"] = _safe(uv / dv_) if dv_ and dv_ > 0 else np.nan
    up_semi = np.mean(np.maximum(r, 0) ** 2)
    dn_semi = np.mean(np.minimum(r, 0) ** 2)
    m["semivar_delta"] = _safe(dn_semi - up_semi)

    # ---- liquidity ------------------------------------------------------- #
    m["dollar_vol"] = _safe(np.median(dv))
    m["liquidity_adj_return"] = _safe(mean * np.log1p(np.median(dv)))

    # ---- forward effect / persistence ------------------------------------ #
    for h in (1, 2, 4, 8):
        f = g[f"fwd{h}"].dropna().to_numpy()
        m[f"fwd{h}"] = _safe(np.mean(f)) if f.size else np.nan
    m["persistence"] = m["fwd4"]
    mask = ~np.isnan(fwd4)
    if mask.sum() >= 4 and np.std(r[mask]) > 0 and np.std(fwd4[mask]) > 0:
        m["persistence_corr"] = _safe(float(np.corrcoef(r[mask], fwd4[mask])[0, 1]))
    else:
        m["persistence_corr"] = np.nan
    up_years = mask & (r > 0)
    m["trend_continuation_rate"] = _safe(np.mean(fwd4[up_years] > 0)) if up_years.sum() else np.nan

    # ---- reliability / anti-overfitting ---------------------------------- #
    k = min(3, n // 2)
    if k >= 2 and mean != 0:
        chunks = np.array_split(r, k)
        m["stability"] = _safe(np.mean([np.sign(np.mean(c)) == np.sign(mean) for c in chunks]))
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

    # cross-sectional volatility compression score (low realized-vol = high)
    df["compression_score"] = -_z(df["realized_vol_anomaly"].fillna(df["realized_vol_anomaly"].median()))
    # reliability blend: z(t)+z(win)+z(GPR) - z(maxDD magnitude)
    df["reliability_score"] = (
        _z(df["t_stat"].fillna(0))
        + _z(df["win_rate"].fillna(0))
        + _z(df["va_gpr"].clip(upper=10).fillna(0))
        - _z((-df["max_drawdown"]).fillna(0))
    )
    return df


# --------------------------------------------------------------------------- #
# Pipeline
# --------------------------------------------------------------------------- #
def run(args) -> None:
    universe = get_universe(limit=args.limit, source=args.universe)
    symbols = universe["symbol"].tolist()
    sector_map = dict(zip(universe["symbol"], universe["sector"]))
    name_map = dict(zip(universe["symbol"], universe["security"]))

    frames = download_weekly(symbols, years=args.years, refresh=args.refresh)
    if not frames:
        print("No data downloaded — aborting.")
        sys.exit(1)

    # derive the reference week from the latest *completed* bar in the data, not a
    # hardcoded date (which silently scans the wrong week as time passes)
    if args.target_week:
        target = args.target_week
        ref = "explicit"
    elif args.today:
        target = pd.Timestamp(args.today).isocalendar().week
        ref = args.today
    else:
        last = max(df.dropna().index[-1] for df in frames.values())
        target = int(pd.Timestamp(last).isocalendar().week)
        ref = f"data max {pd.Timestamp(last).date()}"
    print(f"\n[scan] target week-of-year = {target}  (ref: {ref}; "
          f"min {args.min_years} yrs of history per bucket)\n")

    rows = []
    for sym, df in frames.items():
        feats = build_features(df)
        g = feats[feats["woy"] == target]
        if len(g) < args.min_years:
            continue
        m = bucket_metrics(g, asset_aggregates(feats))
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

    def extended(title, t):
        print(f"\n{'-'*116}\n{title} — extended measures\n{'-'*116}")
        hdr = (f"{'Sym':<7}{'Sortino':>8}{'RobShrp':>8}{'t':>6}{'VCShrp':>7}{'TailR':>7}"
               f"{'Skew':>6}{'RVolAnom':>9}{'VolAsym':>8}{'UpDnVol':>8}{'PrsCorr':>8}"
               f"{'TrndCnt':>8}{'Reliab':>7}{'Compr':>7}")
        print(hdr)
        for _, r in t.iterrows():
            def g(k):
                return r[k] if pd.notna(r[k]) else float("nan")
            print(
                f"{r['symbol']:<7}{g('sortino'):>8.2f}{g('robust_sharpe'):>8.2f}{g('t_stat'):>6.2f}"
                f"{g('vc_sharpe'):>7.2f}{g('tail_ratio'):>7.2f}{g('skew'):>6.2f}"
                f"{g('realized_vol_anomaly'):>9.2f}{g('vol_asymmetry'):>8.2f}"
                f"{min(g('up_down_vol_ratio'),10):>8.2f}{g('persistence_corr'):>8.2f}"
                f"{g('trend_continuation_rate'):>8.2f}{g('reliability_score'):>7.2f}"
                f"{g('compression_score'):>7.2f}"
            )

    print(f"\n###  Week-of-Year {week} seasonal anomalies  ###")
    print(f"###  {len(df)} names had >= min history this week.  "
          f"Composite = 0.30 z(tradable Sharpe) + 0.25 z(VA gain/pain) + 0.20 z(net "
          f"accumulation) + 0.15 z(persistence) + 0.10 z(liquidity).")
    print("###  Full catalog (58 measures) in the CSV: return quality, payoff asymmetry, "
          "volume confirmation, volatility state, liquidity, forward/persistence, reliability.")
    block(f"TOP {len(longs)} BULLISH seasonal anomalies (LONG)", longs)
    extended("BULLISH", longs)
    block(f"TOP {len(shorts)} BEARISH seasonal anomalies (SHORT)", shorts)
    extended("BEARISH", shorts)


def parse_args():
    p = argparse.ArgumentParser(description="S&P MidCap 400 weekly seasonal anomaly scanner")
    p.add_argument("--universe", choices=["sp400", *CAP_SOURCES.keys()], default="sp400",
                   help="sp400 = S&P 400 (Wikipedia); us-<bucket> = financedatabase "
                        "market-cap buckets (e.g. us-midcap, us-smallcap, us-microcap, "
                        "us-smallmicro, us-allcap)")
    p.add_argument("--limit", type=int, default=None, help="cap universe size (testing)")
    p.add_argument("--years", type=int, default=20, help="years of weekly history")
    p.add_argument("--target-week", type=int, default=None, help="ISO week-of-year to scan")
    p.add_argument("--today", default=None,
                   help="reference date for current week (default: derive from data's latest bar)")
    p.add_argument("--min-years", type=int, default=8, help="min historical obs per bucket")
    p.add_argument("--top", type=int, default=25, help="rows per direction to print")
    p.add_argument("--csv", default=None, help="optional path to write full table")
    p.add_argument("--refresh", action="store_true", help="ignore cache, re-download")
    return p.parse_args()


if __name__ == "__main__":
    run(parse_args())
