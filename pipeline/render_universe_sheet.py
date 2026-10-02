"""Render the universe analysis workbook — monochrome academic aesthetic.

A companion to style_analysis.xlsx. This file ranks the FULL 5,862-ticker
universe (no style cut) with the unified_signal score, sorted into sheets
by size bucket and signal type.

Design language is shared with render_style_workbook.py via _style_bw.py.
"""
import os, re, sqlite3
import openpyxl
from openpyxl.utils import get_column_letter

import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _style_bw import (
    business_line,
    complete_text,
    first_sentence,
    add_valuation_columns, valuation_lookup,
    write_title, write_section_heading, write_table_header, write_table_rows,
    autosize, write_legend_sheet, add_contents_index, add_grouped_contents, plain_status, set_print_layout,
    NUMFMT_USD, NUMFMT_PCT, NUMFMT_NUM, NUMFMT_INT, NUMFMT_USD2,
    NUMFMT_MCAP, NUMFMT_M_TO_B,
    TNR, SIZE_BODY, BODY_FONT, BODY_ITALIC, SECTION_FONT, TICKER_FONT, MONO_FONT,
    BLACK, ROW_BORDER, LAPIS, CRIMSON, color_directional, color_fixed,
)
from openpyxl.styles import Font, Alignment, Border, Side
from nport_diff import nport_diff as _nport_diff

DB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "cyclepapa.db")
OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "universe_analysis.xlsx")

ETFs = {"SPY","QQQ","VOO","IWM","IEF","IEFA","EFA","EEM","BIL","IVV","XBI","HYG",
        "GLD","SLV","TLT","XLE","XLF","XLK","XLY","XLP","XLU","XLI","XLV","XLB","XLRE",
        "ARKK","JNK","LQD","TIP","AGG","BND","VEA","VWO","SHY","TIPS"}
MEGA = {"AMZN","MSFT","NVDA","META","GOOGL","GOOG","AAPL","TSLA","BRK-A","BRK-B"}

BIOTECH_PATTERNS = ("pharmaceutic","biological","therapeutic")
def is_biotech(desc):
    if not desc: return False
    d = desc.lower()
    return any(p in d for p in BIOTECH_PATTERNS)

SIG_HDR = ["Ticker","Score","Why","Mcap","ADV $M","Bucket","13F Wt","S1","S3","S4","Act %",
           "pB Max","pB ≥5%","13D","Clu $M",
           "F4 Buy 180d","F4 Buy ≤30d","F4 Sell 180d","F4 Sell ≤30d",
           "EV/EBITDA","P/B",
           "Entry","vs Entry %","3mo %","Off Hi %","Anchor $",
           "Name","Sector","Px","Industry","Business"]

# components string -> readable "why" (top-3 contributing terms). Turns an opaque
# 90+ score into its drivers, e.g. "s1 24 · pb5 18 · s4 14".
_WHY_LABEL = {"sm": "sm", "s3*": "s3", "s4*": "s4", "s1*": "s1", "act": "act",
              "pb_max": "pb", "pb_n5": "pb5", "clust": "clu", "clust$": "clu$",
              "f4buy": "f4buy", "f4rec+": "f4rec", "f4sell": "f4sell",
              "f4recsell": "f4sell30", "mic": "micro", "er": "er", "entry": "entry",
              "cat8k": "8k", "evt": "event"}
def _why(components):
    if not components:
        return ""
    terms = []
    for tok in components.split():
        if "=" not in tok:
            continue
        k, v = tok.split("=", 1)
        try:
            val = float(v)
        except ValueError:
            continue
        if abs(val) >= 1 and k in _WHY_LABEL:
            terms.append((_WHY_LABEL[k], val))
    terms.sort(key=lambda t: -abs(t[1]))
    return " · ".join(f"{lbl} {val:.0f}" for lbl, val in terms[:3])

def get_signal_rows(conn, where_extra="", limit=None, params=()):
    sql = """SELECT us.ticker, us.score, us.mcap_m, us.mcap_bucket, us.smart_money_n,
        us.s1_top, us.s3_new, us.s4_add, us.activist_max_pct, us.max_pct_book,
        us.n_funds_5pct_book, us.activist_filings,
        us.insider_cluster_dollars_m,
        us.form4_buy_usd_m, us.form4_buy_30d_m, us.form4_sell_usd_m, us.form4_sell_30d_m,
        us.ev_ebitda, us.pb_ratio,
        us.entry_bucket, us.vs_entry_pct, us.anchor_px,
        us.expected_return_pct, tm.name, tm.sic_description, COALESCE(NULLIF(yf.price, 0), tm.price),
        COALESCE(yf.industry, tm.industry, tm.sic_description), yf.business_summary,
        tm.adv_3m_usd_m, us.components, ps.mom_3mo, ps.off_high
        FROM unified_signal us
        LEFT JOIN ticker_meta tm ON tm.ticker = us.ticker
        LEFT JOIN ticker_yf  yf ON yf.ticker = us.ticker
        LEFT JOIN price_stats ps ON ps.ticker = us.ticker
        WHERE us.sec_type='common' """ + where_extra + " ORDER BY us.score DESC"
    if limit: sql += f" LIMIT {limit}"
    return list(conn.execute(sql, params))

def signal_row_to_cells(r):
    """Map a raw signal row to display values.
    Row order: ticker,score,mcap,bucket,13F,s1,s3,s4,act,pbmax,pb5,13d,clu,
               f4_180,f4_30,f4sell_180,f4sell_30,ev_ebitda,pb,entry,vsentry,anchor,
               er,name,sector,price
    """
    eb = r[19] or ""
    if eb == "BELOW_ENTRY":         eb_label = "below"
    elif eb == "NEAR_ENTRY":        eb_label = "near"
    elif eb == "MODERATELY_ABOVE":  eb_label = "mod above"
    elif eb == "WELL_ABOVE":        eb_label = "well above"
    else:                           eb_label = ""
    return [
        r[0], round(r[1] or 0, 1),
        _why(r[29]),                             # Why (top-3 score drivers)
        r[2] or "",                              # Mcap
        round(r[28], 1) if r[28] else "",        # ADV $M (adv_3m_usd_m)
        r[3] or "",                              # Bucket
        round(r[4] or 0, 1), r[5] or 0, r[6] or 0, r[7] or 0,
        round(r[8] or 0, 1),
        round(r[9] or 0, 1),
        r[10] or 0,
        r[11] or 0,
        round(r[12] or 0, 1) if r[12] else "",
        round(r[13] or 0, 1) if r[13] else "",   # F4 buy 180d
        round(r[14] or 0, 1) if r[14] else "",   # F4 buy ≤30d
        round(r[15] or 0, 1) if r[15] else "",   # F4 sell 180d
        round(r[16] or 0, 1) if r[16] else "",   # F4 sell ≤30d
        round(r[17], 1) if r[17] is not None else "",   # EV/EBITDA
        round(r[18], 2) if r[18] is not None else "",   # P/B
        eb_label,
        round(r[20] or 0, 1) if r[20] else "",   # vs entry
        round(r[30], 0) if r[30] is not None else "",   # 3mo % momentum (price_stats)
        round(r[31], 0) if r[31] is not None else "",   # off 3mo high (drawdown)
        round(r[21] or 0, 2) if r[21] else "",   # anchor px
        (r[23] or ""),                      # Name
        (r[24] or ""),                      # Sector
        round(r[25] or 0, 2) if r[25] else "",   # Px
        (r[26] or ""),            # Industry
        _one_liner(r[27], 90),         # Business (one-line summary)
    ]

def format_signal_row(ws, ridx):
    """Apply number formats to a signal row. Columns (1-idx):
    1 Ticker 2 Score 3 Why 4 Mcap 5 ADV$M 6 Bucket 7 13F 8 S1 9 S3 10 S4 11 Act%
    12 pBMax 13 pB≥5% 14 13D 15 Clu$M 16 F4B180 17 F4B30 18 F4S180 19 F4S30
    20 EV/EBITDA 21 P/B 22 Entry 23 vsEntry% 24 Anchor$ 25 Name 26 Sector 27 Px"""
    ws.cell(row=ridx, column=2).number_format = '0.0'          # Score (align decimals)
    ws.cell(row=ridx, column=7).number_format = '0.0'          # 13F Wt (decimal = weighted)
    ws.cell(row=ridx, column=4).number_format = NUMFMT_MCAP    # mcap
    ws.cell(row=ridx, column=5).number_format = NUMFMT_M_TO_B  # ADV $M
    ws.cell(row=ridx, column=11).number_format = NUMFMT_PCT    # act
    ws.cell(row=ridx, column=12).number_format = NUMFMT_PCT    # pB max
    ws.cell(row=ridx, column=15).number_format = NUMFMT_M_TO_B # Clu $M
    ws.cell(row=ridx, column=16).number_format = NUMFMT_M_TO_B # F4 buy 180d
    ws.cell(row=ridx, column=17).number_format = NUMFMT_M_TO_B # F4 buy 30d
    ws.cell(row=ridx, column=18).number_format = NUMFMT_M_TO_B # F4 sell 180d
    ws.cell(row=ridx, column=19).number_format = NUMFMT_M_TO_B # F4 sell 30d
    ws.cell(row=ridx, column=20).number_format = '0.0"x"'      # EV/EBITDA
    ws.cell(row=ridx, column=21).number_format = '0.00"x"'     # P/B
    ws.cell(row=ridx, column=23).number_format = NUMFMT_PCT    # vs entry
    ws.cell(row=ridx, column=24).number_format = NUMFMT_PCT    # 3mo %
    ws.cell(row=ridx, column=25).number_format = NUMFMT_PCT    # off hi %
    ws.cell(row=ridx, column=26).number_format = NUMFMT_USD2   # anchor px
    ws.cell(row=ridx, column=29).number_format = NUMFMT_USD2   # px

def add_signal_heatmap(ws, first_row, last_row):
    """Times-Lattice 'colour is data': faint lapis (good) / crimson (bad) washes on
    the decision columns — a dark ink reduced to a whisper, never a bright pastel.
    Score higher = deeper lapis; valuation cheaper = deeper lapis; vs-entry diverges
    lapis(below, opportunity)↔crimson(well above)."""
    from openpyxl.formatting.rule import ColorScaleRule, DataBarRule
    if last_row < first_row:
        return
    rng = lambda col: f"{col}{first_row}:{col}{last_row}"
    WHITE = "FFFFFF"
    LAPIS_WASH, CRIMSON_WASH = "DDE2EA", "EDDCE0"   # the two inks at ~7% strength
    # Score (col B): higher = deeper lapis (more attractive)
    ws.conditional_formatting.add(rng("B"),
        ColorScaleRule(start_type="min", start_color=WHITE, end_type="max", end_color=LAPIS_WASH))
    ws.conditional_formatting.add(rng("B"), DataBarRule(start_type="min", end_type="max", color="C7CEDA"))
    # EV/EBITDA (T) and P/B (U): cheaper (lower) = deeper lapis
    for col in ("T", "U"):
        ws.conditional_formatting.add(rng(col),
            ColorScaleRule(start_type="min", start_color=LAPIS_WASH, end_type="max", end_color=WHITE))
    # vs Entry % (W): below entry (negative) lapis opportunity ↔ well above crimson
    ws.conditional_formatting.add(rng("W"),
        ColorScaleRule(start_type="min", start_color=LAPIS_WASH, mid_type="num", mid_value=0, mid_color=WHITE,
                       end_type="max", end_color=CRIMSON_WASH))

# ---- sheets -----------------------------------------------------------------
# The README's reading guide: every sheet under the question it answers.
SHEET_GUIDE = [
    ("Start here", [
        ("What Changed", "new since the last build: filings, insider trades, 8-Ks, fresh 13Fs, top-100 moves"),
        ("Action Dashboard", "the strongest setups right now, several independent signals at once, one line each"),
        ("Best Ideas", "multi-signal shortlist under $10B (cheap, below entry, insiders, activist, catalyst), with reasons"),
        ("Convergence", "every name firing 3+ independent signal types; the dots show which"),
        ("Ticker Dossier", "one block per top name: holders, insiders, activists, 8-Ks, valuation — vet an idea here"),
    ]),
    ("What the funds did last quarter", [
        ("Revealed Preference", "buying now on dated evidence: 13F net buying, insider buys, new 13D/Gs, N-PORT, capital structure"),
        ("Who's Buying", "for each name, the funds that opened or added to it, with the size of each move"),
        ("QoQ Change", "breadth: how many funds added vs trimmed each name (share counts, every size of move)"),
        ("Material + New", "the score table for names two or more funds opened or added (focus-weighted)"),
        ("Manager Track Records", "how each fund's new buys did after its 13F made them public, vs the S&P 500"),
    ]),
    ("Ranked by the score", [
        ("Top 100", "the highest scores (ETFs and the ten largest US mega-caps left out)"),
        ("Non-Biotech Top 100", "the same without biotech"),
        ("Nano (<$50M)", "top 60 nano-caps"), ("Micro ($50M–$300M)", "top 60 micro-caps"),
        ("Small ($300M–$2B)", "top 60 small-caps"), ("Mid ($2B–$10B)", "top 60 mid-caps"),
        ("Large ($10B–$200B)", "top 60 large-caps"), ("Mega (>$200B)", "every mega-cap, the ten giants included"),
        ("Best in Bucket", "the top 20 of each size class on one sheet"),
    ]),
    ("By industry (FMP's industry designations)", [
        ("Industry Index", "every industry the funds hold, ranked by last quarter's net buying, with medians"),
        ("Industry Detail", "each industry's names: who holds them, who bought and who sold, how they're valued"),
    ]),
    ("Value and setup", [
        ("Valuation", "cheap AND sound: free-cash-flow yield, ROIC, leverage, growth; value traps flagged"),
        ("In The Money", "trading below the funds' estimated entry price"),
        ("Asymmetry", "margin of safety times upside"),
        ("Catalysts 8-K", "M&A, change of control, director changes, dilution, bankruptcy in the last 180 days"),
        ("Special Situations", "proxy fights, spin-offs coming (Form 10), tender and going-private offers"),
        ("Short Interest", "crowded shorts the funds own, bears building, bears leaving (FINRA)"),
    ]),
    ("Insiders and politicians", [
        ("Insider Buys ≤30d", "open-market insider buying in the last 30 days, C-suite first, with the buyers named"),
        ("Insider F4 Buys", "180 days of insider buying, recency-weighted, individuals and entities split"),
        ("Insider Clusters", "several insiders buying the same stock within a window"),
        ("Congress Trades", "members of Congress buying and selling (STOCK Act)"),
    ]),
    ("Activists and hidden stakes", [
        ("Activist 10+", "13D/G stakes of 10% or more"),
        ("Latent Ownership", "warrants, converts, ownership blockers and swaps inside 13D text"),
        ("Broker Swap Radar", "swap-desk share jumps that can show a stake before any 13D"),
    ]),
    ("Outside the US (N-PORT registered funds)", [
        ("Global Picks", "non-US listings ranked on the managers' holdings and last quarter's buying"),
        ("N-PORT Funds", "which registered funds are loaded, as of when, how international"),
        ("N-PORT Holdings", "each fund's complete book, local listings included"),
        ("N-PORT Changes", "what the managers' funds bought and sold since their previous report"),
        ("N-PORT Global Consensus", "non-US stocks by how many managers hold them"),
    ]),
    ("Special and archive", [
        ("Bill Miller", "Miller Value Partners and Patient Capital side by side"),
        ("Adversarial Review", "a June 2026 red-team of the then-top picks — archived; scores and data have moved since"),
    ]),
    ("Reference", [
        ("Legend", "every column and code defined"),
        ("All Positions", "every disclosed position: 13F, research notes and 13D/G"),
        ("Fund Coverage", "which funds have which data, and why some have none"),
        ("All Funds", "every roster fund: its data status, CIK and book"),
        ("Ticker Reference", "every symbol: name, industry, what it does"),
        ("Unknown Mcap", "names whose market cap could not be resolved"),
    ]),
]

def sheet_readme(wb, conn):
    ws = wb.create_sheet("README", 0)
    ws.sheet_view.showGridLines = False
    n_tk = conn.execute("SELECT COUNT(*) FROM unified_signal").fetchone()[0]
    n_fd = conn.execute("SELECT COUNT(DISTINCT fund) FROM fund_meta").fetchone()[0]
    n_hold = conn.execute("SELECT COUNT(*) FROM fund_13f_holdings").fetchone()[0]
    n_13f_funds = conn.execute("SELECT COUNT(DISTINCT fund) FROM fund_13f_holdings").fetchone()[0]
    write_title(ws,
        "Fund Positioning",
        f"How {n_fd} tracked funds are positioned: {n_tk:,} tickers from primary EDGAR filings.",
        1)
    ws.column_dimensions["A"].width = 92

    # --- data-as-of dates (be honest about the 13F lag) ---
    def _maxdate(sql):
        r = conn.execute(sql).fetchone()
        return str(r[0])[:10] if r and r[0] else "—"
    f13_filed = _maxdate("SELECT MAX(filed) FROM fund_13f_holdings")
    # 13F holdings are as-of the quarter-end BEFORE the filing (statutory +45d lag)
    import datetime as _dt, calendar as _cal
    f13_asof = "—"
    try:
        fd = _dt.date.fromisoformat(f13_filed)
        qe_month = ((fd.month - 1) // 3) * 3          # 0,3,6,9 -> prior quarter-end month
        yr = fd.year if qe_month else fd.year - 1
        qe_month = qe_month or 12
        f13_asof = f"{yr}-{qe_month:02d}-{_cal.monthrange(yr, qe_month)[1]}"
    except Exception:
        pass
    f4_date = _maxdate("SELECT MAX(trans_date) FROM form4_transactions")
    d13_date = _maxdate("SELECT MAX(filed) FROM holder_13d")
    c8_date = _maxdate("SELECT MAX(filed) FROM catalysts_8k")
    yf_date = _maxdate("SELECT MAX(asof) FROM ticker_yf")
    n_fp = conn.execute("SELECT COUNT(*) FROM fund_positions").fetchone()[0]
    try:
        n_np, n_np_f, n_np_m, np_fgn = conn.execute("""SELECT COUNT(*), COUNT(DISTINCT series_id),
            COUNT(DISTINCT manager), 100.0 * SUM(CASE WHEN country != 'US' THEN val_usd ELSE 0 END) / SUM(val_usd)
            FROM nport_holdings""").fetchone()
    except sqlite3.OperationalError:
        n_np = 0
    # books kept OUT of every holder count, named in full so nothing drops silently
    try:
        dormant = [r[0] for r in conn.execute("""SELECT DISTINCT d.fund FROM fund_13f_dormant d
            JOIN fund_13f_state s ON s.fund = d.fund ORDER BY s.last_filed DESC""")]
    except sqlite3.OperationalError:
        dormant = []
    empty = [f"{r[0]} ({r[1]})" for r in conn.execute("""SELECT fund, substr(last_filed, 1, 7) FROM fund_13f_state
        WHERE n_holdings = 0 AND last_accession IS NOT NULL ORDER BY fund""")]

    def _wrapped(label, names, width=88):
        out, line = [], label
        for i, nm in enumerate(names):
            piece = nm + (", " if i < len(names) - 1 else "")
            if len(line) + len(piece) > width and line.strip():
                out.append((line.rstrip(),))
                line = " " * 22
            line += piece
        out.append((line.rstrip(),))
        return out

    # fund coverage in one line that reconciles with the Fund Coverage sheet
    from fund_moves import latest_due_quarter, book_info
    from _canon import canon as _cn
    _q = latest_due_quarter()
    _bi = book_info(conn)
    _live = {f for f, d in _bi.items() if d["n"]}
    _cur = {f for f in _live if _bi[f]["period"] == _q}
    _mgr_live = {_cn(f) for f in _live}
    # a dormant book whose manager files on under another name is not a gap
    dormant_named = [f"{d} (live under another name)" if _cn(d) in _mgr_live else d for d in dormant]
    rows = [
        ("",),
        ("START HERE",),
        ("0. What Changed — new since the last build: filings, top-100 entries and exits, score moves. Seen the books",),
        ("   before? Start there.",),
        ("1. Action Dashboard — the strongest setups right now, several independent signals at once, one line each.",),
        ("2. Revealed Preference — what the funds and insiders are buying now, on dated evidence (last 13F quarter,",),
        ("   insider buys and new 13D/Gs in 90 days, N-PORT reports), with who bought and who sold.",),
        ("3. Valuation — which of the names they hold are cheap AND sound (cash flow, returns, leverage, growth).",),
        ("4. Ticker Dossier — every signal on one name in one block: vet an idea there before acting.",),
        ("The Contents at the bottom groups every sheet by the question it answers.",),
        ("",),
        ("DATA AS-OF (read before trusting any number)",),
        (f"13F holdings   quarter ended {f13_asof}  (latest filing {f13_filed}; SEC allows +45d, so fund holdings",),
        ("    reflect quarter-END positions and can be up to ~3-4 months old — a fund may have since exited).",),
        (f"Form 4 insider {f4_date}     ·   13D/G activist {d13_date}     ·   8-K catalysts {c8_date}   (near-current)",),
        (f"Prices & valuations {yf_date}  (FMP company profiles, ratios and end-of-day prices)",),
        ("    → The 13F-derived columns (13F, S1 / S3 / S4, %book) are the LAGGED layer; the Form 4 /",),
        ("      13D / 8-K / valuation columns are current. Don't read a 13F consensus as a live position.",),
        ("",),
        ("Universe",),
        (f"{n_tk:,} tickers — every security in a tracked fund's 13F, research notes or 13D/G, plus the local",),
        ("listings in the N-PORT books. ETFs, preferreds, warrants, units and notes are typed and kept out of pick tables.",),
        (f"{n_fd} funds on the roster: {len(_live)} with a live 13F book ({len(_cur)} of them for the {_q} quarter),",),
        (f"{len(dormant)} dormant (archived), {len(empty)} with an empty latest report; the rest file no 13F (non-US",),
        ("managers, under the $100M threshold, individuals) and count through research notes, 13D/Gs and N-PORT.",),
        ("Name variants of one manager ('Pershing Square Capital Managem', '... Management') count once. See Fund Coverage.",),
        ("",),
        ("Score formula (the 'Score' column; pipeline/unified_score.py)",),
        ("score = 2 × ln(1 + 13F)                13F = CONVICTION-WEIGHTED count of 13F holders",),
        ("    The '13F' column is NOT a raw holder count. Each fund's vote is weighted",),
        ("    min(1, 75 / n_positions): a focused book (<=75 names) counts fully, while",),
        ("    pod-shops / quants are heavily downweighted — Citadel (6,687 names) ×0.011,",),
        ("    Millennium ×0.019, AQR ×0.020 — so statistical-arb breadth can't fake consensus.",),
        ("      + 3.0 × S3 (cap 8)              new positions: the latest 13F quarter where a fund has a current",),
        ("      + 1.5 × S4 (cap 10)             book (focus-weighted), research notes otherwise; S4 = adds of 25%+",),
        ("      + 2.0 × S1 (cap 12)             top picks (research notes), only while the fund still holds the stock",),
        ("      + 0.5 × activist stake % (cap 30)        largest 13D/G stake, filed in the last 24 months",),
        ("      + 0.6 × largest % of a book (cap 25)     halved for a lone 50%+ sponsor stake",),
        ("      + 1.5 × funds with 5%+ of book (cap 12)  concentration cluster",),
        ("      + 5 / 10 / 15 for a live insider buy cluster of 1 / 3 / 5+ insiders, + 3 × ln(1 + cluster $M)",),
        ("      + 2 × ln(1 + insider buys $M, recency-weighted) + 2 × ln(1 + buys in the last 30 days $M)",),
        ("      − 1.5 × ln(1 + insider sells $M) − 1.5 × ln(1 + sells in the last 30 days $M)",),
        ("      + small-cap bonus (+5 under $300M, +3 under $2B)",),
        ("      + entry setup: +2.5 to +5 at 15-30% below the funds' estimated entry, tapering to 0 at 50% below",),
        ("        and -3 beyond (a busted thesis); +1.5 within 15% of it; -3 when 40%+ above it",),
        ("      + 8-K catalysts (M&A +5, change of control +4, director change +1, PIPE -3, bankruptcy -10)",),
        ("      + SEC events, 180 days (proxy contest +4, tender / going-private offer +5, spin-off coming +2)",),
        ("",),
        ("Data sources",),
        (f"fund_13f_holdings     {n_hold:,} rows from SEC 13F-HR XML across {n_13f_funds} funds",),
        *(_wrapped(f"Dormant, archived     {len(dormant)} funds with no 13F-HR in 200+ days, kept out of every count: ",
                   dormant_named) if dormant else []),
        *(_wrapped(f"Empty latest report   {len(empty)} funds filed a $0 holdings table (held no 13F securities): ",
                   empty) if empty else []),
        (f"fund_positions        {n_fp:,} research-team notes (compiled May–June 2026); superseded by the latest",),
        ("                      13F wherever a fund has a current book",),
        *([(f"nport_holdings        {n_np:,} equity positions from N-PORT: the full books of {n_np_f} registered funds",),
           (f"                      of {n_np_m} managers, {np_fgn:.0f}% of it outside the US and invisible in 13F",),
           ("                      sheets: N-PORT Funds -> Holdings -> Changes -> Global Consensus",)] if n_np else []),
        ("holder_13d            SC 13D/G filings via efts.sec.gov full-text search",),
        ("form4_transactions    open-market buys (P) and sells (S): the SEC Form 4 scan plus FMP's insider feed",),
        ("insider_fmp           every Form 4 code for ~100 days (awards, exercises, conversions): capital-structure tells",),
        ("insider_clusters      live ≤180d clusters",),
        ("catalysts_8k          8-K filings with parsed Item codes",),
        ("ticker_yf             FMP profiles, ratios, key metrics, growth and cash flow (market caps in USD)",),
        ("",),
        ("Filters",),
        ("ex-ETF — ETFs and funds removed from pick tables.",),
        ("ex-Mega — the ten largest US mega-caps (AAPL, MSFT, NVDA, AMZN, GOOGL, GOOG, META, TSLA, BRK-A, BRK-B)",),
        ("   are left out of the ranked lists where noted, so they don't crowd everything else; the Mega sheet has them.",),
        ("ex-Biotech — SIC matching pharmaceutic / biological / therapeutic excluded where noted.",),
        ("",),
        ("Methodology note",),
        ("Every number is aggregated from filings and market data. No curated ticker lists, no editorial picks, no memory.",),
        ("The score is shared by the universe and style workbooks. Re-rank by editing pipeline/unified_score.py.",),
    ]
    for i, r in enumerate(rows, 4):
        c = ws.cell(row=i, column=1, value=r[0])
        ws.row_dimensions[i].height = 18
        if not r[0].strip(): continue
        if r[0][:6] not in ("score ", "      "):
            # section heading test: short capitalized phrases
            if r[0] in ("Universe", "Data sources", "Filters", "Methodology note", "START HERE",
                        "DATA AS-OF (read before trusting any number)") or r[0].startswith("Score formula"):
                c.font = SECTION_FONT
            else:
                c.font = BODY_FONT
        else:
            c.font = MONO_FONT

def _baseline(table, base):
    """A table as the last delivered build left it: its CSV in the snapshot
    committed at `base` (default HEAD). None when there is no such build."""
    import csv, io, subprocess
    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    try:
        out = subprocess.run(["git", "-C", repo, "show", f"{base}:data/snapshot/{table}.csv"],
                             capture_output=True, text=True, timeout=180)
    except Exception:
        return None
    if out.returncode != 0 or not out.stdout:
        return None
    csv.field_size_limit(10 ** 8)
    return list(csv.DictReader(io.StringIO(out.stdout)))

def sheet_what_changed(wb, conn):
    """What is new since the last delivered build: filings (13D/G, insider
    buys and large sells, M&A / control 8-Ks, 13F books), names entering or
    leaving the top 100, the biggest score moves and new Revealed Preference
    names. The baseline is the snapshot committed with that build
    (data/snapshot, git HEAD; CHANGES_SINCE=<commit> picks another)."""
    import subprocess
    base = os.environ.get("CHANGES_SINCE", "HEAD")
    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    try:
        when = subprocess.run(["git", "-C", repo, "log", "-1", "--format=%cd", "--date=format:%Y-%m-%d %H:%M UTC", base],
                              capture_output=True, text=True, timeout=30).stdout.strip()
    except Exception:
        when = ""
    ws = wb.create_sheet("What Changed", 1)
    ws.sheet_view.showGridLines = False
    us_prev = _baseline("unified_signal", base)
    if us_prev is None:
        write_title(ws, "What Changed", "No earlier build on file to compare with.", 8)
        return
    write_title(ws, f"What Changed — since the last build ({when or base})",
                "New filings since then (13D/G stakes, insider open-market buys and large sells, M&A and change-of-"
                "control 8-Ks, fresh 13F books), names entering or leaving the Top 100, the largest score moves and "
                "new Revealed Preference names. Read this first when you have seen the books before.", 8)
    row = 4
    ETF_MEGA = ETFs | MEGA

    def section(title, hdr, out, width=8, fmts=None, note=None):
        nonlocal row
        write_section_heading(ws, row, f"{title} — {len(out)}" if out else f"{title} — none", width)
        row += 1
        if note:
            ws.cell(row=row, column=1, value=note).font = BODY_ITALIC
            row += 1
        if not out:
            row += 1
            return
        write_table_header(ws, row, hdr)
        row += 1
        write_table_rows(ws, out, row)
        for col, f in (fmts or {}).items():
            for r_ in range(row, row + len(out)):
                ws.cell(row=r_, column=col).number_format = f
        row += len(out) + 2

    name = {r[0]: r[1] for r in conn.execute("""SELECT us.ticker, COALESCE(y.long_name, us.name)
        FROM unified_signal us LEFT JOIN ticker_yf y ON y.ticker = us.ticker""")}
    # 1. 13D/G stakes
    prev = {r.get("accession") for r in (_baseline("holder_13d", base) or [])}
    import datetime as _dt
    recent_cut = (_dt.date.today() - _dt.timedelta(days=30)).isoformat()
    out, late = [], []
    for holder, form, filed, acc, subj, tk, pct in conn.execute("""SELECT holder, form, filed, accession, subject_name,
            subject_ticker, pct_class FROM holder_13d WHERE subject_ticker IS NOT NULL ORDER BY filed DESC"""):
        if acc and acc not in prev:
            r_ = [tk, holder or "", form or "", round(pct, 1) if pct else "", str(filed)[:10], name.get(tk) or subj or ""]
            (out if str(filed)[:10] >= recent_cut else late).append(r_)
    section("New 13D/G stakes (filed in the last 30 days)", ["Ticker", "Holder", "Form", "% of Class", "Filed", "Name"],
            out, 6, {4: NUMFMT_PCT})
    section("Older 13D/G filings captured for the first time by this build", ["Ticker", "Holder", "Form",
            "% of Class", "Filed", "Name"], late, 6, {4: NUMFMT_PCT},
            note="Filed earlier but missing from the last build (the SEC search refreshes a 21-month window).")
    # 2. insider open-market buys ($25k+) and sells ($1M+)
    key = lambda a, o, d, sh, cd: (a or "", (o or "").upper(), str(d)[:10], round(float(sh or 0)), cd or "")
    prev = {key(r.get("accession"), r.get("owner"), r.get("trans_date"), r.get("shares") or 0, r.get("code"))
            for r in (_baseline("form4_transactions", base) or [])}
    agg = {}
    for acc, tk, owner, role, d, code, sh, px in conn.execute("""SELECT accession, ticker, owner, role, trans_date, code,
            shares, price FROM form4_transactions WHERE code IN ('P', 'S') AND price > 0 AND price < 200000
              AND trans_date >= date('now', '-60 days')"""):
        if key(acc, owner, d, sh, code) in prev:
            continue
        k = (tk, owner, code)
        a = agg.setdefault(k, {"usd": 0.0, "last": "", "role": role or ""})
        a["usd"] += (sh or 0) * (px or 0)
        a["last"] = max(a["last"], str(d)[:10])
    buys = sorted(((v["usd"], k, v) for k, v in agg.items() if k[2] == "P" and v["usd"] >= 25000), reverse=True)
    sells = sorted(((v["usd"], k, v) for k, v in agg.items() if k[2] == "S" and v["usd"] >= 1e6), reverse=True)
    section("New insider open-market buys ($25k+)", ["Ticker", "Insider", "Role", "Type", "$M", "Last Trade", "Name"],
            [[k[0], k[1] or "", v["role"], "entity" if is_entity(k[1]) else "person", round(u / 1e6, 2), v["last"],
              name.get(k[0]) or ""] for u, k, v in buys[:150]], 7, {5: NUMFMT_M_TO_B},
            note="Type: person = an individual's own money; entity = a company, fund or holding vehicle.")
    section("New insider sales ($1M+)", ["Ticker", "Insider", "Role", "$M", "Last Trade", "Name"],
            [[k[0], k[1] or "", v["role"], round(u / 1e6, 2), v["last"], name.get(k[0]) or ""] for u, k, v in sells[:80]],
            6, {4: NUMFMT_M_TO_B})
    # 3. 8-K catalysts
    prev = {r.get("accession") for r in (_baseline("catalysts_8k", base) or [])}
    out = []
    for tk, filed, acc, labels, ma, ctrl, pipe, bnk in conn.execute("""SELECT ticker, filed, accession, item_labels,
            has_ma, has_control, has_pipe, has_bankruptcy FROM catalysts_8k
            WHERE has_ma = 1 OR has_control = 1 OR has_pipe = 1 OR has_bankruptcy = 1 ORDER BY filed DESC"""):
        if acc and acc not in prev:
            kind = ", ".join(k for k, f in (("M&A", ma), ("change of control", ctrl), ("PIPE / dilution", pipe),
                                            ("bankruptcy", bnk)) if f)
            out.append([tk, str(filed)[:10], kind, labels or "", name.get(tk) or ""])
    section("New 8-K catalysts (M&A, control, dilution, bankruptcy)", ["Ticker", "Filed", "Kind", "Items", "Name"],
            out[:150], 5)
    # 4. fresh 13F books
    prev = {r.get("fund"): r.get("last_accession") for r in (_baseline("fund_13f_state", base) or [])}
    out = []
    for fund, acc, filed, n, v in conn.execute("""SELECT fund, last_accession, last_filed, n_holdings, total_value_k
            FROM fund_13f_state ORDER BY last_filed DESC"""):
        if acc and prev.get(fund) != acc:
            out.append([fund, str(filed)[:10], n or 0, round((v or 0) / 1e3)])
    section("New 13F books", ["Fund", "Filed", "Positions", "$M"], out, 4, {4: NUMFMT_M_TO_B})
    # proxy fights, spin-off registrations, tender / going-private offers
    prev_ev = _baseline("sec_events", base)
    try:
        evs = conn.execute("""SELECT kind, form, filed, accession, subject_ticker, subject_name, party_name, detail
            FROM sec_events WHERE kind IN ('proxy', 'spin', 'tender') ORDER BY filed DESC""").fetchall()
    except sqlite3.OperationalError:
        evs = []
    if prev_ev is None:                           # first build with this feed: the last week only
        cut = (_dt.date.today() - _dt.timedelta(days=7)).isoformat()
        evs = [e for e in evs if (e[2] or "") >= cut]
        note = "First build with this feed: filings of the last 7 days."
    else:
        seen_acc = {r.get("accession") for r in prev_ev}
        evs = [e for e in evs if e[3] not in seen_acc]
        note = None
    label = {"proxy": "proxy fight", "spin": "spin-off / Form 10", "tender": "tender / going private"}
    section("New special-situation filings", ["Ticker", "Kind", "Form", "Filed", "Other Party", "Company / Detail"],
            [[e[4] or "", label[e[0]], e[1], e[2], e[6] or "", (e[7] or e[5] or "")] for e in evs][:150], 6, note=note)
    # 5. the Top 100 and the score
    def top(rows_):
        pool = [(float(r["score"] or 0), r["ticker"]) for r in rows_
                if r.get("sec_type") == "common" and r.get("mcap_bucket") not in ("unknown", "", None)
                and r["ticker"] not in ETF_MEGA]
        return [t for sc, t in sorted(pool, reverse=True)[:100]]
    cur_rows = [dict(zip(("ticker", "score", "sec_type", "mcap_bucket", "s3_new", "s4_add", "smart_money_n",
                          "insider_cluster_dollars_m"), r)) for r in conn.execute("""SELECT ticker, score, sec_type,
            mcap_bucket, s3_new, s4_add, smart_money_n, insider_cluster_dollars_m FROM unified_signal""")]
    now_top, was_top = top(cur_rows), top(us_prev)
    was_rank = {t: i + 1 for i, t in enumerate(was_top)}
    now_rank = {t: i + 1 for i, t in enumerate(now_top)}
    prev_by = {r["ticker"]: r for r in us_prev}
    cur_by = {r["ticker"]: r for r in cur_rows}
    def f(x):
        try:
            return float(x or 0)
        except (TypeError, ValueError):
            return 0.0
    entered = [[t, now_rank[t], round(f(cur_by[t]["score"]), 1), round(f(cur_by[t]["score"]) - f((prev_by.get(t) or {}).get("score")), 1),
                name.get(t) or ""] for t in now_top if t not in was_rank]
    left = [[t, was_rank[t], round(f((cur_by.get(t) or {}).get("score")), 1),
             round(f((cur_by.get(t) or {}).get("score")) - f(prev_by[t]["score"]), 1), name.get(t) or ""]
            for t in was_top if t not in now_rank]
    section("Entered the Top 100", ["Ticker", "Rank Now", "Score", "Change", "Name"], entered, 5)
    section("Left the Top 100", ["Ticker", "Rank Before", "Score Now", "Change", "Name"], left, 5)
    moves = []
    for t, r in cur_by.items():
        p = prev_by.get(t)
        if not p or r.get("sec_type") != "common" or t in ETF_MEGA:
            continue
        dlt = f(r["score"]) - f(p.get("score"))
        if abs(dlt) >= 3:
            why = []
            for k, lab in (("s3_new", "S3"), ("s4_add", "S4"), ("smart_money_n", "13F"),
                           ("insider_cluster_dollars_m", "insider $M")):
                dv = f(r.get(k)) - f(p.get(k))
                if abs(dv) >= 0.5:
                    why.append(f"{lab} {dv:+.1f}")
            moves.append((dlt, t, round(f(r["score"]), 1), ", ".join(why)))
    moves.sort(key=lambda x: -abs(x[0]))
    section("Largest score moves (3+ points)", ["Ticker", "Change", "Score Now", "What Moved", "Name"],
            [[t, round(dl, 1), sc, why, name.get(t) or ""] for dl, t, sc, why in moves[:60]], 5, {2: '+0.0;-0.0'})
    # 6. Revealed Preference
    rp_prev = {r["ticker"]: f(r.get("rp_score")) for r in (_baseline("revealed_pref", base) or [])}
    rp_now = dict(conn.execute("SELECT ticker, rp_score FROM revealed_pref"))
    def top_rp(d):
        return [t for t, v in sorted(d.items(), key=lambda x: -x[1]) if t in cur_by
                and (cur_by[t].get("sec_type") == "common") and t not in ETFs][:50]
    was50 = set(top_rp(rp_prev))
    new50 = [[t, round(rp_now[t], 1), round(rp_now[t] - rp_prev.get(t, 0.0), 1), name.get(t) or ""]
             for t in top_rp(rp_now) if t not in was50]
    section("New to the Revealed Preference top 50", ["Ticker", "RP Score", "Change", "Name"], new50, 4)
    ws.freeze_panes = "A4"
    autosize(ws)
    ws.column_dimensions["A"].width = 30
    for col, w in (("B", 34), ("D", 40), ("F", 40)):
        ws.column_dimensions[col].width = w

def write_signal_sheet(wb, conn, name, where_extra="", limit=200, subtitle="", exclude_biotech=False,
                       include_mega=False):
    ws = wb.create_sheet(name)
    ws.sheet_view.showGridLines = False
    write_table_header(ws, 4, SIG_HDR)
    # Fetch a generous superset, then apply the ETF/mega/biotech exclusions in
    # Python and truncate to `limit` — so the exclusions actually reduce the list
    # (the old Non-Biotech sheet passed limit=400 and never filtered biotech).
    # every matching row is fetched, so "[showing top N of M]" states the real M
    rows = get_signal_rows(conn, where_extra=where_extra)
    rows = [r for r in rows if r[0] not in ETFs and (include_mega or r[0] not in MEGA)]
    if exclude_biotech:
        rows = [r for r in rows if not is_biotech(r[24])]   # r[24] = sic_description
    matched = len(rows)
    if limit and matched > limit:
        rows = rows[:limit]
        subtitle = (subtitle + "  " if subtitle else "") + f"[showing top {limit} of {matched} matching names]"
    # Transparency: if the LIMIT truncates, say so in the subtitle rather than
    # silently showing a subset.
    subtitle = (subtitle + "  " if subtitle else "") + "· signal-detail columns (13F/S1-4/pB/13D/insider) are collapsed — click the ＋ above column T to expand."
    write_title(ws, name, subtitle, len(SIG_HDR))
    out = [signal_row_to_cells(r) for r in rows]
    write_table_rows(ws, out, 5)
    for ridx in range(5, 5 + len(out)):
        format_signal_row(ws, ridx)
    add_signal_heatmap(ws, 5, 4 + len(out))
    last = 4 + len(out)
    # colour is data, pervasively: momentum by sign; buys lapis, sells crimson;
    # insider cluster $ lapis; activist stake lapis (its presence is the signal).
    color_directional(ws, 5, last, 24, higher_is_better=True)     # 3mo % momentum
    color_directional(ws, 5, last, 23, higher_is_better=False)    # vs Entry % (below entry = good)
    color_fixed(ws, 5, last, [15, 16, 17], LAPIS)                 # Clu $, F4 buy 180/30
    color_fixed(ws, 5, last, [18, 19], CRIMSON)                   # F4 sell 180/30
    color_fixed(ws, 5, last, [11, 14], LAPIS)                     # Act %, 13D count
    ws.freeze_panes = "B5"
    if out:
        ws.auto_filter.ref = f"A4:{get_column_letter(len(SIG_HDR))}{4 + len(out)}"
    autosize(ws)
    # ticker col narrower; Business (last col) wide for the one-line summary
    ws.column_dimensions["A"].width = 8
    ws.column_dimensions["C"].width = 22  # Why
    ws.column_dimensions[get_column_letter(len(SIG_HDR))].width = 80
    ws.column_dimensions[get_column_letter(len(SIG_HDR) - 1)].width = 24  # Industry
    # Collapse the granular signal-detail block (cols H–S: section counts, activist,
    # pB, 13D, cluster, Form-4 detail) into an outline group — the "Why" column
    # already summarizes it, so the default view is identity → score → why → size →
    # liquidity → valuation → entry. Click the [+] to expand the full breakdown.
    ws.sheet_properties.outlinePr.summaryRight = False
    for _c in range(8, 20):   # cols H(8)..S(19)
        cd = ws.column_dimensions[get_column_letter(_c)]
        cd.outline_level = 1
        cd.hidden = True

def _signal_flags(r):
    """Independent signal types firing for a unified_signal row (as a dict).
    r keys: smart_money_n, activist_max_pct, form4_buy_30d_m, insider_n,
    insider_cluster_dollars_m, entry_bucket, ev_ebitda, pb_ratio, cat8k_ma,
    cat8k_ctrl, s3_new, s4_add, form4_sell_30d_m."""
    cheap = ((r["ev_ebitda"] is not None and 2 <= r["ev_ebitda"] <= 12)
             or (r["pb_ratio"] is not None and 0 < r["pb_ratio"] <= 1.2))
    return {
        "Smart$≥3":  (r["smart_money_n"] or 0) >= 3,
        "Activist":  (r["activist_max_pct"] or 0) >= 10,
        "Insider30d":(r["form4_buy_30d_m"] or 0) > 0,
        "Cluster":   (r["insider_n"] or 0) >= 2,
        "New/Add":   (r["s3_new"] or 0) > 0 or (r["s4_add"] or 0) > 0,
        "BelowEntry":r["entry_bucket"] == "BELOW_ENTRY",
        "Cheap":     cheap,
        "Catalyst":  bool(r["cat8k_ma"] or r["cat8k_ctrl"]),
    }

def sheet_convergence(wb, conn):
    """Names where several INDEPENDENT signal types fire at once — the single most
    decision-relevant pattern, and one with no home until now (a name recurs
    across five sheets today with no consolidated view). Check-glyph matrix."""
    ws = wb.create_sheet("Convergence")
    ws.sheet_view.showGridLines = False
    flag_names = ["Smart$≥3","Activist","Insider30d","Cluster","New/Add","BelowEntry","Cheap","Catalyst"]
    write_title(ws, "Convergence — where independent signals stack up",
                "Names firing ≥3 independent signal types. Convergence of unrelated signals is the strongest read. Sorted by signal count, then score.", 6 + len(flag_names))
    hdr = ["Ticker","# Sig","Score","Mcap","Off Hi %"] + flag_names + ["Name"]
    write_table_header(ws, 4, hdr)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("""
        SELECT us.*, ps.off_high FROM unified_signal us
        LEFT JOIN price_stats ps ON ps.ticker = us.ticker
        WHERE us.sec_type='common'""").fetchall()
    conn.row_factory = None
    scored = []
    for r in rows:
        if r["ticker"] in ETFs or r["ticker"] in MEGA:
            continue
        flags = _signal_flags(r)
        n = sum(flags.values())
        if n >= 3:
            scored.append((n, r, flags))
    scored.sort(key=lambda t: (-t[0], -(t[1]["score"] or 0)))
    out = []
    for n, r, flags in scored[:120]:
        out.append([r["ticker"], n, round(r["score"] or 0, 1), r["mcap_m"] or "",
                    round(r["off_high"], 0) if r["off_high"] is not None else ""]
                   + ["●" if flags[f] else "" for f in flag_names]
                   + [(r["name"] or "")])
    write_table_rows(ws, out, 5, ticker_col=1)
    from openpyxl.formatting.rule import DataBarRule
    if out:
        ws.conditional_formatting.add(f"B5:B{4+len(out)}",
            DataBarRule(start_type="num", start_value=3, end_type="num", end_value=8, color="808080"))
        ws.auto_filter.ref = f"A4:{get_column_letter(len(hdr))}{4+len(out)}"
    for ridx in range(5, 5 + len(out)):
        ws.cell(row=ridx, column=4).number_format = NUMFMT_MCAP
        ws.cell(row=ridx, column=5).number_format = NUMFMT_PCT
    ws.freeze_panes = "C5"
    autosize(ws)
    ws.column_dimensions["A"].width = 8

def sheet_action_dashboard(wb, conn):
    """Front-page scannable summary: the top actionable setups across ALL signal
    types on one screen, so a reader gets the 'what should I look at today' answer
    without opening 30 tabs. Ranks by convergence (signal count) then score,
    tradeable names first."""
    ws = wb.create_sheet("Action Dashboard")
    ws.sheet_view.showGridLines = False
    write_title(ws, "Action Dashboard — top setups across every signal",
                "The most actionable names right now: strongest convergence of independent signals, with the driver, valuation, momentum and a one-line read. Start here.", 9)
    hdr = ["Ticker","Setup","Score","# Sig","Mcap","ADV $M","EV/EBITDA","Off Hi %","Read"]
    write_table_header(ws, 4, hdr)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("""
        SELECT us.*, tm.adv_3m_usd_m AS adv, ps.off_high, ps.mom_3mo
        FROM unified_signal us
        LEFT JOIN ticker_meta tm ON tm.ticker = us.ticker
        LEFT JOIN price_stats ps ON ps.ticker = us.ticker
        WHERE us.sec_type='common'""").fetchall()
    conn.row_factory = None
    cand = []
    for r in rows:
        if r["ticker"] in ETFs or r["ticker"] in MEGA:
            continue
        flags = _signal_flags(r)
        n = sum(flags.values())
        if n >= 2 and (r["score"] or 0) >= 15:
            cand.append((n, r, flags))
    cand.sort(key=lambda t: (-t[0], -(t[1]["score"] or 0)))
    out = []
    for n, r, flags in cand[:25]:
        fired = [f for f in flags if flags[f]]
        setup = " + ".join(fired[:3])
        # one-line read synthesizing the strongest angle
        bits = []
        if flags["Activist"]:  bits.append(f"activist {r['activist_max_pct']:.0f}%")
        if flags["Cluster"]:   bits.append(f"{r['insider_n']} insiders buying")
        elif flags["Insider30d"]: bits.append("insiders buying")
        if flags["New/Add"]:
            _nb = (r['s3_new'] or 0) + (r['s4_add'] or 0)
            bits.append(f"{_nb} fund{'s' if _nb != 1 else ''} building")
        if flags["Cheap"] and r["ev_ebitda"]: bits.append(f"{r['ev_ebitda']:.0f}x EV/EBITDA")
        if flags["BelowEntry"] and r["vs_entry_pct"]: bits.append(f"{r['vs_entry_pct']:.0f}% vs entry")
        if r["off_high"] is not None and r["off_high"] <= -15: bits.append(f"{r['off_high']:.0f}% off high")
        read = "; ".join(bits[:4]) or setup
        out.append([r["ticker"], setup, round(r["score"] or 0, 1), n, r["mcap_m"] or "",
                    round(r["adv"], 1) if r["adv"] else "",
                    round(r["ev_ebitda"], 1) if r["ev_ebitda"] is not None else "",
                    round(r["off_high"], 0) if r["off_high"] is not None else "",
                    read])
    write_table_rows(ws, out, 5, ticker_col=1)
    from openpyxl.formatting.rule import ColorScaleRule
    if out:
        ws.conditional_formatting.add(f"C5:C{4+len(out)}",
            ColorScaleRule(start_type="min", start_color="FFFFFF", end_type="max", end_color="595959"))
        ws.auto_filter.ref = f"A4:I{4+len(out)}"
    for ridx in range(5, 5 + len(out)):
        ws.cell(row=ridx, column=5).number_format = NUMFMT_MCAP
        ws.cell(row=ridx, column=6).number_format = NUMFMT_M_TO_B
        ws.cell(row=ridx, column=7).number_format = '0.0"x"'
        ws.cell(row=ridx, column=8).number_format = NUMFMT_PCT
    ws.freeze_panes = "B5"
    autosize(ws)
    ws.column_dimensions["A"].width = 8
    ws.column_dimensions["B"].width = 30
    ws.column_dimensions["I"].width = 62

def _has_prior(conn):
    try:
        return conn.execute("SELECT COUNT(*) FROM fund_13f_prior").fetchone()[0] > 0
    except sqlite3.OperationalError:
        return False

def sheet_qoq_change(wb, conn):
    """Quarter-over-quarter 13F change: current holdings diffed against each fund's
    PRIOR filing. A single-quarter snapshot cannot tell accumulation from quiet
    distribution — this can. Net funds building (new+add) minus trimming
    (reduced+exited), and net $ flow, per ticker."""
    ws = wb.create_sheet("QoQ Change")
    ws.sheet_view.showGridLines = False
    write_title(ws, "QoQ Position Change — building vs quietly trimming",
                "Current 13F vs each fund's PRIOR filing, matched on CUSIP + share count (mapping/value-unit safe). Net Funds = (new+added) − (trimmed+exited), counting every fund equally and every size of move (for weighted buying see Revealed Preference). All-new names are often IPOs, spin-offs or SPACs (Note says which); mixed-churn rows (both adds and trims) are the cleanest accumulation/distribution reads.", 12)
    hdr = ["Ticker","Net Funds","New","Added","Trimmed","Exited","Δ Shares %","Form","Score","Mcap","Name","Note"]
    write_table_header(ws, 4, hdr)
    # Per-ticker NON-COMMON equity forms held (preferred / warrant / unit /
    # right / note): so an accumulation that is really warrants or converts —
    # optionality/financing, not a clean directional common buy — is flagged
    # rather than read as conviction. Blank = pure common.
    formmix = {}
    try:
        for tk, forms in conn.execute("""
            SELECT COALESCE(cm.ticker, h.cusip) tk,
                   GROUP_CONCAT(DISTINCT sf.sec_form)
            FROM fund_13f_holdings h
            LEFT JOIN cusip_map cm ON cm.cusip = h.cusip
            JOIN holding_sec_form sf ON sf.accession=h.accession AND sf.cusip=h.cusip
            WHERE sf.sec_form IS NOT NULL AND sf.sec_form NOT IN ('common','class')
            GROUP BY tk"""):
            formmix[tk] = forms
    except sqlite3.OperationalError:
        pass
    # Match on CUSIP (stable across quarters), not ticker — the two quarters were
    # mapped by different logic, so a ticker-level diff is dominated by mapping
    # noise (Comcast CMCSA vs CCZ). Share counts are unit-independent, so we
    # ignore the value_k unit stragglers entirely and diff shares.
    conn.execute("""CREATE TABLE IF NOT EXISTS prior_split_factor
        (fund TEXT, ticker TEXT, factor REAL, PRIMARY KEY (fund, ticker))""")   # built by ingest_splits
    rows = list(conn.execute("""
        WITH ok_funds AS (
             -- guard against PARTIAL prior filings: Berkshire's prior accession
             -- covered only $67B of a $263B book, manufacturing fake adds/exits.
             -- A fund's prior book must be within [40%, 250%] of current to diff.
             SELECT c.fund FROM
               (SELECT fund, SUM(value_k) v FROM fund_13f_holdings GROUP BY fund) c
               JOIN (SELECT fund, SUM(value_k) v FROM fund_13f_prior GROUP BY fund) p
               ON p.fund=c.fund
             WHERE c.v > 0 AND p.v BETWEEN c.v*0.4 AND c.v*2.5
                 -- one vote per filing (a manager under two roster names)
                 AND c.fund IN (SELECT MIN(fund) FROM fund_13f_holdings GROUP BY accession)),
             -- match at the TICKER level (via cusip_map), not raw CUSIP: an
             -- ADR->ordinary CUSIP change between quarters (AZN 046353108 ->
             -- G0593M107) otherwise fabricates "19 funds new + 19 exited".
             cur AS (SELECT h.fund, COALESCE(cm.ticker, h.cusip) tk, SUM(h.shares) sh
                     FROM fund_13f_holdings h LEFT JOIN cusip_map cm ON cm.cusip=h.cusip
                     WHERE h.cusip IS NOT NULL AND h.sh_type IN ('SH','')
                       AND substr(h.cusip,7,1) BETWEEN '0' AND '9'
                       AND substr(h.cusip,8,1) BETWEEN '0' AND '9'
                       AND h.fund IN (SELECT fund FROM ok_funds)
                     GROUP BY h.fund, tk),
             -- prior shares on the CURRENT share basis: a split inside the
             -- window (Booking 25:1, KLA 10:1, Carvana 5:1 in Q2 2026) made
             -- every holder read as a +400-999% "adder" (ingest_splits.py)
             pri AS (SELECT h.fund, COALESCE(cm.ticker, h.cusip) tk,
                            SUM(h.shares) * COALESCE(MAX(sf.factor), 1) sh
                     FROM fund_13f_prior h LEFT JOIN cusip_map cm ON cm.cusip=h.cusip
                     LEFT JOIN prior_split_factor sf ON sf.fund = h.fund
                          AND sf.ticker = COALESCE(cm.ticker, h.cusip)
                     WHERE h.cusip IS NOT NULL AND h.sh_type IN ('SH','')
                       AND substr(h.cusip,7,1) BETWEEN '0' AND '9'
                       AND substr(h.cusip,8,1) BETWEEN '0' AND '9'
                       AND h.fund IN (SELECT fund FROM ok_funds)
                     GROUP BY h.fund, tk),
             chg AS (
               SELECT cur.fund, cur.tk, cur.sh cur_sh, pri.sh pri_sh
               FROM cur LEFT JOIN pri ON pri.fund=cur.fund AND pri.tk=cur.tk
               UNION ALL
               SELECT pri.fund, pri.tk, NULL, pri.sh
               FROM pri LEFT JOIN cur ON cur.fund=pri.fund AND cur.tk=pri.tk
               WHERE cur.fund IS NULL)
        SELECT tk,
          SUM(CASE WHEN pri_sh IS NULL AND cur_sh>0 THEN 1 ELSE 0 END) n_new,
          SUM(CASE WHEN pri_sh IS NOT NULL AND cur_sh>pri_sh*1.05 THEN 1 ELSE 0 END) n_add,
          SUM(CASE WHEN cur_sh IS NOT NULL AND pri_sh IS NOT NULL AND cur_sh<pri_sh*0.95 THEN 1 ELSE 0 END) n_trim,
          SUM(CASE WHEN cur_sh IS NULL AND pri_sh>0 THEN 1 ELSE 0 END) n_exit,
          SUM(COALESCE(cur_sh,0)) - SUM(COALESCE(pri_sh,0)) d_sh,
          SUM(COALESCE(pri_sh,0)) p_sh
        FROM chg GROUP BY tk""").fetchall())
    scored = []
    for r in rows:
        tk, n_new, n_add, n_trim, n_exit, d_sh, p_sh = r
        net_funds = (n_new + n_add) - (n_trim + n_exit)
        if abs(net_funds) < 2:
            continue
        us = conn.execute("SELECT score, mcap_m, name, sec_type FROM unified_signal WHERE ticker=?", (tk,)).fetchone()
        if not us or us[3] != 'common' or tk in ETFs or tk in MEGA:
            continue
        d_pct = (d_sh / p_sh * 100) if p_sh else (100 if d_sh > 0 else 0)
        scored.append((net_funds, tk, n_new, n_add, n_trim, n_exit, d_pct, us[0], us[1], us[2]))
    # Mixed-churn rows (some adds/trims/exits, i.e. funds with an existing view
    # changing it) are the cleanest accumulation/distribution read; all-new rows
    # (IPO/SPAC allocations) sort below them rather than walling off the top.
    scored.sort(key=lambda x: (-(1 if (x[3] + x[4] + x[5]) > 0 else 0), -x[0]))
    churn = [t for t in scored if (t[3] + t[4] + t[5]) > 0]
    allnew = [t for t in scored if (t[3] + t[4] + t[5]) == 0]
    top = churn[:70] + churn[-30:] + allnew[:20]
    ws.cell(row=2, column=1).value += (f" [showing the 70 strongest builders and 30 strongest distributors of "
                                       f"{len(churn)} names with churn, and the top 20 of {len(allnew)} all-new names]")
    # an all-new holder list on a fresh listing is allocation, not accumulation
    import datetime as _dt
    from fund_moves import latest_due_quarter, _prev_quarter_end
    since = _prev_quarter_end(latest_due_quarter())
    near = (_dt.date.fromisoformat(since) - _dt.timedelta(days=45)).isoformat()
    lst = {t: (d, ind, nm) for t, d, ind, nm in conn.execute(
        "SELECT ticker, ipo_date, industry, long_name FROM ticker_yf")}
    def note(tk, pure_new):
        d, ind, nm = lst.get(tk, (None, None, None))
        if ind == "Shell Companies" or "acquisition corp" in (nm or "").lower():
            return "SPAC: holders subscribed to a blank-check listing"
        if d and (d > since or (pure_new and d > near)):
            return f"listed {d} (IPO or spin-off): holders were allocated or handed shares"
        return ""
    out = []
    for nf, tk, n_new, n_add, n_trim, n_exit, d_pct, score, mcap, name in top:
        pure_new = (n_add + n_trim + n_exit) == 0
        out.append([tk, nf, n_new, n_add, n_trim, n_exit,
                    "new" if pure_new else round(max(-99, min(999, d_pct)), 0),
                    "common" if tk not in formmix else "+" + formmix[tk],
                    round(score or 0, 1), mcap or "", (name or ""), note(tk, pure_new)])
    write_table_rows(ws, out, 5, ticker_col=1)
    # colour is data: Net Funds & Δ Shares — lapis building, crimson trimming
    color_directional(ws, 5, 4 + len(out), [2, 7], higher_is_better=True)
    if out:
        ws.auto_filter.ref = f"A4:L{4+len(out)}"
    for ridx in range(5, 5 + len(out)):
        ws.cell(row=ridx, column=7).number_format = '0"%"'      # Δ Shares % (was $M — wrong unit)
        ws.cell(row=ridx, column=9).number_format = '0.0'       # Score
        ws.cell(row=ridx, column=10).number_format = NUMFMT_MCAP
    ws.freeze_panes = "B5"
    autosize(ws)
    ws.column_dimensions["A"].width = 8

_EVENTS, _SHORTS = {}, {}

def sheet_dossier(wb, conn, top_n=45):
    """One consolidated block per ticker — score + drivers, holders, insiders,
    activist, catalysts, valuation, momentum — so vetting an idea doesn't mean
    hand-cross-referencing six ticker-keyed sheets. Covers the top-N by score."""
    from _canon import canon
    ws = wb.create_sheet("Ticker Dossier")
    ws.sheet_view.showGridLines = False
    write_title(ws, "Ticker Dossier — every signal per name, one block each",
                f"Top {top_n} by score. Each block: drivers · top holders (13F %book) · insiders · activist · recent 8-Ks · valuation & momentum. The single-idea vetting view.", 8)
    conn.row_factory = sqlite3.Row
    names = conn.execute("""SELECT us.*, tm.adv_3m_usd_m adv, ps.off_high, ps.mom_3mo,
               yf.rev_growth, yf.profit_margin, yf.fwd_pe, yf.ptb_ratio, yf.neg_tbv
        FROM unified_signal us
        LEFT JOIN ticker_meta tm ON tm.ticker=us.ticker
        LEFT JOIN price_stats ps ON ps.ticker=us.ticker
        LEFT JOIN ticker_yf yf ON yf.ticker=us.ticker
        WHERE us.sec_type='common' AND us.ticker NOT IN ({})
        ORDER BY us.score DESC LIMIT ?""".format(",".join("?"*len(MEGA))),
        list(MEGA) + [top_n]).fetchall()
    conn.row_factory = None
    row = 4
    from openpyxl.styles import Font as _F
    for r in names:
        tk = r["ticker"]
        # header line: ticker — name | score | mcap | bucket
        h = ws.cell(row=row, column=1, value=f"{tk} — {(r['name'] or '')}")
        h.font = _F(name="Times New Roman", size=11, bold=True)
        ws.cell(row=row, column=6, value=f"Score {r['score']:.0f}")
        ws.cell(row=row, column=7, value=f"{(r['mcap_m'] or 0)/1000:.1f}B" if r['mcap_m'] else "")
        ws.cell(row=row, column=8, value=r["mcap_bucket"] or "")
        row += 1
        # drivers
        ws.cell(row=row, column=1, value="Drivers"); ws.cell(row=row, column=2, value=_why(r["components"])); row += 1
        # top holders (13F, canonical, %book)
        holders = []
        seen = set()
        for hr in conn.execute("""SELECT fund, pct_book FROM fund_13f_holdings
                WHERE ticker=? AND sh_type IN ('SH','') ORDER BY value_k DESC LIMIT 8""", (tk,)):
            c = canon(hr[0])
            if c in seen: continue
            seen.add(c)
            nm = re.sub(r"\s*\(.*$", "", hr[0]).strip()
            holders.append(f"{nm}{f' {hr[1]:.0f}%' if hr[1] else ''}")
        ws.cell(row=row, column=1, value="Held by"); ws.cell(row=row, column=2, value=", ".join(holders[:6])); row += 1
        # registered funds (N-PORT) holding it, largest weight first
        try:
            npf = conn.execute("""SELECT series, pct FROM nport_holdings WHERE ticker = ?
                                  ORDER BY pct DESC LIMIT 6""", (tk,)).fetchall()
        except sqlite3.OperationalError:
            npf = []
        if npf:
            ws.cell(row=row, column=1, value="N-PORT funds")
            ws.cell(row=row, column=2, value=", ".join(f"{sr} {p:.1f}%" for sr, p in npf if sr)); row += 1
        # insiders + activist
        ins = conn.execute("""SELECT COUNT(DISTINCT owner), SUM(shares*price)/1e6,
                MAX(CASE WHEN role LIKE '%CEO%' OR role LIKE '%CFO%' OR role LIKE '%Chief%' OR role LIKE '%President%' THEN 1 ELSE 0 END)
                FROM form4_transactions WHERE ticker=? AND code='P' AND trans_date>=date('now','-180 days')
                  AND price<200000""", (tk,)).fetchone()
        act = conn.execute("""SELECT holder, pct_class, form FROM holder_13d WHERE subject_ticker=?
                ORDER BY pct_class DESC LIMIT 1""", (tk,)).fetchone()
        parts = []
        if ins and ins[0]: parts.append(f"{ins[0]} insiders bought ${ins[1]:.1f}M{' (C-suite)' if ins[2] else ''}")
        if r["insider_n"] and r["insider_n"] >= 2: parts.append(f"{r['insider_n']}-insider cluster")
        if act: parts.append(f"{re.sub(r'( |).*$','',act[0])} {act[1]:.0f}% ({'13D' if '13D' in (act[2] or '') else '13G'})" if act[1] else "")
        ws.cell(row=row, column=1, value="Insiders"); ws.cell(row=row, column=2, value=" · ".join(p for p in parts if p)); row += 1
        # members of Congress trading this name (STOCK Act, last 180 days)
        try:
            cg = conn.execute("""SELECT
                    COUNT(DISTINCT CASE WHEN type = 'Purchase' THEN member_id END),
                    COUNT(DISTINCT CASE WHEN type LIKE 'Sale%' THEN member_id END),
                    GROUP_CONCAT(CASE WHEN type = 'Purchase' THEN member || ' (' || owner || ', '
                                 || amount_text || ', ' || trans_date || ')' END, ' | ')
                FROM congress_trades WHERE ticker = ? AND trans_date >= date('now', '-180 days')
                  AND asset_type IN ('Stock', 'Stock Option')""", (tk,)).fetchone()
        except sqlite3.OperationalError:
            cg = None
        if cg and (cg[0] or cg[1]):
            ctxt = f"{cg[0]} member(s) bought, {cg[1]} sold in 180 days"
            if cg[2]:
                ctxt += " · " + " | ".join(cg[2].split(" | ")[:6])
            ws.cell(row=row, column=1, value="Congress"); ws.cell(row=row, column=2, value=ctxt); row += 1
        # recent catalysts
        cats = conn.execute("""SELECT filed, has_ma, has_control, has_director, has_pipe FROM catalysts_8k
                WHERE ticker=? ORDER BY filed DESC LIMIT 3""", (tk,)).fetchall()
        clabels = []
        for c in cats:
            tags = [t for t, on in [("M&A", c[1]), ("control", c[2]), ("director", c[3]), ("PIPE", c[4])] if on]
            if tags: clabels.append(f"{c[0][:10]} {'/'.join(tags)}")
        ws.cell(row=row, column=1, value="Catalysts"); ws.cell(row=row, column=2, value="; ".join(clabels) or "—"); row += 1
        evs = _EVENTS.get(tk) or []
        if evs:
            ws.cell(row=row, column=1, value="Events"); ws.cell(row=row, column=2, value="; ".join(e[2] for e in evs[:4])); row += 1
        sh = _SHORTS.get(tk)
        if sh and sh[0] is not None:
            ws.cell(row=row, column=1, value="Shorts")
            ws.cell(row=row, column=2, value=f"{sh[0]:.1f}% of shares sold short, {sh[1] or 0:.1f} days to cover"
                    + (f" ({sh[2]:+.0f}% in three months)" if sh[2] is not None else "")); row += 1
        # valuation + momentum
        val = []
        if r["ev_ebitda"] is not None: val.append(f"EV/EBITDA {r['ev_ebitda']:.1f}x")
        if r["pe_ttm"] is not None and r["pe_ttm"] > 0: val.append(f"P/E {r['pe_ttm']:.1f}x")
        if r["pb_ratio"] is not None: val.append(f"P/B {r['pb_ratio']:.2f}x")
        if r["ptb_ratio"] is not None and r["ptb_ratio"] > 0: val.append(f"P/TB {r['ptb_ratio']:.2f}x")
        elif r["neg_tbv"]: val.append("P/TB n/m (negative tangible book)")
        if r["fwd_pe"] is not None and r["fwd_pe"] > 0: val.append(f"Fwd P/E {r['fwd_pe']:.0f}")
        if r["rev_growth"] is not None: val.append(f"Rev {r['rev_growth']*100:+.0f}%")
        if r["profit_margin"] is not None: val.append(f"Margin {r['profit_margin']*100:.0f}%")
        if r["mom_3mo"] is not None: val.append(f"3mo {r['mom_3mo']:+.0f}%")
        if r["off_high"] is not None: val.append(f"{r['off_high']:+.0f}% off high")
        ws.cell(row=row, column=1, value="Valuation"); ws.cell(row=row, column=2, value=" · ".join(val)); row += 1
        # earnings track record (FMP): beat rate over the last 8 reported quarters
        try:
            eb = conn.execute("""SELECT n_q, beats, last_date, last_surprise_pct, streak,
                                        rev_n, rev_beats, last_rev_surprise_pct
                                 FROM earnings_beat WHERE ticker=?""", (tk,)).fetchone()
        except sqlite3.OperationalError:
            eb = None
        if eb and (eb[0] or eb[5]):
            parts = []
            if eb[0]:
                parts.append(f"EPS beat {eb[1]} of last {eb[0]} quarters")
            if eb[5]:
                parts.append(f"revenue beat {eb[6]} of {eb[5]}")
            last = ([f"EPS {eb[3]:+.0f}%"] if eb[3] is not None else []) + \
                   ([f"revenue {eb[7]:+.1f}%"] if eb[7] is not None else [])
            if last:
                parts.append(f"last ({eb[2]}): {', '.join(last)} vs consensus")
            if eb[4] and eb[4] >= 2:
                parts.append(f"{eb[4]}-quarter EPS beat streak")
            ws.cell(row=row, column=1, value="Earnings"); ws.cell(row=row, column=2, value=" · ".join(parts)); row += 1
        # thin rule between blocks
        row += 1
    for rr in range(4, row):
        c = ws.cell(row=rr, column=1)
        if c.value in ("Drivers", "Held by", "Insiders", "Congress", "Catalysts", "Events", "Shorts",
                       "Valuation", "Earnings"):
            c.font = _F(name="Times New Roman", size=9, italic=True, color="7F7F7F")
    ws.column_dimensions["A"].width = 16
    ws.column_dimensions["B"].width = 96
    ws.freeze_panes = "A4"

def sheet_whos_buying(wb, conn):
    """The NAMES behind the s3/s4 counts — which specific funds are initiating new
    positions and materially adding. Counts tell you 'how many'; this tells you
    'who', which is the part that actually matters (a Baupost new position reads
    very differently from an anonymous count of 3). Same evidence as the score
    (fund_moves.section_evidence): the latest 13F quarter where a fund has a
    current book, research notes only for funds without one."""
    from fund_moves import section_evidence, latest_due_quarter, short_fund
    ev, st = section_evidence(conn)
    q = latest_due_quarter()
    ws = wb.create_sheet("Who's Buying")
    ws.sheet_view.showGridLines = False
    write_title(ws, "Who's Buying — the funds behind the New / Add counts",
                f"Per name: which funds INITIATED a position (S3) and which ADDED 25%+ to one (S4). For the "
                f"{st['fresh']} funds with a current 13F book this is their {q} filing vs the quarter before "
                f"('new 4.1%' = opened, now 4.1% of the book; moves under 0.5% of a book, spin-offs received and "
                f"lines new at an IPO left out). Funds without a current 13F show their research notes, marked. "
                f"Ranked by focus-weighted count (S3 x2 + S4). De-duplicated by manager.", 8)
    hdr = ["Ticker", "Company", "Score", "Form", "# New", "New Initiators (funds)", "# Add", "Material Adders (funds)"]
    write_table_header(ws, 4, hdr)
    nc_form = {}
    try:
        for tk, forms in conn.execute("""
            SELECT COALESCE(cm.ticker, h.cusip) tk, GROUP_CONCAT(DISTINCT sf.sec_form)
            FROM fund_13f_holdings h LEFT JOIN cusip_map cm ON cm.cusip=h.cusip
            JOIN holding_sec_form sf ON sf.accession=h.accession AND sf.cusip=h.cusip
            WHERE sf.sec_form NOT IN ('common','class') GROUP BY tk"""):
            nc_form[tk] = forms
    except sqlite3.OperationalError:
        pass
    rows = conn.execute("""
        SELECT us.ticker, us.name, us.score, us.s3_new, us.s4_add
        FROM unified_signal us
        WHERE us.sec_type='common' AND (us.s3_new > 0 OR us.s4_add > 0)
        ORDER BY (us.s3_new*2 + us.s4_add) DESC, us.score DESC""").fetchall()
    rows = [r for r in rows if r[0] not in ETFs]
    total, limit = len(rows), 200
    ws.cell(row=2, column=1).value += f" [showing top {min(limit, total)} of {total}]"

    def names(d, skip=()):
        items = sorted(((m, e) for m, e in (d or {}).items() if m not in skip), key=lambda x: -x[1]["w"])
        return [f"{short_fund(e['fund'])} ({e['label']})" for m, e in items]
    out = []
    for tk, name, score, s3, s4 in rows[:limit]:
        d = ev.get(tk, {})
        new_d = d.get(3, {})
        # the same manager can't be simultaneously INITIATING and ADDING — when
        # the evidence places it in both sections, the initiation wins.
        new_f = names(new_d)
        add_f = names(d.get(4, {}), skip=set(new_d))
        out.append([tk, (name or ""), round(score or 0, 1),
                    "common" if tk not in nc_form else "+" + nc_form[tk],
                    len(new_f), "; ".join(new_f), len(add_f), "; ".join(add_f)])
    write_table_rows(ws, out, 5, ticker_col=1)
    ws.freeze_panes = "B5"
    if out:
        ws.auto_filter.ref = f"A4:H{4 + len(out)}"
    autosize(ws)
    ws.column_dimensions["F"].width = 60
    ws.column_dimensions["H"].width = 60

def short_data(conn):
    """({ticker: (short % of shares out, days to cover, 3-month change %)},
    settlement date) from FINRA's latest settlement (ingest_short_interest)."""
    try:
        dates = [r[0] for r in conn.execute("SELECT DISTINCT settlement_date FROM short_interest ORDER BY 1 DESC")]
    except sqlite3.OperationalError:
        return {}, None
    if not dates:
        return {}, None
    old = dict(conn.execute("SELECT ticker, short_shares FROM short_interest WHERE settlement_date = ?",
                            (dates[1],))) if len(dates) > 1 else {}
    so = dict(conn.execute("SELECT ticker, shares_out_m FROM ticker_yf WHERE shares_out_m > 0"))
    out = {}
    for tk, ss, dtc in conn.execute("""SELECT ticker, short_shares, days_to_cover FROM short_interest
            WHERE settlement_date = ?""", (dates[0],)):
        pct = 100.0 * ss / (so[tk] * 1e6) if so.get(tk) and ss is not None else None
        if pct is not None and pct > 100:          # an ADR's shares against the ordinary count
            pct = None
        o = old.get(tk)
        chg = 100.0 * (ss / o - 1) if o and ss is not None and o > 0 else None
        out[tk] = (pct, dtc, chg)
    return out, dates[0]

def events_by_ticker(conn):
    """{ticker: [(kind, filed, text)]} from sec_events: proxy contests,
    tender / going-private offers, spin-offs (on the parent's ticker)."""
    out = {}
    try:
        rows = conn.execute("""SELECT kind, form, filed, subject_ticker, subject_name, party_name, detail
            FROM sec_events WHERE kind IN ('proxy', 'tender', 'spin') ORDER BY filed DESC""").fetchall()
    except sqlite3.OperationalError:
        return out
    from ingest_sec_events import parent_ticker
    for kind, form, filed, tk, subj, party, detail in rows:
        if kind == "spin":
            ptk = parent_ticker(detail)
            if ptk:
                out.setdefault(ptk, []).append(("spin", filed, f"spinning off {subj} (Form 10 {filed})"))
            continue
        if not tk:
            continue
        what = {"proxy": f"proxy contest ({party or 'dissident'}, {form} {filed})",
                "tender": f"{'going-private' if form == 'SC 13E3' else 'tender offer'} ({party or subj}, {form} {filed})"}
        out.setdefault(tk, []).append((kind, filed, what[kind]))
    return out

def track_records(conn):
    """{fund: row} from fund_track_record (track_records.py)."""
    try:
        cols = [r[1] for r in conn.execute("PRAGMA table_info(fund_track_record)")]
        return {r[0]: dict(zip(cols, r)) for r in conn.execute("SELECT * FROM fund_track_record")}
    except sqlite3.OperationalError:
        return {}

def sheet_special_situations(wb, conn):
    """Filings that betray a coming catalyst (ingest_sec_events): proxy
    contests, spin-offs being registered, tender and going-private offers —
    each with who holds the company (or the spin-off's parent)."""
    try:
        ev = conn.execute("""SELECT kind, form, filed, accession, subject_cik, subject_name, subject_ticker,
            party_name, detail FROM sec_events WHERE kind IN ('proxy', 'spin', 'tender')""").fetchall()
    except sqlite3.OperationalError:
        return
    ws = wb.create_sheet("Special Situations")
    ws.sheet_view.showGridLines = False
    write_title(ws, "Special Situations — proxy fights, spin-offs coming, tender and going-private offers",
                "From SEC filings (EDGAR full-text search): proxy contests in the last 180 days (a dissident's "
                "materials, or the company's contested proxy); Form 10 registrations in the last 365 days (a new "
                "company being registered — a spin-off when the filing names a parent); third-party tender offers, "
                "going-private deals and target responses in the last 180 days. 13F = conviction-weighted holders "
                "of the company (for a spin-off, of its parent).", 11)
    fac = {r[0]: r[1:] for r in conn.execute("""SELECT us.ticker, us.smart_money_n, us.mcap_m, us.score,
        COALESCE(y.long_name, us.name), rp.rp_score FROM unified_signal us
        LEFT JOIN ticker_yf y ON y.ticker = us.ticker LEFT JOIN revealed_pref rp ON rp.ticker = us.ticker""")}
    roster = {r[0].upper() for r in conn.execute("SELECT fund FROM fund_meta")}
    from _canon import canon
    roster_c = {canon(f) for f in roster}
    row = 4
    def block(title, hdr, out, fmts):
        nonlocal row
        write_section_heading(ws, row, f"{title} — {len(out)}", 11)
        row += 1
        if not out:
            row += 1
            return
        write_table_header(ws, row, hdr)
        row += 1
        write_table_rows(ws, out, row)
        for col, f in fmts.items():
            for r_ in range(row, row + len(out)):
                ws.cell(row=r_, column=col).number_format = f
        row += len(out) + 2
    # proxy fights, one row per company
    g = {}
    for kind, form, filed, acc, cik, subj, tk, party, detail in ev:
        if kind != "proxy":
            continue
        d = g.setdefault(cik, {"tk": tk, "name": subj, "forms": set(), "first": filed, "last": filed, "n": 0,
                               "parties": set()})
        d["forms"].add(form); d["n"] += 1
        d["first"], d["last"] = min(d["first"], filed), max(d["last"], filed)
        if party and form not in ("PREC14A", "DEFC14A"):
            d["parties"].add(party)
    # closed-end and unlisted funds (Saba's discount campaigns, muni funds) are
    # a different game from a dissident at an operating company: shown apart
    fundlike = {t for (t,) in conn.execute("SELECT ticker FROM ticker_yf WHERE is_fund = 1")}
    def is_fund(tk, name):
        return tk in fundlike or bool(re.search(r"\bFund\b|\bMunicipal|Tax[- ]Free|Income Trust|Closed[- ]End",
                                                 name or "", re.I))
    out, funds_out = [], []
    for cik, d in sorted(g.items(), key=lambda x: x[1]["last"], reverse=True):
        f = fac.get(d["tk"]) or (None,) * 5
        tracked = any(canon(p) in roster_c for p in d["parties"])
        (funds_out if is_fund(d["tk"], d["name"]) else out).append(
            [d["tk"] or "", d["name"], "; ".join(sorted(d["parties"])) or "(company's contested proxy)",
             "tracked fund" if tracked else "", d["first"], d["last"], d["n"], ", ".join(sorted(d["forms"])),
             round(f[0], 1) if f[0] else "", f[1] or "", round(f[4], 1) if f[4] else ""])
    hdr_p = ["Ticker", "Company", "Dissident", "Tracked?", "First Filing", "Latest", "Filings", "Forms",
             "13F", "Mcap", "RP Score"]
    block("Proxy fights at operating companies", hdr_p, out, {10: NUMFMT_MCAP})
    block("Proxy fights at closed-end and unlisted funds (discount and governance campaigns)", hdr_p, funds_out,
          {10: NUMFMT_MCAP})
    # spin-offs coming, one row per registrant
    g = {}
    for kind, form, filed, acc, cik, subj, tk, party, detail in ev:
        if kind != "spin":
            continue
        d = g.setdefault(cik, {"name": subj, "tk": tk, "first": filed, "last": filed, "n": 0, "parent": party,
                               "detail": detail})
        d["n"] += 1
        d["first"], d["last"] = min(d["first"], filed), max(d["last"], filed)
    from ingest_sec_events import parent_ticker
    spins, other, unread = [], [], []
    for cik, d in sorted(g.items(), key=lambda x: x[1]["last"], reverse=True):
        ptk = parent_ticker(d["detail"]) or ""
        f = fac.get(ptk) or (None,) * 5
        mm = re.search(r"then merging into (.+)$", d["detail"] or "")
        r_ = [ptk, d["parent"] or "", d["name"], d["tk"] or "", mm.group(1) if mm else "", d["first"], d["last"],
              d["n"], round(f[0], 1) if f[0] else "", f[1] or "", round(f[4], 1) if f[4] else ""]
        if d["parent"]:
            spins.append(r_)
        elif (d["detail"] or "").startswith("parent not read"):
            unread.append(r_[:4] + r_[5:])
        else:
            other.append(r_[:4] + r_[5:])
    block("Spin-offs coming (Form 10 names a parent)", ["Ticker", "Parent", "New Company", "New Ticker",
          "Then Merging Into", "First Filing", "Latest", "Filings", "13F", "Mcap", "RP Score"], spins,
          {10: NUMFMT_MCAP})
    block("Other Form 10 registrations (no company distributes the shares: private funds and BDCs registering, "
          "uplistings, holding-company formations)",
          ["Ticker", "Parent", "Company", "Ticker Filed", "First Filing", "Latest", "Filings", "13F", "Mcap",
           "RP Score"], other, {9: NUMFMT_MCAP})
    if unread:
        block("Form 10 registrations not read yet (EDGAR did not serve the document; read on the next run)",
              ["Ticker", "Parent", "Company", "Ticker Filed", "First Filing", "Latest", "Filings", "13F", "Mcap",
               "RP Score"], unread, {9: NUMFMT_MCAP})
    # tender offers and going-private, one row per target
    g = {}
    for kind, form, filed, acc, cik, subj, tk, party, detail in ev:
        if kind != "tender":
            continue
        d = g.setdefault(cik, {"tk": tk, "name": subj, "forms": set(), "first": filed, "last": filed,
                               "parties": set()})
        d["forms"].add(form)
        d["first"], d["last"] = min(d["first"], filed), max(d["last"], filed)
        if party and party != subj:
            d["parties"].add(party)
    out = []
    for cik, d in sorted(g.items(), key=lambda x: x[1]["last"], reverse=True):
        f = fac.get(d["tk"]) or (None,) * 5
        kind = "going private" if "SC 13E3" in d["forms"] else "tender offer"
        out.append([d["tk"] or "", d["name"], kind, "; ".join(sorted(d["parties"])), d["first"], d["last"],
                    ", ".join(sorted(d["forms"])), round(f[0], 1) if f[0] else "", f[1] or ""])
    block("Tender offers and going-private deals", ["Ticker", "Company", "Kind", "Bidder / Filer", "First Filing",
          "Latest", "Forms", "13F", "Mcap"], out, {9: NUMFMT_MCAP})
    ws.freeze_panes = "A4"
    autosize(ws)
    for col, w in (("B", 36), ("C", 44), ("D", 30)):
        ws.column_dimensions[col].width = w

def sheet_short_interest(wb, conn):
    """FINRA short interest against what the funds own: crowded shorts the
    funds hold with conviction, shorts building, shorts being covered."""
    sd, settle = short_data(conn)
    if not sd:
        return
    ws = wb.create_sheet("Short Interest")
    ws.sheet_view.showGridLines = False
    write_title(ws, f"Short Interest — crowded shorts, bears building and leaving (FINRA, settled {settle})",
                "Short % Out = shares sold short ÷ shares outstanding; Days to Cover = short shares ÷ average daily "
                "volume; 3M Chg = change in short shares against the settlement about three months earlier. A "
                "name the funds own with conviction and the bears crowd is a squeeze candidate, or a warning. "
                "13F = conviction-weighted holders; Last Qtr = funds buying / selling in the latest 13F quarter. "
                "Names the funds own: weighted holders 1.5+ or a 1%+ position, market cap $50M+. A short count "
                "near or above half the shares out usually means a small float (a new listing) or a share count "
                "not yet updated for a reverse split — check before reading it as a squeeze.", 12)
    from fund_moves import quarter_moves
    mv, _ = quarter_moves(conn)
    lq = {}
    for m in mv:
        d = lq.setdefault(m["ticker"], [set(), set()])
        (d[0] if m["kind"] in ("new", "add") else d[1]).add(m["fund"])
    fac = {r[0]: r[1:] for r in conn.execute("""SELECT us.ticker, us.smart_money_n, us.max_pct_book, us.mcap_m,
        COALESCE(y.long_name, us.name), y.industry, rp.rp_score FROM unified_signal us
        LEFT JOIN ticker_yf y ON y.ticker = us.ticker LEFT JOIN revealed_pref rp ON rp.ticker = us.ticker
        WHERE us.sec_type = 'common'""")}
    def row_for(tk):
        pct, dtc, chg = sd[tk]
        f = fac[tk]
        b = lq.get(tk, [set(), set()])
        return [tk, round(pct, 1) if pct is not None else "", round(dtc, 1) if dtc is not None else "",
                round(chg) if chg is not None else "", round(f[0] or 0, 1), round(f[1] or 0, 1),
                f"+{len(b[0])} / -{len(b[1])}" if (b[0] or b[1]) else "", round(f[5], 1) if f[5] else "",
                f[2] or "", f[3] or "", f[4] or ""]
    hdr = ["Ticker", "Short % Out", "Days to Cover", "3M Chg %", "13F", "Max % Book", "Last Qtr", "RP Score",
           "Mcap", "Name", "Industry"]
    fmts = {2: '0.0"%"', 3: '0.0', 4: '+0"%";-0"%"', 5: '0.0', 6: NUMFMT_PCT, 8: '0.0', 9: NUMFMT_MCAP}
    row = 4
    def block(title, tks):
        nonlocal row
        write_section_heading(ws, row, f"{title} — {len(tks)}", 12)
        row += 1
        if not tks:
            row += 1
            return
        write_table_header(ws, row, hdr)
        row += 1
        out = [row_for(t) for t in tks]
        write_table_rows(ws, out, row)
        for col, f in fmts.items():
            for r_ in range(row, row + len(out)):
                ws.cell(row=r_, column=col).number_format = f
        color_directional(ws, row, row + len(out) - 1, [4], higher_is_better=False)
        row += len(out) + 2
    # "the funds own": a real holding (weighted holders 1.5+ or a position of 1%+
    # of a book) in a company big enough to matter ($50M+): a $0.1M shell one
    # fund holds a sliver of is noise, however short it is
    held = [t for t in sd if t in fac and ((fac[t][0] or 0) >= 1.5 or (fac[t][1] or 0) >= 1)
            and (fac[t][2] or 0) >= 50]
    crowded = [t for t in held if (sd[t][0] or 0) >= 10 or ((sd[t][1] or 0) >= 8 and (sd[t][0] or 0) >= 5)]
    crowded.sort(key=lambda t: -(sd[t][0] or 0))
    building = [t for t in held if (sd[t][2] or 0) >= 50 and (sd[t][0] or 0) >= 3]
    building.sort(key=lambda t: -(sd[t][2] or 0))
    leaving = [t for t in held if sd[t][2] is not None and sd[t][2] <= -40 and (sd[t][0] or 0) >= 2]
    leaving.sort(key=lambda t: sd[t][2])
    block("Crowded shorts the funds own (10%+ of shares out, or 8+ days to cover)", crowded[:150])
    block("Bears building (short shares up 50%+ in three months)", building[:100])
    block("Bears leaving (short shares down 40%+ in three months)", leaving[:100])
    ws.freeze_panes = "A4"
    autosize(ws)
    ws.column_dimensions["J"].width = 34
    ws.column_dimensions["K"].width = 30

def sheet_track_records(wb, conn):
    """How each manager's new buys have done since its 13F made them public
    (track_records.py), and last quarter's new buys by the proven ones."""
    tr = track_records(conn)
    if not tr:
        return
    from fund_moves import short_fund, quarter_moves
    import statistics
    style = dict(conn.execute("SELECT fund, macro_style FROM fund_style"))
    # the yardstick: every fund's mature new buys together
    allx = [x for (x,) in conn.execute("""SELECT excess FROM new_buy_returns
        WHERE julianday('now') - julianday(filed) >= 90""")]
    base = (f" All funds together: {100.0 * sum(x > 0 for x in allx) / len(allx):.0f}% of {len(allx):,} new buys "
            f"beat the S&P 500, median {statistics.median(allx):+.1f} pts — the index was led by its largest "
            f"stocks, so read a fund against this, not against zero." if allx else "")
    ws = wb.create_sheet("Manager Track Records")
    ws.sheet_view.showGridLines = False
    write_title(ws, "Manager Track Records — how each fund's new buys did after its 13F made them public",
                "A new buy = a position of 0.5%+ of the 13F book not held the quarter before (IPOs, spin-offs, "
                "renamed companies and partial filings left out). Measured from the filing date — the first day you "
                "could have copied it — to the latest close (a stock taken over or delisted: to its last close), "
                "against the S&P 500 (SPY) over the same days; price moves only, split-adjusted, no dividends on "
                "either side. Quarters filed 90+ days ago count; the latest is shown apart as too early to judge. "
                "Big bets = 3%+ of the book. Funds with 5+ new buys, best median first. Common sense, not a model: "
                "past hit rates are context, not a forecast." + base, 14)
    hdr = ["Fund", "Style", "New Buys", "Beat S&P %", "Median vs S&P", "Average vs S&P", "Big Bets", "Big Bets Beat %",
           "Big Bets Median", "Best", "Worst", "Latest Qtr Buys", "Latest Qtr Median", "Quarters"]
    def fund_rows(lo, hi):
        rs = [r for r in tr.values() if lo <= (r["n"] or 0) <= hi]
        rs.sort(key=lambda r: (-(r["med_excess"] if r["med_excess"] is not None else -999), -(r["n"] or 0)))
        return [[short_fund(r["fund"]), style.get(r["fund"], ""), r["n"], r["beat_pct"], r["med_excess"],
                 r["avg_excess"], r["n_big"] or "", r["big_beat_pct"] if r["n_big"] else "",
                 r["big_med_excess"] if r["n_big"] else "", r["best"], r["worst"], r["recent_n"] or "",
                 r["recent_med_excess"] if r["recent_n"] else "", f"{r['first_period']} to {r['last_period']}"]
                for r in rs]
    row = 4
    # ten or more measured buys make a record; five to nine are shown apart,
    # where one lucky or unlucky pick still moves the median
    for title, lo, hi in (("Funds with 10+ measured new buys, best median first", 10, 10 ** 6),
                          ("Thinner records: 5-9 measured new buys (one pick still moves the median)", 5, 9)):
        out = fund_rows(lo, hi)
        write_section_heading(ws, row, f"{title} — {len(out)}", 14)
        write_table_header(ws, row + 1, hdr)
        write_table_rows(ws, out, row + 2, ticker_col=None)
        first = row + 2
        if out:
            color_directional(ws, first, first + len(out) - 1, [5, 9], higher_is_better=True)
        for r_ in range(first, first + len(out)):
            ws.cell(row=r_, column=4).number_format = '0"%"'
            ws.cell(row=r_, column=8).number_format = '0"%"'
            for col in (5, 6, 9, 13):
                ws.cell(row=r_, column=col).number_format = '+0.0;-0.0'
        row = first + len(out) + 1
    # last quarter's new buys by managers with a record of beating the market
    proven = {f for f, r in tr.items() if (r["n"] or 0) >= 10 and (r["beat_pct"] or 0) >= 60 and (r["med_excess"] or 0) > 0}
    mv, _ = quarter_moves(conn)
    picks = [m for m in mv if m["kind"] in ("new", "add") and m["fund"] in proven and not m["listing"]]
    picks.sort(key=lambda m: -m["cw"])
    write_section_heading(ws, row, f"Last quarter's buys by managers whose new buys beat the S&P 500 60%+ of the time "
                                   f"(10+ buys, positive median) — {len(picks)}", 14)
    row += 1
    write_table_header(ws, row, ["Ticker", "Buyer", "Move", "% of Book", "Buyer Beat %", "Buyer Median", "Name"])
    row += 1
    name = {r[0]: r[1] for r in conn.execute("""SELECT us.ticker, COALESCE(y.long_name, us.name)
        FROM unified_signal us LEFT JOIN ticker_yf y ON y.ticker = us.ticker""")}
    out = [[m["ticker"], short_fund(m["fund"]), m["label"], round(m["cw"], 1), tr[m["fund"]]["beat_pct"],
            tr[m["fund"]]["med_excess"], name.get(m["ticker"]) or ""] for m in picks[:200]]
    write_table_rows(ws, out, row)
    for r_ in range(row, row + len(out)):
        ws.cell(row=r_, column=4).number_format = NUMFMT_PCT
        ws.cell(row=r_, column=5).number_format = '0"%"'
        ws.cell(row=r_, column=6).number_format = '+0.0;-0.0'
    ws.freeze_panes = "B4"
    autosize(ws)
    ws.column_dimensions["A"].width = 36
    ws.column_dimensions["B"].width = 30

def sheet_industries(wb, conn, per_industry=30):
    """The industry lens (FMP's industry designations): an index of every
    industry the funds hold, ranked by last quarter's net buying, each linked
    to its section in Industry Detail — the names, who holds them, who bought
    and who sold them last quarter."""
    from industry_view import IndustryData, is_financial
    from fund_moves import latest_due_quarter
    d = IndustryData(conn)
    q = latest_due_quarter()
    by_ind = d.names_by_industry()
    idx = wb.create_sheet("Industry Index")
    det = wb.create_sheet("Industry Detail")
    for ws in (idx, det):
        ws.sheet_view.showGridLines = False
    # ---- detail first: its section rows are the index's link targets ----
    write_title(det, "Industry Detail — each industry's names: who holds them, who bought and who sold",
                f"FMP industries A–Z. Per industry, the operating common stocks a tracked fund holds (13F, one vote per "
                f"filing; N-PORT books) or moved in the {q} quarter, by conviction: weighted holders, the largest "
                f"position, last quarter's net buying and N-PORT managers. Up to {per_industry} names each; the rest "
                f"are in All Positions (filter its Industry column). Financials carry P/TB and ROE, the rest FCF yield.",
                17)
    hdr = ["Ticker", "Holders", "Max % Book", "Held By", "Last Qtr", "Net Pts", "Who Bought", "Who Sold",
           "N-PORT Mgrs", "Styles", "3M Chg %", "Mcap", "ROE %", "FCF Yield %", "Rev Gr %", "Name", "Business"]
    row, target, summary = 4, {}, {}
    for ind in sorted(by_ind, key=str.lower):
        names = by_ind[ind]
        sm = d.industry_summary(ind, names)
        summary[ind] = sm
        target[ind] = row
        shown = names[:per_industry]
        write_section_heading(det, row,
            f"{ind} — {len(names)} names held · {sm['managers']} managers · last quarter net "
            f"{sm['net']:+.1f} pts ({sm['buyers']} funds buying, {sm['sellers']} selling)"
            + (f" · top {len(shown)} of {len(names)} shown" if len(names) > len(shown) else ""), 17)
        row += 1
        write_table_header(det, row, hdr)
        row += 1
        out = []
        for t in shown:
            f = d.facts.get(t) or {}
            mv = d.moves.get(t) or {}
            ind_, bus = desc_for(conn, t)
            fin = is_financial(ind)
            out.append([t, _r1(f.get("wtd")), _r1((d.holders.get(t) or [(None,)])[0][0]), d.held_by(t),
                        (f"+{len({m['fund'] for m in mv.get('buy', [])})} / -{len({m['fund'] for m in mv.get('sell', [])})}"
                         if mv else ""),
                        round(mv["net"], 1) if mv else "", d.who(mv.get("buy", [])), d.who(mv.get("sell", [])),
                        len(d.nport.get(t, ())) or "", d.styles(t), _r0(f.get("mom")), f.get("mcap") or "",
                        _pct(f.get("roe")), "" if fin else _pct(f.get("fcf")), _pct(f.get("growth")),
                        f.get("name") or "", bus])
        write_table_rows(det, out, row)
        color_directional(det, row, row + len(out) - 1, [6, 11], higher_is_better=True)
        for ridx in range(row, row + len(out)):
            det.cell(row=ridx, column=2).number_format = '0.0'
            det.cell(row=ridx, column=3).number_format = NUMFMT_PCT
            det.cell(row=ridx, column=6).number_format = '0.0'
            det.cell(row=ridx, column=11).number_format = '0"%"'
            det.cell(row=ridx, column=12).number_format = NUMFMT_MCAP
            for col in (13, 14, 15):
                det.cell(row=ridx, column=col).number_format = '0.0"%"'
        row += len(out) + 2
    det.freeze_panes = "B4"
    autosize(det)
    det.column_dimensions["A"].width = 9
    for col, w in (("D", 46), ("G", 50), ("H", 50), ("J", 34), ("P", 30), ("Q", 70)):
        det.column_dimensions[col].width = w

    # ---- the index ----
    write_title(idx, "Industry Index — where the funds are, and where they moved last quarter",
                f"Every FMP industry the tracked funds hold (operating common stocks; SPACs left out), ranked by net "
                f"buying in the {q} quarter: the % of book bought minus sold across all funds (capped at 10 per "
                f"position, weighted by focus; the Revealed Preference rules). Managers = distinct 13F filers plus "
                f"N-PORT managers holding any of its names. Click an industry for its names in Industry Detail. "
                f"Medians are across the industry's held names.", 16)
    ih = ["Industry", "Names", "Managers", "$B Held (13F)", "Net Pts", "Buyers", "Sellers", "Bought Most",
          "Sold Most", "Top Names (conviction)", "Most-Exposed Styles", "Median P/E", "Median EV/EBITDA",
          "Median P/TB", "Median ROE %", "Median 3M %"]
    write_table_header(idx, 4, ih)
    order = sorted(summary, key=lambda i: (-summary[i]["net"], -summary[i]["managers"]))
    out = []
    for ind in order:
        sm = summary[ind]
        out.append([ind, sm["names"], sm["managers"], round(sm["held_m"] / 1e3, 2) if sm["held_m"] else "",
                    round(sm["net"], 1), sm["buyers"], sm["sellers"], sm["bought"], sm["sold"], sm["top"],
                    sm["styles"], _r1(sm["pe"]), _r1(sm["ev"]), _r2(sm["ptb"]),
                    round(sm["roe"] * 100, 1) if sm["roe"] is not None else "", _r0(sm["mom"])])
    write_table_rows(idx, out, 5, ticker_col=None)
    color_directional(idx, 5, 4 + len(out), [5, 16], higher_is_better=True)
    link_font = Font(name=TNR, size=SIZE_BODY, color=BLACK, underline="single")
    for i, ind in enumerate(order):
        c = idx.cell(row=5 + i, column=1)
        c.hyperlink = f"#'Industry Detail'!A{target[ind]}"
        c.font = link_font
        idx.cell(row=5 + i, column=4).number_format = '0.00'
        idx.cell(row=5 + i, column=5).number_format = '0.0'
        idx.cell(row=5 + i, column=15).number_format = '0.0"%"'
        idx.cell(row=5 + i, column=16).number_format = '0"%"'
    idx.freeze_panes = "B5"
    idx.auto_filter.ref = f"A4:{get_column_letter(len(ih))}{4 + len(out)}"
    autosize(idx)
    for col, w in (("A", 40), ("H", 40), ("I", 40), ("J", 34), ("K", 60)):
        idx.column_dimensions[col].width = w

def _r0(v):
    return round(v) if isinstance(v, (int, float)) else ""

def _r1(v):
    return round(v, 1) if isinstance(v, (int, float)) else ""

def _r2(v):
    return round(v, 2) if isinstance(v, (int, float)) else ""

def _pct(v):
    """A ratio stored as a fraction (0.12) shown as a percentage (12.0)."""
    return round(v * 100, 1) if isinstance(v, (int, float)) else ""

def sheet_best_in_bucket(wb, conn, per_bucket=20):
    """Top names WITHIN each size bucket. The flat Top-100 is ~44% large-cap
    because raw scores favor names held by many funds; ranking within-bucket
    surfaces the best small/micro/mid ideas that the mega-caps otherwise bury.
    """
    ws = wb.create_sheet("Best in Bucket")
    ws.sheet_view.showGridLines = False
    write_title(ws, "Best in Bucket — top ideas within each size class",
                "Score is cross-sectionally biased toward large caps; this ranks the best names within nano/micro/small/mid/large/mega separately.",
                len(SIG_HDR))
    row = 4
    for bucket, label in [("nano", "Nano (<$50M)"), ("micro", "Micro ($50–300M)"),
                          ("small", "Small ($300M–2B)"), ("mid", "Mid ($2–10B)"),
                          ("large", "Large ($10–200B)"), ("mega", "Mega (>$200B)")]:
        write_section_heading(ws, row, label, len(SIG_HDR)); row += 1
        write_table_header(ws, row, SIG_HDR); row += 1
        rows = get_signal_rows(conn, where_extra=f"AND us.mcap_bucket='{bucket}'", limit=per_bucket)
        rows = [r for r in rows if r[0] not in ETFs and (bucket == "mega" or r[0] not in MEGA)]
        out = [signal_row_to_cells(r) for r in rows]
        write_table_rows(ws, out, row)
        for ridx in range(row, row + len(out)):
            format_signal_row(ws, ridx)
        row += len(out) + 2
    ws.freeze_panes = "B5"
    autosize(ws)
    ws.column_dimensions["A"].width = 8
    ws.column_dimensions[get_column_letter(len(SIG_HDR))].width = 80
    ws.column_dimensions[get_column_letter(len(SIG_HDR) - 1)].width = 24

def sheet_activist(wb, conn):
    ws = wb.create_sheet("Activist 10+")
    ws.sheet_view.showGridLines = False
    write_title(ws, "Activist Concentration",
                "SC 13D/G filings disclosing ≥10% stake. Type: 13D = ACTIVIST intent; 13G = PASSIVE holder. Filer shown. Ex-biotech, ex-ETF.", 13)
    hdr = ["Ticker","Type","Top Filer","Act %","Mcap","Bucket","13D #","13F #","pB Max","EV/EBITDA","P/B","Name","Sector"]
    write_table_header(ws, 4, hdr)
    rows = list(conn.execute("""
        SELECT us.ticker, us.mcap_m, us.mcap_bucket,
               us.activist_max_pct, us.activist_filings, us.smart_money_n,
               us.max_pct_book, us.ev_ebitda, us.pb_ratio, tm.name, tm.sic_description,
               (SELECT h.holder FROM holder_13d h WHERE h.subject_ticker=us.ticker
                  ORDER BY h.pct_class DESC LIMIT 1) AS top_filer,
               (SELECT h.form FROM holder_13d h WHERE h.subject_ticker=us.ticker
                  ORDER BY h.pct_class DESC LIMIT 1) AS top_form,
               (SELECT MAX(CASE WHEN h.form LIKE '%13D%' THEN 1 ELSE 0 END)
                  FROM holder_13d h WHERE h.subject_ticker=us.ticker) AS any_13d
        FROM unified_signal us
        LEFT JOIN ticker_meta tm ON tm.ticker = us.ticker
        WHERE us.activist_max_pct >= 10 AND us.sec_type='common'
        ORDER BY any_13d DESC, us.activist_max_pct DESC"""))
    out = []
    for r in rows:
        if r[0] in ETFs or r[0] in MEGA: continue
        if is_biotech(r[10]): continue
        # 13D anywhere = activist; else the top filer's form (13G = passive)
        typ = "13D activist" if r[13] else ("13G passive" if r[12] and "13G" in (r[12] or "") else "—")
        filer = re.sub(r"\s*\(.*$", "", (r[11] or "")).strip()
        out.append([r[0], typ, filer, round(r[3] or 0, 1),
                    r[1] or "", r[2] or "",
                    r[4] or 0, r[5] or 0, round(r[6] or 0, 1),
                    round(r[7], 1) if r[7] is not None else "",
                    round(r[8], 2) if r[8] is not None else "",
                    (r[9] or ""), (r[10] or "")])
    write_table_rows(ws, out, 5)
    for ridx in range(5, 5 + len(out)):
        ws.cell(row=ridx, column=4).number_format = NUMFMT_PCT
        ws.cell(row=ridx, column=5).number_format = NUMFMT_MCAP
        ws.cell(row=ridx, column=9).number_format = NUMFMT_PCT
        ws.cell(row=ridx, column=10).number_format = '0.0"x"'
        ws.cell(row=ridx, column=11).number_format = '0.00"x"'
    ws.freeze_panes = "B5"
    autosize(ws)
    ws.column_dimensions["A"].width = 8

def sheet_broker_radar(wb, conn):
    """Swap-desk share-count jumps — the pre-13D shadow-accumulation radar."""
    ws = wb.create_sheet("Broker Swap Radar")
    ws.sheet_view.showGridLines = False
    write_title(ws, "Broker Swap Radar — possible swap-hedge accumulation",
                "QoQ share-count jumps inside ONE swap-desk broker's 13F. An activist building via cash-settled swaps files nothing — the desk hedging the swap buys the physical and prints HERE first. "
                "Idio % = this desk's move vs all desks (high = idiosyncratic, low = index flow). Leads, not proof: ETF baskets and custody flows also move desks. Shadow = accumulation × idiosyncrasy × activist-context × cheapness.", 13)
    hdr = ["Ticker","Shadow","Broker","Δ Sh (M)","Δ % Out","Δ $M","Desk $M","Idio %","Mcap","Score","Disclosed Swap","Live Action","13D Momentum","144 Sale (contra)","13D (12mo)","Activist holders","Name"]
    write_table_header(ws, 4, hdr)
    rows = list(conn.execute("""SELECT ticker, shadow_score, broker, delta_sh_m,
               pct_out, delta_m, cur_m, idio_pct, mcap_m, score,
               live_action, d13_momo, recent_13d, activist_holders, name, disclosed_swap, f144_sale
        FROM broker_swap_radar ORDER BY shadow_score DESC"""))
    out = []
    for r in rows[:200]:
        out.append([r[0], round(r[1] or 0, 1),
                    r[2], r[3], r[4], r[5],
                    r[6], r[7], r[8] or "",
                    round(r[9], 0) if r[9] is not None else "",
                    (r[15] or ""), (r[10] or ""), (r[11] or ""),
                    (r[16] or ""), (r[12] or ""), (r[13] or ""),
                    (r[14] or "")])
    write_table_rows(ws, out, 5)
    for ridx in range(5, 5 + len(out)):
        ws.cell(row=ridx, column=4).number_format = '0.0'
        ws.cell(row=ridx, column=5).number_format = '0.00"%"'
        ws.cell(row=ridx, column=6).number_format = NUMFMT_M_TO_B
        ws.cell(row=ridx, column=7).number_format = NUMFMT_M_TO_B
        ws.cell(row=ridx, column=8).number_format = '0"%"'
        ws.cell(row=ridx, column=9).number_format = NUMFMT_MCAP
    ws.freeze_panes = "B5"
    autosize(ws)
    ws.column_dimensions["A"].width = 8

def sheet_latent_ownership(wb, conn):
    """Hidden economic control: warrants/converts/blockers/board rights/swaps
    named in 13D text — a 4.9% header can mask a far larger latent stake."""
    try:
        rows = list(conn.execute("""SELECT lo.ticker, lo.holder, lo.filed, lo.form,
                   lo.flags, lo.blocker_pct, lo.swap_counterparties, lo.n_features,
                   u.score, u.mcap_m
            FROM latent_ownership lo LEFT JOIN unified_signal u ON u.ticker = lo.ticker
            WHERE lo.n_features >= 1 ORDER BY
              (lo.swap_counterparties IS NOT NULL) DESC, lo.n_features DESC, lo.filed DESC"""))
    except sqlite3.OperationalError:
        return
    ws = wb.create_sheet("Latent Ownership")
    ws.sheet_view.showGridLines = False
    write_title(ws, "Latent Ownership — hidden economic control in 13D text",
                "Warrants, convertibles, ownership blockers (+ the % ceiling), board-designation rights, ROFRs and DISCLOSED swaps parsed from each holder's latest 13D/G. "
                "A small header % with a rich structure = large latent optionality or overhang. Swap rows (top) name a counterparty desk — cross-check the Broker Swap Radar.", 10)
    hdr = ["Ticker","Holder","Filed","Form","# Feat","Blocker %","Swap Cpty","Hidden Features","Score","Mcap","Name"]
    write_table_header(ws, 4, hdr)
    nm = {r[0]: r[1] for r in conn.execute("SELECT ticker, name FROM unified_signal")}
    out = []
    for r in rows[:160]:
        out.append([r[0] or "", (r[1] or ""), r[2], (r[3] or ""),
                    r[7], r[5] if r[5] else "", (r[6] or ""),
                    (r[4] or ""), round(r[8],0) if r[8] is not None else "",
                    r[9] or "", (nm.get(r[0]) or "")])
    write_table_rows(ws, out, 5)
    for ridx in range(5, 5 + len(out)):
        ws.cell(row=ridx, column=6).number_format = '0.00"%"'
        ws.cell(row=ridx, column=10).number_format = NUMFMT_MCAP
    ws.freeze_panes = "B5"; autosize(ws); ws.column_dimensions["A"].width = 8

# An insider purchase by a company, fund or holding vehicle (Volkswagen into
# Rivian, General Atlantic into Alkami, Cascade into Republic Services) is a
# strategic or sponsor decision, not an executive's personal conviction: the
# insider sheets name the buyers and keep the two apart.
_ENTITY_RE = re.compile(r"\b(INC|LLC|L\.?L\.?C|L\.?P|LTD|LIMITED|AG|S\.?A|N\.?V|CORP|CORPORATION|CO|HOLDINGS?|"
                        r"FUNDS?|PARTNERS|CAPITAL|GROUP|GENPAR|MANAGEMENT|INVESTMENTS?|PLC|B\.?V|GMBH|SE|ADVISORS|"
                        r"ADVISERS|VENTURES|FOUNDATION|ASSOCIATES|BANK|COMPANY|OPPORTUNITIES|MASTER)\b\.?", re.I)

def is_entity(owner):
    return bool(_ENTITY_RE.search(owner or ""))

def insider_buyers(conn, days):
    """{ticker: [(usd, owner, role, is_entity)]} — open-market buys over `days`,
    largest first, with the same sanity screens as the insider sheets."""
    out = {}
    for tk, owner, role, usd in conn.execute(f"""
            SELECT f.ticker, COALESCE(NULLIF(f.owner, ''), f.accession), MAX(f.role), SUM(f.shares * f.price)
            FROM form4_transactions f
            WHERE f.code = 'P' AND f.acquired = 1 AND f.price IS NOT NULL
              AND f.trans_date >= date('now', '-{int(days)} days')
              AND NOT EXISTS (SELECT 1 FROM ticker_yf y WHERE y.ticker = f.ticker
                  AND ((y.mcap_m > 0 AND f.shares * f.price / 1e6 > y.mcap_m)
                    OR (y.price > 0 AND (f.price > y.price * 5 OR f.price < y.price * 0.10))))
            GROUP BY f.ticker, 2"""):
        out.setdefault(tk, []).append((usd or 0.0, owner, role or "", is_entity(owner)))
    for v in out.values():
        v.sort(key=lambda x: -x[0])
    return out

def fmt_buyers(lst, k=3):
    """'COHEN RYAN (CEO) $40.1M; ...; +2 more' — all of them up to k."""
    parts = [f"{o} ({r + ', ' if r else ''}{'entity' if e else 'person'}) ${u / 1e6:,.2f}M"
             for u, o, r, e in lst[:k]]
    return "; ".join(parts) + (f"; +{len(lst) - k} more" if len(lst) > k else "")

def sheet_insider_f4(wb, conn):
    """Insider buying ranked by RECENCY-weighted total. ≤30d buys shown separately."""
    ws = wb.create_sheet("Insider F4 Buys")
    ws.sheet_view.showGridLines = False
    write_title(ws, "Form 4 Insider Buying — recency weighted",
                "Open-market P-code buys over 180 days. ≤30d weight 1.0; 31–60 d 0.6; 61–180 d 0.3. Sorted by "
                "recency-weighted dollars. Persons $M vs Entities $M splits executives' and directors' own money "
                "from buys by companies, funds and holding vehicles (a strategic or sponsor decision, e.g. "
                "Volkswagen into Rivian); Top Buyers names them.", 16)
    hdr = ["Ticker","Weighted $M","≤30d $M","31-60 $M","61-180 $M","# Buyers","Persons $M","Entities $M",
           "Top Buyers","Avg Px","Mcap","Bucket","13F","EV/EBITDA","P/B","Name"]
    buyers = insider_buyers(conn, 180)
    write_table_header(ws, 4, hdr)
    rows = list(conn.execute("""
        SELECT f.ticker,
            SUM(CASE WHEN julianday('now')-julianday(f.trans_date) <= 30  THEN f.shares*f.price ELSE 0 END)/1e6 AS d_30,
            SUM(CASE WHEN julianday('now')-julianday(f.trans_date) BETWEEN 31 AND 60  THEN f.shares*f.price ELSE 0 END)/1e6 AS d_60,
            SUM(CASE WHEN julianday('now')-julianday(f.trans_date) > 60   THEN f.shares*f.price ELSE 0 END)/1e6 AS d_180,
            COUNT(DISTINCT f.owner), AVG(f.price),
            us.mcap_m, us.mcap_bucket, us.smart_money_n,
            us.ev_ebitda, us.pb_ratio,
            tm.name
        FROM form4_transactions f
        LEFT JOIN ticker_meta tm ON tm.ticker = f.ticker
        LEFT JOIN unified_signal us ON us.ticker = f.ticker
        WHERE f.code='P' AND f.acquired=1 AND f.price IS NOT NULL
          AND f.trans_date >= date('now','-180 days')
                  AND COALESCE(us.sec_type,'common')='common'
          AND NOT EXISTS (SELECT 1 FROM ticker_yf y WHERE y.ticker = f.ticker
              AND ((y.mcap_m > 0 AND f.shares*f.price/1e6 > y.mcap_m)
                OR (y.price > 0 AND (f.price > y.price*5 OR f.price < y.price*0.10))))
          AND NOT (f.shares*f.price/1e6 > 250
                   AND NOT EXISTS (SELECT 1 FROM ticker_yf y2 WHERE y2.ticker = f.ticker))
        GROUP BY f.ticker
        HAVING (d_30*1.0 + d_60*0.6 + d_180*0.3) >= 0.1
        ORDER BY (d_30*1.0 + d_60*0.6 + d_180*0.3) DESC"""))
    out = []
    for r in rows:
        d30, d60, d180 = r[1] or 0, r[2] or 0, r[3] or 0
        weighted = d30 * 1.0 + d60 * 0.6 + d180 * 0.3
        bl = buyers.get(r[0], [])
        person = sum(u for u, o, rl, e in bl if not e) / 1e6
        entity = sum(u for u, o, rl, e in bl if e) / 1e6
        out.append([r[0], round(weighted, 1),
                    round(d30, 1) if d30 else "",
                    round(d60, 1) if d60 else "",
                    round(d180, 1) if d180 else "",
                    r[4], round(person, 2) if person else "", round(entity, 2) if entity else "",
                    fmt_buyers(bl), round(r[5] or 0, 2),
                    r[6] or "", r[7] or "unknown",
                    r[8] or 0,
                    round(r[9], 1) if r[9] is not None else "",
                    round(r[10], 2) if r[10] is not None else "",
                    (r[11] or "")])
    write_table_rows(ws, out, 5)
    for ridx in range(5, 5 + len(out)):
        for col in (2, 3, 4, 5, 7, 8):
            ws.cell(row=ridx, column=col).number_format = NUMFMT_M_TO_B
        ws.cell(row=ridx, column=10).number_format = NUMFMT_USD2
        ws.cell(row=ridx, column=11).number_format = NUMFMT_MCAP
        ws.cell(row=ridx, column=14).number_format = '0.0"x"'
        ws.cell(row=ridx, column=15).number_format = '0.00"x"'
    ws.freeze_panes = "B5"
    autosize(ws)
    ws.column_dimensions["A"].width = 8
    ws.column_dimensions["I"].width = 70

def sheet_insider_recent(wb, conn):
    """Pure recent (≤30d) insider buying — most actionable."""
    ws = wb.create_sheet("Insider Buys ≤30d")
    ws.sheet_view.showGridLines = False
    write_title(ws, "Recent Insider Buying — last 30 days only",
                "Buys reported in the last 30 days. C-Suite = a CEO/CFO/COO/President/Chair bought (personal-cash conviction beats a passive 10%-owner). Net nets out any sells. Top Buyers names them: 'person' = an individual's own money, 'entity' = a company, fund or holding vehicle.", 17)
    hdr = ["Ticker","Buy $M","Sell $M","Net $M","# Buyers","C-Suite","Top Buyers","Days Ago","Avg Px","Mcap","Bucket",
           "13F","S3","S4","Act %","EV/EBITDA","Name"]
    write_table_header(ws, 4, hdr)
    buyers = insider_buyers(conn, 30)
    rows = list(conn.execute("""
        SELECT f.ticker, SUM(f.shares*f.price)/1e6 AS dollars_m,
               COUNT(DISTINCT CASE WHEN COALESCE(f.owner,'')='' THEN f.accession ELSE f.owner END), MAX(f.trans_date),
               AVG(f.price),
               us.mcap_m, us.mcap_bucket,
               us.smart_money_n, us.s3_new, us.s4_add, us.activist_max_pct,
               us.ev_ebitda, us.pb_ratio,
               tm.name,
               MAX(CASE WHEN f.role LIKE '%CEO%' OR f.role LIKE '%Chief Exec%'
                        OR f.role LIKE '%CFO%' OR f.role LIKE '%Chief Fin%'
                        OR f.role LIKE '%COO%' OR f.role LIKE '%President%'
                        OR f.role LIKE '%Chair%' THEN 1 ELSE 0 END) AS csuite,
               CAST(julianday('now') - julianday(MAX(f.trans_date)) AS INT) AS days_ago,
               (SELECT COALESCE(SUM(s.shares*s.price),0)/1e6 FROM form4_transactions s
                  WHERE s.ticker=f.ticker AND s.code='S' AND s.trans_date >= date('now','-30 days')
                    AND s.price IS NOT NULL AND s.price < 200000) AS sell_m
        FROM form4_transactions f
        LEFT JOIN ticker_meta tm ON tm.ticker = f.ticker
        LEFT JOIN unified_signal us ON us.ticker = f.ticker
        WHERE f.code='P' AND f.acquired=1 AND f.price IS NOT NULL
          AND f.trans_date >= date('now','-30 days')
                  AND COALESCE(us.sec_type,'common')='common'
          AND NOT EXISTS (SELECT 1 FROM ticker_yf y WHERE y.ticker = f.ticker
              AND ((y.mcap_m > 0 AND f.shares*f.price/1e6 > y.mcap_m)
                OR (y.price > 0 AND (f.price > y.price*5 OR f.price < y.price*0.10))))
          AND NOT (f.shares*f.price/1e6 > 250
                   AND NOT EXISTS (SELECT 1 FROM ticker_yf y2 WHERE y2.ticker = f.ticker))
        GROUP BY f.ticker
        HAVING dollars_m >= 0.05
        ORDER BY csuite DESC, dollars_m DESC"""))
    out = []
    for r in rows:
        buy, sell = r[1] or 0, r[16] or 0
        out.append([r[0], round(buy, 2), round(sell, 2) if sell else "",
                    round(buy - sell, 2), r[2],
                    "CEO/CFO" if r[14] else "", fmt_buyers(buyers.get(r[0], [])), r[15],
                    round(r[4] or 0, 2),
                    r[5] or "", r[6] or "unknown",
                    r[7] or 0, r[8] or 0, r[9] or 0,
                    round(r[10] or 0, 1),
                    round(r[11], 1) if r[11] is not None else "",
                    (r[13] or "")])
    write_table_rows(ws, out, 5)
    for ridx in range(5, 5 + len(out)):
        ws.cell(row=ridx, column=2).number_format = NUMFMT_M_TO_B
        ws.cell(row=ridx, column=3).number_format = NUMFMT_M_TO_B
        ws.cell(row=ridx, column=4).number_format = NUMFMT_M_TO_B
        ws.cell(row=ridx, column=9).number_format = NUMFMT_USD2    # Avg Px
        ws.cell(row=ridx, column=10).number_format = NUMFMT_MCAP   # Mcap
        ws.cell(row=ridx, column=15).number_format = NUMFMT_PCT    # Act %
        ws.cell(row=ridx, column=16).number_format = '0.0"x"'      # EV/EBITDA
    # colour is data: Net $ (buy − sell) — lapis net buying, crimson net selling
    color_directional(ws, 5, 4 + len(out), 4, higher_is_better=True)
    ws.freeze_panes = "B5"
    if out:
        ws.auto_filter.ref = f"A4:Q{4 + len(out)}"
    autosize(ws)
    ws.column_dimensions["A"].width = 8
    ws.column_dimensions["G"].width = 70

def sheet_clusters(wb, conn):
    ws = wb.create_sheet("Insider Clusters")
    ws.sheet_view.showGridLines = False
    write_title(ws, "Live Insider Clusters",
                "Insider buy clusters (≤180-day window) — multiple insiders, same ticker. Days-Ago from the window end: a 3-day-old cluster is far stronger than a 29-day-old one. Buyer Type: 'entity' = the largest buyer is a company, fund or holding vehicle (a strategic or sponsor buy), 'person' = an individual.", 13)
    hdr = ["Ticker","Trigger","Days Ago","Window End","# Insiders","Cluster $M","Avg Px","Top Buyer","Buyer Type","Mcap","Bucket","EV/EBITDA","P/B"]
    write_table_header(ws, 4, hdr)
    rows = list(conn.execute("""
        SELECT ic.ticker, ic.trigger, ic.window_end, ic.n_insiders, ic.total_usd_m,
               ic.avg_price, ic.top_buyer, us.mcap_m, us.mcap_bucket,
               us.ev_ebitda, us.pb_ratio,
               CAST(julianday('now') - julianday(ic.window_end) AS INT) AS days_ago
        FROM insider_clusters ic
        LEFT JOIN ticker_meta tm ON tm.ticker = ic.ticker
        LEFT JOIN unified_signal us ON us.ticker = ic.ticker
        WHERE DATE(ic.window_end) >= DATE('now', '-180 days')
          AND COALESCE(us.sec_type,'common')='common'
          AND ic.n_insiders >= 2
        ORDER BY ic.total_usd_m DESC"""))
    out = [[r[0], r[1], r[11], r[2], r[3], round(r[4] or 0, 2), round(r[5] or 0, 2),
            r[6] if r[6] else "", ("entity" if is_entity(r[6]) else "person") if r[6] else "",
            r[7] or "", r[8] or "unknown",
            round(r[9], 1) if r[9] is not None else "",
            round(r[10], 2) if r[10] is not None else ""] for r in rows]
    write_table_rows(ws, out, 5)
    for ridx in range(5, 5 + len(out)):
        ws.cell(row=ridx, column=6).number_format = NUMFMT_M_TO_B
        ws.cell(row=ridx, column=7).number_format = NUMFMT_USD2
        ws.cell(row=ridx, column=10).number_format = NUMFMT_MCAP
        ws.cell(row=ridx, column=12).number_format = '0.0"x"'
        ws.cell(row=ridx, column=13).number_format = '0.00"x"'
    ws.freeze_panes = "B5"
    autosize(ws)
    ws.column_dimensions["A"].width = 8

def sheet_congress(wb, conn):
    """Congressional trading (STOCK Act reports via FMP) read like insider
    buying: several members independently buying one name is the signal; own
    account / option purchases show more conviction than a spouse's managed
    account; a filing past the 45-day deadline is flagged."""
    try:
        conn.execute("SELECT 1 FROM congress_trades LIMIT 1")
    except sqlite3.OperationalError:
        return
    ws = wb.create_sheet("Congress Trades")
    ws.sheet_view.showGridLines = False
    write_title(ws, "Congress Trades — members of Congress buying and selling",
                "STOCK Act disclosures, last 180 days by trade date (stocks and options; funds, bonds excluded). "
                "# Buying = distinct members. Est $ = sum of range midpoints (disclosures give ranges only). "
                "Own acct = Self/Joint (not a spouse's or child's account). Late = filed after the 45-day deadline. "
                "Selective = buyers who traded <40 names in the window; * marks prolific traders (managed-account style, "
                "e.g. 200+ names) whose buys say little about any one stock. Sorted by selective buyers.", 18)
    PROLIFIC = 40
    breadth = {m: n for m, n in conn.execute("""SELECT member_id, COUNT(DISTINCT ticker) FROM congress_trades
        WHERE trans_date >= date('now', '-180 days') GROUP BY member_id""")}
    prolific = {m for m, n in breadth.items() if n >= PROLIFIC}
    hdr = ["Ticker", "Selective Buyers", "# Buying", "# Selling", "Est Buy $M", "Est Sell $M", "Own-Acct Buys",
           "Option Buys", "Latest Buy", "Days Ago", "Late Filings", "Buyers", "Score", "13F",
           "Insider Clu", "Mcap", "Bucket", "Name"]
    write_table_header(ws, 4, hdr)
    rows = conn.execute("""
        WITH w AS (SELECT * FROM congress_trades
                   WHERE trans_date >= date('now', '-180 days') AND ticker IS NOT NULL
                     AND asset_type IN ('Stock', 'Stock Option')),
             mid AS (SELECT *, (COALESCE(amount_lo, 0) + COALESCE(amount_hi, amount_lo, 0)) / 2.0 AS mid_usd,
                            CAST(julianday(disclosure_date) - julianday(trans_date) AS INT) AS lag
                     FROM w)
        SELECT m.ticker,
               COUNT(DISTINCT CASE WHEN m.type = 'Purchase' THEN m.member_id END) AS n_buy,
               COUNT(DISTINCT CASE WHEN m.type LIKE 'Sale%' THEN m.member_id END) AS n_sell,
               SUM(CASE WHEN m.type = 'Purchase' THEN m.mid_usd ELSE 0 END) / 1e6 AS buy_m,
               SUM(CASE WHEN m.type LIKE 'Sale%' THEN m.mid_usd ELSE 0 END) / 1e6 AS sell_m,
               SUM(CASE WHEN m.type = 'Purchase' AND m.owner IN ('Self', 'Joint') THEN 1 ELSE 0 END) AS own_buys,
               SUM(CASE WHEN m.type = 'Purchase' AND m.asset_type = 'Stock Option' THEN 1 ELSE 0 END) AS opt_buys,
               MAX(CASE WHEN m.type = 'Purchase' THEN m.trans_date END) AS last_buy,
               SUM(CASE WHEN m.lag > 45 THEN 1 ELSE 0 END) AS late,
               GROUP_CONCAT(DISTINCT CASE WHEN m.type = 'Purchase' THEN m.member_id || '|' || m.member END) AS buyers,
               us.score, us.smart_money_n, us.insider_n, us.mcap_m, us.mcap_bucket, us.name, us.sec_type
        FROM mid m LEFT JOIN unified_signal us ON us.ticker = m.ticker
        GROUP BY m.ticker
        HAVING n_buy >= 1 AND COALESCE(us.sec_type, 'common') = 'common'""").fetchall()
    out = []
    for r in rows:
        if r[0] in ETFs:
            continue
        days = conn.execute("SELECT CAST(julianday('now') - julianday(?) AS INT)", (r[7],)).fetchone()[0] if r[7] else None
        buyers = {}
        for item in (r[9] or "").split(","):
            mid, _, nm = item.partition("|")
            if nm:
                buyers[mid] = nm + ("*" if mid in prolific else "")
        selective = sum(1 for mid in buyers if mid not in prolific)
        out.append([r[0], selective, r[1], r[2], round(r[3] or 0, 2), round(r[4] or 0, 2) if r[4] else "",
                    r[5] or 0, r[6] or 0, r[7] or "", days if days is not None else "", r[8] or 0,
                    ", ".join(sorted(buyers.values())), round(r[10], 1) if r[10] is not None else "",
                    round(r[11] or 0, 1), r[12] or 0, r[13] or "", r[14] or "unknown", r[15] or ""])
    out.sort(key=lambda x: (-x[1], -x[2], -(x[4] or 0)))
    write_table_rows(ws, out, 5)
    for ridx in range(5, 5 + len(out)):
        ws.cell(row=ridx, column=5).number_format = NUMFMT_M_TO_B
        ws.cell(row=ridx, column=6).number_format = NUMFMT_M_TO_B
        ws.cell(row=ridx, column=16).number_format = NUMFMT_MCAP
    # the individual disclosures behind it: latest stock/option purchases
    r0 = 5 + len(out) + 2
    write_section_heading(ws, r0, "Latest purchase disclosures (newest first)", 12)
    hdr2 = ["Ticker", "Member", "Chamber", "District", "Owner", "Asset", "Amount",
            "Traded", "Disclosed", "Lag Days", "Company", "Filing"]
    write_table_header(ws, r0 + 1, hdr2)
    det = conn.execute("""SELECT ticker, member, chamber, district, owner, asset_type, amount_text,
            trans_date, disclosure_date,
            CAST(julianday(disclosure_date) - julianday(trans_date) AS INT), asset_desc, link
        FROM congress_trades
        WHERE type = 'Purchase' AND asset_type IN ('Stock', 'Stock Option') AND ticker IS NOT NULL
        ORDER BY disclosure_date DESC, trans_date DESC LIMIT 200""").fetchall()
    write_table_rows(ws, [list(d) for d in det], r0 + 2)
    ws.freeze_panes = "B5"
    autosize(ws)
    ws.column_dimensions["A"].width = 9

def sheet_unknown(wb, conn):
    ws = wb.create_sheet("Unknown Mcap")
    ws.sheet_view.showGridLines = False
    write_title(ws, "Unknown Market Cap",
                "Tickers with no market cap from FMP's profiles or SEC share counts: foreign lines FMP doesn't price, SPACs, warrants, defunct names.", 13)
    hdr = ["Ticker","Score","Bucket","13F","S1","S3","S4","Act %","pB Max","F4 $M","Name","Sector","Exch"]
    write_table_header(ws, 4, hdr)
    rows = list(conn.execute("""
        SELECT us.ticker, us.score, us.mcap_bucket, us.smart_money_n,
               us.s1_top, us.s3_new, us.s4_add, us.activist_max_pct, us.max_pct_book,
               us.form4_buy_usd_m, tm.name, tm.sic_description, tm.exchange
        FROM unified_signal us
        LEFT JOIN ticker_meta tm ON tm.ticker = us.ticker
        WHERE us.mcap_bucket = 'unknown' AND us.sec_type='common'
          AND COALESCE(tm.name, us.name) IS NOT NULL
        ORDER BY us.score DESC LIMIT 200"""))
    out = []
    for r in rows:
        if r[0] in ETFs: continue
        out.append([r[0], round(r[1] or 0, 1), r[2] or "",
                    r[3] or 0, r[4] or 0, r[5] or 0, r[6] or 0,
                    round(r[7] or 0, 1), round(r[8] or 0, 1),
                    round(r[9] or 0, 1) if r[9] else "",
                    (r[10] or ""), (r[11] or ""), (r[12] or "")])
    write_table_rows(ws, out, 5)
    for ridx in range(5, 5 + len(out)):
        ws.cell(row=ridx, column=8).number_format = NUMFMT_PCT
        ws.cell(row=ridx, column=9).number_format = NUMFMT_PCT
    ws.freeze_panes = "B5"
    autosize(ws)
    ws.column_dimensions["A"].width = 8

def sheet_fund_coverage(wb, conn):
    """Every roster fund in exactly one category, the 13F ones split the way
    the README counts them (current / older / dormant / empty), so the numbers
    reconcile across the book."""
    from fund_moves import latest_due_quarter, book_info
    ws = wb.create_sheet("Fund Coverage")
    ws.sheet_view.showGridLines = False
    q = latest_due_quarter()
    bi = book_info(conn)
    dormant = {r[0] for r in conn.execute("SELECT DISTINCT fund FROM fund_13f_dormant")}
    empty = {r[0] for r in conn.execute("""SELECT fund FROM fund_13f_state
        WHERE n_holdings = 0 AND last_accession IS NOT NULL""")}
    has_fp = {r[0] for r in conn.execute("SELECT DISTINCT fund FROM fund_positions")}
    has_13d = {r[0] for r in conn.execute("SELECT DISTINCT holder FROM holder_13d")}
    status = dict(conn.execute("SELECT fund, status FROM fund_resolution_state"))
    cats = {}
    for (fund,) in conn.execute("SELECT fund FROM fund_meta"):
        d = bi.get(fund) or {}
        st = status.get(fund) or ""
        if d.get("n") and d.get("period") == q:
            c = (1, f"13F book for the {q} quarter (current)")
        elif d.get("n"):
            c = (2, "13F book for an earlier quarter (late filer)")
        elif fund in dormant:
            c = (3, "13F book dormant: no filing in 200+ days (archived, not counted)")
        elif fund in empty:
            c = (4, "Latest 13F filed with no holdings")
        elif fund in has_fp and fund in has_13d:
            c = (5, "Research notes + 13D/G (no 13F)")
        elif fund in has_fp:
            c = (6, "Research notes only (no 13F)")
        elif fund in has_13d:
            c = (7, "13D/G only (foreign activists)")
        elif "non_filer" in st:
            c = (8, "Foreign non-filer, no public holdings")
        elif st == "below_13f_threshold":
            c = (9, "Below the $100M 13F threshold")
        elif st == "non_equity_strategy":
            c = (10, "CTA / options (no equity to track)")
        elif st == "historical_13f_only":
            c = (11, "Historical 13F only")
        elif st == "individual":
            c = (12, "Individual (not a fund)")
        elif st == "meta_rollup":
            c = (13, "Group heading (not a fund)")
        elif st == "private_office":
            c = (14, "Private office (no disclosure)")
        else:
            c = (15, "Other / unresolved")
        cats[c] = cats.get(c, 0) + 1
    n_fund = sum(cats.values())
    n_data = sum(v for (k, _), v in cats.items() if k in (1, 2, 5, 6, 7))
    write_title(ws, "Fund Coverage",
                f"{n_data} of {n_fund} roster funds ({n_data * 100 // n_fund}%) contribute data now: a live 13F book, "
                f"research notes or 13D/Gs. The rest are documented gaps. Each fund sits in exactly one row.", 3)
    hdr = ["Category", "Funds", "Pct"]
    write_table_header(ws, 4, hdr)
    out = [[f"{k}. {label}", v, round(v * 100 / n_fund, 1)] for (k, label), v in sorted(cats.items())]
    write_table_rows(ws, out, 5)
    for ridx in range(5, 5 + len(out)):
        ws.cell(row=ridx, column=3).number_format = NUMFMT_PCT
    autosize(ws)
    ws.column_dimensions["A"].width = 62

def sheet_all_holdings_consolidated(wb, conn):
    """Union view across 13F, fund_positions, and holder_13d — EVERY disclosed
    position across the whole fund universe. Source column indicates origin.
    No per-fund cap and all fund_positions sections (1-4) are included, so no
    fund and no position is silently dropped (fits well within Excel's limit).
    """
    ws = wb.create_sheet("All Positions")
    ws.sheet_view.showGridLines = False
    hdr = ["Fund","Ticker","Source","Value $M","%Book","Section","Activist %","Mcap","Bucket","EV/EBITDA","P/B",
           "Industry","Style","Sub-Group","Issuer (as filed)"]
    write_table_header(ws, 4, hdr)
    # industry (FMP) and the fund's style on every row: "which banks do the
    # deep-value funds hold" is two filters
    ind = dict(conn.execute("SELECT ticker, industry FROM ticker_yf WHERE industry IS NOT NULL"))
    sty = {f: (m, g) for f, m, g in conn.execute("SELECT fund, macro_style, sub_group FROM fund_style")}
    # EVERY 13F line, mapped or not: ETF / fund lines carry no ticker on the
    # holdings (they stay out of stock signals by design) but are real
    # positions — shown with the CUSIP map's ticker and a fund label; lines no
    # source can map still appear under the filer's own issuer name.
    rows = list(conn.execute("""
        SELECT h.fund, COALESCE(h.ticker, cm.ticker) AS ticker,
               CASE WHEN h.ticker IS NULL AND cm.sec_type = 'etf' THEN '13F-HR (fund/ETF)'
                    WHEN COALESCE(h.ticker, cm.ticker) IS NULL THEN '13F-HR (unmapped)'
                    ELSE '13F-HR' END AS source,
               h.value_k/1000.0 AS value_m,
               h.pct_book, NULL AS section,
               NULL AS act_pct,
               us.mcap_m, us.mcap_bucket, us.ev_ebitda, us.pb_ratio, h.issuer
        FROM fund_13f_holdings h
        LEFT JOIN cusip_map cm ON cm.cusip = h.cusip
        LEFT JOIN unified_signal us ON us.ticker = h.ticker
        WHERE h.value_k > 0 OR h.shares > 0
        UNION ALL
        SELECT fp.fund, fp.ticker, 'XLSX' AS source,
               fp.dollar_m AS value_m,
               fp.pct_value AS pct_book,
               fp.section,
               us.activist_max_pct,
               us.mcap_m, us.mcap_bucket, us.ev_ebitda, us.pb_ratio, NULL
        FROM fund_positions fp
        LEFT JOIN unified_signal us ON us.ticker = fp.ticker
        WHERE fp.ticker IS NOT NULL
          AND fp.section IN (1,2,3,4)
        UNION ALL
        SELECT h.holder AS fund, h.subject_ticker AS ticker, 'SC 13D/G' AS source,
               NULL AS value_m,
               h.pct_class AS pct_book,
               NULL AS section,
               us.activist_max_pct,
               us.mcap_m, us.mcap_bucket, us.ev_ebitda, us.pb_ratio, h.subject_name
        FROM holder_13d h
        LEFT JOIN unified_signal us ON us.ticker = h.subject_ticker
        WHERE h.subject_ticker IS NOT NULL AND h.pct_class >= 5
        ORDER BY fund, value_m DESC
    """))
    # Show ALL rows (they fit well within Excel's ~1.05M limit). The prior version
    # capped at 6000 ordered by FUND NAME (dropping every fund after ~"P") AND
    # top-30 per fund AND excluded section-2 positions — silently hiding 45 funds
    # and ~65k positions. Now genuinely complete: every fund, every position.
    n_funds = len(set(r[0] for r in rows))
    CAP = 500000  # extreme-safety backstop only
    truncated = len(rows) > CAP
    if truncated:
        rows = rows[:CAP]
    write_title(ws, "All Fund Positions — consolidated view",
                f"Every disclosed position: 13F-HR + fund_positions (all sections) + 13D/G (≥5%). "
                f"{len(rows):,} rows across {n_funds} funds — complete, no per-fund cap. "
                f"ETF/fund and unmapped 13F lines included and labelled in Source. Industry (FMP), Style and "
                f"Sub-Group on every row: filter them together (e.g. Industry 'Banks - Regional' within Sub-Group "
                f"'Deep Value').", 15)
    out = []
    for r in rows:
        st = sty.get(r[0]) or ("", "")
        out.append([(r[0] or ""), r[1] or "", r[2],
                    round(r[3] or 0, 1) if r[3] else "",
                    round(r[4] or 0, 2),
                    r[5] or "",
                    round(r[6] or 0, 1) if r[6] else "",
                    r[7] or "", r[8] or "",
                    round(r[9], 1) if r[9] is not None else "",
                    round(r[10], 2) if r[10] is not None else "",
                    ind.get(r[1]) or "", st[0] or "", st[1] or "",
                    r[11] or ""])
    write_table_rows(ws, out, 5)
    for ridx in range(5, 5 + len(out)):
        ws.cell(row=ridx, column=4).number_format = NUMFMT_M_TO_B
        ws.cell(row=ridx, column=5).number_format = NUMFMT_PCT
        ws.cell(row=ridx, column=7).number_format = NUMFMT_PCT
        ws.cell(row=ridx, column=8).number_format = NUMFMT_MCAP
        ws.cell(row=ridx, column=10).number_format = '0.0"x"'
        ws.cell(row=ridx, column=11).number_format = '0.00"x"'
    ws.freeze_panes = "A5"
    if out:
        ws.auto_filter.ref = f"A4:{get_column_letter(len(hdr))}{4 + len(out)}"
    autosize(ws)

def sheet_all_funds(wb, conn):
    ws = wb.create_sheet("All Funds")
    ws.sheet_view.showGridLines = False
    from fund_moves import book_info
    bi = book_info(conn)
    dormant = {r[0] for r in conn.execute("SELECT DISTINCT fund FROM fund_13f_dormant")}
    write_title(ws, "Per-Fund Inventory",
                "Every roster fund with its data status in plain English (resolver code in brackets), the quarter its "
                "latest 13F covers, and its counts. Sorted by 13F holdings.", 8)
    hdr = ["Fund","Status","CIK","Book","13F #","13F $M","13D #","Pos Count"]
    write_table_header(ws, 4, hdr)
    rows = list(conn.execute("""
        SELECT fm.fund, fr.status, fr.best_cik,
               COALESCE(st.n_holdings, 0),
               COALESCE(st.total_value_k, 0) / 1e3,
               (SELECT COUNT(*) FROM holder_13d h WHERE h.holder = fm.fund),
               (SELECT COUNT(*) FROM fund_positions fp WHERE fp.fund = fm.fund)
        FROM fund_meta fm
        LEFT JOIN fund_resolution_state fr ON fr.fund = fm.fund
        LEFT JOIN fund_13f_state st ON st.fund = fm.fund
        ORDER BY st.n_holdings DESC NULLS LAST"""))
    out = []
    for r in rows:
        book = "dormant" if r[0] in dormant else ((bi.get(r[0]) or {}).get("period") or "")
        out.append([r[0], plain_status(r[1]), r[2] or "", book,
                    r[3], round(r[4] or 0), r[5], r[6]])
    write_table_rows(ws, out, 5)
    for ridx in range(5, 5 + len(out)):
        ws.cell(row=ridx, column=6).number_format = NUMFMT_M_TO_B   # 13F total $M
    ws.freeze_panes = "B5"
    autosize(ws)

def sheet_asymmetry(wb, conn):
    """MOST ASYMMETRIC setups: cheap valuation + smart money in below entry +
    catalyst + room to multiply. Downside protection × upside potential."""
    ws = wb.create_sheet("Asymmetry")
    ws.sheet_view.showGridLines = False
    write_title(ws, "Asymmetry — best risk/reward setups",
                "asymmetry = margin-of-safety (cheap EV/EBITDA + low P/B + below smart-money entry) × upside (conviction + activist/insider catalyst + small-cap room). Ranked desc.", 16)
    hdr = ["Ticker","Asym","Score","Mcap","Bucket","EV/EBITDA","P/B","P/E","pB Max","Act %","Entry","vs Entry %","Catalyst","Name","Industry","Business"]
    write_table_header(ws, 4, hdr)
    rows = list(conn.execute("""
        SELECT us.ticker, us.asymmetry_score, us.score, us.mcap_m, us.mcap_bucket,
               us.ev_ebitda, us.pb_ratio, us.pe_ttm, us.max_pct_book, us.activist_max_pct,
               us.entry_bucket, us.vs_entry_pct, us.cat8k_ma, us.cat8k_ctrl,
               us.insider_cluster_dollars_m, tm.name
        FROM unified_signal us
        LEFT JOIN ticker_meta tm ON tm.ticker = us.ticker
        WHERE us.asymmetry_score IS NOT NULL AND us.sec_type='common'
        ORDER BY us.asymmetry_score DESC LIMIT 150"""))
    out = []
    for r in rows:
        if r[0] in ETFs or r[0] in MEGA: continue
        eb = r[10] or ""
        eb_label = ("below" if eb=="BELOW_ENTRY" else "near" if eb=="NEAR_ENTRY"
                    else "above" if "ABOVE" in eb else "")
        cat = []
        if r[12]: cat.append("M&A")
        if r[13]: cat.append("CTRL")
        if r[14] and r[14] > 0: cat.append("clstr")
        d = desc_for(conn, r[0])
        out.append([r[0], round(r[1] or 0, 1), round(r[2] or 0, 1),
                    r[3] or "", r[4] or "",
                    round(r[5], 1) if r[5] is not None else "",
                    round(r[6], 2) if r[6] is not None else "",
                    round(r[7], 1) if r[7] is not None else "",
                    round(r[8] or 0, 1), round(r[9] or 0, 1),
                    eb_label, round(r[11] or 0, 1) if r[11] else "",
                    " ".join(cat), (r[15] or ""), d[0], d[1]])
        if len(out) >= 100: break
    write_table_rows(ws, out, 5)
    for ridx in range(5, 5+len(out)):
        ws.cell(row=ridx, column=4).number_format = NUMFMT_MCAP
        ws.cell(row=ridx, column=6).number_format = '0.0"x"'
        ws.cell(row=ridx, column=7).number_format = '0.00"x"'
        ws.cell(row=ridx, column=8).number_format = '0.0"x"'
        ws.cell(row=ridx, column=9).number_format = NUMFMT_PCT
        ws.cell(row=ridx, column=10).number_format = NUMFMT_PCT
        ws.cell(row=ridx, column=12).number_format = NUMFMT_PCT
    ws.freeze_panes = "B5"
    autosize(ws)
    ws.column_dimensions["A"].width = 8
    ws.column_dimensions[get_column_letter(15)].width = 24   # Industry
    ws.column_dimensions[get_column_letter(16)].width = 80   # Business

def sheet_revealed_pref(wb, conn):
    """What the tracked investors are BUYING now — dated evidence only
    (revealed_preference.py): the latest 13F quarter's net buying, insider
    purchases and new 13D/G stakes in the last 90 days, the latest N-PORT
    reports. The old ranking read the research spreadsheet's position
    sections (a May-June snapshot): no stale evidence counts now."""
    try:
        q = conn.execute("SELECT MAX(quarter) FROM revealed_pref").fetchone()[0]
        rows = conn.execute("""SELECT rp.ticker, rp.rp_score, rp.evidence_date, rp.f13_points, rp.f13_buyers,
                rp.f13_sellers, rp.f13_buying, rp.f13_selling, rp.ins_n, rp.ins_usd_m, rp.ins_csuite,
                rp.stake_holders, rp.np_buyers, rp.np_sellers, rp.np_buying, rp.cap_points, rp.cap_notes,
                y.ipo_date, ps.mom_3mo,
                us.mcap_m, us.mcap_bucket, us.smart_money_n, us.activist_max_pct, us.entry_bucket, tm.name
            FROM revealed_pref rp JOIN unified_signal us ON us.ticker = rp.ticker
            LEFT JOIN ticker_meta tm ON tm.ticker = rp.ticker
            LEFT JOIN ticker_yf y ON y.ticker = rp.ticker
            LEFT JOIN price_stats ps ON ps.ticker = rp.ticker
            WHERE rp.rp_score > 0 AND us.sec_type = 'common'
            ORDER BY rp.rp_score DESC""").fetchall()
    except sqlite3.OperationalError:
        return
    rows = [r for r in rows if r[0] not in ETFs]
    limit, total = 200, len(rows)
    rows = rows[:limit]
    ws = wb.create_sheet("Revealed Preference")
    ws.sheet_view.showGridLines = False
    hdr = ["Ticker", "RP Score", "Latest Evidence", "13F Net Pts", "13F Buyers", "13F Sellers",
           "Who Bought (13F)", "Who Sold (13F)", "Buyers' Record", "Insiders (90d)", "Insider $M", "C-suite",
           "New 13D/G (90d)", "N-PORT Buyers", "N-PORT Sellers", "N-PORT Moves", "Cap Pts",
           "Capital Structure", "Listed", "3M Chg %", "Short % Out", "Days to Cover", "Mcap", "Bucket", "13F",
           "Act %", "Entry", "Name", "Industry", "Business"]
    # the 13F buyers' own track records (track_records.py): how often their
    # new buys beat the S&P 500 after their 13Fs made them public
    tr = track_records(conn)
    from fund_moves import quarter_moves as _qm
    _mv, _ = _qm(conn)
    buyers_of = {}
    for m_ in _mv:
        if m_["kind"] in ("new", "add") and m_["pts"] > 0:
            buyers_of.setdefault(m_["ticker"], []).append(m_["fund"])
    def record(tk):
        rs = [tr[f] for f in buyers_of.get(tk, []) if f in tr and (tr[f]["n"] or 0) >= 10]   # 10+ buys = a record
        if not rs:
            return ""
        beat = sum(r["beat_pct"] for r in rs) / len(rs)
        return f"{beat:.0f}% beat S&P ({len(rs)} of {len(buyers_of[tk])} buyers with records)"
    shorts, _settle = short_data(conn)
    write_title(ws, "Revealed Preference — what they are buying now, with dated evidence",
                f"RP Score = 13F net buying in the {q} quarter (each fund's new or added % of book, net of trims "
                f"and exits, split-adjusted, capped at 10 per fund and scaled by focus min(1, 75/positions)) "
                f"+ 2 per insider buying $25k+ in 90 days (+2 if C-suite) + 5 per new 13D / 2 per new 13G in 90 "
                f"days + 1 per N-PORT manager initiating or adding (-1 trimming or exiting) + capital structure: "
                f"insiders exercising or converting and holding (+1 each, 90 days), funds converting warrants / "
                f"notes / preferred into common (+1 each), issuer tender offers (+3), last fiscal year's net "
                f"buybacks (+1 to +3) or net issuance (-1 / -2), 13D/G stakes raised (+2). Nothing older counts. "
                f"A 13F line new in a stock first listed during the quarter counts half (an IPO allocation, or a "
                f"pre-IPO stake becoming reportable) and a spin-off received counts zero; both stay visible, "
                f"labelled 'at listing' / 'spin-off received'. Listed = IPO in the last 12 months. "
                f"[showing top {min(limit, total)} of {total} net buyers]", len(hdr))
    write_table_header(ws, 4, hdr)
    import datetime as _dt
    ipo_cut = (_dt.date.today() - _dt.timedelta(days=365)).isoformat()
    out = []
    for (tk, score, ev_date, pts, nb, ns, buying, selling, ins_n, ins_usd, cs, stakes, npb, nps, npm,
         cap_pts, cap_notes, ipo, mom, mcap, bucket, sm, act, entry, name) in rows:
        eb = entry or ""
        eb_label = ("below" if eb == "BELOW_ENTRY" else "near" if eb == "NEAR_ENTRY"
                    else "above" if "ABOVE" in eb else "")
        d = desc_for(conn, tk)
        sh = shorts.get(tk) or (None, None, None)
        out.append([tk, round(score, 1), ev_date or "", round(pts, 1) if pts is not None else "", nb or 0, ns or 0,
                    buying or "", selling or "", record(tk), ins_n or 0, ins_usd if ins_usd else "", "yes" if cs else "",
                    stakes or "", npb or 0, nps or 0, npm or "",
                    cap_pts if cap_pts is not None else "", cap_notes or "",
                    f"IPO {ipo}" if (ipo and ipo >= ipo_cut) else "",
                    round(mom, 0) if mom is not None else "",
                    round(sh[0], 1) if sh[0] is not None else "", round(sh[1], 1) if sh[1] is not None else "",
                    mcap or "", bucket or "", round(sm or 0, 1),
                    round(act or 0, 1), eb_label, name or "", d[0], d[1]])
    write_table_rows(ws, out, 5)
    color_directional(ws, 5, 4 + len(out), [17, 20], higher_is_better=True)
    for ridx in range(5, 5 + len(out)):
        ws.cell(row=ridx, column=11).number_format = NUMFMT_M_TO_B
        ws.cell(row=ridx, column=20).number_format = '0"%"'
        ws.cell(row=ridx, column=21).number_format = '0.0"%"'
        ws.cell(row=ridx, column=22).number_format = '0.0'
        ws.cell(row=ridx, column=23).number_format = NUMFMT_MCAP
        ws.cell(row=ridx, column=26).number_format = NUMFMT_PCT
    ws.freeze_panes = "B5"
    autosize(ws)
    ws.column_dimensions["A"].width = 8
    for col in (7, 8):
        ws.column_dimensions[get_column_letter(col)].width = 60
    ws.column_dimensions[get_column_letter(9)].width = 34
    ws.column_dimensions[get_column_letter(13)].width = 36
    ws.column_dimensions[get_column_letter(16)].width = 40
    ws.column_dimensions[get_column_letter(18)].width = 60
    ws.column_dimensions[get_column_letter(29)].width = 24
    ws.column_dimensions[get_column_letter(30)].width = 80

_FIN_IND = ("bank", "insurance", "capital markets", "asset management", "credit services",
            "financial - ", "mortgage", "reinsurance", "financial conglomerate")

def _is_financial(sector, industry):
    """Banks, insurers, asset managers: EV/EBITDA means nothing there; book value does."""
    ind = (industry or "").lower()
    return (sector or "") == "Financial Services" or any(k in ind for k in _FIN_IND)

def sheet_valuation(wb, conn):
    """Cheap AND sound, in three sections: cash-generative non-financials on
    FCF yield, financials on price / tangible book, and the cheap names that
    fail a soundness check, each with the reason (possible value traps)."""
    ws = wb.create_sheet("Valuation")
    ws.sheet_view.showGridLines = False
    hdr = ["Ticker", "EV/EBITDA", "P/B", "P/E", "Fwd P/E", "EV/Rev", "FCF Yield %", "Earn Yield %", "ROIC %",
           "ROE %", "Net Debt/EBITDA", "Rev Gr %", "Margin %", "Flags", "Score", "Mcap", "Bucket", "13F",
           "Act %", "Entry", "vs Entry %", "Name", "Sector", "Industry", "Business"]
    write_title(ws, "Valuation — cheap, cash-generative and sound",
                "Names held by 3+ funds (conviction-weighted). 1) Cheap and sound: EV/EBITDA 2-20x, positive free "
                "cash flow (under 40%: above that is usually a one-off), net debt under 3x EBITDA, revenue not "
                "shrinking over 5% (last fiscal year), ROIC 8%+; "
                "ranked by FCF yield. 2) Financials, where EV/EBITDA means nothing: ROE 8%+ and positive earnings, "
                "ranked by price / tangible book. 3) Cheap (EV/EBITDA 2-10x) but failing a check — each flag says "
                "why (possible value traps).", len(hdr))
    base = list(conn.execute("""
        SELECT us.ticker, us.ev_ebitda, us.pb_ratio, us.pe_ttm, yf.fwd_pe, yf.ev_revenue, yf.fcf_yield,
               yf.earnings_yield, yf.roic, yf.roe, yf.net_debt_ebitda, COALESCE(yf.rev_growth_fy, yf.rev_growth),
               yf.profit_margin, us.score, us.mcap_m, us.mcap_bucket, us.smart_money_n, us.activist_max_pct,
               us.entry_bucket, us.vs_entry_pct, tm.name, yf.sector, COALESCE(yf.industry, tm.sic_description),
               yf.ptb_ratio
        FROM unified_signal us
        LEFT JOIN ticker_meta tm ON tm.ticker = us.ticker
        LEFT JOIN ticker_yf yf ON yf.ticker = us.ticker
        WHERE us.sec_type = 'common' AND us.smart_money_n >= 3
          AND COALESCE(yf.industry, '') != 'Shell Companies'"""))
    base = [r for r in base if r[0] not in ETFs]

    def flags(r):
        f = []
        if r[6] is None or r[10] is None or r[11] is None or r[8] is None:
            f.append("incomplete data")
        if r[6] is not None and r[6] <= 0:
            f.append("negative free cash flow")
        if r[6] is not None and r[6] > 0.40:
            # a 40%+ FCF yield is nearly always a one-off (working capital,
            # insurance float: Oscar Health read 55%), not a durable yield
            f.append(f"FCF yield {r[6] * 100:.0f}%: likely one-off")
        if r[10] is not None and r[10] >= 3:
            f.append(f"net debt {r[10]:.1f}x EBITDA")
        if r[11] is not None and r[11] < -0.05:
            f.append(f"revenue {r[11] * 100:+.0f}% last FY")
        if r[8] is not None and r[8] < 0.08:
            f.append(f"ROIC {r[8] * 100:.0f}%")
        return f

    sound, fin, trap = [], [], []
    for r in base:
        if _is_financial(r[21], r[22]):
            ptb = r[23] if r[23] and r[23] > 0 else (r[2] if r[2] and r[2] > 0 else None)
            if ptb and r[9] is not None and r[9] >= 0.08 and r[3] and r[3] > 0:
                fin.append((ptb, r))
            continue
        if r[1] is None or not (2 <= r[1] <= 20):
            continue
        fl = flags(r)
        if not fl:
            sound.append((-r[6], r))
        elif r[1] <= 10:
            trap.append((r[1], r, "; ".join(fl)))

    def cells(r, flag=""):
        eb = r[18] or ""
        eb_label = ("below" if eb == "BELOW_ENTRY" else "near" if eb == "NEAR_ENTRY"
                    else "above" if "ABOVE" in eb else "")
        pct = lambda x: round(x * 100, 1) if x is not None else ""
        if not flag and r[10] is not None and r[10] < 0:
            flag = "net cash"
        d = desc_for(conn, r[0])
        return [r[0], round(r[1], 1) if r[1] is not None else "", round(r[2], 2) if r[2] is not None else "",
                round(r[3], 1) if r[3] is not None else "", round(r[4], 1) if r[4] is not None else "",
                round(r[5], 1) if r[5] is not None else "", pct(r[6]), pct(r[7]), pct(r[8]), pct(r[9]),
                round(r[10], 1) if r[10] is not None else "", pct(r[11]),
                round(r[12] * 100, 0) if r[12] is not None else "", flag,
                round(r[13] or 0, 1), r[14] or "", r[15] or "", round(r[16] or 0, 1), round(r[17] or 0, 1),
                eb_label, round(r[19] or 0, 1) if r[19] else "", r[20] or "", r[21] or "", d[0], d[1]]

    sections = [
        (f"1 · Cheap and sound — ranked by FCF yield ({len(sound)} names)",
         [cells(r) for _, r in sorted(sound, key=lambda x: x[0])[:80]]),
        (f"2 · Financials — ranked by price / tangible book ({len(fin)} names)",
         [cells(r) for _, r in sorted(fin, key=lambda x: x[0])[:50]]),
        (f"3 · Cheap but flagged — possible value traps ({len(trap)} names)",
         [cells(r, fl) for _, r, fl in sorted(trap, key=lambda x: x[0])[:80]]),
    ]
    row = 4
    for label, out in sections:
        write_section_heading(ws, row, label, len(hdr)); row += 1
        write_table_header(ws, row, hdr); row += 1
        write_table_rows(ws, out, row)
        color_directional(ws, row, row + len(out) - 1, [7, 9, 12], higher_is_better=True)
        for ridx in range(row, row + len(out)):
            for col, fmt in ((2, '0.0"x"'), (3, '0.00"x"'), (4, '0.0"x"'), (5, '0.0"x"'), (6, '0.0"x"'),
                             (7, '0.0"%"'), (8, '0.0"%"'), (9, '0.0"%"'), (10, '0.0"%"'), (11, '0.0"x"'),
                             (12, '0"%"'), (13, '0"%"'), (16, NUMFMT_MCAP), (19, NUMFMT_PCT), (21, NUMFMT_PCT)):
                ws.cell(row=ridx, column=col).number_format = fmt
        row += len(out) + 2
    ws.freeze_panes = "B4"
    autosize(ws)
    ws.column_dimensions["A"].width = 8
    ws.column_dimensions[get_column_letter(14)].width = 40   # Flags
    ws.column_dimensions[get_column_letter(24)].width = 24   # Industry
    ws.column_dimensions[get_column_letter(25)].width = 80   # Business

def sheet_catalysts(wb, conn):
    """8-K material-event tickers: M&A, control change, director shuffle, PIPE, bankruptcy."""
    ws = wb.create_sheet("Catalysts 8-K")
    ws.sheet_view.showGridLines = False
    write_title(ws, "8-K Material-Event Catalysts (≤180d)",
                "M&A (1.01 / 2.01), Control change (5.01), Director change (5.02), PIPE/dilution (3.02), Bankruptcy (1.03). Sorted by unified score, then M&A/control weight.", 15)
    hdr = ["Ticker","Score","Mcap","M&A","Ctrl","Director","PIPE","Bnk","Total Events","13F","Activist %","EV/EBITDA","P/B","Name","Sector"]
    write_table_header(ws, 4, hdr)
    rows = list(conn.execute("""
        SELECT us.ticker, us.score, us.mcap_m,
               us.cat8k_ma, us.cat8k_ctrl, us.cat8k_dir, us.cat8k_pipe, us.cat8k_bnk, us.cat8k_n,
               us.smart_money_n, us.activist_max_pct, us.ev_ebitda, us.pb_ratio, tm.name, tm.sic_description
        FROM unified_signal us
        LEFT JOIN ticker_meta tm ON tm.ticker = us.ticker
        WHERE us.cat8k_n > 0 AND us.sec_type='common'
        ORDER BY us.score DESC, (us.cat8k_ma*5 + us.cat8k_ctrl*4) DESC LIMIT 200"""))
    out = []
    for r in rows:
        if r[0] in ETFs or r[0] in MEGA: continue
        out.append([r[0], round(r[1] or 0, 1), r[2] or "",
                    "✓" if r[3] else "", "✓" if r[4] else "",
                    "✓" if r[5] else "", "✓" if r[6] else "",
                    "✓" if r[7] else "", r[8] or 0,
                    r[9] or 0, round(r[10] or 0, 1),
                    round(r[11], 1) if r[11] is not None else "",
                    round(r[12], 2) if r[12] is not None else "",
                    (r[13] or ""), (r[14] or "")])
    write_table_rows(ws, out, 5)
    for ridx in range(5, 5 + len(out)):
        ws.cell(row=ridx, column=3).number_format = NUMFMT_MCAP
        ws.cell(row=ridx, column=11).number_format = NUMFMT_PCT
        ws.cell(row=ridx, column=12).number_format = '0.0"x"'
        ws.cell(row=ridx, column=13).number_format = '0.00"x"'
    ws.freeze_panes = "B5"
    autosize(ws)
    ws.column_dimensions["A"].width = 8

def _mgr_short(manager):
    """'Harris Associates LP   Oakmark ' -> 'Harris Associates LP' (roster names
    carry PM parentheticals and suffixes after a double space)."""
    m = re.sub(r"\(.*?(\)|$)", "", manager or "")
    return re.split(r"\s{2,}", m)[0].strip() or (manager or "").strip()

def _usd_mcap(mcap_m, ccy):
    """Listing-currency market cap -> USD (major-unit rate: London caps are in
    pounds though the price is in pence)."""
    from unified_score import fx_major
    fx = fx_major(ccy)
    return mcap_m * fx if (mcap_m and fx) else None

# ---- N-PORT: the registered funds' complete books ---------------------------
# One block of sheets, in reading order: which funds (N-PORT Funds), what each
# holds (N-PORT Holdings), what they changed (N-PORT Changes), and where they
# agree outside the US (N-PORT Global Consensus). Registered-fund data: never
# counted in the 13F score.
_STYLE_ORDER = ["Value / Concentrated Quality", "Foreign / EM Value", "Small-cap / Multibagger Specialists",
                "Disruptive Growth / Innovation", "Activists / Special Situations", "Distressed / Event-Driven",
                "Tiger Cubs / L/S Legends", "Family Offices / Individual Filers", "Biotech Specialists",
                "Mega Multi-Strats / Quants"]
_NO_STYLE = "Not on the 13F roster"

def _nport_style(conn):
    try:
        return {f: m for f, m in conn.execute("SELECT fund, macro_style FROM fund_style")}
    except sqlite3.OperationalError:
        return {}

def _style_rank(style):
    return (_STYLE_ORDER.index(style) if style in _STYLE_ORDER else len(_STYLE_ORDER), style or "")

def _fund_heading(ws, row, text, ncols):
    """A fund's line inside a manager's section: italic, not shouted."""
    ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=ncols)
    c = ws.cell(row=row, column=1, value=text)
    c.font = BODY_ITALIC
    c.alignment = Alignment(horizontal="left", vertical="bottom")
    ws.row_dimensions[row].height = 18

def sheet_nport_funds(wb, conn):
    """Which registered funds are loaded: grouped by the manager's style."""
    try:
        funds = conn.execute("""SELECT series_id, manager, series, MAX(period), SUM(val_usd), COUNT(*),
                SUM(CASE WHEN country != 'US' THEN val_usd ELSE 0 END), MAX(filed),
                COUNT(DISTINCT CASE WHEN country != 'US' THEN COALESCE(isin, ticker, issuer) END)
            FROM nport_holdings GROUP BY series_id""").fetchall()
    except sqlite3.OperationalError:
        return
    if not funds:
        return
    pos, exits, _ = _nport_diff(conn)
    style = _nport_style(conn)
    prior_p = {sid: p for sid, p in conn.execute("SELECT series_id, MAX(period) FROM nport_prior GROUP BY series_id")}
    names = {}
    for sid, key, nm, co in conn.execute("""SELECT n.series_id, COALESCE(n.isin, n.ticker, n.issuer),
            COALESCE(y.long_name, n.issuer), n.country FROM nport_holdings n
            LEFT JOIN ticker_yf y ON y.ticker = n.ticker ORDER BY n.val_usd DESC"""):
        names.setdefault(sid, []).append((key, nm if co in (None, "US") else f"{nm} ({co})"))
    ws = wb.create_sheet("N-PORT Funds")
    ws.sheet_view.showGridLines = False
    hdr = ["Manager", "Fund", "Portfolio as of", "Filed", "Equity $M", "Positions", "Non-US %", "Non-US Names",
           "Largest positions", "Largest non-US positions", "Previous report", "Initiated since", "Exited since"]
    n_mgr = len({f[1] for f in funds})
    write_title(ws, "N-PORT Funds — the registered funds whose complete books are loaded",
                f"{len(funds)} funds of {n_mgr} managers, grouped by the manager's style. N-PORT lists every "
                f"holding, local listings included (a 13F lists US-listed securities only); public quarterly, "
                f"about 60 days after each fund's fiscal quarter. Initiated / exited: since the previous report.",
                len(hdr))
    row = 4
    ordered = sorted(funds, key=lambda f: (_style_rank(style.get(f[1]) or _NO_STYLE), _mgr_short(f[1]), f[2]))
    groups = {}
    for f in ordered:
        groups.setdefault(style.get(f[1]) or _NO_STYLE, []).append(f)
    for st, fs in groups.items():
        write_section_heading(ws, row, f"{st} — {len({f[1] for f in fs})} managers, {len(fs)} funds", len(hdr))
        row += 1
        write_table_header(ws, row, hdr)
        row += 1
        out = []
        for sid, mg, series, period, tot, n, fgn, filed, n_fgn in fs:
            held = names.get(sid, [])
            top = conn.execute("""SELECT COALESCE(y.long_name, n.issuer), n.pct, n.country FROM nport_holdings n
                LEFT JOIN ticker_yf y ON y.ticker = n.ticker WHERE n.series_id = ?
                ORDER BY n.val_usd DESC LIMIT 5""", (sid,)).fetchall()
            top_f = conn.execute("""SELECT COALESCE(y.long_name, n.issuer), n.pct, n.country FROM nport_holdings n
                LEFT JOIN ticker_yf y ON y.ticker = n.ticker WHERE n.series_id = ? AND n.country != 'US'
                ORDER BY n.val_usd DESC LIMIT 6""", (sid,)).fetchall()
            new = [nm for key, nm in held if pos.get((sid, key), ("",))[0] == "new"]
            gone = [nm if co in (None, "US") else f"{nm} ({co})"
                    for nm, v, co in sorted(exits.get(sid, []), key=lambda x: -x[1])]
            has_p = sid in prior_p
            fmt = lambda rows: "; ".join(f"{nm} {p:.1f}%{'' if co in (None, 'US') else f' ({co})'}"
                                         for nm, p, co in rows)
            out.append([_mgr_short(mg), series, period, filed, round((tot or 0) / 1e6, 1), n,
                        round(100.0 * (fgn or 0) / tot, 1) if tot else "", n_fgn, fmt(top), fmt(top_f),
                        prior_p.get(sid, "none on file"),
                        ("; ".join(new) or "none") if has_p else "",
                        ("; ".join(gone) or "none") if has_p else ""])
        write_table_rows(ws, out, row)
        for ridx in range(row, row + len(out)):
            ws.cell(row=ridx, column=5).number_format = NUMFMT_M_TO_B
            ws.cell(row=ridx, column=7).number_format = '0"%"'
        row += len(out) + 2
    ws.freeze_panes = "C4"
    autosize(ws)
    for col in (9, 10, 12, 13):
        ws.column_dimensions[get_column_letter(col)].width = 70

def sheet_nport_holdings(wb, conn):
    """Every loaded fund's complete equity book: a section per manager, a
    table per fund, each position with its change since the prior report."""
    try:
        rows = conn.execute("""SELECT n.series_id, n.manager, n.series, n.period, n.ticker,
                COALESCE(n.isin, n.ticker, n.issuer), COALESCE(y.long_name, n.issuer), n.country, n.pct,
                n.val_usd, y.mcap_m, y.currency
            FROM nport_holdings n LEFT JOIN ticker_yf y ON y.ticker = n.ticker
            ORDER BY n.series_id, n.val_usd DESC""").fetchall()
    except sqlite3.OperationalError:
        return
    if not rows:
        return
    pos, _, _ = _nport_diff(conn)
    style = _nport_style(conn)
    books = {}
    for r in rows:
        books.setdefault(r[1], {}).setdefault(r[0], []).append(r)
    ws = wb.create_sheet("N-PORT Holdings")
    ws.sheet_view.showGridLines = False
    hdr = ["Ticker", "Company", "Country", "% of Fund", "$M", "Change", "Δ Shares %", "Mcap $M (USD)", "Industry"]
    write_title(ws, "N-PORT Holdings — each fund's complete equity book",
                "A section per manager, a table per fund, largest position first. Change: since the fund's "
                "previous public report, on split-adjusted share counts (added / trimmed = over 10%). "
                "Local listings a 13F never shows are included.", len(hdr))
    row = 4
    for mg in sorted(books, key=lambda m: (_style_rank(style.get(m) or _NO_STYLE), _mgr_short(m))):
        funds = books[mg]
        write_section_heading(ws, row, f"{_mgr_short(mg)} — {style.get(mg) or _NO_STYLE} · "
                                       f"{len(funds)} fund{'s' if len(funds) > 1 else ''}", len(hdr))
        row += 1
        for sid in sorted(funds, key=lambda s: -sum(r[9] or 0 for r in funds[s])):
            fr = funds[sid]
            tot = sum(r[9] or 0 for r in fr)
            fgn = sum(r[9] or 0 for r in fr if r[7] and r[7] != "US")
            filed = conn.execute("SELECT MAX(filed) FROM nport_holdings WHERE series_id = ?", (sid,)).fetchone()[0]
            _fund_heading(ws, row, f"{fr[0][2]} · portfolio as of {fr[0][3]} (filed {filed}) · ${tot / 1e9:,.2f}B in "
                                   f"{len(fr)} equities · {100 * fgn / tot if tot else 0:.0f}% outside the US",
                          len(hdr))
            row += 1
            write_table_header(ws, row, hdr)
            row += 1
            out = []
            for sid_, mg_, series, period, tk, key, name, co, pct, val, mcap, ccy in fr:
                st, d = pos.get((sid_, key), ("", None))
                usd = _usd_mcap(mcap, ccy)
                out.append([tk or "(no listing)", name, co or "", round(pct or 0, 2), round((val or 0) / 1e6, 1),
                            st, round(d, 0) if d is not None else "", round(usd) if usd else "",
                            desc_for(conn, tk)[0] if tk else ""])
            write_table_rows(ws, out, row, ticker_col=1)
            for ridx in range(row, row + len(out)):
                ws.cell(row=ridx, column=4).number_format = '0.00"%"'
                ws.cell(row=ridx, column=5).number_format = NUMFMT_M_TO_B
                ws.cell(row=ridx, column=7).number_format = '0"%"'
                ws.cell(row=ridx, column=8).number_format = NUMFMT_MCAP
            row += len(out) + 1
        row += 1
    ws.freeze_panes = "B4"
    autosize(ws)
    ws.column_dimensions["B"].width = 36

def sheet_nport_changes(wb, conn):
    """What the managers' registered funds bought and sold since their
    previous reports — per stock, US and non-US."""
    pos, _, mgr = _nport_diff(conn)
    if not mgr:
        return
    info = {}
    for key, tk, name, co, val, pct, sid in conn.execute("""SELECT COALESCE(n.isin, n.ticker, n.issuer), n.ticker,
            COALESCE(y.long_name, n.issuer), n.country, n.val_usd, n.pct, n.series_id
            FROM nport_holdings n LEFT JOIN ticker_yf y ON y.ticker = n.ticker"""):
        d = info.setdefault(key, {"tk": tk, "name": name, "co": co, "val": 0.0, "new_w": 0.0})
        d["val"] += val or 0.0
        if pos.get((sid, key), ("",))[0] == "new":
            d["new_w"] = max(d["new_w"], pct or 0.0)
    for key, tk, name, co in conn.execute("""SELECT COALESCE(p.isin, p.ticker, p.issuer), p.ticker,
            COALESCE(y.long_name, p.issuer), p.country FROM nport_prior p
            LEFT JOIN ticker_yf y ON y.ticker = p.ticker"""):
        info.setdefault(key, {"tk": tk, "name": name, "co": co, "val": 0.0, "new_w": 0.0})
    per = {}
    for (mg, key), st in mgr.items():
        if st in ("new", "added", "trimmed", "exited"):
            per.setdefault(key, {"new": [], "added": [], "trimmed": [], "exited": []})[st].append(_mgr_short(mg))
    ws = wb.create_sheet("N-PORT Changes")
    ws.sheet_view.showGridLines = False
    hdr = ["Ticker", "Company", "Country", "Net", "Initiated", "Added", "Trimmed", "Exited", "Buying",
           "Selling", "Largest New Weight %", "$M Held Now", "Mcap $M (USD)", "Industry"]
    write_title(ws, "N-PORT Changes — what the managers' funds bought and sold",
                "Per stock, across every manager's funds, since each fund's previous public report "
                "(split-adjusted share counts; added / trimmed = over 10%). Net = managers initiating or "
                "adding minus managers trimming or exiting. US and non-US listings.", len(hdr))
    write_table_header(ws, 4, hdr)
    mc = {tk: (m, c) for tk, m, c in conn.execute("SELECT ticker, mcap_m, currency FROM ticker_yf")}
    out = []
    for key, d in per.items():
        i = info.get(key, {"tk": None, "name": key, "co": "", "val": 0.0, "new_w": 0.0})
        buy = [f"{m} (new)" for m in d["new"]] + [f"{m} (added)" for m in d["added"]]
        sell = [f"{m} (trimmed)" for m in d["trimmed"]] + [f"{m} (exited)" for m in d["exited"]]
        net = len(d["new"]) + len(d["added"]) - len(d["trimmed"]) - len(d["exited"])
        usd = _usd_mcap(*mc.get(i["tk"], (None, None))) if i["tk"] else None
        out.append([i["tk"] or "(no listing)", i["name"], i["co"] or "", net, len(d["new"]), len(d["added"]),
                    len(d["trimmed"]), len(d["exited"]), "; ".join(buy), "; ".join(sell),
                    round(i["new_w"], 2) if i["new_w"] else "", round(i["val"] / 1e6, 1) if i["val"] else "",
                    round(usd) if usd else "", desc_for(conn, i["tk"])[0] if i["tk"] else ""])
    out.sort(key=lambda r: (-r[3], -(r[4] + r[5]), -(r[11] or 0)))
    write_table_rows(ws, out, 5, ticker_col=1)
    color_directional(ws, 5, 4 + len(out), [4], higher_is_better=True)
    for ridx in range(5, 5 + len(out)):
        ws.cell(row=ridx, column=11).number_format = '0.00"%"'
        ws.cell(row=ridx, column=12).number_format = NUMFMT_M_TO_B
        ws.cell(row=ridx, column=13).number_format = NUMFMT_MCAP
    ws.freeze_panes = "B5"
    autosize(ws)
    for col in (9, 10):
        ws.column_dimensions[get_column_letter(col)].width = 60

def sheet_nport_consensus(wb, conn):
    """Where the managers agree outside the US: non-US equities ranked by how
    many managers' funds hold them (13F-invisible)."""
    try:
        rows = conn.execute("""SELECT n.ticker, COALESCE(n.isin, n.ticker, n.issuer), n.issuer, n.country,
                n.manager, n.val_usd, n.pct, y.long_name, y.mcap_m, y.currency
            FROM nport_holdings n LEFT JOIN ticker_yf y ON y.ticker = n.ticker
            WHERE n.country IS NOT NULL AND n.country != 'US'""").fetchall()
    except sqlite3.OperationalError:
        return
    if not rows:
        return
    _, _, mgr = _nport_diff(conn)
    per = {}
    for tk, key, issuer, country, manager, val, pct, name, mcap, ccy in rows:
        d = per.setdefault(key, {"tk": tk, "name": name or issuer, "country": country,
                                 "mgr": {}, "new": set(), "val": 0.0, "mcap": _usd_mcap(mcap, ccy)})
        mg = _mgr_short(manager)
        d["mgr"][mg] = max(d["mgr"].get(mg, 0.0), pct or 0.0)
        d["val"] += val or 0.0
        if mgr.get((manager, key)) == "new":
            d["new"].add(mg)
    n_funds, n_mgr, p0, p1 = conn.execute("""SELECT COUNT(DISTINCT series_id), COUNT(DISTINCT manager),
        MIN(period), MAX(period) FROM nport_holdings""").fetchone()
    ws = wb.create_sheet("N-PORT Global Consensus")
    ws.sheet_view.showGridLines = False
    hdr = ["Ticker", "Company", "Country", "Managers", "New Buyers", "Held by (largest % of a fund)",
           "$M Held", "Max % of Fund", "Mcap $M (USD)", "Industry", "Business"]
    write_title(ws, "N-PORT Global Consensus — where the managers agree outside the US",
                f"Every non-US equity held by the funds of {n_mgr} managers ({n_funds} funds, portfolios as of "
                f"{p0} to {p1}), ranked by how many managers hold it. A 13F shows none of these local "
                f"listings. New Buyers: managers holding it now but in none of their previous reports.",
                len(hdr))
    write_table_header(ws, 4, hdr)
    out = []
    for d in sorted(per.values(), key=lambda d: (-len(d["mgr"]), -len(d["new"]), -d["val"])):
        held = "; ".join(f"{m} {p:.1f}%{' (new)' if m in d['new'] else ''}"
                         for m, p in sorted(d["mgr"].items(), key=lambda x: -x[1]))
        ind, bus = desc_for(conn, d["tk"]) if d["tk"] else ("", "")
        out.append([d["tk"] or "(no listing)", d["name"], d["country"], len(d["mgr"]), len(d["new"]), held,
                    round(d["val"] / 1e6, 1), round(max(d["mgr"].values()), 2),
                    round(d["mcap"]) if d["mcap"] else "", ind, bus])
    write_table_rows(ws, out, 5, ticker_col=1)
    for ridx in range(5, 5 + len(out)):
        ws.cell(row=ridx, column=7).number_format = NUMFMT_M_TO_B
        ws.cell(row=ridx, column=8).number_format = '0.0"%"'
        ws.cell(row=ridx, column=9).number_format = NUMFMT_MCAP
    ws.freeze_panes = "B5"
    autosize(ws)
    ws.column_dimensions["F"].width = 60
    ws.column_dimensions[get_column_letter(11)].width = 80

_VENUE = {".T": "Tokyo", ".L": "London", ".HK": "Hong Kong", ".PA": "Paris", ".DE": "Xetra",
          ".F": "Frankfurt", ".AS": "Amsterdam", ".SW": "SIX Swiss", ".KS": "Korea", ".KQ": "KOSDAQ",
          ".TW": "Taiwan", ".TWO": "Taipei OTC", ".TO": "Toronto", ".V": "TSX Venture", ".AX": "ASX",
          ".MI": "Milan", ".MC": "Madrid", ".ST": "Stockholm", ".CO": "Copenhagen", ".HE": "Helsinki",
          ".OL": "Oslo", ".SA": "São Paulo", ".MX": "Mexico", ".NS": "NSE India", ".BO": "BSE India",
          ".JK": "Jakarta", ".SI": "Singapore", ".KL": "Kuala Lumpur", ".BK": "Bangkok", ".SS": "Shanghai",
          ".SZ": "Shenzhen", ".IR": "Dublin", ".BR": "Brussels", ".VI": "Vienna", ".LS": "Lisbon",
          ".IS": "Istanbul", ".JO": "Johannesburg", ".WA": "Warsaw", ".PR": "Prague", ".BD": "Budapest",
          ".TA": "Tel Aviv", ".NZ": "New Zealand", ".SN": "Santiago", ".VN": "Vietnam", ".SR": "Saudi"}

def _venue(ticker, exchange=None):
    """The listing venue: the stored exchange, else read off the ticker suffix."""
    if exchange:
        return exchange
    t = ticker or ""
    return next((v for suf, v in _VENUE.items() if t.endswith(suf)), "US" if "." not in t else "")

def sheet_global_picks(wb, conn):
    """Non-US listings ranked on fresh evidence: how many tracked managers
    hold them in their registered funds (N-PORT) and how many are buying,
    their largest weight, and the 13F funds holding / buying the company's US
    line (ADR or direct listing). The research spreadsheet's sections are
    shown for context but no longer drive the rank (a May-June snapshot)."""
    from nport_diff import nport_diff
    try:
        np_rows = conn.execute("""SELECT n.ticker, COALESCE(n.isin, n.ticker, n.issuer), n.manager, n.pct, n.val_usd
            FROM nport_holdings n WHERE n.ticker IS NOT NULL AND n.country IS NOT NULL AND n.country != 'US'""").fetchall()
    except sqlite3.OperationalError:
        np_rows = []
    _, _, mgr = nport_diff(conn)
    per = {}
    for tk, key, manager, pct, val in np_rows:
        d = per.setdefault(tk, {"mgr": {}, "buy": set(), "sell": set(), "val": 0.0})
        m = _mgr_short(manager)
        d["mgr"][m] = max(d["mgr"].get(m, 0.0), pct or 0.0)
        d["val"] += val or 0.0
        st = mgr.get((manager, key))
        if st in ("new", "added"):
            d["buy"].add(m)
        elif st in ("trimmed", "exited"):
            d["sell"].add(m)
    try:
        for (tk,) in conn.execute("SELECT ticker FROM unified_signal WHERE is_us = 0 AND sec_type = 'common' "
                                  "AND (s1_top + s3_new + s4_add + smart_money_n) >= 1"):
            per.setdefault(tk, {"mgr": {}, "buy": set(), "sell": set(), "val": 0.0})
    except sqlite3.OperationalError:
        pass
    try:
        adr = dict(conn.execute("SELECT ordinary, adr FROM adr_link"))
    except sqlite3.OperationalError:
        adr = {}
    us = {r[0]: r for r in conn.execute("""SELECT us.ticker, us.smart_money_n, us.s1_top, us.s3_new, us.s4_add,
            us.max_pct_book, us.activist_max_pct, us.entry_bucket, us.vs_entry_pct, us.ev_ebitda, us.pb_ratio,
            us.mcap_m FROM unified_signal us""")}
    try:
        rp = {t: (p, b, s) for t, p, b, s in conn.execute(
            "SELECT ticker, f13_points, f13_buyers, f13_sellers FROM revealed_pref")}
    except sqlite3.OperationalError:
        rp = {}
    meta = {t: (ex, nm) for t, ex, nm in conn.execute("SELECT ticker, exchange, name FROM ticker_meta")}
    yfd = {t: (c, m, n, co, fcf, roic) for t, c, m, n, co, fcf, roic in conn.execute(
        "SELECT ticker, currency, mcap_m, long_name, NULL, fcf_yield, roic FROM ticker_yf")}
    out = []
    for tk, d in per.items():
        a = adr.get(tk)
        own, via = us.get(tk), us.get(a) if a else None
        h13 = max((own[1] if own else 0) or 0, (via[1] if via else 0) or 0)
        net13 = sum(x for x in ((rp.get(tk) or (0,))[0] or 0, (rp.get(a) or (0,))[0] or 0 if a else 0))
        b13 = ((rp.get(tk) or (0, 0, 0))[1] or 0) + (((rp.get(a) or (0, 0, 0))[1] or 0) if a else 0)
        n_m, n_b, n_s = len(d["mgr"]), len(d["buy"]), len(d["sell"])
        maxp = max(d["mgr"].values()) if d["mgr"] else 0.0
        score = (2 * n_m + 2 * n_b - n_s + 0.5 * min(maxp, 10) + 0.5 * min(h13, 10)
                 + 0.5 * max(min(net13, 10), -10))
        if score <= 0:
            continue
        ccy, mcap, lname = (yfd.get(tk) or (None, None, None))[:3]
        fcf, roic = (yfd.get(tk) or (None,) * 6)[4:6]
        usd = _usd_mcap(mcap, ccy) if mcap else (own[11] if own else None)
        eb = (own[7] if own else "") or ""
        eb_label = ("below" if eb == "BELOW_ENTRY" else "near" if eb == "NEAR_ENTRY"
                    else "above" if "ABOVE" in eb else "")
        ex, nm = meta.get(tk, ("", ""))
        held = "; ".join(f"{m} {p:.1f}%{' (new)' if m in d['buy'] else ''}"
                         for m, p in sorted(d["mgr"].items(), key=lambda x: -x[1]))
        desc = desc_for(conn, tk)
        out.append([tk, round(score, 1), _venue(tk, ex), round(usd) if usd else "", ccy or "USD",
                    n_m, n_b, n_s, held, a or "", round(h13, 1), b13, round(net13, 1) if net13 else "",
                    (own[2] if own else 0) or 0, (own[3] if own else 0) or 0, (own[4] if own else 0) or 0,
                    round((own[5] if own else 0) or 0, 1), round((own[6] if own else 0) or 0, 1), eb_label,
                    round(own[8], 1) if (own and own[8]) else "",
                    round(own[9], 1) if (own and own[9] is not None) else "",
                    round(own[10], 2) if (own and own[10] is not None) else "",
                    round(fcf * 100, 1) if fcf is not None else "", round(roic * 100, 1) if roic is not None else "",
                    nm or lname or "", desc[0], desc[1]])
    out.sort(key=lambda r: -r[1])
    ws = wb.create_sheet("Global Picks")
    ws.sheet_view.showGridLines = False
    hdr = ["Ticker", "Global Score", "Exchange", "Mcap $ (USD)", "Ccy", "N-PORT Mgrs", "N-PORT Buyers",
           "N-PORT Sellers", "Held by (N-PORT)", "US Line", "13F Holders", "13F Buyers", "13F Net Buying",
           "S1", "S3", "S4", "pB Max", "Act %", "Entry", "vs Entry %", "EV/EBITDA", "P/B", "FCF Yield %",
           "ROIC %", "Name", "Industry", "Business"]
    write_title(ws, "Global Picks — non-US listings ranked on fresh evidence",
                "Global Score = 2 x managers holding it in their registered funds (N-PORT) + 2 x managers buying "
                "it in their latest report - 1 x managers selling + 0.5 x largest % of a fund (cap 10) + 0.5 x 13F "
                "holders of the company's US line or itself (conviction-weighted, cap 10) + 0.5 x the latest "
                "quarter's 13F net buying (cap +/-10). US Line = the ADR or direct US listing whose 13F holders "
                "count here. S1 / S3 / S4 as in the score (the latest 13F quarter where a fund has a current book, "
                "research notes otherwise): context only, not in the rank. Mcap converted to USD at approximate FX.",
                len(hdr))
    write_table_header(ws, 4, hdr)
    limit, total = 200, len(out)
    out = out[:limit]
    write_table_rows(ws, out, 5)
    for ridx in range(5, 5 + len(out)):
        ws.cell(row=ridx, column=4).number_format = NUMFMT_MCAP
        ws.cell(row=ridx, column=17).number_format = NUMFMT_PCT
        ws.cell(row=ridx, column=18).number_format = NUMFMT_PCT
        ws.cell(row=ridx, column=20).number_format = NUMFMT_PCT
        ws.cell(row=ridx, column=21).number_format = '0.0"x"'
        ws.cell(row=ridx, column=22).number_format = '0.00"x"'
        ws.cell(row=ridx, column=23).number_format = '0.0"%"'
        ws.cell(row=ridx, column=24).number_format = '0.0"%"'
    if total > limit:
        ws.cell(row=2, column=1).value = (ws.cell(row=2, column=1).value or "") + \
            f"  [showing top {limit} of {total}]"
    ws.freeze_panes = "B5"
    autosize(ws)
    ws.column_dimensions["A"].width = 10
    ws.column_dimensions["I"].width = 60
    ws.column_dimensions[get_column_letter(26)].width = 24   # Industry
    ws.column_dimensions[get_column_letter(27)].width = 80   # Business


_ANCHOR_LABEL = {"candidates": "analyst anchor", "raw_text": "filing text",
                 "form4_p_buy": "insider avg cost", "p80_close": "80th-pctl price"}
def sheet_in_the_money(wb, conn):
    """Below-entry / in-the-money picks — buy below where smart money entered."""
    ws = wb.create_sheet("In The Money")
    ws.sheet_view.showGridLines = False
    write_title(ws, "In The Money — buy below smart-money entry",
                "Trading below our estimate of what the funds paid (the Anchor). Anchor Src says how it was set: a cost "
                "or deal price stated in a filing or note (e.g. a PIPE at $4.44), else insiders' average open-market "
                "purchase price in the last 180 days, else the 80th percentile of the stock's closes over the year "
                "(p80_close — funds rarely build at the extremes). vs Entry % = today's price against it.", 19)
    hdr = ["Ticker","Score","Mcap","Bucket","Now $","Anchor $","vs Entry %",
           "13F","S1","S3","S4","Act %","pB Max","Anchor Src","EV/EBITDA","P/B","Name","Industry","Business"]
    write_table_header(ws, 4, hdr)
    rows = list(conn.execute("""
        SELECT us.ticker, us.score, us.mcap_m, us.mcap_bucket,
               COALESCE(yf.price, us.price) AS now_px,
               us.anchor_px, us.vs_entry_pct,
               us.smart_money_n, us.s1_top, us.s3_new, us.s4_add,
               us.activist_max_pct, us.max_pct_book,
               us.anchor_source, us.ev_ebitda, us.pb_ratio, tm.name
        FROM unified_signal us
        LEFT JOIN ticker_meta tm ON tm.ticker = us.ticker
        LEFT JOIN ticker_yf yf ON yf.ticker = us.ticker
        WHERE us.entry_bucket = 'BELOW_ENTRY' AND us.sec_type='common'
        ORDER BY us.score DESC LIMIT 100"""))
    out = []
    for r in rows:
        if r[0] in ETFs: continue
        # ONE price vintage: recompute vs-entry from the freshest price shown in
        # the NOW column, and drop rows that are no longer below the anchor —
        # the stored vs_entry_pct could disagree with its own row (FEIM showed
        # -18% while NOW > ANCHOR).
        now_px, anchor = r[4], r[5]
        vs = ((now_px / anchor) - 1) * 100 if (now_px and anchor) else None
        if vs is None or vs > 2:      # not meaningfully below entry any more
            continue
        out.append([r[0], round(r[1] or 0, 1), r[2] or "", r[3] or "",
                    round(now_px or 0, 2) if now_px else "",
                    round(anchor or 0, 2) if anchor else "",
                    round(vs, 1),
                    r[7] or 0, r[8] or 0, r[9] or 0, r[10] or 0,
                    round(r[11] or 0, 1), round(r[12] or 0, 1),
                    _ANCHOR_LABEL.get(r[13], (r[13] or "")),
                    round(r[14], 1) if r[14] is not None else "",
                    round(r[15], 2) if r[15] is not None else "",
                    (r[16] or ""), *desc_for(conn, r[0])])
    write_table_rows(ws, out, 5)
    for ridx in range(5, 5 + len(out)):
        ws.cell(row=ridx, column=3).number_format = NUMFMT_MCAP
        ws.cell(row=ridx, column=5).number_format = NUMFMT_USD2
        ws.cell(row=ridx, column=6).number_format = NUMFMT_USD2
        ws.cell(row=ridx, column=7).number_format = NUMFMT_PCT
        ws.cell(row=ridx, column=12).number_format = NUMFMT_PCT
        ws.cell(row=ridx, column=13).number_format = NUMFMT_PCT
        ws.cell(row=ridx, column=15).number_format = '0.0"x"'
        ws.cell(row=ridx, column=16).number_format = '0.00"x"'
    ws.freeze_panes = "B5"
    autosize(ws)
    ws.column_dimensions["A"].width = 8
    ws.column_dimensions[get_column_letter(18)].width = 24   # Industry
    ws.column_dimensions[get_column_letter(19)].width = 80   # Business

def sheet_bill_miller(wb, conn):
    ws = wb.create_sheet("Bill Miller")
    ws.sheet_view.showGridLines = False
    write_title(ws, "Bill Miller — both Funds",
                "Miller Value Partners (Bill IV, Sarasota) + Patient Capital Management (Bill III). Side-by-side with overlap.", 12)
    funds = [
        ("Bill IV — Miller Value Partners", "Miller Value Partners%"),
        ("Bill III — Patient Capital",       "Patient Capital%"),
    ]
    write_section_heading(ws, 4, "Top 20 holdings — per fund", 12)
    hdr = ["Ticker","Issuer","Value $M","%Book","Mcap","Bucket","13F","Act %","Cluster?","EV/EBITDA","P/B","Name"]
    write_table_header(ws, 5, hdr)
    row = 6
    for label, like in funds:
        ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=12)
        c = ws.cell(row=row, column=1, value=label)
        c.font = BODY_ITALIC
        c.alignment = Alignment(horizontal="left", vertical="center")
        ws.row_dimensions[row].height = 18
        row += 1
        rows = list(conn.execute("""
            SELECT h.ticker, h.issuer, h.value_k, h.pct_book,
                   us.mcap_m, us.mcap_bucket, us.smart_money_n, us.activist_max_pct,
                   us.insider_cluster_dollars_m, us.ev_ebitda, us.pb_ratio, tm.name
            FROM fund_13f_holdings h
            LEFT JOIN ticker_meta tm ON tm.ticker = h.ticker
            LEFT JOIN unified_signal us ON us.ticker = h.ticker
            WHERE h.fund LIKE ?
            ORDER BY h.value_k DESC LIMIT 20""", (like,)))
        out = []
        for r in rows:
            cluster_mark = "yes" if (r[8] and r[8] > 0) else ""
            out.append([r[0] or "-", (r[1] or ""),
                        round((r[2] or 0)/1000, 1) if r[2] else "",
                        round(r[3] or 0, 2),
                        r[4] or "", r[5] or "",
                        r[6] or 0, round(r[7] or 0, 1),
                        cluster_mark,
                        round(r[9], 1) if r[9] is not None else "",
                        round(r[10], 2) if r[10] is not None else "",
                        (r[11] or "")])
        write_table_rows(ws, out, row)
        for ridx in range(row, row + len(out)):
            ws.cell(row=ridx, column=3).number_format = NUMFMT_NUM
            ws.cell(row=ridx, column=4).number_format = NUMFMT_PCT
            ws.cell(row=ridx, column=5).number_format = NUMFMT_MCAP
            ws.cell(row=ridx, column=8).number_format = NUMFMT_PCT
            ws.cell(row=ridx, column=10).number_format = '0.0"x"'
            ws.cell(row=ridx, column=11).number_format = '0.00"x"'
        row += len(out) + 1

    row += 1
    write_section_heading(ws, row, "Shared overlap — held by both funds", 12)
    row += 1
    hdr2 = ["Ticker","Issuer","Bill IV %","Bill III %","Combined %","Mcap","Bucket","13F","Act %","EV/EBITDA","P/B","Name"]
    write_table_header(ws, row, hdr2)
    row += 1
    overlap = list(conn.execute("""
        SELECT h4.ticker, h4.issuer, h4.pct_book pct4, h3.pct_book pct3,
               (h4.pct_book + h3.pct_book) AS combined,
               us.mcap_m, us.mcap_bucket, us.smart_money_n, us.activist_max_pct,
               us.ev_ebitda, us.pb_ratio, tm.name
        FROM fund_13f_holdings h4
        JOIN fund_13f_holdings h3 ON h3.ticker = h4.ticker
        LEFT JOIN ticker_meta tm ON tm.ticker = h4.ticker
        LEFT JOIN unified_signal us ON us.ticker = h4.ticker
        WHERE h4.fund LIKE 'Miller Value%' AND h3.fund LIKE 'Patient Capital%'
          AND h4.ticker IS NOT NULL
        ORDER BY combined DESC"""))
    out = []
    for r in overlap:
        out.append([r[0], (r[1] or ""),
                    round(r[2] or 0, 2),
                    round(r[3] or 0, 2),
                    round(r[4] or 0, 2),
                    r[5] or "", r[6] or "",
                    r[7] or 0, round(r[8] or 0, 1),
                    round(r[9], 1) if r[9] is not None else "",
                    round(r[10], 2) if r[10] is not None else "",
                    (r[11] or "")])
    write_table_rows(ws, out, row)
    for ridx in range(row, row + len(out)):
        ws.cell(row=ridx, column=3).number_format = NUMFMT_PCT
        ws.cell(row=ridx, column=4).number_format = NUMFMT_PCT
        ws.cell(row=ridx, column=5).number_format = NUMFMT_PCT
        ws.cell(row=ridx, column=6).number_format = NUMFMT_MCAP    # mcap
        ws.cell(row=ridx, column=9).number_format = NUMFMT_PCT
        ws.cell(row=ridx, column=10).number_format = '0.0"x"'
        ws.cell(row=ridx, column=11).number_format = '0.00"x"'
    ws.freeze_panes = "B6"
    autosize(ws)
    ws.column_dimensions["A"].width = 8

def sheet_best_ideas(wb, conn):
    """Composite shortlist — names that fire on MULTIPLE independent signals at
    once: cheap valuation, below smart-money entry, recent insider buying,
    activist / concentration, and a live catalyst. Each row carries a plain-text
    rationale. Ex-biotech, ex-mega; small enough to multiply (< $10B)."""
    ws = wb.create_sheet("Best Ideas")
    ws.sheet_view.showGridLines = False
    write_title(ws, "Best Ideas — multi-signal shortlist",
                "Names firing on several independent signals at once (cheap + below entry + insider buying + activist/concentration + catalyst). Ranked by a blended idea score; rationale in the Why column. Ex-biotech, ex-mega, < $10B.", 18)
    hdr = ["Ticker", "Idea Score", "# Signals", "Base Score", "Asym", "Mcap", "Bucket",
           "EV/EBITDA", "P/B", "Entry", "vs Entry %", "F4 ≤30d $M", "Act %",
           "Catalyst", "Name", "Why", "Industry", "Business"]
    write_table_header(ws, 4, hdr)
    rows = list(conn.execute("""
        SELECT us.ticker, us.score, us.asymmetry_score, us.mcap_m, us.mcap_bucket,
               us.ev_ebitda, us.pb_ratio, us.entry_bucket, us.vs_entry_pct,
               us.form4_buy_30d_m, us.insider_cluster_dollars_m,
               us.activist_max_pct, us.max_pct_book, us.n_funds_5pct_book,
               us.smart_money_n, us.s3_new, us.s4_add, us.activist_filings,
               us.cat8k_ma, us.cat8k_ctrl, tm.name, tm.sic_description
        FROM unified_signal us
        LEFT JOIN ticker_meta tm ON tm.ticker = us.ticker
        WHERE us.mcap_bucket IN ('nano','micro','small','mid') AND us.sec_type='common'"""))
    scored = []
    for r in rows:
        (tk, score, asym, mcap, bucket, ev, pb, eb, vse, f4_30, clu,
         actpct, maxpb, n5, smn, s3, s4, actf, c_ma, c_ctrl, name, sic) = r
        if tk in ETFs or tk in MEGA or is_biotech(sic): continue
        cheap   = (ev is not None and 0 < ev <= 12) or (pb is not None and 0 < pb < 2)
        below   = eb == "BELOW_ENTRY"
        insider = (f4_30 or 0) > 0 or (clu or 0) > 0
        activ   = (actpct or 0) >= 5 or (maxpb or 0) >= 5 or (n5 or 0) >= 1
        catal   = bool(c_ma) or bool(c_ctrl)
        backing = (smn or 0) >= 2 or (actf or 0) > 0 or ((s3 or 0) + (s4 or 0)) >= 1
        n_flags = sum([cheap, below, insider, activ, catal])
        if n_flags < 2 or not backing: continue
        idea = round((asym or 0) + 0.4 * (score or 0) + 4 * n_flags, 1)
        # plain-text rationale
        why = []
        if smn: why.append(f"{smn}×13F")
        if s3:  why.append(f"{s3} new")
        if s4:  why.append(f"{s4} add")
        if ev is not None and 0 < ev <= 12: why.append(f"{ev:.1f}x EV/EBITDA")
        if pb is not None and 0 < pb < 2:   why.append(f"{pb:.1f} P/B")
        if below and vse: why.append(f"{vse:.0f}% vs entry")
        if (f4_30 or 0) > 0: why.append(f"insider ${f4_30:.1f}M ≤30d")
        if (clu or 0) > 0:   why.append(f"cluster ${clu:.1f}M")
        if (actpct or 0) >= 5: why.append(f"activist {actpct:.0f}%")
        if c_ma:   why.append("M&A")
        if c_ctrl: why.append("control")
        cat = []
        if c_ma: cat.append("M&A")
        if c_ctrl: cat.append("CTRL")
        if (clu or 0) > 0: cat.append("clstr")
        scored.append([tk, idea, n_flags, round(score or 0, 1), round(asym or 0, 1),
                       mcap or "", bucket or "",
                       round(ev, 1) if ev is not None else "",
                       round(pb, 2) if pb is not None else "",
                       ("below" if below else "near" if eb == "NEAR_ENTRY"
                        else "above" if eb and "ABOVE" in eb else ""),
                       round(vse, 1) if vse else "",
                       round(f4_30, 2) if (f4_30 or 0) > 0 else "",
                       round(actpct or 0, 1),
                       " ".join(cat), (name or ""), " · ".join(why),
                       *desc_for(conn, tk)])
    scored.sort(key=lambda x: -x[1])
    out = scored[:90]
    write_table_rows(ws, out, 5)
    for ridx in range(5, 5 + len(out)):
        ws.cell(row=ridx, column=6).number_format = NUMFMT_MCAP
        ws.cell(row=ridx, column=8).number_format = '0.0"x"'
        ws.cell(row=ridx, column=9).number_format = '0.00"x"'
        ws.cell(row=ridx, column=11).number_format = NUMFMT_PCT
        ws.cell(row=ridx, column=12).number_format = NUMFMT_M_TO_B
        ws.cell(row=ridx, column=13).number_format = NUMFMT_PCT
    ws.freeze_panes = "B5"
    autosize(ws)
    ws.column_dimensions["A"].width = 8
    ws.column_dimensions["P"].width = 76                     # Why
    ws.column_dimensions[get_column_letter(17)].width = 24   # Industry
    ws.column_dimensions[get_column_letter(18)].width = 80   # Business

def sheet_adversarial_review(wb, conn):
    """Surface the 52-agent adversarial review of the top picks — a red-team that
    stress-tested each headline name across data-quality, thesis-soundness and
    recency lenses, separating confirmed setups from data-inflated artifacts."""
    import json
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "data", "adversarial_review.json")
    if not os.path.exists(path):
        return
    data = json.load(open(path))
    ws = wb.create_sheet("Adversarial Review")
    ws.sheet_view.showGridLines = False
    write_title(ws, f"Adversarial Review — ARCHIVE of {data.get('asof')}: a red-team of the then-top picks",
                f"Kept for its reasoning, not as a current list: scores, holdings and prices have moved since "
                f"{data.get('asof')} (today's scores are on every other sheet). A {data.get('agent_count','multi')}-agent "
                f"stress test of the then-highest-ranked names across three lenses (data quality · thesis soundness · "
                f"recency/news), separating confirmed setups from data-inflated artifacts.", 4)
    row = 4
    write_section_heading(ws, row, "Synthesis — confirmed vs data-inflated", 4)
    row += 1
    for raw in data.get("synthesis", "").split("\n"):
        line = raw.strip()
        ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=4)
        if not line:
            ws.row_dimensions[row].height = 6
            row += 1
            continue
        is_head = line.startswith("#")
        clean = (line.replace("**", "").replace("### ", "").replace("## ", "")
                     .replace("# ", "").lstrip("- ").strip())
        if line.startswith("- "):
            clean = "•  " + clean
        c = ws.cell(row=row, column=1, value=clean)
        c.font = SECTION_FONT if is_head else BODY_FONT
        c.alignment = Alignment(horizontal="left", vertical="top", wrap_text=True)
        ws.row_dimensions[row].height = max(16, 15 * (1 + len(clean) // 105))
        row += 1
    row += 1
    write_section_heading(ws, row, "Per-ticker lens detail", 4)
    row += 1
    LENS = {"data-quality": "Data Quality", "thesis-soundness": "Thesis",
            "recency-and-news": "Recency/News"}
    write_table_header(ws, row, ["Ticker", "Score*", "Lens", "Assessment"])
    row += 1
    for rev in data.get("reviews", []):
        first = True
        for L in rev.get("lenses", []):
            txt = L.get("text", "").strip()
            ws.cell(row=row, column=1, value=rev["ticker"] if first else "").font = TICKER_FONT
            sc = ws.cell(row=row, column=2, value=rev.get("score_asof") if first else "")
            sc.font = BODY_FONT; sc.alignment = Alignment(horizontal="right", vertical="top")
            lc = ws.cell(row=row, column=3, value=LENS.get(L.get("lens"), L.get("lens")))
            lc.font = BODY_FONT; lc.alignment = Alignment(horizontal="left", vertical="top")
            ac = ws.cell(row=row, column=4, value=txt)
            ac.font = BODY_FONT
            ac.alignment = Alignment(horizontal="left", vertical="top", wrap_text=True)
            ws.cell(row=row, column=1).alignment = Alignment(horizontal="left", vertical="top")
            ws.row_dimensions[row].height = max(28, 14 * (1 + len(txt) // 95))
            first = False
            row += 1
    ws.column_dimensions["A"].width = 9
    ws.column_dimensions["B"].width = 8
    ws.column_dimensions["C"].width = 14
    ws.column_dimensions["D"].width = 120
    ws.freeze_panes = "A4"

def _one_liner(s, limit=None):
    """The full first sentence of the business summary — never cut, no
    ellipsis (shared rule: _style_bw.first_sentence)."""
    return first_sentence(s)

_DESC_CACHE = None
def desc_for(conn, ticker):
    """(industry, one-line business summary) for a ticker — memoized so every
    sheet can append a self-explanatory description per row."""
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
            # summaries open with "<Company Name>, together with its
            # subsidiaries," — the Name column already says that, so the
            # Business cell starts at what the company does (still a sentence)
            _DESC_CACHE[r[0]] = ((r[1] or ""), business_line(r[2], r[3], r[4]))
        # names outside the score table (the global funds' local listings)
        # still describe themselves from their FMP profile
        for tk, ind, summ, nm in conn.execute(
                "SELECT ticker, industry, business_summary, long_name FROM ticker_yf"):
            if tk in _DESC_CACHE or not (ind or summ):
                continue
            _DESC_CACHE[tk] = ((ind or ""), business_line(summ, nm))
    return _DESC_CACHE.get(ticker, ("", ""))

def sheet_ticker_reference(wb, conn):
    """Glossary: every ticker with name, sector, industry, and a short business
    summary — so any symbol in the workbook can be looked up. Sorted A–Z."""
    ws = wb.create_sheet("Ticker Reference")
    ws.sheet_view.showGridLines = False
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
        # Business Summary is the LAST column, so full text overflows and reads
        # in full — show the whole summary (not a truncated one-liner).
        summ = complete_text(r[5])
        out.append([r[0], (r[1] or ""), (r[2] or ""),
                    (r[3] or ""), r[4] or "", summ])
    write_table_rows(ws, out, 5)
    for ridx in range(5, 5 + len(out)):
        ws.cell(row=ridx, column=5).number_format = NUMFMT_MCAP
    ws.freeze_panes = "B5"
    autosize(ws)
    ws.column_dimensions["A"].width = 9
    ws.column_dimensions["B"].width = 40
    ws.column_dimensions["C"].width = 34
    ws.column_dimensions["D"].width = 30
    ws.column_dimensions["E"].width = 12
    ws.column_dimensions["F"].width = 120

TAB_COLORS = {
    # Navigation / meta — lightest
    "README":          "F2F2F2",
    "Legend":          "F2F2F2",
    "Fund Coverage":   "F2F2F2",
    "All Funds":       "F2F2F2",
    # Universe ranking — darkest
    "Action Dashboard": "1A1A1A",
    "Convergence":     "1A1A1A",
    "Best Ideas":      "262626",
    "Adversarial Review": "262626",
    "Top 100":         "262626",
    "Non-Biotech Top 100": "262626",
    "Asymmetry":       "262626",
    # Size buckets — mid-dark gradient
    "Nano (<$50M)":            "404040",
    "Micro ($50M–$300M)":      "595959",
    "Small ($300M–$2B)":       "595959",
    "Mid ($2B–$10B)":          "595959",
    "Large ($10B–$200B)":      "595959",
    "Mega (>$200B)":           "595959",
    # Signal sheets — mid
    "Material + New":          "808080",
    "Who's Buying":            "808080",
    "Revealed Preference":     "808080",
    "Activist 10+":            "808080",
    "Insider Buys ≤30d":       "808080",
    "Insider F4 Buys":         "808080",
    "Insider Clusters":        "808080",
    "Congress Trades":         "808080",
    "Catalysts 8-K":           "808080",
    # Registered funds (N-PORT) — one block
    "N-PORT Funds":            "6F6F6F",
    "N-PORT Holdings":         "6F6F6F",
    "N-PORT Changes":          "6F6F6F",
    "N-PORT Global Consensus": "6F6F6F",
    # Setup sheets — mid-light
    "In The Money":            "A6A6A6",
    "Valuation":               "A6A6A6",
    "Global Picks":            "A6A6A6",
    "Bill Miller":             "A6A6A6",
    # Reference / support — lighter
    "Unknown Mcap":            "BFBFBF",
    "All Positions":           "BFBFBF",
    "Ticker Reference":        "BFBFBF",
}

def main():
    conn = sqlite3.connect(DB)
    try:                                  # ensure momentum/drawdown are fresh
        import build_price_stats; build_price_stats.run()
    except Exception as e:
        print(f"  (price_stats skipped: {e})")
    wb = openpyxl.Workbook()
    if "Sheet" in wb.sheetnames:
        wb.remove(wb["Sheet"])

    sheet_readme(wb, conn)
    write_legend_sheet(wb, 1)
    _EVENTS.update(events_by_ticker(conn))
    _SHORTS.update(short_data(conn)[0])
    sheet_what_changed(wb, conn)          # new since the last delivered build (sheet 2)
    sheet_action_dashboard(wb, conn)      # front-page scannable summary
    sheet_convergence(wb, conn)           # multi-signal convergence matrix
    sheet_dossier(wb, conn)               # per-ticker consolidated view
    if _has_prior(conn):
        sheet_qoq_change(wb, conn)        # quarter-over-quarter accumulation/distribution
    sheet_best_ideas(wb, conn)
    sheet_adversarial_review(wb, conn)
    write_signal_sheet(wb, conn, "Top 100",
        where_extra="AND us.mcap_bucket != 'unknown'", limit=140,
        subtitle="The 140 highest scores across the universe (the tab's name dates from a shorter list). ETFs and "
                 "the ten largest US mega-caps (AAPL, MSFT, NVDA, AMZN, GOOGL/GOOG, META, TSLA, BRK) left out: "
                 "they are on the Mega sheet.")
    for bucket, title in [("nano","Nano (<$50M)"),
                          ("micro","Micro ($50M–$300M)"),
                          ("small","Small ($300M–$2B)"),
                          ("mid","Mid ($2B–$10B)"),
                          ("large","Large ($10B–$200B)"),
                          ("mega","Mega (>$200B)")]:
        write_signal_sheet(wb, conn, title,
            where_extra=f"AND us.mcap_bucket = '{bucket}'", limit=(200 if bucket == "mega" else 60),
            include_mega=(bucket == "mega"),
            subtitle=(f"Top {bucket}-caps by score. ETFs left out"
                      + ("; the ten largest US mega-caps the other ranked sheets leave out are all here."
                         if bucket == "mega" else ".")))
    sheet_best_in_bucket(wb, conn)
    sheet_industries(wb, conn)            # Industry Index + Industry Detail (FMP industries)
    write_signal_sheet(wb, conn, "Material + New",
        where_extra="AND (us.s3_new + us.s4_add) >= 2 AND us.mcap_bucket != 'unknown'",
        limit=80,
        subtitle="Funds building: S3 + S4 of 2 or more — funds that opened (S3) or added 25%+ to (S4) a position in "
                 "the latest 13F quarter, weighted by focus (research notes for funds without a current 13F). "
                 "Who they are: the Who's Buying sheet.")
    sheet_whos_buying(wb, conn)
    sheet_track_records(wb, conn)         # how each manager's new buys did since its 13F
    sheet_activist(wb, conn)
    sheet_broker_radar(wb, conn)
    sheet_latent_ownership(wb, conn)
    sheet_nport_funds(wb, conn)           # N-PORT block: which funds,
    sheet_nport_holdings(wb, conn)        #   what each holds,
    sheet_nport_changes(wb, conn)         #   what they changed,
    sheet_nport_consensus(wb, conn)       #   where they agree outside the US
    sheet_insider_recent(wb, conn)
    sheet_insider_f4(wb, conn)
    sheet_clusters(wb, conn)
    sheet_congress(wb, conn)
    write_signal_sheet(wb, conn, "Non-Biotech Top 100",
        where_extra="AND us.mcap_bucket != 'unknown'", limit=140,
        subtitle="The 140 highest scores without biotech, ETFs or the ten largest US mega-caps.",
        exclude_biotech=True)
    sheet_in_the_money(wb, conn)
    sheet_asymmetry(wb, conn)
    sheet_revealed_pref(wb, conn)
    sheet_valuation(wb, conn)
    sheet_catalysts(wb, conn)
    sheet_special_situations(wb, conn)    # proxy fights, spin-offs coming, tenders (SEC filings)
    sheet_short_interest(wb, conn)        # FINRA short interest against fund conviction
    sheet_global_picks(wb, conn)
    sheet_bill_miller(wb, conn)
    sheet_unknown(wb, conn)
    sheet_all_holdings_consolidated(wb, conn)
    sheet_fund_coverage(wb, conn)
    sheet_all_funds(wb, conn)
    sheet_ticker_reference(wb, conn)

    # AutoFilter on single-table sheets (header at row 4) — lets the reader
    # sort / filter by any column in Excel. Multi-table sheets are excluded.
    AF_SHEETS = {
        "Best Ideas",
        "Top 100", "Nano (<$50M)", "Micro ($50M–$300M)", "Small ($300M–$2B)",
        "Mid ($2B–$10B)", "Large ($10B–$200B)", "Mega (>$200B)", "Material + New", "Activist 10+", "Insider Buys ≤30d",
        "Insider F4 Buys", "Insider Clusters", "Non-Biotech Top 100", "In The Money",
        "Asymmetry", "Revealed Preference", "Valuation", "Catalysts 8-K",
        "N-PORT Changes", "N-PORT Global Consensus",
        "Global Picks", "Unknown Mcap", "All Positions", "All Funds",
        "Fund Coverage", "Ticker Reference",
    }
    for sn in AF_SHEETS:
        if sn in wb.sheetnames:
            ws = wb[sn]
            if ws.max_row > 4:
                ws.auto_filter.ref = f"A4:{get_column_letter(ws.max_column)}{ws.max_row}"

    # Tab colour-coding — grayscale tones by theme
    for sname, color in TAB_COLORS.items():
        if sname in wb.sheetnames:
            wb[sname].sheet_properties.tabColor = color

    add_grouped_contents(wb["README"], SHEET_GUIDE, wb.sheetnames)
    set_print_layout(wb)

    # every ticker table carries EV/EBITDA, P/E, P/B and P/TB side by side
    add_valuation_columns(wb, valuation_lookup(conn))
    wb.save(OUT)
    print(f"wrote {OUT}")
    print(f"sheets: {wb.sheetnames}")

if __name__ == "__main__":
    main()
