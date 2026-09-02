"""Augment existing stars_aligned_*.csv files with the Minervini M column.

For each region CSV: read the evaluated tickers, fetch daily bars, compute
full_minervini_score, append M / M_base / M_vcp / vcp_contractions /
vcp_pivot_distance_pct / vcp_volume_dryup_ratio columns, save back.

Much faster than a full re-screen since it only runs the new code on the
already-curated ticker list, not the whole W/Q/D/DA/R stack.
"""

import sys
import warnings
import glob
import time

import numpy as np
import pandas as pd

sys.path.insert(0, "/home/user/cyclepapa")
from screen import fetch_ohlc
from minervini_leg import full_minervini_score

warnings.filterwarnings("ignore")


def augment_region(csv_path: str):
    df = pd.read_csv(csv_path)
    region = csv_path.split("stars_aligned_")[-1].replace(".csv", "")

    new_cols = ["M", "M_base", "M_vcp", "vcp_contractions",
                "vcp_pivot_distance_pct", "vcp_volume_dryup_ratio",
                "E", "E_vol_spike", "E_pivot_break", "E_ret_acceleration",
                "E_behavior_shift", "E_close_strength", "E_coil_break",
                "E_ma_aligned", "E_bb_break", "E_new_high", "E_vol_ratio"]
    if "E" in df.columns and df["E"].notna().sum() > len(df) * 0.5:
        print(f"  {region}: already has E", file=sys.stderr)
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

    has_vol = "Volume" in daily.columns.get_level_values(0)
    minervini_rows = []
    for i, t in enumerate(tickers):
        if t not in have_data:
            minervini_rows.append({k: np.nan for k in new_cols})
            continue
        try:
            bars = pd.DataFrame({
                "Open":   daily["Open"][t],
                "High":   daily["High"][t],
                "Low":    daily["Low"][t],
                "Close":  daily["Close"][t],
                "Volume": daily["Volume"][t] if has_vol else np.nan,
            }).dropna(subset=["Close"])
            if len(bars) < 252:
                minervini_rows.append({k: np.nan for k in new_cols})
                continue
            m = full_minervini_score(bars)
            minervini_rows.append({k: m.get(k) for k in new_cols})
        except Exception:
            minervini_rows.append({k: np.nan for k in new_cols})
        if (i + 1) % 250 == 0:
            print(f"    scored {i+1}/{len(tickers)}", file=sys.stderr)

    m_df = pd.DataFrame(minervini_rows)
    for col in new_cols:
        df[col] = m_df[col].values
    df.to_csv(csv_path, index=False)
    print(f"  {region}: wrote {len(df)} rows", file=sys.stderr)


def main():
    csvs = sorted(glob.glob("/tmp/stars_aligned_*.csv"))
    print(f"Augmenting {len(csvs)} regions", file=sys.stderr)
    for p in csvs:
        try:
            augment_region(p)
        except Exception as e:
            print(f"  {p}: error {e}", file=sys.stderr)
        time.sleep(2)
    print("All done.")


if __name__ == "__main__":
    main()
