"""Weekly price history from Yahoo's v8/finance/chart for the names FMP's price
history does not carry (8,174 of the master's 46,526: German .F lines, KOSDAQ
/ KONEX, Indian and Chinese small caps ...) -> yahoo_weekly_prices.parquet,
then merged into fmp_weekly_prices.parquet (only symbols the FMP panel lacks).

Same convention as fmp_prices.py: total-return bars (Yahoo's adjclose is
split- and dividend-adjusted; OHLC are scaled by adjclose / close so the whole
bar is on the adjusted basis), split-adjusted volume, dvol = adjusted close x
volume, one bar per week labelled by its Friday (Yahoo's weekly bars carry the
Monday timestamp). 10 years, interval 1wk.

Resumable: symbols already in the output file are skipped. Yahoo throttles
hard, so a modest thread pool with jitter; failures are skipped and picked up
on the next run.
"""
from __future__ import annotations

import argparse
import json
import os
import random
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

import numpy as np
import pandas as pd

OUT = "yahoo_weekly_prices.parquet"
PANEL = "fmp_weekly_prices.parquet"
URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range=10y&interval=1wk"
UA = ["Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
      "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"]


def fetch(symbol: str) -> pd.DataFrame | None:
    data = None
    for attempt in range(5):
        req = urllib.request.Request(URL.format(symbol=urllib.parse.quote(symbol)),
                                     headers={"User-Agent": random.choice(UA), "Accept": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                data = json.loads(r.read())
            break
        except urllib.error.HTTPError as e:
            if e.code == 429:                       # throttled: back off, never give up on the name
                time.sleep(random.uniform(8, 20) * (attempt + 1))
                continue
            return None
        except Exception:
            return None
    if data is None:
        return None
    time.sleep(random.uniform(0.3, 0.9))
    res = (data.get("chart") or {}).get("result")
    if not res:
        return None
    r0 = res[0]
    ts = r0.get("timestamp") or []
    q = ((r0.get("indicators") or {}).get("quote") or [{}])[0]
    adj = (((r0.get("indicators") or {}).get("adjclose") or [{}])[0]).get("adjclose")
    if not ts or not q.get("close"):
        return None
    d = pd.DataFrame({"t": ts, "open": q.get("open"), "high": q.get("high"), "low": q.get("low"),
                      "close": q.get("close"), "volume": q.get("volume"),
                      "adj": adj if adj else q.get("close")})
    d = d.apply(pd.to_numeric, errors="coerce")
    d = d.dropna(subset=["close", "adj"])
    d = d[(d["close"] > 0) & (d["adj"] > 0)]
    if len(d) < 4:
        return None
    f = d["adj"] / d["close"]
    for c in ("open", "high", "low"):
        d[c] = (d[c] * f).astype("float32")
    d["close"] = d["adj"].astype("float32")
    d["volume"] = d["volume"].fillna(0).astype("float64")
    d["dvol"] = (d["close"] * d["volume"]).astype("float64")
    wk = pd.to_datetime(d["t"], unit="s").dt.normalize()
    # label each bar by its week's Friday (W-FRI, as the FMP panel)
    d["week"] = (wk + pd.to_timedelta((4 - wk.dt.weekday) % 7, unit="D")).astype("datetime64[us]")
    d = d.drop_duplicates("week", keep="last")
    d["symbol"] = symbol
    return d[["symbol", "week", "open", "high", "low", "close", "volume", "dvol"]]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--merge", action="store_true", help="merge into the FMP panel after fetching")
    args = ap.parse_args()
    g = pd.read_csv("asymmetry_global.csv", usecols=["symbol"], low_memory=False)["symbol"].astype(str).drop_duplicates()
    have = set(pd.read_parquet(PANEL, columns=["symbol"])["symbol"].unique())
    done = set(pd.read_parquet(OUT, columns=["symbol"])["symbol"].unique()) if os.path.exists(OUT) else set()
    todo = [s for s in g if s not in have and s not in done]
    print(f"yahoo weekly: {len(g)} master, {len(have)} in FMP panel, {len(done)} done, {len(todo)} to fetch", flush=True)
    parts = []
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {}
        for s in todo:
            futs[ex.submit(fetch, s)] = s
        for i, fu in enumerate(as_completed(futs), 1):
            r = fu.result()
            if r is not None:
                parts.append(r)
            if i % 500 == 0:
                print(f"  {i}/{len(todo)} fetched, {len(parts)} with data", flush=True)
                time.sleep(random.uniform(1, 3))
    if parts:
        new = pd.concat(parts, ignore_index=True)
        if os.path.exists(OUT):
            new = pd.concat([pd.read_parquet(OUT), new], ignore_index=True)
        new.to_parquet(OUT, index=False, compression="zstd")
        print(f"wrote {OUT}: {new['symbol'].nunique()} symbols", flush=True)
    if args.merge:
        merge()
    print("YAHOO_WEEKLY_DONE", flush=True)


def merge() -> None:
    """Add the Yahoo rows for symbols the FMP panel lacks (FMP first, always)."""
    if not os.path.exists(OUT):
        return
    y = pd.read_parquet(OUT)
    p = pd.read_parquet(PANEL)
    y = y[~y["symbol"].isin(set(p["symbol"]))]
    merged = pd.concat([p, y.astype(p.dtypes.to_dict())], ignore_index=True)
    merged.to_parquet(PANEL + ".tmp", index=False, compression="zstd")
    os.replace(PANEL + ".tmp", PANEL)
    print(f"merged {y['symbol'].nunique()} Yahoo symbols into {PANEL}: {merged['symbol'].nunique()} symbols",
          flush=True)


if __name__ == "__main__":
    main()
