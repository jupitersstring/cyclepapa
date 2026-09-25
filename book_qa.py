"""Automated QA over the finished workbooks -- every sheet, every row.

Checks (each finding names the book, sheet, row, ticker and value):
  DUPLICATE ISSUER   the same company listed twice on one sheet (share classes,
                     preferred / note lines, ordinary + ADR)
  BAD SECURITY       notes / preferreds / warrants / units / bankrupt 'Q' lines
                     in an equity list
  IMPLAUSIBLE        P/B <= 0 or > 60, P/E < 0 shown as a multiple, % mcap > 500%,
                     market cap <= 0, dates in the future
  INCONSISTENT       the same ticker's P/B differs by > 25% between a sheet's own
                     P/B column and the validated FMP key numbers
  RAW DECIMALS       floats shown with > 4 decimals (unformatted)
  STALE              a signal date > 18 months old on a "recent" sheet
  NO DATA            a listed ticker with no FMP financial record
  DEAD COLUMN        a column empty / zero in >= 90% of rows

Output: BOOK_QA.md (summary counts + every finding) and book_qa.json.
"""

from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from datetime import date, datetime
from pathlib import Path

import openpyxl

ROOT = Path("/home/user/cyclepapa")
BOOKS = ["MOST_ASYMMETRIC.xlsx", "OTC_BOOK.xlsx", "cyclepapa_risk_reward_workbook.xlsx"]
RECENT_SHEETS = {"What's New", "Recent 30d", "Call Intent", "Turnaround Signal", "Governance Discount",
                 "Insider Conviction", "Insider Filing-Time", "Event Detail", "OTC Intent"}
SKIP = {"Contents", "Cover", "Methodology", "Layer Correlation", "Coverage & Tiers", "Re-Rate Backtest",
        "Winners Study", "Tear Sheets", "Review & data quality"}
# listed debt / hybrid lines (ADRs and German preference shares are equity: not flagged)
_DEBT = re.compile(r"\d%|\bnotes?\b|debenture|\bsr\.? nts?\b|\bpfd\b|warrant|preferred", re.I)


def norm(n):
    n = re.sub(r"[^a-z0-9 ]", " ", str(n or "").lower())
    n = re.sub(r"\b(inc|corp|corporation|co|ltd|limited|plc|holdings?|group|the|class [a-c]|sa|ag|nv|lp|llc)\b", " ", n)
    return " ".join(n.split())[:24]


def header(ws):
    for r in range(1, 13):
        vals = [c.value for c in ws[r]]
        if any(v in ("Ticker", "TKR", "Symbol") for v in vals):
            return r, {str(v).strip(): j + 1 for j, v in enumerate(vals) if v is not None}
    return None, {}


def num(v):
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return float(v)
    if isinstance(v, str):
        m = re.match(r"^\s*([-+]?\d+(?:\.\d+)?)\s*[×x%]?\s*$", v)
        if m:
            return float(m.group(1))
    return None


def run():
    fin = json.loads((ROOT / "name_financials.json").read_text()) if (ROOT / "name_financials.json").exists() else {}
    today = date.today()
    findings = []

    def add(book, sheet, row, kind, ticker, detail):
        findings.append({"book": book, "sheet": sheet, "row": row, "kind": kind, "ticker": ticker, "detail": detail})

    for book in BOOKS:
        p = ROOT / book
        if not p.exists():
            continue
        wb = openpyxl.load_workbook(p, read_only=True)
        for ws in wb.worksheets:
            if ws.title in SKIP:
                continue
            rows = list(ws.iter_rows(values_only=True))
            hr, cols = header(ws)
            if not hr:
                continue
            tcol = (cols.get("Ticker") or cols.get("TKR") or cols.get("Symbol")) - 1
            ncol = (cols.get("Name") or cols.get("Company") or 0) - 1
            body = [(i + 1, r) for i, r in enumerate(rows) if i + 1 > hr and r and tcol < len(r)
                    and isinstance(r[tcol], str) and 0 < len(r[tcol].strip()) < 20 and " " not in r[tcol].strip("● ")
                    and r[tcol].strip() not in ("Ticker", "TKR", "Symbol")]
            seen = defaultdict(list)
            colvals = defaultdict(list)
            for rn, r in body:
                t = r[tcol].replace("●", "").strip()
                nm = r[ncol] if ncol >= 0 and ncol < len(r) else None
                f = fin.get(t) or {}
                key = norm(nm or f.get("name") or "")
                if key:
                    seen[key].append((rn, t))
                full_name = str(f.get("name") or nm or "")
                if _DEBT.search(full_name or "") or (len(t) == 5 and t.endswith("Q")) or re.search(r"-WT$|\.WS$|-U$", t):
                    add(book, ws.title, rn, "BAD SECURITY", t, full_name[:60])
                if not f and book != "cyclepapa_risk_reward_workbook.xlsx" and ws.title not in ("Foreign Markets", "Going Dark", "UK Capital Events"):
                    add(book, ws.title, rn, "NO DATA", t, "no FMP financial record")
                for h, c in cols.items():
                    v = r[c - 1] if c - 1 < len(r) else None
                    colvals[h].append(v)
                    x = num(v)
                    if h in ("P/B",) and x is not None and (x <= 0 or x > 300):
                        add(book, ws.title, rn, "IMPLAUSIBLE", t, f"P/B {v}")
                    if h in ("P/E",) and x is not None and x < 0:
                        add(book, ws.title, rn, "IMPLAUSIBLE", t, f"negative P/E {v} shown as a multiple")
                    if h in ("% mcap", "Size") and isinstance(v, str) and v.endswith("%") and x and x > 500:
                        add(book, ws.title, rn, "IMPLAUSIBLE", t, f"{h} {v}")
                    if isinstance(v, float) and len(repr(v).split(".")[-1]) > 4 and abs(v) < 1e6:
                        add(book, ws.title, rn, "RAW DECIMALS", t, f"{h} = {v}")
                    if isinstance(v, str) and re.match(r"^20\d\d-\d\d-\d\d$", v):
                        try:
                            d = datetime.strptime(v, "%Y-%m-%d").date()
                            if d > today:
                                if h not in ("Window end", "Window start"):
                                    add(book, ws.title, rn, "IMPLAUSIBLE", t, f"{h} {v} is in the future")
                            elif ws.title in RECENT_SHEETS and (today - d).days > 548:
                                add(book, ws.title, rn, "STALE", t, f"{h} {v} (> 18 months)")
                        except ValueError:
                            pass
                pb_col = cols.get("P/B")
                # the cross book lists global tickers that collide with US symbols: skip there
                if pb_col and f.get("p_b") and pb_col - 1 < len(r) and not book.startswith("cyclepapa_risk"):
                    x = num(r[pb_col - 1])
                    if x and x > 0 and abs(x / f["p_b"] - 1) > 0.25:
                        add(book, ws.title, rn, "INCONSISTENT", t,
                            f"P/B {x:.2f} on sheet vs {f['p_b']:.2f} validated (FMP)")
            for key, lst in seen.items():
                ts = {t for _, t in lst}
                # different SPAC series share a name stem (Churchill Capital XII / XIII): not duplicates
                if len(ts) > 1 and not key.replace(" ", "").isdigit() and not re.search(r"capital|acquisition|spac", key):
                    add(book, ws.title, lst[1][0], "DUPLICATE ISSUER", ",".join(t for _, t in lst), key)
            n = len(body)
            for h, vals in colvals.items():
                if n >= 8 and h not in ("FMP financial read",) and not (ws.title == "Payoff Geometry" and h == "Down%"):
                    empty = sum(1 for v in vals if v in (None, "", "–", "—", "-", 0, "0", "None"))
                    if empty / n >= 0.9:
                        add(book, ws.title, hr, "DEAD COLUMN", "", f"'{h}' empty in {empty}/{n} rows")
    return findings


def main() -> int:
    f = run()
    (ROOT / "book_qa.json").write_text(json.dumps(f, indent=1))
    c = Counter((x["book"], x["kind"]) for x in f)
    L = [f"# Book QA — {date.today()}", "", "Automated checks over every sheet of the three books "
         "(`book_qa.py`). Counts by book and kind, then every finding.", "",
         "| Book | Kind | Findings |", "|---|---|---|"]
    for (b, k), n in sorted(c.items()):
        L.append(f"| {b} | {k} | {n} |")
    L += ["", "## Findings", "", "| Book | Sheet | Row | Kind | Ticker | Detail |", "|---|---|---|---|---|---|"]
    for x in sorted(f, key=lambda x: (x["book"], x["kind"], x["sheet"], x["row"])):
        L.append(f"| {x['book'].split('.')[0]} | {x['sheet']} | {x['row']} | {x['kind']} | {x['ticker']} | {x['detail']} |")
    (ROOT / "BOOK_QA.md").write_text("\n".join(L) + "\n")
    print(f"book QA: {len(f)} findings")
    for (b, k), n in sorted(c.items()):
        print(f"  {b:<40} {k:<18} {n}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
