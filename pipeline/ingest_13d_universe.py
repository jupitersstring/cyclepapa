"""Pull 13D/G filings for EVERY fund in our universe — including non-13F filers.

ingest_13d.py covers ~50 hand-curated activists. But ANY fund that crosses 5%
in a US-listed name has to file 13D/G with SEC under their holder CIK,
regardless of whether they file 13F. So Palliser, AVI, Effissimo, TCI,
Pershing Square Holdings PLC etc. — even though they don't file 13F-HR —
DO show up in EDGAR submissions as 13D/G filers under their own CIK.

This module:
  1. Gathers every fund CIK we know about (FUND_CIK + fund_resolution_state)
  2. Queries each one's submissions feed for SC 13D / SC 13G filings
  3. Parses each filing's SUBJECT COMPANY block for issuer + percentage
  4. Stores in holder_13d (extending the hand-curated set already there)

Skips funds whose status indicates 'individual' or 'meta_rollup'.
"""
import json, os, re, sqlite3, subprocess, sys, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ingest_13d import filings_13_for_holder, parse_subject, TICKER_BY_CIK, curl

DB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "cyclepapa.db")

def collect_universe_ciks(conn):
    """Return [(fund, cik)] for every fund in universe with any CIK match."""
    out = {}
    # 1. From fund_resolution_state — the auto/manual seeds
    for fund, cik in conn.execute("""
        SELECT fund, best_cik FROM fund_resolution_state
        WHERE best_cik IS NOT NULL AND best_cik != '' """):
        out[fund] = cik
    # 2. From the hardcoded FUND_CIK dict
    from ingest_13f import FUND_CIK
    for fund, cik in FUND_CIK.items():
        out.setdefault(fund, str(cik))
    return list(out.items())

def run():
    conn = sqlite3.connect(DB)
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS holder_13d (
      holder TEXT, holder_cik TEXT, form TEXT, filed TEXT, accession TEXT,
      subject_name TEXT, subject_cik TEXT, subject_ticker TEXT,
      pct_class REAL, source_url TEXT,
      PRIMARY KEY (holder_cik, accession));
    """)
    # populate TICKER_BY_CIK module-global for parse_subject() to use
    import ingest_13d as i13
    try:
        j = json.loads(curl("https://www.sec.gov/files/company_tickers.json"))
        i13.TICKER_BY_CIK = {str(v["cik_str"]): v["ticker"] for v in j.values()}
    except Exception:
        i13.TICKER_BY_CIK = {}
    print(f"loaded {len(i13.TICKER_BY_CIK)} CIK->ticker mappings\n")

    universe = collect_universe_ciks(conn)
    # skip CIKs we already queried in the hand-curated batch
    done = {r[0] for r in conn.execute("SELECT DISTINCT holder_cik FROM holder_13d")}
    pending = [(f, c) for f, c in universe if str(int(c)).zfill(10) not in done and c not in done]
    print(f"checking 13D/G for {len(pending)} funds (skipping {len(universe)-len(pending)} already cached)\n")

    n_filers = n_filings = 0
    for fund, cik in pending:
        try:
            fl = filings_13_for_holder(cik)
        except Exception as e:
            print(f"  ! {fund[:36]:<36} error: {e}")
            time.sleep(0.3); continue
        time.sleep(0.2)
        if not fl:
            time.sleep(0.1); continue
        n_filers += 1
        # parse top 5 filings (most recent first by submissions ordering)
        for f in fl[:5]:
            try:
                subj, tkr, pct, src = parse_subject(cik, f["accession"], f["primary_doc"])
            except Exception:
                subj, tkr, pct, src = None, None, None, ""
            subj_cik_back = None
            if tkr:
                subj_cik_back = next((c for c, t in i13.TICKER_BY_CIK.items() if t == tkr), None)
            conn.execute("""INSERT OR REPLACE INTO holder_13d VALUES (?,?,?,?,?,?,?,?,?,?)""",
                         (fund[:60], str(cik), f["form"], f["filed"], f["accession"],
                          subj, subj_cik_back, tkr, pct, src))
            n_filings += 1
            time.sleep(0.15)
        print(f"  {fund[:40]:<40} CIK={cik:<10} {len(fl)} SC 13D/G filings")
        conn.commit()

    print(f"\n{n_filers} funds with 13D/G filings, {n_filings} filings stored")
    print("\n--- new high-% positions (>=5%) ---")
    for r in conn.execute("""SELECT holder, subject_ticker, subject_name, form, filed, pct_class
                             FROM holder_13d WHERE subject_ticker IS NOT NULL AND pct_class >= 5
                             ORDER BY filed DESC LIMIT 25"""):
        print(f"  {r[1]:<8} {r[5]:>5.1f}%  {r[3]:<10} {r[4]:<11} {r[0][:32]:<32} ({(r[2] or '')[:32]})")

if __name__ == "__main__":
    run()
