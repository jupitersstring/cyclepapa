"""
Build the Harvard-aesthetic FIP-Asymmetry workbook.
Tabs:
  1. Cover  — title, scope, methodology blurb
  2. Glossary — every metric explained
  3. Composite — top N per region by composite v2 score
  4-7. Leg leaders — UPSIDE / FLOOR / QUALITY / STEALTH per region
  8. Cheap multiples — per-region top by P/B, EV/EBITDA, EV/Sales, FCF yield
  9. Growth & margin — per-region top by rev_growth, rev_growth_inflection, op_margin, ROE
  10. Drift audit — names that entered/exited top 25 in the all-fresh refetch
  11. Full universe — every v2 survivor with all columns
"""
import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side, NamedStyle
from openpyxl.utils import get_column_letter
from openpyxl.styles.differential import DifferentialStyle
from openpyxl.formatting.rule import Rule

# --- Harvard palette ---
CRIMSON = "8C1515"      # Harvard crimson (the deeper, official one)
CRIMSON_LIGHT = "B85450"
IVORY = "F8F4E6"        # warm parchment
WARM_GRAY = "6B7280"
CHARCOAL = "1F2937"
CREAM = "FAF9F6"

SERIF = "Cambria"

REGION_MAP = {
    'United States': 'North America', 'Canada': 'North America',
    'United Kingdom': 'Europe', 'France': 'Europe', 'Germany': 'Europe',
    'Italy': 'Europe', 'Spain': 'Europe', 'Netherlands': 'Europe',
    'Switzerland': 'Europe', 'Sweden': 'Europe', 'Norway': 'Europe',
    'Denmark': 'Europe', 'Finland': 'Europe', 'Ireland': 'Europe',
    'Austria': 'Europe', 'Belgium': 'Europe', 'Portugal': 'Europe',
    'Greece': 'Europe', 'Luxembourg': 'Europe',
    'Japan': 'Asia Developed', 'Australia': 'Asia Developed',
    'Singapore': 'Asia Developed', 'Hong Kong': 'Asia Developed',
    'Taiwan': 'Asia Developed', 'South Korea': 'Asia Developed',
    'Israel': 'Asia Developed', 'New Zealand': 'Asia Developed',
    'China': 'Asia Emerging', 'India': 'Asia Emerging',
    'Indonesia': 'Asia Emerging', 'Thailand': 'Asia Emerging',
    'Malaysia': 'Asia Emerging', 'Philippines': 'Asia Emerging',
    'Vietnam': 'Asia Emerging',
    'Brazil': 'Latin America', 'Mexico': 'Latin America',
    'Chile': 'Latin America', 'Argentina': 'Latin America',
    'Saudi Arabia': 'MENA + Africa', 'United Arab Emirates': 'MENA + Africa',
    'Turkey': 'MENA + Africa', 'Egypt': 'MENA + Africa',
    'South Africa': 'MENA + Africa', 'Qatar': 'MENA + Africa',
}

REGIONS = ['North America', 'Europe', 'Asia Developed', 'Asia Emerging',
           'Latin America', 'MENA + Africa']

df = pd.read_csv('/home/user/cyclepapa/asymmetric_v2_universe_audit.csv')
df['region'] = df['country'].map(REGION_MAP).fillna('Other')

# Convenience renames so the workbook reads cleanly
df = df.rename(columns={
    'pb_use': 'P/B', 'ev_ebitda_use': 'EV/EBITDA', 'rev_growth_use': 'Rev Growth',
    'ev_sales': 'EV/Sales', 'rev_growth_inflection': 'Rev Inflection',
    'fcf_yield': 'FCF Yield', 'op_margin_ex': 'Op Margin', 'roe_ex': 'ROE',
    'sec_rel_ev': 'Sector-Rel EV', 'asym_v2_score': 'v2 Score',
    'fip_d': 'FIP D (252d)', 'fip_w': 'FIP W (52w)', 'fip_m': 'FIP M (24m)',
    'pret_d': '12m Return', 'pret_m': '24m Return',
    'upside': 'Upside Score', 'floor': 'Floor Score',
    'quality': 'Quality Score', 'stealth': 'Stealth Score',
    'sector_used': 'Sector', 'market_cap_bucket': 'Cap',
    'roic_proxy': 'ROIC Proxy', 'debt_to_equity': 'Debt/Equity',
    'eps_q_growth': 'EPS Q Growth',
    'rs_fip_d': 'RS-FIP D', 'rs_fip_w': 'RS-FIP W',
    'rs_fip_w_inflection': 'RS-FIP W Inflect', 'rs_pret_d': 'RS 12m Return',
    'fip_w_minus_d': 'FIP W − D Gap',
    'asym_d_last': 'Volasym D', 'asym_w_last': 'Volasym W',
    'asym_m_last': 'Volasym M', 'asym_w_ma_last': 'Volasym W MA',
    'asym_m_ma_last': 'Volasym M MA', 'asym_w_above_ma': 'Volasym W > MA',
    'asym_m_above_ma': 'Volasym M > MA',
    'asym_w_roc5': 'Volasym W RoC5', 'asym_m_roc3': 'Volasym M RoC3',
    'asym_m_dist50': 'Volasym M Dist-50',
    'nonzero_pct': 'Nonzero %', 'realized_vol_60d': '60d Vol',
    'last_price': 'Last Price', 'market_cap': 'Market Cap',
})

# Express percent-style columns as percentage points (21.5 not 0.215) so the
# Harvard format `#,##0.0;(#,##0.0);"–"` renders without a trailing % sign.
PCT_COLS = ['12m Return', '24m Return', 'RS 12m Return',
            'Rev Growth', 'Rev Inflection', 'Op Margin', 'ROE',
            'FCF Yield', 'EPS Q Growth', 'Nonzero %', '60d Vol',
            'Volasym M Dist-50']
for c in PCT_COLS:
    if c in df.columns:
        df[c] = pd.to_numeric(df[c], errors='coerce') * 100

# --- Styling helpers ---
thin = Side(border_style="thin", color="D6D3D1")
border = Border(left=thin, right=thin, top=thin, bottom=thin)
center = Alignment(horizontal="center", vertical="center", wrap_text=True)
left   = Alignment(horizontal="left",   vertical="center", wrap_text=True)
right  = Alignment(horizontal="right",  vertical="center")
header_fill = PatternFill("solid", fgColor=CRIMSON)
header_font = Font(name=SERIF, bold=True, color="FFFFFF", size=11)
title_font  = Font(name=SERIF, bold=True, color="FFFFFF", size=18)
subtitle_font = Font(name=SERIF, italic=True, color="FFFFFF", size=11)
section_fill = PatternFill("solid", fgColor=CRIMSON_LIGHT)
section_font = Font(name=SERIF, bold=True, color="FFFFFF", size=12)
region_fill = PatternFill("solid", fgColor=IVORY)
region_font = Font(name=SERIF, bold=True, color=CRIMSON, size=11)
body_font   = Font(name=SERIF, size=10, color=CHARCOAL)
body_alt_fill = PatternFill("solid", fgColor=CREAM)
body_white = PatternFill("solid", fgColor="FFFFFF")

# Harvard financial-statement convention: parens for negatives, en-dash for
# zero/empty, accounting separators, right-aligned numbers, no % sign.
EN_DASH = "–"
FMT_RAW   = '#,##0;(#,##0);"–"'         # raw $ (market cap, EV)
FMT_PP    = '#,##0.0;(#,##0.0);"–"'     # percentage points, 1dp
FMT_RATIO = '#,##0.00;(#,##0.00);"–"'   # P/B, EV/EBITDA, scores, FIP, prices

NUM_FMT = {
    'Market Cap': FMT_RAW,
    '12m Return': FMT_PP, '24m Return': FMT_PP, 'RS 12m Return': FMT_PP,
    'Rev Growth': FMT_PP, 'Rev Inflection': FMT_PP,
    'Op Margin': FMT_PP, 'ROE': FMT_PP, 'FCF Yield': FMT_PP,
    'EPS Q Growth': FMT_PP, 'Nonzero %': FMT_PP, '60d Vol': FMT_PP,
    'Volasym D': FMT_PP, 'Volasym W': FMT_PP, 'Volasym M': FMT_PP,
    'Volasym W MA': FMT_PP, 'Volasym M MA': FMT_PP,
    'Volasym M Dist-50': FMT_PP,
    'FIP D (252d)': FMT_RATIO, 'FIP W (52w)': FMT_RATIO, 'FIP M (24m)': FMT_RATIO,
    'RS-FIP D': FMT_RATIO, 'RS-FIP W': FMT_RATIO, 'RS-FIP W Inflect': FMT_RATIO,
    'FIP W − D Gap': FMT_RATIO,
    'Volasym W RoC5': FMT_RATIO, 'Volasym M RoC3': FMT_RATIO,
    'P/B': FMT_RATIO, 'EV/EBITDA': FMT_RATIO, 'EV/Sales': FMT_RATIO,
    'ROIC Proxy': FMT_RATIO, 'Sector-Rel EV': FMT_RATIO,
    'Debt/Equity': FMT_RATIO, 'Last Price': FMT_RATIO,
    'v2 Score': FMT_RATIO, 'Upside Score': FMT_RATIO, 'Floor Score': FMT_RATIO,
    'Quality Score': FMT_RATIO, 'Stealth Score': FMT_RATIO,
}

def render_table(ws, df_sub, start_row, title, cols):
    """Render a section title row + a styled table starting at start_row.
       Returns the row immediately after the table."""
    ncol = len(cols)
    # Section title
    ws.merge_cells(start_row=start_row, start_column=1, end_row=start_row, end_column=ncol)
    cell = ws.cell(row=start_row, column=1, value=title)
    cell.font = section_font
    cell.alignment = left
    cell.fill = section_fill
    ws.row_dimensions[start_row].height = 22
    # Header
    hr = start_row + 1
    for j, c in enumerate(cols, start=1):
        cell = ws.cell(row=hr, column=j, value=c)
        cell.font = header_font; cell.fill = header_fill
        cell.alignment = center; cell.border = border
    ws.row_dimensions[hr].height = 28
    # Body
    for i, (_, row) in enumerate(df_sub[cols].iterrows()):
        r = hr + 1 + i
        fill = body_alt_fill if i % 2 else body_white
        for j, c in enumerate(cols, start=1):
            v = row[c]
            is_num = c in NUM_FMT
            if is_num:
                if pd.isna(v):
                    cell = ws.cell(row=r, column=j, value=EN_DASH)
                else:
                    cell = ws.cell(row=r, column=j, value=float(v))
                    cell.number_format = NUM_FMT[c]
                cell.alignment = right
            else:
                cell = ws.cell(row=r, column=j,
                               value=(v if pd.notna(v) else EN_DASH))
                cell.alignment = left
            cell.font = body_font
            cell.fill = fill
            cell.border = border
    end_row = hr + len(df_sub)
    return end_row + 2  # leave a gap before next section

def set_widths(ws, cols, widths):
    for i, w in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(i)].width = w

# --- Build workbook ---
wb = Workbook()

# 1. Cover
ws = wb.active; ws.title = "Cover"
ws.sheet_view.showGridLines = False
ws.row_dimensions[1].height = 8
ws.merge_cells('A2:H2')
ws['A2'] = "FIP–Asymmetry Workbook"
ws['A2'].font = Font(name=SERIF, bold=True, color="FFFFFF", size=28)
ws['A2'].fill = header_fill
ws['A2'].alignment = Alignment(horizontal="center", vertical="center")
ws.row_dimensions[2].height = 64
ws.merge_cells('A3:H3')
ws['A3'] = "Continuous-Information Momentum × Multi-Metric Asymmetry × Sector-Relative"
ws['A3'].font = Font(name=SERIF, italic=True, color="FFFFFF", size=12)
ws['A3'].fill = header_fill
ws['A3'].alignment = Alignment(horizontal="center", vertical="center")
ws.row_dimensions[3].height = 24

intro = [
    "",
    "PURPOSE",
    "This workbook ranks the entire global universe of mid + large + small caps "
    "(plus US micro) by an asymmetric-opportunity composite built from the "
    "Frog-in-the-Pan (Da/Gurun/Warachka 2014) continuous-information signal, "
    "valuation floor across multiple metrics, fundamental catalyst, and capital-"
    "efficiency quality. All fundamentals are fetched fresh; no cached values "
    "are used in the ranking.",
    "",
    "SCOPE",
    f"• Universe: {len(df)} v2 survivors out of 2,321 unique tickers scanned",
    f"• OHLC cache: 7,176 tickers spanning 44 countries",
    f"• 365 pre-filter candidates passed FIP+liquidity gate; 62 cleared v2 gates",
    "",
    "METHODOLOGY (high level)",
    "1. FIP smoothness: daily + weekly FIP both ≤ −0.08 / −0.10 (formation 252d, "
    "skip last 21d per the paper).",
    "2. Real liquidity: 60d realized vol ≥ 0.008, ≥65% non-zero return days, "
    "price ≥ $1 (suppresses artificial smoothness in illiquid micros).",
    "3. Floor (multi-metric, ANY): P/B ≤ 2 OR EV/EBITDA ≤ 12 OR EV/Sales ≤ 3 OR "
    "FCF yield ≥ 3%.",
    "4. Catalyst (multi-confirmation): rev growth ≥ 5% AND rev inflection ≥ 0 "
    "AND (op margin ≥ 5% OR quarterly EPS growth ≥ 0).",
    "5. Survival: Debt/Equity ≤ 250.",
    "6. Composite v2 score = √(Upside × Floor) × (0.7 + 0.3·Quality) × "
    "(0.8 + 0.2·Stealth).",
    "",
    "REGIONAL TAXONOMY",
    "North America, Europe, Asia Developed (JP/AU/SG/HK/TW/KR/IL/NZ), "
    "Asia Emerging (CN/IN/ID/TH/MY/PH/VN), Latin America, MENA + Africa.",
    "",
    "READING NOTES",
    "Each leg-leaders tab shows the top picks per region by a single dimension. "
    "Single-metric tabs surface specialists. The Composite tab is the headline "
    "ranking used for risk-adjusted allocation; the leg-leader tabs surface "
    "concentrated bets when an investor prefers to weight one dimension.",
]
for i, txt in enumerate(intro, start=5):
    ws.merge_cells(start_row=i, start_column=1, end_row=i, end_column=8)
    cell = ws.cell(row=i, column=1, value=txt)
    if txt in ("PURPOSE","SCOPE","METHODOLOGY (high level)","REGIONAL TAXONOMY","READING NOTES"):
        cell.font = Font(name=SERIF, bold=True, color=CRIMSON, size=12)
    else:
        cell.font = Font(name=SERIF, size=11, color=CHARCOAL)
    cell.alignment = Alignment(horizontal="left", vertical="top", wrap_text=True)
    ws.row_dimensions[i].height = 30 if len(txt) > 80 else 18
set_widths(ws, range(8), [16]*8)
ws.sheet_properties.tabColor = CRIMSON

# 2. Glossary
ws = wb.create_sheet("Glossary"); ws.sheet_view.showGridLines = False
ws.sheet_properties.tabColor = CRIMSON
glossary = [
    ("Term", "Definition"),
    ("FIP (Frog in the Pan)", "Da/Gurun/Warachka 2014. FIP = sgn(PRET) × (%neg − %pos) over the 252-day formation period, with the most recent 21 trading days skipped per the paper. A more-negative FIP for a winner means returns arrived as many small positive days (continuous information) rather than a few large jumps (discrete information) — predictive of stronger momentum continuation."),
    ("FIP_d / FIP_w / FIP_m", "Daily, weekly (52w), and monthly (24m) FIP scores. Smoothness across timeframes confirms the continuous-information setup."),
    ("12m Return (pret_d)", "Cumulative return over the 252-day formation period (skip-last-21d)."),
    ("Pre-filter", "FIP_d ≤ −0.08 AND FIP_w ≤ −0.10 AND winner (return > 0) AND real liquidity (≥65% non-zero return days, 60d vol ≥ 0.008, price ≥ $1)."),
    ("Floor (multi-metric)", "Downside protection. A name passes the floor gate if ANY of P/B ≤ 2.0, EV/EBITDA ≤ 12, EV/Sales ≤ 3, or FCF yield ≥ 3%."),
    ("Catalyst", "Upside trigger. Requires rev growth ≥ 5% AND rev growth inflection ≥ 0 AND (operating margin ≥ 5% OR latest quarterly EPS growth ≥ 0)."),
    ("Survival", "Debt/Equity ≤ 250 — knocks out balance-sheet-impaired names."),
    ("Sector-Rel EV", "EV/EBITDA divided by the sector median. <1 = cheaper than peers, >1 = premium."),
    ("ROIC Proxy", "Operating Margin × (1 / EV/Sales). Approximates return on invested capital independent of accounting leverage."),
    ("Upside Score", "Percentile rank composite of revenue growth and revenue growth inflection."),
    ("Floor Score", "Average percentile rank of low P/B, low EV/EBITDA, low EV/Sales, high FCF yield, and low sector-relative EV."),
    ("Quality Score", "Percentile rank of ROIC proxy. Captures capital efficiency."),
    ("Stealth Score", "Percentile rank of FIP_d + FIP_w (more-negative = better). Measures continuous-information depth."),
    ("v2 Composite", "√(Upside × Floor) × (0.7 + 0.3·Quality) × (0.8 + 0.2·Stealth). Geometric on the two dimensions an investor cannot trade off, multiplied by quality and stealth lifts."),
]
for i, (k, v) in enumerate(glossary, start=2):
    is_header = (i == 2)
    ws.cell(row=i, column=1, value=k).font = (header_font if is_header else
                                              Font(name=SERIF, bold=True, color=CRIMSON, size=11))
    ws.cell(row=i, column=2, value=v).font = Font(name=SERIF, size=10, color=CHARCOAL)
    for c in (1,2):
        cell = ws.cell(row=i, column=c)
        cell.alignment = Alignment(horizontal="left", vertical="top", wrap_text=True)
        cell.fill = header_fill if is_header else (body_alt_fill if i % 2 else body_white)
        cell.border = border
    ws.row_dimensions[i].height = 18 if is_header else max(30, 14*max(1, len(v)//90))
ws.row_dimensions[2].height = 26
set_widths(ws, range(2), [28, 100])

# 3. Composite top-10 per region
def composite_tab():
    ws = wb.create_sheet("Composite by Region")
    ws.sheet_view.showGridLines = False
    ws.sheet_properties.tabColor = CRIMSON
    ws.merge_cells('A1:L1')
    ws['A1'] = "Top picks by composite v2 asymmetry score, per region"
    ws['A1'].font = title_font; ws['A1'].fill = header_fill
    ws['A1'].alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[1].height = 32
    cols = ['symbol', 'name', 'country', 'Cap', 'Sector', '12m Return',
            'Rev Growth', 'Rev Inflection', 'P/B', 'EV/EBITDA', 'EV/Sales', 'v2 Score']
    set_widths(ws, range(len(cols)), [10,30,16,10,18,11,11,11,9,11,10,10])
    cur = 3
    for region in REGIONS:
        sub = df[df['region']==region].sort_values('v2 Score', ascending=False).head(10)
        if sub.empty: continue
        cur = render_table(ws, sub, cur, f"{region}  —  top {len(sub)} by Composite Score", cols)
composite_tab()

# 4-7. Leg-leader tabs
def leg_tab(title, score_col, cols_extra):
    ws = wb.create_sheet(title)
    ws.sheet_view.showGridLines = False
    ws.sheet_properties.tabColor = CRIMSON
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=len(cols_extra)+5)
    ws['A1'] = f"Top picks by {score_col}, per region"
    ws['A1'].font = title_font; ws['A1'].fill = header_fill
    ws['A1'].alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[1].height = 32
    cols = ['symbol','name','country','Cap','Sector', score_col] + cols_extra + ['v2 Score']
    widths = [10,28,16,10,18] + [13]*(len(cols)-5)
    set_widths(ws, range(len(cols)), widths)
    cur = 3
    for region in REGIONS:
        sub = df[df['region']==region].sort_values(score_col, ascending=False).head(10)
        if sub.empty: continue
        cur = render_table(ws, sub, cur, f"{region}  —  top {len(sub)} by {score_col}", cols)

leg_tab("Upside Leaders",  'Upside Score',  ['Rev Growth','Rev Inflection','Op Margin','EPS Q Growth'])
leg_tab("Floor Leaders",   'Floor Score',   ['P/B','EV/EBITDA','EV/Sales','FCF Yield','Sector-Rel EV'])
leg_tab("Quality Leaders", 'Quality Score', ['ROIC Proxy','Op Margin','ROE','Debt/Equity'])
leg_tab("Stealth Leaders", 'Stealth Score', ['FIP D (252d)','FIP W (52w)','FIP M (24m)'])

# 8. Cheap multiples tab — per region, top by each cheap metric
def multi_metric_tab(title, specs):
    ws = wb.create_sheet(title); ws.sheet_view.showGridLines = False
    ws.sheet_properties.tabColor = CRIMSON
    ws.merge_cells('A1:L1')
    ws['A1'] = f"{title}: per-region leaders on each individual metric"
    ws['A1'].font = title_font; ws['A1'].fill = header_fill
    ws['A1'].alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[1].height = 32
    cols = ['symbol','name','country','Cap','Sector'] + [s[0] for s in specs] + ['v2 Score']
    widths = [10,28,16,10,18] + [12]*(len(specs)) + [10]
    set_widths(ws, range(len(cols)), widths)
    cur = 3
    for region in REGIONS:
        region_df = df[df['region']==region]
        if region_df.empty: continue
        ws.merge_cells(start_row=cur, start_column=1, end_row=cur, end_column=len(cols))
        rc = ws.cell(row=cur, column=1, value=f"{region}  —  region top-10 per metric")
        rc.font = region_font; rc.fill = region_fill; rc.alignment = left
        cur += 1
        for metric, ascending in specs:
            mask = region_df[metric].notna() & (region_df[metric] > -1e9)
            if not mask.any(): continue
            sub = region_df[mask].sort_values(metric, ascending=ascending).head(10)
            if sub.empty: continue
            cur = render_table(ws, sub, cur,
                               f"  → {region}: top {len(sub)} by {metric} "
                               f"({'lowest' if ascending else 'highest'})",
                               cols)

multi_metric_tab(
    "Cheap Multiples",
    [('P/B', True), ('EV/EBITDA', True), ('EV/Sales', True),
     ('FCF Yield', False), ('Sector-Rel EV', True)],
)
multi_metric_tab(
    "Growth & Margin",
    [('Rev Growth', False), ('Rev Inflection', False),
     ('Op Margin', False), ('ROE', False), ('EPS Q Growth', False)],
)
# FIP smoothness by timeframe (most-negative wins => ascending sort)
multi_metric_tab(
    "FIP by Timeframe",
    [('FIP D (252d)', True), ('FIP W (52w)', True), ('FIP M (24m)', True),
     ('FIP W − D Gap', True)],
)
# RS-FIP — same FIP measure computed on stock-vs-SPX excess returns
multi_metric_tab(
    "RS-FIP Leaders",
    [('RS-FIP D', True), ('RS-FIP W', True), ('RS-FIP W Inflect', True),
     ('RS 12m Return', False)],
)
# Volatility asymmetry (malikmck Pine, Qullamaggie filters)
multi_metric_tab(
    "Volatility Asymmetry",
    [('Volasym D', False), ('Volasym W', False), ('Volasym M', False),
     ('Volasym W RoC5', False), ('Volasym M RoC3', False),
     ('Volasym M Dist-50', False)],
)
# Survival + balance-sheet quality
multi_metric_tab(
    "Survival & Catalyst",
    [('Debt/Equity', True), ('EPS Q Growth', False),
     ('Rev Inflection', False), ('FCF Yield', False)],
)
# Trend / period returns
multi_metric_tab(
    "Period Returns",
    [('12m Return', False), ('24m Return', False), ('RS 12m Return', False)],
)
# Liquidity quality
multi_metric_tab(
    "Liquidity Quality",
    [('Nonzero %', False), ('60d Vol', False), ('Last Price', False)],
)

# 9. Drift audit
ws = wb.create_sheet("Drift Audit"); ws.sheet_view.showGridLines = False
ws.sheet_properties.tabColor = CRIMSON
ws.merge_cells('A1:H1'); ws['A1'] = "Audit: ranking is across the entire universe, no cache shortcuts"
ws['A1'].font = title_font; ws['A1'].fill = header_fill
ws['A1'].alignment = Alignment(horizontal="center"); ws.row_dimensions[1].height = 32

audit_rows = [
    ("Universe input CSVs", "7 regional `leading_*` runs combined; 3,277 raw rows; 2,321 unique tickers across 44 countries."),
    ("OHLC cache", "7,176 tickers. 100% of pre-filter universe had OHLC."),
    ("FIP computed", "2,250 of 2,307 (post pref-share filter) had ≥300 trading days."),
    ("Pre-filter survivors", "365 (smooth FIP_d ≤ −0.08, smooth FIP_w ≤ −0.10, winner, ≥65% non-zero days, vol ≥ 0.008, price ≥ $1)."),
    ("Fresh fundamentals", "ALL 365 pre-filter survivors re-fetched from yfinance — no cached P/B, EV/EBITDA, or rev growth used in final ranking."),
    ("Median P/B drift", "0.147. 91 rows shifted by > 0.5."),
    ("Median EV/EBITDA drift", "0.847. 88 rows shifted by > 2.0."),
    ("Final v2 survivors", f"{len(df)} after gates re-applied on fresh data."),
]
for i, (k, v) in enumerate(audit_rows, start=3):
    ws.cell(row=i, column=1, value=k).font = Font(name=SERIF, bold=True, color=CRIMSON, size=11)
    ws.merge_cells(start_row=i, start_column=2, end_row=i, end_column=8)
    ws.cell(row=i, column=2, value=v).font = Font(name=SERIF, size=10, color=CHARCOAL)
    for c in (1,2):
        cell = ws.cell(row=i, column=c)
        cell.alignment = Alignment(horizontal="left", vertical="top", wrap_text=True)
        cell.fill = body_alt_fill if i % 2 else body_white
        cell.border = border
    ws.row_dimensions[i].height = max(28, 14*max(1, len(v)//95))

# Churn vs prior committed
churn_rows = [
    ("Names that ENTERED top 25 with all-fresh refetch",
     "BP.L, DINO (HF Sinclair), HPE, NUE, SANM, SNX, BOTJ, 6806.T (Hirose)"),
    ("Names that EXITED top 25 with all-fresh refetch",
     "4042.T (Tosoh), 54E.F, BWFG, CII, CLST (Catalyst Bancorp), CTRE, FMBM, LQDT"),
    ("Implication",
     "Stale cached fundamentals materially affected the ordering. The all-fresh refetch is the right rank to use."),
]
start_churn = len(audit_rows) + 5
for i, (k, v) in enumerate(churn_rows, start=start_churn):
    ws.cell(row=i, column=1, value=k).font = Font(name=SERIF, bold=True, color=CRIMSON, size=11)
    ws.merge_cells(start_row=i, start_column=2, end_row=i, end_column=8)
    ws.cell(row=i, column=2, value=v).font = Font(name=SERIF, size=10, color=CHARCOAL)
    for c in (1,2):
        cell = ws.cell(row=i, column=c)
        cell.alignment = Alignment(horizontal="left", vertical="top", wrap_text=True)
        cell.fill = body_alt_fill if i % 2 else body_white
        cell.border = border
    ws.row_dimensions[i].height = max(28, 14*max(1, len(v)//95))
set_widths(ws, range(8), [32]+[14]*7)

# 10. Full universe — every v2 survivor
ws = wb.create_sheet("All Survivors"); ws.sheet_view.showGridLines = False
ws.sheet_properties.tabColor = CRIMSON
ws.merge_cells('A1:AE1')
ws['A1'] = f"All {len(df)} v2 asymmetric survivors, ranked by composite score"
ws['A1'].font = title_font; ws['A1'].fill = header_fill
ws['A1'].alignment = Alignment(horizontal="center", vertical="center")
ws.row_dimensions[1].height = 32
cols_all = ['symbol','name','region','country','Cap','Sector',
            '12m Return','FIP D (252d)','FIP W (52w)','FIP M (24m)',
            'RS-FIP D','RS-FIP W','Volasym W','Volasym M',
            'Rev Growth','Rev Inflection','EPS Q Growth','Op Margin','ROE',
            'ROIC Proxy','Debt/Equity',
            'P/B','EV/EBITDA','EV/Sales','FCF Yield','Sector-Rel EV',
            'Upside Score','Floor Score','Quality Score','Stealth Score','v2 Score']
widths_all = [10,28,15,15,10,17, 11,11,11,11, 10,10,11,11,
              11,11,12,10,9, 11,11, 9,11,10,11,12, 12,11,12,12,10]
set_widths(ws, range(len(cols_all)), widths_all)
render_table(ws, df.sort_values('v2 Score', ascending=False), 3,
             "Full ranking (sorted by composite v2 score)", cols_all)

# Save
out = '/home/user/cyclepapa/FIP_Asymmetry_Workbook.xlsx'
wb.save(out)
print(f"Saved {out}")
print(f"Tabs: {[s.title for s in wb.worksheets]}")
