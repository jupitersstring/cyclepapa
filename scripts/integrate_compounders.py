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
cols = ['ticker','is_financial','roe_mean_4y','roe_min_4y','roe_std_4y','roa_mean_4y','enduring_roe',
        'roic_mean','roic_min','roic_std','roic_method_agreement','roic_years',
        'roiic_1y','roiic_2y','roiic_3y','roiic_acceleration','roiic_inflection',
        'cc_roic_fcf_latest','cc_roic_fcf_mean_4y','cc_roic_fcf_min_4y',
        'cc_roic_ocf_mean_4y','cc_roiic_1y','cc_roiic_3y','cc_roiic_acceleration',
        'cc_roiic_inflection','fcf_margin_mean_4y','cash_conversion_mean_4y',
        'cash_compounder','enduring_strict','enduring_loose','quality_compounder',
        'compounder_score','compounder_rank',
        'roic_mauboussin','roic_damodaran','roic_greenblatt','roic_croic','roic_dupont']
keep = [c for c in cols if c in comp.columns]
# Drop any prior compounder columns (re-run safety) so we don't create *_research dupes
_drop = [c for c in comp[keep].columns if c != 'ticker' and c in df.columns]
df = df.drop(columns=_drop, errors='ignore')
# Also drop stale *_research columns from earlier runs
df = df.drop(columns=[c for c in df.columns if c.endswith('_research')], errors='ignore')
merged = df.merge(comp[keep], on='ticker', how='left')

for c in ['enduring_strict','enduring_loose','quality_compounder','roiic_inflection',
          'cc_roiic_inflection','cash_compounder','enduring_roe','is_financial']:
    if c in merged.columns:
        merged[c] = merged[c].fillna(False).astype(bool)

merged.to_csv('data/synthesis/v2_universe_ranked_full_q.csv', index=False)
print(f"[integrate] merged {len(comp)} compounder rows into ranking", file=sys.stderr)
n_es = int(merged.get('enduring_strict', pd.Series(dtype=bool)).fillna(False).sum())
n_el = int(merged.get('enduring_loose',  pd.Series(dtype=bool)).fillna(False).sum())
n_ri = int(merged.get('roiic_inflection', pd.Series(dtype=bool)).fillna(False).sum())
print(f"  enduring strict: {n_es}  loose: {n_el}  ROIIC inflecting: {n_ri}", file=sys.stderr)
