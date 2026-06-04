"""Second-pass augment: add DSR (Downside Resilience) + market_corr columns.

DSR = how well stock holds up on market drawdown days. Market proxy = SPY.
This is the "doesn't care about market downside vol" measure.

Run AFTER augment_minervini.py (which adds M + E).
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
from minervini_leg import downside_resilience

warnings.filterwarnings("ignore")


def fetch_market(symbol="SPY", period="36mo"):
    raw = yf.download(symbol, period=period, interval="1d",
                      auto_adjust=True, progress=False, threads=False)
    if raw.empty:
        return None
    return raw["Close"]


def augment_region(csv_path: str, market_close: pd.Series):
    df = pd.read_csv(csv_path)
    region = csv_path.split("stars_aligned_")[-1].replace(".csv", "")
    new_cols = ["DSR", "downside_capture", "market_corr",
                "n_drawdown_days", "stock_ret_drawdown_pct",
                "mkt_ret_drawdown_pct"]
    if "DSR" in df.columns and df["DSR"].notna().sum() > len(df) * 0.5:
        print(f"  {region}: DSR already present", file=sys.stderr)
        return

    tickers = df["ticker"].astype(str).tolist()
    print(f"  {region}: {len(tickers)} tickers", file=sys.stderr)

    daily = fetch_ohlc(tickers, period="36mo",
                       chunk=40, retries=4, pause_between_chunks=2.0)
    closes = daily.get("Close")
    if closes is None or closes.empty:
        print(f"  {region}: no Close data", file=sys.stderr)
        return
    have_data = set(closes.columns)
    print(f"  {region}: fetched data for {len(have_data)}/{len(tickers)}",
          file=sys.stderr)

    dsr_rows = []
    for i, t in enumerate(tickers):
        if t not in have_data:
            dsr_rows.append({k: np.nan for k in new_cols})
            continue
        try:
            bars = pd.DataFrame({
                "Close": daily["Close"][t],
            }).dropna(subset=["Close"])
            if len(bars) < 60:
                dsr_rows.append({k: np.nan for k in new_cols})
                continue
            d = downside_resilience(bars, market_close)
            dsr_rows.append({k: d.get(k) for k in new_cols})
        except Exception:
            dsr_rows.append({k: np.nan for k in new_cols})
        if (i + 1) % 500 == 0:
            print(f"    scored {i+1}/{len(tickers)}", file=sys.stderr)

    d_df = pd.DataFrame(dsr_rows)
    for col in new_cols:
        df[col] = d_df[col].values
    df.to_csv(csv_path, index=False)
    print(f"  {region}: wrote {len(df)} rows", file=sys.stderr)


def main():
    print("Fetching SPY for market proxy...", file=sys.stderr)
    spy = fetch_market("SPY")
    if spy is None:
        print("Could not fetch SPY. Aborting.", file=sys.stderr)
        return
    print(f"SPY: {len(spy)} daily bars", file=sys.stderr)

    csvs = sorted(glob.glob("/tmp/stars_aligned_*.csv"))
    print(f"Augmenting {len(csvs)} regions with DSR", file=sys.stderr)
    for p in csvs:
        try:
            augment_region(p, spy)
        except Exception as e:
            print(f"  {p}: error {e}", file=sys.stderr)
        time.sleep(2)
    print("DSR pass complete.")


if __name__ == "__main__":
    main()
