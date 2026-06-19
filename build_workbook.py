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

# ---------- Harvard Business Review style palette ----------
# Crimson is the HBS primary; warm off-whites and slate-grey neutrals frame it.
CRIMSON_DARK = '7A1320'     # HBS crimson (darker, for headers)
CRIMSON      = 'A51C30'     # HBS crimson
CRIMSON_PALE = 'F4E3E6'     # pale tint for very-light fills
SLATE_DARK   = '1C1F26'     # title / strong text
SLATE        = '2F3640'     # body strong
SLATE_MUTED  = '5F6B7A'     # caption / footnotes
RULE         = 'C6CDD6'     # hairline rule grey
RULE_LIGHT   = 'E5E7EB'     # lighter rule
WARM_WHITE   = 'FBF9F4'     # case-study warm background
ROW_ALT      = 'F4F1EA'     # alternating row warm-grey
CARD_BG      = 'F8F6F0'     # subtle card-fill (for blockquotes)
HIGHLIGHT    = 'F8E7E2'     # pale crimson highlight for accent rows

# Serif for titles (the HBR convention), Calibri for body
TITLE_FONT_NAME = 'Cambria'   # widely available serif
H_FONT_NAME     = 'Cambria'
BODY_FONT_NAME  = 'Calibri'

TITLE_FONT    = Font(name=TITLE_FONT_NAME, size=22, bold=False, color=SLATE_DARK)
KICKER_FONT   = Font(name=BODY_FONT_NAME, size=9, bold=True, color=CRIMSON)  # small uppercase label
DECK_FONT     = Font(name=TITLE_FONT_NAME, size=13, italic=True, color=SLATE_MUTED)
SECTION_FONT  = Font(name=H_FONT_NAME, size=12, bold=True, color=SLATE_DARK)
SUBSECT_FONT  = Font(name=BODY_FONT_NAME, size=9, bold=True, color=CRIMSON)
BODY_FONT     = Font(name=BODY_FONT_NAME, size=10, color=SLATE)
BODY_BOLD     = Font(name=BODY_FONT_NAME, size=10, bold=True, color=SLATE_DARK)
CAPTION_FONT  = Font(name=BODY_FONT_NAME, size=9, italic=True, color=SLATE_MUTED)
TABLE_HEAD_FT = Font(name=BODY_FONT_NAME, size=10, bold=True, color='FFFFFF')
FOOTNOTE_FONT = Font(name=BODY_FONT_NAME, size=8, italic=True, color=SLATE_MUTED)

WARM_FILL  = PatternFill('solid', fgColor=WARM_WHITE)
ALT_FILL   = PatternFill('solid', fgColor=ROW_ALT)
CARD_FILL  = PatternFill('solid', fgColor=CARD_BG)
HIGHLIGHT_FILL = PatternFill('solid', fgColor=HIGHLIGHT)
HEAD_FILL  = PatternFill('solid', fgColor=CRIMSON)
HEAD_DARK_FILL = PatternFill('solid', fgColor=CRIMSON_DARK)

# Hairline borders (lighter, more elegant than standard thin)
HAIRLINE   = Side(style='thin', color=RULE)
RULE_THIN  = Side(style='thin', color=RULE_LIGHT)
BORDER_ALL = Border(left=HAIRLINE, right=HAIRLINE, top=HAIRLINE, bottom=HAIRLINE)
BORDER_TOP_RULE = Border(top=Side(style='thin', color=CRIMSON))
BORDER_BOT_RULE = Border(bottom=Side(style='thin', color=CRIMSON))

ALIGN_LEFT  = Alignment(horizontal='left',   vertical='center', indent=1)
ALIGN_RIGHT = Alignment(horizontal='right',  vertical='center', indent=1)
ALIGN_CTR   = Alignment(horizontal='center', vertical='center', wrap_text=True)
ALIGN_WRAP  = Alignment(horizontal='left',   vertical='top',    wrap_text=True, indent=1)


def _style_header(ws, row, col_start, col_end):
    """Crimson banded header with white serif-cap-style text."""
    for c in range(col_start, col_end + 1):
        cell = ws.cell(row=row, column=c)
        cell.font = TABLE_HEAD_FT
        cell.fill = HEAD_FILL
        cell.alignment = ALIGN_CTR
        cell.border = Border(left=Side(style='thin', color=CRIMSON_DARK),
                              right=Side(style='thin', color=CRIMSON_DARK),
                              top=Side(style='thin', color=CRIMSON_DARK),
                              bottom=Side(style='thin', color=CRIMSON_DARK))


def _autosize(ws, headers, max_w=34):
    for i, h in enumerate(headers, 1):
        col_letter = get_column_letter(i)
        max_len = len(str(h))
        for row in ws.iter_rows(min_col=i, max_col=i, values_only=True):
            for v in row:
                if v is not None:
                    max_len = max(max_len, min(len(str(v)), max_w))
        ws.column_dimensions[col_letter].width = max(9, min(max_len + 2, max_w))


def _write_df(ws, df: pd.DataFrame, headers, start_row: int = 1, alt_shade=True):
    """Write a DataFrame as a styled table. Returns row after."""
    if df.empty:
        c = ws.cell(row=start_row, column=1, value='— no rows —')
        c.font = CAPTION_FONT
        c.alignment = ALIGN_LEFT
        return start_row + 2
    for i, h in enumerate(headers, 1):
        ws.cell(row=start_row, column=i, value=h)
    _style_header(ws, start_row, 1, len(headers))
    for r, (_, row) in enumerate(df.iterrows(), start=start_row + 1):
        is_alt = (r - start_row) % 2 == 0
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
            if alt_shade and is_alt:
                cell.fill = ALT_FILL
            else:
                cell.fill = WARM_FILL
            cell.border = Border(bottom=RULE_THIN)
    return start_row + 1 + len(df) + 1


def _set_page_background(ws, last_col_letter='Z', last_row=600):
    """Tint the whole sheet warm-white (HBS magazine look)."""
    # Set the default row fill via the sheet-level approach: apply WARM_FILL
    # to a strip of cells. Cheaper: just rely on explicit row backgrounds.
    pass


def _draw_title_block(ws, kicker: str, title: str, deck: str = None,
                      start_row: int = 1):
    """Magazine-style title block: KICKER label, title in serif, deck (italic
    subtitle), then a crimson hairline rule under it."""
    # Kicker (small uppercase)
    if kicker:
        c = ws.cell(row=start_row, column=1, value=kicker.upper())
        c.font = KICKER_FONT
        c.alignment = ALIGN_LEFT
        ws.row_dimensions[start_row].height = 14
    # Title
    title_row = start_row + 1
    c = ws.cell(row=title_row, column=1, value=title)
    c.font = TITLE_FONT
    c.alignment = Alignment(horizontal='left', vertical='center', indent=0)
    ws.row_dimensions[title_row].height = 30
    # Deck
    deck_row = title_row + 1
    if deck:
        c = ws.cell(row=deck_row, column=1, value=deck)
        c.font = DECK_FONT
        c.alignment = Alignment(horizontal='left', vertical='center', wrap_text=True)
        ws.merge_cells(start_row=deck_row, start_column=1, end_row=deck_row, end_column=10)
        ws.row_dimensions[deck_row].height = 22
        last_row = deck_row
    else:
        last_row = title_row
    # Crimson hairline rule below the title block
    rule_row = last_row + 1
    for col in range(1, 13):
        ws.cell(row=rule_row, column=col).border = BORDER_TOP_RULE
    ws.row_dimensions[rule_row].height = 6
    return rule_row + 1


def _draw_section(ws, label: str, start_row: int) -> int:
    """Section header: small crimson kicker label + thin underline rule."""
    c = ws.cell(row=start_row, column=1, value=label)
    c.font = SECTION_FONT
    c.alignment = ALIGN_LEFT
    ws.row_dimensions[start_row].height = 22
    # Crimson rule under section heading
    rule_row = start_row + 1
    for col in range(1, 13):
        ws.cell(row=rule_row, column=col).border = BORDER_TOP_RULE
    ws.row_dimensions[rule_row].height = 4
    return rule_row + 1


def _add_footer(ws, last_row: int, source: str = None):
    """Small italic-grey footnote line."""
    txt = source or 'Source: yfinance + financedatabase; analysis as of session date. See README for methodology.'
    c = ws.cell(row=last_row + 1, column=1, value=txt)
    c.font = FOOTNOTE_FONT
    c.alignment = ALIGN_LEFT
    ws.merge_cells(start_row=last_row + 1, start_column=1,
                   end_row=last_row + 1, end_column=10)


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
    ws.sheet_view.showGridLines = False
    row = _draw_title_block(
        ws,
        kicker='Cyclepapa Research  ·  Universe Survey  ·  Methodology',
        title='Best of the Best — How to Read This Workbook',
        deck='A single decision-grade survey of the cross-listed equity universe, '
             'screened on three independent measures and reconciled into a watchlist '
             'of cross-validated cheap-and-quality names.',
    )
    row += 1
    sections = [
        ('I.  Purpose',
         'This workbook surfaces the strongest names per region and per measure. Each measure '
         'has documented failure modes — relying on one alone produces false positives. Three '
         'independent screens are computed and the intersection is reported on the "Best of Best" '
         'page. Use that as the starting watchlist; use the per-region and per-measure tabs to '
         'drill down before sizing positions.'),
        ('II. Universe',
         '7,196 tickers from financedatabase across 10 regions (US, JP, KR, HK, AU, CA, GB, DE, '
         'FR, SE). Market-cap floor of US$25M for broad views, US$100M for the financials carve-out. '
         'Junk filtered out: warrants, preferred series, SPAC units, defunct symbols. '
         'See per-region tabs for the count of names scored in each market.'),
        ('III. The Three Measures',
         '(1) Overall sector-percentile composite — 13 valuation, quality and growth components ranked '
         'within region and aggregated into a 0–100 score. Higher = better.\n'
         '(2) Growth-adjusted value — (EV/EBITDA)÷earn-growth and (EV/Sales)÷rev-growth, with a '
         'gentle low-P/B tilt. Lower = cheaper per unit of growth.\n'
         '(3) Financials carve-out — PEG-style ratios are meaningless for banks, insurers and holdcos. '
         'These are scored separately on P/B, P/Tangible-Book, P/E, ROE, ROA, dividend yield and '
         'earnings growth.'),
        ('IV. The Durable-Growth Cut',
         'Raw growth-adjusted ratios are dominated by low-base merger/rebound spikes (Castellum '
         '+65,383% earnings growth from a prior loss; Mirvac +31,987%). The "durable" filter '
         'requires growth in the 10–100% band, removing those artifacts while keeping real '
         'growers like Spigen Korea and Chow Tai Fook in the running.'),
        ('V.  The Book-Value Tilt',
         'tilt = 1 − 0.2 × (1 − P/B) ÷ (1 + P/B).  P/B = 0.5 yields 0.933 (mild reward); P/B = 2 '
         'yields 1.067 (mild penalty). The function saturates at ±20%, so it acts as a '
         'tilt — not the driver — preventing deep-discount names from getting unbounded credit.'),
        ('VI. The Financials Carve-Out',
         'For banks, insurers and holdcos, deposits and reserves dwarf market cap, "sales" is net '
         'interest income or premiums, and earnings move on reserve releases rather than operations. '
         'EV/EBITDA-style screens give garbage rankings for these names. They are excluded from PEG '
         'screens and ranked on capital-appropriate metrics in their own tab.'),
        ('VII. How to Read Numbers',
         'Lower-is-better for all ratio columns (P/B, P/E, EV/EBITDA, ev_*_g). Higher-is-better for '
         'percentile composites (0–100). All market-cap figures are in MILLIONS OF LOCAL CURRENCY '
         '(JP rows are ¥M, KR rows are ₩M, etc).'),
        ('VIII. Known Limitations',
         'Earnings growth above 300% nearly always reflects merger or reserve effects — treat such '
         'rows as flags. Operating margin sharply negative on a high-revenue-growth name is a '
         'cash-burning early-stage signal; the screen does not weight cash burn explicitly. '
         'yfinance forward P/E is often missing on non-US names — this is data unavailability, '
         'not a screen defect.'),
        ('IX. Files & Reproducibility',
         'Cache snapshot lives on origin/cache-snapshot (~18MB tarball, auto-restored on session '
         'start). Result CSVs are committed to the analysis branch. This workbook regenerates from '
         'those CSVs via build_workbook.py.'),
    ]
    for label, body in sections:
        c = ws.cell(row=row, column=1, value=label)
        c.font = SECTION_FONT
        c.alignment = ALIGN_LEFT
        ws.row_dimensions[row].height = 22
        row += 1
        # Crimson rule
        for col in range(1, 11):
            ws.cell(row=row, column=col).border = BORDER_TOP_RULE
        ws.row_dimensions[row].height = 4
        row += 1
        # Body — merged warm-card with wrap
        cell = ws.cell(row=row, column=1, value=body)
        cell.font = BODY_FONT
        cell.alignment = ALIGN_WRAP
        cell.fill = CARD_FILL
        ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=10)
        # Height proportional to text length
        lines = max(2, int(len(body) / 110) + body.count('\n') + 2)
        ws.row_dimensions[row].height = lines * 14
        row += 2
    _add_footer(ws, row)
    ws.column_dimensions['A'].width = 22
    for c in 'BCDEFGHIJ':
        ws.column_dimensions[c].width = 14


def build_exec_summary(wb, comb, gav, fin):
    ws = wb.create_sheet('Executive Summary')
    ws.sheet_view.showGridLines = False
    row = _draw_title_block(
        ws,
        kicker='Executive Summary',
        title='Best of Each Measure, Per Region',
        deck='Top three names per region across three independent screens — the overall '
             'sector-percentile composite, durable-growth EV/EBITDA per growth, and the '
             'financials-specific composite. Use this page to scan; drill into the per-region '
             'tabs to size.',
    )
    row += 1
    gav_dur = prep_growth_adj_view(gav)
    gav_dur = gav_dur[gav_dur['durable']]
    for region in REGIONS:
        row = _draw_section(ws, f'{region}', row)
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
                block[c] = block[c].astype(str).str[:32]
        headers = ['measure','ticker','longName','sector','composite','priceToBook','trailingPE','marketCap_M']
        row = _write_df(ws, block, headers, start_row=row)
        row += 2
    _autosize(ws, ['measure','ticker','longName','sector','composite','priceToBook','trailingPE','marketCap_M'])
    _add_footer(ws, row)


def build_best_of_best(wb, gav, fin, comb, top_n=25):
    ws = wb.create_sheet('Best of Best')
    ws.sheet_view.showGridLines = False
    row = _draw_title_block(
        ws,
        kicker=f'Cross-Validated Watchlist  ·  Top-{top_n} Per Region',
        title='Best of the Best',
        deck=f'Names that screen in the top {top_n} on at least two of four independent measures '
             '(overall composite, durable EV/EBITDA per growth, durable EV/Sales per growth, '
             'financials composite). Three flags = high conviction; four flags = unanimous. '
             'Sort by n_screens then by your preferred measure.',
    )
    row += 1
    bob = best_of_best(gav, fin, comb, top_n=top_n)
    headers = ['ticker','region','longName','sector','marketCap_M','n_screens','screens_in',
               'composite','ev_ebitda_g_bv','ev_sales_g_bv','fin_composite','priceToBook','trailingPE']
    end_row = _write_df(ws, bob, headers, start_row=row)
    # Highlight rows with 3+ flags
    for r in range(row + 1, end_row):
        n_flag_cell = ws.cell(row=r, column=6).value
        if isinstance(n_flag_cell, (int, float)) and n_flag_cell >= 3:
            for c in range(1, len(headers) + 1):
                ws.cell(row=r, column=c).fill = HIGHLIGHT_FILL
                ws.cell(row=r, column=c).font = BODY_BOLD
    _autosize(ws, headers)
    ws.freeze_panes = 'D' + str(row + 1)
    _add_footer(ws, end_row)


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


def _build_measure_sheet(wb, name: str, kicker: str, title: str, deck: str,
                         top_df: pd.DataFrame, headers):
    ws = wb.create_sheet(name)
    ws.sheet_view.showGridLines = False
    row = _draw_title_block(ws, kicker=kicker, title=title, deck=deck)
    row += 1
    end_row = _write_df(ws, top_df, headers, start_row=row)
    _autosize(ws, headers)
    ws.freeze_panes = 'D' + str(row + 1)
    _add_footer(ws, end_row)


def build_global_measures(wb, gav, fin, comb):
    gav_dur = prep_growth_adj_view(gav)
    gav_dur = gav_dur[gav_dur['durable']]

    # Composite
    top = comb.sort_values('composite', ascending=False).head(30)
    if 'longName' in top.columns:
        top['longName'] = top['longName'].astype(str).str[:32]
    headers = [c for c in ['ticker','region','longName','sector','marketCap_M','composite',
                           'priceToBook','trailingPE','forwardPE','enterpriseToEbitda',
                           'net_cash_pct','fcfYield_pct','grossMargins','operatingMargins',
                           'revenueGrowth','earningsGrowth'] if c in top.columns]
    _build_measure_sheet(wb, 'By Measure · Composite',
        kicker='Global Top 30  ·  Sector-Percentile Composite',
        title='Cheapest on Overall Quality-Value Composite',
        deck='13 valuation, quality and growth components ranked within sector, within region. '
             'Higher score (0–100) means the name sits in the upper tail of its peer set across '
             'multiple dimensions simultaneously.',
        top_df=top, headers=headers)

    # Growth-adj EBITDA
    top = _global_top_by(gav_dur, 'ev_ebitda_g_bv', True, 30, extra_cols=['_bv_tilt'])
    _build_measure_sheet(wb, 'By Measure · Growth-Adj',
        kicker='Global Top 30  ·  Cheapest Per Unit of Earnings Growth',
        title='EV/EBITDA per Earnings Growth, BV-tilted',
        deck='(EV / EBITDA) ÷ earnings-growth %, with a low-P/B reward (bounded ±20%). Durable '
             'cut applied: growth in the 10–100% band. Lower = cheaper per unit of growth.',
        top_df=top, headers=list(top.columns))

    # Growth-adj Sales
    top = _global_top_by(gav_dur, 'ev_sales_g_bv', True, 30, extra_cols=['_bv_tilt'])
    _build_measure_sheet(wb, 'By Measure · Sales-Growth',
        kicker='Global Top 30  ·  Cheapest Per Unit of Revenue Growth',
        title='EV/Sales per Revenue Growth, BV-tilted',
        deck='(EV / Sales) ÷ revenue-growth %, with the same low-P/B reward. EV/Sales is rebuilt '
             'from P/S × (EV/MktCap) so it is currency-neutral across regions.',
        top_df=top, headers=list(top.columns))

    # Financials
    top = fin.sort_values('fin_composite', ascending=False).head(30)
    if 'longName' in top.columns:
        top['longName'] = top['longName'].astype(str).str[:32]
    headers = [c for c in ['ticker','region','longName','industry','marketCap_M','fin_composite',
                           'priceToBook','priceToTangibleBook','trailingPE','forwardPE',
                           'returnOnEquity','returnOnAssets','dividendYield','earningsGrowth'] if c in top.columns]
    _build_measure_sheet(wb, 'By Measure · Financials',
        kicker='Global Top 30  ·  Financials Carve-Out',
        title='Best Banks, Insurers and Holdcos by Capital-Appropriate Metrics',
        deck='Sector-percentile composite within region across P/B, P/Tangible-Book, P/E (trailing '
             'and forward), ROE, ROA, dividend yield and earnings growth. PEG-style ratios are '
             'deliberately not used here.',
        top_df=top, headers=headers)


REGION_FULL_NAME = {
    'US': 'United States', 'JP': 'Japan', 'KR': 'South Korea', 'HK': 'Hong Kong',
    'AU': 'Australia', 'CA': 'Canada', 'GB': 'United Kingdom', 'DE': 'Germany',
    'FR': 'France', 'SE': 'Sweden',
}

def build_per_region_tabs(wb, gav, fin, comb, per_region):
    gav_dur = prep_growth_adj_view(gav)
    gav_dur = gav_dur[gav_dur['durable']]
    for region in REGIONS:
        ws = wb.create_sheet(f'Region · {region}')
        ws.sheet_view.showGridLines = False
        full = REGION_FULL_NAME.get(region, region)
        row = _draw_title_block(
            ws,
            kicker=f'Region File  ·  {region}',
            title=f'{full} — Top Picks Across All Measures',
            deck='Four sections, each ranked to the region\'s own universe: overall composite, '
                 'durable EV/EBITDA per growth, durable EV/Sales per growth, and the financials '
                 'carve-out.',
        )
        row += 1

        # Section I
        row = _draw_section(ws, 'I.  Overall sector-percentile composite — top 25 in region', row)
        sub = comb[comb.region == region].sort_values('composite', ascending=False).head(25)
        headers = [c for c in ['ticker','longName','sector','marketCap_M','composite',
                                'priceToBook','trailingPE','forwardPE','enterpriseToEbitda',
                                'net_cash_pct','fcfYield_pct','grossMargins','operatingMargins',
                                'revenueGrowth','earningsGrowth'] if c in sub.columns]
        if 'longName' in sub.columns:
            sub['longName'] = sub['longName'].astype(str).str[:32]
        row = _write_df(ws, sub, headers, start_row=row)
        row += 2

        # Section II
        row = _draw_section(ws, 'II. Durable-growth cheapest on EV/EBITDA per growth (BV-tilted) — top 25', row)
        sub2 = gav_dur[gav_dur.region == region].dropna(subset=['ev_ebitda_g_bv']).sort_values('ev_ebitda_g_bv').head(25)
        h2 = ['ticker','longName','sector','marketCap_M','ev_ebitda_g_bv','ev_ebitda',
              'priceToBook','rev_g_pct','earn_g_pct','earn_g_q_pct']
        h2 = [c for c in h2 if c in sub2.columns]
        if 'longName' in sub2.columns:
            sub2['longName'] = sub2['longName'].astype(str).str[:32]
        row = _write_df(ws, sub2, h2, start_row=row)
        row += 2

        # Section III
        row = _draw_section(ws, 'III. Durable-growth cheapest on EV/Sales per growth (BV-tilted) — top 25', row)
        sub3 = gav_dur[gav_dur.region == region].dropna(subset=['ev_sales_g_bv']).sort_values('ev_sales_g_bv').head(25)
        h3 = ['ticker','longName','sector','marketCap_M','ev_sales_g_bv','ev_sales',
              'priceToBook','rev_g_pct','earn_g_pct','earn_g_q_pct']
        h3 = [c for c in h3 if c in sub3.columns]
        if 'longName' in sub3.columns:
            sub3['longName'] = sub3['longName'].astype(str).str[:32]
        row = _write_df(ws, sub3, h3, start_row=row)
        row += 2

        # Section IV
        row = _draw_section(ws, 'IV. Financials carve-out — top 25 (P/B + P/E + ROE + dividend composite)', row)
        sub4 = fin[fin.region == region].dropna(subset=['fin_composite']).sort_values('fin_composite', ascending=False).head(25)
        h4 = [c for c in ['ticker','longName','industry','marketCap_M','fin_composite',
                          'priceToBook','priceToTangibleBook','trailingPE','forwardPE',
                          'returnOnEquity','returnOnAssets','dividendYield','earningsGrowth'] if c in sub4.columns]
        if 'longName' in sub4.columns:
            sub4['longName'] = sub4['longName'].astype(str).str[:32]
        row = _write_df(ws, sub4, h4, start_row=row)
        _add_footer(ws, row)


def build_glossary(wb):
    ws = wb.create_sheet('Glossary')
    ws.sheet_view.showGridLines = False
    row = _draw_title_block(
        ws,
        kicker='Reference',
        title='Glossary  ·  Column Dictionary',
        deck='What every column means, in plain English. Use to interpret the screen outputs.',
    )
    row += 1
    rows = [
        ('ticker', 'Symbol as listed on the primary exchange (with suffix for non-US listings).'),
        ('region', 'US, JP, KR, HK, AU, CA, GB, DE, FR, SE.'),
        ('longName', 'Company name as reported by the data vendor.'),
        ('sector', 'GICS-style sector — Technology, Financial Services, Basic Materials, etc.'),
        ('industry', 'Sub-sector — Banks – Regional, Insurance – Life, Asset Management, etc.'),
        ('marketCap_M', 'Market capitalization in millions of local currency. JP = ¥M, KR = ₩M, etc.'),
        ('composite', 'Overall sector-percentile composite (0–100, higher is better). Thirteen sub-components, ranked within sector and region.'),
        ('fin_composite', 'Financials-specific composite (0–100, higher is better). Eight sub-components including P/B, P/TBV, P/E, ROE, ROA and dividend yield.'),
        ('priceToBook', 'P/B ratio (lower is cheaper). Negative values indicate impaired equity and are excluded from the percentile.'),
        ('priceToTangibleBook', 'Price to tangible book value, derived from the cached balance sheet where available; falls back to P/B otherwise.'),
        ('trailingPE', 'Trailing twelve-month price-to-earnings. NaN for loss-makers.'),
        ('forwardPE', 'Consensus forward P/E. Frequently absent for non-US names — this is a data-coverage gap, not a screen defect.'),
        ('enterpriseToEbitda', 'EV/EBITDA. Suppressed in PEG ratios for financials.'),
        ('enterpriseToRevenue / ev_sales', 'EV/Sales. Rebuilt from P/S × (EV ÷ market cap) so the units are currency-neutral.'),
        ('ev_ebitda_g', '(EV/EBITDA) ÷ earnings-growth %. NaN for non-growers, negative growth, or financials.'),
        ('ev_ebitda_g_ltm', 'Same metric using latest-quarter earnings growth — more current; roughly 35% row coverage.'),
        ('ev_sales_g', '(EV/Sales) ÷ revenue-growth %. NaN for non-growers and financials.'),
        ('ev_*_g_bv', 'Multiplied by bv_tilt(P/B). tilt = 1 − 0.2 × (1 − P/B) ÷ (1 + P/B). Saturates at ±20%. Rewards low P/B mildly.'),
        ('durable', 'True if growth sits in the 10–100% band — excludes merger and low-base spikes.'),
        ('rev_g_pct', 'Annual revenue growth %, from yfinance revenueGrowth × 100.'),
        ('earn_g_pct', 'Annual earnings growth %, from yfinance earningsGrowth × 100.'),
        ('earn_g_q_pct', 'Latest-quarter earnings growth %, from yfinance earningsQuarterlyGrowth × 100.'),
        ('net_cash_pct', '(Total cash − total debt) ÷ market cap × 100. Values above 100% mean net cash exceeds market cap.'),
        ('fcfYield_pct', 'Free cash flow ÷ market cap × 100.'),
        ('grossMargins / operatingMargins / profitMargins', 'Decimal margins (0.30 = 30%).'),
        ('returnOnEquity / returnOnAssets', 'Decimal returns. 0.20 = 20%.'),
        ('dividendYield', 'Decimal forward yield (0.04 = 4%). Often missing for non-US names.'),
        ('n_screens', 'Number of top-25 lists in which the name appears (maximum four). Best-of-Best sheet only.'),
        ('screens_in', 'Which lists the name appears in: Composite, Growth-Adj-EBITDA, Growth-Adj-Sales, Financials.'),
    ]
    # Header
    for c, h in enumerate(['Column','Meaning'], 1):
        cell = ws.cell(row=row, column=c, value=h)
        cell.font = TABLE_HEAD_FT
        cell.fill = HEAD_FILL
        cell.alignment = ALIGN_CTR
    row += 1
    for i, (k, v) in enumerate(rows):
        c1 = ws.cell(row=row, column=1, value=k); c1.font = BODY_BOLD
        c1.alignment = ALIGN_LEFT
        c2 = ws.cell(row=row, column=2, value=v); c2.font = BODY_FONT
        c2.alignment = Alignment(wrap_text=True, vertical='top', indent=1)
        if i % 2 == 0:
            c1.fill = ALT_FILL; c2.fill = ALT_FILL
        c1.border = Border(bottom=RULE_THIN)
        c2.border = Border(bottom=RULE_THIN)
        ws.row_dimensions[row].height = 24
        row += 1
    ws.column_dimensions['A'].width = 30
    ws.column_dimensions['B'].width = 110
    _add_footer(ws, row)


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
