"""Overlay SEC EDGAR's authoritative, full-history annual statements onto the
cached yfinance raws for every US filer in the universe.

EDGAR (XBRL companyfacts) gives 10-15+ years of filed annual statements vs
yfinance's ~4, straight from the 10-K, with no meaningful rate wall. This pulls
companyfacts for each US ticker that has a CIK, merges the annual block into the
ticker's cache/raw record (keeping yfinance's market data + quarterly), and
re-saves it so the pipeline recomputes long-horizon metrics off the real backlog.

Resumable (skips already-merged names), SEC-paced (<=8 req/s via earnings_model.edgar),
and rollback-proof: every ``--commit-every`` upgrades it re-archives cache/raw ->
data/raws.tar.gz and git-commits+pushes, so a container reset costs one milestone.

    python scripts/fetch_edgar.py --limit 200 --no-git    # gauge the upgrade
    python scripts/fetch_edgar.py --commit-every 500        # full durable backfill
"""
from __future__ import annotations

import argparse
import glob
import subprocess
import sys
import tarfile
import time
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from earnings_model import config, edgar, fundamentals as F


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


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--commit-every", type=int, default=500)
    ap.add_argument("--refresh", action="store_true", help="re-pull even if already merged")
    ap.add_argument("--no-git", action="store_true")
    args = ap.parse_args()

    uni = pd.read_parquet(config.UNIVERSE_PATH)
    cmap = edgar.ticker_cik_map()
    # Every universe ticker that is a US SEC filer (has a CIK). yfinance suffixed
    # foreign symbols (7203.T, 0700.HK) simply aren't in the domestic CIK map.
    filers = [(s, cmap[str(s).upper()]) for s in uni["symbol"].astype(str)
              if str(s).upper() in cmap]
    print(f"fetch_edgar: {len(filers)} US filers in universe have a CIK", flush=True)

    todo = []
    for sym, cik in filers:
        if not args.refresh:
            cached = F.load_raw(sym, ttl_days=None, fail_ttl_days=None)
            if cached is not None and cached.get("statement_source") == "edgar-annual":
                continue
        todo.append((sym, cik))
    if args.limit:
        todo = todo[: args.limit]
    print(f"  {len(todo)} to overlay (skipping already-merged)", flush=True)

    upgraded = no_base = no_edgar = since = 0
    for i, (sym, cik) in enumerate(todo, 1):
        base = F.load_raw(sym, ttl_days=None, fail_ttl_days=None)
        if base is None:
            no_base += 1
        else:
            try:
                e = edgar.fetch_statements(sym, cik=cik, refresh=args.refresh)
            except Exception:
                e = None
            if e is None:
                no_edgar += 1
            else:
                merged = edgar.merge_into_raw(base, e)
                if merged.get("statement_source") == "edgar-annual":
                    F.save_raw(sym, merged)
                    upgraded += 1
                else:
                    no_edgar += 1          # EDGAR had no more history than yf
                # The merged raw carries the data + a resume flag, so the bulky
                # companyfacts intermediate (~3MB) is no longer needed; drop it to
                # keep the ephemeral cache flat (it is cheaply re-fetchable).
                facts_path = config.CACHE_DIR / "edgar" / f"CIK{cik:010d}.json"
                facts_path.unlink(missing_ok=True)
        since += 1
        if i % 50 == 0 or i == len(todo):
            print(f"  [{i}/{len(todo)}] {upgraded} upgraded, {no_edgar} no-gain, "
                  f"{no_base} no-yf-base", flush=True)
        if not args.no_git and since >= args.commit_every:
            _archive_and_push(f"fetch_edgar: +{i} overlaid ({upgraded} upgraded)")
            since = 0
    if not args.no_git and upgraded:
        _archive_and_push(f"fetch_edgar complete: {upgraded} US names on EDGAR annual backlog")
    print(f"FINISHED: {upgraded} upgraded to EDGAR annual / {len(todo)} attempted", flush=True)


if __name__ == "__main__":
    main()
