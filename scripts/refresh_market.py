"""Refresh stale market data (valuation multiples + prices [+ surprises]) on cached
names via the proxy-compatible urllib Yahoo client, KEEPING their statement blocks
intact (so the EDGAR deep-history overlay is preserved).

Refreshes any cached, has-data name whose ``asof`` is older than ``--stale-days``.
Resumable (a refreshed name's asof becomes today, so a re-run skips it) and
rollback-proof: every ``--commit-every`` refreshes it re-archives cache/raw ->
data/raws.tar.gz and git-commits+pushes.

    python scripts/refresh_market.py --stale-days 20 --commit-every 800
    python scripts/refresh_market.py --limit 100 --no-git      # smoke test
"""
from __future__ import annotations

import argparse
import glob
import json
import subprocess
import sys
import tarfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from earnings_model import config, fundamentals as F, yahoo


def _git(*a):
    return subprocess.run(["git", *a], capture_output=True, text=True, cwd=config.REPO_ROOT)


def _branch():
    return _git("rev-parse", "--abbrev-ref", "HEAD").stdout.strip() or "HEAD"


def _archive_and_push(msg: str) -> None:
    with tarfile.open(config.DATA_DIR / "raws.tar.gz", "w:gz") as tar:
        for p in glob.glob(str(config.RAW_CACHE_DIR / "*.json")):
            tar.add(p, arcname=Path(p).name)
    _git("add", str(config.DATA_DIR / "raws.tar.gz"))
    res = _git("commit", "-m", msg)
    if "nothing to commit" in (res.stdout + res.stderr):
        return
    for i in range(4):
        if _git("push", "-u", "origin", _branch()).returncode == 0:
            return
        time.sleep(2 ** (i + 1))
    print("  [warn] push failed (raws archived locally)", flush=True)


def _stale_todo(uni: pd.DataFrame, stale_days: int) -> list[str]:
    cutoff = datetime.now(timezone.utc) - timedelta(days=stale_days)
    want = set(uni["symbol"].astype(str))
    todo = []
    for p in glob.glob(str(config.RAW_CACHE_DIR / "*.json")):
        sym = Path(p).stem
        if sym not in want and sym.replace("_", "/") not in want:
            continue
        try:
            d = json.loads(open(p).read())
        except Exception:
            continue
        if not d.get("fetch_ok"):
            continue                       # dataless gaps aren't worth a market refresh
        a = d.get("asof")
        try:
            if a and datetime.fromisoformat(a) < cutoff:
                todo.append(d.get("symbol", sym))
        except ValueError:
            continue
    return todo


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stale-days", type=int, default=20)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--commit-every", type=int, default=800)
    ap.add_argument("--rewarm-every", type=int, default=600)
    ap.add_argument("--no-git", action="store_true")
    args = ap.parse_args()

    uni = pd.read_parquet(config.UNIVERSE_PATH)
    sym_region = dict(zip(uni["symbol"].astype(str), uni.get("region", pd.Series())))
    todo = _stale_todo(uni, args.stale_days)
    if args.limit:
        todo = todo[: args.limit]
    print(f"refresh_market: {len(todo)} cached names with market data older than "
          f"{args.stale_days}d", flush=True)

    client = yahoo.YahooClient()
    done = since = 0
    for i, sym in enumerate(todo, 1):
        base = F.load_raw(sym, ttl_days=None, fail_ttl_days=None)
        if base is None:
            continue
        ws = sym_region.get(sym) in config.SURPRISE_REGIONS
        out = yahoo.refresh_market(sym, client, base, with_surprises=ws)
        if out.get("market_refreshed"):
            F.save_raw(sym, out)
            done += 1
        since += 1
        if i % args.rewarm_every == 0:
            client.warm()
        if i % 50 == 0 or i == len(todo):
            print(f"  [{i}/{len(todo)}] {done} refreshed", flush=True)
        if not args.no_git and since >= args.commit_every:
            _archive_and_push(f"refresh_market: +{i} ({done} refreshed)")
            since = 0
        time.sleep(config.RATE_MIN_INTERVAL)
    if not args.no_git and done:
        _archive_and_push(f"refresh_market complete: {done} names refreshed")
    print(f"FINISHED: {done}/{len(todo)} refreshed", flush=True)


if __name__ == "__main__":
    main()
