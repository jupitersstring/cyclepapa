"""Growth-adjusted value survey across the entire cached universe.

Computes the growth-adjusted valuation ratios per the spec:

  ev_ebitda_g       = (EV/EBITDA) / EBITDA-growth%      (latest annual)
  ev_sales_g        = (EV/Sales)  / revenue-growth%     (latest annual)
  ev_ebitda_g_ltm   = (EV/EBITDA) / EPS-quarterly-growth (LTM-style proxy)
  ev_sales_g_ltm    = (EV/Sales)  / revenue-growth      (currently same as above —
                                                          we lack quarterly rev growth scalar)
  ev_*_g_bv         = ev_*_g × bv_tilt(P/B)             (low P/B = bonus, bounded ±20%)

The bv_tilt is gentle + diminishing per the user's spec:
  tilt = 1 - 0.2 * (1 - P/B) / (1 + P/B)
P/B=0.5 -> 0.933 (reward, -6.7%);  P/B=2.0 -> 1.067 (mild penalty, +6.7%).
Bounded to roughly ±20% so it's a tilt, not the driver.

EV/Sales is rebuilt from priceToSales × (EV / MktCap) so it's currency-neutral
across regions (raw EV is in local currency, P/S is unitless).

NaN-rules: a ratio is NaN if either input is NaN or non-positive. PEGs are
meaningless for non-growers / negative multiples.

Output:
  results_peg/growth_adj_value.csv   — every scored row, sortable
  results_peg/growth_adj_value_top.csv — top 60 globally + per-region cuts

Usage:
  python growth_adj_value.py [--min-mcap MCAP] [--top-n N]
"""
from __future__ import annotations
import argparse, sys
from pathlib import Path
import pandas as pd
import numpy as np

CACHE = Path('.cache/yf')
OUT = Path('results_peg'); OUT.mkdir(exist_ok=True)


def safe(t): return ''.join(c if c.isalnum() or c in '-_' else '_' for c in t)


# Region suffix → display label. Covers all 33 markets in REGIONS.
SUFFIX_REGION = {
    '': 'US',
    '.T': 'JP', '.L': 'GB', '.DE': 'DE', '.F': 'DE', '.PA': 'FR',
    '.TO': 'CA', '.V': 'CA', '.AX': 'AU',
    '.SW': 'CH', '.MI': 'IT', '.AS': 'NL', '.MC': 'ES',
    '.ST': 'SE', '.OL': 'NO', '.CO': 'DK', '.BR': 'BE', '.HE': 'FI',
    '.IR': 'IE', '.VI': 'AT', '.LS': 'PT', '.AT': 'GR',
    '.KS': 'KR', '.KQ': 'KR', '.HK': 'HK', '.TW': 'TW', '.TWO': 'TW',
    '.SI': 'SG', '.NZ': 'NZ', '.TA': 'IL',
    '.SS': 'CN', '.SZ': 'CN', '.NS': 'IN', '.BO': 'IN', '.SA': 'BR',
    '.MX': 'MX', '.JO': 'ZA', '.IS': 'TR', '.BK': 'TH', '.JK': 'ID',
}
def _region(tk: str) -> str:
    if '.' in tk:
        suff = '.' + tk.rsplit('.', 1)[1]
        return SUFFIX_REGION.get(suff, 'OTHER')
    return 'US'


def bv_tilt(pb: float, bv_weight: float = 0.2) -> float:
    """Gentle, bounded, diminishing low-P/B reward.
      tilt = 1 - bv_weight * (1 - P/B) / (1 + P/B)
    P/B < 1  -> tilt < 1 (reward — multiply by something < 1 → smaller ratio = cheaper)
    P/B > 1  -> tilt > 1 (mild penalty)
    Diminishing because (1-P/B)/(1+P/B) saturates between -1 and +1.
    """
    if pb is None or not np.isfinite(pb) or pb <= 0:
        return 1.0
    return 1.0 - bv_weight * (1.0 - pb) / (1.0 + pb)


def load_all_info(min_mcap: float):
    """Walk the cache and load every info_metrics row.

    Returns DataFrame with one row per ticker, plus derived region.
    """
    rows = []
    for p in CACHE.glob('*__info_metrics.parquet'):
        tk = p.name.split('__')[0]
        # Reverse the safe-name → ticker mapping. The safe-name uses _ for
        # everything that isn't [A-Za-z0-9_-]; the only case we encode is '.'
        # which becomes '_'. For region inference we want the original ticker
        # with its dot. We can recover this for any *_<suffix> name where
        # <suffix> is a known region suffix.
        # Best effort: replace last '_' with '.' if that maps to a known suffix.
        orig = tk
        if '_' in tk:
            head, _, tail = tk.rpartition('_')
            if ('.' + tail) in {'.T','.L','.DE','.F','.PA','.TO','.V','.AX','.SW','.MI','.AS','.MC','.ST','.OL','.CO','.BR','.HE','.IR','.VI','.LS','.AT','.KS','.KQ','.HK','.TW','.TWO','.SI','.NZ','.TA','.SS','.SZ','.NS','.BO','.SA','.MX','.JO','.IS','.BK','.JK'}:
                orig = head + '.' + tail
        try:
            d = pd.read_parquet(p)
            if d.empty: continue
            r = d.iloc[0].to_dict()
            r['ticker'] = orig
            r['cache_key'] = tk
            r['region'] = _region(orig)
            rows.append(r)
        except Exception: pass
    df = pd.DataFrame(rows)
    if df.empty: return df
    # Filter to mcap floor
    mc = pd.to_numeric(df['marketCap'], errors='coerce')
    df = df[mc.fillna(0) >= min_mcap]
    return df


def _ebitda_series_from(parquet_path: Path) -> pd.Series:
    """Pull an EBITDA time series out of one income parquet (annual OR
    quarterly). Returns empty Series if missing/empty/no EBITDA row."""
    if not parquet_path.exists():
        return pd.Series(dtype=float)
    try:
        inc = pd.read_parquet(parquet_path)
    except Exception:
        return pd.Series(dtype=float)
    if inc.empty:
        return pd.Series(dtype=float)
    for tag in ('EBITDA', 'Normalized EBITDA'):
        if tag in inc.index:
            s = pd.to_numeric(inc.loc[tag], errors='coerce').dropna()
            if s.empty: continue
            s.index = pd.to_datetime(s.index, errors='coerce')
            s = s[~s.index.isna()].sort_index()
            if not s.empty:
                return s
    return pd.Series(dtype=float)


def _load_ebitda_growth(cache_key: str) -> tuple[float | None, float | None]:
    """Return (ltm_ebitda_growth_pct, annual_ebitda_growth_pct) for one
    ticker, preferring LTM where computable.

    Resolution order:
      LTM growth — needs ≥8 quarters in `<key>__income.parquet`. Sum-of-4Q
        now vs sum-of-4Q one year earlier.
      Quarterly-YoY growth — falls back to Q-now vs same-Q one year ago,
        requires ≥5 quarters. Reported as "LTM" since it's a quarterly
        annualised number.
      Annual growth — most recent annual EBITDA vs prior. Uses
        `<key>__income_annual.parquet` if present, else last two columns of
        the quarterly file as a rough proxy.
    """
    qpath = CACHE / f'{cache_key}__income.parquet'
    apath = CACHE / f'{cache_key}__income_annual.parquet'

    q_series = _ebitda_series_from(qpath)
    a_series = _ebitda_series_from(apath)

    ltm_g = None
    # Full LTM-vs-LTM if we have ≥8 quarters
    if len(q_series) >= 8:
        rolled = q_series.rolling(4).sum().dropna()
        if len(rolled) >= 5:
            now = float(rolled.iloc[-1]); prv = float(rolled.iloc[-5])
            if abs(prv) > 0:
                ltm_g = (now - prv) / abs(prv) * 100
    # Fallback: Q vs same-Q-1Y-ago (the yfinance hard cap is ~5-7 quarters)
    if ltm_g is None and len(q_series) >= 5:
        now = float(q_series.iloc[-1]); prv = float(q_series.iloc[-5])
        if abs(prv) > 0:
            ltm_g = (now - prv) / abs(prv) * 100

    yr_g = None
    if len(a_series) >= 2:
        now = float(a_series.iloc[-1]); prv = float(a_series.iloc[-2])
        if abs(prv) > 0:
            yr_g = (now - prv) / abs(prv) * 100
    elif len(q_series) >= 2:
        now = float(q_series.iloc[-1]); prv = float(q_series.iloc[-2])
        if abs(prv) > 0:
            yr_g = (now - prv) / abs(prv) * 100

    return ltm_g, yr_g


def compute_ratios(df: pd.DataFrame) -> pd.DataFrame:
    """Add ev_ebitda_g, ev_sales_g, *_ltm and *_bv variants. NaN where invalid.

    Bug fix: `ev_ebitda_g` previously used yfinance's `earningsGrowth` field
    as the divisor, which is NET-EARNINGS growth (after-tax, after-interest,
    after non-recurring). PEG-style EV/EBITDA should divide by EBITDA growth.
    Now computes EBITDA growth from the cached quarterly income statement.

    Two new columns appear alongside the original:
      ev_ebitda_over_ebg_ltm = EV/EBITDA ÷ EBITDA-growth-LTM
      ev_ebitda_over_ebg_yr  = EV/EBITDA ÷ EBITDA-growth-annual
    The legacy `ev_ebitda_g` column is retained for back-compat but now also
    uses EBITDA growth (not earnings growth). Earnings-growth-divided version
    is preserved as `ev_ebitda_over_earng` for comparison.

    Financials are EXCLUDED from the PEG-style ratios. Banks/insurers/holdcos
    have economically-meaningless EV/EBITDA (deposits/reserves dwarf market
    cap), no real "sales" (net interest income, premiums), and reserve-
    release-driven earnings volatility. PEG breaks down. Use
    financials_value.py for those.
    """
    df = df.copy()
    # Numeric coercion
    for c in ('marketCap','enterpriseValue','enterpriseToEbitda','enterpriseToRevenue',
              'priceToSalesTrailing12Months','priceToBook',
              'revenueGrowth','earningsGrowth','earningsQuarterlyGrowth'):
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors='coerce')

    # Flag financials sector — yfinance uses "Financial Services" consistently.
    sector = df['sector'].astype(str)
    df['is_financial'] = sector.str.contains('Financial', case=False, na=False)

    # EV/Sales rebuilt from P/S × (EV/MktCap). Currency-neutral.
    ev_over_mc = df['enterpriseValue'] / df['marketCap']
    ev_sales_rebuilt = df['priceToSalesTrailing12Months'] * ev_over_mc
    df['ev_sales'] = ev_sales_rebuilt.where(ev_sales_rebuilt.notna(),
                                             df['enterpriseToRevenue'])
    df['ev_ebitda'] = df['enterpriseToEbitda']

    # Growth %s — fields are decimal (0.10 = 10%); convert to %.
    df['rev_g_pct'] = df['revenueGrowth'] * 100
    df['earn_g_pct'] = df['earningsGrowth'] * 100
    df['earn_g_q_pct'] = df['earningsQuarterlyGrowth'] * 100

    # Compute real EBITDA growth (LTM + annual) from cached quarterly income.
    # Per-ticker loop — keyed off cache_key (the on-disk filename stem).
    if 'cache_key' in df.columns:
        eb_g_ltm, eb_g_yr = [], []
        for k in df['cache_key'].tolist():
            ltm, yr = _load_ebitda_growth(k)
            eb_g_ltm.append(ltm)
            eb_g_yr.append(yr)
        df['ebitda_g_ltm_pct'] = pd.to_numeric(pd.Series(eb_g_ltm, index=df.index), errors='coerce')
        df['ebitda_g_yr_pct']  = pd.to_numeric(pd.Series(eb_g_yr,  index=df.index), errors='coerce')
    else:
        df['ebitda_g_ltm_pct'] = np.nan
        df['ebitda_g_yr_pct']  = np.nan

    def _peg(mult, growth, max_g: float = 150.0):
        """PEG ratio with sensible bounds. Growth above max_g is treated as
        base-effect noise (e.g. EBITDA going from tiny-positive to small-
        positive yields huge percent growth that doesn't sustain). Default
        cap = 150% — beyond that the ratio is meaningless for ranking."""
        m = pd.to_numeric(mult, errors='coerce')
        g = pd.to_numeric(growth, errors='coerce')
        m_valid = (m > 0) & np.isfinite(m)
        # Growth must be positive AND below the noise cap
        g_valid = (g > 0) & (g < max_g) & np.isfinite(g)
        out = m / g
        out = out.where(m_valid & g_valid)
        return out

    # PEG-style ratios — divide by the RIGHT growth rate
    # CORRECT: EV/EBITDA divided by EBITDA growth (LTM preferred, annual fallback)
    df['ev_ebitda_over_ebg_ltm'] = _peg(df['ev_ebitda'], df['ebitda_g_ltm_pct'])
    df['ev_ebitda_over_ebg_yr']  = _peg(df['ev_ebitda'], df['ebitda_g_yr_pct'])
    # Backward-compatible alias — was earnings-growth-divided, now EBITDA-growth-divided
    df['ev_ebitda_g'] = df['ev_ebitda_over_ebg_ltm'].where(
        df['ev_ebitda_over_ebg_ltm'].notna(), df['ev_ebitda_over_ebg_yr'])
    # Legacy comparison column — kept for those who want the old behaviour
    df['ev_ebitda_over_earng'] = _peg(df['ev_ebitda'], df['earn_g_pct'])

    # Sales-growth-divided (these were already correct)
    df['ev_sales_g']       = _peg(df['ev_sales'],  df['rev_g_pct'])
    df['ev_ebitda_g_ltm']  = df['ev_ebitda_over_ebg_ltm']  # rename-alias for old code
    df['ev_sales_g_ltm']   = _peg(df['ev_sales'],  df['rev_g_pct'])

    # Suppress PEG ratios for financials — they're not just unusable, they're
    # actively misleading (banks frequently rank top because of accounting
    # quirks around interest income and reserve releases).
    fin = df['is_financial']
    for col in ('ev_ebitda_g','ev_sales_g','ev_ebitda_g_ltm','ev_sales_g_ltm',
                'ev_ebitda_over_ebg_ltm','ev_ebitda_over_ebg_yr','ev_ebitda_over_earng'):
        df.loc[fin, col] = np.nan

    # Book-value tilt — diminishing, bounded ±20% — applied per row
    tilt = df['priceToBook'].apply(lambda x: bv_tilt(x))
    df['_bv_tilt'] = tilt
    df['ev_ebitda_g_bv']     = df['ev_ebitda_g'] * tilt
    df['ev_sales_g_bv']      = df['ev_sales_g']  * tilt
    df['ev_ebitda_g_ltm_bv'] = df['ev_ebitda_g_ltm'] * tilt
    df['ev_sales_g_ltm_bv']  = df['ev_sales_g_ltm']  * tilt

    return df


def display_top(df: pd.DataFrame, sort_col: str, n: int, label: str):
    sub = df.dropna(subset=[sort_col]).sort_values(sort_col).head(n)
    if sub.empty:
        print(f'  (no rows for {label})'); return
    cols = ['ticker','region','longName','sector','marketCap_M', sort_col,
            'priceToBook','ev_ebitda','ev_sales','rev_g_pct','earn_g_pct','earn_g_q_pct',
            '_bv_tilt']
    cols = [c for c in cols if c in sub.columns]
    out = sub[cols].copy()
    for c in out.columns:
        if c not in ('ticker','region','longName','sector'):
            out[c] = pd.to_numeric(out[c], errors='coerce').round(3)
    out['longName'] = out['longName'].astype(str).str.slice(0, 28)
    print(f'\n=== {label} (top {len(out)}) ===')
    print(out.to_string(index=False))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--min-mcap', type=float, default=50e6)
    ap.add_argument('--top-n', type=int, default=30)
    args = ap.parse_args()

    print(f'Loading cache (mcap floor ${args.min_mcap/1e6:.0f}M)...')
    df = load_all_info(args.min_mcap)
    print(f'  loaded {len(df)} rows after mcap filter')
    df['marketCap_M'] = df['marketCap'] / 1e6

    df = compute_ratios(df)

    # Summary of how many scored on each ratio
    print(f'\nRatio coverage:')
    for c in ('ev_ebitda_g','ev_sales_g','ev_ebitda_g_ltm','ev_sales_g_ltm'):
        n = df[c].notna().sum()
        print(f'  {c}: {n}/{len(df)} rows')

    # Persist all
    df.to_csv(OUT / 'growth_adj_value.csv', index=False)
    print(f'\nWrote {OUT/"growth_adj_value.csv"} ({len(df)} rows)')

    # Display GLOBAL top by each ratio
    display_top(df, 'ev_ebitda_g_bv',     args.top_n, 'cheapest by EV/EBITDA/g (annual, BV-tilted)')
    display_top(df, 'ev_sales_g_bv',      args.top_n, 'cheapest by EV/Sales/g (annual, BV-tilted)')
    display_top(df, 'ev_ebitda_g_ltm_bv', args.top_n, 'cheapest by EV/EBITDA/g (LTM, BV-tilted)')
    display_top(df, 'ev_sales_g_ltm_bv',  args.top_n, 'cheapest by EV/Sales/g (LTM, BV-tilted)')

    # Durable-growth cut: filter out merger/low-base spike artifacts by
    # requiring growth in the 10-100% band (so we don't reward +20,000% rebounds).
    # This is the view the user explicitly asked for: "EQT, GTM, Chow Sang Sang,
    # TaskUs screen genuinely cheap-per-growth" are all in this 10-100% range.
    print('\n\n' + '=' * 80)
    print('DURABLE-GROWTH CUT  (filter: 10% ≤ growth ≤ 100% — excludes rebound/merger spikes)')
    print('=' * 80)
    dur = df[
        (df['earn_g_pct'].between(10, 100, inclusive='both')) |
        (df['earn_g_pct'].isna() & df['rev_g_pct'].between(10, 100, inclusive='both'))
    ].copy()
    rev_dur = df[df['rev_g_pct'].between(10, 100, inclusive='both')].copy()
    display_top(dur, 'ev_ebitda_g_bv',     args.top_n, 'durable-growth: cheapest EV/EBITDA/g (annual)')
    display_top(rev_dur, 'ev_sales_g_bv',  args.top_n, 'durable-growth: cheapest EV/Sales/g (annual)')

    # Per-region cut of the primary metric (durable growth, EV/EBITDA/g_bv)
    print('\n\n========= Per-region DURABLE-GROWTH cheapest on EV/EBITDA/g (BV-tilted) =========')
    for region in ['US','JP','KR','HK','AU','CA','GB','DE','FR','SE']:
        sub = dur[dur.region == region]
        display_top(sub, 'ev_ebitda_g_bv', 5, f'{region} durable-growth cheapest')

    # Top file
    pri = df.dropna(subset=['ev_ebitda_g_bv']).sort_values('ev_ebitda_g_bv').head(args.top_n*4)
    pri.to_csv(OUT / 'growth_adj_value_top.csv', index=False)
    print(f'\nWrote {OUT/"growth_adj_value_top.csv"} ({len(pri)} rows)')


if __name__ == '__main__':
    main()
