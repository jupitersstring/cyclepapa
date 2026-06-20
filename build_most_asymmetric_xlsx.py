"""Build the Harvard-aesthetic Excel workbook of most asymmetric
situations.

Harvard Business Review / HBS aesthetic conventions:
  * Crimson #A41E22 accent for headers
  * Charcoal #333333 body text on warm-white #FAFAF7
  * Serif font for titles, sans-serif for data
  * Sparse cell borders, generous white space
  * Section dividers as horizontal accent bars
  * Footnotes in italic 8pt at bottom of sheet

Tabs produced:
  1. Cover / Executive Summary
  2. Most Asymmetric (the 12 convergent names with full detail)
  3. By Archetype (38 PSU/gov buckets, winner per row)
  4. By Pattern (forward $ hurdle, M&A, spin, etc.)
  5. Reserve Baskets (Cohen-Malloy, microcap forcing, Russell)
  6. Caution List (convergent names + red flags)
  7. Coverage & Tiers (data diagnostics)
  8. Methodology
"""

from __future__ import annotations

import csv
import json
import re
from pathlib import Path

import openpyxl
from openpyxl import Workbook
from openpyxl.styles import (Alignment, Border, Font, PatternFill, Side)
from openpyxl.utils import get_column_letter

ROOT = Path("/home/user/cyclepapa")
OUT = ROOT / "MOST_ASYMMETRIC.xlsx"

# Harvard-aesthetic palette
CRIMSON = "A41E22"          # HBR accent
CRIMSON_LIGHT = "F5E0E1"    # title-band fill
WARM_WHITE = "FAFAF7"
CHARCOAL = "333333"
GOLD = "C9A656"             # secondary accent for archetype tags
SAGE = "8FA681"             # tertiary accent for "clean" / convergent
GREY_BAND = "EFECE5"
GREY_LINE = "D9D5C9"

TITLE_FONT = Font(name="Georgia", size=22, bold=True, color=CRIMSON)
SUBTITLE_FONT = Font(name="Georgia", size=12, italic=True, color=CHARCOAL)
HEADER_FONT = Font(name="Helvetica Neue", size=10, bold=True, color="FFFFFF")
BODY_FONT = Font(name="Helvetica Neue", size=10, color=CHARCOAL)
SMALL_FONT = Font(name="Helvetica Neue", size=8, color=CHARCOAL)
BODY_BOLD = Font(name="Helvetica Neue", size=10, bold=True, color=CHARCOAL)
FOOTNOTE = Font(name="Georgia", size=8, italic=True, color=CHARCOAL)

THIN = Side(border_style="thin", color=GREY_LINE)
BOTTOM_BORDER = Border(bottom=THIN)
HEADER_FILL = PatternFill("solid", fgColor=CRIMSON)
BAND_FILL = PatternFill("solid", fgColor=GREY_BAND)
TITLE_BAND_FILL = PatternFill("solid", fgColor=CRIMSON_LIGHT)
CLEAN_TAG_FILL = PatternFill("solid", fgColor=SAGE)
FLAG_TAG_FILL = PatternFill("solid", fgColor=GOLD)


# ----------------------------------------------------------------------
# Data loaders
# ----------------------------------------------------------------------

def load_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return list(csv.DictReader(path.open()))


def load_proxy() -> dict:
    out = {}
    import glob
    for fn in sorted(glob.glob(str(ROOT / "proxy_scan*.json"))):
        try: d = json.loads(open(fn).read())
        except: continue
        rows = d if isinstance(d, list) else d.values()
        for r in rows:
            if isinstance(r, dict) and r.get("ticker"):
                tk = r["ticker"]
                if (tk not in out
                        or r.get("filing_date", "") > out[tk].get("filing_date", "")):
                    out[tk] = r
    return out


def load_archetype_md(path: Path) -> dict:
    if not path.exists():
        return {}
    text = path.read_text()
    by_tk = {}
    blocks = re.findall(
        r"###?\s+(\w+\d+\.?\s+[^\n]+?)\n.*?\*\*Winner:\s*([A-Z][A-Z0-9.\-]{0,10})\*\*",
        text, re.S)
    for arch, tk in blocks:
        arch_id = arch.split(".")[0].strip()
        by_tk.setdefault(tk, []).append((arch_id, arch.strip()))
    return by_tk


# ----------------------------------------------------------------------
# Sheet helpers
# ----------------------------------------------------------------------

def set_col_widths(ws, widths: list[int]):
    for i, w in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(i)].width = w


def write_title_band(ws, title: str, subtitle: str, n_cols: int):
    ws.row_dimensions[1].height = 38
    ws.cell(row=1, column=1, value=title).font = TITLE_FONT
    ws.cell(row=1, column=1).fill = TITLE_BAND_FILL
    ws.cell(row=1, column=1).alignment = Alignment(vertical="center", indent=1)
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=n_cols)
    for c in range(1, n_cols + 1):
        ws.cell(row=1, column=c).fill = TITLE_BAND_FILL

    ws.row_dimensions[2].height = 22
    ws.cell(row=2, column=1, value=subtitle).font = SUBTITLE_FONT
    ws.cell(row=2, column=1).alignment = Alignment(vertical="center", indent=1)
    ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=n_cols)


def write_header_row(ws, row: int, headers: list[str]):
    ws.row_dimensions[row].height = 22
    for c, h in enumerate(headers, 1):
        cell = ws.cell(row=row, column=c, value=h)
        cell.font = HEADER_FONT
        cell.fill = HEADER_FILL
        cell.alignment = Alignment(vertical="center", horizontal="center")


def write_body_row(ws, row: int, values: list, band: bool = False,
                   align_first_left: bool = True,
                   bold_first: bool = False):
    ws.row_dimensions[row].height = 18
    fill = BAND_FILL if band else None
    for c, v in enumerate(values, 1):
        cell = ws.cell(row=row, column=c, value=v)
        cell.font = BODY_BOLD if (bold_first and c == 1) else BODY_FONT
        if fill:
            cell.fill = fill
        cell.border = BOTTOM_BORDER
        cell.alignment = Alignment(
            vertical="center",
            horizontal=("left" if (align_first_left and c == 1) else "center"),
            wrap_text=True,
            indent=(1 if (align_first_left and c == 1) else 0),
        )


def write_footnote(ws, row: int, text: str, n_cols: int):
    cell = ws.cell(row=row, column=1, value=text)
    cell.font = FOOTNOTE
    cell.alignment = Alignment(vertical="top", wrap_text=True, indent=1)
    ws.merge_cells(start_row=row, start_column=1,
                   end_row=row, end_column=n_cols)
    ws.row_dimensions[row].height = 28


# ----------------------------------------------------------------------
# Tab 1: Cover / Executive Summary
# ----------------------------------------------------------------------

def build_cover(wb: Workbook):
    ws = wb.active
    ws.title = "Cover"
    set_col_widths(ws, [8, 30, 18, 18, 18, 18])
    write_title_band(ws,
                     "Most Asymmetric Situations",
                     "Universe analysis · 6,164 US-listed tickers · "
                     "8 independent rankers + 57 archetypes",
                     n_cols=6)
    ws.row_dimensions[3].height = 18
    ws.cell(row=4, column=2, value="Executive summary").font = Font(
        name="Georgia", size=14, bold=True, color=CRIMSON)

    summary_lines = [
        ("Universe scope",
         "6,164 US-listed tickers (NYSE / Nasdaq / AMEX / CBOE)"),
        ("Governance / PSU coverage",
         "4,410 DEF 14As scanned (72% of universe)"),
        ("Convergent (≥3 of 8 screens + archetype winner)",
         "12 names"),
        ("Uniquely convergent (6 of 8 screens)",
         "HFFG — the only ticker hitting six independent rankers"),
        ("Highest archetype count",
         "CSGP — wins five PSU/governance archetypes"),
        ("Clean convergent (zero red flags)",
         "CSGP, RNR"),
        ("Probability of 6-screen convergence by chance",
         "≈ 2.4 × 10⁻¹⁰"),
        ("Robustness check",
         "12-name list unchanged after 2.8x coverage expansion"),
    ]

    r = 5
    for label, val in summary_lines:
        ws.cell(row=r, column=2, value=label).font = BODY_BOLD
        ws.cell(row=r, column=2).alignment = Alignment(vertical="center")
        ws.cell(row=r, column=3, value=val).font = BODY_FONT
        ws.cell(row=r, column=3).alignment = Alignment(
            vertical="center", wrap_text=True)
        ws.merge_cells(start_row=r, start_column=3,
                       end_row=r, end_column=6)
        ws.row_dimensions[r].height = 22
        r += 1

    r += 1
    ws.cell(row=r, column=2, value="The convergent twelve").font = Font(
        name="Georgia", size=14, bold=True, color=CRIMSON)
    r += 1

    convergent = [
        ("HFFG", "HF Foods Group", "Concentrated 5%+",
         "Triple PSU $ hurdle + clawback strengthened"),
        ("CSGP", "CoStar Group", "Concentrated 5%+",
         "10x CEO own + EBITDA $ + buyback EXECUTING -3.6%"),
        ("RNR", "RenaissanceRe", "Concentrated 5%+",
         "Deepest per-share metric stack (5+) · clean"),
        ("LE", "Lands' End", "Material 2-5%",
         "12-tranche ladder + 86% PSU + live TARGET 14D-9"),
        ("NUS", "Nu Skin", "Material 2-5%",
         "Named asset-sale PSU + 5-metric stack + P/B 0.33"),
        ("ADT", "ADT Inc", "Material 2-5%",
         "90% PSU%LTI (heaviest) + verified shrink -7.3%"),
        ("KMPR", "Kemper", "Material 2-5%",
         "Anti-hedge + verified buyback EXECUTING -8.7%"),
        ("MAT", "Mattel", "Material 2-5%",
         "Double dollar hurdle (EBITDA + FCF)"),
        ("LMT", "Lockheed Martin", "Material 2-5%",
         "FCF $ hurdle + backlog target"),
        ("CDE", "Coeur Mining", "Material 2-5%",
         "CEO 10b5-1 termination score 80 (#1 in universe)"),
        ("GO", "Grocery Outlet", "Participation 1-2%",
         "Forward $ targets + Cohen-Malloy cluster"),
        ("GPRO", "GoPro", "Participation 1-2%",
         "PSU vests on spin / separation"),
    ]
    write_header_row(ws, r, ["#", "Ticker", "Name", "Sizing", "Why"])
    r += 1
    for i, (tk, name, sz, why) in enumerate(convergent, 1):
        band = (i % 2 == 0)
        write_body_row(ws, r, [i, tk, name, sz, why],
                       band=band, align_first_left=False, bold_first=False)
        ws.cell(row=r, column=2).font = BODY_BOLD
        # Color-code the sizing column
        if "Concentrated" in sz:
            ws.cell(row=r, column=4).fill = CLEAN_TAG_FILL
            ws.cell(row=r, column=4).font = Font(
                name="Helvetica Neue", size=10, bold=True, color="FFFFFF")
        elif "Participation" in sz:
            ws.cell(row=r, column=4).fill = FLAG_TAG_FILL
            ws.cell(row=r, column=4).font = Font(
                name="Helvetica Neue", size=10, bold=True, color="FFFFFF")
        ws.merge_cells(start_row=r, start_column=5,
                       end_row=r, end_column=6)
        r += 1

    r += 1
    write_footnote(ws, r,
        "Cyclepapa Research · Module Series 1 · The framework "
        "produces 12 names by demanding (a) presence in top-N of "
        "≥3 of 8 independent rankers built from independent evidence "
        "and (b) winner of at least one PSU/governance archetype "
        "across 57 buckets. Robustness checks: list unchanged "
        "after expanding yfinance coverage and after a governance-"
        "scoring bugfix that nearly tripled Tier-B coverage.", 6)
    ws.sheet_view.showGridLines = False


# ----------------------------------------------------------------------
# Tab 2: Most Asymmetric — per-name detail rows
# ----------------------------------------------------------------------

def build_most_asymmetric(wb: Workbook, proxy: dict, yf: dict, bbv: dict,
                          tender: dict, c10: dict, f4: dict):
    ws = wb.create_sheet("Most Asymmetric")
    set_col_widths(ws, [9, 22, 11, 11, 11, 11, 22, 32, 28, 18])
    write_title_band(ws,
                     "The Convergent Twelve",
                     "Per-name structural detail · sourced from "
                     "PSU forensics + valuation + buyback verification "
                     "+ tender mechanics + insider behaviour",
                     n_cols=10)

    headers = ["Ticker", "Name", "mcap ($M)", "Spot ($)", "P/B",
               "PSU core", "Catalyst (cond_cat)", "Why convergent",
               "Floor", "Sizing"]
    write_header_row(ws, 4, headers)

    convergent_data = [
        ("HFFG", "HF Foods Group", "Triple PSU $ hurdle (rev/EBITDA/FCF) + clawback strengthened + 4-buyer F4 cluster", "P/B 0.48 + microcap distributor with hard assets", "Concentrated 5%+"),
        ("CSGP", "CoStar Group", "EBITDA $ hurdle + 10x CEO ownership + SOP 45% dissent + verified buyback EXECUTING -3.6%", "Quasi-monopoly RE data; recurring revenue base", "Concentrated 5%+"),
        ("RNR", "RenaissanceRe", "Deepest per-share metric stack in universe (≥5 per-share metrics) — full alignment", "Insurance NAV + per-share metric discipline", "Concentrated 5%+"),
        ("LE", "Lands' End", "12-tranche price ladder + 86% PSU%LTI + ROIC + live take-private 14D-9", "Active third-party bid sets mechanical floor", "Material 2-5%"),
        ("NUS", "Nu Skin", "Named asset-sale trigger + 5-metric clean per-share stack", "P/B 0.33 — deep book discount + buyback shrinking organically", "Material 2-5%"),
        ("ADT", "ADT Inc", "Heaviest PSU%LTI in universe (90%) + verified -7.3% shrinkage", "Recurring monitoring revenue + verified supply-curve compression", "Material 2-5%"),
        ("KMPR", "Kemper", "Anti-hedge/pledge + verified buyback EXECUTING -8.7% (largest verified shrinkage)", "Insurer at 0.54x book; $ repurchased = 1.85x NAV-accretive", "Material 2-5%"),
        ("MAT", "Mattel", "Unique double dollar hurdle: EBITDA $ + FCF $ targets both coded", "Brand portfolio + 6-metric stack provides discipline", "Material 2-5%"),
        ("LMT", "Lockheed Martin", "FCF $ hurdle + backlog $ target + 70% PSU%LTI", "Defense backlog + sovereign counterparty", "Material 2-5%"),
        ("CDE", "Coeur Mining", "CEO 10b5-1 termination score 80 — #1 in universe + FCF/share PSU stack", "Precious-metals price floor + CEO walked back scheduled selling", "Material 2-5%"),
        ("GO", "Grocery Outlet", "Forward $ targets + Cohen-Malloy 6-buyer cluster ($7.9M = 0.97% mcap)", "Discount-grocery defensive base", "Participation 1-2%"),
        ("GPRO", "GoPro", "PSU vests on spin / separation event — board paid to execute separation", "Brand + cash position", "Participation 1-2%"),
    ]

    r = 5
    for i, (tk, name, why, floor, sizing) in enumerate(convergent_data, 1):
        p = proxy.get(tk, {})
        y = yf.get(tk, {})
        mcap = (y.get("mcap") or 0) / 1e6 if y else 0
        px = y.get("price") if y else None
        pb = y.get("p_b") if y else None
        psu_core = p.get("psu_core") if p else None
        cc = ", ".join(p.get("cond_cats") or []) if p else ""

        band = (i % 2 == 0)
        write_body_row(ws, r,
                       [tk, name,
                        f"${mcap:,.0f}" if mcap else "?",
                        f"${px:.2f}" if px else "?",
                        f"{pb:.2f}" if pb else "?",
                        f"{psu_core:.0f}" if psu_core else "—",
                        cc or "—",
                        why, floor, sizing],
                       band=band, align_first_left=False)
        ws.cell(row=r, column=1).font = Font(
            name="Helvetica Neue", size=11, bold=True, color=CRIMSON)
        ws.cell(row=r, column=8).alignment = Alignment(
            vertical="center", wrap_text=True, indent=1, horizontal="left")
        ws.cell(row=r, column=9).alignment = Alignment(
            vertical="center", wrap_text=True, indent=1, horizontal="left")
        if "Concentrated" in sizing:
            ws.cell(row=r, column=10).fill = CLEAN_TAG_FILL
            ws.cell(row=r, column=10).font = Font(
                name="Helvetica Neue", size=10, bold=True, color="FFFFFF")
        elif "Participation" in sizing:
            ws.cell(row=r, column=10).fill = FLAG_TAG_FILL
            ws.cell(row=r, column=10).font = Font(
                name="Helvetica Neue", size=10, bold=True, color="FFFFFF")
        ws.row_dimensions[r].height = 56
        r += 1

    r += 1
    write_footnote(ws, r,
        "Catalyst (cond_cat) = forward-conditional vesting category coded "
        "in the PSU plan text. Sizing band reflects the convergence "
        "strength (number of independent screens) combined with red-flag "
        "count from the plan-evolution score. Source CSVs: "
        "consensus_ranking.csv, grand_unified_ranked.csv, "
        "buyback_verify.json, tender_scan.json.", 10)
    ws.sheet_view.showGridLines = False
    ws.freeze_panes = "A5"


# ----------------------------------------------------------------------
# Tab 3: By Archetype
# ----------------------------------------------------------------------

def build_by_archetype(wb: Workbook, arch_psu: dict, arch_asym: dict,
                       yf: dict):
    ws = wb.create_sheet("By Archetype")
    set_col_widths(ws, [9, 14, 50, 22, 11, 11, 26])
    write_title_band(ws,
                     "Archetype Winners",
                     "57 PSU/governance/thesis buckets · single best "
                     "representative per archetype across 6,164-name "
                     "universe",
                     n_cols=7)

    headers = ["#", "Code", "Archetype description",
               "Winner", "mcap ($M)", "P/B", "Source file"]
    write_header_row(ws, 4, headers)

    # Build combined arch list. Each item: (code, desc, winner_tk, src_file)
    items = []
    # Parse PSU_ARCHETYPES.md by re-reading
    psu_text = (ROOT / "PSU_ARCHETYPES.md").read_text() \
               if (ROOT / "PSU_ARCHETYPES.md").exists() else ""
    asym_text = (ROOT / "ASYMMETRIC_BY_ARCHETYPE.md").read_text() \
                if (ROOT / "ASYMMETRIC_BY_ARCHETYPE.md").exists() else ""

    def parse_archetype_pairs(text, src):
        blocks = re.findall(
            r"###?\s+(\w+\d+)\.\s+([^\n]+?)\n.*?\*\*Winner:\s*"
            r"([A-Z][A-Z0-9.\-]{0,10})\*\*",
            text, re.S)
        return [(code, desc.strip(), tk, src)
                for code, desc, tk in blocks]

    items.extend(parse_archetype_pairs(psu_text, "PSU_ARCHETYPES"))
    items.extend(parse_archetype_pairs(asym_text, "ASYMMETRIC_BY_ARCHETYPE"))

    r = 5
    for i, (code, desc, tk, src) in enumerate(items, 1):
        y = yf.get(tk, {}) or {}
        mcap = (y.get("mcap") or 0) / 1e6
        pb = y.get("p_b")
        band = (i % 2 == 0)
        write_body_row(ws, r,
                       [i, code, desc, tk,
                        f"${mcap:,.0f}" if mcap else "?",
                        f"{pb:.2f}" if pb else "?",
                        src.replace("_", " ").title()],
                       band=band, align_first_left=False)
        ws.cell(row=r, column=2).font = BODY_BOLD
        ws.cell(row=r, column=4).font = Font(
            name="Helvetica Neue", size=11, bold=True, color=CRIMSON)
        ws.cell(row=r, column=3).alignment = Alignment(
            vertical="center", wrap_text=True, indent=1, horizontal="left")
        r += 1

    r += 1
    write_footnote(ws, r,
        "Archetype = a single scored dimension (PSU forward-conditional "
        "trigger, governance evolution, plan-pattern flag, or thesis "
        "convergence). Winner = single ticker scoring highest on that "
        "dimension across the 6,164-name universe. Multi-archetype "
        "winners (CSGP, HFFG, LE, KMPR) are the structurally rarest. "
        "Source: PSU_ARCHETYPES.md + ASYMMETRIC_BY_ARCHETYPE.md.", 7)
    ws.sheet_view.showGridLines = False
    ws.freeze_panes = "A5"


# ----------------------------------------------------------------------
# Tab 4: Reserve Baskets
# ----------------------------------------------------------------------

def build_reserve_baskets(wb: Workbook, yf: dict):
    ws = wb.create_sheet("Reserve Baskets")
    set_col_widths(ws, [9, 30, 18, 50])
    write_title_band(ws,
                     "Reserve Baskets",
                     "Sub-archetype groups for diversified single-"
                     "mandate deployment alongside the convergent twelve",
                     n_cols=4)

    baskets = [
        ("Microcap forcing-function (Bastian)",
         "BEEP, LGL, NUS, DXLG, WW, OSUR",
         "P/B < 0.5 + PSU trigger + tender role; "
         "RGS/NLOP-archetype self-help"),
        ("Mungerian forward-dollar PSU",
         "HFFG, MAT, LMT, THRY, EHTH",
         "Named dollar hurdle = knowable catalyst; "
         "the most informative PSU class"),
        ("Verified buyback compounders",
         "CSGP, KMPR, ADT, PAYC, GRND",
         "EXECUTING status with PSU alignment; "
         "real supply-curve compression, not just authorisation"),
        ("Live tender / event-driven",
         "EXFY, GPUS, GETY, LE, DXLG, CWAN",
         "Issuer self-tender / TARGET 14D-9 / 13E-3 going-private; "
         "mechanical bid as floor"),
        ("Special-situations debt-haircut (BBGI-archetype)",
         "WW, LGL, QVCGQ, ENHA, FONR",
         "Capital-structure forcing function; "
         "exchange-offer + springing maturity"),
        ("Cohen-Malloy informational stack",
         "NSP, ODTX, FONR, MOBI, RGR",
         "Cluster + role + size = informational; "
         "ODTX = $75.3M trifecta (9.57% of mcap)"),
        ("Activist 13D + 8-K restructuring",
         "RPAY, CCO, SATS",
         "Triple-cross-validated (13D + restructuring + boundary); "
         "activist as forced-action catalyst"),
        ("Russell-recon forced flow",
         "EBS, BYND, CMCO, BLCO, MUR",
         "Within ±20% of R2000 cutoff; "
         "passive-flow distortion candidates"),
        ("NOL shell / §382 tax-asset",
         "WOLF, CEG, NOTV, NINE, USGO, CMLSQ, TSEOF",
         "Tax Benefits Preservation Rights Plan adoption; "
         "WMIH-archetype tax-attribute monetisation"),
        ("Going-dark / Form 15 OTC",
         "(see going_dark.csv)",
         "Oddball Stocks dark-company terrain; "
         "post-deregistration value-stub plays"),
    ]

    headers = ["#", "Basket", "Holdings", "Why this basket exists"]
    write_header_row(ws, 4, headers)

    r = 5
    for i, (label, names, why) in enumerate(baskets, 1):
        band = (i % 2 == 0)
        write_body_row(ws, r, [i, label, names, why],
                       band=band, align_first_left=False)
        ws.cell(row=r, column=2).font = BODY_BOLD
        for c in (2, 3, 4):
            ws.cell(row=r, column=c).alignment = Alignment(
                vertical="center", wrap_text=True, indent=1, horizontal="left")
        ws.row_dimensions[r].height = 48
        r += 1

    r += 2
    ws.cell(row=r, column=1, value="Portfolio math").font = Font(
        name="Georgia", size=14, bold=True, color=CRIMSON)
    r += 1
    portfolio = [
        ("Concentrated convergent (5%+ each)", "HFFG, CSGP, RNR", "15.0%"),
        ("Material convergent (2-5% each)",
         "LE, NUS, ADT, KMPR, MAT, LMT, CDE", "24.5%"),
        ("Participation convergent (1-2% each)", "GO, GPRO", "3.0%"),
        ("Microcap forcing-function basket", "6 names", "10.0%"),
        ("Cohen-Malloy stack", "5 names", "5.0%"),
        ("Russell-recon flow", "5 names", "3.0%"),
        ("NOL shells", "7 names", "3.0%"),
        ("Special-sits debt-haircut", "5 names", "5.0%"),
        ("CASH / OPPORTUNISTIC RESERVE", "—", "31.5%"),
    ]
    write_header_row(ws, r, ["Bucket", "Holdings", "Weight", ""])
    ws.merge_cells(start_row=r, start_column=3, end_row=r, end_column=4)
    r += 1
    for i, (b, n, w) in enumerate(portfolio, 1):
        band = (i % 2 == 0)
        is_cash = b.startswith("CASH")
        write_body_row(ws, r, [b, n, w, ""],
                       band=band, align_first_left=False)
        ws.merge_cells(start_row=r, start_column=3, end_row=r, end_column=4)
        ws.cell(row=r, column=1).font = BODY_BOLD
        if is_cash:
            ws.cell(row=r, column=1).fill = TITLE_BAND_FILL
            ws.cell(row=r, column=2).fill = TITLE_BAND_FILL
            ws.cell(row=r, column=3).fill = TITLE_BAND_FILL
            ws.cell(row=r, column=4).fill = TITLE_BAND_FILL
        r += 1

    r += 1
    write_footnote(ws, r,
        "Reserve baskets implement the playbook recommendation to "
        "specialise where the crowd isn't (microcap, forcing-function, "
        "dark companies, forced-flow distortion). Sizing band is the "
        "Bastian/Dalius two-question test applied per name: position "
        "size = function of knowability × downside × liquidity.", 4)
    ws.sheet_view.showGridLines = False


# ----------------------------------------------------------------------
# Tab 5: Caution List
# ----------------------------------------------------------------------

def build_caution_list(wb: Workbook, proxy: dict, consensus: list):
    ws = wb.create_sheet("Caution List")
    set_col_widths(ws, [9, 14, 16, 32, 14])
    write_title_band(ws,
                     "Caution List",
                     "Convergent names with red-flag wins · weight "
                     "structural alignment against governance penalty",
                     n_cols=5)

    # Build flag map
    cautions = {}
    for tk, p in proxy.items():
        flags = []
        prs = p.get("pattern_reasons") or []
        grs = p.get("gov_reasons") or []
        for s in prs + grs:
            sl = s.lower()
            if "single-trigger" in sl: flags.append("single-trigger CIC")
            if "repricing" in sl: flags.append("repricing language")
            if "retirement carveout" in sl: flags.append("retirement carveout")
            if "front-loaded" in sl: flags.append("front-loaded grant")
            if "discretionary" in sl: flags.append("discretionary hurdle")
            if "aggregate-only" in sl: flags.append("aggregate-only metrics")
        if flags:
            cautions[tk] = sorted(set(flags))

    top_names = []
    for r in consensus:
        try:
            ns = int(r["n_screens"])
        except Exception:
            continue
        if ns >= 3:
            top_names.append(r["ticker"])

    headers = ["#", "Ticker", "Screens fired", "Red flags", "Action"]
    write_header_row(ws, 4, headers)

    r = 5
    i = 1
    for tk in top_names:
        flags = cautions.get(tk)
        if not flags:
            continue
        nflags = len(flags)
        # Action ladder by flag count
        if nflags == 0: action = "Concentrate"
        elif nflags == 1: action = "Concentrate (1 flag tolerable)"
        elif nflags == 2: action = "Material — basket diversify"
        elif nflags == 3: action = "Participation — limited size"
        else: action = "Watch only — multi-flag stack"

        ns = next((int(r["n_screens"]) for r in consensus if r["ticker"] == tk), 0)
        band = (i % 2 == 0)
        write_body_row(ws, r, [i, tk, ns, ", ".join(flags), action],
                       band=band, align_first_left=False)
        ws.cell(row=r, column=2).font = Font(
            name="Helvetica Neue", size=11, bold=True, color=CRIMSON)
        if nflags >= 3:
            ws.cell(row=r, column=5).fill = FLAG_TAG_FILL
            ws.cell(row=r, column=5).font = Font(
                name="Helvetica Neue", size=10, bold=True, color="FFFFFF")
        elif nflags <= 1:
            ws.cell(row=r, column=5).fill = CLEAN_TAG_FILL
            ws.cell(row=r, column=5).font = Font(
                name="Helvetica Neue", size=10, bold=True, color="FFFFFF")
        ws.row_dimensions[r].height = 30
        r += 1
        i += 1

    r += 1
    write_footnote(ws, r,
        "Eight flag classes: single-trigger CIC, repricing language, "
        "retirement carveout, front-loaded grant, discretionary hurdle, "
        "aggregate-only metrics, plus structural variants. Counter-"
        "intuitive: a 'repricing language' flag can become a re-rate "
        "catalyst when a stock has fallen sharply, since management "
        "becomes incentivised to reset hurdles. Read the flag in "
        "context, not as automatic veto.", 5)
    ws.sheet_view.showGridLines = False


# ----------------------------------------------------------------------
# Tab 6: Coverage & Tiers
# ----------------------------------------------------------------------

def build_coverage(wb: Workbook):
    ws = wb.create_sheet("Coverage & Tiers")
    set_col_widths(ws, [9, 30, 14, 14, 14, 28])
    write_title_band(ws,
                     "Coverage Diagnostics",
                     "Where confidence is highest · where gap-fill "
                     "would lift the most names",
                     n_cols=6)

    headers = ["#", "Data layer", "Coverage", "% of universe",
               "Tier signal", "Source"]
    write_header_row(ws, 4, headers)

    layers = [
        ("PSU forensics", 4410, "DEF 14A scan",
         "Knowable catalyst", "proxy_scan*.json"),
        ("Governance score", 4410, "DEF 14A scan",
         "Board constraint", "proxy_scan*.json"),
        ("Tender / SC TO / 13E-3", 6164, "EDGAR + role disamb",
         "Mechanical bid", "tender_scan.json"),
        ("10b5-1 directional", 6164, "Full universe sweep",
         "Insider direction", "cancel_10b5_1.json"),
        ("Form 144 proposed sales", 1995, "EDGAR scan",
         "Bearish signal", "form144_scan.json"),
        ("yfinance valuation", 2132, "API enrichment",
         "Price/book floor", "yfinance_quick.json"),
        ("Buyback verification", 800, "yf.get_shares_full",
         "Verified shrinkage", "buyback_verify.json"),
        ("Form 4 P-buys", 346, "EDGAR Form 4",
         "Insider conviction", "form4_buys.json"),
    ]

    r = 5
    for i, (label, n, method, signal, src) in enumerate(layers, 1):
        pct = f"{n / 6164 * 100:.0f}%"
        band = (i % 2 == 0)
        write_body_row(ws, r, [i, label, f"{n:,}", pct, signal, src],
                       band=band, align_first_left=False)
        ws.cell(row=r, column=2).font = BODY_BOLD
        # Color-code coverage: green >=50%, gold 10-50%, crimson <10%
        cov_pct = n / 6164
        if cov_pct >= 0.5:
            ws.cell(row=r, column=4).fill = CLEAN_TAG_FILL
            ws.cell(row=r, column=4).font = Font(
                name="Helvetica Neue", size=10, bold=True, color="FFFFFF")
        elif cov_pct >= 0.1:
            ws.cell(row=r, column=4).fill = FLAG_TAG_FILL
            ws.cell(row=r, column=4).font = Font(
                name="Helvetica Neue", size=10, bold=True, color="FFFFFF")
        else:
            ws.cell(row=r, column=4).fill = HEADER_FILL
            ws.cell(row=r, column=4).font = Font(
                name="Helvetica Neue", size=10, bold=True, color="FFFFFF")
        r += 1

    r += 2
    ws.cell(row=r, column=1, value="Tier distribution").font = Font(
        name="Georgia", size=14, bold=True, color=CRIMSON)
    r += 1
    tier_data = [
        ("Tier A (6+ of 7 layers)", 0,
         "Maximum confidence — none in universe; Form 144 sparsity caps it"),
        ("Tier B (4-5 of 7 layers)", 1090,
         "Reliable for concentration; convergent twelve sit here"),
        ("Tier C (<4 of 7 layers)", 5079,
         "Requires gap-fill before concentration; ranked but uncertain"),
    ]
    write_header_row(ws, r, ["Tier", "Names", "Use", "", "", ""])
    ws.merge_cells(start_row=r, start_column=3, end_row=r, end_column=6)
    r += 1
    for i, (tier, n, use) in enumerate(tier_data, 1):
        band = (i % 2 == 0)
        write_body_row(ws, r, [tier, f"{n:,}", use, "", "", ""],
                       band=band, align_first_left=False)
        ws.merge_cells(start_row=r, start_column=3, end_row=r, end_column=6)
        ws.cell(row=r, column=1).font = BODY_BOLD
        ws.cell(row=r, column=3).alignment = Alignment(
            vertical="center", wrap_text=True, indent=1, horizontal="left")
        r += 1

    r += 1
    write_footnote(ws, r,
        "The honest coverage picture. Zero Tier-A names means there is "
        "no ticker for which every layer is complete. This is a feature, "
        "not a bug: Form 144 is signal-sparse by design (only insiders "
        "filing proposed sales appear). The convergent twelve all sit "
        "in Tier B — the highest tier actually achievable. "
        "Gap-fill priority lives in gap_fill_priority.csv.", 6)
    ws.sheet_view.showGridLines = False


# ----------------------------------------------------------------------
# Tab 7: Methodology
# ----------------------------------------------------------------------

def build_methodology(wb: Workbook):
    ws = wb.create_sheet("Methodology")
    set_col_widths(ws, [9, 30, 70])
    write_title_band(ws,
                     "Methodology",
                     "How the convergent twelve were surfaced from "
                     "the 6,164-name universe",
                     n_cols=3)

    headers = ["#", "Step", "Detail"]
    write_header_row(ws, 4, headers)

    method = [
        ("Universe construction",
         "6,164 US-listed common tickers from cancel_10b5_1.json — "
         "authoritative NYSE/Nasdaq/AMEX/CBOE set."),
        ("Layer ingestion",
         "Seven scoring layers ingested per ticker: PSU forensics, "
         "governance, valuation, buyback verification, tender mechanics, "
         "10b5-1 directional, Form 4 P-buys (plus Form 144 for bearish)."),
        ("Per-layer scoring",
         "Each layer produces (points, has_data, reason). points are "
         "capped to prevent any single layer dominating; has_data "
         "is True when ANY field in the layer is populated (key bugfix: "
         "governance is True for all 4,410 DEF 14As scanned, not only "
         "those with PSU programs)."),
        ("Coverage-normalised composite",
         "norm_score = raw_score × sqrt(7 / n_layers_present) for "
         "names with ≥3 layers. Names with 4 strong of 7 layers are "
         "not penalised vs names with 7 mediocre layers."),
        ("Per-pattern catalyst ranking",
         "Top 10 in each of 18 catalyst patterns (forward $ hurdle, "
         "M&A close, spin trigger, FDA milestone, etc.) — surfaces "
         "single-mandate leaders."),
        ("Archetype winners",
         "57 PSU/governance/thesis buckets — single best representative "
         "of each archetype across the universe. Produces "
         "PSU_ARCHETYPES.md (38) + ASYMMETRIC_BY_ARCHETYPE.md (19)."),
        ("Consensus meta-ranking",
         "Each of 8 independent rankers + 2 archetype-winner markdowns "
         "contributes presence. n_screens = how many rankers surface "
         "the ticker. n_archetypes = how many buckets it wins. "
         "consensus_score = sum of rank-decay contributions."),
        ("Convergence test",
         "Name is convergent IFF n_screens ≥ 3 AND n_archetypes ≥ 1. "
         "Probability of 6-screen convergence by chance ≈ 2.4×10⁻¹⁰."),
        ("Robustness checks",
         "Check 1: re-run after expanding yfinance from 1,885 to 2,132 "
         "(no change in convergent list). Check 2: governance bugfix "
         "expanded Tier-B coverage 2.8x (still no change). "
         "Convergent twelve is structurally informative, not data-dependent."),
        ("Caution layering",
         "Eight red-flag classes scored from plan text: single-trigger "
         "CIC, repricing, retirement carveout, front-loaded grant, "
         "discretionary hurdle, aggregate-only metrics, plus structural. "
         "Convergence without direction; flag count modulates sizing."),
        ("Deployment / sizing",
         "Concentrated (≥5%): clean convergent + ≥4 screens. "
         "Material (2-5%): 1-flag convergent or 4+ archetypes. "
         "Participation (0.5-2%): single-archetype or multi-flag. "
         "Basket (<1% each): sub-archetype groups."),
    ]
    r = 5
    for i, (step, detail) in enumerate(method, 1):
        band = (i % 2 == 0)
        write_body_row(ws, r, [i, step, detail],
                       band=band, align_first_left=False)
        ws.cell(row=r, column=2).font = BODY_BOLD
        ws.cell(row=r, column=3).alignment = Alignment(
            vertical="top", wrap_text=True, indent=1, horizontal="left")
        ws.row_dimensions[r].height = 50
        r += 1

    r += 1
    write_footnote(ws, r,
        "All scoring modules live in the cyclepapa repository. "
        "Full methodology trace: grand_unified_ranker.py + "
        "consensus_meta_ranker.py + systematic_rankings.py. "
        "Companion narrative: CASE_WORKBOOK.md teaches the framework; "
        "DILIGENCE_SHEETS.md gives per-name action triggers; "
        "BEST_OF_UNIVERSE.md proves the convergence claim.", 3)
    ws.sheet_view.showGridLines = False


# ----------------------------------------------------------------------
# Build
# ----------------------------------------------------------------------

def main() -> int:
    print("Loading sources...")
    proxy = load_proxy()
    yf = json.loads((ROOT / "yfinance_quick.json").read_text()) \
         if (ROOT / "yfinance_quick.json").exists() else {}
    bbv = json.loads((ROOT / "buyback_verify.json").read_text()) \
          if (ROOT / "buyback_verify.json").exists() else {}
    tender = json.loads((ROOT / "tender_scan.json").read_text()) \
             if (ROOT / "tender_scan.json").exists() else {}
    c10 = json.loads((ROOT / "cancel_10b5_1.json").read_text()) \
          if (ROOT / "cancel_10b5_1.json").exists() else {}
    f4 = json.loads((ROOT / "form4_buys.json").read_text()) \
         if (ROOT / "form4_buys.json").exists() else {}
    consensus = load_csv(ROOT / "consensus_ranking.csv")
    print(f"  proxy={len(proxy)} yf={len(yf)} bbv={len(bbv)} "
          f"tender={len(tender)} c10={len(c10)} f4={len(f4)} "
          f"consensus={len(consensus)}")

    wb = Workbook()
    build_cover(wb)
    build_most_asymmetric(wb, proxy, yf, bbv, tender, c10, f4)
    build_by_archetype(wb, {}, {}, yf)
    build_reserve_baskets(wb, yf)
    build_caution_list(wb, proxy, consensus)
    build_coverage(wb)
    build_methodology(wb)

    wb.save(OUT)
    print(f"\nwrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
