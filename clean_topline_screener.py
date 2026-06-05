"""Clean-topline-and-gross-margin screener.

Focuses on the metrics that are HARDEST to manipulate via accounting
(below-the-line adjustments, one-time gains, tax benefits, SBC etc):

  - Revenue YoY growth                  (top-line, hard to fake)
  - Gross profit YoY growth (dollars)   (revenue × gross margin)
  - Gross margin expansion (Δ pp)        (mix-shift / pricing power signal)

Combined with a "stock hasn't rerated" filter, this surfaces names
where structural profitability is improving but the market hasn't
recognized it.

Filters (all required):
  - Market cap >= $200M
  - Revenue LTM YoY growth >= 15%
  - Gross profit LTM YoY growth >= 15%
  - Gross margin expanded >= 0.5pp YoY (structural pricing/mix improvement)
  - 1y price perf <= +20% (un-rerated)
  - Exclude India (.NS/.BO)

Output: results_clean_topline/screener.csv (ranked by gross_profit_growth × margin_chg_pp)
"""
from __future__ import annotations
import argparse, json, gzip
from pathlib import Path
import numpy as np, pandas as pd

CACHE = Path('.cache/yf')
EDGAR = Path('.cache/edgar')
OUTDIR = Path('results_clean_topline'); OUTDIR.mkdir(exist_ok=True)


def _safe(t): return ''.join(c if c.isalnum() or c in '-_' else '_' for c in t)


def _col(df, candidates):
    """Schema-orientation-aware line-item lookup (US/EU dates-as-index OR Asia items-as-index)."""
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


def load_info(tk):
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


def edgar_quarterly(tk):
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
    }


def get_rev_gross_series(tk):
    """Return (rev_qtr, gross_qtr) — prefers EDGAR depth, falls back to yfinance."""
    e = edgar_quarterly(tk)
    rev_e = e.get('revenue') if e else None
    gross_e = e.get('gross') if e else None
    if rev_e is not None and not rev_e.empty and gross_e is not None and not gross_e.empty:
        return rev_e, gross_e
    # yfinance fallback
    inc = load_table(tk, 'income')
    rev = _col(inc, ['Total Revenue','Revenue','Operating Revenue'])
    gross = _col(inc, ['Gross Profit'])
    return rev, gross


def ltm_yoy(series):
    if series is None or series.empty: return None, None, None
    s = series.sort_index()
    ltm = s.rolling(4).sum().dropna()
    if len(ltm) < 5: return None, None, None
    cur = float(ltm.iloc[-1]); prv = float(ltm.iloc[-5])
    g = (cur/prv - 1) * 100 if prv > 0 else None
    return cur, prv, g


def price_perf(tk, days=252):
    p = CACHE / f'{_safe(tk)}__price.parquet'
    if not p.exists(): return None
    try:
        df = pd.read_parquet(p)
        s = pd.to_numeric(df['Close'], errors='coerce').dropna()
        if len(s) < days+5: return None
        return float((s.iloc[-1]/s.iloc[-days] - 1) * 100)
    except Exception: return None


def analyze(tk):
    rev_q, gross_q = get_rev_gross_series(tk)
    if rev_q is None or gross_q is None: return None
    if len(rev_q) < 8 or len(gross_q) < 8: return None
    rev_now, rev_prv, rev_g = ltm_yoy(rev_q)
    gp_now, gp_prv, gp_g = ltm_yoy(gross_q)
    if rev_g is None or gp_g is None: return None
    if rev_now <= 0 or gp_now <= 0: return None
    gross_margin_now = gp_now / rev_now * 100
    gross_margin_prv = gp_prv / rev_prv * 100 if rev_prv > 0 else None
    if gross_margin_prv is None: return None
    margin_chg = gross_margin_now - gross_margin_prv

    info = load_info(tk)
    return {
        'ticker': tk,
        'rev_ltm_now_M': rev_now / 1e6,
        'rev_ltm_yoy_pct': rev_g,
        'gross_ltm_now_M': gp_now / 1e6,
        'gross_ltm_yoy_pct': gp_g,
        'gross_margin_now_pct': gross_margin_now,
        'gross_margin_chg_pp': margin_chg,
        'perf_1y_pct': price_perf(tk),
        'market_cap': info.get('marketCap'),
        'priceToSales': info.get('priceToSalesTrailing12Months'),
        'priceToBook': info.get('priceToBook'),
        'trailingPE': info.get('trailingPE'),
        'enterpriseToEbitda': info.get('enterpriseToEbitda'),
        'enterpriseToRevenue': info.get('enterpriseToRevenue'),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--min-mcap', type=float, default=200e6)
    ap.add_argument('--min-rev-growth', type=float, default=15.0)
    ap.add_argument('--min-gross-growth', type=float, default=15.0)
    ap.add_argument('--min-gross-margin-chg-pp', type=float, default=0.5)
    ap.add_argument('--max-perf-1y', type=float, default=20.0)
    ap.add_argument('--min-perf-1y', type=float, default=-50.0)
    args = ap.parse_args()

    tickers = sorted({p.name.split('__')[0] for p in CACHE.glob('*__income.parquet')})
    print(f'Scanning {len(tickers)} tickers with income data...')
    rows = []
    for i, tk in enumerate(tickers):
        if (i+1) % 1000 == 0: print(f'  {i+1}/{len(tickers)} hits={len(rows)}')
        if tk.upper().endswith(('_NS','_BO','.NS','.BO')): continue
        rec = analyze(tk)
        if rec is None: continue
        mc = rec.get('market_cap')
        if mc is None or mc < args.min_mcap: continue
        if rec['rev_ltm_yoy_pct'] < args.min_rev_growth: continue
        if rec['gross_ltm_yoy_pct'] < args.min_gross_growth: continue
        if rec['gross_margin_chg_pp'] < args.min_gross_margin_chg_pp: continue
        if rec['perf_1y_pct'] is None: continue
        if rec['perf_1y_pct'] > args.max_perf_1y or rec['perf_1y_pct'] < args.min_perf_1y: continue
        # Quality score = gross profit growth * margin expansion / (1 + perf_1y / 100)
        # Rewards strong gross growth + margin expansion + un-rerated price
        rec['quality_score'] = (rec['gross_ltm_yoy_pct'] * rec['gross_margin_chg_pp']
                                 / max(0.5, 1 + rec['perf_1y_pct']/100))
        rows.append(rec)

    if not rows:
        print('No hits.')
        return
    df = pd.DataFrame(rows).set_index('ticker').sort_values('quality_score', ascending=False)
    df.to_csv(OUTDIR / 'screener.csv')
    print(f'\nClean topline hits: {len(df)}')
    cols = ['quality_score','rev_ltm_yoy_pct','gross_ltm_yoy_pct','gross_margin_chg_pp',
            'gross_margin_now_pct','perf_1y_pct','market_cap','priceToSales','priceToBook','trailingPE']
    show = df[cols].head(40).copy()
    show['market_cap'] = (show['market_cap']/1e9).round(2)
    for c in ('quality_score','rev_ltm_yoy_pct','gross_ltm_yoy_pct','gross_margin_chg_pp',
              'gross_margin_now_pct','perf_1y_pct','priceToSales','priceToBook','trailingPE'):
        show[c] = pd.to_numeric(show[c], errors='coerce').round(1)
    pd.set_option('display.width', 240); pd.set_option('display.max_columns', 20)
    print(show.to_string())


if __name__ == '__main__':
    main()
