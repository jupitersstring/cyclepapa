"""Phase 2: derive remaining gaps from balance sheet.

After fill_gaps.py runs, the remaining unfillable-from-income gaps are
priceToBook (need shareholder equity) and forwardPE (need analyst
estimates, often unavailable for non-US).

This script:
  - Fetches yfinance Ticker.balance_sheet for any top-50 row with NaN priceToBook
  - Derives P/B = marketCap / (Common Stock Equity || Stockholders Equity)
  - Tries Ticker.earnings_estimate for forward EPS → derives forwardPE
    (only succeeds for a small fraction of non-US names)
  - Writes back to results_peg/per_region_top_combined.csv with provenance
    appended to _filled_from

Caches both into .cache/yf/<safe>__balance_sheet.parquet and
__earnings_estimate.parquet so future runs reuse them.
"""
from __future__ import annotations
from pathlib import Path
import pandas as pd
import numpy as np
import time
import yfinance as yf

CACHE = Path('.cache/yf')
COMBINED = Path('results_peg/per_region_top_combined.csv')


def safe(t): return ''.join(c if c.isalnum() or c in '-_' else '_' for c in t)


def fetch_balance(tk: str):
    p = CACHE / f'{safe(tk)}__balance_sheet.parquet'
    if p.exists():
        try: return pd.read_parquet(p)
        except: pass
    try:
        bs = yf.Ticker(tk).balance_sheet
        if bs is not None and not bs.empty:
            bs.to_parquet(p)
            return bs
    except Exception: pass
    return None


def fetch_eps_est(tk: str):
    p = CACHE / f'{safe(tk)}__earnings_estimate.parquet'
    if p.exists():
        try: return pd.read_parquet(p)
        except: pass
    try:
        ee = yf.Ticker(tk).earnings_estimate
        if ee is not None and not (hasattr(ee, 'empty') and ee.empty):
            ee.to_parquet(p)
            return ee
    except Exception: pass
    return None


def info_marketcap_currency(tk: str):
    p = CACHE / f'{safe(tk)}__info_metrics.parquet'
    if not p.exists(): return None, None, None
    d = pd.read_parquet(p).iloc[0].to_dict()
    return d.get('marketCap'), d.get('currentPrice'), d.get('currency')


def derive_pb(tk: str):
    mcap, _, _ = info_marketcap_currency(tk)
    if not mcap: return None
    bs = fetch_balance(tk)
    if bs is None or bs.empty: return None
    # Try equity rows in order of preference
    for key in ('Common Stock Equity','Stockholders Equity',
                'Total Equity Gross Minority Interest','Tangible Book Value'):
        for idx in bs.index:
            if str(idx).strip().lower() == key.lower():
                eq = pd.to_numeric(bs.loc[idx], errors='coerce').dropna()
                if not eq.empty and float(eq.iloc[0]) > 0:
                    return float(mcap) / float(eq.iloc[0])
    return None


def derive_fwd_pe(tk: str):
    mcap, price, _ = info_marketcap_currency(tk)
    if not price: return None
    ee = fetch_eps_est(tk)
    if ee is None or ee.empty: return None
    # earnings_estimate is a DataFrame with rows like '+1y' and 'avg' column
    for row_key in ('+1y','+2y','0y','+0q','+1q'):
        if row_key in ee.index:
            row = ee.loc[row_key]
            for col in ('avg','low','high'):
                if col in row.index:
                    v = pd.to_numeric(row[col], errors='coerce')
                    if pd.notna(v) and float(v) > 0:
                        return float(price) / float(v)
    return None


def main():
    df = pd.read_csv(COMBINED)
    print(f'Phase 2 gap-fill on {len(df)} rows...')
    n_pb = n_pe = 0
    for i, r in df.iterrows():
        tk = str(r['ticker'])
        notes = str(r.get('_filled_from','')).strip()
        new_notes = []
        if pd.isna(r.get('priceToBook')):
            pb = derive_pb(tk)
            if pb is not None and pb > 0:
                df.at[i, 'priceToBook'] = pb
                new_notes.append('priceToBook<-MC/StockholdersEquity')
                n_pb += 1
                print(f'  {tk}: P/B = {pb:.2f}')
        if pd.isna(r.get('forwardPE')):
            fpe = derive_fwd_pe(tk)
            if fpe is not None and fpe > 0:
                df.at[i, 'forwardPE'] = fpe
                new_notes.append('forwardPE<-EPS_est')
                n_pe += 1
                print(f'  {tk}: forwardPE = {fpe:.2f}')
        if new_notes:
            df.at[i, '_filled_from'] = (notes + '; ' + '; '.join(new_notes)).strip('; ')
        time.sleep(0.3)
    df.to_csv(COMBINED, index=False)
    print(f'\nFilled: priceToBook={n_pb}/50, forwardPE={n_pe}/50')
    # Summary
    key_cols = ['priceToBook','trailingPE','forwardPE','enterpriseToEbitda',
                'fcfYield_pct','grossMargins','operatingMargins','revenueGrowth','earningsGrowth']
    print('\nRemaining NaN after phase 2:')
    for c in key_cols:
        if c in df.columns:
            print(f'  {c}: {df[c].isna().sum()}/{len(df)}')


if __name__ == '__main__':
    main()
