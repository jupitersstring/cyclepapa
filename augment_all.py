"""Combined augment: fetch each region's OHLC ONCE, then compute M+E+ADV+DSR
in a single pass per ticker. Much faster than running augment_minervini.py
+ augment_adv.py + augment_dsr.py serially since each previously refetched
the same 36mo OHLC.

Idempotent per region: skips legs that are already present (uses
ADV_play_now as the canonical "ADV done" marker since it's the newest).
"""

import sys
import warnings
import glob
import time

import numpy as np
import pandas as pd
import yfinance as yf

sys.path.insert(0, "/home/user/cyclepapa")
from screen import fetch_ohlc
from minervini_leg import (
    full_minervini_score, adv_metrics, downside_resilience,
)

warnings.filterwarnings("ignore")

M_COLS = ["M", "M_base", "M_vcp", "vcp_contractions",
          "vcp_pivot_distance_pct", "vcp_volume_dryup_ratio",
          "E", "E_vol_spike", "E_pivot_break", "E_ret_acceleration",
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


def augment_region(csv_path: str, market_close: pd.Series):
    df = pd.read_csv(csv_path)
    region = csv_path.split("stars_aligned_")[-1].replace(".csv", "")

    need_m   = not ("E" in df.columns and df["E"].notna().sum() > len(df) * 0.5)
    need_adv = not ("ADV_play_now" in df.columns
                    and df["ADV_play_now"].notna().sum() > len(df) * 0.5)
    need_dsr = not ("DSR" in df.columns and df["DSR"].notna().sum() > len(df) * 0.5)

    if not (need_m or need_adv or need_dsr):
        print(f"  {region}: all legs present, skip", file=sys.stderr)
        return

    # Pre-filter: only augment tickers that have a chance of qualifying for
    # Play_Now (best_rank > 50 and at least one TF not rejected). This cuts
    # ~20K tickers -> ~2.3K, ~10x faster, no impact on the picks.
    df["_best_rank"] = df[["daily_rank","weekly_rank","monthly_rank"]].max(axis=1)
    not_rej_mask = (
        (df.daily_label != "Reject") |
        (df.weekly_label != "Reject") |
        (df.monthly_label != "Reject")
    )
    qualify = df[(df["_best_rank"] > 50) & not_rej_mask]
    tickers = qualify["ticker"].astype(str).tolist()
    print(f"  {region}: {len(tickers)}/{len(df)} qualify (best_rank>50, not all reject)  "
          f"needM={need_m} needADV={need_adv} needDSR={need_dsr}",
          file=sys.stderr)
    if not tickers:
        return

    # Use 18mo (enough for SMA200 + 8w slope) and bigger chunks for speed.
    daily = fetch_ohlc(tickers, period="18mo",
                       chunk=80, retries=4, pause_between_chunks=0.7)
    closes = daily.get("Close")
    if closes is None or closes.empty:
        print(f"  {region}: no Close data", file=sys.stderr)
        return
    have_data = set(closes.columns)
    has_vol = "Volume" in daily.columns.get_level_values(0)
    print(f"  {region}: fetched data for {len(have_data)}/{len(tickers)}",
          file=sys.stderr)

    by_ticker = {}  # ticker -> dict of new col values
    for i, t in enumerate(tickers):
        row = {}
        if t not in have_data:
            by_ticker[t] = row
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
                by_ticker[t] = row
                continue

            if need_m and len(bars) >= 252:
                m = full_minervini_score(bars)
                for k in M_COLS:
                    row[k] = m.get(k)

            if need_adv and has_vol:
                a = adv_metrics(bars)
                for k in ADV_COLS:
                    row[k] = a.get(k)

            if need_dsr:
                d = downside_resilience(bars[["Close"]], market_close)
                for k in DSR_COLS:
                    row[k] = d.get(k)
            by_ticker[t] = row
        except Exception:
            by_ticker[t] = row

        if (i + 1) % 500 == 0:
            print(f"    scored {i+1}/{len(tickers)}", file=sys.stderr)

    # Map results back to the full df. Columns that don't exist get created
    # NaN-filled; only the rows whose ticker was augmented get values.
    cols_to_set = []
    if need_m:   cols_to_set += M_COLS
    if need_adv: cols_to_set += ADV_COLS
    if need_dsr: cols_to_set += DSR_COLS
    for col in cols_to_set:
        if col not in df.columns:
            df[col] = np.nan
    new_vals = {col: df[col].copy() for col in cols_to_set}
    for tk, row in by_ticker.items():
        idx = df.index[df.ticker == tk]
        for col in cols_to_set:
            if col in row:
                new_vals[col].loc[idx] = row[col]
    for col in cols_to_set:
        df[col] = new_vals[col]

    df = df.drop(columns=["_best_rank"], errors="ignore")

    df.to_csv(csv_path, index=False)
    print(f"  {region}: wrote {len(df)} rows", file=sys.stderr)


def main():
    print("Fetching SPY...", file=sys.stderr)
    spy = fetch_market("SPY")
    if spy is None:
        print("Could not fetch SPY. Aborting.", file=sys.stderr)
        return
    print(f"SPY: {len(spy)} bars", file=sys.stderr)

    csvs = sorted(glob.glob("/tmp/stars_aligned_*.csv"))
    print(f"Combined augment across {len(csvs)} regions", file=sys.stderr)
    for p in csvs:
        try:
            augment_region(p, spy)
        except Exception as e:
            print(f"  {p}: error {e}", file=sys.stderr)
        time.sleep(2)
    print("Combined augment complete.")


if __name__ == "__main__":
    main()
