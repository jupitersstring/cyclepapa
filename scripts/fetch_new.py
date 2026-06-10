"""Fetch fundamentals for universe names not yet in the cache — rollback-proof.

Used after a universe widening: pulls statements/prices/info for every symbol in
cache/universe.parquet that has no cache/raw entry yet, paced to dodge Yahoo's
rate limit. Resumable (skips cached). Every ``--commit-every`` fetched names it
archives cache/raw -> data/raws.tar.gz and git-commits+pushes, so a container
rollback costs at most one milestone instead of the whole run.

    python scripts/fetch_new.py
    python scripts/fetch_new.py --commit-every 400 --no-git
"""
from __future__ import annotations

import argparse
import glob
import json
import random
import subprocess
import sys
import tarfile
import time
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from earnings_model import config, fundamentals as F


def _git(*a):
    return subprocess.run(["git", *a], capture_output=True, text=True, cwd=config.REPO_ROOT)


def _branch():
    return _git("rev-parse", "--abbrev-ref", "HEAD").stdout.strip() or "HEAD"


def _archive_and_push(msg: str) -> None:
    n = 0
    with tarfile.open(config.DATA_DIR / "raws.tar.gz", "w:gz") as tar:
        for p in glob.glob(str(config.RAW_CACHE_DIR / "*.json")):
            tar.add(p, arcname=Path(p).name); n += 1
    _git("add", str(config.DATA_DIR / "raws.tar.gz"))
    res = _git("commit", "-m", msg)
    if "nothing to commit" in (res.stdout + res.stderr):
        return
    for i in range(4):
        if _git("push", "-u", "origin", _branch()).returncode == 0:
            return
        time.sleep(2 ** (i + 1))
    print(f"  [warn] push failed (archived {n} raws locally)", flush=True)


def _cached_symbols() -> set[str]:
    out = set()
    for p in glob.glob(str(config.RAW_CACHE_DIR / "*.json")):
        out.add(Path(p).stem)            # filename stem == symbol (with '/'->'_')
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--commit-every", type=int, default=400)
    ap.add_argument("--min-sleep", type=float, default=0.6)
    ap.add_argument("--max-sleep", type=float, default=1.4)
    ap.add_argument("--no-git", action="store_true")
    args = ap.parse_args()

    uni = pd.read_parquet(config.UNIVERSE_PATH)
    have = _cached_symbols()
    todo = [s for s in uni["symbol"].tolist()
            if str(s).replace("/", "_") not in have]
    if args.limit:
        todo = todo[: args.limit]
    print(f"fetch_new: {len(todo)} uncached names to fetch "
          f"({len(have)} already cached)", flush=True)

    session = F.make_session()
    ok = since = 0
    for i, sym in enumerate(todo, 1):
        raw = F.fetch_raw(sym, session=session)
        F.save_raw(sym, raw)             # cache failures too (short negative TTL)
        if raw.get("fetch_ok"):
            ok += 1
        since += 1
        if i % 25 == 0 or i == len(todo):
            print(f"  [{i}/{len(todo)}] fetched, {ok} with data", flush=True)
        if not args.no_git and since >= args.commit_every:
            _archive_and_push(f"fetch_new milestone: +{i} fetched ({ok} with data)")
            since = 0
        time.sleep(random.uniform(args.min_sleep, args.max_sleep))
    if not args.no_git:
        _archive_and_push(f"fetch_new complete: {len(todo)} attempted, {ok} with data")
    print(f"FINISHED: {ok}/{len(todo)} new names have data", flush=True)


if __name__ == "__main__":
    main()
