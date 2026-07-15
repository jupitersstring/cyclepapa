#!/usr/bin/env python3
"""Build Large + Mega cap universes per market via financedatabase.

Writes data/universes/large/uni_<mkt>_lg.csv — only tickers that are NOT in
the existing nano/micro/small/mid universes (so we don't duplicate work).
"""
import os, sys
import financedatabase as fd
import pandas as pd

OUT_DIR = 'data/universes/large'
os.makedirs(OUT_DIR, exist_ok=True)

eq = fd.Equities()

MARKETS = {
    'us':         ('United States',    ['NMS','NYQ','NCM','ASE','NGM','PCX']),
    'uk':         ('United Kingdom',   None),
    'italy':      ('Italy',             None),
    'japan':      ('Japan',             None),
    'australia':  ('Australia',         None),
    'canada':     ('Canada',            None),
    'taiwan':     ('Taiwan',            None),
    'korea':      ('South Korea',       None),
    'singapore':  ('Singapore',         None),
    'sweden':     ('Sweden',            None),
    'finland':    ('Finland',           None),
    'norway':     ('Norway',            None),
    'denmark':    ('Denmark',           None),
    'france':     ('France',            None),
    'germany':    ('Germany',           None),
    'netherlands':('Netherlands',       None),
    'belgium':    ('Belgium',           None),
    'hk':         ('Hong Kong',         None),
    'nz':         ('New Zealand',       None),
    'spain':      ('Spain',             None),
    'switzerland':('Switzerland',       None),
}

total = 0
for key, (country, exchanges) in MARKETS.items():
    try:
        df = eq.select(country=country)
        if exchanges:
            df = df[df['exchange'].isin(exchanges)]
        df = df[df['market_cap'].isin(['Large Cap','Mega Cap'])]
        df = df.reset_index().rename(columns={'symbol':'ticker'})

        # Exclude tickers already in our nano/micro/small/mid universe (no double work)
        small_path = f'data/universes/uni_{key}.csv'
        if os.path.exists(small_path):
            sm = pd.read_csv(small_path)
            df = df[~df['ticker'].isin(sm['ticker'])]
        df = df[['ticker','name','sector','industry','market_cap']]
        df.to_csv(f'{OUT_DIR}/uni_{key}_lg.csv', index=False)
        print(f"  {key:<12}: {len(df)}", file=sys.stderr)
        total += len(df)
    except Exception as e:
        print(f"  {key} ERR: {e}", file=sys.stderr)

print(f"\nTotal large+mega cap tickers: {total}", file=sys.stderr)
