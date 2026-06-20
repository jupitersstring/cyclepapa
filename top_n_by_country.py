"""Emit a flat 'top N per country' table for at-a-glance review.

Uses the same entry_today_asymmetry computation as the Harvard workbook:
asymmetry_score * intrinsic_boost * qual_multiplier * post_rally_factor.

Default: top 10 per country, min mcap $10M USD, RED excluded.

Output: top_n_by_country.csv and a Harvard-styled XLSX one-pager.
"""
from __future__ import annotations
import argparse
import glob
import os
import sys

import numpy as np
import pandas as pd


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
        if 'verdict' not in d.columns and default is not None:
            d['verdict'] = default
        keep = [c for c in ['symbol', 'verdict', 'why', 'why_avoid', 'thesis'] if c in d.columns]
        d = d[keep].copy()
        tc = next((c for c in ['why', 'why_avoid', 'thesis'] if c in d.columns), None)
        d['thesis'] = d[tc] if tc else ''
        frames.append(d[['symbol', 'verdict', 'thesis']])
    if not frames:
        return pd.DataFrame(columns=['symbol', 'verdict', 'thesis'])
    return pd.concat(frames, ignore_index=True).drop_duplicates('symbol', keep='last')


def load_quant() -> pd.DataFrame:
    df = pd.read_csv('asymmetry_global.csv').drop_duplicates('symbol')
    extra_cols = [
        'symbol', 'net_cash_pct_mcap', 'ncav_pct_mcap', 'cash_pct_ev',
        'not_priced_in_score', 'inflection_flag', 'inflection_score',
    ]
    frames = []
    for f in sorted(set(glob.glob('*_yartseva.csv'))):
        try:
            d = pd.read_csv(f, usecols=lambda c: c in extra_cols)
        except Exception:
            continue
        if 'symbol' in d.columns:
            frames.append(d)
    if frames:
        extra = pd.concat(frames, ignore_index=True).drop_duplicates('symbol', keep='first')
        mc = ['symbol'] + [c for c in extra.columns if c != 'symbol' and c not in df.columns]
        df = df.merge(extra[mc], on='symbol', how='left')
    return df


def compute_eta(df: pd.DataFrame, verdicts: pd.DataFrame) -> pd.DataFrame:
    df = df.merge(verdicts, on='symbol', how='left')
    df['verdict'] = df['verdict'].fillna('UNRESEARCHED')
    df['thesis'] = df['thesis'].fillna('')

    soft = {'GREEN': 1.10, 'YELLOW': 0.85, 'RED': 0.40}
    df['qual_mult'] = df['verdict'].map(soft).fillna(1.0)

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
    )
    boost = (1.0 + (df['intrinsic_discount'] - 0.25)).clip(0.5, 1.5)

    mom = col('momentum_12m').clip(-0.5, None)
    pr = pd.Series(1.0, index=df.index)
    mid = (mom > 0.30) & (mom <= 1.0)
    hi = (mom > 1.0) & (mom <= 3.0)
    ex = mom > 3.0
    pr.loc[mid] = 1.0 - (mom[mid] - 0.30) / 0.70 * 0.25
    pr.loc[hi] = 0.75 - (mom[hi] - 1.0) / 2.0 * 0.30
    pr.loc[ex] = 0.40
    df['post_rally_factor'] = pr.round(3)
    df['entry_today_asymmetry'] = df['asymmetry_score'] * boost * df['qual_mult'] * pr

    # Parallel entry-today score for the inflection style. Note: we do NOT
    # apply the post-rally factor here — momentum / breakout names should
    # not be penalised for trending up; that's the whole point of the
    # composite. Verdict multiplier still applies.
    if 'inflection_asymmetry_score' in df.columns:
        df['entry_today_inflection'] = (
            df['inflection_asymmetry_score'] * boost * df['qual_mult']
        )
    else:
        df['entry_today_inflection'] = np.nan
    return df


COUNTRY_NAMES = {
    'US': 'United States', 'CA': 'Canada', 'UK': 'United Kingdom',
    'DE': 'Germany', 'FR': 'France', 'IT': 'Italy', 'NL': 'Netherlands',
    'BE': 'Belgium', 'CH': 'Switzerland', 'IE': 'Ireland', 'AT': 'Austria',
    'SE': 'Sweden', 'NO': 'Norway', 'DK': 'Denmark', 'FI': 'Finland', 'IS': 'Iceland',
    'ES': 'Spain', 'PT': 'Portugal', 'GR': 'Greece',
    'CZ': 'Czechia', 'HU': 'Hungary', 'PL': 'Poland', 'RO': 'Romania',
    'EE': 'Estonia', 'LV': 'Latvia', 'LT': 'Lithuania',
    'JP': 'Japan', 'KR': 'Korea', 'TW': 'Taiwan', 'HK': 'Hong Kong',
    'CN': 'China', 'SG': 'Singapore', 'AU': 'Australia', 'NZ': 'New Zealand',
    'IN': 'India', 'ID': 'Indonesia', 'TH': 'Thailand', 'MY': 'Malaysia',
    'BR': 'Brazil', 'MX': 'Mexico', 'CL': 'Chile', 'AR': 'Argentina',
    'TR': 'Turkey', 'ZA': 'South Africa', 'IL': 'Israel', 'SA': 'Saudi Arabia',
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--n', type=int, default=10, help='top N per country')
    ap.add_argument('--min-mcap', type=float, default=10_000_000)
    ap.add_argument('--exclude-red', action='store_true', default=True)
    ap.add_argument('--include-red', dest='exclude_red', action='store_false')
    ap.add_argument('--sort-by', default='asymmetry',
                    choices=['asymmetry', 'inflection'],
                    help='rank within each country by value-and-contra '
                         'asymmetry or by inflection asymmetry')
    ap.add_argument('--out-csv', default='top_n_by_country.csv')
    ap.add_argument('--out-xlsx', default='top_n_by_country.xlsx')
    args = ap.parse_args()

    print('loading...', file=sys.stderr)
    quant = load_quant()
    verdicts = load_verdicts()
    df = compute_eta(quant, verdicts)
    df = df[df['market_cap'].fillna(0) >= args.min_mcap]
    if args.exclude_red:
        df = df[df['verdict'] != 'RED']
    print(f'  {len(df):,} rows after filters, sort by {args.sort_by}', file=sys.stderr)

    sort_col = ('entry_today_asymmetry' if args.sort_by == 'asymmetry'
                else 'entry_today_inflection')
    # Rank within each country by the chosen score
    df['country_rank'] = (
        df.sort_values(sort_col, ascending=False)
          .groupby('src')
          .cumcount() + 1
    )
    top = df[df['country_rank'] <= args.n].copy()
    top = top.sort_values(['src', 'country_rank'])

    # Friendly country name
    top['country_name'] = top['src'].map(COUNTRY_NAMES).fillna(top['src'])

    out_cols = [
        'country_name', 'src', 'country_rank',
        'symbol', 'name', 'sector', 'industry', 'market_cap_bucket',
        'market_cap', 'verdict',
        'entry_today_asymmetry', 'entry_today_inflection',
        'asymmetry_score', 'inflection_asymmetry_score',
        'yartseva_score', 'inflection_score', 'inflection_flag',
        'berezin_score',
        'intrinsic_discount', 'cluster_n',
        'momentum_12m', 'pb', 'fcf_yield',
        'thesis',
    ]
    out_cols = [c for c in out_cols if c in top.columns]
    out = top[out_cols].copy()
    out.to_csv(args.out_csv, index=False)
    print(f'  wrote {args.out_csv}: {len(out):,} rows across '
          f'{out["src"].nunique()} countries', file=sys.stderr)

    # XLSX with light Harvard-style formatting
    _write_xlsx(out, args.out_xlsx, args.n)


def _write_xlsx(out: pd.DataFrame, path: str, n: int):
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter

    CRIMSON = 'A51C30'
    CRIMSON_DARK = '8B1B2F'
    MUTED = '6B6B6B'
    RULE = 'C0BFB8'
    GREEN_BG, YELLOW_BG, GRAY_BG = 'DCEAD2', 'F8EAB4', 'ECECEC'

    wb = Workbook()
    ws = wb.active
    ws.title = f'Top_{n}_by_Country'

    widths = {1: 18, 2: 5, 3: 5, 4: 12, 5: 38, 6: 18, 7: 14, 8: 12, 9: 9, 10: 10, 11: 11, 12: 11, 13: 9}
    for col, w in widths.items():
        ws.column_dimensions[get_column_letter(col)].width = w

    # Banner
    cell = ws.cell(row=1, column=1, value=f'  Top {n} by Country  ·  Entry-today asymmetry')
    cell.font = Font(name='Cambria', size=14, bold=True, color='FFFFFF')
    cell.fill = PatternFill('solid', fgColor=CRIMSON)
    cell.alignment = Alignment(horizontal='left', vertical='center')
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=13)
    ws.row_dimensions[1].height = 28

    headers = ['Country', 'ISO', '#', 'Ticker', 'Name', 'Sector', 'Bucket',
               'Mcap', 'Verdict', 'ETA', 'Asym', 'Yartseva', 'Cluster']
    for i, h in enumerate(headers, start=1):
        c = ws.cell(row=3, column=i, value=h)
        c.font = Font(name='Calibri', size=10, bold=True, color=CRIMSON_DARK)
        c.alignment = Alignment(horizontal='left' if i in (1, 4, 5, 6) else 'center')
        c.border = Border(bottom=Side(style='medium', color=CRIMSON_DARK))
    ws.row_dimensions[3].height = 22

    prev_country = None
    for r_idx, (_, r) in enumerate(out.iterrows(), start=4):
        # Country banner row when country changes
        if r['country_name'] != prev_country:
            ws.row_dimensions[r_idx].height = 18
            prev_country = r['country_name']
            country_cell_font = Font(name='Cambria', size=10, bold=True, color=CRIMSON_DARK)
        else:
            country_cell_font = Font(name='Cambria', size=10, color=MUTED, italic=True)

        ws.cell(row=r_idx, column=1, value=r['country_name']).font = country_cell_font
        ws.cell(row=r_idx, column=2, value=r['src']).font = Font(name='Calibri', size=9, color=MUTED)
        ws.cell(row=r_idx, column=3, value=int(r['country_rank'])).font = Font(name='Calibri', size=10)
        ws.cell(row=r_idx, column=4, value=r['symbol']).font = Font(name='Calibri', size=10, bold=True)

        name = str(r.get('name') or '')[:60]
        ws.cell(row=r_idx, column=5, value=name).font = Font(name='Cambria', size=10)
        ws.cell(row=r_idx, column=6, value=str(r.get('sector') or '')).font = Font(name='Calibri', size=9, color=MUTED)
        ws.cell(row=r_idx, column=7, value=str(r.get('market_cap_bucket') or '')).font = Font(name='Calibri', size=9, color=MUTED)

        mc = r.get('market_cap')
        mc_str = '—' if pd.isna(mc) else (
            f'${mc/1e9:.1f}B' if abs(mc) >= 1e9 else
            f'${mc/1e6:.0f}M' if abs(mc) >= 1e6 else
            f'${mc/1e3:.0f}K'
        )
        ws.cell(row=r_idx, column=8, value=mc_str).font = Font(name='Consolas', size=9)
        ws.cell(row=r_idx, column=8).alignment = Alignment(horizontal='right')

        v = r['verdict']
        bg = {'GREEN': GREEN_BG, 'YELLOW': YELLOW_BG}.get(v, GRAY_BG)
        vc = ws.cell(row=r_idx, column=9, value=v)
        vc.font = Font(name='Calibri', size=9, bold=True)
        vc.fill = PatternFill('solid', fgColor=bg)
        vc.alignment = Alignment(horizontal='center')

        for ci, (val, fmt) in enumerate([
            (r.get('entry_today_asymmetry'), '.3f'),
            (r.get('asymmetry_score'), '.3f'),
            (r.get('yartseva_score'), '.3f'),
            (int(r.get('cluster_n') or 0), 'd'),
        ], start=10):
            v = '—' if pd.isna(val) else format(val, fmt)
            c = ws.cell(row=r_idx, column=ci, value=v)
            c.font = Font(name='Consolas', size=9)
            c.alignment = Alignment(horizontal='right')

        # Bottom hairline
        for c in range(1, 14):
            ws.cell(row=r_idx, column=c).border = Border(bottom=Side(style='thin', color=RULE))

    ws.sheet_view.showGridLines = False
    ws.freeze_panes = 'A4'
    wb.save(path)
    print(f'  wrote {path}', file=sys.stderr)


if __name__ == '__main__':
    main()
