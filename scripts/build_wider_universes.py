#!/usr/bin/env python3
"""Build universes for 18 ADDITIONAL markets — both smid (nano/micro/small/mid)
and large (large/mega) buckets. Excludes tickers already in the 21 existing
markets to avoid double-pulling."""
import os, sys
import financedatabase as fd
import pandas as pd

eq = fd.Equities()

# New markets: (key, country, yfinance suffix(es) to filter to)
NEW_MARKETS = {
    'india':       ('India',         ['.NS','.BO']),
    'china':       ('China',         ['.SS','.SZ']),
    'thailand':    ('Thailand',      ['.BK']),
    'brazil':      ('Brazil',        ['.SA']),
    'israel':      ('Israel',        ['.TA']),
    'indonesia':   ('Indonesia',     ['.JK']),
    'southafrica': ('South Africa',  ['.JO']),
    'ireland':     ('Ireland',       ['.IR','.L']),
    'turkey':      ('Turkey',        ['.IS']),
    'chile':       ('Chile',         ['.SN']),
    'poland':      ('Poland',        ['.WA']),
    'mexico':      ('Mexico',        ['.MX']),
    'greece':      ('Greece',        ['.AT']),
    'portugal':    ('Portugal',      ['.LS']),
    'argentina':   ('Argentina',     ['.BA']),
    'malaysia':    ('Malaysia',      ['.KL']),
    'philippines': ('Philippines',   ['.PS']),
    'austria':     ('Austria',       ['.VI']),
}

# Collect ALL existing tickers from prior universes (smid + large) to dedupe
existing_tickers = set()
for d in ['data/universes', 'data/universes/large']:
    if os.path.isdir(d):
        for f in os.listdir(d):
            if f.startswith('uni_') and f.endswith('.csv'):
                try:
                    df = pd.read_csv(os.path.join(d, f))
                    existing_tickers.update(df['ticker'].dropna().astype(str).tolist())
                except Exception:
                    pass
print(f"Existing universe tickers: {len(existing_tickers)}", file=sys.stderr)

os.makedirs('data/universes', exist_ok=True)
os.makedirs('data/universes/large', exist_ok=True)

smid_caps = ['Nano Cap','Micro Cap','Small Cap','Mid Cap']
large_caps = ['Large Cap','Mega Cap']

total_smid = total_large = 0
for key, (country, suffixes) in NEW_MARKETS.items():
    try:
        df = eq.select(country=country)
        df = df.reset_index().rename(columns={'symbol':'ticker'})
        # yfinance suffix filter
        if suffixes:
            mask = df['ticker'].apply(lambda t: isinstance(t,str) and any(t.endswith(s) for s in suffixes))
            df = df[mask]
        # dedupe against existing
        df = df[~df['ticker'].isin(existing_tickers)]
        # split
        smid = df[df['market_cap'].isin(smid_caps)][['ticker','name','sector','industry','market_cap']]
        large = df[df['market_cap'].isin(large_caps)][['ticker','name','sector','industry','market_cap']]
        smid.to_csv(f'data/universes/uni_{key}.csv', index=False)
        large.to_csv(f'data/universes/large/uni_{key}_lg.csv', index=False)
        total_smid += len(smid); total_large += len(large)
        print(f"  {key:<12}: smid={len(smid):>5}  large={len(large):>5}", file=sys.stderr)
    except Exception as e:
        print(f"  {key} ERR: {e}", file=sys.stderr)

print(f"\nNew universe total: smid={total_smid} large={total_large} grand_total={total_smid+total_large}", file=sys.stderr)
