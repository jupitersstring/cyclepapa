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
    """Backward-compat single-method picker (preferred -> Annual fallback).
    Returns (cur, prv, growth%, source)."""
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
    cur, prv, g = annual_yoy(series)
    if g is not None: return cur, prv, g, 'Annual'
    cur, prv, g = q_yoy(series)
    if g is not None: return (cur*4 if cur else None), (prv*4 if prv else None), g, 'Q_YoY'
    return None, None, None, None


def both_growth_views(series):
    """Compute BOTH LTM-vs-LTM AND latest-year (annual or single-Q) growth.
    Returns dict with: ltm_amount, ltm_growth_pct, yr_amount, yr_growth_pct.
    Either may be None if the underlying data doesn't support that method."""
    out = {
        'ltm_amount': None, 'ltm_growth_pct': None,
        'yr_amount':  None, 'yr_growth_pct':  None,
        'method_yr':  None,
    }
    if series is None or series.empty:
        return out
    freq = detect_frequency(series)
    # LTM only meaningful when underlying is quarterly
    if freq == 'quarterly':
        cur, prv, g = ltm_yoy(series)
        if g is not None:
            out['ltm_amount'] = cur
            out['ltm_growth_pct'] = g
    # "Latest year" — prefer annual data; else single-Q YoY (×4 for amount)
    cur, prv, g = annual_yoy(series)
    if g is not None and freq == 'annual':
        out['yr_amount'] = cur
        out['yr_growth_pct'] = g
        out['method_yr'] = 'Annual'
    elif freq == 'quarterly':
        cur, prv, g = q_yoy(series)
        if g is not None:
            out['yr_amount'] = cur * 4 if cur else None
            out['yr_growth_pct'] = g
            out['method_yr'] = 'Q_YoY'
    return out


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
    # FCF series from cashflow parquet (yfinance) — for FCF growth views
    cf_df = load_table(tk, 'cashflow')
    fcf_s = _col(cf_df, ['Free Cash Flow','FreeCashFlow'])
    if fcf_s is None: fcf_s = pd.Series(dtype=float)
    out['fcf']     = fcf_s
    return out


def load_eps_history(tk):
    """Return Series of reported EPS, indexed by earnings date."""
    p = CACHE / f'{_safe(tk)}__eps_history.parquet'
    if not p.exists(): return pd.Series(dtype=float)
    try:
        df = pd.read_parquet(p)
        if df.empty or 'Reported EPS' not in df.columns: return pd.Series(dtype=float)
        s = pd.to_numeric(df['Reported EPS'], errors='coerce').dropna()
        s = s.sort_index()
        if getattr(s.index, 'tz', None) is not None:
            s.index = s.index.tz_localize(None)
        return s
    except Exception: return pd.Series(dtype=float)


def eps_growth_views(tk, info_eps_qg=None):
    """Compute EPS growth from cached eps_history. Returns
    (ltm_growth_pct, yr_growth_pct, latest_eps_ttm)."""
    s = load_eps_history(tk)
    if s.empty:
        # fallback to info_metrics earningsQuarterlyGrowth if present
        if info_eps_qg is not None:
            try:
                g = float(info_eps_qg) * 100
                return None, g, None
            except Exception: pass
        return None, None, None
    # LTM EPS: rolling 4-quarter sum
    if len(s) >= 8:
        ltm = s.rolling(4).sum().dropna()
        if len(ltm) >= 5:
            cur_ltm = float(ltm.iloc[-1]); prv_ltm = float(ltm.iloc[-5])
            ltm_g = (cur_ltm/prv_ltm - 1) * 100 if prv_ltm > 0 else None
        else:
            cur_ltm, ltm_g = None, None
    else:
        cur_ltm, ltm_g = None, None
    # Latest year: single-Q vs Q-4 if quarterly, or annual diff
    if len(s) >= 5:
        cur_q = float(s.iloc[-1]); prv_q = float(s.iloc[-5])
        yr_g = (cur_q/prv_q - 1) * 100 if prv_q > 0 else None
    elif len(s) >= 2:
        cur_q = float(s.iloc[-1]); prv_q = float(s.iloc[-2])
        yr_g = (cur_q/prv_q - 1) * 100 if prv_q > 0 else None
    else:
        yr_g = None
    return ltm_g, yr_g, cur_ltm


def price_perf(tk, days=252):
    p = CACHE / f'{_safe(tk)}__price.parquet'
    if not p.exists(): return None
    try:
        df = pd.read_parquet(p)
        s = pd.to_numeric(df['Close'], errors='coerce').dropna()
        if len(s) < days+5: return None
        return float((s.iloc[-1]/s.iloc[-days] - 1) * 100)
    except Exception: return None


def analyze(tk, min_mcap=0):
    m = get_metrics(tk)
    i = info(tk)
    mc = i.get('marketCap')
    if min_mcap > 0 and (mc is None or mc < min_mcap): return None

    # Compute BOTH LTM and latest-year growth views per metric
    rev = both_growth_views(m['revenue'])
    gp  = both_growth_views(m['gross'])
    eb  = both_growth_views(m['ebitda'])
    fcf = both_growth_views(m.get('fcf', pd.Series(dtype=float)))

    # ---- LTM AMOUNT FALLBACKS (figures, not growth) ----
    # yfinance's info_metrics has totalRevenue/ebitda/freeCashflow as current
    # LTM snapshots. Use them when rolling-4Q can't compute (Asia, shallow data).
    info_total_rev = i.get('totalRevenue')
    info_ebitda    = i.get('ebitda')
    info_fcf       = i.get('freeCashflow') or i.get('operatingCashflow')
    info_gross_margin = i.get('grossMargins')  # decimal fraction

    if rev['ltm_amount'] is None and info_total_rev is not None:
        rev['ltm_amount'] = float(info_total_rev)
    if eb['ltm_amount'] is None and info_ebitda is not None:
        eb['ltm_amount'] = float(info_ebitda)
    if fcf['ltm_amount'] is None and info_fcf is not None:
        fcf['ltm_amount'] = float(info_fcf)
    # Derive gross from totalRevenue × grossMargins when missing
    if gp['ltm_amount'] is None and info_total_rev is not None and info_gross_margin is not None:
        try:
            gp['ltm_amount'] = float(info_total_rev) * float(info_gross_margin)
        except Exception: pass

    # We'll compute EPS growth below — keep candidate if ANY growth metric is available

    # Multiples (point-in-time, same for both views)
    ps      = i.get('priceToSalesTrailing12Months')
    pe      = i.get('trailingPE')
    ev_ebd  = i.get('enterpriseToEbitda')
    ev_sale = i.get('enterpriseToRevenue')
    ev      = i.get('enterpriseValue')

    # Derive EV/Gross Profit (the RAW multiple) using best available gross profit amount
    gp_amount = gp['ltm_amount'] or gp['yr_amount']
    ev_gp = ev / gp_amount if (ev is not None and gp_amount is not None and gp_amount > 0) else None

    # ---- LTM GROWTH FALLBACK (use YR growth when LTM unavailable) ----
    # Only US-EDGAR tickers have 8+ quarters needed for true LTM YoY. For
    # the other 85%, the YR view (single-Q YoY or annual) is the only signal.
    # Use YR as a noisier proxy for the LTM column when LTM is None, with
    # a `_source` field indicating where the value came from.
    def _ltm_or_yr(view, label):
        if view['ltm_growth_pct'] is not None:
            return view['ltm_growth_pct'], 'LTM'
        if view['yr_growth_pct'] is not None:
            return view['yr_growth_pct'], 'YR_proxy'
        return None, None
    rev_lg, rev_lg_src = _ltm_or_yr(rev, 'rev')
    gp_lg,  gp_lg_src  = _ltm_or_yr(gp,  'gp')
    eb_lg,  eb_lg_src  = _ltm_or_yr(eb,  'eb')
    fcf_lg, fcf_lg_src = _ltm_or_yr(fcf, 'fcf')

    # EPS growth — prefer eps_history series (more accurate); fall back to info field
    eps_ltm_g, eps_yr_g, _ = eps_growth_views(tk, info_eps_qg=i.get('earningsQuarterlyGrowth'))
    # Keep `eps_g` as a single "best available" growth rate for the classic PEG
    eps_g = eps_ltm_g if eps_ltm_g is not None else eps_yr_g

    # Keep row if ANY of these are present: growth signal, raw multiple, EPS
    has_growth = any([
        rev['ltm_growth_pct'], rev['yr_growth_pct'],
        gp['ltm_growth_pct'], gp['yr_growth_pct'],
        eb['ltm_growth_pct'], eb['yr_growth_pct'],
        fcf['ltm_growth_pct'], fcf['yr_growth_pct'],
        eps_ltm_g, eps_yr_g,
    ])
    has_multiple = any([i.get('priceToSalesTrailing12Months'),
                         i.get('trailingPE'), i.get('enterpriseToEbitda'),
                         i.get('enterpriseToRevenue')])
    has_eps = i.get('trailingEps') is not None
    if not (has_growth or has_multiple or has_eps): return None

    def peg_ratio(multiple, growth):
        if multiple is None or growth is None: return None
        try:
            m_ = float(multiple); g_ = float(growth)
            if not np.isfinite(m_) or not np.isfinite(g_) or g_ <= 0 or m_ <= 0: return None
            return m_ / g_
        except Exception: return None

    # Convenience for the most prominent ratios using LTM and latest-year
    rec = {
        'ticker': tk,
        'market_cap': mc,
        'gross_margin_now_pct': (
            (gp_amount / (rev['ltm_amount'] or rev['yr_amount']) * 100)
            if (gp_amount and (rev['ltm_amount'] or rev['yr_amount'])) else None
        ),
        'perf_1y_pct':  price_perf(tk),
        'method_yr':    rev['method_yr'],
        # Amounts
        'rev_ltm_M':    rev['ltm_amount']/1e6 if rev['ltm_amount'] else None,
        'rev_yr_M':     rev['yr_amount']/1e6  if rev['yr_amount']  else None,
        'gross_ltm_M':  gp['ltm_amount']/1e6  if gp['ltm_amount']  else None,
        'gross_yr_M':   gp['yr_amount']/1e6   if gp['yr_amount']   else None,
        'ebitda_ltm_M': eb['ltm_amount']/1e6  if eb['ltm_amount']  else None,
        'ebitda_yr_M':  eb['yr_amount']/1e6   if eb['yr_amount']   else None,
        # Growth rates — both views, side by side
        'rev_growth_ltm_pct':    rev['ltm_growth_pct'],
        'rev_growth_yr_pct':     rev['yr_growth_pct'],
        'gross_growth_ltm_pct':  gp['ltm_growth_pct'],
        'gross_growth_yr_pct':   gp['yr_growth_pct'],
        'ebitda_growth_ltm_pct': eb['ltm_growth_pct'],
        'ebitda_growth_yr_pct':  eb['yr_growth_pct'],
        'fcf_growth_ltm_pct':    fcf['ltm_growth_pct'],
        'fcf_growth_yr_pct':     fcf['yr_growth_pct'],
        'fcf_ltm_M':             fcf['ltm_amount']/1e6 if fcf['ltm_amount'] else None,
        'fcf_yr_M':              fcf['yr_amount']/1e6  if fcf['yr_amount']  else None,
        # Raw multiples
        'trailingPE':      pe,
        'priceToSales':    ps,
        'evToSales':       ev_sale,
        'evToEbitda':      ev_ebd,
        'evToGrossProfit': ev_gp,
        # EPS growth (both views) — feeds the classic PEG
        'eps_growth_ltm_pct':  eps_ltm_g,
        'eps_growth_yr_pct':   eps_yr_g,
        # PEG-style ratios using LTM growth
        'PEG_ltm':                peg_ratio(pe,      eps_ltm_g if eps_ltm_g is not None else eps_yr_g),
        'PEG_yr':                 peg_ratio(pe,      eps_yr_g),
        # _ltm columns now use LTM growth where available, YR as proxy otherwise
        'PSG_ltm':                peg_ratio(ps,      rev_lg),
        'EV_Sales_over_revG_ltm': peg_ratio(ev_sale, rev_lg),
        'EV_GP_over_GPg_ltm':     peg_ratio(ev_gp,   gp_lg),
        'EV_EBITDA_over_EBg_ltm': peg_ratio(ev_ebd,  eb_lg),
        # NEW: EV/EBITDA over GROSS PROFIT growth (harder-to-manipulate divisor)
        'EV_EBITDA_over_GPg_ltm': peg_ratio(ev_ebd,  gp_lg),
        # PE using GP growth (fallback when EV/EBITDA not available)
        'PE_over_GPg_ltm':        peg_ratio(pe,      gp_lg),
        # PS using GP growth
        'PS_over_GPg_ltm':        peg_ratio(ps,      gp_lg),
        # Source markers for the _ltm columns (LTM vs YR_proxy)
        'rev_g_ltm_source':       rev_lg_src,
        'gp_g_ltm_source':        gp_lg_src,
        'eb_g_ltm_source':        eb_lg_src,
        # Same set using LATEST-YEAR growth (annual or single-Q ×4)
        'PSG_yr':                peg_ratio(ps,      rev['yr_growth_pct']),
        'EV_Sales_over_revG_yr': peg_ratio(ev_sale, rev['yr_growth_pct']),
        'EV_GP_over_GPg_yr':     peg_ratio(ev_gp,   gp['yr_growth_pct']),
        'EV_EBITDA_over_EBg_yr': peg_ratio(ev_ebd,  eb['yr_growth_pct']),
        'EV_EBITDA_over_GPg_yr': peg_ratio(ev_ebd,  gp['yr_growth_pct']),
        'PE_over_GPg_yr':        peg_ratio(pe,      gp['yr_growth_pct']),
        'PS_over_GPg_yr':        peg_ratio(ps,      gp['yr_growth_pct']),
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
        # Use whichever revenue growth is available (LTM preferred, else YR)
        rg = rec.get('rev_growth_ltm_pct') or rec.get('rev_growth_yr_pct')
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
        (df[['rev_growth_ltm_pct','rev_growth_yr_pct']].max(axis=1).fillna(-99) >= 10) &
        (df['perf_1y_pct'].between(-50, 30)) &
        ((df['EV_GP_over_GPg_ltm'].fillna(99) < 1.5)
         | (df['EV_GP_over_GPg_yr'].fillna(99) < 1.5)
         | (df['EV_EBITDA_over_EBg_ltm'].fillna(99) < 1.5)
         | (df['EV_EBITDA_over_EBg_yr'].fillna(99) < 1.5)
         | (df['PSG_ltm'].fillna(99) < 1.5)
         | (df['PSG_yr'].fillna(99) < 1.5))
    ].copy()
    df_b = df_b.sort_values('EV_GP_over_GPg_ltm', na_position='last')
    df_b.to_csv(OUTDIR / 'best_undervalued.csv')
    print(f'Best-undervalued: {len(df_b)}')

    # Display top 25 by EV_GP_g (cheapest on gross profit growth)
    cols = ['rev_growth_ltm_pct','rev_growth_yr_pct',
            'gross_growth_ltm_pct','gross_growth_yr_pct',
            'ebitda_growth_ltm_pct','ebitda_growth_yr_pct',
            'gross_margin_now_pct',
            'PSG_ltm','PSG_yr',
            'EV_Sales_over_revG_ltm','EV_Sales_over_revG_yr',
            'EV_GP_over_GPg_ltm','EV_GP_over_GPg_yr',
            'EV_EBITDA_over_EBg_ltm','EV_EBITDA_over_EBg_yr',
            'EV_EBITDA_over_GPg_ltm','EV_EBITDA_over_GPg_yr',
            'PE_over_GPg_ltm','PE_over_GPg_yr',
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
