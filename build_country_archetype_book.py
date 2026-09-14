"""Per-country Top-N-by-archetype book.

The global archetype book ranks across the whole universe, so cheap
high-scoring markets (Korea, Japan smalls, Indonesia...) dominate every
sheet. This book partitions by country first: one sheet per market, and
within it the top N names for EACH archetype, so every market's best
representatives of every pattern are visible side by side.

Reuses load_data + labels from build_archetype_book and the Harvard
styling from build_harvard_workbook. Sections are stacked vertically per
archetype, ordered by match count within the country; rows sorted by
entry_today_asymmetry. Includes the Lynch multiples (PEGY, EV/EBITDA-GY)
as columns.

Output: country_archetype_book.xlsx
"""
from __future__ import annotations
import argparse
import os
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

SORT_COL = 'entry_confirmed'

HEADERS = ['#', 'Ticker', 'Name', 'Sector', 'Bucket', 'Mcap (USD)',
           'Verdict', 'ETA', 'Asym', 'EV/EBITDA', 'P/E', 'PEGY', 'EV-GY',
           'FCF yld %', 'Div %', 'ROCE %', 'ND/EBITDA', 'Mom 12m %', 'Arch #',
           'P/S', 'P/B']
N_COLS = len(HEADERS)
WIDTHS = {1: 4, 2: 12, 3: 34, 4: 16, 5: 11, 6: 15, 7: 12, 8: 7, 9: 7,
          10: 9, 11: 8, 12: 7, 13: 7, 14: 9, 15: 7, 16: 8, 17: 10, 18: 10,
          19: 7, 20: 7, 21: 7}


def _write_country_sheet(ws, cdf, country, arch_cols, n_top,
                         show_country=False):
    """One sheet of stacked per-archetype sections. `show_country=True`
    (GLOBAL / DM / EM / region sheets) inserts a Ctry column after Name."""
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
    f_italic_muted = _font(italic=True, color=MUTED)

    for col, w in widths.items():
        ws.column_dimensions[ws.cell(row=1, column=col).column_letter].width = w

    t = ws.cell(row=2, column=1,
                value=f"{country} — Top {n_top} per archetype   "
                      f"({len(cdf):,} eligible names)")
    t.font = f_bold
    t.alignment = _TXT_ALIGN_LEFT
    ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=n_cols)
    ws.row_dimensions[2].height = 22
    for c in range(1, n_cols + 1):
        ws.cell(row=3, column=c).border = Border(bottom=Side(style='thin', color=INK))
    ws.row_dimensions[3].height = 4

    # Archetypes ordered by in-country match count, skip empty ones
    counts = [(col, int(cdf[col].fillna(0).sum())) for col in arch_cols]
    counts = [(col, n) for col, n in counts if n > 0]
    counts.sort(key=lambda x: -x[1])

    row = 5
    for col, n_match in counts:
        label = ARCHETYPE_LABELS.get(col, col)
        members = cdf[cdf[col].fillna(0) == 1]
        # Archetype-specific sort where one exists (ARCH_SORT_OVERRIDES);
        # falls back to entry_confirmed when the column is missing/all-NaN.
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
            _write_score(ws, row, 8 + o, r.get('entry_today_asymmetry'), font=f_bold)
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


def _write_governance_sheet(ws, gdf, n_top):
    """Flat CONVICTION-RANKED governance sheet: names ordered by governance_score
    (clearest + timeliest first — cluster insider buying, senior/10%-owner
    conviction, buy size), with the revealed-preference breakdown visible."""
    headers = ['#', 'Ticker', 'Name', 'Ctry', 'Sector', 'Mcap (USD)', 'Verdict',
               'Gov', 'Tier', 'Buyers', 'NetBuy $', 'Own %', 'P/B', 'P/E',
               'EV/EBITDA', 'FCF yld', 'Arch#']
    n_cols = len(headers)
    widths = {1: 4, 2: 12, 3: 32, 4: 6, 5: 18, 6: 13, 7: 11, 8: 7, 9: 8, 10: 7,
              11: 13, 12: 7, 13: 7, 14: 7, 15: 10, 16: 8, 17: 6}
    for col, w in widths.items():
        ws.column_dimensions[ws.cell(row=1, column=col).column_letter].width = w
    f_bold = _font(bold=True, color=INK)
    f_bold_muted = _font(bold=True, color=MUTED)
    f_text = _font(color=INK)
    f_text_muted = _font(color=MUTED)

    gdf = gdf.sort_values('governance_score', ascending=False,
                          na_position='last').head(n_top)
    t = ws.cell(row=2, column=1,
                value=f"Governance — conviction-ranked   "
                      f"({len(gdf):,} names; clearest + timeliest first)")
    t.font = f_bold
    t.alignment = _TXT_ALIGN_LEFT
    ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=n_cols)
    ws.row_dimensions[2].height = 22
    sub = ws.cell(row=3, column=1,
                  value="Weighted: insider cluster buying + senior/10%-owner conviction + buy size "
                        "(72%) > timely capital return (12%) > static ownership (10%) > low SBC (6%).")
    sub.font = _font(italic=True, color=MUTED)
    ws.merge_cells(start_row=3, start_column=1, end_row=3, end_column=n_cols)

    hdr = 5
    for i, h in enumerate(headers, start=1):
        c = ws.cell(row=hdr, column=i, value=h)
        c.font = f_bold_muted
        c.alignment = _TXT_ALIGN_LEFT if i in (2, 3, 4, 5, 9) else _NUM_ALIGN_CENTER
    for c in range(1, n_cols + 1):
        ws.cell(row=hdr, column=c).border = Border(bottom=Side(style='thin', color=INK))

    row = hdr + 1
    _t = lambda v: '' if pd.isna(v) else str(v)
    for rank, (_, r) in enumerate(gdf.iterrows(), start=1):
        _write_int(ws, row, 1, rank, font=f_text_muted)
        ws.cell(row=row, column=2, value=r['symbol']).font = f_bold
        ws.cell(row=row, column=2).alignment = _TXT_ALIGN_LEFT
        ws.cell(row=row, column=3, value=_t(r.get('name'))[:46]).font = f_text
        ws.cell(row=row, column=3).alignment = _TXT_ALIGN_LEFT
        ws.cell(row=row, column=4, value=_t(r.get('src'))).font = f_text_muted
        ws.cell(row=row, column=4).alignment = _TXT_ALIGN_LEFT
        ws.cell(row=row, column=5, value=_t(r.get('sector'))[:18]).font = f_text_muted
        ws.cell(row=row, column=5).alignment = _TXT_ALIGN_LEFT
        _write_money(ws, row, 6, r.get('market_cap'), font=f_text)
        _verdict_badge(ws, row, 7, r.get('verdict', 'UNRESEARCHED'))
        _write_score(ws, row, 8, r.get('governance_score'), font=f_bold)
        ws.cell(row=row, column=9, value=_t(r.get('governance_tier'))).font = f_text
        ws.cell(row=row, column=9).alignment = _TXT_ALIGN_LEFT
        _write_int(ws, row, 10,
                   int(r['insider_distinct_buyers']) if pd.notna(r.get('insider_distinct_buyers')) else 0,
                   font=f_text)
        _write_money(ws, row, 11, r.get('insider_net_buy_value'), font=f_text)
        _write_pct(ws, row, 12, r.get('insider_ownership_pct'), font=f_text)
        _write_score(ws, row, 13, r.get('pb'), font=f_text)
        _write_score(ws, row, 14, r.get('p_e'), font=f_text)
        _write_score(ws, row, 15, r.get('ev_ebitda'), font=f_text)
        _write_pct(ws, row, 16, r.get('fcf_yield'), font=f_text)
        _write_int(ws, row, 17,
                   int(r['archetype_count']) if pd.notna(r.get('archetype_count')) else 0,
                   font=f_text_muted)
        for c in range(1, n_cols + 1):
            ws.cell(row=row, column=c).border = Border(bottom=Side(style='thin', color=RULE))
        ws.row_dimensions[row].height = 15
        row += 1
    ws.sheet_view.showGridLines = False
    ws.freeze_panes = f'A{hdr + 1}'
    if ws.max_row > hdr:
        ws.auto_filter.ref = f"A{hdr}:{ws.cell(row=1, column=n_cols).column_letter}{ws.max_row}"


def _not_warrant(d):
    """Mask out warrant / unit / right tickers (…W / …U / …R / .WT) — their tiny
    mcap vs the whole-company balance sheet manufactures absurd net-net ratios."""
    s = d['symbol'].astype(str).str.upper()
    return ~(s.str.match(r'^[A-Z]{3,4}[WUR]$') | s.str.contains(r'\.WT$|\.U$|-WT$|-UN$|-RT$', regex=True))


def _netnet_frame(df_full):
    """The net-net population (cash+investments basis, thorough): a name trades
    below its liquidation/cash value when EITHER net current asset value (NCAV =
    current assets - total liabilities) exceeds market cap (classic Graham) OR
    net cash+investments (cash + investments - total debt) exceeds market cap.
    Returns the frame with a `netnet_ncav_pct`, `netnet_cash_pct` and a blended
    `netnet_score` (the deeper of the two, higher = cheaper vs liquidation)."""
    d = df_full.copy()
    ncav_pct = pd.to_numeric(d.get('ncav_pct_mcap'), errors='coerce')
    cash_pct = pd.to_numeric(d.get('net_cash_pct_mcap'), errors='coerce')
    mc = pd.to_numeric(d.get('market_cap_usd'), errors='coerce').fillna(
        pd.to_numeric(d.get('market_cap'), errors='coerce'))
    d['netnet_ncav_pct'] = ncav_pct
    d['netnet_cash_pct'] = cash_pct
    # EXCLUDE financials / REITs / insurers / lenders: their "cash" is customer
    # deposits / float, not shareholder cash, so the net-cash net-net is
    # meaningless there (a bank at 19x "net cash" is deposits). Net-net is a
    # Graham OPERATING-company concept.
    _sec = d.get('sector', '').astype(str).str.lower()
    _ind = (d.get('industry', '').astype(str).str.lower()
            if 'industry' in d.columns else _sec)
    _fin = (_sec.str.contains('financ') | _sec.str.contains('real estate')
            | _sec.str.contains('insur') | _sec.str.contains('bank')
            | _ind.str.contains('bank|insur|capital market|asset manage|'
                                'closed-end|business development|reinsurance', regex=True)).fillna(False)
    # BURN guard: not a melting shell (deeply negative returns AND burning cash
    # erode the discount before it closes — SOS at roce -23%).
    _roce = pd.to_numeric(d.get('roce'), errors='coerce')
    _fcfy = pd.to_numeric(d.get('fcf_yield'), errors='coerce')
    _melting = ((_roce < -0.20) & ~(_fcfy > 0)).fillna(False)
    is_nn = ((ncav_pct >= 1.0) | (cash_pct >= 1.0)) & (mc >= 10e6) & ~_fin & ~_melting & _not_warrant(d)
    if 'is_price_ghost' in d.columns:
        is_nn = is_nn & ~(pd.to_numeric(d['is_price_ghost'], errors='coerce') == 1)
    if 'data_quality_flag' in d.columns:   # never surface a corrupt-level name as a net-net
        is_nn = is_nn & ~(pd.to_numeric(d['data_quality_flag'], errors='coerce') == 1)
    d = d[is_nn.fillna(False)].copy()
    d['netnet_score'] = pd.concat([d['netnet_ncav_pct'], d['netnet_cash_pct']],
                                  axis=1).max(axis=1)
    return d


def _write_netnet_sheet(ws, nn, n_top, sort_col='netnet_score'):
    """Flat ranked net-net sheet with the cash+investments breakdown."""
    headers = ['#', 'Ticker', 'Name', 'Ctry', 'Sector', 'Mcap (USD)', 'Verdict',
               'NCAV/mcap', 'NetCash+Inv/mcap', 'Cash', 'Investments', 'P/B',
               'P/E', 'FCF yld', 'Gov', 'Arch#']
    n_cols = len(headers)
    widths = {1: 4, 2: 12, 3: 30, 4: 6, 5: 16, 6: 13, 7: 11, 8: 11, 9: 16,
              10: 13, 11: 13, 12: 7, 13: 7, 14: 8, 15: 7, 16: 6}
    for col, w in widths.items():
        ws.column_dimensions[ws.cell(row=1, column=col).column_letter].width = w
    f_bold = _font(bold=True, color=INK)
    f_bold_muted = _font(bold=True, color=MUTED)
    f_text = _font(color=INK)
    f_text_muted = _font(color=MUTED)

    nn = nn.sort_values(sort_col, ascending=False, na_position='last').head(n_top)
    t = ws.cell(row=2, column=1,
                value=f"Net-Nets — below liquidation / cash value   "
                      f"({len(nn):,} names; NCAV>mcap OR net cash+investments>mcap)")
    t.font = f_bold
    t.alignment = _TXT_ALIGN_LEFT
    ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=n_cols)
    ws.row_dimensions[2].height = 22
    sub = ws.cell(row=3, column=1,
                  value="Graham net-current-asset value and net cash+investments, both as a multiple "
                        "of market cap (>1.0 = trading below it). EDGAR/Yahoo-reconciled levels.")
    sub.font = _font(italic=True, color=MUTED)
    ws.merge_cells(start_row=3, start_column=1, end_row=3, end_column=n_cols)

    hdr = 5
    for i, h in enumerate(headers, start=1):
        c = ws.cell(row=hdr, column=i, value=h)
        c.font = f_bold_muted
        c.alignment = _TXT_ALIGN_LEFT if i in (2, 3, 4, 5) else _NUM_ALIGN_CENTER
    for c in range(1, n_cols + 1):
        ws.cell(row=hdr, column=c).border = Border(bottom=Side(style='thin', color=INK))

    row = hdr + 1
    _t = lambda v: '' if pd.isna(v) else str(v)
    for rank, (_, r) in enumerate(nn.iterrows(), start=1):
        _write_int(ws, row, 1, rank, font=f_text_muted)
        ws.cell(row=row, column=2, value=r['symbol']).font = f_bold
        ws.cell(row=row, column=2).alignment = _TXT_ALIGN_LEFT
        ws.cell(row=row, column=3, value=_t(r.get('name'))[:44]).font = f_text
        ws.cell(row=row, column=3).alignment = _TXT_ALIGN_LEFT
        ws.cell(row=row, column=4, value=_t(r.get('src'))).font = f_text_muted
        ws.cell(row=row, column=4).alignment = _TXT_ALIGN_LEFT
        ws.cell(row=row, column=5, value=_t(r.get('sector'))[:16]).font = f_text_muted
        ws.cell(row=row, column=5).alignment = _TXT_ALIGN_LEFT
        _write_money(ws, row, 6, r.get('market_cap'), font=f_text)
        _verdict_badge(ws, row, 7, r.get('verdict', 'UNRESEARCHED'))
        _write_score(ws, row, 8, r.get('netnet_ncav_pct'), font=f_bold)
        _write_score(ws, row, 9, r.get('netnet_cash_pct'), font=f_text)
        _write_money(ws, row, 10, r.get('cash'), font=f_text)
        _write_money(ws, row, 11, r.get('investments_associates'), font=f_text)
        _write_score(ws, row, 12, r.get('pb'), font=f_text)
        _write_score(ws, row, 13, r.get('p_e'), font=f_text)
        _write_pct(ws, row, 14, r.get('fcf_yield'), font=f_text)
        _write_score(ws, row, 15, r.get('governance_score'), font=f_text)
        _write_int(ws, row, 16,
                   int(r['archetype_count']) if pd.notna(r.get('archetype_count')) else 0,
                   font=f_text_muted)
        for c in range(1, n_cols + 1):
            ws.cell(row=row, column=c).border = Border(bottom=Side(style='thin', color=RULE))
        ws.row_dimensions[row].height = 15
        row += 1
    ws.sheet_view.showGridLines = False
    ws.freeze_panes = f'A{hdr + 1}'
    if ws.max_row > hdr:
        ws.auto_filter.ref = f"A{hdr}:{ws.cell(row=1, column=n_cols).column_letter}{ws.max_row}"


def _write_flat_sheet(ws, df, title, subtitle, colspecs, sort_col, ascending=False, n_top=400):
    """Generic flat ranked sheet. colspecs: list of (header, key, kind, width)
    where kind in {int,money,pct,score,text,flag}."""
    df = df.sort_values(sort_col, ascending=ascending, na_position='last').head(n_top)
    n_cols = len(colspecs)
    for i, (_, _, _, w) in enumerate(colspecs, start=1):
        ws.column_dimensions[ws.cell(row=1, column=i).column_letter].width = w
    f_bold = _font(bold=True, color=INK); f_bm = _font(bold=True, color=MUTED)
    f_text = _font(color=INK)
    t = ws.cell(row=2, column=1, value=f"{title}   ({len(df):,} names)")
    t.font = f_bold; t.alignment = _TXT_ALIGN_LEFT
    ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=n_cols)
    ws.row_dimensions[2].height = 22
    sc = ws.cell(row=3, column=1, value=subtitle); sc.font = _font(italic=True, color=MUTED)
    ws.merge_cells(start_row=3, start_column=1, end_row=3, end_column=n_cols)
    hdr = 5
    for i, (h, _, kind, _) in enumerate(colspecs, start=1):
        c = ws.cell(row=hdr, column=i, value=h); c.font = f_bm
        c.alignment = _TXT_ALIGN_LEFT if kind == 'text' else _NUM_ALIGN_CENTER
    for c in range(1, n_cols + 1):
        ws.cell(row=hdr, column=c).border = Border(bottom=Side(style='thin', color=INK))
    row = hdr + 1
    _t = lambda v: '' if pd.isna(v) else str(v)
    for rank, (_, r) in enumerate(df.iterrows(), start=1):
        for i, (_, key, kind, _) in enumerate(colspecs, start=1):
            if key == '#':
                _write_int(ws, row, i, rank, font=_font(color=MUTED)); continue
            v = r.get(key)
            if kind == 'text':
                cell = ws.cell(row=row, column=i, value=_t(v)[:44]); cell.font = f_text
                cell.alignment = _TXT_ALIGN_LEFT
            elif kind == 'money':
                _write_money(ws, row, i, v, font=f_text)
            elif kind == 'pct':
                _write_pct(ws, row, i, v, font=f_text)
            elif kind == 'score':
                _write_score(ws, row, i, v, font=(f_bold if i == 2 else f_text))
            elif kind == 'int':
                _write_int(ws, row, i, int(v) if pd.notna(v) else 0, font=f_text)
            elif kind == 'flag':
                ws.cell(row=row, column=i, value=('Y' if v == 1 else '')).font = f_text
                ws.cell(row=row, column=i).alignment = _NUM_ALIGN_CENTER
            elif kind == 'verdict':
                _verdict_badge(ws, row, i, r.get('verdict', 'UNRESEARCHED'))
        for c in range(1, n_cols + 1):
            ws.cell(row=row, column=c).border = Border(bottom=Side(style='thin', color=RULE))
        ws.row_dimensions[row].height = 15
        row += 1
    ws.sheet_view.showGridLines = False
    ws.freeze_panes = f'A{hdr + 1}'
    if ws.max_row > hdr:
        ws.auto_filter.ref = f"A{hdr}:{ws.cell(row=1, column=n_cols).column_letter}{ws.max_row}"


def _write_unlock_sheet(ws, uf, n_top):
    """Cheap + live value-unlock catalyst, conviction-ranked (value_unlock_score),
    with the forensic-confirmation flag and the phrases that fired."""
    headers = ['#', 'Ticker', 'Name', 'Ctry', 'Sector', 'Mcap (USD)', 'Verdict',
               'Unlock', 'Confirmed', 'P/B', 'FCF yld', 'Gov', 'Unlock phrases']
    n_cols = len(headers)
    widths = {1: 4, 2: 11, 3: 28, 4: 6, 5: 15, 6: 13, 7: 11, 8: 8, 9: 9, 10: 7,
              11: 8, 12: 7, 13: 60}
    for col, w in widths.items():
        ws.column_dimensions[ws.cell(row=1, column=col).column_letter].width = w
    f_bold = _font(bold=True, color=INK); f_bm = _font(bold=True, color=MUTED)
    f_text = _font(color=INK); f_tm = _font(color=MUTED)
    uf = uf.sort_values('value_unlock_score', ascending=False, na_position='last').head(n_top)
    t = ws.cell(row=2, column=1, value=f"Value-Unlock — cheap + live catalyst, conviction-ranked  ({len(uf):,} names)")
    t.font = f_bold; t.alignment = _TXT_ALIGN_LEFT
    ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=n_cols)
    ws.row_dimensions[2].height = 22
    sub = ws.cell(row=3, column=1, value="value_unlock_score = catalyst (distinctive/fresh language or structured event) x forensic confirmation (+60%) x execution footprint (+25%) x alignment (+15%). 'Confirmed' = the forensics prove real hidden value to unlock.")
    sub.font = _font(italic=True, color=MUTED)
    ws.merge_cells(start_row=3, start_column=1, end_row=3, end_column=n_cols)
    hdr = 5
    for i, h in enumerate(headers, start=1):
        c = ws.cell(row=hdr, column=i, value=h); c.font = f_bm
        c.alignment = _TXT_ALIGN_LEFT if i in (2, 3, 4, 5, 13) else _NUM_ALIGN_CENTER
    for c in range(1, n_cols + 1):
        ws.cell(row=hdr, column=c).border = Border(bottom=Side(style='thin', color=INK))
    row = hdr + 1
    _t = lambda v: '' if pd.isna(v) else str(v)
    for rank, (_, r) in enumerate(uf.iterrows(), start=1):
        _write_int(ws, row, 1, rank, font=f_tm)
        ws.cell(row=row, column=2, value=r['symbol']).font = f_bold
        ws.cell(row=row, column=2).alignment = _TXT_ALIGN_LEFT
        ws.cell(row=row, column=3, value=_t(r.get('name'))[:40]).font = f_text
        ws.cell(row=row, column=3).alignment = _TXT_ALIGN_LEFT
        ws.cell(row=row, column=4, value=_t(r.get('src'))).font = f_tm
        ws.cell(row=row, column=4).alignment = _TXT_ALIGN_LEFT
        ws.cell(row=row, column=5, value=_t(r.get('sector'))[:15]).font = f_tm
        ws.cell(row=row, column=5).alignment = _TXT_ALIGN_LEFT
        _write_money(ws, row, 6, r.get('market_cap'), font=f_text)
        _verdict_badge(ws, row, 7, r.get('verdict', 'UNRESEARCHED'))
        _write_score(ws, row, 8, r.get('value_unlock_score'), font=f_bold)
        ws.cell(row=row, column=9, value=('YES' if r.get('value_unlock_confirmed') == 1 else '')).font = f_text
        ws.cell(row=row, column=9).alignment = _NUM_ALIGN_CENTER
        _write_score(ws, row, 10, r.get('pb'), font=f_text)
        _write_pct(ws, row, 11, r.get('fcf_yield'), font=f_text)
        _write_score(ws, row, 12, r.get('governance_score'), font=f_text)
        ws.cell(row=row, column=13, value=_t(r.get('unlock_phrases'))[:90]).font = f_tm
        ws.cell(row=row, column=13).alignment = _TXT_ALIGN_LEFT
        for c in range(1, n_cols + 1):
            ws.cell(row=row, column=c).border = Border(bottom=Side(style='thin', color=RULE))
        ws.row_dimensions[row].height = 15
        row += 1
    ws.sheet_view.showGridLines = False
    ws.freeze_panes = f'A{hdr + 1}'
    if ws.max_row > hdr:
        ws.auto_filter.ref = f"A{hdr}:{ws.cell(row=1, column=n_cols).column_letter}{ws.max_row}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--n', type=int, default=30,
                    help='top N per archetype per country')
    ap.add_argument('--min-names', type=int, default=25,
                    help='minimum eligible names for a country to get a sheet')
    ap.add_argument('--global-n', type=int, default=100,
                    help='top N per archetype on the GLOBAL sheet')
    ap.add_argument('--out', default='country_archetype_book.xlsx')
    ap.add_argument('--min-mcap', type=float, default=0,
                    help='USD market-cap floor (e.g. 2e9 for a mid-cap-\n                         and-above book). 0 = full universe.')
    add_otc_mode_arg(ap)
    add_high_filter_arg(ap)
    ap.add_argument('--max-ret-12m', type=float, default=None,
                    help='keep only names whose trailing 12-month return '
                         '(momentum_12m, fallback price_yoy) is BELOW this '
                         '(e.g. 0.0 for a beaten-down / 12m-ret<0 book). '
                         'Off by default.')
    ap.add_argument('--max-pe', type=float, default=None,
                    help='cheap-multiple filter: keep names with a POSITIVE '
                         'p_e below this (OR-combined with --max-ev).')
    ap.add_argument('--max-ev', type=float, default=None,
                    help='cheap-multiple filter: keep names with a POSITIVE '
                         'ev_ebitda OR ev_ebit below this (OR-combined with '
                         '--max-pe). e.g. --max-pe 8 --max-ev 8 for a '
                         'P/E<8-or-EV<8 universe.')
    ap.add_argument('--max-pb', type=float, default=None,
                    help='keep names with P/B below this (e.g. 1.05 for a '
                         'below-book book with a small margin of error). A '
                         'low floor (pb>0.05) drops corrupt near-zero ADR/FX '
                         'artifacts. Off by default.')
    ap.add_argument('--governance-tab', action='store_true',
                    help='add a Governance sheet: names in the (filtered) '
                         'universe carrying a positive governance signal — '
                         'owner-operator alignment, insider open-market buying, '
                         'no dilution, capital discipline, or low SBC.')
    ap.add_argument('--netnet-tab', action='store_true',
                    help='add Net-Nets and Net-Net Governance sheets (scanned '
                         'across the FULL universe, cash+investments basis).')
    ap.add_argument('--unlock-tab', action='store_true',
                    help='add a Value-Unlock sheet: cheap names with a live '
                         'value-unlock catalyst, ranked by value_unlock_score '
                         '(language x forensics x footprint x alignment).')
    ap.add_argument('--nnwc-tab', action='store_true',
                    help='add a Quality Net-Nets sheet (Graham NNWC: cash 100%% '
                         '/ receivables 85%% / inventory 50%% - all liabilities).')
    ap.add_argument('--adjpb-tab', action='store_true',
                    help='add a Forensic Adjusted P/B sheet (tangible book + '
                         'hidden assets - hidden liabilities).')
    args = ap.parse_args()

    df, arch_cols = load_data(min_mcap=args.min_mcap, otc_mode='all')
    df = apply_otc_mode(df, args.otc_mode)
    df = apply_high_filter(df, args.high_filter)
    df_full = df.copy()   # pre-value-filter universe (for net-net / unlock tabs)
    if args.unlock_tab and os.path.exists('value_unlock_signals.csv'):
        _vu = pd.read_csv('value_unlock_signals.csv').drop_duplicates('symbol')
        if 'unlock_phrases' in _vu.columns:
            df_full = df_full.merge(_vu[['symbol', 'unlock_phrases']], on='symbol', how='left')
    if args.max_pb is not None:
        _pb = pd.to_numeric(df.get('pb'), errors='coerce')
        _dq = pd.to_numeric(df.get('data_quality_flag'), errors='coerce').fillna(0)
        df = df[(_pb > 0.05) & (_pb < args.max_pb) & (_dq == 0)].copy()
        print(f'  P/B filter (0.05 < P/B < {args.max_pb}): {len(df):,} names kept',
              file=sys.stderr)
    if args.max_ret_12m is not None:
        _ret12 = (pd.to_numeric(df.get('momentum_12m'), errors='coerce')
                  .fillna(pd.to_numeric(df.get('price_yoy'), errors='coerce')))
        df = df[_ret12 < args.max_ret_12m].copy()
        print(f'  12m-return filter (<{args.max_ret_12m:+.2f}): {len(df):,} names kept',
              file=sys.stderr)
    if args.max_pe is not None or args.max_ev is not None:
        _pe = pd.to_numeric(df.get('p_e'), errors='coerce')
        _eve = pd.to_numeric(df.get('ev_ebitda'), errors='coerce')
        _evb = pd.to_numeric(df.get('ev_ebit'), errors='coerce')
        _cheap = pd.Series(False, index=df.index)
        if args.max_pe is not None:
            _cheap = _cheap | ((_pe > 0) & (_pe < args.max_pe))
        if args.max_ev is not None:
            _cheap = _cheap | ((_eve > 0) & (_eve < args.max_ev)) \
                            | ((_evb > 0) & (_evb < args.max_ev))
        df = df[_cheap.fillna(False)].copy()
        print(f'  cheap-multiple filter (P/E<{args.max_pe} OR EV<{args.max_ev}): '
              f'{len(df):,} names kept', file=sys.stderr)
    df['src'] = df['src'].fillna('').astype(str).str.upper()
    print(f'  {len(df):,} eligible rows, {len(arch_cols)} archetypes',
          file=sys.stderr)

    wb = Workbook()
    cover = wb.active
    tab_colors.set_tab(cover, tab_colors.COVER)
    cover.title = 'Cover'
    for col, w in {1: 8, 2: 22, 3: 12, 4: 14, 5: 30}.items():
        cover.column_dimensions[cover.cell(row=1, column=col).column_letter].width = w
    _crimson_banner(cover, 2, 'COUNTRY x ARCHETYPE', span_cols=5)
    sub = cover.cell(row=4, column=1,
                     value=f'Top {args.n} names per archetype within each market '
                           f'— so no single country dominates the ranking'
                     + ('   \u00b7  MID-CAP & ABOVE only (\u2265$%.0fB)' % (args.min_mcap/1e9) if args.min_mcap >= 1e9 else ''))
    sub.font = _font(italic=True, color=MUTED)
    sub.alignment = _TXT_ALIGN_LEFT
    f_bold_muted = _font(bold=True, color=MUTED)
    f_text = _font(color=INK)
    f_text_muted = _font(color=MUTED)

    order = (df.groupby('src').size().sort_values(ascending=False))
    # Country tabs organized DM-first, grouped by region (region_map), and
    # by name count within each region.
    countries = ordered_countries(
        [c for c, n in order.items() if c and n >= args.min_names])
    df['_bucket'], df['_region'] = zip(*df['src'].map(classify))

    _section_rule(cover, 7, 'Markets (DM by region, then EM)', span_cols=5)
    for i, h in enumerate(['#', 'Market', 'Names', 'Multi-arch', 'Top name by ETA'], start=1):
        cover.cell(row=8, column=i, value=h).font = f_bold_muted
    r = 9
    _last_region = None
    for i, ctry in enumerate(countries, start=1):
        cdf = df[df['src'] == ctry]
        _bucket, _region = classify(ctry)
        if _region != _last_region:
            cover.cell(row=r, column=2,
                       value=f'{_bucket} — {_region}').font = f_bold_muted
            r += 1
            _last_region = _region
        _write_int(cover, r, 1, i, font=f_text_muted)
        cover.cell(row=r, column=2, value=ctry).font = f_text
        _write_int(cover, r, 3, len(cdf), font=f_text)
        _write_int(cover, r, 4, int((cdf['archetype_count'].fillna(0) >= 2).sum()),
                   font=f_text)
        top = cdf.sort_values(SORT_COL, ascending=False, na_position='last').head(1)
        cover.cell(row=r, column=5,
                   value=(top.iloc[0]['symbol'] if len(top) else '—')).font = f_text_muted
        r += 1

    # Aggregate sheets first (each with a Ctry column): GLOBAL, then the
    # DM / EM buckets, then each region — the cross-market best of every
    # pattern at every level of aggregation, beside the country partitions.
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

    # Governance sheet (opt-in): the subset of the filtered universe that carries
    # a POSITIVE GOVERNANCE signal — revealed-preference alignment and
    # shareholder-friendly capital allocation. Fires on any of: owner-operator
    # (skin in the game), insider open-market BUYING (Form 4 cluster/officer/
    # 10%-owner), no dilution, capital discipline, low SBC, or a strong insider
    # stake that is NOT being diluted. Shown in the same archetype-grouped
    # layout as GLOBAL so the governance-positive cheap names surface by pattern.
    if args.governance_tab:
        _gsc = pd.to_numeric(df.get('governance_score'), errors='coerce')
        # drop trivial single-hygiene names; the sheet then RANKS by conviction
        gov_df = df[_gsc >= 0.15].copy()
        if not gov_df.empty:
            ws = wb.create_sheet(_sheet_safe('Governance'))
            tab_colors.set_tab(ws, tab_colors.AGGREGATE)
            _write_governance_sheet(ws, gov_df, max(args.global_n * 4, 400))
            n_agg_sheets += 1
            _hi = int((pd.to_numeric(gov_df['governance_score'], errors='coerce') >= 0.60).sum())
            print(f'  Governance: {len(gov_df):,} names (score>=0.15), {_hi} High-conviction',
                  file=sys.stderr)

    # Net-Nets + Net-Net Governance (opt-in): scanned across the FULL universe
    # (not the P/B-filtered subset), cash+investments basis. The second sheet is
    # the intersection with governance conviction — cheap-to-liquidation AND
    # insider-aligned, the highest-conviction deep value.
    if args.netnet_tab:
        nn = _netnet_frame(df_full)
        if not nn.empty:
            ws = wb.create_sheet(_sheet_safe('Net-Nets'))
            tab_colors.set_tab(ws, tab_colors.AGGREGATE)
            _write_netnet_sheet(ws, nn, max(args.global_n * 4, 400))
            n_agg_sheets += 1
            _gsc = pd.to_numeric(nn.get('governance_score'), errors='coerce')
            nn_gov = nn[_gsc >= 0.15]
            if not nn_gov.empty:
                ws = wb.create_sheet(_sheet_safe('Net-Net Governance'))
                tab_colors.set_tab(ws, tab_colors.AGGREGATE)
                _write_netnet_sheet(ws, nn_gov, max(args.global_n * 4, 300),
                                    sort_col='governance_score')
                n_agg_sheets += 1
            print(f'  Net-Nets: {len(nn):,} names ({len(nn_gov):,} with governance signal)',
                  file=sys.stderr)

    # Value-Unlock (opt-in): cheap names with a live value-unlock catalyst,
    # conviction-ranked, from the FULL universe (arch_xr_value_unlock members).
    if args.unlock_tab and 'arch_xr_value_unlock' in df_full.columns:
        uf = df_full[pd.to_numeric(df_full['arch_xr_value_unlock'], errors='coerce') == 1].copy()
        if not uf.empty:
            ws = wb.create_sheet(_sheet_safe('Value-Unlock'))
            tab_colors.set_tab(ws, tab_colors.AGGREGATE)
            _write_unlock_sheet(ws, uf, max(args.global_n * 4, 400))
            n_agg_sheets += 1
            _conf = int((pd.to_numeric(uf.get('value_unlock_confirmed'), errors='coerce') == 1).sum())
            print(f'  Value-Unlock: {len(uf):,} names ({_conf} forensically confirmed)',
                  file=sys.stderr)

    # Quality Net-Nets (#1): Graham NNWC (haircut current assets) > market cap.
    if args.nnwc_tab and 'nnwc_pct_mcap' in df_full.columns:
        _np = pd.to_numeric(df_full['nnwc_pct_mcap'], errors='coerce')
        _dq = pd.to_numeric(df_full.get('data_quality_flag'), errors='coerce').fillna(0)
        qn = df_full[(_np >= 1.0) & (_dq == 0) & _not_warrant(df_full)].copy()
        if 'is_price_ghost' in qn.columns:
            qn = qn[~(pd.to_numeric(qn['is_price_ghost'], errors='coerce') == 1)]
        if not qn.empty:
            ws = wb.create_sheet(_sheet_safe('Quality Net-Nets'))
            tab_colors.set_tab(ws, tab_colors.AGGREGATE)
            _write_flat_sheet(ws, qn,
                'Quality Net-Nets — Graham NNWC (cash 100% / receivables 85% / inventory 50% - all liabilities)',
                'NNWC/mcap > 1 = trading below quality-adjusted liquidation value. asset-mix = cash share (higher = safer). Holdco/China flags note distributable-cash / VIE risk.',
                [('#', '#', 'int', 4), ('Ticker', 'symbol', 'text', 11), ('Name', 'name', 'text', 26),
                 ('Ctry', 'src', 'text', 6), ('Sector', 'sector', 'text', 15), ('Mcap (USD)', 'market_cap', 'money', 13),
                 ('Verdict', 'verdict', 'verdict', 11), ('NNWC/mcap', 'nnwc_pct_mcap', 'score', 10),
                 ('NCAV/mcap', 'ncav_pct_mcap', 'score', 10), ('Cash mix', 'nnwc_asset_mix', 'score', 9),
                 ('NNWC $', 'nnwc', 'money', 13), ('P/B', 'pb', 'score', 7), ('FCF yld', 'fcf_yield', 'pct', 8),
                 ('Holdco', 'holdco_flag', 'flag', 7), ('China/VIE', 'china_vie_flag', 'flag', 9),
                 ('Gov', 'governance_score', 'score', 7)],
                sort_col='nnwc_pct_mcap', ascending=False, n_top=max(args.global_n * 5, 500))
            n_agg_sheets += 1
            print(f'  Quality Net-Nets: {len(qn):,} names', file=sys.stderr)

    # Forensic Adjusted P/B (#6): tangible book + hidden assets - hidden liabs.
    if args.adjpb_tab and 'adjusted_pb' in df_full.columns:
        _apb = pd.to_numeric(df_full['adjusted_pb'], errors='coerce')
        _dq = pd.to_numeric(df_full.get('data_quality_flag'), errors='coerce').fillna(0)
        ap = df_full[(_apb > 0.05) & (_apb < 1.0) & (_dq == 0) & _not_warrant(df_full)].copy()
        if 'is_price_ghost' in ap.columns:
            ap = ap[~(pd.to_numeric(ap['is_price_ghost'], errors='coerce') == 1)]
        if not ap.empty:
            ws = wb.create_sheet(_sheet_safe('Adjusted P-B'))
            tab_colors.set_tab(ws, tab_colors.AGGREGATE)
            _write_flat_sheet(ws, ap,
                'Forensic Adjusted P/B — tangible book + hidden assets (LIFO / pension surplus / stake FV gap) - hidden liabilities',
                'adjusted_pb = mcap / adjusted_book, below 1 = below the forensic true book. Compare vs the naive P/B.',
                [('#', '#', 'int', 4), ('Ticker', 'symbol', 'text', 11), ('Name', 'name', 'text', 28),
                 ('Ctry', 'src', 'text', 6), ('Sector', 'sector', 'text', 15), ('Mcap (USD)', 'market_cap', 'money', 13),
                 ('Verdict', 'verdict', 'verdict', 11), ('Adj P/B', 'adjusted_pb', 'score', 8),
                 ('Naive P/B', 'pb', 'score', 9), ('P/TB', 'p_tb', 'score', 7),
                 ('Adj book $', 'adjusted_book', 'money', 13), ('FCF yld', 'fcf_yield', 'pct', 8),
                 ('Gov', 'governance_score', 'score', 7), ('Arch#', 'archetype_count', 'int', 6)],
                sort_col='adjusted_pb', ascending=True, n_top=max(args.global_n * 5, 500))
            n_agg_sheets += 1
            print(f'  Adjusted P/B: {len(ap):,} names below adjusted book', file=sys.stderr)

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
