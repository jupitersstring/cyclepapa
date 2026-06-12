"""Market-wide asymmetric discovery from EDGAR daily indices.

Until now the pipeline only VERIFIED known names. This module DISCOVERS:
  1. Insider-buy clusters (the +109% backtest bucket) across ALL issuers:
     - pull daily form indices (last N business days)
     - count Form 4 filings per issuer CIK (cheap pre-filter, no XML fetches)
     - parse XMLs only for issuers with >= MIN_FILINGS in the window
     - keep code=P open-market buys; cluster = >=2 distinct owners or >=$1M total
     - enrich with Yahoo 1y context: % off 52w high (we want deep drawdown)
  2. Fresh activist stakes: new SCHEDULE 13D filings in the window (list).

Output -> discovery table + console ranking.
"""
import json, os, re, sqlite3, subprocess, sys, time
from collections import defaultdict
from datetime import date, timedelta

DB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "cyclepapa.db")
UA = "cyclepapa-research admin@example.com"
MIN_FILINGS = 3        # issuer must have >=3 Form 4s in window to bother parsing
MAX_ISSUERS = 90
MAX_XML_PER_ISSUER = 4
LOOKBACK_BDAYS = 9

def curl(url):
    out = subprocess.run(["curl", "-sk", "--compressed", "-m", "20", "-A", UA, url],
                         capture_output=True)
    return out.stdout.decode("utf-8", errors="replace")

def qtr(d): return (d.month - 1) // 3 + 1

def business_days_back(n):
    days, d = [], date.today()
    while len(days) < n:
        if d.weekday() < 5: days.append(d)
        d -= timedelta(days=1)
    return days

def fetch_indices():
    """returns list of (form_type, company, cik, date, path)"""
    rows = []
    for d in business_days_back(LOOKBACK_BDAYS):
        url = f"https://www.sec.gov/Archives/edgar/daily-index/{d.year}/QTR{qtr(d)}/form.{d.strftime('%Y%m%d')}.idx"
        txt = curl(url)
        if not txt or "Form Type" not in txt[:2000]:
            continue
        for line in txt.splitlines():
            m = re.match(r'^(4|SCHEDULE 13D)\s{2,}(.+?)\s{2,}(\d+)\s{2,}(\d{8})\s{2,}(\S+)', line)
            if m:
                rows.append((m.group(1), m.group(2).strip(), m.group(3), m.group(4), m.group(5)))
        print(f"  index {d}: ok ({len(txt)//1024}KB)")
        time.sleep(0.12)
    return rows

def parse_form4_txt(path):
    """fetch full submission .txt, extract ownershipDocument values via regex"""
    txt = curl(f"https://www.sec.gov/Archives/{path}")
    get = lambda tag: (re.search(rf"<{tag}>(?:\s*<value>)?([^<]+)", txt) or [None, None])[1]
    issuer_tkr = get("issuerTradingSymbol")
    issuer_name = get("issuerName")
    owner = get("rptOwnerName")
    role = []
    if re.search(r"<isDirector>(?:<value>)?(1|true)", txt): role.append("Dir")
    if re.search(r"<isOfficer>(?:<value>)?(1|true)", txt):
        t = get("officerTitle"); role.append(t or "Officer")
    if re.search(r"<isTenPercentOwner>(?:<value>)?(1|true)", txt): role.append("10%")
    txns = []
    for blk in re.findall(r"<nonDerivativeTransaction>(.*?)</nonDerivativeTransaction>", txt, re.S):
        g = lambda tag: (re.search(rf"<{tag}>(?:\s*<value>)?\s*([^<\s]+)", blk) or [None, None])[1]
        code = g("transactionCode")
        try:
            sh = float(g("transactionShares") or 0); px = float(g("transactionPricePerShare") or 0)
        except (TypeError, ValueError):
            sh, px = 0, 0
        ad = g("transactionAcquiredDisposedCode")
        dt = g("transactionDate")
        txns.append({"code": code, "shares": sh, "price": px, "acq": ad == "A", "date": dt})
    return issuer_tkr, issuer_name, owner, "/".join(role), txns

def yahoo_context(sym):
    out = curl(f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?range=1y&interval=1d")
    try:
        res = json.loads(out)["chart"]["result"][0]
        closes = [c for c in res["indicators"]["quote"][0]["close"] if c]
        last = closes[-1]; hi = max(closes); lo = min(closes)
        return last, (last/hi - 1), (last/lo - 1)
    except Exception:
        return None, None, None

def run():
    conn = sqlite3.connect(DB)
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS discovery (
      ticker TEXT PRIMARY KEY, issuer TEXT, n_filings INTEGER, n_buyers INTEGER,
      total_usd_m REAL, top_buyer TEXT, top_role TEXT, avg_px REAL,
      last_close REAL, off_52w_high REAL, off_52w_low REAL,
      window TEXT, asof TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS discovery_13d (
      cik TEXT, company TEXT, filed TEXT, path TEXT, PRIMARY KEY (cik, filed));
    """)
    conn.execute("DELETE FROM discovery")

    print("fetching daily indices...")
    rows = fetch_indices()
    f4 = [r for r in rows if r[0] == "4"]
    d13 = [r for r in rows if r[0] == "SCHEDULE 13D"]
    print(f"\n{len(f4)} Form 4 filings, {len(d13)} new SCHEDULE 13Ds in last {LOOKBACK_BDAYS} business days")

    for _, comp, cik, filed, path in d13:
        conn.execute("INSERT OR IGNORE INTO discovery_13d VALUES (?,?,?,?)", (cik, comp, filed, path))

    by_cik = defaultdict(list)
    for _, comp, cik, filed, path in f4:
        by_cik[cik].append((comp, filed, path))
    # 3-15 filings: enough for a cluster, below constant-filer mega-cap noise
    candidates_ciks = [(cik, sorted(v, key=lambda x: x[1], reverse=True))
                       for cik, v in by_cik.items() if MIN_FILINGS <= len(v) <= 15]
    print(f"{len(candidates_ciks)} issuers with {MIN_FILINGS}-15 Form 4s — probe phase (1 XML each)...")
    # PROBE: parse most-recent filing only; keep issuers showing a real P-buy
    survivors = []
    for cik, filings in candidates_ciks:
        t, nm, owner, role, txns = parse_form4_txt(filings[0][2])
        time.sleep(0.07)
        if any(x["code"] == "P" and x["acq"] and x["shares"] * x["price"] > 50_000 for x in txns):
            survivors.append((cik, filings, (t, nm, owner, role, txns)))
    print(f"{len(survivors)} issuers survived probe — deep parse...")
    crowded = survivors

    found = []
    known = {r[0] for r in conn.execute("SELECT ticker FROM candidates")}
    FUNDISH = re.compile(r"\b(FUND|TRUST|ETF|CLOSED.END|CAPITAL MGMT|ASSET MGMT|VENTURES? FUND|SPAC|ACQUISITION CORP)\b", re.I)
    MIN_OWNER_USD = 0.05  # ignore sub-$50k buyers (ESPP noise)
    for cik, filings, probe in crowded:
        buys = defaultdict(lambda: {"usd": 0.0, "px": [], "role": ""})
        tkr, name = probe[0], probe[1]
        parsed = [probe]
        for comp, filed, path in filings[1:MAX_XML_PER_ISSUER + 2]:
            parsed.append(parse_form4_txt(path))
            time.sleep(0.08)
        for t, nm, owner, role, txns in parsed:
            tkr, name = tkr or t, name or nm
            for x in txns:
                if x["code"] == "P" and x["acq"] and x["shares"] and x["price"]:
                    b = buys[owner]
                    b["usd"] += x["shares"] * x["price"] / 1e6
                    b["px"].append(x["price"]); b["role"] = role
        buys = {o: b for o, b in buys.items() if b["usd"] >= MIN_OWNER_USD}
        if not buys or not tkr:
            continue
        if FUNDISH.search(name or ""):
            continue
        total = sum(b["usd"] for b in buys.values())
        if len(buys) < 2 and total < 1.0:
            continue
        last, offhi, offlo = yahoo_context(tkr)
        time.sleep(0.12)
        top = max(buys.items(), key=lambda kv: kv[1]["usd"])
        allpx = [p for b in buys.values() for p in b["px"]]
        rec = {"ticker": tkr, "issuer": (name or "")[:40], "n_filings": len(filings),
               "n_buyers": len(buys), "total": round(total, 2),
               "top_buyer": top[0][:28], "top_role": top[1]["role"][:24],
               "avg_px": round(sum(allpx)/len(allpx), 2) if allpx else None,
               "last": last, "offhi": offhi, "offlo": offlo,
               "known": tkr in known}
        found.append(rec)
        conn.execute("""INSERT OR REPLACE INTO discovery VALUES (?,?,?,?,?,?,?,?,?,?,?,?,date('now'))""",
                     (tkr, rec["issuer"], rec["n_filings"], rec["n_buyers"], rec["total"],
                      rec["top_buyer"], rec["top_role"], rec["avg_px"], last, offhi, offlo,
                      f"last {LOOKBACK_BDAYS} bdays"))
    conn.commit()

    # asymmetric shortlist: real cluster + meaningful drawdown
    found.sort(key=lambda r: -(r["n_buyers"] * 2 + r["total"]))
    print(f"\n{'tkr':<7} {'buyers':<7} {'$M':<8} {'avg px':<8} {'last':<8} {'off-hi':<8} {'off-lo':<8} {'known':<6} top buyer")
    for r in found:
        oh = f"{r['offhi']*100:+.0f}%" if r["offhi"] is not None else "?"
        ol = f"{r['offlo']*100:+.0f}%" if r["offlo"] is not None else "?"
        print(f"  {r['ticker']:<7} {r['n_buyers']:<7} {r['total']:<8} {r['avg_px'] or '?':<8} "
              f"{round(r['last'],2) if r['last'] else '?':<8} {oh:<8} {ol:<8} {'*' if r['known'] else '':<6} "
              f"{r['top_buyer']} ({r['top_role']})")
    print("\nASYMMETRIC SHORTLIST (cluster + >=20% off 52w high + NEW to universe):")
    for r in found:
        if not r["known"] and r["offhi"] is not None and r["offhi"] <= -0.20 and (r["n_buyers"] >= 2 or r["total"] >= 1.0):
            print(f"  {r['ticker']:<7} {r['issuer']:<40} {r['n_buyers']} buyers ${r['total']}M "
                  f"@~{r['avg_px']} | now {round(r['last'],2)} ({r['offhi']*100:+.0f}% off hi)")
    n13 = conn.execute("SELECT COUNT(DISTINCT company) FROM discovery_13d").fetchone()[0]
    print(f"\nNew SCHEDULE 13D subjects this window: {n13} (table discovery_13d)")

def enrich_13d():
    """Resolve SUBJECT COMPANY for each new SCHEDULE 13D, add price context."""
    conn = sqlite3.connect(DB)
    conn.execute("""CREATE TABLE IF NOT EXISTS discovery_13d_subjects (
      accession TEXT PRIMARY KEY, subject TEXT, subject_cik TEXT, ticker TEXT,
      filer_hint TEXT, filed TEXT, last_close REAL, off_52w_high REAL, asof TEXT)""")
    raw = list(conn.execute("SELECT DISTINCT path, filed FROM discovery_13d"))
    # ticker map
    tj = curl("https://www.sec.gov/files/company_tickers.json")
    try:
        cmap = {str(v["cik_str"]): v["ticker"] for v in json.loads(tj).values()}
    except Exception:
        cmap = {}
    seen = set()
    out = []
    for path, filed in raw:
        acc = path.split("/")[-1].replace(".txt", "")
        if acc in seen: continue
        seen.add(acc)
        txt = curl(f"https://www.sec.gov/Archives/{path}")
        time.sleep(0.1)
        subj = re.search(r"SUBJECT COMPANY:.*?COMPANY CONFORMED NAME:\s*(.+?)\n.*?CENTRAL INDEX KEY:\s*(\d+)", txt, re.S)
        filer = re.search(r"FILED BY:.*?COMPANY CONFORMED NAME:\s*(.+?)\n", txt, re.S)
        if not subj: continue
        sname, scik = subj.group(1).strip(), str(int(subj.group(2)))
        tkr = cmap.get(scik)
        last = offhi = None
        if tkr:
            last, offhi, _ = yahoo_context(tkr)
            time.sleep(0.1)
        conn.execute("INSERT OR REPLACE INTO discovery_13d_subjects VALUES (?,?,?,?,?,?,?,?,date('now'))",
                     (acc, sname[:50], scik, tkr, (filer.group(1).strip()[:40] if filer else None),
                      filed, last, offhi))
        out.append((tkr or "?", sname[:40], filer.group(1).strip()[:32] if filer else "?", filed, last, offhi))
    conn.commit()
    out.sort(key=lambda r: (r[5] if r[5] is not None else 0))
    print(f"\nNEW SCHEDULE 13D SUBJECTS ({len(out)}), sorted by drawdown:")
    print(f"{'tkr':<7} {'subject':<40} {'filer':<32} {'filed':<10} {'last':<8} off-hi")
    for tkr, s, f, d, last, offhi in out:
        oh = f"{offhi*100:+.0f}%" if offhi is not None else "?"
        print(f"  {tkr:<7} {s:<40} {f:<32} {d:<10} {round(last,2) if last else '?':<8} {oh}")

if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "clusters"
    if mode in ("clusters", "all"): run()
    if mode in ("13d", "all"): enrich_13d()
