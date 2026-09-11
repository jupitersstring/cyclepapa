"""Per-country Top-N-by-archetype book, ranked by INFLECTION.

Same country x archetype crossing as build_country_archetype_book, but the
ranking lens is inflection rather than entry asymmetry — for each market, the
archetype sections are ordered by inflection strength (the top-inflecting
patterns surface first), and within each archetype the names are ranked by the
inflection analogue of entry_confirmed:

    entry_inflection_confirmed = inflection_asymmetry_score
                                 * (1 + 0.20*confirm_overall
                                      + 0.15*inflection_confirm_score
                                      + 0.05*buyback_score)

i.e. the inflection base upweighted where independent measures agree — the same
pool-preserving confirmation upweight used everywhere else. The displayed
"Infl" column is the raw inflection_asymmetry_score so the ranking is legible.

Output: country_archetype_inflection_book.xlsx
"""
from __future__ import annotations
import argparse
import sys

import pandas as pd

from build_harvard_workbook import (
    Workbook,
    INK, MUTED, RULE,
    _font,
    _crimson_banner, _section_rule, _verdict_badge,
    _write_money, _write_pct, _write_score, _write_int,
    _NUM_ALIGN_RIGHT, _NUM_ALIGN_CENTER, _TXT_ALIGN_LEFT,
)
from build_archetype_book import (load_data, ARCHETYPE_LABELS, _sheet_safe,
                                  ARCH_SORT_OVERRIDES, arch_sort_col)
from openpyxl.styles import Border, Side
from otc_flag import dedupe_display
from otc_flag import (add_otc_mode_arg, apply_otc_mode,
                      add_high_filter_arg, apply_high_filter)
from region_map import classify, ordered_countries, REGION_ORDER
import tab_colors

SORT_COL = 'entry_inflection_confirmed'

HEADERS = ['#', 'Ticker', 'Name', 'Sector', 'Bucket', 'Mcap (USD)',
           'Verdict', 'Infl', 'Asym', 'EV/EBITDA', 'P/E', 'PEGY', 'EV-GY',
           'FCF yld %', 'Div %', 'ROCE %', 'ND/EBITDA', 'Mom 12m %', 'Arch #',
           'P/S', 'P/B']
N_COLS = len(HEADERS)
WIDTHS = {1: 4, 2: 12, 3: 34, 4: 16, 5: 11, 6: 15, 7: 12, 8: 7, 9: 7,
          10: 9, 11: 8, 12: 7, 13: 7, 14: 9, 15: 7, 16: 8, 17: 10, 18: 10,
          19: 7, 20: 7, 21: 7}


def _add_inflection_key(df):
    """entry_inflection_confirmed = inflection base * confirmation upweight.

    The inflection lens gets the inflection-specific confirmation folded in:
    inflection_confirm_score (operating leverage + top-line growth agreeing
    across time bases) carries the middle weight, alongside the overall
    multi-measure confirmation and a small buyback leg."""
    infl = pd.to_numeric(df.get('inflection_asymmetry_score'), errors='coerce').fillna(0.0)
    cfo = pd.to_numeric(df.get('confirm_overall'), errors='coerce').fillna(0.0)
    ics = pd.to_numeric(df.get('inflection_confirm_score'), errors='coerce').fillna(0.0)
    bbs = pd.to_numeric(df.get('buyback_score'), errors='coerce').fillna(0.0)
    # (books audit #7) inputs clipped, product capped — the documented
    # <=40% confirmation bound must be enforced, not assumed
    df['entry_inflection_confirmed'] = infl * (1.0 + 0.20 * cfo.clip(0, 1)
                                               + 0.15 * ics.clip(0, 1)
                                               + 0.05 * bbs.clip(0, 1)).clip(1.0, 1.40)
    return df


def _write_country_sheet(ws, cdf, country, arch_cols, n_top,
                         show_country=False):
    o = 1 if show_country else 0                 # column offset past Name
    headers = HEADERS[:3] + (['Ctry'] if show_country else []) + HEADERS[3:]
    n_cols = len(headers)
    widths = {1: 4, 2: 12, 3: 34}
    if show_country:
        widths[4] = 6
    for k in range(4, N_COLS + 1):
        widths[k + o] = WIDTHS[k]
    f_bold = _font(bold=True, color=INK)
    f_bold_muted = _font(bold=True, color=MUTED)
    f_text = _font(color=INK)
    f_text_muted = _font(color=MUTED)

    for col, w in widths.items():
        ws.column_dimensions[ws.cell(row=1, column=col).column_letter].width = w

    t = ws.cell(row=2, column=1,
                value=f"{country} — Top {n_top} per archetype by inflection   "
                      f"({len(cdf):,} eligible names)")
    t.font = f_bold
    t.alignment = _TXT_ALIGN_LEFT
    ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=n_cols)
    ws.row_dimensions[2].height = 22
    for c in range(1, n_cols + 1):
        ws.cell(row=3, column=c).border = Border(bottom=Side(style='thin', color=INK))
    ws.row_dimensions[3].height = 4

    # Archetypes ordered by IN-COUNTRY INFLECTION STRENGTH (the leading name's
    # confirmed inflection), skip archetypes with no members here.
    ranked = []
    for col in arch_cols:
        members = cdf[cdf[col].fillna(0) == 1]
        n_match = int(len(members))
        if n_match == 0:
            continue
        peak = pd.to_numeric(members[SORT_COL], errors='coerce').max()
        ranked.append((col, n_match, float(peak) if pd.notna(peak) else 0.0))
    ranked.sort(key=lambda x: -x[2])   # strongest-inflecting archetype first

    row = 5
    for col, n_match, _peak in ranked:
        label = ARCHETYPE_LABELS.get(col, col)
        members = cdf[cdf[col].fillna(0) == 1]
        # Archetype-specific sort where one exists (ARCH_SORT_OVERRIDES);
        # falls back to the confirmed-inflection key when missing/all-NaN.
        tab_sort = arch_sort_col(col, members, SORT_COL)
        sub = (dedupe_display(
                   members.sort_values(tab_sort, ascending=False,
                                       na_position='last'))
               .head(n_top))
        _section_rule(ws, row, f"{label}   —   {n_match:,} matches in {country}",
                      span_cols=n_cols)
        row += 1
        for i, h in enumerate(headers, start=1):
            c = ws.cell(row=row, column=i, value=h)
            c.font = f_bold_muted
            c.alignment = (_TXT_ALIGN_LEFT if i in (2, 3, 4) else
                           _NUM_ALIGN_CENTER if i in (5 + o, 7 + o) else
                           _NUM_ALIGN_RIGHT)
        row += 1
        for rank, (_, r) in enumerate(sub.iterrows(), start=1):
            _write_int(ws, row, 1, rank, font=f_text_muted)
            ws.cell(row=row, column=2, value=r['symbol']).font = f_bold
            ws.cell(row=row, column=2).alignment = _TXT_ALIGN_LEFT
            _t = lambda v: '' if pd.isna(v) else str(v)
            ws.cell(row=row, column=3, value=_t(r.get('name'))[:48]).font = f_text
            ws.cell(row=row, column=3).alignment = _TXT_ALIGN_LEFT
            if show_country:
                ws.cell(row=row, column=4, value=_t(r.get('src'))).font = f_text_muted
                ws.cell(row=row, column=4).alignment = _TXT_ALIGN_LEFT
            ws.cell(row=row, column=4 + o, value=_t(r.get('sector'))[:20]).font = f_text_muted
            ws.cell(row=row, column=4 + o).alignment = _TXT_ALIGN_LEFT
            ws.cell(row=row, column=5 + o, value=_t(r.get('market_cap_bucket'))).font = f_text_muted
            ws.cell(row=row, column=5 + o).alignment = _NUM_ALIGN_CENTER
            _write_money(ws, row, 6 + o, r.get('market_cap'), font=f_text)
            _verdict_badge(ws, row, 7 + o, r.get('verdict', 'UNRESEARCHED'))
            _write_score(ws, row, 8 + o, r.get('inflection_asymmetry_score'), font=f_bold)
            _write_score(ws, row, 9 + o, r.get('asymmetry_score'), font=f_text)
            _write_score(ws, row, 10 + o, r.get('ev_ebitda'), font=f_text)
            _write_score(ws, row, 11 + o, r.get('p_e'), font=f_text)
            _write_score(ws, row, 12 + o, r.get('pegy'), font=f_text)
            _write_score(ws, row, 13 + o, r.get('ev_ebitda_gy'), font=f_text)
            _write_pct(ws, row, 14 + o, r.get('fcf_yield'), font=f_text)
            _write_pct(ws, row, 15 + o, r.get('dividend_yield'), font=f_text)
            _write_pct(ws, row, 16 + o, r.get('roce'), font=f_text)
            _write_score(ws, row, 17 + o, r.get('net_debt_ebitda'), font=f_text)
            _write_pct(ws, row, 18 + o, r.get('momentum_12m'), font=f_text)
            _write_int(ws, row, 19 + o,
                       int(r['archetype_count']) if pd.notna(r.get('archetype_count')) else 0,
                       font=f_text_muted)
            _write_score(ws, row, 20 + o, r.get('p_s'), font=f_text)
            _write_score(ws, row, 21 + o, r.get('pb'), font=f_text)
            for c in range(1, n_cols + 1):
                ws.cell(row=row, column=c).border = Border(
                    bottom=Side(style='thin', color=RULE))
            ws.row_dimensions[row].height = 15
            row += 1
        row += 2  # gap between archetype sections
    ws.sheet_view.showGridLines = False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--n', type=int, default=30,
                    help='top N per archetype per country')
    ap.add_argument('--min-names', type=int, default=25,
                    help='minimum eligible names for a country to get a sheet')
    ap.add_argument('--global-n', type=int, default=100,
                    help='top N per archetype on the GLOBAL sheet')
    ap.add_argument('--out', default='country_archetype_inflection_book.xlsx')
    ap.add_argument('--min-mcap', type=float, default=0,
                    help='USD market-cap floor (e.g. 2e9 for a mid-cap-\n                         and-above book). 0 = full universe.')
    add_otc_mode_arg(ap)
    add_high_filter_arg(ap)
    args = ap.parse_args()

    df, arch_cols = load_data(min_mcap=args.min_mcap, otc_mode='all')
    df = apply_otc_mode(df, args.otc_mode)
    df = apply_high_filter(df, args.high_filter)
    df = _add_inflection_key(df)
    df['src'] = df['src'].fillna('').astype(str).str.upper()
    print(f'  {len(df):,} eligible rows, {len(arch_cols)} archetypes',
          file=sys.stderr)

    wb = Workbook()
    cover = wb.active
    tab_colors.set_tab(cover, tab_colors.COVER)
    cover.title = 'Cover'
    for col, w in {1: 8, 2: 22, 3: 12, 4: 14, 5: 30}.items():
        cover.column_dimensions[cover.cell(row=1, column=col).column_letter].width = w
    _crimson_banner(cover, 2, 'COUNTRY x ARCHETYPE — INFLECTION', span_cols=5)
    sub = cover.cell(row=4, column=1,
                     value=f'Top {args.n} names per archetype within each market, '
                           f'ranked by inflection — archetype sections ordered by '
                           f'in-market inflection strength')
    sub.font = _font(italic=True, color=MUTED)
    sub.alignment = _TXT_ALIGN_LEFT
    f_bold_muted = _font(bold=True, color=MUTED)
    f_text = _font(color=INK)
    f_text_muted = _font(color=MUTED)

    order = (df.groupby('src').size().sort_values(ascending=False))
    countries = ordered_countries(
        [c for c, n in order.items() if c and n >= args.min_names])
    df['_bucket'], df['_region'] = zip(*df['src'].map(classify))

    _section_rule(cover, 7, 'Markets', span_cols=5)
    for i, h in enumerate(['#', 'Market', 'Names', 'Multi-arch', 'Top name by Infl'], start=1):
        cover.cell(row=8, column=i, value=h).font = f_bold_muted
    r = 9
    for i, ctry in enumerate(countries, start=1):
        cdf = df[df['src'] == ctry]
        _write_int(cover, r, 1, i, font=f_text_muted)
        cover.cell(row=r, column=2, value=ctry).font = f_text
        _write_int(cover, r, 3, len(cdf), font=f_text)
        _write_int(cover, r, 4, int((cdf['archetype_count'].fillna(0) >= 2).sum()),
                   font=f_text)
        top = cdf.sort_values(SORT_COL, ascending=False, na_position='last').head(1)
        cover.cell(row=r, column=5,
                   value=(top.iloc[0]['symbol'] if len(top) else '—')).font = f_text_muted
        r += 1

    # Aggregate sheets first (each with a Ctry column): GLOBAL, DM, EM,
    # then each region — cross-market best by confirmed inflection at every
    # aggregation level, beside the country partitions.
    n_agg_sheets = 0
    for title, sub_df in ([('GLOBAL', df),
                           ('DM', df[df['_bucket'] == 'DM']),
                           ('EM', df[df['_bucket'] == 'EM'])]
                          + [(reg, df[df['_region'] == reg])
                             for _b, reg in REGION_ORDER
                             if (df['_region'] == reg).any()]):
        if sub_df.empty:
            continue
        ws = wb.create_sheet(_sheet_safe(title))
        tab_colors.set_tab(ws, tab_colors.AGGREGATE)
        _write_country_sheet(ws, sub_df, title, arch_cols, args.global_n,
                             show_country=True)
        n_agg_sheets += 1
        print(f'  {title}: {len(sub_df):,} names, top {args.global_n}/archetype',
              file=sys.stderr)

    for ctry in countries:
        cdf = df[df['src'] == ctry]
        ws = wb.create_sheet(_sheet_safe(ctry))
        tab_colors.set_tab(ws, tab_colors.region_color(ctry))
        _write_country_sheet(ws, cdf, ctry, arch_cols, args.n)
        print(f'  {ctry}: {len(cdf):,} names', file=sys.stderr)

    tab_colors.write_legend(cover, 9, 9, tab_colors.region_legend(),
                            title='Tab colours — region')
    cover.sheet_view.showGridLines = False
    wb.save(args.out)
    print(f'wrote {args.out}  ({1 + n_agg_sheets + len(countries)} sheets: '
          f'Cover + GLOBAL/DM/EM/regions ({n_agg_sheets}) + '
          f'{len(countries)} countries)', file=sys.stderr)


if __name__ == '__main__':
    main()
