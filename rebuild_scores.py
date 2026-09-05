"""Post-merge fix + rescore step for the master.

Two pipeline gaps the audit found, folded into one idempotent step that
runs AFTER fill_gaps + derive and BEFORE enrich/archetype:

  1. fix_pipeline.fix_asymmetry_global — FX-convert to market_cap_usd (incl.
     sub-currency units), dedup dual-listings (Thai NVDR / Indian .BO), and
     nan-out ratio anomalies. Without this, market-cap gates read local
     currency (a $70M Korean name looks like 95e9) and duplicates double-count.

  2. asymmetry_rank.compute_asymmetry — recompute upside_score /
     downside_floor_score / asymmetry_score for the WHOLE universe. The
     append+enrich chain never re-scored, so the 17k FDB-expansion names had
     asymmetry_score = NaN -> entry_today_asymmetry = 0 -> buried at the
     bottom of every ranked book. compute_asymmetry renormalises over present
     components, so expansion names' yartseva/inflection/value signals now
     produce real, comparable scores.

Idempotent: FX + anomaly clamps recompute the same values; dedup is a no-op
once the duplicates are gone.
"""
from __future__ import annotations
import argparse
import sys

import pandas as pd

import fix_pipeline
import asymmetry_rank


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--path', default='asymmetry_global.csv')
    args = ap.parse_args()

    # 1) FX + dedup + anomaly (rewrites the file in place)
    fix_pipeline.fix_asymmetry_global(args.path, args.path)

    # 2) Recompute the asymmetry scores over the full (deduped, FX'd) universe
    df = pd.read_csv(args.path, low_memory=False)
    before = int(df['asymmetry_score'].notna().sum()) if 'asymmetry_score' in df.columns else 0
    df = asymmetry_rank.compute_asymmetry(df)
    df = df.copy()  # de-fragment
    after = int(df['asymmetry_score'].notna().sum())
    df.to_csv(args.path, index=False)
    print(f'  asymmetry_score coverage: {before:,} -> {after:,} of {len(df):,}',
          file=sys.stderr)


if __name__ == '__main__':
    main()
