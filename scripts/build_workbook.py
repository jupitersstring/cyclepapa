#!/usr/bin/env python3
"""Build a Harvard-aesthetic xlsx + HTML workbook showing top N candidates per region.

Aesthetic: serif typography, ivory/parchment background, crimson accent, restrained.
Layout: one sheet per region with top 25 ranked across all legs, plus a summary
sheet (top picks worldwide) and a methodology sheet.
"""
import os, sys, datetime
import pandas as pd
import numpy as np

os.makedirs('data/synthesis/workbook', exist_ok=True)

# Region name normalization
REGION_FULLNAME = {
    'us':'United States','uk':'United Kingdom','japan':'Japan','germany':'Germany',
    'france':'France','italy':'Italy','spain':'Spain','netherlands':'Netherlands',
    'belgium':'Belgium','switzerland':'Switzerland','sweden':'Sweden','norway':'Norway',
    'finland':'Finland','denmark':'Denmark','ireland':'Ireland','austria':'Austria',
    'portugal':'Portugal','greece':'Greece','canada':'Canada','australia':'Australia',
    'nz':'New Zealand','hk':'Hong Kong','china':'China','japan':'Japan','korea':'South Korea',
    'taiwan':'Taiwan','singapore':'Singapore','thailand':'Thailand','indonesia':'Indonesia',
    'india':'India','israel':'Israel','turkey':'Turkey','brazil':'Brazil','mexico':'Mexico',
    'argentina':'Argentina','chile':'Chile','southafrica':'South Africa',
}

# Load full universe ranking
df = pd.read_csv('data/synthesis/v2_full_universe_ranked.csv')
print(f"Loaded {len(df)} ranked quality candidates", file=sys.stderr)

# ─── Excel workbook ───
xlsx_path = 'data/synthesis/workbook/candidates_workbook.xlsx'
with pd.ExcelWriter(xlsx_path, engine='xlsxwriter') as writer:
    wb = writer.book

    # ─── Formats: Harvard palette ─────────────────────────────────────────
    ivory     = '#FAF7F2'
    crimson   = '#A41E22'   # Harvard crimson
    charcoal  = '#2B2B2B'
    rule      = '#8B8680'
    serif     = 'Georgia'

    title_fmt = wb.add_format({
        'font_name': serif, 'font_size': 22, 'bold': True,
        'font_color': crimson, 'bg_color': ivory, 'align': 'left', 'valign': 'vcenter',
    })
    subtitle_fmt = wb.add_format({
        'font_name': serif, 'font_size': 11, 'italic': True,
        'font_color': charcoal, 'bg_color': ivory, 'align': 'left',
    })
    header_fmt = wb.add_format({
        'font_name': serif, 'font_size': 9, 'bold': True,
        'font_color': ivory, 'bg_color': crimson, 'align': 'center',
        'valign': 'vcenter', 'border': 1, 'border_color': charcoal,
    })
    cell_fmt = wb.add_format({
        'font_name': serif, 'font_size': 10, 'font_color': charcoal,
        'bg_color': ivory, 'align': 'left', 'border': 1, 'border_color': rule,
    })
    cell_num_fmt = wb.add_format({
        'font_name': serif, 'font_size': 10, 'font_color': charcoal,
        'bg_color': ivory, 'align': 'right', 'num_format': '0.0',
        'border': 1, 'border_color': rule,
    })
    cell_int_fmt = wb.add_format({
        'font_name': serif, 'font_size': 10, 'font_color': charcoal,
        'bg_color': ivory, 'align': 'right', 'num_format': '0',
        'border': 1, 'border_color': rule,
    })
    cell_pct_fmt = wb.add_format({
        'font_name': serif, 'font_size': 10, 'font_color': charcoal,
        'bg_color': ivory, 'align': 'right', 'num_format': '0.0%',
        'border': 1, 'border_color': rule,
    })
    section_fmt = wb.add_format({
        'font_name': serif, 'font_size': 11, 'bold': True, 'italic': True,
        'font_color': crimson, 'bg_color': ivory, 'align': 'left',
    })
    body_fmt = wb.add_format({
        'font_name': serif, 'font_size': 10, 'font_color': charcoal,
        'bg_color': ivory, 'text_wrap': True, 'valign': 'top',
    })

    def write_region_sheet(name, region_df, region_label):
        ws = wb.add_worksheet(name[:31])
        ws.set_tab_color(crimson)
        ws.hide_gridlines(2)
        ws.set_default_row(18)
        # Title block
        ws.set_row(0, 32)
        ws.merge_range(0, 0, 0, 11, region_label, title_fmt)
        ws.set_row(1, 16)
        ws.merge_range(1, 0, 1, 11,
            f"Cross-leg asymmetric ranking · {datetime.date.today().isoformat()} · "
            f"{len(region_df)} qualifying name{'s' if len(region_df)!=1 else ''}",
            subtitle_fmt)
        # Column widths
        widths = [9, 22, 11, 6, 5, 5, 5, 5, 7, 7, 7, 7]
        for c, w in enumerate(widths):
            ws.set_column(c, c, w)
        # Headers
        headers = ['Ticker','Name','Cap','Macro','D %','TD %','F %','Lens',
                   'EV/EBITDA','FCF Y','Rev G','Score']
        for c, h in enumerate(headers):
            ws.write(3, c, h, header_fmt)
        ws.set_row(3, 24)
        # Rows
        for i, (_, r) in enumerate(region_df.iterrows()):
            row = 4 + i
            ws.write(row, 0, str(r.get('ticker','')), cell_fmt)
            ws.write(row, 1, str(r.get('name',''))[:30] if pd.notna(r.get('name')) else '', cell_fmt)
            ws.write(row, 2, str(r.get('cap_tier',''))[:8], cell_fmt)
            ws.write(row, 3, int(r.get('absW_macro',0)) if pd.notna(r.get('absW_macro')) else 0, cell_int_fmt)
            ws.write(row, 4, r.get('leg_dalton', np.nan) if pd.notna(r.get('leg_dalton')) else '', cell_num_fmt)
            ws.write(row, 5, r.get('leg_td', np.nan) if pd.notna(r.get('leg_td')) else '', cell_num_fmt)
            ws.write(row, 6, r.get('leg_fund', np.nan) if pd.notna(r.get('leg_fund')) else '', cell_num_fmt)
            tags = ''
            if r.get('absorp_pass'): tags += 'A'
            if r.get('prebo_pass'): tags += 'P'
            if r.get('compress_pass'): tags += 'C'
            ws.write(row, 7, tags, cell_fmt)
            evb = r.get('ev_valuation')
            ws.write(row, 8, float(evb) if pd.notna(evb) and abs(evb) < 1e4 else '', cell_num_fmt)
            fy = r.get('fcf_yield_clean')
            ws.write(row, 9, float(fy) if pd.notna(fy) else '', cell_pct_fmt)
            rg = r.get('rev_g_clean')
            ws.write(row, 10, float(rg) if pd.notna(rg) else '', cell_pct_fmt)
            ws.write(row, 11, float(r.get('all_legs_score', 0)), cell_num_fmt)

    # ─── Summary sheet: top picks worldwide ───
    ws_sum = wb.add_worksheet('Summary')
    ws_sum.set_tab_color(crimson)
    ws_sum.hide_gridlines(2)
    ws_sum.set_row(0, 36)
    ws_sum.merge_range(0, 0, 0, 11, 'Asymmetric Setups · Cross-Region Workbook', title_fmt)
    ws_sum.set_row(1, 16)
    ws_sum.merge_range(1, 0, 1, 11,
        f"Compiled {datetime.date.today().isoformat()} · {len(df)} ranked candidates across {df['region'].nunique()} markets",
        subtitle_fmt)

    # Methodology box
    methodology = (
        "Methodology — each ticker scored on three core legs (Dalton asymmetric inflection, "
        "TD Sequential mean reversion, Fundamentals: EV/EBITDA + FCF yield + revenue growth + "
        "operating margin) and three binary structural lenses (Wyckoff Absorption, "
        "Weinstein/Qullamaggie Pre-breakout, Compression). Cross-leg score = 55% average leg "
        "percentile + 30% weakest-leg percentile + lens bonus. The weakest-leg gate enforces "
        "consistency: no name ranks high with a thin or contradictory leg.\n\n"
        "Quality filter: Dalton 5-pillar macro ≥ 25, asymmetry ratio ≥ 1.5, position in bracket "
        "20–85, no monthly bear vs weekly bull conflict, strict positive risk margin, ≥1 "
        "bullish timeframe. Cross-listings deduplicated by name; ADR fcf_yield artifacts "
        "winsorized at 50%; EV/EBIT replaced with EV/EBITDA across the board."
    )
    ws_sum.set_column(0, 11, 13)
    ws_sum.merge_range(3, 0, 8, 11, methodology, body_fmt)

    # Top 30 globally
    top_global = df.head(30)
    ws_sum.write(10, 0, 'Top 30 — Worldwide', section_fmt)
    headers = ['Ticker','Name','Region','Cap','D %','TD %','F %','Lens','EV/EBITDA','FCF Y','Rev G','Score']
    for c, h in enumerate(headers):
        ws_sum.write(11, c, h, header_fmt)
    ws_sum.set_row(11, 24)
    for i, (_, r) in enumerate(top_global.iterrows()):
        row = 12 + i
        ws_sum.write(row, 0, str(r.get('ticker','')), cell_fmt)
        ws_sum.write(row, 1, str(r.get('name',''))[:30] if pd.notna(r.get('name')) else '', cell_fmt)
        ws_sum.write(row, 2, REGION_FULLNAME.get(r.get('region',''), r.get('region','')), cell_fmt)
        ws_sum.write(row, 3, str(r.get('cap_tier',''))[:9], cell_fmt)
        ws_sum.write(row, 4, r.get('leg_dalton', np.nan) if pd.notna(r.get('leg_dalton')) else '', cell_num_fmt)
        ws_sum.write(row, 5, r.get('leg_td', np.nan) if pd.notna(r.get('leg_td')) else '', cell_num_fmt)
        ws_sum.write(row, 6, r.get('leg_fund', np.nan) if pd.notna(r.get('leg_fund')) else '', cell_num_fmt)
        tags = ''
        if r.get('absorp_pass'): tags += 'A'
        if r.get('prebo_pass'): tags += 'P'
        if r.get('compress_pass'): tags += 'C'
        ws_sum.write(row, 7, tags, cell_fmt)
        evb = r.get('ev_valuation')
        ws_sum.write(row, 8, float(evb) if pd.notna(evb) and abs(evb)<1e4 else '', cell_num_fmt)
        fy = r.get('fcf_yield_clean')
        ws_sum.write(row, 9, float(fy) if pd.notna(fy) else '', cell_pct_fmt)
        rg = r.get('rev_g_clean')
        ws_sum.write(row, 10, float(rg) if pd.notna(rg) else '', cell_pct_fmt)
        ws_sum.write(row, 11, float(r.get('all_legs_score',0)), cell_num_fmt)

    # Per-region sheets in order of qualifying count
    region_order = df['region'].value_counts().index.tolist()
    for region in region_order:
        sub = df[df['region']==region].head(25)
        if len(sub) == 0: continue
        sheet_name = REGION_FULLNAME.get(region, region)[:31]
        write_region_sheet(sheet_name, sub, REGION_FULLNAME.get(region, region.upper()))

    # Move Summary to first position
    wb.worksheets_objs.insert(0, wb.worksheets_objs.pop(wb.worksheets_objs.index(ws_sum)))

print(f"Workbook saved: {xlsx_path}", file=sys.stderr)
print(f"Sheets: 1 Summary + {df['region'].nunique()} regions", file=sys.stderr)
