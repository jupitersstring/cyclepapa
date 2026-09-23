"""Cross-system master analysis: merge MTF PSAR composite ranks with the
Stars Aligned legs (six-school best_rank, M, E, DSR, ADV_play_now) into a
single master score, plus derived watchlists.

Inputs:
  /tmp/mtf_psar_rank.csv      (from mtf_psar_rank.py)
  /tmp/stars_aligned_*.csv    (from screen + augment_all.py)

Outputs:
  /tmp/master_cross_system.csv   all merged tickers + master score
  /tmp/final_master_liquid.csv   master list, USD-liquidity >= $2M/day
  /tmp/final_coiled_springs.csv  high M+DSR, E NOT yet fired, liquid

Master score (0-100):
  25% PSAR combined (asset+rel net MA, recency-weighted)
  20% six-school best_rank
  20% M  (Minervini MA-respect + VCP)
  15% E  (entry trigger today)
  10% DSR (downside resilience)
  10% ADV_play_now (mcap-normalized liquidity + acceleration)

Coiled springs = the pre-breakout watchlist: structure (M>=65) and
resilience (DSR>=60) and PSAR confirmation (combined>=0.5) but the daily
trigger E < 35 — names to watch for the volume-spike day.

Note: adv_20 in the region CSVs is in LOCAL currency; we convert to USD
with rough per-suffix FX so the liquidity floor is comparable globally.
"""

import glob
import warnings

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

FX = {'.T': 0.0065, '.NS': 0.0117, '.BO': 0.0117, '.KS': 0.00073, '.KQ': 0.00073,
      '.TW': 0.031, '.TWO': 0.031, '.HK': 0.128, '.SS': 0.139, '.SZ': 0.139,
      '.L': 1.27, '.PA': 1.08, '.AS': 1.08, '.BR': 1.08, '.MI': 1.08, '.MC': 1.08,
      '.DE': 1.08, '.F': 1.08, '.SW': 1.12, '.ST': 0.095, '.OL': 0.092, '.CO': 0.145,
      '.HE': 1.08, '.VI': 1.08, '.AT': 1.08, '.AX': 0.65, '.NZ': 0.60, '.IR': 1.08,
      '.WA': 0.25, '.SG': 1.08, '.MU': 1.08, '.HA': 1.08, '.DU': 1.08, '.HM': 1.08,
      '.MX': 0.055, '.SA': 0.18, '.IL': 1.27}


def nz(s, lo, hi):
    return ((s - lo) / (hi - lo)).clip(0, 1)


def adv_usd(row):
    t = str(row['ticker'])
    adv = row['adv_20']
    if pd.isna(adv):
        return np.nan
    if '.' in t:
        suf = '.' + t.rsplit('.', 1)[1]
        return adv * FX.get(suf, 1.0)
    return adv


def main():
    rows = []
    for p in sorted(glob.glob('/tmp/stars_aligned_*.csv')):
        region = p.split('stars_aligned_')[-1].replace('.csv', '')
        df = pd.read_csv(p)
        df['region'] = region
        rows.append(df)
    big = pd.concat(rows, ignore_index=True)
    big['best_rank'] = big[['daily_rank', 'weekly_rank', 'monthly_rank']].max(axis=1)
    big = big.drop_duplicates(subset=['ticker'], keep='first')

    psar = pd.read_csv('/tmp/mtf_psar_rank.csv').drop_duplicates(subset=['ticker'], keep='first')

    m = psar.merge(
        big[['ticker', 'best_rank', 'weekly_label', 'M', 'E', 'DSR',
             'ADV_play_now', 'adv_20', 'W_W', 'Q_W', 'D_W', 'DA_W']],
        on='ticker', how='inner', suffixes=('', '_sa'))
    h = m[m.M.notna()].copy()
    print(f"Merged with legs: {len(h)} tickers")

    h['z_psar'] = nz(h.combined_score, 0, 1.6)
    h['z_rank'] = nz(h.best_rank, 40, 75)
    h['z_M']    = nz(h.M.fillna(0), 40, 85)
    h['z_E']    = nz(h.E.fillna(0), 10, 60)
    h['z_DSR']  = nz(h.DSR.fillna(50), 20, 90)
    h['z_ADV']  = nz(h.ADV_play_now.fillna(0), 30, 80)
    h['master'] = (0.25 * h.z_psar + 0.20 * h.z_rank + 0.20 * h.z_M +
                   0.15 * h.z_E + 0.10 * h.z_DSR + 0.10 * h.z_ADV) * 100
    h['adv_usd'] = h.apply(adv_usd, axis=1)

    h.to_csv('/tmp/master_cross_system.csv', index=False)

    liquid = h[h.adv_usd >= 2e6].sort_values('master', ascending=False)
    liquid.to_csv('/tmp/final_master_liquid.csv', index=False)
    print(f"Liquid master (>= $2M/day USD): {len(liquid)}")

    coiled = h[(h.M.fillna(0) >= 65) & (h.DSR.fillna(0) >= 60) &
               (h.combined_score >= 0.5) & (h.E.fillna(99) < 35) &
               (h.adv_usd >= 2e6)].sort_values('M', ascending=False)
    coiled.to_csv('/tmp/final_coiled_springs.csv', index=False)
    print(f"Coiled springs (liquid): {len(coiled)}")

    cols = ['ticker', 'region', 'master', 'combined_score', 'best_rank',
            'M', 'E', 'DSR', 'adv_usd', 'rel_net_ma', 'asset_net_ma']
    print("\nTop 25 liquid master:")
    print(liquid.head(25)[cols].to_string(index=False, float_format=lambda x: f"{x:.1f}"))


if __name__ == "__main__":
    main()
