"""Fetch fundamentals for uncached universe names via the proxy-compatible urllib
Yahoo client (earnings_model.yahoo) — the transport that works when curl_cffi's
impersonated TLS is reset by the agent proxy.

Resumable (skips names already in cache/raw) and rollback-proof: every
``--commit-every`` fetched names it re-archives cache/raw -> data/raws.tar.gz and
git-commits+pushes, so a container reset costs at most one milestone. Re-warms the
Yahoo cookie/crumb periodically.

    python scripts/widen_fetch.py --commit-every 500
    python scripts/widen_fetch.py --limit 200 --no-git    # smoke test
"""
from __future__ import annotations

import argparse
import glob
import sys
import time
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from earnings_model import config, fundamentals as F, util, yahoo


def _archive_and_push(msg: str) -> None:
    """Checkpoint the raws AND the (possibly widened) universe parquet."""
    try:
        util.archive_raws()
    except RuntimeError as err:
        print(f"  [warn] checkpoint skipped: {err}", flush=True)
        return
    util.commit_paths_and_push(msg, [config.DATA_DIR / "raws.tar.gz",
                                     config.DATA_DIR / "universe.parquet"])


def _cached() -> set[str]:
    return {Path(p).stem for p in glob.glob(str(config.RAW_CACHE_DIR / "*.json"))}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--commit-every", type=int, default=500)
    ap.add_argument("--rewarm-every", type=int, default=600)
    ap.add_argument("--no-git", action="store_true")
    args = ap.parse_args()

    uni = pd.read_parquet(config.UNIVERSE_PATH)
    have = _cached()
    todo = [s for s in uni["symbol"].astype(str).tolist()
            if s.replace("/", "_") not in have]
    if args.limit:
        todo = todo[: args.limit]
    sym_region = dict(zip(uni["symbol"].astype(str), uni.get("region", pd.Series())))
    print(f"widen_fetch: {len(todo)} uncached names via urllib Yahoo client "
          f"({len(have)} already cached)", flush=True)

    client = yahoo.YahooClient()
    ok = since = 0
    for i, sym in enumerate(todo, 1):
        ws = sym_region.get(sym) in config.SURPRISE_REGIONS
        raw = yahoo.fetch_raw(sym, client, with_surprises=ws)
        F.save_raw(sym, raw)
        ok += bool(raw.get("fetch_ok"))
        since += 1
        if i % args.rewarm_every == 0:
            client.warm()                       # refresh cookie/crumb
        if i % 50 == 0 or i == len(todo):
            print(f"  [{i}/{len(todo)}] fetched, {ok} with data", flush=True)
        if not args.no_git and since >= args.commit_every:
            _archive_and_push(f"widen_fetch: +{i} fetched ({ok} with data)")
            since = 0
        time.sleep(config.RATE_MIN_INTERVAL)
    if not args.no_git and ok:
        _archive_and_push(f"widen_fetch complete: {len(todo)} attempted, {ok} with data")
    print(f"FINISHED: {ok}/{len(todo)} new names have data", flush=True)


if __name__ == "__main__":
    main()
