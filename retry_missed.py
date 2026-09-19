"""Retry stars_aligned evaluation for tickers missed in prior runs.

Reads existing /tmp/stars_aligned_<region>.csv, finds tickers from the
configured universe that are absent, fetches them with very conservative
yfinance settings (chunk=30, pause=4s, retries=6) and appends evaluations
to the same CSV.
"""

import sys
import warnings
import time
import argparse

import numpy as np
import pandas as pd

from screen import (
    REGIONS, fetch_universe, fetch_ohlc, fetch_fx, currency_for_ticker,
)
from stars_aligned import evaluate

warnings.filterwarnings("ignore")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("region")
    ap.add_argument("--chunk", type=int, default=30)
    ap.add_argument("--pause", type=float, default=4.0)
    ap.add_argument("--retries", type=int, default=6)
    args = ap.parse_args()

    region = args.region
    if region not in REGIONS:
        raise SystemExit(f"Unknown region {region!r}")
    cfg = REGIONS[region]
    csv_path = f"/tmp/stars_aligned_{region}.csv"

    universe, _ = fetch_universe(region)
    try:
        done_df = pd.read_csv(csv_path)
        done = set(done_df["ticker"].tolist())
    except FileNotFoundError:
        done = set()
        done_df = pd.DataFrame()
    missing = [t for t in universe if t not in done]
    print(f"{region}: {len(missing)} missing of {len(universe)} ({len(done)} already done)", file=sys.stderr)
    if not missing:
        return

    index = cfg["index"]
    # Slow fetch
    daily = fetch_ohlc(missing + [index], period="36mo",
                       chunk=args.chunk, retries=args.retries,
                       pause_between_chunks=args.pause)
    if index not in daily["Close"].columns:
        print(f"  index {index} missing; aborting", file=sys.stderr)
        return
    idx_close = daily["Close"][index]
    tickers_have_data = [t for t in missing if t in daily["Close"].columns]
    print(f"  fetched data for {len(tickers_have_data)} of {len(missing)} missing", file=sys.stderr)

    needed_ccys = {currency_for_ticker(t) for t in tickers_have_data}
    fx = {}
    if currency_for_ticker(index) == "USD" and any(c != "USD" for c in needed_ccys):
        fx = fetch_fx(needed_ccys, period="36mo")

    rows = []
    for i, t in enumerate(tickers_have_data):
        try:
            r = evaluate(daily, idx_close, t, fx)
        except Exception:
            r = None
        if r is not None:
            rows.append(r)
        if (i + 1) % 100 == 0:
            print(f"  evaluated {i+1}/{len(tickers_have_data)}", file=sys.stderr)

    print(f"\n{region}: appended {len(rows)} new evaluations", file=sys.stderr)
    if not rows:
        return
    new_df = pd.DataFrame(rows)
    combined = pd.concat([done_df, new_df], ignore_index=True) if not done_df.empty else new_df
    combined = combined.drop_duplicates(subset=["ticker"], keep="last")
    combined.to_csv(csv_path, index=False)
    print(f"  wrote {len(combined)} rows to {csv_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
