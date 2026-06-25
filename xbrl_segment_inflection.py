"""TRUE segment-inflection screener using XBRL axis-level facts.

This screener works on .cache/segments/<ticker>__segments.parquet —
the per-segment revenue extracted via fetch_xbrl_segments.py (edgartools)
from the raw 10-K XBRL instance documents. Unlike segment_inflection.py
which can only see top-level revenue tags from SEC's companyfacts JSON,
this sees the TRUE axis-level breakdowns: Apple iPhone vs Mac vs Services,
Microsoft Cloud vs Gaming, Amazon AWS vs Retail, etc.

Per ticker we:
  1. Load all (axis, member, fiscal_year, value) tuples
  2. For each axis (Product / BusinessSegments / Geographic), build per-
     segment-member annual time series
  3. Compute YoY growth for each segment vs the consolidated total
  4. Surface the EVC/Smadex archetype: a segment with share < 40%
     of total, growing >10pp faster, that would dominate within
     0.5-12 years if trends persist.

Output: results_xbrl_segments/screener.csv (the ranked archetype list)
        results_xbrl_segments/all.csv (every segment series we extracted)
"""
from __future__ import annotations
import math
from pathlib import Path
import pandas as pd

CACHE = Path('.cache/segments')
YF_CACHE = Path('.cache/yf')
OUT = Path('results_xbrl_segments'); OUT.mkdir(exist_ok=True)

# Members that are aggregations / totals — exclude when iterating "segments"
EXCLUDE_MEMBERS = {
    'us-gaap:ProductMember',          # "Products" total
    'us-gaap:ServiceMember',          # "Service and Other" total
    'srt:NorthAmericaMember',         # geographic aggregations
    'srt:EuropeMember',
    'srt:AsiaPacificMember',
    'us-gaap:ConsolidatedEntitiesMember',
    'us-gaap:OperatingSegmentsMember',
    'us-gaap:CorporateMember',
}


def _safe(t): return ''.join(c if c.isalnum() or c in '-_' else '_' for c in t)


_SEC_TICKER_TO_NAME = None
def _sec_name(ticker: str) -> str:
    """Fallback company name from the SEC ticker map (universal US coverage).
    company_tickers.json is structured as {"0": {"cik_str": N, "ticker": "X",
    "title": "Y"}, ...} — index by ticker, return title."""
    global _SEC_TICKER_TO_NAME
    if _SEC_TICKER_TO_NAME is None:
        import json as _json
        try:
            with open('.cache/edgar/company_tickers.json') as f:
                raw = _json.load(f)
            _SEC_TICKER_TO_NAME = {
                r['ticker'].upper(): r.get('title','')
                for r in raw.values() if isinstance(r, dict) and 'ticker' in r
            }
        except Exception as e:
            print(f'SEC ticker map load failed: {e}')
            _SEC_TICKER_TO_NAME = {}
    return _SEC_TICKER_TO_NAME.get(ticker.upper(), '')


def _company_info(ticker: str) -> dict:
    """Get company info — prefer yfinance info_metrics (rich), fall back to
    SEC ticker map (universal US coverage) for at least the company name.
    Many XBRL-segment tickers are smaller/recently-listed and won't have
    yfinance info, but they ALL have a SEC name."""
    # Default: SEC-name-only entry
    entry = {
        'company': _sec_name(ticker)[:42],
        'sector': '', 'industry': '', 'country': 'United States',
        'market_cap': None, 'priceToBook': None, 'trailingPE': None,
        'enterpriseToEbitda': None,
    }
    p = YF_CACHE / f'{_safe(ticker)}__info_metrics.parquet'
    if not p.exists():
        return entry
    try:
        d = pd.read_parquet(p)
        if d.empty: return entry
        r = d.iloc[0]
        entry['company'] = (r.get('longName') or r.get('shortName') or entry['company'])[:42]
        entry['sector'] = r.get('sector') or entry['sector']
        entry['industry'] = r.get('industry') or entry['industry']
        entry['country'] = r.get('country') or entry['country']
        entry['market_cap'] = r.get('marketCap')
        entry['priceToBook'] = r.get('priceToBook')
        entry['trailingPE'] = r.get('trailingPE')
        entry['enterpriseToEbitda'] = r.get('enterpriseToEbitda')
        return entry
    except Exception:
        return entry


def years_to_dominate(s_now: float, t_now: float, s_g: float, t_g: float,
                       threshold: float = 0.5) -> float:
    rest_now = t_now - s_now
    if s_g <= t_g or s_now <= 0 or rest_now <= 0:
        return float('inf')
    try:
        ratio = (threshold/(1-threshold)) * (rest_now/s_now)
        return math.log(ratio) / math.log((1+s_g)/(1+t_g))
    except (ValueError, ZeroDivisionError):
        return float('inf')


def analyze_ticker(df: pd.DataFrame) -> list[dict]:
    """For each axis × member, compute segment vs total YoY and share.
    Returns one row per (axis, member) pair that qualifies as an archetype
    candidate (share < 40%, excess growth > 10pp, dominates within 0.5-12y)."""
    rows = []
    ticker = df['ticker'].iloc[0]
    # Pick the most recent fiscal year as 'now'
    df = df.dropna(subset=['value', 'fiscal_year'])
    df['fiscal_year'] = pd.to_numeric(df['fiscal_year'], errors='coerce').astype('Int64')
    df = df.dropna(subset=['fiscal_year'])
    if df.empty:
        return rows
    fy_max = int(df['fiscal_year'].max())
    fy_prev = fy_max - 1
    # Some companies report cross-year periods (Q4 vs annual) — pick max value per
    # (axis, member, fiscal_year) to deduplicate
    agg = (df.groupby(['axis', 'member', 'member_label', 'fiscal_year'])['value']
              .max().reset_index())

    # For each axis, compute the total = sum of all NON-aggregation members
    for axis in agg['axis'].unique():
        ax = agg[agg['axis'] == axis]
        # Try to identify the total: either an explicit "all" member or sum-of-leaves
        # In practice each (concept × axis) reports leaves AND totals — we sum the
        # leaves where the leaf member is not in EXCLUDE_MEMBERS.
        ax_leaves = ax[~ax['member'].isin(EXCLUDE_MEMBERS)]
        totals_by_fy = ax_leaves.groupby('fiscal_year')['value'].sum()
        if fy_max not in totals_by_fy.index or fy_prev not in totals_by_fy.index:
            continue
        t_now, t_prv = float(totals_by_fy.loc[fy_max]), float(totals_by_fy.loc[fy_prev])
        if t_now <= 0 or t_prv <= 0:
            continue
        t_g = (t_now / t_prv - 1)

        # Each leaf member is a candidate segment
        for member, mlabel in ax_leaves[['member', 'member_label']].drop_duplicates().itertuples(index=False):
            seg = ax_leaves[(ax_leaves['member'] == member)]
            seg_fy = seg.set_index('fiscal_year')['value']
            if fy_max not in seg_fy.index or fy_prev not in seg_fy.index:
                continue
            s_now, s_prv = float(seg_fy.loc[fy_max]), float(seg_fy.loc[fy_prev])
            if s_now <= 0 or s_prv <= 0:
                continue
            share = s_now / t_now
            if share > 0.7 or share < 0.005:
                continue
            s_g = (s_now / s_prv - 1)
            if s_g <= 0:
                continue
            # Cap base-effect noise: if growth > 500% (5x), the prior-year base
            # was likely tiny or non-existent (new product / new geography
            # first-reported). Still real but distorts ranking — replace with
            # a capped value for the inflection arithmetic.
            s_g_capped = min(s_g, 5.0)
            excess = s_g_capped - t_g
            if excess < 0.10:
                continue
            yrs = years_to_dominate(s_now, t_now, s_g_capped, t_g)
            if not (0.5 <= yrs <= 12):
                continue
            rows.append({
                'ticker': ticker,
                'axis': axis,
                'segment': mlabel,
                'fiscal_year': fy_max,
                'share_now': share,
                'seg_growth': s_g,         # raw — for display
                'seg_growth_capped': s_g_capped,
                'total_growth': t_g,
                'excess_growth': excess,
                'years_to_dominate': yrs,
                'seg_revenue_now_M': s_now / 1e6,
                'total_revenue_now_M': t_now / 1e6,
            })
    return rows


def main():
    files = list(CACHE.glob('*__segments.parquet'))
    print(f'Scanning {len(files):,} XBRL-segment files...')

    all_rows = []
    every_seg = []  # all (ticker, axis, member) we saw, even if not qualifying
    for i, p in enumerate(files):
        try:
            df = pd.read_parquet(p)
        except Exception:
            continue
        rows = analyze_ticker(df)
        all_rows.extend(rows)
        # Also dump every segment, for the "all" CSV
        df2 = df.dropna(subset=['value','fiscal_year']).copy()
        df2['fiscal_year'] = pd.to_numeric(df2['fiscal_year'], errors='coerce').astype('Int64')
        for _, r in df2.iterrows():
            every_seg.append({
                'ticker': r['ticker'],
                'axis': r['axis'],
                'segment': r.get('member_label') or r.get('member'),
                'fiscal_year': r['fiscal_year'],
                'value_M': r['value'] / 1e6,
            })
        if (i + 1) % 500 == 0:
            print(f'  {i+1:,}/{len(files):,}  candidates={len(all_rows):,}')

    # Save the "all" table
    pd.DataFrame(every_seg).to_csv(OUT / 'all.csv', index=False)
    if not all_rows:
        print('No archetype candidates found.')
        return
    # Dedup: keep the FASTEST-dominating segment per ticker
    df = pd.DataFrame(all_rows)
    df['seg_score'] = (df['excess_growth'] / (df['years_to_dominate'] + 1)) * (1 - df['share_now'])
    df = df.sort_values('seg_score', ascending=False)
    best = df.groupby('ticker').head(1)

    # Enrich with company info
    info = pd.DataFrame([{'ticker': t, **_company_info(t)} for t in best['ticker'].tolist()])
    out = info.merge(best, on='ticker', how='inner')
    # Front-load human-readable columns
    front = ['ticker','company','sector','industry','country','axis','segment',
             'share_now','seg_growth','total_growth','excess_growth',
             'years_to_dominate','seg_revenue_now_M','total_revenue_now_M',
             'fiscal_year','market_cap','priceToBook','trailingPE','enterpriseToEbitda',
             'seg_score']
    front = [c for c in front if c in out.columns]
    out = out[front + [c for c in out.columns if c not in front]]
    out = out.sort_values('seg_score', ascending=False)
    out.to_csv(OUT / 'screener.csv', index=False)
    print(f'\nWrote {len(out):,} ranked archetype candidates to {OUT/"screener.csv"}')
    print(f'\nTop 15:')
    show = out.head(15)[['ticker','company','axis','segment','share_now','seg_growth','total_growth','years_to_dominate','seg_score']].copy()
    for c in ('share_now','seg_growth','total_growth'):
        show[c] = (show[c]*100).round(1).astype(str) + '%'
    show['years_to_dominate'] = show['years_to_dominate'].round(1)
    show['seg_score'] = show['seg_score'].round(3)
    pd.set_option('display.width', 240); pd.set_option('display.max_columns', 20)
    print(show.to_string(index=False))


if __name__ == '__main__':
    main()
