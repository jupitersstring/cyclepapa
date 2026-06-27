"""Render the universe analysis workbook — monochrome academic aesthetic.

A companion to style_analysis.xlsx. This file ranks the FULL 5,862-ticker
universe (no style cut) with the unified_signal score, sorted into sheets
by size bucket and signal type.

Design language is shared with render_style_workbook.py via _style_bw.py.
"""
import os, sqlite3
import openpyxl
from openpyxl.utils import get_column_letter

import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _style_bw import (
    write_title, write_section_heading, write_table_header, write_table_rows,
    autosize, NUMFMT_USD, NUMFMT_PCT, NUMFMT_NUM, NUMFMT_INT, NUMFMT_USD2,
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

SIG_HDR = ["Ticker","Score","Mcap","Bucket","13F","S1","S3","S4","Act %",
           "pB Max","pB ≥5%","13D","Clu $M",
           "F4 Buy 180d","F4 Buy ≤30d","F4 Sell 180d","F4 Sell ≤30d",
           "EV/EBITDA","P/B",
           "Entry","vs Entry %","Anchor $",
           "ER %","Name","Sector","Px"]

def get_signal_rows(conn, where_extra="", limit=None, params=()):
    sql = """SELECT us.ticker, us.score, us.mcap_m, us.mcap_bucket, us.smart_money_n,
        us.s1_top, us.s3_new, us.s4_add, us.activist_max_pct, us.max_pct_book,
        us.n_funds_5pct_book, us.activist_filings,
        us.insider_cluster_dollars_m,
        us.form4_buy_usd_m, us.form4_buy_30d_m, us.form4_sell_usd_m, us.form4_sell_30d_m,
        us.ev_ebitda, us.pb_ratio,
        us.entry_bucket, us.vs_entry_pct, us.anchor_px,
        us.expected_return_pct, tm.name, tm.sic_description, tm.price
        FROM unified_signal us
        LEFT JOIN ticker_meta tm ON tm.ticker = us.ticker
        WHERE 1=1 """ + where_extra + " ORDER BY us.score DESC"
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
        r[2] or "", r[3] or "",
        r[4] or 0, r[5] or 0, r[6] or 0, r[7] or 0,
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
        round(r[22] or 0, 1) if r[22] else "",   # ER
        (r[23] or "")[:38],
        (r[24] or "")[:32],
        round(r[25] or 0, 2) if r[25] else "",
    ]

def format_signal_row(ws, ridx):
    """Apply number formats to a signal row."""
    ws.cell(row=ridx, column=3).number_format = NUMFMT_MCAP    # mcap
    ws.cell(row=ridx, column=9).number_format = NUMFMT_PCT     # act
    ws.cell(row=ridx, column=10).number_format = NUMFMT_PCT    # pB max
    ws.cell(row=ridx, column=13).number_format = NUMFMT_M_TO_B # Clu $M
    ws.cell(row=ridx, column=14).number_format = NUMFMT_M_TO_B # F4 buy 180d
    ws.cell(row=ridx, column=15).number_format = NUMFMT_M_TO_B # F4 buy 30d
    ws.cell(row=ridx, column=16).number_format = NUMFMT_M_TO_B # F4 sell 180d
    ws.cell(row=ridx, column=17).number_format = NUMFMT_M_TO_B # F4 sell 30d
    ws.cell(row=ridx, column=18).number_format = '0.0"x"'      # EV/EBITDA
    ws.cell(row=ridx, column=19).number_format = '0.00"x"'     # P/B
    ws.cell(row=ridx, column=21).number_format = NUMFMT_PCT    # vs entry
    ws.cell(row=ridx, column=22).number_format = NUMFMT_USD2   # anchor px
    ws.cell(row=ridx, column=23).number_format = NUMFMT_PCT    # ER
    ws.cell(row=ridx, column=26).number_format = NUMFMT_USD2   # px

# ---- sheets -----------------------------------------------------------------
def sheet_readme(wb, conn):
    ws = wb.create_sheet("README", 0)
    ws.sheet_view.showGridLines = False
    write_title(ws,
        "Cyclepapa — Universe Analysis",
        "A data-driven ranking of the smart-money universe (5,862 tickers, 445 funds, primary EDGAR sources).",
        1)
    ws.column_dimensions["A"].width = 92

    rows = [
        ("",),
        ("Universe",),
        (f"5,862 tickers — the union of fund_13f_holdings, fund_positions, and holder_13d.subject_ticker.",),
        (f"445 funds in fund_meta; 424 (95.3%) have data; 21 documented categorical gaps.",),
        ("",),
        ("Score formula",),
        ("score = log(n_funds_13F) × 2",),
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
        ("fund_13f_holdings     71,706 rows from SEC 13F-HR XML across 306 funds",),
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

def write_signal_sheet(wb, conn, name, where_extra="", limit=200, subtitle=""):
    ws = wb.create_sheet(name)
    ws.sheet_view.showGridLines = False
    write_title(ws, name, subtitle, len(SIG_HDR))
    write_table_header(ws, 4, SIG_HDR)
    rows = get_signal_rows(conn, where_extra=where_extra, limit=limit)
    rows = [r for r in rows if r[0] not in ETFs and r[0] not in MEGA]
    out = [signal_row_to_cells(r) for r in rows]
    write_table_rows(ws, out, 5)
    for ridx in range(5, 5 + len(out)):
        format_signal_row(ws, ridx)
    ws.freeze_panes = "B5"
    autosize(ws)
    # ticker col narrower
    ws.column_dimensions["A"].width = 8

def sheet_activist(wb, conn):
    ws = wb.create_sheet("Activist 10+")
    ws.sheet_view.showGridLines = False
    write_title(ws, "Activist Concentration",
                "SC 13D/G filings disclosing ≥10% stake. Sourced from holder_13d. Ex-biotech, ex-ETF.", 9)
    hdr = ["Ticker","Mcap","Bucket","Act %","13D #","13F #","pB Max","Name","Sector"]
    write_table_header(ws, 4, hdr)
    rows = list(conn.execute("""
        SELECT us.ticker, us.mcap_m, us.mcap_bucket,
               us.activist_max_pct, us.activist_filings, us.smart_money_n,
               us.max_pct_book, tm.name, tm.sic_description
        FROM unified_signal us
        LEFT JOIN ticker_meta tm ON tm.ticker = us.ticker
        WHERE us.activist_max_pct >= 10
        ORDER BY us.activist_max_pct DESC"""))
    out = []
    for r in rows:
        if r[0] in ETFs or r[0] in MEGA: continue
        if is_biotech(r[8]): continue
        out.append([r[0], r[1] or "", r[2] or "", round(r[3] or 0, 1),
                    r[4] or 0, r[5] or 0, round(r[6] or 0, 1),
                    (r[7] or "")[:38], (r[8] or "")[:32]])
    write_table_rows(ws, out, 5)
    for ridx in range(5, 5 + len(out)):
        ws.cell(row=ridx, column=2).number_format = NUMFMT_MCAP
        ws.cell(row=ridx, column=4).number_format = NUMFMT_PCT
        ws.cell(row=ridx, column=7).number_format = NUMFMT_PCT
    ws.freeze_panes = "B5"
    autosize(ws)
    ws.column_dimensions["A"].width = 8

def sheet_insider_f4(wb, conn):
    """Insider buying ranked by RECENCY-weighted total. ≤30d buys shown separately."""
    ws = wb.create_sheet("Insider F4 Buys")
    ws.sheet_view.showGridLines = False
    write_title(ws, "Form 4 Insider Buying — recency weighted",
                "Open-market P-code buys. ≤30d weight 1.0; 31–60 d 0.6; 61–120 d 0.3; 121–180 d 0.1. Sorted by recency-weighted dollars.", 13)
    hdr = ["Ticker","Weighted $M","≤30d $M","31-60 $M","61-180 $M","# Buyers","Avg Px","Mcap","Bucket","13F","Name"]
    write_table_header(ws, 4, hdr)
    rows = list(conn.execute("""
        SELECT f.ticker,
            SUM(CASE WHEN julianday('now')-julianday(f.trans_date) <= 30  THEN f.shares*f.price ELSE 0 END)/1e6 AS d_30,
            SUM(CASE WHEN julianday('now')-julianday(f.trans_date) BETWEEN 31 AND 60  THEN f.shares*f.price ELSE 0 END)/1e6 AS d_60,
            SUM(CASE WHEN julianday('now')-julianday(f.trans_date) > 60   THEN f.shares*f.price ELSE 0 END)/1e6 AS d_180,
            COUNT(DISTINCT f.owner), AVG(f.price),
            tm.mcap_m, us.mcap_bucket, us.smart_money_n,
            tm.name
        FROM form4_transactions f
        LEFT JOIN ticker_meta tm ON tm.ticker = f.ticker
        LEFT JOIN unified_signal us ON us.ticker = f.ticker
        WHERE f.code='P' AND f.acquired=1 AND f.price IS NOT NULL
          AND f.trans_date >= date('now','-180 days')
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
                    r[8] or 0, (r[9] or "")[:38]])
    write_table_rows(ws, out, 5)
    for ridx in range(5, 5 + len(out)):
        for col in (2, 3, 4, 5):
            ws.cell(row=ridx, column=col).number_format = NUMFMT_M_TO_B
        ws.cell(row=ridx, column=7).number_format = NUMFMT_USD2
        ws.cell(row=ridx, column=8).number_format = NUMFMT_MCAP
    ws.freeze_panes = "B5"
    autosize(ws)
    ws.column_dimensions["A"].width = 8

def sheet_insider_recent(wb, conn):
    """Pure recent (≤30d) insider buying — most actionable."""
    ws = wb.create_sheet("Insider Buys ≤30d")
    ws.sheet_view.showGridLines = False
    write_title(ws, "Recent Insider Buying — last 30 days only",
                "Buys reported in the last 30 days. Most signal-rich window.", 12)
    hdr = ["Ticker","≤30d $M","# Buyers","Latest","Avg Px","Mcap","Bucket","13F","S3","S4","Act %","Name"]
    write_table_header(ws, 4, hdr)
    rows = list(conn.execute("""
        SELECT f.ticker, SUM(f.shares*f.price)/1e6 AS dollars_m,
               COUNT(DISTINCT f.owner), MAX(f.trans_date),
               AVG(f.price),
               tm.mcap_m, us.mcap_bucket,
               us.smart_money_n, us.s3_new, us.s4_add, us.activist_max_pct,
               tm.name
        FROM form4_transactions f
        LEFT JOIN ticker_meta tm ON tm.ticker = f.ticker
        LEFT JOIN unified_signal us ON us.ticker = f.ticker
        WHERE f.code='P' AND f.acquired=1 AND f.price IS NOT NULL
          AND f.trans_date >= date('now','-30 days')
        GROUP BY f.ticker
        HAVING dollars_m >= 0.05
        ORDER BY dollars_m DESC"""))
    out = []
    for r in rows:
        out.append([r[0], round(r[1], 2), r[2], r[3], round(r[4] or 0, 2),
                    r[5] or "", r[6] or "unknown",
                    r[7] or 0, r[8] or 0, r[9] or 0,
                    round(r[10] or 0, 1), (r[11] or "")[:38]])
    write_table_rows(ws, out, 5)
    for ridx in range(5, 5 + len(out)):
        ws.cell(row=ridx, column=2).number_format = NUMFMT_M_TO_B
        ws.cell(row=ridx, column=5).number_format = NUMFMT_USD2
        ws.cell(row=ridx, column=6).number_format = NUMFMT_MCAP
        ws.cell(row=ridx, column=11).number_format = NUMFMT_PCT
    ws.freeze_panes = "B5"
    autosize(ws)
    ws.column_dimensions["A"].width = 8

def sheet_clusters(wb, conn):
    ws = wb.create_sheet("Insider Clusters")
    ws.sheet_view.showGridLines = False
    write_title(ws, "Live Insider Clusters",
                "Insider buy clusters (≤180-day window) — multiple insiders, same ticker.", 9)
    hdr = ["Ticker","Trigger","Window End","# Insiders","Cluster $M","Avg Px","Top Buyer","Mcap","Bucket"]
    write_table_header(ws, 4, hdr)
    rows = list(conn.execute("""
        SELECT ic.ticker, ic.trigger, ic.window_end, ic.n_insiders, ic.total_usd_m,
               ic.avg_price, ic.top_buyer, tm.mcap_m, us.mcap_bucket
        FROM insider_clusters ic
        LEFT JOIN ticker_meta tm ON tm.ticker = ic.ticker
        LEFT JOIN unified_signal us ON us.ticker = ic.ticker
        WHERE DATE(ic.window_end) >= DATE('now', '-180 days')
        ORDER BY ic.total_usd_m DESC"""))
    out = [[r[0], r[1], r[2], r[3], round(r[4] or 0, 2), round(r[5] or 0, 2),
            r[6][:30] if r[6] else "", r[7] or "", r[8] or "unknown"] for r in rows]
    write_table_rows(ws, out, 5)
    for ridx in range(5, 5 + len(out)):
        ws.cell(row=ridx, column=5).number_format = NUMFMT_M_TO_B
        ws.cell(row=ridx, column=6).number_format = NUMFMT_USD2
        ws.cell(row=ridx, column=8).number_format = NUMFMT_MCAP
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
        WHERE us.mcap_bucket = 'unknown'
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
    write_title(ws, "Fund Coverage",
                "424 of 445 funds (95.3%) have at least one primary-source data row. 21 documented categorical gaps.", 3)
    hdr = ["Category","Count","Pct"]
    write_table_header(ws, 4, hdr)
    cats = list(conn.execute("""
        SELECT
          CASE
            WHEN st.n_holdings > 0 THEN '1. 13F-HR holdings ingested'
            WHEN fp.fund IS NOT NULL AND h.holder IS NOT NULL THEN '2. fund_positions + 13D/G'
            WHEN fp.fund IS NOT NULL THEN '3. fund_positions only'
            WHEN h.holder IS NOT NULL THEN '4. 13D/G only (foreign activists)'
            WHEN fr.status LIKE '%non_filer%' THEN '5. Foreign non-filer (explicit)'
            WHEN fr.status = 'below_13f_threshold' THEN '6. Below AUM threshold'
            WHEN fr.status = 'non_equity_strategy' THEN '7. CTA / options (no equity to track)'
            WHEN fr.status = 'historical_13f_only' THEN '8. Historical only (pre-2013 format)'
            WHEN fr.status = 'individual' THEN '9. Individual (not a fund)'
            WHEN fr.status = 'meta_rollup' THEN '10. Meta tab (not a real fund)'
            WHEN fr.status = 'private_office' THEN '11. Private office (no disclosure)'
            ELSE '12. Other / unresolved'
          END as cat, COUNT(*)
        FROM fund_meta fm
        LEFT JOIN fund_resolution_state fr ON fr.fund = fm.fund
        LEFT JOIN fund_13f_state st ON st.fund = fm.fund
        LEFT JOIN fund_positions fp ON fp.fund = fm.fund
        LEFT JOIN holder_13d h ON h.holder = fm.fund
        GROUP BY cat ORDER BY 1"""))
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
                "Union of 13F-HR holdings + fund_positions (XLSX-classified) + 13D/G subjects across all 445 funds. Top 30 per fund.", 9)
    hdr = ["Fund","Ticker","Source","Value $M","%Book","Section","Activist %","Mcap","Bucket"]
    write_table_header(ws, 4, hdr)
    rows = list(conn.execute("""
        WITH ranked AS (
          SELECT h.fund, h.ticker, '13F-HR' AS source,
                 h.value_k/1000.0 AS value_m,
                 h.pct_book, NULL AS section,
                 NULL AS act_pct,
                 us.mcap_m, us.mcap_bucket,
                 ROW_NUMBER() OVER (PARTITION BY h.fund ORDER BY h.value_k DESC) AS rn
          FROM fund_13f_holdings h
          LEFT JOIN unified_signal us ON us.ticker = h.ticker
          WHERE h.ticker IS NOT NULL
        )
        SELECT fund, ticker, source, value_m, pct_book, section, act_pct, mcap_m, mcap_bucket
        FROM ranked WHERE rn <= 30
        UNION ALL
        SELECT fp.fund, fp.ticker, 'XLSX' AS source,
               fp.dollar_m AS value_m,
               fp.pct_value AS pct_book,
               fp.section,
               us.activist_max_pct,
               us.mcap_m, us.mcap_bucket
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
               us.mcap_m, us.mcap_bucket
        FROM holder_13d h
        LEFT JOIN unified_signal us ON us.ticker = h.subject_ticker
        WHERE h.subject_ticker IS NOT NULL AND h.pct_class >= 5
        ORDER BY fund, value_m DESC
    """))
    out = []
    for r in rows[:6000]:  # cap for Excel sanity
        out.append([(r[0] or "")[:45], r[1] or "", r[2],
                    round(r[3] or 0, 1) if r[3] else "",
                    round(r[4] or 0, 2),
                    r[5] or "",
                    round(r[6] or 0, 1) if r[6] else "",
                    r[7] or "", r[8] or ""])
    write_table_rows(ws, out, 5)
    for ridx in range(5, 5 + len(out)):
        ws.cell(row=ridx, column=4).number_format = NUMFMT_M_TO_B
        ws.cell(row=ridx, column=5).number_format = NUMFMT_PCT
        ws.cell(row=ridx, column=7).number_format = NUMFMT_PCT
        ws.cell(row=ridx, column=8).number_format = NUMFMT_MCAP
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

def sheet_revealed_pref(wb, conn):
    """Revealed preference — what smart money is ACTIVELY buying (new + adds),
    not just holding. Ranked by revealed_pref = 2*S3 + S4 + 0.5*S1.
    Cross-cut by size bucket so micro/small revealed conviction is visible."""
    ws = wb.create_sheet("Revealed Preference")
    ws.sheet_view.showGridLines = False
    write_title(ws, "Revealed Preference — what they're actively buying",
                "Ranked by revealed_pref = 2×(new major positions) + 1×(material adds) + 0.5×(top-conviction holds). Reveals active accumulation, not static holdings.", 13)
    hdr = ["Ticker","Rev Pref","S3 New","S4 Add","S1 Top","13F","Mcap","Bucket","EV/EBITDA","P/B","Act %","Entry","Name"]
    write_table_header(ws, 4, hdr)
    rows = list(conn.execute("""
        SELECT us.ticker, us.revealed_pref, us.s3_new, us.s4_add, us.s1_top,
               us.smart_money_n, us.mcap_m, us.mcap_bucket,
               us.ev_ebitda, us.pb_ratio, us.activist_max_pct, us.entry_bucket, tm.name
        FROM unified_signal us
        LEFT JOIN ticker_meta tm ON tm.ticker = us.ticker
        WHERE us.revealed_pref > 0
        ORDER BY us.revealed_pref DESC, us.smart_money_n DESC LIMIT 120"""))
    out = []
    for r in rows:
        if r[0] in ETFs or r[0] in MEGA: continue
        eb = r[11] or ""
        eb_label = ("below" if eb == "BELOW_ENTRY" else "near" if eb == "NEAR_ENTRY"
                    else "above" if "ABOVE" in eb else "")
        out.append([r[0], round(r[1] or 0, 1), r[2] or 0, r[3] or 0, r[4] or 0,
                    r[5] or 0, r[6] or "", r[7] or "",
                    round(r[8], 1) if r[8] is not None else "",
                    round(r[9], 2) if r[9] is not None else "",
                    round(r[10] or 0, 1), eb_label, (r[12] or "")[:38]])
    write_table_rows(ws, out, 5)
    for ridx in range(5, 5 + len(out)):
        ws.cell(row=ridx, column=7).number_format = NUMFMT_MCAP
        ws.cell(row=ridx, column=9).number_format = '0.0"x"'
        ws.cell(row=ridx, column=10).number_format = '0.00"x"'
        ws.cell(row=ridx, column=11).number_format = NUMFMT_PCT
    ws.freeze_panes = "B5"
    autosize(ws)
    ws.column_dimensions["A"].width = 8

def sheet_valuation(wb, conn):
    """Cheapest names by valuation among smart-money holdings."""
    ws = wb.create_sheet("Valuation")
    ws.sheet_view.showGridLines = False
    write_title(ws, "Valuation — EV/EBITDA & P/B among smart-money names",
                "Names held by ≥3 funds, sorted by EV/EBITDA ascending (cheapest first). Negative EV/EBITDA (no/neg EBITDA) excluded.", 12)
    hdr = ["Ticker","EV/EBITDA","P/B","P/E","Score","Mcap","Bucket","13F","Act %","Entry","vs Entry %","Name","Sector"]
    write_table_header(ws, 4, hdr)
    # Floor at 2x — below that is almost always a data artifact (warrant,
    # near-zero EBITDA, ADR currency mismatch). Exclude warrant/preferred tickers.
    rows = list(conn.execute("""
        SELECT us.ticker, us.ev_ebitda, us.pb_ratio, us.pe_ttm, us.score, us.mcap_m, us.mcap_bucket,
               us.smart_money_n, us.activist_max_pct, us.entry_bucket, us.vs_entry_pct,
               tm.name, tm.sic_description
        FROM unified_signal us
        LEFT JOIN ticker_meta tm ON tm.ticker = us.ticker
        WHERE us.ev_ebitda IS NOT NULL AND us.ev_ebitda >= 2 AND us.ev_ebitda < 40
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
        out.append([r[0], round(r[1], 1), round(r[2], 2) if r[2] is not None else "",
                    round(r[3], 1) if r[3] is not None else "",
                    round(r[4] or 0, 1), r[5] or "", r[6] or "", r[7] or 0,
                    round(r[8] or 0, 1), eb_label,
                    round(r[10] or 0, 1) if r[10] else "",
                    (r[11] or "")[:38], (r[12] or "")[:30]])
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

def sheet_catalysts(wb, conn):
    """8-K material-event tickers: M&A, control change, director shuffle, PIPE, bankruptcy."""
    ws = wb.create_sheet("Catalysts 8-K")
    ws.sheet_view.showGridLines = False
    write_title(ws, "8-K Material-Event Catalysts (≤180d)",
                "M&A (1.01 / 2.01), Control change (5.01), Director change (5.02), PIPE/dilution (3.02), Bankruptcy (1.03). Cross-referenced with smart money.", 13)
    hdr = ["Ticker","Score","Mcap","M&A","Ctrl","Director","PIPE","Bnk","Total Events","13F","Activist %","Name","Sector"]
    write_table_header(ws, 4, hdr)
    rows = list(conn.execute("""
        SELECT us.ticker, us.score, us.mcap_m,
               us.cat8k_ma, us.cat8k_ctrl, us.cat8k_dir, us.cat8k_pipe, us.cat8k_bnk, us.cat8k_n,
               us.smart_money_n, us.activist_max_pct, tm.name, tm.sic_description
        FROM unified_signal us
        LEFT JOIN ticker_meta tm ON tm.ticker = us.ticker
        WHERE us.cat8k_n > 0
        ORDER BY (us.cat8k_ma*5 + us.cat8k_ctrl*4 + us.cat8k_dir + us.smart_money_n*0.1) DESC LIMIT 200"""))
    out = []
    for r in rows:
        if r[0] in ETFs or r[0] in MEGA: continue
        out.append([r[0], round(r[1] or 0, 1), r[2] or "",
                    "✓" if r[3] else "", "✓" if r[4] else "",
                    "✓" if r[5] else "", "✓" if r[6] else "",
                    "✓" if r[7] else "", r[8] or 0,
                    r[9] or 0, round(r[10] or 0, 1),
                    (r[11] or "")[:38], (r[12] or "")[:32]])
    write_table_rows(ws, out, 5)
    for ridx in range(5, 5 + len(out)):
        ws.cell(row=ridx, column=3).number_format = NUMFMT_MCAP
        ws.cell(row=ridx, column=11).number_format = NUMFMT_PCT
    ws.freeze_panes = "B5"
    autosize(ws)
    ws.column_dimensions["A"].width = 8

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
                "Foreign-exchange tickers (.L London, .T Tokyo, .TO Toronto, .HK Hong Kong, .AX Sydney, .MI Milan, .DE Frankfurt, .PA Paris, .AS Amsterdam, .MC Madrid). Ranked by global_score which excludes US-only signals.", 11)
    hdr = ["Ticker","Global Score","Exchange","Mcap","13F","S1","S3","S4","pB Max","Act %","Entry","vs Entry %","Name"]
    write_table_header(ws, 4, hdr)
    rows = list(conn.execute("""
        SELECT us.ticker, us.global_score, tm.exchange, us.mcap_m,
               us.smart_money_n, us.s1_top, us.s3_new, us.s4_add,
               us.max_pct_book, us.activist_max_pct,
               us.entry_bucket, us.vs_entry_pct, tm.name
        FROM unified_signal us
        LEFT JOIN ticker_meta tm ON tm.ticker = us.ticker
        WHERE us.is_us = 0
          AND (us.s1_top + us.s3_new + us.s4_add + us.smart_money_n) >= 1
        ORDER BY us.global_score DESC LIMIT 150"""))
    out = []
    for r in rows:
        eb = r[10] or ""
        eb_label = ("below" if eb == "BELOW_ENTRY" else
                    "near"  if eb == "NEAR_ENTRY" else
                    "above" if "ABOVE" in eb else "")
        out.append([r[0], round(r[1] or 0, 1),
                    (r[2] or "")[:14],
                    r[3] or "", r[4] or 0,
                    r[5] or 0, r[6] or 0, r[7] or 0,
                    round(r[8] or 0, 1),
                    round(r[9] or 0, 1),
                    eb_label,
                    round(r[11] or 0, 1) if r[11] else "",
                    (r[12] or "")[:38]])
    write_table_rows(ws, out, 5)
    for ridx in range(5, 5 + len(out)):
        ws.cell(row=ridx, column=4).number_format = NUMFMT_MCAP
        ws.cell(row=ridx, column=9).number_format = NUMFMT_PCT
        ws.cell(row=ridx, column=10).number_format = NUMFMT_PCT
        ws.cell(row=ridx, column=12).number_format = NUMFMT_PCT
    ws.freeze_panes = "B5"
    autosize(ws)
    ws.column_dimensions["A"].width = 10

def sheet_in_the_money(wb, conn):
    """Below-entry / in-the-money picks — buy below where smart money entered."""
    ws = wb.create_sheet("In The Money")
    ws.sheet_view.showGridLines = False
    write_title(ws, "In The Money — buy below smart-money entry",
                "Current price below the smart-money cost anchor (cost_basis / raw_text / Form-4 P-buy avg / 80th-pctl). Asymmetric setup.", 14)
    hdr = ["Ticker","Score","Mcap","Bucket","Now $","Anchor $","vs Entry %",
           "13F","S1","S3","S4","Act %","pB Max","Anchor Src","Name"]
    write_table_header(ws, 4, hdr)
    rows = list(conn.execute("""
        SELECT us.ticker, us.score, us.mcap_m, us.mcap_bucket, us.price,
               us.anchor_px, us.vs_entry_pct,
               us.smart_money_n, us.s1_top, us.s3_new, us.s4_add,
               us.activist_max_pct, us.max_pct_book,
               us.anchor_source, tm.name
        FROM unified_signal us
        LEFT JOIN ticker_meta tm ON tm.ticker = us.ticker
        WHERE us.entry_bucket = 'BELOW_ENTRY'
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
                    (r[13] or "")[:18], (r[14] or "")[:38]])
    write_table_rows(ws, out, 5)
    for ridx in range(5, 5 + len(out)):
        ws.cell(row=ridx, column=3).number_format = NUMFMT_MCAP
        ws.cell(row=ridx, column=5).number_format = NUMFMT_USD2
        ws.cell(row=ridx, column=6).number_format = NUMFMT_USD2
        ws.cell(row=ridx, column=7).number_format = NUMFMT_PCT
        ws.cell(row=ridx, column=12).number_format = NUMFMT_PCT
        ws.cell(row=ridx, column=13).number_format = NUMFMT_PCT
    ws.freeze_panes = "B5"
    autosize(ws)
    ws.column_dimensions["A"].width = 8

def sheet_bill_miller(wb, conn):
    ws = wb.create_sheet("Bill Miller")
    ws.sheet_view.showGridLines = False
    write_title(ws, "Bill Miller — both Funds",
                "Miller Value Partners (Bill IV, Sarasota) + Patient Capital Management (Bill III). Side-by-side with overlap.", 10)
    funds = [
        ("Bill IV — Miller Value Partners", "Miller Value Partners%"),
        ("Bill III — Patient Capital",       "Patient Capital%"),
    ]
    write_section_heading(ws, 4, "Top 20 holdings — per fund", 10)
    hdr = ["Ticker","Issuer","Value $M","%Book","Mcap","Bucket","13F","Act %","Cluster?","Name"]
    write_table_header(ws, 5, hdr)
    row = 6
    for label, like in funds:
        ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=10)
        c = ws.cell(row=row, column=1, value=label)
        c.font = BODY_ITALIC
        c.alignment = Alignment(horizontal="left", vertical="center")
        ws.row_dimensions[row].height = 18
        row += 1
        rows = list(conn.execute("""
            SELECT h.ticker, h.issuer, h.value_k, h.pct_book,
                   tm.mcap_m, us.mcap_bucket, us.smart_money_n, us.activist_max_pct,
                   us.insider_cluster_dollars_m, tm.name
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
                        cluster_mark, (r[9] or "")[:30]])
        write_table_rows(ws, out, row)
        for ridx in range(row, row + len(out)):
            ws.cell(row=ridx, column=3).number_format = NUMFMT_NUM
            ws.cell(row=ridx, column=4).number_format = NUMFMT_PCT
            ws.cell(row=ridx, column=5).number_format = NUMFMT_MCAP
            ws.cell(row=ridx, column=8).number_format = NUMFMT_PCT
        row += len(out) + 1

    row += 1
    write_section_heading(ws, row, "Shared overlap — held by both funds", 10)
    row += 1
    hdr2 = ["Ticker","Issuer","Bill IV %","Bill III %","Combined %","Mcap","Bucket","13F","Act %","Name"]
    write_table_header(ws, row, hdr2)
    row += 1
    overlap = list(conn.execute("""
        SELECT h4.ticker, h4.issuer, h4.pct_book pct4, h3.pct_book pct3,
               (h4.pct_book + h3.pct_book) AS combined,
               tm.mcap_m, us.mcap_bucket, us.smart_money_n, us.activist_max_pct, tm.name
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
                    (r[9] or "")[:30]])
    write_table_rows(ws, out, row)
    for ridx in range(row, row + len(out)):
        ws.cell(row=ridx, column=3).number_format = NUMFMT_PCT
        ws.cell(row=ridx, column=4).number_format = NUMFMT_PCT
        ws.cell(row=ridx, column=5).number_format = NUMFMT_PCT
        ws.cell(row=ridx, column=6).number_format = NUMFMT_MCAP    # mcap
        ws.cell(row=ridx, column=9).number_format = NUMFMT_PCT
    ws.freeze_panes = "B6"
    autosize(ws)
    ws.column_dimensions["A"].width = 8

TAB_COLORS = {
    # Navigation / meta — lightest
    "README":          "F2F2F2",
    "Fund Coverage":   "F2F2F2",
    "All Funds":       "F2F2F2",
    # Universe ranking — darkest
    "Top 100":         "262626",
    "Non-Biotech Top 100": "262626",
    # Size buckets — mid-dark gradient
    "Nano (<$50M)":            "404040",
    "Micro ($50M–$300M)":      "595959",
    "Small ($300M–$2B)":       "595959",
    "Mid ($2B–$10B)":          "595959",
    # Signal sheets — mid
    "Material + New":          "808080",
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
}

def main():
    conn = sqlite3.connect(DB)
    wb = openpyxl.Workbook()
    if "Sheet" in wb.sheetnames:
        wb.remove(wb["Sheet"])

    sheet_readme(wb, conn)
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
    write_signal_sheet(wb, conn, "Material + New",
        where_extra="AND (us.s3_new + us.s4_add) >= 2 AND us.mcap_bucket != 'unknown'",
        limit=80,
        subtitle="≥2 funds adding to existing (S4) OR initiating major new (S3) — smart money is BUILDING.")
    sheet_activist(wb, conn)
    sheet_insider_recent(wb, conn)
    sheet_insider_f4(wb, conn)
    sheet_clusters(wb, conn)
    write_signal_sheet(wb, conn, "Non-Biotech Top 100",
        where_extra="AND us.mcap_bucket != 'unknown'", limit=400,
        subtitle="Top 100 ex-biotech, ex-ETF, ex-mega.")
    sheet_in_the_money(wb, conn)
    sheet_revealed_pref(wb, conn)
    sheet_valuation(wb, conn)
    sheet_catalysts(wb, conn)
    sheet_global_picks(wb, conn)
    sheet_bill_miller(wb, conn)
    sheet_unknown(wb, conn)
    sheet_all_holdings_consolidated(wb, conn)
    sheet_fund_coverage(wb, conn)
    sheet_all_funds(wb, conn)

    # Tab colour-coding — grayscale tones by theme
    for sname, color in TAB_COLORS.items():
        if sname in wb.sheetnames:
            wb[sname].sheet_properties.tabColor = color

    wb.save(OUT)
    print(f"wrote {OUT}")
    print(f"sheets: {wb.sheetnames}")

if __name__ == "__main__":
    main()
