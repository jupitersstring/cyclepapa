"""Backfill holding_sec_form for holdings ingested before titleOfClass capture.

One info-table fetch per DISTINCT accession (current + prior books share the
table, keyed by accession+cusip), extracting each line's titleOfClass and its
normalized security form (common / class / preferred / warrant / unit / right /
note / adr). Idempotent and resumable — skips accessions already backfilled.
"""
import os, sqlite3, sys, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ingest_13f as m

DB = m.DB

def run():
    conn = sqlite3.connect(DB, timeout=120); conn.execute("PRAGMA busy_timeout=120000")
    conn.execute("""CREATE TABLE IF NOT EXISTS holding_sec_form (
        accession TEXT, cusip TEXT, title_class TEXT, sec_form TEXT,
        PRIMARY KEY (accession, cusip))""")
    accs = conn.execute("""
        SELECT DISTINCT accession, cik FROM fund_13f_holdings
        UNION SELECT DISTINCT accession, cik FROM fund_13f_prior""").fetchall()
    done_acc = {a for (a,) in conn.execute("SELECT DISTINCT accession FROM holding_sec_form")}
    todo = [(a, c) for a, c in accs if a and c and a not in done_acc]
    print(f"backfill sec_form: {len(todo)} accessions ({len(done_acc)} already done)", flush=True)
    n_rows = 0
    for i, (acc, cik) in enumerate(todo):
        path = m.find_infotable(cik, acc)
        if not path:
            conn.execute("INSERT OR IGNORE INTO holding_sec_form VALUES (?,?,?,?)",
                         (acc, "__none__", None, None))
            continue
        url = path if path.startswith("http") else f"https://www.sec.gov{path}"
        body = m.curl(url)
        rows = m.parse_infotable(body) if body else []
        for r in rows:
            if not r.get("cusip"):
                continue
            conn.execute("INSERT OR REPLACE INTO holding_sec_form VALUES (?,?,?,?)",
                         (acc, r["cusip"], r.get("title"),
                          m.classify_sec_form(r.get("title"), r.get("type"))))
            n_rows += 1
        if i % 25 == 0:
            conn.commit()
            print(f"  ...{i}/{len(todo)}  ({n_rows} rows)", flush=True)
        time.sleep(0.25)
    conn.commit()
    print(f"DONE: {n_rows} sec-form rows", flush=True)
    print("\nform distribution across current holdings:")
    for r in conn.execute("""SELECT COALESCE(sf.sec_form,'?') form, COUNT(*) n
        FROM fund_13f_holdings h LEFT JOIN holding_sec_form sf
          ON sf.accession=h.accession AND sf.cusip=h.cusip
        GROUP BY form ORDER BY n DESC"""):
        print(f"  {r[0]:10s} {r[1]}")
    conn.close()

if __name__ == "__main__":
    run()
