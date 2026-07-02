"""Force-refresh E, ADV, DSR for EVERY ticker with current prices.

Unlike backfill_universe.py (fills missing only), this recomputes all
three legs for all rows — used for periodic updates. DSR uses the
per-region benchmark ETF (regional_benchmarks.py), so this single pass
replaces backfill_universe.py + fix_dsr_regional.py.

Per-region: one OHLC fetch, all legs computed, CSV rewritten,
persist (commit, no push) after each region. Final push at end.
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
from minervini_leg import adv_metrics, downside_resilience, entry_now
from regional_benchmarks import benchmark_for_ticker, unique_benchmarks

warnings.filterwarnings("ignore")

E_COLS = ["E", "E_vol_spike", "E_pivot_break", "E_ret_acceleration",
          "E_behavior_shift", "E_close_strength", "E_coil_break",
          "E_ma_aligned", "E_bb_break", "E_new_high", "E_vol_ratio"]
ADV_COLS = ["ADV", "ADV_play_now", "adv_20", "adv_60",
            "adv_slope_pct_wk", "adv_accel_pct_wk",
            "adv_liq_score", "adv_slope_score", "adv_accel_score",
            "adv_turnover_score"]
DSR_COLS = ["DSR", "downside_capture", "market_corr",
            "n_drawdown_days", "stock_ret_drawdown_pct",
            "mkt_ret_drawdown_pct"]


def fetch_benchmarks(max_rounds=2, cooldown=120):
    """Fetch all benchmark ETFs, retrying rate-limited symbols with a
    cooldown between rounds. Yahoo rate limits typically clear in minutes."""
    out = {}
    remaining = sorted(unique_benchmarks())
    for round_no in range(max_rounds):
        if not remaining:
            break
        if round_no > 0:
            print(f"  benchmark retry round {round_no+1}: {len(remaining)} left; "
                  f"cooling down {cooldown}s...", file=sys.stderr)
            time.sleep(cooldown)
        still = []
        for sym in remaining:
            try:
                raw = yf.download(sym, period="18mo", interval="1d",
                                  auto_adjust=True, progress=False, threads=False)
                if raw.empty:
                    still.append(sym)
                    continue
                close = raw["Close"]
                if isinstance(close, pd.DataFrame):
                    close = close.iloc[:, 0]
                out[sym] = close
                print(f"  bench {sym}: {len(close)} bars", file=sys.stderr)
            except Exception as e:
                print(f"  bench {sym}: {e}", file=sys.stderr)
                still.append(sym)
            time.sleep(1.0)
        remaining = still
    if remaining:
        print(f"  benchmarks still missing after retries: {remaining}", file=sys.stderr)
    return out


DONE_FILE = "/tmp/refresh_legs_done.txt"


def _done_regions():
    try:
        with open(DONE_FILE) as f:
            return set(l.strip() for l in f if l.strip())
    except FileNotFoundError:
        return set()


def _mark_done(region):
    with open(DONE_FILE, "a") as f:
        f.write(region + "\n")


def refresh_region(csv_path: str, benchmarks: dict):
    df = pd.read_csv(csv_path, low_memory=False)
    region = csv_path.split("stars_aligned_")[-1].replace(".csv", "")
    if region in _done_regions():
        print(f"  {region}: already refreshed this run, skip", file=sys.stderr)
        return False

    for col in E_COLS + ADV_COLS + DSR_COLS:
        if col not in df.columns:
            df[col] = np.nan

    tickers = df["ticker"].astype(str).tolist()
    print(f"  {region}: refreshing ALL {len(tickers)} tickers", file=sys.stderr)

    daily = fetch_ohlc(tickers, period="18mo",
                       chunk=80, retries=4, pause_between_chunks=0.7)
    closes = daily.get("Close")
    if closes is None or closes.empty:
        print(f"  {region}: no Close data", file=sys.stderr)
        return False
    have = set(closes.columns)
    has_vol = "Volume" in daily.columns.get_level_values(0)
    print(f"  {region}: fetched {len(have)}/{len(tickers)}", file=sys.stderr)

    new_vals = {c: df[c].copy() for c in E_COLS + ADV_COLS + DSR_COLS}
    spy = benchmarks.get("SPY")

    for i, t in enumerate(tickers):
        if t not in have:
            continue
        try:
            bars = pd.DataFrame({
                "Open":   daily["Open"][t],
                "High":   daily["High"][t],
                "Low":    daily["Low"][t],
                "Close":  daily["Close"][t],
                "Volume": daily["Volume"][t] if has_vol else np.nan,
            }).dropna(subset=["Close"])
            if len(bars) < 60:
                continue
            idx = df.index[df.ticker == t]

            e = entry_now(bars) or {}
            for k in E_COLS:
                if k in e:
                    new_vals[k].loc[idx] = e[k]

            if has_vol:
                a = adv_metrics(bars) or {}
                for k in ADV_COLS:
                    if k in a:
                        new_vals[k].loc[idx] = a[k]

            bench = benchmarks.get(benchmark_for_ticker(t), spy)
            if bench is not None:
                d = downside_resilience(bars[["Close"]], bench) or {}
                for k in DSR_COLS:
                    if k in d:
                        new_vals[k].loc[idx] = d[k]
        except Exception:
            continue
        if (i + 1) % 1000 == 0:
            print(f"    {i+1}/{len(tickers)}", file=sys.stderr)

    for c in new_vals:
        df[c] = new_vals[c]
    df.to_csv(csv_path, index=False)
    print(f"  {region}: wrote {len(df)} rows", file=sys.stderr)
    _mark_done(region)

    try:
        subprocess.run(["python", "/home/user/cyclepapa/persist_results.py",
                        "--no-push"], check=False, timeout=180)
    except Exception as e:
        print(f"  persist warning: {e}", file=sys.stderr)
    return True


def main():
    print("Fetching regional benchmark ETFs...", file=sys.stderr)
    benchmarks = fetch_benchmarks()
    if "SPY" not in benchmarks:
        # Exit nonzero so the shell orchestrator restarts us with a FRESH
        # process (fresh yfinance session/cookies — Yahoo rate-limits key
        # on the session, so in-process retries never recover).
        print("SPY missing — exit 3 for process-level retry.", file=sys.stderr)
        sys.exit(3)

    csvs = sorted(glob.glob("/tmp/stars_aligned_*.csv"))
    print(f"Refreshing legs across {len(csvs)} regions", file=sys.stderr)
    for p in csvs:
        try:
            refresh_region(p, benchmarks)
        except Exception as e:
            print(f"  {p}: error {e}", file=sys.stderr)
        time.sleep(2)

    try:
        subprocess.run(["python", "/home/user/cyclepapa/persist_results.py"],
                       check=False, timeout=300)
    except Exception as e:
        print(f"  final persist warning: {e}", file=sys.stderr)
    print("Legs refresh complete.")


if __name__ == "__main__":
    main()
