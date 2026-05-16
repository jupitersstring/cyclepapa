"""Segment-inflection screener: find names where a small, fast-growing revenue
category would (if growth rates persist) come to dominate consolidated results.

Pattern target: EVC/Smadex-style "pre-rerate" setups -- the consolidated
business looks unremarkable or weak, but a minor revenue category is ramping
fast. The market prices the legacy mix; if/when the new category dominates,
the multiple should re-rate.

Limitation: EDGAR's `companyfacts` API returns ONLY consolidated facts (no
XBRL dimensional context). True multi-segment data would require parsing
10-Q/10-K XBRL instance docs directly. As a proxy, we exploit the fact that
many companies tag distinct revenue STREAMS at the top level:
  SalesRevenueGoodsNet      vs SalesRevenueServicesNet
  LicensesRevenue           vs anything
  SubscriptionRevenue / RecurringRevenue / ContractWithCustomerLiabilityRevenueRecognized

If a company carries one of these AND a total revenue tag, we can compute
the share and growth of the minor category and project a crossover.

Triangulates with:
  - cheap-valuation overlay (P/B, P/S, EV/EBITDA) from yfinance info_metrics
  - share-count trajectory (buybacks) from EDGAR XBRL
  - price-response inflection z (ranked.csv) -- we want the market to NOT yet
    have moved on this story

Output: pre_rerate_setups.csv ranked by `pre_rerate_score`.
"""
from __future__ import annotations
import json, gzip, re, sys, math
from pathlib import Path
from typing import Optional
import pandas as pd, numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from edgar_fetcher import _quarterly_records, _series_from_records, _derive_q4


REVENUE_CATEGORIES = {
    'product':       ['SalesRevenueGoodsNet','SalesRevenueProductLine','ProductRevenue','ProductSales'],
    'services':      ['SalesRevenueServicesNet','ServiceRevenue','ServiceSales','RevenueFromServices'],
    'licenses':      ['LicensesRevenue','LicenseAndServicesRevenue','RoyaltyRevenue','LicenseRevenue'],
    'subscription':  ['SubscriptionRevenue','RevenueFromSubscriptionServices','RecurringRevenue',
                      'ContractWithCustomerLiabilityRevenueRecognized'],
}
TOTAL_TAGS = ['Revenues','RevenueFromContractWithCustomerExcludingAssessedTax','SalesRevenueNet']


def get_quarterly(facts: dict, candidates: list) -> pd.Series:
    for tag in candidates:
        node = facts.get(tag)
        if not node: continue
        recs = node.get('units',{}).get('USD')
        if not recs: continue
        qs = _quarterly_records(recs)
        if not qs: continue
        q, a = _series_from_records(qs)
        q = _derive_q4(q, a)
        if not q.empty:
            return q
    return pd.Series(dtype=float)


def years_to_dominate(s_now: float, t_now: float, s_g: float, t_g: float,
                       threshold: float = 0.5) -> float:
    """Years until segment share crosses `threshold` given current values and
    growth rates. Returns inf if segment growth not above total growth or
    parameters degenerate."""
    rest_now = t_now - s_now
    if s_g <= t_g or s_now <= 0 or rest_now <= 0:
        return float('inf')
    try:
        ratio = (threshold/(1-threshold)) * (rest_now/s_now)
        return math.log(ratio) / math.log((1+s_g)/(1+t_g))
    except (ValueError, ZeroDivisionError):
        return float('inf')


def yoy_growth(ttm: pd.Series) -> float:
    if ttm is None or len(ttm) < 5: return float('nan')
    a, b = float(ttm.iloc[-1]), float(ttm.iloc[-5])
    if b == 0: return float('nan')
    if b < 0:  # symmetric handling
        return 2*(a-b)/(abs(a)+abs(b))
    return (a-b)/b


def scan_segment_inflections(edgar_cache: Path) -> pd.DataFrame:
    """Walk every cached EDGAR companyfacts JSON, look for revenue
    disaggregation, compute segment vs total growth + crossover."""
    with open(edgar_cache/'company_tickers.json') as f:
        cik_to_t = {int(r['cik_str']): r['ticker'].upper() for r in json.load(f).values()}

    rows = []
    files = list(edgar_cache.glob('CF_*.json.gz'))
    for i, fpath in enumerate(files):
        m = re.search(r'CF_(\d+)\.json\.gz$', fpath.name)
        if not m: continue
        cik = int(m.group(1)); tkr = cik_to_t.get(cik)
        if not tkr: continue
        try:
            with gzip.open(fpath, 'rt', encoding='utf-8') as f:
                facts = json.load(f)['facts'].get('us-gaap', {})
        except Exception:
            continue

        total_q = get_quarterly(facts, TOTAL_TAGS)
        if total_q.empty or len(total_q) < 8:
            continue

        for cat, cands in REVENUE_CATEGORIES.items():
            sub_q = get_quarterly(facts, cands)
            if sub_q.empty or len(sub_q) < 8: continue
            idx = total_q.index.intersection(sub_q.index)
            if len(idx) < 8: continue
            t = total_q.reindex(idx); s = sub_q.reindex(idx)
            t_ltm = t.rolling(4).sum().dropna()
            s_ltm = s.rolling(4).sum().dropna()
            if t_ltm.empty or s_ltm.empty: continue
            t_now, s_now = float(t_ltm.iloc[-1]), float(s_ltm.iloc[-1])
            if t_now <= 0 or s_now <= 0: continue
            share = s_now / t_now
            if share > 0.7 or share < 0.005: continue
            s_g, t_g = yoy_growth(s_ltm), yoy_growth(t_ltm)
            if not (pd.notna(s_g) and pd.notna(t_g) and s_g > 0): continue
            years = years_to_dominate(s_now, t_now, s_g, t_g)
            rows.append({'ticker':tkr,'category':cat,
                         'share_now':share,'seg_ltm':s_now,'total_ltm':t_now,
                         'seg_growth':s_g,'total_growth':t_g,
                         'excess_growth':s_g - t_g,
                         'years_to_50pct':years,
                         'n_quarters':len(idx)})
    return pd.DataFrame(rows)


def triangulate(seg_df: pd.DataFrame, yf_cache: Path, edgar_cache: Path,
                ranked_path: Optional[Path] = None) -> pd.DataFrame:
    """Combine segment inflection + valuation + buybacks + price-response z."""
    if seg_df.empty: return seg_df

    # Keep best segment per ticker
    seg = seg_df[
        seg_df['years_to_50pct'].between(0.5, 12)
        & (seg_df['share_now'] < 0.40)
        & (seg_df['excess_growth'] > 0.10)
    ].copy()
    seg['seg_score'] = (seg['excess_growth'] / (seg['years_to_50pct']+1)) * (1-seg['share_now'])
    best = seg.sort_values('seg_score',ascending=False).groupby('ticker').head(1).set_index('ticker')

    # Valuation from yfinance info cache
    vals = []
    for tkr in best.index:
        safe = ''.join(c if c.isalnum() or c in '-_' else '_' for c in tkr)
        p = yf_cache / f'{safe}__info_metrics.parquet'
        if not p.exists(): continue
        try:
            d = pd.read_parquet(p)
            if d.empty: continue
            d = d.iloc[0]
            vals.append({'ticker':tkr,
                         'market_cap':d.get('marketCap'),
                         'priceToBook':d.get('priceToBook'),
                         'priceToSales':d.get('priceToSalesTrailing12Months'),
                         'evEbitda':d.get('enterpriseToEbitda')})
        except: pass
    val_df = pd.DataFrame(vals).set_index('ticker') if vals else pd.DataFrame()

    # Share-count trajectory from EDGAR
    with open(edgar_cache/'company_tickers.json') as f:
        t_to_cik = {r['ticker'].upper(): int(r['cik_str']) for r in json.load(f).values()}
    share_rows = []
    for tkr in best.index:
        cik = t_to_cik.get(tkr)
        if not cik: continue
        fpath = edgar_cache / f'CF_{cik:010d}.json.gz'
        if not fpath.exists(): continue
        try:
            with gzip.open(fpath, 'rt') as f: facts = json.load(f)['facts'].get('us-gaap',{})
        except: continue
        for tag in ('WeightedAverageNumberOfDilutedSharesOutstanding',
                    'WeightedAverageNumberOfSharesOutstandingBasic'):
            n = facts.get(tag,{}).get('units',{}).get('shares')
            if not n: continue
            out = {}
            for r in n:
                if not str(r.get('form','')).startswith(('10-Q','10-K')): continue
                if 'start' not in r or 'end' not in r: continue
                try: s,e = pd.Timestamp(r['start']),pd.Timestamp(r['end'])
                except: continue
                if not (80 <= (e-s).days <= 100): continue
                prior = out.get(e)
                if prior is None or str(r.get('filed','')) > str(prior.get('filed','')):
                    out[e] = r
            if not out: continue
            s = pd.Series({k: float(v['val']) for k,v in out.items()}).sort_index()
            if len(s) >= 5:
                share_rows.append({'ticker':tkr,
                                   'shares_1y_chg':(s.iloc[-1]/s.iloc[-5]-1)})
            break
    share_df = pd.DataFrame(share_rows).set_index('ticker') if share_rows else pd.DataFrame()

    # Price-response inflection z (optional)
    if ranked_path and Path(ranked_path).exists():
        inf = pd.read_csv(ranked_path, index_col=0)['avg_inflection_z']
        inf.name = 'avg_inflection_z'
    else:
        inf = pd.Series(dtype=float, name='avg_inflection_z')

    combo = best.join(val_df, how='left').join(share_df, how='left').join(inf, how='left')
    if 'market_cap' in combo.columns:
        combo = combo[combo['market_cap'].fillna(0) > 50e6]

    # Cheap percentile
    for c in ('priceToBook','priceToSales','evEbitda'):
        if c in combo.columns:
            s = pd.to_numeric(combo[c], errors='coerce').where(lambda x: x>0)
            combo[f'{c}_pct'] = s.rank(pct=True,ascending=True)*100
    val_cols = [f'{c}_pct' for c in ('priceToBook','priceToSales','evEbitda') if f'{c}_pct' in combo.columns]
    combo['cheap_pct'] = combo[val_cols].mean(axis=1,skipna=True) if val_cols else 50

    # Pre-rerate score
    combo['pre_rerate_score'] = (
        combo['seg_score'] * 10
        + (50 - combo['cheap_pct'].fillna(50)) / 2
        - combo.get('avg_inflection_z', 0).fillna(0) * 5
        + np.where(combo.get('shares_1y_chg', 0).fillna(0) < -0.01, 5, 0)
        - np.where(combo.get('shares_1y_chg', 0).fillna(0) > 0.05, 3, 0)
    )
    return combo.sort_values('pre_rerate_score', ascending=False)


def main():
    edgar_cache = Path('.cache/edgar')
    yf_cache = Path('.cache/yf')
    ranked = Path('results_edgar_v2/ranked.csv')

    seg = scan_segment_inflections(edgar_cache)
    seg.to_csv('segment_inflection.csv', index=False)
    print(f"segment_inflection.csv: {len(seg)} (ticker, category) rows")

    combo = triangulate(seg, yf_cache, edgar_cache, ranked)
    combo.to_csv('pre_rerate_setups.csv')
    print(f"pre_rerate_setups.csv: {len(combo)} ranked candidates")
    if not combo.empty:
        print("\nTop 15 pre-rerate setups:")
        cols = ['category','share_now','seg_growth','total_growth','years_to_50pct',
                'market_cap','priceToBook','priceToSales','evEbitda','cheap_pct',
                'shares_1y_chg','pre_rerate_score']
        show = combo.head(15)[[c for c in cols if c in combo.columns]].copy()
        for c in ('share_now','seg_growth','total_growth'):
            if c in show: show[c] = (show[c]*100).round(0).astype(int).astype(str)+'%'
        if 'years_to_50pct' in show: show['years_to_50pct']=show['years_to_50pct'].round(1)
        if 'market_cap' in show: show['market_cap']=(show['market_cap']/1e9).round(2)
        for c in ('priceToBook','priceToSales','evEbitda','cheap_pct','pre_rerate_score'):
            if c in show: show[c]=pd.to_numeric(show[c],errors='coerce').round(1)
        if 'shares_1y_chg' in show:
            show['shares_1y_chg']=pd.to_numeric(show['shares_1y_chg'],errors='coerce').apply(
                lambda x:f"{x*100:+.0f}%" if pd.notna(x) else "")
        pd.set_option('display.width',240); pd.set_option('display.max_columns',30)
        print(show.to_string())


if __name__ == '__main__':
    main()
