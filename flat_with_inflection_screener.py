"""Flat-price-but-fundamentals-improving screener.

Looks for the classic valuation-gap-closing setup:
  - Stock price has been roughly flat over the last 3 years
  - But FCF per share has grown materially over the same period
  - AND there's recent (last 12 months) positive inflection in
    sales, EBITDA, or FCF growth

The thesis: the market hasn't priced fundamental improvement, but the
inflection signals that the gap is starting to close.

Quant filter:
  - 3y price change in [-20%, +25%]
  - LTM FCF/share at least 30% higher than the LTM FCF/share 3 years ago
    (proxied via 12 trailing quarters in EDGAR for US, or annual+TTM in
    yfinance for non-US)
  - Recent inflection: TTM revenue YoY >= 10% OR EBITDA YoY >= 15% OR
    FCF YoY >= 20% (any one)

Output: results_flat_inflection/screener.csv
"""
from __future__ import annotations
import argparse, json, gzip
from pathlib import Path
import numpy as np, pandas as pd

CACHE = Path('.cache/yf')
EDGAR = Path('.cache/edgar')
OUTDIR = Path('results_flat_inflection'); OUTDIR.mkdir(exist_ok=True)


def _safe(t): return ''.join(c if c.isalnum() or c in '-_' else '_' for c in t)


def load_price_series(tk):
    p = CACHE / f'{_safe(tk)}__price.parquet'
    if not p.exists(): return None
    try:
        df = pd.read_parquet(p)
        if df.empty or 'Close' not in df.columns: return None
        s = pd.to_numeric(df['Close'], errors='coerce').dropna()
        if getattr(s.index, 'tz', None) is not None:
            s.index = s.index.tz_localize(None)
        return s.sort_index()
    except Exception: return None


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
    """Get a time series for a given line item, handling both orientations:
      - US/EU: dates as INDEX, line items as COLUMNS
      - Korea/some Asia: line items as INDEX, dates as COLUMNS
    """
    if df is None or df.empty: return None
    items_in_index = pd.api.types.is_datetime64_any_dtype(df.columns) or \
                     any(isinstance(c, pd.Timestamp) for c in df.columns[:3])
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


def edgar_ltm_fcf_ps(tk):
    """Return LTM FCF per share series (quarterly) from EDGAR — same logic as
    fcf_yield_screener. Empty Series if unavailable."""
    cik = cik_for(tk)
    if cik is None: return pd.Series(dtype=float)
    p = EDGAR / f'CF_{cik:010d}.json.gz'
    if not p.exists(): return pd.Series(dtype=float)
    try:
        with gzip.open(p, 'rt') as f:
            facts = json.load(f)['facts'].get('us-gaap', {})
    except Exception: return pd.Series(dtype=float)
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

    ocf = get(['NetCashProvidedByUsedInOperatingActivities',
                'NetCashProvidedByUsedInOperatingActivitiesContinuingOperations'])
    capex = get(['PaymentsToAcquirePropertyPlantAndEquipment',
                  'PaymentsToAcquireProductiveAssets'])
    shares = get(['WeightedAverageNumberOfDilutedSharesOutstanding',
                   'WeightedAverageNumberOfSharesOutstandingBasic'], unit='shares')
    if ocf.empty or capex.empty or shares.empty: return pd.Series(dtype=float)
    idx = ocf.index.union(capex.index)
    fcf = (ocf.reindex(idx) - capex.reindex(idx).abs()).dropna()
    if fcf.empty: return pd.Series(dtype=float)
    idx2 = fcf.index.union(shares.index)
    fcf_ps = (fcf.reindex(idx2) / shares.reindex(idx2).replace(0, np.nan)).dropna().sort_index()
    return fcf_ps.rolling(4).sum().dropna()


def ttm_yoy_growth(series_q):
    """Given quarterly series, compute (sum last 4Q) / (sum prior 4Q) - 1, in %."""
    s = series_q.dropna().sort_index()
    if len(s) < 8: return None
    cur = s.iloc[-4:].sum(); prv = s.iloc[-8:-4].sum()
    return float((cur/prv - 1) * 100) if prv > 0 else None


def main():
    ap = argparse.ArgumentParser()
    # RELAXED for global coverage. The original thresholds catch only the
    # cleanest US setups; loosening surfaces moderate-growth flat-priced names.
    ap.add_argument('--price-flat-lo', type=float, default=-30.0)      # RELAXED -20 -> -30
    ap.add_argument('--price-flat-hi', type=float, default=30.0)       # RELAXED 25 -> 30
    ap.add_argument('--min-fcf-ps-3y-growth', type=float, default=15.0)# RELAXED 30 -> 15
    ap.add_argument('--min-rev-yoy', type=float, default=5.0)          # RELAXED 10 -> 5
    ap.add_argument('--min-ebitda-yoy', type=float, default=8.0)       # RELAXED 15 -> 8
    ap.add_argument('--min-fcf-yoy', type=float, default=10.0)         # RELAXED 20 -> 10
    ap.add_argument('--min-mcap', type=float, default=200e6)
    args = ap.parse_args()

    info_files = list(CACHE.glob('*__info_metrics.parquet'))
    print(f'Scanning {len(info_files)} info_metrics files...')
    rows = []
    for i, p in enumerate(info_files):
        tk = p.name.split('__')[0]
        if (i+1) % 1000 == 0: print(f'  {i+1}/{len(info_files)} rows={len(rows)}')
        info = load_info(tk)
        if info is None: continue
        mcap = info.get('marketCap')
        if mcap is None or mcap < args.min_mcap: continue

        # 1) Price flat over 3y
        s = load_price_series(tk)
        if s is None or len(s) < 800: continue
        last = float(s.iloc[-1])
        three_y_ago = float(s.iloc[-min(756, len(s))])
        if three_y_ago <= 0: continue
        price_3y_pct = (last/three_y_ago - 1) * 100
        if not (args.price_flat_lo <= price_3y_pct <= args.price_flat_hi): continue

        # 2) LTM FCF/share growth over 3y (EDGAR preferred for depth)
        ltm_fcf_ps = edgar_ltm_fcf_ps(tk)
        fcf_ps_growth_3y = None
        if not ltm_fcf_ps.empty and len(ltm_fcf_ps) >= 12:
            cur = float(ltm_fcf_ps.iloc[-1])
            past = float(ltm_fcf_ps.iloc[-min(13, len(ltm_fcf_ps))])
            # require both positive and meaningful magnitude
            if past > 0 and cur > 0:
                fcf_ps_growth_3y = (cur/past - 1) * 100
        if fcf_ps_growth_3y is None or fcf_ps_growth_3y < args.min_fcf_ps_3y_growth: continue

        # 3) Recent inflection (any one of revenue/EBITDA/FCF YoY)
        inc = load_income(tk); cf = load_cashflow(tk)
        rev_q = _row(inc, ['Total Revenue','TotalRevenue','Revenue']) if inc is not None else None
        ebitda_q = _row(inc, ['EBITDA','Normalized EBITDA']) if inc is not None else None
        fcf_q = _row(cf, ['Free Cash Flow','FreeCashFlow']) if cf is not None else None
        rev_yoy = ttm_yoy_growth(rev_q) if rev_q is not None else None
        ebitda_yoy = ttm_yoy_growth(ebitda_q) if ebitda_q is not None else None
        fcf_yoy = ttm_yoy_growth(fcf_q) if fcf_q is not None else None
        # use EDGAR LTM FCF for fcf_yoy if missing
        if fcf_yoy is None and not ltm_fcf_ps.empty and len(ltm_fcf_ps) >= 5:
            cur = float(ltm_fcf_ps.iloc[-1]); prv = float(ltm_fcf_ps.iloc[-5])
            if prv > 0 and cur > 0:
                fcf_yoy = (cur/prv - 1) * 100
        inflected = False
        if rev_yoy is not None and rev_yoy >= args.min_rev_yoy: inflected = True
        if ebitda_yoy is not None and ebitda_yoy >= args.min_ebitda_yoy: inflected = True
        if fcf_yoy is not None and fcf_yoy >= args.min_fcf_yoy: inflected = True
        if not inflected: continue

        rows.append({
            'ticker': tk,
            'price_3y_pct': round(price_3y_pct, 1),
            'fcf_ps_3y_growth_pct': round(fcf_ps_growth_3y, 1),
            'rev_yoy_pct': round(rev_yoy, 1) if rev_yoy is not None else None,
            'ebitda_yoy_pct': round(ebitda_yoy, 1) if ebitda_yoy is not None else None,
            'fcf_yoy_pct': round(fcf_yoy, 1) if fcf_yoy is not None else None,
            'market_cap': mcap,
            'trailingPE': info.get('trailingPE'),
            'priceToBook': info.get('priceToBook'),
            'priceToSales': info.get('priceToSalesTrailing12Months'),
            'enterpriseToEbitda': info.get('enterpriseToEbitda'),
        })

    if not rows:
        print("No rows survived filters; nothing to write."); return
    df = pd.DataFrame(rows).set_index('ticker')
    df['gap_score'] = (df['fcf_ps_3y_growth_pct'] - df['price_3y_pct'].abs())
    df = df.sort_values('gap_score', ascending=False)
    df.to_csv(OUTDIR / 'screener.csv')
    print(f'\nFlat-with-inflection hits: {len(df)}')
    print(df.head(30).to_string())


if __name__ == '__main__':
    main()
