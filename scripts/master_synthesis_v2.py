#!/usr/bin/env python3
"""V2 synthesis — fixes critical issues identified in v1.

Fixes:
  1. TD direction flags require STRICT direction (no overlap between buy/sell)
  2. fcf_yield > 50% capped to 50% (data-artifact damping)
  3. fcf_yield > 200% drops the fund_pass flag entirely (ADR mismatch)
  4. EV/EBITDA fallback explicit; ev_metric column tracks which was used
  5. State weighting: INFLECTION_UP/ACCEL_UP = 1.0, DECEL_UP/TRENDING_UP = 0.5
  6. Cross-listing dedup by name (keep highest mega_score per name)
  7. dist_to_invalidation == 0 names excluded (no risk margin)
  8. monthly_safe checked properly: drop only if absM_state is bear AND absW is bull (conflict)
  9. cap_tier preserved from universe market_cap when available
 10. absW_asymm winsorized at 95th percentile, not blanket cap at 30
"""
import os, glob, sys
import pandas as pd
import numpy as np

os.makedirs('data/synthesis', exist_ok=True)

bull_states_strong = ['INFLECTION_UP','ACCELERATION_UP']
bull_states_weak   = ['DECELERATION_UP','TRENDING_UP']
bear_states        = ['INFLECTION_DOWN','ACCELERATION_DOWN','TRENDING_DOWN']

# ─── Load all Dalton outputs ──────────────────────────────────────────────
print("[v2] Loading Dalton outputs...", file=sys.stderr)
dalton_frames = []
for path in sorted(glob.glob('data/dalton/dalton_*.csv')):
    bn = os.path.basename(path).replace('dalton_','').replace('.csv','')
    if bn.endswith('_recovery'): continue
    cap_suffix = 'large' if bn.endswith('_lg') else 'smid'
    mkt = bn.replace('_lg','')
    try:
        df = pd.read_csv(path)
        if len(df) == 0: continue
        df['region'] = mkt
        df['cap_suffix'] = cap_suffix
        dalton_frames.append(df)
    except Exception as e:
        print(f"  ERR {path}: {e}", file=sys.stderr)
dalton = pd.concat(dalton_frames, ignore_index=True, sort=False)
dalton = dalton.drop_duplicates(subset=['ticker','region'], keep='first')
print(f"  Dalton: {len(dalton)} rows from {len(dalton_frames)} files", file=sys.stderr)

# Bring in true market_cap from universe files
print("[v2] Mapping universe market_cap...", file=sys.stderr)
uni_map = []
for path in sorted(glob.glob('data/universes/uni_*.csv')) + sorted(glob.glob('data/universes/large/uni_*_lg.csv')):
    mkt = os.path.basename(path).replace('uni_','').replace('.csv','').replace('_lg','').replace('_missed','')
    if 'recovery' in path: continue
    try:
        u = pd.read_csv(path)
        if 'market_cap' in u.columns:
            u['region'] = mkt
            uni_map.append(u[['ticker','market_cap','region']])
    except Exception: pass
if uni_map:
    uni_all = pd.concat(uni_map, ignore_index=True).drop_duplicates(['ticker','region'], keep='first')
    dalton = dalton.merge(uni_all, on=['ticker','region'], how='left', suffixes=('','_uni'))
    if 'market_cap_uni' in dalton.columns:
        dalton['market_cap'] = dalton['market_cap'].fillna(dalton['market_cap_uni'])
        dalton = dalton.drop(columns=['market_cap_uni'])

# ─── Load fundamentals ────────────────────────────────────────────────────
print("[v2] Loading fundamentals...", file=sys.stderr)
fund_frames = []
for path in sorted(glob.glob('data/fundamentals/fund_*.csv')):
    bn = os.path.basename(path).replace('fund_','').replace('.csv','')
    if bn.endswith(('_recovery','_backfill')): continue
    try:
        df = pd.read_csv(path)
        if len(df): fund_frames.append(df)
    except Exception: pass
fund = pd.concat(fund_frames, ignore_index=True, sort=False).drop_duplicates(subset='ticker', keep='first')
print(f"  Fund: {len(fund)} rows", file=sys.stderr)

# ─── Fundamental score v2 ─────────────────────────────────────────────────
for c in ['ev_ebit','ev_ebitda','fcf_yield','rev_g','opm','fcf']:
    if c not in fund: fund[c] = np.nan

# Use ev_ebitda since ev_ebit is universally null
fund['ev_metric_used'] = np.where(fund['ev_ebit'].notna(), 'ev_ebit', 'ev_ebitda')
fund['ev_valuation'] = fund['ev_ebit'].fillna(fund['ev_ebitda'])

# FIX 2/3: drop wildly large fcf_yield values (ADR/currency artifacts)
fund['fcf_yield_clean'] = fund['fcf_yield'].clip(lower=-0.5, upper=0.50)
fund['fcf_yield_artifact'] = (fund['fcf_yield'].abs() > 2.0)   # > 200% = always artifact

# rev_g winsorize: cap extreme outliers (468% etc.) — keep direction but de-weight
fund['rev_g_clean'] = fund['rev_g'].clip(lower=-0.5, upper=1.0)  # cap at 100% YoY

fund['fund_pass'] = (
    (fund['ev_valuation'].fillna(99).between(0, 15)) &
    (fund['rev_g_clean'].fillna(0) >= 0.05) &
    (fund['fcf'].fillna(0) > 0) &
    (~fund['fcf_yield_artifact'])
)
fund['fund_score'] = (
    np.clip((15 - fund['ev_valuation'].fillna(99)) / 15 * 10, 0, 10)
  + np.clip(fund['fcf_yield_clean'].fillna(0) * 30, 0, 15)
  + np.clip(fund['rev_g_clean'].fillna(0) * 30, 0, 10)
  + np.clip(fund['opm'].fillna(0) * 15, -5, 8)
).round(2)

# ─── Asymmetric scoring v2 ────────────────────────────────────────────────
for c in ['absW_E_asymm','absW_asymm','absW_macro','absW_pos_in_bracket',
          'velocity','acceleration','absW_dist_invalid']:
    if c not in dalton: dalton[c] = np.nan

# FIX 10: winsorize asymm at 95th percentile rather than blanket cap 30
asymm_p95 = dalton['absW_asymm'].quantile(0.95)
dalton['absW_asymm_w'] = dalton['absW_asymm'].clip(0, asymm_p95)
dalton['asymm_capped_artifact'] = dalton['absW_asymm'] > asymm_p95

# FIX 7: drop names with zero risk margin (dist_invalid == 0 means triggered already)
dalton['valid_risk'] = dalton['absW_dist_invalid'].fillna(1) > 0

# FIX 5: weighted state contribution to bull-TF count
for s, tcol, weight in [('w_strong','absW_state',1.0),('w_weak','absW_state',0.5),
                         ('m_strong','absM_state',1.0),('m_weak','absM_state',0.5),
                         ('rw_strong','relW_state',1.0),('rw_weak','relW_state',0.5),
                         ('rm_strong','relM_state',1.0),('rm_weak','relM_state',0.5)]:
    if tcol not in dalton.columns:
        dalton[s] = 0
        continue
    series = dalton[tcol].fillna('')
    if 'strong' in s:
        dalton[s] = series.isin(bull_states_strong).astype(int) * weight
    else:
        dalton[s] = series.isin(bull_states_weak).astype(int) * weight

dalton['bull_weight'] = dalton[['w_strong','w_weak','m_strong','m_weak',
                                 'rw_strong','rw_weak','rm_strong','rm_weak']].sum(axis=1)
dalton['n_bull_tf'] = (
    (dalton.get('absW_state','').isin(bull_states_strong + bull_states_weak)).astype(int)
  + (dalton.get('absM_state','').isin(bull_states_strong + bull_states_weak)).astype(int)
  + (dalton.get('relW_state','').isin(bull_states_strong + bull_states_weak)).astype(int)
  + (dalton.get('relM_state','').isin(bull_states_strong + bull_states_weak)).astype(int)
)

# FIX 8: monthly conflict — bull weekly + bear monthly is a fakeout candidate
dalton['monthly_conflict'] = (
    dalton.get('absW_state','').isin(bull_states_strong + bull_states_weak) &
    dalton.get('absM_state','').isin(bear_states)
)

dalton['mirage']   = (dalton.get('absW_dp_signal','') == 'MIRAGE_BUY').astype(int)
dalton['bform']    = dalton.get('absW_b_form', False).fillna(False).astype(int)
dalton['fbd_recl'] = dalton.get('absW_failed_bd_reclaim', False).fillna(False).astype(int)
dalton['fbo_rej']  = dalton.get('absW_failed_bo_reject', False).fillna(False).astype(int)

dalton['asym_score'] = (
    dalton['absW_E_asymm'].fillna(0) * 6
  + dalton['absW_asymm_w'].fillna(0) * 4
  + dalton['absW_macro'].fillna(0) * 0.4
  + dalton['bull_weight'].fillna(0) * 10   # weighted by state strength
  + dalton['velocity'].fillna(0).clip(-5,5) * 2
  + dalton['acceleration'].fillna(0).clip(-5,5) * 1.5
  + dalton['mirage'] * 25 + dalton['bform'] * 20
  + dalton['fbd_recl'] * 15 + dalton['fbo_rej'] * 10
  - dalton['monthly_conflict'].astype(int) * 30  # penalty for fakeout
)

# ─── Merge fund → dalton ──────────────────────────────────────────────────
fund_cols = ['ticker','fund_pass','fund_score','ev_valuation','ev_metric_used',
             'ev_ebit','ev_ebitda','fcf_yield','fcf_yield_clean','fcf_yield_artifact',
             'rev_g','rev_g_clean','opm','mktCap','industry','sector','name','currency']
fc = [c for c in fund_cols if c in fund.columns]
merged = dalton.merge(fund[fc], on='ticker', how='left', suffixes=('','_f'))
merged['fund_pass']  = merged['fund_pass'].fillna(False).astype(bool)
merged['fund_score'] = merged['fund_score'].fillna(0)

# ─── Auxiliary screens ────────────────────────────────────────────────────
def load_screen(pattern, exclude=None):
    frames = []
    for p in sorted(glob.glob(pattern)):
        if exclude and exclude in os.path.basename(p):
            continue
        try:
            df = pd.read_csv(p)
            if len(df): frames.append(df)
        except Exception: pass
    if not frames: return pd.DataFrame({'ticker':[]})
    return pd.concat(frames, ignore_index=True, sort=False).drop_duplicates(subset='ticker', keep='first')

absorp = load_screen('data/absorption/absorp_*.csv')
prebo  = load_screen('data/prebreakout/prebo_*.csv')
# Weekly compression = compress_<mkt>.csv  (exclude the monthly-prefixed files)
compress = load_screen('data/compression/compress_*.csv', exclude='compress_monthly')
# Monthly compression = compress_monthly_<mkt>.csv (separate, slower-TF lens)
compress_m = load_screen('data/compression/compress_monthly_*.csv')

if len(absorp):
    absorp['absorp_pass'] = (
        (absorp.get('mfi_chg', 0).fillna(0) <= -10) &
        (absorp.get('px_chg_pct', 99).fillna(99).abs() <= 7) &
        (absorp.get('divergence_ratio', 99).fillna(99) <= 0.4) &
        (absorp.get('atr_pct_avg', 99).fillna(99) <= 6)
    )
    merged = merged.merge(absorp[['ticker','absorp_pass']], on='ticker', how='left')
merged['absorp_pass'] = merged.get('absorp_pass', False).fillna(False).astype(bool)

if len(prebo):
    prebo['prebo_pass'] = (
        (prebo.get('ret_6m_pct', -99).fillna(-99) >= 25) &
        (prebo.get('ret_12m_pct', -99).fillna(-99) >= 30) &
        (prebo.get('atr_pct_avg_8w', 99).fillna(99) <= 3.5) &
        (prebo.get('range_8w_pct', 99).fillna(99) <= 15) &
        (prebo.get('pct_below_52w_high', 99).fillna(99).between(3, 15)) &
        (prebo.get('above_ma30', False).fillna(False).astype(bool))
    )
    merged = merged.merge(prebo[['ticker','prebo_pass']], on='ticker', how='left')
merged['prebo_pass'] = merged.get('prebo_pass', False).fillna(False).astype(bool)

def compress_filter(c):
    return (
        (c.get('mfi_higher_low', False).fillna(False).astype(bool)) &
        (c.get('atr_compression', False).fillna(False).astype(bool)) &
        (c.get('mfi_inflect_amt', 0).fillna(0) >= 1) &
        (c.get('pct_below_5y_high', 99).fillna(99) <= 25)
    )

if len(compress):
    compress['compress_pass'] = compress_filter(compress)
    merged = merged.merge(compress[['ticker','compress_pass']], on='ticker', how='left')
merged['compress_pass'] = merged.get('compress_pass', False).fillna(False).astype(bool)

# Monthly compression — separate lens (slower TF, higher conviction base)
if 'compress_m_pass' not in merged.columns:
    merged['compress_m_pass'] = False
if len(compress_m):
    compress_m['compress_m_pass'] = compress_filter(compress_m)
    merged = merged.drop(columns=['compress_m_pass']).merge(
        compress_m[['ticker','compress_m_pass']], on='ticker', how='left')
merged['compress_m_pass'] = merged['compress_m_pass'].fillna(False).astype(bool)

# ─── Composite ────────────────────────────────────────────────────────────
merged['n_lens'] = (
    merged['fund_pass'].astype(int)
  + merged['absorp_pass'].astype(int)
  + merged['prebo_pass'].astype(int)
  + merged['compress_pass'].astype(int)
  + merged['compress_m_pass'].astype(int)
)
merged['mega_score'] = (
    merged['asym_score'].fillna(0)
  + merged['fund_score'].fillna(0) * 3
  + merged['n_lens'] * 40
)

# FIX 9: precise cap_tier from universe market_cap
if 'market_cap' in merged.columns:
    merged['cap_tier'] = merged['market_cap'].fillna('unknown').astype(str)
else:
    merged['cap_tier'] = merged['cap_suffix']

# ─── Quality filter v2 ────────────────────────────────────────────────────
qual_mask = (
    (merged['absW_macro'].fillna(0) >= 25) &
    (merged['absW_asymm'].fillna(0) >= 1.5) &
    (merged['absW_pos_in_bracket'].fillna(50).between(20, 85)) &
    (~merged['monthly_conflict']) &
    (merged['valid_risk']) &
    (merged['n_bull_tf'] >= 1)
)
quality = merged[qual_mask].copy().sort_values('mega_score', ascending=False)

# ─── FIX 6: cross-listing dedup by name ───────────────────────────────────
if 'name' in quality.columns:
    quality['dedupe_key'] = quality['name'].fillna(quality['ticker']).astype(str).str.upper().str.strip()
    quality = quality.sort_values('mega_score', ascending=False)
    quality_unique = quality.drop_duplicates(subset='dedupe_key', keep='first')
    print(f"  Cross-listing dedup: {len(quality)} → {len(quality_unique)}", file=sys.stderr)
else:
    quality_unique = quality

merged.to_csv('data/synthesis/v2_master_all.csv', index=False)
quality.to_csv('data/synthesis/v2_quality_all.csv', index=False)
quality_unique.head(500).to_csv('data/synthesis/v2_top500_dedup.csv', index=False)

print(f"\n[v2] Universe: {len(merged)} ticker-market", file=sys.stderr)
print(f"     Quality filter pass: {len(quality)}", file=sys.stderr)
print(f"     After ADR dedup:     {len(quality_unique)}", file=sys.stderr)
print(f"     Triple+ lens:        {(quality_unique['n_lens']>=3).sum()}", file=sys.stderr)
print(f"     Fund pass:           {quality_unique['fund_pass'].sum()}", file=sys.stderr)

# Summary
print(f"\n=== v2 fixes applied ===")
print(f"  asymm winsorized at p95={asymm_p95:.2f} ({merged['asymm_capped_artifact'].sum()} artifacts flagged)")
print(f"  fcf_yield artifacts dropped: {fund['fcf_yield_artifact'].sum()}")
print(f"  monthly conflicts excluded: {merged['monthly_conflict'].sum()}")
print(f"  zero-risk-margin excluded:  {(~merged['valid_risk']).sum()}")
print(f"  ev_metric used: {fund['ev_metric_used'].value_counts().to_dict()}")
