"""Recompute DSR (Downside Resilience) for every ticker using its
REGIONAL benchmark ETF instead of SPY globally.

Root cause of the original bias: comparing a Japanese stock's same-date
return to SPY's same-date return is timezone-misaligned (JST trades
before NYSE), so JP rows looked artificially resilient on SPY-down days.
US-listed regional ETFs (EWJ for Japan, EWY for Korea, FXI for China,
INDA for India, EWA for Australia, EWG for Germany, etc.) trade in NY
hours -> timestamp aligns -> the lag artifact disappears.

This script:
  1. Fetches all unique benchmark ETFs once
  2. For each region CSV, computes DSR ticker-by-ticker against the
     appropriate benchmark (no re-fetch of OHLC — uses the existing
     adv_20/M/E columns as evidence the row was already augmented).

Only DSR-related columns are rewritten; E, ADV, M are untouched.
"""

import sys
import glob
import time
import warnings
import subprocess

import numpy as np
import pandas as pd
import yfinance as yf

sys.path.insert(0, "/home/user/cyclepapa")
from screen import fetch_ohlc
from minervini_leg import downside_resilience
from regional_benchmarks import benchmark_for_ticker, unique_benchmarks

warnings.filterwarnings("ignore")

DSR_COLS = ["DSR", "downside_capture", "market_corr",
            "n_drawdown_days", "stock_ret_drawdown_pct",
            "mkt_ret_drawdown_pct"]


def fetch_benchmark(symbol: str, period="18mo"):
    try:
        raw = yf.download(symbol, period=period, interval="1d",
                          auto_adjust=True, progress=False, threads=False)
        if raw.empty:
            return None
        close = raw["Close"]
        if isinstance(close, pd.DataFrame):
            close = close.iloc[:, 0]
        return close
    except Exception as e:
        print(f"  benchmark {symbol}: {e}", file=sys.stderr)
        return None


def fix_region(csv_path: str, benchmarks: dict):
    df = pd.read_csv(csv_path)
    region = csv_path.split("stars_aligned_")[-1].replace(".csv", "")

    # Need OHLC for the stocks again — we don't have it cached.
    tickers = df["ticker"].astype(str).tolist()
    print(f"  {region}: refetching OHLC for {len(tickers)} tickers", file=sys.stderr)

    daily = fetch_ohlc(tickers, period="18mo",
                       chunk=80, retries=4, pause_between_chunks=0.7)
    closes = daily.get("Close")
    if closes is None or closes.empty:
        print(f"  {region}: no Close data", file=sys.stderr)
        return False
    have = set(closes.columns)
    print(f"  {region}: fetched {len(have)}/{len(tickers)}", file=sys.stderr)

    # Recompute DSR per ticker using REGIONAL benchmark
    new_vals = {c: df[c].copy() if c in df.columns else pd.Series([np.nan] * len(df))
                for c in DSR_COLS}
    for col in DSR_COLS:
        if col not in df.columns:
            df[col] = np.nan
            new_vals[col] = df[col].copy()

    for i, t in enumerate(tickers):
        if t not in have:
            continue
        try:
            bench_sym = benchmark_for_ticker(t)
            bench_close = benchmarks.get(bench_sym)
            if bench_close is None:
                # fallback to SPY if regional benchmark failed to fetch
                bench_close = benchmarks.get('SPY')
                if bench_close is None:
                    continue
            stock_close = closes[t].dropna()
            if len(stock_close) < 60:
                continue
            bars = pd.DataFrame({"Close": stock_close})
            d = downside_resilience(bars, bench_close) or {}
            idx = df.index[df.ticker == t]
            for col in DSR_COLS:
                if col in d:
                    new_vals[col].loc[idx] = d.get(col)
        except Exception:
            continue
        if (i + 1) % 1000 == 0:
            print(f"    DSR-fix scored {i+1}/{len(tickers)}", file=sys.stderr)

    for col in DSR_COLS:
        df[col] = new_vals[col]
    df.to_csv(csv_path, index=False)
    print(f"  {region}: wrote {len(df)} rows", file=sys.stderr)
    return True


def main():
    benchmark_symbols = sorted(unique_benchmarks())
    print(f"Fetching {len(benchmark_symbols)} regional benchmark ETFs...",
          file=sys.stderr)
    benchmarks = {}
    for sym in benchmark_symbols:
        b = fetch_benchmark(sym)
        if b is not None:
            benchmarks[sym] = b
            print(f"  {sym}: {len(b)} bars", file=sys.stderr)
        else:
            print(f"  {sym}: FAILED (will fall back to SPY for those tickers)",
                  file=sys.stderr)

    if 'SPY' not in benchmarks:
        print("Could not fetch SPY fallback. Aborting.", file=sys.stderr)
        return

    csvs = sorted(glob.glob("/tmp/stars_aligned_*.csv"))
    print(f"Fixing DSR with regional benchmarks across {len(csvs)} regions",
          file=sys.stderr)
    for p in csvs:
        try:
            fix_region(p, benchmarks)
            # Persist after each region (best-effort)
            try:
                subprocess.run(
                    ["python", "/home/user/cyclepapa/persist_results.py", "--no-push"],
                    check=False, timeout=120,
                )
            except Exception as e:
                print(f"  persist warning: {e}", file=sys.stderr)
        except Exception as e:
            print(f"  {p}: error {e}", file=sys.stderr)
        time.sleep(2)

    # Final push
    try:
        subprocess.run(
            ["python", "/home/user/cyclepapa/persist_results.py"],
            check=False, timeout=300,
        )
    except Exception as e:
        print(f"  final persist warning: {e}", file=sys.stderr)
    print("DSR regional fix complete.")


if __name__ == "__main__":
    main()
