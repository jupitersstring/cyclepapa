"""Repair (2026-09): option lines booked as holdings, stock lines labelled options.

1. Funicular files its puts and calls under option CUSIPs titled "PUT"/"CALL"
   with no putCall element. The ingest filtered on putCall only, so $2.4B of
   them sat in the current book as long positions — puts on MU, NVDA, MSFT,
   TSLA, AMZN, AVGO counted as bullish holders, mapped by issuer name.
2. backfill_sec_form wrote every infotable line, last write winning, so a
   stock line sharing its CUSIP with option lines (Marshall Wace, Tudor: 800+
   lines) was relabelled "EQUITY OPTION" and flagged option-mixed.

Every book (current or prior) holding a line whose recorded form is 'option'
is re-read from its filing through the fixed ingest path (options dropped by
putCall OR title; one holding-line title per CUSIP), and cusip_map entries
that only ever named an option line are dropped so nothing re-maps them.
Idempotent: a clean DB finds no books to repair.
"""
import os, sqlite3, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ingest_13f as m

def run():
    conn = sqlite3.connect(m.DB, timeout=120); conn.execute("PRAGMA busy_timeout=120000")
    name_map = m.cusip_ticker_map(conn)
    cusip_map = {c: (tk, st) for c, tk, st in conn.execute("SELECT cusip, ticker, sec_type FROM cusip_map")}
    px_map = {t: p for t, p in conn.execute("SELECT ticker, price FROM ticker_yf WHERE price > 0")}
    maps = (cusip_map, name_map, px_map)
    option_only, failed = set(), 0
    for table in ("fund_13f_holdings", "fund_13f_prior"):
        books = conn.execute(f"""SELECT DISTINCT h.fund, h.cik, h.accession, h.filed FROM {table} h
            JOIN holding_sec_form f ON f.accession = h.accession AND f.cusip = h.cusip
            WHERE f.sec_form = 'option'""").fetchall()
        for fund, cik, acc, filed in books:
            flagged = {r[0] for r in conn.execute(f"""SELECT h.cusip FROM {table} h
                JOIN holding_sec_form f ON f.accession = h.accession AND f.cusip = h.cusip
                WHERE h.fund = ? AND h.accession = ? AND f.sec_form = 'option'""", (fund, acc))}
            rows = m.fetch_book(cik, acc)
            if rows is None:
                print(f"  [!] {fund[:36]} {acc}: filing could not be read — left as is")
                failed += 1
                continue
            before = conn.execute(f"SELECT COUNT(*), COALESCE(SUM(value_k), 0) FROM {table} WHERE fund=? AND accession=?",
                                  (fund, acc)).fetchone()
            option_only |= flagged - {r["cusip"] for r in rows}
            conn.execute(f"DELETE FROM {table} WHERE fund=? AND accession=?", (fund, acc))
            conn.execute("DELETE FROM holding_sec_form WHERE accession=?", (acc,))
            n, total = m.ingest_book(conn, table, fund, cik, acc, filed, rows, *maps)
            if table == "fund_13f_holdings":
                conn.execute("""UPDATE fund_13f_state SET n_holdings=?, total_value_k=?
                                WHERE fund=? AND last_accession=?""", (n, total, fund, acc))
            else:
                nn, tt = conn.execute("SELECT COUNT(*), COALESCE(SUM(value_k), 0) FROM fund_13f_prior WHERE fund=?",
                                      (fund,)).fetchone()
                conn.execute("UPDATE fund_13f_prior_state SET n_holdings=?, total_value_k=? WHERE fund=?",
                             (nn, tt, fund))
            conn.commit()
            print(f"  {table[9:]:9s} {fund[:36]:36s} {before[0]:5d} lines ${before[1]/1e6:8,.1f}B -> "
                  f"{n:5d} lines ${total/1e6:8,.1f}B  ({len(flagged)} option-labelled lines re-read)")
    if option_only:
        ph = ",".join("?" * len(option_only))
        n = conn.execute(f"DELETE FROM cusip_map WHERE cusip IN ({ph}) AND source IN ('name', 'sec')",
                         sorted(option_only)).rowcount
        conn.commit()
        print(f"{len(option_only)} option-only CUSIPs; {n} name-derived cusip_map entries dropped")
    conn.close()
    return failed

if __name__ == "__main__":
    sys.exit(2 if run() else 0)
