"""
Build universe_global.csv: the widest practical Yahoo-screenable universe.

Sources, merged and deduped:
  1. universe_us.csv            — full NYSE/NASDAQ/AMEX lists (run
                                  build_universe_us.py first)
  2. financedatabase            — ~151k global equities with Yahoo-style
                                  symbols, filtered to listed names with a
                                  known market-cap tier (~67k)

Rows are ordered Mega -> Nano cap so a rate-limited screening run prices
the most investable names first. Names financedatabase can't size
(market_cap NaN, mostly inactive or untracked listings) are excluded —
they are overwhelmingly dead symbols that would burn request budget.

Usage:
    pip install financedatabase
    python build_universe_global.py
"""
import re
from pathlib import Path

import pandas as pd

CAP_ORDER = ['Mega Cap', 'Large Cap', 'Mid Cap', 'Small Cap',
             'Micro Cap', 'Nano Cap']
SYMBOL_OK = re.compile(r'^[A-Z0-9][A-Z0-9.\-]{0,19}$')


def load_financedatabase() -> pd.DataFrame:
    import financedatabase as fd
    df = fd.Equities().select().reset_index()
    df = df[(df['delisted'] == False)
            & df['market_cap'].isin(CAP_ORDER)
            & df['symbol'].astype(str).str.match(SYMBOL_OK)]
    df['market_cap'] = pd.Categorical(df['market_cap'], CAP_ORDER, ordered=True)
    df = df.sort_values('market_cap')
    return pd.DataFrame({
        'ticker': df['symbol'],
        'exchange': df['exchange'].fillna(''),
        'index_tag': 'FD_' + df['market_cap'].astype(str).str.replace(' Cap', '').str.upper(),
        'name': df['name'].fillna(''),
        'sector': df['sector'].fillna(''),
    })


def main():
    frames = []
    us = Path(__file__).with_name('universe_us.csv')
    if us.exists():
        # keep_default_na=False: 'NA' is a real NASDAQ ticker, not missing data
        frames.append(pd.read_csv(us, dtype={'ticker': str},
                                  keep_default_na=False))
    frames.append(load_financedatabase())
    uni = pd.concat(frames, ignore_index=True).drop_duplicates('ticker')
    out = Path(__file__).with_name('universe_global.csv')
    uni.to_csv(out, index=False)
    print(f"universe_global.csv: {len(uni)} tickers "
          f"({uni['index_tag'].str.startswith('FD_').sum()} from financedatabase)")
    print(uni['index_tag'].value_counts().head(12).to_string())


if __name__ == '__main__':
    main()
