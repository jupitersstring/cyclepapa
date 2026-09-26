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

def normalize_cusip_case(conn):
    """CUSIPs are case-insensitive, but some filers (Ancora, Gardner Russo,
    RiverPark...) write them lowercase. Stored as-is, one security splits into
    two rows (RiverPark's TSLA as 561 + 90 shares) and lowercase lines miss the
    upper-case cusip_map entry (471 Ancora holdings had no ticker). Ingest now
    upper-cases; this repairs rows stored before that. Case-twins inside one
    filing are merged (value, shares, weight summed), as ingest aggregates."""
    n = 0
    for t, key in (("fund_13f_holdings", ("fund", "accession")),
                   ("fund_13f_prior", ("fund", "accession")),
                   ("broker_13f", ("broker", "accession"))):
        cols = {r[1] for r in conn.execute(f"PRAGMA table_info({t})")}
        if not cols:
            continue
        for row in conn.execute(f"""SELECT rowid, {key[0]}, {key[1]}, cusip, value_k, shares
                                    FROM {t} WHERE cusip <> UPPER(cusip)""").fetchall():
            rid, k0, k1, cu, v, sh = row
            twin = conn.execute(f"SELECT rowid FROM {t} WHERE {key[0]}=? AND {key[1]}=? AND cusip=?",
                                (k0, k1, cu.upper())).fetchone()
            if twin:
                extra = (", pct_book = COALESCE(pct_book, 0) + COALESCE((SELECT pct_book FROM "
                         f"{t} WHERE rowid={rid}), 0)") if "pct_book" in cols else ""
                conn.execute(f"UPDATE {t} SET value_k = COALESCE(value_k, 0) + ?, "
                             f"shares = COALESCE(shares, 0) + ?{extra} WHERE rowid = ?",
                             (v or 0, sh or 0, twin[0]))
                conn.execute(f"DELETE FROM {t} WHERE rowid = ?", (rid,))
            else:
                conn.execute(f"UPDATE {t} SET cusip = ? WHERE rowid = ?", (cu.upper(), rid))
            n += 1
    for t in ("holding_sec_form", "cusip_map"):
        # keep the upper-case twin (cusip_map: it carries the vetted mapping)
        conn.execute(f"""DELETE FROM {t} WHERE cusip <> UPPER(cusip) AND EXISTS
            (SELECT 1 FROM {t} b WHERE b.cusip = UPPER({t}.cusip)
             {'AND b.accession = ' + t + '.accession' if t == 'holding_sec_form' else ''})""")
        n += conn.execute(f"UPDATE {t} SET cusip = UPPER(cusip) WHERE cusip <> UPPER(cusip)").rowcount
    conn.commit()
    return n

def is_debt_cusip(cusip):
    """Issue code (chars 7-8) with a letter = a debt security (notes, converts)."""
    return bool(cusip) and len(cusip) == 9 and not cusip[6:8].isdigit()

def debt_ticker(tkr, cusip):
    """A bond line keeps its issuer's ticker but must never pool with the stock:
    'WDC' on Western Digital's 958102AT2 notes becomes 'WDC (note)' (the space
    also makes unified_score class it a note). Convert-arb books otherwise
    counted as equity holders (EchoStar, Celcuity, Dexcom notes filed as 'SH')."""
    if tkr and is_debt_cusip(cusip) and " " not in tkr:
        return f"{tkr} (note)"
    return tkr

def tag_debt_lines(conn):
    n = 0
    for t in ("fund_13f_holdings", "fund_13f_prior", "broker_13f"):
        n += conn.execute(f"""UPDATE {t} SET ticker = ticker || ' (note)'
            WHERE ticker IS NOT NULL AND instr(ticker, ' ') = 0 AND length(cusip) = 9
              AND NOT (substr(cusip,7,1) BETWEEN '0' AND '9' AND substr(cusip,8,1) BETWEEN '0' AND '9')""").rowcount
    conn.commit()
    return n

def upsert(conn, cusip, ticker, sec_type, source, asof):
    cusip = (cusip or "").upper()
    if not _valid_cusip(cusip) or not _valid_ticker(ticker):
        return
    # Never let a lower-authority source overwrite an OpenFIGI/FMP/curated mapping.
    prior = conn.execute("SELECT source FROM cusip_map WHERE cusip=?", (cusip,)).fetchone()
    RANK = {"curated": 3, "openfigi": 2, "fmp": 2, "fmp-name": 1.5, "name": 1, "sec": 1}
    if prior and RANK.get(prior[0], 0) > RANK.get(source, 0):
        return
    conn.execute("""INSERT INTO cusip_map VALUES (?,?,?,?,?)
        ON CONFLICT(cusip) DO UPDATE SET ticker=excluded.ticker, sec_type=excluded.sec_type,
            source=excluded.source, asof=excluded.asof""",
        (cusip, ticker, sec_type, source, asof))

def run(figi_files=None):
    conn = sqlite3.connect(DB); conn.execute("PRAGMA busy_timeout=30000")
    init(conn)
    n_case = normalize_cusip_case(conn)
    if n_case:
        print(f"normalized {n_case} lowercase CUSIP rows to upper case")
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
    #    Never an option CUSIP: a "PUT" line filed under its own CUSIP carries the
    #    stock's issuer name, and consensus once mapped Funicular's MU puts to MU.
    for cusip, tk, n in conn.execute("""SELECT h.cusip, h.ticker, COUNT(*) FROM fund_13f_holdings h
            WHERE h.ticker IS NOT NULL AND h.cusip IS NOT NULL
              AND NOT EXISTS (SELECT 1 FROM holding_sec_form f WHERE f.cusip = h.cusip
                              AND f.accession = h.accession AND f.sec_form = 'option')
            GROUP BY h.cusip HAVING COUNT(DISTINCT h.ticker)=1"""):
        if conn.execute("SELECT 1 FROM cusip_map WHERE cusip=?", (cusip,)).fetchone():
            continue
        upsert(conn, cusip, tk, "common", "name", asof); n_hold += 1

    conn.commit()
    total = conn.execute("SELECT COUNT(*) FROM cusip_map").fetchone()[0]
    mapped = conn.execute("SELECT COUNT(*) FROM cusip_map WHERE ticker IS NOT NULL").fetchone()[0]
    print(f"cusip_map: {total} cusips ({mapped} -> ticker, {total-mapped} known-unmappable); "
          f"+{n_figi} from OpenFIGI, +{n_hold} from holdings consensus")

    # 3. Back-apply to any holdings still NULL where cusip_map now knows the answer.
    #    Common stock only: FMP-resolved ETF/fund rows carry the fund's ticker in
    #    cusip_map, but funds stay off the holdings so they never score as picks.
    applied = 0
    for t in ("fund_13f_holdings", "fund_13f_prior", "broker_13f"):
        applied += conn.execute(f"""UPDATE {t}
            SET ticker=(SELECT ticker FROM cusip_map WHERE cusip={t}.cusip)
            WHERE ticker IS NULL AND cusip IN (SELECT cusip FROM cusip_map
                WHERE ticker IS NOT NULL AND sec_type = 'common')""").rowcount
    conn.commit()
    print(f"back-applied cusip_map to {applied} previously-unmapped holdings")
    # 3b. ...and OVERWRITE a disagreeing ticker where the authority is proven
    #     (curated / OpenFIGI / FMP), not only NULLs: a name-matched line keeps
    #     whatever the SEC name file said when it was ingested, and "ALPHABET
    #     INC" on the class-C CUSIP had become GOOGL on some books and GOOGN
    #     (the 2026 convertible preferred) on others. Equity CUSIPs only — debt
    #     lines carry their "<ticker> (note)" tag.
    fixed = 0
    for t in ("fund_13f_holdings", "fund_13f_prior", "broker_13f"):
        fixed += conn.execute(f"""UPDATE {t}
            SET ticker=(SELECT ticker FROM cusip_map WHERE cusip={t}.cusip)
            WHERE ticker IS NOT NULL
              AND substr(cusip,7,1) BETWEEN '0' AND '9' AND substr(cusip,8,1) BETWEEN '0' AND '9'
              AND EXISTS (SELECT 1 FROM cusip_map m WHERE m.cusip={t}.cusip AND m.ticker IS NOT NULL
                          AND m.sec_type = 'common' AND m.ticker != {t}.ticker
                          AND m.source IN ('curated', 'openfigi', 'fmp', 'fmp-name'))""").rowcount
    conn.commit()
    print(f"corrected {fixed} holdings whose ticker disagreed with a proven CUSIP mapping")
    print(f"tagged {tag_debt_lines(conn)} bond lines '(note)' so they never pool with the stock")
    conn.close()

if __name__ == "__main__":
    base = "/tmp/claude-0/-home-user-cyclepapa/397c23d0-231d-5c3a-866d-8af2219f3cb2/scratchpad"
    run(figi_files=[f"{base}/figi.json", f"{base}/recover.json"])
