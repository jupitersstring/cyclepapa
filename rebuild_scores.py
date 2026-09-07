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

    # Refresh momentum_12m from the live lynch tape BEFORE compute_asymmetry
    # so the upside leg (u_mom) uses fresh momentum in the SAME pass that
    # enrich later uses it for post_rally_factor — otherwise asymmetry_score
    # lags one full cycle behind. Stored momentum goes stale while the lynch
    # drive owns Yahoo (corr 0.13 with live). roc_12m is already a fraction.
    try:
        import numpy as _np
        _lm = pd.read_csv('lynch_reward_signals.csv',
                          usecols=['symbol', 'roc_12m', 'stale_tape',
                                   'last_bar_age_days']).drop_duplicates('symbol')
        _lm = df[['symbol']].merge(_lm, on='symbol', how='left')
        _roc = pd.to_numeric(_lm['roc_12m'], errors='coerce').values
        _st = pd.to_numeric(_lm['stale_tape'], errors='coerce').fillna(0).values
        _ag = pd.to_numeric(_lm['last_bar_age_days'], errors='coerce').values
        _ok = (~_np.isnan(_roc)) & (_st != 1) & (_np.isnan(_ag) | (_ag <= 21))
        if 'momentum_12m' in df.columns:
            _cur = pd.to_numeric(df['momentum_12m'], errors='coerce').values
            df['momentum_12m'] = _np.where(_ok, _roc, _cur)
            print(f'  refreshed momentum_12m from live tape on '
                  f'{int(_ok.sum())} rows before rescore', file=sys.stderr)
    except Exception as _e:
        print(f'  momentum refresh skipped ({_e})', file=sys.stderr)

    df = asymmetry_rank.compute_asymmetry(df)
    df = df.copy()  # de-fragment
    after = int(df['asymmetry_score'].notna().sum())
    from master_versions import versioned_replace
    df.to_csv(args.path + '.tmp', index=False)
    versioned_replace(args.path + '.tmp', args.path)   # atomic + pre-image snapshot
    print(f'  asymmetry_score coverage: {before:,} -> {after:,} of {len(df):,}',
          file=sys.stderr)


if __name__ == '__main__':
    main()
