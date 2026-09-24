"""Compute the MU-style consolidation-base overlay from cached monthly prices.

Local, no network: reads the monthly close history in cache/raw and writes
``data/base_metrics.parquet`` (git-tracked, durable, read directly by
``base_signal.attach`` inside step_analyze). Re-run whenever prices are refreshed.

    python scripts/fetch_base.py                 # raws -> data/base_metrics.parquet -> commit
    python scripts/fetch_base.py --no-git        # local only
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from earnings_model import base_signal, config, util


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-git", action="store_true")
    args = ap.parse_args()

    uni = pd.read_parquet(config.UNIVERSE_PATH)
    ov = base_signal.build_base_overlay(symbols=set(uni["symbol"].astype(str)))
    print(f"base overlay: {len(ov)} names | above 40w MA: {int(ov['base_above_ma'].sum())} | "
          f"base_score p90={ov['base_score'].quantile(.9):.2f}", flush=True)
    base_signal.save_overlay(ov)
    print(f"saved -> {base_signal.BASE_METRICS_PATH}", flush=True)
    if not args.no_git:
        util.commit_paths_and_push(
            f"Refresh base-consolidation overlay: {len(ov)} names",
            [base_signal.BASE_METRICS_PATH])


if __name__ == "__main__":
    main()
