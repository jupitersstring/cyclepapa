"""Live corporate-action radar from EDGAR full-text search (efts.sec.gov).

Filings that mean a control event is ALREADY IN MOTION — the "evidence that
something is beginning" dimension:

  PREC14A / DEFC14A / DFAN14A  contested proxy materials (proxy fight)
  SC TO-T / SC TO-I            tender offers (third-party / issuer)
  SC 13E3                      going-private transaction
  PREM14A                      merger proxy (deal signed)

EFTS returns display_names like "Company Name  (TICK)  (CIK 0001234567)" —
ticker parsed from there. Table: corp_actions(form, filed, company, ticker,
accession). Joined by the swap radar as a shadow-score multiplier and
rendered in the Catalysts context.
"""
import json, os, re, sqlite3, subprocess, time

DB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "cyclepapa.db")
UA = "cyclepapa-research admin@example.com"

FORMS = ["PREC14A", "DEFC14A", "DFAN14A", "SC TO-T", "SC TO-I", "SC 13E3", "PREM14A"]
LOOKBACK_DAYS = 270

def curl(url):
    return subprocess.run(["curl", "-sk", "--compressed", "-m", "30", "-A", UA, url],
                          capture_output=True).stdout

def run():
    conn = sqlite3.connect(DB, timeout=60)
    conn.execute("PRAGMA busy_timeout=60000")
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS corp_actions (
      form TEXT, filed TEXT, company TEXT, ticker TEXT, accession TEXT,
      PRIMARY KEY (form, accession));
    CREATE INDEX IF NOT EXISTS idx_corpact_tk ON corp_actions(ticker);
    """)
    start = time.strftime("%Y-%m-%d", time.localtime(time.time() - LOOKBACK_DAYS * 86400))
    end = time.strftime("%Y-%m-%d")
    n_new = 0
    for form in FORMS:
        got = 0
        for frm in range(0, 800, 100):
            url = (f"https://efts.sec.gov/LATEST/search-index?q=%22a%22&forms={form.replace(' ', '+')}"
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
                acc = src.get("adsh") or h.get("_id", "").split(":")[0]
                filed = src.get("file_date")
                names = src.get("display_names") or []
                company = ticker = None
                for nm in names:
                    m = re.match(r"(.*?)\s*\(([A-Z][A-Z0-9.\-]{0,6})\)\s*\(CIK", nm)
                    if m:
                        company, ticker = m.group(1).strip(), m.group(2).strip()
                        break
                if company is None and names:
                    company = re.sub(r"\s*\(CIK.*", "", names[0]).strip()
                cur = conn.execute("INSERT OR IGNORE INTO corp_actions VALUES (?,?,?,?,?)",
                                   (form, filed, company, ticker, acc))
                n_new += cur.rowcount
                got += 1
            if len(hits) < 100:
                break
            time.sleep(0.4)
        print(f"  {form:9s} {got} filings in window", flush=True)
        time.sleep(0.4)
    conn.commit()
    tot = conn.execute("SELECT COUNT(*), COUNT(DISTINCT ticker) FROM corp_actions").fetchone()
    print(f"corp_actions: +{n_new} new; total {tot[0]} filings across {tot[1]} tickers")
    print("\nlive situations touching our universe:")
    for r in conn.execute("""SELECT ca.ticker, ca.form, MAX(ca.filed), MAX(ca.company), u.score
        FROM corp_actions ca JOIN unified_signal u ON u.ticker = ca.ticker
        WHERE u.score > 15 GROUP BY ca.ticker, ca.form
        ORDER BY u.score DESC LIMIT 20"""):
        print(f"  {r[0]:6s} {r[1]:9s} {r[2]}  {(r[3] or '')[:40]:42s} score={r[4]:.0f}")
    conn.close()

if __name__ == "__main__":
    run()
