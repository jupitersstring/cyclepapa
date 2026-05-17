"""Materialize the financedatabase universe to parquet + seed the alias CSV.

Usage:
    python scripts/build_universe.py
    python scripts/build_universe.py --country "United States" --refresh
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from social_arb import aliases as aliases_mod
from social_arb import universe
from social_arb.config import Config


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--country", default="United States")
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--consumer-only", action="store_true")
    args = parser.parse_args()

    cfg = Config()
    df = universe.build_universe(cfg, country=args.country, refresh=args.refresh)
    if args.consumer_only:
        df = universe.filter_consumer_focused(df)
        df.to_parquet(cfg.universe_parquet, index=False)
    print(f"universe: {len(df):,} rows -> {cfg.universe_parquet}")
    aliases_mod.write_seed_csv(cfg.aliases_csv)
    print(f"aliases : seed written -> {cfg.aliases_csv}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
