"""PEG-style screener — compute traditional PEG and equivalents that
normalize valuation by growth rate. Lower = cheaper per unit of growth.

Ratios computed:
  PEG          = trailingPE / EPS growth YoY
  PSG          = P/S / sales growth YoY
  EV/EBITDA/g  = (EV/EBITDA) / EBITDA growth YoY      <- like PEG with EBITDA
  EV/Sales/g   = (EV/Sales) / sales growth YoY
  EV/GP/g      = (EV/GP) / gross profit growth YoY    <- gross-profit PEG

Plus headline data: gross margin Δ, 1y perf (rerate gauge), market cap.

Filters (relaxed vs clean_topline — we want browsability, not just hits):
  - Mkt cap >= $200M
  - Sales growth YoY > 5%
  - At least one of PSG/EV-Sales-g/EV-GP-g/EV-EBITDA-g is computable
  - Exclude India

Two outputs:
  results_peg/all.csv           — every eligible ticker with all ratios
  results_peg/best_undervalued.csv — sub-list passing strict cheap-on-growth filter
"""
from __future__ import annotations
import argparse, json, gzip
from pathlib import Path
import numpy as np, pandas as pd

CACHE = Path('.cache/yf')
EDGAR = Path('.cache/edgar')
OUTDIR = Path('results_peg'); OUTDIR.mkdir(exist_ok=True)


def _safe(t): return ''.join(c if c.isalnum() or c in '-_' else '_' for c in t)


def _col(df, candidates):
    if df is None or df.empty: return None
    items_in_index = (
        pd.api.types.is_datetime64_any_dtype(df.columns)
        or any(isinstance(c, pd.Timestamp) for c in df.columns[:3])
    )
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


def load_table(tk, slot):
    p = CACHE / f'{_safe(tk)}__{slot}.parquet'
    if not p.exists(): return None
    try:
        d = pd.read_parquet(p)
        return d if not d.empty else None
    except Exception: return None


def info(tk):
    d = load_table(tk, 'info_metrics')
    return d.iloc[0].to_dict() if d is not None else {}


_CIK_MAP = None
def cik_for(ticker):
    global _CIK_MAP
    if _CIK_MAP is None:
        try:
            with open(EDGAR / 'company_tickers.json') as f:
                raw = json.load(f)
            _CIK_MAP = {r['ticker'].upper(): int(r['cik_str']) for r in raw.values()}
        except Exception: _CIK_MAP = {}
    return _CIK_MAP.get(ticker.upper())


def edgar_series(tk):
    cik = cik_for(tk)
    if cik is None: return {}
    p = EDGAR / f'CF_{cik:010d}.json.gz'
    if not p.exists(): return {}
    try:
        with gzip.open(p, 'rt') as f:
            facts = json.load(f)['facts'].get('us-gaap', {})
    except Exception: return {}
    import sys; sys.path.insert(0, '.')
    from edgar_fetcher import _quarterly_records, _series_from_records, _derive_q4
    def get(cands, unit='USD'):
        for tag in cands:
            node = facts.get(tag)
            if not node: continue
            recs = node.get('units', {}).get(unit)
            if not recs: continue
            qs = _quarterly_records(recs)
            if not qs: continue
            q, a = _series_from_records(qs)
            return _derive_q4(q, a)
        return pd.Series(dtype=float)
    return {
        'revenue': get(['Revenues','RevenueFromContractWithCustomerExcludingAssessedTax',
                          'RevenueFromContractWithCustomerIncludingAssessedTax','SalesRevenueNet']),
        'gross':   get(['GrossProfit']),
        'op_inc':  get(['OperatingIncomeLoss']),
        'd_and_a': get(['DepreciationAndAmortization','DepreciationDepletionAndAmortization',
                          'DepreciationAmortizationAndAccretionNet']),
    }


def ltm_yoy(series):
    """Latest-12m vs prior-12m growth %. Returns (cur, prv, growth%)."""
    if series is None or series.empty: return None, None, None
    s = series.sort_index()
    ltm = s.rolling(4).sum().dropna()
    if len(ltm) < 5: return None, None, None
    cur = float(ltm.iloc[-1]); prv = float(ltm.iloc[-5])
    g = (cur/prv - 1) * 100 if prv != 0 else None
    return cur, prv, g


def q_yoy(series):
    """Single-quarter YoY: latest Q vs Q-4. Less smooth than LTM but only
    requires 5 quarters (which is yfinance's depth ceiling)."""
    if series is None or series.empty: return None, None, None
    s = series.sort_index()
    if len(s) < 5: return None, None, None
    cur = float(s.iloc[-1]); prv = float(s.iloc[-5])
    g = (cur/prv - 1) * 100 if prv != 0 else None
    return cur, prv, g


def detect_frequency(series):
    """Return 'annual' or 'quarterly' or None based on median date gap."""
    if series is None or len(series) < 2: return None
    s = series.sort_index()
    diffs = np.diff(s.index.values.astype('datetime64[D]').astype(int))
    if len(diffs) == 0: return None
    median_gap = float(np.median(diffs))
    if median_gap > 270:   # annual data (typically 360-365 days)
        return 'annual'
    if 60 < median_gap < 120:  # quarterly (~91 days)
        return 'quarterly'
    return None


def annual_yoy(series):
    """Latest annual vs prior annual. Requires 2 annual periods."""
    if series is None or len(series) < 2: return None, None, None
    s = series.sort_index()
    cur = float(s.iloc[-1]); prv = float(s.iloc[-2])
    g = (cur/prv - 1) * 100 if prv != 0 else None
    return cur, prv, g


def ltm_or_q_yoy(series):
    """Pick the best available YoY method:
      1) LTM-vs-LTM (rolling 4Q sum, requires 8 quarters) — preferred for US/EDGAR
      2) Single-Q YoY (Q vs Q-4, requires 5 quarters) — yfinance quarterly fallback
      3) Annual-vs-annual (requires 2 annual periods) — yfinance annual fallback
    Returns (current_amount, prior_amount, growth%, source)."""
    freq = detect_frequency(series)
    if freq == 'quarterly':
        cur, prv, g = ltm_yoy(series)
        if g is not None: return cur, prv, g, 'LTM'
        cur, prv, g = q_yoy(series)
        if g is not None:
            return (cur*4 if cur else None), (prv*4 if prv else None), g, 'Q_YoY'
    if freq == 'annual':
        cur, prv, g = annual_yoy(series)
        if g is not None: return cur, prv, g, 'Annual'
    # Last-resort: try whichever doesn't fail
    cur, prv, g = annual_yoy(series)
    if g is not None: return cur, prv, g, 'Annual'
    cur, prv, g = q_yoy(series)
    if g is not None: return (cur*4 if cur else None), (prv*4 if prv else None), g, 'Q_YoY'
    return None, None, None, None


def get_metrics(tk):
    """Pull all the series we need, preferring EDGAR depth."""
    e = edgar_series(tk)
    out = {}
    # revenue
    rev_e = e.get('revenue', pd.Series(dtype=float)) if e else pd.Series(dtype=float)
    if rev_e is not None and not rev_e.empty:
        rev = rev_e
    else:
        rev = _col(load_table(tk, 'income'), ['Total Revenue','Revenue','Operating Revenue'])
        if rev is None: rev = pd.Series(dtype=float)
    # gross
    gross_e = e.get('gross', pd.Series(dtype=float)) if e else pd.Series(dtype=float)
    if gross_e is not None and not gross_e.empty:
        gross = gross_e
    else:
        gross = _col(load_table(tk, 'income'), ['Gross Profit'])
        if gross is None: gross = pd.Series(dtype=float)
    # EBITDA = op_inc + |d_and_a| from EDGAR if available
    op_e = e.get('op_inc', pd.Series(dtype=float)) if e else pd.Series(dtype=float)
    da_e = e.get('d_and_a', pd.Series(dtype=float)) if e else pd.Series(dtype=float)
    if not op_e.empty and not da_e.empty:
        idx = op_e.index.union(da_e.index)
        ebitda = op_e.reindex(idx).add(da_e.reindex(idx).abs(), fill_value=np.nan).dropna()
    else:
        ebitda = _col(load_table(tk, 'income'), ['EBITDA','Normalized EBITDA'])
        if ebitda is None: ebitda = pd.Series(dtype=float)
    out['revenue'] = rev
    out['gross']   = gross
    out['ebitda']  = ebitda
    return out


def price_perf(tk, days=252):
    p = CACHE / f'{_safe(tk)}__price.parquet'
    if not p.exists(): return None
    try:
        df = pd.read_parquet(p)
        s = pd.to_numeric(df['Close'], errors='coerce').dropna()
        if len(s) < days+5: return None
        return float((s.iloc[-1]/s.iloc[-days] - 1) * 100)
    except Exception: return None


def analyze(tk, min_mcap=50e6):
    m = get_metrics(tk)
    i = info(tk)
    mc = i.get('marketCap')
    if mc is None or mc < min_mcap: return None

    rev_now, rev_prv, rev_g, rev_src = ltm_or_q_yoy(m['revenue'])
    gp_now, gp_prv, gp_g, gp_src     = ltm_or_q_yoy(m['gross'])
    eb_now, eb_prv, eb_g, eb_src     = ltm_or_q_yoy(m['ebitda'])

    # Need at least ONE growth metric to score
    if rev_g is None and gp_g is None and eb_g is None: return None

    # Multiples
    ps      = i.get('priceToSalesTrailing12Months')
    pe      = i.get('trailingPE')
    ev_ebd  = i.get('enterpriseToEbitda')
    ev_sale = i.get('enterpriseToRevenue')
    ev      = i.get('enterpriseValue')

    # Derive EV/Gross Profit
    ev_gp = ev / gp_now if (ev is not None and gp_now is not None and gp_now > 0) else None

    # EPS growth — pull from info if present (yfinance has 'earningsQuarterlyGrowth')
    eps_g = i.get('earningsQuarterlyGrowth')  # decimal fraction
    if eps_g is not None: eps_g = eps_g * 100  # to percent

    def peg_ratio(multiple, growth):
        if multiple is None or growth is None: return None
        try:
            m = float(multiple); g = float(growth)
            if not np.isfinite(m) or not np.isfinite(g) or g <= 0 or m <= 0: return None
            return m / g
        except Exception: return None

    rec = {
        'ticker': tk,
        'market_cap': mc,
        'rev_ltm_M':   rev_now/1e6 if rev_now else None,
        'gross_ltm_M': gp_now/1e6  if gp_now  else None,
        'ebitda_ltm_M': eb_now/1e6 if eb_now  else None,
        'rev_growth_pct':    rev_g,
        'gross_growth_pct':  gp_g,
        'ebitda_growth_pct': eb_g,
        'gross_margin_now_pct': (gp_now/rev_now*100) if (gp_now and rev_now and rev_now>0) else None,
        # multiples
        'trailingPE':  pe,
        'priceToSales': ps,
        'evToEbitda':  ev_ebd,
        'evToSales':   ev_sale,
        'evToGrossProfit': ev_gp,
        # PEG-style ratios (lower = cheaper per unit growth)
        'PEG':            peg_ratio(pe, eps_g),
        'PSG':            peg_ratio(ps, rev_g),
        'EV_Sales_g':     peg_ratio(ev_sale, rev_g),
        'EV_GP_g':        peg_ratio(ev_gp, gp_g),
        'EV_EBITDA_g':    peg_ratio(ev_ebd, eb_g),
        'perf_1y_pct':    price_perf(tk),
        'growth_source':  rev_src,  # 'LTM' or 'Q_YoY'
    }
    return rec


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--min-mcap', type=float, default=50e6)
    ap.add_argument('--min-rev-growth', type=float, default=0.0)
    args = ap.parse_args()

    # Iterate every cached ticker (price OR info OR income) — broadest possible
    inc = {p.name.split('__')[0] for p in CACHE.glob('*__income.parquet')}
    inf = {p.name.split('__')[0] for p in CACHE.glob('*__info_metrics.parquet')}
    tickers = sorted(inc | inf)
    print(f'Scanning {len(tickers)} tickers (income OR info)...')
    rows = []
    for i, tk in enumerate(tickers):
        if (i+1) % 1000 == 0: print(f'  {i+1}/{len(tickers)} rows={len(rows)}')
        if tk.upper().endswith(('_NS','_BO','.NS','.BO')): continue
        rec = analyze(tk, min_mcap=args.min_mcap)
        if rec is None: continue
        # Apply rev_growth gate only if computed; allow nullable for broader browse
        rg = rec.get('rev_growth_pct')
        if rg is not None and rg < args.min_rev_growth: continue
        rows.append(rec)
    if not rows:
        print('No hits'); return
    df = pd.DataFrame(rows).set_index('ticker')
    df.to_csv(OUTDIR / 'all.csv')
    print(f'\nTotal scored: {len(df)}')

    # Best-undervalued sub-list:
    #   - EV_GP_g < 1.5 (cheap on gross-profit growth) OR EV_EBITDA_g < 1.5 OR PSG < 1.5
    #   - sales growth >= 10
    #   - perf_1y in [-50, +30]
    #   - gross margin expanding > 0
    df_b = df[
        (df['rev_growth_pct'] >= 10) &
        (df['perf_1y_pct'].between(-50, 30)) &
        ((df['EV_GP_g'].fillna(99) < 1.5) | (df['EV_EBITDA_g'].fillna(99) < 1.5) | (df['PSG'].fillna(99) < 1.5))
    ].copy()
    # If gross margin Δ available, prefer expanding
    if 'gross_margin_now_pct' in df_b:
        df_b = df_b.sort_values(['EV_GP_g','EV_EBITDA_g','PSG'])
    df_b.to_csv(OUTDIR / 'best_undervalued.csv')
    print(f'Best-undervalued: {len(df_b)}')

    # Display top 25 by EV_GP_g (cheapest on gross profit growth)
    cols = ['rev_growth_pct','gross_growth_pct','ebitda_growth_pct',
            'gross_margin_now_pct',
            'PEG','PSG','EV_Sales_g','EV_GP_g','EV_EBITDA_g',
            'perf_1y_pct','market_cap','trailingPE','priceToSales',
            'evToEbitda','evToSales','evToGrossProfit']
    top = df_b.head(25)[cols].copy()
    top['market_cap'] = (top['market_cap']/1e9).round(2)
    for c in top.columns:
        if c not in ('market_cap',):
            top[c] = pd.to_numeric(top[c], errors='coerce').round(2)
    pd.set_option('display.width', 240); pd.set_option('display.max_columns', 30)
    print('\nCheapest 25 on gross-profit growth (EV_GP_g):')
    print(top.to_string())


if __name__ == '__main__':
    main()
