"""Ingest each fund's PRIOR-quarter 13F-HR into fund_13f_prior, so we can diff
against the current holdings and show who is BUILDING vs quietly TRIMMING — the
signal a single-quarter snapshot cannot give. Reuses ingest_13f's parser, book
writer and CUSIP-authority map so the prior quarter maps identically to the
current one.

The prior is the 13F-HR whose report period is the quarter IMMEDIATELY before
the current book's (EDGAR report dates), never merely "the second-newest
filing": that rule diffed across two quarters after a missed roll, and across
seven for a filer that skipped a year (VY Capital: Q3 2024 -> Q2 2026). A fund
with no preceding-quarter filing gets no diff. The normal quarterly roll never
comes here: ingest_13f --refresh moves the replaced book into the prior slot.
"""
import json, os, sqlite3, time, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ingest_13f as m

DB = m.DB

def normalize_units(conn):
    """Full-dollar filings booked as $k -> $k, by implied price (value/shares
    vs actual price): unit-free, immune to the megacap blind spot of an mcap
    rule; one quarter of drift is irrelevant against a ~1000x signal. Runs at
    the START of each run too: a run interrupted mid-way (SEC throttling) once
    left five books (Baillie Gifford, Eagle, Ensign Peak...) at $7T."""
    import statistics
    px = {t: p for t, p in conn.execute("SELECT ticker, price FROM ticker_yf WHERE price > 0")}
    for (fund,) in conn.execute("SELECT DISTINCT fund FROM fund_13f_prior").fetchall():
        ratios = []
        for tk, v, sh, st in conn.execute("""SELECT ticker, value_k, shares, sh_type FROM fund_13f_prior
                                             WHERE fund=? AND shares>0 AND value_k>0""", (fund,)):
            p = 1.0 if st == "PRN" else px.get(tk)   # bonds trade near par per $1 principal
            if p:
                ratios.append((v * 1000.0 / sh) / p)
        if len(ratios) >= 2 and statistics.median(ratios) > 100:
            conn.execute("UPDATE fund_13f_prior SET value_k=value_k/1000.0 WHERE fund=?", (fund,))
    # the recorded totals follow the lines: a book normalised here after its
    # state row was written kept its whole-dollar total (66 funds sat at 1000x)
    conn.execute("""UPDATE fund_13f_prior_state SET total_value_k = (SELECT COALESCE(SUM(p.value_k), 0)
        FROM fund_13f_prior p WHERE p.fund = fund_13f_prior_state.fund) WHERE accession IS NOT NULL""")
    conn.commit()

def _period(conn, acc):
    r = conn.execute("SELECT period FROM sec_13f_filings WHERE accession=? AND period != ''",
                     (acc,)).fetchone()
    return r[0] if r else None

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
    CREATE TABLE IF NOT EXISTS sec_13f_filings (
      cik TEXT, accession TEXT, form TEXT, filed TEXT, period TEXT,
      PRIMARY KEY (cik, accession));
    """)
    normalize_units(conn)              # repair an interrupted earlier run first
    name_map = m.cusip_ticker_map(conn)
    cusip_map = {c: (tk, st) for c, tk, st in
                 conn.execute("SELECT cusip, ticker, sec_type FROM cusip_map")}
    px_map = {t: p for t, p in conn.execute("SELECT ticker, price FROM ticker_yf WHERE price > 0")}
    maps = (cusip_map, name_map, px_map)
    # every fund we have a current filing + CIK for
    funds = conn.execute("""SELECT s.fund, s.cik, s.last_accession
        FROM fund_13f_state s WHERE s.cik IS NOT NULL AND s.last_accession IS NOT NULL""").fetchall()
    print(f"prior-quarter ingest: {len(funds)} funds", flush=True)
    done = skip = none = failed = redone = 0
    for fund, cik, cur_acc in funds:
        ps = conn.execute("SELECT accession FROM fund_13f_prior_state WHERE fund=?", (fund,)).fetchone()
        if ps:
            # A recorded prior must be the IMMEDIATELY preceding quarter of the
            # current book. The old rule took "the second-newest 13F-HR", which
            # after a missed roll or a filing gap diffed across 2+ quarters (or
            # against a same-quarter restatement) under a quarter-change header.
            cur_p, pri_p = _period(conn, cur_acc), _period(conn, ps[0]) if ps[0] else None
            if not ps[0] or not cur_p or (pri_p and m.qkey(pri_p) == m.qkey(m.prev_quarter(cur_p))):
                skip += 1; continue
            if not pri_p:
                skip += 1; continue      # period unknown offline: keep (validate reports it)
            conn.execute("DELETE FROM fund_13f_prior WHERE fund=?", (fund,))
            conn.execute("DELETE FROM fund_13f_prior_state WHERE fund=?", (fund,))
            redone += 1
        filings = m.f13_filings(cik)
        time.sleep(0.2)
        if filings is None:
            failed += 1; continue        # fetch failed: leave unrecorded, retry next run
        m.record_f13(conn, cik, filings)
        cur_p = next((x["period"] for x in filings if x["acc"] == cur_acc), "")
        want = m.prev_quarter(cur_p) if cur_p else None
        cands = [x for x in filings if x["form"] == "13F-HR" and x["acc"] != cur_acc
                 and want and x["period"] and m.qkey(x["period"]) == m.qkey(want)]
        got, fetch_failed = None, False
        for x in cands:                  # newest first: a same-period re-file supersedes
            rows = m.fetch_book(cik, x["acc"])
            if rows is None:
                fetch_failed = True; break
            if rows:
                got = (x, rows); break
        if fetch_failed:
            failed += 1; conn.commit(); continue
        if not got:
            # no 13F-HR for the preceding quarter (a new filer, a skipped
            # quarter): no diff is better than a diff across a gap
            conn.execute("INSERT OR REPLACE INTO fund_13f_prior_state VALUES (?,?,?,?,?)",
                         (fund, None, None, 0, 0)); conn.commit()
            none += 1; continue
        x, rows = got
        n, total_v = m.ingest_book(conn, "fund_13f_prior", fund, cik, x["acc"], x["filed"], rows, *maps)
        conn.execute("INSERT OR REPLACE INTO fund_13f_prior_state VALUES (?,?,?,?,?)",
                     (fund, x["acc"], x["filed"], n, total_v))
        conn.commit(); done += 1
        if done % 25 == 0:
            print(f"  {done} funds ingested ({skip} already current)", flush=True)
    normalize_units(conn)
    conn.commit()
    n = conn.execute("SELECT COUNT(*) FROM fund_13f_prior").fetchone()[0]
    print(f"DONE: {done} priors ingested ({redone} replaced as not the preceding quarter), "
          f"{none} with no preceding-quarter 13F, {skip} already current, {failed} fetch failures; "
          f"{n} prior holdings", flush=True)
    conn.close()
    return failed

if __name__ == "__main__":
    sys.exit(2 if run() else 0)
