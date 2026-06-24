#!/usr/bin/env python3
"""Build the Archetype Sections — distinct cohorts identifying different
investment shapes from the same underlying ranked universe.

Archetypes:
  1. Enduring Compounders — high stable ROIC over multiple years
  2. Compounders Turning — ROIIC inflecting (accrual + cash)
  3. Cash Machines — high cash-on-cash ROIC + cash conversion
  4. Deep Value Quality — cheap (EV/EBIT) + decent ROIC
  5. Asymmetric Inflection — Dalton inflection setups
  6. Qullamaggie Continuation — proper Q breakout setups
  7. Triple-Lens Conviction — multi-overlap of the above

Each archetype gets its own section on the workbook Summary sheet.
"""
import os, sys, datetime, glob
import pandas as pd
import numpy as np

EM_DASH = '–'

# ─── Load merged ranking + EDGAR + Q+EP ───
base = ('data/synthesis/v2_universe_ranked_full_q.csv'
        if os.path.exists('data/synthesis/v2_universe_ranked_full_q.csv')
        else 'data/synthesis/v2_universe_ranked_full.csv')
df = pd.read_csv(base)
print(f"Base ranking: {len(df)} rows", file=sys.stderr)

# Re-integrate EDGAR compounders (in case rank_compounders hasn't been re-run)
if os.path.exists('data/research/roic_edgar_combined.csv'):
    e = pd.read_csv('data/research/roic_edgar_combined.csv')
    keep = ['ticker','roic_mean_4y_med','roic_min_4y_med','roic_std_4y_med',
            'roic_method_agreement','roic_years','roiic_1y','roiic_2y','roiic_3y',
            'roiic_acceleration','roiic_inflection',
            'cc_roic_fcf_latest','cc_roic_fcf_mean_4y','cc_roic_fcf_min_4y',
            'cc_roic_ocf_mean_4y','cc_roiic_1y','cc_roiic_3y','cc_roiic_acceleration',
            'cc_roiic_inflection','fcf_margin_mean_4y','cash_conversion_mean_4y',
            'enduring_strict','enduring_loose','has_history']
    e = e[[c for c in keep if c in e.columns]]
    # Drop existing columns to overwrite
    for c in [x for x in e.columns if x != 'ticker' and x in df.columns]:
        df = df.drop(columns=[c])
    df = df.merge(e, on='ticker', how='left')
    print(f"  merged EDGAR data: {len(e)} rows", file=sys.stderr)

for col in ['enduring_strict','enduring_loose','roiic_inflection','cc_roiic_inflection','has_history']:
    if col in df.columns:
        df[col] = df[col].fillna(False).astype(bool)

if 'mktCap_M' not in df.columns and 'mktCap' in df.columns:
    df['mktCap_M'] = pd.to_numeric(df['mktCap'], errors='coerce') / 1e6
if 'fcf_yield_pct' not in df.columns and 'fcf_yield' in df.columns:
    df['fcf_yield_pct'] = pd.to_numeric(df['fcf_yield'], errors='coerce') * 100

# ─── Define archetypes ───
df['has_history'] = df.get('has_history', False).fillna(False).astype(bool)

# Archetype 1: Enduring Compounders (strict)
df['arch_enduring'] = df['enduring_strict']
# Archetype 2: Compounders Turning (ROIIC inflecting OR CC-ROIIC inflecting + at least loose quality)
df['arch_turning'] = (
    (df['enduring_loose'] | df['enduring_strict'])
    & (df['roiic_inflection'] | df['cc_roiic_inflection'])
)
# Archetype 3: Cash Machines (high CC-ROIC + high conversion)
df['arch_cash'] = (
    df['has_history']
    & (df.get('cc_roic_fcf_mean_4y', pd.Series(-1, index=df.index)).fillna(-1) >= 0.10)
    & (df.get('cash_conversion_mean_4y', pd.Series(-1, index=df.index)).fillna(-1) >= 0.7)
)
# Archetype 4: Deep Value Quality (cheap + decent ROIC)
df['arch_dv_quality'] = (
    df['has_history']
    & (df.get('ev_valuation', pd.Series(99, index=df.index)).fillna(99) > 0)
    & (df.get('ev_valuation', pd.Series(99, index=df.index)).fillna(99) <= 8)
    & (df.get('roic_mean_4y_med', pd.Series(-1, index=df.index)).fillna(-1) >= 0.10)
)
# Archetype 5: Asymmetric Inflection (Dalton)
df['arch_asym'] = df['quality_pass'].fillna(False).astype(bool) if 'quality_pass' in df.columns else False
# Archetype 6: Qullamaggie
df['arch_q'] = df.get('qmaggie_pass', pd.Series(False, index=df.index)).fillna(False).astype(bool)
# Archetype 7: Episodic Pivot
df['arch_ep'] = df.get('ep_pass', pd.Series(False, index=df.index)).fillna(False).astype(bool)
# Archetype 8: TD Mean Reversion (oversold across multiple timeframes)
df['arch_td_mr'] = (
    (df.get('net_setup', pd.Series(0, index=df.index)).fillna(0) <= -25)
    | (df.get('net_perfect', pd.Series(0, index=df.index)).fillna(0) <= -40)
    | (df.get('cd_buy_sum', pd.Series(0, index=df.index)).fillna(0) >= 13)
)
# Archetype 9: Wyckoff Absorption (money out, price holding)
df['arch_absorp'] = df.get('absorp_pass', pd.Series(False, index=df.index)).fillna(False).astype(bool)
# Archetype 10: Compression (MFI higher-low + ATR squeeze pre-trigger)
df['arch_compress'] = df.get('compress_pass', pd.Series(False, index=df.index)).fillna(False).astype(bool)
# Archetype 11: Pre-breakout Weinstein/O'Neil hybrid
df['arch_prebo'] = df.get('prebo_pass', pd.Series(False, index=df.index)).fillna(False).astype(bool)
# Archetype 12: Mirage Buy (Dalton hidden bull — selling structure + higher value)
df['arch_mirage'] = df.get('absW_dp_signal', pd.Series('', index=df.index)).fillna('').astype(str).str.upper().str.contains('MIRAGE', na=False)
# Archetype 13: B-Formation (Dalton long-liquidation completing — bottom)
if 'absW_b_form' in df.columns:
    df['arch_bform'] = df['absW_b_form'].fillna(False).astype(bool)
else:
    df['arch_bform'] = False
# Archetype 14: Failed Breakdown Reclaim (Dalton bracket reversal)
if 'absW_failed_bd_reclaim' in df.columns:
    df['arch_fbdr'] = df['absW_failed_bd_reclaim'].fillna(False).astype(bool)
else:
    df['arch_fbdr'] = False
# Archetype 15: Hidden FCF Generators (cheap on FCF + high FCF margin)
df['arch_hidden_fcf'] = (
    df['has_history']
    & (df.get('fcf_margin_mean_4y', pd.Series(-1, index=df.index)).fillna(-1) >= 0.10)
    & (df.get('ev_valuation', pd.Series(99, index=df.index)).fillna(99) > 0)
    & (df.get('ev_valuation', pd.Series(99, index=df.index)).fillna(99) <= 12)
)
# Archetype 16: Reinvestment Heroes (high ROIIC + meaningful capital growth — compounding machine)
if 'reinvest_rate' in df.columns:
    df['arch_reinvest'] = (
        df['has_history']
        & (df.get('roiic_1y', pd.Series(-99, index=df.index)).fillna(-99) >= 0.20)
        & (df.get('reinvest_rate', pd.Series(0, index=df.index)).fillna(0) >= 0.20)
    )
else:
    df['arch_reinvest'] = (
        df['has_history']
        & (df.get('roiic_1y', pd.Series(-99, index=df.index)).fillna(-99) >= 0.30)
        & (df.get('roiic_3y', pd.Series(-99, index=df.index)).fillna(-99) >= 0.15)
    )
# Archetype 17: Insider-heavy quality (insider ownership + decent ROIC)
df['arch_insider'] = (
    (df.get('insiders', pd.Series(0, index=df.index)).fillna(0) >= 0.20)
    & df['has_history']
    & (df.get('roic_mean_4y_med', pd.Series(-1, index=df.index)).fillna(-1) >= 0.08)
)
# Triple-Lens Conviction — passes 3+ archetypes (excluding the broad Dalton asym which fires too often)
all_arch_cols = ['arch_enduring','arch_turning','arch_cash','arch_dv_quality',
                 'arch_q','arch_ep','arch_td_mr','arch_absorp','arch_compress',
                 'arch_prebo','arch_mirage','arch_bform','arch_fbdr',
                 'arch_hidden_fcf','arch_reinvest','arch_insider']
df['arch_n'] = sum(df[c].astype(int) for c in all_arch_cols if c in df.columns)
df['arch_conviction'] = df['arch_n'] >= 3

REGION_FULLNAME = {
    'us':'United States','uk':'United Kingdom','japan':'Japan','germany':'Germany',
    'france':'France','italy':'Italy','spain':'Spain','netherlands':'Netherlands',
    'belgium':'Belgium','switzerland':'Switzerland','sweden':'Sweden','norway':'Norway',
    'finland':'Finland','denmark':'Denmark','ireland':'Ireland','austria':'Austria',
    'portugal':'Portugal','greece':'Greece','canada':'Canada','australia':'Australia',
    'nz':'New Zealand','hk':'Hong Kong','china':'China','korea':'South Korea',
    'taiwan':'Taiwan','singapore':'Singapore',
}

os.makedirs('data/synthesis/workbook', exist_ok=True)
xlsx_path = 'data/synthesis/workbook/archetypes_workbook.xlsx'

with pd.ExcelWriter(xlsx_path, engine='xlsxwriter') as writer:
    wb = writer.book
    ivory, crimson, charcoal, rule = '#FAF7F2','#A41E22','#2B2B2B','#8B8680'
    serif = 'Georgia'

    title_fmt    = wb.add_format({'font_name':serif,'font_size':22,'bold':True,'font_color':crimson,'bg_color':ivory,'align':'left','valign':'vcenter'})
    subtitle_fmt = wb.add_format({'font_name':serif,'font_size':11,'italic':True,'font_color':charcoal,'bg_color':ivory,'align':'left'})
    section_fmt  = wb.add_format({'font_name':serif,'font_size':12,'bold':True,'italic':True,'font_color':crimson,'bg_color':ivory,'align':'left'})
    header_fmt   = wb.add_format({'font_name':serif,'font_size':9,'bold':True,'font_color':ivory,'bg_color':crimson,'align':'center','valign':'vcenter','border':1,'border_color':charcoal})
    text_left    = wb.add_format({'font_name':serif,'font_size':10,'font_color':charcoal,'bg_color':ivory,'align':'left','border':1,'border_color':rule})
    text_left_q  = wb.add_format({'font_name':serif,'font_size':10,'bold':True,'font_color':crimson,'bg_color':ivory,'align':'left','border':1,'border_color':rule})
    text_em      = wb.add_format({'font_name':serif,'font_size':10,'font_color':charcoal,'bg_color':ivory,'align':'right','border':1,'border_color':rule})
    money_fmt    = wb.add_format({'font_name':serif,'font_size':10,'font_color':charcoal,'bg_color':ivory,'align':'right','num_format':'#,##0;(#,##0)','border':1,'border_color':rule})
    pct_fmt      = wb.add_format({'font_name':serif,'font_size':10,'font_color':charcoal,'bg_color':ivory,'align':'right','num_format':'#,##0.0;(#,##0.0)','border':1,'border_color':rule})
    ratio_fmt    = wb.add_format({'font_name':serif,'font_size':10,'font_color':charcoal,'bg_color':ivory,'align':'right','num_format':'#,##0.00;(#,##0.00)','border':1,'border_color':rule})
    body_fmt     = wb.add_format({'font_name':serif,'font_size':10,'font_color':charcoal,'bg_color':ivory,'text_wrap':True,'valign':'top'})

    def wt(ws,r,c,v,fmt=text_left):
        if v is None or (isinstance(v, float) and pd.isna(v)) or str(v).strip() in ('','nan','None'):
            ws.write_string(r, c, EM_DASH, text_em)
        else:
            ws.write_string(r, c, str(v), fmt)
    def wn(ws,r,c,v,fmt):
        if v is None or pd.isna(v):
            ws.write_string(r, c, EM_DASH, text_em); return
        try:
            fv = float(v)
            if not np.isfinite(fv) or abs(fv) > 1e15:
                ws.write_string(r, c, EM_DASH, text_em)
            else:
                ws.write_number(r, c, fv, fmt)
        except Exception:
            ws.write_string(r, c, EM_DASH, text_em)

    def topct(v):
        if pd.notna(v) and abs(float(v)) < 50: return float(v) * 100
        return None

    ws = wb.add_worksheet('Archetypes')
    ws.set_tab_color(crimson); ws.hide_gridlines(2)
    ws.set_row(0, 32)
    ws.merge_range(0, 0, 0, 18, 'Investment Archetypes — Cross-Cohort Summary', title_fmt)
    ws.merge_range(1, 0, 1, 18,
        f"{datetime.date.today().isoformat()} · {len(df):,} ranked tickers · "
        f"{int(df['arch_enduring'].sum())} enduring · {int(df['arch_turning'].sum())} turning · "
        f"{int(df['arch_cash'].sum())} cash · {int(df['arch_dv_quality'].sum())} deep-value quality · "
        f"{int(df['arch_asym'].sum())} asymmetric · {int(df['arch_q'].sum())} Q · "
        f"{int(df['arch_conviction'].sum())} triple-lens",
        subtitle_fmt)
    for c, w in [(0,9),(1,30),(2,11),(3,5),(4,7),(5,7),(6,7),(7,7),(8,7),(9,7),(10,7),(11,9),(12,7),(13,7),(14,9),(15,7),(16,7),(17,8),(18,8)]:
        ws.set_column(c, c, w)

    row = [3]
    def write_archetype(title, df_sub, sort_col):
        ws.write(row[0], 0, title + f" — {len(df_sub)} names", section_fmt)
        row[0] += 1
        headers = ['Ticker','Company','Region','Cap','Mkt Cap (M$)','ROIC Mn 4y%','ROIC Min%','Method Agr%',
                   'ROIIC 1y%','ROIIC 3y%','CC-ROIC 4y%','CC-ROIIC 1y%','CC Conv%','EV/EBIT','FCF Y%','Rev G%',
                   'Infl', 'CC-Infl', 'Score']
        for c, h in enumerate(headers): ws.write(row[0], c, h, header_fmt)
        ws.set_row(row[0], 22); row[0] += 1
        for _, r in df_sub.sort_values(sort_col, ascending=False).head(25).iterrows():
            wt(ws, row[0], 0, r.get('ticker'))
            wt(ws, row[0], 1, str(r.get('name',''))[:30] if pd.notna(r.get('name')) else None)
            wt(ws, row[0], 2, REGION_FULLNAME.get(r.get('region',''), r.get('region','')))
            wt(ws, row[0], 3, str(r.get('cap_tier',''))[:9])
            wn(ws, row[0], 4, r.get('mktCap_M'), money_fmt)
            wn(ws, row[0], 5, topct(r.get('roic_mean_4y_med')), pct_fmt)
            wn(ws, row[0], 6, topct(r.get('roic_min_4y_med')), pct_fmt)
            wn(ws, row[0], 7, topct(r.get('roic_method_agreement')), pct_fmt)
            wn(ws, row[0], 8, topct(r.get('roiic_1y')), pct_fmt)
            wn(ws, row[0], 9, topct(r.get('roiic_3y')), pct_fmt)
            wn(ws, row[0],10, topct(r.get('cc_roic_fcf_mean_4y')), pct_fmt)
            wn(ws, row[0],11, topct(r.get('cc_roiic_1y')), pct_fmt)
            wn(ws, row[0],12, topct(r.get('cash_conversion_mean_4y')), pct_fmt)
            wn(ws, row[0],13, r.get('ev_valuation') if pd.notna(r.get('ev_valuation', np.nan)) else r.get('ev_ebit'), ratio_fmt)
            wn(ws, row[0],14, r.get('fcf_yield_pct') if 'fcf_yield_pct' in r.index else (topct(r.get('fcf_yield'))), pct_fmt)
            wn(ws, row[0],15, r.get('rev_g_pct') if 'rev_g_pct' in r.index else (topct(r.get('rev_g'))), pct_fmt)
            ws.write_string(row[0],16, 'Y' if bool(r.get('roiic_inflection', False)) else EM_DASH, text_em)
            ws.write_string(row[0],17, 'Y' if bool(r.get('cc_roiic_inflection', False)) else EM_DASH, text_em)
            wn(ws, row[0],18, r.get('all_legs_score'), ratio_fmt)
            row[0] += 1
        row[0] += 2

    df['score_proxy'] = df.get('all_legs_score', 0).fillna(0)
    write_archetype('1. Enduring Compounders — strict ROIC stability, never below 15%', df[df['arch_enduring']], 'roic_mean_4y_med')
    write_archetype('2. Compounders Turning — ROIIC or CC-ROIIC inflecting + ≥ loose quality', df[df['arch_turning']], 'roiic_1y')
    write_archetype('3. Cash Machines — CC-ROIC ≥ 10% + cash conversion ≥ 70%', df[df['arch_cash']], 'cc_roic_fcf_mean_4y')
    write_archetype('4. Deep Value Quality — EV/EBIT ≤ 8 with ROIC ≥ 10%', df[df['arch_dv_quality']], 'roic_mean_4y_med')
    write_archetype('5. Asymmetric Inflection — Dalton quality (strict pass)', df[df['arch_asym']], 'score_proxy')
    write_archetype('6. Qullamaggie Continuation — proper Q breakout setup (10/20-SMA surf, ADR ≤ 6%)', df[df['arch_q']], 'score_proxy')
    write_archetype('7. Episodic Pivot — earnings/news gap ≥ 10% on ≥ 2× ADV after 3-6mo sideways', df[df['arch_ep']], 'score_proxy')
    write_archetype('8. TD Mean Reversion — oversold across multiple TFs (1h/4h/1d/1w/1M)', df[df['arch_td_mr']], 'score_proxy')
    write_archetype('9. Wyckoff Absorption — money out, price holding (stealth accumulation)', df[df['arch_absorp']], 'score_proxy')
    write_archetype('10. Compression — MFI higher-low + ATR squeeze (pre-trigger phase)', df[df['arch_compress']], 'score_proxy')
    write_archetype('11. Pre-breakout (Weinstein/O\'Neil) — late Stage-1 with handle/flag', df[df['arch_prebo']], 'score_proxy')
    write_archetype('12. Mirage Buy — Dalton hidden bull (selling structure + higher value placement)', df[df['arch_mirage']], 'score_proxy')
    write_archetype('13. B-Formation — Dalton long-liquidation completing (bottom turning)', df[df['arch_bform']], 'score_proxy')
    write_archetype('14. Failed Breakdown Reclaim — Dalton bracket reversal (false-break recapture)', df[df['arch_fbdr']], 'score_proxy')
    write_archetype('15. Hidden FCF Generators — FCF margin ≥ 10% + EV/EBITDA ≤ 12', df[df['arch_hidden_fcf']], 'fcf_margin_mean_4y')
    write_archetype('16. Reinvestment Heroes — high ROIIC + significant capital deployment', df[df['arch_reinvest']], 'roiic_1y')
    write_archetype('17. Insider-Heavy Quality — insider ownership ≥ 20% + ROIC ≥ 8%', df[df['arch_insider']], 'roic_mean_4y_med')
    write_archetype('18. Triple-Lens Conviction — passes 3+ archetypes', df[df['arch_conviction']], 'arch_n')

print(f"Wrote {xlsx_path}", file=sys.stderr)
print(f"Sizes: enduring={int(df['arch_enduring'].sum())} turning={int(df['arch_turning'].sum())} "
      f"cash={int(df['arch_cash'].sum())} dv={int(df['arch_dv_quality'].sum())} "
      f"asym={int(df['arch_asym'].sum())} q={int(df['arch_q'].sum())} conviction={int(df['arch_conviction'].sum())}",
      file=sys.stderr)
