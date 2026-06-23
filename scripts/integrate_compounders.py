#!/usr/bin/env python3
"""Merge compounder research (ROIC/ROIIC/structural) into the full ranking."""
import os, glob, sys
import pandas as pd

base = ('data/synthesis/v2_universe_ranked_full_q.csv'
        if os.path.exists('data/synthesis/v2_universe_ranked_full_q.csv')
        else 'data/synthesis/v2_universe_ranked_full.csv')
df = pd.read_csv(base)

if not os.path.exists('data/synthesis/compounders_ranked.csv'):
    print("[integrate] no compounders_ranked yet", file=sys.stderr)
    sys.exit(0)

comp = pd.read_csv('data/synthesis/compounders_ranked.csv')
cols = ['ticker','roic_latest','roic_mean_4y','roic_min_4y','roic_std_4y',
        'roiic_3y','reinvest_rate','structural_quality','enduring_compounder',
        'quality_compounder','compounder_score','compounder_rank',
        'years_history','ev_ebit','ev_ebitda','ev_fcf']
keep = [c for c in cols if c in comp.columns]
merged = df.merge(comp[keep], on='ticker', how='left', suffixes=('','_research'))

# Fill missing structural flags as False (not just NaN)
for c in ['structural_quality','enduring_compounder','quality_compounder']:
    if c in merged.columns:
        merged[c] = merged[c].fillna(False).astype(bool)

merged.to_csv('data/synthesis/v2_universe_ranked_full_q.csv', index=False)
print(f"[integrate] merged {len(comp)} compounder rows into ranking", file=sys.stderr)
n_end = int(merged['enduring_compounder'].sum()) if 'enduring_compounder' in merged else 0
n_q   = int(merged['quality_compounder'].sum())  if 'quality_compounder'  in merged else 0
print(f"  enduring: {n_end}  quality: {n_q}", file=sys.stderr)
