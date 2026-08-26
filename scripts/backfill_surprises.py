"""Back-fill EPS-surprise history for developed-market names — rollback-proof.

yfinance only carries EPS surprises (good coverage in US/UK/EU/CA/ANZ, sparse
elsewhere), one ``get_earnings_dates`` call per name and *heavily* rate-limited:
hammer it with no delay and it silently returns "no earnings dates" for liquid
names that obviously have data, so we pace with jitter + periodic breathers.

Crucially, progress is **committed to git as it is fetched** (the compact
``data/surprises.json`` via ``earnings_model.surprise_store``), so a hosted
container rollback — which reverts the ephemeral ``cache/`` — cannot wipe the
hard-won coverage. Resuming after a kill skips names already in the durable
store or the durable checked-set, so we don't re-hammer Yahoo from the top.

    python scripts/backfill_surprises.py                      # all developed plain tickers
    python scripts/backfill_surprises.py --regions US         # one market
    python scripts/backfill_surprises.py --commit-every 250   # git push cadence (hits)
"""
from __future__ import annotations

import argparse
import glob
import json
import random
import re
import sys
import time
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from earnings_model import config, fundamentals as F, surprise_store as S, util

# Skip clear non-operating securities (no EPS surprise) WITHOUT false-excluding
# real tickers. Two patterns only:
#   * a dash suffix  -> preferreds/classes/warrants (IVR-PC, BRK-A, FOO-WT)
#   * a 5-LETTER symbol whose 5th letter is a class indicator (Nasdaq convention):
#     W=warrant U=unit P/N/O/M=preferred/note R=right Q=bankruptcy E=delinquent
#     (LUNRW, NOVTU, POWWP, AGNCN). Crucially this needs exactly 5 letters, so
#     3-4 char names ending in those letters (AMZN, CRM, IBM, QCOM, MU, PLTR,
#     TTWO, LOW, UBER, ...) are NOT excluded — the old `[WURM]$|N$|O$|P$` was.
NONOP = re.compile(r"(-[A-Z]{1,3}$|^[A-Z]{4}[WUPNORMQE]$)")


def _persist_and_push(msg: str) -> None:
    """Commit ONLY the durable surprise files and push (retry/backoff inside).

    Runs against the repo root regardless of CWD (the old local _git helper
    inherited the caller's directory) and pushes whatever branch is checked out.
    """
    util.commit_paths_and_push(msg, [S.SURPRISES_PATH, S.CHECKED_PATH])


def targets(store: dict, checked: set[str], wanted: set[str]) -> list[str]:
    """Operating-likely plain tickers in `wanted` regions not yet fetched/attempted."""
    uni = pd.read_parquet(config.UNIVERSE_PATH)
    region = dict(zip(uni["symbol"], uni["region"])) if "region" in uni.columns else {}
    out = []
    for p in glob.glob(str(config.RAW_CACHE_DIR / "*.json")):
        try:
            r = json.loads(Path(p).read_text())
        except (json.JSONDecodeError, OSError):
            continue
        s = r.get("symbol")
        if not (s and r.get("fetch_ok")):
            continue
        if s in store or s in checked:          # already have it / already tried
            continue
        if region.get(s) in wanted and not NONOP.search(s):
            out.append(s)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--regions", default=",".join(config.SURPRISE_REGIONS),
                    help="comma-separated region codes")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--min-sleep", type=float, default=1.0)
    ap.add_argument("--max-sleep", type=float, default=2.0)
    ap.add_argument("--breather-every", type=int, default=200, help="calls between 30s rests")
    ap.add_argument("--commit-every", type=int, default=250, help="hits between git pushes")
    ap.add_argument("--no-git", action="store_true", help="skip git commits (local only)")
    args = ap.parse_args()
    wanted = {r.strip() for r in args.regions.split(",") if r.strip()}

    # Capture whatever surprises are currently in the cache into the durable store
    # first (so a fresh rollback's survivors are folded in, not lost), then push it.
    store = S.seed_from_cache()
    checked = S.load_checked()
    if not args.no_git:
        _persist_and_push("Seed durable surprise store from cache")

    todo = targets(store, checked, wanted)
    if args.limit:
        todo = todo[: args.limit]
    print(f"surprise back-fill {sorted(wanted)}: {len(todo)} to attempt "
          f"(durable store has {len(store)}, checked {len(checked)})", flush=True)

    session = F.make_session()
    got = since_commit = 0
    for i, sym in enumerate(todo, 1):
        raw = F.refresh_surprises(sym, session=session)
        checked.add(sym)
        if raw and raw.get("surprises"):
            store[sym] = raw["surprises"]
            got += 1
            since_commit += 1
        if i % 50 == 0 or i == len(todo):
            S.save(store)
            S.save_checked(checked)
            print(f"  [{i}/{len(todo)}] attempted, {got} new (store={len(store)})", flush=True)
        if not args.no_git and since_commit >= args.commit_every:
            S.save(store)            # flush before commit so the diff is current
            S.save_checked(checked)
            _persist_and_push(f"Back-fill surprises: store={len(store)} (+{got} this run)")
            since_commit = 0
        time.sleep(30 if i % args.breather_every == 0 else random.uniform(args.min_sleep, args.max_sleep))

    S.save(store)
    S.save_checked(checked)
    if not args.no_git:
        _persist_and_push(f"Back-fill surprises complete: store={len(store)} (+{got} this run)")
    print(f"FINISHED: +{got} new, durable store now {len(store)} names", flush=True)


if __name__ == "__main__":
    main()
