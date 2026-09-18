"""Pull 13D / 13G filings for known activist HOLDERS by CIK.

The submissions API on the issuer's CIK misses 13D/G filings because those
are filed by the HOLDER and appear under the holder's submissions feed.

This module hits each known holder CIK in turn, pulls their recent 13D/G
filings, then parses the subject ticker out of the form header — producing
a verified primary-source link between holder, issuer, and percentage.
"""
import json, os, re, sqlite3, subprocess, sys, time
DB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "cyclepapa.db")
UA = "cyclepapa-research admin@example.com"

# Known activist holders + their EDGAR CIKs (the ones we cite in headline claims)
HOLDERS = [
    ("Abrams Capital Management",       "0001358975"),
    ("Steel Partners Holdings",         "0001255474"),
    ("Star Equity Fund / Eberwein",     "0001548312"),
    ("Veradace Partners",               "0002041010"),
    ("Forager Capital",                 "0001942215"),
    ("Bradley L. Radoff",               "0001380585"),
    ("Funicular Funds / Cable Car",     "0001690997"),
    ("Casdin Capital",                  "0001702290"),
    ("Carl Icahn / Icahn Capital",      "0000921669"),
    ("GAMCO / Gabelli",                 "0000807249"),
    ("Mario Gabelli individual",        "0001056679"),
    ("Wynnefield Capital",              "0001083638"),
    ("Coliseum Capital",                "0001460438"),
    ("Pershing Square",                 "0001336528"),
    ("Saber Capital / John Huber",      "0001755484"),
    ("Right Tail Capital",              "0001930434"),
    ("Brave Warrior",                   "0001316772"),
    ("Permian Investment Partners",     "0001475144"),
    ("ADW Capital Management",          "0001525266"),
    ("Engine Capital",                  "0001603194"),
    ("Pelham Capital",                  "0001442067"),
    ("Greystone Capital",               "0001904057"),
    ("Buckley Capital Advisors",        "0001834376"),
    ("Findell Capital",                 "0001863466"),
    ("Caligan Partners",                "0001782902"),
    ("Harbert Discovery Fund",          "0001626127"),
    ("OrbiMed Advisors",                "0001055951"),
    ("RA Capital",                      "0001346824"),
    ("Baker Bros Advisors",             "0001263508"),
    ("Suvretta Capital",                "0001528984"),
    ("BVF Partners",                    "0001029387"),
    ("EcoR1 Capital",                   "0001515691"),
    ("Mudrick Capital",                 "0001628094"),
    ("Paulson & Co",                    "0001035674"),
    ("GoldenTree Asset Management",     "0001278951"),
    ("Marathon Asset Management",       "0001218497"),
    ("Silver Point Capital",            "0001332784"),
    ("Pentwater Capital",               "0001425851"),
    ("Sachem Head Capital",             "0001559392"),
    ("Glenview Capital",                "0001088980"),
    ("Mangrove Partners",               "0001535738"),
    ("Cevian Capital",                  "0001234487"),
    ("Cartica Management",              "0001493152"),
    ("Sequoia Fund / Ruane Cunniff",    "0000089043"),
    ("Pzena Investment",                "0001185186"),
    ("CAS Investment Partners",         "0001628110"),
    ("Davis Selected Advisers",         "0001274838"),
    ("Sessa Capital",                   "0001543160"),
    ("Greenhaven Road Investment",      "0001633836"),
    ("Legion Partners",                 "0001603250"),
    ("D3 / Nierenberg",                 "0001096752"),
    ("Petrus Advisers",                 "0001712110"),
]

def curl(url):
    return subprocess.run(["curl", "-sk", "--compressed", "-m", "20", "-A", UA, url],
                          capture_output=True).stdout.decode("utf-8", errors="replace")

def filings_13_for_holder(cik):
    cik = cik.zfill(10)
    j = curl(f"https://data.sec.gov/submissions/CIK{cik}.json")
    try:
        d = json.loads(j); rec = d["filings"]["recent"]
    except Exception:
        return []
    out = []
    for i in range(min(len(rec["form"]), 80)):
        f = rec["form"][i]
        if f.startswith("SC 13"):
            out.append({"form": f, "filed": rec["filingDate"][i],
                        "accession": rec["accessionNumber"][i],
                        "primary_doc": rec["primaryDocument"][i]})
    return out

def parse_subject(cik, accession, primary_doc):
    """Pull subject company + percentage from a 13D/G filing header."""
    acc = accession.replace("-", "")
    url = f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={cik}&type=SC+13&dateb=&owner=include&count=10"
    # try the .txt header which has standardized SUBJECT COMPANY block
    txt_url = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc}/{accession}.txt"
    txt = curl(txt_url)
    if not txt or len(txt) < 500:
        # try the index page format
        ix = curl(f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc}/")
        return None, None, None, txt_url
    # SUBJECT COMPANY block
    m = re.search(r"SUBJECT COMPANY:.*?COMPANY CONFORMED NAME:\s*(.+?)\n.*?CENTRAL INDEX KEY:\s*(\d+)",
                  txt, re.S | re.I)
    subj_name = m.group(1).strip() if m else None
    subj_cik = m.group(2) if m else None
    # ticker from CIK via the master list
    tkr = TICKER_BY_CIK.get(str(int(subj_cik))) if subj_cik else None
    # Fallback: pull subject ticker from CUSIP -> not available;
    # try header-based "Name of Issuer:" pattern instead
    if not tkr:
        m2 = re.search(r"(?:Name of Issuer|Issuer Name|Issuer:|Company Name:)\s*([A-Z][^\n]{2,40})", txt)
        if m2 and not subj_name:
            subj_name = m2.group(1).strip()
    # find a "PERCENT OF CLASS" or "Item 5" % statement
    pct = None
    for pat in (r"PERCENT OF CLASS.*?(\d+(?:\.\d+)?)\s*%",
                r"percentage of class.*?(\d+(?:\.\d+)?)\s*%",
                r"approximately\s+(\d+(?:\.\d+)?)\s*%",
                r"\b(\d+(?:\.\d+)?)\s*%\s+of\s+(?:the\s+)?(?:outstanding|issued|common|class)"):
        mp = re.search(pat, txt, re.I | re.S)
        if mp:
            try:
                v = float(mp.group(1))
                if 0.5 < v < 100: pct = v; break
            except ValueError: pass
    return subj_name, tkr, pct, txt_url

TICKER_BY_CIK = {}

def run():
    conn = sqlite3.connect(DB)
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS holder_13d (
      holder TEXT, holder_cik TEXT, form TEXT, filed TEXT, accession TEXT,
      subject_name TEXT, subject_cik TEXT, subject_ticker TEXT,
      pct_class REAL, source_url TEXT,
      PRIMARY KEY (holder_cik, accession));
    """)
    global TICKER_BY_CIK
    try:
        j = json.loads(curl("https://www.sec.gov/files/company_tickers.json"))
        TICKER_BY_CIK = {str(v["cik_str"]): v["ticker"] for v in j.values()}
    except Exception:
        TICKER_BY_CIK = {}
    print(f"loaded {len(TICKER_BY_CIK)} ticker mappings")
    n_holders = n_filings = 0
    for hname, cik in HOLDERS:
        fl = filings_13_for_holder(cik)
        if not fl:
            print(f"  {hname:<36} no 13D/G found")
            n_holders += 1
            time.sleep(0.15)
            continue
        for f in fl[:8]:
            subj, tkr, pct, src = parse_subject(cik, f["accession"], f["primary_doc"])
            # If ticker came back but subject CIK didn't (regex variant), still keep ticker.
            # Backfill subject_cik from TICKER_BY_CIK reverse map when possible.
            subj_cik_back = None
            if tkr:
                subj_cik_back = next((c for c, t in TICKER_BY_CIK.items() if t == tkr), None)
            conn.execute("""INSERT OR REPLACE INTO holder_13d VALUES (?,?,?,?,?,?,?,?,?,?)""",
                         (hname, cik, f["form"], f["filed"], f["accession"],
                          subj, subj_cik_back, tkr, pct, src))
            n_filings += 1
            time.sleep(0.12)
        print(f"  {hname:<36} {len(fl)} 13D/G filings parsed")
        n_holders += 1
    conn.commit()
    print(f"\n{n_holders} holders queried, {n_filings} filings stored")
    print(f"\nHEADLINE PRIMARY-SOURCE OWNERSHIP (recent SC 13D/G with parsed %):")
    for r in conn.execute("""SELECT holder, subject_ticker, subject_name, form, filed, pct_class
                             FROM holder_13d WHERE subject_ticker IS NOT NULL AND pct_class IS NOT NULL
                             ORDER BY pct_class DESC LIMIT 30"""):
        print(f"  {r[1]:<7} {r[5]:>5.1f}%  {r[3]:<10} {r[4]:<11} {r[0][:32]:<32} ({r[2][:34] if r[2] else ''})")

if __name__ == "__main__":
    run()
