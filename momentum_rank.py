"""
Qullamaggie-style momentum watchlist qualifier.

For each ticker we compute three momentum ratios on DAILY bars:

  mom_1m = last_close / SMA(close, 25)
  mom_3m = last_close / SMA(close, 66)
  mom_6m = last_close / SMA(close, 126)

The universe is ranked by each, the top N (default 30) per metric are
surfaced separately, and the intersection (top N on all three timeframes =
sustained leadership) is the headline list. Output is a CSV that can be
fed directly into volume_screen.py for tightness / POC checks.
"""

import argparse
import os
import pickle
import sys
import time

import numpy as np
import pandas as pd
import yfinance as yf

# Reuse the universe definitions from scan_failed_bearish.py
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from scan_failed_bearish import get_universe  # noqa: E402


PICKLE_TMPL = "/tmp/cyclepapa_dl_{universe}_daily_{years}y.pkl"


def load_pickle_frames(universe, years):
    path = PICKLE_TMPL.format(universe=universe, years=years)
    if not os.path.exists(path):
        return {}, set()
    with open(path, "rb") as f:
        state = pickle.load(f)
    return state.get("frames", {}), set(state.get("done", []))


def save_pickle(universe, years, frames, done):
    path = PICKLE_TMPL.format(universe=universe, years=years)
    tmp = path + ".tmp"
    try:
        with open(tmp, "wb") as f:
            pickle.dump({"frames": frames, "done": list(done)}, f)
        os.replace(tmp, path)
    except Exception as e:
        print(f"    checkpoint save failed: {e}")


def download_daily(universe, tickers, years=2, chunk_size=80, batch_sleep=15):
    frames, done = load_pickle_frames(universe, years)
    if frames:
        print(f"  resumed: {len(frames)} kept, {len(done)} already attempted")
    todo = [t for t in tickers if t not in done]
    total = len(todo)
    n_batches = (total + chunk_size - 1) // chunk_size
    for i in range(0, total, chunk_size):
        b = i // chunk_size + 1
        chunk = todo[i:i + chunk_size]
        print(f"  batch {b}/{n_batches}: {i + 1}-{min(i + chunk_size, total)} of {total} (kept: {len(frames)})")
        try:
            data = yf.download(
                chunk, period=f"{years}y", interval="1d",
                group_by="ticker", threads=True, progress=False, auto_adjust=True,
            )
        except Exception as e:
            print(f"    batch failed: {e}")
            data = None
        if data is not None and not data.empty:
            for t in chunk:
                try:
                    if isinstance(data.columns, pd.MultiIndex):
                        sub = data[t].dropna(how="all")
                    else:
                        sub = data.dropna(how="all")
                    if "Close" in sub.columns and len(sub) >= 130:
                        frames[t] = sub
                except Exception:
                    continue
        done.update(chunk)
        save_pickle(universe, years, frames, done)
        if b < n_batches:
            time.sleep(batch_sleep)
    return frames


def compute_momentum(df):
    close = pd.to_numeric(df["Close"], errors="coerce").dropna()
    if len(close) < 130:
        return None
    last = float(close.iloc[-1])
    sma25 = float(close.tail(25).mean())
    sma66 = float(close.tail(66).mean())
    sma126 = float(close.tail(126).mean())
    if sma25 <= 0 or sma66 <= 0 or sma126 <= 0:
        return None
    return {
        "last_close": last,
        "mom_1m": last / sma25,
        "mom_3m": last / sma66,
        "mom_6m": last / sma126,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--universe", required=True,
                        help="Universe key (e.g. us-smid, us-midlarge, us-micro, eu-smid).")
    parser.add_argument("--years", type=int, default=2)
    parser.add_argument("--top", type=int, default=30)
    parser.add_argument("--min-price", type=float, default=5.0,
                        help="Drop tickers with last close below this (liquidity floor).")
    parser.add_argument("--out", default=None)
    args = parser.parse_args()

    print(f"Loading {args.universe} universe...")
    universe = get_universe(args.universe)
    tickers = [t for t in universe.index.tolist() if isinstance(t, str) and t]
    print(f"  {len(tickers)} tickers")

    print(f"Downloading daily bars ({args.years}y)...")
    frames = download_daily(args.universe, tickers, years=args.years)
    print(f"  {len(frames)} tickers with usable daily data")

    rows = []
    for t, f in frames.items():
        m = compute_momentum(f)
        if m is None:
            continue
        if m["last_close"] < args.min_price:
            continue
        m["Ticker"] = t
        name_col = "name" if "name" in universe.columns else "shortName"
        m["name"] = universe.loc[t, name_col] if t in universe.index else None
        m["sector"] = universe.loc[t, "sector"] if t in universe.index and "sector" in universe.columns else None
        rows.append(m)

    if not rows:
        print("No momentum metrics computed.")
        return

    df = pd.DataFrame(rows).set_index("Ticker")
    df["rank_1m"] = df["mom_1m"].rank(ascending=False).astype(int)
    df["rank_3m"] = df["mom_3m"].rank(ascending=False).astype(int)
    df["rank_6m"] = df["mom_6m"].rank(ascending=False).astype(int)
    df["rank_avg"] = (df["rank_1m"] + df["rank_3m"] + df["rank_6m"]) / 3
    df["rank_max"] = df[["rank_1m", "rank_3m", "rank_6m"]].max(axis=1)

    top_1m = df.nlargest(args.top, "mom_1m")
    top_3m = df.nlargest(args.top, "mom_3m")
    top_6m = df.nlargest(args.top, "mom_6m")
    intersection = set(top_1m.index) & set(top_3m.index) & set(top_6m.index)
    union = set(top_1m.index) | set(top_3m.index) | set(top_6m.index)

    df["in_top_1m"] = df.index.isin(top_1m.index)
    df["in_top_3m"] = df.index.isin(top_3m.index)
    df["in_top_6m"] = df.index.isin(top_6m.index)
    df["in_all_three"] = df.index.isin(intersection)
    df["in_any"] = df.index.isin(union)

    flagged = df[df["in_any"]].sort_values("rank_max")

    out_path = args.out or f"momentum_rank_{args.universe}_{pd.Timestamp.today():%Y%m%d}.csv"
    flagged.to_csv(out_path)
    print(f"Saved {len(flagged)} flagged tickers to {out_path}")

    show_cols = ["name", "sector", "last_close", "mom_1m", "mom_3m", "mom_6m",
                 "rank_1m", "rank_3m", "rank_6m", "in_top_1m", "in_top_3m", "in_top_6m"]
    show_cols = [c for c in show_cols if c in flagged.columns]

    with pd.option_context("display.max_columns", None, "display.width", 240, "display.float_format", "{:.2f}".format):
        print(f"\n=== INTERSECTION: top {args.top} on ALL three timeframes ({len(intersection)} tickers) ===")
        if intersection:
            print(df.loc[list(intersection)].sort_values("rank_max")[show_cols].to_string())
        else:
            print("(none)")

        print(f"\n=== Top {args.top} by 1-month momentum (c/avgc25) ===")
        print(top_1m[show_cols].to_string())

        print(f"\n=== Top {args.top} by 3-month momentum (c/avgc66) ===")
        print(top_3m[show_cols].to_string())

        print(f"\n=== Top {args.top} by 6-month momentum (c/avgc126) ===")
        print(top_6m[show_cols].to_string())


if __name__ == "__main__":
    main()
