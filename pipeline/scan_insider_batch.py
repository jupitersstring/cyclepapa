"""Batch insider Form 4 scan across the top-signal small/micro cap tickers.

ingest_edgar.py was wired for a small REFRESH_TICKERS list. This extends
the scan to ALL high-signal small/micro names so we can detect "insiders
are buying ahead of smart money" patterns across the universe.

Targets: tickers with smart-money adds (S3/S4) OR 13D/G subject OR
multi-fund 13F (≥5 funds), filtered to US-listed small/micro caps
(mcap < $5B if known, else included by default).
"""
import json, os, re, sqlite3, subprocess, sys, time
import xml.etree.ElementTree as ET

DB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "cyclepapa.db")
UA = "cyclepapa-research admin@example.com"

def curl(url):
    out = subprocess.run(["curl","-sk","--compressed","-m","15","-A",UA, url],
                         capture_output=True, text=True).stdout
    return out

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

def recent_form4_filings(cik, lookback_days=180):
    """Return list of (accession, primary_doc, date) for Form 4 in the window."""
    j = json.loads(curl(f"https://data.sec.gov/submissions/CIK{cik}.json"))
    rec = j["filings"]["recent"]
    cutoff = time.strftime("%Y-%m-%d", time.localtime(time.time() - lookback_days*86400))
    out = []
    for i in range(min(80, len(rec["form"]))):
        if rec["form"][i] == "4" and rec["filingDate"][i] >= cutoff:
            out.append((rec["accessionNumber"][i], rec["primaryDocument"][i], rec["filingDate"][i]))
    return out

def parse_form4(cik, accession, primary_doc):
    """Extract owner, role, code, shares, price, acquired (1/0) from Form 4 XML."""
    acc = accession.replace("-", "")
    raw_doc = primary_doc.split("/")[-1]
    url = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc}/{raw_doc}"
    body = curl(url)
    out = []
    try:
        root = ET.fromstring(body)
    except ET.ParseError:
        return out
    # owner + role
    owner = ""
    for o in root.iter("rptOwner"):
        n = o.find(".//rptOwnerName")
        if n is not None and n.text:
            owner = n.text.strip(); break
    role = ""
    for r in root.iter("reportingOwnerRelationship"):
        is_dir = r.find("isDirector")
        is_off = r.find("isOfficer")
        is_10p = r.find("isTenPercentOwner")
        title = r.find("officerTitle")
        if is_dir is not None and is_dir.text == "1": role = "Director"
        if is_off is not None and is_off.text == "1":
            role = title.text.strip() if title is not None and title.text else "Officer"
        if is_10p is not None and is_10p.text == "1": role = "10%+ Owner"
        break
    # iterate nonDerivativeTable transactions
    for tx in root.iter("nonDerivativeTransaction"):
        code_el = tx.find(".//transactionCode")
        if code_el is None or not code_el.text: continue
        code = code_el.text.strip()
        shares_el = tx.find(".//transactionShares/value")
        price_el  = tx.find(".//transactionPricePerShare/value")
        date_el   = tx.find(".//transactionDate/value")
        a_d_el    = tx.find(".//transactionAcquiredDisposedCode/value")
        if shares_el is None: continue
        try: shares = float(shares_el.text)
        except: continue
        price = float(price_el.text) if (price_el is not None and price_el.text) else None
        acquired = 1 if (a_d_el is not None and a_d_el.text == "A") else 0
        out.append({
            "owner": owner, "role": role, "code": code,
            "shares": shares, "price": price, "acquired": acquired,
            "trans_date": date_el.text if date_el is not None else None,
        })
    return out

def target_tickers(conn, max_n=500):
    """Build the target list — highest-signal small/micro US tickers."""
    have_4 = {r[0] for r in conn.execute(
        "SELECT DISTINCT ticker FROM form4_transactions WHERE trans_date >= date('now','-180 days')")}
    # signal score: section 3*3 + section 4*1.5 + 13D + log(1+13F holders)
    sig = {}
    for r in conn.execute("""SELECT ticker, COUNT(DISTINCT CASE WHEN section=3 THEN fund END) s3,
        COUNT(DISTINCT CASE WHEN section=4 THEN fund END) s4 FROM fund_positions
        WHERE ticker IS NOT NULL AND section IN (3,4) GROUP BY ticker"""):
        sig[r[0]] = sig.get(r[0], 0) + r[1]*3 + r[2]*1.5
    for r in conn.execute("SELECT subject_ticker FROM holder_13d WHERE subject_ticker IS NOT NULL"):
        sig[r[0]] = sig.get(r[0], 0) + 2
    for r in conn.execute("""SELECT ticker, COUNT(DISTINCT fund) c FROM fund_13f_holdings
        WHERE ticker IS NOT NULL GROUP BY ticker"""):
        if r[1] >= 3:
            sig[r[0]] = sig.get(r[0], 0) + min(r[1], 10) * 0.5

    # mcap filter — if known, require <$10B; if unknown, include
    keep = {}
    for tkr, s in sig.items():
        if "." in tkr or tkr in have_4: continue  # foreign or already scanned
        if not re.match(r"^[A-Z][A-Z0-9.\-]{0,5}$", tkr): continue
        mc = conn.execute("SELECT mcap_m FROM ticker_meta WHERE ticker=?", (tkr,)).fetchone()
        if mc and mc[0] and mc[0] > 10000: continue  # skip large caps
        keep[tkr] = s
    return [t for t, _ in sorted(keep.items(), key=lambda x: -x[1])][:max_n]

def run():
    conn = sqlite3.connect(DB)
    targets = target_tickers(conn, max_n=400)
    print(f"scanning {len(targets)} tickers for Form 4 P-code buys")
    n_filings = n_buys = 0
    for i, tkr in enumerate(targets):
        cik = cik_for(tkr)
        if not cik:
            continue
        try:
            filings = recent_form4_filings(cik, lookback_days=180)
        except Exception:
            time.sleep(0.5); continue
        time.sleep(0.15)
        for acc, doc, dt in filings:
            txns = parse_form4(cik, acc, doc)
            time.sleep(0.12)
            for t in txns:
                if t["code"] != "P": continue  # only open-market buys
                if t["acquired"] != 1: continue
                conn.execute("""INSERT OR IGNORE INTO form4_transactions
                    (accession, ticker, owner, role, trans_date, code, shares, price, acquired, source_url)
                    VALUES (?,?,?,?,?,?,?,?,?,?)""",
                    (acc, tkr, t["owner"], t["role"], t["trans_date"],
                     t["code"], t["shares"], t["price"], t["acquired"],
                     f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc.replace('-','')}/{doc}"))
                n_buys += 1
            n_filings += len(filings)
        if i % 25 == 0 and i > 0:
            conn.commit()
            print(f"  [{i+1}/{len(targets)}] {tkr} cik={cik} filings={len(filings)}  buys_total={n_buys}")
    conn.commit()
    print(f"\nscanned {len(targets)} tickers, found {n_buys} P-code buys across {n_filings} Form 4 filings")

if __name__ == "__main__":
    run()
