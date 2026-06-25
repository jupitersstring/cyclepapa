"""Style-subcategory workbook — top picks within each fund style + size bucket.

Companion to universe_analysis.xlsx. Where that book ranks the FULL universe
flat, this one slices the picks BY the style of fund originating the signal.

For each macro_style and sub_group:
  - Top positions (by total holders-within-style + max pct_book within style)
  - New initiations (section 3) within the style
  - Material adds (section 4) within the style
  - Concentration leaders (pct_book ≥ 5%)
  - Insider clusters overlapping the style
  - Activist intensity within the style

Cross-cut: per style, surface by SIZE bucket (nano/micro/small/mid/large).
"""
import os, sqlite3
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

DB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "cyclepapa.db")
OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "style_analysis.xlsx")

# Harvard aesthetic — match universe_analysis.xlsx
CRIMSON = "A51C30"
CRIMSON_DARK = "7A0E25"
CRIMSON_PALE = "F4E4E7"
CHARCOAL = "1C1C1C"
PAPER = "FBF9F4"

TNR = "Times New Roman"
HDR_FONT = Font(name=TNR, bold=True, color="FFFFFF", size=11)
HDR_FILL = PatternFill("solid", fgColor=CRIMSON)
TITLE_FONT = Font(name=TNR, bold=True, size=20, color=CRIMSON)
SUBTITLE_FONT = Font(name=TNR, italic=True, size=11, color=CHARCOAL)
SECTION_FONT = Font(name=TNR, bold=True, size=12, color=CRIMSON_DARK)
BODY_FONT = Font(name=TNR, size=11, color=CHARCOAL)
NUM_FONT = Font(name=TNR, size=11, color=CHARCOAL)

THIN = Side(border_style="thin", color="D9C8C8")
THICK = Side(border_style="medium", color=CRIMSON)
BOX = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
BOTTOM_THICK = Border(left=THIN, right=THIN, top=THIN, bottom=THICK)
ALT_FILL = PatternFill("solid", fgColor=PAPER)
HDR_HEIGHT = 28
BODY_HEIGHT = 20
NUMFMT_USD = '"$"#,##0'
NUMFMT_PCT = '0.0"%"'
NUMFMT_NUM = '#,##0.0'

ETFs = {"SPY","QQQ","VOO","IWM","IEF","IEFA","EFA","EEM","BIL","IVV","XBI","HYG",
        "GLD","SLV","TLT","XLE","XLF","XLK","XLY","XLP","XLU","XLI","XLV","XLB","XLRE",
        "ARKK","JNK","LQD","TIP","AGG","BND","VEA","VWO","SHY"}
MEGA = {"AMZN","MSFT","NVDA","META","GOOGL","GOOG","AAPL","TSLA","BRK-A","BRK-B"}

def write_header(ws, cols, row=1):
    ws.row_dimensions[row].height = HDR_HEIGHT
    for i, h in enumerate(cols, 1):
        c = ws.cell(row=row, column=i, value=h)
        c.font = HDR_FONT
        c.fill = HDR_FILL
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        c.border = BOTTOM_THICK

def write_rows(ws, rows, start_row=2, alt_shading=True):
    for i, row in enumerate(rows):
        ws.row_dimensions[start_row+i].height = BODY_HEIGHT
        for j, v in enumerate(row, 1):
            c = ws.cell(row=start_row+i, column=j, value=v)
            c.font = NUM_FONT if isinstance(v, (int, float)) else BODY_FONT
            c.alignment = Alignment(vertical="center",
                                     horizontal="right" if isinstance(v, (int, float)) else "left")
            if alt_shading and i % 2 == 1:
                c.fill = ALT_FILL
            c.border = BOX

def style_ticker_col(ws, start_row, n_rows, col=1):
    for r in range(start_row, start_row+n_rows):
        c = ws.cell(row=r, column=col)
        c.font = Font(name=TNR, bold=True, size=11, color=CRIMSON_DARK)
        c.alignment = Alignment(horizontal="center", vertical="center")

def autosize(ws):
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
        ws.column_dimensions[letter].width = max(10, min(max_len + 3, 44))

def title_bar(ws, title, note, ncols):
    ws.sheet_view.showGridLines = False
    ws.row_dimensions[1].height = 34
    ws.merge_cells(f"A1:{get_column_letter(ncols)}1")
    t = ws.cell(row=1, column=1, value=title.upper())
    t.font = Font(name=TNR, bold=True, size=16, color=CRIMSON)
    t.alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[2].height = 22
    ws.merge_cells(f"A2:{get_column_letter(ncols)}2")
    n = ws.cell(row=2, column=1, value=note)
    n.font = SUBTITLE_FONT
    n.alignment = Alignment(horizontal="center", vertical="center")

# Safe sheet name (Excel: ≤31 chars, no /\?*[])
def safe_sheet_name(name):
    s = name.replace("/", "-").replace("\\", "-").replace("?","").replace("*","")
    s = s.replace("[","(").replace("]",")")
    return s[:31]

def style_macro_list(conn):
    out = []
    for r in conn.execute("""SELECT macro_style, COUNT(*) c FROM fund_style
        WHERE macro_style IS NOT NULL
        GROUP BY macro_style ORDER BY 2 DESC"""):
        out.append((r[0], r[1]))
    return out

def sheet_readme(wb, conn):
    ws = wb.create_sheet("README", 0)
    ws.sheet_view.showGridLines = False
    ws.row_dimensions[1].height = 48
    ws.merge_cells("A1:H1")
    c = ws.cell(row=1, column=1, value="CYCLEPAPA · Style Analysis")
    c.font = TITLE_FONT
    c.alignment = Alignment(horizontal="center", vertical="center")

    ws.row_dimensions[2].height = 22
    ws.merge_cells("A2:H2")
    c = ws.cell(row=2, column=1, value="Top picks within each fund style and size bucket")
    c.font = SUBTITLE_FONT
    c.alignment = Alignment(horizontal="center", vertical="center")

    ws.row_dimensions[3].height = 8
    for col in range(1, 9):
        ws.cell(row=3, column=col, value="").fill = PatternFill("solid", fgColor=CRIMSON)

    styles = style_macro_list(conn)
    rows = [
        ("",), ("HOW IT'S ORGANIZED",),
        ("Overview     — universe-wide style summary across the 445-fund universe.",),
        ("Per-Style    — one sheet per macro_style with: top picks, S3 new, S4 adds,",),
        ("               concentration leaders, activist intensity, insider overlap.",),
        ("Size Cross   — within each style, names broken out by size bucket.",),
        ("Sub-group    — top picks within sub_group tiers (e.g. US Activist Tier 1).",),
        ("",), ("STYLES IN UNIVERSE",),
    ]
    for s, c_count in styles:
        rows.append((f"  {s:<40} {c_count} funds",))
    rows += [
        ("",), ("METHODOLOGY",),
        ("All measures are computed from primary data (13F-HR, 13D/G, Form 4,",),
        ("XLSX-classifications). No memory-based picks. Score formula:",),
        ("",),
        ("  score = log(n_funds) × 2",),
        ("        + 3.0 × s3_new_init",),
        ("        + 1.5 × s4_material_add",),
        ("        + 2.0 × s1_top_pick",),
        ("        + 0.5 × activist_max_pct",),
        ("        + 0.6 × max(pct_book)              ← NEW: position concentration",),
        ("        + 1.5 × n_funds_5pct_book          ← NEW: cluster of concentration",),
        ("        + cluster_step(n_insiders)",),
        ("        + log(form4_buys + 1) × 2",),
        ("        - log(form4_sells + 1) × 1.5      ← NEW: insider sell counter-signal",),
        ("        + micro_bonus",),
        ("",),
    ]
    for i, r in enumerate(rows, 5):
        c = ws.cell(row=i, column=1, value=r[0])
        ws.row_dimensions[i].height = BODY_HEIGHT
        if not r[0].strip():
            continue
        if r[0].isupper() or r[0].split()[0].isupper():
            c.font = SECTION_FONT
        else:
            c.font = BODY_FONT
    ws.column_dimensions["A"].width = 80
    for col in "BCDEFGH":
        ws.column_dimensions[col].width = 2

def write_style_sheet(wb, conn, macro_style, sheet_name):
    ws = wb.create_sheet(sheet_name)
    style_funds = [r[0] for r in conn.execute(
        "SELECT fund FROM fund_style WHERE macro_style = ?", (macro_style,))]
    title_bar(ws, macro_style,
              f"Top picks held by funds in this style ({len(style_funds)} funds). "
              f"All cross-referenced with universe-level unified_signal.",
              13)
    # Section 1: top picks
    row = 4
    ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=13)
    c = ws.cell(row=row, column=1, value="TOP PICKS (most-held within this style)")
    c.font = SECTION_FONT
    ws.row_dimensions[row].height = 26
    row += 1
    hdr = ["Ticker","Style Holders","%Book Max","%Book ≥5% Funds","S3 New","S4 Add",
           "S1 Top","Mcap $M","Bucket","Activist %","Insider $M","F4 Buys $M","Name"]
    write_header(ws, hdr, row=row)
    row += 1

    ph = ",".join("?" * len(style_funds))
    sql = f"""
        SELECT h.ticker,
               COUNT(DISTINCT h.fund) AS holders,
               MAX(h.pct_book) AS max_pb,
               SUM(CASE WHEN h.pct_book >= 5 THEN 1 ELSE 0 END) AS n5,
               (SELECT COUNT(DISTINCT fp.fund) FROM fund_positions fp
                 WHERE fp.ticker = h.ticker AND fp.section = 3
                   AND fp.fund IN ({ph})) AS s3_st,
               (SELECT COUNT(DISTINCT fp.fund) FROM fund_positions fp
                 WHERE fp.ticker = h.ticker AND fp.section = 4
                   AND fp.fund IN ({ph})) AS s4_st,
               (SELECT COUNT(DISTINCT fp.fund) FROM fund_positions fp
                 WHERE fp.ticker = h.ticker AND fp.section = 1
                   AND fp.fund IN ({ph})) AS s1_st,
               us.mcap_m, us.mcap_bucket,
               us.activist_max_pct, us.insider_cluster_dollars_m, us.form4_buy_usd_m,
               tm.name
        FROM fund_13f_holdings h
        LEFT JOIN unified_signal us ON us.ticker = h.ticker
        LEFT JOIN ticker_meta tm ON tm.ticker = h.ticker
        WHERE h.fund IN ({ph}) AND h.ticker IS NOT NULL
        GROUP BY h.ticker
        ORDER BY holders DESC, max_pb DESC
        LIMIT 60
    """
    rows = list(conn.execute(sql, style_funds * 4))
    out = []
    for r in rows:
        if r[0] in ETFs: continue
        out.append([r[0], r[1], round(r[2] or 0, 1), r[3] or 0,
                    r[4] or 0, r[5] or 0, r[6] or 0,
                    r[7] or "", r[8] or "",
                    round(r[9] or 0, 1),
                    round(r[10] or 0, 1) if r[10] else "",
                    round(r[11] or 0, 1) if r[11] else "",
                    (r[12] or "")[:35]])
        if len(out) >= 35: break
    write_rows(ws, out, start_row=row)
    style_ticker_col(ws, row, len(out))
    for ridx in range(row, row+len(out)):
        ws.cell(row=ridx, column=3).number_format = NUMFMT_PCT
        ws.cell(row=ridx, column=8).number_format = NUMFMT_USD
        ws.cell(row=ridx, column=10).number_format = NUMFMT_PCT
        ws.cell(row=ridx, column=11).number_format = NUMFMT_NUM
        ws.cell(row=ridx, column=12).number_format = NUMFMT_NUM
    row += len(out) + 2

    # Section 2: New initiations (S3) within style
    ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=13)
    c = ws.cell(row=row, column=1, value="NEW MAJOR POSITIONS (Section 3) WITHIN THIS STYLE")
    c.font = SECTION_FONT
    ws.row_dimensions[row].height = 26
    row += 1
    hdr2 = ["Ticker","Style S3 #","Universe 13F","%Book Max","Mcap $M","Bucket","Activist %","Name"]
    write_header(ws, hdr2, row=row)
    row += 1
    rows = list(conn.execute(f"""
        SELECT fp.ticker, COUNT(DISTINCT fp.fund) AS n,
               us.smart_money_n, us.max_pct_book, us.mcap_m, us.mcap_bucket,
               us.activist_max_pct, tm.name
        FROM fund_positions fp
        LEFT JOIN unified_signal us ON us.ticker = fp.ticker
        LEFT JOIN ticker_meta tm ON tm.ticker = fp.ticker
        WHERE fp.fund IN ({ph}) AND fp.section = 3 AND fp.ticker IS NOT NULL
        GROUP BY fp.ticker ORDER BY n DESC LIMIT 25""", style_funds))
    out = [[r[0], r[1], r[2] or 0, round(r[3] or 0, 1),
            r[4] or "", r[5] or "", round(r[6] or 0, 1),
            (r[7] or "")[:35]] for r in rows if r[0] not in ETFs]
    write_rows(ws, out, start_row=row)
    style_ticker_col(ws, row, len(out))
    for ridx in range(row, row+len(out)):
        ws.cell(row=ridx, column=4).number_format = NUMFMT_PCT
        ws.cell(row=ridx, column=5).number_format = NUMFMT_USD
        ws.cell(row=ridx, column=7).number_format = NUMFMT_PCT
    row += len(out) + 2

    # Section 3: Material adds (S4) within style
    ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=13)
    c = ws.cell(row=row, column=1, value="MATERIAL ADDS (Section 4) WITHIN THIS STYLE")
    c.font = SECTION_FONT
    ws.row_dimensions[row].height = 26
    row += 1
    write_header(ws, hdr2, row=row)
    row += 1
    rows = list(conn.execute(f"""
        SELECT fp.ticker, COUNT(DISTINCT fp.fund) AS n,
               us.smart_money_n, us.max_pct_book, us.mcap_m, us.mcap_bucket,
               us.activist_max_pct, tm.name
        FROM fund_positions fp
        LEFT JOIN unified_signal us ON us.ticker = fp.ticker
        LEFT JOIN ticker_meta tm ON tm.ticker = fp.ticker
        WHERE fp.fund IN ({ph}) AND fp.section = 4 AND fp.ticker IS NOT NULL
        GROUP BY fp.ticker ORDER BY n DESC LIMIT 25""", style_funds))
    out = [[r[0], r[1], r[2] or 0, round(r[3] or 0, 1),
            r[4] or "", r[5] or "", round(r[6] or 0, 1),
            (r[7] or "")[:35]] for r in rows if r[0] not in ETFs]
    write_rows(ws, out, start_row=row)
    style_ticker_col(ws, row, len(out))
    for ridx in range(row, row+len(out)):
        ws.cell(row=ridx, column=4).number_format = NUMFMT_PCT
        ws.cell(row=ridx, column=5).number_format = NUMFMT_USD
        ws.cell(row=ridx, column=7).number_format = NUMFMT_PCT
    row += len(out) + 2

    # Section 4: Concentration leaders (max pct_book within style)
    ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=13)
    c = ws.cell(row=row, column=1, value="CONCENTRATION LEADERS — single-fund pct_book ≥5% within this style")
    c.font = SECTION_FONT
    ws.row_dimensions[row].height = 26
    row += 1
    hdr3 = ["Ticker","Fund","%Book","Universe 13F","Mcap $M","Bucket","Name"]
    write_header(ws, hdr3, row=row)
    row += 1
    rows = list(conn.execute(f"""
        SELECT h.ticker, h.fund, h.pct_book, us.smart_money_n, us.mcap_m, us.mcap_bucket, tm.name
        FROM fund_13f_holdings h
        LEFT JOIN unified_signal us ON us.ticker = h.ticker
        LEFT JOIN ticker_meta tm ON tm.ticker = h.ticker
        WHERE h.fund IN ({ph}) AND h.pct_book >= 5 AND h.pct_book <= 100
        ORDER BY h.pct_book DESC LIMIT 25""", style_funds))
    out = [[r[0], r[1][:32], round(r[2] or 0, 1), r[3] or 0,
            r[4] or "", r[5] or "", (r[6] or "")[:32]]
           for r in rows if r[0] not in ETFs]
    write_rows(ws, out, start_row=row)
    style_ticker_col(ws, row, len(out))
    for ridx in range(row, row+len(out)):
        ws.cell(row=ridx, column=3).number_format = NUMFMT_PCT
        ws.cell(row=ridx, column=5).number_format = NUMFMT_USD
    row += len(out) + 2

    # Section 5: Size cross-cut — best name in each size bucket within style
    ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=13)
    c = ws.cell(row=row, column=1, value="BY SIZE BUCKET — top names within this style by mcap class")
    c.font = SECTION_FONT
    ws.row_dimensions[row].height = 26
    row += 1
    hdr4 = ["Bucket","Ticker","Style Holders","%Book Max","Mcap $M","S3","S4","Activist %","Name"]
    write_header(ws, hdr4, row=row)
    row += 1

    out = []
    for bucket in ["nano","micro","small","mid","large"]:
        # top 5 names in this style at this size bucket
        rows = list(conn.execute(f"""
            SELECT h.ticker, COUNT(DISTINCT h.fund) AS holders,
                   MAX(h.pct_book) AS max_pb,
                   us.mcap_m,
                   (SELECT COUNT(DISTINCT fp.fund) FROM fund_positions fp
                    WHERE fp.ticker = h.ticker AND fp.section = 3
                      AND fp.fund IN ({ph})) AS s3_st,
                   (SELECT COUNT(DISTINCT fp.fund) FROM fund_positions fp
                    WHERE fp.ticker = h.ticker AND fp.section = 4
                      AND fp.fund IN ({ph})) AS s4_st,
                   us.activist_max_pct, tm.name
            FROM fund_13f_holdings h
            JOIN unified_signal us ON us.ticker = h.ticker
            LEFT JOIN ticker_meta tm ON tm.ticker = h.ticker
            WHERE h.fund IN ({ph}) AND us.mcap_bucket = ?
              AND h.ticker NOT IN ({','.join('?'*len(ETFs))})
            GROUP BY h.ticker
            ORDER BY (holders * 2 + max_pb * 0.5) DESC LIMIT 5""",
            style_funds + style_funds + style_funds + [bucket] + list(ETFs)))
        for r in rows:
            out.append([bucket, r[0], r[1], round(r[2] or 0, 1),
                        r[3] or "", r[4] or 0, r[5] or 0,
                        round(r[6] or 0, 1), (r[7] or "")[:32]])
    write_rows(ws, out, start_row=row)
    style_ticker_col(ws, row, len(out), col=2)
    for ridx in range(row, row+len(out)):
        ws.cell(row=ridx, column=4).number_format = NUMFMT_PCT
        ws.cell(row=ridx, column=5).number_format = NUMFMT_USD
        ws.cell(row=ridx, column=8).number_format = NUMFMT_PCT
    ws.freeze_panes = "B6"
    autosize(ws)

def sheet_overview(wb, conn):
    """Universe-wide: top names by style, all styles side-by-side."""
    ws = wb.create_sheet("Overview by Style")
    title_bar(ws, "Universe Overview by Style",
              "For each macro_style, top 10 names by within-style holder count. Click into per-style sheets for full detail.",
              13)
    row = 4
    for ms, count in style_macro_list(conn):
        ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=13)
        c = ws.cell(row=row, column=1, value=f"{ms.upper()}  ({count} funds)")
        c.font = SECTION_FONT
        c.fill = PatternFill("solid", fgColor=CRIMSON_PALE)
        ws.row_dimensions[row].height = 24
        row += 1
        hdr = ["Ticker","Style Holders","%Book Max","%Book≥5%","S3","S4","Mcap $M","Bucket","Activist %","Cluster $M","F4 Buy $M","Sell $M","Name"]
        write_header(ws, hdr, row=row)
        row += 1
        style_funds = [r[0] for r in conn.execute(
            "SELECT fund FROM fund_style WHERE macro_style = ?", (ms,))]
        if not style_funds: continue
        ph = ",".join("?" * len(style_funds))
        rows = list(conn.execute(f"""
            SELECT h.ticker, COUNT(DISTINCT h.fund) AS holders,
                   MAX(h.pct_book), SUM(CASE WHEN h.pct_book>=5 THEN 1 ELSE 0 END),
                   (SELECT COUNT(DISTINCT fp.fund) FROM fund_positions fp
                    WHERE fp.ticker = h.ticker AND fp.section = 3 AND fp.fund IN ({ph})),
                   (SELECT COUNT(DISTINCT fp.fund) FROM fund_positions fp
                    WHERE fp.ticker = h.ticker AND fp.section = 4 AND fp.fund IN ({ph})),
                   us.mcap_m, us.mcap_bucket, us.activist_max_pct,
                   us.insider_cluster_dollars_m, us.form4_buy_usd_m, us.form4_sell_usd_m,
                   tm.name
            FROM fund_13f_holdings h
            LEFT JOIN unified_signal us ON us.ticker = h.ticker
            LEFT JOIN ticker_meta tm ON tm.ticker = h.ticker
            WHERE h.fund IN ({ph}) AND h.ticker IS NOT NULL
            GROUP BY h.ticker
            ORDER BY holders DESC LIMIT 12""", style_funds * 3))
        out = []
        for r in rows:
            if r[0] in ETFs: continue
            out.append([r[0], r[1], round(r[2] or 0, 1), r[3] or 0, r[4] or 0, r[5] or 0,
                        r[6] or "", r[7] or "", round(r[8] or 0, 1),
                        round(r[9] or 0, 1) if r[9] else "",
                        round(r[10] or 0, 1) if r[10] else "",
                        round(r[11] or 0, 1) if r[11] else "",
                        (r[12] or "")[:30]])
            if len(out) >= 10: break
        write_rows(ws, out, start_row=row)
        style_ticker_col(ws, row, len(out))
        for ridx in range(row, row+len(out)):
            ws.cell(row=ridx, column=3).number_format = NUMFMT_PCT
            ws.cell(row=ridx, column=7).number_format = NUMFMT_USD
            ws.cell(row=ridx, column=9).number_format = NUMFMT_PCT
            ws.cell(row=ridx, column=10).number_format = NUMFMT_NUM
            ws.cell(row=ridx, column=11).number_format = NUMFMT_NUM
            ws.cell(row=ridx, column=12).number_format = NUMFMT_NUM
        row += len(out) + 2
    autosize(ws)

def sheet_subgroup_focus(wb, conn):
    """One sheet per high-value sub_group tier."""
    # Choose the most interesting sub-groups (those with >= 5 funds)
    subgroups = list(conn.execute("""SELECT macro_style, sub_group, COUNT(*) c
        FROM fund_style WHERE sub_group IS NOT NULL AND macro_style IS NOT NULL
        GROUP BY macro_style, sub_group
        HAVING c >= 5 ORDER BY macro_style, c DESC"""))

    ws = wb.create_sheet("Sub-Group Tiers")
    title_bar(ws, "Sub-Group Tier Picks",
              "Within each macro style, top picks by sub_group (Tier-1/Tier-2/specialist tier). Only sub-groups with ≥5 funds shown.",
              11)
    row = 4
    last_macro = None
    for ms, sg, n in subgroups:
        if ms != last_macro:
            ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=11)
            c = ws.cell(row=row, column=1, value=f"━━ {ms.upper()} ━━")
            c.font = Font(name=TNR, bold=True, size=13, color=CRIMSON)
            c.alignment = Alignment(horizontal="left", vertical="center")
            ws.row_dimensions[row].height = 28
            row += 1
            last_macro = ms
        ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=11)
        c = ws.cell(row=row, column=1, value=f"  {sg}  ({n} funds)")
        c.font = SECTION_FONT
        c.fill = PatternFill("solid", fgColor=CRIMSON_PALE)
        ws.row_dimensions[row].height = 22
        row += 1
        hdr = ["Ticker","Sub Holders","%Book Max","Mcap $M","Bucket","S3","S4","Activist %","Cluster $M","F4 $M","Name"]
        write_header(ws, hdr, row=row)
        row += 1
        sg_funds = [r[0] for r in conn.execute(
            "SELECT fund FROM fund_style WHERE sub_group = ?", (sg,))]
        if not sg_funds: continue
        ph = ",".join("?" * len(sg_funds))
        rows = list(conn.execute(f"""
            SELECT h.ticker, COUNT(DISTINCT h.fund) holders, MAX(h.pct_book) max_pb,
                   us.mcap_m, us.mcap_bucket,
                   (SELECT COUNT(DISTINCT fp.fund) FROM fund_positions fp
                    WHERE fp.ticker=h.ticker AND fp.section=3 AND fp.fund IN ({ph})),
                   (SELECT COUNT(DISTINCT fp.fund) FROM fund_positions fp
                    WHERE fp.ticker=h.ticker AND fp.section=4 AND fp.fund IN ({ph})),
                   us.activist_max_pct, us.insider_cluster_dollars_m, us.form4_buy_usd_m,
                   tm.name
            FROM fund_13f_holdings h
            LEFT JOIN unified_signal us ON us.ticker = h.ticker
            LEFT JOIN ticker_meta tm ON tm.ticker = h.ticker
            WHERE h.fund IN ({ph}) AND h.ticker IS NOT NULL
            GROUP BY h.ticker
            ORDER BY (holders * 2 + (COALESCE(max_pb,0)) * 0.5) DESC LIMIT 10
        """, sg_funds * 3))
        out = []
        for r in rows:
            if r[0] in ETFs: continue
            out.append([r[0], r[1], round(r[2] or 0, 1),
                        r[3] or "", r[4] or "", r[5] or 0, r[6] or 0,
                        round(r[7] or 0, 1),
                        round(r[8] or 0, 1) if r[8] else "",
                        round(r[9] or 0, 1) if r[9] else "",
                        (r[10] or "")[:32]])
            if len(out) >= 8: break
        write_rows(ws, out, start_row=row)
        style_ticker_col(ws, row, len(out))
        for ridx in range(row, row+len(out)):
            ws.cell(row=ridx, column=3).number_format = NUMFMT_PCT
            ws.cell(row=ridx, column=4).number_format = NUMFMT_USD
            ws.cell(row=ridx, column=8).number_format = NUMFMT_PCT
            ws.cell(row=ridx, column=9).number_format = NUMFMT_NUM
            ws.cell(row=ridx, column=10).number_format = NUMFMT_NUM
        row += len(out) + 2
    autosize(ws)

def main():
    conn = sqlite3.connect(DB)
    wb = openpyxl.Workbook()
    if "Sheet" in wb.sheetnames:
        wb.remove(wb["Sheet"])

    sheet_readme(wb, conn)
    sheet_overview(wb, conn)
    sheet_subgroup_focus(wb, conn)
    for ms, _ in style_macro_list(conn):
        sn = safe_sheet_name(ms)
        write_style_sheet(wb, conn, ms, sn)

    wb.save(OUT)
    print(f"wrote {OUT}")
    print(f"sheets: {wb.sheetnames}")

if __name__ == "__main__":
    main()
