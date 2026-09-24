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
    for j, h in enumerate(cols, 1):
        c = ws.cell(row=row, column=j, value=h)
        c.font, c.fill = HEAD, FILL


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
    ws["A1"] = "Hand review & data quality"
    ws["A1"].font = TITLE
    ws["A2"] = (f"Reviewed {date.today()}. Hand-built waterfalls checked against today's prices; "
                "FMP overlay data-quality log; known limitations.")
    r = 4
    ws.cell(row=r, column=1, value="1. Hand-built waterfalls: are they still current?").font = SUB
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
        for j, v in enumerate(vals, 1):
            c = ws.cell(row=r, column=j, value=v)
            c.alignment = WRAP
            if j == 8 and note.startswith(("RESOLVED", "BROKEN", "WRONG")):
                c.font = RED
        ws.row_dimensions[r].height = 30 if len(note) > 70 else 16
    r += 1
    ws.cell(row=r, column=1, value="* EV× if the YAML's absolute targets still hold, re-based "
            "to today's price (stated EV ÷ (1 + move)). A rise shrinks remaining upside; a fall "
            "raises it only if the thesis is intact.").font = Font(italic=True, size=9)

    r += 2
    ws.cell(row=r, column=1, value="2. FMP overlay: data-quality log").font = SUB
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
        c = ws.cell(row=r, column=1, value="•  " + t)
        c.alignment = WRAP
        ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=8)
        ws.row_dimensions[r].height = 32
    r += 2
    ws.cell(row=r, column=1, value="3. Known limitations (and the fix)").font = SUB
    for t in LIMITS:
        r += 1
        c = ws.cell(row=r, column=1, value="•  " + t)
        c.alignment = WRAP
        ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=8)
        ws.row_dimensions[r].height = 44

    # ---------------------------------------------------------------- call intent sheet
    ci = json.loads((ROOT / "call_intent.json").read_text()) if (ROOT / "call_intent.json").exists() else {}
    wc = wb.create_sheet("Call intent", 2)
    for col, w in zip("ABCDEFGHIJ", (8, 12, 24, 13, 8, 10, 8, 26, 70, 1)):
        wc.column_dimensions[col].width = w
    wc["A1"] = "Call intent — what management said on its latest earnings call"
    wc["A1"].font = TITLE
    wc["A2"] = ("Clause-level linguistic scoring of each company's calls (call_intent.py): "
                "commitment strength, negation, new-vs-routine programmes, action size, CEO/CFO "
                "agreement and novelty vs prior calls; act probability calibrated on what "
                "companies then did (CALL_INTENT_VALIDATION.md). Predicts ACTION, not the re-rating.")
    wc["A2"].alignment = WRAP
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
            cell = wc.cell(row=rr, column=j, value=v)
            cell.alignment = WRAP
        wc.row_dimensions[rr].height = 30
    wc.freeze_panes = "A5"

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
    wb.save(a.xlsx)
    print(f"post-process: review sheet ({len(real)} hand-built names checked) + call intent "
          f"({len(have)} of {len(rows)} names have transcripts)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
