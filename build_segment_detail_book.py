"""Per-name segment-detail workbook — what the binary archetypes hide.

Shows for every name with EDGAR or FMP segment coverage:
  - Top 3 segments by % of revenue (with names + share)
  - Largest segment $ revenue + share
  - Fastest-growing segment + YoY %
  - Geographic mix (top regions + shares)
  - Number of business segments, geographic regions, product lines
  - HHI of segment revenue concentration

Output: segment_detail_book.xlsx
  Cover           headline tiles + archetype index
  All Segments    every name with segment data, ranked by ETA
  Plus 4 per-archetype drill-downs:
  Diversified     names with 4+ segments + HHI <= 0.40
  Concentrated    HHI >= 0.70 or top segment >= 70%
  Global          4+ geographies
  Fastest         single segment growing > 25% YoY
"""
from __future__ import annotations
import argparse
import os
import sys

import pandas as pd
import tab_colors

import build_harvard_workbook as bhw
from build_harvard_workbook import (
    Workbook,
    INK, DARK_GREY, MUTED, RULE, LIGHT_GREY, PALE_GREY, WHITE,
    FONT_NAME, FONT_SIZE,
    _font, _border, _align,
    _section_rule, _verdict_badge,
    _write_money, _write_pct, _write_ratio, _write_score, _write_int,
    _NUM_ALIGN_RIGHT, _NUM_ALIGN_CENTER, _TXT_ALIGN_LEFT,
)
from openpyxl.styles import Alignment, Border, Side
from openpyxl.utils import get_column_letter


def load_data():
    """Merge asymmetry_global + segment_signals + valuation columns."""
    import glob
    import numpy as np
    df = pd.read_csv('asymmetry_global.csv').drop_duplicates('symbol')
    sig = (pd.read_csv('edgar_segment_signals.csv') if os.path.exists('edgar_segment_signals.csv')
           else pd.DataFrame(columns=['symbol']))
    # UNIVERSE = EDGAR dimensional harvest UNION FMP revenue segmentation.
    # Until now the book was hard-restricted to the EDGAR harvest (~10% of US
    # filers); FMP adds product + geographic segment revenue for every filer it
    # covers, US and non-US.
    fmp = (pd.read_csv('fmp_segments.csv', low_memory=False).drop_duplicates('symbol')
           if os.path.exists('fmp_segments.csv') else pd.DataFrame(columns=['symbol']))
    _fmp_has = pd.Series(False, index=fmp.index)
    for _c in ('fmp_seg_count', 'fmp_geo_count'):
        if _c in fmp.columns:
            _fmp_has |= pd.to_numeric(fmp[_c], errors='coerce').fillna(0) >= 1
    fmp = fmp[_fmp_has]
    keep = set(sig['symbol'].astype(str)) | set(fmp['symbol'].astype(str))
    df = df[df['symbol'].astype(str).isin(keep)].copy()
    df = df.drop(columns=[c for c in df.columns if c.endswith('_arch')])
    df = df.merge(sig, on='symbol', how='left')
    df = df.merge(fmp, on='symbol', how='left')
    _in_edgar = df['symbol'].isin(sig['symbol'])
    _in_fmp = df['symbol'].isin(fmp['symbol'])
    df['seg_source'] = np.select([_in_edgar & _in_fmp, _in_edgar, _in_fmp],
                                 ['EDGAR+FMP', 'EDGAR', 'FMP'], default='')
    # FMP fills the displayed segment fields only where EDGAR has nothing.
    # EDGAR keeps precedence (it also carries segment operating margin, which
    # FMP does not), so the forensic margin columns remain EDGAR-sourced.
    for _b, _f in (('segment_count', 'fmp_seg_count'), ('segment_revenue_hhi', 'fmp_seg_hhi'),
                   ('largest_segment_name', 'fmp_seg_largest_name'),
                   ('largest_segment_share', 'fmp_seg_largest_share'),
                   ('fastest_segment_name', 'fmp_seg_fastest_name'),
                   ('fastest_segment_yoy', 'fmp_seg_fastest_yoy'),
                   ('fastest_segment_share', 'fmp_seg_fastest_share'),
                   ('fastest_segment_share_delta', 'fmp_seg_fastest_share_delta'),
                   ('segment_growth_dispersion', 'fmp_seg_growth_dispersion'),
                   ('geographic_region_count', 'fmp_geo_count'),
                   ('largest_region_name', 'fmp_geo_largest_name'),
                   ('largest_region_share', 'fmp_geo_largest_share')):
        if _f in df.columns:
            if _b not in df.columns:
                df[_b] = np.nan
            df[_b] = df[_b].where(df[_b].notna(), df[_f])
    # top-3 segment / region strings from the FMP long-format detail (latest FY)
    if os.path.exists('fmp_segments_detail.csv'):
        det = pd.read_csv('fmp_segments_detail.csv', low_memory=False)
        det = det[det['symbol'].isin(df['symbol'])]
        if not det.empty:
            det['_fy_max'] = det.groupby(['symbol', 'axis'])['fiscal_year'].transform('max')
            det = det[det['fiscal_year'] == det['_fy_max']].sort_values('share', ascending=False)

            def _top3(g):
                return '; '.join(f"{n} ({s*100:.0f}%)" for n, s in
                                 zip(g['segment'].head(3), g['share'].head(3)))
            for _axis, _col in (('product', 'top_segments'), ('geographic', 'top_regions')):
                _t = det[det['axis'] == _axis].groupby('symbol').apply(_top3)
                if _col not in df.columns:
                    df[_col] = np.nan
                df[_col] = df[_col].where(df[_col].notna() & (df[_col].astype(str) != ''),
                                          df['symbol'].map(_t))

    # segment-archetype membership flags (from the tags output) so the book can
    # carry a tab per segment SETUP, not just the raw segment-structure cuts
    if os.path.exists('archetype_tags.csv'):
        _seg_arch = ['arch_fastest_segment', 'arch_xr_hidden_segment_compounder',
                     'arch_xr_segment_justifies_whole', 'arch_xr_margin_mixshift',
                     'segment_rot_flag',
                     'arch_concentrated_segments', 'arch_diversified_segments',
                     'arch_geographic_global']
        _at = pd.read_csv('archetype_tags.csv', low_memory=False)
        _keep = ['symbol'] + [c for c in _seg_arch if c in _at.columns]
        df = df.drop(columns=[c for c in _seg_arch if c in df.columns], errors='ignore')
        df = df.merge(_at[_keep].drop_duplicates('symbol'), on='symbol', how='left')

    # Pull valuation ratios from per-country yartseva CSVs (master is sparse)
    val_cols = ['symbol', 'ev_ebitda', 'p_e', 'pb', 'p_s', 'fcf_yield', 'roce',
                'net_debt_ebitda', 'ebitda_margin', 'momentum_12m']
    val_frames = []
    for f in sorted(glob.glob('*_yartseva.csv')):
        try:
            d = pd.read_csv(f, usecols=lambda c: c in val_cols)
        except Exception:
            continue
        if 'symbol' in d.columns:
            val_frames.append(d)
    if val_frames:
        val = pd.concat(val_frames, ignore_index=True).drop_duplicates('symbol', keep='first')
        # Only merge columns we don't already have
        merge_cols = ['symbol'] + [c for c in val.columns if c != 'symbol' and c not in df.columns]
        df = df.merge(val[merge_cols], on='symbol', how='left')

    # Fresh verdicts from the qualitative_*.csv files (the verdict column
    # asymmetry_global carries is a snapshot from the last enrich run; the
    # qualitative files are the rolling diligence log and always win) — same
    # pattern as build_archetype_book.load_data.
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
        frames.append(d[[c for c in ['symbol', 'verdict'] if c in d.columns]])
    if frames:
        v = pd.concat(frames, ignore_index=True).drop_duplicates('symbol', keep='last')
        df = df.drop(columns=[c for c in ('verdict',) if c in df.columns])
        df = df.merge(v, on='symbol', how='left')
    if 'verdict' not in df.columns:
        df['verdict'] = pd.NA
    df['verdict'] = df['verdict'].fillna('UNRESEARCHED')

    if 'entry_today_asymmetry' not in df.columns:
        df['entry_today_asymmetry'] = df.get('asymmetry_score', 0)
    df['entry_today_asymmetry'] = df['entry_today_asymmetry'].fillna(0)

    # Confirmation upweight (house doctrine: rankings upweight where
    # independent measures agree) — same shape as the archetype books'
    # entry_confirmed. Ranking key only; sheets still display raw values.
    _eta = pd.to_numeric(df['entry_today_asymmetry'], errors='coerce').fillna(0.0)
    _cfo = pd.to_numeric(df.get('confirm_overall'), errors='coerce').fillna(0.0)
    _bbs = pd.to_numeric(df.get('buyback_score'), errors='coerce').fillna(0.0)
    df['entry_confirmed'] = _eta * (1.0 + 0.20 * _cfo + 0.10 * _bbs)

    from otc_flag import apply_otc_mode as _apply_otc
    df = _apply_otc(df, 'ex-otc')   # general books: genuine listings only
    # USD-normalise market cap so the $10M gate is comparable across markets
    # (same idiom as build_archetype_book.load_data).
    if 'market_cap_usd' in df.columns:
        df['market_cap'] = (pd.to_numeric(df['market_cap_usd'], errors='coerce')
                            .fillna(pd.to_numeric(df['market_cap'], errors='coerce')))
    if 'market_cap' in df.columns:
        df = df[df['market_cap'].fillna(0) >= 10_000_000]
    df = df[df['verdict'] != 'RED']
    return df


def _sheet_safe(s: str) -> str:
    out = ''.join(ch if ch.isalnum() or ch in '_+- ' else '_' for ch in str(s))
    return out[:31]


def _write_segment_table(ws, df_subset, label, n_total, sort_col='entry_confirmed'):
    f_bold = _font(bold=True, color=INK)
    f_bold_muted = _font(bold=True, color=MUTED)
    f_text = _font(color=INK)
    f_text_muted = _font(color=MUTED)
    f_italic_muted = _font(italic=True, color=MUTED)

    NCOLS = 31   # 28 original + Src, EM rev %, China rev %
    # Title
    t = ws.cell(row=2, column=1, value=label)
    t.font = f_bold
    t.alignment = _TXT_ALIGN_LEFT
    ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=NCOLS)
    ws.row_dimensions[2].height = 22
    for c in range(1, NCOLS + 1):
        ws.cell(row=3, column=c).border = Border(bottom=Side(style='thin', color=INK))
    ws.row_dimensions[3].height = 4

    # Headline tiles
    n_match = len(df_subset)
    pct_universe = (n_match / n_total * 100) if n_total else 0
    n_diverse = int((df_subset['segment_count'].fillna(0) >= 4).sum())
    n_concentrated = int((df_subset['segment_revenue_hhi'].fillna(0) >= 0.7).sum())
    n_global = int((df_subset['geographic_region_count'].fillna(0) >= 4).sum())
    fastest_row = df_subset.dropna(subset=['fastest_segment_yoy']).nlargest(1, 'fastest_segment_yoy')
    fastest_label = (f"{fastest_row.iloc[0]['symbol']} {fastest_row.iloc[0]['fastest_segment_name']} "
                     f"+{fastest_row.iloc[0]['fastest_segment_yoy']*100:.0f}%"
                     if len(fastest_row) else "—")

    headline = [
        ("MATCHES", f"{n_match:,}", f"{pct_universe:.1f}% of segment-covered"),
        ("DIVERSIFIED", f"{n_diverse:,}", "4+ segments"),
        ("CONCENTRATED", f"{n_concentrated:,}", "HHI >= 0.70"),
        ("GLOBAL", f"{n_global:,}", "4+ regions"),
        ("FASTEST", fastest_label[:24], "yoy among matches"),
    ]
    for i, (lbl, val, sub) in enumerate(headline):
        col = 1 + i * 4
        ws.cell(row=5, column=col, value=lbl).font = f_italic_muted
        ws.cell(row=5, column=col).alignment = _TXT_ALIGN_LEFT
        ws.cell(row=6, column=col, value=val).font = f_bold
        ws.cell(row=6, column=col).alignment = _TXT_ALIGN_LEFT
        ws.cell(row=7, column=col, value=sub).font = f_italic_muted
        ws.cell(row=7, column=col).alignment = _TXT_ALIGN_LEFT
    ws.row_dimensions[6].height = 22
    for c in range(1, NCOLS + 1):
        ws.cell(row=8, column=c).border = Border(top=Side(style='thin', color=INK))
    ws.row_dimensions[8].height = 4

    _section_rule(ws, 10, "Headline valuation + segment detail — top by confirmed ETA", span_cols=NCOLS)

    headers = ['#', 'Ticker', 'Name', 'Country', 'Sector', 'Industry', 'Mcap (USD)',
               'Verdict',
               'EV/EBITDA', 'P/E', 'P/B', 'P/S', 'FCF yld %', 'Div %', 'ROIC %',
               'EBITDA m %', 'ND/EBITDA', 'Mom 12m %',
               'Segs', 'HHI', 'Largest segment (share)',
               'Top 3 segments', 'Regs', 'Top regions', 'Fastest segment YoY',
               # FORENSIC segment signals — a hidden PROFITABLE engine (segment
               # growing revenue AND expanding margin / operating leverage),
               # not just revenue growth.
               'Fast seg OpMgn ΔYoY %', 'Seg OpLev', 'MgnInflect',
               # source + true revenue geography (FMP)
               'Src', 'EM rev %', 'China rev %']
    text_cols = {2, 3, 4, 5, 6, 21, 22, 24, 25}  # ticker/name/country/sector/industry/segment text
    center_cols = {8, 19, 28, 29}  # verdict + segs count + margin-inflect flag + source
    for i, h in enumerate(headers, start=1):
        c = ws.cell(row=11, column=i, value=h)
        c.font = f_bold_muted
        c.alignment = (_TXT_ALIGN_LEFT if i in text_cols else
                       _NUM_ALIGN_CENTER if i in center_cols else
                       _NUM_ALIGN_RIGHT)
    for c in range(1, NCOLS + 1):
        ws.cell(row=12, column=c).border = Border(top=Side(style='thin', color=INK))

    for r_idx, (_, r) in enumerate(df_subset.iterrows(), start=13):
        _write_int(ws, r_idx, 1, r_idx - 12, font=f_text_muted)
        ws.cell(row=r_idx, column=2, value=r['symbol']).font = f_bold
        ws.cell(row=r_idx, column=2).alignment = _TXT_ALIGN_LEFT
        ws.cell(row=r_idx, column=3, value=str(r.get('name') or '')[:30]).font = f_text
        ws.cell(row=r_idx, column=3).alignment = _TXT_ALIGN_LEFT
        ws.cell(row=r_idx, column=4, value=str(r.get('src') or '')).font = f_text_muted
        ws.cell(row=r_idx, column=4).alignment = _NUM_ALIGN_CENTER
        ws.cell(row=r_idx, column=5, value=str(r.get('sector') or '')[:14]).font = f_text_muted
        ws.cell(row=r_idx, column=5).alignment = _TXT_ALIGN_LEFT
        ws.cell(row=r_idx, column=6, value=str(r.get('industry') or '')[:22]).font = f_text_muted
        ws.cell(row=r_idx, column=6).alignment = _TXT_ALIGN_LEFT
        _write_money(ws, r_idx, 7, r.get('market_cap'), font=f_text)
        # pd.notna guard: a bare `or` fallback lets NaN (truthy) through
        _v = r.get('verdict')
        _verdict_badge(ws, r_idx, 8,
                       _v if (pd.notna(_v) and _v) else 'UNRESEARCHED')
        # Valuation columns
        _write_score(ws, r_idx, 9, r.get('ev_ebitda'), font=f_text)
        _write_score(ws, r_idx, 10, r.get('p_e'), font=f_text)
        _write_score(ws, r_idx, 11, r.get('pb'), font=f_text)
        _write_score(ws, r_idx, 12, r.get('p_s'), font=f_text)
        _write_pct(ws, r_idx, 13, r.get('fcf_yield'), font=f_text)
        _write_pct(ws, r_idx, 14, r.get('dividend_yield'), font=f_text)
        _write_pct(ws, r_idx, 15, r.get('roce'), font=f_text)
        _write_pct(ws, r_idx, 16, r.get('ebitda_margin'), font=f_text)
        _write_score(ws, r_idx, 17, r.get('net_debt_ebitda'), font=f_text)
        _write_pct(ws, r_idx, 18, r.get('momentum_12m'), font=f_text)
        # Segment columns
        _write_int(ws, r_idx, 19, int(r['segment_count']) if pd.notna(r.get('segment_count')) else 0, font=f_text)
        _write_ratio(ws, r_idx, 20, r.get('segment_revenue_hhi'), font=f_text)
        ls_name = str(r.get('largest_segment_name') or '')[:22]
        ls_share = r.get('largest_segment_share')
        if pd.notna(ls_share) and ls_share is not None:
            largest_str = f"{ls_name} ({ls_share*100:.0f}%)"
        else:
            largest_str = ls_name
        ws.cell(row=r_idx, column=21, value=largest_str).font = f_text
        ws.cell(row=r_idx, column=21).alignment = _TXT_ALIGN_LEFT
        ws.cell(row=r_idx, column=22, value=str(r.get('top_segments') or '')[:80]).font = f_text_muted
        ws.cell(row=r_idx, column=22).alignment = _TXT_ALIGN_LEFT
        _write_int(ws, r_idx, 23, int(r['geographic_region_count']) if pd.notna(r.get('geographic_region_count')) else 0, font=f_text)
        ws.cell(row=r_idx, column=24, value=str(r.get('top_regions') or '')[:60]).font = f_text_muted
        ws.cell(row=r_idx, column=24).alignment = _TXT_ALIGN_LEFT
        fs_name = str(r.get('fastest_segment_name') or '')[:20]
        fs_yoy = r.get('fastest_segment_yoy')
        if pd.notna(fs_yoy):
            fast_str = f"{fs_name} {fs_yoy*100:+.0f}%"
        else:
            fast_str = fs_name
        ws.cell(row=r_idx, column=25, value=fast_str).font = f_text
        ws.cell(row=r_idx, column=25).alignment = _TXT_ALIGN_LEFT
        # FORENSIC segment signals: segment-level op-margin inflection +
        # operating leverage = the tell of a hidden PROFITABLE engine.
        _write_pct(ws, r_idx, 26, r.get('fastest_seg_opmargin_delta_yoy'), font=f_text)
        _write_score(ws, r_idx, 27, r.get('seg_oplev'), font=f_text)
        _mif = r.get('seg_margin_inflect_flag')
        ws.cell(row=r_idx, column=28,
                value='✓' if (pd.notna(_mif) and _mif == 1) else '').font = f_text
        ws.cell(row=r_idx, column=28).alignment = _NUM_ALIGN_CENTER
        ws.cell(row=r_idx, column=29, value=str(r.get('seg_source') or '')).font = f_text_muted
        ws.cell(row=r_idx, column=29).alignment = _NUM_ALIGN_CENTER
        _write_pct(ws, r_idx, 30, r.get('fmp_geo_em_share'), font=f_text)
        _write_pct(ws, r_idx, 31, r.get('fmp_geo_china_share'), font=f_text)
        for c in range(1, NCOLS + 1):
            ws.cell(row=r_idx, column=c).border = Border(
                bottom=Side(style='thin', color=RULE))
        ws.row_dimensions[r_idx].height = 16

    # Column widths tuned for the new wider layout
    widths = {1: 4, 2: 10, 3: 22, 4: 6, 5: 14, 6: 16, 7: 14, 8: 12,
              9: 9, 10: 8, 11: 7, 12: 7, 13: 9, 14: 7, 15: 8, 16: 10, 17: 9, 18: 10,
              19: 5, 20: 7, 21: 28, 22: 52, 23: 5, 24: 32, 25: 22,
              26: 18, 27: 9, 28: 10, 29: 10, 30: 9, 31: 10}
    for col, w in widths.items():
        ws.column_dimensions[get_column_letter(col)].width = w

    ws.sheet_view.showGridLines = False
    ws.freeze_panes = 'A13'
    # QoL: sortable/filterable table (header row 11 → last data row)
    if ws.max_row >= 13:
        ws.auto_filter.ref = f"A11:{get_column_letter(ws.max_column)}{ws.max_row}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--n', type=int, default=60, help='top N per archetype tab')
    ap.add_argument('--detail-n', type=int, default=300,
                    help='top N in the All Segments master tab')
    ap.add_argument('--out', default='segment_detail_book.xlsx')
    args = ap.parse_args()

    print('loading data...', file=sys.stderr)
    df = load_data()
    print(f'  {len(df):,} segment-covered rows', file=sys.stderr)
    if 'entry_today_asymmetry' not in df.columns:
        df['entry_today_asymmetry'] = 0
    # Confirmation-upweighted ranking key (computed in load_data): ETA x
    # (1 + 0.20*confirm_overall + 0.10*buyback_score). Same treatment the
    # archetype books apply via entry_confirmed.
    sort_col = 'entry_confirmed' if 'entry_confirmed' in df.columns \
        else 'entry_today_asymmetry'

    wb = Workbook()
    cover = wb.active
    tab_colors.set_tab(cover, tab_colors.COVER)
    cover.title = 'Cover'
    cover.column_dimensions['A'].width = 6
    for col_letter in 'BCDEFG':
        cover.column_dimensions[col_letter].width = 28
    cover.column_dimensions['H'].width = 6

    f_bold = _font(bold=True, color=INK)
    f_italic = _font(italic=True, color=INK)
    f_italic_muted = _font(italic=True, color=MUTED)
    f_text = _font(color=INK)

    t = cover.cell(row=3, column=2, value="Segment-Level Detail")
    t.font = f_bold
    cover.merge_cells(start_row=3, start_column=2, end_row=3, end_column=7)
    cover.row_dimensions[3].height = 22
    for c in range(2, 8):
        cover.cell(row=4, column=c).border = Border(bottom=Side(style='thin', color=INK))
    cover.row_dimensions[4].height = 4

    sub = cover.cell(row=5, column=2,
                     value="What the binary archetypes hide — actual segment names, % of sales, YoY growth")
    sub.font = f_italic
    cover.merge_cells(start_row=5, start_column=2, end_row=5, end_column=7)

    src_note = cover.cell(row=7, column=2,
                          value="Sources: SEC EDGAR dimensional XBRL (US multi-segment 10-K filers; also carries segment "
                                "operating margin) UNION Financial Modeling Prep revenue segmentation (product + geographic, "
                                "US and non-US). 'Src' column shows which. FMP is revenue-only: margin columns stay EDGAR.")
    src_note.font = f_italic_muted
    cover.merge_cells(start_row=7, start_column=2, end_row=7, end_column=7)

    _section_rule(cover, 9, "Universe stats", span_cols=7)
    n_total = len(df)
    n_4plus = int((df['segment_count'].fillna(0) >= 4).sum())
    n_hhi_diverse = int((df['segment_revenue_hhi'].fillna(1.0) <= 0.40).sum())
    n_hhi_concentr = int((df['segment_revenue_hhi'].fillna(0) >= 0.70).sum())
    n_global = int((df['geographic_region_count'].fillna(0) >= 4).sum())
    n_fast = int((df['fastest_segment_yoy'].fillna(0) >= 0.25).sum())

    tiles = [
        ("FILERS", f"{n_total:,}", "with segment data"),
        ("DIVERSIFIED", f"{n_4plus:,}", "4+ segments"),
        ("BALANCED", f"{n_hhi_diverse:,}", "HHI <= 0.40"),
        ("CONCENTRATED", f"{n_hhi_concentr:,}", "HHI >= 0.70"),
        ("GLOBAL", f"{n_global:,}", "4+ regions"),
        ("FAST SEG", f"{n_fast:,}", "+25% YoY"),
    ]
    for i, (lbl, val, sub_lbl) in enumerate(tiles):
        col = 2 + i
        cover.cell(row=10, column=col, value=lbl).font = f_italic_muted
        cover.cell(row=11, column=col, value=val).font = f_bold
        cover.cell(row=12, column=col, value=sub_lbl).font = f_italic_muted
        for r in (10, 11, 12):
            cover.cell(row=r, column=col).alignment = _TXT_ALIGN_LEFT
    cover.row_dimensions[11].height = 24
    for c in range(2, 8):
        cover.cell(row=13, column=c).border = Border(top=Side(style='thin', color=INK))
    cover.row_dimensions[13].height = 4

    # Per-archetype top scorers index
    _section_rule(cover, 15, "Tabs in this workbook", span_cols=7)
    rows_meta = [
        ("All Segments", f"top {args.detail_n:,} by confirmed ETA", "every name we have segment data on"),
        ("Diversified", f"top {args.n:,}", "4+ segments AND HHI <= 0.40 (real diversification)"),
        ("Concentrated", f"top {args.n:,}", "HHI >= 0.70 or top segment >= 70% (single-segment risk)"),
        ("Global", f"top {args.n:,}", "4+ reporting geographies"),
        ("Fastest", f"top {args.n:,}", "single segment growing > 25% YoY (hidden engine)"),
        ("Hidden Compounder", "top 60", "XR: margin-inflecting fast segment gaining share, still <60%, cheap consolidated"),
        ("Segment Justifies Whole", "top 60", "XR SOTP: best segment @ ~12x EBIT >= full EV (rest free); revenue-reconciled"),
        ("Margin Mix-Shift", "top 60", "XR: rich segment (>=5pp over blend) gaining share -> coming consolidated margin lift"),
        ("Hidden Engine (all)", f"top {max(args.n,150):,}", "arch_fastest_segment — broad hidden growth-engine tag"),
        ("EM Revenue Exposure", f"top {max(args.n,150):,}", ">=50% of revenue from emerging markets (FMP geography), incl. DM listings"),
        ("FMP Segment Detail", "every name", "per-ticker product + geographic segment revenue, share and YoY (latest FY)"),
    ]
    for i, (tab, n, desc) in enumerate(rows_meta, start=16):
        cover.cell(row=i, column=2, value=tab).font = f_bold
        cover.cell(row=i, column=2).hyperlink = f"#'{_sheet_safe(tab)}'!A1"
        cover.cell(row=i, column=2).alignment = _TXT_ALIGN_LEFT
        cover.cell(row=i, column=3, value=n).font = f_text
        cover.cell(row=i, column=3).alignment = _TXT_ALIGN_LEFT
        cover.cell(row=i, column=4, value=desc).font = f_text
        cover.cell(row=i, column=4).alignment = _TXT_ALIGN_LEFT
        cover.merge_cells(start_row=i, start_column=4, end_row=i, end_column=7)

    cover.sheet_view.showGridLines = False

    # Confirmation-upweighted segment inflection for the Fastest tab: the
    # segment's own YoY is the thesis (primary, so hidden engines like
    # EVC/Smadex still surface), UPWEIGHTED where independent measures agree —
    # the consolidated multi-measure confirmation (confirm_overall) and
    # insider alignment. Same shape as entry_confirmed; ranking only, the pool
    # is unchanged. This makes the Fastest tab robust in the same manner as
    # the archetype books (broaden via the tag's fire-on-ANY, upweight here).
    _fsy = pd.to_numeric(df.get('fastest_segment_yoy'), errors='coerce')
    _cfo = pd.to_numeric(df.get('confirm_overall'), errors='coerce').fillna(0.0)
    _aln = pd.to_numeric(df.get('alignment_score'), errors='coerce').fillna(0.0)
    # (books audit #4/#5) fastest-segment yoy is max-across-segments — the
    # most base-effect-exposed number; cap before it drives a ranking
    # (user directive) latest-quarter corroboration and a consecutive-
    # growth streak UPWEIGHT the FY-based number (never replace it)
    _qcf_s = pd.to_numeric(df['fastest_seg_q_confirm'], errors='coerce').fillna(0).clip(0, 1) if 'fastest_seg_q_confirm' in df.columns else pd.Series(0.0, index=df.index)
    _stk_s = (pd.to_numeric(df['fastest_seg_consec_growth'], errors='coerce').fillna(0).clip(0, 3) / 3.0) if 'fastest_seg_consec_growth' in df.columns else pd.Series(0.0, index=df.index)
    df['seg_inflect_confirmed'] = (_fsy.clip(-1.0, 1.0)
                                   * (1.0 + 0.20 * _cfo.clip(0, 1)
                                      + 0.10 * _aln.clip(0, 1)
                                      + 0.10 * _qcf_s
                                      + 0.05 * _stk_s).clip(1.0, 1.45))

    # === All Segments tab ===
    all_seg = df.sort_values(sort_col, ascending=False).head(args.detail_n).reset_index(drop=True)
    ws = wb.create_sheet('All Segments')
    tab_colors.set_tab(ws, tab_colors.AGGREGATE)
    _write_segment_table(ws, all_seg, 'All Segment-Covered Names (top by confirmed ETA)', n_total, sort_col)

    # === Per-archetype tabs ===
    # Each entry carries its own (sort column, depth). The "Fastest" tab is a
    # HIDDEN-ENGINE discovery view: it must rank by the segment's own YoY, not
    # by whole-company entry asymmetry. Names whose fast segment is masked by a
    # shrinking legacy segment (e.g. EVC/Smadex — AdTech +90% inside a
    # declining media co) have muted CONSOLIDATED multiples, so an
    # entry-asymmetry sort buries exactly the population this tab exists to
    # surface. Rank by fastest_segment_yoy and show a deeper list.
    archetypes = [
        ('Diversified',
         df[(df['segment_count'].fillna(0) >= 4) & (df['segment_revenue_hhi'].fillna(1.0) <= 0.40)],
         '4+ segments AND HHI <= 0.40', sort_col, args.n),
        ('Concentrated',
         df[((df['segment_revenue_hhi'].fillna(0) >= 0.70) |
             (df['largest_segment_share'].fillna(0) >= 0.70)) &
            (df['segment_count'].fillna(0) >= 2)],
         'HHI >= 0.70 or top segment >= 70%', sort_col, args.n),
        ('Global',
         df[df['geographic_region_count'].fillna(0) >= 4],
         '4+ reporting geographies', sort_col, args.n),
        ('Fastest',
         df[(df['fastest_segment_yoy'].fillna(0) >= 0.25) & (df['segment_count'].fillna(0) >= 2)],
         'Single segment growing > 25% YoY — ranked by segment YoY, upweighted where consolidated measures confirm (hidden engine)',
         'seg_inflect_confirmed', max(args.n, 150)),
        # FORENSIC-XR setups (archetype membership from the tags output)
        ('Hidden Compounder',
         df[df.get('arch_xr_hidden_segment_compounder', 0).fillna(0) == 1]
         if 'arch_xr_hidden_segment_compounder' in df.columns else df.iloc[0:0],
         'XR sum-of-parts: fast segment with MARGIN inflecting + gaining share but <60% of the co, '
         'while the consolidated whole is priced cheap — the compounder the trailing numbers mask',
         'seg_inflect_confirmed', max(args.n, 60)),
        ('Segment Justifies Whole',
         df[df.get('arch_xr_segment_justifies_whole', 0).fillna(0) == 1]
         if 'arch_xr_segment_justifies_whole' in df.columns else df.iloc[0:0],
         'XR SOTP: the single best segment valued alone at ~12x its own operating EBIT already covers the '
         'ENTIRE enterprise value — every other (net-positive) segment comes free; segment revenue reconciled to consolidated USD',
         sort_col, max(args.n, 60)),
        ('Margin Mix-Shift',
         df[df.get('arch_xr_margin_mixshift', 0).fillna(0) == 1]
         if 'arch_xr_margin_mixshift' in df.columns else df.iloc[0:0],
         'XR: the fastest-growing segment earns a materially richer margin (>=5pp over the blend) AND is gaining share — '
         'as mix shifts the consolidated margin must expand, but the trailing blended figure the market prices cannot yet show it',
         sort_col, max(args.n, 60)),
        ('Hidden Engine (all)',
         df[df.get('arch_fastest_segment', 0).fillna(0) == 1]
         if 'arch_fastest_segment' in df.columns else df.iloc[0:0],
         'arch_fastest_segment — the broad hidden growth-engine tag (segment inflection, no valuation gate)',
         'seg_inflect_confirmed', max(args.n, 150)),
    ]

    for label, sub_df, desc, tab_sort, tab_n in archetypes:
        sub_df = sub_df.nlargest(tab_n, tab_sort).reset_index(drop=True)
        if sub_df.empty:
            continue
        ws = wb.create_sheet(_sheet_safe(label))
        tab_colors.set_tab(ws, tab_colors.FAMILY_COLORS['segment'])
        _write_segment_table(ws, sub_df, f"{label} — {desc}", n_total, tab_sort)

    # === EM Revenue Exposure: true economic geography, not listing domicile ===
    if 'fmp_geo_em_share' in df.columns:
        em = df[pd.to_numeric(df['fmp_geo_em_share'], errors='coerce') >= 0.50]
        em = em.sort_values('fmp_geo_em_share', ascending=False).head(max(args.n, 150)).reset_index(drop=True)
        if not em.empty:
            ws = wb.create_sheet('EM Revenue Exposure')
            tab_colors.set_tab(ws, tab_colors.FAMILY_COLORS['segment'])
            _write_segment_table(ws, em, 'EM Revenue Exposure — >=50% of revenue earned in emerging markets '
                                 '(FMP geographic segmentation); includes developed-market listings whose '
                                 'economics are EM (the Cluseau sizing tier keys on this too)', n_total, 'fmp_geo_em_share')

    # === FMP Segment Detail: per-ticker rows for EVERY name in the book ===
    if os.path.exists('fmp_segments_detail.csv'):
        det = pd.read_csv('fmp_segments_detail.csv', low_memory=False)
        det = det[det['symbol'].isin(df['symbol'])]
        if not det.empty:
            det['_fy_max'] = det.groupby(['symbol', 'axis'])['fiscal_year'].transform('max')
            det = det[det['fiscal_year'] == det['_fy_max']]
            rank = {sym: i for i, sym in enumerate(df.sort_values(sort_col, ascending=False)['symbol'])}
            det = det.assign(_r=det['symbol'].map(rank),
                             _ax=det['axis'].map({'product': 0, 'geographic': 1}))
            det = det.sort_values(['_r', '_ax', 'share'], ascending=[True, True, False])
            nm = df.drop_duplicates('symbol').set_index('symbol')
            ws = wb.create_sheet('FMP Segment Detail')
            tab_colors.set_tab(ws, tab_colors.FAMILY_COLORS['segment'])
            hdr = ['Ticker', 'Name', 'Country', 'Axis', 'FY', 'Segment', 'Revenue', 'Ccy', 'Share %', 'YoY %']
            ws.append(hdr)
            for c in range(1, len(hdr) + 1):
                ws.cell(row=1, column=c).font = _font(bold=True, color=MUTED)
            for r in det.itertuples(index=False):
                ws.append([r.symbol,
                           str(nm['name'].get(r.symbol, '') if 'name' in nm.columns else '')[:40],
                           str(nm['src'].get(r.symbol, '') if 'src' in nm.columns else ''),
                           r.axis, int(r.fiscal_year), r.segment,
                           round(float(r.revenue)) if pd.notna(r.revenue) else None,
                           r.currency if isinstance(r.currency, str) else '',
                           round(float(r.share) * 100, 1) if pd.notna(r.share) else None,
                           round(float(r.yoy) * 100, 1) if pd.notna(r.yoy) else None])
            for col, w in zip('ABCDEFGHIJ', (10, 30, 7, 11, 6, 44, 16, 6, 9, 9)):
                ws.column_dimensions[col].width = w
            ws.freeze_panes = 'A2'
            ws.auto_filter.ref = f"A1:J{ws.max_row}"
            ws.sheet_view.showGridLines = False

    wb.save(args.out)
    from harvard_style import sanitize_nan_text
    sanitize_nan_text(args.out)
    print(f'wrote {args.out}: {len(wb.worksheets)} sheets', file=sys.stderr)


if __name__ == '__main__':
    main()
