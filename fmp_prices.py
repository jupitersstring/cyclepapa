"""Weekly price panel (2010->today) for the event study of long bases that
explode ("goes nowhere for two years, then triples in three months").

Source: FMP historical-price-eod/dividend-adjusted (split- AND dividend-
adjusted OHLC, split-adjusted volume) — total-return prices, so a base that
"went nowhere" is measured the way a holder experienced it.

Daily payloads are NOT cached (46k names x ~4,000 days would be tens of GB);
each series is reduced in memory to W-FRI bars:
    open  high  low  close  volume  dvol (sum of daily close x volume)
Dollar volume is split-invariant (adjusted price x adjusted volume), so it is
the tradability filter at any historical date.

SURVIVORSHIP: the universe is today's names PLUS companies delisted since
2013 (FMP delisted-companies). Without them the study would only see the
bases that survived — exactly the bias that flatters "buy the base".

Outputs (local, large -> .gitignore):
    fmp_price_parts/part_*.parquet   resumable chunks
    fmp_weekly_prices.parquet        consolidated panel (symbol, week, ...)
    fmp_price_universe.csv           symbol, source (current|delisted), status
"""
from __future__ import annotations

import argparse
import glob
import os
import time
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pandas as pd

import fmp_client as fc

PARTS = "fmp_price_parts"
OUT = "fmp_weekly_prices.parquet"
UNIVERSE = "fmp_price_universe.csv"
START = "2010-01-01"


def delisted_universe(since: str = "2013-01-01") -> pd.DataFrame:
    rows, page = [], 0
    while True:
        chunk = fc.get_json("delisted-companies", {"page": page, "limit": 100}, ttl=fc.TTL_SLOW) or []
        if not chunk:
            break
        rows.extend(chunk)
        page += 1
        if page > 2000:
            break
    d = pd.DataFrame(rows)
    if d.empty:
        return pd.DataFrame(columns=["symbol", "source"])
    d = d[pd.to_datetime(d["delistedDate"], errors="coerce") >= pd.Timestamp(since)]
    return pd.DataFrame({"symbol": d["symbol"].astype(str).unique(), "source": "delisted"})


def weekly_bars(sym: str) -> pd.DataFrame | None:
    for attempt in range(12):
        try:
            data = fc.get_json("historical-price-eod/dividend-adjusted",
                               {"symbol": sym, "from": START}, cache=False)
            break
        except fc.FMPError as exc:
            if "Limit Reach" in str(exc) or "429" in str(exc):
                time.sleep(30 * (attempt + 1))
                continue
            return None
    else:
        return None
    if not data:
        return None
    d = pd.DataFrame(data)
    need = {"date", "adjOpen", "adjHigh", "adjLow", "adjClose", "volume"}
    if not need.issubset(d.columns):
        return None
    d["date"] = pd.to_datetime(d["date"], errors="coerce")
    d = d.dropna(subset=["date", "adjClose"]).sort_values("date")
    d = d[d["adjClose"] > 0]
    if len(d) < 60:
        return None
    d["dvol"] = d["adjClose"] * d["volume"].fillna(0)
    w = d.set_index("date").resample("W-FRI").agg(
        {"adjOpen": "first", "adjHigh": "max", "adjLow": "min", "adjClose": "last",
         "volume": "sum", "dvol": "sum"}).dropna(subset=["adjClose"])
    w = w.rename(columns={"adjOpen": "open", "adjHigh": "high", "adjLow": "low", "adjClose": "close"})
    w = w.reset_index().rename(columns={"date": "week"})
    w.insert(0, "symbol", sym)
    for c in ("open", "high", "low", "close"):
        w[c] = w[c].astype("float32")
    w["volume"] = w["volume"].astype("float64")
    w["dvol"] = w["dvol"].astype("float64")
    return w


def consolidate() -> int:
    files = sorted(glob.glob(os.path.join(PARTS, "part_*.parquet")))
    if not files:
        return 0
    p = pd.concat([pd.read_parquet(f) for f in files], ignore_index=True)
    p = p.drop_duplicates(["symbol", "week"], keep="last").sort_values(["symbol", "week"])
    p.to_parquet(OUT + ".tmp", index=False, compression="zstd")
    os.replace(OUT + ".tmp", OUT)
    return len(p)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--chunk", type=int, default=500)
    ap.add_argument("--max", type=int, default=0)
    ap.add_argument("--consolidate", action="store_true")
    args = ap.parse_args()
    if args.consolidate:
        print("rows:", consolidate())
        return
    cur = pd.read_csv("archetype_tags.csv", usecols=["symbol", "archetype_count"], low_memory=False)
    cur = cur.sort_values("archetype_count", ascending=False)
    uni = pd.concat([pd.DataFrame({"symbol": cur["symbol"].astype(str), "source": "current"}),
                     delisted_universe()], ignore_index=True).drop_duplicates("symbol")
    if args.max:
        uni = uni.head(args.max)
    os.makedirs(PARTS, exist_ok=True)
    done = set()
    if os.path.exists(UNIVERSE):
        u0 = pd.read_csv(UNIVERSE)
        done = set(u0.loc[u0["status"].notna(), "symbol"].astype(str))
    todo = [s for s in uni["symbol"] if s not in done]
    src = dict(zip(uni["symbol"], uni["source"]))
    print(f"prices: {len(uni)} symbols ({(uni['source'] == 'delisted').sum()} delisted), "
          f"{len(done)} done, {len(todo)} to fetch", flush=True)
    part = len(glob.glob(os.path.join(PARTS, "part_*.parquet")))
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        for i in range(0, len(todo), args.chunk):
            batch = todo[i:i + args.chunk]
            res = list(ex.map(weekly_bars, batch))
            frames = [r for r in res if r is not None]
            if frames:
                part += 1
                pd.concat(frames, ignore_index=True).to_parquet(
                    os.path.join(PARTS, f"part_{part:05d}.parquet"), index=False, compression="zstd")
            st = pd.DataFrame({"symbol": batch, "source": [src[s] for s in batch],
                               "status": ["ok" if r is not None else "empty" for r in res]})
            st.to_csv(UNIVERSE, mode="a", header=not os.path.exists(UNIVERSE), index=False)
            s = fc.cache_stats()
            print(f"  prices {min(i + args.chunk, len(todo))}/{len(todo)} | ok {len(frames)}/{len(batch)} "
                  f"| hit_rate={s['hit_rate']}", flush=True)
    print("consolidated rows:", consolidate(), flush=True)


if __name__ == "__main__":
    main()
