#!/usr/bin/env python3
"""Build per-market 'recovery' universes — tickers in uni_X.csv that DIDN'T
make it into dalton_X.csv (rate-limited / failed downloads).

Writes data/universes/recovery/uni_<mkt>_missed.csv per market with non-trivial gap.
"""
import os, sys
import pandas as pd

REC_DIR = 'data/universes/recovery'
os.makedirs(REC_DIR, exist_ok=True)

markets = []
for f in sorted(os.listdir('data/universes')):
    if f.startswith('uni_') and f.endswith('.csv'):
        markets.append(f.replace('uni_','').replace('.csv',''))

total_missed = 0
print(f"{'market':<12} {'universe':>8} {'captured':>8} {'missed':>7} {'recovered_file'}")
for m in markets:
    uni_path = f'data/universes/uni_{m}.csv'
    dal_path = f'data/dalton/dalton_{m}.csv'
    if not os.path.exists(dal_path):
        continue
    uni = pd.read_csv(uni_path)
    try:
        dal = pd.read_csv(dal_path)
        dal_t = set(dal['ticker'].dropna().astype(str)) if 'ticker' in dal.columns else set()
    except (pd.errors.EmptyDataError, pd.errors.ParserError):
        dal_t = set()
    uni_t = set(uni['ticker'].dropna().astype(str))
    missed = uni_t - dal_t
    pct_miss = len(missed) / max(1, len(uni_t)) * 100
    rec_path = f'{REC_DIR}/uni_{m}_missed.csv'
    # Build recovery file with the same columns as the original universe
    if len(missed) >= 5:
        rec = uni[uni['ticker'].astype(str).isin(missed)].copy()
        rec.to_csv(rec_path, index=False)
        total_missed += len(rec)
        print(f"{m:<12} {len(uni_t):>8} {len(dal_t):>8} {len(missed):>7} {rec_path}")
    else:
        print(f"{m:<12} {len(uni_t):>8} {len(dal_t):>8} {len(missed):>7} (skip - small)")

print(f"\nTotal tickers to recover: {total_missed}")
