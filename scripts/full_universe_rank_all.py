#!/usr/bin/env python3
"""Rank the ENTIRE Dalton universe (~16k rows), not just quality-filtered subset.

Same scoring methodology as full_universe_rank.py but:
  • Quality filter REMOVED — every Dalton-scored ticker gets ranked
  • Quality flag added as a column (so user can filter post-hoc)
  • TD overlay applied where available
  • All-legs composite computed for every name

Outputs:
  data/synthesis/v2_universe_ranked_full.csv  — all ~16k rows
"""
import os, glob, sys
import pandas as pd
import numpy as np

# Start from the master_all (full Dalton + fund + lens merge, pre quality filter)
df = pd.read_csv('data/synthesis/v2_master_all.csv')
print(f"Full universe (all Dalton rows): {len(df)}", file=sys.stderr)

# Pull all TD data
td_frames = []
for p in sorted(glob.glob('data/td_seq/td_*.csv')):
    if 'merged' in p or 'remain' in p: continue
    try: td_frames.append(pd.read_csv(p))
    except: pass
if td_frames:
    td = pd.concat(td_frames, ignore_index=True).drop_duplicates(subset='ticker', keep='first')
    print(f"TD data for {len(td)} tickers", file=sys.stderr)
    td_cols = ['ticker','net_setup','net_perfect','buy_setup_prop','sell_setup_prop',
               'buy_perfect_prop','sell_perfect_prop','cd_buy_sum','cd_sell_sum']
    df = df.merge(td[[c for c in td_cols if c in td.columns]], on='ticker', how='left')

# Per-leg percentile scores over FULL universe
df['leg_dalton'] = df['asym_score'].rank(pct=True) * 100

if 'net_setup' in df.columns:
    td_raw = (df['net_setup'].fillna(0) * 0.4
            + df['net_perfect'].fillna(0) * 0.3
            + df['cd_buy_sum'].fillna(0) * 0.5
            - df['cd_sell_sum'].fillna(0) * 0.3)
    df['leg_td'] = np.where(df['net_setup'].notna(), td_raw.rank(pct=True) * 100, np.nan)
else:
    df['leg_td'] = np.nan

df['leg_fund'] = np.where(df['fund_score'] > 0, df['fund_score'].rank(pct=True) * 100, np.nan)

df['leg_absorp']   = np.where(df['absorp_pass'].fillna(False), 100, 0)
df['leg_prebo']    = np.where(df['prebo_pass'].fillna(False), 100, 0)
df['leg_compress'] = np.where(df['compress_pass'].fillna(False), 100, 0)
if 'compress_m_pass' not in df.columns: df['compress_m_pass'] = False

# AUDIT FIX — TD selection bias: TD Sequential was only run on a pre-selected
# top set, so leg_td has a median of ~96 and artificially inflates the composite
# for the 7% of names that have it. Exclude leg_td from the core average to avoid
# rewarding mere data-availability; keep it as a separate informational column and
# a small bonus only when it independently confirms (oversold/overbought).
core = df[['leg_dalton','leg_fund']]
df['n_core_legs'] = core.notna().sum(axis=1)
df['core_avg']    = core.mean(axis=1, skipna=True)
df['min_core']    = core.min(axis=1, skipna=True)
df['lens_bonus']  = (df['absorp_pass'].fillna(False).astype(int)
                   + df['prebo_pass'].fillna(False).astype(int)
                   + df['compress_pass'].fillna(False).astype(int)
                   + df['compress_m_pass'].fillna(False).astype(int)) * 8
# TD confirmation bonus: only added when TD genuinely signals (not just present)
df['td_bonus'] = 0.0
if 'net_setup' in df.columns:
    td_oversold = (pd.to_numeric(df['net_setup'], errors='coerce') >= 25)
    df.loc[td_oversold.fillna(False), 'td_bonus'] = 6.0

df['all_legs_score'] = (
    df['core_avg'].fillna(0) * 0.60
  + df['min_core'].fillna(0) * 0.30
  + df['lens_bonus']
  + df['td_bonus']
  + df['n_core_legs'] * 2
)

# Quality flag (does the name pass the asymmetric quality filter?)
# STRICT — original tight filter
df['quality_pass'] = (
    (df['absW_macro'].fillna(0) >= 25)
  & (df['absW_asymm'].fillna(0) >= 1.5)
  & (df['absW_pos_in_bracket'].fillna(50).between(20, 85))
  & (~df.get('monthly_conflict', False).fillna(False))
  & (df.get('valid_risk', True).fillna(True))
  & (df['n_bull_tf'].fillna(0) >= 1)
)

# LOOSE — broader net for borderline asymmetric setups
df['quality_pass_loose'] = (
    (df['absW_macro'].fillna(0) >= 18)
  & (df['absW_asymm'].fillna(0) >= 1.15)
  & (df['absW_pos_in_bracket'].fillna(50).between(15, 90))
  & (~df.get('monthly_conflict', False).fillna(False))
  & (df.get('valid_risk', True).fillna(True))
  & (df['n_bull_tf'].fillna(0) >= 1)
)

df = df.sort_values('all_legs_score', ascending=False).reset_index(drop=True)
df.to_csv('data/synthesis/v2_universe_ranked_full.csv', index=False)

print(f"Universe ranked: {len(df)} names", file=sys.stderr)
print(f"  Quality-pass STRICT: {df['quality_pass'].sum()} ({df['quality_pass'].mean()*100:.0f}%)", file=sys.stderr)
print(f"  Quality-pass LOOSE:  {df['quality_pass_loose'].sum()} ({df['quality_pass_loose'].mean()*100:.0f}%)", file=sys.stderr)
print(f"  Region distribution:", file=sys.stderr)
print(df['region'].value_counts().to_string(), file=sys.stderr)
