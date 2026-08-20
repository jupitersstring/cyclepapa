"""Retry universe names that previously returned no data (fetch_ok=False), to fill
coverage gaps after a paced bulk fetch. Rollback-proof: paced, and every
``--commit-every`` names it re-archives cache/raw -> data/raws.tar.gz and
git-commits+pushes, so a container reset costs one milestone, not the whole run.

    python scripts/fill_gaps.py --limit 80 --no-git     # gauge recovery rate
    python scripts/fill_gaps.py --commit-every 500       # full durable retry
"""
from __future__ import annotations

import argparse
import glob
import sys
import time
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from earnings_model import config, fundamentals as F, util




def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--commit-every", type=int, default=500)
    ap.add_argument("--min-sleep", type=float, default=0.5)
    ap.add_argument("--max-sleep", type=float, default=1.2)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--no-git", action="store_true")
    ap.add_argument("--max-retries", type=int, default=config.MAX_RETRIES,
                    help="fetch attempts per name; use 1 to skip retry-backoff on "
                         "the (mostly delisted) gap tail so the run isn't dominated "
                         "by futile 2/4/8s backoffs")
    args = ap.parse_args()

    uni = pd.read_parquet(config.UNIVERSE_PATH)
    # The documented contract: retry names whose CACHED raw has no data. Deriving
    # this from scored.parquet (as before) wrongly re-fetched anything fetched
    # after the last rebuild — and, through a broken transport, could overwrite
    # good raws with failures.
    todo = []
    for s_ in uni["symbol"].astype(str).tolist():
        r = F.load_raw(s_, ttl_days=None, fail_ttl_days=None)
        if r is None or not r.get("fetch_ok"):
            todo.append(s_)
    if args.limit:
        todo = todo[: args.limit]
    print(f"fill_gaps: retrying {len(todo)} no-data names", flush=True)

    # Adaptive, self-warming, self-healing session: paces internally and re-warms
    # the cookie/crumb after a run of failures. --min-sleep/--max-sleep retained
    # for back-compat but the adaptive limiter now governs pacing.
    mgr = F.SessionManager()
    recovered = since = 0
    for i, sym in enumerate(todo, 1):
        raw = mgr.fetch(sym, max_retries=args.max_retries)
        F.save_raw(sym, raw)
        if raw.get("fetch_ok"):
            recovered += 1
        since += 1
        if i % 50 == 0 or i == len(todo):
            extra = f", {mgr.refreshes} refresh(es)" if mgr.refreshes else ""
            print(f"  [{i}/{len(todo)}] {recovered} recovered{extra}", flush=True)
        if not args.no_git and since >= args.commit_every:
            util.archive_and_push(f"fill_gaps: +{i} retried ({recovered} recovered)")
            since = 0
    if not args.no_git:
        util.archive_and_push(f"fill_gaps complete: {len(todo)} retried, {recovered} recovered")
    print(f"FINISHED: recovered {recovered}/{len(todo)}", flush=True)


if __name__ == "__main__":
    main()
