#!/usr/bin/env python3
"""Merge Q-pass and EP-pass flags into the full universe ranking.

Reads:
  data/synthesis/v2_universe_ranked_full.csv (16k+ rows)
  data/qmaggie/qmaggie_*.csv (per-market Q outputs)
  data/ep/ep_*.csv (per-market EP outputs)

Adds columns:
  qmaggie_pass: True if any Q screen in the universe set passes for this ticker
  ep_pass: True if any EP screen passes
  best_leg_pct, adr_pct, consol_days, sma10_rising, sma20_rising — from Q output
  biggest_gap_pct, vol_ratio_gap_day, days_since_gap — from EP output

Writes v2_universe_ranked_full_q.csv
"""
import os, glob, sys
import pandas as pd

df = pd.read_csv('data/synthesis/v2_universe_ranked_full.csv')
print(f"Loaded {len(df)} ranked tickers", file=sys.stderr)

# Merge Q
q_frames = []
for p in sorted(glob.glob('data/qmaggie/qmaggie_*.csv')):
    try:
        d = pd.read_csv(p)
        if len(d): q_frames.append(d)
    except Exception: pass
if q_frames:
    qall = pd.concat(q_frames, ignore_index=True, sort=False).drop_duplicates(subset='ticker', keep='first')
    qcols = ['ticker','best_leg_pct','leg_end_bars_ago','ret_1m_pct','ret_3m_pct','ret_6m_pct',
             'consol_days','consol_range_pct','adr_pct','above_sma10','above_sma20','above_sma50',
             'sma10_rising','sma20_rising','pct_below_leg_high','vol_contract_ratio','qmaggie_pass']
    qall = qall[[c for c in qcols if c in qall.columns]]
    df = df.merge(qall, on='ticker', how='left')
    print(f"  Q merged: {df['qmaggie_pass'].fillna(False).sum()} Q-pass", file=sys.stderr)
else:
    df['qmaggie_pass'] = False
    print("  no Q files yet", file=sys.stderr)

# Merge EP
e_frames = []
for p in sorted(glob.glob('data/ep/ep_*.csv')):
    try:
        d = pd.read_csv(p)
        if len(d): e_frames.append(d)
    except Exception: pass
if e_frames:
    eall = pd.concat(e_frames, ignore_index=True, sort=False).drop_duplicates(subset='ticker', keep='first')
    ecols = ['ticker','biggest_gap_pct','vol_ratio_gap_day','pre_gap_range_6m_pct',
             'pre_gap_return_6m_pct','days_since_gap','hold_pct_since_gap','ep_pass']
    eall = eall[[c for c in ecols if c in eall.columns]]
    df = df.merge(eall, on='ticker', how='left')
    print(f"  EP merged: {df['ep_pass'].fillna(False).sum()} EP-pass", file=sys.stderr)
else:
    df['ep_pass'] = False
    print("  no EP files yet", file=sys.stderr)

df['qmaggie_pass'] = df['qmaggie_pass'].fillna(False).astype(bool)
df['ep_pass'] = df['ep_pass'].fillna(False).astype(bool)

df.to_csv('data/synthesis/v2_universe_ranked_full_q.csv', index=False)
print(f"Output: data/synthesis/v2_universe_ranked_full_q.csv ({len(df)} rows)", file=sys.stderr)
