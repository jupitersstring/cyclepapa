"""Rescore yartseva_score in existing per-country *_yartseva.csv files.

After amending yartseva_db.py's composite to align with the Anna Yartseva
CAFE WP 33 (2025) paper, we want to refresh the score column on the
~100+ per-country CSVs already on disk without re-fetching yfinance for
every name (which would take hours).

This script re-reads each per-country CSV, recomputes:
  - yartseva_score (new Yartseva-aligned weights)
  - inflection_flag (aggregate column - 1 if any inflection signal fires)

and writes the file back in place. All other columns are left untouched.

After this runs, the asymmetry_global rebuild + alta_fox_score re-run +
country-workbook + Harvard workbook will all pick up the new scores
through the normal pipeline.
"""
from __future__ import annotations
import argparse
import glob
import sys

import numpy as np
import pandas as pd


def clip01(x):
    if pd.isna(x):
        return np.nan
    return float(max(0.0, min(1.0, x)))


def compute_yartseva_score(row: pd.Series) -> float:
    """Recompute yartseva_score per the new (Yartseva-paper-aligned) weights.

    Uses columns already present in the per-country CSVs:
      fcf_yield, pb, enterprise_value / market_cap,
      ebitda_margin, roce, rev_yoy, ebitda_yoy, momentum_12m
    Falls back gracefully when fields are missing - the per-component
    contribution drops out and the remaining weights are renormalised.
    """
    # 1. FCF yield - Yartseva's #1 factor (regression coeffs 46-82). Score
    #    0 at 0% FCF yield, 1.0 at 12%.
    fy = row.get('fcf_yield')
    fcf_yield_score = clip01(fy / 0.12) if pd.notna(fy) else np.nan

    # 2. Book-to-market = 1/PB. Score 0 at B/M=0.20, 1.0 at B/M=1.0+.
    #    Negative equity (PB<=0) -> NaN (she finds neg-equity firms
    #    underperform -7% to -18% annually; we exclude them from this
    #    factor entirely so they're scored only on what's defensible).
    pb = row.get('pb')
    if pd.notna(pb) and pb > 0:
        b_to_m = 1.0 / pb
        book_to_market_score = clip01((b_to_m - 0.20) / 0.80)
    else:
        book_to_market_score = np.nan

    # 3. Small size. EV < $250M (her median was $348M) scores 1.0;
    #    ramps to 0 by $5B. Falls back to market_cap when EV missing.
    ev = row.get('enterprise_value')
    if pd.notna(ev) and ev > 0:
        ev_m = ev / 1e6
        if ev_m < 250:
            size_score = 1.0
        elif ev_m < 5000:
            size_score = max(0.0, (5000 - ev_m) / (5000 - 250))
        else:
            size_score = 0.0
    else:
        mc = row.get('market_cap')
        if pd.notna(mc) and mc > 0:
            mc_m = mc / 1e6
            if mc_m < 250:
                size_score = 1.0
            elif mc_m < 5000:
                size_score = max(0.0, (5000 - mc_m) / (5000 - 250))
            else:
                size_score = 0.0
        else:
            size_score = np.nan

    # 4. Profitability LEVEL - mean of EBITDA margin score and ROCE
    #    score. She finds modest positive margins suffice; the level
    #    matters, not expansion.
    em = row.get('ebitda_margin')
    em_score = clip01((em + 0.05) / 0.20) if pd.notna(em) else np.nan
    rc = row.get('roce')
    roce_lvl_score = clip01(rc / 0.15) if pd.notna(rc) else np.nan
    profit_parts = [s for s in (em_score, roce_lvl_score) if pd.notna(s)]
    profit_level_score = float(np.mean(profit_parts)) if profit_parts else np.nan

    # 5. Asset-growth-gate proxy. We don't have asset_growth in existing
    #    CSVs; proxy with sales_yoy <= ebitda_yoy (same spirit:
    #    operational expansion not diluting earnings). Healthy when
    #    EBITDA growth >= sales growth.
    ry = row.get('rev_yoy')
    ey = row.get('ebitda_yoy')
    if pd.notna(ry) and pd.notna(ey):
        spread = ey - ry
        asset_growth_gate_score = clip01((spread + 0.10) / 0.20)
    else:
        asset_growth_gate_score = np.nan

    # 6. Contra-momentum. Near-52w-low / negative 3-6m momentum is her
    #    signal #6. We proxy with negative 12m momentum (column we have).
    #    1.0 at -30% momentum, 0.5 at 0%, 0 at +30%+.
    mm = row.get('momentum_12m')
    if pd.notna(mm):
        contra_momentum_score = clip01((0.30 - mm) / 0.60)
    else:
        contra_momentum_score = np.nan

    weights = {
        'fcf_yield':            0.30,
        'book_to_market':       0.15,
        'size':                 0.10,
        'profit_level':         0.15,
        'asset_growth_gate':    0.15,
        'contra_momentum':      0.15,
    }
    parts = {
        'fcf_yield':            fcf_yield_score,
        'book_to_market':       book_to_market_score,
        'size':                 size_score,
        'profit_level':         profit_level_score,
        'asset_growth_gate':    asset_growth_gate_score,
        'contra_momentum':      contra_momentum_score,
    }
    total_w = 0.0
    total_v = 0.0
    for k, v in parts.items():
        if pd.notna(v):
            total_w += weights[k]
            total_v += weights[k] * v
    return (total_v / total_w) if total_w > 0 else np.nan


def compute_inflection_flag(row: pd.Series) -> int:
    """1 if any inflection / first-positive / ROCE-inflection signal fires."""
    fields = [
        'rev_inflection', 'ebitda_inflection', 'cfo_inflection', 'fcf_inflection',
        'ebitda_first_positive', 'cfo_first_positive', 'fcf_first_positive',
        'net_income_first_positive',
        'roce_inflection', 'roce_first_positive',
    ]
    for f in fields:
        v = row.get(f)
        if pd.notna(v) and int(v) == 1:
            return 1
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--glob', default='*_yartseva.csv',
                    help='glob pattern for per-country CSVs to rescore')
    ap.add_argument('--dry-run', action='store_true',
                    help='print what would change without writing')
    args = ap.parse_args()

    paths = sorted(set(glob.glob(args.glob)))
    if not paths:
        print(f'no files match {args.glob!r}', file=sys.stderr)
        sys.exit(1)

    total_rows = 0
    changed = 0
    for p in paths:
        try:
            df = pd.read_csv(p)
        except Exception as e:
            print(f'{p}: read failed - {e}', file=sys.stderr)
            continue

        if 'yartseva_score' not in df.columns:
            print(f'{p}: no yartseva_score column, skipping', file=sys.stderr)
            continue

        old_score = df['yartseva_score'].copy()

        # Recompute scores
        df['yartseva_score'] = df.apply(compute_yartseva_score, axis=1).round(6)

        # Add inflection_flag if not already present, or refresh from row signals
        df['inflection_flag'] = df.apply(compute_inflection_flag, axis=1).astype(int)

        # Diagnostics
        n = len(df)
        n_changed = int((old_score.fillna(-999) != df['yartseva_score'].fillna(-999)).sum())
        n_inflect = int(df['inflection_flag'].sum())
        total_rows += n
        changed += n_changed

        if args.dry_run:
            print(f'{p:50s}  {n:6d} rows  {n_changed:6d} would change  '
                  f'{n_inflect:5d} inflection_flag=1', file=sys.stderr)
        else:
            df.to_csv(p, index=False)
            print(f'{p:50s}  {n:6d} rows  {n_changed:6d} rescored      '
                  f'{n_inflect:5d} inflection_flag=1', file=sys.stderr)

    print(f'\ndone: {total_rows:,} total rows, {changed:,} rescored '
          f'across {len(paths)} files', file=sys.stderr)


if __name__ == '__main__':
    main()
