"""Fetch the FMP balance-sheet/quality overlay and save it as a durable parquet.

One bulk call (whole-market key-metrics-ttm) overlays ~26k of our names with the
balance-sheet / cash-flow / quality view the Yahoo+EDGAR pipeline lacks. Output is
``data/fmp_metrics.parquet`` (small, git-tracked, atomic write).

    export FMP_API_KEY=...            # never commit the key
    python scripts/fetch_fmp.py                 # fetch + save + commit
    python scripts/fetch_fmp.py --no-git        # local only
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from earnings_model import config, fmp, util


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-git", action="store_true")
    args = ap.parse_args()

    uni = pd.read_parquet(config.UNIVERSE_PATH)
    usyms = set(uni["symbol"].astype(str))
    print(f"fetching FMP bulk key-metrics-ttm (universe {len(usyms)}) ...", flush=True)
    ov = fmp.build_overlay(universe_symbols=usyms)
    matched = len(ov)
    print(f"overlay: {matched} names matched ({100*matched/len(usyms):.0f}% of universe)", flush=True)
    for c in ["fmp_net_debt_to_ebitda", "fmp_fcf_yield", "fmp_roic", "fmp_income_quality"]:
        if c in ov.columns:
            print(f"  {c}: {100*ov[c].notna().mean():.0f}% non-null", flush=True)
    fmp.save_overlay(ov)
    print(f"saved -> {fmp.FMP_METRICS_PATH}", flush=True)

    if not args.no_git:
        util.commit_paths_and_push(
            f"Fetch FMP overlay: {matched} names (balance-sheet/FCF/quality)",
            [fmp.FMP_METRICS_PATH])


if __name__ == "__main__":
    main()
