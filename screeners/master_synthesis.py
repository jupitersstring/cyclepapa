#!/usr/bin/env python3
"""Master Synthesis — finds names with best technical AND fundamental setups.

Combines:
  • Comprehensive Dalton results (dalton_complete_*.csv)
  • Fundamental cheap+growth+FCF results (*cheap_growth_fcf*.csv or similar)
  • Mauboussin compounder (compounder_elite.csv if present)
  • Inflection plays (inflect_deep.csv if present)
  • Pre-breakout patterns (compression / absorption / prebreakout)

Outputs a unified scoring with:
  • category_count: how many distinct lens categories the name appears on
  • tech_score: composite Dalton final_rank + score-velocity
  • fund_score: composite cheap+growth+FCF quality (lower EV/EBIT, higher FCF yield)
  • combined_score: weighted blend favoring multi-lens names

Usage:
    python3 master_synthesis.py \\
        --dalton path/to/dalton_complete_us.csv \\
        --fund   path/to/cheap_growth_fcf.csv \\
        --out    master_top.csv \\
        [--region "US"]
"""
import argparse, sys
import pandas as pd
import numpy as np

ap = argparse.ArgumentParser()
ap.add_argument('--dalton',     nargs='*', default=[], help='Dalton output CSVs (can pass multiple)')
ap.add_argument('--fund',       nargs='*', default=[], help='Fundamental cheap/growth CSVs')
ap.add_argument('--compounder', default=None, help='Compounder elite CSV')
ap.add_argument('--inflect',    default=None, help='Inflection play CSV')
ap.add_argument('--out',        default='/tmp/master_top.csv')
ap.add_argument('--top',        type=int, default=50, help='Top N to display')
ap.add_argument('--region',     default='')
ap.add_argument('--macro-min',  type=int, default=25, help='Min Dalton macro')
ap.add_argument('--mcap-min',   type=float, default=0, help='Min market cap')
args = ap.parse_args()


# ─── Load all Dalton frames and tag region ───
dalton_dfs = []
for f in args.dalton:
    if not f: continue
    try:
        d = pd.read_csv(f)
        dalton_dfs.append(d)
    except Exception as e:
        print(f"  err loading {f}: {e}", file=sys.stderr)
dalton = pd.concat(dalton_dfs, ignore_index=True).drop_duplicates(subset='ticker') if dalton_dfs else pd.DataFrame()
print(f"Dalton frame: {len(dalton)} rows", file=sys.stderr)


# ─── Load fundamental frames ───
fund_dfs = []
for f in args.fund:
    if not f: continue
    try:
        df = pd.read_csv(f)
        fund_dfs.append(df)
    except Exception as e:
        print(f"  err loading {f}: {e}", file=sys.stderr)
fund = pd.concat(fund_dfs, ignore_index=True).drop_duplicates(subset='ticker') if fund_dfs else pd.DataFrame()
print(f"Fundamental frame: {len(fund)} rows", file=sys.stderr)


def safe_float(x):
    try: return float(x)
    except: return np.nan


# ─── Tech score from Dalton ───
if len(dalton):
    # Already have final_rank if dalton_complete_screen produced it
    dalton['tech_score'] = dalton.get('final_rank', dalton.get('signal_score', 0))
    # State badge: count of bullish timeframes
    bull_states = ('INFLECTION_UP','ACCELERATION_UP','DECELERATION_UP','TRENDING_UP')
    dalton['n_bull_tf'] = 0
    for col in ['absW_state','absM_state','relW_state','relM_state']:
        if col in dalton.columns:
            dalton['n_bull_tf'] += dalton[col].fillna('').isin(bull_states).astype(int)
    # Macro safety check
    dalton['macro_ok'] = dalton.get('absW_macro', 0).fillna(0) >= args.macro_min
    # Has room left?
    if 'absW_pos_in_bracket' in dalton.columns:
        dalton['has_room'] = dalton['absW_pos_in_bracket'].fillna(0).between(35, 90)
    else:
        dalton['has_room'] = True

# ─── Fund score from EV/EBIT, FCF yield, growth ───
if len(fund):
    fund['fund_score'] = 0.0
    if 'ev_ebit' in fund.columns:
        # Lower EV/EBIT = better. Cap at 15, scale 0-10
        evb = fund['ev_ebit'].fillna(99)
        fund['fund_score'] += np.clip((15 - evb) / 15 * 10, 0, 10)
    if 'fcf_yield' in fund.columns:
        # Higher FCF yield = better
        fy = fund['fcf_yield'].fillna(0)
        fund['fund_score'] += np.clip(fy * 50, 0, 15)  # 30% yield = 15 pts
    if 'rev_g' in fund.columns:
        # Higher growth = better
        rg = fund['rev_g'].fillna(0)
        fund['fund_score'] += np.clip(rg * 30, 0, 10)  # 33% growth = 10 pts
    if 'opm' in fund.columns:
        # Higher op margin = better
        om = fund['opm'].fillna(0)
        fund['fund_score'] += np.clip(om * 15, -5, 8)  # 50% op margin = 7.5 pts
    fund['fund_pass'] = (fund.get('ev_ebit', 99).fillna(99) <= 15) & \
                       (fund.get('rev_g', 0).fillna(0) >= 0.05) & \
                       (fund.get('fcf', 0).fillna(0) > 0)


# ─── Merge ───
both = pd.merge(
    dalton if len(dalton) else pd.DataFrame({'ticker':[]}),
    fund   if len(fund)   else pd.DataFrame({'ticker':[]}),
    on='ticker', how='outer', suffixes=('_d','_f')
)
print(f"Joined: {len(both)} unique tickers", file=sys.stderr)


# ─── Determine which categories each name appears on ───
both['on_dalton'] = both['ticker'].isin(dalton['ticker'])      if len(dalton)      else False
both['on_fund']   = both['ticker'].isin(fund['ticker'])        if len(fund)        else False
if args.compounder:
    try:
        comp = pd.read_csv(args.compounder)['ticker'].dropna().unique()
        both['on_compounder'] = both['ticker'].isin(comp)
    except: both['on_compounder'] = False
else: both['on_compounder'] = False
if args.inflect:
    try:
        inf = pd.read_csv(args.inflect)['ticker'].dropna().unique()
        both['on_inflect'] = both['ticker'].isin(inf)
    except: both['on_inflect'] = False
else: both['on_inflect'] = False

both['category_count'] = (both['on_dalton'].astype(int)
                         + both['on_fund'].astype(int)
                         + both['on_compounder'].astype(int)
                         + both['on_inflect'].astype(int))


# ─── Combined score ───
both['tech_score'] = both.get('tech_score', 0).fillna(0)
both['fund_score'] = both.get('fund_score', 0).fillna(0)

# Bonus for being on multiple lists (the rare overlap)
both['multi_bonus'] = (both['category_count'] - 1) * 25  # +25 per extra category
# Tech AND fund both passing = big bonus
both['cross_bonus'] = 0
mask = both['on_dalton'] & both['on_fund']
if mask.any():
    both.loc[mask, 'cross_bonus'] = 50

# Bull TF count bonus
both['tf_bonus'] = both.get('n_bull_tf', 0).fillna(0) * 5

# Final composite
both['combined_score'] = (
    both['tech_score'] +
    both['fund_score'] * 3 +    # fundamentals weighted heavily
    both['multi_bonus'] +
    both['cross_bonus'] +
    both['tf_bonus']
)

# Apply minimum quality filters
filt = both.copy()
if 'macro_ok' in filt.columns:
    filt = filt[filt['macro_ok'].fillna(False) | filt['on_fund']]   # Either Dalton macro OK or on fund list
if 'has_room' in filt.columns:
    filt = filt[filt['has_room'].fillna(True)]
if args.mcap_min > 0 and 'mktCap' in filt.columns:
    filt = filt[filt['mktCap'].fillna(0) >= args.mcap_min]

filt = filt.sort_values('combined_score', ascending=False).head(args.top)


# ─── Display ───
pd.set_option('display.width', 320); pd.set_option('display.max_colwidth', 36); pd.set_option('display.max_rows', 100)
print(f"\n{'='*135}")
print(f"  MASTER SYNTHESIS TOP {args.top} — Best Tech + Fund Setups{' ('+args.region+')' if args.region else ''}")
print(f"{'='*135}")

cols = ['ticker','name_d','name_f','sector_d','industry_d','sector_f','industry_f','cap_bucket','market_cap',
        'mktCap','price','final_rank','tech_score','fund_score','combined_score',
        'absW_macro','absW_state','absM_state','relM_state','absW_dp_signal','absW_init_resp','absW_b_form',
        'ev_ebit','fcf_yield','rev_g','opm','insiders','category_count']
cols_show = [c for c in cols if c in filt.columns]

for i, (_, r) in enumerate(filt.iterrows(), 1):
    nm = r.get('name_d') or r.get('name_f') or ''
    nm = str(nm)[:30]
    sec = r.get('sector_d') or r.get('sector_f') or r.get('industry_d') or r.get('industry_f') or ''
    sec = str(sec)[:18]
    cap = r.get('cap_bucket') or r.get('market_cap') or ''
    cap = str(cap)[:6]
    tags = []
    if r.get('on_dalton'): tags.append('D')
    if r.get('on_fund'):   tags.append('F')
    if r.get('on_compounder'): tags.append('C')
    if r.get('on_inflect'):    tags.append('I')
    tag = ''.join(tags)
    macro = r.get('absW_macro', np.nan)
    macro_s = f"mac={int(macro)}" if pd.notna(macro) else "mac=  -"
    evb = r.get('ev_ebit', np.nan)
    evb_s = f"EV/EBIT={evb:>4.1f}" if pd.notna(evb) else "EV/EBIT=  -"
    fy = r.get('fcf_yield', np.nan)
    fy_s = f"FCFy={fy*100:>5.1f}%" if pd.notna(fy) else "FCFy=     -"
    rg = r.get('rev_g', np.nan)
    rg_s = f"revG={rg*100:>5.1f}%" if pd.notna(rg) else "revG=     -"
    abs_state = str(r.get('absW_state','')) [:14]
    dp = str(r.get('absW_dp_signal','')) [:13]
    print(f"{i:>3} {r['ticker']:<8} {nm:<31} {cap:<6} {sec:<19} [{tag:<4}] combo={r['combined_score']:>6.1f} fr={r.get('tech_score', 0):>6.1f} fund={r.get('fund_score', 0):>5.1f} | {macro_s} {evb_s} {fy_s} {rg_s} | {abs_state:<14} DP={dp}")

# Summary stats
print(f"\nTotals:")
print(f"  Dalton-only: {(both['on_dalton'] & ~both['on_fund']).sum()}")
print(f"  Fund-only:   {(~both['on_dalton'] & both['on_fund']).sum()}")
print(f"  CROSS (Dalton + Fund): {(both['on_dalton'] & both['on_fund']).sum()}")
print(f"  Compounder overlap: {both['on_compounder'].sum()}")
print(f"  Inflection overlap: {both['on_inflect'].sum()}")

filt.to_csv(args.out, index=False)
print(f"\nSaved {len(filt)} rows -> {args.out}")
