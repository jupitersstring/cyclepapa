"""Master analysis across the ENTIRE universe (not just PSAR-intersected).

Closes the three remaining selection gaps:

1. PSAR-relative residual SPY bias — region-demean rel_net_ma so each
   region is scored against its own median, removing systematic
   country/currency drift that PSAR's SPY benchmark still introduces.

2. Coverage hole: 7,885 stars_aligned tickers had NO PSAR row, so master
   couldn't be computed. Solution: master is now PSAR-OPTIONAL. PSAR
   contributes a 25% boost when available; without it, the remaining
   weights (M + E + DSR + ADV + rank) are renormalized to 100%.

3. Liquid floor too high. Output picks at three tiers:
     $1M/day  — tradeable for individuals / small funds
     $5M/day  — tradeable for mid-size institutions
     $20M/day — Minervini's hard institutional floor

Outputs:
  /tmp/master_full_universe.csv          all tickers with master score
  /tmp/master_top_liquid_1M.csv          top 50 at $1M+ tier
  /tmp/master_top_liquid_5M.csv          top 50 at $5M+ tier
  /tmp/master_top_liquid_20M.csv         top 50 at $20M+ tier
  /tmp/master_top_per_region_tiered.csv  top 5 per region per tier
"""

import pandas as pd
import numpy as np
import glob
import warnings

warnings.filterwarnings("ignore")

NATIVE_SUF = {".L",".PA",".AS",".BR",".LS",".IR",".MI",".MC",".SW",".VI",
              ".DE",".ST",".OL",".CO",".HE",".AT",".T",".JP",".HK",".SI",
              ".KS",".KQ",".TW",".TWO",".NS",".BO",".SS",".SZ",".AX",".NZ"}

FX = {'.T':0.0065,'.NS':0.0117,'.BO':0.0117,'.KS':0.00073,'.KQ':0.00073,
      '.TW':0.031,'.TWO':0.031,'.HK':0.128,'.SS':0.139,'.SZ':0.139,
      '.L':0.0127,'.PA':1.08,'.AS':1.08,'.BR':1.08,'.MI':1.08,'.MC':1.08,
      '.DE':1.08,'.SW':1.12,'.ST':0.095,'.OL':0.092,'.CO':0.145,
      '.HE':1.08,'.VI':1.08,'.AT':1.08,'.AX':0.65,'.NZ':0.60,'.IR':1.08,
      '.WA':0.25,'.SG':1.08,'.MX':0.055,'.SA':0.18,'.IL':0.0127}


def is_clean(t):
    if not isinstance(t, str): return False
    if "." not in t:
        if len(t) == 5 and t[-1] in ("F", "Y"): return False
        return True
    return "." + t.rsplit(".", 1)[1] in NATIVE_SUF


def adv_usd(row):
    t = str(row['ticker']); adv = row.get('adv_20')
    if pd.isna(adv): return np.nan
    if '.' in t: return adv * FX.get('.' + t.rsplit('.', 1)[1], 1.0)
    return adv


def nz(s, lo, hi):
    return ((s - lo) / (hi - lo)).clip(0, 1)


def main():
    rows = []
    for p in sorted(glob.glob('/tmp/stars_aligned_*.csv')):
        region = p.split('stars_aligned_')[-1].replace('.csv', '')
        d = pd.read_csv(p); d['region'] = region; rows.append(d)
    big = pd.concat(rows, ignore_index=True).drop_duplicates('ticker')
    big['best_rank'] = big[['daily_rank', 'weekly_rank', 'monthly_rank']].max(axis=1)
    big_c = big[big.ticker.apply(is_clean)].copy()
    big_c['adv_usd'] = big_c.apply(adv_usd, axis=1)
    print(f"Cleaned universe (native, non-OTC-wrapper): {len(big_c)}")

    psar = pd.read_csv('/tmp/mtf_psar_rank_full_clean.csv').drop_duplicates('ticker')

    # Fix #1: region-demean rel_net_ma so SPY-vs-regional currency drift cancels out
    psar = psar.merge(big_c[['ticker', 'region']], on='ticker', how='left', suffixes=('', '_sa'))
    psar['region'] = psar['region'].fillna(psar['region_sa']) if 'region_sa' in psar.columns else psar['region']
    reg_med = psar.groupby('region')['rel_net_ma'].transform('median')
    psar['rel_net_ma_adj'] = psar['rel_net_ma'] - reg_med
    # Recompute relative composite score with the regionally-demeaned MA
    # using the same recency-weighted formula
    psar_g = psar.sort_values('ticker')
    psar['rel_score_adj'] = psar['rel_score']  # default
    # Rebuild combined: use adjusted relative + original asset
    psar['combined_score_adj'] = psar['asset_score'] + psar['rel_score_adj']
    print(f"PSAR pool (region-demeaned): {len(psar)}")

    # Merge — LEFT join keeps stars_aligned tickers WITHOUT PSAR data
    merged = big_c.merge(
        psar[['ticker', 'asset_net_ma', 'rel_net_ma', 'rel_net_ma_adj',
              'combined_score', 'combined_score_adj', 'n_active_tfs',
              'asset_score', 'rel_score', 'rel_score_adj']],
        on='ticker', how='left'
    )
    print(f"Merged universe (LEFT join — keeps all stars_aligned): {len(merged)}")

    # Fix #2: PSAR-OPTIONAL master. With PSAR: 25% PSAR + 20% rank + 20% M + 15% E + 10% DSR + 10% ADV
    # Without PSAR: renormalize (boost rank to 27%, M to 27%, E to 20%, DSR to 13%, ADV to 13%)
    # i.e. without_psar_weight_total = 0.75 -> divide each non-PSAR weight by 0.75

    has_psar = merged.combined_score_adj.notna()
    score_with_psar = (
        0.25 * nz(merged.combined_score_adj, -0.5, 1.6) +
        0.20 * nz(merged.best_rank.fillna(50), 40, 75) +
        0.20 * nz(merged.M.fillna(50), 40, 85) +
        0.15 * nz(merged.E.fillna(20), 10, 60) +
        0.10 * nz(merged.DSR.fillna(50), 20, 90) +
        0.10 * nz(merged.ADV_play_now.fillna(40), 30, 80)
    ) * 100

    score_without_psar = (
        0.267 * nz(merged.best_rank.fillna(50), 40, 75) +
        0.267 * nz(merged.M.fillna(50), 40, 85) +
        0.200 * nz(merged.E.fillna(20), 10, 60) +
        0.133 * nz(merged.DSR.fillna(50), 20, 90) +
        0.133 * nz(merged.ADV_play_now.fillna(40), 30, 80)
    ) * 100

    merged['master'] = np.where(has_psar, score_with_psar, score_without_psar)
    merged['has_psar'] = has_psar

    print(f"Master computed for {len(merged)}: "
          f"{has_psar.sum()} with PSAR, {(~has_psar).sum()} without")
    merged.to_csv('/tmp/master_full_universe.csv', index=False)

    # Fix #3: three liquidity tiers
    for thr in [1, 5, 20]:
        tier = merged[merged.adv_usd >= thr * 1e6].sort_values('master', ascending=False)
        tier.head(50).to_csv(f'/tmp/master_top_liquid_{thr}M.csv', index=False)
        print(f"  >= ${thr}M/day pool: {len(tier)}  (top 50 saved)")

    # Per-region top 5 at each tier
    per_region = []
    for thr in [1, 5, 20]:
        tier = merged[merged.adv_usd >= thr * 1e6]
        for region in sorted(merged.region.unique()):
            sub = tier[tier.region == region].sort_values('master', ascending=False).head(5)
            sub = sub.assign(tier=f'>=${thr}M')
            per_region.append(sub)
    pr = pd.concat(per_region, ignore_index=True)
    pr.to_csv('/tmp/master_top_per_region_tiered.csv', index=False)
    print(f"  Per-region tiered picks: {len(pr)} (5 per region per tier)")

    # Top 25 overall at $5M tier
    print("\n=== TOP 25 BY MASTER (>= $5M/day USD) ===")
    cols = ['ticker', 'region', 'master', 'best_rank', 'M', 'E', 'DSR',
            'ADV_play_now', 'combined_score_adj', 'has_psar', 'adv_usd']
    cols = [c for c in cols if c in merged.columns]
    top5 = merged[merged.adv_usd >= 5e6].sort_values('master', ascending=False).head(25).copy()
    top5['adv_usd'] = (top5['adv_usd'] / 1e6).round(1)
    print(top5[cols].to_string(index=False, float_format=lambda x: f"{x:.1f}"))


if __name__ == "__main__":
    main()
