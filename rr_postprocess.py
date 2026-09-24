"""Post-process the risk-reward (cross) book after the engine builds it:
adds two sheets that the engine itself cannot produce.

  * "Review & data quality" -- the hand review: for each hand-built (REAL)
    waterfall, when its YAML was last edited, the price move since, the EV
    re-based to today's price (if its absolute targets still stand) and the
    reviewer's thesis-status note; then the FMP overlay's data-quality log
    (rows dropped as non-companies, flagged untradeable/bankrupt names, P/B
    provenance) and the book's known limitations.
  * "Call intent" -- earnings-call intent (call_intent.json) for every name
    in the book that has transcripts: tier, act probability, NEW families,
    stated action size and the verbatim evidence.

Usage: python3 rr_postprocess.py --wt <worktree> --xlsx <workbook>
"""

from __future__ import annotations

import argparse
import csv
import json
import subprocess
from collections import Counter
from datetime import date
from pathlib import Path

from openpyxl import load_workbook
from openpyxl.styles import Alignment, Font, PatternFill

import fmp_client as fmp

ROOT = Path("/home/user/cyclepapa")
HEAD = Font(bold=True, color="FFFFFF")
FILL = PatternFill("solid", fgColor="1F3864")
TITLE = Font(bold=True, size=14, color="1F3864")
SUB = Font(bold=True, size=11, color="1F3864")
WRAP = Alignment(wrap_text=True, vertical="top")
RED = Font(color="C00000")

# reviewer's thesis-status notes (hand review, 2026-09-24): facts that the
# YAMLs have not caught up with. Keep terse and factual.
NOTES = {
    "SAB": "RESOLVED CATALYST: BBVA's offer lapsed in Oct-2025 with ~25% acceptance -- the "
           "'BBVA bid resolution' catalyst (p=0.6, Jun-Dec 2026) no longer exists. Thesis is now "
           "stand-alone ROTE + TSB-sale capital return; rebuild the waterfall.",
    "241560": "BROKEN CATALYST: the Doosan Bobcat / Doosan Robotics share swap was cancelled in "
              "Dec-2024. 'Revised stock-swap terms' refers to a deal that no longer exists; thesis "
              "rests on Korea Value-Up only.",
    "UREE": "WRONG TICKER: USA Rare Earth trades as USAR (Nasdaq); 'UREE' cannot be priced, so "
            "the waterfall has no live price anchor.",
    "LAC": "Price -36% since the YAML. The US DOE took an equity stake (Oct-2025) -- check the "
           "waterfall prices that in and re-base the multiples.",
    "ETL": "Price -42% since the YAML: the base/bull multiples are stale -- re-base or rebuild "
           "(check the latest results call in the Call intent sheet).",
    "HE": "Price -32% since the YAML, new 12-month low (Sep-2026). Re-examine the bear case.",
    "OHLA": "Price -23% since the YAML; the Apollo take-out catalyst (p=0.35) needs a status check.",
    "SUNAC": "Price -22% since the YAML; re-base.",
    "TKA": "Price +39% since the YAML: much of the base case may be realised -- re-base before "
           "sizing (reward/risk from today is lower than shown).",
    "LOCAL": "Market-cap data inconsistent in FMP (share count after the 2024 restructuring): "
             "the #1 rank rests entirely on the YAML (bear -15%, EV 4.0x) -- verify price and "
             "share count by hand before relying on it.",
    "GTCO": "No FMP price feed (NGX; also LSE-listed since Jul-2025) -- price move unverified.",
    "DSI": "No FMP price feed (DFM) -- price move unverified; thinly traded.",
}
YAML_SYM = {"LOCAL": "LOCAL.PA", "LAC": "LAC", "SZG": "SZG.DE", "TKA": "TKA.DE",
            "ELUX-B": "ELUX-B.ST", "6305": "6305.T", "241560": "241560.KS", "ETL": "ETL.PA",
            "OHLA": "OHLA.MC", "WLN": "WLN.PA", "DRX": "DRX.L", "SAB": "SAB.MC", "UREE": "USAR",
            "YPF": "YPF", "HE": "HE", "TMQ": "TMQ", "MP": "MP", "FLG": "FLG", "SUNAC": "1918.HK"}

LIMITS = [
    "Hand-built waterfalls store RETURN MULTIPLES relative to the price when the YAML was "
    "written, with no reference price or date. When the price moves the multiples silently go "
    "stale (see the table above). Fix upstream: store absolute bear/base/bull VALUES per share "
    "plus an as-of price/date, and derive multiples from today's price.",
    "PROXY rows (formula on a screener score) and FMP rows (balance-sheet floor + re-rate to "
    "book) are not comparable to REAL waterfalls; the composite normalises reward/risk WITHIN "
    "each source, so a PROXY 2.6x and an FMP 2.6x do not mean the same thing.",
    "FMP floor = max(net cash after a year of burn, 2/3 NCAV (not for property), soft book "
    "floor capped at 60% of mcap). Many top FMP rows are micro-cap cash boxes (net cash > "
    "mcap): real, but burn, dilution and control/insider risk decide whether the cash reaches "
    "shareholders.",
    "Portfolio sizing: every name hits the 10% raw-Kelly cap and the 3% cluster cap, so sizing "
    "is effectively equal-weight -- the Kelly inputs (p, payoff) are not differentiating.",
    "Catalyst timeline: most windows are multi-year and sourced to 'industry'/'company "
    "guidance' -- few hard-dated events. Dated catalysts (votes, deadlines, filings) would "
    "make the timing column useful.",
    "Regions and archetypes for PROXY rows come from the upstream screener and were often "
    "wrong/blank; regions are now taken from FMP where the name maps.",
]


def hdr(ws, row, cols):
    import book_layout as bl
    k = bl.kit(ws.parent)
    for j, h in enumerate(cols, 1):
        k.header(ws.cell(row=row, column=j, value=h))


def body(ws, r, c, v, band=False, bold=False, wrap=True):
    import book_layout as bl
    cell = ws.cell(row=r, column=c, value=v)
    bl.kit(ws.parent).body(cell, band=band, bold=bold, wrap=wrap)
    return cell


def title(ws, cell_ref, text):
    import book_layout as bl
    ws[cell_ref] = text
    bl.kit(ws.parent).title(ws[cell_ref])


def subtitle(ws, cell_ref, text):
    import book_layout as bl
    ws[cell_ref] = text
    bl.kit(ws.parent).subtitle(ws[cell_ref])


def yaml_date(wt, t):
    r = subprocess.run(["git", "-C", str(wt), "log", "-1", "--format=%cs", "--",
                        f"data/candidates/{t}.yaml"], capture_output=True, text=True)
    return r.stdout.strip() or None


def move_since(sym, d):
    if not sym or not d:
        return None
    try:
        px = fmp.daily_adjusted(sym, d)
    except RuntimeError:
        return None
    return (px[-1][4] / px[0][4] - 1) if len(px) >= 2 else None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--wt", required=True)
    ap.add_argument("--xlsx", required=True)
    a = ap.parse_args()
    wt = Path(a.wt)
    rows = list(csv.DictReader(open(wt / "output" / "universe_risk_reward.csv")))
    log = json.loads((wt / "output" / "fmp_overlay_log.json").read_text()) \
        if (wt / "output" / "fmp_overlay_log.json").exists() else {}
    wb = load_workbook(a.xlsx)

    # ---------------------------------------------------------------- review sheet
    ws = wb.create_sheet("Review & data quality", 1)
    for col, w in zip("ABCDEFGHI", (10, 26, 11, 10, 10, 11, 10, 70, 1)):
        ws.column_dimensions[col].width = w
    ws.sheet_view.showGridLines = False
    title(ws, "A1", "Hand review & data quality")
    subtitle(ws, "A2", f"Reviewed {date.today()}. Hand-built waterfalls checked against today's prices; "
                       "FMP overlay data-quality log; known limitations.")
    ws.merge_cells("A2:H2")
    r = 4
    subtitle(ws, f"A{r}", "1. Hand-built waterfalls: are they still current?")
    r += 1
    hdr(ws, r, ["Ticker", "Name", "YAML edited", "Px since", "EV× stated", "EV× today*",
                "Bear loss", "Reviewer note"])
    real = [x for x in rows if x["source"] == "REAL"]
    for x in real:
        t = x["ticker"].split(":")[-1]
        d = yaml_date(wt, t)
        ch = move_since(YAML_SYM.get(t) or x.get("fmp_symbol"), d)
        ev = float(x["ev"] or 0)
        ev_today = ev / (1 + ch) if ch is not None and ch > -0.95 else None
        note = NOTES.get(t, "")
        if not note and ch is not None and abs(ch) >= 0.2:
            note = f"Price {ch:+.0%} since the YAML -- re-base the multiples."
        r += 1
        vals = [t, x["name"][:26], d, f"{ch:+.0%}" if ch is not None else "n/a", f"{ev:.2f}",
                f"{ev_today:.2f}" if ev_today else "n/a", f"{float(x['bear_loss'] or 0):.0%}", note]
        band = (len(real) and (r % 2 == 0))
        for j, v in enumerate(vals, 1):
            c = body(ws, r, j, v, band=band, bold=(j == 1))
            if j == 8 and note.startswith(("RESOLVED", "BROKEN", "WRONG")):
                from copy import copy
                fnt = copy(c.font); fnt.color = "C00000"; fnt.b = True
                c.font = fnt
        ws.row_dimensions[r].height = 30 if len(note) > 70 else 16
    r += 1
    subtitle(ws, f"A{r}", "* EV× if the YAML's absolute targets still hold, re-based "
             "to today's price (stated EV ÷ (1 + move)). A rise shrinks remaining upside; a fall "
             "raises it only if the thesis is intact.")
    ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=8)

    r += 2
    subtitle(ws, f"A{r}", "2. FMP overlay: data-quality log")
    src = Counter(x["source"] for x in rows)
    pbs = Counter(x.get("pb_src") for x in rows if x.get("fmp_symbol"))
    flags = Counter((x.get("flag") or "").split(" (")[0].split(":")[0] for x in rows if x.get("flag"))
    lines = [
        f"Rows ranked: {len(rows)} (REAL {src['REAL']}, FMP {src['FMP']}, PROXY {src['PROXY']}).",
        f"Dropped as not investable companies: {len(log.get('dropped_not_companies', []))} "
        "(OFAC/Treasury notice titles and press-release headlines ingested as names, funds, "
        "warrants/units). Examples: " + "; ".join(n[:45] for _, n in log.get("dropped_not_companies", [])[:4]),
        "Ticker mapping: bare engine tickers are now name-verified (ASX names such as CMG, AON, "
        "JLL, HAS had been matched to Chipotle, Aon, JLL, Hasbro); unmatched names stay PROXY.",
        "P/B provenance for mapped rows: " + ", ".join(f"{k} {v}" for k, v in pbs.most_common()) +
        " (calc = mcap/latest equity; calc_fx = at spot FX; mcap_suspect = quote mcap disagrees "
        "with price × shares -- not used).",
        "Flags (demoted in the composite): " + ", ".join(f"{k} {v}" for k, v in flags.most_common()),
    ]
    for t in lines:
        r += 1
        body(ws, r, 1, "•  " + t)
        ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=8)
        ws.row_dimensions[r].height = 32
    r += 2
    subtitle(ws, f"A{r}", "3. Known limitations (and the fix)")
    for t in LIMITS:
        r += 1
        body(ws, r, 1, "•  " + t)
        ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=8)
        ws.row_dimensions[r].height = 44

    # ---------------------------------------------------------------- call intent sheet
    ci = json.loads((ROOT / "call_intent.json").read_text()) if (ROOT / "call_intent.json").exists() else {}
    wc = wb.create_sheet("Call intent", 2)
    for col, w in zip("ABCDEFGHIJ", (8, 12, 24, 13, 8, 10, 8, 26, 70, 1)):
        wc.column_dimensions[col].width = w
    wc.sheet_view.showGridLines = False
    title(wc, "A1", "Call intent — what management said on its latest earnings call")
    subtitle(wc, "A2", ("Clause-level linguistic scoring of each company's calls (call_intent.py): "
                "commitment strength, negation, new-vs-routine programmes, action size, CEO/CFO "
                "agreement and novelty vs prior calls; act probability calibrated on what "
                "companies then did (CALL_INTENT_VALIDATION.md). Predicts ACTION, not the re-rating."))
    wc.merge_cells("A2:I2")
    wc.row_dimensions[2].height = 44
    hdr(wc, 4, ["Rank", "Ticker", "Name", "Tier", "Act prob", "Last call", "Size",
                "New / strongest families", "Evidence (verbatim)"])
    rr = 4
    have = []
    for x in rows:
        c = ci.get(x.get("fmp_symbol") or "")
        if c:
            have.append((x, c))
    have.sort(key=lambda t: ({"ACT SIGNALLED": 0, "BUILDING": 1}.get(t[1].get("tier"), 2),
                             int(t[0]["rank"])))
    for x, c in have:
        fams = c.get("families") or {}
        strongest = [k for k, _ in sorted(fams.items(), key=lambda kv: -kv[1])
                     if k not in ("ANTICIPATION", "COST")][:3]
        lab = ", ".join(["NEW " + f.lower() for f in c.get("new_families") or []] +
                        [k.lower() for k in strongest if k not in (c.get("new_families") or [])])
        ev = ""
        for k in (c.get("new_families") or []) + strongest:
            e = (c.get("evidence") or {}).get(k)
            if e:
                ev = f"[{k.lower()}] “{e[0]['q'][:200]}”"
                break
        rr += 1
        vals = [int(x["rank"]), x["ticker"].split(":")[-1], x["name"][:24], c.get("tier") or "",
                c.get("act_prob"), c.get("date", "")[:10],
                f"{c['size_pct']:.0%}" if c.get("size_pct") else "", lab[:40], ev]
        for j, v in enumerate(vals, 1):
            body(wc, rr, j, v, band=(rr % 2 == 0), bold=(j == 2))
        wc.row_dimensions[rr].height = 30
    wc.freeze_panes = "A5"

    # Executive Summary: show the SORT KEY (the composite) and the review flag --
    # without them the order looks arbitrary (a 2.9x REAL row above 15x FMP rows)
    try:
        es = wb["Executive Summary"]
        hdr_r = next(r for r in range(1, 8) if es.cell(row=r, column=3).value == "Ticker")
        by_t = {x["ticker"]: x for x in rows}
        c0 = es.max_column + 1
        import book_layout as bl
        for j, h in enumerate(("Composite (sort key)", "Review flag"), 0):
            for rr_ in range(hdr_r, es.max_row + 1):
                bl.clone(es.cell(row=rr_, column=c0 - 1), es.cell(row=rr_, column=c0 + j))
            es.cell(row=hdr_r, column=c0 + j, value=h)
        es.column_dimensions[es.cell(row=hdr_r, column=c0).column_letter].width = 11
        es.column_dimensions[es.cell(row=hdr_r, column=c0 + 1).column_letter].width = 40
        for r in range(hdr_r + 1, es.max_row + 1):
            x = by_t.get(es.cell(row=r, column=3).value)
            if x:
                es.cell(row=r, column=c0, value=float(x["composite"]))
                es.cell(row=r, column=c0 + 1, value=x.get("flag") or "")
    except StopIteration:
        pass

    # FMP / flagged rows carry the upstream screener's placeholder Score / Bucket /
    # Archetype (0.52 · A · F for every FMP row): blank them so they aren't read
    src_of = {x["ticker"]: x["source"] for x in rows}
    for sh in wb.worksheets:
        hr = next((r for r in range(1, 8) if any(sh.cell(row=r, column=c).value == "Ticker"
                                                   for c in range(1, 6))), None)
        if not hr:
            continue
        cols = {sh.cell(row=hr, column=c).value: c for c in range(1, sh.max_column + 1)}
        tcol = cols.get("Ticker")
        blank = [cols[h] for h in ("Score", "Bucket", "Archetype", "Arch") if h in cols]
        if not blank:
            continue
        for r in range(hr + 1, sh.max_row + 1):
            if src_of.get(sh.cell(row=r, column=tcol).value) == "FMP":
                for c in blank:
                    sh.cell(row=r, column=c).value = "—"

    # sheets the engine leaves without an explanation
    EXPLAIN = {
        "All names": "Every ranked name (REAL hand-built waterfalls, FMP balance-sheet rows, PROXY "
                     "formula rows), in composite order. Bear = downside to the floor; EV× = expected "
                     "multiple; RR = (EV−1)/bear. Compare within a source: PROXY and FMP numbers are "
                     "not on the same basis as REAL waterfalls.",
        "Universe (Tier 1+2)": "The hand-built names (YAMLs) with their jurisdiction, sector, bucket, "
                               "archetype, build tier and scenario multiples.",
        "Waterfall matrix": "Each hand-built name's bear / base / bull scenario: probability (P), "
                            "return multiple (R) and P×R; EV× = ΣP×R. Rationale columns give the "
                            "YAML's reasoning. Multiples are relative to the price when the YAML was "
                            "written (see Review & data quality).",
        "Catalyst timeline": "Dated catalysts from the hand-built YAMLs: window, event, probability "
                             "it goes our way, re-rate if yes and hit if no. Sorted by window start.",
        "Portfolio sizing": "Risk-budgeted weights for the hand-built basket: raw Kelly → correlation "
                            "haircut → cluster cap (3%). EV× on weight and its contribution in bps.",
        "Methodology": "How the ranking, waterfalls, FMP overlay and sizing are built.",
    }
    for t, txt in EXPLAIN.items():
        if t in wb.sheetnames:
            sh = wb[t]
            if sh.cell(row=2, column=1).value in (None, ""):
                subtitle(sh, "A2", txt)
                if t != "Methodology":
                    sh.merge_cells(start_row=2, start_column=1, end_row=2, end_column=min(12, sh.max_column))
                    sh.row_dimensions[2].height = 42

    # FMP financials for every name in the book (tickers shown as 'EPA:LOCAL' or 'LOCAL')
    import name_financials
    sym_map = {}
    for x in rows:
        if x.get("fmp_symbol"):
            sym_map[x["ticker"]] = x["fmp_symbol"]
            sym_map.setdefault(x["ticker"].split(":")[-1], x["fmp_symbol"])
    sym_map.update({k: v for k, v in YAML_SYM.items()})
    fin = name_financials.build(set(sym_map.values()))
    name_financials.add_financials(wb, fin, sym_map, index=3,
                                   skip=("Cover", "Methodology", "Review & data quality"))
    import book_layout as bl
    bl.key_numbers(wb, fin, sym_map, skip=("Cover", "Methodology", "Review & data quality",
                                           "Name Financials"))
    fin_disp = {k: fin.get(v) for k, v in sym_map.items() if fin.get(v)}
    print("  QA fixes:", dict(bl.qa_fixes(wb, fin_disp, harmonise_pb=False,
                                          skip=("Cover", "Methodology", "Review & data quality"))))
    top = [x["ticker"] for x in rows[:40]] + [x["ticker"] for x in rows if x["source"] == "REAL"]
    bl.tear_sheets(wb, fin, list(dict.fromkeys(top)), sym_map, index=1, max_names=60)
    wb.save(a.xlsx)
    print(f"post-process: review sheet ({len(real)} hand-built names checked) + call intent "
          f"({len(have)} of {len(rows)} names have transcripts)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
