"""Post-pass enrichment of asymmetry_global.csv.

After asymmetry_rank.py writes the deduped universe, this script merges
in archetype tags + verdicts + intrinsic-discount inputs and computes
four NEW columns that close the audit #3 gaps:

  entry_today_asymmetry        asymmetry_score x qual_mult x intrinsic_boost
                               x post_rally_factor — verdict-aware ranking so
                               downstream consumers don't surface REDs.

  archetype_count_pct          archetype_count divided by the count of
                               archetypes ELIGIBLE for the row (26 for US-
                               EDGAR-covered names, 9 for non-EDGAR names
                               that can't hit the 17 EDGAR-required tags).
                               Removes the structural US bias in
                               raw archetype_count.

  archetype_asymmetry_score    sqrt(archetype_count_pct x downside_floor) —
                               parallel ranking on archetype density,
                               wiring together the archetype framework and
                               the asymmetry geometric-mean structure.

  mcap_proxy                   market_cap when available, else book equity
                               (then revenue, then assets). Used to scale
                               size-dependent legs for names like MELI
                               whose mcap is missing.

Run after every rebuild of asymmetry_global.csv.
"""
from __future__ import annotations
import argparse
import glob
import os
import sys

import numpy as np
import pandas as pd


EDGAR_REQUIRED_ARCHETYPES = {
    # The 25 archetypes that can only fire when EDGAR multi-year + cap-
    # allocation + segment data is present. Non-EDGAR rows can't
    # structurally match these.
    "arch_durable_reinvestment", "arch_cash_reinvest", "arch_roic_inflect",
    "arch_cheap_per_roiic", "arch_tangible_value",
    "arch_lindy_margin", "arch_lindy_fcf", "arch_no_dilution", "arch_lindy_growth",
    "arch_quiet_compounder", "arch_buyback_compounder", "arch_owner_operator",
    "arch_qarp", "arch_reinvest_inflect", "arch_double_inflect",
    "arch_cash_quality", "arch_capital_light_pivot",
    "arch_capital_returner", "arch_low_sbc_quality",
    "arch_tax_efficient", "arch_strong_coverage",
    # NEW: segment-level archetypes (edgartools dimensional XBRL harvest)
    "arch_diversified_segments", "arch_concentrated_segments",
    "arch_geographic_global", "arch_fastest_segment",
}


def load_verdicts() -> pd.DataFrame:
    frames = []
    for path, default in [
        ('qualitative_aligned_green.csv', 'GREEN'),
        ('qualitative_red_avoid.csv', 'RED'),
        ('qualitative_extended_verdicts.csv', None),
    ]:
        if not os.path.exists(path):
            continue
        try:
            d = pd.read_csv(path)
        except pd.errors.ParserError:
            d = pd.read_csv(path, engine='python', on_bad_lines='skip', quoting=3)
        if 'verdict' not in d.columns and default:
            d['verdict'] = default
        keep = [c for c in ['symbol', 'verdict'] if c in d.columns]
        frames.append(d[keep])
    if not frames:
        return pd.DataFrame(columns=['symbol', 'verdict'])
    return pd.concat(frames, ignore_index=True).drop_duplicates('symbol', keep='last')


def load_intrinsic_inputs() -> pd.DataFrame:
    """Pull net_cash/mcap, NCAV/mcap, cash/EV, not_priced_in from per-country
    yartseva CSVs — same source as the Harvard workbook's intrinsic_discount
    computation, kept consistent here."""
    keep = ['symbol', 'net_cash_pct_mcap', 'ncav_pct_mcap', 'cash_pct_ev',
            'not_priced_in_score']
    frames = []
    for f in sorted(glob.glob('*_yartseva.csv')):
        try:
            d = pd.read_csv(f, usecols=lambda c: c in keep)
        except Exception:
            continue
        if 'symbol' in d.columns:
            frames.append(d)
    if not frames:
        return pd.DataFrame(columns=keep)
    df = pd.concat(frames, ignore_index=True).drop_duplicates('symbol', keep='first')
    return df


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--asym', default='asymmetry_global.csv')
    ap.add_argument('--arch', default='archetype_tags.csv')
    ap.add_argument('--total-archetypes', type=int, default=34)
    args = ap.parse_args()

    print('loading asymmetry_global, archetype_tags, verdicts...', file=sys.stderr)
    df = pd.read_csv(args.asym)
    # Drop stale suffixed columns from prior enrich runs
    df = df.drop(columns=[c for c in df.columns if c.endswith('_arch')])
    arch_df = pd.read_csv(args.arch)
    verdicts = load_verdicts()
    intrinsic_in = load_intrinsic_inputs()

    arch_cols = [c for c in arch_df.columns if c.startswith('arch_')]
    edgar_arch_cols = [c for c in arch_cols if c in EDGAR_REQUIRED_ARCHETYPES]
    non_edgar_arch_cols = [c for c in arch_cols if c not in EDGAR_REQUIRED_ARCHETYPES]
    print(f'  {len(arch_cols)} archetype columns ({len(edgar_arch_cols)} EDGAR-only, '
          f'{len(non_edgar_arch_cols)} universal)', file=sys.stderr)

    df = df.merge(arch_df[['symbol'] + arch_cols + ['archetype_count']],
                  on='symbol', how='left', suffixes=('', '_arch'))
    # Drop any pre-existing verdict so the fresh merge wins
    if 'verdict' in df.columns:
        df = df.drop(columns=['verdict'])
    df = df.merge(verdicts, on='symbol', how='left')
    df['verdict'] = df['verdict'].fillna('UNRESEARCHED')
    mc = ['symbol'] + [c for c in intrinsic_in.columns
                       if c != 'symbol' and c not in df.columns]
    df = df.merge(intrinsic_in[mc], on='symbol', how='left')

    # ----- mcap_proxy (book-equity fallback for ranking) -----
    # Used to scale size-dependent legs when yfinance market_cap is NaN.
    mcap = df['market_cap'].copy() if 'market_cap' in df.columns else pd.Series(np.nan, index=df.index)
    if 'equity' in df.columns:
        mcap = mcap.fillna(df['equity'].clip(lower=0))
    if 'revenue_ttm' in df.columns:
        mcap = mcap.fillna(df['revenue_ttm'].clip(lower=0))
    if 'assets' in df.columns:
        mcap = mcap.fillna(df['assets'].clip(lower=0) * 0.5)
    df['mcap_proxy'] = mcap

    # ----- intrinsic_discount (same formula as Harvard workbook) -----
    def col(c, d=0.0):
        return df[c].fillna(d) if c in df.columns else pd.Series(d, index=df.index)

    def c01(s):
        return s.clip(0, 1).fillna(0)

    nc = c01(col('net_cash_pct_mcap'))
    ncav = c01(col('ncav_pct_mcap'))
    sub_book = c01(1.0 - col('pb', 2.0).clip(lower=0.01))
    cash_ev = c01((col('cash_pct_ev') - 1.0).clip(0, 2) / 2.0)
    npi = c01(col('not_priced_in_score'))
    df['intrinsic_discount'] = (
        0.30 * nc + 0.20 * ncav + 0.20 * sub_book + 0.15 * cash_ev + 0.15 * npi
    ).round(4)
    intrinsic_boost = (1.0 + (df['intrinsic_discount'] - 0.25)).clip(0.5, 1.5)

    # ----- qual_mult + post_rally_factor -----
    soft_mult = {'GREEN': 1.10, 'YELLOW': 0.85, 'RED': 0.40}
    df['qual_mult'] = df['verdict'].map(soft_mult).fillna(1.0)

    mom = col('momentum_12m').clip(-0.5, None)
    pr = pd.Series(1.0, index=df.index)
    mid = (mom > 0.30) & (mom <= 1.0)
    hi = (mom > 1.0) & (mom <= 3.0)
    ex = mom > 3.0
    pr.loc[mid] = 1.0 - (mom[mid] - 0.30) / 0.70 * 0.25
    pr.loc[hi] = 0.75 - (mom[hi] - 1.0) / 2.0 * 0.30
    pr.loc[ex] = 0.40
    df['post_rally_factor'] = pr.round(3)

    # ----- entry_today_asymmetry -----
    df['entry_today_asymmetry'] = (
        df['asymmetry_score'].fillna(0)
        * intrinsic_boost
        * df['qual_mult']
        * df['post_rally_factor']
    ).round(6)

    # ----- archetype_count_pct (region-fair denominator) -----
    # A row is EDGAR-eligible if it has at least one EDGAR-only archetype
    # matching (= EDGAR XBRL was present for this name).
    if edgar_arch_cols:
        has_edgar_data = (df[edgar_arch_cols].fillna(0).sum(axis=1) > 0)
        # Or any row carrying multi-year fields:
        for marker in ('roic_lindy', 'm5_engine_score', 'tangible_equity_pct'):
            if marker in df.columns:
                has_edgar_data = has_edgar_data | df[marker].notna()
        archetypes_eligible = np.where(has_edgar_data, args.total_archetypes,
                                       len(non_edgar_arch_cols))
    else:
        archetypes_eligible = args.total_archetypes
    df['archetypes_eligible'] = archetypes_eligible
    df['archetype_count'] = df['archetype_count'].fillna(0)
    df['archetype_count_pct'] = (df['archetype_count'] / archetypes_eligible).round(4)

    # ----- archetype_asymmetry_score -----
    # Same geometric-mean structure as the existing asymmetry_score, but
    # using archetype density as the upside leg. Wires the archetype
    # framework into a parallel ranking.
    floor = df['downside_floor_score'].fillna(0).clip(0, 1)
    df['archetype_asymmetry_score'] = np.sqrt(
        df['archetype_count_pct'].clip(0, 1) * floor
    ).round(6)

    # Optional: also incorporate qual_mult into the archetype ranking
    df['entry_today_archetype_asymmetry'] = (
        df['archetype_asymmetry_score']
        * df['qual_mult']
        * df['post_rally_factor']
    ).round(6)

    # Reorder columns so the new ones land in a logical place
    new_cols = ['entry_today_asymmetry', 'archetype_count', 'archetype_count_pct',
                'archetypes_eligible', 'archetype_asymmetry_score',
                'entry_today_archetype_asymmetry',
                'mcap_proxy', 'intrinsic_discount', 'qual_mult',
                'post_rally_factor', 'verdict']
    # Drop the per-archetype boolean columns we merged in — they're
    # available via archetype_tags.csv if anyone wants them. Keeps
    # asymmetry_global slim.
    cols_to_drop = [c for c in arch_cols if c in df.columns]
    df = df.drop(columns=cols_to_drop)

    front_existing = [c for c in df.columns if c not in new_cols]
    ordered = front_existing + [c for c in new_cols if c in df.columns]
    df = df[ordered]

    df.to_csv(args.asym, index=False)
    print(f'  wrote enriched {args.asym}: {len(df):,} rows, '
          f'{len(df.columns)} columns', file=sys.stderr)

    # Diagnostics
    print('\nVerdict distribution:')
    print(df['verdict'].value_counts(dropna=False).to_string())
    print(f'\nentry_today_asymmetry distribution:')
    eta = df['entry_today_asymmetry']
    print(f'  mean={eta.mean():.3f}, median={eta.median():.3f}, '
          f'p90={eta.quantile(0.90):.3f}, max={eta.max():.3f}')
    print(f'\narchetype_count_pct distribution (by EDGAR eligibility):')
    edg = df[df['archetypes_eligible'] == args.total_archetypes]
    non = df[df['archetypes_eligible'] != args.total_archetypes]
    if len(edg):
        print(f'  EDGAR-eligible ({len(edg):,}): mean count {edg.archetype_count.mean():.2f}, '
              f'mean pct {edg.archetype_count_pct.mean():.3f}')
    if len(non):
        print(f'  Non-EDGAR    ({len(non):,}): mean count {non.archetype_count.mean():.2f}, '
              f'mean pct {non.archetype_count_pct.mean():.3f}')

    # Top by new score
    print('\nTop 15 by entry_today_archetype_asymmetry:')
    cols_show = ['symbol', 'name', 'src', 'verdict', 'archetype_count',
                 'archetype_count_pct', 'asymmetry_score', 'archetype_asymmetry_score',
                 'entry_today_asymmetry', 'entry_today_archetype_asymmetry']
    cols_show = [c for c in cols_show if c in df.columns]
    print(df.nlargest(15, 'entry_today_archetype_asymmetry')[cols_show].round(3).to_string(index=False))


if __name__ == '__main__':
    main()
