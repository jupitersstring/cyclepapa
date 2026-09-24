"""Refresh STATEMENT data (annual + quarterly revenue/EBITDA/EPS blocks) on cached
names via the proxy-compatible urllib Yahoo client, MERGING freshly reported
periods into the existing blocks so deep history (esp. the EDGAR annual overlay)
is preserved. Complements refresh_market.py, which updates only prices/multiples.

Targets any cached, has-data name that already carries a statement block and whose
``statements_refreshed`` stamp is missing or older than ``--stale-days`` (so a
first run hits everyone with statements, and a re-run resumes where it stopped).
Rollback-proof: every ``--commit-every`` refreshes it re-archives cache/raw ->
data/raws.tar.gz and git-commits+pushes (shrink-guarded, atomic).

    python scripts/refresh_statements.py --commit-every 800
    python scripts/refresh_statements.py --limit 100 --no-git      # smoke test
"""
from __future__ import annotations

import argparse
import glob
import json
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from earnings_model import config, fundamentals as F, util, yahoo


def _has_statements(d: dict) -> bool:
    return bool(((d.get("annual") or {}).get("dates")) or
                ((d.get("quarterly") or {}).get("dates")))


def _todo(uni: pd.DataFrame, stale_days: int) -> list[str]:
    """Cached, has-data, has-statements names not refreshed within stale_days."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=stale_days)
    want = set(uni["symbol"].astype(str))
    todo = []
    for p in glob.glob(str(config.RAW_CACHE_DIR / "*.json")):
        sym = Path(p).stem
        if sym not in want and sym.replace("_", "/") not in want:
            continue
        try:
            d = json.loads(open(p).read())
        except (json.JSONDecodeError, OSError):
            continue
        if not d.get("fetch_ok") or not _has_statements(d):
            continue
        sr = d.get("statements_refreshed")
        if sr:
            try:
                if datetime.fromisoformat(sr) >= cutoff:
                    continue                       # already refreshed recently
            except (ValueError, TypeError):
                pass
        todo.append(d.get("symbol", sym))
    return todo


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stale-days", type=int, default=25)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--commit-every", type=int, default=800)
    ap.add_argument("--rewarm-every", type=int, default=600)
    ap.add_argument("--no-git", action="store_true")
    args = ap.parse_args()

    uni = pd.read_parquet(config.UNIVERSE_PATH)
    todo = _todo(uni, args.stale_days)
    if args.limit:
        todo = todo[: args.limit]
    print(f"refresh_statements: {len(todo)} cached names with statements to refresh "
          f"(stamp older than {args.stale_days}d)", flush=True)

    client = yahoo.YahooClient()
    done = grew = since = 0
    for i, sym in enumerate(todo, 1):
        base = F.load_raw(sym, ttl_days=None, fail_ttl_days=None)
        if base is None:
            continue
        n_q0 = len((base.get("quarterly") or {}).get("dates") or [])
        out = yahoo.refresh_statements(sym, client, base)
        if out is not None:                        # None = keep cached (no usable data)
            if len((out.get("quarterly") or {}).get("dates") or []) > n_q0:
                grew += 1                          # gained at least one new quarter
            F.save_raw(sym, out)
            done += 1
        since += 1
        if i % args.rewarm_every == 0:
            client.warm()
        if i % 50 == 0 or i == len(todo):
            print(f"  [{i}/{len(todo)}] {done} refreshed, {grew} gained a new quarter", flush=True)
        if not args.no_git and since >= args.commit_every:
            util.archive_and_push(f"refresh_statements: +{i} ({done} refreshed, {grew} grew)")
            since = 0
        time.sleep(config.RATE_MIN_INTERVAL)
    if not args.no_git and done:
        util.archive_and_push(f"refresh_statements complete: {done} refreshed, {grew} grew")
    print(f"FINISHED: {done}/{len(todo)} refreshed, {grew} gained a new quarter", flush=True)


if __name__ == "__main__":
    main()
