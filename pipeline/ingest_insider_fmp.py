"""Every insider transaction type (FMP's Form 4 feed), last ~100 days.

The SEC Form 4 scan keeps open-market buys and sells (codes P / S) only. The
capital-structure moves that betray a view — exercising options and HOLDING
the stock, converting a preferred or note into common — sit in the other
codes (M exempt exercise, X in-the-money exercise, C conversion) and never
reached the database. FMP's latest-filings feed carries all of them; this
pages it back to the window and stores the raw transactions in insider_fmp.
Read by revealed_preference.py (exercise-and-hold); open-market buys there
still come from the SEC scan, so nothing is counted twice.
"""
import datetime as dt
import json, os, sqlite3, subprocess, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from enrich_fmp import API, CACHE, DB, api_key

WINDOW_DAYS = 100
PAGE_CACHE = os.path.join(CACHE, "insider_latest")

def page(n):
    """One 1,000-row page of the feed, newest first; cached for a day."""
    os.makedirs(PAGE_CACHE, exist_ok=True)
    fn = os.path.join(PAGE_CACHE, f"page_{n:04d}.json")
    if os.path.exists(fn) and time.time() - os.path.getmtime(fn) < 20 * 3600:
        return json.load(open(fn))
    url = f"{API}/insider-trading/latest?page={n}&limit=1000&apikey={api_key()}"
    for attempt in range(5):
        body = subprocess.run(["curl", "-sS", "--max-time", "90", url], capture_output=True, text=True).stdout
        if "Limit Reach" in body:
            time.sleep(20 * (attempt + 1))
            continue
        try:
            d = json.loads(body)
        except ValueError:
            time.sleep(3)
            continue
        if isinstance(d, list):
            json.dump(d, open(fn, "w"))
            return d
        time.sleep(3)
    return None

def _accession(url):
    import re
    m = re.search(r"/(\d{10}-\d{2}-\d{6})-index", url or "") or re.search(r"/(\d{18})/", url or "")
    if not m:
        return None
    a = m.group(1)
    return a if "-" in a else f"{a[:10]}-{a[10:12]}-{a[12:]}"

def _role(owner_type):
    """'officer: Chief Executive Officer' -> 'Chief Executive Officer'; 'director' -> 'Director'."""
    parts = []
    for p in (owner_type or "").split(","):
        p = p.strip()
        if not p:
            continue
        p = p.split(":", 1)[1].strip() if ":" in p else p
        parts.append({"director": "Director", "10 percent owner": "10% Owner"}.get(p.lower(), p))
    return ", ".join(parts)

def merge_open_market(conn):
    """FMP's open-market buys and sells the SEC scan missed, into
    form4_transactions (src='fmp'). In September 2026 the scan held insider
    buying at 178 tickers of the universe over 90 days; FMP's feed had 752.
    Deduplicated on accession + owner + date + shares; a filing the table
    already ties to another ticker is skipped (one accession = one issuer)."""
    cols = {r[1] for r in conn.execute("PRAGMA table_info(form4_transactions)")}
    if "src" not in cols:
        conn.execute("ALTER TABLE form4_transactions ADD COLUMN src TEXT")
    conn.execute("DELETE FROM form4_transactions WHERE src = 'fmp'")   # rebuilt each run
    have = {(a, str(k or "").lstrip("0"), d, round(sh or 0)) for a, k, d, sh in conn.execute(
        "SELECT accession, owner_cik, trans_date, shares FROM form4_transactions")}
    acc_tk = {a: t for a, t in conn.execute("SELECT accession, ticker FROM form4_transactions")}
    universe = {r[0] for r in conn.execute("SELECT ticker FROM ticker_yf")} | \
               {r[0] for r in conn.execute("SELECT ticker FROM unified_signal")}
    add = []
    for sym, url, cik, name, otype, ttype, ad, sh, px, after, td in conn.execute("""SELECT symbol, url,
            reporting_cik, name, owner_type, trans_type, acq_disp, shares, price, owned_after, trans_date
            FROM insider_fmp WHERE trans_type IN ('P-Purchase', 'S-Sale')"""):
        if sym not in universe or not sh or not td:
            continue
        # FMP's feed carries some corrupted fields: the same sanity the SEC
        # scan enforces (validate I2 / I3) keeps them out
        if (px or 0) > 200000 and sym != "BRK-A" or sh > 1e8 or (px is not None and px < 0):
            continue
        code, acq = ("P", 1) if ttype == "P-Purchase" else ("S", 0)
        if (code == "P" and ad != "A") or (code == "S" and ad != "D"):
            continue
        acc = _accession(url)
        if not acc or (acc in acc_tk and acc_tk[acc] != sym):
            continue
        k = (acc, str(cik or "").lstrip("0"), td, round(sh))
        if k in have:
            continue
        have.add(k)
        add.append((acc, sym, name, _role(otype), td, code, sh, px, acq, url, 0, 0,
                    str(cik or "").lstrip("0") or None, after, "fmp"))
    conn.executemany("""INSERT INTO form4_transactions (accession, ticker, owner, role, trans_date, code, shares,
        price, acquired, source_url, swap_involved, planned_10b5, owner_cik, owned_after, src)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", add)
    conn.commit()
    return sum(1 for a in add if a[5] == "P"), sum(1 for a in add if a[5] == "S")

def run():
    cutoff = (dt.date.today() - dt.timedelta(days=WINDOW_DAYS)).isoformat()
    rows, n, failed = [], 0, 0
    while n < 400:
        d = page(n)
        if d is None:
            failed += 1
            break
        if not d:
            break
        rows.extend(d)
        if min((x.get("filingDate") or "9") for x in d) < cutoff:
            break
        n += 1
    conn = sqlite3.connect(DB, timeout=120); conn.execute("PRAGMA busy_timeout=120000")
    conn.executescript("""DROP TABLE IF EXISTS insider_fmp;
        CREATE TABLE insider_fmp (symbol TEXT, filing_date TEXT, trans_date TEXT, reporting_cik TEXT,
          name TEXT, owner_type TEXT, trans_type TEXT, acq_disp TEXT, shares REAL, price REAL,
          owned_after REAL, security_name TEXT, url TEXT);
        CREATE INDEX idx_insfmp_sym ON insider_fmp(symbol);""")
    seen, keep = set(), []
    for x in rows:
        if (x.get("filingDate") or "") < cutoff or not x.get("symbol"):
            continue
        k = (x.get("url"), x.get("reportingCik"), x.get("transactionDate"), x.get("transactionType"),
             x.get("securitiesTransacted"), x.get("securityName"), x.get("acquisitionOrDisposition"))
        if k in seen:
            continue
        seen.add(k)
        keep.append((x["symbol"], x.get("filingDate"), x.get("transactionDate"), x.get("reportingCik"),
                     x.get("reportingName"), x.get("typeOfOwner"), x.get("transactionType"),
                     x.get("acquisitionOrDisposition"), x.get("securitiesTransacted"), x.get("price"),
                     x.get("securitiesOwned"), x.get("securityName"), x.get("url")))
    conn.executemany(f"INSERT INTO insider_fmp VALUES ({','.join('?' * 13)})", keep)
    conn.commit()
    types = conn.execute("SELECT trans_type, COUNT(*) FROM insider_fmp GROUP BY 1 ORDER BY 2 DESC").fetchall()
    print(f"insider_fmp: {len(keep):,} transactions filed since {cutoff} ({n + 1} pages"
          f"{', a page fetch FAILED — window incomplete' if failed else ''}): "
          + ", ".join(f"{t or '?'} {k:,}" for t, k in types[:10]))
    n_p, n_s = merge_open_market(conn)
    print(f"form4_transactions: +{n_p:,} open-market buys and +{n_s:,} sells the SEC scan had missed (src='fmp')")
    conn.close()
    return failed

if __name__ == "__main__":
    sys.exit(2 if run() else 0)
