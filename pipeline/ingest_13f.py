"""13F-HR information-table ingest from SEC EDGAR primary XML.

For each fund with a known CIK, pull the most recent 13F-HR filing, parse
the information table (issuer name, CUSIP, value, shares), translate CUSIP
to ticker, store in fund_13f_holdings. This replaces the curated-only
fund_positions data with EVERY position a fund reports — 50-500+ per
filer instead of ~15.

Politeness contract per SEC EDGAR rules: ~5 req/sec max, sleep on 429,
exponential backoff. Designed to run as a long-running background job;
state is persisted on the fly so partial runs are resumable.
"""
import json, os, re, sqlite3, subprocess, time, sys
import xml.etree.ElementTree as ET

DB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "cyclepapa.db")
UA = "cyclepapa-research admin@example.com"

NS = {'i': 'http://www.sec.gov/edgar/document/thirteenf/informationtable'}

# CIK map for our known funds. Keyed by canonical fund name.
# Add to this as we resolve more CIKs.
FUND_CIK = {
    "Pershing Square Capital Manag":       "1336528",
    "Pershing Square Capital Management":  "1336528",
    "Third Point LLC":                     "1040273",
    "Elliott Investment Management":       "0001791786",
    "Starboard Value LP":                  "1517137",
    "Trian Fund Management":               "1345471",
    "Icahn Capital   Carl Icahn":          "921669",
    "Carl Icahn":                          "921669",
    "Greenlight Capital":                  "1079114",
    "Greenlight Capital (David Ein":       "1079114",
    "Baupost Group LLC":                   "1061165",
    "Pershing Square":                     "1336528",
    "ValueAct Capital":                    "1418814",
    "Glenview Capital Management":         "1138742",
    "TCI Fund Management Ltd":             "1647824",
    "The Children's Investment Fund":      "1647824",
    "Children's Investment":               "1647824",
    "Lone Pine Capital LLC":               "1061768",
    "Tiger Global Management LLC":         "1167483",
    "Coatue Management LLC":               "1135730",
    "D1 Capital Partners":                 "1745776",
    "Viking Global Investors LP":          "1144565",
    "Eminence Capital LP":                 "1107310",
    "Sachem Head Capital Management":      "1559392",
    "Pentwater Capital Management":        "1425851",
    "Magnetar Capital LLC":                "1326190",
    "Brave Warrior Advisors":              "1316772",
    "Brave Warrior Advisors LLC":          "1316772",
    "Glenn Greenberg":                     "1316772",
    "Davis Selected Advisers":             "1274838",
    "Davis Selected Advisers LP":          "1274838",
    "Sequoia Fund":                        "89043",
    "Sequoia Fund   Ruane, Cu":            "89043",
    "Suvretta Capital Management":         "1528984",
    "BVF Partners L.P.":                   "1029387",
    "OrbiMed Advisors LLC":                "1055951",
    "Baker Bros. Advisors LP":             "1263508",
    "RA Capital Management LP":            "1346824",
    "Perceptive Advisors LLC":             "1224370",
    "EcoR1 Capital LLC":                   "1515691",
    "Casdin Capital LLC":                  "1702290",
    "Armistice Capital LLC":               "1664353",
    "Marathon Asset Management":           "1218497",
    "Silver Point Capital":                "1332784",
    "Hudson Bay Capital Management":       "1408140",
    "Hudson Bay Capital Management L":     "1408140",
    "GoldenTree Asset Management":         "1278951",
    "Mudrick Capital Management":          "1628094",
    "Paulson & Co Inc":                    "1035674",
    "Fairfax Financial Holdings":          "915191",
    "Pelham Capital Management":           "1442067",
    "Engine Capital":                      "1603194",
    "Legion Partners":                     "1603250",
    "Wynnefield Capital":                  "1083638",
    "Saber Capital (John Hube":            "1755484",
    "Right Tail Capital":                  "1930434",
    "Permian Investment Partners":         "1475144",
    "Greystone Capital":                   "1904057",
    "ADW Capital Management":              "1525266",
    "Caligan Partners LP":                 "1782902",
    "Findell Capital Manageme":            "1863466",
    "Buckley Capital Advisors":            "1834376",
    "Harbert Discovery Fund":              "1626127",
    "Cevian Capital":                      "1234487",
    "Cartica Management":                  "1493152",
    "Sessa Capital":                       "1543160",
    "Pzena Investment Management":         "1185186",
    "CAS Investment Partners":             "1628110",
    "Petrus Advisers":                     "1712110",
    "Nierenberg Investment Mg":            "1096752",
    "Bradley L. Radoff":                   "1380585",
    "Star Equity Fund LP (Jef":            "1548312",
    "JANA Partners":                       "1159159",
    "Greenhaven Road Investme":           "1633836",
    "Cooper Creek Partners Ma":           "1493152",
    "Coliseum Capital":                    "1460438",
    "Abrams Capital Managemen":            "1358975",
    "ShawSpring Partners":                 "1714402",
    "Atlas":                               "1567619",
    "Voss Capital":                        "1716181",
    "Marlowe Partners":                    "1858353",
    "Alta Fox Capital Management":         "1858353",
    "Roumell Asset Management":            "1188133",
    "Akre Capital Management":             "1414534",
    "Polen Capital Management":            "1316259",
    "Cove Street Capital":                 "1262228",
    "Donald Smith & Co":                   "1117077",
    "Third Avenue Management":             "1099281",
    "Dodge and Cox":                       "29332",
    "Fundsmith LLP":                       "1543160",
    "Lindsell Train Limited":              "1543160",
    "Yacktman Asset Management LP":        "938793",
    "Wedgewood Partners":                  "1054432",
    "Cantillon Capital Management":        "1263254",
    "Dorsey Asset Management":             "1543291",
    "Patient Capital Management":          "1893389",
    "Oakcliff Capital Partners":           "1514548",
    "Greenlea Lane Capital":               "1457915",
    "Daily Journal Corporation":           "783412",
    "Berkshire Hathaway":                  "1067983",
    "Himalaya Capital Management":         "1709323",
    "Semper Augustus":                     "1500866",
    "Sound Shore Management":              "1179218",
    "Kahn Brothers Group":                 "901219",
    "Jensen Investment Management":        "820605",
    "Atlantic Investment Management":      "898053",
    "Conifer Management":                  "1689775",
    "Altarock Partners":                   "1349713",
    "FPA Crescent Fund":                   "915191",
    "Miller Value Partners":               "1487545",
    "Gardner Russo & Quinn LLC":           "1158956",
}

def curl(url, retries=6):
    for i in range(retries):
        r = subprocess.run(["curl", "-sk", "--compressed", "-m", "20", "-A", UA, url],
                           capture_output=True)
        out = r.stdout
        # 429 detection
        if out[:200].find(b'Rate Threshold Exceeded') != -1 or out[:200].find(b'<!DOCTYPE html') != -1:
            wait = 20 + 10 * i
            print(f"  ! rate-limited, waiting {wait}s")
            time.sleep(wait)
            continue
        return out
    return b''

def latest_13f_acc(cik):
    """Return (accession, filed_date) of the latest 13F-HR for this CIK."""
    cik10 = cik.zfill(10)
    data = curl(f"https://data.sec.gov/submissions/CIK{cik10}.json")
    if not data: return None, None
    try:
        d = json.loads(data)
    except json.JSONDecodeError:
        return None, None
    rec = d["filings"]["recent"]
    for i, form in enumerate(rec["form"]):
        if form == "13F-HR":
            return rec["accessionNumber"][i], rec["filingDate"][i]
    return None, None

def find_infotable(cik, accession):
    """Find the infotable XML file in the filing directory."""
    acc = accession.replace("-", "")
    data = curl(f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc}/")
    if not data: return None
    # Look for any .xml whose name is not the primary form13f doc
    matches = re.findall(r'href="([^"]+\.xml)"', data.decode("utf-8", errors="ignore"))
    for m in matches:
        n = m.split("/")[-1].lower()
        if "infotable" in n or "informationtable" in n: return m
    # Fallback: try the standard filename
    return f"/Archives/edgar/data/{int(cik)}/{acc}/infotable.xml"

def _strip_ns(elem):
    """Recursively strip XML namespaces from element tags."""
    if "}" in elem.tag:
        elem.tag = elem.tag.split("}", 1)[1]
    for k in list(elem.attrib):
        if "}" in k:
            elem.attrib[k.split("}", 1)[1]] = elem.attrib.pop(k)
    for child in elem:
        _strip_ns(child)
    return elem

def parse_infotable(xml_bytes):
    """Yield {issuer, cusip, value_k, shares, type} dicts."""
    try:
        root = _strip_ns(ET.fromstring(xml_bytes))
    except ET.ParseError:
        return []
    out = []
    for it in root.findall(".//infoTable"):
        def t(p):
            e = it.find(p)
            return (e.text or "").strip() if e is not None else ""
        try: v = int(t("value"))
        except ValueError: v = 0
        try: sh = int(t("shrsOrPrnAmt/sshPrnamt"))
        except ValueError: sh = 0
        out.append({
            "issuer": t("nameOfIssuer")[:80],
            "cusip":  t("cusip"),
            "value_k": v,
            "shares":  sh,
            "type":    t("shrsOrPrnAmt/sshPrnamtType"),
        })
    return out

def cusip_ticker_map(conn):
    """Build CUSIP -> ticker map from any available source.
    We use the SEC's company_tickers_exchange.json which has CIK+name+ticker.
    For now we map by issuer NAME → ticker, since the file doesn't include CUSIP.
    Better mapping requires the OpenFIGI API or a vendor file; this is good enough
    for the names already in our universe."""
    data = curl("https://www.sec.gov/files/company_tickers_exchange.json")
    if not data: return {}
    try:
        d = json.loads(data)
    except json.JSONDecodeError:
        return {}
    # Format: {"fields":["cik","name","ticker","exchange"], "data":[[...],...]}
    by_name = {}
    for row in d.get("data", []):
        if len(row) >= 3:
            cik, name, tkr, exch = row[0], row[1].upper(), row[2], row[3] if len(row)>3 else ""
            by_name[name] = tkr
            # First-word and acronym fallbacks
    return by_name

def name_to_ticker(name, name_map):
    if not name: return None
    n = name.upper().strip()
    if n in name_map: return name_map[n]
    # try without common suffixes
    cleaned = re.sub(r"\b(INC|CORP|CORPORATION|HOLDINGS?|GROUP|LTD|PLC|LP|LLC|CLASS\s+[A-Z]|COM|COMMON)\b", "", n).strip()
    if cleaned in name_map: return name_map[cleaned]
    # token match: ticker exists in name
    for full_name, tkr in name_map.items():
        if full_name and full_name in n and len(full_name) > 6: return tkr
    return None

def run(only=None):
    conn = sqlite3.connect(DB)
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS fund_13f_holdings (
      fund TEXT, cik TEXT, accession TEXT, filed TEXT,
      issuer TEXT, cusip TEXT, ticker TEXT, value_k INTEGER, shares INTEGER,
      sh_type TEXT, pct_book REAL,
      PRIMARY KEY (fund, accession, cusip));
    CREATE INDEX IF NOT EXISTS idx_13f_ticker ON fund_13f_holdings(ticker);
    CREATE INDEX IF NOT EXISTS idx_13f_fund ON fund_13f_holdings(fund);
    CREATE TABLE IF NOT EXISTS fund_13f_state (
      fund TEXT PRIMARY KEY, cik TEXT, last_accession TEXT, last_filed TEXT,
      n_holdings INTEGER, total_value_k INTEGER, ingested_at TEXT);
    """)

    print("loading SEC ticker map...")
    name_map = cusip_ticker_map(conn)
    print(f"  {len(name_map)} name-to-ticker mappings loaded")
    time.sleep(1)

    funds = [(name, cik) for name, cik in FUND_CIK.items()]
    if only:
        only_set = set(only)
        funds = [f for f in funds if f[0] in only_set or any(o in f[0] for o in only_set)]
    print(f"\nfunds to process: {len(funds)}")
    n_done = n_skipped = n_holdings_total = 0
    for fund_name, cik in funds:
        # Skip if already done in this DB
        prior = conn.execute("SELECT last_accession FROM fund_13f_state WHERE fund=?",
                             (fund_name,)).fetchone()
        if prior and prior[0]:
            print(f"  [skip] {fund_name[:40]}: already ingested {prior[0]}")
            n_skipped += 1
            continue
        acc, filed = latest_13f_acc(cik)
        if not acc:
            print(f"  [-] {fund_name[:40]}: no 13F-HR found")
            time.sleep(1)
            continue
        path = find_infotable(cik, acc)
        if not path:
            print(f"  [-] {fund_name[:40]}: no infotable in {acc}")
            time.sleep(1)
            continue
        url = path if path.startswith("http") else f"https://www.sec.gov{path}"
        body = curl(url)
        if not body:
            print(f"  [-] {fund_name[:40]}: failed to fetch infotable")
            time.sleep(2)
            continue
        rows = parse_infotable(body)
        if not rows:
            print(f"  [-] {fund_name[:40]}: 0 rows parsed from XML")
            time.sleep(1)
            continue
        total_v = sum(r["value_k"] for r in rows)
        for r in rows:
            tkr = name_to_ticker(r["issuer"], name_map)
            pct = (r["value_k"] / total_v * 100) if total_v else None
            conn.execute("""INSERT OR REPLACE INTO fund_13f_holdings
                VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (fund_name, cik, acc, filed, r["issuer"], r["cusip"], tkr,
                 r["value_k"], r["shares"], r["type"], pct))
        conn.execute("""INSERT OR REPLACE INTO fund_13f_state VALUES
            (?,?,?,?,?,?,datetime('now'))""",
            (fund_name, cik, acc, filed, len(rows), total_v))
        conn.commit()
        n_done += 1
        n_holdings_total += len(rows)
        print(f"  ✓ {fund_name[:40]:<40} {len(rows)} holdings  ${total_v/1000:.0f}M total")
        time.sleep(0.5)  # polite throttle

    print(f"\nDone: {n_done} new funds, {n_skipped} skipped (already ingested), {n_holdings_total} holdings added")

if __name__ == "__main__":
    only = sys.argv[1:] if len(sys.argv) > 1 else None
    run(only)
