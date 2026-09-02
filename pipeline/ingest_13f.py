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
import json, os, re, sqlite3, statistics, subprocess, time, sys
import xml.etree.ElementTree as ET

DB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "cyclepapa.db")
UA = "cyclepapa-research admin@example.com"

NS = {'i': 'http://www.sec.gov/edgar/document/thirteenf/informationtable'}

# CIK map for our known funds. Keyed by canonical fund name.
# Add to this as we resolve more CIKs.
FUND_CIK = {
    # --- Concentrated microcap / special-sits big-swing funds (2026-08) ---
    "Black Diamond Capital (Stephen Deckoff)": "2084285",
    "Newtyn Management": "1569241",
    "Roubaix Capital": "1769700",
    "Hudson Executive Capital (Braunstein)": "1652522",
    "Palogic Value Management": "1532943",
    "North Peak Capital Management": "1747888",
    # --- Under-radar long-term compounders (2026-08) ---
    "Eagle Capital Management (Boykin Curry)": "945631",
    "SRS Investment Mgmt (Karthik Sarma)": "1503174",
    "Atreides Management (Gavin Baker)": "1777813",
    "Markel Group (Tom Gayner)": "1096343",
    "Ensign Peak Advisors (LDS Church)": "1454984",
    "Chou Associates (Francis Chou)": "1389403",
    "Broad Run Investment Mgmt": "1568621",
    "Findlay Park Partners": "1351950",
    "WCM Investment Management": "1061186",
    "Baillie Gifford & Co": "1088875",
    "Pershing Square Capital Managem": "1336528",
    # --- Low-profile / "hidden" exceptional filers (2026-08, verified active) ---
    "Euclidean Capital (Jim Simons FO)":    "1825034",
    "Gates Foundation Trust (Larson)":      "1166559",
    "Longview Asset Mgmt (Crown Family)":   "1086477",
    "Woodbridge Co (Thomson Family)":       "1397960",
    "Summer Road (Sackler FO)":             "1604873",
    "Continental Grain (Fribourg)":         "929607",
    "Koch Inc (Koch Family)":               "2027344",
    "Stockbridge Partners (Berkshire Ptrs)": "1505183",
    "BlueCrest Capital (Michael Platt)":    "1610880",
    "Quadrature Capital (London Quant)":    "1651424",
    "Boxer Capital Management (Tavistock)": "2018299",
    # --- Billionaire family-office gap-fill (2026-08, verified active filers) ---
    "Meritage Group (Nat Simons)":          "1427119",
    "Wildcat Capital (Bonderman FO)":       "1582384",
    "Thiel Macro (Peter Thiel)":            "1562087",
    # --- PitchBook-sourced additions (2026-07, verified active 13F filers) ---
    "Cat Rock Capital Management":          "1654648",
    "Theleme Partners":                     "1511881",
    "Clarkston Capital Partners":           "1562855",
    "Hosking Partners":                     "1650135",
    "Tybourne Capital Management":          "1553936",
    "Man Group":                            "1637460",
    "Mubadala Investment Company":          "1704268",
    "Third Point LLC":                     "1040273",
    "Elliott Investment Management":       "0001791786",
    "Starboard Value LP":                  "1517137",
    "Trian Fund Management":               "1345471",
    "Icahn Capital   Carl Icahn":          "921669",
    "Baupost Group LLC":                   "1061768",
    "ValueAct Capital":                    "1418814",
    "Glenview Capital Management":         "1138995",
    "TCI Fund Management Ltd":             "1647251",
    "Lone Pine Capital LLC":               "1061165",
    "Tiger Global Management LLC":         "1167483",
    "Coatue Management LLC":               "1135730",
    "D1 Capital Partners":                 "1747057",
    "Eminence Capital LP":                 "1107310",
    "Sachem Head Capital Management":      "1582090",
    "Pentwater Capital Management":        "1425851",
    "Magnetar Capital LLC":                "1352851",
    "Suvretta Capital Management":         "1569064",
    "BVF Partners L.P.":                   "1056807",
    "OrbiMed Advisors LLC":                "1055951",
    "Baker Bros. Advisors LP":             "1263508",
    "RA Capital Management LP":            "1346824",
    "Perceptive Advisors LLC":             "1224962",
    "EcoR1 Capital LLC":                   "1587114",
    "Casdin Capital LLC":                  "1534261",
    "Armistice Capital LLC":               "1601086",
    "Marathon Asset Management":           "1279913",
    "Silver Point Capital":                "1332784",
    "Hudson Bay Capital Management L":     "1393825",
    "GoldenTree Asset Management":         "1278951",
    "Mudrick Capital Management":          "1655183",
    "Paulson & Co Inc":                    "1035674",
    "Fairfax Financial Holdings":          "915191",
    "Pelham Capital Management":           "1654111",
    "Engine Capital":                      "1665590",
    "Wynnefield Capital":                  "1251567",
    "ADW Capital Management":              "1745214",
    "Caligan Partners LP":                 "1727492",
    "Buckley Capital Advisors":            "2111611",
    "Harbert Discovery Fund":              "1616659",
    "Cevian Capital":                      "1365341",
    "Cartica Management":                  "1600011",
    "Sessa Capital":                       "1595849",
    "Pzena Investment Management":         "1027796",
    "CAS Investment Partners":             "1697591",
    "Petrus Advisers":                     "1473429",
    "JANA Partners":                       "1998597",
    "Voss Capital":                        "1730145",
    "Marlowe Partners":                    "1624049",
    "Alta Fox Capital Management":         "1858353",
    "Roumell Asset Management":            "1331693",
    "Cove Street Capital":                 "1531612",
    "Donald Smith & Co":                   "814375",
    "Third Avenue Management":             "1099281",
    "Dodge and Cox":                       "200217",
    "Lindsell Train Limited":              "1484150",
    "Yacktman Asset Management LP":        "905567",
    "Wedgewood Partners":                  "859804",
    "Cantillon Capital Management":        "1279936",
    "Dorsey Asset Management":             "1671657",
    "Patient Capital Management":          "1854794",
    "Oakcliff Capital Partners":           "1657335",
    "Greenlea Lane Capital":               "1766504",
    "Daily Journal Corporation":           "783412",
    "Berkshire Hathaway":                  "1067983",
    "Himalaya Capital Management":         "1709323",
    "Sound Shore Management":              "820124",
    "Kahn Brothers Group":                 "1039565",
    "Jensen Investment Management":        "1106129",
    "Atlantic Investment Management":      "1063296",
    "Conifer Management":                  "1773994",
    "Altarock Partners":                   "1631014",
    "FPA Crescent Fund":                   "1377581",
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
    """Return (accession, filed_date) of the latest 13F-HR for this CIK.

    The submissions JSON "recent" block holds only the last ~1000 filings. A
    10%-owner like Viking files hundreds of Form 4/SC 13 amendments a quarter,
    which can push its own 13F-HR out of the window — fall through to the paged
    history files (newest first) before concluding the CIK doesn't file."""
    cik10 = cik.zfill(10)
    data = curl(f"https://data.sec.gov/submissions/CIK{cik10}.json")
    if not data: return None, None
    try:
        d = json.loads(data)
    except json.JSONDecodeError:
        return None, None
    rec = d["filings"]["recent"]
    hits = [(rec["accessionNumber"][i], rec["filingDate"][i])
            for i, form in enumerate(rec["form"]) if form == "13F-HR"]
    if not hits:
        pages = sorted(d["filings"].get("files", []),
                       key=lambda p: p.get("filingTo", ""), reverse=True)
        for pg in pages:                            # newest chunk first
            data = curl(f"https://data.sec.gov/submissions/{pg['name']}")
            if not data: continue
            try:
                rec = json.loads(data)
            except json.JSONDecodeError:
                continue
            hits = [(rec["accessionNumber"][i], rec["filingDate"][i])
                    for i, form in enumerate(rec["form"]) if form == "13F-HR"]
            if hits:
                break
    return hits[0] if hits else (None, None)

def list_13f_accs(cik, k=3):
    """Up to k most recent 13F-HR (accession, filed) pairs, newest first.
    Lets the ingest fall past an empty off-cycle restatement (Eminence filed a
    1-row 13F-HR in July 2026; the real Q1 book was the accession before it)."""
    cik10 = cik.zfill(10)
    data = curl(f"https://data.sec.gov/submissions/CIK{cik10}.json")
    if not data: return []
    try:
        d = json.loads(data)
    except json.JSONDecodeError:
        return []
    rec = d["filings"]["recent"]
    hits = [(rec["accessionNumber"][i], rec["filingDate"][i])
            for i, form in enumerate(rec["form"]) if form == "13F-HR"]
    if len(hits) < k:
        for pg in sorted(d["filings"].get("files", []),
                         key=lambda p: p.get("filingTo", ""), reverse=True):
            data = curl(f"https://data.sec.gov/submissions/{pg['name']}")
            if not data: continue
            try:
                rec = json.loads(data)
            except json.JSONDecodeError:
                continue
            hits += [(rec["accessionNumber"][i], rec["filingDate"][i])
                     for i, form in enumerate(rec["form"]) if form == "13F-HR"]
            if len(hits) >= k:
                break
    return hits[:k]

def find_infotable(cik, accession):
    """Find the infotable XML file in the filing directory.

    The XML name is filer-controlled and inconsistent — examples seen:
      infotable.xml / informationtable.xml (most common)
      WedgewoodPartners_13f_1Q26.xml (some filers brand the file)
      13F_2026Q1.xml / xslform13fhrxxx-fix.xml (others)

    Strategy: prefer obvious "infotable" / "informationtable" name; else
    fall back to ANY .xml in the directory that isn't primary_doc.xml
    (which is the cover-page form13f wrapper).
    """
    acc = accession.replace("-", "")
    data = curl(f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc}/")
    if not data: return None
    matches = re.findall(r'href="([^"]+\.xml)"', data.decode("utf-8", errors="ignore"), re.I)
    # Drop noisy hrefs that aren't in our filing dir, and exclude xslForm paths
    # (those are the XSL-rendered HTML versions, not raw data)
    relevant = [m for m in matches if str(int(cik)) in m and acc in m
                and "xslform" not in m.lower()]
    for m in relevant:
        n = m.split("/")[-1].lower()
        if "infotable" in n or "informationtable" in n: return m
    for m in relevant:
        n = m.split("/")[-1].lower()
        if n == "primary_doc.xml": continue
        return m
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
            # titleOfClass is the filer's own security-class label ("COM",
            # "PFD", "WARRANT", "CL A", "UNIT", "NOTE", "SPON ADR"...). Lets us
            # tell an add of COMMON (a clean directional bet) from an add of
            # warrants / preferred / converts (optionality or financing).
            "title":  t("titleOfClass")[:40],
            # Derivatives are reported at underlying value with putCall set.
            # Booking them as shares corrupts consensus (a PUT is bearish!) —
            # OrbiMed's $286M MDXH call surfaced as an 11x-mcap "holding".
            "put_call": t("putCall").lower(),
        })
    return out

# titleOfClass -> normalized equity form. Order matters (warrant before common
# so "COM WT" reads as warrant). Falls back to sh_type for bonds (PRN=note).
def classify_sec_form(title, sh_type=""):
    tt = (title or "").upper()
    if sh_type == "PRN" or re.search(r"\bNOTE|\bBOND|\bDEB\b|SR NT|% DUE|CONV NT", tt):
        return "note"
    if re.search(r"WARRANT|\bWTS?\b|\bWT\b|\bWS\b", tt):
        return "warrant"
    if re.search(r"\bRIGHT|\bRTS?\b|\bRT\b|CVR|CONTINGENT VALUE", tt):
        return "right"
    if re.search(r"\bUNIT", tt):
        return "unit"
    if re.search(r"\bPFD|PREF|PREFERRED|DEP(OSITARY)?\s+SH|DEP\s+REP|% CUM|% SR", tt):
        return "preferred"
    if re.search(r"\bADR|ADS|SPON(SORED)?\s+ADR|AMERICAN DEP", tt):
        return "adr"
    if re.search(r"\bCL\s+[A-Z]\b|CLASS\s+[A-Z]\b|SER(IES)?\s+[A-Z]\b", tt):
        return "class"          # dual-class common (COM CL A / CLASS B)
    if re.search(r"\bCOM\b|COMMON|\bORD|ORDINARY|\bSHS?\b|SHARES|STK\b|CAP STK|BEN INT|SBI", tt):
        return "common"
    return "common" if tt == "" else "other"

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
            nn = _norm_name(name)          # normalized key for fuzzy match
            if nn and nn not in by_name:
                by_name[nn] = tkr
    return by_name

def _norm_name(s):
    """Normalise an issuer name for matching: drop punctuation and corporate
    suffixes so 'MOODYS CORP DEL' and 'Moody's Corporation' collide."""
    s = (s or "").upper()
    s = re.sub(r"[.,'/&()\-]", " ", s)
    # Expand SEC's standard abbreviations FIRST so an issuer's "CNX RES CORP" and
    # the SEC file's "CNX Resources Corp" normalize to the same tokens. This is the
    # single biggest source of silently-dropped REAL companies (Brookdale "SR
    # LIVING", VICI "PPTYS", UGI "CORP NEW", Global "PMTS") — expansion makes both
    # sides specific rather than guessing. Expanding NEVER collapses distinct firms.
    s = " " + s + " "
    for ab, full in _ABBREV.items():
        s = re.sub(rf"\b{ab}\b", full, s)
    s = re.sub(r"\b(THE|INC|CORP|CORPORATION|CO|COMPANY|COS|HOLDING|HOLDINGS|HLDGS?|"
               r"GROUP|GRP|LTD|LIMITED|PLC|LP|LLC|NV|SA|AG|ADR|ADS|SP|SPONSORED|"
               r"CLASS|CL|COM|COMMON|ORD|ORDINARY|NEW|DEL|TR|TRUST|REIT|PARTNERS)\b", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s

# SEC issuer-name abbreviations -> full word (both the 13F issuer and the SEC
# ticker file get normalized through this, so they collide).
_ABBREV = {
    "RES": "RESOURCES", "PPTYS": "PROPERTIES", "PPTY": "PROPERTIES", "PROPS": "PROPERTIES",
    "SR": "SENIOR", "PMTS": "PAYMENTS", "PMT": "PAYMENT", "INDS": "INDUSTRIES",
    "IND": "INDUSTRIES", "INVT": "INVESTMENT", "INVTS": "INVESTMENTS", "INV": "INVESTMENT",
    "MGMT": "MANAGEMENT", "MGT": "MANAGEMENT", "INTL": "INTERNATIONAL", "NATL": "NATIONAL",
    "FINL": "FINANCIAL", "FIN": "FINANCIAL", "SVCS": "SERVICES", "SVC": "SERVICE",
    "SYS": "SYSTEMS", "TECHS": "TECHNOLOGIES", "TCHNLGY": "TECHNOLOGY", "COMMTNS": "COMMUNICATIONS",
    "COMM": "COMMUNICATIONS", "COMMUN": "COMMUNICATIONS", "PHARMS": "PHARMACEUTICALS",
    "PHARM": "PHARMACEUTICALS", "PHRM": "PHARMACEUTICALS", "LAB": "LABORATORIES",
    "LABS": "LABORATORIES", "MTLS": "MATERIALS", "MTL": "METALS", "ENGY": "ENERGY",
    "ENRGY": "ENERGY", "PWR": "POWER", "BANCORPORATION": "BANCORP", "BANCSHARES": "BANCSHARES",
    "HLTH": "HEALTH", "HLTHCARE": "HEALTHCARE", "Cap": "CAPITAL", "CAP": "CAPITAL",
    "MFG": "MANUFACTURING", "MFRS": "MANUFACTURERS", "GLBL": "GLOBAL", "SEMICONDUCTOR": "SEMICONDUCTOR",
    "SEMI": "SEMICONDUCTOR", "PROD": "PRODUCTS", "PRODS": "PRODUCTS", "SOLTNS": "SOLUTIONS",
    "SLTNS": "SOLUTIONS", "ENTMT": "ENTERTAINMENT", "ENTERTAINMEN": "ENTERTAINMENT",
}

# ETF / fund-family issuers. A 13F line for "Invesco Exch Trd" or "Global X Fds"
# is an ETF POSITION, not smart money in the operating company that shares a name
# stem (Invesco Ltd / Global Partners LP). Historically the fuzzy matcher
# collapsed whole fund families onto one operating ticker (GLP got 137 phantom
# "Global*" holders; IVZ 302), badly inflating smart_money_n. Fund issuers must
# NOT fuzzy-map to an operating ticker.
# Structural fund-vehicle tokens only — NOT brand names (WisdomTree/Invesco are
# also operating tickers). Real operating companies whose name contains "Trust"
# or "Fund" (Northern Trust=NTRS, Eaton Vance, Franklin) are protected because
# name_to_ticker's raw-exact SEC lookup runs BEFORE this guard; only issuers
# absent from the SEC ticker file (the ETF trust entities) fall through to it.
_FUND_ISSUER_RE = re.compile(
    r"\b(ETF|ETFS|EXCH\s*TRD|EXCHANGE\s*TRD|FDS|SER\s*TR|"
    r"INDEX\s*(FD|FDS|FUND|FUNDS|TR|TRUST)|"
    r"UCITS|SELECT\s*SECTOR|ISHARES|SPDR|POWERSHARES|PROSHARES)\b"
    r"|(\bTR|TRUST|FUND|FUNDS|SHARES|PORTFOLIO)\s*$", re.I)

def _is_fund_issuer(name):
    return bool(_FUND_ISSUER_RE.search(name or ""))

def name_to_ticker(name, name_map):
    if not name: return None
    n = name.upper().strip()
    if n in name_map: return name_map[n]   # raw exact is always safe
    # Fund/ETF issuers stop here: normalization strips the very tokens (TRUST /
    # FUND / TR) that distinguish an ETF from its same-named operating parent, so
    # norm-exact and fuzzy would collapse "WisdomTree Trust" onto WT, "Invesco
    # Exch Trd" onto IVZ. A fund line is an ETF position, not a stock pick.
    if _is_fund_issuer(name):
        return None
    # normalised exact match (handles punctuation + corporate suffixes)
    nn = _norm_name(name)
    if nn and nn in name_map: return name_map[nn]
    # legacy suffix-strip
    cleaned = re.sub(r"\b(INC|CORP|CORPORATION|HOLDINGS?|GROUP|LTD|PLC|LP|LLC|CLASS\s+[A-Z]|COM|COMMON)\b", "", n).strip()
    if cleaned in name_map: return name_map[cleaned]
    # token match: a map key must be a leading prefix of the issuer AND cover most
    # of it (>=60%), so "INVESCO" (7) can't claim "INVESCO EXCH TRD" (16).
    for full_name, tkr in name_map.items():
        if (full_name and len(full_name) > 6
                and n.startswith(full_name) and len(full_name) >= 0.6 * len(n)):
            return tkr
    return None

def run(only=None):
    conn = sqlite3.connect(DB, timeout=120); conn.execute("PRAGMA busy_timeout=120000")
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
    CREATE TABLE IF NOT EXISTS holding_sec_form (
      accession TEXT, cusip TEXT, title_class TEXT, sec_form TEXT,
      PRIMARY KEY (accession, cusip));
    """)

    print("loading SEC ticker map...")
    name_map = cusip_ticker_map(conn)
    print(f"  {len(name_map)} name-to-ticker mappings loaded")
    # CUSIP authority: persisted resolutions (OpenFIGI + consensus) checked FIRST,
    # so a once-resolved CUSIP is never re-lost to a name quirk and a fund vehicle
    # never re-maps onto an operating ticker. ticker may be None = known-unmappable.
    try:
        cusip_map = {c: (tk, st) for c, tk, st in
                     conn.execute("SELECT cusip, ticker, sec_type FROM cusip_map")}
    except sqlite3.OperationalError:
        cusip_map = {}
    print(f"  {len(cusip_map)} CUSIP-authority mappings loaded")
    try:
        px_map = {t: p for t, p in conn.execute(
            "SELECT ticker, price FROM ticker_yf WHERE price > 0")}
    except sqlite3.OperationalError:
        px_map = {}
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
        # Walk recent 13F-HRs newest-first: an empty off-cycle restatement
        # (Eminence, July 2026: 1 zero row) must fall through to the real book.
        rows, acc, filed = None, None, None
        for cand_acc, cand_filed in list_13f_accs(cik):
            if not cand_acc:
                break
            path = find_infotable(cik, cand_acc)
            if not path:
                continue
            url = path if path.startswith("http") else f"https://www.sec.gov{path}"
            body = curl(url)
            cand = parse_infotable(body) if body else []
            cand = [r for r in cand if not r.get("put_call")]  # options are not holdings
            cand = [r for r in cand if r["value_k"] or r["shares"]]
            if cand:
                rows, acc, filed = cand, cand_acc, cand_filed
                break
            time.sleep(0.4)
        if not rows:
            print(f"  [-] {fund_name[:40]}: no usable 13F-HR (empty/derivative-only/missing)")
            time.sleep(1)
            continue
        # A combined report files one line per ACCOUNT per security (Kopernik:
        # 23,960 lines for ~4,400 securities). Sum lines by CUSIP — the old
        # REPLACE-on-PK kept only the last account's slice of each position.
        agg = {}
        for r in rows:
            a = agg.get(r["cusip"])
            if a is None:
                agg[r["cusip"]] = dict(r)
            else:
                a["value_k"] += r["value_k"]
                a["shares"]  += r["shares"]
        rows = list(agg.values())
        total_v = sum(r["value_k"] for r in rows)
        ratios = []          # implied-price / actual-price, for value-unit detection
        for r in rows:
            # Empty-filing markers ("NONE", "NA", cusip 000000000) and zero rows
            # carry no information and must never be booked as holdings.
            if not r["value_k"] and not r["shares"]:
                continue
            # Placeholder CUSIPs are shared across unrelated rows: never consult
            # the authority map for them, fall through to name matching.
            cusip_ok = r["cusip"] and len(r["cusip"]) == 9 and len(set(r["cusip"])) > 1
            cm = cusip_map.get(r["cusip"]) if cusip_ok else None
            if cm is not None:                       # CUSIP authority wins
                tkr = cm[0] if cm[1] != "etf" else None
            else:
                tkr = name_to_ticker(r["issuer"], name_map)
            pct = (r["value_k"] / total_v * 100) if total_v else None
            conn.execute("""INSERT OR REPLACE INTO fund_13f_holdings
                VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (fund_name, cik, acc, filed, r["issuer"], r["cusip"], tkr,
                 r["value_k"], r["shares"], r["type"], pct))
            conn.execute("""INSERT OR REPLACE INTO holding_sec_form VALUES (?,?,?,?)""",
                (acc, r["cusip"], r.get("title"),
                 classify_sec_form(r.get("title"), r["type"])))
            # PRN rows: shares = bond principal in dollars, which trades near par
            # (~1.0 value per $1) — reference price 1.0 keeps convert-arb books
            # (Linden: mostly bonds, few priced SH rows) inside the detector.
            p = 1.0 if r["type"] == "PRN" else px_map.get(tkr)
            if p and r["shares"] and r["value_k"]:
                ratios.append((r["value_k"] * 1000.0 / r["shares"]) / p)
        # Value-unit sanity: filings since 2023 report FULL DOLLARS; value_k
        # assumes thousands. Implied price (value/shares) vs actual price is a
        # unit-free detector: median ratio ~1000 means full-dollar filing.
        # The old mcap-based check missed megacap-heavy books (a raw-dollar
        # TSM position is still below TSM's mcap) — Gates Trust booked $31.7T.
        if ((len(ratios) >= 2 and statistics.median(ratios) > 100)
                or (len(ratios) == 1 and ratios[0] > 100)):
            conn.execute("UPDATE fund_13f_holdings SET value_k=value_k/1000.0 WHERE fund=?",
                         (fund_name,))
            total_v /= 1000.0
            print(f"    [unit] {fund_name[:36]}: full-dollar filing normalized to $k")
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
