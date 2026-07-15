#!/usr/bin/env python3
"""V2 TD overlay — strict direction flags (no double-tagging)."""
import pandas as pd
import numpy as np

m = pd.read_csv('data/synthesis/v2_top500_dedup.csv')
td = pd.read_csv('data/td_seq/td_top200.csv')

td_cols = ['ticker','net_setup','net_perfect','buy_setup_prop','sell_setup_prop',
           'buy_perfect_prop','sell_perfect_prop','cd_buy_sum','cd_sell_sum']
td_keep = td[[c for c in td_cols if c in td.columns]]
fin = m.merge(td_keep, on='ticker', how='left')

# FIX 1: CORRECT direction
# buy_setup_prop aggregates `bull_count` = close < close[4] streaks (DOWN moves)
# So HIGH buy_setup_prop = repeated falls = OVERSOLD = mean-revert UP (BUY signal)
# net_setup = buy_setup_prop - sell_setup_prop:
#   POSITIVE net_setup = buy signals dominate = OVERSOLD = BUY candidate
#   NEGATIVE net_setup = sell signals dominate = OVERBOUGHT = SELL candidate
# Earlier mr_buy_score = -net_setup * 0.6 was inverted; fixing here.
fin['td_oversold_strict'] = (
    (fin['net_setup'].fillna(-99) >= 25)
    & (fin['buy_setup_prop'].fillna(0) > fin['sell_setup_prop'].fillna(0) + 15)
    & (
        (fin['cd_buy_sum'].fillna(0) >= fin['cd_sell_sum'].fillna(0))
        | ((fin['cd_buy_sum'].fillna(0) == 0) & (fin['cd_sell_sum'].fillna(0) == 0))
      )
)
fin['td_overbought_strict'] = (
    (fin['net_setup'].fillna(99) <= -25)
    & (fin['sell_setup_prop'].fillna(0) > fin['buy_setup_prop'].fillna(0) + 15)
    & (
        (fin['cd_sell_sum'].fillna(0) >= fin['cd_buy_sum'].fillna(0))
        | ((fin['cd_buy_sum'].fillna(0) == 0) & (fin['cd_sell_sum'].fillna(0) == 0))
      )
)

both = (fin['td_oversold_strict'] & fin['td_overbought_strict']).sum()
print(f"Strict-direction collisions: {both} (should be 0)")
print(f"TD oversold (strict):   {fin['td_oversold_strict'].sum()}")
print(f"TD overbought (strict): {fin['td_overbought_strict'].sum()}")

# CORRECTED scoring: positive net_setup = oversold = reward as BUY
fin['mr_buy_composite'] = (
    fin['mega_score'].fillna(0)
  + (fin['net_setup'].fillna(0) * 0.4 + fin['net_perfect'].fillna(0) * 0.3
     + fin['cd_buy_sum'].fillna(0) * 0.5).clip(lower=0)
  + fin['td_oversold_strict'].astype(int) * 50
)
# Trend-continuation: avoid stretched-up names (negative net_setup = overbought)
fin['trend_buy_composite'] = (
    fin['mega_score'].fillna(0)
  + fin['n_bull_tf'].fillna(0) * 10
  - fin['td_overbought_strict'].astype(int) * 30
)

mr = fin.sort_values('mr_buy_composite', ascending=False)
br = fin.sort_values('trend_buy_composite', ascending=False)
mr.head(50).to_csv('data/synthesis/v2_final_mr_ranked.csv', index=False)
br.head(50).to_csv('data/synthesis/v2_final_trend_ranked.csv', index=False)
fin.to_csv('data/synthesis/v2_final_all.csv', index=False)

print(f"\nWith TD data (in top 500 dedup): {fin['net_setup'].notna().sum()}")

pd.set_option('display.width', 220); pd.set_option('display.max_colwidth', 22)
print(f"\n{'='*155}\n  V2 TIER 1 — MEAN REVERSION (strict TD oversold + Dalton asym + cheap)\n{'='*155}")
print(f"{'#':>3} {'ticker':<10} {'mkt':<5} {'cap':<10} {'name':<22} "
      f"{'macro':>5} {'asym':>5} {'nTF':>3} {'absW':<14} {'net_S':>6} {'cdB':>3} "
      f"{'EV/EB':>6} {'FCFy%':>5} {'revG%':>5} {'lens':<5} {'MR':>6}")
print('-'*155)
for i, r in mr.head(30).iterrows():
    tags = 'D'
    if r['fund_pass']: tags += 'F'
    if r['absorp_pass']: tags += 'A'
    if r['prebo_pass']: tags += 'P'
    if r['compress_pass']: tags += 'C'
    if r['td_oversold_strict']: tags += 'T'
    name = str(r.get('name',''))[:20]
    aw = str(r.get('absW_state',''))[:13]
    ns = r.get('net_setup'); ns_s = f"{ns:>6.1f}" if pd.notna(ns) else "    -"
    cdb = r.get('cd_buy_sum'); cdb_s = f"{int(cdb):>3}" if pd.notna(cdb) else "  -"
    evb = r.get('ev_valuation'); evb_s = f"{evb:>6.1f}" if pd.notna(evb) and abs(evb) < 1e4 else "    -"
    fy = r.get('fcf_yield_clean'); fy_s = f"{fy*100:>5.1f}" if pd.notna(fy) else "    -"
    rg = r.get('rev_g_clean'); rg_s = f"{rg*100:>5.1f}" if pd.notna(rg) else "    -"
    cap_s = str(r.get('cap_tier',''))[:9]
    print(f"{i:>3} {r['ticker']:<10} {str(r.get('region',''))[:4]:<5} {cap_s:<10} {name:<22} "
          f"{int(r.get('absW_macro',0)):>5} {r.get('absW_asymm',0):>5.2f} {int(r.get('n_bull_tf',0)):>3} "
          f"{aw:<14} {ns_s} {cdb_s} {evb_s} {fy_s} {rg_s} {tags:<5} {r['mr_buy_composite']:>6.1f}")
