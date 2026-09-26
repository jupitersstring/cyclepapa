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
import re
from openpyxl.utils import get_column_letter, column_index_from_string
from openpyxl.worksheet.properties import PageSetupProperties

TNR = "Times New Roman"

# Single body size — restraint
SIZE_BODY = 10
SIZE_HDR = 10
SIZE_SECTION = 11
SIZE_SUBTITLE = 10
SIZE_TITLE = 15

BLACK = "000000"
LIGHT_GREY = "BFBFBF"
HAIRLINE = "D9D9D9"
MUTED = "3F3F3F"
# Times-Lattice style guide: the ONLY two accent inks. Colour is data — lapis =
# good/improving, crimson = bad/deteriorating. Used ONLY as directional font
# colour on value cells (never fills, headings, or borders).
LAPIS = "061933"
CRIMSON = "7A0019"

def ink_for(value, higher_is_better=True):
    """Return LAPIS (good) / CRIMSON (bad) / None for a signed value."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    if v == 0:
        return None
    good = (v > 0) if higher_is_better else (v < 0)
    return LAPIS if good else CRIMSON

def color_directional(ws, first_row, last_row, cols, higher_is_better=True):
    """Colour the given 1-indexed columns lapis/crimson by the cell's sign, over
    [first_row, last_row]. cols may be one int or a list. Keeps Times + size."""
    if isinstance(cols, int):
        cols = [cols]
    for r in range(first_row, last_row + 1):
        for c in cols:
            cell = ws.cell(row=r, column=c)
            ink = ink_for(cell.value, higher_is_better)
            if ink:
                f = cell.font
                cell.font = Font(name=f.name or TNR, size=f.size or SIZE_BODY,
                                 bold=f.bold, italic=f.italic, color=ink)

def color_fixed(ws, first_row, last_row, cols, ink):
    """Colour non-blank/non-zero cells in `cols` a FIXED ink — for columns whose
    mere presence carries direction (a buy $ is always good=lapis, a sell $ always
    bad=crimson, regardless of sign)."""
    if isinstance(cols, int):
        cols = [cols]
    for r in range(first_row, last_row + 1):
        for c in cols:
            cell = ws.cell(row=r, column=c)
            v = cell.value
            if v in (None, "", "—", 0, 0.0):
                continue
            f = cell.font
            cell.font = Font(name=f.name or TNR, size=f.size or SIZE_BODY,
                             bold=f.bold, italic=f.italic, color=ink)

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

# Smart scale-aware money format — input is in millions.
#   < 1,000          → "$NNN M"     (i.e. < $1B)
#   1,000 – 999,999  → "$N.NN B"   (i.e. $1B to $1T)
#   >= 1,000,000     → "$N.N T"    (>= $1T)
NUMFMT_MCAP = '[>=1000000]"$"#,##0.0,,"T";[>=1000]"$"#,##0.0,"B";"$"#,##0" M"'
# Same idea for dollar quantities in $M (Form 4 $M, cluster $M, position $M):
NUMFMT_M_TO_B = '[>=1000]"$"#,##0.0,"B";"$"#,##0.0" M"'

# Times-Lattice density spec — rows are separated by a hairline, not padding, so
# heights are tight (the ledger-like feel). Was 22/18/30 (airy); now dense.
HDR_HEIGHT = 17
BODY_HEIGHT = 14
TITLE_HEIGHT = 26

# ---------- helpers ----------
MEDIUM_BLK = Side(border_style="medium", color=BLACK)

def write_title(ws, title, subtitle, ncols):
    """Plain heading: the title in normal body size (bold), over an italic-muted
    subline, closed by a black rule. No oversized nameplate, no ornament."""
    ws.sheet_view.showGridLines = False
    ws.row_dimensions[1].height = 16
    ws.merge_cells(f"A1:{get_column_letter(ncols)}1")
    t = ws.cell(row=1, column=1, value=str(title))
    t.font = Font(name=TNR, bold=True, size=SIZE_BODY + 1, color=BLACK)
    t.alignment = Alignment(horizontal="left", vertical="center")
    # rule directly under the title
    for col in range(1, ncols + 1):
        ws.cell(row=1, column=col).border = Border(bottom=THIN_BLK, top=NO_SIDE, left=NO_SIDE, right=NO_SIDE)
    ws.row_dimensions[2].height = 15
    ws.merge_cells(f"A2:{get_column_letter(ncols)}2")
    s = ws.cell(row=2, column=1, value=subtitle)
    s.font = SUBTITLE_FONT
    s.alignment = Alignment(horizontal="left", vertical="center")
    # thin black rule closing the masthead under the subline
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

def write_table_rows(ws, rows, start_row, ticker_col=1, hairline=True, blank="—"):
    """Write rows. First column treated as ticker (bold, left). Rest right-aligned if numeric.

    Empty cells (None or "") are rendered as a placeholder em-dash so every cell
    reads as intentional — "—" is the standard "not applicable / not available"
    mark. Genuine zeros are preserved as 0 (callers pass `x or 0` for counts).
    """
    for i, row in enumerate(rows):
        ws.row_dimensions[start_row + i].height = BODY_HEIGHT
        for j, v in enumerate(row, 1):
            is_blank = v is None or (isinstance(v, str) and v.strip() == "")
            display = blank if is_blank else v
            c = ws.cell(row=start_row + i, column=j, value=display)
            is_num = isinstance(v, (int, float))
            if j == ticker_col and isinstance(v, str) and not is_blank:
                c.font = TICKER_FONT
                c.alignment = Alignment(horizontal="left", vertical="center")
            else:
                c.font = BODY_FONT
                # numbers and placeholders right-align (placeholder usually
                # stands in for a numeric column); real text left-aligns.
                c.alignment = Alignment(
                    horizontal="right" if (is_num or is_blank) else "left",
                    vertical="center")
            if hairline:
                c.border = ROW_BORDER

def autosize(ws):
    """Column widths chosen for visual rhythm — content + 2. Text columns
    (names, sectors, descriptions) get enough width to show their full value;
    only genuinely long comma-lists are allowed to run to the wide cap."""
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
                max_len = max(max_len, min(len(str(v)), 80))
        ws.column_dimensions[letter].width = max(8, min(max_len + 2.5, 62))

# ---------- business descriptions ----------
# a "word." that does NOT end a sentence: corporate suffixes, country
# abbreviations, honorifics, initials ("Apple Inc. designs..." must not stop at
# "Apple Inc.", which the old first-". " rule did)
_ABBR = {"INC", "CORP", "CO", "LTD", "LLC", "LP", "L.P", "N.V", "NV", "S.A", "SA", "PLC",
         "AG", "SE", "S.P.A", "U.S", "U.K", "U.S.A", "NO", "ST", "MR", "MS", "MRS", "DR",
         "JR", "SR", "VS", "ETC", "E.G", "I.E", "APPROX", "INCL", "DEPT", "INT'L", "BHD",
         "PTY", "PTE", "KK", "OYJ", "ASA", "AB", "SPA", "B.V", "BV", "GMBH", "S.A.B", "C.V"}

def first_sentence(s):
    """The full first sentence of a business summary — never cut, never an
    ellipsis. A period ends the sentence only when the next word is
    capitalised and the word before it isn't an abbreviation or an initial."""
    if not s:
        return ""
    s = " ".join(str(s).split())
    for m in re.finditer(r"\.\s+", s):
        words = s[:m.start()].split()
        prev = words[-1].upper().rstrip(".").strip("(\"'") if words else ""
        nxt = s[m.end():m.end() + 1]
        if not nxt or not (nxt.isupper() or nxt.isdigit()):
            continue
        if prev in _ABBR or len(prev) <= 1 or (len(prev) <= 3 and "." in prev):
            continue
        return s[:m.start() + 1]
    return complete_text(s)             # one sentence, maybe cut at the source

def business_line(summary, *names):
    """The first sentence of a business summary without its '<Company Name>'
    lead-in (the sheet's Name column already says it), still a sentence:
      'Celsius Holdings, Inc. is a global enterprise…' -> 'A global enterprise…'
      'JBS N.V., together with its subsidiaries, engages in…' -> 'Engages in…'
      'Taiwan Semiconductor … Limited (TSMC) specializes in…' -> 'Specializes in…'
    When what follows the name doesn't stand alone ('Seagate …, headquartered
    in Dublin, Ireland, is…'; 'Alibaba …, a leading Chinese technology
    conglomerate, provides…') the whole sentence is kept. The old rule cut the
    name without its final period and left '. is a global enterprise…'."""
    s = first_sentence(summary)
    for nm in names:
        nm = " ".join(str(nm or "").split())
        if not s or not nm:
            continue
        for cand in (nm, nm.rstrip(".")):
            if not s.upper().startswith(cand.upper()):
                continue
            rest = s[len(cand):]
            rest = re.sub(r"^[\s.,;:]*(\([^)]{1,25}\)[\s,]*)?", "", rest)
            rest = re.sub(r"^((together|along) with|(operating )?through|and) its [\w\s-]{0,40}?"
                          r"(subsidiaries|affiliates|companies|businesses)[\s,]*", "", rest, flags=re.I)
            m = re.match(r"(is|are)\s+", rest)
            if m:
                rest = rest[m.end():]                 # "is a global…" -> "a global…"
            elif not re.match(r"[a-z]{3,}s\b", rest):  # "operates", "provides", "designs"
                return s
            if len(rest) < 25 or not rest[:1].isalpha():
                return s
            return rest[0].upper() + rest[1:]
    return s

def complete_text(s):
    """The full stored text. If an old store cut it (trailing '…', from the
    500-char Yahoo summaries FMP doesn't cover), end it at its last complete
    sentence rather than show a fragment."""
    s = " ".join(str(s or "").split())
    if s.endswith(("…", "...")):
        body = s.rstrip(".…").rstrip()
        ends = [m.start() for m in re.finditer(r"\.\s+(?=[A-Z0-9])", body)]
        if ends:
            return body[:ends[-1] + 1]
        # one long sentence cut mid-list (a fund summary FMP doesn't carry,
        # PSPFX): end at its last complete clause, not on a fragment
        cut = max(body.rfind("; "), body.rfind(", "))
        if cut > len(body) // 2:
            return body[:cut].rstrip(",;") + "."
    return s

_STATUS_PLAIN = [
    (r"^filer_13f_live", "13F filer: files 13F-HRs (was listed as a non-filer)"),
    (r"^filer_13f_other_name", "13F filer: its book is held under another roster name"),
    (r"^efts_resolved", "13F filer: CIK found by EDGAR full-text search"),
    (r"^v\d_verified", "13F filer: CIK verified"),
    (r"^manual_seed", "13F filer: CIK set by hand"),
    (r"^needs_verify", "CIK matched by name, not yet verified"),
    (r"^below_13f_threshold", "No 13F: under the $100M reporting threshold"),
    (r"^(\w\w)_non_filer_no_disclosure", "No 13F: non-US manager ({cc}), no public holdings"),
    (r"^(\w\w)_non_filer", "No 13F: non-US manager ({cc}); holdings from research notes"),
    (r"^non_equity_strategy", "No 13F: not a long-equity strategy"),
    (r"^individual", "No 13F: an individual (13D/G and Form 4 only)"),
    (r"^historical_13f_only", "Stopped filing 13Fs (history only)"),
    (r"^private_office", "No 13F: private family office"),
    (r"^meta_rollup", "Group heading, not a fund"),
    (r"^skip_no_aum", "Skipped: no assets reported"),
    (r"^gap_", "CIK uncertain"),
    (r"^rejected: CIK (\d+) is (.*)", "Wrong CIK rejected ({1} belongs to {2})"),
]
_CC = {"uk": "UK", "es": "Spain", "jp": "Japan", "ca": "Canada", "au": "Australia", "fr": "France", "za": "South Africa",
       "sg": "Singapore", "hk": "Hong Kong", "de": "Germany", "ch": "Switzerland"}

def plain_status(code):
    """Resolver status code -> plain English, the code kept in brackets."""
    code = (code or "").strip()
    if not code:
        return "13F filer (added from its filings)"
    for pat, txt in _STATUS_PLAIN:
        m = re.match(pat, code)
        if m:
            g = m.groups()
            out = txt.replace("{cc}", _CC.get(g[0], g[0].upper()) if g else "")
            if len(g) >= 2:
                out = out.replace("{1}", g[0]).replace("{2}", g[1])
            return out if code.startswith("rejected") else f"{out} [{code}]"
    return code

def add_grouped_contents(ws, guide, sheetnames, start_row=None):
    """A reading guide on the README: sheets grouped by the question they
    answer, each a clickable link with one line on what it is for. Any sheet
    the guide doesn't name is listed at the end, so none goes missing."""
    row = start_row or (ws.max_row or 1) + 2
    write_section_heading(ws, row, "Contents — sheets grouped by the question they answer (click to open)", 2)
    row += 1
    link_font = Font(name=TNR, size=SIZE_BODY, color=BLACK, underline="single")
    named = set()
    for group, items in guide:
        items = [(n, d) for n, d in items if n in sheetnames]
        if not items:
            continue
        c = ws.cell(row=row, column=1, value=group)
        c.font = SECTION_FONT
        row += 1
        for name, desc in items:
            named.add(name)
            c = ws.cell(row=row, column=1, value=f"{name} — {desc}")
            c.hyperlink = f"#'{name}'!A1"
            c.font = link_font
            c.alignment = Alignment(horizontal="left", vertical="top", wrap_text=True)
            ws.row_dimensions[row].height = 16 if len(name) + len(desc) < 110 else 30
            row += 1
        row += 1
    rest = [n for n in sheetnames if n not in named and n != ws.title]
    if rest:
        c = ws.cell(row=row, column=1, value="Other sheets")
        c.font = SECTION_FONT
        row += 1
        for name in rest:
            c = ws.cell(row=row, column=1, value=name)
            c.hyperlink = f"#'{name}'!A1"
            c.font = link_font
            row += 1
    return row

# ---------- valuation multiples on every ticker table ----------
VALUATION_COLS = ("EV/EBITDA", "P/E", "P/B", "P/TB")
_VAL_FMT = {"EV/EBITDA": '0.0"x"', "P/E": '0.0"x"', "P/B": '0.00"x"', "P/TB": '0.00"x"'}
_VAL_DP = {"EV/EBITDA": 1, "P/E": 1, "P/B": 2, "P/TB": 2}

_SEC_LABEL = {"etf": "fund", "warrant": "warrant", "unit": "unit", "right": "right",
              "preferred": "pref", "note": "note", "delisted": "delisted"}

def valuation_lookup(conn):
    """ticker -> {EV/EBITDA, P/E, P/B, P/TB}: the multiple where it is
    meaningful, otherwise the REASON it isn't, so a cell never reads as missing
    data when the data is saying something:
      loss · neg EBITDA · net cash · neg equity · neg TBV   (the company's numbers)
      fund · warrant · unit · right · pref · note · delisted (not an operating stock)
    "—" is left only where no source has the figure. EV/EBITDA needs positive EV
    and EBITDA, P/E positive earnings, P/B positive book (<=30 unless FMP's),
    P/TB positive tangible book. unified_signal wins for the multiples it
    carries, so a new column never contradicts an existing one."""
    import sqlite3
    out = {}
    try:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(ticker_yf)")}
        raw = ", pe_raw, pb_raw, ev_ebitda_raw" if {"pe_raw", "pb_raw", "ev_ebitda_raw"} <= cols \
            else ", NULL, NULL, NULL"
        for (tk, evx, ev, ebitda, pe, pb, src, ptb, neg, fund, industry,
             pe_r, pb_r, evx_r) in conn.execute(f"""SELECT ticker, ev_ebitda, enterprise_value_m,
                ebitda_m, pe_ttm, pb_ratio, src, ptb_ratio, neg_tbv, is_fund, industry{raw} FROM ticker_yf"""):
            if fund:
                out[tk] = dict.fromkeys(VALUATION_COLS, "fund")
                continue
            if industry == "Shell Companies":       # a pre-merger SPAC: cash in trust, no operations
                out[tk] = dict.fromkeys(VALUATION_COLS, "SPAC")
                continue
            d = dict.fromkeys(VALUATION_COLS)
            if evx and ev and ev > 0 and ebitda and ebitda > 0:
                d["EV/EBITDA"] = evx
            elif (ebitda is not None and ebitda <= 0) or (evx_r is not None and evx_r < 0 and (ev or 0) > 0):
                d["EV/EBITDA"] = "neg EBITDA"
            elif ev is not None and ev <= 0:
                d["EV/EBITDA"] = "net cash"
            if pe and pe > 0:
                d["P/E"] = pe
            elif pe_r is not None and pe_r <= 0:
                d["P/E"] = "loss"
            if pb and pb > 0 and (pb <= 30 or src == "fmp"):
                d["P/B"] = pb
            elif pb_r is not None and pb_r <= 0:
                d["P/B"] = "neg equity"
            if ptb and ptb > 0:
                d["P/TB"] = ptb
            elif neg:
                d["P/TB"] = "neg TBV"
            elif pb_r is not None and pb_r <= 0:
                d["P/TB"] = "neg equity"
            out[tk] = d
    except sqlite3.OperationalError:
        pass
    for tk, ev, pb, pe in conn.execute("SELECT ticker, ev_ebitda, pb_ratio, pe_ttm FROM unified_signal"):
        d = out.setdefault(tk, dict.fromkeys(VALUATION_COLS))
        if ev is not None:
            d["EV/EBITDA"] = ev
        if pb is not None:
            d["P/B"] = pb
        if pe is not None and pe > 0:
            d["P/E"] = pe
    # not an operating stock: no multiple applies, whatever a data feed holds
    for tk, st in conn.execute("SELECT ticker, sec_type FROM unified_signal"):
        if st in _SEC_LABEL:
            out[tk] = dict.fromkeys(VALUATION_COLS, _SEC_LABEL[st])
    try:
        for (tk,) in conn.execute("SELECT ticker FROM yf_dead"):
            out[tk] = dict.fromkeys(VALUATION_COLS, "delisted")
    except sqlite3.OperationalError:
        pass
    return out

def valuation_for(vals, ticker, name):
    """One cell's value: bond lines ("MSTR 0.625 03-15-30", "ON (note)") are
    notes; anything no source knows stays None (rendered "—")."""
    t = str(ticker or "")
    if " " in t.strip():
        low = t.lower()
        return "warrant" if "(warrant)" in low else "right" if "(right)" in low else "note"
    return (vals.get(t) or {}).get(name)

def _fit_widths(ws, first_col):
    """autosize() for columns >= first_col only (keeps hand-set widths left of it)."""
    for col_idx in range(first_col, (ws.max_column or 1) + 1):
        max_len = 0
        for row in ws.iter_rows(min_col=col_idx, max_col=col_idx, values_only=True):
            v = row[0]
            if v is not None:
                max_len = max(max_len, min(len(str(v)), 80))
        ws.column_dimensions[get_column_letter(col_idx)].width = max(8, min(max_len + 2.5, 62))


def _is_header_row(ws, r, max_col):
    """A table header: 3+ filled cells, every one bold (data rows bold only
    their ticker; merged headings are a single cell)."""
    n = 0
    for c in range(1, max_col + 1):
        cell = ws.cell(r, c)
        if cell.value in (None, ""):
            continue
        if not (cell.font is not None and cell.font.bold):
            return False                    # data rows fail at their 2nd filled cell
        n += 1
    return n >= 3

def add_valuation_columns(wb, vals, skip=("README", "Legend")):
    """Every ticker table carries the same four multiples — EV/EBITDA, P/E,
    P/B, P/TB. Missing ones are inserted beside the valuation columns a table
    already has (else after MCAP / BUCKET, else at its end). Works table by
    table on the finished workbook: only that table's rows shift right, so
    stacked tables with different layouts on one sheet stay intact. Nothing
    is removed; existing columns keep their values, formats and colours."""
    from copy import copy
    for ws in wb.worksheets:
        if ws.title in skip:
            continue
        # openpyxl recomputes max_row / max_column by scanning every cell on
        # each access: read them once (84k-row sheets otherwise go quadratic)
        max_row, max_col = ws.max_row or 1, ws.max_column or 1
        heads = []
        for row in ws.iter_rows(min_row=1, max_row=max_row, max_col=min(max_col, 40)):
            for cell in row:
                if cell.value == "TICKER":
                    heads.append((cell.row, cell.column))
                    break
        # merged rows are section headings / notes, never table rows: a table
        # ends where one begins (and cells inside a merge can't be written)
        merged_rows = set()
        for rng in ws.merged_cells.ranges:
            merged_rows.update(range(rng.min_row, rng.max_row + 1))
        changes = []
        for h, tcol in heads:
            if h in merged_rows:
                continue
            hdr, width = {}, 0
            for col in range(1, max_col + 1):
                v = ws.cell(h, col).value
                if v not in (None, ""):
                    width = col
                    hdr.setdefault(str(v), col)
            missing = [m for m in VALUATION_COLS if m not in hdr]
            present = [hdr[m] for m in VALUATION_COLS if m in hdr]
            ins = max(present) if present else next(
                (hdr[a] for a in ("BUCKET", "MCAP", "MCAP $ (USD)") if a in hdr), width)
            # the table runs to the next header row; blank rows and merged
            # sub-headings inside it ('Bill IV — Miller Value Partners') are
            # stepped over, and only rows whose ticker cell is a ticker (or the
            # '—' placeholder) shift — notes and other tables are never touched
            body = []
            rr = h + 1
            while rr <= max_row:
                if rr not in merged_rows:
                    v = ws.cell(rr, tcol).value
                    if v == "TICKER" or _is_header_row(ws, rr, max_col):
                        break
                    # any filled ticker cell on a multi-cell row: tickers can be
                    # bond descriptors ("ON 0.5 03-01-29") in position lists
                    if v not in (None, "") and sum(ws.cell(rr, c).value not in (None, "")
                                                   for c in range(1, min(max_col, 6) + 1)) >= 2:
                        body.append(rr)
                rr += 1
            # valuation columns the table already has: a blank / "—" cell gets
            # the figure or the reason it has none, like the inserted columns
            for m in VALUATION_COLS:
                if m not in hdr:
                    continue
                for rr in body:
                    c = ws.cell(rr, hdr[m])
                    if c.value not in (None, "", "—"):
                        continue
                    v = valuation_for(vals, ws.cell(rr, tcol).value, m)
                    if v in (None, ""):
                        continue
                    num = isinstance(v, (int, float))
                    c.value = round(v, _VAL_DP[m]) if num else v
                    c.number_format = _VAL_FMT[m] if num else "General"
                    c.alignment = Alignment(horizontal="right", vertical="center")
            if not missing:
                continue
            k = len(missing)
            for rr in [h] + body:
                for col in range(width, ins, -1):          # rightmost first
                    src, dst = ws.cell(rr, col), ws.cell(rr, col + k)
                    dst.value, dst._style = src.value, copy(src._style)
                for i, name in enumerate(missing, 1):
                    c = ws.cell(rr, ins + i)
                    if rr == h:
                        c.value, c.font, c.border = name, HDR_FONT, HDR_BORDER
                        c.alignment = Alignment(horizontal="right", vertical="bottom")
                        c.number_format = "General"
                        continue
                    v = valuation_for(vals, ws.cell(rr, tcol).value, name)
                    num = isinstance(v, (int, float))
                    c.value = round(v, _VAL_DP[name]) if num else (v if v else "—")
                    c.font, c.border = BODY_FONT, ROW_BORDER
                    c.fill = PatternFill(fill_type=None)
                    c.alignment = Alignment(horizontal="right", vertical="center")
                    c.number_format = _VAL_FMT[name] if num else "General"
            ref = ws.auto_filter.ref
            if ref:
                m = re.match(r"([A-Z]+)(\d+):([A-Z]+)(\d+)$", ref)
                if m and int(m.group(2)) == h:
                    end = column_index_from_string(m.group(3)) + k
                    ws.auto_filter.ref = f"{m.group(1)}{m.group(2)}:{get_column_letter(end)}{m.group(4)}"
            changes.append((ins, k, width))
        if not changes:
            continue
        new_width = max(w + k for _, k, w in changes)
        for rng in list(ws.merged_cells.ranges):            # masthead spans the wider table
            if rng.min_row == rng.max_row and rng.min_row in (1, 2) and rng.min_col == 1 \
                    and rng.max_col < new_width:
                r0 = rng.min_row
                ws.unmerge_cells(rng.coord)
                ws.merge_cells(start_row=r0, start_column=1, end_row=r0, end_column=new_width)
                for col in range(1, new_width + 1):
                    ws.cell(r0, col).border = Border(bottom=THIN_BLK, top=NO_SIDE, left=NO_SIDE, right=NO_SIDE)
        if len(changes) == 1:
            ins, k, width = changes[0]                      # carry hand-set widths with their columns
            for col in range(width, ins, -1):
                w = ws.column_dimensions[get_column_letter(col)].width
                if w:
                    ws.column_dimensions[get_column_letter(col + k)].width = w
            for i in range(1, k + 1):
                ws.column_dimensions[get_column_letter(ins + i)].width = 9
        else:
            _fit_widths(ws, min(ins for ins, _, _ in changes) + 1)

def set_default_font(wb):
    """Apply Times New Roman as the workbook default styles where possible."""
    for ws in wb.worksheets:
        ws.sheet_properties.tabColor = None

# ---------- legend / glossary (shared across both workbooks) ----------
LEGEND = [
    ("Position classification", [
        ("Section 1 / S1", "Top-conviction holding (researcher notes) — counted only while the fund still holds the stock (any share class) in its latest 13F."),
        ("Section 3 / S3", "New position. A fund with a current 13F book counts when it opened the position in the latest quarter (0.5%+ of its book; spin-offs received and lines new at an IPO excluded); a fund with no current book counts from the researcher notes. Universe book: weighted by focus (a 20-name fund = 1, a 750-name fund = 0.1). Style book: number of funds."),
        ("Section 4 / S4", "Material add: as S3, for a position whose share count rose 25% or more in the latest quarter."),
        ("Section 5", "Researcher-flagged position (letters, interviews, primary research) without a 13F section."),
        ("ST  (prefix)", "Within-style: counted only across funds in THIS macro-style. e.g. ST S3 = funds in this style initiating a new major position; ST Holders = holders within the style."),
        ("Sub (prefix)", "Within sub-group: counted only across funds in this sub-group tier (e.g. Sub Holders)."),
        ("Uni (prefix)", "Universe-wide: counted across every tracked fund (e.g. Uni 13F)."),
    ]),
    ("Smart money & conviction", [
        ("13F / 13F WT / Smart$ n", "Conviction-weighted count of 13F holders: each fund counts min(1, 75 ÷ its positions), so a 20-name book counts 1 and a 6,000-name quant 0.01. Not a raw holder count."),
        ("Holders", "Count of funds holding the name (overall, or within style / sub-group when prefixed)."),
        ("pB Max", "Largest single-fund position weight — the maximum % of any one fund's book in the name."),
        ("pB ≥5%", "Number of funds with at least 5% of their book in the name (a concentration cluster)."),
        ("%Book", "A position's weight as a percent of the fund's reported equity book."),
        ("Score", "Unified score: log(13F)×2 + section weights + concentration + activist + insider + catalyst − sells (full formula on README)."),
        ("Global Score", "Score excluding US-only signals (Form 4, clusters) so foreign listings rank on equal footing."),
        ("Rev Pref", "Score-table column: 2×S3 + 1×S4 + 0.5×S1 — active accumulation, not static holding. The Revealed Preference sheet ranks on its own RP Score (dated evidence only; see that sheet)."),
        ("Asym", "Asymmetry score — margin-of-safety (cheap valuation + below smart-money entry) × upside (conviction + catalyst + small-cap room)."),
        ("Why", "The top-3 terms driving the Score, as compact codes: sm=smart-money holders, s1=top-pick funds, s3=new-position funds, s4=add funds, pb=low price/book, pb5=funds ≥5% book, clu$=insider-cluster $, f4buy=insider buys, f4rec=very-recent buys, f4sell=insider sells, act=activist %, 8k=catalyst, micro=small-cap, entry=below smart-money entry. e.g. 's1 24 · pb5 18 · pb 14'."),
        ("Lift  (Signature picks)", "How much a fund STYLE over-indexes on a name vs the whole universe: (style holder-share) ÷ (universe holder-share). >1 = the style's distinctive bet."),
    ]),
    ("Latest quarter & holders (style book)", [
        ("Vote Wt", "A fund's vote: min(1, 75 ÷ its positions). A focused 20-name book counts 1; a 1,800-name quant book 0.04. Diversified books show the crowd, not conviction."),
        ("St Wtd / Sub Wtd", "Holders within the style (sub-group) weighted by Vote Wt — the ranking for 'most held'."),
        ("Held By", "The style's largest holders by % of their own book (all of them up to four, then '+N more')."),
        ("Last Qtr", "Within the style, funds that bought (new or added) / sold (trimmed or exited) the name in the latest 13F quarter, e.g. '+3 / -1'."),
        ("Net Pts", "Sum over the style's funds of the % of book bought, minus sold, in the latest quarter (new or added positions, net of trims and exits, capped at 10 per fund, times Vote Wt). Half weight for a line new at an IPO (an allocation, or a pre-IPO stake becoming reportable); zero for a spin-off received."),
        ("Who Bought / Who Sold", "Each fund's move: 'new 4.1%' (opened, now 4.1% of book), '+38% to 6.0%' (shares up 38%), 'exited 2.2%', '-50% to 1.1%'."),
        ("Book / Filed", "The quarter a fund's latest 13F covers, and its filing date. 'dormant' = no 13F for 200+ days (archived, not counted)."),
        ("Top-10 %", "Share of the fund's 13F equity book in its ten largest positions — how concentrated it is."),
        ("Share classes", "Classes of one company (GOOG + GOOGL, BRK-A + BRK-B) count as one holding in the style book; the Name column lists the merged classes."),
    ]),
    ("Convergence / Action Dashboard signals", [
        ("Smart$≥3", "13F (conviction-weighted holders) of 3 or more."),
        ("Activist", "A 13D/G stake of 10% or more, filed in the last 24 months."),
        ("Insider30d", "Any open-market insider purchase in the last 30 days."),
        ("Cluster", "Two or more insiders buying within a live (≤180-day) window."),
        ("New/Add", "S3 or S4 above zero: a fund opened or added 25%+ to the position (latest 13F quarter; research notes for funds without a current 13F)."),
        ("BelowEntry", "Price 15%+ below the funds' estimated entry (see In The Money for how the anchor is set)."),
        ("Cheap", "EV/EBITDA 2–12x, or price / book up to 1.2x."),
        ("Catalyst", "An 8-K for M&A (Item 1.01 / 2.01) or change of control (5.01) in the last 180 days."),
        ("# Sig", "How many of these eight fire."),
    ]),
    ("Industries (FMP designations)", [
        ("Industry", "FMP's industry designation (\"Banks - Regional\", \"Semiconductors\", \"Oil & Gas E&P\"): narrower than a sector, independent of GICS."),
        ("Managers", "Industry Index: distinct 13F filers (one per filing) plus N-PORT managers holding any of the industry's names."),
        ("$B Held (13F)", "The tracked funds' 13F value in the industry's names, in $ billions."),
        ("Net Pts / Buyers / Sellers", "Last quarter's net buying across all funds (as in Revealed Preference), and how many funds bought or sold any of the industry's names."),
        ("Holders", "Industry Detail: conviction-weighted 13F holders (each fund counts min(1, 75 ÷ its positions))."),
        ("Styles", "The styles holding the name, ranked by their funds' combined % of book in it, with the number of their funds."),
        ("Share % / All Funds % / Tilt", "Industries by Style: the average fund's % of book in the industry, in the style and across all funds; Tilt = Share ÷ All Funds (above 1 = the style leans in)."),
        ("Median P/E, EV/EBITDA, P/TB, ROE, 3M", "Across the industry's held names. For financials read P/TB and ROE; EV/EBITDA means nothing for a bank."),
    ]),
    ("Short interest, events and track records", [
        ("Short % Out", "Shares sold short ÷ shares outstanding, from FINRA's latest twice-monthly settlement."),
        ("Days to Cover", "Short shares ÷ average daily volume: how many days of normal trading the shorts would need to buy back."),
        ("3M Chg % (shorts)", "Change in short shares against the settlement about three months earlier: bears building (up) or leaving (down)."),
        ("Buyers' Record", "For a name the funds bought last quarter: how often those buyers' earlier new buys beat the S&P 500 after their 13Fs went public, averaged over the buyers with a record (10+ measured buys; Manager Track Records). Read it against the all-funds figure in that sheet's header, not against 50%."),
        ("Beat S&P % / Median vs S&P", "Manager Track Records: of a fund's new buys (0.5%+ of book, not held the quarter before), the share that beat the S&P 500 from the 13F filing date to the latest close (a stock taken over: to its last close, the S&P to the same day), and the middle result in percentage points. Price moves only, split-adjusted."),
        ("Big Bets", "New buys of 3%+ of the book, measured the same way."),
        ("Proxy fight / Dissident", "Special Situations: a proxy contest filed in the last 180 days (DFAN14A / PREN14A / DEFN14A from a dissident, PREC14A / DEFC14A from the company); Tracked? = the dissident is on the fund roster."),
        ("Spin-off coming / Form 10", "A new company registering its shares (Form 10-12B / 10-12G) that names a parent: shares are about to be distributed to the parent's holders."),
        ("Tender / going private", "A third-party tender offer (SC TO-T), a going-private deal (SC 13E3) or a target's response (SC 14D9) in the last 180 days."),
    ]),
    ("Activist & insider (SEC)", [
        ("13D", "Number of SC 13D / 13G beneficial-ownership filings (a ≥5% stake)."),
        ("Act %", "Largest activist stake disclosed via 13D/G (max percent of share class)."),
        ("Clu $M", "Insider cluster size — total dollars of a live (≤180-day) multi-insider open-market buy cluster."),
        ("F4 Buy / F4 $M", "Form 4 open-market insider purchases (transaction code P), in millions of dollars."),
        ("F4 Buy ≤30d / 180d", "Insider open-market buys reported within the last 30 / 180 days."),
        ("F4 Sell", "Form 4 open-market insider sales (code S) — a counter-signal."),
        ("Weighted $M", "Recency-weighted insider buys: ≤30d ×1.0, 31–60d ×0.6, 61–120d ×0.3, 121–180d ×0.1."),
        ("# Insiders / # Buyers", "Distinct insiders buying in the window."),
        ("Cluster? / clstr", "A live insider buy cluster is present for the name."),
    ]),
    ("Valuation", [
        ("Mcap", "Market capitalization in USD ($M, auto-scaled to $B / $T). Foreign caps are FX-converted to USD."),
        ("ADV $M", "Average daily dollar volume traded (3-month, $M) — the tradeability check: a high score on a $0.3M/day nano is hard to act on."),
        ("EV/EBITDA", "Enterprise value ÷ trailing EBITDA (shown ×). A negative figure means negative EBITDA."),
        ("P/B", "Price ÷ book value per share (shown ×). A negative figure means negative book equity."),
        ("P/E  /  Fwd P/E", "Price ÷ trailing (or forward) EPS (shown ×)."),
        ("Rev Gr %", "Year-over-year revenue growth. Negative (crimson) flags a possible value trap on an otherwise-cheap multiple."),
        ("Margin %", "Net profit margin. Negative (crimson) = loss-making."),
        ("EV/Rev  /  PEG", "Enterprise value ÷ revenue; PEG = P/E ÷ growth. Cover names with no meaningful EV/EBITDA."),
    ]),
    ("Price & momentum (from daily closes)", [
        ("3mo %  /  20d %", "Price change over the last ~3 months / ~20 trading days. Positive = lapis, negative = crimson."),
        ("Off Hi %", "Percent below the 3-month high (drawdown). A name deep off its high with insiders buying is a different setup from one at highs."),
    ]),
    ("Quarter-over-quarter (QoQ Change sheet)", [
        ("Net Funds", "(New + Added) − (Trimmed + Exited) funds this quarter vs each fund's prior 13F. Lapis = accumulating, crimson = distributing."),
        ("New / Added / Trimmed / Exited", "Count of funds that started / grew (>5%) / cut (>5%) / closed the position, matched on CUSIP + share count."),
        ("Δ Shares %", "Aggregate share-count change across all funds vs the prior quarter."),
        ("Form", "Security form being accumulated, from each 13F line's titleOfClass. \"common\" = ordinary common/ordinary shares (a clean directional bet). \"+preferred / +warrant / +unit / +right / +note\" flags that non-common equity forms are held under this ticker — optionality or financing, which should NOT be read as the same conviction as buying common."),
    ]),
    ("Broker Swap Radar", [
        ("Δ Sh (M) / Δ % Out", "Quarter-over-quarter share-count change in ONE swap-desk broker's 13F (UBS, GS, MS, JPM...), absolute and as % of shares outstanding."),
        ("Idio %", "This desk's move as a share of ALL tracked desks' movement in the name. High = idiosyncratic (swap-hedge-like); low = every desk moved (index/ETF flow)."),
        ("Why it matters", "An activist building via total-return swaps appears on NO 13F/13D of their own — the counterparty desk hedges with physical shares, which print HERE. Leads, not proof: baskets and custody flows also move desks."),
    ]),
    ("Latent Ownership (13D text)", [
        ("# Feat / Hidden Features", "Count and list of economic-control features parsed from the holder's 13D: prefunded/ordinary warrants, convertibles, ownership blocker, board-designation rights, registration rights, ROFR, anti-dilution, standstill, disclosed swap."),
        ("Blocker %", "The ownership-limitation ceiling (4.99 / 9.99 / 19.99%) — the holder's economic exposure can sit just under it while the header % looks small; the blocker is often contractually raisable."),
        ("Swap Cpty", "A total-return / cash-settled swap named in the 13D text, with counterparty desk if disclosed — the clearest hidden-economic-exposure tell; cross-check the Broker Swap Radar."),
    ]),
    ("N-PORT (registered funds)", [
        ("N-PORT", "A US-registered fund's full holdings report (Form N-PORT-P), public quarterly about 60 days after each fund's fiscal quarter. Unlike a 13F it lists EVERY holding, local non-US listings included. Supplementary: never counted in the 13F score."),
        ("N-PORT Funds", "Directory of the funds loaded, grouped by the manager's style: portfolio date, equity $, positions, non-US share, largest positions, names initiated / exited since the previous report."),
        ("N-PORT Holdings", "Each fund's complete equity book, a section per manager and a table per fund, with each position's change since the previous report."),
        ("Change", "new (not in the previous report) · added / trimmed (shares up / down over 10%, split-adjusted) · held · blank when the fund has no earlier report on file."),
        ("N-PORT Changes", "Per stock: managers initiating, adding, trimming and exiting across all their funds; Net = buyers minus sellers."),
        ("N-PORT Global Consensus", "Non-US equities ranked by how many managers hold them; New Buyers = managers holding it now but in none of their previous reports."),
    ]),
    ("Entry / setup", [
        ("Entry / Bucket", "Where the current price sits versus the smart-money cost anchor: below / near / above."),
        ("Anchor $", "Estimated smart-money cost basis (cost_basis / filing text / Form-4 buy average / 80th-percentile)."),
        ("vs Entry %", "Current price relative to the anchor (negative = trading below where smart money bought)."),
        ("Now $", "Current share price (USD)."),
        ("ER %", "Expected return — base-rate-weighted historical 12-month excess for the name's factor tags."),
    ]),
    ("Catalysts (8-K, ≤180 days)", [
        ("M&A", "Item 1.01 / 2.01 — merger, acquisition, or material definitive agreement."),
        ("Ctrl / CTRL", "Item 5.01 — change of control of the registrant."),
        ("Director", "Item 5.02 — departure / appointment of directors or officers."),
        ("PIPE", "Item 3.02 — unregistered sale of equity (potential dilution)."),
        ("Bnk", "Item 1.03 — bankruptcy or receivership."),
        ("Total Events", "Count of distinct 8-K material events in the window."),
    ]),
    ("Size buckets", [
        ("nano", "Under $50M market cap."),
        ("micro", "$50M – $300M."),
        ("small", "$300M – $2B."),
        ("mid", "$2B – $10B."),
        ("large", "$10B – $200B."),
        ("mega", "Over $200B."),
        ("unknown", "Market cap unresolved (foreign / SPAC / warrant / defunct)."),
    ]),
    ("Valuation cells", [
        ("number", "The multiple: EV/EBITDA, P/E (trailing), P/B, P/TB (price / tangible book)."),
        ("loss", "Trailing earnings are negative: no P/E."),
        ("neg EBITDA", "Trailing EBITDA is negative: no EV/EBITDA."),
        ("net cash", "Enterprise value is below zero (cash exceeds market cap plus debt): no EV/EBITDA."),
        ("neg equity", "Book equity is negative (buybacks, accumulated losses): no P/B or P/TB."),
        ("neg TBV", "Book is positive but tangible book is negative (goodwill-heavy): no P/TB."),
        ("fund / warrant / unit / right / pref / note", "Not an operating stock: company multiples do not apply."),
        ("SPAC", "A pre-merger blank-check shell (cash in trust, no operations): multiples do not apply."),
        ("delisted", "No longer trades."),
        ("—", "No source carries the figure."),
    ]),
    ("Sources & symbols", [
        ("13F-HR", "SEC quarterly institutional holdings filing (the standard smart-money source). NOTE: 13F holdings are quarter-END positions filed up to 45 days later — the smart-money columns can be up to ~3–4 months old (see each sheet's as-of date). Form 4 / 13D / 8-K / valuation columns are near-current."),
        ("XLSX", "Research-team position notes (sections 1 / 3 / 4 / 5), compiled May–June 2026 from mostly Q4 2025 – Q1 2026 filings. Superseded by the latest 13F wherever a fund has a current book; the only source for funds without one."),
        ("SC 13D/G", "SEC beneficial-ownership filing (a ≥5% stake)."),
        ("Value $M", "Position market value in $M (13F holdings); blank for 13D/G rows."),
        ("—", "An em-dash means not applicable / not available for that cell."),
    ]),
    ("Colour (Times-Lattice — 'colour is data')", [
        ("Lapis blue", "Good / improving: positive momentum & growth, insider buying, net funds accumulating, cheap valuation."),
        ("Crimson red", "Bad / deteriorating: negative momentum & growth, insider selling, net funds distributing."),
        ("Faint wash", "Score / valuation / vs-entry heatmaps — a lapis or crimson tint at ~7% strength, darker = more attractive."),
        ("Black only", "Everything structural. Colour appears ONLY where it carries a good/bad meaning, never for decoration."),
    ]),
]

def write_legend_sheet(wb, index=1):
    """Insert a 'Legend' sheet defining every column header / abbreviation used
    across the workbook. Shared so both books document the same vocabulary."""
    ws = wb.create_sheet("Legend", index)
    ws.sheet_view.showGridLines = False
    write_title(ws, "Legend — column definitions & abbreviations",
                "What every column header and code means. Prefixes: ST = within macro-style · Sub = within sub-group · Uni = universe-wide.", 2)
    ws.column_dimensions["A"].width = 24
    ws.column_dimensions["B"].width = 116
    row = 4
    for group, items in LEGEND:
        write_section_heading(ws, row, group, 2)
        row += 1
        for term, definition in items:
            a = ws.cell(row=row, column=1, value=term)
            a.font = TICKER_FONT
            a.alignment = Alignment(horizontal="left", vertical="top")
            b = ws.cell(row=row, column=2, value=definition)
            b.font = BODY_FONT
            b.alignment = Alignment(horizontal="left", vertical="top", wrap_text=True)
            ws.row_dimensions[row].height = 30 if len(definition) <= 110 else 44
            a.border = ROW_BORDER
            b.border = ROW_BORDER
            row += 1
        row += 1  # gap between groups
    ws.freeze_panes = "A4"
    return ws

def add_contents_index(ws, sheetnames, exclude=("README",)):
    """Append a clickable 'Contents' index to the README sheet — one internal
    hyperlink per sheet so the reader can jump straight to any tab. Monochrome:
    black text, underlined to signal it is clickable."""
    row = (ws.max_row or 1) + 2
    write_section_heading(ws, row, "Contents — click to open a sheet", 2)
    row += 1
    link_font = Font(name=TNR, size=SIZE_BODY, color=BLACK, underline="single")
    for name in sheetnames:
        if name in exclude:
            continue
        c = ws.cell(row=row, column=1, value=name)
        c.hyperlink = f"#'{name}'!A1"
        c.font = link_font
        c.alignment = Alignment(horizontal="left", vertical="center")
        ws.row_dimensions[row].height = 16
        row += 1

def set_print_layout(wb, header_rows=4):
    """Sensible print defaults on every sheet: landscape, fit-to-width, and the
    title/header rows repeated at the top of each printed page."""
    for ws in wb.worksheets:
        ws.page_setup.orientation = "landscape"
        ws.page_setup.fitToWidth = 1
        ws.page_setup.fitToHeight = 0
        ws.sheet_properties.pageSetUpPr = PageSetupProperties(fitToPage=True)
        ws.print_options.horizontalCentered = False
        try:
            ws.print_title_rows = f"1:{header_rows}"
        except Exception:
            pass
