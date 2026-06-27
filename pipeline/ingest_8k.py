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
    # Walk the ENTIRE recent block (≤1000), not just the first 80 — companies file
    # many forms, so an 80-cap drops in-window 8-Ks for any active filer.
    forms = rec["form"]
    for i in range(len(forms)):
        if forms[i] == "8-K" and rec["filingDate"][i] >= cutoff:
            out.append((rec["accessionNumber"][i], rec["primaryDocument"][i], rec["filingDate"][i]))
    return out

# SEC header uses descriptive item names — map them to standard codes.
ITEM_DESC_TO_CODE = {
    "entry into a material definitive agreement": "1.01",
    "termination of a material definitive agreement": "1.02",
    "bankruptcy or receivership": "1.03",
    "mine safety": "1.04",
    "completion of acquisition or disposition of assets": "2.01",
    "results of operations and financial condition": "2.02",
    "creation of a direct financial obligation": "2.03",
    "costs associated with exit or disposal activities": "2.05",
    "material impairments": "2.06",
    "notice of delisting": "3.01",
    "unregistered sales of equity securities": "3.02",
    "material modification to rights of security holders": "3.03",
    "changes in registrant's certifying accountant": "4.01",
    "non-reliance on previously issued financial statements": "4.02",
    "changes in control of registrant": "5.01",
    "departure of directors or certain officers": "5.02",
    "election of directors": "5.02",
    "appointment of certain officers": "5.02",
    "compensatory arrangements of certain officers": "5.02",
    "amendments to articles of incorporation": "5.03",
    "amendments to the registrant's code of ethics": "5.05",
    "submission of matters to a vote of security holders": "5.07",
    "shareholder director nominations": "5.08",
    "regulation fd disclosure": "7.01",
    "other events": "8.01",
    "financial statements and exhibits": "9.01",
}

def parse_8k_items(cik, accession):
    """Parse 8-K item codes — two-pass:
       1. Body text for explicit 'Item X.XX' references (cleanest signal)
       2. SEC header 'ITEM INFORMATION:' descriptions mapped via lookup
    """
    acc = accession.replace("-", "")
    body = curl(f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc}/{accession}.txt")
    if not body: return []
    text = body.decode("utf-8", errors="replace")
    items = set()
    # Pass 1: explicit Item X.XX in body
    for m in re.finditer(r"\bItem\s+([0-9]+\.[0-9]+)\b", text):
        items.add(m.group(1))
    # Pass 2: header descriptions
    for m in re.finditer(r"ITEM\s+INFORMATION:\s*([^\n]+?)(?=\n|$)", text, re.I):
        desc = m.group(1).strip().lower()
        # Match longest description that's a prefix of `desc`
        for k, code in sorted(ITEM_DESC_TO_CODE.items(), key=lambda x: -len(x[0])):
            if k in desc:
                items.add(code)
                break
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

def target_tickers(conn, max_n, all_us=False):
    """Top signal tickers — small/mid cap with smart-money activity.

    all_us=True returns the COMPLETE US-held universe (every name held by >=1
    fund or carrying any disclosed signal) with no smart_money>=3 floor, no mcap
    cap, no top-N truncation and no already-scanned skip — the (cik, accession)
    primary key makes re-inserts idempotent."""
    if all_us:
        return [r[0] for r in conn.execute("""
            SELECT us.ticker FROM unified_signal us
            WHERE us.is_us = 1 AND us.ticker NOT LIKE '%.%'
              AND (us.smart_money_n >= 1 OR us.s1_top > 0 OR us.s3_new >= 1
                   OR us.s4_add >= 1 OR us.activist_filings >= 1)
            ORDER BY us.score DESC""")]
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

def _row_for(tkr, cik, acc, dt, items):
    labels = ", ".join(f"{x}: {ITEM_LABELS.get(x, x)}" for x in items)
    return (tkr, cik, acc, dt, ",".join(items), labels,
            1 if any(x in items for x in ("1.01", "2.01")) else 0,
            1 if "5.02" in items else 0,
            1 if "2.02" in items else 0,
            1 if "1.03" in items else 0,
            1 if "3.02" in items else 0,
            1 if "5.01" in items else 0,
            f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc.replace('-','')}/")

def scan_8k_one(tkr):
    """Worker: all 8-Ks (≤180d) for one ticker, parsed to item codes."""
    cik = cik_for(tkr)
    if not cik:
        return []
    try:
        filings = recent_8k(cik, lookback_days=180)
    except Exception:
        return []
    rows = []
    for acc, doc, dt in filings:
        try:
            items = parse_8k_items(cik, acc)
        except Exception:
            items = []
        rows.append(_row_for(tkr, cik, acc, dt, items))
    return rows

def run_sharded(all_us=True, n_workers=8, rps=8):
    """Complete, fast 8-K ingest across the full US-held universe."""
    conn = sqlite3.connect(DB)
    init_schema(conn)
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from _shard import shard_map
    targets = target_tickers(conn, 0, all_us=all_us)
    print(f"sharded 8-K scan: {len(targets)} tickers, {n_workers} workers, {rps} req/s [FULL US-held]")
    n_filings = [0]; prog = [0]
    def on_result(tkr, rows):
        for row in rows:
            try:
                conn.execute("""INSERT OR IGNORE INTO catalysts_8k
                    (ticker, cik, accession, filed, items, item_labels,
                     has_ma, has_director, has_earnings, has_bankruptcy, has_pipe, has_control, source_url)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""", row)
                n_filings[0] += 1
            except Exception:
                pass
        prog[0] += 1
        if prog[0] % 100 == 0:
            conn.commit()
            print(f"  [{prog[0]}/{len(targets)}] {tkr} 8K_total={n_filings[0]}")
    def on_error(tkr, exc):
        prog[0] += 1
    shard_map(scan_8k_one, targets, n_workers=n_workers, rps=rps,
              on_result=on_result, on_error=on_error)
    conn.commit()
    print(f"\ndone: {n_filings[0]} 8-K filings across {len(targets)} tickers scanned")

if __name__ == "__main__":
    args = sys.argv[1:]
    if args and args[0] == "all":
        run_sharded(all_us=True)
    else:
        run(max_n=int(args[0]) if args else 600)
