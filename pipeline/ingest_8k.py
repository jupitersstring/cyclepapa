"""Ingest 8-K filings for the universe tickers — the catalyst layer.

8-K Items we care about (with their meaning):
  1.01  Entry into Material Definitive Agreement (M&A)
  1.02  Termination of Material Definitive Agreement
  1.03  Bankruptcy
  2.01  Completion of Acquisition or Disposition
  2.02  Results of Operations (earnings)
  2.05  Costs Associated with Exit/Disposal (restructuring)
  3.01  Notice of Delisting (warning)
  3.02  Unregistered Sales of Equity (PIPE, dilution)
  5.01  Changes in Control
  5.02  Director/Officer Departure or Appointment
  5.07  Submission to Vote (shareholder meeting)
  7.01  Reg FD Disclosure
  8.01  Other Events (catch-all)
  9.01  Financial Statements and Exhibits

For each ticker in unified_signal with a CIK, fetch the last 90 days of
8-K filings and parse the Items list. Stored in catalysts_8k table.
"""
import json, os, re, sqlite3, subprocess, sys, time

DB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "cyclepapa.db")
UA = "cyclepapa-research admin@example.com"

ITEM_LABELS = {
    "1.01": "M&A entered",        "1.02": "M&A terminated",
    "1.03": "Bankruptcy",
    "2.01": "Acquisition closed",  "2.02": "Earnings",
    "2.05": "Restructuring/exit",  "2.06": "Material impairment",
    "3.01": "Delisting notice",    "3.02": "PIPE/dilution",
    "3.03": "Material modification of rights",
    "4.01": "Auditor change",      "4.02": "Non-reliance restate",
    "5.01": "Control change",      "5.02": "Director/officer change",
    "5.03": "Bylaw change",        "5.07": "Vote/meeting",
    "5.08": "Shareholder director nominations",
    "7.01": "Reg FD",              "8.01": "Other event",
    "9.01": "Financials",
}

def curl(url):
    return subprocess.run(["curl","-sk","--compressed","-m","12","-A",UA, url],
                          capture_output=True).stdout

_CIK = None
def cik_for(t):
    global _CIK
    if _CIK is None:
        try:
            j = json.loads(curl("https://www.sec.gov/files/company_tickers.json"))
            _CIK = {v["ticker"].upper(): str(v["cik_str"]).zfill(10) for v in j.values()}
        except Exception:
            _CIK = {}
    return _CIK.get(t.upper())

def recent_8k(cik, lookback_days=180):
    """Return list of (accession, primary_doc, file_date) for 8-Ks in window."""
    body = curl(f"https://data.sec.gov/submissions/CIK{cik}.json")
    try:
        j = json.loads(body)
        rec = j["filings"]["recent"]
    except Exception:
        return []
    cutoff = time.strftime("%Y-%m-%d", time.localtime(time.time() - lookback_days*86400))
    out = []
    for i in range(min(80, len(rec["form"]))):
        if rec["form"][i] == "8-K" and rec["filingDate"][i] >= cutoff:
            out.append((rec["accessionNumber"][i], rec["primaryDocument"][i], rec["filingDate"][i]))
    return out

def parse_8k_items(cik, accession):
    """Pull the 8-K txt header to extract the ITEM INFORMATION line(s)."""
    acc = accession.replace("-", "")
    body = curl(f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc}/{accession}.txt")
    if not body: return []
    text = body.decode("utf-8", errors="replace")
    items = set()
    # Standard EDGAR header format
    for m in re.finditer(r"ITEM\s+INFORMATION:\s+Item\s+([0-9]+\.[0-9]+)", text, re.I):
        items.add(m.group(1))
    # Alt format inside the primary doc
    for m in re.finditer(r"Item\s+([0-9]+\.[0-9]+)\b", text[:3000]):
        items.add(m.group(1))
    return sorted(items)

def init_schema(conn):
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS catalysts_8k (
      ticker TEXT, cik TEXT, accession TEXT, filed TEXT,
      items TEXT,                -- comma-separated item codes
      item_labels TEXT,          -- human-readable labels
      has_ma INTEGER, has_director INTEGER, has_earnings INTEGER,
      has_bankruptcy INTEGER, has_pipe INTEGER, has_control INTEGER,
      source_url TEXT,
      PRIMARY KEY (cik, accession));
    CREATE INDEX IF NOT EXISTS idx_8k_ticker ON catalysts_8k(ticker);
    CREATE INDEX IF NOT EXISTS idx_8k_filed ON catalysts_8k(filed);
    """)

def target_tickers(conn, max_n):
    """Top signal tickers — small/mid cap with smart-money activity."""
    have = {r[0] for r in conn.execute(
        "SELECT DISTINCT ticker FROM catalysts_8k WHERE filed >= date('now','-180 days')")}
    targets = [r[0] for r in conn.execute("""
        SELECT us.ticker FROM unified_signal us
        WHERE us.ticker NOT LIKE '%.%'
          AND (us.smart_money_n >= 3 OR us.s3_new >= 1 OR us.s4_add >= 1
               OR us.activist_filings >= 1)
          AND (us.mcap_m IS NULL OR us.mcap_m < 50000)
        ORDER BY us.score DESC""")]
    return [t for t in targets if t not in have][:max_n]

def run(max_n=600):
    conn = sqlite3.connect(DB)
    init_schema(conn)
    targets = target_tickers(conn, max_n)
    print(f"scanning {len(targets)} tickers for 8-K filings (≤180d)")
    n_filings = 0
    for i, tkr in enumerate(targets):
        cik = cik_for(tkr)
        if not cik:
            continue
        filings = recent_8k(cik, lookback_days=180)
        time.sleep(0.15)
        for acc, doc, dt in filings:
            items = parse_8k_items(cik, acc)
            time.sleep(0.1)
            labels = ", ".join(f"{x}: {ITEM_LABELS.get(x, x)}" for x in items)
            conn.execute("""INSERT OR IGNORE INTO catalysts_8k
                (ticker, cik, accession, filed, items, item_labels,
                 has_ma, has_director, has_earnings, has_bankruptcy, has_pipe, has_control, source_url)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (tkr, cik, acc, dt, ",".join(items), labels,
                 1 if any(x in items for x in ("1.01","2.01")) else 0,
                 1 if "5.02" in items else 0,
                 1 if "2.02" in items else 0,
                 1 if "1.03" in items else 0,
                 1 if "3.02" in items else 0,
                 1 if "5.01" in items else 0,
                 f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc.replace('-','')}/"))
            n_filings += 1
        if i % 25 == 0 and i > 0:
            conn.commit()
            print(f"  [{i+1}/{len(targets)}] {tkr} 8K_total={n_filings}")
    conn.commit()
    print(f"\ndone: {n_filings} 8-K filings ingested across {len(targets)} tickers")

if __name__ == "__main__":
    run(max_n=int(sys.argv[1]) if sys.argv[1:] else 600)
