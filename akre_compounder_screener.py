"""AKRE-archetype compounder screener.

Chuck Akre's framework — the "three-legged stool" — looks for businesses
that combine (1) high returns on capital, (2) high reinvestment rates
back into the business, and (3) a long runway for that reinvestment
to compound. American Tower in 1998 was the prototype: predictable
cash flows from existing towers + a massive build-out runway for new
towers at high incremental returns.

Quantitative proxies we can extract from cached fundamentals:
  - ROE > 15%                       (high return on capital)
  - Operating margin > 12%          (real margin structure)
  - Revenue YoY growth > 8%         (runway still open)
  - Debt/equity < 100%              (conservative balance sheet)
  - Operating margin not contracting from prior year
  - Market cap in [$300M, $20B]     (not too small, not too discovered)

Scoring: weighted blend of ROE, op margin, revenue growth, and
balance-sheet conservatism. Higher = closer to the Akre archetype.

Output: results_akre/screener.csv
"""
from __future__ import annotations
import argparse, json, gzip
from pathlib import Path
import numpy as np, pandas as pd

CACHE = Path('.cache/yf')
EDGAR = Path('.cache/edgar')
OUTDIR = Path('results_akre'); OUTDIR.mkdir(exist_ok=True)


def _safe(t): return ''.join(c if c.isalnum() or c in '-_' else '_' for c in t)


def load_info(tk):
    p = CACHE / f'{_safe(tk)}__info_metrics.parquet'
    if not p.exists(): return None
    try:
        d = pd.read_parquet(p)
        return d.iloc[0].to_dict() if not d.empty else None
    except Exception: return None


def load_income(tk):
    p = CACHE / f'{_safe(tk)}__income.parquet'
    if not p.exists(): return None
    try:
        d = pd.read_parquet(p)
        return d if not d.empty else None
    except Exception: return None


def load_cashflow(tk):
    p = CACHE / f'{_safe(tk)}__cashflow.parquet'
    if not p.exists(): return None
    try:
        d = pd.read_parquet(p)
        return d if not d.empty else None
    except Exception: return None


def _row(df, candidates):
    if df is None: return None
    for c in candidates:
        if c in df.index:
            s = pd.to_numeric(df.loc[c], errors='coerce').dropna()
            if not s.empty: return s
    return None


def revenue_growth_ttm_yoy(tk):
    """Sum of latest 4 quarters vs prior 4 quarters from yfinance income."""
    inc = load_income(tk)
    if inc is None: return None
    rev = _row(inc, ['Total Revenue','TotalRevenue','Revenue'])
    if rev is None or len(rev) < 6: return None
    rev = rev.sort_index()
    # Some yfinance returns quarterly; if so we need 8 quarters, if annual we need 2
    # Heuristic: if dates are within 13 months => annual, else quarterly
    diffs = np.diff(rev.index.values.astype('datetime64[D]').astype(int))
    if (diffs.mean() if len(diffs) else 0) > 200:
        # annual: latest vs prior
        if len(rev) < 2: return None
        cur, prv = rev.iloc[-1], rev.iloc[-2]
        return float((cur/prv - 1)*100) if prv > 0 else None
    else:
        # quarterly: sum of 4 vs prior 4
        if len(rev) < 8: return None
        cur = rev.iloc[-4:].sum(); prv = rev.iloc[-8:-4].sum()
        return float((cur/prv - 1)*100) if prv > 0 else None


def op_margin_yoy_change(tk):
    """Change in operating margin (current TTM vs prior TTM), in percentage points."""
    inc = load_income(tk)
    if inc is None: return None
    rev = _row(inc, ['Total Revenue','TotalRevenue','Revenue'])
    op  = _row(inc, ['Operating Income','OperatingIncome','EBIT'])
    if rev is None or op is None: return None
    rev = rev.sort_index(); op = op.sort_index()
    diffs = np.diff(rev.index.values.astype('datetime64[D]').astype(int))
    if (diffs.mean() if len(diffs) else 0) > 200:
        if len(rev) < 2 or len(op) < 2: return None
        cur = op.iloc[-1] / rev.iloc[-1] if rev.iloc[-1] > 0 else None
        prv = op.iloc[-2] / rev.iloc[-2] if rev.iloc[-2] > 0 else None
    else:
        if len(rev) < 8 or len(op) < 8: return None
        cur = op.iloc[-4:].sum() / rev.iloc[-4:].sum() if rev.iloc[-4:].sum() > 0 else None
        prv = op.iloc[-8:-4].sum() / rev.iloc[-8:-4].sum() if rev.iloc[-8:-4].sum() > 0 else None
    if cur is None or prv is None: return None
    return float((cur - prv) * 100)


def reinvestment_rate(tk):
    """abs(capex) / OCF over latest period — proxy for reinvestment intensity."""
    cf = load_cashflow(tk)
    if cf is None: return None
    ocf = _row(cf, ['Operating Cash Flow','OperatingCashFlow','Cash Flow From Continuing Operating Activities'])
    capex = _row(cf, ['Capital Expenditure','CapitalExpenditure','PurchaseOfPPE'])
    if ocf is None or capex is None: return None
    if ocf.empty or capex.empty: return None
    ocf_v = float(ocf.iloc[-1]); capex_v = float(capex.iloc[-1])
    if ocf_v <= 0: return None
    return abs(capex_v) / ocf_v * 100


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--min-roe', type=float, default=15.0)
    ap.add_argument('--min-op-margin', type=float, default=12.0)
    ap.add_argument('--min-rev-growth', type=float, default=8.0)
    ap.add_argument('--max-de', type=float, default=100.0)
    ap.add_argument('--min-mcap', type=float, default=300e6)
    ap.add_argument('--max-mcap', type=float, default=20e9)
    args = ap.parse_args()

    info_files = list(CACHE.glob('*__info_metrics.parquet'))
    print(f'Scanning {len(info_files)} info_metrics files...')
    rows = []
    for i, p in enumerate(info_files):
        tk = p.name.split('__')[0]
        if (i+1) % 1000 == 0: print(f'  {i+1}/{len(info_files)} rows={len(rows)}')
        info = load_info(tk)
        if info is None: continue
        roe = info.get('returnOnEquity')
        op_m = info.get('operatingMargins')
        de   = info.get('debtToEquity')
        mcap = info.get('marketCap')
        rev_g = revenue_growth_ttm_yoy(tk)
        op_m_chg = op_margin_yoy_change(tk)
        reinv = reinvestment_rate(tk)
        if roe is None or op_m is None or mcap is None: continue
        roe_pct = roe * 100; op_m_pct = op_m * 100
        if roe_pct < args.min_roe: continue
        if op_m_pct < args.min_op_margin: continue
        if rev_g is None or rev_g < args.min_rev_growth: continue
        if de is not None and de > args.max_de: continue
        if mcap < args.min_mcap or mcap > args.max_mcap: continue
        # Akre score: weighted blend (rev growth + ROE + op margin + low D/E + margin stability)
        score = (roe_pct * 0.30 + op_m_pct * 0.20 + rev_g * 0.30
                 + (max(0, 100 - (de or 0)) * 0.10)
                 + ((op_m_chg or 0) * 0.10))
        rows.append({
            'ticker': tk,
            'akre_score': round(score, 2),
            'roe_pct': round(roe_pct, 1),
            'op_margin_pct': round(op_m_pct, 1),
            'op_margin_chg_pp': round(op_m_chg, 1) if op_m_chg is not None else None,
            'rev_growth_ttm_pct': round(rev_g, 1),
            'reinvestment_rate_pct': round(reinv, 1) if reinv is not None else None,
            'debt_to_equity': de,
            'market_cap': mcap,
            'priceToBook': info.get('priceToBook'),
            'priceToSales': info.get('priceToSalesTrailing12Months'),
            'enterpriseToEbitda': info.get('enterpriseToEbitda'),
            'trailingPE': info.get('trailingPE'),
            'sector': None,
        })
    df = pd.DataFrame(rows).set_index('ticker').sort_values('akre_score', ascending=False)
    df.to_csv(OUTDIR / 'screener.csv')
    print(f'\nAkre archetype hits: {len(df)}')
    print(df.head(30).to_string())


if __name__ == '__main__':
    main()
