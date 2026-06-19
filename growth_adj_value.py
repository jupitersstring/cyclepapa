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


# Region suffix → display label
SUFFIX_REGION = {
    '': 'US', '.T': 'JP', '.KS': 'KR', '.KQ': 'KR', '.HK': 'HK',
    '.AX': 'AU', '.TO': 'CA', '.V': 'CA', '.L': 'GB', '.DE': 'DE',
    '.F': 'DE', '.PA': 'FR', '.ST': 'SE',
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
            if ('.' + tail) in {'.T','.KS','.KQ','.HK','.AX','.TO','.V','.L','.DE','.F','.PA','.ST'}:
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


def compute_ratios(df: pd.DataFrame) -> pd.DataFrame:
    """Add ev_ebitda_g, ev_sales_g, *_ltm and *_bv variants. NaN where invalid."""
    df = df.copy()
    # Numeric coercion
    for c in ('marketCap','enterpriseValue','enterpriseToEbitda','enterpriseToRevenue',
              'priceToSalesTrailing12Months','priceToBook',
              'revenueGrowth','earningsGrowth','earningsQuarterlyGrowth'):
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors='coerce')

    # EV/Sales rebuilt from P/S × (EV/MktCap). Currency-neutral.
    # If enterpriseToRevenue is present it's already this number, but it's been
    # observed to come back garbled for some non-US filers; rebuild as a check.
    ev_over_mc = df['enterpriseValue'] / df['marketCap']
    ev_sales_rebuilt = df['priceToSalesTrailing12Months'] * ev_over_mc
    # Where both available, prefer the rebuilt (avoids currency mix in raw EV/Sales)
    df['ev_sales'] = ev_sales_rebuilt.where(ev_sales_rebuilt.notna(),
                                             df['enterpriseToRevenue'])
    df['ev_ebitda'] = df['enterpriseToEbitda']

    # Growth %s — fields are decimal (0.10 = 10%); convert to %.
    df['rev_g_pct'] = df['revenueGrowth'] * 100
    df['earn_g_pct'] = df['earningsGrowth'] * 100
    df['earn_g_q_pct'] = df['earningsQuarterlyGrowth'] * 100

    def _peg(mult, growth):
        m = pd.to_numeric(mult, errors='coerce')
        g = pd.to_numeric(growth, errors='coerce')
        m_valid = (m > 0) & np.isfinite(m)
        g_valid = (g > 0) & np.isfinite(g)
        out = m / g
        out = out.where(m_valid & g_valid)
        return out

    df['ev_ebitda_g']      = _peg(df['ev_ebitda'], df['earn_g_pct'])
    df['ev_sales_g']       = _peg(df['ev_sales'],  df['rev_g_pct'])
    df['ev_ebitda_g_ltm']  = _peg(df['ev_ebitda'], df['earn_g_q_pct'])
    df['ev_sales_g_ltm']   = _peg(df['ev_sales'],  df['rev_g_pct'])  # same: no LTM rev g scalar

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
