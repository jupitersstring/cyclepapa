#!/usr/bin/env python3
"""Rank compounders using v2 multi-method ROIC + ROIIC inflection emphasis.

Score blends:
  • Roic_mean × multi-method agreement (Lindy confidence)
  • Recent ROIIC level + inflection flag (compounders turning the corner)
  • Cheap (low EV/EBIT, high FCF yield)
  • Structural stability (low roic_std)
  • Growth (rev_g)
"""
import os, glob, sys
import pandas as pd
import numpy as np

frames = []
for p in sorted(glob.glob('data/research/roic_*.csv')):
    if 'v1_partial' in p: continue
    try:
        df = pd.read_csv(p)
        if len(df): frames.append(df)
    except Exception: pass

if not frames:
    print("[rank] no v2 research files yet", file=sys.stderr); sys.exit(0)

r = pd.concat(frames, ignore_index=True, sort=False).drop_duplicates(subset='ticker', keep='first')
print(f"[rank] research rows: {len(r)}", file=sys.stderr)

# Detect which schema (v1 had roic_mean_4y, v2 has roic_mean_4y_med + agreement)
is_v2 = 'roic_mean_4y_med' in r.columns
print(f"  schema: v2={is_v2}", file=sys.stderr)

if is_v2:
    r['roic_mean'] = r['roic_mean_4y_med']
    r['roic_min']  = r['roic_min_4y_med']
    r['roic_std']  = r['roic_std_4y_med']
else:
    r['roic_mean'] = r.get('roic_mean_4y')
    r['roic_min']  = r.get('roic_min_4y')
    r['roic_std']  = r.get('roic_std_4y')

# Lindy quality tiers
has_hist = r['has_history'].fillna(False)
r['enduring_strict'] = (
    has_hist
    & (r['roic_min'].fillna(-1) >= 0.15)
    & (r['roic_std'].fillna(99) <= 0.08)
    & (r.get('roic_years', r.get('years_history', 0)).fillna(0) >= 3)
    & (r.get('roic_method_agreement', 0.5).fillna(0.5) >= 0.4)
)
r['enduring_loose'] = (
    has_hist
    & (r['roic_min'].fillna(-1) >= 0.10)
    & (r['roic_std'].fillna(99) <= 0.12)
    & (r.get('roic_years', r.get('years_history', 0)).fillna(0) >= 3)
)
r['quality_compounder'] = (
    has_hist
    & (r['roic_mean'].fillna(-1) >= 0.10)
    & (r.get('roic_years', r.get('years_history', 0)).fillna(0) >= 3)
)

# ROIIC inflection (accrual)
if 'roiic_inflection' not in r.columns: r['roiic_inflection'] = False
r['roiic_inflection'] = r['roiic_inflection'].fillna(False).astype(bool)
if 'roiic_1y' not in r.columns: r['roiic_1y'] = np.nan
if 'roiic_3y' not in r.columns: r['roiic_3y'] = r.get('roiic_3y', np.nan)

# Cash-on-cash ROIIC inflection
if 'cc_roiic_inflection' not in r.columns: r['cc_roiic_inflection'] = False
r['cc_roiic_inflection'] = r['cc_roiic_inflection'].fillna(False).astype(bool)

# Cash-quality compounder (real cash returns, not just accruals)
r['cash_compounder'] = (
    has_hist
    & (r.get('cc_roic_fcf_min_4y', pd.Series(-1, index=r.index)).fillna(-1) >= 0.08)
    & (r.get('cc_roic_fcf_mean_4y', pd.Series(-1, index=r.index)).fillna(-1) >= 0.12)
    & (r.get('cash_conversion_mean_4y', pd.Series(-1, index=r.index)).fillna(-1) >= 0.6)
)

def comp_rank(row):
    if not bool(row.get('has_history', False)): return 0
    s = 0
    rm = row.get('roic_mean'); r1 = row.get('roiic_1y'); r3 = row.get('roiic_3y')
    eb = row.get('ev_ebit'); fy = row.get('fcf_yield')
    rg = row.get('rev_g'); agree = row.get('roic_method_agreement')

    if pd.notna(rm) and rm > 0: s += min(float(rm) * 150, 35)
    if pd.notna(r1) and r1 > 0: s += min(float(r1) * 60, 25)
    elif pd.notna(r3) and r3 > 0: s += min(float(r3) * 40, 20)
    if row.get('roiic_inflection'): s += 20

    # Cash-on-cash add-ons
    cc_mean = row.get('cc_roic_fcf_mean_4y')
    if pd.notna(cc_mean) and cc_mean > 0: s += min(float(cc_mean) * 100, 20)
    cc1 = row.get('cc_roiic_1y')
    if pd.notna(cc1) and cc1 > 0: s += min(float(cc1) * 40, 15)
    if row.get('cc_roiic_inflection'): s += 15
    cash_conv = row.get('cash_conversion_mean_4y')
    if pd.notna(cash_conv) and cash_conv >= 0.8: s += 5
    if row.get('cash_compounder'): s += 10

    if pd.notna(eb) and eb > 0 and eb < 50: s += max(0, (15 - float(eb)))
    if pd.notna(fy): s += min(max(float(fy), -0.05) * 100, 10)
    if pd.notna(rg): s += min(max(float(rg), -0.10) * 30, 8)
    if row.get('enduring_strict'): s += 25
    elif row.get('enduring_loose'): s += 12
    if pd.notna(agree): s += float(agree) * 5
    return round(float(s), 2)

r['compounder_score'] = r.apply(comp_rank, axis=1)
r['compounder_rank'] = r['compounder_score'].rank(ascending=False, method='dense').astype(int)

r.to_csv('data/synthesis/compounders_ranked.csv', index=False)
top = r.sort_values('compounder_score', ascending=False).head(50)
top.to_csv('data/synthesis/compounders_top50.csv', index=False)

print(f"\n[rank] enduring strict: {int(r['enduring_strict'].sum())}", file=sys.stderr)
print(f"[rank] enduring loose:  {int(r['enduring_loose'].sum())}", file=sys.stderr)
print(f"[rank] ROIIC inflecting: {int(r['roiic_inflection'].sum())}", file=sys.stderr)
print(f"[rank] enduring + ROIIC inflecting: {int((r['enduring_loose'] & r['roiic_inflection']).sum())}", file=sys.stderr)

# Display top 25
cols_show = ['ticker','name','sector','industry','mktCap','roic_mean','roic_min','roic_std',
             'roic_method_agreement','roiic_1y','roiic_3y','roiic_inflection',
             'ev_ebit','ev_ebitda','fcf_yield','rev_g','enduring_strict','compounder_score']
cols_present = [c for c in cols_show if c in top.columns]
print("\nTop 25 compounders:")
print(top.head(25)[cols_present].to_string(index=False))
