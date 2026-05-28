#!/usr/bin/env python3
"""Overlay TD Sequential onto master_top500 to produce the final ranked list.

Adds:
  • net_setup, net_perfect, buy_setup_prop, sell_setup_prop, cd_buy_sum, cd_sell_sum
  • td_oversold flag (net_setup <= -25 OR net_perfect <= -40 OR cd_buy_sum >= 13)
  • td_overbought flag (symmetric upside)
  • mean-reversion score
  • final composite score with TD overlay weight

Outputs:
  data/synthesis/final_mr_ranked.csv  — top by mean-reversion conviction
  data/synthesis/final_breakout_ranked.csv  — top by breakout conviction
"""
import pandas as pd
import numpy as np

m = pd.read_csv('data/synthesis/master_top500.csv')
print(f"Master top500: {len(m)} rows")

td = pd.read_csv('data/td_seq/td_top200.csv')
print(f"TD seq: {len(td)} rows")

# Keep only the headline TD columns
td_cols = ['ticker','net_setup','net_perfect','buy_setup_prop','sell_setup_prop',
           'buy_perfect_prop','sell_perfect_prop','cd_buy_sum','cd_sell_sum',
           'mr_buy_score','mr_sell_score','tfs_with_data']
td_keep = td[[c for c in td_cols if c in td.columns]]

# Merge
fin = m.merge(td_keep, on='ticker', how='left')

# Flags
fin['td_oversold']   = (fin['net_setup'].fillna(99) <= -25) | \
                       (fin['net_perfect'].fillna(99) <= -40) | \
                       (fin['cd_buy_sum'].fillna(0) >= 13)
fin['td_overbought'] = (fin['net_setup'].fillna(-99) >= 25) | \
                       (fin['net_perfect'].fillna(-99) >= 40) | \
                       (fin['cd_sell_sum'].fillna(0) >= 13)

# Mean-reversion BUY = Dalton asymmetric + TD oversold + fund cheap
fin['mr_buy_composite'] = (
    fin['mega_score'].fillna(0)
  + fin['mr_buy_score'].fillna(0) * 1.5
  + fin['td_oversold'].astype(int) * 50
)
# Trend BUY = Dalton inflection + bull TFs aligned + no TD overbought
fin['trend_buy_composite'] = (
    fin['mega_score'].fillna(0)
  + (fin['n_bull_tf'].fillna(0) * 10)
  - fin['td_overbought'].astype(int) * 30
)

mr = fin.sort_values('mr_buy_composite', ascending=False)
br = fin.sort_values('trend_buy_composite', ascending=False)

mr.head(50).to_csv('data/synthesis/final_mr_ranked.csv', index=False)
br.head(50).to_csv('data/synthesis/final_trend_ranked.csv', index=False)
fin.to_csv('data/synthesis/final_all.csv', index=False)

# Display
pd.set_option('display.width', 230); pd.set_option('display.max_colwidth', 22)

print(f"\n{'='*160}")
print(f"  TIER 1 — MEAN REVERSION (Dalton asym + TD oversold + fund cheap)")
print(f"{'='*160}")
print(f"{'#':>3} {'ticker':<10} {'mkt':<5} {'cap':<5} {'name':<22} {'macro':>5} {'asym':>5} {'nTF':>3} "
      f"{'absW':<15} {'net_S':>6} {'net_P':>6} {'cdB':>3} {'EV/EB':>6} {'FCFy%':>5} {'lens':<5} {'MR':>7}")
print('-'*160)
for i, r in mr.head(35).iterrows():
    tags = 'D'
    if r['fund_pass']: tags += 'F'
    if r['absorp_pass']: tags += 'A'
    if r['prebo_pass']: tags += 'P'
    if r['compress_pass']: tags += 'C'
    if r['td_oversold']: tags += 'T'
    name = str(r.get('name',''))[:20]
    aw = str(r.get('absW_state',''))[:14]
    ns = r.get('net_setup')
    ns_s = f"{ns:>6.1f}" if pd.notna(ns) else "    -"
    npp = r.get('net_perfect')
    np_s = f"{npp:>6.1f}" if pd.notna(npp) else "    -"
    cdb = r.get('cd_buy_sum')
    cdb_s = f"{int(cdb):>3}" if pd.notna(cdb) else "  -"
    evb = r.get('ev_ebit')
    evb_s = f"{evb:>6.1f}" if pd.notna(evb) and abs(evb) < 1e4 else "    -"
    fy = r.get('fcf_yield')
    fy_s = f"{fy*100:>5.1f}" if pd.notna(fy) else "    -"
    print(f"{i:>3} {r['ticker']:<10} {str(r.get('region',''))[:4]:<5} "
          f"{r.get('cap_tier','')[:5]:<5} {name:<22} "
          f"{int(r['absW_macro']):>5} {r['absW_asymm']:>5.2f} {int(r['n_bull_tf']):>3} "
          f"{aw:<15} {ns_s} {np_s} {cdb_s} {evb_s} {fy_s} {tags:<5} {r['mr_buy_composite']:>7.1f}")

print(f"\n{'='*160}")
print(f"  TIER 2 — TREND CONTINUATION (Dalton inflection up + multi-TF + not TD overbought)")
print(f"{'='*160}")
print(f"{'#':>3} {'ticker':<10} {'mkt':<5} {'cap':<5} {'name':<22} {'macro':>5} {'asym':>5} {'nTF':>3} "
      f"{'absW':<15} {'net_S':>6} {'EV/EB':>6} {'revG%':>5} {'lens':<5} {'Trend':>7}")
print('-'*160)
for i, r in br.head(30).iterrows():
    tags = 'D'
    if r['fund_pass']: tags += 'F'
    if r['absorp_pass']: tags += 'A'
    if r['prebo_pass']: tags += 'P'
    if r['compress_pass']: tags += 'C'
    if r['td_oversold']: tags += 'T'
    name = str(r.get('name',''))[:20]
    aw = str(r.get('absW_state',''))[:14]
    ns = r.get('net_setup')
    ns_s = f"{ns:>6.1f}" if pd.notna(ns) else "    -"
    evb = r.get('ev_ebit')
    evb_s = f"{evb:>6.1f}" if pd.notna(evb) and abs(evb) < 1e4 else "    -"
    rg = r.get('rev_g')
    rg_s = f"{rg*100:>5.1f}" if pd.notna(rg) else "    -"
    print(f"{i:>3} {r['ticker']:<10} {str(r.get('region',''))[:4]:<5} "
          f"{r.get('cap_tier','')[:5]:<5} {name:<22} "
          f"{int(r['absW_macro']):>5} {r['absW_asymm']:>5.2f} {int(r['n_bull_tf']):>3} "
          f"{aw:<15} {ns_s} {evb_s} {rg_s} {tags:<5} {r['trend_buy_composite']:>7.1f}")

# Stats
print(f"\n{'─'*80}")
print(f"Coverage of top 200 by TD:")
print(f"  With TD data:       {fin['net_setup'].notna().sum()} / 200")
print(f"  TD oversold (BUY):  {fin['td_oversold'].sum()}")
print(f"  TD overbought:      {fin['td_overbought'].sum()}")
print(f"  Mean net_setup:     {fin['net_setup'].mean():.1f}")
print(f"  Mean net_perfect:   {fin['net_perfect'].mean():.1f}")
