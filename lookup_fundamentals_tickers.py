"""Compute TD MTF + momentum measures for a hand-picked ticker list.

Loads from any of the local daily caches first; falls back to a direct
yfinance fetch if missing. Bypasses the "flagged" filter so every name
in the fundamentals shortlist is surfaced regardless of whether it
trips any technical screen.
"""

import glob
import os
import pickle
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from momentum_rank import compute_momentum, load_or_download_spy, load_or_download_spy_monthly

pd.set_option("display.max_columns", None)
pd.set_option("display.width", 240)
pd.set_option("display.float_format", "{:.2f}".format)


def find_in_caches(ticker):
    for path in sorted(glob.glob("/tmp/cyclepapa_dl_*_daily_2y.pkl")):
        try:
            with open(path, "rb") as f:
                s = pickle.load(f)
            if ticker in s.get("frames", {}):
                return s["frames"][ticker], path
        except Exception:
            continue
    return None, None


def fetch_direct(ticker, years=2):
    print(f"  fetching {ticker} via yfinance...")
    try:
        df = yf.download(ticker, period=f"{years}y", interval="1d",
                         auto_adjust=True, progress=False, threads=False)
        if df is None or df.empty:
            return None
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        return df
    except Exception as e:
        print(f"    error: {e}")
        return None


def fetch_monthly(ticker, years=10):
    try:
        df = yf.download(ticker, period=f"{years}y", interval="1mo",
                         auto_adjust=True, progress=False, threads=False)
        if df is None or df.empty:
            return None
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        return df
    except Exception:
        return None


def main():
    tickers = sys.argv[1:] if len(sys.argv) > 1 else [
        "WBD", "RKT.L", "C", "CNC", "NKE", "UNH",
        "BAYN.DE", "STLA", "GIS", "ALSN",
    ]

    spy = load_or_download_spy(3)
    spy_m = load_or_download_spy_monthly(10)

    rows = []
    for t in tickers:
        df, source = find_in_caches(t)
        if df is None:
            df = fetch_direct(t)
            source = "yfinance-direct"
        if df is None or len(df) < 130:
            print(f"{t}: NO DATA available")
            continue
        dfm = fetch_monthly(t)
        try:
            measures = compute_momentum(df, spy_close=spy, df_monthly=dfm,
                                         spy_monthly_close=spy_m)
            measures["_source"] = source
            measures["Ticker"] = t
            rows.append(measures)
        except Exception as e:
            print(f"{t}: compute error: {e}")
            continue

    if not rows:
        print("no rows computed")
        return

    out = pd.DataFrame(rows).set_index("Ticker")
    cols = ["last_close", "_source", "td_mtf_composite",
            "td_mtf_net_setup", "td_mtf_net_cd", "td_mtf_net_perfect",
            "td_mtf_net_triple",
            "td_w_buy_setup", "td_w_sell_setup",
            "td_w_buy_cd", "td_w_sell_cd",
            "td_m_buy_setup", "td_m_sell_setup",
            "td_m_buy_cd", "td_m_sell_cd",
            "rs_rank_max", "mom_3m", "mom_6m",
            "roque_score", "q_method_pass",
            "box_length_weeks", "pos_in_box_pct",
            "td_bullish_exhaustion", "td_bearish_exhaustion"]
    cols = [c for c in cols if c in out.columns]
    print(out[cols].to_string())
    out.to_csv("/tmp/fundamentals_lookup.csv")
    print("\nFull set saved to /tmp/fundamentals_lookup.csv")


if __name__ == "__main__":
    main()
