"""Post-process an .xlsx into the Harvard house aesthetic.

Single typeface (Cambria) at a single size (10pt), black & white only,
no fills, whitespace-driven: a bold header row with a thin black rule
beneath it, muted grey for secondary text, gridlines off, header frozen.

This is applied to workbooks built via plain pandas.to_excel (which
default to Calibri 11 with no structure) so they match the hand-built
Harvard workbooks. For builders that already render through
build_harvard_workbook's helpers this pass is a harmless no-op-ish
normaliser (it only enforces font/size/fill, never touches values or
number formats).
"""
from __future__ import annotations
import sys

from openpyxl import load_workbook
from openpyxl.styles import Font, PatternFill, Border, Side, Alignment
from openpyxl.utils import get_column_letter


FONT_NAME = "Cambria"
FONT_SIZE = 10
INK = "FF000000"
MUTED = "FF707070"
RULE = "FFB0B0B0"

_NO_FILL = PatternFill(fill_type=None)
_HEADER_RULE = Border(bottom=Side(style="thin", color=INK))
_ROW_RULE = Border(bottom=Side(style="thin", color=RULE))


def _is_number(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def apply_harvard_style(path: str,
                        header_row: int = 1,
                        muted_text_cols: tuple = (),
                        freeze_header: bool = True,
                        zebra_rule: bool = False) -> None:
    """Rewrite every sheet of `path` into the Harvard aesthetic in place."""
    wb = load_workbook(path)
    for ws in wb.worksheets:
        ws.sheet_view.showGridLines = False
        max_row = ws.max_row
        max_col = ws.max_column
        if max_row == 0 or max_col == 0:
            continue

        # Track content width per column for auto-sizing
        col_width = {c: 6 for c in range(1, max_col + 1)}

        for row in ws.iter_rows(min_row=1, max_row=max_row,
                                min_col=1, max_col=max_col):
            for cell in row:
                r, c = cell.row, cell.column
                # Strip any fill
                cell.fill = _NO_FILL
                is_header = (r == header_row)
                if is_header:
                    cell.font = Font(name=FONT_NAME, size=FONT_SIZE,
                                     bold=True, color=INK)
                    cell.alignment = Alignment(
                        horizontal="left" if isinstance(cell.value, str) else "right",
                        vertical="center", wrap_text=False)
                    cell.border = _HEADER_RULE
                else:
                    muted = c in muted_text_cols
                    cell.font = Font(name=FONT_NAME, size=FONT_SIZE,
                                     color=MUTED if muted else INK)
                    cell.alignment = Alignment(
                        horizontal="right" if _is_number(cell.value) else "left",
                        vertical="center", wrap_text=False)
                    if zebra_rule:
                        cell.border = _ROW_RULE
                # Width tracking
                if cell.value is not None:
                    ln = len(str(cell.value))
                    if ln > col_width[c]:
                        col_width[c] = ln

        # Apply column widths (cap so prose columns don't explode the sheet)
        for c, w in col_width.items():
            ws.column_dimensions[get_column_letter(c)].width = min(max(w + 2, 8), 60)

        if freeze_header and max_row > header_row:
            ws.freeze_panes = ws.cell(row=header_row + 1, column=1).coordinate

    wb.save(path)


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("path")
    ap.add_argument("--zebra", action="store_true",
                    help="add a thin grey rule under every data row")
    args = ap.parse_args()
    apply_harvard_style(args.path, zebra_rule=args.zebra)
    print(f"styled {args.path}", file=sys.stderr)


if __name__ == "__main__":
    main()
