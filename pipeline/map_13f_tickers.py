"""Resolve issuer names from 13F filings to tickers via multi-source matching.

The 13F infotable has nameOfIssuer + cusip but NOT ticker. SEC's
company_tickers_exchange.json has cik→ticker→name but not by CUSIP.

Strategy in order:
  1. Direct name match against SEC's company list (8,000+ issuers)
  2. Aggressive normalize (strip CLASS A / B, INC, CORP, LTD, etc.)
  3. CUSIP → CIK via the SEC EDGAR full-text 'company-tickers.json' with CUSIP key (if available)
  4. CUSIP → ticker via FUND_POSITIONS table — if any fund has tagged the
     same CUSIP and ticker in fund_positions, we propagate the mapping

Updates fund_13f_holdings.ticker in place. Idempotent — safe to re-run.
"""
import json, os, re, sqlite3, subprocess, time
DB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "cyclepapa.db")
UA = "cyclepapa-research admin@example.com"

def curl(url):
    return subprocess.run(["curl", "-sk", "--compressed", "-m", "20", "-A", UA, url],
                          capture_output=True).stdout

SUFFIX_RE = re.compile(r"\b(INC|CORP|CORPORATION|HOLDINGS?|HLDGS|GROUP|GRP|LTD|PLC|LP|LLC|"
                       r"CLASS\s+[A-Z]|CL\s+[A-Z]|COM|COMMON|NEW|TRUST|SA|SE|NV|AG|OYJ|OY|AB|"
                       r"SOC|COMPANIES?|INDUSTRIES?|PARTNERS|FUND|N\.V\.|A/S)\b", re.I)
PUNCT_RE = re.compile(r"[.,&'/\-]")

def normalize(name):
    if not name: return ""
    n = name.upper()
    n = SUFFIX_RE.sub("", n)
    n = PUNCT_RE.sub(" ", n)
    n = re.sub(r"\s+", " ", n).strip()
    return n

def build_name_index(conn):
    """Pull SEC's company-tickers-exchange and build a name → ticker index."""
    data = curl("https://www.sec.gov/files/company_tickers_exchange.json")
    if not data: return {}
    j = json.loads(data)
    cols = j["fields"]
    idx_name = cols.index("name")
    idx_tkr = cols.index("ticker")
    name_to_tkr = {}
    for row in j["data"]:
        nm = row[idx_name]
        tk = row[idx_tkr]
        if not nm or not tk: continue
        # exact uppercase
        name_to_tkr[nm.upper()] = tk
        # normalized
        n = normalize(nm)
        if n and n not in name_to_tkr: name_to_tkr[n] = tk
        # first 2 words normalized
        words = n.split()
        if len(words) >= 2:
            two = " ".join(words[:2])
            if two not in name_to_tkr: name_to_tkr[two] = tk
    return name_to_tkr

def cusip_to_ticker_from_positions(conn):
    """If a CUSIP appears with a known ticker anywhere in fund_13f_holdings (or
    in fund_positions if we add CUSIP there), use that as a propagation source."""
    out = {}
    for r in conn.execute("""SELECT cusip, ticker, COUNT(*) AS c
        FROM fund_13f_holdings WHERE ticker IS NOT NULL AND cusip != ''
        GROUP BY cusip, ticker ORDER BY c DESC"""):
        if r[0] not in out: out[r[0]] = r[1]
    return out

def run():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    print("building SEC name index...")
    name_idx = build_name_index(conn)
    print(f"  {len(name_idx)} name variants")
    cusip_idx = cusip_to_ticker_from_positions(conn)
    print(f"  {len(cusip_idx)} cusip-to-ticker propagations available")

    unmapped = list(conn.execute("""SELECT DISTINCT issuer, cusip FROM fund_13f_holdings
        WHERE ticker IS NULL OR ticker = ''"""))
    print(f"\nresolving {len(unmapped)} unmapped issuers...")
    resolved = 0
    for issuer, cusip in unmapped:
        tkr = None
        # CUSIP-based first (highest precision)
        if cusip and cusip in cusip_idx:
            tkr = cusip_idx[cusip]
        # Exact name
        if not tkr and issuer.upper() in name_idx:
            tkr = name_idx[issuer.upper()]
        # Normalized
        if not tkr:
            n = normalize(issuer)
            if n in name_idx: tkr = name_idx[n]
        # First two words
        if not tkr:
            words = normalize(issuer).split()
            if len(words) >= 2:
                two = " ".join(words[:2])
                if two in name_idx: tkr = name_idx[two]
        # First word as last resort if distinctive
        if not tkr:
            words = normalize(issuer).split()
            if len(words) >= 1 and len(words[0]) >= 6:
                if words[0] in name_idx: tkr = name_idx[words[0]]
        if tkr:
            conn.execute("UPDATE fund_13f_holdings SET ticker=? WHERE issuer=? AND cusip=?",
                         (tkr, issuer, cusip))
            resolved += 1
    conn.commit()
    total = conn.execute("SELECT COUNT(*) FROM fund_13f_holdings").fetchone()[0]
    mapped = conn.execute("SELECT COUNT(*) FROM fund_13f_holdings WHERE ticker IS NOT NULL").fetchone()[0]
    print(f"\nresolved {resolved} of {len(unmapped)} unmapped rows")
    print(f"  total ticker coverage: {mapped}/{total} = {mapped/total*100:.0f}%")

if __name__ == "__main__":
    run()
