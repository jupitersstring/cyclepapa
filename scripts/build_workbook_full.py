#!/usr/bin/env python3
"""Harvard-aesthetic workbook showing ALL ranked tickers per region.

Reads v2_universe_ranked_full.csv (16k+ unfiltered) and writes one sheet per
region with EVERY ticker, sorted by all_legs_score. Quality_pass column lets
the user filter post-hoc. Summary sheet shows top 50 worldwide that are
quality_pass + top 50 overall.
"""
import os, sys, datetime
import pandas as pd
import numpy as np

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

df = pd.read_csv('data/synthesis/v2_universe_ranked_full.csv')
print(f"Loaded {len(df)} ranked tickers", file=sys.stderr)

xlsx_path = 'data/synthesis/workbook/candidates_workbook_full.xlsx'
with pd.ExcelWriter(xlsx_path, engine='xlsxwriter') as writer:
    wb = writer.book
    ivory, crimson, charcoal, rule = '#FAF7F2', '#A41E22', '#2B2B2B', '#8B8680'
    serif = 'Georgia'

    title_fmt = wb.add_format({'font_name': serif,'font_size': 22,'bold': True,'font_color': crimson,'bg_color': ivory,'align': 'left','valign': 'vcenter'})
    subtitle_fmt = wb.add_format({'font_name': serif,'font_size': 11,'italic': True,'font_color': charcoal,'bg_color': ivory,'align': 'left'})
    header_fmt = wb.add_format({'font_name': serif,'font_size': 9,'bold': True,'font_color': ivory,'bg_color': crimson,'align': 'center','valign': 'vcenter','border': 1,'border_color': charcoal})
    cell_fmt = wb.add_format({'font_name': serif,'font_size': 10,'font_color': charcoal,'bg_color': ivory,'align': 'left','border': 1,'border_color': rule})
    quality_cell = wb.add_format({'font_name': serif,'font_size': 10,'bold': True,'font_color': crimson,'bg_color': ivory,'align': 'left','border': 1,'border_color': rule})
    cell_num_fmt = wb.add_format({'font_name': serif,'font_size': 10,'font_color': charcoal,'bg_color': ivory,'align': 'right','num_format': '0.0','border': 1,'border_color': rule})
    cell_int_fmt = wb.add_format({'font_name': serif,'font_size': 10,'font_color': charcoal,'bg_color': ivory,'align': 'right','num_format': '0','border': 1,'border_color': rule})
    cell_pct_fmt = wb.add_format({'font_name': serif,'font_size': 10,'font_color': charcoal,'bg_color': ivory,'align': 'right','num_format': '0.0%','border': 1,'border_color': rule})
    section_fmt = wb.add_format({'font_name': serif,'font_size': 11,'bold': True,'italic': True,'font_color': crimson,'bg_color': ivory,'align': 'left'})
    body_fmt = wb.add_format({'font_name': serif,'font_size': 10,'font_color': charcoal,'bg_color': ivory,'text_wrap': True,'valign': 'top'})

    def write_region(name, region_df, label, max_rows=10000):
        ws = wb.add_worksheet(name[:31])
        ws.set_tab_color(crimson)
        ws.hide_gridlines(2)
        ws.set_default_row(16)
        ws.freeze_panes(4, 0)
        ws.set_row(0, 30)
        ws.merge_range(0, 0, 0, 14, label, title_fmt)
        ws.set_row(1, 14)
        n_q = region_df['quality_pass'].sum() if 'quality_pass' in region_df else 0
        n_ql = region_df['quality_pass_loose'].sum() if 'quality_pass_loose' in region_df else 0
        ws.merge_range(1, 0, 1, 14,
            f"{len(region_df)} tickers ranked · {n_q} strict · {n_ql} loose · {datetime.date.today().isoformat()}",
            subtitle_fmt)
        widths = [9, 24, 11, 4, 4, 5, 5, 5, 5, 5, 7, 7, 7, 5, 7]
        for c, w in enumerate(widths): ws.set_column(c, c, w)
        headers = ['Ticker','Name','Cap','Q','QL','Macro','D %','TD %','F %','Lens','EV/EBITDA','FCF Y','Rev G','Macro','Score']
        for c, h in enumerate(headers): ws.write(3, c, h, header_fmt)
        ws.set_row(3, 22)
        last_row = min(len(region_df), max_rows) + 3
        ws.autofilter(3, 0, last_row, 14)
        for i, (_, r) in enumerate(region_df.head(max_rows).iterrows()):
            row = 4 + i
            qpass = bool(r.get('quality_pass', False))
            qloose = bool(r.get('quality_pass_loose', False))
            fmt = quality_cell if qpass else cell_fmt
            ws.write(row, 0, str(r.get('ticker','')), fmt)
            ws.write(row, 1, str(r.get('name',''))[:32] if pd.notna(r.get('name')) else '', fmt)
            ws.write(row, 2, str(r.get('cap_tier',''))[:9], fmt)
            ws.write(row, 3, 'Y' if qpass else '', fmt)
            ws.write(row, 4, 'Y' if qloose else '', fmt)
            ws.write(row, 5, int(r.get('absW_macro',0)) if pd.notna(r.get('absW_macro')) else '', cell_int_fmt)
            for c_idx, leg in enumerate(['leg_dalton','leg_td','leg_fund'], start=6):
                v = r.get(leg, np.nan)
                ws.write(row, c_idx, v if pd.notna(v) else '', cell_num_fmt)
            tags = ''
            if r.get('absorp_pass'): tags += 'A'
            if r.get('prebo_pass'): tags += 'P'
            if r.get('compress_pass'): tags += 'C'
            ws.write(row, 9, tags, cell_fmt)
            evb = r.get('ev_valuation')
            ws.write(row, 10, float(evb) if pd.notna(evb) and abs(evb)<1e4 else '', cell_num_fmt)
            fy = r.get('fcf_yield_clean')
            ws.write(row, 11, float(fy) if pd.notna(fy) else '', cell_pct_fmt)
            rg = r.get('rev_g_clean')
            ws.write(row, 12, float(rg) if pd.notna(rg) else '', cell_pct_fmt)
            ws.write(row, 13, int(r.get('absW_macro',0)) if pd.notna(r.get('absW_macro')) else '', cell_int_fmt)
            ws.write(row, 14, float(r.get('all_legs_score',0)), cell_num_fmt)

    # Summary
    ws_sum = wb.add_worksheet('Summary')
    ws_sum.set_tab_color(crimson); ws_sum.hide_gridlines(2)
    ws_sum.set_row(0, 36)
    ws_sum.merge_range(0, 0, 0, 13, 'Asymmetric Setups · Full-Universe Workbook', title_fmt)
    ws_sum.merge_range(1, 0, 1, 13,
        f"{datetime.date.today().isoformat()} · {len(df)} ranked tickers across "
        f"{df['region'].nunique()} markets · {df['quality_pass'].sum()} quality-pass",
        subtitle_fmt)
    methodology = (
        "Methodology — every ticker in the screening universe gets a composite "
        "score across three core legs (Dalton asymmetric inflection, TD Sequential "
        "mean reversion, Fundamentals: EV/EBITDA + FCF yield + revenue growth + "
        "operating margin) plus three structural lenses (Wyckoff Absorption, "
        "Weinstein/Qullamaggie Pre-breakout, MFI-higher-low Compression). Cross-leg "
        "score = 55% average leg percentile + 30% weakest-leg percentile + lens "
        "bonus. The 'Q' column flags names that ALSO pass the strict asymmetric "
        "quality filter (Dalton macro ≥ 25, asymmetry ≥ 1.5×, position 20–85, no "
        "monthly conflict, positive risk margin, ≥1 bullish timeframe). Filter on "
        "Q=Y to see only the highest-conviction setups."
    )
    ws_sum.set_column(0, 13, 12)
    ws_sum.merge_range(3, 0, 9, 13, methodology, body_fmt)

    # Top 30 overall + top 30 quality
    top_overall = df.head(30)
    top_quality = df[df['quality_pass']].head(30)
    headers = ['Ticker','Name','Region','Cap','Q','D %','TD %','F %','Lens','EV/EBITDA','FCF Y','Rev G','Macro','Score']
    for c, h in enumerate(headers): ws_sum.write(11, c, h, header_fmt)
    ws_sum.set_row(11, 22)
    ws_sum.write(10, 0, 'Top 30 — Overall (any name with score)', section_fmt)
    for i, (_, r) in enumerate(top_overall.iterrows()):
        row = 12 + i
        qpass = bool(r.get('quality_pass', False))
        fmt = quality_cell if qpass else cell_fmt
        ws_sum.write(row, 0, str(r.get('ticker','')), fmt)
        ws_sum.write(row, 1, str(r.get('name',''))[:30] if pd.notna(r.get('name')) else '', fmt)
        ws_sum.write(row, 2, REGION_FULLNAME.get(r.get('region',''), r.get('region','')), fmt)
        ws_sum.write(row, 3, str(r.get('cap_tier',''))[:9], fmt)
        ws_sum.write(row, 4, 'Y' if qpass else '', fmt)
        for c_idx, leg in enumerate(['leg_dalton','leg_td','leg_fund'], start=5):
            v = r.get(leg, np.nan)
            ws_sum.write(row, c_idx, v if pd.notna(v) else '', cell_num_fmt)
        tags = ''
        if r.get('absorp_pass'): tags += 'A'
        if r.get('prebo_pass'): tags += 'P'
        if r.get('compress_pass'): tags += 'C'
        ws_sum.write(row, 8, tags, cell_fmt)
        evb = r.get('ev_valuation'); ws_sum.write(row, 9, float(evb) if pd.notna(evb) and abs(evb)<1e4 else '', cell_num_fmt)
        fy = r.get('fcf_yield_clean'); ws_sum.write(row, 10, float(fy) if pd.notna(fy) else '', cell_pct_fmt)
        rg = r.get('rev_g_clean'); ws_sum.write(row, 11, float(rg) if pd.notna(rg) else '', cell_pct_fmt)
        ws_sum.write(row, 12, int(r.get('absW_macro',0)) if pd.notna(r.get('absW_macro')) else '', cell_int_fmt)
        ws_sum.write(row, 13, float(r.get('all_legs_score',0)), cell_num_fmt)

    base_row = 12 + len(top_overall) + 2
    ws_sum.write(base_row-1, 0, 'Top 30 — Quality-Pass Only (highest conviction)', section_fmt)
    for c, h in enumerate(headers): ws_sum.write(base_row, c, h, header_fmt)
    for i, (_, r) in enumerate(top_quality.iterrows()):
        row = base_row + 1 + i
        ws_sum.write(row, 0, str(r.get('ticker','')), quality_cell)
        ws_sum.write(row, 1, str(r.get('name',''))[:30] if pd.notna(r.get('name')) else '', quality_cell)
        ws_sum.write(row, 2, REGION_FULLNAME.get(r.get('region',''), r.get('region','')), quality_cell)
        ws_sum.write(row, 3, str(r.get('cap_tier',''))[:9], quality_cell)
        ws_sum.write(row, 4, 'Y', quality_cell)
        for c_idx, leg in enumerate(['leg_dalton','leg_td','leg_fund'], start=5):
            v = r.get(leg, np.nan)
            ws_sum.write(row, c_idx, v if pd.notna(v) else '', cell_num_fmt)
        tags = ''
        if r.get('absorp_pass'): tags += 'A'
        if r.get('prebo_pass'): tags += 'P'
        if r.get('compress_pass'): tags += 'C'
        ws_sum.write(row, 8, tags, cell_fmt)
        evb = r.get('ev_valuation'); ws_sum.write(row, 9, float(evb) if pd.notna(evb) and abs(evb)<1e4 else '', cell_num_fmt)
        fy = r.get('fcf_yield_clean'); ws_sum.write(row, 10, float(fy) if pd.notna(fy) else '', cell_pct_fmt)
        rg = r.get('rev_g_clean'); ws_sum.write(row, 11, float(rg) if pd.notna(rg) else '', cell_pct_fmt)
        ws_sum.write(row, 12, int(r.get('absW_macro',0)) if pd.notna(r.get('absW_macro')) else '', cell_int_fmt)
        ws_sum.write(row, 13, float(r.get('all_legs_score',0)), cell_num_fmt)

    region_order = df['region'].value_counts().index.tolist()
    for region in region_order:
        sub = df[df['region']==region]
        if len(sub) == 0: continue
        sheet_name = REGION_FULLNAME.get(region, region)[:31]
        write_region(sheet_name, sub, REGION_FULLNAME.get(region, region.upper()))

    wb.worksheets_objs.insert(0, wb.worksheets_objs.pop(wb.worksheets_objs.index(ws_sum)))

print(f"Workbook: {xlsx_path}", file=sys.stderr)
print(f"  Total tickers ranked: {len(df)}", file=sys.stderr)
print(f"  Sheets: 1 Summary + {df['region'].nunique()} regions (each with autofilter on Q column)", file=sys.stderr)
