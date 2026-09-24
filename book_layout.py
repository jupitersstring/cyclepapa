"""Workbook layout helpers shared by the three books.

  key_numbers(wb, fin, sym_map)   a compact "Key numbers" column (P/B · EV/EBITDA
                                  · net debt/mcap · 52w position) inserted right
                                  after each tab's Name column -- the reader sees
                                  the financials next to the name, not off-screen
  strength(wb, populations)       ONE ranking scale: "Strength %ile" next to the
                                  name on every thesis / signal tab = the name's
                                  percentile among EVERYTHING that layer scored
                                  (100 = strongest), not just the rows shown
  regroup(wb, groups, colors)     reorder tabs by how a reader works (Decide ·
                                  Theses · Signals · Evidence · Plumbing), colour
                                  the tabs by group, rewrite Contents with a group
                                  column
  tear_sheets(wb, fin, names, ...) one block per name: identity, financial panel,
                                  and every tab the name appears on with its
                                  strength percentile and that tab's own facts
"""

from __future__ import annotations

import json
from bisect import bisect_left, bisect_right
from pathlib import Path

from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

ROOT = Path("/home/user/cyclepapa")
NAVY = "1F3864"
HEAD = Font(bold=True, color="FFFFFF")
FILL = PatternFill("solid", fgColor=NAVY)
TICKER_HDR = ("Ticker", "TKR", "Symbol")
SKIP_COLS = {"FMP financial read", "Key numbers (FMP)", "Strength %ile", "Name", "Company", "Ticker", "#", "Rank"}


NEW_SHEETS = ("Name Financials", "Tear Sheets", "Review & data quality", "Call intent", "Contents")


def clone(src, dst):
    """Copy the full cell style (font, fill, border, alignment, number format)."""
    from copy import copy
    from openpyxl.cell.cell import MergedCell
    if isinstance(dst, MergedCell) or src is None or not src.has_style:
        return
    dst.font = copy(src.font)
    dst.fill = copy(src.fill)
    dst.border = copy(src.border)
    dst.alignment = copy(src.alignment)
    dst.number_format = src.number_format


class Kit:
    """The workbook's OWN house style, read from one of its existing ticker
    sheets, so anything we add looks like the rest of the book."""

    def __init__(self, wb):
        ref = None
        for ws in wb.worksheets:
            if ws.title in NEW_SHEETS:
                continue
            hr, cols = header_of(ws)
            if hr and ws.max_row > hr + 3 and len(cols) >= 4:
                ref = (ws, hr, cols)
                break
        ws, hr, cols = ref
        tcol = cols.get("Ticker") or cols.get("TKR") or cols.get("Symbol")
        ncol = cols.get("Name") or cols.get("Company") or (tcol + 1)
        self.title_c, self.sub_c = ws["A1"], ws["A2"]
        if not ws["A2"].has_style or ws["A2"].value is None:
            self.sub_c = ws["A1"]
        self.head_c = ws.cell(row=hr, column=ncol)
        r1, r2 = ws.cell(row=hr + 1, column=ncol), ws.cell(row=hr + 2, column=ncol)
        banded = lambda c: bool(c.fill is not None and c.fill.fill_type)
        plain_r, band_r = (hr + 1, hr + 2) if not banded(r1) else (hr + 2, hr + 1)
        self.body_c, self.band_c = ws.cell(row=plain_r, column=ncol), ws.cell(row=band_r, column=ncol)
        self.bold_c, self.bold_band_c = ws.cell(row=plain_r, column=tcol), ws.cell(row=band_r, column=tcol)
        self.header_height = ws.row_dimensions[hr].height

    def title(self, c):
        clone(self.title_c, c)

    def subtitle(self, c, wrap=True):
        clone(self.sub_c, c)
        if wrap:
            from copy import copy
            a = copy(c.alignment); a.wrap_text = True; a.vertical = "top"
            c.alignment = a

    def header(self, c):
        clone(self.head_c, c)

    def body(self, c, band=False, bold=False, wrap=False):
        clone((self.bold_band_c if band else self.bold_c) if bold else (self.band_c if band else self.body_c), c)
        if wrap:
            from copy import copy
            a = copy(c.alignment); a.wrap_text = True; a.vertical = "top"
            c.alignment = a


def kit(wb):
    k = getattr(wb, "_style_kit", None)
    if k is None:
        k = wb._style_kit = Kit(wb)
    return k


def header_of(ws, max_row=12):
    """(header_row, {header: col}) for the first row with a Ticker cell."""
    for row in ws.iter_rows(min_row=1, max_row=min(ws.max_row, max_row)):
        for c in row:
            if isinstance(c.value, str) and c.value.strip() in TICKER_HDR:
                return c.row, {str(x.value).strip(): x.column for x in row if x.value is not None}
    return None, {}


def insert_col(ws, idx, header, hdr_row, width=24):
    """Insert a column at idx, keeping merged ranges and column widths aligned
    (openpyxl's insert_cols moves cells but not merges or widths)."""
    widths = {i: ws.column_dimensions[get_column_letter(i)].width for i in range(1, ws.max_column + 1)}
    merges = [(m.min_row, m.min_col, m.max_row, m.max_col) for m in ws.merged_cells.ranges]
    for m in list(ws.merged_cells.ranges):
        ws.unmerge_cells(str(m))
    ws.insert_cols(idx)
    for r0, c0, r1, c1 in merges:
        if c0 >= idx:
            c0, c1 = c0 + 1, c1 + 1
        elif c1 >= idx:
            c1 += 1
        ws.merge_cells(start_row=r0, start_column=c0, end_row=r1, end_column=c1)
    for i in sorted(widths, reverse=True):
        j = i + 1 if i >= idx else i
        if widths[i]:
            ws.column_dimensions[get_column_letter(j)].width = widths[i]
    ws.column_dimensions[get_column_letter(idx)].width = width
    # the new column inherits its neighbour's style on every row (header rule,
    # body font, row banding, borders), so it reads as part of the table
    nb = idx - 1 if idx > 1 else idx + 1
    for r in range(hdr_row, ws.max_row + 1):
        clone(ws.cell(row=r, column=nb), ws.cell(row=r, column=idx))
    ws.cell(row=hdr_row, column=idx, value=header)


def _name_col(cols):
    for k in ("Name", "Company"):
        if k in cols:
            return cols[k]
    return cols.get("Ticker") or next(iter(cols.values()))


def _ticker(v):
    return v.replace("●", "").strip() if isinstance(v, str) else None


def key_line(f):
    if not f:
        return None
    bits = []
    if f.get("p_b") is not None:
        bits.append(f"P/B {f['p_b']:.2f}")
    ev = f.get("ev_ebitda")
    if (f.get("sector") or "") == "Financial Services":
        if f.get("pe") is not None and 0 < f["pe"] < 200:
            bits.append(f"P/E {f['pe']:.1f}")
    elif ev is not None and 0 < ev < 200:
        bits.append(f"{ev:.1f}× EBITDA")
    nc = f.get("net_cash_pct")
    if nc is not None and (f.get("sector") or "") != "Financial Services":
        bits.append(("cash " if nc >= 0 else "debt ") + f"{abs(nc) * 100:.0f}%")
    if f.get("range_pos") is not None:
        bits.append(f"52w {f['range_pos'] * 100:.0f}%")
    return " · ".join(bits)


def key_numbers(wb, fin, sym_map=None, skip=()):
    n = 0
    for ws in wb.worksheets:
        if ws.title in skip:
            continue
        hr, cols = header_of(ws)
        if not hr or "Key numbers (FMP)" in cols:
            continue
        idx = _name_col(cols) + 1
        insert_col(ws, idx, "Key numbers (FMP)", hr, width=30)
        tcol = cols.get("Ticker") or cols.get("TKR") or cols.get("Symbol")
        tcol = tcol + 1 if tcol >= idx else tcol
        for r in range(hr + 1, ws.max_row + 1):
            t = _ticker(ws.cell(row=r, column=tcol).value)
            if t:
                line = key_line(fin.get((sym_map or {}).get(t, t)))
                if line:
                    ws.cell(row=r, column=idx, value=line)
        n += 1
    return n


# ---------------------------------------------------------------- one scale
def _load(fn):
    p = ROOT / fn
    return json.loads(p.read_text()) if p.exists() else {}


def _field(fn, field, nested=None):
    d = _load(fn)
    if nested:
        d = d.get(nested) or {}
    out = {}
    for k, v in d.items():
        if isinstance(v, dict):
            x = v.get(field)
            if isinstance(x, (int, float)) and x > 0:
                out[k] = float(x)
    return out


def populations():
    """Tab -> {ticker: score} over EVERYTHING the layer scored."""
    return {
        "Governance Discount": _field("governance_discount.json", "score"),
        "Mechanism Gates": _field("mechanism_gates.json", "score"),
        "Payoff Geometry": _field("payoff_geometry.json", "score"),
        "MD&A Intent": _field("mda_scan.json", "score"),
        "Call Intent": _field("call_intent.json", "act_prob"),
        "Structured Distressed": _field("structured_distressed_injection.json", "score"),
        "Distressed Stub Progress": _field("distressed_stub_progress.json", "score"),
        "Re-Rate Catalysts": _field("rerate_catalysts.json", "rerate_score") or _field("rerate_catalysts.json", "catalyst_score"),
        "Tail Odds": _field("tail_odds.json", "est_tail_prob"),
        "Insider Conviction": _field("discretionary_insider_conviction.json", "score"),
        "Insider Filing-Time": _field("form4_timing.json", "score", nested="scores"),
        "Asymmetry Assembly": _field("asymmetry_assembly.json", "score"),
        "Foreign Markets": _field("foreign_markets.json", "score"),
    }


SCORE_HDRS = ("Score", "Conviction", "Timing pts", "Improve", "Assembly", "Conf. tail p", "Tail p",
              "Act prob", "Consensus", "Screens fired", "Distress")


def _pctile(sorted_vals, v):
    if not sorted_vals:
        return None
    lo, hi = bisect_left(sorted_vals, v), bisect_right(sorted_vals, v)
    return round(100.0 * ((lo + hi) / 2) / len(sorted_vals))


def strength(wb, pops, skip=()):
    """Insert 'Strength %ile' after the name (after Key numbers when present)."""
    n = 0
    for ws in wb.worksheets:
        if ws.title in skip:
            continue
        hr, cols = header_of(ws)
        if not hr or "Strength %ile" in cols:
            continue
        sc = next((cols[h] for h in SCORE_HDRS if h in cols), None)
        pop = pops.get(ws.title)
        if sc is None and not pop:
            continue
        tcol = cols.get("Ticker") or cols.get("TKR") or cols.get("Symbol")
        rows = [r for r in range(hr + 1, ws.max_row + 1) if _ticker(ws.cell(row=r, column=tcol).value)]
        if pop:
            vals, basis = sorted(pop.values()), f"all {len(pop):,} names scored"
            get = lambda r: pop.get(_ticker(ws.cell(row=r, column=tcol).value))
        else:
            within = [ws.cell(row=r, column=sc).value for r in rows]
            vals = sorted(v for v in within if isinstance(v, (int, float)))
            basis = f"the {len(vals)} names on this tab"
            get = lambda r: ws.cell(row=r, column=sc).value if isinstance(ws.cell(row=r, column=sc).value, (int, float)) else None
        if not vals:
            continue
        idx = (cols.get("Key numbers (FMP)") or _name_col(cols)) + 1
        scores = {r: get(r) for r in rows}
        insert_col(ws, idx, "Strength %ile", hr, width=9)
        ws.cell(row=hr, column=idx).comment = None
        for r, v in scores.items():
            if v is not None:
                ws.cell(row=r, column=idx, value=_pctile(vals, v))
        # say what the percentile is measured against, under the header row
        from openpyxl.cell.cell import MergedCell
        note = ws.cell(row=hr - 1, column=idx) if hr > 1 else None
        if note is not None and not isinstance(note, MergedCell) and note.value is None:
            note.value = f"%ile vs {basis}"
            base = ws.cell(row=hr + 1, column=idx).font
            note.font = Font(name=base.name, italic=True, size=max(7, (base.size or 10) - 2), color="666666")
        n += 1
    return n


# ---------------------------------------------------------------- grouping
GROUP_COLORS = {"Decide": "1F3864", "Theses": "2E75B6", "Signals": "70AD47",
                "Evidence": "ED7D31", "Plumbing": "A5A5A5"}


def regroup(wb, groups, contents="Contents", descriptions=None):
    """Reorder sheets by group; colour tabs; rewrite the Contents table."""
    order, seen = [], set()
    for g, tabs in groups:
        for t in tabs:
            if t in wb.sheetnames and t not in seen:
                order.append((g, t)); seen.add(t)
    for t in wb.sheetnames:                       # anything unlisted goes to Plumbing
        if t not in seen:
            order.append(("Plumbing", t)); seen.add(t)
    wb._sheets = [wb[t] for _, t in order]
    for g, t in order:
        wb[t].sheet_properties.tabColor = GROUP_COLORS.get(g, "A5A5A5")
    if contents in wb.sheetnames:
        ws = wb[contents]
        hr, cols = None, {}
        for row in ws.iter_rows(min_row=1, max_row=8):
            for c in row:
                if c.value == "Tab":
                    hr = c.row
            if hr:
                break
        if hr:
            from copy import copy
            hdr_src = ws.cell(row=hr, column=2)
            body_srcs = [ws.cell(row=hr + 1, column=2), ws.cell(row=hr + 2, column=2)]
            bold_srcs = [ws.cell(row=hr + 1, column=1), ws.cell(row=hr + 2, column=1)]
            # snapshot the styles before the cells are cleared
            snap = {}
            for key, c in (("h", hdr_src), ("b0", body_srcs[0]), ("b1", body_srcs[1]),
                           ("k0", bold_srcs[0]), ("k1", bold_srcs[1])):
                snap[key] = (copy(c.font), copy(c.fill), copy(c.border), copy(c.alignment), c.number_format)

            def apply(c, key):
                c.font, c.fill, c.border, c.alignment, c.number_format = [copy(x) for x in snap[key][:4]] + [snap[key][4]]
            old = {}
            for r in range(hr + 1, ws.max_row + 1):
                vals = [ws.cell(row=r, column=j).value for j in range(1, 5)]
                tab = next((v for v in vals if isinstance(v, str) and v in wb.sheetnames), None)
                if tab:
                    old[tab] = next((v for v in vals[vals.index(tab) + 1:] if isinstance(v, str)), "")
            for m in list(ws.merged_cells.ranges):
                if m.min_row >= hr:
                    ws.unmerge_cells(str(m))
            for r in range(hr, ws.max_row + 1):
                for j in range(1, 5):
                    ws.cell(row=r, column=j).value = None
            for j, h in enumerate(["Group", "Tab", "What it contains"], 1):
                apply(ws.cell(row=hr, column=j, value=h), "h")
            ws.column_dimensions["A"].width = 11
            ws.column_dimensions["B"].width = 26
            ws.column_dimensions["C"].width = 90
            r = hr
            i = 0
            for g, t in order:
                if t == contents:
                    continue
                r += 1
                i += 1
                b = "1" if i % 2 == 0 else "0"
                apply(ws.cell(row=r, column=1, value=g), "k" + b)
                apply(ws.cell(row=r, column=2, value=t), "b" + b)
                apply(ws.cell(row=r, column=3, value=(descriptions or {}).get(t) or old.get(t, "")), "b" + b)
    return order


# ---------------------------------------------------------------- tear sheets
METRICS = [("P/B", "p_b", "{:.2f}"), ("P/E", "pe", "{:.1f}"), ("EV/EBITDA", "ev_ebitda", "{:.1f}×"),
           ("FCF yield", "fcf_yield", "{:.0%}"), ("Net cash / mcap", "net_cash_pct", "{:+.0%}"),
           ("Net debt / EBITDA", "nd_ebitda", "{:.1f}×"), ("Revenue growth", "rev_growth", "{:+.0%}"),
           ("Operating margin", "op_m", "{:.0%}"), ("ROE", "roe", "{:.0%}"),
           ("Shares YoY", "shares_yoy", "{:+.0%}"), ("Interest cover", "int_cover", "{:.1f}×"),
           ("52-week position", "range_pos", "{:.0%}"), ("Avg $ volume", "adv_usd", "${:,.0f}")]


def _row_facts(ws, r, cols):
    out = []
    for h, c in cols.items():
        if h in SKIP_COLS or h in TICKER_HDR:
            continue
        v = ws.cell(row=r, column=c).value
        if v in (None, "", "–", "—"):
            continue
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            s = f"{v:,.0f}" if abs(v) >= 1000 else (f"{v:.3g}" if isinstance(v, float) else str(v))
        else:
            s = str(v)
        out.append(f"{h}: {s[:60]}")
    return " · ".join(out)


def tear_sheets(wb, fin, names, sym_map=None, title="Tear Sheets", index=None, max_names=60):
    """names: [display_ticker] in priority order."""
    # index every tab row by ticker once
    where = {}
    for ws in wb.worksheets:
        if ws.title in (title, "Name Financials"):
            continue
        hr, cols = header_of(ws)
        if not hr:
            continue
        tcol = cols.get("Ticker") or cols.get("TKR") or cols.get("Symbol")
        for r in range(hr + 1, ws.max_row + 1):
            t = _ticker(ws.cell(row=r, column=tcol).value)
            if t and len(t) < 20:
                where.setdefault(t, []).append((ws, r, cols))
    k = kit(wb)
    ts = wb.create_sheet(title, index) if index is not None else wb.create_sheet(title)
    ts.sheet_view.showGridLines = False
    ts.column_dimensions["A"].width = 24
    ts.column_dimensions["B"].width = 14
    ts.column_dimensions["C"].width = 110
    k.title(ts.cell(row=1, column=1, value=title))
    k.subtitle(ts.cell(row=2, column=1, value=(
        "One block per name: identity, the FMP financial panel, and every tab the name appears "
        "on -- with its strength percentile (100 = strongest in that layer's full population) and "
        "the facts that tab records. Names in priority order.")))
    ts.merge_cells("A2:C2")
    ts.row_dimensions[2].height = 30
    r = 4
    done = 0
    for t in names:
        if done >= max_names or t not in where:
            continue
        sym = (sym_map or {}).get(t, t)
        f = fin.get(sym) or {}
        done += 1
        nm = f.get("name")
        if not nm:                                # no FMP record: take the name from the tab itself
            ws0, r0, c0 = where[t][0]
            nc = c0.get("Name") or c0.get("Company")
            nm = ws0.cell(row=r0, column=nc).value if nc else ""
        meta = " · ".join(x for x in [f.get("sector"), f.get("country"),
                                      f"mcap ${(f.get('mcap') or 0) / 1e6:,.0f}M" if f.get("mcap") else None,
                                      f"price {f.get('price')}" if f.get("price") else None] if x)
        # name line styled as a table header (the book's header rule), meta as subtitle
        for j in (1, 2, 3):
            k.header(ts.cell(row=r, column=j))
        ts.cell(row=r, column=1, value=f"{t}  —  {nm or ''}")
        if k.header_height:
            ts.row_dimensions[r].height = k.header_height
        r += 1
        if meta:
            k.subtitle(ts.cell(row=r, column=1, value=meta), wrap=False)
            r += 1
        i = 0
        if f.get("read"):
            i += 1
            k.body(ts.cell(row=r, column=1, value="Financial read"), band=False, bold=True)
            k.body(ts.cell(row=r, column=2, value=f.get("read") + (
                "  [" + "; ".join(f["flags"]) + "]" if f.get("flags") else "")), band=False)
            k.body(ts.cell(row=r, column=3), band=False)
            ts.merge_cells(start_row=r, start_column=2, end_row=r, end_column=3)
            r += 1
        cells = [(lab, fmt.format(f[kk])) for lab, kk, fmt in METRICS
                 if f.get(kk) is not None and not (kk == "int_cover" and f[kk] == 0)]
        for p0 in range(0, len(cells), 2):
            i += 1
            band = i % 2 == 0
            pair = cells[p0:p0 + 2]
            k.body(ts.cell(row=r, column=1, value=pair[0][0]), band=band, bold=True)
            k.body(ts.cell(row=r, column=2, value=pair[0][1]), band=band)
            k.body(ts.cell(row=r, column=3, value=(f"{pair[1][0]}: {pair[1][1]}" if len(pair) > 1 else None)),
                   band=band)
            r += 1
        for j, h in enumerate(("Appears on", "Strength %ile", "What that tab says"), 1):
            k.header(ts.cell(row=r, column=j, value=h))
        r += 1
        for i2, (ws, row, cols) in enumerate(where[t], 1):
            band = i2 % 2 == 0
            k.body(ts.cell(row=r, column=1, value=ws.title), band=band, bold=True)
            st = cols.get("Strength %ile")
            k.body(ts.cell(row=r, column=2, value=ws.cell(row=row, column=st).value if st else None), band=band)
            k.body(ts.cell(row=r, column=3, value=_row_facts(ws, row, cols)), band=band, wrap=True)
            ts.row_dimensions[r].height = 30
            r += 1
        r += 1
    ts.freeze_panes = "A4"
    return done
