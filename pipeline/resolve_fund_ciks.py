"""Resolve fund_meta names to SEC CIKs via EDGAR full-text search.

For each fund in fund_meta we hit EDGAR's company-search to find candidate
CIKs filing 13F-HR. Stores all candidates with confidence scores in
fund_cik_map so the user can audit/override.

Politeness: per-call sleep + 429 backoff. Resumable — skips funds already
resolved.
"""
import json, os, re, sqlite3, subprocess, sys, time

DB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "cyclepapa.db")
UA = "cyclepapa-research admin@example.com"

def curl(url):
    for i in range(3):
        r = subprocess.run(["curl", "-sk", "--compressed", "-m", "20", "-A", UA, url],
                           capture_output=True).stdout
        if r[:200].find(b"Rate Threshold Exceeded") != -1:
            time.sleep(15 + 5*i); continue
        return r
    return b''

def clean_fund_name(n):
    """Strip trailing manager/partner names and tier suffixes.

    Excel sheet names are capped at 31 chars, so we frequently get an
    UNCLOSED parenthetical at the end (e.g. "AQR Capital LLC (Cli"). Cut
    everything from the first '(' onward unconditionally rather than only
    matching balanced parens.
    """
    n = n.split(" / ")[0].split("  ")[0]
    n = re.sub(r"\b(Tier\s+\d|–.*$|—.*$|\bT\d\b)", "", n)
    cut = n.find("(")
    if cut > 0:
        n = n[:cut]
    n = re.sub(r"\s+", " ", n).strip(" ,-/.")
    return n

def search_edgar(name):
    """Use EDGAR's full-text company search to find CIK candidates."""
    q = name.replace(" ", "+")
    url = f"https://www.sec.gov/cgi-bin/browse-edgar?company={q}&CIK=&type=13F&dateb=&owner=include&count=10&action=getcompany"
    body = curl(url)
    if not body: return []
    text = body.decode("utf-8", errors="ignore")
    # parse the table rows: <a href="...CIK=0001234567...">Company Name</a>
    rows = []
    for m in re.finditer(r'CIK=(\d{10})[^"]*"[^>]*>([^<]+)</a>', text):
        cik, label = m.group(1), m.group(2).strip()
        # immediate window for filing-state info
        snippet = text[m.end():m.end()+400]
        has_13f = "13F-HR" in snippet
        rows.append((cik.lstrip("0") or cik, label, has_13f))
    # dedupe by cik, prefer 13F filers
    seen, out = set(), []
    for cik, lbl, h in sorted(rows, key=lambda x: not x[2]):
        if cik in seen: continue
        seen.add(cik); out.append((cik, lbl, h))
    return out[:5]

def confidence(query, label):
    """Word-overlap confidence between query and matched company name.

    Strip only the most uninformative legal-form tokens (LP/LLC/INC/CORP/LTD).
    Keep CAPITAL/MANAGEMENT/PARTNERS — those distinguish similarly-named
    firms (e.g. "Capital Partners" vs "Asset Management"). Use Jaccard so
    very short queries don't get a deceptively high score.
    """
    qw = set(re.sub(r"[^A-Za-z ]", "", query).upper().split())
    lw = set(re.sub(r"[^A-Za-z ]", "", label).upper().split())
    legal = {"LP","LLC","INC","CORP","LTD","PLC","COMPANY","CO","THE","AND","OF"}
    qw -= legal; lw -= legal
    if not qw or not lw: return 0.0
    return round(len(qw & lw) / len(qw | lw), 2)

def run():
    conn = sqlite3.connect(DB)
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS fund_cik_map (
      fund TEXT, cik TEXT, edgar_name TEXT, confidence REAL, has_13f INTEGER,
      asof TEXT, PRIMARY KEY (fund, cik));
    CREATE TABLE IF NOT EXISTS fund_resolution_state (
      fund TEXT PRIMARY KEY, n_candidates INTEGER, best_cik TEXT,
      best_conf REAL, status TEXT, asof TEXT);
    """)

    # Skip funds already resolved (have any candidate)
    done = {r[0] for r in conn.execute("SELECT fund FROM fund_resolution_state")}
    # Skip funds already in ingest_13f's FUND_CIK
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from ingest_13f import FUND_CIK
    already_have = {k for k in FUND_CIK}
    targets = [r[0] for r in conn.execute("SELECT fund FROM fund_meta ORDER BY fund")
               if r[0] not in done and r[0] not in already_have]
    print(f"resolving {len(targets)} funds...\n")

    n_resolved = 0
    for fund in targets:
        clean = clean_fund_name(fund)
        if not clean or len(clean) < 4:
            conn.execute("INSERT INTO fund_resolution_state VALUES (?,?,?,?,?,date('now'))",
                         (fund, 0, None, 0, "name_too_short"))
            continue
        candidates = search_edgar(clean)
        time.sleep(0.7)
        best_cik = None; best_conf = 0.0; best_status = "none"
        for cik, lbl, has13 in candidates:
            conf = confidence(clean, lbl)
            conn.execute("""INSERT OR REPLACE INTO fund_cik_map
                VALUES (?,?,?,?,?,date('now'))""", (fund, cik, lbl, conf, 1 if has13 else 0))
            if conf > best_conf:
                best_cik, best_conf = cik, conf
                best_status = "13F_filer" if has13 else "non_13F"
        if best_conf == 0 and candidates:
            best_cik = candidates[0][0]; best_status = "low_confidence"
        status = best_status if best_cik else "no_match"
        conn.execute("""INSERT OR REPLACE INTO fund_resolution_state
            VALUES (?,?,?,?,?,date('now'))""",
            (fund, len(candidates), best_cik, best_conf, status))
        if best_cik and best_conf >= 0.5 and best_status == "13F_filer":
            n_resolved += 1
            print(f"  ✓ {fund[:40]:<40} CIK={best_cik:<10}  conf={best_conf:<4}  {candidates[0][1][:40]}")
        elif best_cik:
            print(f"  ~ {fund[:40]:<40} CIK={best_cik:<10}  conf={best_conf:<4}  status={status}")
        else:
            print(f"  - {fund[:40]:<40} no match found")
        conn.commit()

    print(f"\nDone. {n_resolved} high-confidence 13F filers resolved.")

if __name__ == "__main__":
    run()
