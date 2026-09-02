"""Persistent CUSIP -> ticker authority (cusip_map).

Name-based mapping silently drops real companies on suffix/abbreviation quirks
(Brookdale "SR LIVING", Jazz's "INVESTMENTS I LTD" financing entity). The robust
fix is CUSIP authority: once a CUSIP is resolved (by OpenFIGI, by SEC file, or by
a confirmed name match), we PERSIST it here and check it FIRST on every future
ingest, so a resolution is never lost and a fund vehicle never re-maps onto an
operating ticker.

Columns: cusip, ticker (NULL = known-unmappable, e.g. a foreign issuer with no US
line), sec_type ('common'|'etf'|'unknown'), source, asof.
"""
import os, sqlite3, json, time

DB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "cyclepapa.db")

def init(conn):
    conn.execute("""CREATE TABLE IF NOT EXISTS cusip_map (
        cusip TEXT PRIMARY KEY, ticker TEXT, sec_type TEXT, source TEXT, asof TEXT)""")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_cusipmap_tk ON cusip_map(ticker)")

def _valid_cusip(c):
    # Placeholder CUSIPs ("000000000", "0") appear in empty 13F filings ("NONE",
    # "No Securities") and on not-yet-assigned issues; the same placeholder is
    # shared across unrelated rows, so it can never serve as an authority key.
    return bool(c) and len(c) == 9 and len(set(c)) > 1

_CCY = ("EUR","GBP","CHF","JPY","SEK","NOK","DKK","HKD","CAD","AUD","USD","PLN",
        "CZK","HUF","MXN","BRL","ZAR","TRY","KRW","TWD","SGD","INR","CNY","CNH",
        "THB","IDR","MYR","PHP","VND","AED","SAR","ILS","NZD")

def _valid_ticker(t):
    # Composite venue tickers ("TRI4EUR", "APLSUSD", "CCL1EUR") leak in from
    # OpenFIGI/Yahoo European listing lines. Persisting one poisons every later
    # ingest of that CUSIP (Woodbridge's $27B TRI stake surfaced as TRI4EUR).
    if t is None:
        return True                      # NULL = known-unmappable, allowed
    return not (len(t) >= 6 and any(t.endswith(x) for x in _CCY))

def upsert(conn, cusip, ticker, sec_type, source, asof):
    if not _valid_cusip(cusip) or not _valid_ticker(ticker):
        return
    # Never let a lower-authority source overwrite an OpenFIGI/curated mapping.
    prior = conn.execute("SELECT source FROM cusip_map WHERE cusip=?", (cusip,)).fetchone()
    RANK = {"curated": 3, "openfigi": 2, "name": 1, "sec": 1}
    if prior and RANK.get(prior[0], 0) > RANK.get(source, 0):
        return
    conn.execute("""INSERT INTO cusip_map VALUES (?,?,?,?,?)
        ON CONFLICT(cusip) DO UPDATE SET ticker=excluded.ticker, sec_type=excluded.sec_type,
            source=excluded.source, asof=excluded.asof""",
        (cusip, ticker, sec_type, source, asof))

def run(figi_files=None):
    conn = sqlite3.connect(DB); conn.execute("PRAGMA busy_timeout=30000")
    init(conn)
    asof = time.strftime("%Y-%m-%d")
    n_figi = n_hold = 0

    # 1. OpenFIGI resolutions (highest automatic authority) from saved runs
    for path in (figi_files or []):
        if not os.path.exists(path):
            continue
        d = json.load(open(path))
        for c, tk in (d.get("resolved") or {}).items():
            upsert(conn, c, tk, "common", "openfigi", asof); n_figi += 1
        for c in (d.get("etf") or []):
            upsert(conn, c, None, "etf", "openfigi", asof); n_figi += 1

    # 2. Consensus from already-mapped holdings: a CUSIP that consistently carries
    #    ONE ticker in the holdings table is a trustworthy name-derived mapping.
    for cusip, tk, n in conn.execute("""SELECT cusip, ticker, COUNT(*) FROM fund_13f_holdings
            WHERE ticker IS NOT NULL AND cusip IS NOT NULL
            GROUP BY cusip HAVING COUNT(DISTINCT ticker)=1"""):
        if conn.execute("SELECT 1 FROM cusip_map WHERE cusip=?", (cusip,)).fetchone():
            continue
        upsert(conn, cusip, tk, "common", "name", asof); n_hold += 1

    conn.commit()
    total = conn.execute("SELECT COUNT(*) FROM cusip_map").fetchone()[0]
    mapped = conn.execute("SELECT COUNT(*) FROM cusip_map WHERE ticker IS NOT NULL").fetchone()[0]
    print(f"cusip_map: {total} cusips ({mapped} -> ticker, {total-mapped} known-unmappable); "
          f"+{n_figi} from OpenFIGI, +{n_hold} from holdings consensus")

    # 3. Back-apply to any holdings still NULL where cusip_map now knows the answer.
    applied = conn.execute("""UPDATE fund_13f_holdings
        SET ticker=(SELECT ticker FROM cusip_map WHERE cusip=fund_13f_holdings.cusip)
        WHERE ticker IS NULL AND cusip IN (SELECT cusip FROM cusip_map WHERE ticker IS NOT NULL)""").rowcount
    conn.commit()
    print(f"back-applied cusip_map to {applied} previously-unmapped holdings")
    conn.close()

if __name__ == "__main__":
    base = "/tmp/claude-0/-home-user-cyclepapa/397c23d0-231d-5c3a-866d-8af2219f3cb2/scratchpad"
    run(figi_files=[f"{base}/figi.json", f"{base}/recover.json"])
