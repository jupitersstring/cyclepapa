"""Build the multi-sheet Excel deliverable.

Inputs:
  asymmetry_global.csv                  - quant rankings (4,983 names)
  qualitative_aligned_green.csv         - 26 GREEN from initial 8 region agents
  qualitative_red_avoid.csv             - 19 RED from initial 8 region agents
  qualitative_extended_verdicts.csv     - 80-90 additional verdicts from 4 follow-up agents

Outputs:
  asymmetry_country_workbook.xlsx       - master workbook
    Sheet 1: Master_By_Asymmetry  - top names global, ranked by asymmetry, qualitatively-amended
    Sheet 2: Master_By_Upside     - top names global, ranked by upside potential, qualitatively-amended
    Sheets 3-N: One per country with top 15-20 + verdicts

Qualitative amendment logic:
  GREEN  -> adj_asymmetry = asymmetry_score * 1.10  (10% boost)
  YELLOW -> adj_asymmetry = asymmetry_score * 0.85  (15% haircut)
  RED    -> adj_asymmetry = asymmetry_score * 0.40  (60% haircut - effectively removes from upper ranks)
  (not researched) -> adj_asymmetry = asymmetry_score (unchanged)
"""

from __future__ import annotations
import argparse
import os
import sys
from pathlib import Path

import pandas as pd
import numpy as np


def load_quant(p: str = 'asymmetry_global.csv') -> pd.DataFrame:
    df = pd.read_csv(p).drop_duplicates('symbol').sort_values('asymmetry_score', ascending=False)

    # Merge in the framework's intrinsic-value-discount measures from the
    # per-country yartseva snapshots (these fields exist on the raw scans
    # but were not propagated into asymmetry_global.csv).
    extra_cols = [
        'symbol','net_cash_pct_mcap','ncav_pct_mcap','cash_pct_ev',
        'not_priced_in_score','revenue_ttm','balance_sheet_date',
    ]
    import glob, os
    yartseva_csvs = sorted(set(
        glob.glob('*_yartseva.csv')
        + glob.glob('us_nano_micro_small_yartseva.csv')
        + glob.glob('italian_yartseva.csv')
    ))
    extra_frames = []
    for f in yartseva_csvs:
        try:
            d = pd.read_csv(f, usecols=lambda c: c in extra_cols)
        except Exception:
            continue
        if 'symbol' in d.columns:
            extra_frames.append(d)
    if extra_frames:
        extra = pd.concat(extra_frames, ignore_index=True).drop_duplicates('symbol', keep='first')
        # Avoid clobbering existing columns from asymmetry_global
        merge_cols = ['symbol'] + [c for c in extra.columns if c != 'symbol' and c not in df.columns]
        df = df.merge(extra[merge_cols], on='symbol', how='left')
    return df


def load_verdicts() -> pd.DataFrame:
    """Concat all qualitative verdict CSVs into a single (symbol, verdict, thesis) frame."""
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
            # Some thesis lines have unquoted commas; fall back to python engine
            d = pd.read_csv(path, engine='python', on_bad_lines='skip', quoting=3)
        if 'verdict' not in d.columns and default is not None:
            d['verdict'] = default
        keep = [c for c in ['symbol','verdict','why','why_avoid','thesis'] if c in d.columns]
        d = d[keep].copy()
        # Standardise the thesis column
        thesis_col = next((c for c in ['why','why_avoid','thesis'] if c in d.columns), None)
        if thesis_col:
            d['thesis'] = d[thesis_col]
        else:
            d['thesis'] = ''
        frames.append(d[['symbol','verdict','thesis']])
    if not frames:
        return pd.DataFrame(columns=['symbol','verdict','thesis'])
    out = pd.concat(frames, ignore_index=True).drop_duplicates('symbol', keep='first')
    return out


def amend_scores(df: pd.DataFrame) -> pd.DataFrame:
    """Apply qualitative multiplier to the asymmetry score and the upside score."""
    # Soft multiplier used on the master sheets (keeps RED in the table for
    # transparency, with a heavy haircut).
    mult = {
        'GREEN': 1.10,
        'YELLOW': 0.85,
        'RED': 0.40,
    }
    df['qual_multiplier'] = df['verdict'].map(mult).fillna(1.0)

    # Stricter multiplier for per-country tops: drops RED entirely, gives
    # GREEN a stronger boost, treats UNRESEARCHED as cautious (haven't
    # validated yet so should not lead a country list).
    strict_mult = {
        'GREEN': 1.30,
        'YELLOW': 0.70,
        'RED': 0.0,             # excluded from per-country tops
        'UNRESEARCHED': 0.85,
    }
    df['strict_qual_multiplier'] = df['verdict'].map(strict_mult).fillna(0.85)

    df['adj_asymmetry'] = df['asymmetry_score'] * df['qual_multiplier']
    df['adj_upside']    = df['upside_score']    * df['qual_multiplier']

    # ----- Discount to intrinsic value (entry-today lens) -----
    # Built from the framework's existing measures of how cheap the stock
    # is RIGHT NOW vs intrinsic value (book / NCAV / net cash / EV multiples
    # / not-priced-in). Higher = bigger margin of safety on entry today.
    #
    #   30% net cash / mcap          (cash above debt as % of mcap, capped 0..1)
    #   20% NCAV / mcap              (Graham working-capital cushion, capped 0..1)
    #   20% (1 - pb)                 (sub-book bonus when pb < 1)
    #   15% cash > EV strength       (cash_pct_ev - 1 mapped to 0..1, cap at 3x)
    #   15% not_priced_in_score      (fundamentals running ahead of price)
    def _series(col, default=0.0):
        if col in df.columns:
            return df[col].fillna(default)
        return pd.Series(default, index=df.index)

    def clip01(s):
        return s.clip(0, 1).fillna(0)

    nc_pct  = clip01(_series('net_cash_pct_mcap'))
    ncav    = clip01(_series('ncav_pct_mcap'))
    sub_book = clip01(1.0 - _series('pb', 2.0).clip(lower=0.01))
    cash_ev_strength = clip01(
        (_series('cash_pct_ev') - 1.0).clip(0, 2) / 2.0
    )
    not_priced = clip01(_series('not_priced_in_score'))

    df['intrinsic_discount'] = (
        0.30 * nc_pct
        + 0.20 * ncav
        + 0.20 * sub_book
        + 0.15 * cash_ev_strength
        + 0.15 * not_priced
    )

    # Entry-today asymmetry = the existing asymmetry score scaled by the
    # depth of discount-to-intrinsic-value, then qualitatively amended.
    # The boost factor sits in roughly [0.5, 1.5] so a name with strong
    # framework-measured discount gets a meaningful lift, weak ones get a
    # haircut, but neither dominates the existing quant ranking.
    boost = (1.0 + (df['intrinsic_discount'] - 0.25)).clip(0.5, 1.5)
    df['entry_today_asymmetry'] = df['asymmetry_score'] * boost * df['qual_multiplier']
    df['entry_today_upside']    = df['upside_score']    * boost * df['qual_multiplier']

    # Strict variants used to sort per-country sheets. RED -> 0 (excluded);
    # GREEN gets +30% boost; YELLOW haircut to 0.70; UNRESEARCHED at 0.85.
    df['country_entry_asymmetry'] = df['asymmetry_score'] * boost * df['strict_qual_multiplier']
    df['country_entry_upside']    = df['upside_score']    * boost * df['strict_qual_multiplier']

    return df


def compose_thesis(row) -> str:
    bits = []
    # Cluster signals
    if pd.notna(row.get('cluster_n')) and row['cluster_n'] >= 4:
        bits.append(f'{int(row["cluster_n"])}-cluster')
    # Cash floor
    if row.get('cash_gt_ev_flag') == 1:
        bits.append('cash > EV')
    if row.get('graham_net_net_flag') == 1:
        bits.append('Graham net-net')
    if row.get('pew_negative_ev_flag') == 1:
        bits.append('neg-EV')
    # Sub-book
    if pd.notna(row.get('pb')) and 0 < row['pb'] < 1.0:
        bits.append(f'P/B {row["pb"]:.2f}')
    # Insider
    if pd.notna(row.get('insider_ownership_pct')) and row['insider_ownership_pct'] >= 0.30:
        bits.append(f'insider {row["insider_ownership_pct"]:.0%}')
    # Scores
    if pd.notna(row.get('yartseva_score')) and row['yartseva_score'] >= 0.55:
        bits.append(f'yart {row["yartseva_score"]:.2f}')
    if pd.notna(row.get('berezin_score')) and row['berezin_score'] >= 0.50:
        bits.append(f'Berez {row["berezin_score"]:.2f}')
    return '; '.join(bits)


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--per-country-n', type=int, default=30)
    p.add_argument('--top-master', type=int, default=200)
    p.add_argument('--out', default='asymmetry_country_workbook.xlsx')
    p.add_argument('--min-mcap', type=float, default=10_000_000)
    args = p.parse_args()

    df = load_quant()
    print(f'loaded quant: {len(df)} rows', file=sys.stderr)
    verdicts = load_verdicts()
    print(f'loaded verdicts: {len(verdicts)} names', file=sys.stderr)

    df = df.merge(verdicts, on='symbol', how='left')
    df['verdict'] = df['verdict'].fillna('UNRESEARCHED')
    df['thesis']  = df['thesis'].fillna('')
    df['quant_thesis'] = df.apply(compose_thesis, axis=1)
    df['full_thesis']  = df.apply(
        lambda r: (r['thesis'] + ' | ' + r['quant_thesis']).strip(' |'),
        axis=1,
    )
    df = amend_scores(df)

    df = df[df['market_cap'].fillna(0) >= args.min_mcap]

    # Master rankings - 4 versions:
    #   1. By raw qualitatively-amended asymmetry (full upside)
    #   2. By raw qualitatively-amended upside    (full upside)
    #   3. By ENTRY-TODAY asymmetry  (upside discounted by 12m run-up)
    #   4. By ENTRY-TODAY upside     (upside discounted by 12m run-up)
    master_asym       = df.sort_values('adj_asymmetry', ascending=False).head(args.top_master).copy()
    master_upside     = df.sort_values('adj_upside', ascending=False).head(args.top_master).copy()
    master_entry_asym = df.sort_values('entry_today_asymmetry', ascending=False).head(args.top_master).copy()
    master_entry_ups  = df.sort_values('entry_today_upside', ascending=False).head(args.top_master).copy()

    master_cols = [
        'symbol','name','src','sector','market_cap_bucket','market_cap',
        'verdict',
        'entry_today_asymmetry','entry_today_upside','intrinsic_discount',
        'adj_asymmetry','asymmetry_score','adj_upside','upside_score',
        'downside_floor_score','cluster_n','yartseva_score','berezin_score',
        'pb','net_cash_pct_mcap','ncav_pct_mcap','cash_pct_ev',
        'not_priced_in_score','insider_ownership_pct',
        'cash_gt_ev_flag','graham_net_net_flag',
        'full_thesis','thesis',
    ]
    master_cols = [c for c in master_cols if c in df.columns]

    with pd.ExcelWriter(args.out, engine='openpyxl') as xl:
        # Entry-today views first (the more honest "buying today" lists)
        master_entry_asym[master_cols].to_excel(xl, sheet_name='Master_EntryToday_Asymmetry', index=False)
        master_entry_ups[master_cols].to_excel(xl,  sheet_name='Master_EntryToday_Upside', index=False)
        # Then the raw (full-asymmetry-cycle) views
        master_asym[master_cols].to_excel(xl, sheet_name='Master_By_Asymmetry', index=False)
        master_upside[master_cols].to_excel(xl, sheet_name='Master_By_Upside', index=False)

        # Per-country summary - top 3 per country by the strict country
        # entry-today asymmetry (drops RED, boosts GREEN, treats
        # UNRESEARCHED cautiously).
        summary_rows = []
        for ctry, _ in df['src'].value_counts().items():
            sub = df[(df['src'] == ctry) & (df['verdict'] != 'RED')] \
                .sort_values('country_entry_asymmetry', ascending=False) \
                .head(3)
            for rank, (_, r) in enumerate(sub.iterrows(), start=1):
                summary_rows.append({
                    'country': ctry,
                    'country_rank': rank,
                    'symbol': r['symbol'],
                    'name': r['name'],
                    'sector': r.get('sector', ''),
                    'market_cap_bucket': r.get('market_cap_bucket', ''),
                    'market_cap': r.get('market_cap', 0),
                    'verdict': r.get('verdict', 'UNRESEARCHED'),
                    'country_entry_asymmetry': r.get('country_entry_asymmetry', 0),
                    'entry_today_asymmetry': r.get('entry_today_asymmetry', 0),
                    'intrinsic_discount': r.get('intrinsic_discount', 0),
                    'cluster_n': r.get('cluster_n', 0),
                    'pb': r.get('pb', 0),
                    'cash_gt_ev_flag': r.get('cash_gt_ev_flag', 0),
                    'insider_ownership_pct': r.get('insider_ownership_pct', 0),
                    'thesis': r.get('full_thesis', ''),
                })
        pd.DataFrame(summary_rows).to_excel(xl, sheet_name='Per_Country_Top3', index=False)

        # Per-country sheets, sorted by adj_asymmetry within country
        per_country_cols = [
            'symbol','name','sector','market_cap_bucket','market_cap',
            'verdict',
            'country_entry_asymmetry','country_entry_upside','intrinsic_discount',
            'entry_today_asymmetry','entry_today_upside',
            'adj_asymmetry','adj_upside','asymmetry_score','upside_score',
            'cluster_n','yartseva_score','berezin_score',
            'pb','net_cash_pct_mcap','ncav_pct_mcap','cash_pct_ev',
            'not_priced_in_score','insider_ownership_pct',
            'cash_gt_ev_flag','graham_net_net_flag','full_thesis','thesis',
        ]
        per_country_cols = [c for c in per_country_cols if c in df.columns]

        # Country code -> long name for sheet titles (kept under Excel's 31-char limit)
        country_names = {
            'US':'USA','UK':'UK','DE':'Germany','FR':'France','IT':'Italy','NL':'Netherlands',
            'BE':'Belgium','CH':'Switzerland','IE':'Ireland','SE':'Sweden','NO':'Norway',
            'DK':'Denmark','FI':'Finland','AT':'Austria','ES':'Spain','GR':'Greece','PT':'Portugal',
            'CZ':'Czechia','HU':'Hungary','EE':'Estonia','LV':'Latvia','LT':'Lithuania',
            'JP':'Japan','HK':'HongKong','KR':'Korea','TW':'Taiwan','SG':'Singapore',
            'IN':'India','ID':'Indonesia','TH':'Thailand','AU':'Australia','NZ':'NewZealand',
            'CA':'Canada','BR':'Brazil','MX':'Mexico','ZA':'SouthAfrica','TR':'Turkey','IL':'Israel',
        }
        # Order by number of survivors per country
        for ctry, _ in df['src'].value_counts().items():
            # Sort per-country sheets by the STRICT entry-today asymmetry
            # (drops RED, boosts GREEN, treats UNRESEARCHED cautiously).
            sub_all = df[df['src'] == ctry]
            sub = sub_all[sub_all['verdict'] != 'RED'] \
                .sort_values('country_entry_asymmetry', ascending=False) \
                .head(args.per_country_n)
            if len(sub) == 0:
                continue
            name = country_names.get(ctry, ctry)
            sheet = f'{name}_{ctry}'[:31]
            sub[per_country_cols].to_excel(xl, sheet_name=sheet, index=False)

    print(f'wrote {args.out}', file=sys.stderr)


if __name__ == '__main__':
    main()
