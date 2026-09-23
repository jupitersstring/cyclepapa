"""Targeted gap-fill for US/UK/EU regions: recompute E/ADV/DSR/M ONLY for
rows where any leg is missing, using regional benchmark ETFs for DSR.
Small ticker count (~dozens) -> single cheap fetch.
"""

import sys
import glob
import warnings

import numpy as np
import pandas as pd

sys.path.insert(0, "/home/user/cyclepapa")
from screen import fetch_ohlc
from minervini_leg import (adv_metrics, downside_resilience, entry_now,
                            full_minervini_score)
from refresh_legs import fetch_benchmarks, E_COLS, ADV_COLS, DSR_COLS
from regional_benchmarks import benchmark_for_ticker

warnings.filterwarnings("ignore")

REGIONS = {'us-small', 'us-mid', 'fd-us-micro', 'fd-us-large', 'fd-us-mega',
           'fd-eu-nano', 'fd-eu-micro', 'fd-eu-small', 'fd-eu-mid',
           'fd-eu-large', 'fd-eu-mega'}
M_COLS = ["M", "M_base", "M_vcp"]


def main():
    benchmarks = fetch_benchmarks()
    if "SPY" not in benchmarks:
        print("SPY missing — exit 3", file=sys.stderr)
        sys.exit(3)
    spy = benchmarks["SPY"]

    for path in sorted(glob.glob("/tmp/stars_aligned_*.csv")):
        region = path.split("stars_aligned_")[-1].replace(".csv", "")
        if region not in REGIONS:
            continue
        df = pd.read_csv(path, low_memory=False)
        needs = (df.E.isna() | df.ADV_play_now.isna() | df.DSR.isna()
                 | df.M.isna())
        tickers = df.loc[needs, "ticker"].astype(str).tolist()
        if not tickers:
            print(f"  {region}: no gaps", file=sys.stderr)
            continue
        print(f"  {region}: filling {len(tickers)} gap tickers", file=sys.stderr)

        daily = fetch_ohlc(tickers, period="18mo",
                           chunk=40, retries=3, pause_between_chunks=1.0)
        closes = daily.get("Close")
        if closes is None or closes.empty:
            print(f"  {region}: fetch empty (likely all delisted)", file=sys.stderr)
            continue
        have = set(closes.columns)
        has_vol = "Volume" in daily.columns.get_level_values(0)

        all_cols = E_COLS + ADV_COLS + DSR_COLS + M_COLS
        new_vals = {c: df[c].copy() if c in df.columns
                    else pd.Series([np.nan] * len(df)) for c in all_cols}
        filled = 0
        for t in tickers:
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
                d = downside_resilience(bars[["Close"]], bench) or {}
                for k in DSR_COLS:
                    if k in d:
                        new_vals[k].loc[idx] = d[k]
                if len(bars) >= 252:
                    m = full_minervini_score(bars) or {}
                    for k in M_COLS:
                        if k in m and m[k] is not None:
                            new_vals[k].loc[idx] = m[k]
                filled += 1
            except Exception:
                continue
        for c in all_cols:
            if c in df.columns:
                df[c] = new_vals[c]
        df.to_csv(path, index=False)
        print(f"  {region}: filled {filled}/{len(tickers)}", file=sys.stderr)

    print("Gap fill complete.")


if __name__ == "__main__":
    main()
