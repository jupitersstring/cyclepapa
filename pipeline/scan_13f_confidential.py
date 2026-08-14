"""Confidential-treatment (CTR) detector for 13F filings.

A manager granted confidential treatment omits positions from the public
information table, and the COVER PAGE says so (isConfidentialOmitted=true).
The omission itself is public — the manager is telling you disclosure would
harm an ACTIVE accumulation/disposition program. Academic work (Agarwal et
al.) finds confidential positions are informed and larger.

Alone it names no ticker, so it is a Bayesian multiplier, not a selector:
CTR fund + a swap-desk accumulation spike + activist-shaped target =
priority candidate. Writes fund_13f_confidential; joined by the swap radar
and the Fund Coverage sheet.
"""
import os, re, sqlite3, sys, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ingest_13f as m

DB = m.DB
_RE = re.compile(rb"<(?:\w+:)?isConfidentialOmitted>\s*(true|1)\s*<", re.I)

def primary_doc_url(cik, acc):
    accn = acc.replace("-", "")
    import json
    body = m.curl(f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accn}/index.json")
    try:
        items = json.loads(body)["directory"]["item"]
    except Exception:
        return None
    for f in items:
        if f["name"].lower() == "primary_doc.xml":
            return f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accn}/primary_doc.xml"
    for f in items:
        if f["name"].lower().endswith(".xml") and "info" not in f["name"].lower():
            return f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accn}/{f['name']}"
    return None

def run():
    conn = sqlite3.connect(DB, timeout=60)
    conn.execute("PRAGMA busy_timeout=60000")
    conn.execute("""CREATE TABLE IF NOT EXISTS fund_13f_confidential (
        fund TEXT PRIMARY KEY, cik TEXT, accession TEXT, filed TEXT,
        omitted INTEGER, asof TEXT)""")
    rows = conn.execute("""SELECT fund, cik, last_accession, last_filed
        FROM fund_13f_state WHERE last_accession IS NOT NULL""").fetchall()
    asof = time.strftime("%Y-%m-%d")
    n_omit = 0
    for i, (fund, cik, acc, filed) in enumerate(rows):
        done = conn.execute("SELECT 1 FROM fund_13f_confidential WHERE fund=? AND accession=?",
                            (fund, acc)).fetchone()
        if done:
            continue
        url = primary_doc_url(cik, acc)
        omitted = 0
        if url:
            body = m.curl(url)
            if body and _RE.search(body):
                omitted = 1
        conn.execute("INSERT OR REPLACE INTO fund_13f_confidential VALUES (?,?,?,?,?,?)",
                     (fund, cik, acc, filed, omitted, asof))
        if omitted:
            n_omit += 1
            print(f"  CTR: {fund}  ({filed})", flush=True)
        if i % 40 == 0:
            conn.commit()
            print(f"  ...{i}/{len(rows)}", flush=True)
        time.sleep(0.3)
    conn.commit()
    total = conn.execute("SELECT COUNT(*) FROM fund_13f_confidential WHERE omitted=1").fetchone()[0]
    print(f"DONE: {total} funds currently omitting positions under confidential treatment", flush=True)
    conn.close()

if __name__ == "__main__":
    run()
