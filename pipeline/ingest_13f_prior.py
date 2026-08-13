"""Ingest each fund's PRIOR-quarter 13F-HR into fund_13f_prior, so we can diff
against the current holdings and show who is BUILDING vs quietly TRIMMING — the
signal a single-quarter snapshot cannot give. Reuses ingest_13f's parser + the
CUSIP-authority map so the prior quarter maps identically to the current one.
"""
import json, os, sqlite3, time, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ingest_13f as m

DB = m.DB

def nth_13f_acc(cik, n=1):
    """(accession, filed) of the n-th most recent 13F-HR (0 = latest, 1 = prior)."""
    data = m.curl(f"https://data.sec.gov/submissions/CIK{str(cik).zfill(10)}.json")
    if not data:
        return None, None
    try:
        rec = json.loads(data)["filings"]["recent"]
    except (json.JSONDecodeError, KeyError):
        return None, None
    hits = [(rec["accessionNumber"][i], rec["filingDate"][i])
            for i, f in enumerate(rec["form"]) if f == "13F-HR"]
    return hits[n] if len(hits) > n else (None, None)

def run():
    conn = sqlite3.connect(DB); conn.execute("PRAGMA busy_timeout=30000")
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS fund_13f_prior (
      fund TEXT, cik TEXT, accession TEXT, filed TEXT,
      issuer TEXT, cusip TEXT, ticker TEXT, value_k INTEGER, shares INTEGER,
      sh_type TEXT, pct_book REAL,
      PRIMARY KEY (fund, accession, cusip));
    CREATE INDEX IF NOT EXISTS idx_prior_ticker ON fund_13f_prior(ticker);
    CREATE INDEX IF NOT EXISTS idx_prior_fund ON fund_13f_prior(fund);
    CREATE TABLE IF NOT EXISTS fund_13f_prior_state (
      fund TEXT PRIMARY KEY, accession TEXT, filed TEXT, n_holdings INTEGER, total_value_k INTEGER);
    """)
    name_map = m.cusip_ticker_map(conn)
    cusip_map = {c: (tk, st) for c, tk, st in
                 conn.execute("SELECT cusip, ticker, sec_type FROM cusip_map")}
    # every fund we have a current filing + CIK for
    funds = conn.execute("""SELECT s.fund, s.cik, s.last_accession
        FROM fund_13f_state s WHERE s.cik IS NOT NULL AND s.last_accession IS NOT NULL""").fetchall()
    print(f"prior-quarter ingest: {len(funds)} funds", flush=True)
    done = skip = 0
    for fund, cik, cur_acc in funds:
        if conn.execute("SELECT 1 FROM fund_13f_prior_state WHERE fund=?", (fund,)).fetchone():
            skip += 1; continue
        acc, filed = nth_13f_acc(cik, 1)
        time.sleep(0.35)
        if not acc or acc == cur_acc:
            conn.execute("INSERT OR REPLACE INTO fund_13f_prior_state VALUES (?,?,?,?,?)",
                         (fund, acc, filed, 0, 0)); conn.commit()
            continue
        path = m.find_infotable(cik, acc)
        if not path:
            continue
        url = path if path.startswith("http") else f"https://www.sec.gov{path}"
        body = m.curl(url)
        rows = m.parse_infotable(body) if body else []
        if not rows:
            continue
        total_v = sum(r["value_k"] for r in rows)
        for r in rows:
            # Same guards as current-quarter ingest: skip empty-filing markers,
            # never consult the authority map for shared placeholder CUSIPs.
            if not r["value_k"] and not r["shares"]:
                continue
            cusip_ok = r["cusip"] and len(r["cusip"]) == 9 and len(set(r["cusip"])) > 1
            cm = cusip_map.get(r["cusip"]) if cusip_ok else None
            tkr = (cm[0] if cm[1] != "etf" else None) if cm is not None else m.name_to_ticker(r["issuer"], name_map)
            pct = (r["value_k"] / total_v * 100) if total_v else None
            conn.execute("INSERT OR REPLACE INTO fund_13f_prior VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                         (fund, cik, acc, filed, r["issuer"], r["cusip"], tkr,
                          r["value_k"], r["shares"], r["type"], pct))
        conn.execute("INSERT OR REPLACE INTO fund_13f_prior_state VALUES (?,?,?,?,?)",
                     (fund, acc, filed, len(rows), total_v))
        conn.commit(); done += 1
        if done % 25 == 0:
            print(f"  {done} funds ingested ({skip} skipped)", flush=True)
    # same value-unit straggler normalization as current (recent filings in dollars)
    for (fund,) in conn.execute("""SELECT p.fund FROM fund_13f_prior p JOIN ticker_yf y ON y.ticker=p.ticker
            WHERE y.mcap_m>0 AND p.value_k/1e3 > y.mcap_m*1.5 GROUP BY p.fund
            HAVING COUNT(*)*1.0/(SELECT COUNT(*) FROM fund_13f_prior x WHERE x.fund=p.fund) > 0.5""").fetchall():
        conn.execute("UPDATE fund_13f_prior SET value_k=value_k/1000.0 WHERE fund=?", (fund,))
    conn.commit()
    n = conn.execute("SELECT COUNT(*) FROM fund_13f_prior").fetchone()[0]
    print(f"DONE: {done} funds, {n} prior holdings", flush=True)
    conn.close()

if __name__ == "__main__":
    run()
