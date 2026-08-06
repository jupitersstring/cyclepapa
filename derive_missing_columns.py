"""Derive missing columns in asymmetry_global.csv from existing inputs.

The master CSV is rich for some columns and sparse for others. Several
useful columns are pure functions of fields that ARE present in the
master (market_cap, revenue_ttm, ev_sales, etc.) or are present in
edgar_universe_facts.csv (opinc_ttm, pretax_income_ttm, netinc_ttm).

This script computes derived columns where ALL inputs are present
without overwriting existing non-null values. It is idempotent.

Derived columns:
    ev_ebit          = enterprise_value / opinc_ttm
    cash_pct_mcap    = cash / market_cap
    cash_pct_ev      = cash / enterprise_value
    net_cash         = cash - total_debt
    net_cash_pct_mcap = net_cash / market_cap
    fcf_per_share    = fcf_ttm / shares_outstanding
    eps_diluted_ttm  = netinc_ttm / shares_outstanding
    pretax_margin    = pretax_income_ttm / revenue_ttm
    asset_turnover   = revenue_ttm / assets
    ev_revenue       = enterprise_value / revenue_ttm  (alias of ev_sales)

Sign / sanity rules:
  - Ratios where a positive value is meaningful (margins, turnover,
    cash%) require positive numerator inputs and positive
    market_cap / enterprise_value denominators.
  - net_cash and net_cash_pct_mcap accept any sign (a debt-laden firm
    has negative net cash -- that's the whole point of the signal).
  - eps_diluted_ttm accepts any sign (net income can be negative).
  - All results must be finite.

Enterprise value derivation (the master doesn't carry EV directly):
  Try in order, take first non-null positive result:
    1. ev_sales * revenue_ttm
    2. ev_ebitda * ebitda_ttm  (only when ebitda_ttm > 0)
    3. market_cap + total_debt - cash
"""
from __future__ import annotations

import argparse
import sys

import numpy as np
import pandas as pd


# Derived columns we produce. Order matters: enterprise_value first
# (others depend on it).
DERIVED_COLUMNS = [
    'enterprise_value',
    'ev_ebit',
    'cash_pct_mcap',
    'cash_pct_ev',
    'net_cash',
    'net_cash_pct_mcap',
    'fcf_per_share',
    'eps_diluted_ttm',
    'pretax_margin',
    'asset_turnover',
    'ev_revenue',
    'pegy',
    'ev_ebitda_gy',
]


def _to_num(s: pd.Series) -> pd.Series:
    """Coerce a column to numeric; non-parseable -> NaN."""
    return pd.to_numeric(s, errors='coerce')


def _safe_div(num: pd.Series, den: pd.Series,
              den_must_be_positive: bool = True) -> pd.Series:
    """Element-wise num/den that returns NaN when either input is NaN
    or den is zero / non-positive (when required) / non-finite."""
    den_ok = den.notna() & np.isfinite(den)
    if den_must_be_positive:
        den_ok &= (den > 0)
    else:
        den_ok &= (den != 0)
    num_ok = num.notna() & np.isfinite(num)
    out = pd.Series(np.nan, index=num.index, dtype='float64')
    mask = den_ok & num_ok
    out.loc[mask] = num.loc[mask] / den.loc[mask]
    out = out.replace([np.inf, -np.inf], np.nan)
    return out


def load_edgar_facts(path: str) -> pd.DataFrame:
    """Load the edgar fact table, keep just the income-statement fields
    we need to backfill derived inputs. Indexed by symbol."""
    keep = [
        'symbol', 'opinc_ttm', 'pretax_income_ttm', 'netinc_ttm',
        'revenue_ttm', 'cash', 'total_debt', 'shares_outstanding',
        'fcf_ttm', 'assets', 'eps_diluted_ttm',
    ]
    try:
        ed = pd.read_csv(path, usecols=lambda c: c in keep, low_memory=False)
    except FileNotFoundError:
        return pd.DataFrame()
    if 'symbol' not in ed.columns:
        return pd.DataFrame()
    # In case of dup symbols, prefer the row with the most non-null
    ed['_n'] = ed.notna().sum(axis=1)
    ed = (ed.sort_values(['symbol', '_n'], ascending=[True, False])
            .drop_duplicates('symbol', keep='first')
            .drop(columns=['_n']))
    return ed.set_index('symbol')


def derive_enterprise_value(master: pd.DataFrame) -> pd.Series:
    """Back out EV using whatever inputs we have, preferring already-priced
    ratios over reconstructing from the balance sheet. Returns a float
    series aligned with master.index. NaN where no path produces a value."""
    def _g(col):
        return _to_num(master.get(col, pd.Series(np.nan, index=master.index)))

    mcap = _g('market_cap')
    rev = _g('revenue_ttm')
    ebitda = _g('ebitda_ttm')
    cash = _g('cash')
    debt = _g('total_debt')
    ev_sales = _g('ev_sales')
    ev_ebitda = _g('ev_ebitda')

    # Path 1: ev_sales * revenue_ttm (most common and best signal)
    ev = ev_sales * rev
    ev = ev.where(np.isfinite(ev) & (ev > 0))

    # Path 2: ev_ebitda * ebitda_ttm -- only useful when ebitda_ttm > 0
    ev2 = ev_ebitda * ebitda
    ev2 = ev2.where(np.isfinite(ev2) & (ev2 > 0) & (ebitda > 0))
    ev = ev.where(ev.notna(), ev2)

    # Path 3: balance-sheet reconstruction. Requires mcap.
    ev3 = mcap + debt.fillna(0) - cash.fillna(0)
    ev3 = ev3.where(mcap.notna() & (mcap > 0))
    ev3 = ev3.where(np.isfinite(ev3) & (ev3 > 0))
    ev = ev.where(ev.notna(), ev3)

    return ev


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--in', dest='in_path', default='asymmetry_global.csv')
    ap.add_argument('--out', default=None,
                    help='write to this path (default: overwrite in-place)')
    ap.add_argument('--edgar', default='edgar_universe_facts.csv',
                    help='source for opinc_ttm / pretax_income_ttm / netinc_ttm')
    args = ap.parse_args()
    out_path = args.out or args.in_path

    print(f'loading master {args.in_path}...', file=sys.stderr)
    master = pd.read_csv(args.in_path, low_memory=False)
    n_rows = len(master)
    print(f'  {n_rows:,} rows, {len(master.columns)} cols', file=sys.stderr)

    # Coerce numeric inputs we will touch
    for c in ['market_cap', 'revenue_ttm', 'cash', 'total_debt',
              'shares_outstanding', 'fcf_ttm', 'assets', 'ev_sales',
              'ev_ebitda', 'ebitda_ttm']:
        if c in master.columns:
            master[c] = _to_num(master[c])

    # Pull income-statement fields from edgar (US tickers, mostly)
    print(f'loading edgar facts {args.edgar}...', file=sys.stderr)
    edgar = load_edgar_facts(args.edgar)
    if len(edgar):
        print(f'  {len(edgar):,} symbols from edgar', file=sys.stderr)
        master = master.set_index('symbol')
        # Bring opinc/pretax/netinc in as helper columns (we drop them
        # at the end -- they're not master-CSV citizens).
        for col in ['opinc_ttm', 'pretax_income_ttm', 'netinc_ttm']:
            if col in edgar.columns:
                master[f'_e_{col}'] = edgar[col].reindex(master.index)
        # Backfill (fill-only, never overwrite) structural fields from
        # edgar so we get derivations on more rows.
        for col in ['cash', 'total_debt', 'shares_outstanding',
                    'fcf_ttm', 'assets', 'revenue_ttm', 'eps_diluted_ttm']:
            if col in edgar.columns:
                edgar_col = edgar[col].reindex(master.index)
                if col in master.columns:
                    fill_mask = master[col].isna() & edgar_col.notna()
                    master.loc[fill_mask, col] = edgar_col.loc[fill_mask]
                else:
                    master[col] = edgar_col
        master = master.reset_index()
    else:
        print('  (no edgar data found -- derivations that need edgar income '
              'statement will be NaN for those rows)', file=sys.stderr)

    # Re-coerce after the fill
    for c in ['market_cap', 'revenue_ttm', 'cash', 'total_debt',
              'shares_outstanding', 'fcf_ttm', 'assets',
              'eps_diluted_ttm', 'ebitda_ttm',
              '_e_opinc_ttm', '_e_pretax_income_ttm', '_e_netinc_ttm']:
        if c in master.columns:
            master[c] = _to_num(master[c])

    # Pre-derivation coverage snapshot
    coverage_before = {}
    for c in DERIVED_COLUMNS:
        coverage_before[c] = int(master[c].notna().sum()) if c in master.columns else 0

    # 1) enterprise_value -- needed by ev_ebit / cash_pct_ev / ev_revenue.
    ev_derived = derive_enterprise_value(master)
    if 'enterprise_value' in master.columns:
        ev_existing = _to_num(master['enterprise_value'])
        ev_use = ev_existing.where(ev_existing.notna(), ev_derived)
        master['enterprise_value'] = ev_use
    else:
        master['enterprise_value'] = ev_derived
        ev_use = ev_derived

    # Input series (NaN-safe)
    def _s(col):
        return master[col] if col in master.columns else pd.Series(np.nan, index=master.index)

    mcap = _to_num(_s('market_cap'))
    rev = _to_num(_s('revenue_ttm'))
    cash = _to_num(_s('cash'))
    debt = _to_num(_s('total_debt'))
    sh = _to_num(_s('shares_outstanding'))
    fcf = _to_num(_s('fcf_ttm'))
    assets = _to_num(_s('assets'))
    opinc = _to_num(_s('_e_opinc_ttm'))
    pretax = _to_num(_s('_e_pretax_income_ttm'))
    netinc = _to_num(_s('_e_netinc_ttm'))
    ev = _to_num(ev_use)

    # Counter for how many cells we add (any column, any row)
    fillable_columns_added = 0

    def _fill(col_name: str, computed: pd.Series) -> int:
        """Write computed values only into rows where master[col_name]
        is currently null. Returns count of newly-filled cells."""
        nonlocal fillable_columns_added
        if col_name not in master.columns:
            master[col_name] = np.nan
        existing = _to_num(master[col_name])
        # Strict idempotence: do not overwrite existing non-null
        fill_mask = existing.isna() & computed.notna() & np.isfinite(computed)
        n_filled = int(fill_mask.sum())
        if n_filled:
            master.loc[fill_mask, col_name] = computed.loc[fill_mask]
        fillable_columns_added += n_filled
        return n_filled

    # 2) ev_ebit -- opinc must be > 0
    _fill('ev_ebit', _safe_div(ev, opinc, den_must_be_positive=True))

    # 3) cash_pct_mcap -- cash >= 0, mcap > 0
    cash_pos = cash.where(cash.notna() & (cash >= 0))
    _fill('cash_pct_mcap', _safe_div(cash_pos, mcap))

    # 4) cash_pct_ev -- cash >= 0, ev > 0
    _fill('cash_pct_ev', _safe_div(cash_pos, ev))

    # 5) net_cash -- both sides present; any sign OK
    net_cash = cash - debt
    net_cash = net_cash.where(cash.notna() & debt.notna() & np.isfinite(net_cash))
    _fill('net_cash', net_cash)

    # 6) net_cash_pct_mcap -- any sign OK on numerator, mcap > 0
    _fill('net_cash_pct_mcap', _safe_div(net_cash, mcap, den_must_be_positive=True))

    # 7) fcf_per_share -- any sign on fcf, shares > 0
    _fill('fcf_per_share', _safe_div(fcf, sh, den_must_be_positive=True))

    # 8) eps_diluted_ttm -- only when not already present (any sign)
    _fill('eps_diluted_ttm', _safe_div(netinc, sh, den_must_be_positive=True))

    # 9) pretax_margin -- pretax may be negative, revenue must be > 0
    _fill('pretax_margin', _safe_div(pretax, rev, den_must_be_positive=True))

    # 10) asset_turnover -- both > 0
    rev_pos = rev.where(rev.notna() & (rev > 0))
    _fill('asset_turnover', _safe_div(rev_pos, assets, den_must_be_positive=True))

    # 11) ev_revenue -- EV > 0, revenue > 0 (alias of ev_sales)
    _fill('ev_revenue', _safe_div(ev, rev, den_must_be_positive=True))

    # 12+13) Lynch multiples (recomputed every run, not gap-filled, so they
    # track the freshest growth/yield inputs).
    #   pegy         = P/E / (earnings growth% + dividend yield%)   (Lynch PEGY)
    #   ev_ebitda_gy = EV/EBITDA / (EBITDA growth% + dividend yield%)
    # Lynch's convention expresses growth+yield in percentage points (PE 15 on
    # 15% growth -> PEG 1.0). Inputs here are fractions, hence the x100.
    # Growth is capped at 100% so a one-off doubling can't manufacture a
    # sub-0.1 multiple; negative/zero denominators -> NaN (not meaningful).
    pe_v = _to_num(_s('p_e'))
    ev_eb_v = _to_num(_s('ev_ebitda'))
    egrow = _to_num(_s('yf_earnings_growth')).clip(upper=1.0)
    ebgrow = _to_num(_s('ebitda_yoy')).clip(upper=1.0)
    divy = _to_num(_s('dividend_yield')).fillna(0.0).clip(lower=0.0, upper=0.25)
    pe_pos = pe_v.where(pe_v > 0)
    ev_eb_pos = ev_eb_v.where(ev_eb_v > 0)
    master['pegy'] = _safe_div(pe_pos, (egrow + divy) * 100.0,
                               den_must_be_positive=True)
    master['ev_ebitda_gy'] = _safe_div(ev_eb_pos, (ebgrow + divy) * 100.0,
                                       den_must_be_positive=True)

    # Drop helper edgar columns (don't pollute the master)
    drop_cols = [c for c in master.columns if c.startswith('_e_')]
    if drop_cols:
        master = master.drop(columns=drop_cols)

    # Post-derivation coverage
    coverage_after = {c: int(master[c].notna().sum()) for c in DERIVED_COLUMNS
                      if c in master.columns}

    master.to_csv(out_path, index=False)
    print(f'\nwrote {out_path}: {len(master):,} rows, '
          f'{len(master.columns)} cols', file=sys.stderr)

    # Report
    print(f'\nfillable_columns_added (total cells filled): '
          f'{fillable_columns_added:,}', file=sys.stderr)
    print(f'\nCoverage delta per column (before -> after, +new):',
          file=sys.stderr)
    n_total = len(master)
    rows = []
    for c in DERIVED_COLUMNS:
        b = coverage_before.get(c, 0)
        a = coverage_after.get(c, 0)
        rows.append((c, b, a, a - b))
    rows.sort(key=lambda r: -r[3])
    for c, b, a, d in rows:
        pct = (100 * a / n_total) if n_total else 0
        print(f"  {c:22s}  {b:6,} -> {a:6,}  (+{d:6,})  {pct:5.1f}%",
              file=sys.stderr)


if __name__ == '__main__':
    main()
