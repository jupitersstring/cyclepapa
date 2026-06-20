"""Render the data-driven universe analysis to a single comprehensive workbook.

Output: universe_analysis.xlsx

Sheets:
  1. README                  — methodology + universe scope
  2. Top 100 All Buckets     — pure rank by unified_signal.score
  3. Top SMALL Cap           — $300M-$2B leaderboard
  4. Top MICRO Cap           — $50M-$300M leaderboard
  5. Top NANO Cap            — <$50M leaderboard
  6. Top MID Cap             — $2B-$10B leaderboard
  7. Material Adds + New     — S3/S4 confluence (smart money building)
  8. Activist Concentration  — >=10% 13D/G positions
  9. Insider Form 4 Leaders  — recent open-market buys ranked
  10. Live Insider Clusters  — ≤180d insider buy clusters
  11. Multi-Fund Consensus   — high-13F-holder counts (ex mega/ETF)
  12. Non-Biotech Filter     — biotech-excluded via SIC
  13. Unknown Mcap Category  — tried+failed enrichment (explicit gap)
  14. Fund Coverage          — 424/445 status + 21 documented blind
  15. All Funds Status       — per-fund inventory
"""
import os, sqlite3
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

DB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "cyclepapa.db")
OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "universe_analysis.xlsx")

# Styles
HDR_FONT = Font(bold=True, color="FFFFFF", size=10)
HDR_FILL = PatternFill("solid", fgColor="305496")
TITLE_FONT = Font(bold=True, size=14, color="305496")
SUB_FONT = Font(italic=True, color="595959", size=9)
THIN = Side(border_style="thin", color="D9D9D9")
BOX = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
ALT_FILL = PatternFill("solid", fgColor="F2F2F2")
NUMFMT_USD = '"$"#,##0'
NUMFMT_M = '"$"#,##0"M"'
NUMFMT_PCT = '0.0"%"'
NUMFMT_NUM = '#,##0.0'

ETFs = {"SPY","QQQ","VOO","IWM","IEF","IEFA","EFA","EEM","BIL","IVV","XBI","HYG",
        "GLD","SLV","TLT","XLE","XLF","XLK","XLY","XLP","XLU","XLI","XLV","XLB","XLRE",
        "ARKK","JNK","LQD","TIP","AGG","BND","VEA","VWO","SHY","TIPS"}
MEGA = {"AMZN","MSFT","NVDA","META","GOOGL","GOOG","AAPL","TSLA","BRK-A","BRK-B"}
BIOTECH_PATTERNS = ("pharmaceutic","biological","therapeutic","biotech")

def is_biotech(desc):
    if not desc: return False
    d = desc.lower()
    return any(p in d for p in BIOTECH_PATTERNS)

def write_header(ws, cols, row=1):
    for i, h in enumerate(cols, 1):
        c = ws.cell(row=row, column=i, value=h)
        c.font = HDR_FONT
        c.fill = HDR_FILL
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        c.border = BOX

def autosize(ws):
    for col in ws.columns:
        try:
            letter = get_column_letter(col[0].column)
        except Exception:
            continue
        max_len = 0
        for c in col:
            if c.value is not None:
                max_len = max(max_len, min(len(str(c.value)), 50))
        ws.column_dimensions[letter].width = max(8, min(max_len + 2, 40))

def write_rows(ws, rows, start_row=2, alt_shading=True):
    for i, row in enumerate(rows):
        for j, v in enumerate(row, 1):
            c = ws.cell(row=start_row+i, column=j, value=v)
            if alt_shading and i % 2 == 1:
                c.fill = ALT_FILL
            c.border = BOX

# ---------------------------------------------------------------------------
def sheet_readme(wb, conn):
    ws = wb.create_sheet("README", 0)
    ws.merge_cells("A1:H1")
    ws.cell(row=1, column=1, value="cyclepapa universe analysis — data-driven ranking").font = TITLE_FONT
    rows = [
        ("",),
        ("Universe scope:",),
        (f"  unified_signal table covers {conn.execute('SELECT COUNT(*) FROM unified_signal').fetchone()[0]} tickers",),
        (f"  = union of fund_13f_holdings ∪ fund_positions ∪ holder_13d.subject_ticker",),
        ("",),
        ("Score formula (pipeline/unified_score.py):",),
        ("  score = log(n_funds_13F) × 2          ← smart-money consensus weight",),
        ("        + 3.0 × n_funds_section3        ← new MAJOR positions (XLSX-tagged)",),
        ("        + 1.5 × n_funds_section4        ← existing positions MATERIALLY added",),
        ("        + 2.0 × n_funds_section1        ← top picks / highest conviction",),
        ("        + 0.5 × activist_max_pct        ← 13D/G concentration (capped 30%)",),
        ("        + cluster_step(n_insiders)      ← live insider buy cluster (≤180d)",),
        ("        + log(form4_dollars + 1) × 2    ← cumulative open-market buying $M",),
        ("        + micro_bonus                   ← +5 if <$300M, +3 if <$2B",),
        ("        + 0.5 × expected_return_pct     ← base-rate weighted 12mo excess",),
        ("",),
        ("Data sources (all primary):",),
        ("  fund_13f_holdings:  71,706 rows from SEC 13F-HR XML across 306 funds",),
        ("  fund_positions:      6,748 rows from XLSX research-team classifications",),
        ("  holder_13d:            563 SC 13D/G filings under HOLDER CIK",),
        ("  form4_transactions:   ~900 P-code open-market insider buys (≤180d)",),
        ("  insider_clusters:        6 live clusters",),
        ("  ticker_meta:         5,590 enriched rows (Yahoo chart + SEC XBRL)",),
        ("",),
        ("Fund coverage: 424 / 445 = 95.3%",),
        ("Ticker mcap coverage: 4,433 / 5,862 = 76% (rest in explicit 'unknown' bucket)",),
        ("Ticker SIC coverage: 5,064 / 5,862 = 86%",),
        ("",),
        ("Filters applied across sheets:",),
        ("  EX-ETF:    SPY/QQQ/IWM/XL*/sector ETFs removed for noise reduction",),
        ("  EX-MEGA:   top-10 mega-caps removed for clarity (they always rank high)",),
        ("  EX-BIO:    per user pref, SIC matching pharmaceutic/biological/therapeutic excluded where noted",),
    ]
    for i, r in enumerate(rows, 2):
        c = ws.cell(row=i, column=1, value=r[0])
        if r[0].startswith("  ") or not r[0].strip():
            c.font = Font(name="Consolas", size=10)
        elif r[0].endswith(":"):
            c.font = Font(bold=True, size=11, color="305496")
        else:
            c.font = Font(size=10)
    ws.column_dimensions["A"].width = 100

def get_signal_rows(conn, where_extra="", limit=None, params=()):
    sql = """SELECT us.ticker, us.score, us.mcap_m, us.mcap_bucket, us.smart_money_n,
        us.s1_top, us.s3_new, us.s4_add, us.activist_max_pct, us.activist_filings,
        us.insider_cluster_dollars_m, us.insider_n, us.form4_buy_usd_m,
        us.expected_return_pct, tm.name, tm.sic_description, tm.exchange, tm.price
        FROM unified_signal us
        LEFT JOIN ticker_meta tm ON tm.ticker = us.ticker
        WHERE 1=1 """ + where_extra + " ORDER BY us.score DESC"
    if limit: sql += f" LIMIT {limit}"
    return list(conn.execute(sql, params))

SIG_HDR = ["Ticker","Score","Mcap $M","Bucket","13F #","S1","S3","S4","Act %","13D #",
           "Cluster $M","Cluster #","F4 $M","ER %","Name","Sector","Exch","Price"]

def write_signal_sheet(wb, conn, name, where_extra="", limit=200, top_note=""):
    ws = wb.create_sheet(name)
    if top_note:
        ws.cell(row=1, column=1, value=top_note).font = SUB_FONT
        ws.merge_cells(f"A1:{get_column_letter(len(SIG_HDR))}1")
        hdr_row = 2
    else:
        hdr_row = 1
    write_header(ws, SIG_HDR, row=hdr_row)
    rows = get_signal_rows(conn, where_extra=where_extra, limit=limit)
    # apply ex-ETF + ex-mega filter
    rows = [r for r in rows if r[0] not in ETFs and r[0] not in MEGA]
    out_rows = []
    for r in rows:
        out_rows.append([r[0], round(r[1] or 0, 1), r[2] or "", r[3] or "",
                         r[4] or 0, r[5] or 0, r[6] or 0, r[7] or 0,
                         r[8] or 0, r[9] or 0,
                         round(r[10] or 0, 1) if r[10] else "",
                         r[11] or "",
                         round(r[12] or 0, 1) if r[12] else "",
                         round(r[13] or 0, 1) if r[13] else "",
                         (r[14] or "")[:35], (r[15] or "")[:35],
                         (r[16] or "")[:12], r[17] or ""])
    write_rows(ws, out_rows, start_row=hdr_row+1)
    # format columns
    for ridx in range(hdr_row+1, hdr_row+1+len(out_rows)):
        ws.cell(row=ridx, column=3).number_format = NUMFMT_USD  # mcap
        ws.cell(row=ridx, column=9).number_format = NUMFMT_PCT  # act
        ws.cell(row=ridx, column=11).number_format = NUMFMT_NUM
        ws.cell(row=ridx, column=13).number_format = NUMFMT_NUM
        ws.cell(row=ridx, column=14).number_format = NUMFMT_PCT
        ws.cell(row=ridx, column=18).number_format = '"$"#,##0.00'
    ws.freeze_panes = ws.cell(row=hdr_row+1, column=2)
    autosize(ws)

def sheet_activist(wb, conn):
    ws = wb.create_sheet("Activist 13D 10+pct")
    note = "Holder filed SC 13D/G disclosing ≥10% stake. From holder_13d aggregated by subject_ticker. Non-biotech."
    ws.cell(row=1, column=1, value=note).font = SUB_FONT
    hdr = ["Ticker","Mcap $M","Bucket","Activist %","13D Filings","13F Holders","Name","Sector"]
    write_header(ws, hdr, row=2)
    rows = list(conn.execute("""
        SELECT us.ticker, us.mcap_m, us.mcap_bucket,
               us.activist_max_pct, us.activist_filings, us.smart_money_n,
               tm.name, tm.sic_description
        FROM unified_signal us
        LEFT JOIN ticker_meta tm ON tm.ticker = us.ticker
        WHERE us.activist_max_pct >= 10
        ORDER BY us.activist_max_pct DESC"""))
    out = []
    for r in rows:
        if r[0] in ETFs or r[0] in MEGA: continue
        if is_biotech(r[7]): continue
        out.append([r[0], r[1] or "", r[2] or "", round(r[3] or 0, 1),
                    r[4] or 0, r[5] or 0,
                    (r[6] or "")[:35], (r[7] or "")[:30]])
    write_rows(ws, out, start_row=3)
    ws.freeze_panes = ws.cell(row=3, column=2)
    autosize(ws)

def sheet_insider(wb, conn):
    ws = wb.create_sheet("Insider F4 Leaders")
    note = "≤180-day Form 4 P-code open-market buys, sorted by dollar volume. Includes mcap + smart-money cross."
    ws.cell(row=1, column=1, value=note).font = SUB_FONT
    hdr = ["Ticker","Buy $M","# Buyers","Avg Px","Mcap $M","Bucket","13F #","S1","S3","S4","Name","Sector"]
    write_header(ws, hdr, row=2)
    rows = list(conn.execute("""
        SELECT f.ticker, SUM(f.shares*f.price)/1e6 AS dollars_m,
               COUNT(DISTINCT f.owner), AVG(f.price),
               tm.mcap_m, us.mcap_bucket,
               us.smart_money_n, us.s1_top, us.s3_new, us.s4_add,
               tm.name, tm.sic_description
        FROM form4_transactions f
        LEFT JOIN ticker_meta tm ON tm.ticker = f.ticker
        LEFT JOIN unified_signal us ON us.ticker = f.ticker
        WHERE f.code='P' AND f.acquired=1
          AND f.trans_date >= date('now','-180 days')
        GROUP BY f.ticker
        HAVING dollars_m >= 0.1
        ORDER BY dollars_m DESC"""))
    out = []
    for r in rows:
        out.append([r[0], round(r[1], 1), r[2], round(r[3] or 0, 2),
                    r[4] or "", r[5] or "unknown",
                    r[6] or 0, r[7] or 0, r[8] or 0, r[9] or 0,
                    (r[10] or "")[:35], (r[11] or "")[:30]])
    write_rows(ws, out, start_row=3)
    ws.freeze_panes = ws.cell(row=3, column=2)
    autosize(ws)

def sheet_clusters(wb, conn):
    ws = wb.create_sheet("Insider Clusters Live")
    note = "Live insider buy clusters from insider_clusters table (window ≤180d)."
    ws.cell(row=1, column=1, value=note).font = SUB_FONT
    hdr = ["Ticker","Trigger","Window End","# Insiders","Cluster $M","Avg Px","Top Buyer","Mcap $M","Bucket"]
    write_header(ws, hdr, row=2)
    rows = list(conn.execute("""
        SELECT ic.ticker, ic.trigger, ic.window_end, ic.n_insiders, ic.total_usd_m,
               ic.avg_price, ic.top_buyer, tm.mcap_m, us.mcap_bucket
        FROM insider_clusters ic
        LEFT JOIN ticker_meta tm ON tm.ticker = ic.ticker
        LEFT JOIN unified_signal us ON us.ticker = ic.ticker
        WHERE DATE(ic.window_end) >= DATE('now', '-180 days')
        ORDER BY ic.total_usd_m DESC"""))
    out = [[r[0], r[1], r[2], r[3], round(r[4] or 0, 2), round(r[5] or 0, 2),
            r[6][:25] if r[6] else "", r[7] or "", r[8] or "unknown"] for r in rows]
    write_rows(ws, out, start_row=3)
    ws.freeze_panes = ws.cell(row=3, column=2)
    autosize(ws)

def sheet_unknown_bucket(wb, conn):
    ws = wb.create_sheet("Unknown Mcap (cat)")
    note = "Tickers where Yahoo+SEC XBRL share-out lookup failed. Explicit category. Mostly foreign listings, SPACs, warrants, defunct/delisted."
    ws.cell(row=1, column=1, value=note).font = SUB_FONT
    hdr = ["Ticker","Score","Bucket","13F #","S1","S3","S4","Act %","F4 $M","Name","Sector","Exch","Price"]
    write_header(ws, hdr, row=2)
    rows = list(conn.execute("""
        SELECT us.ticker, us.score, us.mcap_bucket, us.smart_money_n,
               us.s1_top, us.s3_new, us.s4_add, us.activist_max_pct, us.form4_buy_usd_m,
               tm.name, tm.sic_description, tm.exchange, tm.price
        FROM unified_signal us
        LEFT JOIN ticker_meta tm ON tm.ticker = us.ticker
        WHERE us.mcap_bucket = 'unknown'
        ORDER BY us.score DESC LIMIT 250"""))
    out = []
    for r in rows:
        if r[0] in ETFs: continue
        out.append([r[0], round(r[1] or 0, 1), r[2] or "",
                    r[3] or 0, r[4] or 0, r[5] or 0, r[6] or 0,
                    round(r[7] or 0, 1), round(r[8] or 0, 1) if r[8] else "",
                    (r[9] or "")[:35], (r[10] or "")[:30],
                    (r[11] or "")[:12], r[12] or ""])
    write_rows(ws, out, start_row=3)
    ws.freeze_panes = ws.cell(row=3, column=2)
    autosize(ws)

def sheet_fund_coverage(wb, conn):
    ws = wb.create_sheet("Fund Coverage Summary")
    ws.cell(row=1, column=1, value="Fund coverage: 424 of 445 = 95.3%").font = TITLE_FONT
    hdr = ["Category","Count","Pct"]
    write_header(ws, hdr, row=3)
    cats = list(conn.execute("""
        SELECT
          CASE
            WHEN st.n_holdings > 0 THEN '1. 13F-HR holdings ingested'
            WHEN fp.fund IS NOT NULL AND h.holder IS NOT NULL THEN '2. fund_positions + 13D/G'
            WHEN fp.fund IS NOT NULL THEN '3. fund_positions only'
            WHEN h.holder IS NOT NULL THEN '4. 13D/G only (foreign activists)'
            WHEN fr.status LIKE '%non_filer%' THEN '5. Foreign non-filer (explicit)'
            WHEN fr.status = 'below_13f_threshold' THEN '6. Below AUM threshold'
            WHEN fr.status = 'non_equity_strategy' THEN '7. CTA/options (no equity to track)'
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
    write_rows(ws, out, start_row=4)
    autosize(ws)

def sheet_all_funds(wb, conn):
    ws = wb.create_sheet("All Funds (per-fund status)")
    hdr = ["Fund","Resolution Status","CIK","13F #Holdings","13F Total $M","13D/G #Filings","Positions Count"]
    write_header(ws, hdr, row=1)
    rows = list(conn.execute("""
        SELECT fm.fund,
               fr.status,
               fr.best_cik,
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
        out.append([r[0][:60], r[1] or "", r[2] or "",
                    r[3], round(r[4] or 0), r[5], r[6]])
    write_rows(ws, out, start_row=2)
    ws.freeze_panes = ws.cell(row=2, column=2)
    autosize(ws)

def main():
    conn = sqlite3.connect(DB)
    wb = openpyxl.Workbook()
    # Remove default sheet
    if "Sheet" in wb.sheetnames:
        wb.remove(wb["Sheet"])

    sheet_readme(wb, conn)
    write_signal_sheet(wb, conn, "Top 100 All Buckets",
                       where_extra="AND us.mcap_bucket != 'unknown'",
                       limit=120,
                       top_note="Top 100 by unified_score across the full 5,862-ticker universe (ex-ETF/mega-cap, mcap known)")
    write_signal_sheet(wb, conn, "Top SMALL Cap",
                       where_extra="AND us.mcap_bucket = 'small'",
                       limit=50,
                       top_note="Top SMALL CAP ($300M–$2B) by unified_score")
    write_signal_sheet(wb, conn, "Top MICRO Cap",
                       where_extra="AND us.mcap_bucket = 'micro'",
                       limit=50,
                       top_note="Top MICRO CAP ($50M–$300M) by unified_score")
    write_signal_sheet(wb, conn, "Top NANO Cap",
                       where_extra="AND us.mcap_bucket = 'nano'",
                       limit=50,
                       top_note="Top NANO CAP (<$50M) by unified_score")
    write_signal_sheet(wb, conn, "Top MID Cap",
                       where_extra="AND us.mcap_bucket = 'mid'",
                       limit=50,
                       top_note="Top MID CAP ($2B–$10B) by unified_score")
    # Material adds + new positions (S3 + S4)
    write_signal_sheet(wb, conn, "Material Adds + New",
                       where_extra="AND (us.s3_new + us.s4_add) >= 2 AND us.mcap_bucket != 'unknown'",
                       limit=80,
                       top_note="≥2 funds adding to existing (S4) OR initiating major new (S3) — smart money is BUILDING")

    sheet_activist(wb, conn)
    sheet_insider(wb, conn)
    sheet_clusters(wb, conn)

    # Non-biotech top picks
    ws = wb.create_sheet("Non-Biotech Top 100")
    ws.cell(row=1, column=1,
            value="Top 100 ex-biotech (SIC pharmaceutic/biological/therapeutic excluded), ex-ETF, ex-mega-cap, mcap known").font = SUB_FONT
    write_header(ws, SIG_HDR, row=2)
    rows = get_signal_rows(conn, where_extra="AND us.mcap_bucket != 'unknown'", limit=400)
    out = []
    for r in rows:
        if r[0] in ETFs or r[0] in MEGA: continue
        if is_biotech(r[15]): continue
        out.append([r[0], round(r[1] or 0, 1), r[2] or "", r[3] or "",
                    r[4] or 0, r[5] or 0, r[6] or 0, r[7] or 0,
                    r[8] or 0, r[9] or 0,
                    round(r[10] or 0, 1) if r[10] else "",
                    r[11] or "",
                    round(r[12] or 0, 1) if r[12] else "",
                    round(r[13] or 0, 1) if r[13] else "",
                    (r[14] or "")[:35], (r[15] or "")[:35],
                    (r[16] or "")[:12], r[17] or ""])
        if len(out) >= 100: break
    write_rows(ws, out, start_row=3)
    ws.freeze_panes = ws.cell(row=3, column=2)
    autosize(ws)

    sheet_unknown_bucket(wb, conn)
    sheet_fund_coverage(wb, conn)
    sheet_all_funds(wb, conn)

    wb.save(OUT)
    print(f"wrote {OUT}")
    print(f"sheets: {wb.sheetnames}")

if __name__ == "__main__":
    main()
