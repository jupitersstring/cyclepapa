"""Resolve EDGAR 13F-HR filer CIKs for under-covered funds.

Many funds we hold with only a thin top-N research stub actually FILE a US
Form 13F-HR — we just never resolved their filer CIK. We resolve the filer by
NAME using EDGAR's company browser filtered to type=13F-HR (so only genuine 13F
filers are ever returned), confirm the authoritative entity name via the
submissions API, and write best_cik so refresh_13f_holdings can pull the
COMPLETE position list.

Why not full-text search (efts)?  efts surfaces every filer who *mentions* a
phrase in their documents — e.g. a 13D co-filer naming another fund — which
produced false matches (Abrams Capital -> Knighthead). browse-edgar's company
search matches the FILER's own registered name, and the type=13F-HR filter means
an empty result is authoritative evidence the fund does not file a 13F.

Input: scratchpad/wf_args.json (list of {fund,status,n13f,npos}).
"""
import json, os, re, sqlite3, subprocess, time
from urllib.parse import quote

DB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "cyclepapa.db")
UA = "cyclepapa-research admin@example.com"
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ingest_13f import _norm_name

WF = "/tmp/claude-0/-home-user-cyclepapa/397c23d0-231d-5c3a-866d-8af2219f3cb2/scratchpad/wf_args.json"
OUT = "/tmp/claude-0/-home-user-cyclepapa/397c23d0-231d-5c3a-866d-8af2219f3cb2/scratchpad/cik_resolve.json"

# Generic firm words carry no identity — the matched entity must share every
# DISTINCTIVE (non-generic) token of the fund name, else it's a different firm.
GENERIC = {"capital","management","mgmt","partners","partner","fund","funds",
    "asset","assets","advisors","advisers","advisory","group","holdings","holding",
    "investment","investments","investors","investor","global","value","master",
    "offshore","gp","co","company","cos","the","opportunities","opportunity",
    "lp","llc","ltd","inc","trust","associates"}

def curl(url):
    return subprocess.run(["curl", "-s", "--compressed", "-m", "25", "-A", UA, url],
                          capture_output=True, text=True).stdout

def firm_name(fund):
    """Strip parenthetical manager and trailing noise to get the firm search term."""
    n = re.sub(r"\(.*?\)", "", fund)
    n = re.sub(r"\s{2,}.*$", "", n)   # our names sometimes append "  Manager"
    return n.strip()

def search_term(name):
    """browse-edgar prefix-matches the company field, so a SHORTER prefix returns
    a superset of candidates (better recall); name-matching filters afterwards.
    Use the first two meaningful words."""
    toks = [t for t in re.split(r"\s+", name.strip()) if t]
    return " ".join(toks[:2]) if toks else name

def edgar_company_search(term, form="13F-HR"):
    """Return [(cik, last_date)] of filers whose name prefix-matches `term` and
    who file `form`. Empty list => no such filer (authoritative for 13F-HR)."""
    url = (f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany"
           f"&company={quote(term)}&type={quote(form)}&dateb=&owner=include"
           f"&count=40&output=atom")
    body = curl(url)
    out = []
    # MULTI-match: one <entry> per company, each with a <cik>+<last-date>.
    entries = re.findall(r"<entry[^>]*>.*?</entry>", body, re.S)
    for entry in entries:
        m = re.search(r"<cik>(\d{10})</cik>", entry)
        if not m:
            continue
        d = re.search(r"<last-date>(\d{4}-\d\d-\d\d)</last-date>", entry)
        out.append((m.group(1), d.group(1) if d else ""))
    # SINGLE exact match: browse-edgar returns one top-level <company-info>
    # (no <entry> wrapper) — grab the CIK directly so we don't miss it.
    if not out:
        seen = set()
        for m in re.finditer(r"<cik>(\d{10})</cik>", body):
            if m.group(1) not in seen:
                seen.add(m.group(1))
                out.append((m.group(1), ""))
    return out

def submissions_info(cik):
    """Authoritative (name, n_13f_hr, latest_13f_date) from the submissions API.
    latest_13f_date is the most recent 13F-HR filing date (or '') — the key
    signal for picking the ACTIVE filer entity when a manager has migrated CIKs
    (e.g. Greenlight Capital -> DME Capital, Appaloosa Mgmt -> Appaloosa LP)."""
    body = curl(f"https://data.sec.gov/submissions/CIK{cik}.json")
    try:
        j = json.loads(body)
        rec = j["filings"]["recent"]
        forms, dates = rec["form"], rec["filingDate"]
    except Exception:
        return None, 0, ""
    n13f = sum(1 for f in forms if f == "13F-HR")
    last = next((d for f, d in zip(forms, dates) if f == "13F-HR"), "")
    return j.get("name", ""), n13f, last

def resolve(name):
    """Resolve the best 13F-HR filer for a manager name.
    Returns (cik, authoritative_name, files13f). Prefers the most RECENTLY active
    filer so CIK migrations don't leave us on a dormant entity."""
    want = set(_norm_name(name).split())
    if not want:
        return None, None, False
    distinct = want - GENERIC
    cands = edgar_company_search(search_term(name))
    if not cands:
        return None, None, False
    scored = []
    for cik, last_date in cands[:10]:
        ent, n13f, last13f = submissions_info(cik)
        time.sleep(0.12)
        if n13f <= 0:
            continue
        have = set(_norm_name(ent).split())
        if not have:
            continue
        # require every distinctive token present; if the name is all-generic,
        # demand a near-exact full-token match instead.
        overlap = len(want & have) / len(want)
        if distinct:
            if not distinct.issubset(have):
                continue
        elif overlap < 0.85:
            continue
        # RECENCY FIRST: the active entity wins over a dormant one with more
        # history; then name overlap; then filing count.
        scored.append((last13f, round(overlap, 3), n13f, cik, ent))
    if not scored:
        return None, None, False
    scored.sort(reverse=True)
    last13f, overlap, n13f, cik, ent = scored[0]
    return cik, ent, True

def run(limit=None, test_only=False):
    work = json.load(open(WF))
    if limit:
        work = work[:limit]
    conn = None if test_only else sqlite3.connect(DB)
    if conn:
        conn.execute("PRAGMA busy_timeout=30000")
    matched = []; nomatch = []
    for i, w in enumerate(work):
        fund = w["fund"]
        if w.get("n13f", 0) >= 5:    # already covered
            continue
        name = firm_name(fund)
        try:
            cik, ent, files13f = resolve(name)
        except Exception as e:
            print(f"  ! {fund[:38]}  ERROR {e}")
            nomatch.append(fund); continue
        time.sleep(0.2)
        if cik and files13f:
            matched.append((fund, cik, ent))
            print(f"  ✓ {fund[:38]:<38} CIK {cik}  ({ent[:34]})")
            if conn:
                row = conn.execute("SELECT 1 FROM fund_resolution_state WHERE fund=?", (fund,)).fetchone()
                if row is None:
                    conn.execute("INSERT INTO fund_resolution_state (fund,best_cik,status) VALUES (?,?,?)",
                                 (fund, cik, "edgar_13f_resolved"))
                else:
                    conn.execute("""UPDATE fund_resolution_state SET best_cik=?,
                        status=COALESCE(NULLIF(status,''),'edgar_13f_resolved') WHERE fund=?""",
                        (cik, fund))
        else:
            nomatch.append(fund)
            print(f"    · {fund[:38]:<38} no 13F-HR filer")
        if conn and i % 20 == 0:
            conn.commit()
    if conn:
        conn.commit()
    print(f"\nresolved {len(matched)} new 13F filers; {len(nomatch)} no US 13F match")
    json.dump({"matched": matched, "nomatch": nomatch}, open(OUT, "w"))
    return matched, nomatch

if __name__ == "__main__":
    test = "--test" in sys.argv
    lim = None
    for a in sys.argv[1:]:
        if a.isdigit():
            lim = int(a)
    run(limit=lim, test_only=test)
