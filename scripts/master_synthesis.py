#!/usr/bin/env python3
"""Master synthesis across all 21 markets × small+large cap buckets.

Loads:
  • All Dalton complete outputs (data/dalton/dalton_*.csv)
  • All fundamentals (data/fundamentals/fund_*.csv)
  • All absorption, prebreakout, compression weekly screens

Computes:
  1. Per-stock asymmetric score (Dalton 5-pillar macro + state inflection)
  2. Fundamental score (cheap + growing + FCF positive)
  3. Cross-lens flags (absorption, prebreakout, compression passes)
  4. Composite mega_score blending tech + fund + multi-lens bonus

Outputs:
  • data/synthesis/master_top.csv  — top 500 across all markets ranked
  • Plus per-tier sliced views
"""
import os, glob, re, sys
import pandas as pd
import numpy as np

os.makedirs('data/synthesis', exist_ok=True)

bull_states = ['INFLECTION_UP','ACCELERATION_UP','DECELERATION_UP','TRENDING_UP']

# ─── Load all Dalton outputs (small/mid + large/mega) ─────────────────────
print("Loading Dalton outputs...", file=sys.stderr)
dalton_frames = []
for path in sorted(glob.glob('data/dalton/dalton_*.csv')):
    bn = os.path.basename(path).replace('dalton_','').replace('.csv','')
    if bn.endswith('_recovery'): continue
    cap_tier = 'large' if bn.endswith('_lg') else 'smid'
    mkt = bn.replace('_lg','')
    try:
        df = pd.read_csv(path)
        if len(df) == 0: continue
        df['region'] = mkt
        df['cap_tier'] = cap_tier
        dalton_frames.append(df)
    except Exception as e:
        print(f"  ERR loading {path}: {e}", file=sys.stderr)

dalton = pd.concat(dalton_frames, ignore_index=True, sort=False) if dalton_frames else pd.DataFrame()
# Dedup: same ticker may appear in both buckets via universe overlap
dalton = dalton.drop_duplicates(subset=['ticker','region'], keep='first')
print(f"  Dalton total: {len(dalton)} rows across {len(dalton_frames)} files", file=sys.stderr)

# ─── Load all fundamentals ────────────────────────────────────────────────
print("Loading fundamentals...", file=sys.stderr)
fund_frames = []
for path in sorted(glob.glob('data/fundamentals/fund_*.csv')):
    bn = os.path.basename(path).replace('fund_','').replace('.csv','')
    if bn.endswith(('_recovery','_backfill')): continue
    try:
        df = pd.read_csv(path)
        if len(df) == 0: continue
        df['fund_market'] = bn.replace('_lg','')
        df['fund_cap_tier'] = 'large' if bn.endswith('_lg') else 'smid'
        fund_frames.append(df)
    except Exception:
        pass

fund = pd.concat(fund_frames, ignore_index=True, sort=False) if fund_frames else pd.DataFrame()
fund = fund.drop_duplicates(subset='ticker', keep='first')
print(f"  Fund total: {len(fund)} rows", file=sys.stderr)

# ─── Compute Dalton tech / asymmetric score ───────────────────────────────
for c in ['absW_E_asymm','absW_asymm','absW_macro','absW_pos_in_bracket',
          'velocity','acceleration','final_rank']:
    if c not in dalton: dalton[c] = np.nan

dalton['absW_E_asymm']  = dalton['absW_E_asymm'].fillna(0)
dalton['absW_asymm']    = dalton['absW_asymm'].fillna(0).clip(0, 30)  # cap data-artifact spikes
dalton['absW_macro']    = dalton['absW_macro'].fillna(0)
dalton['absW_pos']      = dalton['absW_pos_in_bracket'].fillna(50)
dalton['velocity']      = dalton['velocity'].fillna(0)
dalton['acceleration']  = dalton['acceleration'].fillna(0)

for s, t in [('w_bull','absW_state'),('m_bull','absM_state'),
             ('rw_bull','relW_state'),('rm_bull','relM_state')]:
    if t in dalton.columns:
        dalton[s] = dalton[t].fillna('').isin(bull_states).astype(int)
    else:
        dalton[s] = 0
dalton['n_bull_tf'] = dalton[['w_bull','m_bull','rw_bull','rm_bull']].sum(axis=1)

dalton['mirage']   = (dalton.get('absW_dp_signal','') == 'MIRAGE_BUY').astype(int)
dalton['bform']    = dalton.get('absW_b_form', False).fillna(False).astype(int)
dalton['fbd_recl'] = dalton.get('absW_failed_bd_reclaim', False).fillna(False).astype(int)
dalton['fbo_rej']  = dalton.get('absW_failed_bo_reject', False).fillna(False).astype(int)

dalton['asym_score'] = (
    dalton['absW_E_asymm'] * 6
  + dalton['absW_asymm'] * 4
  + dalton['absW_macro'] * 0.4
  + dalton['n_bull_tf'] * 8
  + dalton['velocity'].clip(-5,5) * 2
  + dalton['acceleration'].clip(-5,5) * 1.5
  + dalton['mirage'] * 25 + dalton['bform'] * 20
  + dalton['fbd_recl'] * 15 + dalton['fbo_rej'] * 10
)

# ─── Compute fundamental score ────────────────────────────────────────────
if len(fund):
    for c in ['ev_ebit','ev_ebitda','fcf_yield','rev_g','opm','fcf']:
        if c not in fund: fund[c] = np.nan
    # ev_ebit is universally None from yfinance.info; fall back to ev_ebitda
    fund['ev_valuation'] = fund['ev_ebit'].fillna(fund['ev_ebitda'])
    fund['fund_pass'] = (
        (fund['ev_valuation'].fillna(99).between(0, 15)) &
        (fund['rev_g'].fillna(0) >= 0.05) &
        (fund['fcf'].fillna(0) > 0)
    )
    fund['fund_score'] = (
        np.clip((15 - fund['ev_valuation'].fillna(99)) / 15 * 10, 0, 10)
      + np.clip(fund['fcf_yield'].fillna(0) * 60, 0, 15)
      + np.clip(fund['rev_g'].fillna(0) * 30, 0, 10)
      + np.clip(fund['opm'].fillna(0) * 15, -5, 8)
    ).round(2)
else:
    fund = pd.DataFrame(columns=['ticker','fund_pass','fund_score','ev_valuation','ev_ebit','ev_ebitda','fcf_yield','rev_g','opm'])

# ─── Merge Dalton + Fund ──────────────────────────────────────────────────
fund_cols = ['ticker','fund_pass','fund_score','ev_valuation','ev_ebit','ev_ebitda',
             'fcf_yield','rev_g','opm','mktCap','industry','sector','name','currency']
fc = [c for c in fund_cols if c in fund.columns]
merged = dalton.merge(fund[fc], on='ticker', how='left', suffixes=('','_f'))
merged['fund_pass'] = merged['fund_pass'].fillna(False)
merged['fund_score'] = merged['fund_score'].fillna(0)

# ─── Load and merge auxiliary screens ─────────────────────────────────────
def load_screen(pattern, drop_cols):
    frames = []
    for p in sorted(glob.glob(pattern)):
        bn = os.path.basename(p)
        try:
            df = pd.read_csv(p)
            if len(df): frames.append(df)
        except Exception: pass
    if not frames: return pd.DataFrame({'ticker':[]})
    big = pd.concat(frames, ignore_index=True, sort=False).drop_duplicates(subset='ticker', keep='first')
    return big

absorp = load_screen('data/absorption/absorp_*.csv', [])
prebo  = load_screen('data/prebreakout/prebo_*.csv', [])
compress = load_screen('data/compression/compress_*.csv', [])

# Absorption pass: money out, price holding
if len(absorp):
    absorp['absorp_pass'] = (
        (absorp.get('mfi_chg', 0).fillna(0) <= -10) &
        (absorp.get('px_chg_pct', 99).fillna(99).abs() <= 7) &
        (absorp.get('divergence_ratio', 99).fillna(99) <= 0.4) &
        (absorp.get('atr_pct_avg', 99).fillna(99) <= 6)
    )
    merged = merged.merge(absorp[['ticker','absorp_pass']], on='ticker', how='left')
merged['absorp_pass'] = merged.get('absorp_pass', False).fillna(False)

# Pre-breakout pass (Weinstein/Qullamaggie/O'Neil)
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
merged['prebo_pass'] = merged.get('prebo_pass', False).fillna(False)

# Compression pass: MFI higher-low + ATR contracting
if len(compress):
    compress['compress_pass'] = (
        (compress.get('mfi_higher_low', False).fillna(False).astype(bool)) &
        (compress.get('atr_compression', False).fillna(False).astype(bool)) &
        (compress.get('mfi_inflect_amt', 0).fillna(0) >= 1) &
        (compress.get('pct_below_5y_high', 99).fillna(99) <= 15)
    )
    merged = merged.merge(compress[['ticker','compress_pass']], on='ticker', how='left')
merged['compress_pass'] = merged.get('compress_pass', False).fillna(False)

# ─── Composite mega_score ─────────────────────────────────────────────────
merged['n_lens'] = (
    merged['fund_pass'].astype(int)
  + merged['absorp_pass'].astype(int)
  + merged['prebo_pass'].astype(int)
  + merged['compress_pass'].astype(int)
)
merged['mega_score'] = (
    merged['asym_score'].fillna(0)
  + merged['fund_score'].fillna(0) * 3
  + merged['n_lens'] * 40
)

# ─── Quality filter and sort ──────────────────────────────────────────────
if 'monthly_safe' not in merged.columns:
    merged['monthly_safe'] = True
qual_mask = (
    (merged['absW_macro'] >= 25) &
    (merged['absW_asymm'] >= 1.5) &
    (merged['absW_pos'].between(20, 85)) &
    (merged['monthly_safe'].fillna(True).astype(bool)) &
    (merged['n_bull_tf'] >= 1)
)
quality = merged[qual_mask].copy().sort_values('mega_score', ascending=False)

# Save outputs
merged.to_csv('data/synthesis/master_all.csv', index=False)
quality.head(500).to_csv('data/synthesis/master_top500.csv', index=False)
quality.head(50).to_csv('data/synthesis/master_top50.csv', index=False)

# Per-tier slices
for tier, name in [(quality[quality['cap_tier']=='smid'].head(100), 'top100_smid'),
                   (quality[quality['cap_tier']=='large'].head(100), 'top100_large'),
                   (quality[quality['n_lens']>=3].head(100), 'triple_lens'),
                   (quality[quality['fund_pass']].head(100), 'fund_pass_asym')]:
    tier.to_csv(f'data/synthesis/{name}.csv', index=False)

print(f"\nUniverse: {len(merged)} ticker-market pairs", file=sys.stderr)
print(f"Quality (asym macro + bull TF): {len(quality)}", file=sys.stderr)
print(f"  Triple+ lens: {(quality['n_lens']>=3).sum()}", file=sys.stderr)
print(f"  Fund pass:    {quality['fund_pass'].sum()}", file=sys.stderr)
print(f"  Top500 saved to data/synthesis/master_top500.csv", file=sys.stderr)

# ─── Display top 30 ───────────────────────────────────────────────────────
pd.set_option('display.width', 240); pd.set_option('display.max_colwidth', 22)
print(f"\n{'='*155}")
print(f"  MEGA SYNTHESIS — TOP 30 BY COMPOSITE SCORE")
print(f"{'='*155}")
print(f"{'#':>3} {'ticker':<10} {'mkt':<6} {'cap':<5} {'name':<25} "
      f"{'macro':>5} {'asym':>5} {'nTF':>3} {'absW':<15} {'dp':<13} "
      f"{'EV/EB':>6} {'FCFy%':>5} {'revG%':>5} {'lens':<5} {'score':>6}")
print('-'*155)
for i, r in quality.head(30).iterrows():
    tags = 'D'
    if r['fund_pass']: tags += 'F'
    if r['absorp_pass']: tags += 'A'
    if r['prebo_pass']: tags += 'P'
    if r['compress_pass']: tags += 'C'
    name = str(r.get('name',''))[:22]
    aw = str(r.get('absW_state',''))[:14]
    dp = str(r.get('absW_dp_signal',''))[:11]
    evb = r.get('ev_ebit')
    evb_s = f"{evb:>6.1f}" if pd.notna(evb) and abs(evb) < 1e4 else "    -"
    fy = r.get('fcf_yield')
    fy_s = f"{fy*100:>5.1f}" if pd.notna(fy) else "    -"
    rg = r.get('rev_g')
    rg_s = f"{rg*100:>5.1f}" if pd.notna(rg) else "    -"
    print(f"{i:>3} {r['ticker']:<10} {str(r.get('region',''))[:5]:<6} "
          f"{r.get('cap_tier',''):<5} {name:<25} "
          f"{int(r['absW_macro']):>5} {r['absW_asymm']:>5.2f} {int(r['n_bull_tf']):>3} "
          f"{aw:<15} {dp:<13} {evb_s} {fy_s} {rg_s} {tags:<5} {r['mega_score']:>6.1f}")

# Region breakdown
print(f"\n{'─'*60}\nRegion breakdown of top 500:")
print(quality.head(500)['region'].value_counts().to_string())
print(f"\nCap tier breakdown of top 500:")
print(quality.head(500)['cap_tier'].value_counts().to_string())
print(f"\nMulti-lens counts in top 500:")
print(quality.head(500)['n_lens'].value_counts().sort_index().to_string())
