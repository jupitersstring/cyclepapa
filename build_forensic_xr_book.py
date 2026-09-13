"""Forensic-XR asymmetry book.

Ranks the universe by forensic_xr_score — size-normalized hidden/unpriced
forensic value (LIFO reserve, pension surplus, reversible DTA valuation
allowance, off-BS equity-method stakes, off-EV hidden assets, RPO backlog
gross profit), each as a fraction of market cap, combined with valuation
(x1.5 when the visible business is also cheap) and gated to a monetizable,
tradeable, non-melting opportunity. Each row breaks down the SOURCE of the
hidden value so the reader sees why it ranks.

Output: forensic_xr_book.xlsx
"""
from __future__ import annotations
import argparse
import os
import sys

import numpy as np
import pandas as pd

import tab_colors
from build_harvard_workbook import (
    Workbook,
    INK, MUTED, RULE,
    _font, _section_rule, _verdict_badge,
    _write_money, _write_pct, _write_score, _write_int,
    _TXT_ALIGN_LEFT, _NUM_ALIGN_CENTER,
)
from openpyxl.styles import Border, Side
from openpyxl.utils import get_column_letter


def load_data():
    """asymmetry_global + the forensic score/columns from archetype_tags.csv."""
    df = pd.read_csv('asymmetry_global.csv', low_memory=False).drop_duplicates('symbol')
    # forensic_xr_score / forensic_hidden_pct live in the tags output
    if os.path.exists('archetype_tags.csv'):
        t = pd.read_csv('archetype_tags.csv', low_memory=False)
        keep = ['symbol'] + [c for c in ('forensic_xr_score', 'forensic_hidden_pct')
                             if c in t.columns]
        df = df.drop(columns=[c for c in ('forensic_xr_score', 'forensic_hidden_pct')
                              if c in df.columns], errors='ignore')
        df = df.merge(t[keep].drop_duplicates('symbol'), on='symbol', how='left')

    # fresh verdicts (rolling diligence log wins over the enrich snapshot)
    frames = []
    for path, default in [('qualitative_aligned_green.csv', 'GREEN'),
                          ('qualitative_red_avoid.csv', 'RED'),
                          ('qualitative_extended_verdicts.csv', None)]:
        if not os.path.exists(path):
            continue
        try:
            d = pd.read_csv(path)
        except pd.errors.ParserError:
            d = pd.read_csv(path, engine='python', on_bad_lines='skip', quoting=3)
        if 'verdict' not in d.columns and default is not None:
            d['verdict'] = default
        frames.append(d[[c for c in ['symbol', 'verdict'] if c in d.columns]])
    if frames:
        v = pd.concat(frames, ignore_index=True).drop_duplicates('symbol', keep='last')
        df = df.drop(columns=[c for c in ('verdict',) if c in df.columns])
        df = df.merge(v, on='symbol', how='left')
    if 'verdict' not in df.columns:
        df['verdict'] = pd.NA
    df['verdict'] = df['verdict'].fillna('UNRESEARCHED')

    from otc_flag import apply_otc_mode as _apply_otc
    df = _apply_otc(df, 'ex-otc')
    if 'market_cap_usd' in df.columns:
        df['market_cap'] = (pd.to_numeric(df['market_cap_usd'], errors='coerce')
                            .fillna(pd.to_numeric(df.get('market_cap'), errors='coerce')))
    df = df[df['verdict'] != 'RED']
    df['forensic_xr_score'] = pd.to_numeric(df.get('forensic_xr_score'), errors='coerce').fillna(0)
    return df[df['forensic_xr_score'] > 0].copy()


HEADERS = ['#', 'Ticker', 'Name', 'Country', 'Sector', 'Mcap (USD)', 'Verdict',
           'ForXR score', 'Hidden %mcap',
           'Pension %', 'DTA allow %', 'LIFO %', 'Eq-stake %', 'RPO %rev',
           'EV/EBITDA', 'P/B', 'FCF yld %']
NCOLS = len(HEADERS)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--n', type=int, default=250, help='top N by forensic_xr_score')
    ap.add_argument('--out', default='forensic_xr_book.xlsx')
    args = ap.parse_args()

    print('loading data...', file=sys.stderr)
    df = load_data()
    print(f'  {len(df):,} names with a forensic_xr_score > 0', file=sys.stderr)
    df = df.sort_values('forensic_xr_score', ascending=False).head(args.n)

    n = lambda c: pd.to_numeric(df[c], errors='coerce') if c in df.columns \
        else pd.Series(np.nan, index=df.index)
    mc = n('market_cap_usd')
    # size-normalized source components (recomputed for display)
    pension = (n('pension_funded_status').clip(lower=0) / mc)
    dta = (n('deferred_tax_valuation_allowance') / mc)
    lifo = (n('lifo_reserve') / mc)
    eqst = (n('equity_method_investments') / mc)
    rpo = (n('rpo') / n('revenue_ttm_usd'))

    wb = Workbook()
    ws = wb.active
    ws.title = 'Forensic-XR'
    tab_colors.set_tab(ws, tab_colors.FAMILY_COLORS['deep_value'])

    f_bold = _font(bold=True, color=INK)
    f_italic_muted = _font(italic=True, color=MUTED)
    f_text = _font(color=INK)

    t = ws.cell(row=2, column=1, value='Forensic-XR — most asymmetric hidden value')
    t.font = f_bold
    ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=NCOLS)
    ws.row_dimensions[2].height = 22
    sub = ws.cell(row=3, column=1,
                  value='Hidden/unpriced forensic value as a share of market cap (size-comparable), '
                        'x1.5 where the visible business is also cheap; tradeable + non-melting only.')
    sub.font = f_italic_muted
    ws.merge_cells(start_row=3, start_column=1, end_row=3, end_column=NCOLS)
    _section_rule(ws, 5, 'Ranked by forensic_xr_score — components show the SOURCE of the hidden value',
                  span_cols=NCOLS)

    hdr = 6
    for i, h in enumerate(HEADERS, start=1):
        c = ws.cell(row=hdr, column=i, value=h)
        c.font = _font(bold=True, color=MUTED)
        c.alignment = _TXT_ALIGN_LEFT if i in (2, 3, 4, 5) else _NUM_ALIGN_CENTER
    for c in range(1, NCOLS + 1):
        ws.cell(row=hdr + 1, column=c).border = Border(top=Side(style='thin', color=INK))

    r = hdr + 1
    for rank, (_, row) in enumerate(df.iterrows(), start=1):
        r += 1
        i = row.name
        ws.cell(row=r, column=1, value=rank).font = f_text
        ws.cell(row=r, column=2, value=str(row.get('symbol') or '')).font = f_text
        ws.cell(row=r, column=3, value=str(row.get('name') or '')[:30]).font = f_text
        ws.cell(row=r, column=3).alignment = _TXT_ALIGN_LEFT
        ws.cell(row=r, column=4, value=str(row.get('src') or '')).font = _font(color=MUTED)
        ws.cell(row=r, column=5, value=str(row.get('sector') or '')[:14]).font = _font(color=MUTED)
        ws.cell(row=r, column=5).alignment = _TXT_ALIGN_LEFT
        _write_money(ws, r, 6, row.get('market_cap'), font=f_text)
        _v = row.get('verdict')
        _verdict_badge(ws, r, 7, _v if (pd.notna(_v) and _v) else 'UNRESEARCHED')
        _write_score(ws, r, 8, row.get('forensic_xr_score'), font=f_text)
        _write_pct(ws, r, 9, row.get('forensic_hidden_pct'), font=f_text)
        _write_pct(ws, r, 10, pension.get(i), font=f_text)
        _write_pct(ws, r, 11, dta.get(i), font=f_text)
        _write_pct(ws, r, 12, lifo.get(i), font=f_text)
        _write_pct(ws, r, 13, eqst.get(i), font=f_text)
        _write_pct(ws, r, 14, rpo.get(i), font=f_text)
        _write_score(ws, r, 15, row.get('ev_ebitda'), font=f_text)
        _write_score(ws, r, 16, row.get('pb'), font=f_text)
        _write_pct(ws, r, 17, row.get('fcf_yield'), font=f_text)
        for c in range(1, NCOLS + 1):
            ws.cell(row=r, column=c).border = Border(bottom=Side(style='thin', color=RULE))

    widths = {1: 4, 2: 9, 3: 30, 4: 6, 5: 14, 6: 13, 7: 12, 8: 11, 9: 11,
              10: 10, 11: 11, 12: 8, 13: 11, 14: 10, 15: 10, 16: 7, 17: 10}
    for col, w in widths.items():
        ws.column_dimensions[get_column_letter(col)].width = w
    ws.sheet_view.showGridLines = False
    ws.freeze_panes = f'A{hdr + 2}'
    if ws.max_row > hdr + 1:
        ws.auto_filter.ref = f"A{hdr}:{get_column_letter(NCOLS)}{ws.max_row}"

    wb.save(args.out)
    print(f'wrote {args.out}: {len(df)} rows', file=sys.stderr)


if __name__ == '__main__':
    main()
