#!/usr/bin/env python3
"""Harvard-aesthetic workbook with financial-statement number formatting.

Layout rules:
  • Text columns (ticker, name, cap, sector, lens, flags) — left-aligned, no num format
  • Currency raw $ (mktCap, EV) — right-aligned, `#,##0;(#,##0);"–"`
  • Currency in millions (_M cols) — right-aligned, `#,##0;(#,##0);"–"`
  • Percentages (%-units, growth, margin) — right-aligned, `#,##0.0;(#,##0.0);"–"`
  • Ratios (P/E, EV/EBITDA, scores) — right-aligned, `#,##0.00;(#,##0.00);"–"`
  • Prices, EPS — right-aligned, `#,##0.00;(#,##0.00);"–"`
  • Negatives in parentheses (financial convention)
  • Em-dash (–) for empty cells
"""
import os, sys, datetime
import pandas as pd
import numpy as np

EM_DASH = '–'

os.makedirs('data/synthesis/workbook', exist_ok=True)

REGION_FULLNAME = {
    'us':'United States','uk':'United Kingdom','japan':'Japan','germany':'Germany',
    'france':'France','italy':'Italy','spain':'Spain','netherlands':'Netherlands',
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
for col in ['qmaggie_pass','ep_pass']:
    if col not in df.columns: df[col] = False
    df[col] = df[col].fillna(False).astype(bool)

# Convert raw fcf_yield and rev_g (already as fraction 0.054 = 5.4%) to %-units for nicer display
df['fcf_yield_pct'] = df['fcf_yield_clean'] * 100 if 'fcf_yield_clean' in df.columns else np.nan
df['rev_g_pct'] = df['rev_g_clean'] * 100 if 'rev_g_clean' in df.columns else np.nan

# Market cap in millions
if 'mktCap' in df.columns:
    df['mktCap_M'] = pd.to_numeric(df['mktCap'], errors='coerce') / 1e6

print(f"Loaded {len(df)} ranked tickers from {src}", file=sys.stderr)

xlsx_path = 'data/synthesis/workbook/candidates_workbook_full.xlsx'
with pd.ExcelWriter(xlsx_path, engine='xlsxwriter') as writer:
    wb = writer.book
    ivory, crimson, charcoal, rule = '#FAF7F2', '#A41E22', '#2B2B2B', '#8B8680'
    serif = 'Georgia'

    title_fmt    = wb.add_format({'font_name': serif,'font_size': 22,'bold': True,'font_color': crimson,'bg_color': ivory,'align': 'left','valign': 'vcenter'})
    subtitle_fmt = wb.add_format({'font_name': serif,'font_size': 11,'italic': True,'font_color': charcoal,'bg_color': ivory,'align': 'left'})
    header_fmt   = wb.add_format({'font_name': serif,'font_size': 9,'bold': True,'font_color': ivory,'bg_color': crimson,'align': 'center','valign': 'vcenter','border': 1,'border_color': charcoal})
    section_fmt  = wb.add_format({'font_name': serif,'font_size': 11,'bold': True,'italic': True,'font_color': crimson,'bg_color': ivory,'align': 'left'})
    body_fmt     = wb.add_format({'font_name': serif,'font_size': 10,'font_color': charcoal,'bg_color': ivory,'text_wrap': True,'valign': 'top'})

    # Text formats
    text_left      = wb.add_format({'font_name': serif,'font_size': 10,'font_color': charcoal,'bg_color': ivory,'align': 'left','border': 1,'border_color': rule})
    text_left_em   = wb.add_format({'font_name': serif,'font_size': 10,'font_color': charcoal,'bg_color': ivory,'align': 'right','border': 1,'border_color': rule})  # em-dash, right aligned per numeric column convention
    text_left_q    = wb.add_format({'font_name': serif,'font_size': 10,'bold': True,'font_color': crimson,'bg_color': ivory,'align': 'left','border': 1,'border_color': rule})

    # Number formats — financial-statement convention (negatives in parens)
    money_fmt  = wb.add_format({'font_name': serif,'font_size': 10,'font_color': charcoal,'bg_color': ivory,'align': 'right','num_format': '#,##0;(#,##0)','border': 1,'border_color': rule})
    pct_fmt    = wb.add_format({'font_name': serif,'font_size': 10,'font_color': charcoal,'bg_color': ivory,'align': 'right','num_format': '#,##0.0;(#,##0.0)','border': 1,'border_color': rule})
    ratio_fmt  = wb.add_format({'font_name': serif,'font_size': 10,'font_color': charcoal,'bg_color': ivory,'align': 'right','num_format': '#,##0.00;(#,##0.00)','border': 1,'border_color': rule})

    money_fmt_q = wb.add_format({'font_name': serif,'font_size': 10,'bold': True,'font_color': crimson,'bg_color': ivory,'align': 'right','num_format': '#,##0;(#,##0)','border': 1,'border_color': rule})
    pct_fmt_q   = wb.add_format({'font_name': serif,'font_size': 10,'bold': True,'font_color': crimson,'bg_color': ivory,'align': 'right','num_format': '#,##0.0;(#,##0.0)','border': 1,'border_color': rule})
    ratio_fmt_q = wb.add_format({'font_name': serif,'font_size': 10,'bold': True,'font_color': crimson,'bg_color': ivory,'align': 'right','num_format': '#,##0.00;(#,##0.00)','border': 1,'border_color': rule})

    def write_num(ws, row, col, v, fmt, em_fmt):
        """Write a number with em-dash for NaN/None/inf, financial format otherwise."""
        if v is None or pd.isna(v):
            ws.write_string(row, col, EM_DASH, em_fmt)
        else:
            try:
                fv = float(v)
                if not np.isfinite(fv) or abs(fv) > 1e15:
                    ws.write_string(row, col, EM_DASH, em_fmt)
                else:
                    ws.write_number(row, col, fv, fmt)
            except Exception:
                ws.write_string(row, col, EM_DASH, em_fmt)

    def write_text(ws, row, col, v, fmt, em_fmt):
        """Write text with em-dash for None/empty."""
        if v is None or (isinstance(v, float) and pd.isna(v)) or str(v).strip() in ('', 'nan', 'None'):
            ws.write_string(row, col, EM_DASH, em_fmt)
        else:
            ws.write_string(row, col, str(v), fmt)

    # ─── Region sheets ────────────────────────────────────────────────────
    def write_region(name, region_df, label, max_rows=10000):
        ws = wb.add_worksheet(name[:31])
        ws.set_tab_color(crimson); ws.hide_gridlines(2)
        ws.set_default_row(16)
        ws.freeze_panes(4, 0)
        ws.set_row(0, 30)
        n_q   = int(region_df['quality_pass'].sum())  if 'quality_pass'  in region_df else 0
        n_ql  = int(region_df['quality_pass_loose'].sum()) if 'quality_pass_loose' in region_df else 0
        n_qm  = int(region_df['qmaggie_pass'].sum()) if 'qmaggie_pass' in region_df else 0
        n_ep  = int(region_df['ep_pass'].sum())      if 'ep_pass'      in region_df else 0
        ncols = 17
        ws.merge_range(0, 0, 0, ncols-1, label, title_fmt)
        ws.set_row(1, 14)
        ws.merge_range(1, 0, 1, ncols-1,
            f"{len(region_df)} ranked · {n_q} Q-strict · {n_ql} Q-loose · {n_qm} Qmaggie · {n_ep} EP · {datetime.date.today().isoformat()}",
            subtitle_fmt)

        # Column widths
        widths = {0:9, 1:30, 2:11, 3:4, 4:4, 5:4, 6:4, 7:6, 8:6, 9:6, 10:6, 11:5, 12:10, 13:7, 14:7, 15:14, 16:7}
        for c, w in widths.items(): ws.set_column(c, c, w)
        headers = ['Ticker','Company','Cap','Q','QL','Qm','EP','Macro','D %','TD %','F %','Lens','EV / EBITDA','FCF Y','Rev G','Market Cap','Score']
        for c, h in enumerate(headers): ws.write(3, c, h, header_fmt)
        ws.set_row(3, 22)

        last_row = min(len(region_df), max_rows) + 3
        ws.autofilter(3, 0, last_row, ncols-1)

        for i, (_, r) in enumerate(region_df.head(max_rows).iterrows()):
            row = 4 + i
            qpass = bool(r.get('quality_pass', False))
            text_fmt = text_left_q if qpass else text_left
            money_n  = money_fmt_q if qpass else money_fmt
            pct_n    = pct_fmt_q if qpass else pct_fmt
            ratio_n  = ratio_fmt_q if qpass else ratio_fmt

            write_text(ws, row, 0, r.get('ticker'), text_fmt, text_left_em)
            write_text(ws, row, 1, str(r.get('name'))[:34] if pd.notna(r.get('name')) else None, text_fmt, text_left_em)
            write_text(ws, row, 2, r.get('cap_tier'), text_fmt, text_left_em)
            ws.write_string(row, 3, 'Y' if qpass else EM_DASH, text_fmt if qpass else text_left_em)
            ws.write_string(row, 4, 'Y' if bool(r.get('quality_pass_loose', False)) else EM_DASH, text_fmt if bool(r.get('quality_pass_loose', False)) else text_left_em)
            ws.write_string(row, 5, 'Y' if bool(r.get('qmaggie_pass', False)) else EM_DASH, text_fmt if bool(r.get('qmaggie_pass', False)) else text_left_em)
            ws.write_string(row, 6, 'Y' if bool(r.get('ep_pass', False))     else EM_DASH, text_fmt if bool(r.get('ep_pass', False)) else text_left_em)
            write_num(ws, row, 7, r.get('absW_macro'), money_n, text_left_em)
            write_num(ws, row, 8, r.get('leg_dalton'), pct_n, text_left_em)
            write_num(ws, row, 9, r.get('leg_td'),     pct_n, text_left_em)
            write_num(ws, row,10, r.get('leg_fund'),   pct_n, text_left_em)
            tags = ''
            if r.get('absorp_pass'): tags += 'A'
            if r.get('prebo_pass'): tags += 'P'
            if r.get('compress_pass'): tags += 'C'
            ws.write_string(row, 11, tags or EM_DASH, text_fmt if tags else text_left_em)
            write_num(ws, row,12, r.get('ev_valuation'), ratio_n, text_left_em)
            write_num(ws, row,13, r.get('fcf_yield_pct'), pct_n, text_left_em)
            write_num(ws, row,14, r.get('rev_g_pct'), pct_n, text_left_em)
            write_num(ws, row,15, r.get('mktCap_M') if 'mktCap_M' in r.index else None, money_n, text_left_em)
            write_num(ws, row,16, r.get('all_legs_score'), ratio_n, text_left_em)

    # ─── Summary ──────────────────────────────────────────────────────────
    ws_sum = wb.add_worksheet('Summary')
    ws_sum.set_tab_color(crimson); ws_sum.hide_gridlines(2)
    ws_sum.set_row(0, 36)
    ws_sum.merge_range(0, 0, 0, 14, 'Asymmetric Setups · Full-Universe Workbook', title_fmt)
    ws_sum.merge_range(1, 0, 1, 14,
        f"{datetime.date.today().isoformat()} · {len(df):,} ranked tickers across "
        f"{df['region'].nunique()} markets · {int(df['quality_pass'].sum()):,} Q-strict",
        subtitle_fmt)
    methodology = (
        "Methodology — every ticker in the screening universe receives a composite score across three core legs "
        "(Dalton asymmetric inflection, TD Sequential mean reversion, Fundamentals: EV/EBITDA + FCF yield + revenue "
        "growth + operating margin) plus three structural lenses (Wyckoff Absorption, Weinstein/O'Neil Pre-breakout, "
        "MFI-higher-low Compression). Cross-leg score = 55% average leg percentile + 30% weakest-leg percentile + lens "
        "bonus.\n\nFlags: Q = strict asymmetric (macro ≥ 25, asymmetry ≥ 1.5×, bracket 20–85%, no monthly conflict, "
        "positive risk margin, ≥1 bullish timeframe). QL = looser (macro ≥ 18, asymmetry ≥ 1.15×). Qm = proper Qullamaggie "
        "continuation breakout (30-100% leg in past 1-3 months, 10/20-day SMA surf, ADR ≤ 6%, 2w–2mo base). "
        "EP = Episodic Pivot (≥10% gap on ≥2× volume, prior 3-6mo sideways).\n\n"
        "Negatives shown in parentheses (financial-statement convention); em-dash for missing data."
    )
    ws_sum.set_column(0, 14, 12)
    ws_sum.merge_range(3, 0, 9, 14, methodology, body_fmt)

    sum_headers = ['Ticker','Company','Region','Cap','Q','Qm','D %','TD %','F %','Lens','EV / EBITDA','FCF Y','Rev G','Market Cap','Score']
    def write_sum_row(ws, row, r):
        qpass = bool(r.get('quality_pass', False))
        text_fmt = text_left_q if qpass else text_left
        pct_n   = pct_fmt_q if qpass else pct_fmt
        ratio_n = ratio_fmt_q if qpass else ratio_fmt
        money_n = money_fmt_q if qpass else money_fmt
        write_text(ws, row, 0, r.get('ticker'), text_fmt, text_left_em)
        write_text(ws, row, 1, str(r.get('name'))[:30] if pd.notna(r.get('name')) else None, text_fmt, text_left_em)
        write_text(ws, row, 2, REGION_FULLNAME.get(r.get('region',''), r.get('region','')), text_fmt, text_left_em)
        write_text(ws, row, 3, str(r.get('cap_tier',''))[:9], text_fmt, text_left_em)
        ws.write_string(row, 4, 'Y' if qpass else EM_DASH, text_fmt if qpass else text_left_em)
        ws.write_string(row, 5, 'Y' if bool(r.get('qmaggie_pass', False)) else EM_DASH, text_fmt if bool(r.get('qmaggie_pass', False)) else text_left_em)
        write_num(ws, row, 6, r.get('leg_dalton'), pct_n, text_left_em)
        write_num(ws, row, 7, r.get('leg_td'),     pct_n, text_left_em)
        write_num(ws, row, 8, r.get('leg_fund'),   pct_n, text_left_em)
        tags = ''
        if r.get('absorp_pass'): tags += 'A'
        if r.get('prebo_pass'): tags += 'P'
        if r.get('compress_pass'): tags += 'C'
        ws.write_string(row, 9, tags or EM_DASH, text_fmt if tags else text_left_em)
        write_num(ws, row,10, r.get('ev_valuation'), ratio_n, text_left_em)
        write_num(ws, row,11, r.get('fcf_yield_pct'), pct_n, text_left_em)
        write_num(ws, row,12, r.get('rev_g_pct'), pct_n, text_left_em)
        write_num(ws, row,13, r.get('mktCap_M'), money_n, text_left_em)
        write_num(ws, row,14, r.get('all_legs_score'), ratio_n, text_left_em)

    ws_sum.write(10, 0, 'Top 30 — Overall (any name with score)', section_fmt)
    for c, h in enumerate(sum_headers): ws_sum.write(11, c, h, header_fmt)
    ws_sum.set_row(11, 22)
    for i, (_, r) in enumerate(df.head(30).iterrows()):
        write_sum_row(ws_sum, 12 + i, r)

    base_row = 12 + 30 + 2
    ws_sum.write(base_row-1, 0, 'Top 30 — Quality-Strict Only (highest conviction)', section_fmt)
    for c, h in enumerate(sum_headers): ws_sum.write(base_row, c, h, header_fmt)
    top_quality = df[df['quality_pass']].head(30)
    for i, (_, r) in enumerate(top_quality.iterrows()):
        write_sum_row(ws_sum, base_row + 1 + i, r)

    # Qmaggie cohort table
    base_row2 = base_row + 1 + len(top_quality) + 2
    qmag = df[df['qmaggie_pass']].sort_values('best_leg_pct', ascending=False).head(30) if 'best_leg_pct' in df.columns else df[df['qmaggie_pass']].head(30)
    if len(qmag):
        ws_sum.write(base_row2-1, 0, f'Qullamaggie Cohort ({len(df[df["qmaggie_pass"]])} names)', section_fmt)
        qh = ['Ticker','Company','Region','Cap','Leg %','ADR %','Consol Days','Ret 3m %','Below LegHigh %','EV/EBITDA','Score']
        for c, h in enumerate(qh): ws_sum.write(base_row2, c, h, header_fmt)
        for i, (_, r) in enumerate(qmag.iterrows()):
            row = base_row2 + 1 + i
            write_text(ws_sum, row, 0, r.get('ticker'), text_left_q, text_left_em)
            write_text(ws_sum, row, 1, str(r.get('name'))[:30] if pd.notna(r.get('name')) else None, text_left_q, text_left_em)
            write_text(ws_sum, row, 2, REGION_FULLNAME.get(r.get('region',''), r.get('region','')), text_left_q, text_left_em)
            write_text(ws_sum, row, 3, str(r.get('cap_tier',''))[:9], text_left_q, text_left_em)
            write_num(ws_sum, row, 4, r.get('best_leg_pct'), pct_fmt_q, text_left_em)
            write_num(ws_sum, row, 5, r.get('adr_pct'), pct_fmt_q, text_left_em)
            write_num(ws_sum, row, 6, r.get('consol_days'), money_fmt_q, text_left_em)
            write_num(ws_sum, row, 7, r.get('ret_3m_pct'), pct_fmt_q, text_left_em)
            write_num(ws_sum, row, 8, r.get('pct_below_leg_high'), pct_fmt_q, text_left_em)
            write_num(ws_sum, row, 9, r.get('ev_valuation'), ratio_fmt_q, text_left_em)
            write_num(ws_sum, row,10, r.get('all_legs_score'), ratio_fmt_q, text_left_em)

    region_order = df['region'].value_counts().index.tolist()
    for region in region_order:
        sub = df[df['region']==region]
        if len(sub) == 0: continue
        sheet_name = REGION_FULLNAME.get(region, region)[:31]
        write_region(sheet_name, sub, REGION_FULLNAME.get(region, region.upper()))

    wb.worksheets_objs.insert(0, wb.worksheets_objs.pop(wb.worksheets_objs.index(ws_sum)))

print(f"Workbook: {xlsx_path}", file=sys.stderr)
print(f"  Total tickers ranked: {len(df):,}", file=sys.stderr)
print(f"  Sheets: 1 Summary + {df['region'].nunique()} regions", file=sys.stderr)
