"""Discover high-conviction 13F filers we don't track — screened with FMP.

The roster (ingest_13f.FUND_CIK) was built by hand. This scans EVERY filer of
the latest 13F quarter through FMP's holder analytics and surfaces books that
look like the roster's mandate — concentrated, patient, big swings — and that
have beaten the market over years, not quarters:

  * concentrated:  3-60 positions
  * sized:         $30M-$40B of 13F assets (not a fund-of-accounts giant)
  * patient:       top-10 positions held >= 4 quarters on average
  * proven:        5-year holdings return beats the S&P 500 by >= 25 points
                   (3-year by >= 15 as the fallback for younger books)

Business-model filter (the user's rule: no asset gatherers, no diversified
quants): names carrying wealth-management / bank / trust-company / pension /
insurance / index / quant tokens are dropped before any API call; the
survivors still get a human read before joining the roster.

FMP's performance figures are holdings-based estimates from 13F snapshots
(they miss intra-quarter trading, shorts, cash) — a screen, not a record.
Output: table fund_discovery (one row per surviving filer) + printed shortlist.
"""
import json, os, re, sqlite3, subprocess, sys, time
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from enrich_fmp import API, CACHE, DB, api_key

PERF_CACHE = os.path.join(CACHE, "holder_perf")
GATHERER = re.compile(
    r"WEALTH|FINANCIAL PLANN|PLANNING|RETIREMENT|PENSION|INSURANCE|ASSURANCE|\bBANK|BANCORP|"
    r"TRUST CO|TRUST COMPANY|\bN\.?A\.?$|SECURITIES|BROKER|INDEX|\bETF|QUANT|SYSTEMATIC|"
    r"ALGORITHM|FAMILY WEALTH|PRIVATE CLIENT|CLIENT|UNIVERSITY|COLLEGE|ENDOWMENT|STATE OF|"
    r"TEACHERS|EMPLOYEES|MUNICIPAL|COUNTY|COMMONWEALTH|VANGUARD|BLACKROCK|STATE STREET|FIDELITY|"
    r"SCHWAB|MORGAN STANLEY|GOLDMAN|JPMORGAN|MERRILL|UBS|CREDIT SUISSE|DEUTSCHE|BARCLAYS|NOMURA|"
    r"RAYMOND JAMES|AMERIPRISE|EDWARD JONES|LPL|STIFEL|CAPITAL GROUP|INVESCO|FRANKLIN|T\. ROWE|"
    r"NORTHERN TRUST|WELLS FARGO|CITIGROUP|HSBC|ROYAL BANK|TORONTO|NATIXIS|AMUNDI|ALLIANZ|NUVEEN|"
    r"ADVISORY SERVICES|INVESTMENT SERVICES|FINANCIAL SERVICES|FINANCIAL GROUP|FINANCIAL ADVIS|"
    r"PORTFOLIO MANAGEMENT SERVICES|ASSET MANAGEMENT SERVICES|TAX|CPA|INSTITUTIONAL|RIA\b", re.I)

def _get(path, **p):
    q = "&".join(f"{k}={v}" for k, v in p.items())
    url = f"{API}/{path}?{q}&apikey={api_key()}"
    for attempt in range(6):
        r = subprocess.run(["curl", "-sS", "--max-time", "90", url], capture_output=True, text=True)
        body = r.stdout
        if "Limit Reach" in body:
            time.sleep(20 * (attempt + 1))            # rolling window: wait it out
            continue
        try:
            d = json.loads(body)
            if isinstance(d, list):
                return d
        except ValueError:
            pass
        time.sleep(3 * (attempt + 1))
    return None

def filer_universe(quarter_end):
    """Every 13F-HR filer for the quarter, from FMP's latest-filings feed."""
    seen = {}
    for page in range(0, 400):
        d = _get("institutional-ownership/latest", page=page, limit=100)
        if not d:
            break
        for x in d:
            if (x.get("date") or "")[:10] == quarter_end and (x.get("formType") or "").startswith("13F-HR"):
                seen.setdefault(x["cik"].lstrip("0"), x.get("name") or "")
        if max((x.get("filingDate") or "")[:10] for x in d) < quarter_end:
            break                                     # past the quarter's filing window
    return seen

def perf(cik):
    os.makedirs(PERF_CACHE, exist_ok=True)
    path = os.path.join(PERF_CACHE, f"{cik}.json")
    if os.path.exists(path) and time.time() - os.path.getmtime(path) < 7 * 86400:
        return json.load(open(path))
    d = _get("institutional-ownership/holder-performance-summary", cik=cik.zfill(10), page=0)
    if d is not None:
        json.dump(d[:1], open(path, "w"))             # latest quarter is all we use
        return d[:1]
    return None

def run(quarter_end="2026-06-30"):
    conn = sqlite3.connect(DB, timeout=120)
    conn.execute("PRAGMA busy_timeout=120000")
    import ingest_13f
    roster = {str(c).lstrip("0") for c in ingest_13f.FUND_CIK.values() if c}
    roster |= {str(r[0]).lstrip("0") for r in conn.execute("SELECT DISTINCT cik FROM fund_13f_holdings") if r[0]}
    filers = filer_universe(quarter_end)
    # keep the full filer list: later name lookups (saved-search investor lists,
    # people screens) resolve firms to 13F CIKs against it without re-fetching
    conn.executescript("""CREATE TABLE IF NOT EXISTS filer_universe (
        cik TEXT, name TEXT, quarter_end TEXT, PRIMARY KEY (cik, quarter_end));""")
    conn.executemany("INSERT OR REPLACE INTO filer_universe VALUES (?,?,?)",
                     [(c, n, quarter_end) for c, n in filers.items()])
    conn.commit()
    todo = {c: n for c, n in filers.items() if c not in roster and not GATHERER.search(n)}
    print(f"{len(filers):,} filers for {quarter_end}; {len(roster):,} on the roster; "
          f"{len(filers) - len(todo) - len(roster & set(filers)):,} dropped as asset gatherers / banks / "
          f"pensions / index / quant by name; scanning {len(todo):,}", flush=True)
    with ThreadPoolExecutor(3) as ex:
        res = dict(zip(todo, ex.map(perf, todo)))
    rows = []
    for cik, d in res.items():
        if not d:
            continue
        x = d[0]
        n, mv = x.get("portfolioSize") or 0, (x.get("marketValue") or 0) / 1e6
        hold10 = x.get("averageHoldingPeriodTop10") or 0
        rel5, rel3 = x.get("performance5yearRelativeToSP500Percentage"), x.get("performance3yearRelativeToSP500Percentage")
        if not (3 <= n <= 60 and 30 <= mv <= 40000 and hold10 >= 4):
            continue
        if not ((rel5 is not None and rel5 >= 25) or (rel5 is None and rel3 is not None and rel3 >= 15)):
            continue
        rows.append((cik, todo[cik], x.get("date"), n, round(mv, 1), hold10, x.get("turnover"),
                     x.get("performancePercentage1year"), x.get("performancePercentage3year"),
                     x.get("performancePercentage5year"), rel3, rel5))
    conn.executescript("""DROP TABLE IF EXISTS fund_discovery;
        CREATE TABLE fund_discovery (cik TEXT PRIMARY KEY, name TEXT, asof TEXT, positions INTEGER,
          mv_m REAL, hold_top10_q REAL, turnover REAL, ret_1y REAL, ret_3y REAL, ret_5y REAL,
          rel_sp_3y REAL, rel_sp_5y REAL, reviewed TEXT);""")
    conn.executemany("INSERT INTO fund_discovery VALUES (?,?,?,?,?,?,?,?,?,?,?,?,NULL)", rows)
    conn.commit()
    got = sum(1 for d in res.values() if d)
    print(f"analytics for {got:,} of {len(todo):,}; {len(rows)} pass the screen")
    for r in sorted(rows, key=lambda r: -(r[11] if r[11] is not None else r[10] or 0))[:60]:
        print(f"  {r[1][:44]:44s} cik {r[0]:>8s}  {r[3]:3d} pos  ${r[4]:>8,.0f}M  top10 held {r[5]:.0f}q  "
              f"5y {r[9] or 0:+.0f}% (vs S&P {r[11] if r[11] is not None else float('nan'):+.0f}pp)  3y {r[8] or 0:+.0f}%")
    conn.close()

if __name__ == "__main__":
    run(*sys.argv[1:])
