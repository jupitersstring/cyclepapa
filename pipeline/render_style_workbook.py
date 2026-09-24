"""Style-subcategory workbook — monochrome academic aesthetic.

Companion to universe_analysis.xlsx. Where that book ranks the FULL universe
flat, this slices the picks BY style of fund originating the signal.
Visual grammar shared via _style_bw.py.
"""
import os, re, sqlite3, statistics
import openpyxl
from openpyxl.utils import get_column_letter
from openpyxl.styles import Font, Alignment

import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fund_moves import quarter_moves, book_info, latest_due_quarter, share_classes, short_fund, section_evidence
from _style_bw import (
    business_line, plain_status,
    first_sentence,
    add_valuation_columns, valuation_lookup,
    write_title, write_section_heading, write_table_header, write_table_rows,
    autosize, write_legend_sheet, add_contents_index, set_print_layout,
    NUMFMT_USD, NUMFMT_PCT, NUMFMT_NUM, NUMFMT_INT, NUMFMT_USD2,
    NUMFMT_MCAP, NUMFMT_M_TO_B,
    BODY_FONT, BODY_ITALIC, SECTION_FONT, MONO_FONT, TICKER_FONT,
    TNR, SIZE_BODY, LAPIS, CRIMSON, color_fixed, color_directional,
)

DB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "cyclepapa.db")
OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "style_analysis.xlsx")

ETFs = {"SPY","QQQ","VOO","IWM","IEF","IEFA","EFA","EEM","BIL","IVV","XBI","HYG",
        "GLD","SLV","TLT","XLE","XLF","XLK","XLY","XLP","XLU","XLI","XLV","XLB","XLRE",
        "ARKK","JNK","LQD","TIP","AGG","BND","VEA","VWO","SHY"}

EQUITY_SQL = ("h.sh_type IN ('SH','') AND substr(h.cusip,7,1) BETWEEN '0' AND '9' "
              "AND substr(h.cusip,8,1) BETWEEN '0' AND '9'")
# unmapped 13F lines that are index products (hedges / index exposure), not picks
_INDEX_PRODUCT = re.compile(r"ISHARES|SPDR|VANGUARD|INVESCO|\bETF|PROSHARES|DIREXION|SELECT SECTOR|"
                            r"WISDOMTREE|GLOBAL X|VANECK|\bINDEX\b|\bTR\b|TRUST|\bFDS?\b|FUND", re.I)
# styles whose books are diversified by design: holder counts there read crowding
DIVERSIFIED = {"Mega Multi-Strats / Quants", "CTA / Trend Followers"}

class StyleData:
    """What every style sheet reads, computed once: one 13F book per manager
    (name variants such as 'AKO Capital LLP' and 'AKO Capital (Nicolai Tangen)'
    share one book and count once), share classes merged (GOOG into GOOGL),
    each fund's vote weight min(1, 75 / positions), and the latest quarter's
    position moves (fund_moves — the same rules as the Revealed Preference score)."""

    def __init__(self, conn):
        self.conn = conn
        self.quarter = latest_due_quarter()
        self.moves, self.fresh_funds = quarter_moves(conn, self.quarter)
        self.info = book_info(conn)
        from _canon import canon
        self._cn = canon
        self.cls = share_classes(conn)
        self.classes = {}
        for t, prim in self.cls.items():
            self.classes.setdefault(prim, []).append(t)
        rep = {}
        for f, d in self.info.items():
            if d["n"]:
                m = self.cn(f)
                if m not in rep or d["n"] > self.info[rep[m]]["n"]:
                    rep[m] = f
        self.rep = rep
        self.hold, self.unmapped = {}, {}
        for f, tk, iss, cusip, pct in conn.execute(f"""SELECT h.fund, h.ticker, MAX(h.issuer), MAX(h.cusip),
                SUM(h.pct_book) FROM fund_13f_holdings h WHERE {EQUITY_SQL}
                GROUP BY h.fund, COALESCE(h.ticker, h.cusip)"""):
            m = self.cn(f)
            if rep.get(m) != f:
                continue
            if tk:
                t = self.cls.get(tk, tk)
                d = self.hold.setdefault(m, {})
                d[t] = d.get(t, 0.0) + (pct or 0.0)
            elif not _INDEX_PRODUCT.search(iss or ""):
                self.unmapped.setdefault(m, []).append((pct or 0.0, iss or "", cusip))
        self.fresh = {self.cn(f) for f in self.fresh_funds}
        self.move_at = {}
        for mv in self.moves:
            self.move_at[(self.cn(mv["fund"]), self.cls.get(mv["ticker"], mv["ticker"]))] = mv
        self.display = {}
        for f in [r[0] for r in conn.execute("SELECT fund FROM fund_style")] + list(self.info):
            m = self.cn(f)
            if m not in self.display or f == rep.get(m):
                self.display[m] = short_fund(f)
        self.members = {}
        for f, st in conn.execute("SELECT fund, macro_style FROM fund_style"):
            self.members.setdefault(st, set()).add(self.cn(f))
        self.meta = {}
        for r in conn.execute("""SELECT us.ticker, us.sec_type, COALESCE(tm.name, y.long_name, us.name),
                us.mcap_m, us.mcap_bucket, us.ev_ebitda, us.pb_ratio, us.activist_max_pct,
                us.insider_cluster_dollars_m, us.form4_buy_usd_m, us.form4_sell_usd_m, us.smart_money_n,
                us.score, ps.mom_3mo, y.industry
            FROM unified_signal us LEFT JOIN ticker_meta tm ON tm.ticker = us.ticker
            LEFT JOIN ticker_yf y ON y.ticker = us.ticker
            LEFT JOIN price_stats ps ON ps.ticker = us.ticker"""):
            self.meta[r[0]] = {"sec": r[1], "name": r[2], "mcap": r[3], "bucket": r[4], "ev": r[5], "pb": r[6],
                               "act": r[7], "clu": r[8], "f4b": r[9], "f4s": r[10], "sm": r[11], "score": r[12],
                               "mom": r[13], "industry": r[14]}

    def cn(self, f):
        return self._cn(f)

    def focus(self, m):
        return (self.info.get(self.rep.get(m)) or {}).get("focus") or 0.0

    def with_book(self, managers):
        return {m for m in managers if m in self.hold}

    def is_pick(self, t):
        """An operating common stock (not an ETF, SPAC shell, warrant, preferred)."""
        mt = self.meta.get(t) or {}
        return ((mt.get("sec") or "common") == "common" and t not in ETFs
                and (mt.get("industry") or "") != "Shell Companies")

    def name(self, t):
        nm = (self.meta.get(t) or {}).get("name") or ""
        others = self.classes.get(t)
        return nm + (f" (with {', '.join(sorted(others))})" if others else "")

    def agg(self, managers):
        """{ticker: {'h': [(% of book, manager)...], 'n', 'wtd', 'max', 'n5'}}."""
        out = {}
        for m in managers:
            w = self.focus(m)
            for t, pct in self.hold.get(m, {}).items():
                a = out.setdefault(t, {"h": [], "wtd": 0.0})
                a["h"].append((pct, m))
                a["wtd"] += w
        for a in out.values():
            a["h"].sort(key=lambda x: -x[0])
            a["n"], a["max"] = len(a["h"]), a["h"][0][0]
            a["n5"] = sum(1 for p, _ in a["h"] if p >= 5)
        return out

    def moves_for(self, managers):
        """{ticker: {'net', 'buy': [moves], 'sell': [moves]}} for the latest quarter."""
        out = {}
        for mv in self.moves:
            if self.cn(mv["fund"]) not in managers:
                continue
            d = out.setdefault(self.cls.get(mv["ticker"], mv["ticker"]), {"net": 0.0, "buy": [], "sell": []})
            d["net"] += mv["pts"]
            (d["buy"] if mv["kind"] in ("new", "add") else d["sell"]).append(mv)
        return out

    def sections(self, managers):
        """{ticker: [S1, S3, S4]} — number of the managers per section, from
        the score's own evidence (fund_moves.section_evidence): the latest 13F
        quarter's new / added positions where a fund has a current book,
        researcher notes otherwise, S1 only while held."""
        if not hasattr(self, "_ev"):
            self._ev, _ = section_evidence(self.conn, self.quarter)
        sets = {}
        for tk, secs in self._ev.items():
            t = self.cls.get(tk, tk)
            for sec in (1, 3, 4):
                ms = set(secs.get(sec, {})) & managers
                if ms:
                    sets.setdefault(t, {1: set(), 3: set(), 4: set()})[sec] |= ms
        return {t: [len(d[1]), len(d[3]), len(d[4])] for t, d in sets.items()}

    def held_by(self, h, k=4):
        s = "; ".join(f"{self.display.get(m, m)} {p:.1f}%" for p, m in h[:k])
        return s + (f"; +{len(h) - k} more" if len(h) > k else "")

    def who(self, moves):
        return "; ".join(f"{self.display.get(self.cn(mv['fund']), short_fund(mv['fund']))} ({mv['label']})"
                         for mv in sorted(moves, key=lambda mv: -abs(mv["pts"])))

    @staticmethod
    def last_qtr(d):
        if not d:
            return ""
        return f"+{len({mv['fund'] for mv in d['buy']})} / -{len({mv['fund'] for mv in d['sell']})}"

    def style_line(self, managers):
        """'133 funds · 94 with a 13F book for 2026-06-30 · median 38 positions'."""
        booked = [m for m in managers if (self.info.get(self.rep.get(m)) or {}).get("period") == self.quarter]
        ns = [self.info[self.rep[m]]["n"] for m in managers if m in self.rep]
        med = f" · median {statistics.median(ns):.0f} positions per book" if ns else ""
        return f"{len(managers)} funds · {len(booked)} with a 13F book for {self.quarter}{med}"

_SD = None
def style_data(conn):
    global _SD
    if _SD is None:
        _SD = StyleData(conn)
    return _SD

def _mom(v):
    return round(v, 0) if v is not None else ""

def _r(v, nd=1):
    return round(v, nd) if v is not None else ""

# Excel: ≤31 chars, no /\?*[]
def safe_sheet_name(name):
    s = name.replace("/", "-").replace("\\", "-").replace("?","").replace("*","")
    s = s.replace("[","(").replace("]",")").replace(":", "-")
    return s[:31]

def style_macro_list(conn):
    return list(conn.execute("""SELECT macro_style, COUNT(*) FROM fund_style
        WHERE macro_style IS NOT NULL
        GROUP BY macro_style ORDER BY 2 DESC"""))

def sheet_readme(wb, conn):
    ws = wb.create_sheet("README", 0)
    sd = style_data(conn)
    n_f = conn.execute("SELECT COUNT(*) FROM fund_style").fetchone()[0]
    n_s = conn.execute("SELECT COUNT(DISTINCT macro_style) FROM fund_style").fetchone()[0]
    n_cur = sum(1 for m in sd.rep if (sd.info.get(sd.rep[m]) or {}).get("period") == sd.quarter)
    res_asof = conn.execute("SELECT MIN(asof), MAX(asof) FROM fund_positions").fetchone()
    write_title(ws,
        "Funds by Investing Style",
        f"What each style of manager owns, bought and sold. {n_f} funds in {n_s} styles; {n_cur} managers have a "
        f"13F book for the quarter ended {sd.quarter}.", 1)
    ws.column_dimensions["A"].width = 110
    styles = style_macro_list(conn)
    rows = [
        ("",),
        ("How to use this book",),
        ("1. Overview — every style side by side: what each bought and sold most last quarter, then its most-held names.",),
        (f"2. One sheet per style ({n_s}), each in the same order:",),
        ("     Bought last quarter — names the style's funds opened or added to, ranked by net % of book moved, with who",),
        ("        bought and who sold (e.g. 'new 4.1%', '+38% to 6.0%'). Start here for what the style is doing now.",),
        ("     Sold last quarter — the same for exits and trims.",),
        ("     Signature picks — names this style holds far more often than the universe does (its distinctive bets).",),
        ("     Most held — ranked by holders weighted by each fund's focus, so 20-name books outweigh 1,800-name ones.",),
        ("     Concentration leaders — single positions of 5%+ of a fund's book, with that fund's move last quarter.",),
        ("     Researcher notes — the research spreadsheet's new-position and add sections, kept as written;",),
        ("        'Still Held' checks each against the funds' latest 13F.",),
        ("     By size bucket — the top 5 per market-cap class (nano to mega).",),
        ("3. Sub-Group Tiers — the same view within narrower peer groups (e.g. US Activists Tier 1), members named.",),
        ("4. Fund Roster — every fund: whether its 13F book is current, how concentrated it is, what its vote weighs,",),
        ("   and in plain English why a fund has no 13F data (non-US manager, below the $100M threshold, ...).",),
        ("5. Legend — every column defined.  6. Ticker Reference — every symbol: name, industry, what it does.",),
        ("",),
        ("Data as of",),
        (f"13F books: quarter ended {sd.quarter} (filed by mid-August), compared with each fund's previous quarter. "
         f"Moves read for {len(sd.fresh_funds)} managers.",),
        (f"Researcher notes: a spreadsheet compiled {res_asof[0]} to {res_asof[1]}, describing mostly Q4 2025 – Q1 2026 "
         f"filings.",),
        ("   Where a fund has a current 13F book, its latest filing supersedes the notes (S3 / S4 from the filing; S1",),
        ("   top picks counted only while still held). Funds without a 13F keep their notes: they are all we have.",),
        ("Prices, market caps and multiples: FMP, refreshed with each build.",),
        ("",),
        ("Reading the numbers",),
        ("Vote Wt = min(1, 75 / positions): a focused book votes fully; a 750-name book 0.1; an 1,800-name quant 0.04.",),
        ("Net Pts = % of book bought minus sold across the style's funds (capped at 10 per fund, times Vote Wt). A line new",),
        ("   at an IPO counts half (an allocation, or a pre-IPO stake becoming reportable); a spin-off received counts zero.",),
        ("Share classes of one company (GOOG + GOOGL, BRK-A + BRK-B) count as one holding here.",),
        ("Moves under 0.5% of a book are housekeeping and not shown.",),
        ("",),
        ("Styles",),
    ]
    for st, c_count in styles:
        managers = sd.members.get(st, set())
        rows.append((f"{st:<40} {sd.style_line(managers)}"
                     + ("   (diversified: counts show crowding)" if st in DIVERSIFIED else ""),))
    rows += [
        ("",),
        ("Score (the universe book's unified score, shown as 'Score')",),
        ("score = 2 × ln(1 + weighted 13F holders) + 3 × S3 (cap 8) + 1.5 × S4 (cap 10) + 2 × S1 (cap 12)",),
        ("      + 0.5 × activist 13D/G stake % (cap 30) + 0.6 × largest % of a book (cap 25)",),
        ("      + 1.5 × funds with 5%+ of book (cap 12) + insider buy cluster (5 / 10 / 15) + 3 × ln(1 + cluster $M)",),
        ("      + 2 × ln(1 + insider buys $M) + 2 × ln(1 + buys in 30 days) − 1.5 × ln(1 + insider sells $M) (and 30-day)",),
        ("      + small-cap bonus (+5 under $300M, +3 under $2B) + entry setup + 8-K catalysts (M&A +5, control +4, ...)",),
        ("All inputs are primary filings (13F, 13D/G, Form 4, 8-K, N-PORT) plus FMP market data. No memory-based picks.",),
    ]
    for i, r in enumerate(rows, 4):
        c = ws.cell(row=i, column=1, value=r[0])
        ws.row_dimensions[i].height = 18
        if not r[0].strip():
            continue
        if r[0] in ("How to use this book", "Data as of", "Reading the numbers", "Styles") or r[0].startswith("Score ("):
            c.font = SECTION_FONT
        elif r[0].startswith(("score", "      ")) or r[0][:40].strip() in {st for st, _ in styles}:
            c.font = MONO_FONT
        else:
            c.font = BODY_FONT

def _fmt(ws, row, n, fmts):
    """Apply {column: number_format} to n rows starting at `row`."""
    for ridx in range(row, row + n):
        for col, f in fmts.items():
            ws.cell(row=ridx, column=col).number_format = f

def write_moves_section(ws, sd, managers, row, title, buying, width, limit):
    """The style's latest-quarter buying (or selling), ranked by net % of book
    moved. Returns the next free row."""
    mv = sd.moves_for(managers)
    rows = [(t, d) for t, d in mv.items() if sd.is_pick(t) and ((d["net"] > 0) if buying else (d["net"] < 0))]
    rows.sort(key=lambda x: -x[1]["net"] if buying else x[1]["net"])
    write_section_heading(ws, row, title, width)
    row += 1
    if buying:
        hdr = ["Ticker", "Net Pts", "Buyers", "Sellers", "Who Bought", "Who Sold", "3M Chg %", "Mcap", "Bucket",
               "EV/EBITDA", "P/B", "St Held", "Name", "Industry", "Business"]
    else:
        hdr = ["Ticker", "Net Pts", "Sellers", "Buyers", "Who Sold", "Who Bought", "3M Chg %", "Mcap", "Bucket",
               "EV/EBITDA", "P/B", "St Held", "Name", "Industry", "Business"]
    write_table_header(ws, row, hdr)
    row += 1
    held = sd.agg(sd.with_book(managers))
    out = []
    for t, d in rows[:limit]:
        mt = sd.meta.get(t) or {}
        nb, ns = len({x["fund"] for x in d["buy"]}), len({x["fund"] for x in d["sell"]})
        first, second = (d["buy"], d["sell"]) if buying else (d["sell"], d["buy"])
        ind, bus = desc_for(conn_of(sd), t)
        out.append([t, round(d["net"], 1), nb if buying else ns, ns if buying else nb,
                    sd.who(first), sd.who(second), _mom(mt.get("mom")), mt.get("mcap") or "",
                    mt.get("bucket") or "", _r(mt.get("ev")), _r(mt.get("pb"), 2),
                    (held.get(t) or {}).get("n", 0), sd.name(t), ind, bus])
    if not out:
        ws.cell(row=row, column=1, value="None: no fund in this style with a current 13F book moved 0.5%+ of its book "
                                         "into or out of a common stock last quarter.").font = BODY_ITALIC
        return row + 2
    write_table_rows(ws, out, row)
    color_directional(ws, row, row + len(out) - 1, [2, 7], higher_is_better=True)
    _fmt(ws, row, len(out), {2: '0.0', 7: '0"%"', 8: NUMFMT_MCAP, 10: '0.0"x"', 11: '0.00"x"'})
    return row + len(out) + 2

def conn_of(sd):
    return sd.conn

def write_style_sheet(wb, conn, macro_style, sheet_name):
    ws = wb.create_sheet(sheet_name)
    sd = style_data(conn)
    managers = sd.members.get(macro_style, set())
    booked = sd.with_book(managers)
    # ---- SIGNATURE PICKS: where this style over-indexes vs the universe ----
    # lift = (style holder-share) / (universe holder-share), counted over
    # managers with a 13F book (one per manager). A name held by a much larger
    # fraction of THIS style than of all funds is the style's fingerprint; this
    # is what stops GOOGL/AMZN topping every style sheet identically.
    everyone = set(sd.hold)
    uni = sd.agg(everyone)
    sty = sd.agg(booked)
    n_style, n_univ = len(booked) or 1, len(everyone) or 1
    min_holders = 2 if n_style < 8 else 3   # adaptive: small styles need only 2 holders
    moves = sd.moves_for(managers)
    sig = []
    for t, a in sty.items():
        mt = sd.meta.get(t) or {}
        if a["n"] >= min_holders and sd.is_pick(t) and (mt.get("score") or 0) > 0 and t in uni:
            sig.append((t, (a["n"] / n_style) / (uni[t]["n"] / n_univ), a))
    sig.sort(key=lambda x: (-x[1], -x[2]["n"]))
    sig = sig[:12]
    # only rows genuinely OVER-weighted (lift >= 1.2) belong under a "distinctive
    # over-weights" heading; a saturated/uniform lift column carries no signal.
    sig = [x for x in sig if x[1] >= 1.2]
    if len({round(x[1], 1) for x in sig}) <= 1 and len(sig) > 5:
        sig = []   # lift saturated (tiny style where st==uni) — section is noise
    line = sd.style_line(managers)
    crowd = (" These books are diversified by design: holder counts here show crowding, not conviction."
             if macro_style in DIVERSIFIED else "")
    sub = (f"{line}. Sections: what the style bought and sold in the {sd.quarter} quarter (13F vs the quarter "
           f"before) · {'signature picks (where it over-indexes on the universe) · ' if sig else ''}most held "
           f"(weighted by each fund's focus) · concentration leaders · researcher notes · a size cross-cut.{crowd}")
    if not sig:
        sub += " Too few funds for a distinctive-lift ranking, so no signature-picks section."
    write_title(ws, macro_style, sub, 17)
    row = 4
    row = write_moves_section(ws, sd, managers, row,
                              f"Bought last quarter — the style's net buying in {sd.quarter} 13Fs", True, 15, 25)
    row = write_moves_section(ws, sd, managers, row,
                              f"Sold last quarter — the style's net selling in {sd.quarter} 13Fs", False, 15, 20)
    if sig:
        write_section_heading(ws, row, "Signature picks — this style's distinctive over-weights (by lift)", 17); row += 1
        write_table_header(ws, row, ["Ticker", "Lift", "St Held", "Uni Held", "Score", "Bucket", "EV/EBITDA",
                                     "pB Max", "Held By", "Last Qtr", "Name"]); row += 1
        sout = []
        for t, lift, a in sig:
            mt = sd.meta.get(t) or {}
            sout.append([t, round(lift, 1), a["n"], uni[t]["n"], _r(mt.get("score")), mt.get("bucket") or "",
                         _r(mt.get("ev")), round(a["max"], 1), sd.held_by(a["h"]), sd.last_qtr(moves.get(t)),
                         sd.name(t)])
        write_table_rows(ws, sout, row, ticker_col=1)
        _fmt(ws, row, len(sout), {2: '0.0"× univ"', 5: '0.0', 7: '0.0"x"', 8: '0.0"%"'})
        row += len(sout) + 2
    write_section_heading(ws, row, "Most held — ranked by holders weighted by each fund's focus (a 20-name book "
                                   "counts 1, a 750-name book 0.1)", 17)
    row += 1
    hdr = ["Ticker", "St Holders", "St Wtd", "pB Max", "pB ≥5%", "Last Qtr", "Held By", "S3", "S4", "S1", "Mcap",
           "Bucket", "EV/EBITDA", "P/B", "Act %", "Clu $M", "F4 Buy", "Name", "Industry", "Business"]
    write_table_header(ws, row, hdr)
    row += 1
    secs = sd.sections(managers)
    top = sorted(((t, a) for t, a in sty.items() if sd.is_pick(t)), key=lambda x: (-x[1]["wtd"], -x[1]["max"]))[:30]
    out = []
    for t, a in top:
        mt = sd.meta.get(t) or {}
        s1, s3, s4 = secs.get(t, [0, 0, 0])
        ind, bus = desc_for(conn, t)
        out.append([t, a["n"], round(a["wtd"], 1), round(a["max"], 1), a["n5"], sd.last_qtr(moves.get(t)),
                    sd.held_by(a["h"]), s3, s4, s1, mt.get("mcap") or "", mt.get("bucket") or "",
                    _r(mt.get("ev")), _r(mt.get("pb"), 2), round(mt.get("act") or 0, 1),
                    _r(mt.get("clu")) if mt.get("clu") else "", _r(mt.get("f4b")) if mt.get("f4b") else "",
                    sd.name(t), ind, bus])
    write_table_rows(ws, out, row)
    # colour is data: activist stake / cluster $ / insider buys = lapis (all are
    # positive signals whose presence is the read).
    color_fixed(ws, row, row + len(out) - 1, [15, 16, 17], LAPIS)  # Act %, Clu $M, F4 Buy
    _fmt(ws, row, len(out), {3: '0.0', 4: NUMFMT_PCT, 11: NUMFMT_MCAP, 13: '0.0"x"', 14: '0.00"x"',
                             15: NUMFMT_PCT, 16: NUMFMT_M_TO_B, 17: NUMFMT_M_TO_B})
    row += len(out) + 2

    # Concentration leaders
    write_section_heading(ws, row, "Concentration leaders — single-fund positions of 5%+ of book, with last "
                                   "quarter's move", 13)
    row += 1
    hdr3 = ["Ticker", "Fund", "%Book", "Last Qtr", "Uni 13F wtd", "Mcap", "Bucket", "EV/EBITDA", "P/B", "Name"]
    write_table_header(ws, row, hdr3)
    row += 1
    lines = []
    for m in booked:
        for t, pct in sd.hold[m].items():
            if 5 <= pct <= 100 and sd.is_pick(t):
                lines.append((pct, m, t, None))
        for pct, iss, cusip in sd.unmapped.get(m, []):
            if 5 <= pct <= 100:
                lines.append((pct, m, None, f"{iss} (CUSIP {cusip}, no ticker mapped)"))
    lines.sort(key=lambda x: -x[0])
    out = []
    for pct, m, t, label in lines[:20]:
        mt = sd.meta.get(t) or {}
        mv = sd.move_at.get((m, t)) if t else None
        lq = mv["label"] if mv else ("held, little changed" if m in sd.fresh else "")
        out.append([t or "—", sd.display.get(m, m), round(pct, 1), lq, _r(mt.get("sm")) if t else "",
                    mt.get("mcap") or "", mt.get("bucket") or "", _r(mt.get("ev")), _r(mt.get("pb"), 2),
                    label or sd.name(t)])
    write_table_rows(ws, out, row)
    _fmt(ws, row, len(out), {3: NUMFMT_PCT, 6: NUMFMT_MCAP, 8: '0.0"x"', 9: '0.00"x"'})
    row += len(out) + 2

    # Researcher notes — the spreadsheet's sections 3 and 4, kept as written;
    # "Still Held" checks each against the funds' latest 13F books
    ph = ",".join("?" * len(managers)) or "''"
    style_funds = [r[0] for r in conn.execute("SELECT fund FROM fund_style WHERE macro_style = ?", (macro_style,))]
    phf = ",".join("?" * len(style_funds)) or "''"
    for sec, title in ((3, "New major positions — researcher notes, section 3"),
                       (4, "Material adds — researcher notes, section 4")):
        write_section_heading(ws, row, f"{title} (compiled May–June 2026 from mostly Q4 2025 – Q1 2026 filings; "
                                       f"Still Held checks the latest 13F)", 13)
        row += 1
        write_table_header(ws, row, ["Ticker", f"St S{sec} #", "Still Held", "Uni 13F wtd", "pB Max", "Mcap",
                                     "Bucket", "EV/EBITDA", "P/B", "Act %", "Name"])
        row += 1
        rows = list(conn.execute(f"""
            SELECT fp.ticker, GROUP_CONCAT(DISTINCT fp.fund)
            FROM fund_positions fp
            WHERE fp.fund IN ({phf}) AND fp.section = ? AND fp.ticker IS NOT NULL
            GROUP BY fp.ticker""", style_funds + [sec]))
        ranked = []
        for tk, funds in rows:
            if tk in ETFs or ((sd.meta.get(tk) or {}).get("sec") or "common") != "common":
                continue
            ms = {sd.cn(f) for f in (funds or "").split(",")}
            t = sd.cls.get(tk, tk)
            checkable = [m for m in ms if m in sd.fresh]
            still = sum(1 for m in checkable if t in sd.hold.get(m, {}))
            ranked.append((len(ms), tk, t, still, len(checkable)))
        ranked.sort(key=lambda x: (-x[0], x[1]))
        out = []
        for n, tk, t, still, chk in ranked[:20]:
            mt = sd.meta.get(tk) or {}
            out.append([tk, n, f"{still} of {chk}" if chk else "no current 13F", _r(mt.get("sm")),
                        _r((sty.get(t) or {}).get("max")), mt.get("mcap") or "", mt.get("bucket") or "",
                        _r(mt.get("ev")), _r(mt.get("pb"), 2), _r(mt.get("act")) if mt.get("act") else "",
                        sd.name(tk)])
        write_table_rows(ws, out, row)
        _fmt(ws, row, len(out), {5: NUMFMT_PCT, 6: NUMFMT_MCAP, 8: '0.0"x"', 9: '0.00"x"', 10: NUMFMT_PCT})
        row += len(out) + 2

    # Size cross-cut — ranked on conviction: weighted holders and the largest
    # position; a name must be 1%+ of some style fund's book to qualify (a
    # 0.4% line held by one fund says nothing), filled from the rest if short
    write_section_heading(ws, row, "By size bucket — top 5 within the style per market-cap class (1%+ of a "
                                   "style fund's book first)", 13)
    row += 1
    write_table_header(ws, row, ["Bucket", "Ticker", "Holders", "pB Max", "Held By", "Mcap", "S3", "S4", "Act %",
                                 "EV/EBITDA", "P/B", "Name"])
    row += 1
    out = []
    for bucket in ["nano", "micro", "small", "mid", "large", "mega"]:
        cand = [(t, a) for t, a in sty.items() if sd.is_pick(t) and (sd.meta.get(t) or {}).get("bucket") == bucket]
        cand.sort(key=lambda x: (x[1]["max"] < 1, -(x[1]["wtd"] * 2 + min(x[1]["max"], 25) * 0.5)))
        for t, a in cand[:5]:
            mt = sd.meta.get(t) or {}
            s1, s3, s4 = secs.get(t, [0, 0, 0])
            out.append([bucket, t, a["n"], round(a["max"], 1), sd.held_by(a["h"], 3), mt.get("mcap") or "",
                        s3, s4, round(mt.get("act") or 0, 1), _r(mt.get("ev")), _r(mt.get("pb"), 2), sd.name(t)])
    write_table_rows(ws, out, row, ticker_col=2)
    _fmt(ws, row, len(out), {4: NUMFMT_PCT, 6: NUMFMT_MCAP, 9: NUMFMT_PCT, 10: '0.0"x"', 11: '0.00"x"'})
    ws.freeze_panes = "B5"
    autosize(ws)
    ws.column_dimensions["A"].width = 10
    for col, w in ((5, 60), (6, 60), (7, 44)):
        ws.column_dimensions[get_column_letter(col)].width = w
    ws.column_dimensions[get_column_letter(19)].width = 24   # Industry (Most held)
    ws.column_dimensions[get_column_letter(20)].width = 80   # Business (Most held)

def sheet_overview(wb, conn):
    ws = wb.create_sheet("Overview")
    sd = style_data(conn)
    write_title(ws, "Universe Overview by Style",
                f"First, every style side by side: what its funds bought and sold most in the {sd.quarter} quarter. "
                f"Then, per style, the 10 most-held names (holders weighted by each fund's focus, share classes "
                f"merged) with last quarter's buyers / sellers and the largest holders.", 16)
    row = 4
    write_section_heading(ws, row, f"Every style at a glance — {sd.quarter} 13F quarter", 16)
    row += 1
    write_table_header(ws, row, ["Style", "Funds", "Current Books", "Median Positions", "Bought Most (net pts)",
                                 "Sold Most (net pts)"])
    row += 1
    out = []
    for ms, count in style_macro_list(conn):
        managers = sd.members.get(ms, set())
        mv = sd.moves_for(managers)
        picks = [(t, d["net"]) for t, d in mv.items() if sd.is_pick(t)]
        buys = sorted([x for x in picks if x[1] > 0], key=lambda x: -x[1])[:5]
        sells = sorted([x for x in picks if x[1] < 0], key=lambda x: x[1])[:5]
        booked = [m for m in managers if (sd.info.get(sd.rep.get(m)) or {}).get("period") == sd.quarter]
        ns = [sd.info[sd.rep[m]]["n"] for m in managers if m in sd.rep]
        out.append([ms, len(managers), len(booked), round(statistics.median(ns)) if ns else "",
                    ", ".join(f"{t} {v:+.1f}" for t, v in buys), ", ".join(f"{t} {v:+.1f}" for t, v in sells)])
    write_table_rows(ws, out, row, ticker_col=None)
    row += len(out) + 2
    for ms, count in style_macro_list(conn):
        managers = sd.members.get(ms, set())
        write_section_heading(ws, row, f"{ms} — {sd.style_line(managers)}", 16)
        row += 1
        hdr = ["Ticker", "St Holders", "St Wtd", "pB Max", "pB ≥5%", "Last Qtr", "S3", "S4", "Mcap", "Bucket",
               "EV/EBITDA", "P/B", "Act %", "Clu $M", "F4 Buy", "Sell", "Held By", "Name"]
        write_table_header(ws, row, hdr)
        row += 1
        sty = sd.agg(sd.with_book(managers))
        mv = sd.moves_for(managers)
        secs = sd.sections(managers)
        top = sorted(((t, a) for t, a in sty.items() if sd.is_pick(t)),
                     key=lambda x: (-x[1]["wtd"], -x[1]["max"]))[:10]
        out = []
        for t, a in top:
            mt = sd.meta.get(t) or {}
            s1, s3, s4 = secs.get(t, [0, 0, 0])
            out.append([t, a["n"], round(a["wtd"], 1), round(a["max"], 1), a["n5"], sd.last_qtr(mv.get(t)), s3, s4,
                        mt.get("mcap") or "", mt.get("bucket") or "", _r(mt.get("ev")), _r(mt.get("pb"), 2),
                        round(mt.get("act") or 0, 1), _r(mt.get("clu")) if mt.get("clu") else "",
                        _r(mt.get("f4b")) if mt.get("f4b") else "", _r(mt.get("f4s")) if mt.get("f4s") else "",
                        sd.held_by(a["h"], 3), sd.name(t)])
        write_table_rows(ws, out, row)
        _fmt(ws, row, len(out), {3: '0.0', 4: NUMFMT_PCT, 9: NUMFMT_MCAP, 11: '0.0"x"', 12: '0.00"x"',
                                 13: NUMFMT_PCT, 14: NUMFMT_M_TO_B, 15: NUMFMT_M_TO_B, 16: NUMFMT_M_TO_B})
        row += len(out) + 2
    autosize(ws)
    ws.column_dimensions["A"].width = 30
    ws.column_dimensions["E"].width = 58
    ws.column_dimensions["F"].width = 58

def sheet_subgroup_focus(wb, conn):
    """Sub_group tier picks. Multi-fund sub_groups shown explicitly;
    single-fund specialists consolidated into a 'Specialist Funds' bucket
    per macro_style so every fund is visible without 90 separate sections."""
    multi = list(conn.execute("""SELECT macro_style, sub_group, COUNT(*) c
        FROM fund_style WHERE sub_group IS NOT NULL AND macro_style IS NOT NULL
        GROUP BY macro_style, sub_group
        HAVING c >= 2
        ORDER BY macro_style, c DESC, sub_group"""))
    # All singletons grouped per macro_style
    singletons = {}
    for r in conn.execute("""SELECT macro_style, sub_group, fund FROM fund_style
        WHERE sub_group IS NOT NULL AND macro_style IS NOT NULL
        AND sub_group IN (SELECT sub_group FROM fund_style GROUP BY sub_group HAVING COUNT(*) = 1)
        ORDER BY macro_style, sub_group"""):
        singletons.setdefault(r[0], []).append((r[1], r[2]))

    ws = wb.create_sheet("Sub-Group Tiers")
    sd = style_data(conn)
    write_title(ws, "Sub-Group Tier Picks",
                "Multi-fund tiers shown explicitly, each with its member funds named and its top 8 names "
                "(holders one per manager, weighted by focus; Last Qtr = buyers / sellers in the tier last quarter). "
                "Single-fund specialists consolidated per macro_style — every fund is visible.", 13)
    # Group multi-fund subgroups by macro_style so we can render the
    # singletons-roll-up right after each macro's multi-fund tiers.
    multi_by_macro = {}
    for ms, sg, n in multi:
        multi_by_macro.setdefault(ms, []).append((sg, n))
    all_macros = sorted(set(list(multi_by_macro) + list(singletons)))

    row = 4
    for ms in all_macros:
        ws.row_dimensions[row].height = 22
        ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=13)
        c = ws.cell(row=row, column=1, value=ms.upper())
        c.font = Font(name=TNR, bold=True, size=SIZE_BODY + 1, color="000000")
        c.alignment = Alignment(horizontal="left", vertical="bottom")
        row += 1
        # Multi-fund sub_groups for this macro_style — EACH gets its own
        # heading + tier table (previously only the last one rendered).
        hdr = ["Ticker", "Sub Holders", "Sub Wtd", "pB Max", "Last Qtr", "Held By", "Mcap", "Bucket", "S3", "S4",
               "Act %", "Clu $M", "F4 $M", "EV/EBITDA", "P/B", "Name"]
        for sg, n in multi_by_macro.get(ms, []):
            write_section_heading(ws, row, f"  {sg}  ({n} funds)", 13)
            row += 1
            sg_funds = [r[0] for r in conn.execute(
                "SELECT fund FROM fund_style WHERE sub_group = ? ORDER BY fund", (sg,))]
            # name every member fund so the tier is self-documenting
            ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=13)
            fc = ws.cell(row=row, column=1, value="     " + "  ·  ".join(sg_funds))
            fc.font = BODY_ITALIC
            fc.alignment = Alignment(horizontal="left", vertical="center")
            row += 1
            write_table_header(ws, row, hdr)
            row += 1
            if not sg_funds:
                row += 1
                continue
            managers = {sd.cn(f) for f in sg_funds}
            sub = sd.agg(sd.with_book(managers))
            mv = sd.moves_for(managers)
            secs = sd.sections(managers)
            # ranked as before (holders × 2 + largest position × 0.5), holders
            # now one per manager and weighted by focus
            top = sorted(((t, a) for t, a in sub.items() if sd.is_pick(t)),
                         key=lambda x: -(x[1]["wtd"] * 2 + min(x[1]["max"], 100) * 0.5))[:8]
            out = []
            for t, a in top:
                mt = sd.meta.get(t) or {}
                s1, s3, s4 = secs.get(t, [0, 0, 0])
                out.append([t, a["n"], round(a["wtd"], 1), round(a["max"], 1), sd.last_qtr(mv.get(t)),
                            sd.held_by(a["h"], 3), mt.get("mcap") or "", mt.get("bucket") or "", s3, s4,
                            round(mt.get("act") or 0, 1), _r(mt.get("clu")) if mt.get("clu") else "",
                            _r(mt.get("f4b")) if mt.get("f4b") else "", _r(mt.get("ev")), _r(mt.get("pb"), 2),
                            sd.name(t)])
            if not out:
                ws.cell(row=row, column=1, value="No 13F common-stock holdings on file for these funds "
                                                  "(non-US managers or non-filers: see Fund Roster).").font = BODY_ITALIC
                row += 2
                continue
            write_table_rows(ws, out, row)
            _fmt(ws, row, len(out), {3: '0.0', 4: NUMFMT_PCT, 7: NUMFMT_MCAP, 11: NUMFMT_PCT, 12: NUMFMT_M_TO_B,
                                     13: NUMFMT_M_TO_B, 14: '0.0"x"', 15: '0.00"x"'})
            row += len(out) + 2
        # ── end inner sub_group loop ──

        # SPECIALIST FUNDS — consolidate all singletons in this macro_style
        macro_singletons = singletons.get(ms, [])
        if macro_singletons:
            write_section_heading(ws, row,
                f"  Specialist Funds — {len(macro_singletons)} single-fund sub_groups consolidated",
                11)
            row += 1
            spec_hdr = ["Fund","Sub-Group","Top Holding","%Book","13F #","Mcap","Bucket","Book"]
            write_table_header(ws, row, spec_hdr)
            row += 1
            spec_out = []
            for sg, fund in macro_singletons:
                # Top 1 holding for this fund (by value)
                top = conn.execute("""SELECT h.ticker, h.pct_book,
                       us.smart_money_n, us.mcap_m, us.mcap_bucket
                    FROM fund_13f_holdings h
                    LEFT JOIN unified_signal us ON us.ticker = h.ticker
                    WHERE h.fund = ? AND h.ticker IS NOT NULL
                    ORDER BY h.value_k DESC LIMIT 1""", (fund,)).fetchone()
                book = (sd.info.get(fund) or {}).get("period") or ""
                if top:
                    spec_out.append([fund, sg, top[0],
                                     round(top[1] or 0, 2),
                                     top[2] or 0,
                                     top[3] or "",
                                     top[4] or "", book])
                else:
                    spec_out.append([fund, sg, "—", 0, 0, "", "", book or "no 13F book"])
            write_table_rows(ws, spec_out, row)
            for ridx in range(row, row + len(spec_out)):
                ws.cell(row=ridx, column=4).number_format = NUMFMT_PCT
                ws.cell(row=ridx, column=6).number_format = NUMFMT_MCAP
            row += len(spec_out) + 2
    autosize(ws)
    ws.column_dimensions["A"].width = 30

# Grayscale tab palette — content stays B&W; tab tint just aids navigation.
# 15 macro_styles mapped to 8 distinct greyscale tones, grouped by character.
TAB_COLORS = {
    # Activists / Special Sits / Distressed — darkest (high-action)
    "Activists / Special Situations":      "262626",
    "Distressed / Event-Driven":           "404040",
    # Value / Quality — mid-dark
    "Value / Concentrated Quality":        "595959",
    "Concentrated Growth / Tech":          "595959",
    "Foreign / EM Value":                  "595959",
    "Small-cap / Multibagger Specialists": "595959",
    "Microcap-Tactical":                   "595959",
    # Tiger Cubs / Family Offices — mid
    "Tiger Cubs / L/S Legends":            "808080",
    "Family Offices / Individual Filers":  "808080",
    # Mega multi-strat / Macro — mid-light
    "Mega Multi-Strats / Quants":          "A6A6A6",
    "Macro / Trend":                       "A6A6A6",
    "CTA / Trend Followers":               "A6A6A6",
    # Specialist — light
    "Biotech Specialists":                 "BFBFBF",
    "Warrant Specialists":                 "BFBFBF",
    "PE / SPAC / Gold / Mining":           "BFBFBF",
    "Other / Unclassified":                "D9D9D9",
}

def sheet_fund_roster(wb, conn):
    """Definitive roster — EVERY fund with its macro_style + sub_group + data
    counts, grouped by style then sub-group. Guarantees no fund is missed. Says
    for each fund whether its 13F book is current, how concentrated it is, what
    its vote weighs, and what the resolver status means in plain English."""
    sd = style_data(conn)
    ws = wb.create_sheet("Fund Roster")
    write_title(ws, "Fund Roster — all funds by style & sub-group",
                f"Every fund with its style, sub-group and data coverage. Book = the quarter its latest 13F covers "
                f"(current = {sd.quarter}); Vote Wt = min(1, 75 / positions), how much its holdings count; Top-10 % "
                f"= how concentrated it is; N-PORT = registered-fund reports loaded. Name variants of one manager "
                f"share one book and count once (Note).", 14)
    row = 4
    macros = [r[0] for r in conn.execute(
        "SELECT DISTINCT macro_style FROM fund_style WHERE macro_style IS NOT NULL ORDER BY macro_style")]
    dormant = {f: (d or "")[:10] for f, d in conn.execute("SELECT fund, MAX(filed) FROM fund_13f_dormant GROUP BY fund")}
    nport = dict(conn.execute("SELECT manager, COUNT(DISTINCT series_id) FROM nport_holdings GROUP BY manager"))
    total_funds = 0
    for ms in macros:
        n_in_macro = conn.execute("SELECT COUNT(*) FROM fund_style WHERE macro_style=?", (ms,)).fetchone()[0]
        ws.row_dimensions[row].height = 22
        ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=14)
        c = ws.cell(row=row, column=1, value=f"{ms.upper()}  ({n_in_macro} funds)")
        c.font = Font(name=TNR, bold=True, size=SIZE_BODY + 1, color="000000")
        c.alignment = Alignment(horizontal="left", vertical="bottom")
        row += 1
        hdr = ["Fund", "Sub-Group", "Book", "Filed", "13F #", "13F $M", "Top-10 %", "Vote Wt", "13D #", "N-PORT",
               "Foreign Pos", "Total Pos", "Status", "Note"]
        write_table_header(ws, row, hdr)
        row += 1
        # all funds in this macro_style, ordered by sub_group then fund
        funds = list(conn.execute("""
            SELECT fm.fund, fs.sub_group,
                   COALESCE(st.n_holdings,0),
                   COALESCE(st.total_value_k,0)/1e3,
                   (SELECT COUNT(*) FROM holder_13d h WHERE h.holder=fm.fund),
                   (SELECT COUNT(*) FROM fund_positions fp WHERE fp.fund=fm.fund AND fp.ticker LIKE '%.%'),
                   (SELECT COUNT(*) FROM fund_positions fp WHERE fp.fund=fm.fund),
                   fr.status
            FROM fund_meta fm
            JOIN fund_style fs ON fs.fund=fm.fund
            LEFT JOIN fund_13f_state st ON st.fund=fm.fund
            LEFT JOIN fund_resolution_state fr ON fr.fund=fm.fund
            WHERE fs.macro_style=?
            ORDER BY fs.sub_group, fm.fund""", (ms,)))
        out = []
        for f in funds:
            fund = f[0]
            inf = sd.info.get(fund) or {}
            m = sd.cn(fund)
            if fund in dormant:
                book = f"dormant (last filed {dormant[fund]})"
            else:
                book = inf.get("period") or ""
            rep = sd.rep.get(m)
            note = (f"same manager as {rep}: its book is counted" if rep and rep != fund else "")
            out.append([fund, (f[1] or ""), book, inf.get("filed") or "", f[2], round(f[3] or 0),
                        round(inf["top10"]) if inf.get("top10") is not None else "",
                        round(inf["focus"], 2) if inf.get("focus") is not None else "",
                        f[4], nport.get(fund, 0) or "", f[5], f[6], plain_status(f[7]), note])
        write_table_rows(ws, out, row)
        _fmt(ws, row, len(out), {6: NUMFMT_M_TO_B, 7: '0"%"', 8: '0.00'})
        total_funds += len(out)
        row += len(out) + 2
    # footer tally
    ws.cell(row=row, column=1, value=f"TOTAL: {total_funds} funds across {len(macros)} macro-styles").font = SECTION_FONT
    ws.freeze_panes = "A4"
    autosize(ws)
    ws.column_dimensions["M"].width = 52
    ws.column_dimensions["N"].width = 44

def _one_liner(s, limit=None):
    """The full first sentence of the business summary — never cut, no
    ellipsis (shared rule: _style_bw.first_sentence)."""
    return first_sentence(s)

_DESC_CACHE = None
def desc_for(conn, ticker):
    """(industry, one-line business summary) for a ticker — memoized."""
    global _DESC_CACHE
    if _DESC_CACHE is None:
        _DESC_CACHE = {}
        for r in conn.execute("""
            SELECT us.ticker,
                   COALESCE(yf.industry, tm.industry, tm.sic_description),
                   yf.business_summary, yf.long_name, us.name
            FROM unified_signal us
            LEFT JOIN ticker_meta tm ON tm.ticker = us.ticker
            LEFT JOIN ticker_yf  yf ON yf.ticker = us.ticker"""):
            # the Name column says who; the Business cell starts at what it does
            _DESC_CACHE[r[0]] = ((r[1] or ""), business_line(r[2], r[3], r[4]))
    return _DESC_CACHE.get(ticker, ("", ""))

def sheet_ticker_reference(wb, conn):
    """Glossary: every ticker with name, sector, industry, and a short business
    summary — so any symbol in the style book can be looked up. Sorted A–Z."""
    ws = wb.create_sheet("Ticker Reference")
    write_title(ws, "Ticker Reference — name, industry, business",
                "Every symbol in the universe with its company name, sector, industry, market cap, and a one-line description of what it does. Sourced from FMP company profiles and SEC filings. Sorted A–Z.", 6)
    hdr = ["Ticker", "Name", "Sector", "Industry", "Mcap", "Business Summary"]
    write_table_header(ws, 4, hdr)
    rows = list(conn.execute("""
        SELECT us.ticker,
               COALESCE(tm.name, yf.long_name)                       AS name,
               COALESCE(yf.sector, tm.sector)                        AS sector,
               COALESCE(yf.industry, tm.industry, tm.sic_description) AS industry,
               us.mcap_m,
               yf.business_summary
        FROM unified_signal us
        LEFT JOIN ticker_meta tm ON tm.ticker = us.ticker
        LEFT JOIN ticker_yf  yf ON yf.ticker = us.ticker
        WHERE COALESCE(tm.name, yf.long_name, yf.business_summary, yf.sector,
                       tm.sic_description) IS NOT NULL
        ORDER BY us.ticker"""))
    out = []
    for r in rows:
        if r[0] in ETFs: continue
        out.append([r[0], (r[1] or ""), (r[2] or ""),
                    (r[3] or ""), r[4] or "", _one_liner(r[5])])
    write_table_rows(ws, out, 5)
    for ridx in range(5, 5 + len(out)):
        ws.cell(row=ridx, column=5).number_format = NUMFMT_MCAP
    ws.freeze_panes = "B5"
    autosize(ws)
    ws.column_dimensions["A"].width = 9
    ws.column_dimensions["B"].width = 34
    ws.column_dimensions["C"].width = 20
    ws.column_dimensions["D"].width = 28
    ws.column_dimensions["E"].width = 12
    ws.column_dimensions["F"].width = 100

def main():
    conn = sqlite3.connect(DB)
    wb = openpyxl.Workbook()
    if "Sheet" in wb.sheetnames:
        wb.remove(wb["Sheet"])

    sheet_readme(wb, conn)
    write_legend_sheet(wb, 1)
    sheet_fund_roster(wb, conn)
    sheet_overview(wb, conn)
    sheet_subgroup_focus(wb, conn)
    for ms, _ in style_macro_list(conn):
        sn = safe_sheet_name(ms)
        write_style_sheet(wb, conn, ms, sn)
        ws = wb[sn]
        # Tab color — grayscale per macro_style
        if ms in TAB_COLORS:
            ws.sheet_properties.tabColor = TAB_COLORS[ms]

    sheet_ticker_reference(wb, conn)

    # AutoFilter on the single-table Ticker Reference (header at row 4)
    if "Ticker Reference" in wb.sheetnames:
        ws = wb["Ticker Reference"]
        if ws.max_row > 4:
            ws.auto_filter.ref = f"A4:{get_column_letter(ws.max_column)}{ws.max_row}"

    # README + meta tabs in lightest grey for distinction
    for nav in ("README", "Legend", "Fund Roster", "Overview", "Sub-Group Tiers", "Ticker Reference"):
        if nav in wb.sheetnames:
            wb[nav].sheet_properties.tabColor = "F2F2F2"

    add_contents_index(wb["README"], wb.sheetnames)
    set_print_layout(wb)

    # every ticker table carries EV/EBITDA, P/E, P/B and P/TB side by side
    add_valuation_columns(wb, valuation_lookup(conn))
    wb.save(OUT)
    print(f"wrote {OUT}")
    print(f"sheets: {wb.sheetnames}")

if __name__ == "__main__":
    main()
