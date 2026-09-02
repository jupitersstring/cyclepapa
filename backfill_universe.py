"""Full-universe backfill of E, DSR, ADV legs across all 20K+ tickers.

Unlike augment_all.py which pre-filters to best_rank>50 (~2.3K),
this targets EVERY ticker in /tmp/stars_aligned_*.csv that has E missing
(currently 89% of the universe). M is already complete so we skip it.

Per-ticker idempotent: if E/DSR/ADV are already populated for a row,
that row is not recomputed. Allows incremental progress under reset.

After each region completes, the region's CSV is rewritten AND
persist_results.py is invoked to push the fresh data/ snapshot to git —
so a sandbox reset mid-run loses at most one region's worth of work.
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


def fetch_market(symbol="SPY", period="18mo"):
    raw = yf.download(symbol, period=period, interval="1d",
                      auto_adjust=True, progress=False, threads=False)
    if raw.empty:
        return None
    close = raw["Close"]
    if isinstance(close, pd.DataFrame):
        close = close.iloc[:, 0]
    return close


def backfill_region(csv_path: str, market_close: pd.Series, persist_after: bool):
    df = pd.read_csv(csv_path)
    region = csv_path.split("stars_aligned_")[-1].replace(".csv", "")

    # Ensure cols exist
    for col in E_COLS + ADV_COLS + DSR_COLS:
        if col not in df.columns:
            df[col] = np.nan

    # Find rows missing ANY of the three legs
    miss_E   = df.E.isna()
    miss_ADV = df.ADV_play_now.isna()
    miss_DSR = df.DSR.isna()
    needs = miss_E | miss_ADV | miss_DSR
    n_needs = int(needs.sum())

    if n_needs == 0:
        print(f"  {region}: 0 rows need backfill, skip", file=sys.stderr)
        return False

    tickers = df.loc[needs, "ticker"].astype(str).tolist()
    print(f"  {region}: backfilling {n_needs}/{len(df)} rows  "
          f"(missing E:{miss_E.sum()} ADV:{miss_ADV.sum()} DSR:{miss_DSR.sum()})",
          file=sys.stderr)

    daily = fetch_ohlc(tickers, period="18mo",
                       chunk=80, retries=4, pause_between_chunks=0.7)
    closes = daily.get("Close")
    if closes is None or closes.empty:
        print(f"  {region}: no Close data", file=sys.stderr)
        return False
    have = set(closes.columns)
    has_vol = "Volume" in daily.columns.get_level_values(0)
    print(f"  {region}: fetched {len(have)}/{len(tickers)}", file=sys.stderr)

    by_t = {}
    for i, t in enumerate(tickers):
        row = {}
        if t not in have:
            by_t[t] = row
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
                by_t[t] = row
                continue
            # E (cheap, just needs daily bars)
            e = entry_now(bars) or {}
            for k in E_COLS:
                row[k] = e.get(k)
            # ADV
            if has_vol:
                a = adv_metrics(bars) or {}
                for k in ADV_COLS:
                    row[k] = a.get(k)
            # DSR
            d = downside_resilience(bars[["Close"]], market_close) or {}
            for k in DSR_COLS:
                row[k] = d.get(k)
            by_t[t] = row
        except Exception:
            by_t[t] = row
        if (i + 1) % 1000 == 0:
            print(f"    scored {i+1}/{len(tickers)}", file=sys.stderr)

    # Write back
    new_vals = {c: df[c].copy() for c in E_COLS + ADV_COLS + DSR_COLS}
    for tk, row in by_t.items():
        idx = df.index[df.ticker == tk]
        for c, v in row.items():
            new_vals[c].loc[idx] = v
    for c in new_vals:
        df[c] = new_vals[c]
    df.to_csv(csv_path, index=False)
    print(f"  {region}: wrote {len(df)} rows", file=sys.stderr)

    if persist_after:
        # Best-effort persist + push; don't fail the whole run if git push hits a hiccup.
        try:
            subprocess.run(
                ["python", "/home/user/cyclepapa/persist_results.py"],
                check=False, timeout=120,
            )
        except Exception as e:
            print(f"  persist warning: {e}", file=sys.stderr)
    return True


def main():
    print("Fetching SPY (regional benchmark fix is a separate task)...", file=sys.stderr)
    spy = fetch_market("SPY")
    if spy is None:
        print("Could not fetch SPY. Aborting.", file=sys.stderr); return
    print(f"SPY: {len(spy)} bars", file=sys.stderr)

    csvs = sorted(glob.glob("/tmp/stars_aligned_*.csv"))
    print(f"Full-universe backfill across {len(csvs)} regions", file=sys.stderr)
    any_changed = False
    for p in csvs:
        try:
            changed = backfill_region(p, spy, persist_after=True)
            any_changed = any_changed or changed
        except Exception as e:
            print(f"  {p}: error {e}", file=sys.stderr)
        time.sleep(2)
    # Final push at end
    if any_changed:
        try:
            subprocess.run(
                ["python", "/home/user/cyclepapa/persist_results.py"],
                check=False, timeout=300,
            )
        except Exception as e:
            print(f"  final persist warning: {e}", file=sys.stderr)
    print("Backfill complete.")


if __name__ == "__main__":
    main()
