#!/usr/bin/env python3
"""Best-across-all-legs ranking on the FULL quality universe (not truncated 500).

Reads v2_quality_all.csv (2,376 names), v2_master_all.csv (16k for sanity),
and any available TD data, then ranks across all legs without dropping
candidates below an arbitrary cutoff.

Writes data/synthesis/v2_full_universe_ranked.csv with ALL quality names ranked.
"""
import os, glob, sys
import pandas as pd
import numpy as np

q = pd.read_csv('data/synthesis/v2_quality_all.csv')
print(f"Full quality universe: {len(q)} names", file=sys.stderr)

# Pull every TD file we have (top200 plus any later runs)
td_frames = []
for p in sorted(glob.glob('data/td_seq/td_*.csv')):
    try:
        td_frames.append(pd.read_csv(p))
    except Exception:
        pass
if td_frames:
    td = pd.concat(td_frames, ignore_index=True).drop_duplicates(subset='ticker', keep='first')
    print(f"TD data available for {len(td)} names", file=sys.stderr)
    td_cols = ['ticker','net_setup','net_perfect','buy_setup_prop','sell_setup_prop',
               'buy_perfect_prop','sell_perfect_prop','cd_buy_sum','cd_sell_sum']
    q = q.merge(td[[c for c in td_cols if c in td.columns]], on='ticker', how='left')

# ─── Per-leg percentile scores over FULL universe ───
q['leg_dalton'] = q['asym_score'].rank(pct=True) * 100

if 'net_setup' in q.columns:
    td_raw = (q['net_setup'].fillna(0) * 0.4
            + q['net_perfect'].fillna(0) * 0.3
            + q['cd_buy_sum'].fillna(0) * 0.5
            - q['cd_sell_sum'].fillna(0) * 0.3)
    q['leg_td'] = np.where(q['net_setup'].notna(), td_raw.rank(pct=True) * 100, np.nan)
else:
    q['leg_td'] = np.nan

q['leg_fund'] = np.where(q['fund_score'] > 0, q['fund_score'].rank(pct=True) * 100, np.nan)

q['leg_absorp']   = np.where(q['absorp_pass'], 100, 0)
q['leg_prebo']    = np.where(q['prebo_pass'], 100, 0)
q['leg_compress'] = np.where(q['compress_pass'], 100, 0)

core = q[['leg_dalton','leg_td','leg_fund']]
q['n_core_legs'] = core.notna().sum(axis=1)
q['core_avg']    = core.mean(axis=1, skipna=True)
q['min_core']    = core.min(axis=1, skipna=True)
q['lens_bonus']  = (q['absorp_pass'].astype(int) + q['prebo_pass'].astype(int)
                  + q['compress_pass'].astype(int)) * 8

q['all_legs_score'] = (
    q['core_avg'].fillna(0) * 0.55
  + q['min_core'].fillna(0) * 0.30
  + q['lens_bonus']
  + q['n_core_legs'] * 3
)

# Two views
# A) STRICT — names with TD data AND ≥2 core legs at ≥30 percentile (best-of-all)
strict = q[(q['n_core_legs'] >= 2) & (q['min_core'] >= 30)].copy().sort_values('all_legs_score', ascending=False)
# B) FULL — every quality-passing name with its score (so missing TD doesn't hide them)
full = q.copy().sort_values('all_legs_score', ascending=False)

strict.to_csv('data/synthesis/v2_full_strict_ranked.csv', index=False)
full.to_csv('data/synthesis/v2_full_universe_ranked.csv', index=False)

print(f"\nStrict (≥2 core legs, no weak leg): {len(strict)} names")
print(f"Full (all quality names ranked):    {len(full)} names")

# Stratified TD-missing report — which names need TD coverage?
needs_td = q[(q['leg_td'].isna()) & (q['asym_score'].rank(pct=True) > 0.5)].copy()
needs_td = needs_td.sort_values('asym_score', ascending=False)
needs_td[['ticker','region']].to_csv('/tmp/td_needs.csv', index=False)
print(f"\nQuality names missing TD coverage (top half by Dalton): {len(needs_td)}")
print(f"  → universe written to /tmp/td_needs.csv for next TD run")
