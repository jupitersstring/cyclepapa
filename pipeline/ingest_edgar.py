"""EDGAR primary-source ingest — no more second-hand transcription.

- ticker->CIK via SEC company_tickers.json
- recent filings (Form 4, SC 13D/G, 13F-HR) via data.sec.gov submissions API
- Form 4 XML parsed for transaction CODE (P=open-market buy, S=sale, J=other)
  -> the PRM error class (J-code mistaken for a buy) is structurally impossible now
Usage: python3 pipeline/ingest_edgar.py [TICKER ...]
"""
import json, os, re, sqlite3, subprocess, sys, time
import xml.etree.ElementTree as ET

DB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "cyclepapa.db")
UA = "cyclepapa-research admin@example.com"

def curl(url):
    out = subprocess.run(["curl", "-sk", "-m", "20", "-A", UA, url], capture_output=True, text=True)
    return out.stdout

_cikmap = None
def cik_for(ticker):
    global _cikmap
    if _cikmap is None:
        raw = curl("https://www.sec.gov/files/company_tickers.json")
        try:
            j = json.loads(raw)
            _cikmap = {v["ticker"].upper(): str(v["cik_str"]).zfill(10) for v in j.values()}
        except Exception:
            _cikmap = {}
    return _cikmap.get(ticker.upper().replace('.TO', '').replace('.IM', ''))

def filings(cik, forms=("4", "SC 13D", "SC 13D/A", "SC 13G", "SC 13G/A", "13F-HR"), limit=40):
    j = json.loads(curl(f"https://data.sec.gov/submissions/CIK{cik}.json"))
    rec = j["filings"]["recent"]
    out = []
    for i in range(min(limit, len(rec["form"]))):
        if rec["form"][i] in forms:
            out.append({"form": rec["form"][i], "filed": rec["filingDate"][i],
                        "accession": rec["accessionNumber"][i],
                        "primary_doc": rec["primaryDocument"][i]})
    return out

def parse_form4(cik, accession, primary_doc):
    acc = accession.replace("-", "")
    # xslF345X*/ prefix returns rendered HTML; strip it for the raw ownershipDocument XML
    raw_doc = primary_doc.split("/")[-1]
    url = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc}/{raw_doc}"
    xml = curl(url)
    try:
        root = ET.fromstring(xml)
    except ET.ParseError:
        return [], url
    owner = (root.findtext(".//rptOwnerName") or "?")
    role_bits = []
    if root.findtext(".//isDirector") == "1": role_bits.append("Director")
    if root.findtext(".//isOfficer") == "1": role_bits.append(root.findtext(".//officerTitle") or "Officer")
    if root.findtext(".//isTenPercentOwner") == "1": role_bits.append("10%Owner")
    txns = []
    for t in root.findall(".//nonDerivativeTransaction"):
        code = t.findtext(".//transactionCode")
        sh = t.findtext(".//transactionShares/value")
        px = t.findtext(".//transactionPricePerShare/value")
        ad = t.findtext(".//transactionAcquiredDisposedCode/value")
        dt = t.findtext(".//transactionDate/value")
        txns.append({"owner": owner, "role": "/".join(role_bits), "date": dt, "code": code,
                     "shares": float(sh) if sh else None, "price": float(px) if px else None,
                     "acquired": 1 if ad == "A" else 0})
    return txns, url

def run(tickers):
    conn = sqlite3.connect(DB)
    for t in tickers:
        cik = cik_for(t)
        if not cik:
            print(f"  {t}: no CIK"); continue
        try:
            fl = filings(cik)
        except Exception as e:
            print(f"  {t}: submissions failed ({e})"); continue
        n4 = 0
        for f in fl:
            url = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{f['accession'].replace('-','')}/{f['primary_doc']}"
            conn.execute("""INSERT OR IGNORE INTO edgar_filings (accession,ticker,cik,form,filed,primary_doc,url)
                            VALUES (?,?,?,?,?,?,?)""",
                         (f["accession"], t, cik, f["form"], f["filed"], f["primary_doc"], url))
            if f["form"] == "4" and n4 < 5 and f["primary_doc"].endswith(".xml"):
                txns, src = parse_form4(cik, f["accession"], f["primary_doc"])
                for x in txns:
                    conn.execute("""INSERT INTO form4_transactions
                        (accession,ticker,owner,role,trans_date,code,shares,price,acquired,source_url)
                        VALUES (?,?,?,?,?,?,?,?,?,?)""",
                        (f["accession"], t, x["owner"], x["role"], x["date"], x["code"],
                         x["shares"], x["price"], x["acquired"], src))
                n4 += 1
                time.sleep(0.15)
        forms = {}
        for f in fl: forms[f["form"]] = forms.get(f["form"], 0) + 1
        print(f"  {t}: {len(fl)} filings {dict(forms)}; parsed {n4} Form 4s")
        time.sleep(0.15)
    conn.commit()
    # summary of REAL open-market buys (code P only)
    print("\nOpen-market BUYS (code=P) found:")
    for r in conn.execute("""SELECT ticker, owner, role, trans_date, shares, price
                             FROM form4_transactions WHERE code='P' AND acquired=1
                             AND price IS NOT NULL AND shares IS NOT NULL
                             ORDER BY trans_date DESC LIMIT 30"""):
        val = (r[4] or 0) * (r[5] or 0) / 1e6
        role = r[2] or ""
        print(f"  {r[0]:<6} {r[3]} {r[1][:28]:<28} {role[:20]:<20} {r[4]:>10,.0f} sh @ {r[5]} (${val:.2f}M)")

if __name__ == '__main__':
    tk = sys.argv[1:] or ["INMD", "KBR", "ROCK", "NSP", "SONO", "RPAY", "SEER", "MNRO", "UAA", "HHH", "NRP", "CDRE"]
    run(tk)
