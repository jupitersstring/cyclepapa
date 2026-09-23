"""
Long-horizon trend cross screen.

For each ticker:
- resample daily closes to 6-month (semi-annual) bars,
- compute a 20-period MA (fast) on those bars,
- compute a 40-period Hull MA AND a 40-period SMA (slow) on those bars,
- find names where the fast MA crossed ABOVE the slow MA in the last N
  6-month bars. More recent crosses score higher.

20 periods of 6m = 10 years; 40 periods of 6m = 20 years. Tickers without
~23 years of price history are silently dropped.

Usage: python3 cross_6m.py [us|europe|uk] [N=8]
"""

import sys
import warnings

import numpy as np
import pandas as pd
import yfinance as yf

from screen import REGIONS, fetch_universe, currency_for_ticker, fetch_fx

warnings.filterwarnings("ignore")

DEFAULT_LOOKBACK_BARS = 8  # last 8 six-month bars = ~4 years


def wma(series: pd.Series, n: int) -> pd.Series:
    weights = np.arange(1, n + 1, dtype=float)
    weights /= weights.sum()
    return series.rolling(n).apply(lambda x: float(np.dot(x, weights)), raw=True)


def hma(series: pd.Series, n: int) -> pd.Series:
    half = wma(series, max(2, n // 2))
    full = wma(series, n)
    raw = 2 * half - full
    return wma(raw, max(2, int(round(np.sqrt(n)))))


def find_cross(close_6m: pd.Series, n_fast: int = 20, n_slow: int = 40,
               lookback: int = DEFAULT_LOOKBACK_BARS) -> dict | None:
    if len(close_6m) < n_slow + lookback + 5:
        return None
    ma_fast = close_6m.rolling(n_fast).mean()
    hma_slow = hma(close_6m, n_slow)
    sma_slow = close_6m.rolling(n_slow).mean()
    valid = pd.DataFrame({
        "fast": ma_fast, "slow_hma": hma_slow, "slow_sma": sma_slow
    }).dropna()
    if len(valid) < lookback + 2:
        return None
    win = valid.iloc[-(lookback + 1):]
    above_hma = win["fast"] > win["slow_hma"]
    above_sma = win["fast"] > win["slow_sma"]
    cross_hma_idx = cross_sma_idx = None
    for i in range(1, len(win)):
        if not above_hma.iloc[i - 1] and above_hma.iloc[i]:
            cross_hma_idx = i
        if not above_sma.iloc[i - 1] and above_sma.iloc[i]:
            cross_sma_idx = i

    def bars_ago(idx):
        return (len(win) - 1 - idx) if idx is not None else None

    return dict(
        n_bars=int(len(close_6m)),
        last_date=str(close_6m.index[-1].date()),
        cross_hma_bars_ago=bars_ago(cross_hma_idx),
        cross_sma_bars_ago=bars_ago(cross_sma_idx),
        above_hma_now=bool(above_hma.iloc[-1]),
        above_sma_now=bool(above_sma.iloc[-1]),
        fast_now=float(win["fast"].iloc[-1]),
        hma_now=float(win["slow_hma"].iloc[-1]),
        sma_now=float(win["slow_sma"].iloc[-1]),
        ratio_fast_hma=float(win["fast"].iloc[-1] / win["slow_hma"].iloc[-1] - 1),
        ratio_fast_sma=float(win["fast"].iloc[-1] / win["slow_sma"].iloc[-1] - 1),
    )


def fetch_max_closes(tickers: list[str], chunk: int = 80) -> pd.DataFrame:
    out = {}
    for i in range(0, len(tickers), chunk):
        sub = tickers[i:i + chunk]
        print(f"  fetching {i}..{i+len(sub)} of {len(tickers)}", file=sys.stderr)
        raw = yf.download(sub, period="max", interval="1d",
                          auto_adjust=True, progress=False, threads=True,
                          group_by="column")
        close = raw["Close"] if isinstance(raw.columns, pd.MultiIndex) else \
            pd.DataFrame({sub[0]: raw["Close"]})
        for t in close.columns:
            s = close[t].dropna()
            if not s.empty:
                out[t] = s
    return pd.DataFrame(out)


def main() -> None:
    region = (sys.argv[1] if len(sys.argv) > 1 else "europe").lower()
    lookback = int(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT_LOOKBACK_BARS

    universe, _ = fetch_universe(region)
    print(f"\n>>> Region: {region}; universe: {len(universe)} tickers; lookback: {lookback} 6m bars\n", file=sys.stderr)

    closes = fetch_max_closes(universe)
    print(f"\nClosing-price coverage: {closes.shape[1]} tickers with any history.", file=sys.stderr)

    rows = []
    for t in closes.columns:
        s = closes[t].dropna()
        sa = s.resample("2QE").last().dropna()  # semi-annual (every 6 months) bars
        info = find_cross(sa, n_fast=20, n_slow=40, lookback=lookback)
        if info is None:
            continue
        info["ticker"] = t
        info["years_history"] = round(info["n_bars"] / 2, 1)
        # Recency-weighted score: more recent cross = higher.
        # cross_hma_bars_ago in [0..lookback]; None = no cross in window.
        def recency(ba):
            return (lookback - ba) if ba is not None else -100
        info["score_hma"] = recency(info["cross_hma_bars_ago"]) + info["ratio_fast_hma"] * 5
        info["score_sma"] = recency(info["cross_sma_bars_ago"]) + info["ratio_fast_sma"] * 5
        info["score_any"] = max(info["score_hma"], info["score_sma"])
        rows.append(info)

    if not rows:
        print("No tickers had enough history (>= ~23 years).")
        return

    df = pd.DataFrame(rows)
    print(f"\nTickers with sufficient 6m-bar history: {len(df)}")
    print(f"  with HMA cross in last {lookback} bars: {df.cross_hma_bars_ago.notna().sum()}")
    print(f"  with SMA cross in last {lookback} bars: {df.cross_sma_bars_ago.notna().sum()}")
    print(f"  with either cross:                       "
          f"{(df.cross_hma_bars_ago.notna() | df.cross_sma_bars_ago.notna()).sum()}")

    hits = df[(df.cross_hma_bars_ago.notna()) | (df.cross_sma_bars_ago.notna())].copy()
    hits = hits.sort_values("score_any", ascending=False)

    cols = ["ticker", "years_history", "last_date",
            "cross_hma_bars_ago", "cross_sma_bars_ago",
            "above_hma_now", "above_sma_now",
            "ratio_fast_hma", "ratio_fast_sma",
            "score_hma", "score_sma", "score_any"]
    print(f"\n=== Tickers with recent 6m-bar fast/slow cross (ranked by recency) ===")
    print(hits[cols].head(40).to_string(index=False, float_format=lambda x: f"{x:.3f}"))


if __name__ == "__main__":
    main()
