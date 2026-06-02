#!/usr/bin/env python3
"""Top 10 asymmetric setups per measure (Dalton / TD / Fund / Absorp / PreBO / Compress)
across all 21 markets × 2 cap buckets.

Reads merged final_all.csv (already has all lenses + TD overlay merged).
For measures where only top-200 was scored (TD), we still use that.
For Dalton/Fund/Absorp/Prebo/Compress, we restart from master_all.csv to
include the full ~16k universe rather than just top-500.
"""
import pandas as pd
import numpy as np

# Use the full merged dataset for Dalton/Fund/Absorp/Prebo/Compress measures
all_df = pd.read_csv('data/synthesis/master_all.csv')
# Apply same quality filter used in master_synthesis
qual = all_df[
    (all_df['absW_macro'].fillna(0) >= 25) &
    (all_df['absW_asymm'].fillna(0) >= 1.5) &
    (all_df['absW_pos'].fillna(50).between(20, 85)) &
    (all_df.get('monthly_safe', True).fillna(True).astype(bool)) &
    (all_df['n_bull_tf'].fillna(0) >= 1)
].copy()
print(f"Quality universe: {len(qual)} ticker-market rows")

# TD only ran on top-200 — separate frame
td_df = pd.read_csv('data/synthesis/final_all.csv')

pd.set_option('display.width', 200)
pd.set_option('display.max_colwidth', 22)

def show(df, title, cols, score_col):
    print(f"\n{'='*145}")
    print(f"  {title}")
    print(f"{'='*145}")
    # Header
    print(f"{'#':>3} {'ticker':<10} {'mkt':<5} {'cap':<5} {'name':<26} ", end='')
    for c, _ in cols:
        print(f"{c:>8}", end=' ')
    print(f"{'score':>7}")
    print('-'*145)
    for i, (_, r) in enumerate(df.iterrows(), 1):
        name = str(r.get('name',''))[:24]
        print(f"{i:>3} {r['ticker']:<10} {str(r.get('region',''))[:4]:<5} "
              f"{r.get('cap_tier','')[:5]:<5} {name:<26} ", end='')
        for c, fmt in cols:
            v = r.get(c)
            if pd.isna(v):
                print(f"{'-':>8}", end=' ')
            elif fmt == 'int':
                print(f"{int(v):>8}", end=' ')
            elif fmt == 'float2':
                print(f"{v:>8.2f}", end=' ')
            elif fmt == 'pct':
                print(f"{v*100:>7.1f}%", end=' ')
            elif fmt == 'str':
                print(f"{str(v)[:8]:>8}", end=' ')
            else:
                print(f"{v:>8.1f}", end=' ')
        print(f"{r[score_col]:>7.1f}")

# ─── 1. DALTON asymmetric ───
print("\n[1/6] DALTON asymmetric — best macro/inflection/asymmetry")
d = qual.sort_values('asym_score', ascending=False).head(10)
show(d, "TOP 10 — DALTON ASYMMETRIC",
     [('absW_macro','int'),('absW_asymm','float2'),('n_bull_tf','int'),
      ('absW_state','str'),('absW_dp_signal','str')], 'asym_score')

# ─── 2. TD Sequential mean reversion ───
td_data = td_df[td_df['net_setup'].notna()].copy()
td_data['mr_score_combined'] = (
    -td_data['net_setup'].fillna(0) * 0.6
    -td_data['net_perfect'].fillna(0) * 0.4
    +td_data.get('cd_buy_sum', 0).fillna(0) * 0.5
    +td_data['asym_score'].fillna(0) * 0.3
)
td_top = td_data.sort_values('mr_score_combined', ascending=False).head(10)
show(td_top, "TOP 10 — TD SEQUENTIAL MEAN REVERSION (oversold)",
     [('net_setup','float2'),('net_perfect','float2'),
      ('cd_buy_sum','int'),('absW_state','str')], 'mr_score_combined')

# ─── 3. FUNDAMENTALS (cheap + growing + FCF positive + asymmetric) ───
f = qual[qual['fund_pass']==True].copy()
# Add a stricter fund-only score:
f['fund_only_score'] = (
    np.clip((15 - f['ev_valuation'].fillna(99)) / 15 * 10, 0, 10)
    + np.clip(f['fcf_yield'].fillna(0) * 60, 0, 15)
    + np.clip(f['rev_g'].fillna(0) * 30, 0, 10)
    + np.clip(f['opm'].fillna(0) * 15, -5, 8)
    + f['asym_score'].fillna(0) * 0.1
)
f_top = f.sort_values('fund_only_score', ascending=False).head(10)
show(f_top, "TOP 10 — FUNDAMENTAL (cheap + growing + FCF positive + asymmetric)",
     [('ev_valuation','float2'),('fcf_yield','pct'),('rev_g','pct'),('opm','pct')], 'fund_only_score')

# ─── 4. ABSORPTION (Wyckoff money-out price-holding + asymmetric) ───
a = qual[qual['absorp_pass']==True].copy()
a['absorp_combo'] = a['asym_score'].fillna(0) + 50
a_top = a.sort_values('absorp_combo', ascending=False).head(10)
show(a_top, "TOP 10 — ABSORPTION (Wyckoff accumulation + asymmetric)",
     [('absW_macro','int'),('absW_asymm','float2'),('n_bull_tf','int'),
      ('absW_state','str')], 'absorp_combo')

# ─── 5. PREBREAKOUT (Weinstein/Qullamaggie + asymmetric) ───
p = qual[qual['prebo_pass']==True].copy()
p['prebo_combo'] = p['asym_score'].fillna(0) + 50
p_top = p.sort_values('prebo_combo', ascending=False).head(10)
if len(p_top) == 0:
    print(f"\n{'='*145}\n  TOP 10 — PREBREAKOUT (no qualifying names — strict filter)\n{'='*145}")
else:
    show(p_top, "TOP 10 — PREBREAKOUT (Weinstein/Qullamaggie/O'Neil + asymmetric)",
         [('absW_macro','int'),('absW_asymm','float2'),('n_bull_tf','int'),
          ('absW_state','str')], 'prebo_combo')

# ─── 6. COMPRESSION (MFI higher-low + ATR squeeze + asymmetric) ───
c = qual[qual['compress_pass']==True].copy()
c['compress_combo'] = c['asym_score'].fillna(0) + 50
c_top = c.sort_values('compress_combo', ascending=False).head(10)
show(c_top, "TOP 10 — COMPRESSION (MFI higher-low + range squeeze + asymmetric)",
     [('absW_macro','int'),('absW_asymm','float2'),('n_bull_tf','int'),
      ('absW_state','str')], 'compress_combo')

# Save each tier
d.to_csv('data/synthesis/top10_dalton.csv', index=False)
td_top.to_csv('data/synthesis/top10_td_seq.csv', index=False)
f_top.to_csv('data/synthesis/top10_fund.csv', index=False)
a_top.to_csv('data/synthesis/top10_absorption.csv', index=False)
p_top.to_csv('data/synthesis/top10_prebo.csv', index=False)
c_top.to_csv('data/synthesis/top10_compress.csv', index=False)

print(f"\n{'─'*60}\nQualifying counts (lens passes within asymmetric quality set):")
print(f"  Dalton asymmetric : {len(qual)}")
print(f"  TD Sequential     : {len(td_data)}  (only top-200 was scored)")
print(f"  Fundamental pass  : {len(f)}")
print(f"  Absorption pass   : {len(a)}")
print(f"  Pre-breakout pass : {len(p)}")
print(f"  Compression pass  : {len(c)}")
