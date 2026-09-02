"""Third-pass augment: add ADV (Average Dollar Volume) metrics + DSR.

After augment_minervini.py (adds M+E) and before/with augment_dsr.py.
Adds ADV liquidity + 8-week slope columns. Market-cap-relative turnover
requires the yfinance .info field which we resolve later in the Excel build.

Run order: augment_minervini.py → augment_adv.py → augment_dsr.py (or
combined manually).
"""

import sys
import warnings
import glob
import time

import numpy as np
import pandas as pd

sys.path.insert(0, "/home/user/cyclepapa")
from screen import fetch_ohlc
from minervini_leg import adv_metrics

warnings.filterwarnings("ignore")


def augment_region(csv_path: str):
    df = pd.read_csv(csv_path)
    region = csv_path.split("stars_aligned_")[-1].replace(".csv", "")
    new_cols = ["ADV", "ADV_play_now", "adv_20", "adv_60",
                "adv_slope_pct_wk", "adv_accel_pct_wk",
                "adv_liq_score", "adv_slope_score", "adv_accel_score",
                "adv_turnover_score"]
    if "ADV_play_now" in df.columns and df["ADV_play_now"].notna().sum() > len(df) * 0.5:
        print(f"  {region}: ADV_play_now already present", file=sys.stderr)
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
    has_vol = "Volume" in daily.columns.get_level_values(0)
    if not has_vol:
        print(f"  {region}: no volume data; cannot compute ADV", file=sys.stderr)
        return

    rows = []
    for i, t in enumerate(tickers):
        if t not in have_data:
            rows.append({k: np.nan for k in new_cols})
            continue
        try:
            bars = pd.DataFrame({
                "Close":  daily["Close"][t],
                "Volume": daily["Volume"][t],
            }).dropna(subset=["Close"])
            if len(bars) < 60:
                rows.append({k: np.nan for k in new_cols})
                continue
            a = adv_metrics(bars)
            rows.append({k: a.get(k) for k in new_cols})
        except Exception:
            rows.append({k: np.nan for k in new_cols})
        if (i + 1) % 500 == 0:
            print(f"    scored {i+1}/{len(tickers)}", file=sys.stderr)

    a_df = pd.DataFrame(rows)
    for col in new_cols:
        df[col] = a_df[col].values
    df.to_csv(csv_path, index=False)
    print(f"  {region}: wrote {len(df)} rows", file=sys.stderr)


def main():
    csvs = sorted(glob.glob("/tmp/stars_aligned_*.csv"))
    print(f"ADV augment across {len(csvs)} regions", file=sys.stderr)
    for p in csvs:
        try:
            augment_region(p)
        except Exception as e:
            print(f"  {p}: error {e}", file=sys.stderr)
        time.sleep(2)
    print("ADV pass complete.")


if __name__ == "__main__":
    main()
