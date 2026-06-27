"""Fetch business descriptions (name / sector / industry / short summary) from
Yahoo Finance for every ticker in the universe.

yfinance's .info already returns longBusinessSummary, longName, sector, and
industry — the original valuation pass (enrich_yfinance.py) called .info but
only stored the numeric fields. This pass back-fills the descriptive fields
into ticker_yf so the workbooks can show, for each name, WHAT THE COMPANY DOES.

Storage: business_summary is truncated to ~500 chars (a "short summary"), which
keeps the committed snapshot small while preserving the essential description.

Proxy handling is identical to enrich_yfinance.py (CA bundle + cookie warmup).
"""
import os, sqlite3, sys, time

DB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "cyclepapa.db")
CA = "/root/.ccr/ca-bundle.crt"
os.environ.setdefault("REQUESTS_CA_BUNDLE", CA)
os.environ.setdefault("SSL_CERT_FILE", CA)

import requests
import yfinance as yf

def make_session():
    s = requests.Session()
    s.verify = CA
    proxy = os.environ.get("https_proxy") or os.environ.get("HTTPS_PROXY")
    if proxy:
        s.proxies = {"https": proxy, "http": proxy}
    s.headers.update({"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"})
    try:
        s.get("https://finance.yahoo.com", timeout=12)
    except Exception:
        pass
    return s

def add_columns(conn):
    cols = {r[1] for r in conn.execute("PRAGMA table_info(ticker_yf)")}
    if "business_summary" not in cols:
        conn.execute("ALTER TABLE ticker_yf ADD COLUMN business_summary TEXT")
    if "long_name" not in cols:
        conn.execute("ALTER TABLE ticker_yf ADD COLUMN long_name TEXT")
    conn.commit()

def short(summary, limit=500):
    """Truncate a long business summary to ~limit chars on a sentence boundary."""
    if not summary:
        return None
    s = summary.strip().replace("\n", " ")
    if len(s) <= limit:
        return s
    cut = s[:limit]
    # back up to the last sentence end for a clean stop
    dot = cut.rfind(". ")
    if dot > limit * 0.5:
        return cut[:dot + 1]
    return cut.rstrip() + "…"

def fetch_profile(tkr, session):
    try:
        info = yf.Ticker(tkr, session=session).info
    except Exception:
        return None
    if not info:
        return None
    summ = info.get("longBusinessSummary")
    name = info.get("longName") or info.get("shortName")
    sector = info.get("sector")
    industry = info.get("industry")
    if not any((summ, name, sector, industry)):
        return None
    return {
        "summary": short(summ),
        "name": name,
        "sector": sector,
        "industry": industry,
    }

def run(max_n=8000, rps=3.0, refetch=False):
    conn = sqlite3.connect(DB)
    add_columns(conn)
    have = set()
    if not refetch:
        have = {r[0] for r in conn.execute(
            "SELECT ticker FROM ticker_yf WHERE business_summary IS NOT NULL AND business_summary != ''")}
    targets = [r[0] for r in conn.execute(
        "SELECT ticker FROM unified_signal ORDER BY score DESC")]
    todo = [t for t in targets if t not in have][:max_n]
    print(f"summary enrich: {len(todo)} tickers (skip {len(have)} done), ~{rps} req/s")

    session = make_session()
    asof = time.strftime("%Y-%m-%d")
    interval = 1.0 / rps
    n_ok = n_summ = n_fail = 0
    last = time.time() - interval
    for i, tkr in enumerate(todo):
        wait = max(0, last + interval - time.time())
        if wait > 0:
            time.sleep(wait)
        last = time.time()
        res = fetch_profile(tkr, session)
        if not res:
            n_fail += 1
            if n_fail % 25 == 0:
                session = make_session()
            continue
        # ensure a row exists, then update descriptive fields without clobbering valuation
        conn.execute("INSERT OR IGNORE INTO ticker_yf (ticker, asof) VALUES (?,?)", (tkr, asof))
        conn.execute("""UPDATE ticker_yf SET
                business_summary = ?,
                long_name = COALESCE(?, long_name),
                sector   = COALESCE(?, sector),
                industry = COALESCE(?, industry)
            WHERE ticker = ?""",
            (res["summary"], res["name"], res["sector"], res["industry"], tkr))
        n_ok += 1
        if res["summary"]:
            n_summ += 1
        if i % 50 == 0 and i > 0:
            conn.commit()
            print(f"  [{i}/{len(todo)}] {tkr} ok={n_ok} summ={n_summ} fail={n_fail}")
    conn.commit()
    print(f"\ndone: {n_ok} profiles ({n_summ} with summary), {n_fail} failed")

if __name__ == "__main__":
    max_n = int(sys.argv[1]) if sys.argv[1:] else 8000
    run(max_n=max_n)
