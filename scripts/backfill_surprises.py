"""Back-fill EPS-surprise history for developed-market names that lack it.

yfinance only carries EPS surprises, with good coverage in the US/UK/EU/CA/ANZ
and little elsewhere, so we only attempt those regions (config.SURPRISE_REGIONS).
Each name is one cheap ``get_earnings_dates`` call via ``refresh_surprises`` (no
statement/price re-pull). Progress is saved per-name into cache/raw, and a sidecar
``surprises_checked.json`` records every attempted symbol so that resuming after a
container kill skips names we've already tried (including genuine no-coverage ones)
instead of re-hammering Yahoo from the top.

    python scripts/backfill_surprises.py            # all developed names missing surprises
    python scripts/backfill_surprises.py --limit 500
"""
from __future__ import annotations

import argparse
import glob
import json
import random
import sys
import time
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from earnings_model import config, fundamentals as F

CHECKED_PATH = config.CACHE_DIR / "surprises_checked.json"


def _load_checked() -> set[str]:
    if CHECKED_PATH.exists():
        try:
            return set(json.loads(CHECKED_PATH.read_text()))
        except (json.JSONDecodeError, OSError):
            return set()
    return set()


def _save_checked(checked: set[str]) -> None:
    CHECKED_PATH.write_text(json.dumps(sorted(checked)))


def targets(checked: set[str], regions: tuple[str, ...] | None = None) -> list[str]:
    """Developed-region, fetch_ok, currently-empty-surprise names not yet checked."""
    uni = pd.read_parquet(config.UNIVERSE_PATH)
    region = dict(zip(uni["symbol"], uni["region"])) if "region" in uni.columns else {}
    allowed = regions if regions is not None else config.SURPRISE_REGIONS
    out = []
    for p in glob.glob(str(config.RAW_CACHE_DIR / "*.json")):
        try:
            r = json.loads(Path(p).read_text())
        except (json.JSONDecodeError, OSError):
            continue
        s = r.get("symbol")
        if not (s and r.get("fetch_ok")):
            continue
        if r.get("surprises"):       # already has data
            continue
        if s in checked:             # already attempted this run-series
            continue
        if region.get(s) in allowed:
            out.append(s)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--regions", default=None,
                    help="comma-separated region codes (default: config.SURPRISE_REGIONS)")
    ap.add_argument("--reset", action="store_true",
                    help="clear the checked-set for the targeted regions before running "
                         "(use after a rate-limited run silently missed names)")
    ap.add_argument("--min-sleep", type=float, default=0.4,
                    help="min seconds between Yahoo calls (jitter prevents rate-limiting)")
    ap.add_argument("--max-sleep", type=float, default=0.9)
    args = ap.parse_args()

    regions = tuple(r.strip() for r in args.regions.split(",")) if args.regions else None
    checked = _load_checked()
    if args.reset:
        uni = pd.read_parquet(config.UNIVERSE_PATH)
        region = dict(zip(uni["symbol"], uni["region"]))
        allowed = regions if regions is not None else config.SURPRISE_REGIONS
        before = len(checked)
        checked = {s for s in checked if region.get(s) not in allowed}
        print(f"reset: dropped {before - len(checked)} checked entries in regions {allowed}",
              flush=True)
    todo = targets(checked, regions=regions)
    if args.limit:
        todo = todo[: args.limit]
    print(f"surprise back-fill: {len(todo)} developed names to attempt "
          f"({len(checked)} already checked)", flush=True)

    session = F.make_session()
    got = 0
    for i, sym in enumerate(todo, 1):
        raw = F.refresh_surprises(sym, session=session)
        if raw and raw.get("surprises"):
            got += 1
        checked.add(sym)
        if i % 50 == 0 or i == len(todo):
            _save_checked(checked)
            print(f"  [{i}/{len(todo)}] attempted, {got} with surprise data", flush=True)
        time.sleep(random.uniform(args.min_sleep, args.max_sleep))
    _save_checked(checked)
    print(f"FINISHED: {got}/{len(todo)} names gained surprise data", flush=True)


if __name__ == "__main__":
    main()
