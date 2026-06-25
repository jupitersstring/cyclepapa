#!/usr/bin/env python3
"""Harvard-aesthetic workbook — grayscale only, single font size, Times New Roman.

Design tenets:
  • ONE font: Times New Roman
  • ONE size: 10pt
  • Condensed glyphs (font_condense=True) for the tall academic feel
  • Pure grayscale — black text, white background, mid-gray rule lines only
  • Hierarchy via WEIGHT (bold), ITALIC, SMALL CAPS (manual upper()), and rule lines
  • Negatives in parens, em-dash for empty, thousands separators
  • Generous whitespace — taller row heights than default
  • No tab colors, no fills, no stripes — like a 1950s annual report

Surfaces segment-level specifics: which segment is largest/fastest/slowest, by how much.
"""
import os, sys, datetime
import pandas as pd
import numpy as np

EM_DASH = '–'
os.makedirs('data/synthesis/workbook', exist_ok=True)

REGION_FULLNAME = {
    'us':'United States','us_x':'United States (Expanded)','uk':'United Kingdom','japan':'Japan',
    'germany':'Germany','france':'France','italy':'Italy','spain':'Spain','netherlands':'Netherlands',
    'belgium':'Belgium','switzerland':'Switzerland','sweden':'Sweden','norway':'Norway',
    'finland':'Finland','denmark':'Denmark','ireland':'Ireland','austria':'Austria',
    'portugal':'Portugal','greece':'Greece','canada':'Canada','australia':'Australia',
    'nz':'New Zealand','hk':'Hong Kong','china':'China','korea':'South Korea',
    'taiwan':'Taiwan','singapore':'Singapore','thailand':'Thailand','indonesia':'Indonesia',
    'israel':'Israel','turkey':'Turkey','brazil':'Brazil','mexico':'Mexico',
    'argentina':'Argentina','chile':'Chile','southafrica':'South Africa',
}

src = ('data/synthesis/v2_universe_ranked_full_q.csv'
       if os.path.exists('data/synthesis/v2_universe_ranked_full_q.csv')
       else 'data/synthesis/v2_universe_ranked_full.csv')
df = pd.read_csv(src)
for col in ['qmaggie_pass','ep_pass','quality_pass','quality_pass_loose','absorp_pass','prebo_pass',
            'compress_pass','seg_inflection_flag','seg_high_margin_growing','backlog_inflection_flag',
            'enduring_strict','enduring_loose','roiic_inflection','cc_roiic_inflection','has_history',
            'is_financial','enduring_roe']:
    if col not in df.columns: df[col] = False
    df[col] = df[col].fillna(False).astype(bool)

if 'fcf_yield_pct' not in df.columns and 'fcf_yield' in df.columns:
    df['fcf_yield_pct'] = pd.to_numeric(df['fcf_yield'], errors='coerce') * 100
if 'rev_g_pct' not in df.columns and 'rev_g' in df.columns:
    df['rev_g_pct'] = pd.to_numeric(df['rev_g'], errors='coerce') * 100
if 'mktCap_M' not in df.columns and 'mktCap' in df.columns:
    df['mktCap_M'] = pd.to_numeric(df['mktCap'], errors='coerce') / 1e6

print(f"Loaded {len(df)} rows from {src}", file=sys.stderr)

# ───────────────────────────── STYLE ────────────────────────────────
def build_styles(wb):
    """Single font: Times New Roman 10pt, condensed. All grayscale."""
    F = 'Times New Roman'
    S = 10
    BLACK = '#000000'
    GRAY_RULE = '#7F7F7F'    # mid-gray for cell borders
    GRAY_HAIR = '#BFBFBF'    # hair-line for inner separators
    WHITE = '#FFFFFF'

    base = {'font_name': F, 'font_size': S, 'font_color': BLACK, 'bg_color': WHITE,
            'font_condense': True}

    s = {}
    s['title']        = wb.add_format({**base, 'bold': True, 'align': 'left', 'valign': 'vcenter',
                                       'bottom': 2, 'border_color': BLACK})
    s['subtitle']     = wb.add_format({**base, 'italic': True, 'align': 'left', 'valign': 'vcenter'})
    s['section']      = wb.add_format({**base, 'bold': True, 'italic': True, 'align': 'left',
                                       'top': 1, 'bottom': 1, 'border_color': BLACK, 'valign': 'vcenter'})
    s['notes']        = wb.add_format({**base, 'italic': True, 'align': 'left', 'text_wrap': True,
                                       'valign': 'top'})
    s['header']       = wb.add_format({**base, 'bold': True, 'align': 'center', 'valign': 'vcenter',
                                       'top': 1, 'bottom': 1, 'border_color': BLACK})

    # Body cells: thin gray bottom rule between rows; no side borders
    body_kw  = {**base, 'bottom': 1, 'border_color': GRAY_HAIR, 'valign': 'vcenter'}
    s['text_l']     = wb.add_format({**body_kw, 'align': 'left'})
    s['text_r']     = wb.add_format({**body_kw, 'align': 'right'})
    s['text_c']     = wb.add_format({**body_kw, 'align': 'center'})
    s['text_l_b']   = wb.add_format({**body_kw, 'align': 'left',  'bold': True})
    s['text_c_b']   = wb.add_format({**body_kw, 'align': 'center', 'bold': True})

    s['money']      = wb.add_format({**body_kw, 'align': 'right', 'num_format': '#,##0;(#,##0);"–"'})
    s['money_b']    = wb.add_format({**body_kw, 'align': 'right', 'num_format': '#,##0;(#,##0);"–"', 'bold': True})
    s['pct']        = wb.add_format({**body_kw, 'align': 'right', 'num_format': '#,##0.0;(#,##0.0);"–"'})
    s['pct_b']      = wb.add_format({**body_kw, 'align': 'right', 'num_format': '#,##0.0;(#,##0.0);"–"', 'bold': True})
    s['ratio']      = wb.add_format({**body_kw, 'align': 'right', 'num_format': '#,##0.00;(#,##0.00);"–"'})
    s['ratio_b']    = wb.add_format({**body_kw, 'align': 'right', 'num_format': '#,##0.00;(#,##0.00);"–"', 'bold': True})
    s['em']         = wb.add_format({**body_kw, 'align': 'right'})  # for em-dash strings

    return s

def write_text(ws, r, c, v, fmt, em_fmt):
    if v is None or (isinstance(v, float) and pd.isna(v)) or str(v).strip() in ('','nan','None'):
        ws.write_string(r, c, EM_DASH, em_fmt)
    else:
        ws.write_string(r, c, str(v), fmt)

def write_num(ws, r, c, v, fmt, em_fmt):
    if v is None or pd.isna(v):
        ws.write_string(r, c, EM_DASH, em_fmt); return
    try:
        fv = float(v)
        if not np.isfinite(fv) or abs(fv) > 1e15:
            ws.write_string(r, c, EM_DASH, em_fmt)
        else:
            ws.write_number(r, c, fv, fmt)
    except Exception:
        ws.write_string(r, c, EM_DASH, em_fmt)

def topct(v):
    if pd.notna(v) and abs(float(v)) < 50: return float(v) * 100
    return None

# ──────────────────────────── BUILD ─────────────────────────────────
xlsx_path = 'data/synthesis/workbook/candidates_workbook_harvard.xlsx'
with pd.ExcelWriter(xlsx_path, engine='xlsxwriter') as writer:
    wb = writer.book
    S = build_styles(wb)

    def region_sheet(name, region_df, label, max_rows=8000):
        ws = wb.add_worksheet(name[:31])
        ws.hide_gridlines(2)
        ws.set_default_row(15)
        ws.freeze_panes(4, 1)

        n_q   = int(region_df['quality_pass'].sum())
        n_ql  = int(region_df['quality_pass_loose'].sum()) if 'quality_pass_loose' in region_df else 0
        n_qm  = int(region_df['qmaggie_pass'].sum())
        n_ep  = int(region_df['ep_pass'].sum())
        n_seg = int(region_df.get('seg_inflection_flag', pd.Series(False, index=region_df.index)).sum())

        ws.set_row(0, 26)
        ws.merge_range(0, 0, 0, 18, label.upper(), S['title'])
        ws.set_row(1, 16)
        ws.merge_range(1, 0, 1, 18,
            f"{len(region_df):,} ranked  ·  {n_q} Q-strict  ·  {n_ql} Q-loose  ·  {n_qm} Qullamaggie  "
            f"·  {n_ep} Episodic Pivot  ·  {n_seg} segment inflection  ·  {datetime.date.today().isoformat()}",
            S['subtitle'])

        widths = [9, 32, 11, 4, 4, 4, 4, 4, 7, 7, 7, 5, 9, 7, 7, 13, 7, 22, 7]
        for c, w in enumerate(widths): ws.set_column(c, c, w)

        headers = ['Ticker','Company','Cap','Q','QL','Qm','EP','Seg','Macro','Dalton %','TD %','Lens',
                   'EV/EBITDA','FCF Yld %','Rev G %','Market Cap (M)','Score','Largest Segment','Seg %']
        ws.set_row(3, 22)
        for c, h in enumerate(headers):
            ws.write(3, c, h, S['header'])

        ws.autofilter(3, 0, min(len(region_df), max_rows) + 3, len(headers) - 1)

        for i, (_, r) in enumerate(region_df.head(max_rows).iterrows()):
            row = 4 + i
            qpass = bool(r.get('quality_pass', False))
            tfmt  = S['text_l_b'] if qpass else S['text_l']
            mfmt  = S['money_b']  if qpass else S['money']
            pfmt  = S['pct_b']    if qpass else S['pct']
            rfmt  = S['ratio_b']  if qpass else S['ratio']
            cfmt  = S['text_c_b'] if qpass else S['text_c']

            write_text(ws, row, 0, r.get('ticker'), tfmt, S['em'])
            write_text(ws, row, 1, str(r.get('name',''))[:36] if pd.notna(r.get('name')) else None, tfmt, S['em'])
            write_text(ws, row, 2, r.get('cap_tier'), tfmt, S['em'])
            for c, k in [(3,'quality_pass'),(4,'quality_pass_loose'),(5,'qmaggie_pass'),
                         (6,'ep_pass'),(7,'seg_inflection_flag')]:
                v = bool(r.get(k, False))
                ws.write_string(row, c, '•' if v else EM_DASH, cfmt if v else S['em'])
            write_num(ws, row, 8, r.get('absW_macro'), mfmt, S['em'])
            write_num(ws, row, 9, r.get('leg_dalton'), pfmt, S['em'])
            write_num(ws, row,10, r.get('leg_td'),     pfmt, S['em'])
            tags = ''
            if r.get('absorp_pass'): tags += 'A'
            if r.get('prebo_pass'): tags += 'P'
            if r.get('compress_pass'): tags += 'C'
            write_text(ws, row,11, tags, cfmt, S['em'])
            write_num(ws, row,12, r.get('ev_valuation'), rfmt, S['em'])
            write_num(ws, row,13, r.get('fcf_yield_pct'), pfmt, S['em'])
            write_num(ws, row,14, r.get('rev_g_pct'), pfmt, S['em'])
            write_num(ws, row,15, r.get('mktCap_M'), mfmt, S['em'])
            write_num(ws, row,16, r.get('all_legs_score'), rfmt, S['em'])
            seg_name = str(r.get('largest_segment',''))[:28] if pd.notna(r.get('largest_segment')) else None
            write_text(ws, row,17, seg_name, tfmt, S['em'])
            write_num(ws, row,18, r.get('largest_segment_pct'), pfmt, S['em'])

    # ─── Summary cover sheet ───
    ws = wb.add_worksheet('Summary')
    ws.hide_gridlines(2)
    ws.set_default_row(15)
    for c, w in [(0,11),(1,30),(2,18),(3,10),(4,5),(5,5),(6,8),(7,8),(8,8),
                 (9,5),(10,10),(11,8),(12,8),(13,12),(14,8)]:
        ws.set_column(c, c, w)

    ws.set_row(0, 30)
    ws.merge_range(0, 0, 0, 14, 'ASYMMETRIC SETUPS  ·  FULL-UNIVERSE WORKBOOK', S['title'])
    ws.set_row(1, 16)
    ws.merge_range(1, 0, 1, 14,
        f"{datetime.date.today().isoformat()}  ·  {len(df):,} ranked tickers across "
        f"{df['region'].nunique()} markets  ·  {int(df['quality_pass'].sum()):,} Q-strict",
        S['subtitle'])

    methodology = (
        "Methodology — every ticker receives a composite score across three core legs (Dalton asymmetric inflection, "
        "TD Sequential mean reversion, Fundamentals: EV/EBITDA + FCF yield + revenue growth + operating margin) plus "
        "structural lenses (Wyckoff Absorption, Weinstein/O'Neil Pre-breakout, MFI Compression weekly + monthly), then "
        "augmented with SEC EDGAR fundamentals: Lindy multi-method ROIC (Mauboussin · Damodaran · Greenblatt · CROIC · "
        "DuPont) with method-agreement scoring, ROIIC inflection detection (accrual + cash-on-cash), backlog inflection "
        "from RPO and deferred-revenue XBRL concepts, and segment-level inflection from full XBRL dimensional facts "
        "(largest segment, fastest-growing segment, mix-shift, margin profile).\n\n"
        "Flags — Q = strict asymmetric (macro ≥ 25, asymmetry ≥ 1.5×, bracket 20–85%, no monthly conflict, positive "
        "risk margin, ≥ 1 bullish timeframe). QL = looser (macro ≥ 18, asymmetry ≥ 1.15×). Qm = proper Qullamaggie "
        "continuation breakout (30–100% leg in past 1–3 months, 10/20-day SMA surf, ADR ≤ 6 %, 2 wk–2 mo base). "
        "EP = Episodic Pivot (≥ 10 % gap on ≥ 2× ADV after a 3–6 mo sideways base). Seg = segment inflection (a new "
        "segment gaining mix share while a legacy segment shrinks).\n\n"
        "Conventions — negatives shown in parentheses (financial-statement convention); em-dash for missing data; "
        "Times New Roman 10 pt throughout."
    )
    ws.merge_range(3, 0, 9, 14, methodology, S['notes'])
    for r in range(3, 10): ws.set_row(r, 18)

    sum_headers = ['Ticker','Company','Region','Cap','Q','Qm','Dalton %','TD %','Fund %','Lens',
                   'EV/EBITDA','FCF Y %','Rev G %','Market Cap (M)','Score']

    def write_summary_row(row, r):
        qpass = bool(r.get('quality_pass', False))
        tfmt = S['text_l_b'] if qpass else S['text_l']
        cfmt = S['text_c_b'] if qpass else S['text_c']
        mfmt = S['money_b']  if qpass else S['money']
        pfmt = S['pct_b']    if qpass else S['pct']
        rfmt = S['ratio_b']  if qpass else S['ratio']
        write_text(ws, row, 0, r.get('ticker'), tfmt, S['em'])
        write_text(ws, row, 1, str(r.get('name',''))[:30] if pd.notna(r.get('name')) else None, tfmt, S['em'])
        write_text(ws, row, 2, REGION_FULLNAME.get(r.get('region',''), r.get('region','')), tfmt, S['em'])
        write_text(ws, row, 3, str(r.get('cap_tier',''))[:9], tfmt, S['em'])
        for c, k in [(4,'quality_pass'),(5,'qmaggie_pass')]:
            v = bool(r.get(k, False))
            ws.write_string(row, c, '•' if v else EM_DASH, cfmt if v else S['em'])
        write_num(ws, row, 6, r.get('leg_dalton'), pfmt, S['em'])
        write_num(ws, row, 7, r.get('leg_td'),     pfmt, S['em'])
        write_num(ws, row, 8, r.get('leg_fund'),   pfmt, S['em'])
        tags = ''
        if r.get('absorp_pass'): tags += 'A'
        if r.get('prebo_pass'): tags += 'P'
        if r.get('compress_pass'): tags += 'C'
        write_text(ws, row, 9, tags, cfmt, S['em'])
        write_num(ws, row,10, r.get('ev_valuation'), rfmt, S['em'])
        write_num(ws, row,11, r.get('fcf_yield_pct'), pfmt, S['em'])
        write_num(ws, row,12, r.get('rev_g_pct'), pfmt, S['em'])
        write_num(ws, row,13, r.get('mktCap_M'), mfmt, S['em'])
        write_num(ws, row,14, r.get('all_legs_score'), rfmt, S['em'])

    row = 11
    ws.set_row(row, 20)
    ws.merge_range(row, 0, row, 14, 'TOP 30 — OVERALL COMPOSITE', S['section']); row += 1
    ws.set_row(row, 20)
    for c, h in enumerate(sum_headers): ws.write(row, c, h, S['header'])
    row += 1
    for _, r in df.head(30).iterrows():
        write_summary_row(row, r); row += 1
    row += 1

    ws.set_row(row, 20)
    ws.merge_range(row, 0, row, 14, 'TOP 30 — QUALITY-STRICT ONLY', S['section']); row += 1
    ws.set_row(row, 20)
    for c, h in enumerate(sum_headers): ws.write(row, c, h, S['header'])
    row += 1
    for _, r in df[df['quality_pass']].head(30).iterrows():
        write_summary_row(row, r); row += 1
    row += 1

    # Segment Inflection — surface specifics
    if 'seg_inflection_flag' in df.columns:
        seg = df[df['seg_inflection_flag']].copy()
        if 'seg_mix_shift_pp' in seg.columns:
            seg = seg.sort_values('seg_mix_shift_pp', ascending=False)
        ws.set_row(row, 20)
        ws.merge_range(row, 0, row, 14,
            f'SEGMENT INFLECTION — {len(seg)} NAMES (largest mix-shift first)', S['section']); row += 1
        seg_hdr = ['Ticker','Company','Cap','Largest Segment','Largest %','Fastest Segment',
                   'Fastest %','Slowest Segment','Slowest %','Mix Gainer','Mix Δ pp',
                   'Best Margin Segment','Best Margin %','Hi-Mgn ↑','Score']
        ws.set_row(row, 22)
        for c, h in enumerate(seg_hdr): ws.write(row, c, h, S['header'])
        row += 1
        for _, r in seg.head(40).iterrows():
            write_text(ws, row, 0, r.get('ticker'), S['text_l_b'], S['em'])
            write_text(ws, row, 1, str(r.get('name',''))[:26] if pd.notna(r.get('name')) else None, S['text_l'], S['em'])
            write_text(ws, row, 2, r.get('cap_tier'), S['text_l'], S['em'])
            write_text(ws, row, 3, str(r.get('largest_segment',''))[:18] if pd.notna(r.get('largest_segment')) else None, S['text_l'], S['em'])
            write_num(ws, row, 4, r.get('largest_segment_pct'), S['pct'], S['em'])
            write_text(ws, row, 5, str(r.get('seg_fastest_name',''))[:18] if pd.notna(r.get('seg_fastest_name')) else None, S['text_l'], S['em'])
            write_num(ws, row, 6, r.get('seg_rev_growth_fastest'), S['pct'], S['em'])
            write_text(ws, row, 7, str(r.get('seg_slowest_name',''))[:18] if pd.notna(r.get('seg_slowest_name')) else None, S['text_l'], S['em'])
            write_num(ws, row, 8, r.get('seg_rev_growth_slowest'), S['pct'], S['em'])
            write_text(ws, row, 9, str(r.get('seg_mix_gainer',''))[:18] if pd.notna(r.get('seg_mix_gainer')) else None, S['text_l'], S['em'])
            write_num(ws, row,10, r.get('seg_mix_shift_pp'), S['pct'], S['em'])
            write_text(ws, row,11, str(r.get('seg_margin_best_name',''))[:18] if pd.notna(r.get('seg_margin_best_name')) else None, S['text_l'], S['em'])
            write_num(ws, row,12, r.get('seg_margin_best'), S['pct'], S['em'])
            v = bool(r.get('seg_high_margin_growing', False))
            ws.write_string(row,13, '•' if v else EM_DASH, S['text_c_b'] if v else S['em'])
            write_num(ws, row,14, r.get('all_legs_score'), S['ratio'], S['em'])
            row += 1
        row += 1

    # Backlog Inflection
    if 'backlog_inflection_flag' in df.columns:
        bl = df[df['backlog_inflection_flag']].copy()
        if 'backlog_inflection_pp' in bl.columns:
            bl = bl.sort_values('backlog_inflection_pp', ascending=False)
        if len(bl):
            ws.set_row(row, 20)
            ws.merge_range(row, 0, row, 14,
                f'BACKLOG INFLECTION — {len(bl)} NAMES (largest accel first)', S['section']); row += 1
            bl_hdr = ['Ticker','Company','Cap','Concept','Latest Backlog (M)','QoQ %','YoY %',
                      '4Q Avg %','8Q Avg %','Δ pp','Backlog/Rev','Latest Date','EV/EBITDA','FCF Y %','Score']
            ws.set_row(row, 22)
            for c, h in enumerate(bl_hdr): ws.write(row, c, h, S['header'])
            row += 1
            for _, r in bl.head(40).iterrows():
                write_text(ws, row, 0, r.get('ticker'), S['text_l_b'], S['em'])
                write_text(ws, row, 1, str(r.get('name',''))[:26] if pd.notna(r.get('name')) else None, S['text_l'], S['em'])
                write_text(ws, row, 2, r.get('cap_tier'), S['text_l'], S['em'])
                write_text(ws, row, 3, str(r.get('backlog_concept_used',''))[:24] if pd.notna(r.get('backlog_concept_used')) else None, S['text_l'], S['em'])
                bl_m = r.get('backlog_latest')
                write_num(ws, row, 4, (float(bl_m)/1e6) if pd.notna(bl_m) else None, S['money'], S['em'])
                write_num(ws, row, 5, r.get('backlog_qoq_pct'), S['pct'], S['em'])
                write_num(ws, row, 6, r.get('backlog_yoy_pct'), S['pct'], S['em'])
                write_num(ws, row, 7, r.get('backlog_growth_4q_mean'), S['pct'], S['em'])
                write_num(ws, row, 8, r.get('backlog_growth_8q_mean'), S['pct'], S['em'])
                write_num(ws, row, 9, r.get('backlog_inflection_pp'), S['pct'], S['em'])
                write_num(ws, row,10, r.get('backlog_to_rev_ratio'), S['ratio'], S['em'])
                write_text(ws, row,11, str(r.get('backlog_latest_date',''))[:10] if pd.notna(r.get('backlog_latest_date')) else None, S['text_l'], S['em'])
                write_num(ws, row,12, r.get('ev_valuation'), S['ratio'], S['em'])
                write_num(ws, row,13, r.get('fcf_yield_pct'), S['pct'], S['em'])
                write_num(ws, row,14, r.get('all_legs_score'), S['ratio'], S['em'])
                row += 1
            row += 1

    # Compounder cohort with full ROIC specifics
    if 'compounder_score' in df.columns and df['compounder_score'].notna().any():
        comp = df[df['has_history']].sort_values('compounder_score', ascending=False).head(30)
        n_strict = int(df.get('enduring_strict', pd.Series(False, index=df.index)).sum())
        n_infl   = int(df.get('roiic_inflection', pd.Series(False, index=df.index)).sum())
        ws.set_row(row, 20)
        ws.merge_range(row, 0, row, 14,
            f'ENDURING COMPOUNDERS — LINDY MULTI-METHOD ROIC  ·  {n_strict} strict  ·  {n_infl} ROIIC inflecting',
            S['section']); row += 1
        ch = ['Ticker','Company','Sector','Cap','Market Cap (M)','ROIC Mean %','ROIC Min %',
              'Method Agr','ROIIC 1y %','ROIIC 3y %','CC-ROIC %','EV/EBIT','FCF Y %','Strict','Score']
        ws.set_row(row, 22)
        for c, h in enumerate(ch): ws.write(row, c, h, S['header'])
        row += 1
        for _, r in comp.iterrows():
            endur = bool(r.get('enduring_strict', False))
            tfmt = S['text_l_b'] if endur else S['text_l']
            cfmt = S['text_c_b'] if endur else S['text_c']
            mfmt = S['money_b']  if endur else S['money']
            pfmt = S['pct_b']    if endur else S['pct']
            rfmt = S['ratio_b']  if endur else S['ratio']
            write_text(ws, row, 0, r.get('ticker'), tfmt, S['em'])
            write_text(ws, row, 1, str(r.get('name',''))[:26] if pd.notna(r.get('name')) else None, tfmt, S['em'])
            write_text(ws, row, 2, str(r.get('sector',''))[:14] if pd.notna(r.get('sector')) else None, tfmt, S['em'])
            write_text(ws, row, 3, r.get('cap_tier'), tfmt, S['em'])
            write_num(ws, row, 4, r.get('mktCap_M'), mfmt, S['em'])
            write_num(ws, row, 5, topct(r.get('roic_mean')), pfmt, S['em'])
            write_num(ws, row, 6, topct(r.get('roic_min')), pfmt, S['em'])
            write_num(ws, row, 7, topct(r.get('roic_method_agreement')), pfmt, S['em'])
            write_num(ws, row, 8, topct(r.get('roiic_1y')), pfmt, S['em'])
            write_num(ws, row, 9, topct(r.get('roiic_3y')), pfmt, S['em'])
            write_num(ws, row,10, topct(r.get('cc_roic_fcf_mean_4y')), pfmt, S['em'])
            write_num(ws, row,11, r.get('ev_ebit'), rfmt, S['em'])
            write_num(ws, row,12, topct(r.get('fcf_yield')), pfmt, S['em'])
            v = endur
            ws.write_string(row,13, '•' if v else EM_DASH, cfmt if v else S['em'])
            write_num(ws, row,14, r.get('compounder_score'), rfmt, S['em'])
            row += 1

    # Region sheets — sorted by # of ranked tickers
    for region in df['region'].value_counts().index.tolist():
        sub = df[df['region']==region]
        if len(sub) == 0: continue
        sheet_name = REGION_FULLNAME.get(region, region)[:31]
        region_sheet(sheet_name, sub, REGION_FULLNAME.get(region, region.upper()))

    wb.worksheets_objs.insert(0, wb.worksheets_objs.pop(wb.worksheets_objs.index(ws)))

print(f"Wrote {xlsx_path}", file=sys.stderr)
print(f"  {len(df):,} tickers · {df['region'].nunique()} regions · "
      f"{int(df.get('seg_inflection_flag', pd.Series(False)).sum())} segment inflections · "
      f"{int(df.get('backlog_inflection_flag', pd.Series(False)).sum())} backlog inflections",
      file=sys.stderr)
