"""Add SIC sector to ticker_meta for US-listed tickers.

The Yahoo chart endpoint we use doesn't return sector/industry. SEC's
submissions feed has SIC code + description for every US filer — that's
the canonical sector classification (e.g. SIC 3826 = Laboratory
Analytical Instruments).
"""
import json, os, sqlite3, subprocess, sys, time

DB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "cyclepapa.db")
UA = "cyclepapa-research admin@example.com"

def curl(url):
    return subprocess.run(["curl","-sk","--compressed","-m","10","-A",UA, url],
                          capture_output=True).stdout

_CIKMAP = None
def cik_for(ticker):
    global _CIKMAP
    if _CIKMAP is None:
        raw = curl("https://www.sec.gov/files/company_tickers.json")
        try:
            j = json.loads(raw)
            _CIKMAP = {v["ticker"].upper(): str(v["cik_str"]).zfill(10) for v in j.values()}
        except Exception:
            _CIKMAP = {}
    return _CIKMAP.get(ticker.upper())

def sic_for(cik):
    body = curl(f"https://data.sec.gov/submissions/CIK{cik}.json")
    try:
        j = json.loads(body)
        return j.get("sic"), j.get("sicDescription")
    except Exception:
        return None, None

def run():
    conn = sqlite3.connect(DB)
    # Add sic columns if missing
    cols = {r[1] for r in conn.execute("PRAGMA table_info(ticker_meta)")}
    if "sic" not in cols:
        conn.execute("ALTER TABLE ticker_meta ADD COLUMN sic TEXT")
        conn.execute("ALTER TABLE ticker_meta ADD COLUMN sic_description TEXT")
        conn.commit()
    todo = [r[0] for r in conn.execute(
        """SELECT ticker FROM ticker_meta
           WHERE sic IS NULL AND ticker NOT LIKE '%.%'
           ORDER BY mcap_m DESC NULLS LAST""")]
    print(f"adding SIC for {len(todo)} US tickers")
    n_ok = n_fail = 0
    for i, tkr in enumerate(todo):
        cik = cik_for(tkr)
        if not cik:
            n_fail += 1; continue
        sic, desc = sic_for(cik)
        time.sleep(0.12)
        if sic:
            conn.execute("UPDATE ticker_meta SET sic=?, sic_description=? WHERE ticker=?",
                         (str(sic), desc, tkr))
            n_ok += 1
        else:
            n_fail += 1
        if i % 50 == 0 and i > 0:
            conn.commit()
            print(f"  [{i+1}/{len(todo)}] ok={n_ok} fail={n_fail}")
    conn.commit()
    print(f"done: {n_ok} sectorized, {n_fail} no-sic")

if __name__ == "__main__":
    run()
