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
import sys
import time
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from earnings_model import config, edgar, fundamentals as F, util




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
            util.archive_and_push(f"fetch_edgar: +{i} overlaid ({upgraded} upgraded)")
            since = 0
    if not args.no_git and upgraded:
        util.archive_and_push(f"fetch_edgar complete: {upgraded} US names on EDGAR annual backlog")
    print(f"FINISHED: {upgraded} upgraded to EDGAR annual / {len(todo)} attempted", flush=True)


if __name__ == "__main__":
    main()
