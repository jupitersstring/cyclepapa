#!/usr/bin/env python3
"""Build expanded US + UK + European universes — broader exchange + cap inclusion.

Outputs:
  data/universes/expanded/uni_<mkt>_x.csv

Adds:
  US:    PNK pink sheets, NCM/NYQ/NMS/ASE/NGM, null-market-cap names
  UK:    full LSE + AIM (no cap restriction)
  EU:    all primary exchanges for 14 countries; no cap restriction
"""
import os, sys
import financedatabase as fd
import pandas as pd

OUT = 'data/universes/expanded'
os.makedirs(OUT, exist_ok=True)

eq = fd.Equities()

def primary_only(df, suffixes):
    """Keep only tickers with primary native exchange suffixes."""
    if not suffixes: return df
    mask = df['ticker'].apply(lambda t: isinstance(t,str) and any(t.endswith(s) for s in suffixes))
    return df[mask]

# Existing universes (used for dedup)
existing = set()
for d in ['data/universes', 'data/universes/large']:
    if os.path.isdir(d):
        for f in os.listdir(d):
            if f.startswith('uni_') and f.endswith('.csv'):
                try: existing.update(pd.read_csv(os.path.join(d,f))['ticker'].dropna().astype(str).tolist())
                except: pass
print(f"Existing tickers: {len(existing)}", file=sys.stderr)

# ─── US expansion ───
print("\n=== US ===", file=sys.stderr)
us = eq.select(country='United States').reset_index().rename(columns={'symbol':'ticker'})
us = us[us['exchange'].isin(['NMS','NYQ','NCM','ASE','NGM','PCX','PNK','OEM','OTC'])]
us = us[~us['ticker'].isin(existing)]
us[['ticker','name','sector','industry','market_cap','exchange']].to_csv(f'{OUT}/uni_us_x.csv', index=False)
print(f"  US expansion: {len(us)} new tickers", file=sys.stderr)
print(f"  exchanges: {us['exchange'].value_counts().to_dict()}", file=sys.stderr)

# ─── UK expansion ───
print("\n=== UK ===", file=sys.stderr)
uk = eq.select(country='United Kingdom').reset_index().rename(columns={'symbol':'ticker'})
uk = primary_only(uk, ['.L','.IL'])  # LSE primary + AIM
uk = uk[~uk['ticker'].isin(existing)]
uk[['ticker','name','sector','industry','market_cap','exchange']].to_csv(f'{OUT}/uni_uk_x.csv', index=False)
print(f"  UK expansion: {len(uk)} new tickers", file=sys.stderr)

# ─── Europe expansion ───
EUROPE = {
    'germany':    ['.DE','.F','.MU','.SG','.HM','.HA','.BE','.DU'],
    'france':     ['.PA','.NX'],
    'italy':      ['.MI'],
    'spain':      ['.MC'],
    'netherlands':['.AS'],
    'belgium':    ['.BR'],
    'switzerland':['.SW','.S'],
    'sweden':     ['.ST','.STO'],
    'norway':     ['.OL'],
    'finland':    ['.HE'],
    'denmark':    ['.CO'],
    'austria':    ['.VI'],
    'ireland':    ['.IR','.DE','.L'],
    'portugal':   ['.LS'],
    'greece':     ['.AT'],
}
country_map = {
    'germany':'Germany','france':'France','italy':'Italy','spain':'Spain',
    'netherlands':'Netherlands','belgium':'Belgium','switzerland':'Switzerland',
    'sweden':'Sweden','norway':'Norway','finland':'Finland','denmark':'Denmark',
    'austria':'Austria','ireland':'Ireland','portugal':'Portugal','greece':'Greece',
}
for key, suffs in EUROPE.items():
    df = eq.select(country=country_map[key]).reset_index().rename(columns={'symbol':'ticker'})
    df = primary_only(df, suffs)
    df = df[~df['ticker'].isin(existing)]
    df[['ticker','name','sector','industry','market_cap','exchange']].to_csv(f'{OUT}/uni_{key}_x.csv', index=False)
    print(f"  {key}: +{len(df)}", file=sys.stderr)
