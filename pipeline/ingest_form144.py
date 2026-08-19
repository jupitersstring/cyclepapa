"""Form 144 proposed-sale radar — advance insider supply signal.

Rule 144 requires an insider to file BEFORE selling restricted/control stock,
so a 144 is a PROPOSED sale — it precedes the Form 4 that later records the
actual trade. Alone it is noisy (10b5-1 plans, diversification, taxes), so we
treat it as a NEGATIVE Bayesian modifier and only surface ABNORMAL clusters:
multiple insiders proposing at once, or a proposed $ amount large vs the
company. Pulled from EDGAR full-text search (structured 144 XML since 2022).

Tables: form144(accession, ticker, filer, filed, shares, value_usd,
broker, source_url) and form144_signal(ticker, n_filers, total_m, last_filed).
"""
import json, os, re, sqlite3, subprocess, sys, time

DB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "cyclepapa.db")
UA = "cyclepapa-research admin@example.com"
LOOKBACK_DAYS = 120

def curl(url, timeout=30):
    return subprocess.run(["curl", "-sk", "--compressed", "-m", str(timeout), "-A", UA, url],
                          capture_output=True).stdout

def parse144(cik, acc):
    """Pull aggregate proposed shares + $ and broker from the 144 XML."""
    accn = acc.replace("-", "")
    body = curl(f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accn}/{acc}.txt")
    if not body:
        return None
    txt = body.decode("utf-8", "ignore")
    def fnum(pat):
        vals = [float(x.replace(",", "")) for x in re.findall(pat, txt, re.I) if x]
        return sum(vals) if vals else None
    # aggregate across securitiesSoldInPast3Months / amountOfSecuritiesSold blocks
    sh = fnum(r"<noOfUnitsSold>([\d,\.]+)</noOfUnitsSold>") \
        or fnum(r"<amtOfSecOwned>([\d,\.]+)</amtOfSecOwned>")
    val = fnum(r"<aggregateMarketValue>([\d,\.]+)</aggregateMarketValue>") \
        or fnum(r"<marketValue>([\d,\.]+)</marketValue>")
    broker = None
    b = re.search(r"<brokerName>([^<]+)</brokerName>|<nameOfBroker>([^<]+)</nameOfBroker>", txt, re.I)
    if b:
        broker = (b.group(1) or b.group(2) or "").strip()[:40]
    return {"shares": sh, "value_usd": val, "broker": broker}

def run():
    conn = sqlite3.connect(DB, timeout=60); conn.execute("PRAGMA busy_timeout=60000")
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS form144 (
      accession TEXT PRIMARY KEY, ticker TEXT, filer TEXT, filed TEXT,
      shares REAL, value_usd REAL, broker TEXT, source_url TEXT);
    CREATE INDEX IF NOT EXISTS idx_f144_tk ON form144(ticker);
    DROP TABLE IF EXISTS form144_signal;
    CREATE TABLE form144_signal (
      ticker TEXT PRIMARY KEY, n_filers INTEGER, n_filings INTEGER,
      total_m REAL, last_filed TEXT, pct_mcap REAL);
    """)
    universe = {r[0] for r in conn.execute(
        "SELECT ticker FROM unified_signal WHERE is_us=1")}
    start = time.strftime("%Y-%m-%d", time.localtime(time.time() - LOOKBACK_DAYS * 86400))
    end = time.strftime("%Y-%m-%d")
    seen = 0
    for frm in range(0, 2000, 100):
        url = (f"https://efts.sec.gov/LATEST/search-index?q=%22a%22&forms=144"
               f"&dateRange=custom&startdt={start}&enddt={end}&from={frm}&size=100")
        try:
            d = json.loads(curl(url))
        except Exception:
            break
        hits = d.get("hits", {}).get("hits", [])
        if not hits:
            break
        for h in hits:
            src = h.get("_source", {})
            names = src.get("display_names") or []
            tk = None
            for nm in names:
                mm = re.search(r"\(([A-Z][A-Z0-9.\-]{0,6})\)\s*\(CIK", nm)
                if mm:
                    tk = mm.group(1); break
            if tk not in universe:
                continue
            acc = src.get("adsh") or h.get("_id", "").split(":")[0]
            if conn.execute("SELECT 1 FROM form144 WHERE accession=?", (acc,)).fetchone():
                continue
            issuer_cik = None
            for cs in (src.get("ciks") or []):
                issuer_cik = cs; break
            filer = names[-1] if len(names) > 1 else (names[0] if names else None)
            filer = re.sub(r"\s*\(CIK.*", "", filer or "").strip()[:40]
            det = parse144(issuer_cik, acc) if issuer_cik else None
            conn.execute("INSERT OR REPLACE INTO form144 VALUES (?,?,?,?,?,?,?,?)",
                (acc, tk, filer, src.get("file_date"),
                 (det or {}).get("shares"), (det or {}).get("value_usd"),
                 (det or {}).get("broker"),
                 f"https://www.sec.gov/Archives/edgar/data/{int(issuer_cik)}/{acc.replace('-','')}/" if issuer_cik else None))
            seen += 1
            time.sleep(0.15)
        conn.commit()
        print(f"  ...{frm+len(hits)} scanned, {seen} in-universe 144s", flush=True)
        if len(hits) < 100:
            break
        time.sleep(0.3)
    # aggregate signal
    mcap = {r[0]: r[1] for r in conn.execute("SELECT ticker, mcap_m FROM ticker_yf WHERE mcap_m>0")}
    for r in conn.execute("""SELECT ticker, COUNT(DISTINCT filer) nf, COUNT(*) n,
            SUM(value_usd)/1e6 tot, MAX(filed) lf
        FROM form144 WHERE filed >= date('now','-90 days') GROUP BY ticker"""):
        mc = mcap.get(r[0])
        pct = (r[3] / mc * 100) if (mc and r[3]) else None
        conn.execute("INSERT OR REPLACE INTO form144_signal VALUES (?,?,?,?,?,?)",
                     (r[0], r[1], r[2], round(r[3] or 0, 1), r[4],
                      round(pct, 2) if pct else None))
    conn.commit()
    tot = conn.execute("SELECT COUNT(*), COUNT(DISTINCT ticker) FROM form144").fetchone()
    print(f"DONE: {tot[0]} Form 144s across {tot[1]} tickers", flush=True)
    print("\nabnormal proposed-sale clusters (>=2 filers, ranked by $ then breadth):")
    for r in conn.execute("""SELECT s.ticker, s.n_filers, s.n_filings, s.total_m, s.pct_mcap, u.score
        FROM form144_signal s LEFT JOIN unified_signal u ON u.ticker=s.ticker
        WHERE s.n_filers >= 2 ORDER BY s.total_m DESC LIMIT 20"""):
        print(f"  {r[0]:6s} filers={r[1]:2d} filings={r[2]:2d} ${r[3]:>8.1f}M "
              f"pct_mcap={r[4]}  score={r[5] or 0:.0f}")
    conn.close()

if __name__ == "__main__":
    run()
