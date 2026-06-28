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


_EDGAR_VAL_MAP = None
def _edgar_val(ticker: str) -> dict:
    """Lookup EDGAR-computed valuation (P/E, P/B, EV/EBITDA, market cap)
    for US tickers. Built by edgar_valuation_fill.py. Used as a Yahoo-
    independent fallback when yfinance info_metrics is empty."""
    global _EDGAR_VAL_MAP
    if _EDGAR_VAL_MAP is None:
        try:
            df = pd.read_csv('results_peg/edgar_valuation.csv')
            _EDGAR_VAL_MAP = df.set_index(df['ticker'].str.upper()).to_dict('index')
        except Exception:
            _EDGAR_VAL_MAP = {}
    return _EDGAR_VAL_MAP.get(ticker.upper(), {})


def _company_info(ticker: str) -> dict:
    """Get company info — prefer yfinance info_metrics, fall back through:
      1. EDGAR-computed valuation (US tickers — independent of Yahoo)
      2. SEC ticker map (company name only)
    """
    sec_name = _sec_name(ticker)
    entry = {
        'company': sec_name[:42],
        'sector': '', 'industry': '', 'country': 'United States' if sec_name else '',
        'market_cap': None, 'priceToBook': None, 'trailingPE': None,
        'enterpriseToEbitda': None,
    }
    # First try yfinance
    p = YF_CACHE / f'{_safe(ticker)}__info_metrics.parquet'
    if p.exists():
        try:
            d = pd.read_parquet(p)
            if not d.empty:
                r = d.iloc[0]
                name = r.get('longName') or r.get('shortName') or sec_name
                entry['company'] = (str(name)[:42]) if name else entry['company']
                if r.get('sector'):   entry['sector'] = str(r.get('sector'))
                if r.get('industry'): entry['industry'] = str(r.get('industry'))
                if r.get('country'):  entry['country'] = str(r.get('country'))
                if pd.notna(r.get('marketCap')):           entry['market_cap'] = r.get('marketCap')
                if pd.notna(r.get('priceToBook')):         entry['priceToBook'] = r.get('priceToBook')
                if pd.notna(r.get('trailingPE')):          entry['trailingPE'] = r.get('trailingPE')
                if pd.notna(r.get('enterpriseToEbitda')):  entry['enterpriseToEbitda'] = r.get('enterpriseToEbitda')
        except Exception:
            pass
    # Fall back to EDGAR for any field still empty
    ed = _edgar_val(ticker)
    if ed:
        if entry['market_cap'] is None:
            v = ed.get('marketCap_edgar')
            if v is not None and pd.notna(v): entry['market_cap'] = v
        if entry['priceToBook'] is None:
            v = ed.get('priceToBook_edgar')
            if v is not None and pd.notna(v): entry['priceToBook'] = v
        if entry['trailingPE'] is None:
            v = ed.get('trailingPE_edgar')
            if v is not None and pd.notna(v): entry['trailingPE'] = v
        if entry['enterpriseToEbitda'] is None:
            v = ed.get('enterpriseToEbitda_edgar')
            if v is not None and pd.notna(v): entry['enterpriseToEbitda'] = v
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


def analyze_ticker(df: pd.DataFrame, consolidated_total: dict | None = None) -> list[dict]:
    """For each axis × member, compute segment vs total YoY and share.
    Returns one row per (axis, member) pair that qualifies as an archetype
    candidate (share < 40%, excess growth > 10pp, dominates within 0.5-12y).

    `consolidated_total` maps fiscal_year -> total revenue (from companyfacts,
    the non-dimensioned consolidated figure). Using it as the denominator
    avoids the leaf-vs-subtotal DOUBLE-COUNTING that plagued the old
    "sum all leaf members" approach (which gave AAPL a $724B total vs the
    real $416B because it added the "Products" subtotal AND its iPhone/Mac/
    iPad leaves). When the consolidated total isn't available for a year we
    fall back to the segment-sum, but that path is now the exception."""
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
    consolidated_total = consolidated_total or {}

    for axis in agg['axis'].unique():
        ax = agg[agg['axis'] == axis]
        ax_leaves = ax[~ax['member'].isin(EXCLUDE_MEMBERS)]
        # TOTAL: prefer the consolidated revenue from companyfacts (correct,
        # no double-counting). Fall back to leaf-sum only if unavailable.
        ct_now = consolidated_total.get(fy_max)
        ct_prv = consolidated_total.get(fy_prev)
        if ct_now and ct_prv and ct_now > 0 and ct_prv > 0:
            t_now, t_prv = float(ct_now), float(ct_prv)
        else:
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


_EDGAR_CACHE = Path('.cache/edgar')

_CONSOL_CACHE = Path('.cache/edgar/consolidated_revenue.parquet')

def _load_consolidated_revenue(only_ciks: set | None = None) -> dict:
    """Build {ticker_upper: {fiscal_year: total_revenue}} from companyfacts.
    The non-dimensioned annual revenue is the correct segment denominator —
    summing dimensional leaf members double-counts subtotals.

    Loads from the .cache parquet if present (fast). Pass `only_ciks` to
    restrict the (slow) companyfacts scan to a subset — used to compute just
    the segment-bearing tickers rather than all 6,959 filers."""
    # Fast path: load the pre-built cache
    if _CONSOL_CACHE.exists():
        try:
            df = pd.read_parquet(_CONSOL_CACHE)
            out = {}
            for tkr, grp in df.groupby('ticker'):
                out[tkr] = dict(zip(grp['fiscal_year'].astype(int), grp['total_revenue']))
            return out
        except Exception:
            pass
    import json, gzip, re
    out = {}
    tk_file = _EDGAR_CACHE / 'company_tickers.json'
    if not tk_file.exists():
        return out
    try:
        with open(tk_file) as f:
            raw = json.load(f)
        cik_to_ticker = {int(r['cik_str']): r['ticker'].upper()
                         for r in raw.values() if isinstance(r, dict) and 'ticker' in r}
    except Exception:
        return out
    REV_TAGS = ['RevenueFromContractWithCustomerExcludingAssessedTax',
                'Revenues', 'SalesRevenueNet',
                'RevenueFromContractWithCustomerIncludingAssessedTax']
    for f in _EDGAR_CACHE.glob('CF_*.json.gz'):
        m = re.search(r'CF_(\d+)\.json\.gz$', f.name)
        if not m: continue
        cik = int(m.group(1)); tkr = cik_to_ticker.get(cik)
        if not tkr: continue
        if only_ciks is not None and cik not in only_ciks:
            continue
        try:
            with gzip.open(f, 'rt') as fp:
                facts = json.load(fp)['facts'].get('us-gaap', {})
        except Exception:
            continue
        by_fy = {}
        for tag in REV_TAGS:
            node = facts.get(tag)
            if not node: continue
            for r in node.get('units', {}).get('USD', []):
                # Consolidated annual = 10-K, full fiscal period, ~365-day span
                if r.get('form') != '10-K' or r.get('fp') != 'FY':
                    continue
                if 'start' not in r or 'end' not in r:
                    continue
                try:
                    s = pd.Timestamp(r['start']); e = pd.Timestamp(r['end'])
                except Exception:
                    continue
                if not (350 <= (e - s).days <= 380):
                    continue
                fy = r.get('fy')
                if fy is None: continue
                # Keep the latest-filed value per fiscal year
                prior = by_fy.get(int(fy))
                if prior is None or str(r.get('filed','')) > prior[1]:
                    by_fy[int(fy)] = (float(r['val']), str(r.get('filed','')))
            if by_fy:
                break  # first tag with data wins
        if by_fy:
            out[tkr] = {fy: v for fy, (v, _) in by_fy.items()}
    return out


def main():
    files = list(CACHE.glob('*__segments.parquet'))
    print(f'Scanning {len(files):,} XBRL-segment files...')

    # Load consolidated total revenue per ticker from companyfacts (the
    # correct denominator). Keyed CIK → {fiscal_year: total_revenue}.
    consolidated = _load_consolidated_revenue()

    import re as _re
    # Non-common share classes that the SEC CIK→ticker map sometimes returns
    # instead of the primary common stock (e.g. EP-PC = a legacy El Paso
    # preferred now under Kinder Morgan's CIK). These carry the issuer's
    # segment data but the WRONG ticker + no/garbage valuation. Drop them —
    # the common-stock ticker for the same CIK carries the real story.
    _NON_COMMON = _re.compile(r'-P[A-Z]?$|\.PR|-WT$|-WS$|-U$|-UN$|-RT$|-R$|W$', _re.I)

    def _is_non_common(tkr: str) -> bool:
        t = str(tkr)
        # Preferred / warrant / unit / right suffixes
        if _re.search(r'-P[A-Z]?$|\.PR|-WT$|-WS$|-UN?$|-RT?$', t):
            return True
        # Bare trailing 'W' on a 5-char US warrant (CELUW, GEGGL handled elsewhere)
        if len(t) == 5 and t.isalpha() and t.endswith('W'):
            return True
        return False

    all_rows = []
    every_seg = []  # all (ticker, axis, member) we saw, even if not qualifying
    for i, p in enumerate(files):
        try:
            df = pd.read_parquet(p)
        except Exception:
            continue
        # Skip preferred/warrant/unit tickers — the common stock for the same
        # issuer is the right representation
        if not df.empty and _is_non_common(df['ticker'].iloc[0]):
            continue
        tkr = str(df['ticker'].iloc[0]).upper() if not df.empty else ''
        # NOTE: companyfacts fiscal_year (fy) may differ from the segment
        # parquet's fiscal_year. The consolidated dict is keyed by the SEC
        # fy; the segment fiscal_year comes from edgartools. They align for
        # the vast majority of US filers (calendar-ish fiscal years).
        rows = analyze_ticker(df, consolidated_total=consolidated.get(tkr))
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
    # Dedup: keep the FASTEST-dominating segment per ticker.
    df = pd.DataFrame(all_rows)
    df['seg_score'] = (df['excess_growth'] / (df['years_to_dominate'] + 1)) * (1 - df['share_now'])
    # Axis preference: a PRODUCT or BUSINESS segment overtaking the rest is
    # the true pre-rerate archetype (Entravision's Digital Advertising/Smadex
    # overtaking Broadcast; a SaaS line overtaking licenses). A GEOGRAPHIC
    # segment dominating ("Rest of the World" growing) is a weaker signal —
    # it's the same business in a new place, not a business-mix re-rate. So
    # geographic segments get a 0.5x rank weight: still listed, but a
    # product/business story for the same ticker outranks them. This is why
    # EVC now surfaces Digital Advertising instead of Rest-of-the-World.
    _AXIS_WEIGHT = {
        'srt:ProductOrServiceAxis': 1.0,
        'us-gaap:StatementBusinessSegmentsAxis': 1.0,
        'srt:StatementGeographicalAxis': 0.5,
    }
    df['_rank_score'] = df['seg_score'] * df['axis'].map(_AXIS_WEIGHT).fillna(0.8)
    df = df.sort_values('_rank_score', ascending=False)
    best = df.groupby('ticker').head(1).drop(columns=['_rank_score'])

    # Enrich with company info
    info = pd.DataFrame([{'ticker': t, **_company_info(t)} for t in best['ticker'].tolist()])
    out = info.merge(best, on='ticker', how='inner')

    # Dedup at the COMPANY level — same issuer often has preferred-series
    # tickers (FTAIM, FTAIN for FTAI Aviation; BRKB vs BRKA) whose EV/EBITDA
    # and market cap are warped/null. Keep the row with the LARGEST market
    # cap per company name, which is the common-stock ticker by definition.
    if 'company' in out.columns:
        # Push market_cap NaNs to the bottom of the per-company sort
        out['_mc_for_sort'] = pd.to_numeric(out['market_cap'], errors='coerce').fillna(-1)
        out = (out.sort_values(['company','_mc_for_sort','seg_score'],
                               ascending=[True, False, False])
                  .groupby(out['company'].replace('', None).fillna(out['ticker']))
                  .head(1)
                  .drop(columns=['_mc_for_sort'])
                  .reset_index(drop=True))
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
