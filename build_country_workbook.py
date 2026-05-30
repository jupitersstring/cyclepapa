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
    mult = {
        'GREEN': 1.10,
        'YELLOW': 0.85,
        'RED': 0.40,
    }
    df['qual_multiplier'] = df['verdict'].map(mult).fillna(1.0)
    df['adj_asymmetry'] = df['asymmetry_score'] * df['qual_multiplier']
    df['adj_upside']    = df['upside_score']    * df['qual_multiplier']
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

    # Master by Asymmetry (qualitatively-amended)
    master_asym = df.sort_values('adj_asymmetry', ascending=False).head(args.top_master).copy()
    # Master by Upside (qualitatively-amended)
    master_upside = df.sort_values('adj_upside', ascending=False).head(args.top_master).copy()

    master_cols = [
        'symbol','name','src','sector','market_cap_bucket','market_cap',
        'verdict','adj_asymmetry','asymmetry_score','adj_upside','upside_score',
        'downside_floor_score','cluster_n','yartseva_score','berezin_score',
        'pb','insider_ownership_pct','cash_gt_ev_flag','graham_net_net_flag',
        'full_thesis','thesis',
    ]
    master_cols = [c for c in master_cols if c in df.columns]

    with pd.ExcelWriter(args.out, engine='openpyxl') as xl:
        master_asym[master_cols].to_excel(xl, sheet_name='Master_By_Asymmetry', index=False)
        master_upside[master_cols].to_excel(xl, sheet_name='Master_By_Upside', index=False)

        # Per-country sheets, sorted by adj_asymmetry within country
        per_country_cols = [
            'symbol','name','sector','market_cap_bucket','market_cap',
            'verdict','adj_asymmetry','adj_upside','asymmetry_score','upside_score',
            'cluster_n','yartseva_score','berezin_score',
            'pb','insider_ownership_pct',
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
            sub = df[df['src'] == ctry].sort_values('adj_asymmetry', ascending=False).head(args.per_country_n)
            if len(sub) == 0:
                continue
            name = country_names.get(ctry, ctry)
            sheet = f'{name}_{ctry}'[:31]
            sub[per_country_cols].to_excel(xl, sheet_name=sheet, index=False)

    print(f'wrote {args.out}', file=sys.stderr)


if __name__ == '__main__':
    main()
