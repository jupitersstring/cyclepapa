"""
Batch-screen the crypto universe across MR + Trend.

Fetches all symbols at each timeframe in a single yfinance call (bulk
download), then runs the per-symbol MR rank and per-symbol Trend score.
Saves the full ranked table to CSV and prints the top picks.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import pickle
import sys
import time
from typing import Dict, List, Optional, Tuple

import pandas as pd
import yfinance as yf


CACHE_DIR = os.environ.get("CYCLEPAPA_CACHE", ".cache/universe")
# Default cache TTL by interval label (seconds). Intraday data goes stale
# fast; daily / weekly / monthly can be reused for hours.
CACHE_TTL = {
    "1m":  10 * 60,
    "5m":  20 * 60,
    "15m": 30 * 60,
    "1h":  60 * 60,
    "4h":  60 * 60,
    "1d":   6 * 60 * 60,
    "1w":  24 * 60 * 60,
    "1mo": 24 * 60 * 60,
}


def _cache_key(symbols: List[str], label: str, interval: str, period: str) -> str:
    h = hashlib.sha1(("|".join(sorted(symbols)) + f"|{interval}|{period}").encode()).hexdigest()[:12]
    return f"{label}_{interval}_{h}.pkl"


def _cache_load(symbols: List[str], label: str, interval: str, period: str) -> Optional[Dict[str, pd.DataFrame]]:
    path = os.path.join(CACHE_DIR, _cache_key(symbols, label, interval, period))
    if not os.path.exists(path):
        return None
    age = time.time() - os.path.getmtime(path)
    ttl = CACHE_TTL.get(label, 60 * 60)
    if age > ttl:
        return None
    try:
        with open(path, "rb") as f:
            return pickle.load(f)
    except Exception:
        return None


def _cache_save(symbols: List[str], label: str, interval: str, period: str,
                data: Dict[str, pd.DataFrame]) -> None:
    os.makedirs(CACHE_DIR, exist_ok=True)
    path = os.path.join(CACHE_DIR, _cache_key(symbols, label, interval, period))
    try:
        with open(path, "wb") as f:
            pickle.dump(data, f, protocol=pickle.HIGHEST_PROTOCOL)
    except Exception:
        pass

from crypto_universe import (
    revolut_universe, top_yf_cryptos_by_mcap, top_yf_cryptos_by_volume,
)
from mr_engine import (
    _YF_PERIOD_FOR_INTERVAL, _normalise_ohlcv,
    td_sequential, aggregate_across_tfs,
)
from trend_engine import trend_score, make_relative


DEFAULT_TIMEFRAMES: List[Tuple[str, str]] = [
    ("1h",  "60m"),
    ("4h",  "4h"),    # resampled from 60m
    ("1d",  "1d"),
    ("1w",  "1wk"),
    ("1mo", "1mo"),
]


def _bulk_download(symbols: List[str], interval: str, period: str) -> Dict[str, pd.DataFrame]:
    """Bulk-fetch many tickers at one interval via a single yfinance call."""
    if not symbols:
        return {}
    tickers_str = " ".join(symbols)
    data = yf.download(
        tickers_str, period=period, interval=interval,
        group_by="ticker", auto_adjust=False, progress=False, threads=True,
    )
    out: Dict[str, pd.DataFrame] = {}
    if data is None or data.empty:
        return out
    if isinstance(data.columns, pd.MultiIndex):
        for sym in symbols:
            if sym not in data.columns.get_level_values(0):
                continue
            try:
                sub = data[sym].dropna(how="all")
            except KeyError:
                continue
            if sub.empty:
                continue
            try:
                out[sym] = _normalise_ohlcv(sub)
            except Exception:
                continue
    else:
        # Single ticker case
        try:
            out[symbols[0]] = _normalise_ohlcv(data)
        except Exception:
            pass
    return out


def _fetch_with_cache(symbols: List[str], label: str, interval: str) -> Dict[str, pd.DataFrame]:
    period = _YF_PERIOD_FOR_INTERVAL.get(interval, "max")
    cached = _cache_load(symbols, label, interval, period)
    if cached is not None:
        print(f"  cache hit  {label} ({interval})  ->  {len(cached)} symbols")
        return cached
    data = _bulk_download(symbols, interval, period)
    _cache_save(symbols, label, interval, period, data)
    return data


def fetch_universe_mtf(symbols: List[str], timeframes: List[Tuple[str, str]]) -> Dict[str, Dict[str, pd.DataFrame]]:
    """
    Returns {tf_label: {symbol: ohlcv_df}}. Uses bulk yfinance downloads
    cached on disk per (symbols, interval). 4h is resampled from 60m.
    """
    per_tf: Dict[str, Dict[str, pd.DataFrame]] = {}
    cached_60m: Optional[Dict[str, pd.DataFrame]] = None
    for label, interval in timeframes:
        t0 = time.time()
        if label == "4h":
            if cached_60m is None:
                cached_60m = _fetch_with_cache(symbols, "1h_for_4h", "60m")
            resampled = {}
            for sym, df in cached_60m.items():
                r = df.resample("4h").agg({
                    "open": "first", "high": "max", "low": "min",
                    "close": "last", "volume": "sum",
                }).dropna()
                if len(r) >= 30:
                    resampled[sym] = r
            per_tf[label] = resampled
            print(f"  resampled {label}  ->  {len(per_tf[label])} symbols   [{time.time()-t0:.1f}s]")
        else:
            data = _fetch_with_cache(symbols, label, interval)
            if interval == "60m" and cached_60m is None:
                cached_60m = data
            per_tf[label] = {s: d for s, d in data.items() if len(d) >= 30}
            print(f"  fetched   {label} ({interval})  ->  {len(per_tf[label])} symbols   [{time.time()-t0:.1f}s]")
    return per_tf


def score_universe(symbols: List[str], per_tf: Dict[str, Dict[str, pd.DataFrame]],
                   rel_weight: float = 0.5) -> pd.DataFrame:
    """Run MR + Trend on each symbol and return a ranked DataFrame."""
    btc_per_tf = {tf: per_tf[tf]["BTC-USD"] for tf in per_tf if "BTC-USD" in per_tf[tf]}
    rows = []
    for sym in symbols:
        sym_tfs = {tf: per_tf[tf][sym] for tf in per_tf if sym in per_tf[tf] and len(per_tf[tf][sym]) >= 60}
        if not sym_tfs:
            rows.append({"symbol": sym, "status": "no_data"})
            continue

        # Trend (absolute)
        abs_scores = {tf: trend_score(df) for tf, df in sym_tfs.items()}
        abs_net = sum(s.net for s in abs_scores.values()) / len(abs_scores)
        abs_long = sum(s.long_score for s in abs_scores.values()) / len(abs_scores)
        abs_short = sum(s.short_score for s in abs_scores.values()) / len(abs_scores)

        # Trend (BTC-relative)
        rel_scores: Dict[str, object] = {}
        if sym.upper() != "BTC-USD":
            for tf, df in sym_tfs.items():
                if tf in btc_per_tf:
                    rel = make_relative(df, btc_per_tf[tf])
                    if rel is not None:
                        rel_scores[tf] = trend_score(rel)
        if rel_scores:
            rel_net = sum(s.net for s in rel_scores.values()) / len(rel_scores)
            rel_long = sum(s.long_score for s in rel_scores.values()) / len(rel_scores)
            rel_short = sum(s.short_score for s in rel_scores.values()) / len(rel_scores)
        else:
            rel_net = abs_net; rel_long = abs_long; rel_short = abs_short

        combined = rel_weight * rel_net + (1.0 - rel_weight) * abs_net

        # MR
        try:
            td_per = {tf: td_sequential(df) for tf, df in sym_tfs.items() if len(df) >= 50}
            mr = aggregate_across_tfs(td_per) if td_per else None
        except Exception:
            mr = None

        any_breakout = any(s.flags.get("breakout_20") for s in abs_scores.values())
        any_ep       = any(s.flags.get("ep_signal") for s in abs_scores.values())
        any_release  = any(s.sr.get("release_after_squeeze_window") for s in abs_scores.values())
        any_va_attr  = any(s.volasym.get("above_ma") and s.volasym.get("rising") and s.volasym.get("in_band")
                            for s in abs_scores.values())
        any_parabolic = any(s.qm.get("parabolic_extended") for s in abs_scores.values())
        bull_infl_tfs = sum(int(s.flags.get("inflection_bull", False)) for s in abs_scores.values())
        bear_infl_tfs = sum(int(s.flags.get("inflection_bear", False)) for s in abs_scores.values())

        rows.append({
            "symbol": sym,
            "status": "ok",
            "trend_combined": combined,
            "trend_abs": abs_net,
            "trend_rel_btc": rel_net,
            "trend_abs_long": abs_long,
            "trend_abs_short": abs_short,
            "trend_rel_long": rel_long,
            "trend_rel_short": rel_short,
            "mr_net_signal": mr.net_signal if mr else None,
            "mr_net_divergence": mr.net["divergence"] if mr else None,
            "mr_net_setup": mr.net["setup"] if mr else None,
            "mr_net_countdown": mr.net["countdown"] if mr else None,
            "breakout": any_breakout,
            "ep": any_ep,
            "release_after_squeeze": any_release,
            "volasym_attractive": any_va_attr,
            "parabolic_extended": any_parabolic,
            "inflection_bull_tfs": bull_infl_tfs,
            "inflection_bear_tfs": bear_infl_tfs,
            "n_tfs": len(abs_scores),
        })
    return pd.DataFrame(rows)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--source", choices=["revolut", "mcap", "volume", "combined", "revolut_mcap"],
                   default="revolut_mcap")
    p.add_argument("--n", type=int, default=100, help="top-N when source is mcap/volume/combined")
    p.add_argument("--rel-weight", type=float, default=0.5)
    p.add_argument("--out", default="universe_rank.csv")
    args = p.parse_args()

    print("== building universe ==")
    if args.source == "revolut":
        syms = revolut_universe()
    elif args.source == "mcap":
        syms = top_yf_cryptos_by_mcap(args.n)
    elif args.source == "volume":
        syms = top_yf_cryptos_by_volume(args.n)
    elif args.source == "revolut_mcap":
        seen, out = set(), []
        for src in (revolut_universe(), top_yf_cryptos_by_mcap(args.n)):
            for s in src:
                if s not in seen:
                    seen.add(s); out.append(s)
        syms = out
    else:
        seen, out = set(), []
        for src in (revolut_universe(),
                    top_yf_cryptos_by_mcap(args.n),
                    top_yf_cryptos_by_volume(args.n)):
            for s in src:
                if s not in seen:
                    seen.add(s); out.append(s)
        syms = out
    if "BTC-USD" not in syms:
        syms.insert(0, "BTC-USD")
    print(f"  {len(syms)} unique symbols")

    print("\n== bulk-fetching ==")
    per_tf = fetch_universe_mtf(syms, DEFAULT_TIMEFRAMES)

    print("\n== scoring ==")
    df = score_universe(syms, per_tf, rel_weight=args.rel_weight)
    ok = df[df["status"] == "ok"].copy()
    ok = ok.sort_values("trend_combined", ascending=False, na_position="last")
    df.to_csv(args.out, index=False)
    print(f"  wrote {args.out}  ({len(ok)} scored, {len(df)-len(ok)} no-data)")

    print("\n== top 25 by trend_combined ==")
    cols_top = ["symbol", "trend_combined", "trend_abs", "trend_rel_btc",
                "mr_net_signal", "mr_net_divergence",
                "breakout", "ep", "release_after_squeeze",
                "volasym_attractive", "inflection_bull_tfs", "inflection_bear_tfs"]
    print(ok.head(25)[cols_top].to_string(index=False))

    print("\n== bottom 10 by trend_combined (parabolic-short candidates) ==")
    print(ok.tail(10)[cols_top].to_string(index=False))

    return 0


if __name__ == "__main__":
    sys.exit(main())
