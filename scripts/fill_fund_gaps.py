#!/usr/bin/env python3
"""Identify tickers in existing fundamentals files with missing EV multiples
and write a 'gaps' universe per market for re-pulling with v3 (which falls
back to financial statements).
"""
import glob, os, sys
import pandas as pd

OUT_DIR = 'data/universes/fund_gaps'
os.makedirs(OUT_DIR, exist_ok=True)

total = 0
for path in sorted(glob.glob('data/fundamentals/fund_*.csv')):
    bn = os.path.basename(path).replace('fund_','').replace('.csv','')
    if bn.endswith(('_recovery','_backfill','_x')): continue
    try:
        df = pd.read_csv(path)
    except Exception: continue
    if 'ticker' not in df.columns or len(df) == 0: continue

    # Missing if EV/EBIT AND EV/EBITDA are both null
    miss = df[df['ev_ebit'].isna() & df['ev_ebitda'].isna()]
    if len(miss) >= 10:
        out = miss[['ticker']].copy()
        out['name'] = miss.get('name')
        out.to_csv(f'{OUT_DIR}/uni_{bn}_gap.csv', index=False)
        print(f"  {bn:<18} gap: {len(miss):>5} / {len(df):>5}", file=sys.stderr)
        total += len(miss)

print(f"\nTotal fundamental-multiple gaps: {total}", file=sys.stderr)
