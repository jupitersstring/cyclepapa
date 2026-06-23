#!/usr/bin/env python3
"""Rank compounders from primary-research data — high incremental ROIC,
structurally enduring, cheap valuation. Small/micro/nano cap preferred.

Reads data/research/roic_*.csv → ranks by composite score.

Output columns added to the synthesis:
  roic_latest, roic_mean_4y, roic_min_4y, roic_std_4y, roiic_3y,
  reinvest_rate, structural_quality, comp_score, compounder_rank,
  enduring_compounder (the bool flag)
"""
import os, glob, sys
import pandas as pd
import numpy as np

frames = []
for p in sorted(glob.glob('data/research/roic_*.csv')):
    try:
        df = pd.read_csv(p)
        if len(df): frames.append(df)
    except Exception: pass

if not frames:
    print("[rank] no research files yet", file=sys.stderr)
    sys.exit(0)

research = pd.concat(frames, ignore_index=True, sort=False).drop_duplicates(subset='ticker', keep='first')
print(f"[rank] research rows: {len(research)}", file=sys.stderr)
has_hist = research['has_history'].fillna(False)
research_h = research[has_hist].copy()
print(f"  with history: {len(research_h)}", file=sys.stderr)

# Enduring compounder definition (strict)
research['enduring_compounder'] = (
    has_hist
    & (research['roic_min_4y'].fillna(-1) >= 0.15)        # never below 15%
    & (research['roic_std_4y'].fillna(99) <= 0.08)         # stable
    & (research['years_history'].fillna(0) >= 3)           # at least 3 years
)
# Loose compounder
research['quality_compounder'] = (
    has_hist
    & (research['roic_mean_4y'].fillna(-1) >= 0.12)
    & (research['roic_min_4y'].fillna(-1) >= 0.06)
    & (research['years_history'].fillna(0) >= 3)
)

# Composite rank — enduring + high ROIIC + cheap
def comp_rank(row):
    if not bool(row.get('has_history', False)): return 0
    score = 0
    rm = row.get('roic_mean_4y'); ri = row.get('roiic_3y')
    eb = row.get('ev_ebit'); fy = row.get('fcf_yield')
    rg = row.get('rev_g')
    if pd.notna(rm) and rm > 0: score += min(rm * 200, 40)        # 20% ROIC = 40 pts
    if pd.notna(ri) and ri > 0 and ri < 5: score += min(ri * 80, 30)  # 25% ROIIC = ~20 pts
    if pd.notna(eb) and eb > 0 and eb < 50: score += max(0, (20 - eb) * 1.5)   # ev/ebit 10 = +15 pts
    if pd.notna(fy) and fy > -0.2: score += min(fy * 100, 15)
    if pd.notna(rg): score += min(max(rg, -0.2) * 30, 10)
    if row.get('enduring_compounder'): score += 25
    elif row.get('quality_compounder'): score += 10
    return round(float(score), 2)

research['compounder_score'] = research.apply(comp_rank, axis=1)
research['compounder_rank'] = research['compounder_score'].rank(ascending=False, method='dense').astype(int)

research.to_csv('data/synthesis/compounders_ranked.csv', index=False)
top = research.sort_values('compounder_score', ascending=False).head(50)
top.to_csv('data/synthesis/compounders_top50.csv', index=False)

print(f"\n[rank] structural-quality compounders: {int(research['enduring_compounder'].sum())}", file=sys.stderr)
print(f"[rank] quality compounders (loose):     {int(research['quality_compounder'].sum())}", file=sys.stderr)
print(f"\nTop 30 compounders by composite score:")
cols_show = ['ticker','name','sector','industry','mktCap','roic_mean_4y','roiic_3y',
             'roic_min_4y','ev_ebit','ev_ebitda','fcf_yield','rev_g','enduring_compounder','compounder_score']
print(top.head(30)[[c for c in cols_show if c in top.columns]].to_string(index=False))
