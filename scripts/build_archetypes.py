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
# Prefer the fixed v2 EDGAR extract (financials via ROE, date-alignment fix)
_edgar_src = ('data/research/edgar_all_v2.csv'
              if os.path.exists('data/research/edgar_all_v2.csv')
              else 'data/research/roic_edgar_combined.csv')
if os.path.exists(_edgar_src):
    e = pd.read_csv(_edgar_src)
    keep = ['ticker','roic_mean_4y_med','roic_min_4y_med','roic_std_4y_med',
            'roic_method_agreement','roic_years','roiic_1y','roiic_2y','roiic_3y',
            'roiic_acceleration','roiic_inflection',
            'cc_roic_fcf_latest','cc_roic_fcf_mean_4y','cc_roic_fcf_min_4y',
            'cc_roic_ocf_mean_4y','cc_roiic_1y','cc_roiic_3y','cc_roiic_acceleration',
            'cc_roiic_inflection','fcf_margin_mean_4y','cash_conversion_mean_4y',
            'enduring_strict','enduring_loose','has_history',
            'is_financial','roe_mean_4y','roe_min_4y','roe_std_4y','roa_mean_4y','enduring_roe']
    e = e[[c for c in keep if c in e.columns]]
    # Drop existing columns to overwrite
    for c in [x for x in e.columns if x != 'ticker' and x in df.columns]:
        df = df.drop(columns=[c])
    # OUTER merge — preserve EDGAR-only tickers (compounders not in Dalton)
    df = df.merge(e, on='ticker', how='outer')
    # Tag rows from EDGAR-only as US (default region) so they show up in US sheet
    df.loc[df['region'].isna(), 'region'] = 'us'
    df.loc[df['cap_tier'].isna(), 'cap_tier'] = 'unknown'
    print(f"  merged EDGAR data (outer): {len(e)} rows → universe now {len(df)}", file=sys.stderr)

for col in ['enduring_strict','enduring_loose','roiic_inflection','cc_roiic_inflection','has_history']:
    if col in df.columns:
        df[col] = df[col].fillna(False).astype(bool)

if 'mktCap_M' not in df.columns and 'mktCap' in df.columns:
    df['mktCap_M'] = pd.to_numeric(df['mktCap'], errors='coerce') / 1e6
if 'fcf_yield_pct' not in df.columns and 'fcf_yield' in df.columns:
    df['fcf_yield_pct'] = pd.to_numeric(df['fcf_yield'], errors='coerce') * 100

# ─── Data hygiene: FLAG dubious values, never cap/discard them ───
# FCF yield > 50% is usually a currency/ADR mismatch but can be real — keep raw, flag it
if 'fcf_yield' in df.columns:
    fy = pd.to_numeric(df['fcf_yield'], errors='coerce')
    df['fcf_yield_pct'] = fy * 100
    df['fcf_yield_dubious'] = (fy.abs() > 0.5).fillna(False)
# Rev growth > 100% YoY — often base-effect/one-off but keep raw, flag it
if 'rev_g' in df.columns:
    rg = pd.to_numeric(df['rev_g'], errors='coerce')
    df['rev_g_pct'] = rg * 100
    df['rev_g_dubious'] = (rg.abs() > 1.0).fillna(False)

# ROIIC inflection — keep the real flag; ADDITIONALLY tag whether it's driven by the
# 2.0 cap (d_IC <= 0, i.e. earning more on shrinking capital — a real but distinct signal)
if 'roiic_1y' in df.columns:
    r1 = pd.to_numeric(df['roiic_1y'], errors='coerce')
    r3 = pd.to_numeric(df['roiic_3y'], errors='coerce')
    df['roiic_capdriven'] = (r1 >= 2.0).fillna(False)  # capital-shrink case, flag don't drop
if 'cc_roiic_1y' in df.columns:
    cr1 = pd.to_numeric(df['cc_roiic_1y'], errors='coerce')
    df['cc_roiic_capdriven'] = (cr1 >= 2.0).fillna(False)

# Method disagreement — flag (agreement < 0 means the 5 ROIC methods diverge), don't exclude
if 'roic_method_agreement' in df.columns:
    ma = pd.to_numeric(df['roic_method_agreement'], errors='coerce')
    df['roic_method_disagree'] = (ma < 0).fillna(False)

# ─── Define archetypes ───
df['has_history'] = df.get('has_history', False).fillna(False).astype(bool)

# Archetype 0: Enduring ROE Financials — banks/REITs/BDCs/insurers (ROIC ill-defined,
# so use ROE: min ≥ 12%, stable). Recovered by the EDGAR financial-sector fix.
if 'enduring_roe' in df.columns:
    df['arch_enduring_roe'] = (
        df['enduring_roe'].fillna(False).astype(bool)
        & df.get('is_financial', pd.Series(False, index=df.index)).fillna(False).astype(bool)
    )
else:
    df['arch_enduring_roe'] = False
# Archetype 1: Enduring Compounders (strict) — keep all, dubious ones are flagged in columns
df['arch_enduring'] = df['enduring_strict']
# Archetype 2: Compounders Turning — real inflection (accrual or cash)
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
# Monthly compression — slower-TF base squeeze (higher conviction than weekly)
df['arch_compress_m'] = df.get('compress_m_pass', pd.Series(False, index=df.index)).fillna(False).astype(bool)
# Dual-TF compression: both weekly AND monthly firing = strongest squeeze signal
df['arch_compress_dual'] = df['arch_compress'] & df['arch_compress_m']
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
# Archetype 18: Backlog Inflection — RPO / deferred revenue growth accelerating
backlog_path = 'data/research/backlog_us.csv'
if os.path.exists(backlog_path):
    try:
        b = pd.read_csv(backlog_path)
        bc = ['ticker','backlog_concept_used','backlog_latest','backlog_qoq_pct',
              'backlog_yoy_pct','backlog_growth_4q_mean','backlog_growth_8q_mean',
              'backlog_inflection_pp','backlog_inflection_flag','backlog_to_rev_ratio',
              'backlog_quarters_history']
        b = b[[c for c in bc if c in b.columns]]
        for c in [x for x in b.columns if x != 'ticker' and x in df.columns]:
            df = df.drop(columns=[c])
        df = df.merge(b, on='ticker', how='left')
        print(f"  merged backlog: {len(b)} rows", file=sys.stderr)
    except Exception as e:
        print(f"  backlog merge err: {e}", file=sys.stderr)

# ─── Segment-level archetypes (edgartools dimensional XBRL) ───
seg_path = 'data/research/segments_us.csv'
if os.path.exists(seg_path):
    try:
        sg = pd.read_csv(seg_path)
        segcols = ['ticker','n_segments','largest_segment','largest_segment_pct',
                   'seg_rev_growth_fastest','seg_fastest_name','seg_rev_growth_slowest',
                   'seg_slowest_name','seg_growth_dispersion','seg_mix_shift_pp',
                   'seg_mix_gainer','seg_inflection_flag','seg_margin_best',
                   'seg_margin_best_name','seg_high_margin_growing']
        sg = sg[[c for c in segcols if c in sg.columns]]
        for c in [x for x in sg.columns if x != 'ticker' and x in df.columns]:
            df = df.drop(columns=[c])
        df = df.merge(sg, on='ticker', how='left')
        print(f"  merged segments: {len(sg)} rows", file=sys.stderr)
    except Exception as e:
        print(f"  segment merge err: {e}", file=sys.stderr)
df['arch_seg_inflection'] = df.get('seg_inflection_flag', pd.Series(False, index=df.index)).fillna(False).astype(bool)
df['arch_seg_highmargin'] = df.get('seg_high_margin_growing', pd.Series(False, index=df.index)).fillna(False).astype(bool)

if 'backlog_inflection_flag' in df.columns:
    # AUDIT FIX: backlog is a leading indicator — stale filings are useless.
    # Require the latest backlog observation within ~15 months.
    backlog_fresh = pd.Series(True, index=df.index)
    if 'backlog_latest_date' in df.columns:
        bdate = pd.to_datetime(df['backlog_latest_date'], errors='coerce')
        cutoff = pd.Timestamp(datetime.date.today()) - pd.Timedelta(days=460)
        backlog_fresh = (bdate >= cutoff).fillna(False)
        df['backlog_stale'] = (bdate < cutoff).fillna(False)
    df['arch_backlog'] = df['backlog_inflection_flag'].fillna(False).astype(bool) & backlog_fresh
else:
    df['arch_backlog'] = False

# ─── Additional Dalton-derived archetypes we discussed but hadn't surfaced ───
# Helper
def _bool(col, fill=False):
    if col in df.columns:
        return df[col].fillna(fill).astype(bool)
    return pd.Series(False, index=df.index)
def _num(col, fill=0):
    if col in df.columns:
        return pd.to_numeric(df[col], errors='coerce').fillna(fill)
    return pd.Series(fill, index=df.index)
def _str(col, fill=''):
    if col in df.columns:
        return df[col].fillna(fill).astype(str)
    return pd.Series(fill, index=df.index)

# Archetype 19: Value Area Rule trigger (Dalton bracket-rule continuation: open outside, accept inside)
df['arch_var'] = _bool('absW_var_trigger')

# Archetype 20: Accepted Outside (value area rule SUCCEEDED — full migration)
df['arch_accepted_out'] = _bool('absW_accepted_outside')

# Archetype 21: Bullish High Volume (dp_signal — institutional sponsorship up)
df['arch_bull_highvol'] = _str('absW_dp_signal').str.upper().eq('BULLISH_HIGH_VOL')

# Archetype 22: Confirmed Up (dp_signal — directional performance matrix confirms bull)
df['arch_confirmed_up'] = _str('absW_dp_signal').str.upper().eq('CONFIRMED_UP')

# Archetype 23: Sponsorship Leaders (C-pillar — RS at 13w/26w highs, institutional)
df['arch_sponsor'] = _num('absW_C_sponsor') >= 15

# Archetype 24: Readiness High (D-pillar — pre-trigger setup quality)
df['arch_ready'] = _num('absW_D_ready') >= 15

# Archetype 25: No-Tail Streak (close-on-extreme persistence — strong continuation)
df['arch_notail'] = _num('absW_no_tail_streak') >= 3

# Archetype 26: Long-Term Excess Buy + Bull (Dalton structural buyers + bull weekly state)
df['arch_excess_bull'] = (
    _bool('absW_excess_buy')
    & _str('absW_state').isin(['INFLECTION_UP','ACCELERATION_UP','TRENDING_UP'])
)

# Archetype 27: Sub Book Value (Ben Graham deep value — original semis prompt)
if 'pb' in df.columns:
    df['arch_sub_book'] = (
        (pd.to_numeric(df['pb'], errors='coerce') > 0)
        & (pd.to_numeric(df['pb'], errors='coerce') < 1.0)
    )
else:
    df['arch_sub_book'] = False

# Archetype 28: Failed Up (short candidate — failed buying attempt)
df['arch_failed_up'] = _str('absW_dp_signal').str.upper().eq('FAILED_UP')

# Archetype 29: P-Formation (short cover fade — bearish reversal candidate)
df['arch_pform'] = _bool('absW_p_form')
# Triple-Lens Conviction — passes 3+ archetypes (excluding the broad Dalton asym which fires too often)
all_arch_cols = ['arch_enduring','arch_turning','arch_cash','arch_dv_quality',
                 'arch_q','arch_ep','arch_td_mr','arch_absorp','arch_compress','arch_compress_m',
                 'arch_prebo','arch_mirage','arch_bform','arch_fbdr',
                 'arch_hidden_fcf','arch_reinvest','arch_insider','arch_backlog',
                 'arch_var','arch_accepted_out','arch_bull_highvol','arch_confirmed_up',
                 'arch_sponsor','arch_ready','arch_notail','arch_excess_bull','arch_sub_book']
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
        _sub = df_sub
        if sort_col in _sub.columns and len(_sub):
            _sub = _sub.sort_values(sort_col, ascending=False)
        for _, r in _sub.head(25).iterrows():
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
    write_archetype('0. Enduring ROE Financials — banks/REITs/BDCs: min ROE ≥ 12%, stable (ROIC ill-defined)', df[df['arch_enduring_roe']], 'roe_mean_4y')
    write_archetype('1. Enduring Compounders — strict ROIC stability, never below 15%', df[df['arch_enduring']], 'roic_mean_4y_med')
    write_archetype('2. Compounders Turning — ROIIC or CC-ROIIC inflecting + ≥ loose quality', df[df['arch_turning']], 'roiic_1y')
    write_archetype('3. Cash Machines — CC-ROIC ≥ 10% + cash conversion ≥ 70%', df[df['arch_cash']], 'cc_roic_fcf_mean_4y')
    write_archetype('4. Deep Value Quality — EV/EBIT ≤ 8 with ROIC ≥ 10%', df[df['arch_dv_quality']], 'roic_mean_4y_med')
    write_archetype('5. Asymmetric Inflection — Dalton quality (strict pass)', df[df['arch_asym']], 'score_proxy')
    write_archetype('6. Qullamaggie Continuation — proper Q breakout setup (10/20-SMA surf, ADR ≤ 6%)', df[df['arch_q']], 'score_proxy')
    write_archetype('7. Episodic Pivot — earnings/news gap ≥ 10% on ≥ 2× ADV after 3-6mo sideways', df[df['arch_ep']], 'score_proxy')
    write_archetype('8. TD Mean Reversion — oversold across multiple TFs (1h/4h/1d/1w/1M)', df[df['arch_td_mr']], 'score_proxy')
    write_archetype('9. Wyckoff Absorption — money out, price holding (stealth accumulation)', df[df['arch_absorp']], 'score_proxy')
    write_archetype('10. Compression (weekly) — MFI higher-low + ATR squeeze (pre-trigger phase)', df[df['arch_compress']], 'score_proxy')
    write_archetype('10b. Compression (monthly) — slower-TF base squeeze + MFI higher-low', df[df['arch_compress_m']], 'score_proxy')
    write_archetype('10c. Compression DUAL (weekly + monthly both firing) — strongest squeeze', df[df['arch_compress_dual']], 'score_proxy')
    write_archetype('11. Pre-breakout (Weinstein/O\'Neil) — late Stage-1 with handle/flag', df[df['arch_prebo']], 'score_proxy')
    write_archetype('12. Mirage Buy — Dalton hidden bull (selling structure + higher value placement)', df[df['arch_mirage']], 'score_proxy')
    write_archetype('13. B-Formation — Dalton long-liquidation completing (bottom turning)', df[df['arch_bform']], 'score_proxy')
    write_archetype('14. Failed Breakdown Reclaim — Dalton bracket reversal (false-break recapture)', df[df['arch_fbdr']], 'score_proxy')
    write_archetype('15. Hidden FCF Generators — FCF margin ≥ 10% + EV/EBITDA ≤ 12', df[df['arch_hidden_fcf']], 'fcf_margin_mean_4y')
    write_archetype('16. Reinvestment Heroes — high ROIIC + significant capital deployment', df[df['arch_reinvest']], 'roiic_1y')
    write_archetype('17. Insider-Heavy Quality — insider ownership ≥ 20% + ROIC ≥ 8%', df[df['arch_insider']], 'roic_mean_4y_med')
    write_archetype('18. Backlog Inflection — RPO / deferred-rev growth accelerating (leading-indicator)', df[df['arch_backlog']], 'backlog_inflection_pp')
    write_archetype('18b. Segment Inflection — fast segment gaining mix share while legacy shrinks', df[df['arch_seg_inflection']], 'seg_mix_shift_pp')
    write_archetype('18c. Segment Margin Mix-Up — highest-margin segment is also growing', df[df['arch_seg_highmargin']], 'seg_margin_best')
    write_archetype('19. Value Area Rule Trigger — Dalton bracket-rule continuation (open outside, accept inside)', df[df['arch_var']], 'score_proxy')
    write_archetype('20. Accepted Outside — VAR succeeded (full value-area migration)', df[df['arch_accepted_out']], 'score_proxy')
    write_archetype('21. Bullish High Volume — Dalton DP signal: institutional sponsorship up', df[df['arch_bull_highvol']], 'score_proxy')
    write_archetype('22. Confirmed Up — Dalton DP signal: directional performance matrix confirms', df[df['arch_confirmed_up']], 'score_proxy')
    write_archetype('23. Sponsorship Leaders — Dalton C-pillar ≥ 15 (RS at 13w/26w highs)', df[df['arch_sponsor']], 'score_proxy')
    write_archetype('24. Readiness High — Dalton D-pillar ≥ 15 (pre-trigger setup quality)', df[df['arch_ready']], 'score_proxy')
    write_archetype('25. No-Tail Streak — close-on-extreme persistence (continuation momentum)', df[df['arch_notail']], 'score_proxy')
    write_archetype('26. Long-Term Excess Buy + Bull — Dalton structural buyers + bull weekly state', df[df['arch_excess_bull']], 'score_proxy')
    write_archetype('27. Sub Book Value (Graham deep value) — P/B < 1', df[df['arch_sub_book']], 'score_proxy')
    write_archetype('28. Failed Up — Dalton DP signal: failed buying attempt (short candidate)', df[df['arch_failed_up']], 'score_proxy')
    write_archetype('29. P-Formation — short-cover fade (bearish reversal candidate)', df[df['arch_pform']], 'score_proxy')
    write_archetype('30. Triple-Lens Conviction — passes 3+ BUY-side archetypes', df[df['arch_conviction']], 'arch_n')

print(f"Wrote {xlsx_path}", file=sys.stderr)
print(f"Sizes: enduring={int(df['arch_enduring'].sum())} turning={int(df['arch_turning'].sum())} "
      f"cash={int(df['arch_cash'].sum())} dv={int(df['arch_dv_quality'].sum())} "
      f"asym={int(df['arch_asym'].sum())} q={int(df['arch_q'].sum())} conviction={int(df['arch_conviction'].sum())}",
      file=sys.stderr)
