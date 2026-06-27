#!/usr/bin/env python3
"""Harvard-aesthetic archetypes workbook — same style rules as build_workbook_harvard.py.

Each archetype section now includes WHICH segment / backlog concept / ROIC method drove the flag.
"""
import os, sys, datetime
import pandas as pd
import numpy as np

EM_DASH = '–'
os.makedirs('data/synthesis/workbook', exist_ok=True)

REGION_FULLNAME = {
    'us':'United States','us_x':'United States (Expanded)','uk':'United Kingdom',
    'japan':'Japan','germany':'Germany','france':'France','italy':'Italy','spain':'Spain',
    'netherlands':'Netherlands','belgium':'Belgium','switzerland':'Switzerland','sweden':'Sweden',
    'norway':'Norway','finland':'Finland','denmark':'Denmark','ireland':'Ireland',
    'austria':'Austria','portugal':'Portugal','greece':'Greece','canada':'Canada',
    'australia':'Australia','hk':'Hong Kong','china':'China','korea':'South Korea',
    'taiwan':'Taiwan','singapore':'Singapore','thailand':'Thailand','indonesia':'Indonesia',
    'israel':'Israel','turkey':'Turkey','brazil':'Brazil','mexico':'Mexico',
    'argentina':'Argentina','chile':'Chile','southafrica':'South Africa',
}

src = ('data/synthesis/v2_universe_ranked_full_q.csv'
       if os.path.exists('data/synthesis/v2_universe_ranked_full_q.csv')
       else 'data/synthesis/v2_universe_ranked_full.csv')
df = pd.read_csv(src)
print(f"Loaded {len(df)} rows from {src}", file=sys.stderr)

for col in ['quality_pass','qmaggie_pass','ep_pass','enduring_strict','enduring_loose',
            'roiic_inflection','cc_roiic_inflection','has_history','is_financial','enduring_roe',
            'absorp_pass','prebo_pass','compress_pass','compress_m_pass',
            'seg_inflection_flag','seg_high_margin_growing','backlog_inflection_flag',
            'absW_failed_bd_reclaim','absW_b_form','absW_var_trigger','absW_accepted_outside',
            'absW_excess_buy','absW_p_form']:
    if col not in df.columns: df[col] = False
    df[col] = df[col].fillna(False).astype(bool)

# Derived flags (mirror build_archetypes.py)
df['arch_enduring_roe'] = df['enduring_roe'] & df['is_financial']
df['arch_enduring']     = df['enduring_strict']
df['arch_turning']      = (df['enduring_loose'] | df['enduring_strict']) & (df['roiic_inflection'] | df['cc_roiic_inflection'])
df['arch_cash']         = df['has_history'] & (df.get('cc_roic_fcf_mean_4y', pd.Series(-1, index=df.index)).fillna(-1) >= 0.10) & (df.get('cash_conversion_mean_4y', pd.Series(-1, index=df.index)).fillna(-1) >= 0.7)
df['arch_dv_quality']   = df['has_history'] & (df.get('ev_valuation', pd.Series(99, index=df.index)).fillna(99) > 0) & (df.get('ev_valuation', pd.Series(99, index=df.index)).fillna(99) <= 8) & (df.get('roic_mean', pd.Series(-1, index=df.index)).fillna(-1) >= 0.10)
df['arch_asym']         = df['quality_pass']
df['arch_q']            = df['qmaggie_pass']
df['arch_ep']           = df['ep_pass']
df['arch_td_mr']        = (pd.to_numeric(df.get('net_setup', 0), errors='coerce').fillna(0) <= -25) | (pd.to_numeric(df.get('net_perfect', 0), errors='coerce').fillna(0) <= -40)
df['arch_absorp']       = df['absorp_pass']
df['arch_compress_w']   = df['compress_pass']
df['arch_compress_m']   = df['compress_m_pass']
df['arch_compress_dual']= df['compress_pass'] & df['compress_m_pass']
df['arch_prebo']        = df['prebo_pass']
df['arch_bform']        = df['absW_b_form']
df['arch_fbdr']         = df['absW_failed_bd_reclaim']
df['arch_seg_inflect']  = df['seg_inflection_flag']
df['arch_seg_highmgn']  = df['seg_high_margin_growing']
df['arch_backlog']      = df['backlog_inflection_flag']
df['arch_var']          = df['absW_var_trigger']
df['arch_accepted_out'] = df['absW_accepted_outside']
df['arch_excess_bull']  = df['absW_excess_buy']
df['arch_pform']        = df['absW_p_form']
df['arch_sub_book']     = (pd.to_numeric(df.get('pb', np.nan), errors='coerce') > 0) & (pd.to_numeric(df.get('pb', np.nan), errors='coerce') < 1.0)
df['arch_hidden_fcf']   = df['has_history'] & (df.get('fcf_margin_mean_4y', pd.Series(-1, index=df.index)).fillna(-1) >= 0.10) & (df.get('ev_valuation', pd.Series(99, index=df.index)).fillna(99).between(0.01, 12))
df['arch_reinvest']     = df['has_history'] & (df.get('roiic_1y', pd.Series(-99, index=df.index)).fillna(-99) >= 0.30) & (df.get('roiic_3y', pd.Series(-99, index=df.index)).fillna(-99) >= 0.15)

ALL_ARCH = ['arch_enduring','arch_turning','arch_cash','arch_dv_quality','arch_q','arch_ep','arch_td_mr',
            'arch_absorp','arch_compress_w','arch_compress_m','arch_prebo','arch_bform','arch_fbdr',
            'arch_hidden_fcf','arch_reinvest','arch_backlog','arch_seg_inflect','arch_var',
            'arch_accepted_out','arch_excess_bull','arch_sub_book']
df['arch_n'] = sum(df[c].astype(int) for c in ALL_ARCH if c in df.columns)
df['arch_conviction'] = df['arch_n'] >= 3

if 'mktCap_M' not in df.columns and 'mktCap' in df.columns:
    df['mktCap_M'] = pd.to_numeric(df['mktCap'], errors='coerce') / 1e6
if 'fcf_yield_pct' not in df.columns and 'fcf_yield' in df.columns:
    df['fcf_yield_pct'] = pd.to_numeric(df['fcf_yield'], errors='coerce') * 100
if 'rev_g_pct' not in df.columns and 'rev_g' in df.columns:
    df['rev_g_pct'] = pd.to_numeric(df['rev_g'], errors='coerce') * 100


def build_styles(wb):
    F = 'Times New Roman'; S = 10
    BLACK = '#000000'; WHITE = '#FFFFFF'; GRAY_HAIR = '#BFBFBF'
    base = {'font_name': F, 'font_size': S, 'font_color': BLACK, 'bg_color': WHITE, 'font_condense': True}
    s = {}
    s['title']    = wb.add_format({**base, 'bold': True, 'align': 'left', 'valign': 'vcenter', 'bottom': 2, 'border_color': BLACK})
    s['subtitle'] = wb.add_format({**base, 'italic': True, 'align': 'left'})
    s['section']  = wb.add_format({**base, 'bold': True, 'italic': True, 'align': 'left', 'top': 1, 'bottom': 1, 'border_color': BLACK, 'valign': 'vcenter'})
    s['header']   = wb.add_format({**base, 'bold': True, 'align': 'center', 'valign': 'vcenter', 'top': 1, 'bottom': 1, 'border_color': BLACK})
    s['notes']    = wb.add_format({**base, 'italic': True, 'text_wrap': True, 'valign': 'top'})
    body = {**base, 'bottom': 1, 'border_color': GRAY_HAIR, 'valign': 'vcenter'}
    s['text_l']   = wb.add_format({**body, 'align': 'left'})
    s['text_l_b'] = wb.add_format({**body, 'align': 'left', 'bold': True})
    s['text_c']   = wb.add_format({**body, 'align': 'center'})
    s['text_c_b'] = wb.add_format({**body, 'align': 'center', 'bold': True})
    s['em']       = wb.add_format({**body, 'align': 'right'})
    s['money']    = wb.add_format({**body, 'align': 'right', 'num_format': '#,##0;(#,##0);"–"'})
    s['pct']      = wb.add_format({**body, 'align': 'right', 'num_format': '#,##0.0;(#,##0.0);"–"'})
    s['ratio']    = wb.add_format({**body, 'align': 'right', 'num_format': '#,##0.00;(#,##0.00);"–"'})
    return s

def wt(ws, r, c, v, fmt, em_fmt):
    if v is None or (isinstance(v, float) and pd.isna(v)) or str(v).strip() in ('','nan','None'):
        ws.write_string(r, c, EM_DASH, em_fmt)
    else:
        ws.write_string(r, c, str(v), fmt)

def wn(ws, r, c, v, fmt, em_fmt):
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


xlsx_path = 'data/synthesis/workbook/archetypes_workbook_harvard.xlsx'
with pd.ExcelWriter(xlsx_path, engine='xlsxwriter') as writer:
    wb = writer.book
    S = build_styles(wb)
    ws = wb.add_worksheet('Archetypes')
    ws.hide_gridlines(2)
    ws.set_default_row(15)

    # Column widths sized for wide rows — segment names take 28 chars, backlog concepts 28
    widths = [8, 28, 11, 8, 9, 9, 9, 9, 9, 9, 9, 9, 28, 9, 28, 9, 9, 28, 9, 7, 8, 8]
    for c, w in enumerate(widths): ws.set_column(c, c, w)

    ws.set_row(0, 28)
    ws.merge_range(0, 0, 0, 21, 'INVESTMENT ARCHETYPES  ·  CROSS-COHORT SUMMARY', S['title'])
    ws.set_row(1, 16)
    ws.merge_range(1, 0, 1, 21,
        f"{datetime.date.today().isoformat()}  ·  {len(df):,} ranked  ·  "
        f"{int(df['arch_enduring'].sum())} enduring  ·  {int(df['arch_turning'].sum())} turning  ·  "
        f"{int(df['arch_cash'].sum())} cash  ·  {int(df['arch_seg_inflect'].sum())} segment-inflect  ·  "
        f"{int(df['arch_backlog'].sum())} backlog-inflect  ·  {int(df['arch_conviction'].sum())} triple-lens",
        S['subtitle'])

    row = [3]

    def section(title):
        ws.set_row(row[0], 22)
        ws.merge_range(row[0], 0, row[0], 21, title.upper(), S['section'])
        row[0] += 1

    # ─── Standard archetype block — includes segment + backlog specifics ───
    def write_block(title, dfsub, sort_col=None, ascending=False, n=25):
        section(f"{title}  ·  {len(dfsub)} names")
        headers = ['Ticker','Company','Region','Cap','Mkt Cap (M)','ROIC Mn %','ROIC Min %',
                   'ROIIC 1y %','CC-ROIC %','EV/EBIT','FCF Y %','Rev G %','Largest Seg','Largest %',
                   'Fastest Seg','Fastest %','Mix Δ pp','Backlog Concept','Backlog Δ pp','Inflect','CC Inflect','Score']
        ws.set_row(row[0], 22)
        for c, h in enumerate(headers): ws.write(row[0], c, h, S['header'])
        row[0] += 1
        if sort_col and sort_col in dfsub.columns:
            dfsub = dfsub.sort_values(sort_col, ascending=ascending)
        for _, r in dfsub.head(n).iterrows():
            wt(ws, row[0], 0, r.get('ticker'), S['text_l_b'], S['em'])
            wt(ws, row[0], 1, str(r.get('name',''))[:26] if pd.notna(r.get('name')) else None, S['text_l'], S['em'])
            wt(ws, row[0], 2, REGION_FULLNAME.get(r.get('region',''), r.get('region','')), S['text_l'], S['em'])
            wt(ws, row[0], 3, r.get('cap_tier'), S['text_l'], S['em'])
            wn(ws, row[0], 4, r.get('mktCap_M'), S['money'], S['em'])
            wn(ws, row[0], 5, topct(r.get('roic_mean')), S['pct'], S['em'])
            wn(ws, row[0], 6, topct(r.get('roic_min')), S['pct'], S['em'])
            wn(ws, row[0], 7, topct(r.get('roiic_1y')), S['pct'], S['em'])
            wn(ws, row[0], 8, topct(r.get('cc_roic_fcf_mean_4y')), S['pct'], S['em'])
            wn(ws, row[0], 9, r.get('ev_valuation') if pd.notna(r.get('ev_valuation', np.nan)) else r.get('ev_ebit'), S['ratio'], S['em'])
            wn(ws, row[0],10, r.get('fcf_yield_pct'), S['pct'], S['em'])
            wn(ws, row[0],11, r.get('rev_g_pct'), S['pct'], S['em'])
            wt(ws, row[0],12, str(r.get('largest_segment',''))[:18] if pd.notna(r.get('largest_segment')) else None, S['text_l'], S['em'])
            wn(ws, row[0],13, r.get('largest_segment_pct'), S['pct'], S['em'])
            wt(ws, row[0],14, str(r.get('seg_fastest_name',''))[:18] if pd.notna(r.get('seg_fastest_name')) else None, S['text_l'], S['em'])
            wn(ws, row[0],15, r.get('seg_rev_growth_fastest'), S['pct'], S['em'])
            wn(ws, row[0],16, r.get('seg_mix_shift_pp'), S['pct'], S['em'])
            wt(ws, row[0],17, str(r.get('backlog_concept_used',''))[:16] if pd.notna(r.get('backlog_concept_used')) else None, S['text_l'], S['em'])
            wn(ws, row[0],18, r.get('backlog_inflection_pp'), S['pct'], S['em'])
            v1 = bool(r.get('roiic_inflection', False))
            ws.write_string(row[0],19, '•' if v1 else EM_DASH, S['text_c_b'] if v1 else S['em'])
            v2 = bool(r.get('cc_roiic_inflection', False))
            ws.write_string(row[0],20, '•' if v2 else EM_DASH, S['text_c_b'] if v2 else S['em'])
            wn(ws, row[0],21, r.get('all_legs_score'), S['ratio'], S['em'])
            row[0] += 1
        row[0] += 1

    # Specialized segment block (different columns — emphasis on segment specifics)
    def write_segment_block(title, dfsub):
        section(f"{title}  ·  {len(dfsub)} names")
        headers = ['Ticker','Company','Region','Cap','Mkt Cap (M)','Largest Segment','Largest %',
                   'Fastest Segment','Fastest %','Slowest Segment','Slowest %','Mix Gainer','Mix Δ pp',
                   'Best-Margin Seg','Best Mgn %','Worst Mgn %','Dispersion','# Seg','Hi-Mgn ↑','Latest FY','EV/EBIT','Score']
        ws.set_row(row[0], 22)
        for c, h in enumerate(headers): ws.write(row[0], c, h, S['header'])
        row[0] += 1
        # Sort by FASTEST-segment growth (the actual "new segment compounding" signal)
        # so cases like EVC (Smadex inside Digital Advertising) surface even with small mix-shift.
        if 'seg_rev_growth_fastest' in dfsub.columns:
            dfsub = dfsub.sort_values('seg_rev_growth_fastest', ascending=False)
        # Show ALL — was capped at 40 which hid most names
        for _, r in dfsub.iterrows():
            wt(ws, row[0], 0, r.get('ticker'), S['text_l_b'], S['em'])
            wt(ws, row[0], 1, str(r.get('name',''))[:24] if pd.notna(r.get('name')) else None, S['text_l'], S['em'])
            wt(ws, row[0], 2, REGION_FULLNAME.get(r.get('region',''), r.get('region','')), S['text_l'], S['em'])
            wt(ws, row[0], 3, r.get('cap_tier'), S['text_l'], S['em'])
            wn(ws, row[0], 4, r.get('mktCap_M'), S['money'], S['em'])
            wt(ws, row[0], 5, str(r.get('largest_segment',''))[:28] if pd.notna(r.get('largest_segment')) else None, S['text_l'], S['em'])
            wn(ws, row[0], 6, r.get('largest_segment_pct'), S['pct'], S['em'])
            wt(ws, row[0], 7, str(r.get('seg_fastest_name',''))[:28] if pd.notna(r.get('seg_fastest_name')) else None, S['text_l'], S['em'])
            wn(ws, row[0], 8, r.get('seg_rev_growth_fastest'), S['pct'], S['em'])
            wt(ws, row[0], 9, str(r.get('seg_slowest_name',''))[:28] if pd.notna(r.get('seg_slowest_name')) else None, S['text_l'], S['em'])
            wn(ws, row[0],10, r.get('seg_rev_growth_slowest'), S['pct'], S['em'])
            wt(ws, row[0],11, str(r.get('seg_mix_gainer',''))[:28] if pd.notna(r.get('seg_mix_gainer')) else None, S['text_l'], S['em'])
            wn(ws, row[0],12, r.get('seg_mix_shift_pp'), S['pct'], S['em'])
            wt(ws, row[0],13, str(r.get('seg_margin_best_name',''))[:28] if pd.notna(r.get('seg_margin_best_name')) else None, S['text_l'], S['em'])
            wn(ws, row[0],14, r.get('seg_margin_best'), S['pct'], S['em'])
            wn(ws, row[0],15, r.get('seg_margin_worst'), S['pct'], S['em'])
            wn(ws, row[0],16, r.get('seg_growth_dispersion'), S['pct'], S['em'])
            wn(ws, row[0],17, r.get('n_segments'), S['money'], S['em'])
            v = bool(r.get('seg_high_margin_growing', False))
            ws.write_string(row[0],18, '•' if v else EM_DASH, S['text_c_b'] if v else S['em'])
            wn(ws, row[0],19, r.get('latest_fy'), S['money'], S['em'])
            wn(ws, row[0],20, r.get('ev_valuation') if pd.notna(r.get('ev_valuation', np.nan)) else r.get('ev_ebit'), S['ratio'], S['em'])
            wn(ws, row[0],21, r.get('all_legs_score'), S['ratio'], S['em'])
            row[0] += 1
        row[0] += 1

    # Specialized backlog block
    def write_backlog_block(title, dfsub):
        section(f"{title}  ·  {len(dfsub)} names")
        headers = ['Ticker','Company','Region','Cap','Mkt Cap (M)','Backlog Concept','Latest Backlog (M)',
                   'Latest Date','QoQ %','YoY %','4Q Avg %','8Q Avg %','Accel Δ pp','Backlog / Rev',
                   'EV (M)','Backlog / EV','ROIC Mn %','ROIIC 1y %','EV/EBITDA','FCF Y %','Rev G %','Score']
        ws.set_row(row[0], 22)
        for c, h in enumerate(headers): ws.write(row[0], c, h, S['header'])
        row[0] += 1
        if 'backlog_inflection_pp' in dfsub.columns:
            dfsub = dfsub.sort_values('backlog_inflection_pp', ascending=False)
        for _, r in dfsub.head(40).iterrows():
            wt(ws, row[0], 0, r.get('ticker'), S['text_l_b'], S['em'])
            wt(ws, row[0], 1, str(r.get('name',''))[:24] if pd.notna(r.get('name')) else None, S['text_l'], S['em'])
            wt(ws, row[0], 2, REGION_FULLNAME.get(r.get('region',''), r.get('region','')), S['text_l'], S['em'])
            wt(ws, row[0], 3, r.get('cap_tier'), S['text_l'], S['em'])
            wn(ws, row[0], 4, r.get('mktCap_M'), S['money'], S['em'])
            wt(ws, row[0], 5, str(r.get('backlog_concept_used',''))[:28] if pd.notna(r.get('backlog_concept_used')) else None, S['text_l'], S['em'])
            bl = r.get('backlog_latest')
            wn(ws, row[0], 6, (float(bl)/1e6) if pd.notna(bl) else None, S['money'], S['em'])
            wt(ws, row[0], 7, str(r.get('backlog_latest_date',''))[:10] if pd.notna(r.get('backlog_latest_date')) else None, S['text_l'], S['em'])
            wn(ws, row[0], 8, r.get('backlog_qoq_pct'), S['pct'], S['em'])
            wn(ws, row[0], 9, r.get('backlog_yoy_pct'), S['pct'], S['em'])
            wn(ws, row[0],10, r.get('backlog_growth_4q_mean'), S['pct'], S['em'])
            wn(ws, row[0],11, r.get('backlog_growth_8q_mean'), S['pct'], S['em'])
            wn(ws, row[0],12, r.get('backlog_inflection_pp'), S['pct'], S['em'])
            wn(ws, row[0],13, r.get('backlog_to_rev_ratio'), S['ratio'], S['em'])
            ev_t = r.get('ev_total')
            wn(ws, row[0],14, (float(ev_t)/1e6) if pd.notna(ev_t) else None, S['money'], S['em'])
            wn(ws, row[0],15, r.get('backlog_to_ev_ratio'), S['ratio'], S['em'])
            wn(ws, row[0],16, topct(r.get('roic_mean')), S['pct'], S['em'])
            wn(ws, row[0],17, topct(r.get('roiic_1y')), S['pct'], S['em'])
            wn(ws, row[0],18, r.get('ev_valuation') if pd.notna(r.get('ev_valuation', np.nan)) else r.get('ev_ebit'), S['ratio'], S['em'])
            wn(ws, row[0],19, r.get('fcf_yield_pct'), S['pct'], S['em'])
            wn(ws, row[0],20, r.get('rev_g_pct'), S['pct'], S['em'])
            wn(ws, row[0],21, r.get('all_legs_score'), S['ratio'], S['em'])
            row[0] += 1
        row[0] += 1

    # Methodology note up top
    ws.set_row(row[0], 16)
    ws.merge_range(row[0], 0, row[0]+3, 21,
        "Each archetype is a structurally distinct setup. A name may appear in multiple cohorts — the "
        "Triple-Lens Conviction block at the end shows names with ≥ 3 archetype overlaps. Segment and "
        "backlog data come from full SEC EDGAR XBRL dimensional parsing (edgartools); fundamentals from "
        "Lindy multi-method ROIC reconciliation. Every cohort row shows the specific segment name, "
        "backlog concept, and inflection magnitude that drove the flag.",
        S['notes'])
    row[0] += 5

    write_block('0. Enduring ROE Financials — banks / REITs / BDCs: min ROE ≥ 12 %, stable (ROIC ill-defined)',
                df[df['arch_enduring_roe']], 'roe_mean_4y')
    write_block('1. Enduring Compounders — strict ROIC stability, never below 15 %',
                df[df['arch_enduring']], 'roic_mean')
    write_block('2. Compounders Turning — ROIIC or CC-ROIIC inflecting + ≥ loose quality',
                df[df['arch_turning']], 'roiic_1y')
    write_block('3. Cash Machines — CC-ROIC ≥ 10 % + cash conversion ≥ 70 %',
                df[df['arch_cash']], 'cc_roic_fcf_mean_4y')
    write_block('4. Deep Value Quality — EV/EBIT ≤ 8 with ROIC ≥ 10 %',
                df[df['arch_dv_quality']], 'roic_mean')
    write_block('5. Asymmetric Inflection — Dalton strict quality pass',
                df[df['arch_asym']], 'all_legs_score')
    write_block('6. Qullamaggie Continuation — proper Q breakout (10/20-SMA surf, ADR ≤ 6 %, 30-100% leg in 1-3 mo)',
                df[df['arch_q']], 'all_legs_score')
    write_block('7. Episodic Pivot — earnings/news gap ≥ 10 % on ≥ 2× ADV after 3-6 mo sideways',
                df[df['arch_ep']], 'all_legs_score')
    write_block('8. TD Mean Reversion — oversold across multiple timeframes',
                df[df['arch_td_mr']], 'all_legs_score')
    write_block('9. Wyckoff Absorption — money out, price holding (stealth accumulation)',
                df[df['arch_absorp']], 'all_legs_score')
    write_block('10. Compression (weekly) — MFI higher-low + ATR squeeze pre-trigger',
                df[df['arch_compress_w']], 'all_legs_score')
    write_block('11. Compression (monthly) — slower-TF base squeeze + MFI higher-low',
                df[df['arch_compress_m']], 'all_legs_score')
    write_block('12. Compression DUAL (W + M both firing) — strongest squeeze signal',
                df[df['arch_compress_dual']], 'all_legs_score')
    write_block('13. Pre-breakout (Weinstein / O\'Neil hybrid) — late Stage-1 with handle/flag',
                df[df['arch_prebo']], 'all_legs_score')
    write_block('14. B-Formation — Dalton long-liquidation completing (bottom turning)',
                df[df['arch_bform']], 'all_legs_score')
    write_block('15. Failed Breakdown Reclaim — Dalton bracket reversal (false break recaptured)',
                df[df['arch_fbdr']], 'all_legs_score')
    write_block('16. Hidden FCF Generators — FCF margin ≥ 10 % + EV/EBITDA ≤ 12',
                df[df['arch_hidden_fcf']], 'fcf_margin_mean_4y')
    write_block('17. Reinvestment Heroes — high ROIIC + significant capital deployment',
                df[df['arch_reinvest']], 'roiic_1y')

    # Segment-specific blocks with full segment specifics
    write_segment_block('18. Segment Inflection — new segment gaining mix share while legacy shrinks',
                        df[df['arch_seg_inflect']])
    write_segment_block('19. Segment Margin Mix-Up — highest-margin segment also growing',
                        df[df['arch_seg_highmgn']])

    # Backlog-specific block with full backlog specifics
    write_backlog_block('20. Backlog Inflection — RPO / deferred-rev growth accelerating (leading-indicator)',
                        df[df['arch_backlog']])

    write_block('21. Value Area Rule Trigger — Dalton bracket-rule continuation (open outside, accept inside)',
                df[df['arch_var']], 'all_legs_score')
    write_block('22. Accepted Outside — VAR succeeded (full value-area migration)',
                df[df['arch_accepted_out']], 'all_legs_score')
    write_block('23. Long-Term Excess Buy — Dalton structural buyers + bull weekly state',
                df[df['arch_excess_bull']], 'all_legs_score')
    write_block('24. Sub Book Value — Graham deep value (P/B < 1)',
                df[df['arch_sub_book']], 'all_legs_score')
    write_block('25. P-Formation — short-cover fade (bearish reversal candidate)',
                df[df['arch_pform']], 'all_legs_score')
    write_block('26. Triple-Lens Conviction — passes ≥ 3 buy-side archetypes',
                df[df['arch_conviction']], 'arch_n')

print(f"Wrote {xlsx_path}", file=sys.stderr)
sizes = {k.replace('arch_',''): int(df[k].sum()) for k in ALL_ARCH if k in df.columns}
print(f"Sizes: {sizes}", file=sys.stderr)
