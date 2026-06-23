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

REGIONS = ['US','JP','GB','DE','FR','CA','AU',         # Tier 1
           'CH','IT','NL','ES','SE','NO','DK','BE','FI','IE','AT','PT','GR',   # Tier 2 EU
           'KR','HK','TW','SG','NZ','IL',              # Tier 3 APAC
           'CN','IN','BR','MX','ZA','TR','TH','ID']    # Tier 4 EM

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

# Serif throughout (Harvard style) — Times New Roman everywhere, including body
TITLE_FONT_NAME = 'Times New Roman'
H_FONT_NAME     = 'Times New Roman'
BODY_FONT_NAME  = 'Times New Roman'

TITLE_FONT    = Font(name=TITLE_FONT_NAME, size=24, bold=False, color=SLATE_DARK)
KICKER_FONT   = Font(name=BODY_FONT_NAME, size=9, bold=True, color=CRIMSON)
DECK_FONT     = Font(name=TITLE_FONT_NAME, size=13, italic=True, color=SLATE_MUTED)
SECTION_FONT  = Font(name=H_FONT_NAME, size=13, bold=True, color=SLATE_DARK)
SUBSECT_FONT  = Font(name=BODY_FONT_NAME, size=10, bold=True, color=CRIMSON)
BODY_FONT     = Font(name=BODY_FONT_NAME, size=11, color=SLATE)
BODY_BOLD     = Font(name=BODY_FONT_NAME, size=11, bold=True, color=SLATE_DARK)
CAPTION_FONT  = Font(name=BODY_FONT_NAME, size=10, italic=True, color=SLATE_MUTED)
TABLE_HEAD_FT = Font(name=BODY_FONT_NAME, size=11, bold=True, color=SLATE_DARK)
FOOTNOTE_FONT = Font(name=BODY_FONT_NAME, size=9, italic=True, color=SLATE_MUTED)

WARM_FILL  = PatternFill('solid', fgColor=WARM_WHITE)
ALT_FILL   = PatternFill('solid', fgColor=WARM_WHITE)  # no row stripes — Harvard tables don't stripe
CARD_FILL  = PatternFill('solid', fgColor=CARD_BG)
HIGHLIGHT_FILL = PatternFill('solid', fgColor=HIGHLIGHT)
HEAD_FILL  = PatternFill('solid', fgColor=WARM_WHITE)  # no header fill — Harvard tables use underline
HEAD_DARK_FILL = PatternFill('solid', fgColor=CRIMSON_DARK)

# Harvard "booktabs"-style rules. Tables have a heavy top rule, a hairline
# under the header row, and a hairline at the bottom. No vertical lines.
RULE_HEAVY   = Side(style='medium', color=SLATE_DARK)  # 1.5pt top-of-table rule
RULE_HEAD    = Side(style='thin', color=SLATE_DARK)    # 0.5pt under header
RULE_BOTTOM  = Side(style='thin', color=SLATE_DARK)    # 0.5pt at end of table
RULE_CRIMSON = Side(style='medium', color=CRIMSON)     # crimson section/title rule
NO_BORDER    = Border()  # explicit empty border for body cells

ALIGN_LEFT  = Alignment(horizontal='left',   vertical='center', indent=0)
ALIGN_RIGHT = Alignment(horizontal='right',  vertical='center', indent=0)
ALIGN_CTR   = Alignment(horizontal='center', vertical='center', wrap_text=True)
ALIGN_WRAP  = Alignment(horizontal='left',   vertical='top',    wrap_text=True, indent=0)


def _style_header(ws, row, col_start, col_end):
    """Booktabs-style header — bold black text on warm white, heavy top rule,
    thin bottom rule. No vertical or fill colours."""
    for c in range(col_start, col_end + 1):
        cell = ws.cell(row=row, column=c)
        cell.font = TABLE_HEAD_FT
        cell.fill = WARM_FILL
        cell.alignment = ALIGN_CTR
        cell.border = Border(top=RULE_HEAVY, bottom=RULE_HEAD)


def _autosize(ws, headers, max_w=34):
    """Set column widths from the wider of the humanised header label vs the
    longest cell value (capped). Adds ~2 chars padding."""
    for i, h in enumerate(headers, 1):
        col_letter = get_column_letter(i)
        # Header width uses the humanised label (what's actually rendered)
        header_label = _humanize(h)
        max_len = len(str(header_label))
        for row in ws.iter_rows(min_col=i, max_col=i, values_only=True):
            for v in row:
                if v is None:
                    continue
                # For numbers, account for comma separators and "%" suffix
                if isinstance(v, (int, float)) and not isinstance(v, bool):
                    if abs(v) >= 1000:
                        digits = len(f'{v:,.0f}')
                    else:
                        digits = len(f'{v:.2f}')
                    max_len = max(max_len, digits + 2)  # +2 for () negative
                else:
                    max_len = max(max_len, min(len(str(v)), max_w))
        ws.column_dimensions[col_letter].width = max(10, min(max_len + 2, max_w))


_TEXT_COLS = {
    'ticker','company','sector','industry','country','region','name','longname',
    'shortname','category','growing_revenue_type','status','path','measure',
    'symbol','holder','firm','position','action','grade','transaction','insider',
    'ownership','text','url','tab','periodtype','period','pe_peak_date',
}

# Human-readable column titles. snake_case → Title-Case-with-Units. Anything
# not in the map is title-cased automatically (rev_yoy_pct → "Rev Yoy Pct").
# Tune this dictionary when a column reads awkwardly in the published sheets.
COLUMN_LABELS: dict[str, str] = {
    'ticker': 'Ticker',
    'company': 'Company',
    'sector': 'Sector',
    'industry': 'Industry',
    'country': 'Country',
    'region': 'Region',
    'longName': 'Company',
    'shortName': 'Company',
    'category': 'Category',
    'growing_revenue_type': 'Growing Revenue Type',
    'status': 'Status',
    'path': 'Path',
    'measure': 'Measure',
    'rows': 'Rows',
    # Valuation
    'market_cap': 'Market Cap',
    'marketCap': 'Market Cap',
    'marketCap_M': 'Market Cap ($M)',
    'enterpriseValue': 'Enterprise Value',
    'ev_now': 'Enterprise Value',
    'priceToBook': 'P/B',
    'priceToTangibleBook': 'P/TBV',
    'priceToSales': 'P/S',
    'trailingPE': 'P/E (TTM)',
    'forwardPE': 'P/E (Fwd)',
    'enterpriseToEbitda': 'EV/EBITDA',
    'enterpriseToRevenue': 'EV/Sales',
    'evEbitda': 'EV/EBITDA',
    'ev_ebitda_now': 'EV/EBITDA',
    'ev_sales_now': 'EV/Sales',
    'ev_fcf_now': 'EV/FCF',
    'ev_fcf_per_growth': 'EV/FCF per pp Growth',
    'ev_ebitda_over_ebg_ltm': 'EV/EBITDA ÷ EBITDA Growth (LTM)',
    'ev_ebitda_over_ebg_yr': 'EV/EBITDA ÷ EBITDA Growth (Annual)',
    'ev_ebitda_over_earng': 'EV/EBITDA ÷ Earnings Growth',
    'ebitda_g_ltm_pct': 'EBITDA Growth (LTM)',
    'ebitda_g_yr_pct': 'EBITDA Growth (Annual)',
    'ev_ebitda_g': 'EV/EBITDA ÷ EBITDA Growth',
    'ev_ebitda_g_ltm': 'EV/EBITDA ÷ EBITDA Growth (LTM)',
    'ev_ebitda_g_bv': 'EV/EBITDA ÷ EBITDA Growth × BV Tilt',
    'ev_sales_g': 'EV/Sales ÷ Sales Growth',
    'ev_sales_g_ltm': 'EV/Sales ÷ Sales Growth (LTM)',
    'ev_sales_g_bv': 'EV/Sales ÷ Sales Growth × BV Tilt',
    'rev_g_pct': 'Revenue Growth',
    'earn_g_pct': 'Earnings Growth',
    'earn_g_q_pct': 'Earnings Growth (Q)',
    'pe_now': 'P/E Now',
    'pe_y_ago': 'P/E 1Y Ago',
    'pe_turns_yoy': 'P/E Δ (turns)',
    'pe_change_pct': 'P/E Change',
    'pe_peak_5y': 'P/E Peak (5Y)',
    'pe_turns_off_peak': 'Turns Off Peak',
    'pe_pct_off_peak': 'Off Peak',
    'pe_peak_date': 'Peak Date',
    'ps_now': 'P/S',
    'pb_now': 'P/B',
    'multiple_compression_pct': 'Multiple Compression',
    # Performance
    'perf_1y_pct': '1Y Performance',
    'price_now': 'Price Now',
    'price_y_ago': 'Price 1Y Ago',
    'price_change_pct': 'Price Change',
    'price_3y_pct': '3Y Price Change',
    # Top line / margins
    'rev_ltm_now_M': 'Revenue LTM ($M)',
    'rev_ltm_yoy_pct': 'Revenue YoY',
    'rev_now_M': 'Revenue LTM ($M)',
    'rev_y_ago_M': 'Revenue 1Y Ago ($M)',
    'rev_yoy_pct': 'Revenue YoY',
    'rev_growth_yoy_pct': 'Revenue YoY',
    'sales_growth_pct': 'Sales Growth',
    'gross_ltm_now_M': 'Gross Profit LTM ($M)',
    'gross_ltm_yoy_pct': 'Gross Profit YoY',
    'gross_margin_now_pct': 'Gross Margin',
    'gross_margin_chg_pp': 'Gross Margin Δ (pp)',
    'op_margin_now_pct': 'Op Margin',
    'op_margin_chg_pp': 'Op Margin Δ (pp)',
    'margin_expansion_pp': 'Margin Δ (pp)',
    'ebitda_now_M': 'EBITDA LTM ($M)',
    'ebitda_margin_now_pct': 'EBITDA Margin',
    'ebitda_margin_y_ago_pct': 'EBITDA Margin 1Y Ago',
    'ebitda_yoy_pct': 'EBITDA YoY',
    'ebitda_growth_pct': 'EBITDA Growth',
    # Cash flow / yield
    'fcf_now_M': 'FCF LTM ($M)',
    'fcf_y_ago_M': 'FCF 1Y Ago ($M)',
    'fcf_yoy_pct': 'FCF YoY',
    'fcf_growth_pct': 'FCF Growth',
    'fcf_margin_now_pct': 'FCF Margin',
    'fcf_margin_y_ago_pct': 'FCF Margin 1Y Ago',
    'fcf_yield_now_pct': 'FCF Yield Now',
    'fcf_yield_y_ago_pct': 'FCF Yield 1Y Ago',
    'fcf_yield_2y_ago_pct': 'FCF Yield 2Y Ago',
    'fcf_yield_3y_ago_pct': 'FCF Yield 3Y Ago',
    'yield_trend_pp_1y': 'Yield Trend 1Y (pp)',
    'yield_trend_pp_2y': 'Yield Trend 2Y (pp)',
    'yield_yoy_growth_pct': 'Yield YoY Growth',
    'fcf_ps_growth_pct': 'FCF/sh Growth',
    'fcf_ps_3y_growth_pct': 'FCF/sh 3Y Growth',
    'ltm_fcf_ps_now': 'FCF/sh LTM',
    # Earnings
    'eps_now_ltm': 'EPS LTM',
    'eps_y_ago_ltm': 'EPS 1Y Ago',
    'eps_growth_pct': 'EPS Growth',
    'roe_pct': 'ROE',
    # Balance sheet
    'debt_to_equity': 'D/E',
    'shares_1y_chg': 'Shares Δ (1Y)',
    # Segment
    'share_now': 'Segment Share',
    'seg_growth': 'Segment Growth',
    'total_growth': 'Total Growth',
    'excess_growth': 'Excess Growth',
    'years_to_50pct': 'Years to 50%',
    'seg_ltm': 'Segment LTM',
    'total_ltm': 'Total LTM',
    'n_quarters': 'Quarters',
    'cheap_pct': 'Cheap Pct',
    'avg_inflection_z': 'Inflection Z',
    # Scores
    'akre_score': 'Akre Score',
    'seg_score': 'Segment Score',
    'pre_rerate_score': 'Pre-Rerate Score',
    'leverage_score': 'Leverage Score',
    'quality_score': 'Quality Score',
    'composite': 'Composite',
    'fin_composite': 'Fin Composite',
    'is_inflection': 'Inflection?',
    'is_acceleration': 'Acceleration?',
}

def _humanize(col: str) -> str:
    """Friendly column header. Use COLUMN_LABELS when mapped, else title-case
    the snake_case identifier."""
    if col in COLUMN_LABELS:
        return COLUMN_LABELS[col]
    # Auto title-case fallback
    parts = str(col).replace('_', ' ').split()
    pretty = []
    for p in parts:
        up = p.upper()
        if up in ('LTM','TTM','YOY','M','B','P','PE','PB','PS','EV','FCF','EBITDA','EPS','ROE','ROA','PP','USD','API'):
            pretty.append(up)
        else:
            pretty.append(p.title())
    return ' '.join(pretty)


def _truncate_with_ellipsis(s: str, max_len: int) -> str:
    """Trim long strings to max_len chars, ending with a real ellipsis
    (U+2026) when truncated. Preserves whole words when possible."""
    s = str(s)
    if len(s) <= max_len:
        return s
    cut = s[: max_len - 1].rstrip(' ,.;:-')
    return cut + '…'

def _excel_number_format(col_name: str, sample: float | None = None) -> str | None:
    """Pick an Excel number format string based on column-name heuristics.
    Returns None for text/id columns. All numeric formats use comma
    thousands separators and parentheses for negatives (Harvard-magazine
    convention for financial tables)."""
    name = (col_name or '').lower()
    if name in _TEXT_COLS:
        return None
    # Z-scores and other dimensionless metrics (don't carry %)
    if name in ('avg_inflection_z',):
        return '#,##0.00;(#,##0.00);"–"'
    # Fractional columns — stored as decimals (0.105 means 10.5%, 37.8 means
    # 3780%). Use Excel's auto-percentage format which multiplies by 100.
    if name in ('share_now','shares_1y_chg','seg_growth','total_growth',
                'excess_growth'):
        return r'0.0%;(0.0%);"–"'
    # Percent-like columns — data is already in pct points (e.g. 23.4 means
    # 23.4%). Render with a literal % suffix (Excel: escape with backslash).
    if (name.endswith('_pct') or name.endswith('_pct_change') or '_pp' in name
            or 'percent' in name or name in ('perf_1y','perf_1y_pct',
            'cheap_pct','rev_growth','sales_growth_pct',
            'fcf_growth_pct','ebitda_growth_pct','margin_expansion_pp',
            'price_change_pct','price_3y_pct','rev_yoy_pct','fcf_yoy_pct',
            'ebitda_yoy_pct','fcf_ps_3y_growth_pct','yield_yoy_growth_pct',
            'yield_trend_pp_1y','yield_trend_pp_2y')):
        return r'#,##0.0\%;(#,##0.0\%);"–"'
    # Money fields in millions (suffixed _M) — show with comma, no decimals
    if name.endswith('_m') or name.endswith('_ltm_m') or name == 'rev_now_m' or name == 'fcf_now_m':
        return '#,##0;(#,##0);"–"'
    # Money fields in billions
    if name.endswith('_b') or name.endswith('_ltm_b'):
        return '#,##0.00;(#,##0.00);"–"'
    # Raw market cap / enterprise value — big numbers, no decimals
    if name in ('market_cap','marketcap','enterprisevalue','ev_now','ev','total_ltm','seg_ltm'):
        return '#,##0;(#,##0);"–"'
    # Days / counts / years
    if name in ('years_to_50pct','n_quarters'):
        return '#,##0.0;(#,##0.0);"–"'
    # Valuation ratios / scores — 2dp
    if name in ('pricetobook','pricetosales','trailingpe','forwardpe',
                'enterprisetoebitda','enterprisetorevenue','evebitda','ev_ebitda',
                'psg','pe_now','pe_y_ago','ps_now','pb_now','priceToBook'.lower(),
                'priceToSales'.lower(),'priceToTangibleBook'.lower(),
                'pretty_pe','peg','akre_score','seg_score','quality_score',
                'pre_rerate_score','leverage_score','composite','fin_composite',
                'multiple_compression_pct','debt_to_equity'):
        return '#,##0.00;(#,##0.00);"–"'
    # Prices — 2dp
    if name in ('price_now','price_y_ago','price','open','close','high','low',
                'eps_now_ltm','eps_y_ago_ltm','eps','ltm_fcf_ps_now'):
        return '#,##0.00;(#,##0.00);"–"'
    # Default for any other numeric column: 2dp + brackets for negatives
    return '#,##0.00;(#,##0.00);"–"'


def _write_df(ws, df: pd.DataFrame, headers, start_row: int = 1, alt_shade=True):
    """Write a DataFrame as a Harvard-style booktabs table:
       heavy top rule, thin rule under header, thin rule at bottom.
       No vertical lines, no row striping, no cell borders.
       Numeric columns get comma separators + parens for negatives."""
    if df.empty:
        c = ws.cell(row=start_row, column=1, value='— no rows —')
        c.font = CAPTION_FONT
        c.alignment = ALIGN_LEFT
        return start_row + 2
    # Decide a number format per column from the first non-null sample,
    # plus determine whether each column is numeric (for alignment).
    col_fmt: dict[str, str | None] = {}
    col_is_numeric: dict[str, bool] = {}
    for h in headers:
        sample = None
        numeric = False
        if h in df.columns:
            s = df[h].dropna()
            if not s.empty:
                v = s.iloc[0]
                if isinstance(v, (int, float, np.integer, np.floating)) and not isinstance(v, bool):
                    sample = float(v)
                    numeric = True
        col_fmt[h] = _excel_number_format(h, sample)
        col_is_numeric[h] = numeric and (h.lower() not in _TEXT_COLS)

    # Header row: humanised labels, right-align numeric column headers so
    # they sit over their digits; left-align text headers.
    for i, h in enumerate(headers, 1):
        cell = ws.cell(row=start_row, column=i, value=_humanize(h))
    _style_header(ws, start_row, 1, len(headers))
    # Re-apply alignment per column (overrides the centred default from _style_header)
    for i, h in enumerate(headers, 1):
        cell = ws.cell(row=start_row, column=i)
        cell.alignment = ALIGN_RIGHT if col_is_numeric.get(h) else ALIGN_LEFT

    last_data_row = start_row + len(df)
    # Column width guards for truncating very long strings (company names etc.)
    max_text_width = {'company': 38, 'industry': 32, 'sector': 24, 'country': 22,
                      'longName': 38, 'shortName': 38, 'name': 32}
    for r, (_, row) in enumerate(df.iterrows(), start=start_row + 1):
        is_last = (r == last_data_row)
        for c, h in enumerate(headers, 1):
            v = row.get(h)
            if pd.isna(v) or v == '' or v is None:
                cell = ws.cell(row=r, column=c, value=None)
                # Show em-dash for blank numeric cells; blank for blank text
                if col_is_numeric.get(h):
                    cell.value = None  # number_format "–" placeholder handles it
                cell.font = BODY_FONT
                cell.alignment = ALIGN_RIGHT if col_is_numeric.get(h) else ALIGN_LEFT
                cell.fill = WARM_FILL
                cell.border = Border(bottom=RULE_BOTTOM) if is_last else NO_BORDER
                continue
            # Preserve native numeric types — formatting is via number_format
            if isinstance(v, (np.integer,)):
                v = int(v)
            elif isinstance(v, (np.floating, float)):
                v = float(v)
            elif isinstance(v, str):
                # Truncate long text cleanly with an ellipsis (not hard-cut)
                if h in max_text_width:
                    v = _truncate_with_ellipsis(v, max_text_width[h])
            cell = ws.cell(row=r, column=c, value=v)
            if isinstance(v, bool):
                cell.alignment = ALIGN_LEFT
            elif isinstance(v, (int, float)):
                cell.alignment = ALIGN_RIGHT
                fmt = col_fmt.get(h)
                if fmt:
                    cell.number_format = fmt
            else:
                cell.alignment = ALIGN_LEFT
            cell.font = BODY_FONT
            cell.fill = WARM_FILL
            if is_last:
                cell.border = Border(bottom=RULE_BOTTOM)
            else:
                cell.border = NO_BORDER
    return last_data_row + 2  # one blank row after the table


def _set_page_background(ws, last_col_letter='Z', last_row=600):
    """Tint the whole sheet warm-white (HBS magazine look)."""
    # Set the default row fill via the sheet-level approach: apply WARM_FILL
    # to a strip of cells. Cheaper: just rely on explicit row backgrounds.
    pass


def _draw_title_block(ws, kicker: str, title: str, deck: str = None,
                      start_row: int = 1):
    """Harvard-style title block — kicker label, serif title, italic deck,
    bracketed top and bottom by crimson rules (the only horizontal lines
    on the page above the data tables)."""
    # Top crimson rule above kicker
    top_rule_row = start_row
    for col in range(1, 13):
        ws.cell(row=top_rule_row, column=col).border = Border(top=RULE_CRIMSON)
    ws.row_dimensions[top_rule_row].height = 5
    # Kicker (small uppercase) directly below the rule
    kicker_row = top_rule_row + 1
    if kicker:
        c = ws.cell(row=kicker_row, column=1, value=kicker.upper())
        c.font = KICKER_FONT
        c.alignment = ALIGN_LEFT
        ws.row_dimensions[kicker_row].height = 16
    # Title
    title_row = kicker_row + 1
    c = ws.cell(row=title_row, column=1, value=title)
    c.font = TITLE_FONT
    c.alignment = Alignment(horizontal='left', vertical='center', indent=0)
    ws.row_dimensions[title_row].height = 34
    # Deck
    deck_row = title_row + 1
    if deck:
        c = ws.cell(row=deck_row, column=1, value=deck)
        c.font = DECK_FONT
        c.alignment = Alignment(horizontal='left', vertical='center', wrap_text=True)
        ws.merge_cells(start_row=deck_row, start_column=1, end_row=deck_row, end_column=10)
        ws.row_dimensions[deck_row].height = 26
        last_row = deck_row
    else:
        last_row = title_row
    # Bottom crimson rule under the title block
    rule_row = last_row + 1
    for col in range(1, 13):
        ws.cell(row=rule_row, column=col).border = Border(top=RULE_CRIMSON)
    ws.row_dimensions[rule_row].height = 5
    return rule_row + 1


def _draw_section(ws, label: str, start_row: int) -> int:
    """Section header: serif italicized-style label with a crimson underline rule."""
    c = ws.cell(row=start_row, column=1, value=label)
    c.font = SECTION_FONT
    c.alignment = ALIGN_LEFT
    ws.row_dimensions[start_row].height = 24
    # Single underline beneath label (cells under text only)
    rule_row = start_row + 1
    for col in range(1, 13):
        ws.cell(row=rule_row, column=col).border = Border(top=Side(style='thin', color=CRIMSON))
    ws.row_dimensions[rule_row].height = 3
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
        ws.row_dimensions[row].height = 24
        row += 1
        # Crimson hairline under section heading
        for col in range(1, 11):
            ws.cell(row=row, column=col).border = Border(top=Side(style='thin', color=CRIMSON))
        ws.row_dimensions[row].height = 3
        row += 1
        # Body — wrapped with no card-fill (Harvard journal pages are uncoloured)
        cell = ws.cell(row=row, column=1, value=body)
        cell.font = BODY_FONT
        cell.alignment = ALIGN_WRAP
        cell.fill = WARM_FILL
        ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=10)
        lines = max(2, int(len(body) / 110) + body.count('\n') + 2)
        ws.row_dimensions[row].height = lines * 16
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
    # Subtle highlight on rows that screen in 3+ lists. Preserve existing
    # borders (the booktabs rule on the last row) and keep alignment.
    for r in range(row + 1, end_row):
        n_flag_cell = ws.cell(row=r, column=6).value
        if isinstance(n_flag_cell, (int, float)) and n_flag_cell >= 3:
            for c in range(1, len(headers) + 1):
                cell = ws.cell(row=r, column=c)
                cell.fill = HIGHLIGHT_FILL
                cell.font = Font(name=BODY_FONT_NAME, size=11, bold=True, color=SLATE_DARK)
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
    'US': 'United States', 'JP': 'Japan', 'GB': 'United Kingdom', 'DE': 'Germany',
    'FR': 'France', 'CA': 'Canada', 'AU': 'Australia',
    'CH': 'Switzerland', 'IT': 'Italy', 'NL': 'Netherlands', 'ES': 'Spain',
    'SE': 'Sweden', 'NO': 'Norway', 'DK': 'Denmark', 'BE': 'Belgium',
    'FI': 'Finland', 'IE': 'Ireland', 'AT': 'Austria', 'PT': 'Portugal', 'GR': 'Greece',
    'KR': 'South Korea', 'HK': 'Hong Kong', 'TW': 'Taiwan', 'SG': 'Singapore',
    'NZ': 'New Zealand', 'IL': 'Israel',
    'CN': 'China', 'IN': 'India', 'BR': 'Brazil', 'MX': 'Mexico',
    'ZA': 'South Africa', 'TR': 'Turkey', 'TH': 'Thailand', 'ID': 'Indonesia',
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


CREATIVE_MEASURES = [
    ('results_multiple_compression/screener.csv', 'Multiple Compression',
     'Names with P/E and EV/EBITDA compression — both YoY (turns + %) and vs the 5-year peak. '
     'pe_turns_yoy/ev_turns_yoy = absolute multiple shrinkage in turns; '
     'pe_pct_off_peak/ev_pct_off_peak = how far below the 5y peak we are now. '
     'EV/EBITDA history reconstructed from rolling-4Q EBITDA × shares_now + net_debt_now '
     '(conservative — biased to UNDER-state compression).',
     ['ticker','pe_now','pe_y_ago','pe_turns_yoy','pe_change_pct',
      'pe_peak_5y','pe_turns_off_peak','pe_pct_off_peak','pe_peak_date',
      'ev_ebitda_now','ev_ebitda_y_ago_recon','ev_turns_yoy','ev_yoy_pct',
      'ev_ebitda_peak_5y','ev_turns_off_peak','ev_pct_off_peak','ev_peak_date',
      'price_change_pct','eps_growth_pct','pb_now','market_cap','priceToSales']),
    ('results_akre/screener.csv', 'Akre Compounder',
     'Three-leg framework — ROE × reinvestment × durable moat. Higher akre_score = stronger compounder.',
     ['ticker','akre_score','roe_pct','op_margin_now_pct','op_margin_chg_pp','rev_growth_yoy_pct',
      'fcf_ps_growth_pct','perf_1y_pct','market_cap','trailingPE','priceToBook','priceToSales','enterpriseToEbitda','debt_to_equity']),
    ('results_clean_topline/screener.csv', 'Clean Top-Line',
     'Names with revenue +15%, gross profit +15%, and gross margin expanding — hardest-to-fake fundamentals.',
     None),
    ('results_op_leverage/screener.csv', 'Operating Leverage',
     'Revenue grows X%, EBITDA grows ≥2X% — margins scaling, true operating leverage.',
     None),
    ('results_fcf_yield/screener.csv', 'FCF Yield',
     'FCF/price ranking with quality screens — durable cash return on equity value.',
     None),
    ('results_ev_compression/screener.csv', 'EV Compression',
     'Multiple compression on enterprise-value basis (cheaper for cap-structure reasons).',
     None),
    ('results_ev_fcf_leverage/screener.csv', 'EV/FCF Leverage',
     'EV/FCF compression + cap structure leverage; cheap on cash flow with debt working for shareholders.',
     None),
    ('results_52wh/screener.csv', '52-Week High',
     'Within X% of 52-week high with fundamentals okay — momentum + quality.',
     None),
    ('results_flat_inflection/screener.csv', 'Flat + Inflection',
     'Flat-trending share price with fundamentals inflecting up — pre-rerate setups.',
     None),
    ('results_volasym/screener.csv', 'Vol Asymmetry',
     'Upside volatility > downside volatility — positive skew names.',
     None),
    ('pre_rerate_setups.csv', 'Segment Inflection',
     'A small, fast-growing revenue segment will (if growth persists) come to dominate consolidated results.',
     None),
    ('results_extras/screener.csv', 'Analyst & Insider Extras',
     'Composite of four forward-looking signals from yfinance analyst & insider feeds: '
     'upside-to-mean-target, % net insider buying (last 6m), broker-rating buy share, '
     'and average forward-quarter+forward-year consensus growth. Each signal is z-scored '
     'across the universe; missing signals contribute z=0 (median) rather than penalise.',
     None),
]

EXTRA_COLUMN_LABELS = {
    'upside_to_mean_target_pct': 'Upside to Target',
    'insider_net_pct_6m': 'Net Insider Buying (6m)',
    'consensus_buy_share_pct': 'Buy/Strong-Buy Share',
    'fwd_growth_avg_pct': 'Fwd Growth (Avg)',
    'extras_composite': 'Extras Composite',
    'n_signals': 'Signals',
}
COLUMN_LABELS.update(EXTRA_COLUMN_LABELS)


def build_creative_measures(wb):
    """One tab per creative measure. Each tab loads its CSV if present."""
    available = [(p, label, deck, cols) for p, label, deck, cols in CREATIVE_MEASURES
                 if Path(p).exists() and Path(p).stat().st_size > 50]
    if not available:
        return  # No creative measures landed yet

    ws = wb.create_sheet('Creative Measures Index')
    ws.sheet_view.showGridLines = False
    row = _draw_title_block(
        ws,
        kicker='Beyond Composites  ·  Eleven Specialised Screens',
        title='Creative Measures — Index',
        deck=('Each creative measure isolates a specific market pattern that the broad '
              'composite cannot capture: pure operating leverage, hidden segment '
              'inflection, multiple compression, capital-efficient compounders. '
              'Coverage depends on availability of quarterly income/cashflow/price '
              'history. Names without deep cached data are skipped.'),
    )
    row += 1
    # Index: list of measures with row counts
    idx = []
    for p, label, deck, _cols in CREATIVE_MEASURES:
        rows = 0
        if Path(p).exists():
            try:
                rows = sum(1 for _ in open(p)) - 1
            except Exception:
                rows = 0
        status = 'covered' if rows > 0 else ('present, 0 rows' if Path(p).exists() else 'pending deep fetch')
        idx.append({'measure': label, 'rows': rows, 'status': status, 'path': p})
    _write_df(ws, pd.DataFrame(idx), ['measure','rows','status','path'], start_row=row)
    _autosize(ws, ['measure','rows','status','path'])

    # Pre-load yfinance info cache once, then look up by ticker
    yf_cache = Path('.cache/yf')
    def _enrich_with_company_info(df: pd.DataFrame) -> pd.DataFrame:
        """Prepend company / sector / industry / country columns by joining
        on the per-ticker info_metrics parquet. Tickers without a parquet get
        blanks. Idempotent — if columns already exist, they're refreshed."""
        if df.empty or 'ticker' not in df.columns:
            return df
        rows = []
        for tkr in df['ticker'].astype(str).tolist():
            safe = ''.join(c if c.isalnum() or c in '-_' else '_' for c in tkr)
            p = yf_cache / f'{safe}__info_metrics.parquet'
            entry = {'ticker': tkr, 'company': '', 'sector': '', 'industry': '', 'country': ''}
            if p.exists():
                try:
                    d = pd.read_parquet(p)
                    if not d.empty:
                        row = d.iloc[0]
                        name = row.get('longName') or row.get('shortName') or ''
                        entry['company'] = str(name)[:42]
                        entry['sector'] = str(row.get('sector') or '')
                        entry['industry'] = str(row.get('industry') or '')
                        entry['country'] = str(row.get('country') or '')
                except Exception:
                    pass
            rows.append(entry)
        info_df = pd.DataFrame(rows)
        # Drop any pre-existing copies so the join overrides
        for c in ('company','sector','industry','country'):
            if c in df.columns:
                df = df.drop(columns=[c])
        return info_df.merge(df, on='ticker', how='left')

    # One tab per available measure
    for p, label, deck, cols in available:
        try:
            df = pd.read_csv(p)
        except Exception:
            continue
        if df.empty:
            continue
        df = _enrich_with_company_info(df)
        # Name the sheet "CM · <Label>" — Excel forbids /,\\,?,*,[,] in titles
        clean = label.replace('/', '-').replace('\\', '-').replace('?', '').replace('*', '').replace('[','(').replace(']',')')
        sheet_name = f'CM · {clean}'[:31]
        ws = wb.create_sheet(sheet_name)
        ws.sheet_view.showGridLines = False
        r = _draw_title_block(ws,
                              kicker='Creative Measure',
                              title=label,
                              deck=deck)
        r += 1
        # If columns specified, use them (where present); else use the dataframe's columns.
        # Always prepend the human-readable id columns when present.
        front = [c for c in ('ticker','company','sector','industry','country') if c in df.columns]
        if cols:
            cols = [c for c in cols if c in df.columns]
            rest_cols = [c for c in cols if c not in front]
        else:
            rest_cols = [c for c in df.columns if c not in front]
        cols = front + rest_cols
        # Caption above the table: N rows, top-N selector
        n_total = len(df)
        top_n = min(50, n_total)
        if n_total > top_n:
            caption = f'Top {top_n} of {n_total:,} candidates, ranked by the screen-specific score.'
        else:
            caption = f'All {n_total:,} surviving candidates.'
        c = ws.cell(row=r, column=1, value=caption)
        c.font = CAPTION_FONT
        c.alignment = ALIGN_LEFT
        ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=min(len(cols), 10))
        r += 2
        # Truncation of longName/name happens inside _write_df via ellipsis
        end_row = _write_df(ws, df.head(top_n), cols, start_row=r)
        _autosize(ws, cols)
        # Freeze after the front columns so ticker+company stay visible while scrolling
        ws.freeze_panes = chr(ord('A') + len(front)) + str(r + 1)
        _add_footer(
            ws, end_row,
            source=('Source: Yahoo Finance via yfinance · SEC EDGAR XBRL companyfacts · '
                    'computed locally. See README for methodology.'))


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
    # Header row with booktabs heavy-top + thin-bottom rule
    for c, h in enumerate(['Column','Meaning'], 1):
        cell = ws.cell(row=row, column=c, value=h)
        cell.font = TABLE_HEAD_FT
        cell.fill = WARM_FILL
        cell.alignment = ALIGN_CTR
        cell.border = Border(top=RULE_HEAVY, bottom=RULE_HEAD)
    row += 1
    for i, (k, v) in enumerate(rows):
        is_last = (i == len(rows) - 1)
        c1 = ws.cell(row=row, column=1, value=k); c1.font = BODY_BOLD
        c1.alignment = Alignment(horizontal='left', vertical='top', indent=0)
        c2 = ws.cell(row=row, column=2, value=v); c2.font = BODY_FONT
        c2.alignment = Alignment(wrap_text=True, vertical='top', indent=0)
        c1.fill = WARM_FILL; c2.fill = WARM_FILL
        if is_last:
            c1.border = Border(bottom=RULE_BOTTOM)
            c2.border = Border(bottom=RULE_BOTTOM)
        ws.row_dimensions[row].height = 26
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
    build_creative_measures(wb)
    build_glossary(wb)

    wb.save(WB_PATH)
    print(f'Wrote {WB_PATH} with {len(wb.sheetnames)} sheets:')
    for s in wb.sheetnames:
        print(f'  - {s}')


if __name__ == '__main__':
    main()
