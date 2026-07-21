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
    write_title, write_section_heading, write_table_header, write_table_rows,
    autosize, write_legend_sheet, add_contents_index, set_print_layout,
    NUMFMT_USD, NUMFMT_PCT, NUMFMT_NUM, NUMFMT_INT, NUMFMT_USD2,
    NUMFMT_MCAP, NUMFMT_M_TO_B,
    TNR, SIZE_BODY, BODY_FONT, BODY_ITALIC, SECTION_FONT, TICKER_FONT, MONO_FONT,
    BLACK, ROW_BORDER,
)
from openpyxl.styles import Font, Alignment, Border, Side

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

SIG_HDR = ["Ticker","Score","Why","Mcap","ADV $M","Bucket","13F","S1","S3","S4","Act %",
           "pB Max","pB ≥5%","13D","Clu $M",
           "F4 Buy 180d","F4 Buy ≤30d","F4 Sell 180d","F4 Sell ≤30d",
           "EV/EBITDA","P/B",
           "Entry","vs Entry %","Anchor $",
           "Name","Sector","Px","Industry","Business"]

# components string -> readable "why" (top-3 contributing terms). Turns an opaque
# 90+ score into its drivers, e.g. "s1 24 · pb5 18 · s4 14".
_WHY_LABEL = {"sm": "sm", "s3*": "s3", "s4*": "s4", "s1*": "s1", "act": "act",
              "pb_max": "pb", "pb_n5": "pb5", "clust": "clu", "clust$": "clu$",
              "f4buy": "f4buy", "f4rec+": "f4rec", "f4sell": "f4sell",
              "f4recsell": "f4sell30", "mic": "micro", "er": "er", "entry": "entry",
              "cat8k": "8k"}
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
        us.expected_return_pct, tm.name, tm.sic_description, tm.price,
        COALESCE(yf.industry, tm.industry, tm.sic_description), yf.business_summary,
        tm.adv_3m_usd_m, us.components
        FROM unified_signal us
        LEFT JOIN ticker_meta tm ON tm.ticker = us.ticker
        LEFT JOIN ticker_yf  yf ON yf.ticker = us.ticker
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
        round(r[21] or 0, 2) if r[21] else "",   # anchor px
        (r[23] or "")[:38],                      # Name
        (r[24] or "")[:32],                      # Sector
        round(r[25] or 0, 2) if r[25] else "",   # Px
        (r[26] or "")[:26],            # Industry
        _one_liner(r[27], 90),         # Business (one-line summary)
    ]

def format_signal_row(ws, ridx):
    """Apply number formats to a signal row. Columns (1-idx):
    1 Ticker 2 Score 3 Why 4 Mcap 5 ADV$M 6 Bucket 7 13F 8 S1 9 S3 10 S4 11 Act%
    12 pBMax 13 pB≥5% 14 13D 15 Clu$M 16 F4B180 17 F4B30 18 F4S180 19 F4S30
    20 EV/EBITDA 21 P/B 22 Entry 23 vsEntry% 24 Anchor$ 25 Name 26 Sector 27 Px"""
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
    ws.cell(row=ridx, column=24).number_format = NUMFMT_USD2   # anchor px
    ws.cell(row=ridx, column=27).number_format = NUMFMT_USD2   # px

def add_signal_heatmap(ws, first_row, last_row):
    """Monochrome conditional-format heatmaps on the key decision columns so a
    reader can eyeball the cheap-below-entry-high-score corner without reading
    every cell. Score/vs-entry darker = more attractive; valuation cheaper=darker."""
    from openpyxl.formatting.rule import ColorScaleRule, DataBarRule
    if last_row < first_row:
        return
    rng = lambda col: f"{col}{first_row}:{col}{last_row}"
    WHITE, GREY, DARK = "FFFFFF", "BFBFBF", "595959"
    # Score (col B): higher = darker (more attractive)
    ws.conditional_formatting.add(rng("B"),
        ColorScaleRule(start_type="min", start_color=WHITE, end_type="max", end_color=DARK))
    ws.conditional_formatting.add(rng("B"), DataBarRule(start_type="min", end_type="max", color="A6A6A6"))
    # EV/EBITDA (T) and P/B (U): cheaper (lower) = darker
    for col in ("T", "U"):
        ws.conditional_formatting.add(rng(col),
            ColorScaleRule(start_type="min", start_color=DARK, end_type="max", end_color=WHITE))
    # vs Entry % (W): more below entry (more negative) = darker
    ws.conditional_formatting.add(rng("W"),
        ColorScaleRule(start_type="min", start_color=DARK, mid_type="num", mid_value=0, mid_color=GREY,
                       end_type="max", end_color=WHITE))

# ---- sheets -----------------------------------------------------------------
def sheet_readme(wb, conn):
    ws = wb.create_sheet("README", 0)
    ws.sheet_view.showGridLines = False
    n_tk = conn.execute("SELECT COUNT(*) FROM unified_signal").fetchone()[0]
    n_fd = conn.execute("SELECT COUNT(DISTINCT fund) FROM fund_meta").fetchone()[0]
    n_hold = conn.execute("SELECT COUNT(*) FROM fund_13f_holdings").fetchone()[0]
    n_13f_funds = conn.execute("SELECT COUNT(DISTINCT fund) FROM fund_13f_holdings").fetchone()[0]
    write_title(ws,
        "Cyclepapa — Universe Analysis",
        f"A data-driven ranking of the smart-money universe ({n_tk:,} tickers, {n_fd} funds, primary EDGAR sources).",
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

    rows = [
        ("",),
        ("DATA AS-OF (read before trusting any number)",),
        (f"13F holdings   position as-of ~{f13_asof}  (latest filing {f13_filed}; SEC allows +45d, so 'smart money'",),
        ("    reflects quarter-END positions and can be up to ~3-4 months old — a fund may have since exited).",),
        (f"Form 4 insider {f4_date}     ·   13D/G activist {d13_date}     ·   8-K catalysts {c8_date}   (near-current)",),
        (f"Valuations     {yf_date}     (Yahoo; price/mcap current to within days)",),
        ("    → The 13F-derived columns (smart_money, section counts, %book) are the LAGGED layer; the Form 4 /",),
        ("      13D / 8-K / valuation columns are current. Don't read a 13F consensus as a live position.",),
        ("",),
        ("Universe",),
        (f"{n_tk:,} tickers — the union of fund_13f_holdings, fund_positions, and holder_13d.subject_ticker.",),
        (f"{n_fd} funds in fund_meta; ETFs/preferreds/warrants are classified (sec_type) and excluded from pick tables.",),
        ("",),
        ("Score formula",),
        ("score = log(smart_money) × 2          smart_money = CONVICTION-WEIGHTED 13F holders",),
        ("    The '13F' column is NOT a raw holder count. Each fund's vote is weighted",),
        ("    min(1, 75 / n_positions): a focused book (<=75 names) counts fully, while",),
        ("    pod-shops / quants are heavily downweighted — Citadel (6,687 names) ×0.011,",),
        ("    Millennium ×0.019, AQR ×0.020 — so statistical-arb breadth can't fake consensus.",),
        ("      + 3.0 × n_funds_section3        new major positions",),
        ("      + 1.5 × n_funds_section4        existing material adds",),
        ("      + 2.0 × n_funds_section1        top picks",),
        ("      + 0.5 × activist_max_pct        13D/G concentration",),
        ("      + 0.6 × max_pct_book            single-fund concentration",),
        ("      + 1.5 × n_funds_5pct_book       concentration cluster",),
        ("      + cluster_step(n_insiders)      live insider buy cluster",),
        ("      + log(form4_buys + 1) × 2       cumulative open-market buying",),
        ("      − log(form4_sells + 1) × 1.5    insider sells (counter-signal)",),
        ("      + micro_bonus                   +5 if <$300M, +3 if <$2B",),
        ("      + 0.5 × expected_return_pct     base-rate weighted excess",),
        ("",),
        ("Data sources",),
        (f"fund_13f_holdings     {n_hold:,} rows from SEC 13F-HR XML across {n_13f_funds} funds",),
        ("fund_positions        6,748 rows from XLSX research-team classifications",),
        ("holder_13d            current SC 13D/G filings via efts.sec.gov full-text search",),
        ("form4_transactions    P-code open-market buys + S-code sells, ≤180d",),
        ("insider_clusters      live ≤180d clusters",),
        ("catalysts_8k          8-K filings with parsed Item codes",),
        ("ticker_meta           Yahoo chart price + SEC XBRL shares-out (76% mcap coverage)",),
        ("",),
        ("Filters",),
        ("ex-ETF — SPY, QQQ, IWM, sector ETFs removed for noise reduction.",),
        ("ex-Mega — top-10 mega-caps removed where noted.",),
        ("ex-Biotech — SIC matching pharmaceutic / biological / therapeutic excluded where noted.",),
        ("",),
        ("Methodology note",),
        ("This is a pure SQL aggregation. No curated ticker lists, no editorial picks, no memory.",),
        ("The score formula is shared between universe and style workbooks. Re-rank by editing pipeline/unified_score.py.",),
    ]
    for i, r in enumerate(rows, 4):
        c = ws.cell(row=i, column=1, value=r[0])
        ws.row_dimensions[i].height = 18
        if not r[0].strip(): continue
        if r[0][:6] not in ("score ", "      "):
            # section heading test: short capitalized phrases
            if r[0] in ("Universe","Score formula","Data sources","Filters","Methodology note"):
                c.font = SECTION_FONT
            else:
                c.font = BODY_FONT
        else:
            c.font = MONO_FONT

def write_signal_sheet(wb, conn, name, where_extra="", limit=200, subtitle="", exclude_biotech=False):
    ws = wb.create_sheet(name)
    ws.sheet_view.showGridLines = False
    write_table_header(ws, 4, SIG_HDR)
    # Fetch a generous superset, then apply the ETF/mega/biotech exclusions in
    # Python and truncate to `limit` — so the exclusions actually reduce the list
    # (the old Non-Biotech sheet passed limit=400 and never filtered biotech).
    fetch = (limit * 4) if limit else None
    rows = get_signal_rows(conn, where_extra=where_extra, limit=fetch)
    rows = [r for r in rows if r[0] not in ETFs and r[0] not in MEGA]
    if exclude_biotech:
        rows = [r for r in rows if not is_biotech(r[24])]   # r[24] = sic_description
    matched = len(rows)
    if limit and matched > limit:
        rows = rows[:limit]
        subtitle = (subtitle + "  " if subtitle else "") + f"[showing top {limit} of {matched} matching names]"
    # Transparency: if the LIMIT truncates, say so in the subtitle rather than
    # silently showing a subset.
    write_title(ws, name, subtitle, len(SIG_HDR))
    out = [signal_row_to_cells(r) for r in rows]
    write_table_rows(ws, out, 5)
    for ridx in range(5, 5 + len(out)):
        format_signal_row(ws, ridx)
    add_signal_heatmap(ws, 5, 4 + len(out))
    ws.freeze_panes = "B5"
    if out:
        ws.auto_filter.ref = f"A4:{get_column_letter(len(SIG_HDR))}{4 + len(out)}"
    autosize(ws)
    # ticker col narrower; Business (last col) wide for the one-line summary
    ws.column_dimensions["A"].width = 8
    ws.column_dimensions["C"].width = 22  # Why
    ws.column_dimensions[get_column_letter(len(SIG_HDR))].width = 80
    ws.column_dimensions[get_column_letter(len(SIG_HDR) - 1)].width = 24  # Industry

def sheet_whos_buying(wb, conn):
    """The NAMES behind the s3/s4 counts — which specific funds are initiating new
    positions and materially adding. Counts tell you 'how many'; this tells you
    'who', which is the part that actually matters (a Baupost new position reads
    very differently from an anonymous count of 3)."""
    ws = wb.create_sheet("Who's Buying")
    ws.sheet_view.showGridLines = False
    write_title(ws, "Who's Buying — the funds behind the New / Add counts",
                "Per name: which funds are INITIATING (S3 new major position) and ADDING (S4 material add), from fund_positions. De-duplicated by canonical manager.", 7)
    hdr = ["Ticker", "Company", "Score", "# New", "New Initiators (funds)", "# Add", "Material Adders (funds)"]
    write_table_header(ws, 4, hdr)
    # canonical-manager de-dupe so a fund's name variants don't list twice
    from _canon import canon
    rows = conn.execute("""
        SELECT us.ticker, us.name, us.score, us.s3_new, us.s4_add
        FROM unified_signal us
        WHERE us.sec_type='common' AND (us.s3_new > 0 OR us.s4_add > 0)
        ORDER BY (us.s3_new*2 + us.s4_add) DESC, us.score DESC LIMIT 200""").fetchall()
    def funds_for(tk, sec):
        seen, out = set(), []
        for (f,) in conn.execute("""SELECT DISTINCT fund FROM fund_positions
                WHERE ticker=? AND section=? AND ticker IS NOT NULL""", (tk, sec)):
            c = canon(f)
            if c in seen:
                continue
            seen.add(c)
            # display the raw fund but trimmed of the trailing manager parenthetical
            out.append(re.sub(r"\s*\(.*$", "", f).strip()[:26])
        return out
    out = []
    for tk, name, score, s3, s4 in rows:
        new_f = funds_for(tk, 3)
        add_f = funds_for(tk, 4)
        out.append([tk, (name or "")[:24], round(score or 0, 1),
                    len(new_f), ", ".join(new_f)[:70],
                    len(add_f), ", ".join(add_f)[:70]])
    write_table_rows(ws, out, 5, ticker_col=1)
    ws.freeze_panes = "B5"
    autosize(ws)
    ws.column_dimensions["E"].width = 60
    ws.column_dimensions["G"].width = 60

def sheet_best_in_bucket(wb, conn, per_bucket=20):
    """Top names WITHIN each size bucket. The flat Top-100 is ~44% large-cap
    because raw scores favor names held by many funds; ranking within-bucket
    surfaces the best small/micro/mid ideas that the mega-caps otherwise bury.
    """
    ws = wb.create_sheet("Best in Bucket")
    ws.sheet_view.showGridLines = False
    write_title(ws, "Best in Bucket — top ideas within each size class",
                "Score is cross-sectionally biased toward large caps; this ranks the best names within nano/micro/small/mid/large separately.",
                len(SIG_HDR))
    row = 4
    for bucket, label in [("nano", "Nano (<$50M)"), ("micro", "Micro ($50–300M)"),
                          ("small", "Small ($300M–2B)"), ("mid", "Mid ($2–10B)"),
                          ("large", "Large (>$10B)")]:
        write_section_heading(ws, row, label, len(SIG_HDR)); row += 1
        write_table_header(ws, row, SIG_HDR); row += 1
        rows = get_signal_rows(conn, where_extra=f"AND us.mcap_bucket='{bucket}'", limit=per_bucket)
        rows = [r for r in rows if r[0] not in ETFs and r[0] not in MEGA]
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
        filer = re.sub(r"\s*\(.*$", "", (r[11] or "")).strip()[:26]
        out.append([r[0], typ, filer, round(r[3] or 0, 1),
                    r[1] or "", r[2] or "",
                    r[4] or 0, r[5] or 0, round(r[6] or 0, 1),
                    round(r[7], 1) if r[7] is not None else "",
                    round(r[8], 2) if r[8] is not None else "",
                    (r[9] or "")[:38], (r[10] or "")[:32]])
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

def sheet_insider_f4(wb, conn):
    """Insider buying ranked by RECENCY-weighted total. ≤30d buys shown separately."""
    ws = wb.create_sheet("Insider F4 Buys")
    ws.sheet_view.showGridLines = False
    write_title(ws, "Form 4 Insider Buying — recency weighted",
                "Open-market P-code buys. ≤30d weight 1.0; 31–60 d 0.6; 61–120 d 0.3; 121–180 d 0.1. Sorted by recency-weighted dollars.", 13)
    hdr = ["Ticker","Weighted $M","≤30d $M","31-60 $M","61-180 $M","# Buyers","Avg Px","Mcap","Bucket","13F","EV/EBITDA","P/B","Name"]
    write_table_header(ws, 4, hdr)
    rows = list(conn.execute("""
        SELECT f.ticker,
            SUM(CASE WHEN julianday('now')-julianday(f.trans_date) <= 30  THEN f.shares*f.price ELSE 0 END)/1e6 AS d_30,
            SUM(CASE WHEN julianday('now')-julianday(f.trans_date) BETWEEN 31 AND 60  THEN f.shares*f.price ELSE 0 END)/1e6 AS d_60,
            SUM(CASE WHEN julianday('now')-julianday(f.trans_date) > 60   THEN f.shares*f.price ELSE 0 END)/1e6 AS d_180,
            COUNT(DISTINCT f.owner), AVG(f.price),
            tm.mcap_m, us.mcap_bucket, us.smart_money_n,
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
        out.append([r[0], round(weighted, 1),
                    round(d30, 1) if d30 else "",
                    round(d60, 1) if d60 else "",
                    round(d180, 1) if d180 else "",
                    r[4], round(r[5] or 0, 2),
                    r[6] or "", r[7] or "unknown",
                    r[8] or 0,
                    round(r[9], 1) if r[9] is not None else "",
                    round(r[10], 2) if r[10] is not None else "",
                    (r[11] or "")[:38]])
    write_table_rows(ws, out, 5)
    for ridx in range(5, 5 + len(out)):
        for col in (2, 3, 4, 5):
            ws.cell(row=ridx, column=col).number_format = NUMFMT_M_TO_B
        ws.cell(row=ridx, column=7).number_format = NUMFMT_USD2
        ws.cell(row=ridx, column=8).number_format = NUMFMT_MCAP
        ws.cell(row=ridx, column=11).number_format = '0.0"x"'
        ws.cell(row=ridx, column=12).number_format = '0.00"x"'
    ws.freeze_panes = "B5"
    autosize(ws)
    ws.column_dimensions["A"].width = 8

def sheet_insider_recent(wb, conn):
    """Pure recent (≤30d) insider buying — most actionable."""
    ws = wb.create_sheet("Insider Buys ≤30d")
    ws.sheet_view.showGridLines = False
    write_title(ws, "Recent Insider Buying — last 30 days only",
                "Buys reported in the last 30 days. Most signal-rich window.", 14)
    hdr = ["Ticker","≤30d $M","# Buyers","Latest","Avg Px","Mcap","Bucket","13F","S3","S4","Act %","EV/EBITDA","P/B","Name"]
    write_table_header(ws, 4, hdr)
    rows = list(conn.execute("""
        SELECT f.ticker, SUM(f.shares*f.price)/1e6 AS dollars_m,
               COUNT(DISTINCT f.owner), MAX(f.trans_date),
               AVG(f.price),
               tm.mcap_m, us.mcap_bucket,
               us.smart_money_n, us.s3_new, us.s4_add, us.activist_max_pct,
               us.ev_ebitda, us.pb_ratio,
               tm.name
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
        ORDER BY dollars_m DESC"""))
    out = []
    for r in rows:
        out.append([r[0], round(r[1], 2), r[2], r[3], round(r[4] or 0, 2),
                    r[5] or "", r[6] or "unknown",
                    r[7] or 0, r[8] or 0, r[9] or 0,
                    round(r[10] or 0, 1),
                    round(r[11], 1) if r[11] is not None else "",
                    round(r[12], 2) if r[12] is not None else "",
                    (r[13] or "")[:38]])
    write_table_rows(ws, out, 5)
    for ridx in range(5, 5 + len(out)):
        ws.cell(row=ridx, column=2).number_format = NUMFMT_M_TO_B
        ws.cell(row=ridx, column=5).number_format = NUMFMT_USD2
        ws.cell(row=ridx, column=6).number_format = NUMFMT_MCAP
        ws.cell(row=ridx, column=11).number_format = NUMFMT_PCT
        ws.cell(row=ridx, column=12).number_format = '0.0"x"'
        ws.cell(row=ridx, column=13).number_format = '0.00"x"'
    ws.freeze_panes = "B5"
    autosize(ws)
    ws.column_dimensions["A"].width = 8

def sheet_clusters(wb, conn):
    ws = wb.create_sheet("Insider Clusters")
    ws.sheet_view.showGridLines = False
    write_title(ws, "Live Insider Clusters",
                "Insider buy clusters (≤180-day window) — multiple insiders, same ticker.", 11)
    hdr = ["Ticker","Trigger","Window End","# Insiders","Cluster $M","Avg Px","Top Buyer","Mcap","Bucket","EV/EBITDA","P/B"]
    write_table_header(ws, 4, hdr)
    rows = list(conn.execute("""
        SELECT ic.ticker, ic.trigger, ic.window_end, ic.n_insiders, ic.total_usd_m,
               ic.avg_price, ic.top_buyer, tm.mcap_m, us.mcap_bucket,
               us.ev_ebitda, us.pb_ratio
        FROM insider_clusters ic
        LEFT JOIN ticker_meta tm ON tm.ticker = ic.ticker
        LEFT JOIN unified_signal us ON us.ticker = ic.ticker
        WHERE DATE(ic.window_end) >= DATE('now', '-180 days')
          AND COALESCE(us.sec_type,'common')='common'
          AND ic.n_insiders >= 2
        ORDER BY ic.total_usd_m DESC"""))
    out = [[r[0], r[1], r[2], r[3], round(r[4] or 0, 2), round(r[5] or 0, 2),
            r[6][:30] if r[6] else "", r[7] or "", r[8] or "unknown",
            round(r[9], 1) if r[9] is not None else "",
            round(r[10], 2) if r[10] is not None else ""] for r in rows]
    write_table_rows(ws, out, 5)
    for ridx in range(5, 5 + len(out)):
        ws.cell(row=ridx, column=5).number_format = NUMFMT_M_TO_B
        ws.cell(row=ridx, column=6).number_format = NUMFMT_USD2
        ws.cell(row=ridx, column=8).number_format = NUMFMT_MCAP
        ws.cell(row=ridx, column=10).number_format = '0.0"x"'
        ws.cell(row=ridx, column=11).number_format = '0.00"x"'
    ws.freeze_panes = "B5"
    autosize(ws)
    ws.column_dimensions["A"].width = 8

def sheet_unknown(wb, conn):
    ws = wb.create_sheet("Unknown Mcap")
    ws.sheet_view.showGridLines = False
    write_title(ws, "Unknown Market Cap",
                "Tickers where Yahoo + SEC XBRL share-out resolution failed. Foreign listings, SPACs, warrants, defunct.", 13)
    hdr = ["Ticker","Score","Bucket","13F","S1","S3","S4","Act %","pB Max","F4 $M","Name","Sector","Exch"]
    write_table_header(ws, 4, hdr)
    rows = list(conn.execute("""
        SELECT us.ticker, us.score, us.mcap_bucket, us.smart_money_n,
               us.s1_top, us.s3_new, us.s4_add, us.activist_max_pct, us.max_pct_book,
               us.form4_buy_usd_m, tm.name, tm.sic_description, tm.exchange
        FROM unified_signal us
        LEFT JOIN ticker_meta tm ON tm.ticker = us.ticker
        WHERE us.mcap_bucket = 'unknown' AND us.sec_type='common'
        ORDER BY us.score DESC LIMIT 200"""))
    out = []
    for r in rows:
        if r[0] in ETFs: continue
        out.append([r[0], round(r[1] or 0, 1), r[2] or "",
                    r[3] or 0, r[4] or 0, r[5] or 0, r[6] or 0,
                    round(r[7] or 0, 1), round(r[8] or 0, 1),
                    round(r[9] or 0, 1) if r[9] else "",
                    (r[10] or "")[:38], (r[11] or "")[:30], (r[12] or "")[:12]])
    write_table_rows(ws, out, 5)
    for ridx in range(5, 5 + len(out)):
        ws.cell(row=ridx, column=8).number_format = NUMFMT_PCT
        ws.cell(row=ridx, column=9).number_format = NUMFMT_PCT
    ws.freeze_panes = "B5"
    autosize(ws)
    ws.column_dimensions["A"].width = 8

def sheet_fund_coverage(wb, conn):
    ws = wb.create_sheet("Fund Coverage")
    ws.sheet_view.showGridLines = False
    n_fund = conn.execute("SELECT COUNT(*) FROM fund_meta").fetchone()[0]
    n_data = conn.execute("""SELECT COUNT(DISTINCT fm.fund) FROM fund_meta fm
        WHERE fm.fund IN (SELECT fund FROM fund_13f_state WHERE n_holdings > 0)
           OR fm.fund IN (SELECT fund FROM fund_positions)
           OR fm.fund IN (SELECT holder FROM holder_13d)""").fetchone()[0]
    write_title(ws, "Fund Coverage",
                f"{n_data} of {n_fund} funds ({n_data*100//n_fund}%) have at least one primary-source data row. "
                f"Remaining are documented categorical gaps (below-threshold, CTA, private office, ...).", 3)
    hdr = ["Category","Funds","Pct"]
    write_table_header(ws, 4, hdr)
    # COUNT(DISTINCT fm.fund): the LEFT JOINs to fund_positions/holder_13d fan out
    # (a fund with 50 positions x 5 filings = 250 rows), so a plain COUNT(*)
    # inflated every category ~200x. We also collapse the joins to EXISTS-style
    # per-fund flags first so each fund lands in exactly one category.
    cats = list(conn.execute("""
        WITH f AS (
          SELECT fm.fund,
                 (SELECT n_holdings FROM fund_13f_state s WHERE s.fund=fm.fund) AS nh,
                 EXISTS(SELECT 1 FROM fund_positions p WHERE p.fund=fm.fund) AS has_fp,
                 EXISTS(SELECT 1 FROM holder_13d h WHERE h.holder=fm.fund) AS has_13d,
                 (SELECT status FROM fund_resolution_state r WHERE r.fund=fm.fund) AS status
          FROM fund_meta fm)
        SELECT
          CASE
            WHEN nh > 0 THEN '1. 13F-HR holdings ingested'
            WHEN has_fp AND has_13d THEN '2. fund_positions + 13D/G'
            WHEN has_fp THEN '3. fund_positions only'
            WHEN has_13d THEN '4. 13D/G only (foreign activists)'
            WHEN status LIKE '%non_filer%' THEN '5. Foreign non-filer (explicit)'
            WHEN status = 'below_13f_threshold' THEN '6. Below AUM threshold'
            WHEN status = 'non_equity_strategy' THEN '7. CTA / options (no equity to track)'
            WHEN status = 'historical_13f_only' THEN '8. Historical only (pre-2013 format)'
            WHEN status = 'individual' THEN '9. Individual (not a fund)'
            WHEN status = 'meta_rollup' THEN '10. Meta tab (not a real fund)'
            WHEN status = 'private_office' THEN '11. Private office (no disclosure)'
            ELSE '12. Other / unresolved'
          END as cat, COUNT(DISTINCT fund)
        FROM f GROUP BY cat ORDER BY 1"""))
    total = sum(r[1] for r in cats)
    out = [[r[0], r[1], round(r[1]*100/total, 1)] for r in cats]
    write_table_rows(ws, out, 5)
    for ridx in range(5, 5 + len(out)):
        ws.cell(row=ridx, column=3).number_format = NUMFMT_PCT
    autosize(ws)
    ws.column_dimensions["A"].width = 40

def sheet_all_holdings_consolidated(wb, conn):
    """Union view across 13F, fund_positions, and holder_13d — every disclosed
    position across the 445-fund universe. Source column indicates origin.
    Shows top 30 positions per fund to keep workbook navigable.
    """
    ws = wb.create_sheet("All Positions")
    ws.sheet_view.showGridLines = False
    write_title(ws, "All Fund Positions — consolidated view",
                "Union of 13F-HR holdings + fund_positions (XLSX-classified) + 13D/G subjects across all 445 funds. Top 30 per fund.", 11)
    hdr = ["Fund","Ticker","Source","Value $M","%Book","Section","Activist %","Mcap","Bucket","EV/EBITDA","P/B"]
    write_table_header(ws, 4, hdr)
    rows = list(conn.execute("""
        WITH ranked AS (
          SELECT h.fund, h.ticker, '13F-HR' AS source,
                 h.value_k/1000.0 AS value_m,
                 h.pct_book, NULL AS section,
                 NULL AS act_pct,
                 us.mcap_m, us.mcap_bucket, us.ev_ebitda, us.pb_ratio,
                 ROW_NUMBER() OVER (PARTITION BY h.fund ORDER BY h.value_k DESC) AS rn
          FROM fund_13f_holdings h
          LEFT JOIN unified_signal us ON us.ticker = h.ticker
          WHERE h.ticker IS NOT NULL
        )
        SELECT fund, ticker, source, value_m, pct_book, section, act_pct, mcap_m, mcap_bucket, ev_ebitda, pb_ratio
        FROM ranked WHERE rn <= 30
        UNION ALL
        SELECT fp.fund, fp.ticker, 'XLSX' AS source,
               fp.dollar_m AS value_m,
               fp.pct_value AS pct_book,
               fp.section,
               us.activist_max_pct,
               us.mcap_m, us.mcap_bucket, us.ev_ebitda, us.pb_ratio
        FROM fund_positions fp
        LEFT JOIN unified_signal us ON us.ticker = fp.ticker
        WHERE fp.ticker IS NOT NULL
          AND fp.section IN (1,3,4)
        UNION ALL
        SELECT h.holder AS fund, h.subject_ticker AS ticker, 'SC 13D/G' AS source,
               NULL AS value_m,
               h.pct_class AS pct_book,
               NULL AS section,
               us.activist_max_pct,
               us.mcap_m, us.mcap_bucket, us.ev_ebitda, us.pb_ratio
        FROM holder_13d h
        LEFT JOIN unified_signal us ON us.ticker = h.subject_ticker
        WHERE h.subject_ticker IS NOT NULL AND h.pct_class >= 5
        ORDER BY fund, value_m DESC
    """))
    # Show ALL rows (they fit well within Excel's limit). The prior 6000-row slice
    # was ordered by FUND NAME, so it silently dropped every fund after ~"P" while
    # claiming full coverage. Cap only as an extreme-safety backstop, with a note.
    CAP = 60000
    if len(rows) > CAP:
        rows = rows[:CAP]
    ws.cell(row=2, column=1).value = (
        f"Union of 13F-HR (top 30/fund) + fund_positions + 13D/G across all funds. "
        f"{len(rows):,} rows shown, grouped by fund.")
    out = []
    for r in rows:
        out.append([(r[0] or "")[:45], r[1] or "", r[2],
                    round(r[3] or 0, 1) if r[3] else "",
                    round(r[4] or 0, 2),
                    r[5] or "",
                    round(r[6] or 0, 1) if r[6] else "",
                    r[7] or "", r[8] or "",
                    round(r[9], 1) if r[9] is not None else "",
                    round(r[10], 2) if r[10] is not None else ""])
    write_table_rows(ws, out, 5)
    for ridx in range(5, 5 + len(out)):
        ws.cell(row=ridx, column=4).number_format = NUMFMT_M_TO_B
        ws.cell(row=ridx, column=5).number_format = NUMFMT_PCT
        ws.cell(row=ridx, column=7).number_format = NUMFMT_PCT
        ws.cell(row=ridx, column=8).number_format = NUMFMT_MCAP
        ws.cell(row=ridx, column=10).number_format = '0.0"x"'
        ws.cell(row=ridx, column=11).number_format = '0.00"x"'
    ws.freeze_panes = "A5"
    autosize(ws)

def sheet_all_funds(wb, conn):
    ws = wb.create_sheet("All Funds")
    ws.sheet_view.showGridLines = False
    write_title(ws, "Per-Fund Inventory",
                "Every fund in fund_meta with data-availability status. Sorted by 13F holdings count.", 7)
    hdr = ["Fund","Status","CIK","13F #","13F $M","13D #","Pos Count"]
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
        out.append([r[0][:55], r[1] or "", r[2] or "",
                    r[3], round(r[4] or 0), r[5], r[6]])
    write_table_rows(ws, out, 5)
    for ridx in range(5, 5 + len(out)):
        ws.cell(row=ridx, column=5).number_format = NUMFMT_M_TO_B   # 13F total $M
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
                    " ".join(cat), (r[15] or "")[:34], d[0], d[1]])
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
    """Revealed preference — what smart money is ACTIVELY buying (new + adds),
    not just holding. Ranked by revealed_pref = 2*S3 + S4 + 0.5*S1.
    Cross-cut by size bucket so micro/small revealed conviction is visible."""
    ws = wb.create_sheet("Revealed Preference")
    ws.sheet_view.showGridLines = False
    write_title(ws, "Revealed Preference — what they're actively buying",
                "Ranked by revealed_pref = 2×(new major positions) + 1×(material adds) + 0.5×(top-conviction holds). Reveals active accumulation, not static holdings.", 15)
    hdr = ["Ticker","Rev Pref","S3 New","S4 Add","S1 Top","13F","Mcap","Bucket","EV/EBITDA","P/B","Act %","Entry","Name","Industry","Business"]
    write_table_header(ws, 4, hdr)
    rows = list(conn.execute("""
        SELECT us.ticker, us.revealed_pref, us.s3_new, us.s4_add, us.s1_top,
               us.smart_money_n, us.mcap_m, us.mcap_bucket,
               us.ev_ebitda, us.pb_ratio, us.activist_max_pct, us.entry_bucket, tm.name
        FROM unified_signal us
        LEFT JOIN ticker_meta tm ON tm.ticker = us.ticker
        WHERE us.revealed_pref > 0 AND us.sec_type='common'
        ORDER BY us.revealed_pref DESC, us.smart_money_n DESC LIMIT 120"""))
    out = []
    for r in rows:
        if r[0] in ETFs or r[0] in MEGA: continue
        eb = r[11] or ""
        eb_label = ("below" if eb == "BELOW_ENTRY" else "near" if eb == "NEAR_ENTRY"
                    else "above" if "ABOVE" in eb else "")
        d = desc_for(conn, r[0])
        out.append([r[0], round(r[1] or 0, 1), r[2] or 0, r[3] or 0, r[4] or 0,
                    r[5] or 0, r[6] or "", r[7] or "",
                    round(r[8], 1) if r[8] is not None else "",
                    round(r[9], 2) if r[9] is not None else "",
                    round(r[10] or 0, 1), eb_label, (r[12] or "")[:38], d[0], d[1]])
    write_table_rows(ws, out, 5)
    for ridx in range(5, 5 + len(out)):
        ws.cell(row=ridx, column=7).number_format = NUMFMT_MCAP
        ws.cell(row=ridx, column=9).number_format = '0.0"x"'
        ws.cell(row=ridx, column=10).number_format = '0.00"x"'
        ws.cell(row=ridx, column=11).number_format = NUMFMT_PCT
    ws.column_dimensions[get_column_letter(14)].width = 24   # Industry
    ws.column_dimensions[get_column_letter(15)].width = 80   # Business
    ws.freeze_panes = "B5"
    autosize(ws)
    ws.column_dimensions["A"].width = 8

def sheet_valuation(wb, conn):
    """Cheapest names by valuation among smart-money holdings."""
    ws = wb.create_sheet("Valuation")
    ws.sheet_view.showGridLines = False
    write_title(ws, "Valuation — EV/EBITDA & P/B among smart-money names",
                "Names held by ≥3 funds, sorted by EV/EBITDA ascending (cheapest first). Negative EV/EBITDA (no/neg EBITDA) excluded.", 15)
    hdr = ["Ticker","EV/EBITDA","P/B","P/E","Score","Mcap","Bucket","13F","Act %","Entry","vs Entry %","Name","Sector","Industry","Business"]
    write_table_header(ws, 4, hdr)
    # Floor at 2x — below that is almost always a data artifact (warrant,
    # near-zero EBITDA, ADR currency mismatch). Exclude warrant/preferred tickers.
    rows = list(conn.execute("""
        SELECT us.ticker, us.ev_ebitda, us.pb_ratio, us.pe_ttm, us.score, us.mcap_m, us.mcap_bucket,
               us.smart_money_n, us.activist_max_pct, us.entry_bucket, us.vs_entry_pct,
               tm.name, tm.sic_description
        FROM unified_signal us
        LEFT JOIN ticker_meta tm ON tm.ticker = us.ticker
        WHERE us.ev_ebitda IS NOT NULL AND us.ev_ebitda >= 2 AND us.ev_ebitda < 40 AND us.sec_type='common'
          AND us.smart_money_n >= 3
          AND us.ticker NOT LIKE '%-P%'   -- preferreds
          AND us.ticker NOT LIKE '%-W%'   -- warrants/when-issued
          AND us.ticker NOT LIKE '%W'     -- warrant suffix
          AND us.ticker NOT LIKE '%.W%'
        ORDER BY us.ev_ebitda ASC LIMIT 120"""))
    out = []
    for r in rows:
        if r[0] in ETFs or r[0] in MEGA: continue
        eb = r[9] or ""
        eb_label = ("below" if eb == "BELOW_ENTRY" else "near" if eb == "NEAR_ENTRY"
                    else "above" if "ABOVE" in eb else "")
        d = desc_for(conn, r[0])
        out.append([r[0], round(r[1], 1), round(r[2], 2) if r[2] is not None else "",
                    round(r[3], 1) if r[3] is not None else "",
                    round(r[4] or 0, 1), r[5] or "", r[6] or "", r[7] or 0,
                    round(r[8] or 0, 1), eb_label,
                    round(r[10] or 0, 1) if r[10] else "",
                    (r[11] or "")[:38], (r[12] or "")[:30], d[0], d[1]])
    write_table_rows(ws, out, 5)
    for ridx in range(5, 5 + len(out)):
        ws.cell(row=ridx, column=2).number_format = '0.0"x"'
        ws.cell(row=ridx, column=3).number_format = '0.00"x"'
        ws.cell(row=ridx, column=4).number_format = '0.0"x"'
        ws.cell(row=ridx, column=6).number_format = NUMFMT_MCAP
        ws.cell(row=ridx, column=9).number_format = NUMFMT_PCT
        ws.cell(row=ridx, column=11).number_format = NUMFMT_PCT
    ws.freeze_panes = "B5"
    autosize(ws)
    ws.column_dimensions["A"].width = 8
    ws.column_dimensions[get_column_letter(14)].width = 24   # Industry
    ws.column_dimensions[get_column_letter(15)].width = 80   # Business

def sheet_catalysts(wb, conn):
    """8-K material-event tickers: M&A, control change, director shuffle, PIPE, bankruptcy."""
    ws = wb.create_sheet("Catalysts 8-K")
    ws.sheet_view.showGridLines = False
    write_title(ws, "8-K Material-Event Catalysts (≤180d)",
                "M&A (1.01 / 2.01), Control change (5.01), Director change (5.02), PIPE/dilution (3.02), Bankruptcy (1.03). Cross-referenced with smart money.", 15)
    hdr = ["Ticker","Score","Mcap","M&A","Ctrl","Director","PIPE","Bnk","Total Events","13F","Activist %","EV/EBITDA","P/B","Name","Sector"]
    write_table_header(ws, 4, hdr)
    rows = list(conn.execute("""
        SELECT us.ticker, us.score, us.mcap_m,
               us.cat8k_ma, us.cat8k_ctrl, us.cat8k_dir, us.cat8k_pipe, us.cat8k_bnk, us.cat8k_n,
               us.smart_money_n, us.activist_max_pct, us.ev_ebitda, us.pb_ratio, tm.name, tm.sic_description
        FROM unified_signal us
        LEFT JOIN ticker_meta tm ON tm.ticker = us.ticker
        WHERE us.cat8k_n > 0 AND us.sec_type='common'
        ORDER BY (us.cat8k_ma*5 + us.cat8k_ctrl*4 + us.cat8k_dir + us.smart_money_n*0.1) DESC LIMIT 200"""))
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
                    (r[13] or "")[:38], (r[14] or "")[:32]])
    write_table_rows(ws, out, 5)
    for ridx in range(5, 5 + len(out)):
        ws.cell(row=ridx, column=3).number_format = NUMFMT_MCAP
        ws.cell(row=ridx, column=11).number_format = NUMFMT_PCT
        ws.cell(row=ridx, column=12).number_format = '0.0"x"'
        ws.cell(row=ridx, column=13).number_format = '0.00"x"'
    ws.freeze_panes = "B5"
    autosize(ws)
    ws.column_dimensions["A"].width = 8

# Approximate FX -> USD (mid-2026). Foreign mcap in ticker_yf is in the LISTING
# currency; printing it with a "$" made 4676.T (¥586B ≈ $3.9B) read as "$586B".
# These are approximate and drift; the sheet labels them so and shows the
# currency. Minor units (GBp pence, ZAc cents) convert via their major /100.
_FX_USD = {
    "USD": 1.0, "CAD": 0.73, "EUR": 1.08, "GBP": 1.28, "GBp": 0.0128, "JPY": 0.0064,
    "HKD": 0.128, "AUD": 0.66, "CHF": 1.12, "SGD": 0.74, "INR": 0.012, "KRW": 0.00073,
    "TWD": 0.031, "ZAR": 0.055, "ZAc": 0.00055, "NOK": 0.093, "DKK": 0.145, "SEK": 0.095,
    "PLN": 0.25, "IDR": 0.0000615, "TRY": 0.030, "HUF": 0.0028, "MYR": 0.21, "CNY": 0.138,
    "BRL": 0.18, "MXN": 0.055, "THB": 0.028, "PHP": 0.017, "NZD": 0.60, "ILS": 0.27,
}

def _mcap_usd(mcap_m, currency):
    if not mcap_m:
        return None
    return mcap_m * _FX_USD.get(currency or "USD", None) if (currency or "USD") in _FX_USD else None

def sheet_global_picks(wb, conn):
    """Foreign-exchange tickers — scored on a GLOBAL-FAIR formula.

    The standard unified_score includes US-only signals (Form 4 buys,
    insider clusters) which SEC doesn't provide for foreign listings.
    This sheet uses global_score (smart_money + sections + activist +
    pct_book + micro_bonus + entry_bonus only) so foreign tickers rank
    on the same footing as US tickers stripped of the same signals.
    """
    ws = wb.create_sheet("Global Picks")
    ws.sheet_view.showGridLines = False
    write_title(ws, "Global Picks — non-US listings, fair-score",
                "Foreign-exchange tickers (.L London, .T Tokyo, .TO Toronto, .HK Hong Kong, .AX Sydney, .MI Milan, .DE Frankfurt, .PA Paris, .AS Amsterdam, .MC Madrid). Ranked by global_score which excludes US-only signals.", 17)
    ws.cell(row=2, column=1).value = (ws.cell(row=2, column=1).value or "") + \
        "  Mcap converted to USD at approximate mid-2026 FX (see Currency col)."
    hdr = ["Ticker","Global Score","Exchange","Mcap $ (USD)","Ccy","13F","S1","S3","S4","pB Max","Act %","Entry","vs Entry %","EV/EBITDA","P/B","Name","Industry","Business"]
    write_table_header(ws, 4, hdr)
    rows = list(conn.execute("""
        SELECT us.ticker, us.global_score, tm.exchange, us.mcap_m,
               us.smart_money_n, us.s1_top, us.s3_new, us.s4_add,
               us.max_pct_book, us.activist_max_pct,
               us.entry_bucket, us.vs_entry_pct, us.ev_ebitda, us.pb_ratio, tm.name,
               yf.currency
        FROM unified_signal us
        LEFT JOIN ticker_meta tm ON tm.ticker = us.ticker
        LEFT JOIN ticker_yf yf ON yf.ticker = us.ticker
        WHERE us.is_us = 0 AND us.sec_type='common'
          AND (us.s1_top + us.s3_new + us.s4_add + us.smart_money_n) >= 1
        ORDER BY us.global_score DESC LIMIT 150"""))
    out = []
    for r in rows:
        eb = r[10] or ""
        eb_label = ("below" if eb == "BELOW_ENTRY" else
                    "near"  if eb == "NEAR_ENTRY" else
                    "above" if "ABOVE" in eb else "")
        ccy = r[15] or "USD"
        mcap_usd = _mcap_usd(r[3], ccy)
        out.append([r[0], round(r[1] or 0, 1),
                    (r[2] or "")[:14],
                    round(mcap_usd) if mcap_usd is not None else "", ccy, r[4] or 0,
                    r[5] or 0, r[6] or 0, r[7] or 0,
                    round(r[8] or 0, 1),
                    round(r[9] or 0, 1),
                    eb_label,
                    round(r[11] or 0, 1) if r[11] else "",
                    round(r[12], 1) if r[12] is not None else "",
                    round(r[13], 2) if r[13] is not None else "",
                    (r[14] or "")[:38], *desc_for(conn, r[0])])
    write_table_rows(ws, out, 5)
    for ridx in range(5, 5 + len(out)):
        ws.cell(row=ridx, column=4).number_format = NUMFMT_MCAP    # Mcap $ (USD)
        ws.cell(row=ridx, column=10).number_format = NUMFMT_PCT    # pB Max
        ws.cell(row=ridx, column=11).number_format = NUMFMT_PCT    # Act %
        ws.cell(row=ridx, column=13).number_format = NUMFMT_PCT    # vs Entry %
        ws.cell(row=ridx, column=14).number_format = '0.0"x"'      # EV/EBITDA
        ws.cell(row=ridx, column=15).number_format = '0.00"x"'     # P/B
    ws.freeze_panes = "B5"
    autosize(ws)
    ws.column_dimensions["A"].width = 10
    ws.column_dimensions[get_column_letter(17)].width = 24   # Industry
    ws.column_dimensions[get_column_letter(18)].width = 80   # Business

def sheet_in_the_money(wb, conn):
    """Below-entry / in-the-money picks — buy below where smart money entered."""
    ws = wb.create_sheet("In The Money")
    ws.sheet_view.showGridLines = False
    write_title(ws, "In The Money — buy below smart-money entry",
                "Current price below the smart-money cost anchor (cost_basis / raw_text / Form-4 P-buy avg / 80th-pctl). Asymmetric setup.", 19)
    hdr = ["Ticker","Score","Mcap","Bucket","Now $","Anchor $","vs Entry %",
           "13F","S1","S3","S4","Act %","pB Max","Anchor Src","EV/EBITDA","P/B","Name","Industry","Business"]
    write_table_header(ws, 4, hdr)
    rows = list(conn.execute("""
        SELECT us.ticker, us.score, us.mcap_m, us.mcap_bucket, us.price,
               us.anchor_px, us.vs_entry_pct,
               us.smart_money_n, us.s1_top, us.s3_new, us.s4_add,
               us.activist_max_pct, us.max_pct_book,
               us.anchor_source, us.ev_ebitda, us.pb_ratio, tm.name
        FROM unified_signal us
        LEFT JOIN ticker_meta tm ON tm.ticker = us.ticker
        WHERE us.entry_bucket = 'BELOW_ENTRY' AND us.sec_type='common'
        ORDER BY us.score DESC LIMIT 100"""))
    out = []
    for r in rows:
        if r[0] in ETFs: continue
        out.append([r[0], round(r[1] or 0, 1), r[2] or "", r[3] or "",
                    round(r[4] or 0, 2) if r[4] else "",
                    round(r[5] or 0, 2) if r[5] else "",
                    round(r[6] or 0, 1) if r[6] else "",
                    r[7] or 0, r[8] or 0, r[9] or 0, r[10] or 0,
                    round(r[11] or 0, 1), round(r[12] or 0, 1),
                    (r[13] or "")[:18],
                    round(r[14], 1) if r[14] is not None else "",
                    round(r[15], 2) if r[15] is not None else "",
                    (r[16] or "")[:38], *desc_for(conn, r[0])])
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
                   tm.mcap_m, us.mcap_bucket, us.smart_money_n, us.activist_max_pct,
                   us.insider_cluster_dollars_m, us.ev_ebitda, us.pb_ratio, tm.name
            FROM fund_13f_holdings h
            LEFT JOIN ticker_meta tm ON tm.ticker = h.ticker
            LEFT JOIN unified_signal us ON us.ticker = h.ticker
            WHERE h.fund LIKE ?
            ORDER BY h.value_k DESC LIMIT 20""", (like,)))
        out = []
        for r in rows:
            cluster_mark = "yes" if (r[8] and r[8] > 0) else ""
            out.append([r[0] or "-", (r[1] or "")[:30],
                        round((r[2] or 0)/1000, 1) if r[2] else "",
                        round(r[3] or 0, 2),
                        r[4] or "", r[5] or "",
                        r[6] or 0, round(r[7] or 0, 1),
                        cluster_mark,
                        round(r[9], 1) if r[9] is not None else "",
                        round(r[10], 2) if r[10] is not None else "",
                        (r[11] or "")[:30]])
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
               tm.mcap_m, us.mcap_bucket, us.smart_money_n, us.activist_max_pct,
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
        out.append([r[0], (r[1] or "")[:30],
                    round(r[2] or 0, 2),
                    round(r[3] or 0, 2),
                    round(r[4] or 0, 2),
                    r[5] or "", r[6] or "",
                    r[7] or 0, round(r[8] or 0, 1),
                    round(r[9], 1) if r[9] is not None else "",
                    round(r[10], 2) if r[10] is not None else "",
                    (r[11] or "")[:30]])
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
    hdr = ["Ticker", "Idea", "Flags", "Score", "Asym", "Mcap", "Bucket",
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
                       " ".join(cat), (name or "")[:34], " · ".join(why),
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
    write_title(ws, "Adversarial Review — red-team of the top picks",
                f"A {data.get('agent_count','multi')}-agent stress test of the highest-ranked names across three lenses (data quality · thesis soundness · recency/news), separating confirmed setups from data-inflated artifacts. Scores as of {data.get('asof')}.", 4)
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

def _one_liner(s, limit=200):
    """Condense a stored business summary to a short one-liner for display."""
    if not s:
        return ""
    s = str(s).strip().replace("\n", " ")
    dot = s.find(". ")
    if 0 < dot <= limit:
        return s[:dot + 1]
    return s if len(s) <= limit else s[:limit].rstrip() + "…"

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
                   yf.business_summary
            FROM unified_signal us
            LEFT JOIN ticker_meta tm ON tm.ticker = us.ticker
            LEFT JOIN ticker_yf  yf ON yf.ticker = us.ticker"""):
            _DESC_CACHE[r[0]] = ((r[1] or "")[:26], _one_liner(r[2], 90))
    return _DESC_CACHE.get(ticker, ("", ""))

def sheet_ticker_reference(wb, conn):
    """Glossary: every ticker with name, sector, industry, and a short business
    summary — so any symbol in the workbook can be looked up. Sorted A–Z."""
    ws = wb.create_sheet("Ticker Reference")
    ws.sheet_view.showGridLines = False
    write_title(ws, "Ticker Reference — name, industry, business",
                "Every symbol in the universe with its company name, sector, industry, market cap, and a one-line description of what it does. Sourced from Yahoo Finance + SEC. Sorted A–Z.", 6)
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
        out.append([r[0], (r[1] or "")[:46], (r[2] or "")[:22],
                    (r[3] or "")[:30], r[4] or "", _one_liner(r[5])])
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

TAB_COLORS = {
    # Navigation / meta — lightest
    "README":          "F2F2F2",
    "Legend":          "F2F2F2",
    "Fund Coverage":   "F2F2F2",
    "All Funds":       "F2F2F2",
    # Universe ranking — darkest
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
    # Signal sheets — mid
    "Material + New":          "808080",
    "Who's Buying":            "808080",
    "Revealed Preference":     "808080",
    "Activist 10+":            "808080",
    "Insider Buys ≤30d":       "808080",
    "Insider F4 Buys":         "808080",
    "Insider Clusters":        "808080",
    "Catalysts 8-K":           "808080",
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
    wb = openpyxl.Workbook()
    if "Sheet" in wb.sheetnames:
        wb.remove(wb["Sheet"])

    sheet_readme(wb, conn)
    write_legend_sheet(wb, 1)
    sheet_best_ideas(wb, conn)
    sheet_adversarial_review(wb, conn)
    write_signal_sheet(wb, conn, "Top 100",
        where_extra="AND us.mcap_bucket != 'unknown'", limit=140,
        subtitle="Top 100 by unified_score across the full 5,862-ticker universe (ex-ETF, ex-mega-cap, mcap known).")
    for bucket, title in [("nano","Nano (<$50M)"),
                          ("micro","Micro ($50M–$300M)"),
                          ("small","Small ($300M–$2B)"),
                          ("mid","Mid ($2B–$10B)")]:
        write_signal_sheet(wb, conn, title,
            where_extra=f"AND us.mcap_bucket = '{bucket}'", limit=60,
            subtitle=f"Top {bucket} cap by unified_score. Ex-ETF, ex-mega.")
    sheet_best_in_bucket(wb, conn)
    write_signal_sheet(wb, conn, "Material + New",
        where_extra="AND (us.s3_new + us.s4_add) >= 2 AND us.mcap_bucket != 'unknown'",
        limit=80,
        subtitle="≥2 funds adding to existing (S4) OR initiating major new (S3) — smart money is BUILDING.")
    sheet_whos_buying(wb, conn)
    sheet_activist(wb, conn)
    sheet_insider_recent(wb, conn)
    sheet_insider_f4(wb, conn)
    sheet_clusters(wb, conn)
    write_signal_sheet(wb, conn, "Non-Biotech Top 100",
        where_extra="AND us.mcap_bucket != 'unknown'", limit=140,
        subtitle="Top ex-biotech, ex-ETF, ex-mega.", exclude_biotech=True)
    sheet_in_the_money(wb, conn)
    sheet_asymmetry(wb, conn)
    sheet_revealed_pref(wb, conn)
    sheet_valuation(wb, conn)
    sheet_catalysts(wb, conn)
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
        "Mid ($2B–$10B)", "Material + New", "Activist 10+", "Insider Buys ≤30d",
        "Insider F4 Buys", "Insider Clusters", "Non-Biotech Top 100", "In The Money",
        "Asymmetry", "Revealed Preference", "Valuation", "Catalysts 8-K",
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

    add_contents_index(wb["README"], wb.sheetnames)
    set_print_layout(wb)

    wb.save(OUT)
    print(f"wrote {OUT}")
    print(f"sheets: {wb.sheetnames}")

if __name__ == "__main__":
    main()
