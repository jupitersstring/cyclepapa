"""OTC-universe top-N-by-archetype book.

The global archetype book spans every exchange; OTC / Pink-Sheet names get
buried by better-covered listed names. This book restricts to the US
over-the-counter universe (FinanceDatabase exchanges PNK / OQX / OQB —
OTC Pink, OTCQX, OTCQB) and shows the top N per archetype WITHIN it, so
the best OTC representative of each pattern is visible.

OTC membership comes from otc_symbols.csv (symbol,exchange), produced from
FinanceDatabase. Reuses load_data + labels + the per-archetype table
writer from build_archetype_book, and the Harvard styling.

Output: otc_archetype_book.xlsx
"""
from __future__ import annotations
import argparse
import os
import sys

import pandas as pd

from build_harvard_workbook import (
    Workbook, INK, MUTED, _font, _crimson_banner, _section_rule, _write_int,
    _TXT_ALIGN_LEFT,
)
from build_archetype_book import (
    load_data, ARCHETYPE_LABELS, _sheet_safe, _write_archetype_table,
)

SORT_COL = 'entry_confirmed'
OTC_MAP = 'otc_symbols.csv'


def load_otc_symbols() -> set:
    if not os.path.exists(OTC_MAP):
        print(f'  WARNING: {OTC_MAP} missing — no OTC filter applied', file=sys.stderr)
        return set()
    try:
        return set(pd.read_csv(OTC_MAP, usecols=['symbol'])['symbol'].dropna())
    except Exception as e:
        print(f'  WARNING: could not read {OTC_MAP}: {e}', file=sys.stderr)
        return set()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--n', type=int, default=30, help='top N per archetype')
    ap.add_argument('--min-mcap', type=float, default=2_000_000,
                    help='min USD market cap (OTC is inherently tiny)')
    ap.add_argument('--out', default='otc_archetype_book.xlsx')
    args = ap.parse_args()

    df, arch_cols = load_data(min_mcap=args.min_mcap, otc_mode='all')
    otc = load_otc_symbols()
    if otc:
        df = df[df['symbol'].isin(otc)].copy()
    n_total = len(df)
    print(f'  {n_total:,} OTC rows (of universe), {len(arch_cols)} archetypes',
          file=sys.stderr)

    wb = Workbook()
    cover = wb.active
    cover.title = 'Cover'
    for col, w in {1: 30, 2: 10, 3: 12, 4: 30}.items():
        cover.column_dimensions[cover.cell(row=1, column=col).column_letter].width = w
    _crimson_banner(cover, 2, 'OTC UNIVERSE x ARCHETYPE', span_cols=4)
    sub = cover.cell(row=4, column=1,
                     value=f'Top {args.n} per archetype among US OTC names '
                           f'(Pink / OTCQX / OTCQB) — {n_total:,} eligible')
    sub.font = _font(italic=True, color=MUTED)
    sub.alignment = _TXT_ALIGN_LEFT
    f_bold_muted = _font(bold=True, color=MUTED)
    f_text = _font(color=INK)

    # Rank archetypes by in-OTC match count; skip empties
    counts = [(c, int(df[c].fillna(0).sum())) for c in arch_cols]
    counts = [(c, n) for c, n in counts if n > 0]
    counts.sort(key=lambda x: -x[1])

    _section_rule(cover, 7, 'Archetypes (by OTC matches)', span_cols=4)
    for i, h in enumerate(['Archetype', 'Matches', 'Top by ETA'], start=1):
        cover.cell(row=8, column=i, value=h).font = f_bold_muted
    r = 9
    for col, n_match in counts:
        label = ARCHETYPE_LABELS.get(col, col)
        sheet_name = _sheet_safe(label)
        c_label = cover.cell(row=r, column=1, value=label)
        c_label.font = f_text
        c_label.hyperlink = f"#'{sheet_name}'!A1"
        _write_int(cover, r, 2, n_match, font=f_text)
        top = (df[df[col].fillna(0) == 1]
               .sort_values(SORT_COL, ascending=False, na_position='last').head(1))
        cover.cell(row=r, column=3,
                   value=(top.iloc[0]['symbol'] if len(top) else '—')).font = f_text
        r += 1
    cover.sheet_view.showGridLines = False

    # One sheet per archetype: top-N OTC names
    for col, _n in counts:
        label = ARCHETYPE_LABELS.get(col, col)
        sub_df = (df[df[col].fillna(0) == 1]
                  .sort_values(SORT_COL, ascending=False, na_position='last')
                  .head(args.n).reset_index(drop=True))
        ws = wb.create_sheet(_sheet_safe(label))
        _write_archetype_table(ws, sub_df, label, n_total, SORT_COL)

    wb.save(args.out)
    print(f'wrote {args.out}  ({1 + len(counts)} sheets: Cover + '
          f'{len(counts)} archetypes)', file=sys.stderr)


if __name__ == '__main__':
    main()
