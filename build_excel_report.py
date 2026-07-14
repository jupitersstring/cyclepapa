"""Build a multi-tab Excel workbook with the top-N names from each screener
plus a composite-score tab.

Each tab carries:
  - the screener-specific signal columns (z-scores, growth pct, etc.)
  - a consistent block of headline financials joined in from the cached
    info_metrics parquet (market cap, P/B, P/S, EV/EBITDA, trailing EPS,
    LTM revenue, margins, ROE/ROA, debt/equity, sector)

Output: screener_report.xlsx
"""
from __future__ import annotations
from pathlib import Path
import numpy as np, pandas as pd

CACHE = Path('.cache/yf')
OUT_XLSX = Path('screener_report.xlsx')
TOP_N = 50

# India suffix filter — exclude from main tabs; surface separately
def _is_india(ticker: str) -> bool:
    t = str(ticker).upper()
    return t.endswith('.NS') or t.endswith('.BO') or t.endswith('_NS') or t.endswith('_BO')

# Headline-financial columns we want on every tab
HEADLINE_COLS = [
    'name','sector','industry','country',
    'market_cap','currentPrice',
    'priceToBook','priceToSalesTrailing12Months',
    'trailingPE','forwardPE',
    'enterpriseToEbitda','enterpriseToRevenue',
    'trailingEps','totalRevenue',
    'profitMargins','operatingMargins','grossMargins',
    'returnOnEquity','returnOnAssets','debtToEquity',
    'totalCash','totalDebt','enterpriseValue','sharesOutstanding',
]


def _safe(t: str) -> str:
    return ''.join(c if c.isalnum() or c in '-_' else '_' for c in t)


# Pre-build sector / industry / name lookup from the financedatabase universe CSVs
_META_LOOKUP: dict[str, dict] = {}
def _build_meta_lookup():
    if _META_LOOKUP: return
    universe_files = [
        'universe_us_wide.csv','universe_expanded.csv','universe_wider.csv',
        'universe_eu.csv','universe_eu_extra.csv','universe_canada.csv',
        'us_small_full.csv','us_small_universe.csv',
    ]
    fields = ['name','sector','industry','country']
    for fn in universe_files:
        p = Path(fn)
        if not p.exists(): continue
        try:
            df = pd.read_csv(p, usecols=lambda c: c in (['symbol'] + fields), low_memory=False)
        except Exception: continue
        if 'symbol' not in df.columns: continue
        for _, r in df.iterrows():
            tk = r.get('symbol')
            if not isinstance(tk, str): continue
            tk = tk.upper()
            if tk in _META_LOOKUP: continue
            _META_LOOKUP[tk] = {f: r.get(f) for f in fields if f in df.columns}
    # Also fall back to any sector/industry stored in screener CSVs
    for path in [
        'results_operating_leverage/screener.csv',
        'results_ev_fcf_leverage/screener.csv',
        'results_fcf_yield/screener.csv',
        'pre_rerate_setups.csv',
    ]:
        p = Path(path)
        if not p.exists(): continue
        try:
            df = pd.read_csv(p)
        except Exception: continue
        if 'ticker' not in df.columns: continue
        for _, r in df.iterrows():
            tk = r.get('ticker')
            if not isinstance(tk, str): continue
            tk = tk.upper()
            cur = _META_LOOKUP.setdefault(tk, {})
            for f in ('sector','industry'):
                if f in df.columns and not cur.get(f) and isinstance(r.get(f), str):
                    cur[f] = r.get(f)


_INFO_CACHE: dict[str, dict] = {}
def load_info(ticker: str) -> dict:
    if ticker in _INFO_CACHE:
        return _INFO_CACHE[ticker]
    for variant in (ticker, _safe(ticker)):
        p = CACHE / f'{variant}__info_metrics.parquet'
        if p.exists():
            try:
                df = pd.read_parquet(p)
                if not df.empty:
                    d = df.iloc[0].to_dict()
                    _INFO_CACHE[ticker] = d
                    return d
            except Exception: pass
    _INFO_CACHE[ticker] = {}
    return {}


def headline_block(ticker: str) -> dict:
    _build_meta_lookup()
    d = load_info(ticker)
    meta = _META_LOOKUP.get(ticker.upper(), {})
    out = {}
    for c in HEADLINE_COLS:
        if c in ('name','sector','industry','country'):
            out[c] = meta.get(c)
        elif c == 'market_cap':
            out[c] = d.get('marketCap')
        else:
            out[c] = d.get(c)
    return out


def merge_headline(df: pd.DataFrame, ticker_col: str = 'ticker') -> pd.DataFrame:
    """Append headline-financial columns by joining on ticker."""
    if df.empty: return df
    rows = []
    for tk in df[ticker_col].astype(str):
        rows.append(headline_block(tk))
    hl = pd.DataFrame(rows, index=df.index)
    # don't clobber columns the screener already has
    new_cols = [c for c in hl.columns if c not in df.columns]
    return pd.concat([df, hl[new_cols]], axis=1)


# ---------- per-screener loaders/top-N ----------

def load_multi_variant(path: str, min_variants: int) -> pd.DataFrame:
    p = Path(path)
    if not p.exists(): return pd.DataFrame()
    df = pd.read_csv(p)
    cols = ['ticker',
            'avg_inflection_z',
            'eps_ret_abs_inflection_z','eps_ret_rel_inflection_z',
            'comp_ret_abs_inflection_z','comp_ret_rel_inflection_z',
            'eps_shp_abs_inflection_z','eps_shp_rel_inflection_z',
            'comp_shp_abs_inflection_z','comp_shp_rel_inflection_z']
    # count how many of the 8 variants are inflected
    flag_cols = [c for c in df.columns if c.endswith('_is_inflected')]
    df['n_variants_inflected'] = df[flag_cols].sum(axis=1)
    df = df[df['n_variants_inflected'] >= min_variants]
    df = df.sort_values('avg_inflection_z', ascending=False).head(TOP_N)
    keep = [c for c in cols if c in df.columns] + ['n_variants_inflected']
    return df[keep].reset_index(drop=True)


def load_fcf_signflip(path: str) -> pd.DataFrame:
    p = Path(path)
    if not p.exists(): return pd.DataFrame()
    df = pd.read_csv(p)
    df = df[(df['metric'] == 'fcf_ps') & (df['is_flip'] == True)
            & (df['view'].isin(['quarterly_strict','ttm_yoy']))].copy()
    df = df.sort_values('flip_magnitude_pct', ascending=False).head(TOP_N * 2)
    keep = ['ticker','view','prior_mean','recent_mean','flip_magnitude_pct',
            'frac_negative_prior','frac_positive_recent','latest_value','n_history']
    return df[[c for c in keep if c in df.columns]].reset_index(drop=True)


def load_deep_value(path: str) -> pd.DataFrame:
    p = Path(path)
    if not p.exists(): return pd.DataFrame()
    df = pd.read_csv(p)
    df = df[df['is_value_plus_inflection'] == True].copy()
    df = df.sort_values('n_variants_inflected', ascending=False).head(TOP_N)
    keep = ['ticker','enterprise_value','market_cap','is_negative_ev','ncav',
            'ncav_per_share','price_to_ncav','is_net_net','is_strict_net_net',
            'n_variants_inflected']
    return df[[c for c in keep if c in df.columns]].reset_index(drop=True)


def load_cheap_inflecting(path: str) -> pd.DataFrame:
    p = Path(path)
    if not p.exists(): return pd.DataFrame()
    df = pd.read_csv(p)
    df = df[df['is_cheap_inflecting'] == True].copy()
    df = df.sort_values('n_variants_inflected', ascending=False).head(TOP_N)
    keep = ['ticker','info_priceToBook','info_priceToSalesTrailing12Months',
            'pb_pct','ps_pct','n_variants_inflected']
    return df[[c for c in keep if c in df.columns]].reset_index(drop=True)


def load_52wh(path: str) -> pd.DataFrame:
    p = Path(path)
    if not p.exists(): return pd.DataFrame()
    df = pd.read_csv(p)
    # require new_52w_high AND rel_new_52w_high — strictest setup
    if 'rel_new_52w_high' in df.columns:
        df = df[(df['new_52w_high'] == True) & (df['rel_new_52w_high'] == True)]
    df = df.sort_values('revenue_growth_ltm', ascending=False).head(TOP_N)
    keep = ['ticker','market_cap','price_latest','52w_high','pct_off_high',
            'at_52w_high','new_52w_high','rel_at_52w_high','rel_new_52w_high',
            'pe','priceToBook','priceToSales','ev_ebitda',
            'revenue_growth_ltm','ebitda_growth_ltm']
    return df[[c for c in keep if c in df.columns]].reset_index(drop=True)


def load_simple(path: str, sort_col: str, ascending=False, where=None) -> pd.DataFrame:
    p = Path(path)
    if not p.exists(): return pd.DataFrame()
    df = pd.read_csv(p)
    if where is not None: df = df[where(df)]
    if sort_col in df.columns:
        df = df.sort_values(sort_col, ascending=ascending)
    return df.head(TOP_N).reset_index(drop=True)


def load_volasym(path: str) -> pd.DataFrame:
    p = Path(path)
    if not p.exists(): return pd.DataFrame()
    df = pd.read_csv(p)
    # m_state in (squeeze, hyper_squeeze) AND m_asym_state == upper
    if 'm_state' in df.columns and 'm_asym_state' in df.columns:
        df = df[df['m_state'].isin(['squeeze','hyper_squeeze'])
                & (df['m_asym_state'] == 'upper')]
    keep = ['ticker','w_state','w_asym_state','m_state','m_asym_state',
            'w_sq','w_asym','m_sq','m_asym',
            'w_bars_since_squeeze_cross','m_bars_since_squeeze_cross']
    keep = [c for c in keep if c in df.columns]
    return df[keep].head(TOP_N).reset_index(drop=True)


# ---------- composite tab ----------

# Replicates the SCREENS list from convergence_report.py so we get the same
# pass-criteria, but we build it inline here to avoid coupling.
COMP_SCREENS = [
    ('multi_variant_us',     'results_us_wide/ranked.csv',
        lambda r: pd.notna(r.get('n_variants_inflected')) and r.get('n_variants_inflected', 0) >= 4),
    ('multi_variant_eu',     'results_eu_relaxed/ranked.csv',
        lambda r: pd.notna(r.get('n_variants_inflected')) and r.get('n_variants_inflected', 0) >= 3),
    ('multi_variant_ca',     'results_canada/ranked.csv',
        lambda r: pd.notna(r.get('n_variants_inflected')) and r.get('n_variants_inflected', 0) >= 3),
    ('fcf_signflip_strict',  'results_us_wide/fcf_inflections.csv',
        lambda r: r.get('view') == 'quarterly_strict' and r.get('metric') == 'fcf_ps' and r.get('is_flip') == True),
    ('fcf_signflip_ttm',     'results_us_wide/fcf_inflections.csv',
        lambda r: r.get('view') == 'ttm_yoy' and r.get('metric') == 'fcf_ps' and r.get('is_flip') == True),
    ('deep_value_us',        'results_us_wide/deep_value_screen.csv',
        lambda r: r.get('is_value_plus_inflection') == True),
    ('cheap_inflecting',     'results_us_wide/valuation_screen.csv',
        lambda r: r.get('is_cheap_inflecting') == True),
    ('52wh_cheap',           'results_52wh/screener.csv',
        lambda r: True),
    ('multiple_compression', 'results_multiple_compression/clean.csv',
        lambda r: pd.notna(r.get('multiple_compression_pct')) and r.get('multiple_compression_pct') < -10),
    ('ev_compression',       'results_ev_compression/screener.csv',
        lambda r: True),
    ('operating_leverage',   'results_operating_leverage/screener.csv',
        lambda r: True),
    ('ev_fcf_leverage',      'results_ev_fcf_leverage/screener.csv',
        lambda r: True),
    ('fcf_yield_setup',      'results_fcf_yield/screener.csv',
        lambda r: True),
    ('segment_pre_rerate',   'pre_rerate_setups.csv',
        lambda r: pd.notna(r.get('pre_rerate_score')) and r.get('pre_rerate_score') > 5),
    ('volasym_bullish',      'results_volasym/volatility_asymmetry.csv',
        lambda r: r.get('m_state') in ('squeeze','hyper_squeeze') and r.get('m_asym_state') == 'upper'),
]


def build_composite() -> pd.DataFrame:
    from collections import defaultdict
    membership: dict[str, set[str]] = defaultdict(set)
    for label, path, filt in COMP_SCREENS:
        p = Path(path)
        if not p.exists(): continue
        try:
            df = pd.read_csv(p)
        except Exception: continue
        for _, row in df.iterrows():
            try:
                tk = row.get('ticker')
                if not isinstance(tk, str): continue
                tk = tk.upper()
                if filt(row): membership[tk].add(label)
            except Exception: continue

    rows = []
    for tk, screens in membership.items():
        if len(screens) < 3: continue   # composite tab = 3+ screens
        rows.append({
            'ticker': tk,
            'n_screens': len(screens),
            'screens_joined': '; '.join(sorted(screens)),
        })
    comp = pd.DataFrame(rows).sort_values('n_screens', ascending=False).reset_index(drop=True)
    return comp


# ---------- write workbook ----------

def main():
    print('Building tabs...')

    tabs: dict[str, pd.DataFrame] = {}

    # Composite first so it lands as the front tab
    comp = build_composite()
    if not comp.empty:
        tabs['composite_score'] = merge_headline(comp)
        print(f"  composite_score          {len(tabs['composite_score'])} rows (3+ screens)")

    # Multi-variant inflection
    for region, path, min_v in [
        ('multi_variant_us',  'results_us_wide/ranked.csv',  4),
        ('multi_variant_eu',  'results_eu_relaxed/ranked.csv', 3),
        ('multi_variant_ca',  'results_canada/ranked.csv',   3),
    ]:
        d = load_multi_variant(path, min_v)
        if not d.empty:
            tabs[region] = merge_headline(d)
            print(f"  {region:<24} {len(tabs[region])} rows")

    # FCF sign-flip (combined strict+ttm)
    d = load_fcf_signflip('results_us_wide/fcf_inflections.csv')
    if not d.empty:
        tabs['fcf_signflip'] = merge_headline(d.head(TOP_N))
        print(f"  fcf_signflip             {len(tabs['fcf_signflip'])} rows")

    d = load_deep_value('results_us_wide/deep_value_screen.csv')
    if not d.empty:
        tabs['deep_value_us'] = merge_headline(d)
        print(f"  deep_value_us            {len(tabs['deep_value_us'])} rows")

    d = load_cheap_inflecting('results_us_wide/valuation_screen.csv')
    if not d.empty:
        tabs['cheap_inflecting'] = merge_headline(d)
        print(f"  cheap_inflecting         {len(tabs['cheap_inflecting'])} rows")

    d = load_52wh('results_52wh/screener.csv')
    if not d.empty:
        tabs['52wh_cheap'] = merge_headline(d)
        print(f"  52wh_cheap               {len(tabs['52wh_cheap'])} rows")

    d = load_simple('results_multiple_compression/clean.csv', 'multiple_compression_pct', ascending=True,
                    where=lambda d: d['multiple_compression_pct'] < -10)
    if not d.empty:
        tabs['multiple_compression'] = merge_headline(d)
        print(f"  multiple_compression     {len(tabs['multiple_compression'])} rows")

    d = load_simple('results_ev_compression/screener.csv', 'compression_vs_sales_pct', ascending=True)
    if not d.empty:
        tabs['ev_compression'] = merge_headline(d)
        print(f"  ev_compression           {len(tabs['ev_compression'])} rows")

    d = load_simple('results_operating_leverage/screener.csv', 'leverage_score', ascending=False)
    if not d.empty:
        tabs['operating_leverage'] = merge_headline(d)
        print(f"  operating_leverage       {len(tabs['operating_leverage'])} rows")

    d = load_simple('results_ev_fcf_leverage/screener.csv', 'fcf_growth_pct', ascending=False)
    if not d.empty:
        tabs['ev_fcf_leverage'] = merge_headline(d)
        print(f"  ev_fcf_leverage          {len(tabs['ev_fcf_leverage'])} rows")

    d = load_simple('results_fcf_yield/screener.csv', 'fcf_yield_now_pct', ascending=False)
    if not d.empty:
        tabs['fcf_yield_setup'] = merge_headline(d)
        print(f"  fcf_yield_setup          {len(tabs['fcf_yield_setup'])} rows")

    d = load_simple('pre_rerate_setups.csv', 'pre_rerate_score', ascending=False,
                    where=lambda d: d['pre_rerate_score'] > 5)
    if not d.empty:
        tabs['segment_pre_rerate'] = merge_headline(d)
        print(f"  segment_pre_rerate       {len(tabs['segment_pre_rerate'])} rows")

    d = load_volasym('results_volasym/volatility_asymmetry.csv')
    if not d.empty:
        tabs['volasym_bullish'] = merge_headline(d)
        print(f"  volasym_bullish          {len(tabs['volasym_bullish'])} rows")

    # Build a separate India tab from every screener (concatenated)
    india_rows = []
    for name, df in tabs.items():
        if df is None or df.empty: continue
        if 'ticker' not in df.columns: continue
        india = df[df['ticker'].apply(_is_india)].copy()
        if not india.empty:
            india.insert(0, 'source_screen', name)
            india_rows.append(india)
    # Strip India from main tabs
    for name in list(tabs):
        df = tabs[name]
        if df is None or df.empty or 'ticker' not in df.columns: continue
        tabs[name] = df[~df['ticker'].apply(_is_india)].reset_index(drop=True)
    if india_rows:
        tabs['india_only'] = pd.concat(india_rows, ignore_index=True, sort=False)

    # Write
    with pd.ExcelWriter(OUT_XLSX, engine='openpyxl') as xw:
        for name, df in tabs.items():
            df.to_excel(xw, sheet_name=name[:31], index=False)
            ws = xw.sheets[name[:31]]
            ws.column_dimensions['A'].width = 14
            ws.freeze_panes = 'B2'

    print(f'\nWrote {OUT_XLSX} ({sum(len(d) for d in tabs.values())} total rows across {len(tabs)} tabs)')


if __name__ == '__main__':
    main()
