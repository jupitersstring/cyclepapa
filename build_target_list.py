"""Build a target list of high-conviction names from all current rankings
and emit a list (one ticker per line) for downstream fetching.

Pulls from:
  - results_peg/per_region_top_combined.csv (top-5 per region per measure)
  - results_peg/growth_adj_value.csv (durable cut, top by ev_ebitda_g_bv and ev_sales_g_bv)
  - results_peg/financials_value.csv (top by fin_composite)
  - results_peg/per_region_<R>_full.csv (top 10 by composite per region)

Output: results_peg/deep_fetch_targets.txt
"""
from __future__ import annotations
from pathlib import Path
import pandas as pd
import numpy as np

OUT = Path('results_peg')
REGIONS = ['US','JP','GB','DE','FR','CA','AU',
           'CH','IT','NL','ES','SE','NO','DK','BE','FI','IE','AT','PT','GR',
           'KR','HK','TW','SG','NZ','IL',
           'CN','IN','BR','MX','ZA','TR','TH','ID']


def main():
    tickers = set()

    # 1. Combined per-region top-5 (already deduped by region+measure)
    if (OUT / 'per_region_top_combined.csv').exists():
        df = pd.read_csv(OUT / 'per_region_top_combined.csv')
        for tk in df['ticker'].astype(str):
            tickers.add(tk)
        print(f'  per_region_top_combined: +{len(df)} -> {len(tickers)} unique')

    # 2. Top 10 per region from each per_region_full.csv (composite > 50)
    for r in REGIONS:
        p = OUT / f'per_region_{r}_full.csv'
        if not p.exists(): continue
        df = pd.read_csv(p)
        top10 = df.sort_values('composite', ascending=False).head(10)
        for tk in top10['ticker'].astype(str):
            tickers.add(tk)
    print(f'  + top 10 per region composite -> {len(tickers)}')

    # 3. Growth-adj durable top per region (EV/EBITDA/g_bv and EV/Sales/g_bv)
    if (OUT / 'growth_adj_value.csv').exists():
        df = pd.read_csv(OUT / 'growth_adj_value.csv', low_memory=False)
        # Durable cut
        eg = pd.to_numeric(df.get('earn_g_pct'), errors='coerce')
        rg = pd.to_numeric(df.get('rev_g_pct'), errors='coerce')
        dur = df[eg.between(10, 100, inclusive='both') | (eg.isna() & rg.between(10, 100, inclusive='both'))]
        # Top 10 per region per metric
        for col in ('ev_ebitda_g_bv','ev_sales_g_bv'):
            top = dur.dropna(subset=[col]).sort_values(col).groupby('region').head(10)
            for tk in top['ticker'].astype(str):
                tickers.add(tk)
        print(f'  + top 10 per region per growth-adj metric -> {len(tickers)}')

    # 4. Financials top 10 per region
    if (OUT / 'financials_value.csv').exists():
        df = pd.read_csv(OUT / 'financials_value.csv', low_memory=False)
        top = df.dropna(subset=['fin_composite']).sort_values('fin_composite', ascending=False).groupby('region').head(10)
        for tk in top['ticker'].astype(str):
            tickers.add(tk)
    print(f'  + top 10 per region financials -> {len(tickers)}')

    # Filter out NaN strings if any
    tickers = {t for t in tickers if t and t.lower() != 'nan'}

    # Write
    out_path = OUT / 'deep_fetch_targets.txt'
    out_path.write_text('\n'.join(sorted(tickers)) + '\n')
    print(f'\nWrote {out_path}: {len(tickers)} unique tickers')


if __name__ == '__main__':
    main()
