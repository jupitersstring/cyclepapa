"""One-off slower retry for US plain-ticker (operating-likely) names.

The general back-fill (scripts/backfill_surprises.py) caught the cooperative
names. A second pass with longer jitter rescues the ones Yahoo silently
rate-limited (PPG/KSS/TTWO-class liquids that returned 'no earnings dates'
under load). Plain tickers only — preferreds (-PC), warrants (W), units (U),
and CEFs are excluded by regex since they legitimately have no EPS surprise.
"""
from __future__ import annotations

import glob
import json
import random
import re
import sys
import time
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from earnings_model import config, fundamentals as F  # noqa: E402

NONOP = re.compile(r"(-P[A-Z]?$|[WURM]$|UN$|WS$|RT$|-A$|-B$|-C$|-D$|N$|O$|P$)")
CHECKED = config.CACHE_DIR / "surprises_checked.json"


def load_checked() -> set[str]:
    if CHECKED.exists():
        try:
            return set(json.loads(CHECKED.read_text()))
        except (json.JSONDecodeError, OSError):
            return set()
    return set()


def main() -> None:
    uni = pd.read_parquet(config.UNIVERSE_PATH)
    region = dict(zip(uni["symbol"], uni["region"]))

    targets = []
    for p in glob.glob(str(config.RAW_CACHE_DIR / "*.json")):
        try:
            r = json.loads(Path(p).read_text())
        except (json.JSONDecodeError, OSError):
            continue
        s = r.get("symbol")
        if not (s and r.get("fetch_ok")) or r.get("surprises"):
            continue
        if region.get(s) != "US" or NONOP.search(s):
            continue
        targets.append(s)

    print(f"slow US retry: {len(targets)} plain tickers", flush=True)
    # Clear the checked sidecar entries for these so prior rate-limited 'misses'
    # actually retry. The checked-set is updated in this loop too.
    checked = load_checked()
    checked.difference_update(targets)

    session = F.make_session()
    got = 0
    for i, sym in enumerate(targets, 1):
        raw = F.refresh_surprises(sym, session=session)
        if raw and raw.get("surprises"):
            got += 1
        checked.add(sym)
        if i % 50 == 0 or i == len(targets):
            CHECKED.write_text(json.dumps(sorted(checked)))
            print(f"  [{i}/{len(targets)}] attempted, {got} with surprise data", flush=True)
        # Every 200 calls give Yahoo a 30s breather to let the per-window limiter reset.
        if i % 200 == 0:
            time.sleep(30)
        else:
            time.sleep(random.uniform(1.0, 2.0))
    CHECKED.write_text(json.dumps(sorted(checked)))
    print(f"FINISHED: {got}/{len(targets)} names gained surprise data", flush=True)


if __name__ == "__main__":
    main()
