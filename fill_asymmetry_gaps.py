"""Fill valuation / financials gaps in asymmetry_global.csv from
per-country *_yartseva.csv sources.

The master CSV (asymmetry_global.csv) is built by asymmetry_rank.py
from a sparse set of fields. Downstream workbook builders re-glob
the per-country yartseva CSVs to fill in valuation ratios (EV/EBITDA,
P/E, FCF yield, ROIC, ND/EBITDA, EBITDA margin, momentum) — but that
means every consumer pays the merge cost, and any consumer that
doesn't do it ends up with empty columns.

This script does the merge once and writes the result back to
asymmetry_global.csv, so the master is rich and every consumer
(workbooks, screens, the agent) sees the same data.

Priority on conflict: existing non-null value in asymmetry_global wins.
Per-country yartseva files only fill gaps, never overwrite.
"""
from __future__ import annotations
import argparse
import glob
import sys

import pandas as pd


# Columns we want to fill in the master CSV (if not already present
# or if currently NaN for a given symbol).
FILL_COLUMNS = [
    # Valuation
    'price', 'ev_ebitda', 'ev_ebit', 'ev_sales', 'p_e', 'pb', 'p_tb',
    'p_s', 'p_ocf',
    'fcf_yield', 'roce', 'roic_after_sbc',
    'capital_return_yield', 'dividend_yield', 'buyback_yield',
    'market_cap', 'enterprise_value',
    # Margins / quality
    'ebitda_margin', 'op_margin', 'net_margin', 'fcf_margin', 'gross_margin',
    'net_debt_ebitda', 'cash_conversion', 'interest_coverage',
    'debt_to_equity',
    # Levels (TTM and balance sheet)
    'revenue_ttm', 'ebitda_ttm', 'cfo_ttm', 'fcf_ttm',
    'gross_profit_ttm', 'gross_profit_to_mcap',
    'equity', 'assets', 'cash', 'total_debt', 'tangible_equity',
    'goodwill', 'intangibles', 'shares_outstanding',
    # Ownership / sell-side
    'insider_ownership_pct',
    'analyst_target_mean', 'analyst_target_upside_pct',
    # Momentum / 52w
    'momentum_12m', 'pct_off_52w_high', 'price_52w_high',
    # Cap allocation
    'sbc_pct_revenue', 'effective_tax_rate',
    # Inflections / multi-year growth
    'rev_yoy', 'ebitda_yoy', 'fcf_yoy', 'cfo_yoy',
    'rev_accel', 'ebitda_accel', 'cfo_accel', 'fcf_accel',
    'rev_qoq_ttm', 'ebitda_qoq_ttm', 'cfo_qoq_ttm', 'fcf_qoq_ttm',
    'rev_seq', 'ebitda_seq', 'cfo_seq', 'fcf_seq',
    'ebitda_margin_delta_yoy', 'fcf_margin_delta_yoy',
    'rev_inflection', 'ebitda_inflection', 'cfo_inflection',
    'fcf_inflection', 'roce_inflection',
    'ebitda_first_positive', 'cfo_first_positive',
    'fcf_first_positive', 'net_income_first_positive',
    'roce_first_positive',
    'roce_prev', 'roce_delta_yoy',
    # ETA-to-positive (quarters/years until inflection)
    'fcf_run_rate_delta',
    'fcf_eta_quarters', 'fcf_eta_years',
    'ebitda_eta_years', 'cfo_eta_years', 'ni_eta_years',
    'fcf_projected_positive_in_n',
    # Price-vs-fundamentals divergence
    'price_yoy', 'price_minus_rev_yoy', 'price_minus_ebitda_yoy',
    'price_minus_fcf_yoy', 'ev_sales_change_yoy',
    # Cash-vs-EV signals
    'net_cash', 'cash_pct_mcap',
    'ncav', 'mcap_to_ncav',
    'net_cash_pct_mcap', 'cash_pct_ev', 'ncav_pct_mcap',
    'cash_gt_ev_flag', 'graham_net_net_flag',
    # Composite quality / cheapness / inflection scores
    'not_priced_in_score',
    'berezin_classic_flag', 'berezin_score',
    'cheapness_growth_blend', 'cheapness_ev_ebit_vs_growth',
    'cheapness_under_7x_flag', 'cheapness_blend_vs_growth',
    'yartseva_score',
    'inflection_flag', 'inflection_score',
    # Tier-B: extra operating-leverage angles, share-count trajectory,
    # normalized (mid-cycle) earnings
    'gross_profit_yoy', 'gross_margin_delta_yoy', 'op_margin_delta_yoy',
    'ebit_growth_yoy', 'shares_yoy', 'shares_3y_cagr', 'fcf_per_share_yoy',
    'net_buyback_ttm', 'normalized_ebitda', 'normalized_ebit', 'normalized_revenue',
    'earnings_beat_rate', 'avg_earnings_surprise', 'earnings_beat_streak',
    'earnings_surprise_inflecting', 'price_vs_5y_avg', 'price_pct_of_5y_range',
]


def load_yartseva_union():
    """Concat every per-country yartseva CSV. Drop dupes by symbol,
    preferring rows with the most non-null values."""
    frames = []
    for f in sorted(glob.glob('*_yartseva.csv')):
        if f == 'us_edgar_yartseva.csv':
            # us_edgar is already richer; include but keep first if dup
            pass
        try:
            keep = ['symbol'] + FILL_COLUMNS
            d = pd.read_csv(f, usecols=lambda c: c in keep)
        except Exception:
            continue
        if 'symbol' in d.columns:
            frames.append(d)
    if not frames:
        return pd.DataFrame(columns=['symbol'] + FILL_COLUMNS)
    df = pd.concat(frames, ignore_index=True)
    # Rank by "row richness" so the most-populated row wins per symbol
    df['_n_nonnull'] = df.notna().sum(axis=1)
    df = (df.sort_values(['symbol', '_n_nonnull'], ascending=[True, False])
            .drop_duplicates('symbol', keep='first')
            .drop(columns=['_n_nonnull']))
    return df


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--in', dest='in_path', default='asymmetry_global.csv')
    ap.add_argument('--out', default=None,
                    help='write enriched master to this path (default: overwrite in-place)')
    args = ap.parse_args()
    out_path = args.out or args.in_path

    print(f'loading master {args.in_path}...', file=sys.stderr)
    master = pd.read_csv(args.in_path)
    print(f'  {len(master):,} rows, {len(master.columns)} cols', file=sys.stderr)

    print('loading per-country yartseva union...', file=sys.stderr)
    yart = load_yartseva_union()
    print(f'  {len(yart):,} symbols with valuation/financials data', file=sys.stderr)

    # Use combine_first semantics: existing master value wins where non-null;
    # yart fills only where master is null.
    yart_idx = yart.set_index('symbol')
    master_idx = master.set_index('symbol')

    # Coverage BEFORE
    coverage_before = {c: master_idx[c].notna().sum() if c in master_idx.columns else 0
                       for c in FILL_COLUMNS}

    for col in FILL_COLUMNS:
        if col not in yart_idx.columns:
            continue
        if col not in master_idx.columns:
            # Brand-new column — add it
            master_idx[col] = yart_idx[col]
        else:
            # Fill where null
            mask = master_idx[col].isna() & master_idx.index.isin(yart_idx.index)
            if mask.any():
                master_idx.loc[mask, col] = yart_idx.loc[
                    master_idx.index[mask].intersection(yart_idx.index), col
                ]

    # Coverage AFTER
    coverage_after = {c: master_idx[c].notna().sum() if c in master_idx.columns else 0
                      for c in FILL_COLUMNS}

    master = master_idx.reset_index()
    master.to_csv(out_path, index=False)
    print(f'\nwrote {out_path}: {len(master):,} rows, {len(master.columns)} cols',
          file=sys.stderr)

    print(f'\nCoverage deltas (before -> after, +delta):', file=sys.stderr)
    n_total = len(master)
    deltas = []
    for c in FILL_COLUMNS:
        b = coverage_before.get(c, 0)
        a = coverage_after.get(c, 0)
        deltas.append((c, b, a, a - b))
    # Sort by delta desc, only show columns that changed
    deltas.sort(key=lambda r: -r[3])
    for c, b, a, d in deltas:
        if d == 0 and b == 0 and a == 0:
            continue
        print(f"  {c:25s}  {b:6,} -> {a:6,}  (+{d:,})  "
              f"{100*a/n_total:.1f}%", file=sys.stderr)


if __name__ == '__main__':
    main()
