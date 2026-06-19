"""Build a Harvard-style decision workbook: best of the best per region & measure.

Combines all the screen outputs into a single workbook with executive
summary, per-region cuts, per-measure cuts, and an intersection view
(names that screen as top across multiple measures = "best of the best").

Reads:
  results_peg/growth_adj_value.csv     (non-financial PEG-style ratios + bv tilt)
  results_peg/financials_value.csv     (financials-specific composite)
  results_peg/per_region_top_combined.csv (overall sector-percentile composite)
  results_peg/per_region_<R>_full.csv  (per-region overall composite, full lists)

Writes:
  results_peg/best_of_best.xlsx

Sheets:
  README                       methodology, caveats, how to read
  Executive Summary            top 3 per region on each major measure
  Best of Best                 names appearing in ≥2 top-25 lists (intersection)
  By Measure - Composite       top 30 globally on overall composite (per region)
  By Measure - Growth-Adj      top 30 globally on durable EV/EBITDA/g_bv
  By Measure - Sales-Growth    top 30 globally on durable EV/Sales/g_bv
  By Measure - Financials      top 30 globally on financials composite
  Region <US>                  full per-region drill-down: 3 sections (composite, growth-adj, financials)
  Region <JP>                  same per region
  ...                          one tab per region
  Glossary                     column-by-column dictionary
"""
from __future__ import annotations
from pathlib import Path
import pandas as pd
import numpy as np
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.formatting.rule import ColorScaleRule, CellIsRule
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.table import Table, TableStyleInfo

OUT = Path('results_peg')
WB_PATH = OUT / 'best_of_best.xlsx'

REGIONS = ['US','JP','KR','HK','AU','CA','GB','DE','FR','SE']

# ---------- Styling ----------
TITLE_FONT = Font(name='Calibri', size=16, bold=True, color='1F2937')
H1_FONT    = Font(name='Calibri', size=13, bold=True, color='1F2937')
H2_FONT    = Font(name='Calibri', size=11, bold=True, color='374151')
BODY_FONT  = Font(name='Calibri', size=10)
HEAD_FILL  = PatternFill('solid', fgColor='E5E7EB')
ALT_FILL   = PatternFill('solid', fgColor='F9FAFB')
EXEC_FILL  = PatternFill('solid', fgColor='DBEAFE')
WARN_FILL  = PatternFill('solid', fgColor='FEF3C7')
BORDER     = Border(left=Side(style='thin', color='D1D5DB'),
                    right=Side(style='thin', color='D1D5DB'),
                    top=Side(style='thin', color='D1D5DB'),
                    bottom=Side(style='thin', color='D1D5DB'))
ALIGN_LEFT  = Alignment(horizontal='left',  vertical='center', wrap_text=False)
ALIGN_RIGHT = Alignment(horizontal='right', vertical='center')
ALIGN_CTR   = Alignment(horizontal='center', vertical='center', wrap_text=True)


def _style_header(ws, row, col_start, col_end):
    for c in range(col_start, col_end + 1):
        cell = ws.cell(row=row, column=c)
        cell.font = Font(name='Calibri', size=10, bold=True, color='FFFFFF')
        cell.fill = PatternFill('solid', fgColor='374151')
        cell.alignment = ALIGN_CTR
        cell.border = BORDER


def _autosize(ws, headers, max_w=32):
    for i, h in enumerate(headers, 1):
        col_letter = get_column_letter(i)
        max_len = len(str(h))
        for row in ws.iter_rows(min_col=i, max_col=i, values_only=True):
            for v in row:
                if v is not None:
                    max_len = max(max_len, min(len(str(v)), max_w))
        ws.column_dimensions[col_letter].width = max(8, min(max_len + 2, max_w))


def _write_df(ws, df: pd.DataFrame, headers, start_row: int = 1, alt_shade=True):
    """Write a DataFrame as a styled table starting at start_row. Returns row after."""
    if df.empty:
        ws.cell(row=start_row, column=1, value='(no rows)').font = BODY_FONT
        return start_row + 2
    # Header
    for i, h in enumerate(headers, 1):
        ws.cell(row=start_row, column=i, value=h)
    _style_header(ws, start_row, 1, len(headers))
    # Body
    for r, (_, row) in enumerate(df.iterrows(), start=start_row + 1):
        for c, h in enumerate(headers, 1):
            v = row.get(h)
            if pd.isna(v): v = ''
            elif isinstance(v, (np.floating, float)):
                v = round(float(v), 3)
            cell = ws.cell(row=r, column=c, value=v)
            cell.font = BODY_FONT
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                cell.alignment = ALIGN_RIGHT
            else:
                cell.alignment = ALIGN_LEFT
            if alt_shade and (r - start_row) % 2 == 0:
                cell.fill = ALT_FILL
            cell.border = BORDER
    return start_row + 1 + len(df) + 1


# ---------- Data loading ----------
def load_data():
    gav = pd.read_csv(OUT / 'growth_adj_value.csv', low_memory=False)
    fin = pd.read_csv(OUT / 'financials_value.csv', low_memory=False)
    comb = pd.read_csv(OUT / 'per_region_top_combined.csv', low_memory=False)
    # Per-region overall composite full lists
    per_region = {}
    for r in REGIONS:
        p = OUT / f'per_region_{r}_full.csv'
        if p.exists():
            per_region[r] = pd.read_csv(p, low_memory=False)
    return gav, fin, comb, per_region


def _short(s, n=30):
    return str(s)[:n] if pd.notna(s) else ''


def prep_growth_adj_view(df: pd.DataFrame):
    """Clean growth-adj rows for display. Add a 'durable' flag."""
    df = df.copy()
    # Durable = earnings or revenue growth in 10-100% band
    eg = pd.to_numeric(df.get('earn_g_pct'), errors='coerce')
    rg = pd.to_numeric(df.get('rev_g_pct'), errors='coerce')
    df['durable'] = (eg.between(10, 100, inclusive='both') |
                     (eg.isna() & rg.between(10, 100, inclusive='both')))
    return df


def best_of_best(gav, fin, comb, top_n=25):
    """Names that screen as top-N across ≥ 2 of:
    - Overall sector-percentile composite (from per_region_rank)
    - Growth-adj durable EV/EBITDA/g_bv (gav, durable only)
    - Growth-adj durable EV/Sales/g_bv (gav, durable only)
    - Financials composite (fin, financials only)
    Returns a dataframe with which lists each name appeared in.
    """
    # 1. Top-25 by overall composite per region
    top_composite = comb.copy()
    top_composite = top_composite.sort_values('composite', ascending=False).groupby('region').head(top_n)
    set_comp = set(top_composite['ticker'].astype(str))

    # 2. Durable EV/EBITDA/g_bv per region
    gav_dur = prep_growth_adj_view(gav)
    gav_dur = gav_dur[gav_dur['durable']]
    top_eb = gav_dur.dropna(subset=['ev_ebitda_g_bv']).sort_values('ev_ebitda_g_bv').groupby('region').head(top_n)
    set_eb = set(top_eb['ticker'].astype(str))

    # 3. Durable EV/Sales/g_bv per region
    top_sl = gav_dur.dropna(subset=['ev_sales_g_bv']).sort_values('ev_sales_g_bv').groupby('region').head(top_n)
    set_sl = set(top_sl['ticker'].astype(str))

    # 4. Financials composite per region
    top_fin = fin.dropna(subset=['fin_composite']).sort_values('fin_composite', ascending=False).groupby('region').head(top_n)
    set_fin = set(top_fin['ticker'].astype(str))

    # Union; tag membership
    universe = set_comp | set_eb | set_sl | set_fin
    rows = []
    # Build a quick metadata lookup from the gav (full universe).
    meta = {str(r['ticker']): r for _, r in gav.iterrows()}
    fin_meta = {str(r['ticker']): r for _, r in fin.iterrows()}
    for tk in universe:
        flags = (
            ('Composite'        if tk in set_comp else None),
            ('Growth-Adj-EBITDA' if tk in set_eb else None),
            ('Growth-Adj-Sales' if tk in set_sl else None),
            ('Financials'        if tk in set_fin else None),
        )
        flags = [f for f in flags if f]
        if len(flags) < 2: continue
        m = meta.get(tk, fin_meta.get(tk, {}))
        rows.append({
            'ticker': tk,
            'region': m.get('region', ''),
            'longName': _short(m.get('longName',''), 40),
            'sector': m.get('sector',''),
            'marketCap_M': pd.to_numeric(m.get('marketCap',0)/1e6 if m.get('marketCap') else None, errors='coerce'),
            'screens_in': ', '.join(flags),
            'n_screens': len(flags),
            'priceToBook': m.get('priceToBook'),
            'trailingPE': m.get('trailingPE'),
            'ev_ebitda_g_bv':  m.get('ev_ebitda_g_bv'),
            'ev_sales_g_bv':   m.get('ev_sales_g_bv'),
            'fin_composite':   fin_meta.get(tk, {}).get('fin_composite') if tk in fin_meta else None,
            'composite':       (comb[comb.ticker == tk]['composite'].iloc[0]
                                if not comb[comb.ticker == tk].empty else None),
        })
    out = pd.DataFrame(rows).sort_values(['n_screens','region'],
                                          ascending=[False, True])
    return out


# ---------- Sheet builders ----------
def build_readme(wb):
    ws = wb.create_sheet('README', 0)
    title = 'Best-of-Best Universe Screen — How to Read'
    ws.cell(row=1, column=1, value=title).font = TITLE_FONT
    ws.row_dimensions[1].height = 24
    notes = [
        ('Purpose', ('A single decision-grade workbook for surfacing the strongest names per region and per measure.'
                     ' Each measure has known failure modes; this workbook deliberately shows multiple views so the'
                     ' top-of-list is cross-validated.')),
        ('Universe', ('7,196 cached tickers from financedatabase across 10 regions (US, JP, KR, HK, AU, CA, GB, DE, FR, SE).'
                      ' Mcap floor $25M for the broad views, $100M for financials. Junk filtered: warrants, preferreds, SPAC units, defunct symbols.')),
        ('Measures', ('Three independent scoring frameworks: '
                      '(1) Sector-percentile COMPOSITE on 13 valuation/quality/growth components within region. '
                      '(2) GROWTH-ADJUSTED VALUE: (EV/EBITDA)/earn-g and (EV/Sales)/rev-g, with low-P/B tilt (bounded ±20%). '
                      '(3) FINANCIALS-specific composite: P/B, P/Tangible-Book, P/E, ROE, ROA, div yield, earnings growth — '
                      'because PEG-style ratios are meaningless for banks/insurers/holdcos.')),
        ('Durable Growth Cut', ('The growth-adjusted ratios surface low-base merger/rebound spikes if not filtered.'
                                ' The "durable" cut keeps only names with growth in the 10-100% band so e.g. Castellum (+65,383% earnings growth'
                                ' from prior loss) and Mirvac (+31,987%) don\'t dominate.')),
        ('BV Tilt', ('Low-P/B reward applied as: tilt = 1 - 0.2·(1-P/B)/(1+P/B). Saturates at ±20% so it\'s a tilt, not the driver.'
                     ' P/B=0.5 → 0.933 (cheaper rating); P/B=2.0 → 1.067 (mild penalty).')),
        ('Financials Carve-Out', ('Banks and insurers and holdcos are EXCLUDED from PEG-style ratios — deposits/reserves dwarf market cap,'
                                  ' net interest income isn\'t "sales", and earnings move on reserve releases not operations. They have their own tab.')),
        ('Best of Best', ('The "Best of Best" sheet shows names that screen in the top-25 on ≥ 2 of the four lists.'
                          ' Three or four flags = cross-validated cheap-and-quality. Use as your starting watchlist.')),
        ('How to Read Numbers', ('Lower-is-better for all ratio columns (PEG, P/B, P/E, EV/EBITDA).'
                                  ' Higher-is-better for percentile composites (sector_pct, fin_composite, durable_composite — these are 0-100).'
                                  ' All currency figures are in millions of local-currency units (so JP names are in million yen, KR in million won, etc).')),
        ('Caveats', ('Earnings growth >300% is almost always merger/reserve/low-base — flag the row.'
                     ' Operating margin << 0 for high-revenue-growth names = cash-burning early-stage; don\'t size on net cash alone.'
                     ' yfinance forwardPE is often empty for non-US — that\'s data unavailability, not a defect.'
                     ' P/B negative = negative book value (impaired or buyback-driven); the screener excludes these from the percentile but they show in raw data.')),
        ('Files', ('Cache snapshot lives on origin/cache-snapshot (~18MB tarball, auto-restored on session start).'
                   ' Results CSVs commit to the analysis branch alongside source.'
                   ' This workbook regenerates from those CSVs via build_workbook.py.')),
    ]
    row = 3
    for h, body in notes:
        if h:
            ws.cell(row=row, column=1, value=h).font = H1_FONT
            row += 1
            cell = ws.cell(row=row, column=1, value=body)
            cell.font = BODY_FONT
            cell.alignment = Alignment(wrap_text=True, vertical='top')
            ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=8)
            ws.row_dimensions[row].height = 50
        row += 2
    ws.column_dimensions['A'].width = 22
    for c in 'BCDEFGH':
        ws.column_dimensions[c].width = 18


def build_exec_summary(wb, comb, gav, fin):
    ws = wb.create_sheet('Executive Summary')
    ws.cell(row=1, column=1, value='Best of Each Measure — Per Region').font = TITLE_FONT
    row = 3
    gav_dur = prep_growth_adj_view(gav)
    gav_dur = gav_dur[gav_dur['durable']]
    for region in REGIONS:
        ws.cell(row=row, column=1, value=region).font = H1_FONT
        row += 1
        # 3 picks per measure
        # 1. Overall composite
        sub = comb[comb.region == region].sort_values('composite', ascending=False).head(3)
        sub_disp = sub[['ticker','longName','sector','composite','priceToBook','trailingPE','marketCap_M']].copy()
        sub_disp.insert(0, 'measure', 'Overall Composite')
        # 2. Growth-adj EBITDA (durable)
        sub2 = gav_dur[gav_dur.region == region].dropna(subset=['ev_ebitda_g_bv']).sort_values('ev_ebitda_g_bv').head(3)
        sub2_disp = sub2[['ticker','longName','sector']].copy()
        sub2_disp['composite'] = sub2['ev_ebitda_g_bv'].astype(float)
        sub2_disp['priceToBook'] = sub2['priceToBook']
        sub2_disp['trailingPE'] = None
        sub2_disp['marketCap_M'] = sub2['marketCap_M']
        sub2_disp.insert(0, 'measure', 'Growth-Adj EBITDA (durable)')
        # 3. Financials composite
        sub3 = fin[fin.region == region].dropna(subset=['fin_composite']).sort_values('fin_composite', ascending=False).head(3)
        sub3_disp = sub3[['ticker','longName']].copy()
        sub3_disp['sector'] = 'Financial Services'
        sub3_disp['composite'] = sub3['fin_composite']
        sub3_disp['priceToBook'] = sub3['priceToBook']
        sub3_disp['trailingPE'] = sub3['trailingPE']
        sub3_disp['marketCap_M'] = sub3['marketCap_M']
        sub3_disp.insert(0, 'measure', 'Financials Composite')
        block = pd.concat([sub_disp, sub2_disp, sub3_disp], ignore_index=True)
        for c in ('longName','sector'):
            if c in block.columns:
                block[c] = block[c].astype(str).str[:30]
        headers = ['measure','ticker','longName','sector','composite','priceToBook','trailingPE','marketCap_M']
        row = _write_df(ws, block, headers, start_row=row)
        row += 1
    _autosize(ws, ['measure','ticker','longName','sector','composite','priceToBook','trailingPE','marketCap_M'])


def build_best_of_best(wb, gav, fin, comb, top_n=25):
    ws = wb.create_sheet('Best of Best')
    title = ('Names That Screen Top-{n} On ≥ 2 Of: Composite, Growth-Adj EBITDA (durable), '
             'Growth-Adj Sales (durable), Financials').format(n=top_n)
    ws.cell(row=1, column=1, value=title).font = TITLE_FONT
    ws.merge_cells('A1:K1')
    bob = best_of_best(gav, fin, comb, top_n=top_n)
    headers = ['ticker','region','longName','sector','marketCap_M','n_screens','screens_in',
               'composite','ev_ebitda_g_bv','ev_sales_g_bv','fin_composite','priceToBook','trailingPE']
    row = _write_df(ws, bob, headers, start_row=3)
    _autosize(ws, headers)
    ws.freeze_panes = 'D4'


def _global_top_by(df: pd.DataFrame, sort_col: str, ascending: bool, n: int,
                   extra_cols=None) -> pd.DataFrame:
    sub = df.dropna(subset=[sort_col]).sort_values(sort_col, ascending=ascending).head(n)
    cols = ['ticker','region','longName','sector','marketCap_M', sort_col,
            'priceToBook','trailingPE','ev_ebitda','ev_sales','rev_g_pct','earn_g_pct']
    if extra_cols:
        for c in extra_cols:
            if c not in cols and c in sub.columns:
                cols.append(c)
    cols = [c for c in cols if c in sub.columns]
    out = sub[cols].copy()
    if 'longName' in out.columns:
        out['longName'] = out['longName'].astype(str).str[:32]
    return out


def build_global_measures(wb, gav, fin, comb):
    gav_dur = prep_growth_adj_view(gav)
    gav_dur = gav_dur[gav_dur['durable']]

    ws = wb.create_sheet('By Measure - Composite')
    ws.cell(row=1, column=1, value='Top 30 Globally on Overall Composite (sector-percentile, per region)').font = TITLE_FONT
    top = comb.sort_values('composite', ascending=False).head(30)
    headers = [c for c in ['ticker','region','longName','sector','marketCap_M','composite',
                           'priceToBook','trailingPE','forwardPE','enterpriseToEbitda',
                           'net_cash_pct','fcfYield_pct','grossMargins','operatingMargins',
                           'revenueGrowth','earningsGrowth'] if c in top.columns]
    if 'longName' in top.columns:
        top['longName'] = top['longName'].astype(str).str[:32]
    _write_df(ws, top, headers, start_row=3)
    _autosize(ws, headers)
    ws.freeze_panes = 'D4'

    ws = wb.create_sheet('By Measure - Growth-Adj')
    ws.cell(row=1, column=1, value='Top 30 Globally on Durable EV/EBITDA/g (BV-tilted)').font = TITLE_FONT
    top = _global_top_by(gav_dur, 'ev_ebitda_g_bv', True, 30, extra_cols=['_bv_tilt'])
    headers = list(top.columns)
    _write_df(ws, top, headers, start_row=3)
    _autosize(ws, headers)
    ws.freeze_panes = 'D4'

    ws = wb.create_sheet('By Measure - Sales-Growth')
    ws.cell(row=1, column=1, value='Top 30 Globally on Durable EV/Sales/g (BV-tilted)').font = TITLE_FONT
    top = _global_top_by(gav_dur, 'ev_sales_g_bv', True, 30, extra_cols=['_bv_tilt'])
    headers = list(top.columns)
    _write_df(ws, top, headers, start_row=3)
    _autosize(ws, headers)
    ws.freeze_panes = 'D4'

    ws = wb.create_sheet('By Measure - Financials')
    ws.cell(row=1, column=1, value='Top 30 Globally on Financials Composite (P/B + P/TBV + P/E + ROE + ROA + Div + Earn-g)').font = TITLE_FONT
    top = fin.sort_values('fin_composite', ascending=False).head(30)
    headers = [c for c in ['ticker','region','longName','industry','marketCap_M','fin_composite',
                           'priceToBook','priceToTangibleBook','trailingPE','forwardPE',
                           'returnOnEquity','returnOnAssets','dividendYield','earningsGrowth'] if c in top.columns]
    if 'longName' in top.columns:
        top['longName'] = top['longName'].astype(str).str[:32]
    _write_df(ws, top, headers, start_row=3)
    _autosize(ws, headers)
    ws.freeze_panes = 'D4'


def build_per_region_tabs(wb, gav, fin, comb, per_region):
    gav_dur = prep_growth_adj_view(gav)
    gav_dur = gav_dur[gav_dur['durable']]
    for region in REGIONS:
        ws = wb.create_sheet(f'Region {region}')
        ws.cell(row=1, column=1, value=f'{region} — Top picks across all measures').font = TITLE_FONT
        row = 3

        # Section 1: Overall sector-percentile composite (top 25)
        ws.cell(row=row, column=1, value='1. Overall sector-percentile composite (top 25 in region)').font = H1_FONT
        row += 1
        sub = comb[comb.region == region].sort_values('composite', ascending=False).head(25)
        headers = [c for c in ['ticker','longName','sector','marketCap_M','composite',
                                'priceToBook','trailingPE','forwardPE','enterpriseToEbitda',
                                'net_cash_pct','fcfYield_pct','grossMargins','operatingMargins',
                                'revenueGrowth','earningsGrowth'] if c in sub.columns]
        if 'longName' in sub.columns:
            sub['longName'] = sub['longName'].astype(str).str[:32]
        row = _write_df(ws, sub, headers, start_row=row)
        row += 1

        # Section 2: Growth-adj durable EV/EBITDA/g_bv (top 25)
        ws.cell(row=row, column=1, value='2. Durable-growth cheapest on EV/EBITDA/g (BV-tilted) — top 25').font = H1_FONT
        row += 1
        sub2 = gav_dur[gav_dur.region == region].dropna(subset=['ev_ebitda_g_bv']).sort_values('ev_ebitda_g_bv').head(25)
        h2 = ['ticker','longName','sector','marketCap_M','ev_ebitda_g_bv','ev_ebitda',
              'priceToBook','rev_g_pct','earn_g_pct','earn_g_q_pct']
        h2 = [c for c in h2 if c in sub2.columns]
        if 'longName' in sub2.columns:
            sub2['longName'] = sub2['longName'].astype(str).str[:32]
        row = _write_df(ws, sub2, h2, start_row=row)
        row += 1

        # Section 3: Growth-adj durable EV/Sales/g_bv (top 25)
        ws.cell(row=row, column=1, value='3. Durable-growth cheapest on EV/Sales/g (BV-tilted) — top 25').font = H1_FONT
        row += 1
        sub3 = gav_dur[gav_dur.region == region].dropna(subset=['ev_sales_g_bv']).sort_values('ev_sales_g_bv').head(25)
        h3 = ['ticker','longName','sector','marketCap_M','ev_sales_g_bv','ev_sales',
              'priceToBook','rev_g_pct','earn_g_pct','earn_g_q_pct']
        h3 = [c for c in h3 if c in sub3.columns]
        if 'longName' in sub3.columns:
            sub3['longName'] = sub3['longName'].astype(str).str[:32]
        row = _write_df(ws, sub3, h3, start_row=row)
        row += 1

        # Section 4: Financials top 25
        ws.cell(row=row, column=1, value='4. Financials top 25 (P/B + P/E + ROE + Div composite)').font = H1_FONT
        row += 1
        sub4 = fin[fin.region == region].dropna(subset=['fin_composite']).sort_values('fin_composite', ascending=False).head(25)
        h4 = [c for c in ['ticker','longName','industry','marketCap_M','fin_composite',
                          'priceToBook','priceToTangibleBook','trailingPE','forwardPE',
                          'returnOnEquity','returnOnAssets','dividendYield','earningsGrowth'] if c in sub4.columns]
        if 'longName' in sub4.columns:
            sub4['longName'] = sub4['longName'].astype(str).str[:32]
        row = _write_df(ws, sub4, h4, start_row=row)
        ws.freeze_panes = 'A4'


def build_glossary(wb):
    ws = wb.create_sheet('Glossary')
    ws.cell(row=1, column=1, value='Column Dictionary').font = TITLE_FONT
    rows = [
        ('Column', 'Meaning'),
        ('ticker', 'Symbol as listed on the primary exchange (with suffix for non-US)'),
        ('region', 'US, JP, KR, HK, AU, CA, GB, DE, FR, SE'),
        ('longName', 'Company name'),
        ('sector', 'GICS-style sector (Technology, Financial Services, Basic Materials, …)'),
        ('industry', 'Sub-sector (Banks - Regional, Insurance - Life, Asset Management, …)'),
        ('marketCap_M', 'Market cap in MILLIONS of local currency (JP=¥M, KR=₩M, etc)'),
        ('composite', 'Overall sector-percentile composite 0-100, higher = better. 13 sub-components, sector-relative within region.'),
        ('fin_composite', 'Financials-specific composite 0-100, higher = better. 8 sub-components incl. P/B, P/TBV, P/E, ROE, ROA, div yield.'),
        ('priceToBook', 'P/B ratio (lower = cheaper). Negative = impaired equity.'),
        ('priceToTangibleBook', 'P/TBV — derived from balance_sheet where cached; falls back to P/B otherwise.'),
        ('trailingPE', 'Trailing 12-month P/E. NaN for loss-makers.'),
        ('forwardPE', 'Consensus forward P/E. Often NaN for non-US (yfinance lacks analyst data).'),
        ('enterpriseToEbitda', 'EV/EBITDA. Suppressed in PEG ratios for financials.'),
        ('enterpriseToRevenue / ev_sales', 'EV/Sales. Rebuilt from P/S × (EV/MktCap) for currency safety.'),
        ('ev_ebitda_g', '(EV/EBITDA) / earnings-growth%. NaN for non-growers, negative growth, or financials.'),
        ('ev_ebitda_g_ltm', 'Same with earningsQuarterlyGrowth — more current; ~35% row coverage.'),
        ('ev_sales_g', '(EV/Sales) / revenue-growth%. NaN for non-growers/financials.'),
        ('ev_*_g_bv', '×bv_tilt(P/B). tilt = 1 - 0.2·(1-P/B)/(1+P/B). Saturates ±20%. Rewards low P/B mildly.'),
        ('durable', '(in the workbook filter) True if growth in 10-100% band — excludes merger/low-base spikes.'),
        ('rev_g_pct', 'Annual revenue growth %, from yfinance revenueGrowth × 100.'),
        ('earn_g_pct', 'Annual earnings growth %, from earningsGrowth × 100.'),
        ('earn_g_q_pct', 'Earnings growth latest-quarter YoY %, from earningsQuarterlyGrowth × 100.'),
        ('net_cash_pct', '(totalCash - totalDebt) / marketCap × 100. >100 = net-cash > market cap.'),
        ('fcfYield_pct', 'Free cash flow / marketCap × 100.'),
        ('grossMargins / operatingMargins / profitMargins', 'Decimal margins (0.30 = 30%).'),
        ('returnOnEquity / returnOnAssets', 'Decimal returns. 0.20 = 20%.'),
        ('dividendYield', 'Decimal forward yield (0.04 = 4%). Often missing on non-US.'),
        ('n_screens', '(Best of Best) How many top-25 lists this name appears in (max 4).'),
        ('screens_in', '(Best of Best) Which lists: Composite, Growth-Adj-EBITDA, Growth-Adj-Sales, Financials.'),
    ]
    for r, (k, v) in enumerate(rows, 1):
        c1 = ws.cell(row=r+2, column=1, value=k); c1.font = H2_FONT if r == 1 else BODY_FONT
        c2 = ws.cell(row=r+2, column=2, value=v); c2.font = H2_FONT if r == 1 else BODY_FONT
        c2.alignment = Alignment(wrap_text=True, vertical='top')
        if r == 1:
            c1.fill = HEAD_FILL; c2.fill = HEAD_FILL
        ws.row_dimensions[r+2].height = 20 if r != 1 else 18
    ws.column_dimensions['A'].width = 28
    ws.column_dimensions['B'].width = 110


def main():
    gav, fin, comb, per_region = load_data()
    print(f'Loaded: growth-adj={len(gav)}  financials={len(fin)}  combined={len(comb)}')

    wb = Workbook()
    # Remove default sheet
    if 'Sheet' in wb.sheetnames:
        del wb['Sheet']

    build_readme(wb)
    build_exec_summary(wb, comb, gav, fin)
    build_best_of_best(wb, gav, fin, comb, top_n=25)
    build_global_measures(wb, gav, fin, comb)
    build_per_region_tabs(wb, gav, fin, comb, per_region)
    build_glossary(wb)

    wb.save(WB_PATH)
    print(f'Wrote {WB_PATH} with {len(wb.sheetnames)} sheets:')
    for s in wb.sheetnames:
        print(f'  - {s}')


if __name__ == '__main__':
    main()
