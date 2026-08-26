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
import sys
import time
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from earnings_model import config, fundamentals as F, util


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

    # Adaptive, self-warming, self-healing session: paces internally and re-warms
    # the cookie/crumb after a run of failures. --min-sleep/--max-sleep retained
    # for back-compat but the adaptive limiter now governs pacing.
    mgr = F.SessionManager()
    ok = since = 0
    for i, sym in enumerate(todo, 1):
        raw = mgr.fetch(sym)
        F.save_raw(sym, raw)             # cache failures too (short negative TTL)
        if raw.get("fetch_ok"):
            ok += 1
        since += 1
        if i % 25 == 0 or i == len(todo):
            extra = f", {mgr.refreshes} refresh(es)" if mgr.refreshes else ""
            print(f"  [{i}/{len(todo)}] fetched, {ok} with data{extra}", flush=True)
        if not args.no_git and since >= args.commit_every:
            util.archive_and_push(f"fetch_new milestone: +{i} fetched ({ok} with data)")
            since = 0
    if not args.no_git:
        util.archive_and_push(f"fetch_new complete: {len(todo)} attempted, {ok} with data")
    print(f"FINISHED: {ok}/{len(todo)} new names have data", flush=True)


if __name__ == "__main__":
    main()
