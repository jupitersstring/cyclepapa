"""
Crypto weekly seasonality / calendar-anomaly screener.

For every symbol in the universe (Revolut + top-100 by mcap), pull max
weekly history from yfinance, compute per-week-of-year metrics
(Sharpe / Sortino / GPR / VA-Sharpe / VA-GPR / Net Accumulation /
Persistence / Liquidity / sample-penalty / stability), then build the
cross-sectional composite anomaly score for the CURRENT week-of-year.

Output: long-bias and short-bias rankings.
"""

from __future__ import annotations

import os
import pickle
import time

import pandas as pd
import yfinance as yf

from crypto_universe import revolut_universe, top_yf_cryptos_by_mcap
import seasonality as sn


CACHE_DIR = ".cache/seasonality"
CACHE_TTL_HOURS = 24


def _cache_path(syms, period, interval):
    import hashlib
    key = hashlib.sha1(("|".join(sorted(syms)) + f"|{period}|{interval}").encode()).hexdigest()[:12]
    return os.path.join(CACHE_DIR, f"{interval}_{period}_{key}.pkl")


def _bulk_weekly(syms, period="max"):
    os.makedirs(CACHE_DIR, exist_ok=True)
    cp = _cache_path(syms, period, "1wk")
    if os.path.exists(cp) and (time.time() - os.path.getmtime(cp)) < CACHE_TTL_HOURS * 3600:
        with open(cp, "rb") as f:
            print(f"  cache hit  weekly  ->  loaded from {cp}")
            return pickle.load(f)
    print(f"  fetching weekly bars ({period}, {len(syms)} symbols)...")
    data = yf.download(" ".join(syms), period=period, interval="1wk",
                       group_by="ticker", auto_adjust=False, progress=False, threads=True)
    with open(cp, "wb") as f:
        pickle.dump(data, f, protocol=pickle.HIGHEST_PROTOCOL)
    return data


def main() -> None:
    seen, syms = set(), []
    for src in (revolut_universe(), top_yf_cryptos_by_mcap(100)):
        for s in src:
            if s not in seen:
                seen.add(s); syms.append(s)
    print(f"Crypto universe: {len(syms)} symbols")

    data = _bulk_weekly(syms, period="max")

    print("Computing per-symbol weekly metrics...")
    per_asset = {}
    for sym in syms:
        try:
            sub = data[sym].dropna(how="all")
            if sub.empty:
                continue
            sub = sub.rename(columns={c: c.lower() for c in sub.columns})
            metrics = sn.weekly_metrics(sub)
            if not metrics.empty:
                per_asset[sym] = metrics
        except (KeyError, ValueError):
            continue
    print(f"  computed for {len(per_asset)} symbols")

    current_week = sn.current_week_of_year()
    print(f"\nCurrent week of year: {current_week}")

    long_rank = sn.composite_for_week(per_asset, current_week)
    short_rank = sn.composite_for_week(per_asset, current_week, invert_for_short=True)

    long_rank.to_csv("seasonality_long.csv")
    short_rank.to_csv("seasonality_short.csv")

    pd.set_option("display.width", 220)
    pd.set_option("display.max_columns", None)
    show = [
        "composite", "tradable_sharpe", "va_gpr_capped", "net_accumulation",
        "persistence_4w", "liquidity_pct", "n_obs", "win_rate",
        "mean_return", "sharpe", "sortino", "stability", "sample_penalty",
    ]
    show = [c for c in show if c in long_rank.columns]

    print(f"\n=== Top 25 long-bias crypto seasonal anomalies (week {current_week}) ===")
    print(long_rank.head(25)[show].to_string(float_format=lambda x: f"{x:.3f}"))

    print(f"\n=== Top 15 short-bias (worst long-anomaly stocks; invert for shorts) ===")
    print(short_rank.head(15)[show].to_string(float_format=lambda x: f"{x:.3f}"))


if __name__ == "__main__":
    main()
