"""Refresh the durable price cache for liquid names via the proxy-routed
Yahoo fetcher, then those universes can be re-ranked offline.

Fetches each unique liquid ticker ONCE (daily 2y + monthly 10y) and writes the
fresh bars into every universe cache pickle that contains it, so whichever copy
wins the workbook dedup is current. Checkpoints each universe cache to the
durable bz2 store as it goes (resumable across resets).

Usage: python3 update_prices.py [adv_threshold]   (default 20 = $20M USD ADV)
"""
import sys
import time
import concurrent.futures as cf
from collections import defaultdict
import pandas as pd

import momentum_rank as mr
from yahoo_fetch import fetch_ohlcv

THRESH = float(sys.argv[1]) if len(sys.argv) > 1 else 20.0
WORKERS = 6


def liquid_pairs():
    df = pd.read_csv("global_equities_consolidated.csv", index_col=0, low_memory=False)
    adv = pd.to_numeric(df.get("adv_20d_usd_millions"), errors="coerce").fillna(0)
    liq = df[adv >= THRESH]
    tick_unis = defaultdict(set)
    for t, u in zip(liq.index.astype(str), liq["_universe"].astype(str)):
        if u.endswith("etfs"):
            continue
        tick_unis[t].add(u)
    return tick_unis


def main():
    tick_unis = liquid_pairs()
    tickers = sorted(tick_unis)
    universes = sorted({u for us in tick_unis.values() for u in us})
    print(f"Liquid (ADV>=${THRESH:.0f}M): {len(tickers)} unique tickers across {len(universes)} universes")

    # 1. Update SPY benchmark (single ticker, both intervals)
    spy_d = fetch_ohlcv("SPY", "3y", "1d")
    if spy_d is not None:
        s = pd.to_numeric(spy_d["Close"], errors="coerce").dropna()
        mr._durable_save(mr.SPY_PICKLE, s)
        print(f"  SPY daily updated -> last {s.index[-1].date()} ({len(s)} bars)")
    spy_m = fetch_ohlcv("SPY", "10y", "1mo")
    if spy_m is not None:
        s = pd.to_numeric(spy_m["Close"], errors="coerce").dropna()
        mr._durable_save(mr.SPY_MONTHLY_PICKLE, s)
        print(f"  SPY monthly updated -> {len(s)} bars")

    # 2. Fetch each unique ticker ONCE (daily + monthly), threaded
    t0 = time.time()
    daily, monthly = {}, {}

    def fd(t):
        return t, fetch_ohlcv(t, "2y", "1d")

    def fm(t):
        return t, fetch_ohlcv(t, "10y", "1mo")

    got_d = 0
    with cf.ThreadPoolExecutor(WORKERS) as ex:
        for i, (t, d) in enumerate(ex.map(fd, tickers), 1):
            if d is not None and len(d) >= 60:
                daily[t] = d
                got_d += 1
            if i % 250 == 0:
                print(f"  daily {i}/{len(tickers)} ({got_d} ok, {time.time()-t0:.0f}s)")
    print(f"  daily done: {got_d}/{len(tickers)} in {time.time()-t0:.0f}s")

    t1 = time.time()
    got_m = 0
    with cf.ThreadPoolExecutor(WORKERS) as ex:
        for i, (t, d) in enumerate(ex.map(fm, tickers), 1):
            if d is not None and len(d) >= 12:
                monthly[t] = d
                got_m += 1
            if i % 250 == 0:
                print(f"  monthly {i}/{len(tickers)} ({got_m} ok, {time.time()-t1:.0f}s)")
    print(f"  monthly done: {got_m}/{len(tickers)} in {time.time()-t1:.0f}s")

    # 3. Write fresh bars into every universe cache that contains each ticker
    uni_tickers = defaultdict(list)
    for t, us in tick_unis.items():
        for u in us:
            uni_tickers[u].append(t)

    for u in sorted(uni_tickers):
        frames, done = mr.load_pickle_frames(u, 2)
        mframes, mdone = mr.load_pickle_frames_monthly(u, 10)
        nd = nm = 0
        for t in uni_tickers[u]:
            if t in daily:
                frames[t] = daily[t]; done.add(t); nd += 1
            if t in monthly:
                mframes[t] = monthly[t]; mdone.add(t); nm += 1
        mr.save_pickle(u, 2, frames, done)
        mr.save_pickle_monthly(u, 10, mframes, mdone)
        print(f"  {u:14s} refreshed {nd} daily / {nm} monthly")

    print(f"DONE — {got_d} tickers refreshed to today across {len(uni_tickers)} universes")


if __name__ == "__main__":
    main()
