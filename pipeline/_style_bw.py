"""Shared Harvard-academic monochrome aesthetic for cyclepapa workbooks.

Design grammar:
  - All black on white. No fills, no shading, no colors.
  - Single body font size (10pt Times New Roman) — like an HBR article.
  - Headers in SMALL CAPS, bold, same size as body.
  - Thin black bottom rule under headers (FT/HBR style).
  - Title 14pt bold; subtitle 10pt italic.
  - Section headers: 11pt bold, small caps.
  - Generous row heights (18 pt) for breathability.
  - Right-align numbers, left-align text.
  - Hairline gray rules between rows (D9D9D9), only where helpful.
  - No gridlines visible.
"""
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

TNR = "Times New Roman"

# Single body size — restraint
SIZE_BODY = 10
SIZE_HDR = 10
SIZE_SECTION = 11
SIZE_SUBTITLE = 10
SIZE_TITLE = 14

BLACK = "000000"
LIGHT_GREY = "BFBFBF"
HAIRLINE = "D9D9D9"

# Fonts
TITLE_FONT     = Font(name=TNR, bold=True, size=SIZE_TITLE, color=BLACK)
SUBTITLE_FONT  = Font(name=TNR, italic=True, size=SIZE_SUBTITLE, color=BLACK)
SECTION_FONT   = Font(name=TNR, bold=True, size=SIZE_SECTION, color=BLACK)
HDR_FONT       = Font(name=TNR, bold=True, size=SIZE_HDR, color=BLACK)
BODY_FONT      = Font(name=TNR, size=SIZE_BODY, color=BLACK)
BODY_ITALIC    = Font(name=TNR, italic=True, size=SIZE_BODY, color=BLACK)
TICKER_FONT    = Font(name=TNR, bold=True, size=SIZE_BODY, color=BLACK)
MONO_FONT      = Font(name="Consolas", size=SIZE_BODY, color=BLACK)

# Borders
THIN_BLK       = Side(border_style="thin", color=BLACK)
HAIRLINE_SIDE  = Side(border_style="hair", color=HAIRLINE)
NO_SIDE        = Side(border_style=None)

# header row: black 0.5pt under, nothing above/sides
HDR_BORDER     = Border(top=NO_SIDE, bottom=THIN_BLK, left=NO_SIDE, right=NO_SIDE)
# body row: hairline gray bottom only
ROW_BORDER     = Border(top=NO_SIDE, bottom=HAIRLINE_SIDE, left=NO_SIDE, right=NO_SIDE)
TITLE_BORDER   = Border(bottom=THIN_BLK, top=NO_SIDE, left=NO_SIDE, right=NO_SIDE)

NO_FILL = PatternFill(fill_type=None)

NUMFMT_USD  = '"$"#,##0'
NUMFMT_PCT  = '0.0"%"'
NUMFMT_NUM  = '#,##0.0'
NUMFMT_INT  = '#,##0'
NUMFMT_USD2 = '"$"#,##0.00'

HDR_HEIGHT = 22
BODY_HEIGHT = 18
TITLE_HEIGHT = 30

# ---------- helpers ----------
def write_title(ws, title, subtitle, ncols):
    """Title block at the top — title 14pt bold, subtitle italic, thin rule under."""
    ws.sheet_view.showGridLines = False
    ws.row_dimensions[1].height = TITLE_HEIGHT
    ws.merge_cells(f"A1:{get_column_letter(ncols)}1")
    t = ws.cell(row=1, column=1, value=title)
    t.font = TITLE_FONT
    t.alignment = Alignment(horizontal="left", vertical="center")
    ws.row_dimensions[2].height = 18
    ws.merge_cells(f"A2:{get_column_letter(ncols)}2")
    s = ws.cell(row=2, column=1, value=subtitle)
    s.font = SUBTITLE_FONT
    s.alignment = Alignment(horizontal="left", vertical="center")
    # thin black rule under title row 2
    for col in range(1, ncols + 1):
        ws.cell(row=2, column=col).border = Border(bottom=THIN_BLK, top=NO_SIDE, left=NO_SIDE, right=NO_SIDE)

def write_section_heading(ws, row, text, ncols):
    """Section heading: small caps, 11pt bold, hairline rule beneath."""
    ws.row_dimensions[row].height = 22
    ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=ncols)
    c = ws.cell(row=row, column=1, value=text.upper())
    c.font = SECTION_FONT
    c.alignment = Alignment(horizontal="left", vertical="bottom")

def write_table_header(ws, row, cols):
    ws.row_dimensions[row].height = HDR_HEIGHT
    for i, h in enumerate(cols, 1):
        c = ws.cell(row=row, column=i, value=h.upper())
        c.font = HDR_FONT
        c.alignment = Alignment(horizontal="right" if i > 1 else "left",
                                 vertical="bottom", wrap_text=False)
        c.border = HDR_BORDER

def write_table_rows(ws, rows, start_row, ticker_col=1, hairline=True):
    """Write rows. First column treated as ticker (bold, left). Rest right-aligned if numeric."""
    for i, row in enumerate(rows):
        ws.row_dimensions[start_row + i].height = BODY_HEIGHT
        for j, v in enumerate(row, 1):
            c = ws.cell(row=start_row + i, column=j, value=v)
            is_num = isinstance(v, (int, float))
            if j == ticker_col and isinstance(v, str):
                c.font = TICKER_FONT
                c.alignment = Alignment(horizontal="left", vertical="center")
            else:
                c.font = BODY_FONT
                c.alignment = Alignment(
                    horizontal="right" if is_num else "left",
                    vertical="center")
            if hairline:
                c.border = ROW_BORDER

def autosize(ws):
    """Column widths chosen for visual rhythm — content + 2."""
    max_col = ws.max_column or 1
    max_row = ws.max_row or 1
    for col_idx in range(1, max_col + 1):
        letter = get_column_letter(col_idx)
        max_len = 0
        for row_idx in range(1, max_row + 1):
            try:
                v = ws.cell(row=row_idx, column=col_idx).value
            except Exception:
                continue
            if v is not None:
                max_len = max(max_len, min(len(str(v)), 50))
        ws.column_dimensions[letter].width = max(8, min(max_len + 2.5, 42))

def set_default_font(wb):
    """Apply Times New Roman as the workbook default styles where possible."""
    for ws in wb.worksheets:
        ws.sheet_properties.tabColor = None
