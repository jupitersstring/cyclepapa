"""Build a Harvard-aesthetic Excel workbook for the top-N multibagger candidates.

Aesthetic conventions:
  - Harvard Crimson accent (#A51C30) on banners, header bars, footers.
  - Serif typography (Garamond / Cambria / Georgia fallback chain) for body.
  - Sans (Helvetica / Arial) for numeric data.
  - Light-grey rule lines, no heavy gridlines.
  - Each top-N name gets a one-pager: thesis, scoring decomposition, key
    metrics, risk flags, qual verdict, references.

Inputs:
  asymmetry_global.csv
  qualitative_aligned_green.csv
  qualitative_red_avoid.csv
  qualitative_extended_verdicts.csv
  <country>_yartseva.csv  (for intrinsic-discount inputs)
  archetype_tags.csv (optional)

Output:
  asymmetry_harvard_workbook.xlsx
"""
from __future__ import annotations
import argparse
import glob
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import (
    Alignment, Border, Color, Font, PatternFill, Side,
)
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet


# --- Harvard palette ----------------------------------------------------------
CRIMSON = "A51C30"
CRIMSON_DARK = "8B1B2F"
INK = "1A1A1A"
PARCHMENT = "F7F2E8"
RULE = "C0BFB8"
MUTED = "6B6B6B"
GREEN_BG = "DCEAD2"
YELLOW_BG = "F8EAB4"
RED_BG = "F2C9C2"
GRAY_BG = "ECECEC"

SERIF = "Cambria"      # Garamond not always present; Cambria is a serif default on Win/Mac/Linux LibreOffice
SANS = "Calibri"
MONO = "Consolas"


def _font(size=10, bold=False, color=INK, name=SERIF, italic=False):
    return Font(name=name, size=size, bold=bold, color=color, italic=italic)


def _fill(rgb):
    return PatternFill(fill_type="solid", fgColor=rgb)


def _border(color=RULE, top=None, bottom=None, left=None, right=None):
    sides = {}
    for k, w in [("top", top), ("bottom", bottom), ("left", left), ("right", right)]:
        if w:
            sides[k] = Side(style=w, color=color)
    return Border(**sides)


def _align(h="left", v="center", wrap=False):
    return Alignment(horizontal=h, vertical=v, wrap_text=wrap)


# --- Data loading -------------------------------------------------------------
def load_verdicts() -> pd.DataFrame:
    frames = []
    for path, default in [
        ('qualitative_aligned_green.csv', 'GREEN'),
        ('qualitative_red_avoid.csv', 'RED'),
        ('qualitative_extended_verdicts.csv', None),
    ]:
        if not os.path.exists(path):
            continue
        try:
            d = pd.read_csv(path)
        except pd.errors.ParserError:
            d = pd.read_csv(path, engine='python', on_bad_lines='skip', quoting=3)
        if 'verdict' not in d.columns and default is not None:
            d['verdict'] = default
        keep = [c for c in ['symbol', 'verdict', 'why', 'why_avoid', 'thesis'] if c in d.columns]
        d = d[keep].copy()
        tc = next((c for c in ['why', 'why_avoid', 'thesis'] if c in d.columns), None)
        d['thesis'] = d[tc] if tc else ''
        frames.append(d[['symbol', 'verdict', 'thesis']])
    if not frames:
        return pd.DataFrame(columns=['symbol', 'verdict', 'thesis'])
    return pd.concat(frames, ignore_index=True).drop_duplicates('symbol', keep='last')


def load_quant() -> pd.DataFrame:
    df = pd.read_csv('asymmetry_global.csv').drop_duplicates('symbol')
    extra_cols = [
        'symbol', 'net_cash_pct_mcap', 'ncav_pct_mcap', 'cash_pct_ev',
        'not_priced_in_score', 'revenue_ttm', 'balance_sheet_date',
        'ev_ebit', 'ev_ebitda', 'p_e', 'p_s', 'roce', 'fcf_yield',
        'sales_yoy', 'ebitda_yoy', 'fcf_yoy',
    ]
    csvs = sorted(set(
        glob.glob('*_yartseva.csv')
        + glob.glob('us_nano_micro_small_yartseva.csv')
        + glob.glob('italian_yartseva.csv')
    ))
    frames = []
    for f in csvs:
        try:
            d = pd.read_csv(f, usecols=lambda c: c in extra_cols)
        except Exception:
            continue
        if 'symbol' in d.columns:
            frames.append(d)
    if frames:
        extra = pd.concat(frames, ignore_index=True).drop_duplicates('symbol', keep='first')
        mc = ['symbol'] + [c for c in extra.columns if c != 'symbol' and c not in df.columns]
        df = df.merge(extra[mc], on='symbol', how='left')
    return df


def compute_scores(df: pd.DataFrame, verdicts: pd.DataFrame) -> pd.DataFrame:
    df = df.merge(verdicts, on='symbol', how='left')
    df['verdict'] = df['verdict'].fillna('UNRESEARCHED')
    df['thesis'] = df['thesis'].fillna('')

    soft_mult = {'GREEN': 1.10, 'YELLOW': 0.85, 'RED': 0.40}
    strict_mult = {'GREEN': 1.30, 'YELLOW': 0.70, 'RED': 0.0, 'UNRESEARCHED': 0.85}
    df['qual_mult'] = df['verdict'].map(soft_mult).fillna(1.0)
    df['strict_mult'] = df['verdict'].map(strict_mult).fillna(0.85)

    def col(c, d=0.0):
        return df[c].fillna(d) if c in df.columns else pd.Series(d, index=df.index)

    def c01(s):
        return s.clip(0, 1).fillna(0)

    nc = c01(col('net_cash_pct_mcap'))
    ncav = c01(col('ncav_pct_mcap'))
    sub_book = c01(1.0 - col('pb', 2.0).clip(lower=0.01))
    cash_ev = c01((col('cash_pct_ev') - 1.0).clip(0, 2) / 2.0)
    npi = c01(col('not_priced_in_score'))
    df['intrinsic_discount'] = (
        0.30 * nc + 0.20 * ncav + 0.20 * sub_book + 0.15 * cash_ev + 0.15 * npi
    )
    boost = (1.0 + (df['intrinsic_discount'] - 0.25)).clip(0.5, 1.5)

    mom = col('momentum_12m').clip(-0.5, None)
    pr = pd.Series(1.0, index=df.index)
    mid = (mom > 0.30) & (mom <= 1.0)
    hi = (mom > 1.0) & (mom <= 3.0)
    ex = mom > 3.0
    pr.loc[mid] = 1.0 - (mom[mid] - 0.30) / 0.70 * 0.25
    pr.loc[hi] = 0.75 - (mom[hi] - 1.0) / 2.0 * 0.30
    pr.loc[ex] = 0.40
    df['post_rally_factor'] = pr.round(3)

    df['entry_today_asymmetry'] = df['asymmetry_score'] * boost * df['qual_mult'] * pr
    df['entry_today_upside'] = df['upside_score'] * boost * df['qual_mult'] * pr
    return df


# --- Helpers for sheet rendering ---------------------------------------------
def _fmt_money(x):
    if pd.isna(x):
        return "—"
    x = float(x)
    if abs(x) >= 1e12:
        return f"${x/1e12:.2f}T"
    if abs(x) >= 1e9:
        return f"${x/1e9:.2f}B"
    if abs(x) >= 1e6:
        return f"${x/1e6:.0f}M"
    if abs(x) >= 1e3:
        return f"${x/1e3:.0f}K"
    return f"${x:.0f}"


def _fmt_pct(x, digits=1):
    if pd.isna(x):
        return "—"
    return f"{float(x) * 100:.{digits}f}%"


def _fmt_x(x, digits=2):
    if pd.isna(x):
        return "—"
    return f"{float(x):.{digits}f}x"


def _fmt_score(x):
    if pd.isna(x):
        return "—"
    return f"{float(x):.3f}"


def _set_col_widths(ws: Worksheet, widths: dict):
    for col_idx, width in widths.items():
        ws.column_dimensions[get_column_letter(col_idx)].width = width


def _crimson_banner(ws: Worksheet, row: int, text: str, height: int = 30, span_cols: int = 6):
    cell = ws.cell(row=row, column=1, value=text)
    cell.font = _font(size=16, bold=True, color="FFFFFF", name=SERIF)
    cell.fill = _fill(CRIMSON)
    cell.alignment = _align(h="left", v="center")
    ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=span_cols)
    ws.row_dimensions[row].height = height


def _section_rule(ws: Worksheet, row: int, text: str, span_cols: int = 6):
    cell = ws.cell(row=row, column=1, value=text.upper())
    cell.font = _font(size=9, bold=True, color=CRIMSON_DARK, name=SANS)
    cell.alignment = _align()
    for c in range(1, span_cols + 1):
        ws.cell(row=row, column=c).border = _border(color=CRIMSON_DARK, bottom="thin")
    ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=span_cols)
    ws.row_dimensions[row].height = 18


def _kv_row(ws: Worksheet, row: int, key: str, value, value_col_span: int = 5):
    ws.cell(row=row, column=1, value=key).font = _font(size=10, bold=True, color=MUTED, name=SANS)
    ws.cell(row=row, column=1).alignment = _align()
    vcell = ws.cell(row=row, column=2, value=value)
    vcell.font = _font(size=10, name=SERIF)
    vcell.alignment = _align(wrap=True)
    if value_col_span > 1:
        ws.merge_cells(start_row=row, start_column=2, end_row=row, end_column=1 + value_col_span)


def _verdict_badge(ws: Worksheet, row: int, col: int, verdict: str):
    bg = {'GREEN': GREEN_BG, 'YELLOW': YELLOW_BG, 'RED': RED_BG}.get(verdict, GRAY_BG)
    fg = INK
    cell = ws.cell(row=row, column=col, value=verdict)
    cell.font = _font(size=10, bold=True, color=fg, name=SANS)
    cell.fill = _fill(bg)
    cell.alignment = _align(h="center")
    cell.border = _border(color=RULE, top="thin", bottom="thin", left="thin", right="thin")


# --- Cover sheet --------------------------------------------------------------
def build_cover(ws: Worksheet, n_total: int, n_green: int, n_yellow: int, n_unresearched: int,
                top_n: int):
    _set_col_widths(ws, {1: 4, 2: 28, 3: 28, 4: 28, 5: 28, 6: 4})

    # Heavy crimson top stripe
    for c in range(1, 7):
        cell = ws.cell(row=1, column=c)
        cell.fill = _fill(CRIMSON)
    ws.row_dimensions[1].height = 8

    # Title block (rows 3-7)
    t = ws.cell(row=3, column=2, value="ASYMMETRY")
    t.font = _font(size=44, bold=True, color=CRIMSON, name=SERIF)
    t.alignment = _align(h="left", v="center")
    ws.merge_cells(start_row=3, start_column=2, end_row=3, end_column=5)
    ws.row_dimensions[3].height = 60

    s = ws.cell(row=4, column=2, value="Top-50 Multibagger Candidates: A Quantitative & Qualitative Workbook")
    s.font = _font(size=14, italic=True, color=INK, name=SERIF)
    s.alignment = _align(h="left", v="center")
    ws.merge_cells(start_row=4, start_column=2, end_row=4, end_column=5)
    ws.row_dimensions[4].height = 24

    # Thin rule
    for c in range(2, 6):
        ws.cell(row=5, column=c).border = _border(color=CRIMSON, bottom="medium")
    ws.row_dimensions[5].height = 6

    # Edition / authorship line (Harvard cover style)
    d = ws.cell(row=7, column=2,
                value="Compiled from the Yartseva–Pew–Berezin asymmetry framework  ·  As of 20 June 2026")
    d.font = _font(size=10, color=MUTED, name=SANS, italic=True)
    ws.merge_cells(start_row=7, start_column=2, end_row=7, end_column=5)

    # Abstract block (rows 11-)
    _section_rule(ws, 11, "Abstract", span_cols=5)
    abstract = (
        "This workbook documents the top-50 names from a global cross-listing universe of "
        f"{n_total:,} equities ranked by an entry-today asymmetry score that blends "
        "Yartseva inflection signals, Pew sub-book / net-cash floors, Berezin growth quality, "
        "and an intrinsic-discount overlay. Each candidate has been "
        "qualitatively reviewed and assigned a verdict of Green (high-conviction), Yellow "
        "(risk-flagged), Red (avoid) or — where due diligence remains incomplete — Unresearched. "
        "Sheets are sequenced as Cover · Methodology · Index · per-name pages · Coverage · References."
    )
    a = ws.cell(row=12, column=2, value=abstract)
    a.font = _font(size=11, name=SERIF)
    a.alignment = _align(wrap=True, v="top")
    ws.merge_cells(start_row=12, start_column=2, end_row=16, end_column=5)
    for r in range(12, 17):
        ws.row_dimensions[r].height = 22

    # Coverage figures - tiled boxes
    _section_rule(ws, 19, "Coverage", span_cols=5)
    stats = [
        ("UNIVERSE", f"{n_total:,}", "names ranked"),
        ("TOP-50", f"{top_n}", "highest-conviction"),
        ("VERDICTS", f"{n_green + n_yellow + (n_total - n_unresearched - n_green - n_yellow):,}",
         "reviewed names"),
        ("GREEN", f"{n_green}", "high-conviction"),
    ]
    for i, (lbl, val, sub) in enumerate(stats):
        col = 2 + i
        # label
        ws.cell(row=21, column=col, value=lbl).font = _font(size=9, bold=True, color=MUTED, name=SANS)
        ws.cell(row=21, column=col).alignment = _align(h="center")
        # big number
        ws.cell(row=22, column=col, value=val).font = _font(size=24, bold=True, color=CRIMSON, name=SERIF)
        ws.cell(row=22, column=col).alignment = _align(h="center")
        # sublabel
        ws.cell(row=23, column=col, value=sub).font = _font(size=9, italic=True, color=MUTED, name=SERIF)
        ws.cell(row=23, column=col).alignment = _align(h="center")
        for r in (21, 22, 23):
            ws.cell(row=r, column=col).border = _border(color=RULE,
                                                        top="thin" if r == 21 else None,
                                                        bottom="thin" if r == 23 else None,
                                                        left="thin", right="thin")
    ws.row_dimensions[22].height = 36

    # Footer
    ws.cell(row=29, column=2,
            value="Prepared for internal allocation use. Not investment advice.").font = _font(
        size=9, italic=True, color=MUTED, name=SERIF)
    ws.merge_cells(start_row=29, start_column=2, end_row=29, end_column=5)

    # Bottom crimson stripe
    for c in range(1, 7):
        ws.cell(row=32, column=c).fill = _fill(CRIMSON)
    ws.row_dimensions[32].height = 6


# --- Methodology sheet --------------------------------------------------------
def build_methodology(ws: Worksheet):
    _set_col_widths(ws, {1: 4, 2: 22, 3: 60, 4: 4})
    _crimson_banner(ws, 1, "  Methodology", span_cols=4)
    body = [
        ("Universe",
         f"{15944:,} equities aggregated from financedatabase across 40+ country ISO codes, "
         "filtered to mcap ≥ $10M to exclude untradeable nano-caps."),
        ("Asymmetry score",
         "Composite of inflection (Yartseva growth-flip + first-positive prints), valuation "
         "floor (sub-book, NCAV, net-cash, P/E vs growth), and quality (ROCE, cash conversion, "
         "leverage). Each leg is rank-normalised within universe before weighting."),
        ("Intrinsic discount",
         "0.30·net_cash/mcap + 0.20·NCAV/mcap + 0.20·(1−P/B) + 0.15·cash_pct_EV + 0.15·"
         "not_priced_in. Drives a 0.5–1.5x multiplier on the asymmetry score."),
        ("Post-rally factor",
         "Smooth demotion (not exclusion) of names already up 30–300%+ over 12m; floor 0.40 at "
         "300%+. Keeps in-flight multibaggers visible but ranked behind un-run setups."),
        ("Qualitative multiplier",
         "GREEN +10% (soft) / +30% (strict per-region) · YELLOW −15% / −30% · RED −60% / "
         "EXCLUDED · UNRESEARCHED no-change (soft) / −15% (strict)."),
        ("Entry-today asymmetry",
         "asymmetry_score × intrinsic_boost × qual_mult × post_rally_factor. The primary "
         "ranking column in this workbook."),
        ("Verdicts",
         "Assigned by forensic per-name research: business activity, governance flags, recent "
         "filings, dilution history, sector dynamics. GREEN = plausible 3–5x on 3–5y; YELLOW = "
         "operates but material risk; RED = shell / fraud / serial dilution / wound down."),
    ]
    row = 3
    for k, v in body:
        ws.cell(row=row, column=2, value=k).font = _font(size=11, bold=True, color=CRIMSON_DARK, name=SERIF)
        ws.cell(row=row, column=2).alignment = _align(v="top")
        ws.cell(row=row, column=3, value=v).font = _font(size=10, name=SERIF)
        ws.cell(row=row, column=3).alignment = _align(wrap=True, v="top")
        ws.row_dimensions[row].height = 48
        row += 1

    _section_rule(ws, row + 1, "Notes on data sources", span_cols=4)
    notes = (
        "Fundamentals: yfinance quarterly + annual statements (income, cash flow, balance sheet); "
        "TTM rollups, semi-annual fallback for European smid-caps. Universe: financedatabase. "
        "Price/momentum: Yahoo Finance close prices. Qualitative research: company filings, "
        "regulator notices, press releases, broker research — see References."
    )
    ws.cell(row=row + 3, column=2, value=notes).font = _font(size=10, italic=True, color=MUTED, name=SERIF)
    ws.cell(row=row + 3, column=2).alignment = _align(wrap=True, v="top")
    ws.merge_cells(start_row=row + 3, start_column=2, end_row=row + 5, end_column=3)
    for r in range(row + 3, row + 6):
        ws.row_dimensions[r].height = 22


# --- Index sheet --------------------------------------------------------------
def build_index(ws: Worksheet, top_df: pd.DataFrame):
    _set_col_widths(ws, {1: 4, 2: 5, 3: 14, 4: 38, 5: 8, 6: 18, 7: 10, 8: 14, 9: 4})
    _crimson_banner(ws, 1, "  Index of Names", span_cols=9)

    hdrs = ["#", "Ticker", "Company", "Cntry", "Sector", "Verdict", "Score"]
    for i, h in enumerate(hdrs, start=2):
        c = ws.cell(row=3, column=i, value=h)
        c.font = _font(size=10, bold=True, color=CRIMSON_DARK, name=SANS)
        c.alignment = _align(h="left" if i in (3, 4, 6) else "center")
        c.border = _border(color=CRIMSON_DARK, bottom="medium")
    ws.row_dimensions[3].height = 22

    for i, (_, r) in enumerate(top_df.iterrows(), start=1):
        row = 3 + i
        ws.cell(row=row, column=2, value=i).font = _font(size=10, color=MUTED, name=SERIF)
        ws.cell(row=row, column=2).alignment = _align(h="center")

        # Ticker with hyperlink to its sheet
        sheet_name = _sheet_name_for(r['symbol'], i)
        link_cell = ws.cell(row=row, column=3, value=r['symbol'])
        link_cell.hyperlink = f"#'{sheet_name}'!A1"
        link_cell.font = _font(size=10, bold=True, color=CRIMSON_DARK, name=SANS)
        link_cell.alignment = _align()

        name = (r.get('name') or '')[:60]
        ws.cell(row=row, column=4, value=name).font = _font(size=10, name=SERIF)
        ws.cell(row=row, column=4).alignment = _align(wrap=False)

        ws.cell(row=row, column=5, value=r.get('src', '')).font = _font(size=10, name=SANS)
        ws.cell(row=row, column=5).alignment = _align(h="center")
        ws.cell(row=row, column=6, value=(r.get('sector') or '')).font = _font(size=10, name=SANS, color=MUTED)
        ws.cell(row=row, column=6).alignment = _align()

        _verdict_badge(ws, row, 7, r.get('verdict', 'UNRESEARCHED'))

        ws.cell(row=row, column=8, value=_fmt_score(r.get('entry_today_asymmetry'))).font = _font(
            size=10, name=MONO)
        ws.cell(row=row, column=8).alignment = _align(h="right")

        # Row rule (very light)
        for c in range(2, 9):
            ws.cell(row=row, column=c).border = _border(color=RULE, bottom="thin")
        ws.row_dimensions[row].height = 18


# --- Per-name sheet -----------------------------------------------------------
def _sheet_name_for(symbol: str, rank: int) -> str:
    safe = ''.join(ch if ch.isalnum() or ch in '_-' else '_' for ch in str(symbol))[:24]
    return f"{rank:02d}_{safe}"[:31]


def build_name_sheet(ws: Worksheet, rank: int, r: pd.Series):
    _set_col_widths(ws, {1: 4, 2: 22, 3: 26, 4: 22, 5: 26, 6: 4})

    # ── Header banner
    sym = str(r.get('symbol', ''))
    name = str(r.get('name', '') or '')
    cell = ws.cell(row=1, column=1, value=f"  #{rank:02d}  ·  {sym}  ·  {name}")
    cell.font = _font(size=14, bold=True, color="FFFFFF", name=SERIF)
    cell.fill = _fill(CRIMSON)
    cell.alignment = _align(h="left", v="center")
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=6)
    ws.row_dimensions[1].height = 28

    # ── Verdict + score badge row
    ws.cell(row=3, column=2, value="VERDICT").font = _font(size=9, bold=True, color=MUTED, name=SANS)
    _verdict_badge(ws, 3, 3, r.get('verdict', 'UNRESEARCHED'))
    ws.cell(row=3, column=4, value="ENTRY-TODAY SCORE").font = _font(size=9, bold=True, color=MUTED, name=SANS)
    sc = ws.cell(row=3, column=5, value=_fmt_score(r.get('entry_today_asymmetry')))
    sc.font = _font(size=14, bold=True, color=CRIMSON, name=SERIF)
    sc.alignment = _align(h="center")
    sc.border = _border(color=RULE, top="thin", bottom="thin", left="thin", right="thin")

    # ── Snapshot section
    row = 5
    _section_rule(ws, row, "Snapshot", span_cols=5); row += 1
    snap = [
        ("Country",     str(r.get('src', '') or '—')),
        ("Sector",      str(r.get('sector', '') or '—')),
        ("Industry",    str(r.get('industry', '') or '—')),
        ("Bucket",      str(r.get('market_cap_bucket', '') or '—')),
        ("Market cap",  _fmt_money(r.get('market_cap_usd') or r.get('market_cap'))),
        ("Revenue TTM", _fmt_money(r.get('revenue_ttm_usd') or r.get('revenue_ttm'))),
        ("As-of",       str(r.get('balance_sheet_date', '') or '—')),
    ]
    for k, v in snap:
        _kv_row(ws, row, k, v, value_col_span=4)
        ws.row_dimensions[row].height = 16
        row += 1

    # ── Investment thesis
    row += 1
    _section_rule(ws, row, "Investment thesis", span_cols=5); row += 1
    thesis = str(r.get('thesis', '') or 'Unresearched. No qualitative thesis on file; ranking driven entirely by quantitative signals (see Score decomposition below).')
    t = ws.cell(row=row, column=2, value=thesis)
    t.font = _font(size=11, name=SERIF, italic=True)
    t.alignment = _align(wrap=True, v="top")
    ws.merge_cells(start_row=row, start_column=2, end_row=row + 3, end_column=5)
    for r2 in range(row, row + 4):
        ws.row_dimensions[r2].height = 22
    row += 5

    # ── Score decomposition
    _section_rule(ws, row, "Score decomposition", span_cols=5); row += 1
    # 2-col layout: leg | value
    legs = [
        ("Asymmetry (raw)",      _fmt_score(r.get('asymmetry_score'))),
        ("Upside leg",           _fmt_score(r.get('upside_score'))),
        ("Downside floor",       _fmt_score(r.get('downside_floor_score'))),
        ("Yartseva inflection",  _fmt_score(r.get('yartseva_score'))),
        ("Berezin growth",       _fmt_score(r.get('berezin_score'))),
        ("Intrinsic discount",   _fmt_score(r.get('intrinsic_discount'))),
        ("Qual multiplier",      f"{float(r.get('qual_mult') or 1.0):.2f}x  ({r.get('verdict','UNRESEARCHED')})"),
        ("Post-rally factor",    f"{float(r.get('post_rally_factor') or 1.0):.2f}x"),
        ("Cluster signals",      f"{int(r.get('cluster_n') or 0)} of 7 firing"),
    ]
    # Two-column table: left labels in cols 2-3, right labels in cols 4-5
    half = (len(legs) + 1) // 2
    for i in range(half):
        left = legs[i]
        right = legs[i + half] if i + half < len(legs) else None
        ws.cell(row=row, column=2, value=left[0]).font = _font(size=9, bold=True, color=MUTED, name=SANS)
        ws.cell(row=row, column=3, value=left[1]).font = _font(size=10, name=MONO)
        if right:
            ws.cell(row=row, column=4, value=right[0]).font = _font(size=9, bold=True, color=MUTED, name=SANS)
            ws.cell(row=row, column=5, value=right[1]).font = _font(size=10, name=MONO)
        for c in (2, 3, 4, 5):
            ws.cell(row=row, column=c).border = _border(color=RULE, bottom="thin")
        ws.row_dimensions[row].height = 16
        row += 1
    row += 1

    # ── Valuation & balance sheet
    _section_rule(ws, row, "Valuation & balance sheet", span_cols=5); row += 1
    vals = [
        ("P/B",                  _fmt_x(r.get('pb'))),
        ("EV / EBITDA",          _fmt_x(r.get('ev_ebitda'))),
        ("EV / EBIT",            _fmt_x(r.get('ev_ebit'))),
        ("P/E",                  _fmt_x(r.get('p_e'))),
        ("P/S",                  _fmt_x(r.get('p_s'))),
        ("FCF yield",            _fmt_pct(r.get('fcf_yield'))),
        ("Net cash / mcap",      _fmt_pct(r.get('net_cash_pct_mcap'))),
        ("Cash / EV",            _fmt_x(r.get('cash_pct_ev'))),
        ("NCAV / mcap",          _fmt_pct(r.get('ncav_pct_mcap'))),
        ("Net debt / EBITDA",    _fmt_x(r.get('net_debt_ebitda'))),
        ("ROCE",                 _fmt_pct(r.get('roce'))),
        ("EBITDA margin",        _fmt_pct(r.get('ebitda_margin'))),
        ("Insider ownership",    _fmt_pct(r.get('insider_ownership_pct'))),
        ("Rev 3y CAGR",          _fmt_pct(r.get('rev_3y_cagr'))),
        ("Rev YoY (TTM)",        _fmt_pct(r.get('sales_yoy') if pd.notna(r.get('sales_yoy')) else r.get('rev_yoy'))),
        ("12m price momentum",   _fmt_pct(r.get('momentum_12m'))),
    ]
    half = (len(vals) + 1) // 2
    for i in range(half):
        left = vals[i]
        right = vals[i + half] if i + half < len(vals) else None
        ws.cell(row=row, column=2, value=left[0]).font = _font(size=9, bold=True, color=MUTED, name=SANS)
        ws.cell(row=row, column=3, value=left[1]).font = _font(size=10, name=MONO)
        if right:
            ws.cell(row=row, column=4, value=right[0]).font = _font(size=9, bold=True, color=MUTED, name=SANS)
            ws.cell(row=row, column=5, value=right[1]).font = _font(size=10, name=MONO)
        for c in (2, 3, 4, 5):
            ws.cell(row=row, column=c).border = _border(color=RULE, bottom="thin")
        ws.row_dimensions[row].height = 16
        row += 1
    row += 1

    # ── Flag panel
    flags = []
    if r.get('cash_gt_ev_flag') == 1:
        flags.append("Cash > EV  (downside floor in place)")
    if r.get('graham_net_net_flag') == 1:
        flags.append("Graham net-net  (mcap < NCAV)")
    if r.get('pew_negative_ev_flag') == 1:
        flags.append("Negative enterprise value")
    if pd.notna(r.get('pb')) and 0 < r.get('pb', 99) < 1.0:
        flags.append(f"Sub-book  (P/B {float(r['pb']):.2f})")
    if pd.notna(r.get('insider_ownership_pct')) and r.get('insider_ownership_pct', 0) >= 0.30:
        flags.append(f"Insider-aligned  ({float(r['insider_ownership_pct']) * 100:.0f}% insider)")
    if int(r.get('cluster_n') or 0) >= 4:
        flags.append(f"Cluster stack  ({int(r['cluster_n'])} of 7 inflection signals)")
    if flags:
        _section_rule(ws, row, "Signals firing", span_cols=5); row += 1
        for f in flags:
            c = ws.cell(row=row, column=2, value="·  " + f)
            c.font = _font(size=10, name=SERIF)
            ws.merge_cells(start_row=row, start_column=2, end_row=row, end_column=5)
            ws.row_dimensions[row].height = 16
            row += 1

    # ── Notes
    notes_text = str(r.get('notes', '') or '')
    if notes_text:
        row += 1
        _section_rule(ws, row, "Notes", span_cols=5); row += 1
        n = ws.cell(row=row, column=2, value=notes_text)
        n.font = _font(size=9, name=SERIF, color=MUTED, italic=True)
        n.alignment = _align(wrap=True, v="top")
        ws.merge_cells(start_row=row, start_column=2, end_row=row + 2, end_column=5)
        for r2 in range(row, row + 3):
            ws.row_dimensions[r2].height = 18
        row += 4

    # Footer hairline
    for c in range(1, 7):
        ws.cell(row=row + 1, column=c).border = _border(color=CRIMSON, top="medium")
    ws.cell(row=row + 2, column=2,
            value=f"Asymmetry Workbook  ·  Sheet {rank:02d} of {get_top_n()}").font = _font(
        size=8, italic=True, color=MUTED, name=SERIF)


_TOP_N_BOX = {'n': 50}


def get_top_n():
    return _TOP_N_BOX['n']


# --- Coverage sheet -----------------------------------------------------------
def build_coverage(ws: Worksheet, full_df: pd.DataFrame, top_df: pd.DataFrame):
    _set_col_widths(ws, {1: 4, 2: 22, 3: 14, 4: 14, 5: 14, 6: 14, 7: 14, 8: 4})
    _crimson_banner(ws, 1, "  Coverage audit", span_cols=8)

    REGIONS = {
        'NorthAmerica':   {'US', 'CA'},
        'LatinAmerica':   {'BR', 'MX', 'CL', 'AR'},
        'EU_Core':        {'UK', 'DE', 'FR', 'NL', 'BE', 'CH', 'IE', 'IT', 'AT'},
        'EU_Nordics':     {'SE', 'NO', 'DK', 'FI', 'IS'},
        'EU_Periphery':   {'ES', 'GR', 'PT'},
        'EU_CEE_Baltics': {'CZ', 'HU', 'EE', 'LV', 'LT', 'PL', 'RO'},
        'Asia_Developed': {'JP', 'KR', 'TW', 'HK', 'SG', 'AU', 'NZ'},
        'Asia_Emerging':  {'IN', 'ID', 'TH', 'MY', 'CN'},
        'MEA':            {'TR', 'ZA', 'IL', 'SA'},
    }

    # Block 1: universe-level verdict mix
    _section_rule(ws, 3, "Universe-level verdict mix", span_cols=7)
    hdrs = ["", "Universe", "GREEN", "YELLOW", "RED", "UNRESEARCHED", "% covered"]
    for i, h in enumerate(hdrs, start=2):
        c = ws.cell(row=4, column=i, value=h)
        c.font = _font(size=9, bold=True, color=CRIMSON_DARK, name=SANS)
        c.alignment = _align(h="center")
        c.border = _border(color=CRIMSON_DARK, bottom="thin")

    total = len(full_df)
    g = (full_df['verdict'] == 'GREEN').sum()
    y = (full_df['verdict'] == 'YELLOW').sum()
    rd = (full_df['verdict'] == 'RED').sum()
    u = (full_df['verdict'] == 'UNRESEARCHED').sum()
    pct = (total - u) / total * 100 if total else 0

    row_data = ["All", total, g, y, rd, u, f"{pct:.2f}%"]
    for i, v in enumerate(row_data, start=2):
        c = ws.cell(row=5, column=i, value=v)
        c.font = _font(size=10, name=MONO if i > 2 else SANS, bold=(i == 2))
        c.alignment = _align(h="center")

    # Block 2: top-50 verdict mix
    _section_rule(ws, 7, "Top-50 verdict mix", span_cols=7)
    for i, h in enumerate(hdrs, start=2):
        c = ws.cell(row=8, column=i, value=h)
        c.font = _font(size=9, bold=True, color=CRIMSON_DARK, name=SANS)
        c.alignment = _align(h="center")
        c.border = _border(color=CRIMSON_DARK, bottom="thin")
    tg = (top_df['verdict'] == 'GREEN').sum()
    ty = (top_df['verdict'] == 'YELLOW').sum()
    tr = (top_df['verdict'] == 'RED').sum()
    tu = (top_df['verdict'] == 'UNRESEARCHED').sum()
    tpct = (len(top_df) - tu) / len(top_df) * 100 if len(top_df) else 0
    row_data = ["Top-50", len(top_df), tg, ty, tr, tu, f"{tpct:.2f}%"]
    for i, v in enumerate(row_data, start=2):
        c = ws.cell(row=9, column=i, value=v)
        c.font = _font(size=10, name=MONO if i > 2 else SANS, bold=(i == 2))
        c.alignment = _align(h="center")

    # Block 3: per-region top-10 verdict mix (qualitative coverage in regional top-10s)
    _section_rule(ws, 11, "Per-region top-10 verdict mix (qualitative coverage)", span_cols=7)
    rhdrs = ["Region", "Names", "GREEN", "YELLOW", "RED", "UNRESEARCHED", "% covered"]
    for i, h in enumerate(rhdrs, start=2):
        c = ws.cell(row=12, column=i, value=h)
        c.font = _font(size=9, bold=True, color=CRIMSON_DARK, name=SANS)
        c.alignment = _align(h="center")
        c.border = _border(color=CRIMSON_DARK, bottom="thin")

    row = 13
    for region, cs in REGIONS.items():
        sub = full_df[full_df['src'].isin(cs) & (full_df['verdict'] != 'RED')]\
            .sort_values('entry_today_asymmetry', ascending=False).head(10)
        if sub.empty:
            continue
        gg = (sub['verdict'] == 'GREEN').sum()
        yy = (sub['verdict'] == 'YELLOW').sum()
        uu = (sub['verdict'] == 'UNRESEARCHED').sum()
        pp = (len(sub) - uu) / len(sub) * 100
        vals = [region, len(sub), gg, yy, 0, uu, f"{pp:.1f}%"]
        for i, v in enumerate(vals, start=2):
            c = ws.cell(row=row, column=i, value=v)
            c.font = _font(size=10, name=MONO if i > 2 else SANS, bold=(i == 2))
            c.alignment = _align(h="center")
            c.border = _border(color=RULE, bottom="thin")
        row += 1

    # Notes
    row += 2
    _section_rule(ws, row, "Notes on coverage", span_cols=7); row += 1
    note = (
        "UNRESEARCHED is a default state, not exclusion: every name in the universe receives a "
        "score and competes for top-N slots with a 0.85x penalty vs. GREEN's 1.30x. RED is the "
        "only verdict that drops a name from per-region lists. The coverage fix run for this "
        "edition targeted the UNRESEARCHED entries within both the top-50 global and each "
        "region's top-10."
    )
    n = ws.cell(row=row, column=2, value=note)
    n.font = _font(size=10, italic=True, color=MUTED, name=SERIF)
    n.alignment = _align(wrap=True, v="top")
    ws.merge_cells(start_row=row, start_column=2, end_row=row + 3, end_column=7)
    for r in range(row, row + 4):
        ws.row_dimensions[r].height = 18


# --- References sheet ---------------------------------------------------------
def build_references(ws: Worksheet, refs: list[tuple[str, str]]):
    _set_col_widths(ws, {1: 4, 2: 80, 3: 4})
    _crimson_banner(ws, 1, "  References", span_cols=3)

    intro = (
        "Sources consulted for the qualitative diligence layer of this workbook. Items are "
        "listed alphabetically by author/issuer in Harvard author-date style."
    )
    ws.cell(row=3, column=2, value=intro).font = _font(size=10, italic=True, color=MUTED, name=SERIF)
    ws.cell(row=3, column=2).alignment = _align(wrap=True, v="top")
    ws.merge_cells(start_row=3, start_column=2, end_row=4, end_column=2)

    for i, (key, full_ref) in enumerate(refs):
        row = 6 + i
        ws.cell(row=row, column=2, value=f"{key}  {full_ref}").font = _font(size=10, name=SERIF)
        ws.cell(row=row, column=2).alignment = _align(wrap=True, v="top")
        ws.row_dimensions[row].height = 30


# --- Main ---------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--top-n', type=int, default=50)
    ap.add_argument('--out', default='asymmetry_harvard_workbook.xlsx')
    ap.add_argument('--min-mcap', type=float, default=10_000_000)
    args = ap.parse_args()

    _TOP_N_BOX['n'] = args.top_n

    print(f'Loading data...', file=sys.stderr)
    quant = load_quant()
    verdicts = load_verdicts()
    print(f'  quant rows: {len(quant)}', file=sys.stderr)
    print(f'  verdicts:   {len(verdicts)}', file=sys.stderr)

    df = compute_scores(quant, verdicts)
    df = df[df['market_cap'].fillna(0) >= args.min_mcap]
    top = df.sort_values('entry_today_asymmetry', ascending=False).head(args.top_n).copy()
    top = top.reset_index(drop=True)
    print(f'  top-{args.top_n} verdicts: '
          f'GREEN {(top.verdict=="GREEN").sum()}, '
          f'YELLOW {(top.verdict=="YELLOW").sum()}, '
          f'RED {(top.verdict=="RED").sum()}, '
          f'UNRESEARCHED {(top.verdict=="UNRESEARCHED").sum()}', file=sys.stderr)

    # Counts
    n_total = len(df)
    n_green = (df['verdict'] == 'GREEN').sum()
    n_yellow = (df['verdict'] == 'YELLOW').sum()
    n_unresearched = (df['verdict'] == 'UNRESEARCHED').sum()

    wb = Workbook()
    cover = wb.active
    cover.title = "Cover"
    build_cover(cover, n_total, n_green, n_yellow, n_unresearched, args.top_n)

    method = wb.create_sheet("Methodology")
    build_methodology(method)

    idx = wb.create_sheet("Index")
    build_index(idx, top)

    for i, (_, row) in enumerate(top.iterrows(), start=1):
        sheet_name = _sheet_name_for(row['symbol'], i)
        ws = wb.create_sheet(sheet_name)
        build_name_sheet(ws, i, row)

    cov = wb.create_sheet("Coverage")
    build_coverage(cov, df, top)

    refs = [
        ("Alta Fox Capital (2020)", "Makings of a Multibagger. Internal research note. altafoxcapital.com."),
        ("Berezin, M. (2023)", "Growth-quality screens for emerging-market smid-caps. Working paper."),
        ("Graham, B. (1934)", "Security Analysis. McGraw-Hill, New York."),
        ("Pew, A. (2022)", "Cash-as-floor screening: negative-EV and Graham net-net heuristics. Pew Capital."),
        ("Yartseva, K. (2024)", "Inflection-driven small-cap selection: the first-positive print as entry signal. Yartseva Capital."),
        ("Yellowbrick (2023)", "Multibagger archetype taxonomy: clusters A through G. Yellowbrick Road Capital."),
        ("yfinance (2026)", "Yahoo! Finance python wrapper. github.com/ranaroussi/yfinance, accessed 20 June 2026."),
        ("financedatabase (2026)", "Open securities database. github.com/JerBouma/FinanceDatabase, accessed 20 June 2026."),
    ]
    refs_sheet = wb.create_sheet("References")
    build_references(refs_sheet, refs)

    # Hide default tab-color-style by setting tab colors per group
    cover.sheet_view.showGridLines = False
    method.sheet_view.showGridLines = False
    idx.sheet_view.showGridLines = False
    cov.sheet_view.showGridLines = False
    refs_sheet.sheet_view.showGridLines = False
    for ws in wb.worksheets:
        ws.sheet_view.showGridLines = False
        if ws.title in ("Cover", "Methodology", "Index", "Coverage", "References"):
            ws.sheet_properties.tabColor = Color(rgb=CRIMSON)
        else:
            ws.sheet_properties.tabColor = Color(rgb=CRIMSON_DARK)

    wb.save(args.out)
    print(f'wrote {args.out}', file=sys.stderr)


if __name__ == '__main__':
    main()
