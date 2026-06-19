"""Financials-specific value screener.

PEG-style ratios are meaningless for banks/insurers/holdcos. Use the right
metrics for the right business:

  Banks & insurers:
    P/Tangible-Book       primary — book value should support the price floor
    P/E                   profitability multiple (less noisy than EBITDA for banks)
    ROE                   capital efficiency
    dividendYield         payout discipline + cash return
    earningsGrowth        durable growth, modest weight (volatile from reserves)

  Asset managers / brokers:
    P/E, ROE, dividendYield — same core
    P/B less informative (intangible-heavy)

Composite: sector-percentile rank within the Financial Services sector,
within the region. Lower-is-better for valuation multiples, higher-is-better
for ROE/yield/growth. Composite = mean of available percentiles.

We deliberately don't use EV/EBITDA, EV/Sales or any PEG variant here.

Outputs:
  results_peg/financials_value.csv      — every financial row scored
  results_peg/financials_top.csv        — top N per region
"""
from __future__ import annotations
import argparse, sys
from pathlib import Path
import pandas as pd
import numpy as np

CACHE = Path('.cache/yf')
OUT = Path('results_peg'); OUT.mkdir(exist_ok=True)


def safe(t): return ''.join(c if c.isalnum() or c in '-_' else '_' for c in t)


SUFFIX_REGION = {
    '': 'US', '.T': 'JP', '.KS': 'KR', '.KQ': 'KR', '.HK': 'HK',
    '.AX': 'AU', '.TO': 'CA', '.V': 'CA', '.L': 'GB', '.DE': 'DE',
    '.F': 'DE', '.PA': 'FR', '.ST': 'SE',
}
def _region(tk: str) -> str:
    if '.' in tk:
        return SUFFIX_REGION.get('.' + tk.rsplit('.', 1)[1], 'OTHER')
    return 'US'


def _load_financials(min_mcap: float) -> pd.DataFrame:
    """Walk the cache, keep only Financial Services sector rows."""
    rows = []
    for p in CACHE.glob('*__info_metrics.parquet'):
        tk = p.name.split('__')[0]
        orig = tk
        if '_' in tk:
            head, _, tail = tk.rpartition('_')
            if ('.' + tail) in {'.T','.KS','.KQ','.HK','.AX','.TO','.V','.L','.DE','.F','.PA','.ST'}:
                orig = head + '.' + tail
        try:
            d = pd.read_parquet(p)
            if d.empty: continue
            r = d.iloc[0].to_dict()
            sector = str(r.get('sector') or '')
            if 'Financial' not in sector: continue
            r['ticker'] = orig
            r['region'] = _region(orig)
            rows.append(r)
        except Exception: pass
    df = pd.DataFrame(rows)
    if df.empty: return df
    mc = pd.to_numeric(df['marketCap'], errors='coerce')
    df = df[mc.fillna(0) >= min_mcap]
    return df


def _try_load_balance_sheet_tbv(tk: str):
    """Return tangible book value (Stockholders Equity - Goodwill - Intangible Assets)
    from cached balance_sheet, or None."""
    p = CACHE / f'{safe(tk)}__balance_sheet.parquet'
    if not p.exists(): return None
    try:
        bs = pd.read_parquet(p)
        if bs is None or bs.empty: return None
        def _val(keys):
            for key in keys:
                for idx in bs.index:
                    if str(idx).strip().lower() == key.lower():
                        s = pd.to_numeric(bs.loc[idx], errors='coerce').dropna()
                        if not s.empty: return float(s.iloc[0])
            return 0.0
        equity = _val(['Common Stock Equity','Stockholders Equity',
                       'Total Equity Gross Minority Interest','Tangible Book Value'])
        if equity <= 0: return None
        # If the balance sheet directly has Tangible Book Value, prefer it
        for idx in bs.index:
            if str(idx).strip().lower() == 'tangible book value':
                s = pd.to_numeric(bs.loc[idx], errors='coerce').dropna()
                if not s.empty and float(s.iloc[0]) > 0:
                    return float(s.iloc[0])
        goodwill = _val(['Goodwill','Goodwill And Other Intangible Assets'])
        intangibles = _val(['Other Intangible Assets','Net Tangible Assets'])
        return max(0.0, equity - goodwill - intangibles)
    except Exception:
        return None


def compute(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    for c in ('marketCap','priceToBook','trailingPE','forwardPE',
              'returnOnEquity','returnOnAssets','dividendYield',
              'earningsGrowth','earningsQuarterlyGrowth','revenueGrowth',
              'currentPrice','bookValue','sharesOutstanding','totalRevenue'):
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors='coerce')

    # Tangible book value per share where balance sheet is cached
    p_tbv = []
    for tk in df['ticker']:
        tbv = _try_load_balance_sheet_tbv(tk)
        p_tbv.append(tbv)
    df['_tbv'] = p_tbv

    # P/TBV = marketCap / TBV when TBV available; fall back to priceToBook
    df['priceToTangibleBook'] = df['marketCap'] / df['_tbv']
    df['priceToTangibleBook'] = df['priceToTangibleBook'].where(
        df['priceToTangibleBook'].notna(), df['priceToBook'])

    # Sector-percentile rank within region (so French banks compete with
    # French banks, US insurers compete with US insurers).
    df['region_key'] = df['region'].fillna('OTHER')

    def pct(s, direction):
        s = pd.to_numeric(s, errors='coerce')
        rank = s.groupby(df['region_key']).rank(pct=True) * 100
        return (100 - rank) if direction == 'lo' else rank

    # Only positive multiples for "cheap" ranks
    pb_v  = df['priceToBook'].where(df['priceToBook'] > 0)
    ptbv  = df['priceToTangibleBook'].where(df['priceToTangibleBook'] > 0)
    pe_v  = df['trailingPE'].where(df['trailingPE'] > 0)
    pef_v = df['forwardPE'].where(df['forwardPE'] > 0)

    df['_pct_pb']    = pct(pb_v,                   'lo')
    df['_pct_ptbv']  = pct(ptbv,                   'lo')
    df['_pct_pe']    = pct(pe_v,                   'lo')
    df['_pct_pef']   = pct(pef_v,                  'lo')
    df['_pct_roe']   = pct(df['returnOnEquity'],   'hi')
    df['_pct_roa']   = pct(df['returnOnAssets'],   'hi')
    # dividendYield isn't in the cached KEEP list (yet); skip cleanly.
    if 'dividendYield' in df.columns:
        df['_pct_div'] = pct(df['dividendYield'], 'hi')
    else:
        df['_pct_div'] = np.nan
    df['_pct_eg']    = pct(df['earningsGrowth'],   'hi')

    pct_cols = ['_pct_pb','_pct_ptbv','_pct_pe','_pct_pef','_pct_roe','_pct_roa','_pct_div','_pct_eg']
    df['n_valid'] = df[pct_cols].notna().sum(axis=1)
    df['fin_composite'] = df[pct_cols].mean(axis=1, skipna=True)
    df.loc[df['n_valid'] < 4, 'fin_composite'] = np.nan
    return df


def display_top(df: pd.DataFrame, region: str, n: int):
    sub = df[df.region == region].dropna(subset=['fin_composite'])
    sub = sub.sort_values('fin_composite', ascending=False).head(n)
    if sub.empty:
        print(f'  (no rows for {region})'); return
    cols = ['ticker','longName','industry','marketCap_M','fin_composite',
            'priceToBook','priceToTangibleBook','trailingPE','forwardPE',
            'returnOnEquity','returnOnAssets','dividendYield','earningsGrowth']
    cols = [c for c in cols if c in sub.columns]
    out = sub[cols].copy()
    for c in out.columns:
        if c not in ('ticker','longName','industry'):
            out[c] = pd.to_numeric(out[c], errors='coerce').round(3)
    out['longName'] = out['longName'].astype(str).str.slice(0, 28)
    if 'industry' in out.columns:
        out['industry'] = out['industry'].astype(str).str.slice(0, 24)
    print(f'\n=== {region} financials top {len(out)} ===')
    print(out.to_string(index=False))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--min-mcap', type=float, default=100e6)
    ap.add_argument('--top-n', type=int, default=5)
    args = ap.parse_args()

    print(f'Loading financials from cache (mcap floor ${args.min_mcap/1e6:.0f}M)...')
    df = _load_financials(args.min_mcap)
    print(f'  {len(df)} financial-sector rows')
    if df.empty: return

    df['marketCap_M'] = df['marketCap'] / 1e6
    df = compute(df)
    n_tbv = df['_tbv'].notna().sum()
    print(f'  {n_tbv} rows with cached balance sheet (tangible book derived)')

    df.to_csv(OUT / 'financials_value.csv', index=False)
    print(f'\nWrote {OUT/"financials_value.csv"}')

    print('\n========= Per-region financials top-5 =========')
    for region in ['US','JP','KR','HK','AU','CA','GB','DE','FR','SE']:
        display_top(df, region, args.top_n)

    # Top file
    top = df.dropna(subset=['fin_composite']).sort_values('fin_composite', ascending=False)
    top.to_csv(OUT / 'financials_top.csv', index=False)


if __name__ == '__main__':
    main()
