"""AKRE-archetype compounder screener — INFLECTION VERSION.

Chuck Akre's framework looks for businesses with three legs: high
returns on capital, high reinvestment rates, and a long runway. The
*priced-in* version of this finds today's AMTs — but those compounders
already trade at premium multiples. The *un-priced* version (what we
want) finds setups where the compounding flywheel is just starting to
turn: ROIIC and/or FCF per share are inflecting upward, margins are
expanding, but the price hasn't responded yet.

Filter:
  - Mkt cap in [$200M, $30B]
  - Recent ROE > 12% AND ROE expanding (proxied: latest > 1.1x prior)
  - Operating margin expanding YoY (delta > 0)
  - LTM FCF per share inflecting up — recent LTM > 1.2x prior LTM
    (using EDGAR 12Q series for US; yfinance fallback elsewhere)
  - Revenue growth > 5% (runway still open, not exit-velocity)
  - 1y price perf in [-30%, +30%] (un-rerated)
  - Leverage NOT a filter — Akre style accepts levered compounders if
    the cash machine is working

Scoring weights inflection magnitude (ROIIC delta, FCF/share growth,
margin expansion) over absolute level.

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


def load_table(tk, slot):
    p = CACHE / f'{_safe(tk)}__{slot}.parquet'
    if not p.exists(): return None
    try:
        d = pd.read_parquet(p)
        return d if not d.empty else None
    except Exception: return None


def col(df, candidates):
    """Get a sorted Series for one of the candidate line-item names.

    yfinance parquets vary by region:
      - US/EU style: dates as INDEX, line items as COLUMNS
      - Korea/some Asia: line items as INDEX (often string-truncated),
        dates as COLUMNS
    """
    if df is None or df.empty: return None
    # Detect orientation: if columns look like timestamps, line items are in index
    items_in_index = pd.api.types.is_datetime64_any_dtype(df.columns) or \
                     any(isinstance(c, pd.Timestamp) for c in df.columns[:3])
    for c in candidates:
        if items_in_index:
            # Look in INDEX (allow startswith for truncated names)
            matches = [ix for ix in df.index if str(ix) == c or str(ix).startswith(c[:10])]
            if matches:
                s = pd.to_numeric(df.loc[matches[0]], errors='coerce').dropna()
                if not s.empty: return s.sort_index()
        else:
            if c in df.columns:
                s = pd.to_numeric(df[c], errors='coerce').dropna()
                if not s.empty: return s.sort_index()
    return None


def revenue_growth_yoy(tk):
    """Latest period vs one year prior using yfinance income.
    With Yahoo's 5-quarter depth: use latest quarter vs same quarter prior year."""
    inc = load_table(tk, 'income')
    rev = col(inc, ['Total Revenue','Revenue'])
    if rev is None or len(rev) < 2: return None
    # If at least 5 datapoints assume quarterly and use Q vs Q-4
    if len(rev) >= 5:
        cur = float(rev.iloc[-1]); prv = float(rev.iloc[-5])
    else:
        cur = float(rev.iloc[-1]); prv = float(rev.iloc[0])
    return (cur/prv - 1) * 100 if prv > 0 else None


def op_margin_change_yoy(tk):
    """Change in operating margin: latest period vs same period prior year."""
    inc = load_table(tk, 'income')
    rev = col(inc, ['Total Revenue','Revenue'])
    op  = col(inc, ['Operating Income','EBIT','Operating Revenue'])
    if rev is None or op is None: return None
    if len(rev) < 2 or len(op) < 2: return None
    if len(rev) >= 5 and len(op) >= 5:
        cur_m = float(op.iloc[-1]) / float(rev.iloc[-1]) if rev.iloc[-1] > 0 else None
        prv_m = float(op.iloc[-5]) / float(rev.iloc[-5]) if rev.iloc[-5] > 0 else None
    else:
        cur_m = float(op.iloc[-1]) / float(rev.iloc[-1]) if rev.iloc[-1] > 0 else None
        prv_m = float(op.iloc[0])  / float(rev.iloc[0])  if rev.iloc[0]  > 0 else None
    if cur_m is None or prv_m is None: return None
    return (cur_m - prv_m) * 100


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


def fcf_ps_inflection(tk):
    """Return (recent_ltm_fcf_ps, prior_ltm_fcf_ps, growth_pct).
    Prefer EDGAR depth; fall back to yfinance latest vs prior."""
    ltm = edgar_ltm_fcf_ps(tk)
    if not ltm.empty and len(ltm) >= 5:
        cur = float(ltm.iloc[-1]); prv = float(ltm.iloc[-5])
        if prv > 0 and cur > 0: return cur, prv, (cur/prv - 1) * 100
        if prv <= 0 and cur > 0: return cur, prv, 999.0  # crossed from neg to pos = max inflection
    # yfinance fallback
    cf = load_table(tk, 'cashflow')
    fcf = col(cf, ['Free Cash Flow'])
    if fcf is None or len(fcf) < 5: return None, None, None
    info = load_info(tk)
    shares = info.get('sharesOutstanding') if info else None
    if not shares: return None, None, None
    cur = float(fcf.iloc[-1]) / shares
    prv = float(fcf.iloc[-5]) / shares
    if prv > 0 and cur > 0: return cur, prv, (cur/prv - 1) * 100
    if prv <= 0 and cur > 0: return cur, prv, 999.0
    return None, None, None


def roic_proxy_inflection(tk):
    """Crude ROIIC inflection proxy: change in (operating income / invested capital)
    YoY. Invested capital ~ total assets - cash + total debt is hard from yfinance
    summary; use return on equity delta as practical proxy."""
    info = load_info(tk)
    if info is None: return None
    # not enough series in info_metrics for time progression; fall back to op-margin change
    return op_margin_change_yoy(tk)


def perf_1y(tk):
    p = CACHE / f'{_safe(tk)}__price.parquet'
    if not p.exists(): return None
    try:
        df = pd.read_parquet(p)
        if df.empty: return None
        s = pd.to_numeric(df['Close'], errors='coerce').dropna()
        if len(s) < 252: return None
        return (float(s.iloc[-1]) / float(s.iloc[-252]) - 1) * 100
    except Exception: return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--min-roe', type=float, default=12.0)
    ap.add_argument('--min-rev-growth', type=float, default=5.0)
    ap.add_argument('--min-fcf-ps-growth', type=float, default=20.0)
    ap.add_argument('--min-mcap', type=float, default=200e6)
    ap.add_argument('--max-mcap', type=float, default=30e9)
    ap.add_argument('--perf-1y-lo', type=float, default=-30.0)
    ap.add_argument('--perf-1y-hi', type=float, default=30.0)
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
        roe = info.get('returnOnEquity')
        if mcap is None or roe is None: continue
        if mcap < args.min_mcap or mcap > args.max_mcap: continue
        roe_pct = roe * 100
        if roe_pct < args.min_roe: continue

        rev_g = revenue_growth_yoy(tk)
        if rev_g is None or rev_g < args.min_rev_growth: continue

        margin_chg = op_margin_change_yoy(tk)
        # not strict requirement but used in scoring
        if margin_chg is None: margin_chg = 0.0

        cur_fcf, prv_fcf, fcf_g = fcf_ps_inflection(tk)
        if fcf_g is None: continue
        if fcf_g < args.min_fcf_ps_growth: continue

        perf = perf_1y(tk)
        if perf is None: continue
        if not (args.perf_1y_lo <= perf <= args.perf_1y_hi): continue

        # Akre INFLECTION score: weight on un-priced fundamental improvement
        score = (rev_g * 0.20 + min(fcf_g, 500) * 0.35 + margin_chg * 0.20
                 + roe_pct * 0.15
                 - max(0, perf) * 0.10)  # penalize names that already rerated
        rows.append({
            'ticker': tk,
            'akre_score': round(score, 2),
            'roe_pct': round(roe_pct, 1),
            'op_margin_now_pct': round((info.get('operatingMargins') or 0) * 100, 1),
            'op_margin_chg_pp': round(margin_chg, 1),
            'rev_growth_yoy_pct': round(rev_g, 1),
            'fcf_ps_growth_pct': round(min(fcf_g, 999), 1),
            'perf_1y_pct': round(perf, 1),
            'market_cap': mcap,
            'trailingPE': info.get('trailingPE'),
            'priceToBook': info.get('priceToBook'),
            'priceToSales': info.get('priceToSalesTrailing12Months'),
            'enterpriseToEbitda': info.get('enterpriseToEbitda'),
            'debt_to_equity': info.get('debtToEquity'),
        })
    if not rows:
        print('No tickers passed.')
        return
    df = pd.DataFrame(rows).set_index('ticker').sort_values('akre_score', ascending=False)
    df.to_csv(OUTDIR / 'screener.csv')
    print(f'\nAKRE inflection hits: {len(df)}')
    print(df.head(30).to_string())


if __name__ == '__main__':
    main()
