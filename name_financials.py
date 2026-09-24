"""Per-name financial profile from FMP -- the numbers a reader needs next to
every name in the books.

For every symbol in the US quote store, the risk-reward book's mapped
symbols and the OTC intent names, one record from the FMP bulk files
(no per-name API calls):

  valuation   price, mcap, EV, P/B (validated: fmp_book), P/E, P/S, EV/EBITDA,
              FCF yield, earnings yield, dividend yield
  quality     gross / operating / net margin, ROE, ROIC, SBC % revenue
  balance     net cash % mcap (same-currency), net debt / EBITDA, debt/equity,
              interest cover, current ratio
  trajectory  revenue growth (TTM vs prior TTM) and share-count change (YoY)
              from the bulk quarterly statements
  trading     52-week range position, average $ volume
  read        a one-line plain-English summary + data-quality flags

Output: name_financials.json {symbol: {...}}.  Also provides
financials_sheet(wb, title, symbols, fin) used by all three workbooks.
"""

from __future__ import annotations

import csv
import glob
import json
from pathlib import Path

import fmp_book
import fmp_client as fmp

ROOT = Path("/home/user/cyclepapa")
OUT = ROOT / "name_financials.json"


def _f(x):
    try:
        v = float(x)
        return v if v == v else None
    except (TypeError, ValueError):
        return None


def _quarterly(prefix, fields):
    """{sym: [(date, {field: value})...] ascending} from cached bulk statements."""
    out = {}
    for fn in glob.glob(str(ROOT / "fmp_cache" / f"{prefix}_*")):
        for r in csv.DictReader(open(fn, encoding="utf-8", errors="ignore")):
            if r.get("date"):
                out.setdefault(r["symbol"], {})[r["date"][:10]] = {k: _f(r.get(k)) for k in fields}
    return {s: sorted(m.items()) for s, m in out.items()}


def _days(a, b):
    from datetime import date
    return (date.fromisoformat(b) - date.fromisoformat(a)).days


def _ttm_growth(rows, key):
    """TTM vs prior TTM using statement DATES: quarterly reporters sum the last
    4 vs prior 4 quarters; semi-annual reporters (gaps ~6 months) the last 2
    vs prior 2 halves. Mixed / gappy histories return None."""
    pts = [(d, v[key]) for d, v in rows if v.get(key) is not None]
    if len(pts) < 4:
        return None
    gaps = [_days(pts[i][0], pts[i + 1][0]) for i in range(len(pts) - 1)]
    last = gaps[-3:]
    if all(70 <= g <= 110 for g in gaps[-7:]) and len(pts) >= 8:
        n = 4
    elif all(160 <= g <= 200 for g in last[-3:]) and len(pts) >= 4:
        n = 2
    else:
        return None
    vals = [v for _, v in pts]
    now, prev = sum(vals[-n:]), sum(vals[-2 * n:-n])
    return (now / prev - 1) if prev and prev > 0 else None


def _yoy(rows, key):
    """Value now vs the statement closest to one year earlier (330-400 days)."""
    pts = [(d, v[key]) for d, v in rows if v.get(key)]
    if len(pts) < 2:
        return None
    d_now, v_now = pts[-1]
    prior = [(abs(_days(d, d_now) - 365), v) for d, v in pts[:-1] if 330 <= _days(d, d_now) <= 400]
    if not prior:
        return None
    v0 = min(prior)[1]
    return (v_now / v0 - 1) if v0 else None


def _range_pos(rng, price):
    try:
        lo, hi = [float(x) for x in str(rng).split("-")[:2]]
        return (price - lo) / (hi - lo) if hi > lo and price else None
    except (ValueError, TypeError):
        return None


def universe():
    syms = set(json.loads((ROOT / "yfinance_quick.json").read_text()))
    for fn in ("otc_intent.json", "call_intent.json", "fmp_quotes.json"):
        p = ROOT / fn
        if p.exists():
            syms |= set(json.loads(p.read_text()))
    return syms


_BULK = None


def _bulk():
    global _BULK
    if _BULK is None:
        prof = {}
        for fn in glob.glob(str(ROOT / "fmp_cache" / "profile-bulk_part*.csv")):
            for r in csv.DictReader(open(fn, encoding="utf-8", errors="ignore")):
                prof[r["symbol"]] = r
        _BULK = (prof, {r["symbol"]: r for r in fmp.get_bulk_csv("ratios-ttm-bulk")},
                 {r["symbol"]: r for r in fmp.get_bulk_csv("key-metrics-ttm-bulk")},
                 fmp_book.load(), _quarterly("isbulk", ["revenue", "weightedAverageShsOutDil", "ebitda"]))
    return _BULK


def build(symbols) -> dict:
    """Financial records for the given FMP symbols (those FMP knows)."""
    prof, rat, km, sheets, inc = _bulk()
    out = {}
    for s in sorted(set(symbols) & set(prof)):
        p, ra, k = prof[s], rat.get(s) or {}, km.get(s) or {}
        price, mcap = _f(p.get("price")), _f(p.get("marketCap"))
        pb, pb_src = fmp_book.pb(s, mcap, p.get("currency"), ra.get("priceToBookRatioTTM"), sheets,
                                 price, str(p.get("isAdr")).lower() == "true")
        bs = sheets.get(s) or {}
        eq = _f(bs.get("totalStockholdersEquity"))
        cash, debt = _f(bs.get("cashAndShortTermInvestments")), _f(bs.get("totalDebt"))
        # net cash as % of mcap inside ONE statement currency: (cash-debt)/equity x 1/(P/B)
        ncp = ((cash or 0) - (debt or 0)) / eq / pb if (eq and eq > 0 and pb and cash is not None) else None
        q = inc.get(s) or []
        sh_chg = _yoy(q, "weightedAverageShsOutDil")
        if sh_chg is not None and not (-0.6 < sh_chg < 3):
            sh_chg = None                                   # split artefact
        rec = {
            "name": p.get("companyName"), "sector": p.get("sector"), "country": p.get("country"),
            "currency": p.get("currency"), "price": price, "mcap": mcap,
            "ev": _f(k.get("enterpriseValueTTM")), "p_b": pb, "pb_src": pb_src,
            "pe": _f(ra.get("priceToEarningsRatioTTM")), "ps": _f(ra.get("priceToSalesRatioTTM")),
            "ev_ebitda": _f(k.get("evToEBITDATTM")), "fcf_yield": _f(k.get("freeCashFlowYieldTTM")),
            "earn_yield": _f(k.get("earningsYieldTTM")), "div_yield": _f(ra.get("dividendYieldTTM")),
            "gross_m": _f(ra.get("grossProfitMarginTTM")), "op_m": _f(ra.get("operatingProfitMarginTTM")),
            "net_m": _f(ra.get("netProfitMarginTTM")), "roe": _f(k.get("returnOnEquityTTM")),
            "roic": _f(k.get("returnOnInvestedCapitalTTM")),
            "sbc_rev": _f(k.get("stockBasedCompensationToRevenueTTM")),
            "net_cash_pct": ncp, "nd_ebitda": _f(k.get("netDebtToEBITDATTM")),
            "de": _f(ra.get("debtToEquityRatioTTM")), "int_cover": _f(ra.get("interestCoverageRatioTTM")),
            "current": _f(ra.get("currentRatioTTM")),
            "rev_growth": _ttm_growth(q, "revenue"), "shares_yoy": sh_chg,
            "range_pos": _range_pos(p.get("range"), price),
            "adv_usd": (_f(p.get("averageVolume")) or 0) * (price or 0) or None,
            "stmt_date": bs.get("date"),
        }
        # sanity: FMP TTM ratios break on the same artefacts as P/B
        flags = []
        if pb_src in ("mcap_suspect", "implausible"):
            flags.append("market-cap/share data inconsistent")
        if pb_src == "neg_equity":
            flags.append("negative equity")
        if rec["pe"] is not None and rec["earn_yield"] is not None and (rec["pe"] > 0) != (rec["earn_yield"] > 0):
            flags.append("P/E vs earnings-yield sign mismatch")
        if rec["fcf_yield"] is not None and abs(rec["fcf_yield"]) > 1.0:
            flags.append("FCF yield >100% (check)")
            rec["fcf_yield"] = None
        if rec["shares_yoy"] is not None and abs(rec["shares_yoy"]) > 0.15 and (p.get("country") or "US") != "US":
            flags.append("share-count history inconsistent (foreign line)")
            rec["shares_yoy"] = None
        if rec["shares_yoy"] is not None and rec["shares_yoy"] > 1.0:
            flags.append("new entity / merger: history not comparable")
            rec["shares_yoy"] = rec["rev_growth"] = None
        if rec["rev_growth"] is not None and rec["rev_growth"] <= -0.95:
            rec["rev_growth"] = None                      # stub period, not a collapse
        if rec["div_yield"] is not None and rec["div_yield"] > 0.25:
            flags.append("dividend yield >25% (special or bad data)")
            rec["div_yield"] = None
        if rec["rev_growth"] is not None and rec["rev_growth"] > 3.0:
            flags.append("revenue not comparable YoY (fair-value / one-off income?)")
            rec["rev_growth"] = None
        rec["flags"] = flags
        rec["read"] = read_line(rec)
        out[s] = rec
    return out


def main() -> int:
    import sys
    syms = universe() | set(sys.argv[1:])
    out = build(syms)
    OUT.write_text(json.dumps(out))
    print(f"wrote {OUT.name}: {len(out)} names")
    return 0


def _pct(x, d=0):
    return None if x is None else f"{x * 100:+.{d}f}%"


def read_line(r):
    """Plain-English one-liner a reader would write in the margin."""
    bits = []
    if (r.get("sector") or "") == "Financial Services":
        # banks / insurers / asset managers: cash-flow and EBITDA metrics are meaningless
        if r["p_b"] is not None:
            bits.append(f"P/B {r['p_b']:.2f}")
        if r["pe"] is not None and 0 < r["pe"] < 200:
            bits.append(f"P/E {r['pe']:.1f}")
        if r["roe"] is not None:
            bits.append(f"ROE {r['roe'] * 100:.0f}%")
        if r["div_yield"]:
            bits.append(f"div yld {r['div_yield'] * 100:.1f}%")
        if r["shares_yoy"] is not None and abs(r["shares_yoy"]) >= 0.02:
            bits.append(("buying back " if r["shares_yoy"] < 0 else "diluting ")
                        + f"{abs(r['shares_yoy']) * 100:.0f}%/yr")
        return " · ".join(bits) + " (financial: book/earnings basis)"
    if r["p_b"] is not None:
        bits.append(f"P/B {r['p_b']:.2f}")
    if r["ev_ebitda"] is not None and 0 < r["ev_ebitda"] < 200:
        bits.append(f"EV/EBITDA {r['ev_ebitda']:.1f}×")
    elif r["ps"] is not None:
        bits.append(f"P/S {r['ps']:.1f}")
    if r["fcf_yield"] is not None:
        bits.append(f"FCF yld {r['fcf_yield'] * 100:.0f}%")
    if r["net_cash_pct"] is not None:
        bits.append(("net cash " if r["net_cash_pct"] >= 0 else "net debt ")
                    + f"{abs(r['net_cash_pct']) * 100:.0f}% of mcap")
    if r["rev_growth"] is not None:
        bits.append(f"rev {r['rev_growth'] * 100:+.0f}%")
    if r["op_m"] is not None and abs(r["op_m"]) < 5:
        bits.append(f"op margin {r['op_m'] * 100:.0f}%")
    if r["shares_yoy"] is not None and abs(r["shares_yoy"]) >= 0.02:
        bits.append(("buying back " if r["shares_yoy"] < 0 else "diluting ")
                    + f"{abs(r['shares_yoy']) * 100:.0f}%/yr")
    if r["int_cover"] not in (None, 0) and r["int_cover"] < 1.5 and (r["net_cash_pct"] or 0) < -0.10:
        bits.append(f"interest cover {r['int_cover']:.1f}× ⚠")
    return " · ".join(bits)


# ---------------------------------------------------------------- shared sheet
COLS = [("Ticker", 9), ("Name", 22), ("Sector", 14), ("Mcap $M", 9), ("P/B", 6), ("P/E", 6),
        ("EV/EBITDA", 8), ("FCF yld", 7), ("Net cash/mcap", 9), ("ND/EBITDA", 8),
        ("Rev g", 7), ("Op m", 7), ("ROE", 7), ("Shares YoY", 8), ("Int cover", 7),
        ("52w pos", 7), ("ADV $k", 8), ("Read", 70), ("Data flags", 26)]


def financials_sheet(wb, title, symbols, fin, subtitle="", index=None):
    """Add a financials sheet for `symbols` [(display_ticker, fmp_symbol)]."""
    from openpyxl.styles import Alignment, Font, PatternFill
    ws = wb.create_sheet(title, index) if index is not None else wb.create_sheet(title)
    ws["A1"] = title
    ws["A1"].font = Font(bold=True, size=14, color="1F3864")
    ws["A2"] = subtitle or ("FMP TTM ratios + bulk statements. P/B validated (market cap ÷ latest "
                            "equity, FX-converted); net cash measured inside one statement currency; "
                            "revenue growth = TTM vs prior TTM; shares YoY from diluted weighted shares.")
    ws["A2"].alignment = Alignment(wrap_text=True)
    ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=12)
    ws.row_dimensions[2].height = 30
    for j, (h, w) in enumerate(COLS, 1):
        c = ws.cell(row=4, column=j, value=h)
        c.font, c.fill = Font(bold=True, color="FFFFFF"), PatternFill("solid", fgColor="1F3864")
        ws.column_dimensions[c.column_letter].width = w

    def num(x, d=1):
        return None if x is None else round(x, d)

    def pc(x):
        return None if x is None else f"{x * 100:.0f}%"
    r = 4
    seen = set()
    for disp, s in symbols:
        f = fin.get(s)
        if not f or s in seen:
            continue
        seen.add(s)
        r += 1
        vals = [disp, (f.get("name") or "")[:22], (f.get("sector") or "")[:14],
                num((f.get("mcap") or 0) / 1e6, 0), num(f.get("p_b"), 2), num(f.get("pe"), 1),
                num(f.get("ev_ebitda"), 1), pc(f.get("fcf_yield")), pc(f.get("net_cash_pct")),
                num(f.get("nd_ebitda"), 1), pc(f.get("rev_growth")), pc(f.get("op_m")), pc(f.get("roe")),
                pc(f.get("shares_yoy")), num(f.get("int_cover"), 1), pc(f.get("range_pos")),
                num((f.get("adv_usd") or 0) / 1e3, 0), f.get("read"), "; ".join(f.get("flags") or [])]
        for j, v in enumerate(vals, 1):
            ws.cell(row=r, column=j, value=v)
    ws.freeze_panes = "B5"
    return r - 4


def annotate_workbook(wb, fin, sym_map=None, skip=()):
    """Append an 'FMP financial read' column to every sheet whose header row
    has a 'Ticker' cell, so each listed name carries its numbers. sym_map maps
    a displayed ticker to its FMP symbol (default: identity)."""
    from openpyxl.styles import Alignment, Font, PatternFill
    n = 0
    for ws in wb.worksheets:
        if ws.title in skip:
            continue
        hdr_row = tcol = None
        for row in ws.iter_rows(min_row=1, max_row=min(ws.max_row, 12)):
            for c in row:
                if isinstance(c.value, str) and c.value.strip() in ("Ticker", "TKR", "Symbol"):
                    hdr_row, tcol = c.row, c.column
                    break
            if hdr_row:
                break
        if not hdr_row:
            continue
        col = ws.max_column + 1
        h = ws.cell(row=hdr_row, column=col, value="FMP financial read")
        h.font, h.fill = Font(bold=True, color="FFFFFF"), PatternFill("solid", fgColor="1F3864")
        ws.column_dimensions[h.column_letter].width = 62
        hit = 0
        seen = getattr(wb, "_fin_seen", [])
        for r in range(hdr_row + 1, ws.max_row + 1):
            v = ws.cell(row=r, column=tcol).value
            if not isinstance(v, str) or not v.strip():
                continue
            key = v.replace("●", "").strip()
            sym = (sym_map or {}).get(key, key)
            f = fin.get(sym)
            if f:
                seen.append((key, sym))
                c = ws.cell(row=r, column=col, value=f.get("read") + (
                    "  [" + "; ".join(f["flags"]) + "]" if f.get("flags") else ""))
                c.alignment = Alignment(wrap_text=False)
                hit += 1
        wb._fin_seen = seen
        n += hit > 0
    return n


def add_financials(wb, fin, sym_map=None, skip=(), title="Name Financials", index=None):
    """Annotate every ticker sheet, then add one full financials sheet for
    every name that appears anywhere in the workbook."""
    n = annotate_workbook(wb, fin, sym_map, skip)
    rows = list(dict.fromkeys(getattr(wb, "_fin_seen", [])))
    k = financials_sheet(wb, title, rows, fin, index=index)
    print(f"  financials: read column on {n} sheets; {title} sheet with {k} names")
    return k


def load():
    return json.loads(OUT.read_text()) if OUT.exists() else {}


if __name__ == "__main__":
    raise SystemExit(main())
