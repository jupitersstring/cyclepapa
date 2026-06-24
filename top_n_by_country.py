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
    # asymmetry_global may carry a verdict/thesis column from the
    # enrich_asymmetry_global post-pass. Drop those before merging the
    # fresh verdicts file (which is the most up-to-date source).
    df = df.drop(columns=[c for c in ('verdict', 'thesis') if c in df.columns])
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
    """Harvard-style table: numbers as real numbers with cell number_format,
    text left-aligned, numbers right-aligned, negatives in parens, em-dash
    for empty cells. Mirrors the spec used in build_harvard_workbook.py."""
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter

    # Monochrome palette — single font + grey-only highlights
    INK = '000000'
    DARK_GREY = '404040'
    MUTED = '707070'
    RULE = 'B0B0B0'
    LIGHT_GREY = 'E8E8E8'
    PALE_GREY = 'F2F2F2'
    WHITE = 'FFFFFF'
    CRIMSON = INK
    CRIMSON_DARK = DARK_GREY
    GREEN_BG = LIGHT_GREY
    YELLOW_BG = PALE_GREY
    GRAY_BG = WHITE
    FONT_NAME = 'Cambria'   # Harvard-style serif default
    FONT_SIZE = 10

    EM_DASH = '–'
    FMT_INT_RAW = '#,##0;(#,##0);"–"'
    FMT_ONE = '#,##0.0;(#,##0.0);"–"'
    FMT_TWO = '#,##0.00;(#,##0.00);"–"'

    A_LEFT = Alignment(horizontal='left', vertical='center')
    A_RIGHT = Alignment(horizontal='right', vertical='center')
    A_CENTER = Alignment(horizontal='center', vertical='center')

    wb = Workbook()
    ws = wb.active
    ws.title = f'Top_{n}_by_Country'

    def _put_num(row, col, value, fmt, scale=1.0, font=None, align=A_RIGHT):
        cell = ws.cell(row=row, column=col)
        if value is None or (isinstance(value, float) and pd.isna(value)):
            cell.value = EM_DASH
            cell.alignment = align
        else:
            try:
                cell.value = float(value) * scale
                cell.number_format = fmt
            except (TypeError, ValueError):
                cell.value = EM_DASH
            cell.alignment = align
        if font is not None:
            cell.font = font

    def _put_int(row, col, value, font=None):
        _put_num(row, col, value, FMT_INT_RAW, font=font)

    def _put_money(row, col, value, font=None):
        _put_num(row, col, value, FMT_INT_RAW, font=font)

    def _put_score(row, col, value, font=None):
        _put_num(row, col, value, FMT_TWO, font=font)

    def _put_text(row, col, value, font=None, align=A_LEFT):
        cell = ws.cell(row=row, column=col,
                       value=value if value not in (None, '') else EM_DASH)
        cell.alignment = align
        if font is not None:
            cell.font = font

    # Country | ISO | # | Ticker | Name | Sector | Bucket |
    # Mcap (USD) | Verdict | ETA | Asym | Yartseva | Cluster
    widths = {1: 18, 2: 6, 3: 5, 4: 12, 5: 38, 6: 18, 7: 14,
              8: 18, 9: 10, 10: 10, 11: 10, 12: 10, 13: 8}
    for col, w in widths.items():
        ws.column_dimensions[get_column_letter(col)].width = w

    # Banner
    cell = ws.cell(row=1, column=1,
                   value=f'  Top {n} by Country  ·  Entry-today asymmetry')
    cell.font = Font(name=FONT_NAME, size=FONT_SIZE, bold=True, color='FFFFFF')
    cell.fill = PatternFill('solid', fgColor=LIGHT_GREY)
    cell.alignment = A_LEFT
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=13)
    ws.row_dimensions[1].height = 28

    headers = ['Country', 'ISO', '#', 'Ticker', 'Name', 'Sector', 'Bucket',
               'Mcap (USD)', 'Verdict', 'ETA', 'Asym', 'Yartseva', 'Cluster']
    for i, h in enumerate(headers, start=1):
        c = ws.cell(row=3, column=i, value=h)
        c.font = Font(name=FONT_NAME, size=FONT_SIZE, bold=True, color=CRIMSON_DARK)
        if i in (1, 4, 5, 6, 7):
            c.alignment = A_LEFT
        elif i in (2, 3, 9):
            c.alignment = A_CENTER
        else:
            c.alignment = A_RIGHT
        c.border = Border(bottom=Side(style='medium', color=CRIMSON_DARK))
    ws.row_dimensions[3].height = 22

    f_text = Font(name=FONT_NAME, size=FONT_SIZE,)
    f_text_muted = Font(name=FONT_NAME, size=FONT_SIZE, color=MUTED)
    f_ticker = Font(name=FONT_NAME, size=FONT_SIZE, bold=True)
    f_mono = Font(name=FONT_NAME, size=FONT_SIZE,)
    f_int = Font(name=FONT_NAME, size=FONT_SIZE,)
    f_country_header = Font(name=FONT_NAME, size=FONT_SIZE, bold=True, color=CRIMSON_DARK)
    f_country_repeat = Font(name=FONT_NAME, size=FONT_SIZE, color=MUTED, italic=True)

    prev_country = None
    for r_idx, (_, r) in enumerate(out.iterrows(), start=4):
        country_font = (f_country_header if r['country_name'] != prev_country
                        else f_country_repeat)
        prev_country = r['country_name']

        _put_text(r_idx, 1, r['country_name'], font=country_font)
        _put_text(r_idx, 2, r['src'], font=f_text_muted, align=A_CENTER)
        _put_int(r_idx, 3, int(r['country_rank']), font=f_int)
        _put_text(r_idx, 4, r['symbol'], font=f_ticker)
        _put_text(r_idx, 5, str(r.get('name') or '')[:60], font=f_text)
        _put_text(r_idx, 6, str(r.get('sector') or ''), font=f_text_muted)
        _put_text(r_idx, 7, str(r.get('market_cap_bucket') or ''), font=f_text_muted)

        # Mcap: raw USD, comma-grouped, parens-on-negative, em-dash if missing.
        _put_money(r_idx, 8, r.get('market_cap'), font=f_mono)

        # Verdict badge (colored fill, centered)
        v = r['verdict']
        bg = {'GREEN': GREEN_BG, 'YELLOW': YELLOW_BG}.get(v, GRAY_BG)
        vc = ws.cell(row=r_idx, column=9, value=v)
        vc.font = Font(name=FONT_NAME, size=FONT_SIZE, bold=True)
        vc.fill = PatternFill('solid', fgColor=bg)
        vc.alignment = A_CENTER

        # Scores: 2-decimal ratios, right-aligned, em-dash on missing
        _put_score(r_idx, 10, r.get('entry_today_asymmetry'), font=f_mono)
        _put_score(r_idx, 11, r.get('asymmetry_score'), font=f_mono)
        _put_score(r_idx, 12, r.get('yartseva_score'), font=f_mono)
        _put_int(r_idx, 13, int(r.get('cluster_n') or 0), font=f_mono)

        # Bottom hairline
        for cidx in range(1, 14):
            ws.cell(row=r_idx, column=cidx).border = Border(
                bottom=Side(style='thin', color=RULE))

    ws.sheet_view.showGridLines = False
    ws.freeze_panes = 'A4'
    wb.save(path)
    print(f'  wrote {path}', file=sys.stderr)


if __name__ == '__main__':
    main()
