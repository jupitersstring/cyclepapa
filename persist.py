#!/usr/bin/env python3
"""
Durability layer — the fix for "expensive cache lived only in the ephemeral
sandbox". Snapshots the canonical caches into git-tracked, compressed, SHARDED
parquet under data/ (each shard < GitHub's 100 MB limit), and restores them
into the working .cache/ on a fresh sandbox.

CONTRACT
  data/      = durable, committed source of truth (survives sandbox resets)
  .cache/    = ephemeral working pickles, rebuilt from data/ at session start

  python3 persist.py snapshot   # .cache  -> data/   (run after expensive fetches)
  python3 persist.py restore    # data/   -> .cache  (run on a fresh sandbox)

Then `git add data && git commit && git push` to make it durable. A SessionStart
hook runs `restore` automatically (see .claude/settings.json).
"""
from __future__ import annotations

import glob
import json
import os
import shutil
import sys

import pandas as pd

ROOT = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(ROOT, ".cache")
DATA = os.path.join(ROOT, "data")
SHARD_MB = 80                     # keep each parquet well under GitHub's 100 MB
# canonical OHLCV caches worth persisting (legacy *_400/_1223 are superseded)
OHLCV = {"ohlcvdict_1d_20y.pkl": "1d", "ohlcvdict_1wk_20y.pkl": "1wk",
         "ohlcvdict_90m_60d.pkl": "90m"}


def _to_long(d: dict) -> pd.DataFrame:
    frames = []
    for s, df in d.items():
        x = df.dropna()
        if not len(x):
            continue
        frames.append(pd.DataFrame({"symbol": s, "date": x.index.values,
                                    "close": x["Close"].astype("float32").values,
                                    "vol": x["Volume"].astype("float32").values}))
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def _shard_write(long: pd.DataFrame, outdir: str):
    """Write the long frame into N parquet shards (split by symbol) so each file
    stays under SHARD_MB."""
    os.makedirs(outdir, exist_ok=True)
    for old in glob.glob(os.path.join(outdir, "part_*.parquet")):
        os.remove(old)
    syms = sorted(long["symbol"].unique())
    # estimate shards from a probe write of the whole thing
    probe = os.path.join(outdir, "_probe.parquet")
    long.to_parquet(probe, compression="zstd", index=False)
    total_mb = os.path.getsize(probe) / 1e6
    os.remove(probe)
    n = max(1, int(total_mb // SHARD_MB) + 1)
    buckets = {s: i % n for i, s in enumerate(syms)}
    long = long.assign(_b=long["symbol"].map(buckets))
    for b, g in long.groupby("_b"):
        g.drop(columns="_b").to_parquet(
            os.path.join(outdir, f"part_{b:03d}.parquet"), compression="zstd", index=False)
    return n, total_mb


def snapshot():
    os.makedirs(os.path.join(DATA, "ohlcv"), exist_ok=True)
    os.makedirs(os.path.join(DATA, "meta"), exist_ok=True)
    os.makedirs(os.path.join(DATA, "fundamentals"), exist_ok=True)
    manifest = {}
    for pkl, key in OHLCV.items():
        p = os.path.join(CACHE, pkl)
        if not os.path.exists(p):
            continue
        long = _to_long(pd.read_pickle(p))
        n, mb = _shard_write(long, os.path.join(DATA, "ohlcv", key))
        manifest[key] = {"rows": int(len(long)), "symbols": int(long["symbol"].nunique()),
                         "shards": n, "asof": str(long["date"].max())[:10]}
        print(f"[snapshot] {key}: {len(long):,} rows, {long['symbol'].nunique()} symbols "
              f"-> {n} shard(s) (~{mb:.0f}MB zstd)")
    # small but expensive: fundamentals CSVs + meta json
    for f in glob.glob(os.path.join(CACHE, "*.json")):
        shutil.copy2(f, os.path.join(DATA, "meta", os.path.basename(f)))
    for pat in ("gov_*.csv", "insider_*.csv", "ev_ebitda*.csv", "forecast.csv", "uk_fc.csv"):
        for f in glob.glob(os.path.join(CACHE, pat)):
            shutil.copy2(f, os.path.join(DATA, "fundamentals", os.path.basename(f)))
    json.dump(manifest, open(os.path.join(DATA, "MANIFEST.json"), "w"), indent=2)
    print(f"[snapshot] manifest -> data/MANIFEST.json  ({sum(m['rows'] for m in manifest.values()):,} total rows)")


def _from_long(long: pd.DataFrame) -> dict:
    out = {}
    for s, g in long.groupby("symbol", observed=True):
        idx = pd.DatetimeIndex(g["date"])
        out[str(s)] = pd.DataFrame({"Close": g["close"].astype(float).values,
                                    "Volume": g["vol"].astype(float).values}, index=idx).sort_index()
    return out


def restore():
    os.makedirs(CACHE, exist_ok=True)
    for pkl, key in OHLCV.items():
        d = os.path.join(DATA, "ohlcv", key)
        shards = sorted(glob.glob(os.path.join(d, "part_*.parquet")))
        if not shards:
            continue
        long = pd.concat([pd.read_parquet(s) for s in shards], ignore_index=True)
        pd.to_pickle(_from_long(long), os.path.join(CACHE, pkl))
        print(f"[restore] {pkl}: {len(long):,} rows -> {long['symbol'].nunique()} symbols")
    for f in glob.glob(os.path.join(DATA, "meta", "*.json")):
        shutil.copy2(f, os.path.join(CACHE, os.path.basename(f)))
    for f in glob.glob(os.path.join(DATA, "fundamentals", "*.csv")):
        shutil.copy2(f, os.path.join(CACHE, os.path.basename(f)))
    print("[restore] done — caches rehydrated from data/")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "snapshot"
    (snapshot if cmd == "snapshot" else restore)()
