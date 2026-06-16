"""Backfill missing valuation fields for the per-region top-50 list.

For each ticker, take the row from results_peg/per_region_top_combined.csv
and try to derive any NaN field from the cached deeper slots:

  trailingPE       <- currentPrice / sum-of-last-4-quarters Diluted EPS
                      (falls back to latest annual EPS)
  enterpriseToEbitda <- enterpriseValue / latest annual EBITDA
  revenueGrowth    <- latest annual Total Revenue YoY
  earningsGrowth   <- latest annual Net Income YoY
  fcfYield_pct     <- latest annual Free Cash Flow / marketCap × 100
  grossMargins     <- latest annual Gross Profit / Total Revenue

Writes back to results_peg/per_region_top_combined.csv with a
`_filled_from` column noting which fields we backfilled and from where,
so the lineage is auditable.

Usage:
    python fill_gaps.py
"""
from __future__ import annotations
from pathlib import Path
import pandas as pd
import numpy as np

CACHE = Path('.cache/yf')
COMBINED = Path('results_peg/per_region_top_combined.csv')


def safe(t): return ''.join(c if c.isalnum() or c in '-_' else '_' for c in t)


def load_slot(tk: str, slot: str):
    p = CACHE / f'{safe(tk)}__{slot}.parquet'
    if not p.exists(): return None
    try:
        d = pd.read_parquet(p)
        return d if not d.empty else None
    except Exception: return None


def info(tk):
    d = load_slot(tk, 'info_metrics')
    return d.iloc[0].to_dict() if d is not None else {}


def _col(df, candidates):
    if df is None or df.empty: return None
    items_in_index = (pd.api.types.is_datetime64_any_dtype(df.columns)
                      or any(isinstance(c, pd.Timestamp) for c in df.columns[:3]))
    for c in candidates:
        if items_in_index:
            matches = [ix for ix in df.index if str(ix) == c or str(ix).startswith(c[:10])]
            if matches:
                s = pd.to_numeric(df.loc[matches[0]], errors='coerce').dropna()
                if not s.empty: return s.sort_index()
        else:
            if c in df.columns:
                s = pd.to_numeric(df[c], errors='coerce').dropna()
                if not s.empty: return s.sort_index()
    return None


def _ltm_or_annual(quarterly, annual):
    """Return (LTM amount from rolling-4Q, or latest annual)."""
    if quarterly is not None and len(quarterly) >= 4:
        s = quarterly.sort_index()
        ltm = s.rolling(4).sum().dropna()
        if not ltm.empty:
            return float(ltm.iloc[-1]), 'quarterly_LTM'
    if annual is not None and not annual.empty:
        return float(annual.sort_index().iloc[-1]), 'annual'
    return None, None


def derive(tk: str, row: dict) -> dict:
    """Return updated row + provenance string."""
    i = info(tk)
    iq = load_slot(tk, 'income')
    ia = load_slot(tk, 'income_annual')
    cq = load_slot(tk, 'cashflow')
    ca = load_slot(tk, 'cashflow_annual')

    price = i.get('currentPrice') or i.get('regularMarketPrice')
    mcap  = i.get('marketCap')
    ev    = i.get('enterpriseValue')

    rev_q  = _col(iq, ['Total Revenue','Revenue','Operating Revenue']) if iq is not None else None
    rev_a  = _col(ia, ['Total Revenue','Revenue','Operating Revenue']) if ia is not None else None
    gp_q   = _col(iq, ['Gross Profit']) if iq is not None else None
    gp_a   = _col(ia, ['Gross Profit']) if ia is not None else None
    ni_q   = _col(iq, ['Net Income','Net Income Common Stockholders']) if iq is not None else None
    ni_a   = _col(ia, ['Net Income','Net Income Common Stockholders']) if ia is not None else None
    eps_q  = _col(iq, ['Diluted EPS','Basic EPS']) if iq is not None else None
    eps_a  = _col(ia, ['Diluted EPS','Basic EPS']) if ia is not None else None
    ebd_q  = _col(iq, ['EBITDA','Normalized EBITDA']) if iq is not None else None
    ebd_a  = _col(ia, ['EBITDA','Normalized EBITDA']) if ia is not None else None
    fcf_q  = _col(cq, ['Free Cash Flow','FreeCashFlow']) if cq is not None else None
    fcf_a  = _col(ca, ['Free Cash Flow','FreeCashFlow']) if ca is not None else None

    filled = []

    def isnan(v): return v is None or (isinstance(v, float) and np.isnan(v))

    # trailingPE
    if isnan(row.get('trailingPE')) and price:
        eps_ltm, src = _ltm_or_annual(eps_q, eps_a)
        if eps_ltm and eps_ltm > 0:
            row['trailingPE'] = float(price) / eps_ltm
            filled.append(f'trailingPE<-EPS_{src}')

    # enterpriseToEbitda
    if isnan(row.get('enterpriseToEbitda')) and ev:
        ebd, src = _ltm_or_annual(ebd_q, ebd_a)
        if ebd and ebd != 0:
            row['enterpriseToEbitda'] = float(ev) / ebd
            filled.append(f'evEbitda<-EBITDA_{src}')

    # revenueGrowth
    if isnan(row.get('revenueGrowth')):
        if rev_a is not None and len(rev_a) >= 2:
            cur = float(rev_a.iloc[-1]); prv = float(rev_a.iloc[-2])
            if prv > 0:
                row['revenueGrowth'] = (cur/prv - 1)
                filled.append('revenueGrowth<-rev_annual')

    # earningsGrowth (use net income annual YoY)
    if isnan(row.get('earningsGrowth')):
        if ni_a is not None and len(ni_a) >= 2:
            cur = float(ni_a.iloc[-1]); prv = float(ni_a.iloc[-2])
            if prv != 0:
                row['earningsGrowth'] = (cur/prv - 1)
                filled.append('earningsGrowth<-NI_annual')

    # fcfYield_pct
    if isnan(row.get('fcfYield_pct')) and mcap:
        fcf, src = _ltm_or_annual(fcf_q, fcf_a)
        if fcf is not None:
            row['fcfYield_pct'] = fcf / float(mcap) * 100
            filled.append(f'fcfYield<-FCF_{src}')

    # grossMargins
    if isnan(row.get('grossMargins')):
        rev_ltm, rev_src = _ltm_or_annual(rev_q, rev_a)
        gp_ltm,  gp_src  = _ltm_or_annual(gp_q,  gp_a)
        if rev_ltm and gp_ltm and rev_ltm > 0:
            row['grossMargins'] = gp_ltm / rev_ltm
            filled.append(f'grossMargin<-GP/Rev_{gp_src}')

    row['_filled_from'] = '; '.join(filled) if filled else ''
    return row


def main():
    df = pd.read_csv(COMBINED)
    print(f'Filling gaps in {len(df)} top-50 rows...')
    out = []
    n_filled = 0
    for _, r in df.iterrows():
        before_nan = sum(1 for c in ['trailingPE','enterpriseToEbitda','revenueGrowth',
                                      'earningsGrowth','fcfYield_pct','grossMargins']
                         if pd.isna(r.get(c)))
        r2 = derive(str(r['ticker']), r.to_dict())
        after_nan = sum(1 for c in ['trailingPE','enterpriseToEbitda','revenueGrowth',
                                     'earningsGrowth','fcfYield_pct','grossMargins']
                        if pd.isna(r2.get(c)))
        if r2.get('_filled_from'):
            n_filled += 1
        if before_nan > after_nan:
            print(f"  {r['ticker']:12s} filled {before_nan-after_nan}: {r2['_filled_from']}")
        out.append(r2)
    new_df = pd.DataFrame(out)
    new_df.to_csv(COMBINED, index=False)
    print(f'\nDone. Filled at least one gap in {n_filled} of {len(df)} rows.')
    # Summary of remaining NaN after fill
    key_cols = ['priceToBook','trailingPE','forwardPE','enterpriseToEbitda',
                'fcfYield_pct','grossMargins','operatingMargins','revenueGrowth','earningsGrowth']
    print('\nRemaining NaN:')
    for c in key_cols:
        if c in new_df.columns:
            print(f'  {c}: {new_df[c].isna().sum()}/{len(new_df)}')


if __name__ == '__main__':
    main()
