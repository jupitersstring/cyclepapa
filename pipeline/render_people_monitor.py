"""People & Titan Tea-Leaves monitor — a SEPARATE workbook from the universe/style
books. Tracks influential individuals (hedge-fund titans, concentrated managers,
sovereign-wealth heads, dynastic family offices) sourced from PitchBook people
searches, mapped to the public companies they sit on / run, and cross-referenced
with our own smart-money signal.

Alpha logic: an active board seat / chairman / advisor role held by a tracked
principal is a "revealed placement" — where the influential money is putting its
people. Overlay our unified_signal and the strongest cell is where a titan's
board seat coincides with independent 13F accumulation.
"""
import os, sqlite3
import openpyxl
from _style_bw import (
    write_title, write_section_heading, write_table_header, write_table_rows,
    autosize, set_default_font, add_contents_index, set_print_layout,
    NUMFMT_MCAP, NUMFMT_M_TO_B,
)

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(BASE, "data", "cyclepapa.db")
OUT = os.path.join(BASE, "people_monitor.xlsx")

NEW_FUNDS = ["Cat Rock Capital Management", "Theleme Partners", "Clarkston Capital Partners",
             "Hosking Partners", "Tybourne Capital Management", "Man Group",
             "Mubadala Investment Company"]


def sheet_readme(wb, conn):
    ws = wb.create_sheet("README")
    ws.sheet_view.showGridLines = False
    n_people = conn.execute("SELECT COUNT(DISTINCT full_name) FROM pb_people").fetchone()[0]
    n_prin = conn.execute("SELECT COUNT(DISTINCT full_name) FROM pb_people WHERE is_principal=1").fetchone()[0]
    n_map = conn.execute("SELECT COUNT(DISTINCT ticker) FROM pb_affiliation WHERE ticker IS NOT NULL").fetchone()[0]
    write_title(ws, "People & Titan Tea-Leaves — Alpha Monitor",
                "Influential individuals mapped to public companies, cross-referenced with our smart-money signal.", 4)
    ws.column_dimensions["A"].width = 100
    rows = [
        ("",),
        ("What this is",),
        (f"A separate monitor tracking {n_people:,} influential individuals — hedge-fund titans, concentrated "
         "value managers, sovereign-wealth heads, and dynastic family offices — sourced from five PitchBook",),
        ("people searches. Each person's active board seats and primary affiliation are mapped to public tickers "
         "and overlaid with our own 13F / signal data.",),
        ("",),
        (f"{n_prin} of these appear as themselves (search principals); the rest surface via biography linkage.",),
        (f"{n_map} distinct tickers were matched to our universe for cross-referencing.",),
        ("",),
        ("How to read it — the alpha logic",),
        ("• 'What Titans Are Buying' — THE forward signal: recent new positions & material adds by titan-run",),
        (f"   funds ({conn.execute('SELECT COUNT(*) FROM pb_principal_fund').fetchone()[0]} legends linked to their funds — Ackman, Einhorn, Icahn, Klarman, Li Lu, Tepper...).",),
        ("• 'What Titans Own' — each legend's largest disclosed 13F positions by conviction (% of book).",),
        ("• 'Titan Consensus' — names held by MULTIPLE titans at once; where the smart money converges.",),
        ("• 'Titan-Connected Tickers' — where a titan's board seat COINCIDES with independent smart-money",),
        ("   accumulation (our smart_money_n / score). Two independent signals pointing at the same name.",),
        ("• 'Principal Positions' — where a tracked titan personally sits (board seat / chairman / advisor).",),
        ("• 'Concentrated Managers' — the roster-relevant fund managers; shows which we now track holdings for.",),
        ("• 'Family Office / SWF Map' — Gulf, royal, and billionaire-vehicle affiliations mapped to tickers.",),
        ("• 'New Roster Funds' — 7 investment firms found missing from our tracker and now ingested.",),
        ("• 'Not-in-Universe Watch' — titan-connected public companies (mostly foreign) we don't yet cover.",),
        ("",),
        ("Sources & caveats",),
        ("• Five PitchBook 'Search Result Columns' exports (Safa Amirbayat, M&G Investments, 2025-09 to 2025-10).",),
        ("• Themes: Sequoia Network; Gulf/Royal Family Offices; Billionaire/Oligarch Vehicles; Titans & "
         "Concentrated Managers.",),
        ("• One of the five files (2025-09-19) arrived physically truncated (only 64KB of the zip survived) and "
         "its rows are unrecoverable; its metadata shows a same-author 2025-09-20 search.",),
        ("• Board-seat data is a point-in-time snapshot; '(Former)' roles are flagged and excluded from live signals.",),
        ("• Name→ticker mapping is best-effort against our universe; foreign listings (Gulf/India/Europe boards) "
         "are largely outside our US-13F coverage and appear in the watchlist instead.",),
    ]
    for i, r in enumerate(rows, start=3):
        ws.cell(row=i, column=1, value=r[0])
    return ws


def sheet_titans_buying(wb, conn):
    """The forward signal: recent NEW initiations (section 3) and material ADDS
    (section 4) by titan-run funds — what they are actively buying now."""
    ws = wb.create_sheet("What Titans Are Buying")
    ws.sheet_view.showGridLines = False
    write_title(ws, "What Titans Are Buying — recent initiations & adds",
                "New positions (NEW) and material adds (ADD) from titan-run funds. The forward signal: what the smart money is accumulating now.", 6)
    hdr = ["Titan", "Fund", "Action", "Ticker", "Company", "Our Score"]
    write_table_header(ws, 4, hdr)
    rows = conn.execute("""
        SELECT pf.principal, pf.fund,
               CASE fp.section WHEN 3 THEN 'NEW' WHEN 4 THEN 'ADD' END,
               fp.ticker, u.name, u.score
        FROM pb_principal_fund pf
        JOIN fund_positions fp ON fp.fund=pf.fund AND fp.section IN (3,4) AND fp.ticker IS NOT NULL
        LEFT JOIN unified_signal u ON u.ticker=fp.ticker
        WHERE COALESCE(u.sec_type,'common')='common'
        GROUP BY pf.principal, fp.ticker, fp.section
        ORDER BY pf.principal, fp.section, (u.score IS NULL), u.score DESC""").fetchall()
    out = []
    for r in rows:
        out.append([r[0], (r[1] or "")[:30], r[2], r[3], (r[4] or "")[:26],
                    round(r[5], 1) if r[5] is not None else ""])
    write_table_rows(ws, out, 5, ticker_col=4)
    return ws


def sheet_titans_own(wb, conn):
    """What titans hold: top 13F positions by book weight, per titan-run fund."""
    ws = wb.create_sheet("What Titans Own")
    ws.sheet_view.showGridLines = False
    write_title(ws, "What Titans Own — top 13F positions by conviction",
                "Each titan-run fund's largest disclosed US positions (by % of 13F book), with our score overlay. Their standing bullish bets.", 6)
    hdr = ["Titan", "Fund", "Ticker", "Company", "% Book", "Our Score"]
    write_table_header(ws, 4, hdr)
    out = []
    links = conn.execute("SELECT principal, fund FROM pb_principal_fund ORDER BY principal").fetchall()
    for person, fund in links:
        tops = conn.execute("""
            SELECT h.ticker, u.name, h.pct_book, u.score
            FROM fund_13f_holdings h LEFT JOIN unified_signal u ON u.ticker=h.ticker
            WHERE h.fund=? AND h.ticker IS NOT NULL AND COALESCE(u.sec_type,'common')='common'
            ORDER BY h.value_k DESC LIMIT 6""", (fund,)).fetchall()
        for t in tops:
            out.append([person, (fund or "")[:28], t[0], (t[1] or "")[:26],
                        round(t[2], 1) if t[2] is not None else "",
                        round(t[3], 1) if t[3] is not None else ""])
    write_table_rows(ws, out, 5, ticker_col=3)
    for ridx in range(5, 5 + len(out)):
        ws.cell(row=ridx, column=5).number_format = '0.0"%"'
    return ws


def sheet_titan_consensus(wb, conn):
    """Where multiple titans converge — the highest-conviction consensus names."""
    ws = wb.create_sheet("Titan Consensus")
    ws.sheet_view.showGridLines = False
    write_title(ws, "Titan Consensus — where the smart money converges",
                "Tickers held by MULTIPLE titan-run funds, ranked by number of titans. Consensus conviction among tracked legends.", 6)
    hdr = ["Ticker", "Company", "# Titans", "Titans", "Our Score", "Smart$ n"]
    write_table_header(ws, 4, hdr)
    rows = conn.execute("""
        SELECT h.ticker, u.name, COUNT(DISTINCT pf.principal) nt,
               GROUP_CONCAT(DISTINCT pf.principal), u.score, u.smart_money_n
        FROM pb_principal_fund pf
        JOIN fund_13f_holdings h ON h.fund=pf.fund AND h.ticker IS NOT NULL
        LEFT JOIN unified_signal u ON u.ticker=h.ticker
        WHERE COALESCE(u.sec_type,'common')='common'
        GROUP BY h.ticker
        HAVING COUNT(DISTINCT pf.principal) >= 2
        ORDER BY nt DESC, u.score DESC LIMIT 80""").fetchall()
    out = []
    for r in rows:
        out.append([r[0], (r[1] or "")[:26], r[2], (r[3] or "")[:40],
                    round(r[4], 1) if r[4] is not None else "",
                    round(r[5], 1) if r[5] is not None else ""])
    write_table_rows(ws, out, 5, ticker_col=1)
    return ws


def sheet_principal_positions(wb, conn):
    ws = wb.create_sheet("Principal Positions")
    ws.sheet_view.showGridLines = False
    write_title(ws, "Principal Positions — where the titans personally sit",
                "Tracked individuals appearing as themselves, with active affiliations. Mapped ticker + our score where in universe.", 7)
    hdr = ["Principal", "Position", "Company", "Type", "Active", "Ticker", "Our Score"]
    write_table_header(ws, 4, hdr)
    rows = conn.execute("""
        SELECT p.full_name, p.primary_position, p.primary_company, p.primary_company_type,
               CASE WHEN p.is_former=1 THEN 'Former' ELSE 'Active' END,
               a.ticker, u.score
        FROM pb_people p
        LEFT JOIN pb_affiliation a ON a.full_name=p.full_name AND a.company=p.primary_company
        LEFT JOIN unified_signal u ON u.ticker=a.ticker
        WHERE p.is_principal=1 AND p.primary_company IS NOT NULL
        ORDER BY (u.score IS NULL), u.score DESC, p.full_name""").fetchall()
    out = []
    for r in rows:
        out.append([r[0], (r[1] or "")[:34], (r[2] or "")[:30], (r[3] or "")[:20],
                    r[4], r[5] or "", round(r[6], 1) if r[6] is not None else ""])
    write_table_rows(ws, out, 5, ticker_col=6)
    return ws


def sheet_titan_tickers(wb, conn):
    ws = wb.create_sheet("Titan-Connected Tickers")
    ws.sheet_view.showGridLines = False
    write_title(ws, "Titan-Connected Tickers — placement × smart money",
                "Tickers ranked by our score where an influential person holds an ACTIVE position. Two independent signals on one name.", 8)
    hdr = ["Ticker", "Company", "Our Score", "Smart$ n", "Sector", "# Titans", "Connected Principals", "Types"]
    write_table_header(ws, 4, hdr)
    # Principals only (is_principal=1) — the tracked titans themselves, not bio
    # associates — so a row means a titan personally placed on this company.
    rows = conn.execute("""
        SELECT a.ticker, u.name, u.score, u.smart_money_n, u.sector,
               COUNT(DISTINCT a.full_name) np,
               GROUP_CONCAT(DISTINCT a.full_name),
               GROUP_CONCAT(DISTINCT a.company_type)
        FROM pb_affiliation a
        JOIN unified_signal u ON u.ticker=a.ticker
        WHERE a.ticker IS NOT NULL AND a.is_former=0 AND a.is_principal=1
          AND u.sec_type='common'
        GROUP BY a.ticker
        ORDER BY u.score DESC LIMIT 120""").fetchall()
    out = []
    for r in rows:
        out.append([r[0], (r[1] or "")[:26], round(r[2], 1) if r[2] is not None else "",
                    round(r[3], 1) if r[3] is not None else "", (r[4] or "")[:18],
                    r[5], (r[6] or "")[:46], (r[7] or "")[:24]])
    write_table_rows(ws, out, 5, ticker_col=1)
    return ws


def sheet_concentrated_managers(wb, conn):
    ws = wb.create_sheet("Concentrated Managers")
    ws.sheet_view.showGridLines = False
    write_title(ws, "Concentrated & Titan Managers — roster status",
                "Investment-firm affiliations from the Titans search. 'Tracked' = we ingest this firm's 13F holdings.", 5)
    hdr = ["Firm", "Type", "Associated Individuals", "Theme", "Tracked?"]
    write_table_header(ws, 4, hdr)
    roster = {r[0] for r in conn.execute("SELECT fund FROM fund_meta")}
    import re
    def norm(s): return re.sub(r"[^a-z]", "", (s or "").lower())
    rnorm = {norm(f): f for f in roster}
    rows = conn.execute("""
        SELECT p.primary_company, p.primary_company_type, p.theme,
               GROUP_CONCAT(DISTINCT p.full_name)
        FROM pb_people p
        WHERE p.primary_company_type IN
              ('Asset Manager','PE/Buyout','Venture Capital','Hedge Fund','Investor',
               'Family Office (Multi)','Family Office (Single)','Growth/Expansion')
          AND p.primary_company IS NOT NULL
          AND (p.is_principal=1 OR p.primary_company_type IN ('Asset Manager','Hedge Fund'))
        GROUP BY p.primary_company
        ORDER BY p.primary_company""").fetchall()
    out = []
    for c, t, th, ppl in rows:
        cn = norm(c)
        tracked = any(cn and (cn in rk or rk in cn) and min(len(cn), len(rk)) >= 5 for rk in rnorm)
        out.append([(c or "")[:40], (t or "")[:20], (ppl or "")[:44], (th or "")[:26],
                    "Yes" if tracked else "—"])
    write_table_rows(ws, out, 5, ticker_col=1)
    return ws


def sheet_fo_swf(wb, conn):
    ws = wb.create_sheet("Family Office & SWF Map")
    ws.sheet_view.showGridLines = False
    write_title(ws, "Family Office / Sovereign-Wealth Map",
                "Gulf, royal, and billionaire-vehicle people mapped to public companies. Active affiliations, in-universe tickers first.", 6)
    hdr = ["Individual", "Company", "Type", "Theme", "Ticker", "Our Score"]
    write_table_header(ws, 4, hdr)
    rows = conn.execute("""
        SELECT p.full_name, p.primary_company, p.primary_company_type, p.theme,
               a.ticker, u.score
        FROM pb_people p
        LEFT JOIN pb_affiliation a ON a.full_name=p.full_name AND a.company=p.primary_company
        LEFT JOIN unified_signal u ON u.ticker=a.ticker
        WHERE p.theme IN ('Gulf / Royal Family Offices','Billionaire / Oligarch Vehicles')
          AND p.is_former=0 AND p.primary_company IS NOT NULL
          AND p.primary_company_type IN ('Asset Manager','PE/Buyout','Public Company',
               'Family Office (Multi)','Family Office (Single)','Investor','Real Estate')
        ORDER BY (u.score IS NULL), u.score DESC, p.full_name LIMIT 200""").fetchall()
    out = []
    for r in rows:
        out.append([r[0], (r[1] or "")[:30], (r[2] or "")[:20], (r[3] or "")[:24],
                    r[4] or "", round(r[5], 1) if r[5] is not None else ""])
    write_table_rows(ws, out, 5, ticker_col=5)
    return ws


def sheet_new_funds(wb, conn):
    ws = wb.create_sheet("New Roster Funds")
    ws.sheet_view.showGridLines = False
    write_title(ws, "New Roster Funds — added from PitchBook data",
                "Investment firms found missing from our tracker, verified as active 13F filers, now ingested. Top holding shown.", 6)
    hdr = ["Fund", "Style", "Holdings", "13F Book", "Top Holding", "Top $M"]
    write_table_header(ws, 4, hdr)
    out = []
    for f in NEW_FUNDS:
        n = conn.execute("SELECT COUNT(*) FROM fund_13f_holdings WHERE fund=?", (f,)).fetchone()[0]
        book = conn.execute("SELECT SUM(value_k)/1e3 FROM fund_13f_holdings WHERE fund=?", (f,)).fetchone()[0]
        style = conn.execute("SELECT macro_style FROM fund_style WHERE fund=?", (f,)).fetchone()
        top = conn.execute("""SELECT ticker, issuer, value_k/1e3 FROM fund_13f_holdings
            WHERE fund=? ORDER BY value_k DESC LIMIT 1""", (f,)).fetchone()
        top_name = (top[0] or top[1]) if top else ""
        out.append([f, style[0] if style else "", n, round(book or 0, 1),
                    (top_name or "")[:22], round(top[2], 1) if top else ""])
    write_table_rows(ws, out, 5, ticker_col=1)
    for ridx in range(5, 5 + len(out)):
        ws.cell(row=ridx, column=4).number_format = NUMFMT_M_TO_B
        ws.cell(row=ridx, column=6).number_format = NUMFMT_M_TO_B
    return ws


def sheet_watchlist(wb, conn):
    ws = wb.create_sheet("Not-in-Universe Watch")
    ws.sheet_view.showGridLines = False
    write_title(ws, "Titan-Connected — Not in Our Universe",
                "Public companies where a tracked individual holds an active position, but which our US-13F universe doesn't cover. Candidates.", 4)
    hdr = ["Company", "Connected Individuals", "# People", "Themes"]
    write_table_header(ws, 4, hdr)
    rows = conn.execute("""
        SELECT a.company, GROUP_CONCAT(DISTINCT a.full_name), COUNT(DISTINCT a.full_name),
               GROUP_CONCAT(DISTINCT a.theme)
        FROM pb_affiliation a
        WHERE a.company_type='Public Company' AND a.is_former=0 AND a.ticker IS NULL
        GROUP BY a.company
        HAVING COUNT(DISTINCT a.full_name) >= 1
        ORDER BY COUNT(DISTINCT a.full_name) DESC, a.company LIMIT 150""").fetchall()
    out = [[(r[0] or "")[:40], (r[1] or "")[:50], r[2], (r[3] or "")[:30]] for r in rows]
    write_table_rows(ws, out, 5, ticker_col=1)
    return ws


def run():
    conn = sqlite3.connect(DB)
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    sheet_readme(wb, conn)
    sheet_titans_buying(wb, conn)
    sheet_titans_own(wb, conn)
    sheet_titan_consensus(wb, conn)
    sheet_titan_tickers(wb, conn)
    sheet_principal_positions(wb, conn)
    sheet_concentrated_managers(wb, conn)
    sheet_fo_swf(wb, conn)
    sheet_new_funds(wb, conn)
    sheet_watchlist(wb, conn)
    for ws in wb.worksheets:
        autosize(ws)
    set_default_font(wb)
    set_print_layout(wb, header_rows=4)
    ws0 = wb["README"]
    add_contents_index(ws0, [s.title for s in wb.worksheets])
    wb.save(OUT)
    print(f"wrote {OUT}")
    conn.close()


if __name__ == "__main__":
    run()
