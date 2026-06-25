"""Fix the 18-month staleness in holder_13d by querying efts.sec.gov directly.

The submissions API recent[0:80] window is filled with Form 4 / 144 for
high-volume filers (Starboard, Elliott, Icahn, etc.), pushing SC 13D/G
filings off the list. Result: holder_13d capped at Dec 2024 when today
is June 2026.

This module queries efts.sec.gov full-text search per holder CIK with:
  forms=SC 13D, SC 13D/A, SC 13G, SC 13G/A
  dateRange=2025-01-01 to today

Adds rows to holder_13d (idempotent via PRIMARY KEY on holder_cik+accession).
Then parses subject ticker + percentage from each filing.
"""
import json, os, re, sqlite3, subprocess, sys, time

DB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "cyclepapa.db")
UA = "cyclepapa-research admin@example.com"

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ingest_13d import parse_subject, TICKER_BY_CIK

def curl(url, timeout=20):
    out = subprocess.run(["curl","-sk","--compressed","-m",str(timeout),"-A",UA, url],
                         capture_output=True).stdout
    return out

def efts_sc13_search(cik, start="2025-01-01", end="2026-12-31"):
    """Hit efts.sec.gov for all SC 13D/G filings by this CIK in the date range.
    Returns list of (accession, form, file_date, primary_doc)."""
    cik_padded = str(cik).zfill(10)
    out = []
    page_from = 0
    while True:
        url = (f"https://efts.sec.gov/LATEST/search-index?"
               f"q=&forms=SC+13D,SC+13D/A,SC+13G,SC+13G/A"
               f"&dateRange=custom&startdt={start}&enddt={end}"
               f"&ciks={cik_padded}&hits=100&from={page_from}")
        body = curl(url)
        if not body: break
        try:
            j = json.loads(body)
        except Exception:
            break
        hits = j.get("hits", {}).get("hits", [])
        if not hits: break
        for h in hits:
            s = h.get("_source", {})
            adsh = s.get("adsh", "")
            form = s.get("form", "")
            dt = s.get("file_date", "")
            # primary_doc — use the _id which is e.g. "0001517137-26-000123:primary_doc.xml"
            doc = h.get("_id", ":").split(":")[1] if ":" in h.get("_id","") else ""
            out.append((adsh, form, dt, doc))
        if len(hits) < 100: break
        page_from += 100
        time.sleep(0.3)
    return out

def collect_holders(conn):
    """All HOLDER CIKs we care about — any CIK that's a fund in fund_resolution_state
    OR is already a holder in holder_13d."""
    out = {}
    # known fund CIKs
    for r in conn.execute("""SELECT fund, best_cik FROM fund_resolution_state
        WHERE best_cik IS NOT NULL AND best_cik != ''"""):
        out[r[1]] = r[0]
    # existing holder_13d CIKs (curated activists from ingest_13d.HOLDERS)
    for r in conn.execute("""SELECT DISTINCT holder, holder_cik FROM holder_13d"""):
        out.setdefault(r[1], r[0])
    return list(out.items())

def run():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    # Make sure ticker map is loaded
    import ingest_13d as i13
    try:
        j = json.loads(curl("https://www.sec.gov/files/company_tickers.json"))
        i13.TICKER_BY_CIK = {str(v["cik_str"]): v["ticker"] for v in j.values()}
        print(f"loaded {len(i13.TICKER_BY_CIK)} CIK→ticker mappings\n")
    except Exception as e:
        print(f"warn: ticker map load failed: {e}")

    holders = collect_holders(conn)
    print(f"refreshing 13D/G for {len(holders)} holder CIKs (2025-01-01 → today)\n")

    n_holders_with_new = n_new_filings = n_parsed = 0
    for cik, name in holders:
        filings = efts_sc13_search(cik)
        time.sleep(0.4)
        if not filings: continue
        new_this_holder = 0
        for adsh, form, dt, doc in filings:
            existing = conn.execute("SELECT 1 FROM holder_13d WHERE holder_cik=? AND accession=?",
                                    (cik, adsh)).fetchone()
            if existing: continue
            # parse subject
            try:
                subj, tkr, pct, src = parse_subject(cik, adsh, doc or "primary_doc.xml")
            except Exception:
                subj, tkr, pct, src = None, None, None, ""
            subj_cik_back = None
            if tkr:
                subj_cik_back = next((c for c, t in i13.TICKER_BY_CIK.items() if t == tkr), None)
            conn.execute("""INSERT OR REPLACE INTO holder_13d VALUES (?,?,?,?,?,?,?,?,?,?)""",
                         (name[:60], str(cik), form, dt, adsh,
                          subj, subj_cik_back, tkr, pct, src))
            new_this_holder += 1
            n_new_filings += 1
            if tkr: n_parsed += 1
            time.sleep(0.15)
        if new_this_holder:
            n_holders_with_new += 1
            print(f"  + {name[:38]:<38} CIK={cik:<8} {new_this_holder} new filings (total this holder)")
        conn.commit()

    print(f"\ndone: {n_new_filings} new 13D/G filings across {n_holders_with_new} holders ({n_parsed} parsed to ticker)")

if __name__ == "__main__":
    run()
