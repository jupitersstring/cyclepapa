#!/usr/bin/env python3
"""Per-archetype ranked-firer dump for the rank 1-10 / 30-50 diligence review.

Usage:  python3 scratch_diligence_dump.py <arch_col> [more arch_cols...]
        python3 scratch_diligence_dump.py --list

For each archetype it ranks the firers by entry_today_asymmetry (ETA, the #1
ranking key the books sort on) and prints ranks 1-10 and 30-50 with the
diagnostic columns needed to judge whether a name honours the archetype's
SPIRIT. A name that fires but violates the thesis is the target.
"""
import sys
import pandas as pd
import numpy as np

pd.set_option('display.width', 260)
pd.set_option('display.max_columns', 60)
pd.set_option('display.max_colwidth', 30)

TAGS = pd.read_csv('archetype_tags.csv', low_memory=False)
ASYM = pd.read_csv('asymmetry_global.csv', low_memory=False)

# metrics that matter for spirit checks
COLS = ['symbol', 'name', 'sector', 'industry', 'country', 'src',
        'market_cap', 'entry_today_asymmetry', 'asymmetry_score', 'verdict',
        'ev_ebitda', 'p_e', 'p_s', 'pb', 'p_tb', 'ev_sales',
        'fcf_yield', 'dividend_yield', 'roce', 'roe',
        'ebitda_margin', 'op_margin', 'gross_margin',
        'net_debt_ebitda', 'debt_to_equity', 'net_cash_pct_mcap',
        'rev_yoy', 'revenue_ttm', 'revenue_5y_cagr',
        'roic_lindy', 'roiic_lindy', 'n_yrs_positive_roic', 'years_of_history',
        'insider_ownership_pct', 'n_analysts',
        'pct_off_52w_high', 'momentum_12m', 'roc_6m',
        'shares_growth_3y', 'shares_yoy', 'archetype_count']


def load(arch):
    a = ASYM.drop_duplicates('symbol')
    t = TAGS[['symbol', arch]].drop_duplicates('symbol')
    m = t.merge(a, on='symbol', how='left')
    m = m[m[arch] == 1].copy()
    m['entry_today_asymmetry'] = pd.to_numeric(
        m.get('entry_today_asymmetry'), errors='coerce')
    m = m.sort_values('entry_today_asymmetry', ascending=False)
    keep = [c for c in COLS if c in m.columns]
    return m[keep].reset_index(drop=True)


def dump(arch):
    m = load(arch)
    print('\n' + '=' * 120)
    print(f'{arch}   —   {len(m)} firers (ranked by entry_today_asymmetry)')
    print('=' * 120)
    if len(m) == 0:
        print('  (no firers)')
        return
    print('\n----- RANKS 1-10 -----')
    print(m.head(10).to_string())
    if len(m) > 29:
        print('\n----- RANKS 30-50 -----')
        print(m.iloc[29:50].to_string())
    if len(m) > 49:
        print('\n----- RANKS 50-100 (deep tail) -----')
        print(m.iloc[49:100].to_string())
    if len(m) <= 29:
        print(f'\n(only {len(m)} firers — no deeper bands)')


if __name__ == '__main__':
    if len(sys.argv) < 2 or sys.argv[1] == '--list':
        cols = [c for c in TAGS.columns if c.startswith('arch_')]
        print('\n'.join(cols))
        sys.exit(0)
    for arch in sys.argv[1:]:
        dump(arch)
