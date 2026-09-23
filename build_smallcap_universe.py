"""Build a tradeable small-cap universe (mktcap $50M-$2B, $ADV>=750k, real
equity) from FMP profile-bulk intersected with our master universe, excluding
the already-fetched liquid-500. Writes /tmp/smallcap_universe.json.

Prereq: /tmp/fmp_bulk/profile_*.csv (FMP profile-bulk parts).
"""
import pandas as pd, glob, json
prof = pd.concat([pd.read_csv(f) for f in sorted(glob.glob('/tmp/fmp_bulk/profile_*.csv'))], ignore_index=True)
prof = prof.drop_duplicates('symbol')
m = pd.read_csv('/tmp/master_full_universe.csv', low_memory=False)
uni = set(m.ticker.astype(str))
cov = prof[prof.symbol.isin(uni)].copy()
adv = cov['averageVolume'] * cov['price']
sc = cov[(cov.marketCap.between(50e6, 2e9)) & (adv >= 7.5e5)
         & (~cov.isEtf.fillna(False)) & (~cov.isFund.fillna(False))
         & (cov.isActivelyTrading.fillna(True))].assign(advp=adv)
liq500 = set(m[m.adv_usd.notna()].sort_values('adv_usd', ascending=False).ticker.astype(str).head(500))
sc = sc[~sc.symbol.isin(liq500)].sort_values('advp', ascending=False)
N = 1800
json.dump(sc.symbol.head(N).tolist(), open('/tmp/smallcap_universe.json', 'w'))
print(f"small-cap universe: {min(N,len(sc))} of {len(sc)} candidates")
