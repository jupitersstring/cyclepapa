"""N-PORT-P holdings — the WHOLE book of registered funds, foreign listings included.

A 13F lists only US-listed securities, so for a global manager it shows the US
slice of the book and none of its Tokyo, London, Paris or Seoul positions.
Registered funds file Form N-PORT-P listing EVERY holding with its ISIN and
country, and each fiscal-quarter-end filing is public (~60 days after). This
reads the latest public N-PORT of each series below — the international /
global funds of managers already on the 13F roster, plus a few marquee
single-manager funds kept for their monthly freshness — keeps the long equity
positions, and maps each to a ticker: the CUSIP authority for US lines, then
the ISIN against FMP's global profile file, preferring the home listing that
trades in the holding's currency over an OTC line.

Stored SEPARATELY in nport_holdings (registered-fund data, not 13F) and never
counted as 13F smart money. Feeds the N-PORT sheets (Funds, Holdings, Changes,
Global Consensus).
Unmapped lines are kept (ticker NULL, ISIN and issuer shown), never dropped.
"""
import csv, os, re, sqlite3, sys, time
import xml.etree.ElementTree as ET
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ingest_13f as m

DB = m.DB
PROFILE = os.path.join(os.path.dirname(DB), "fmp_cache", "profile_bulk.csv")

# (series id, roster fund-name prefix or None, label). Series ids from SEC's
# company_tickers_mf.json (share-class ticker -> registrant + series).
SERIES = [
    # global / international books of roster managers (13F shows their US slice only)
    ("S000002762", "Harris Associates", "Oakmark International"),
    ("S000013607", "Harris Associates", "Oakmark Global Select"),
    ("S000002763", "Harris Associates", "Oakmark International Small Cap"),
    ("S000038187", "Southeastern Asset", "Longleaf Partners Global"),
    ("S000009311", "Southeastern Asset", "Longleaf Partners Fund"),
    ("S000001302", "Tweedy, Browne", "Tweedy, Browne International Value"),
    ("S000018426", "Tweedy, Browne", "Tweedy, Browne Worldwide High Dividend Yield Value"),
    ("S000011211", "First Eagle", "First Eagle Global"),
    ("S000011212", "First Eagle", "First Eagle Overseas"),
    ("S000011214", "First Eagle", "First Eagle Gold"),
    ("S000042718", "Kopernik", "Kopernik Global All-Cap"),
    ("S000011203", "Dodge and Cox", "Dodge & Cox International Stock"),
    ("S000022057", "Dodge and Cox", "Dodge & Cox Global Stock"),
    ("S000069725", "Dodge and Cox", "Dodge & Cox Emerging Markets Stock"),
    ("S000084885", "Brandes", "Brandes International Equity"),
    ("S000084889", "Brandes", "Brandes Emerging Markets Value"),
    # (Pzena International Value / International Small Cap: no public N-PORT-P)
    ("S000044708", "Pzena", "Pzena Emerging Markets Value"),
    ("S000056022", "Polen", "Polen International Growth"),
    ("S000047882", "Polen", "Polen Global Growth"),
    ("S000012764", "Baillie Gifford", "Baillie Gifford International Growth"),
    ("S000046079", "Baillie Gifford", "Baillie Gifford Long Term Global Growth"),
    ("S000014591", "Davis Selected", "Davis International"),
    ("S000003441", "Davis Selected", "Davis Global"),
    ("S000030672", "Royce", "Royce International Premier"),
    ("S000035291", "Ariel", "Ariel International"),
    ("S000035292", "Ariel", "Ariel Global"),
    ("S000009495", "FPA Crescent", "FPA Crescent"),
    ("S000001464", "Third Avenue", "Third Avenue Value"),
    # marquee single-manager funds (monthly freshness vs the quarterly 13F)
    ("S000012155", "Sequoia Fund", "Sequoia Fund"),
    ("S000003439", "Davis Selected", "Davis New York Venture"),
    ("S000005540", "PRIMECAP Management", "PRIMECAP Odyssey Growth"),
    ("S000005541", "PRIMECAP Management", "PRIMECAP Odyssey Aggressive Growth"),
    ("S000005539", "PRIMECAP Management", "PRIMECAP Odyssey Stock"),
    ("S000000588", "Baron Capital", "Baron Partners"),
    ("S000022521", "Baron Capital", "Baron Focused Growth"),
    ("S000036767", "Baron Capital", "Baron Global Advantage"),
]

# ISINs a filer still reports after the issuer re-domiciled (FMP carries only
# the new one): verified by hand
ISIN_ALIAS = {
    "CH0102993182": "TEL",   # TE Connectivity: Swiss ISIN, re-domiciled to Ireland in 2024
    "SG9999014716": "WVE",   # Wave Life Sciences (Singapore-incorporated, Nasdaq)
}

_CCY = {"GBP": "GBP", "GBX": "GBP", "ZAC": "ZAR", "ILA": "ILS"}
_OTC = {"OTC", "PNK", "OTCMKTS", "OTCQX", "OTCQB", "GREY"}

def _ccy(c):
    c = (c or "").strip()
    return _CCY.get(c.upper(), c.upper()) if c != "GBp" else "GBP"

def isin_index():
    """ISIN -> [FMP profile rows], from the bulk profile file enrich_fmp caches."""
    csv.field_size_limit(10 ** 9)
    idx = {}
    with open(PROFILE, newline="") as f:
        for r in csv.DictReader(f):
            if r.get("isin"):
                idx.setdefault(r["isin"].strip().upper(), []).append(r)
    return idx

_SUFFIX = {"co", "ltd", "limited", "inc", "corp", "corporation", "company", "plc", "sa", "ag", "se", "nv",
           "spa", "ab", "asa", "oyj", "as", "kgaa", "the", "sab", "de", "cv", "tbk", "pt", "pcl", "bhd",
           "berhad", "publ", "adr", "ads", "sponsored", "unsponsored", "holding", "holdings", "group"}

def norm_company(name):
    """'Taiwan Semiconductor Manufacturing Company Limited' and its ADR's
    profile name collide; suffixes and punctuation don't count."""
    import unicodedata
    n = unicodedata.normalize("NFKD", name or "").encode("ascii", "ignore").decode().lower()
    return " ".join(t for t in re.split(r"[^a-z0-9]+", n) if t and t not in _SUFFIX)

def build_adr_links(conn):
    """adr_link(ordinary, adr): a non-US listing's US line (ADR or direct
    listing), by identical normalised company name. Only an unambiguous match
    is kept (an exchange-listed line is preferred over an OTC one)."""
    csv.field_size_limit(10 ** 9)
    adrs = {}
    with open(PROFILE, newline="") as f:
        for r in csv.DictReader(f):
            # a non-US company's US-dollar line on a US venue: an ADR (TSM, DEO)
            # or a direct listing (SHOP). FMP's isAdr flag misses many (SAP)
            # and marks Canadian depositary receipts (NSTL.TO): not used.
            if ("." not in r["symbol"] and (r.get("currency") or "") == "USD"
                    and (r.get("country") or "US") != "US"
                    and str(r.get("isActivelyTrading", "")).lower() == "true"
                    and str(r.get("isEtf", "")).lower() != "true" and str(r.get("isFund", "")).lower() != "true"):
                adrs.setdefault(norm_company(r.get("companyName")), []).append(
                    (r["symbol"], (r.get("exchange") or "").upper() not in _OTC))
    targets = {t: n for t, n in conn.execute("""SELECT DISTINCT n.ticker, COALESCE(y.long_name, n.issuer)
        FROM nport_holdings n LEFT JOIN ticker_yf y ON y.ticker = n.ticker
        WHERE n.ticker IS NOT NULL AND n.country != 'US'""")}
    try:
        targets.update({t: n for t, n in conn.execute("""SELECT u.ticker, COALESCE(y.long_name, u.name)
            FROM unified_signal u LEFT JOIN ticker_yf y ON y.ticker = u.ticker
            WHERE u.is_us = 0 AND u.sec_type = 'common'""") if t not in targets})
    except sqlite3.OperationalError:
        pass
    links = []
    for tk, name in targets.items():
        cands = adrs.get(norm_company(name)) or []
        listed = [s for s, is_listed in cands if is_listed and s != tk]
        pick = listed if listed else [s for s, _ in cands if s != tk]
        if len(pick) == 1:
            links.append((tk, pick[0]))
    conn.executescript("DROP TABLE IF EXISTS adr_link; CREATE TABLE adr_link (ordinary TEXT PRIMARY KEY, adr TEXT);")
    conn.executemany("INSERT INTO adr_link VALUES (?,?)", links)
    conn.commit()
    return len(links), len(targets)

def pick_symbol(rows, cur):
    """The listing a holder's ISIN most plausibly is: actively trading, not
    OTC, quoted in the holding's own currency, then the most liquid."""
    live = [r for r in rows if str(r.get("isActivelyTrading", "")).lower() == "true"] or rows
    def key(r):
        def num(x):
            try:
                return float(x or 0)
            except ValueError:
                return 0.0
        return ((r.get("exchange") or "").upper() not in _OTC,
                _ccy(r.get("currency")) == cur,
                num(r.get("averageVolume")) * num(r.get("price")),
                num(r.get("marketCap")))
    return max(live, key=key)["symbol"] if live else None

def series_filings(series_id):
    """(trust cik, [(accession, filed)] newest first) of a series' public
    N-PORT-Ps, via EDGAR's series-level company browse (a trust like Advisors'
    Inner Circle Fund II files for dozens of unrelated series)."""
    for wait in (0, 10, 30):             # browse-edgar sheds bursts with a bare error page
        time.sleep(wait)
        body = m.curl(f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={series_id}"
                      f"&type=NPORT-P&dateb=&owner=include&count=8&output=atom").decode("utf-8", "ignore")
        if "<feed" in body:
            break
    else:
        return None                      # throttled / failed: NOT "files nothing"
    cik = re.search(r"<cik>(\d+)</cik>", body)
    ents = re.findall(r"<accession-number>([\d-]+)</accession-number>.*?<filing-date>([\d-]+)</filing-date>",
                      body, re.S)
    return (str(int(cik.group(1))) if cik else None), ents

def _t(e, path):
    x = e.find(path)
    return (x.text or "").strip() if x is not None and x.text else ""

def parse(cik, acc):
    """(series name, report date, [long equity positions]) of one N-PORT-P."""
    body = m.curl(f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc.replace('-', '')}/primary_doc.xml")
    try:
        root = m._strip_ns(ET.fromstring(body))
    except ET.ParseError:
        return None
    series = _t(root, ".//genInfo/seriesName")
    period = _t(root, ".//genInfo/repPdDate") or _t(root, ".//genInfo/repPdEnd")
    out = []
    for s in root.iter("invstOrSec"):
        asset = _t(s, "assetCat") or (s.find("assetConditional").get("assetCat")
                                      if s.find("assetConditional") is not None else "")
        if asset != "EC" or _t(s, "payoffProfile") != "Long":
            continue
        ids = s.find("identifiers")
        isin = ids.find("isin").get("value") if ids is not None and ids.find("isin") is not None else ""
        tick = ids.find("ticker").get("value") if ids is not None and ids.find("ticker") is not None else ""
        cur = _t(s, "curCd") or (s.find("currencyConditional").get("curCd")
                                 if s.find("currencyConditional") is not None else "")
        try:
            val = float(_t(s, "valUSD") or 0)
        except ValueError:
            val = 0.0
        if val <= 0:
            continue
        try:
            pct = float(_t(s, "pctVal") or 0)
        except ValueError:
            pct = None
        try:
            bal = float(_t(s, "balance") or 0) if _t(s, "units") == "NS" else None
        except ValueError:
            bal = None
        cusip = _t(s, "cusip").upper()
        out.append({"issuer": (_t(s, "name") or _t(s, "title"))[:80],
                    "cusip": cusip if re.fullmatch(r"[0-9A-Z]{9}", cusip or "") and len(set(cusip)) > 1 else None,
                    "isin": isin.strip().upper() or None, "ticker": tick.strip().upper() or None,
                    "currency": _ccy(cur), "country": _t(s, "invCountry").upper() or None,
                    "val_usd": val, "pct": pct, "shares": bal})
    return series, period, out

def run():
    conn = sqlite3.connect(DB, timeout=120); conn.execute("PRAGMA busy_timeout=120000")
    cols = """trust TEXT, series TEXT, filed TEXT, issuer TEXT, ticker TEXT,
      cusip TEXT, val_usd REAL, pct REAL,
      series_id TEXT, manager TEXT, isin TEXT, country TEXT, currency TEXT,
      shares REAL, period TEXT"""
    # Tables persist across runs and each series is replaced only once its new
    # filing has parsed: a throttled run once rebuilt the table from scratch
    # and silently lost seven funds' books. (A pre-series-id table from the old
    # four-trust ingest is rebuilt once.)
    for t in ("nport_holdings", "nport_prior"):
        have = {r[1] for r in conn.execute(f"PRAGMA table_info({t})")}
        if have and "series_id" not in have:
            conn.execute(f"DROP TABLE {t}")
    conn.executescript(f"""
    CREATE TABLE IF NOT EXISTS nport_holdings ({cols});
    CREATE INDEX IF NOT EXISTS idx_nport_tk ON nport_holdings(ticker);
    CREATE INDEX IF NOT EXISTS idx_nport_series ON nport_holdings(series);
    -- each series' previous public book: what the global managers initiated
    -- and exited since (diffed by ISIN presence, immune to splits)
    CREATE TABLE IF NOT EXISTS nport_prior ({cols});
    """)
    listed = {sid for sid, _, _ in SERIES}
    for t in ("nport_holdings", "nport_prior"):          # series dropped from the list
        conn.execute(f"DELETE FROM {t} WHERE series_id NOT IN ({','.join('?' * len(listed))})", sorted(listed))
    cmap = {c: t for c, t, st in conn.execute("SELECT cusip, ticker, sec_type FROM cusip_map")
            if t and st == "common"}
    roster = [r[0] for r in conn.execute("SELECT fund FROM fund_13f_state ORDER BY last_filed DESC")]
    idx = isin_index()
    failed, no_public = 0, set()
    for sid, prefix, label in SERIES:
        manager = next((f for f in roster if prefix and f.startswith(prefix)), None) or prefix or label
        sf = series_filings(sid)
        if sf is None:
            print(f"  [!] {label}: EDGAR fetch failed — previous book kept, retried next run")
            failed += 1
            continue
        cik, ents = sf
        if not (cik and ents):
            print(f"  [-] {label}: no public N-PORT-P for series {sid}")
            no_public.add(sid)
            conn.execute("DELETE FROM nport_holdings WHERE series_id=?", (sid,))
            conn.execute("DELETE FROM nport_prior WHERE series_id=?", (sid,))
            continue
        acc, filed = ents[0]
        got = parse(cik, acc)
        if got is None:
            print(f"  [!] {label}: {acc} could not be read — previous book kept, retried next run")
            failed += 1
            continue
        series, period, rows = got
        conn.execute("DELETE FROM nport_holdings WHERE series_id=?", (sid,))

        def store(table, rows, filed, period):
            for r in rows:
                tk = cmap.get(r["cusip"]) if r["cusip"] else None
                if not tk and r["isin"] in idx:
                    tk = pick_symbol(idx[r["isin"]], r["currency"])
                if not tk:
                    tk = ISIN_ALIAS.get(r["isin"])
                conn.execute(f"""INSERT INTO {table} (trust, series, filed, issuer, ticker, cusip, val_usd, pct,
                    series_id, manager, isin, country, currency, shares, period) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (manager, series or label, filed, r["issuer"], tk, r["cusip"], r["val_usd"], r["pct"],
                     sid, manager, r["isin"], r["country"], r["currency"], r["shares"], period))
        store("nport_holdings", rows, filed, period)
        # the previous public book: the next filing for an EARLIER period (an
        # amendment of the same period is skipped)
        prior_note = "no earlier public filing"
        for pacc, pfiled in ents[1:]:
            pgot = parse(cik, pacc)
            if pgot is None:
                prior_note = "earlier filing unreadable (previous prior kept)"
                failed += 1
                break
            if pgot[1] and period and pgot[1] < period:
                conn.execute("DELETE FROM nport_prior WHERE series_id=?", (sid,))
                store("nport_prior", pgot[2], pfiled, pgot[1])
                prior_note = f"vs {pgot[1]}"
                break
            time.sleep(0.3)
        foreign = [r for r in rows if r["country"] and r["country"] != "US"]
        fv = sum(r["val_usd"] for r in foreign)
        tv = sum(r["val_usd"] for r in rows) or 1
        print(f"  {(series or label)[:44]:44s} {period or filed}  {len(rows):4d} equities, "
              f"{len(foreign):4d} non-US ({fv / tv:4.0%} of equity value)  [{prior_note}]", flush=True)
        conn.commit()
        time.sleep(1.0)                  # browse-edgar throttles bursts
    tot = conn.execute("""SELECT COUNT(*), COUNT(DISTINCT series_id),
            SUM(CASE WHEN country != 'US' THEN val_usd END),
            SUM(CASE WHEN country != 'US' AND ticker IS NOT NULL THEN val_usd END)
        FROM nport_holdings""").fetchone()
    print(f"DONE: {tot[0]:,} equity positions across {tot[1]} fund series; non-US ${(tot[2] or 0) / 1e9:,.1f}B, "
          f"{(tot[3] or 0) / (tot[2] or 1):.0%} of it mapped to a listing", flush=True)
    print("largest non-US lines FMP has no listing for (kept, ticker blank):")
    for r in conn.execute("""SELECT issuer, isin, country, ROUND(SUM(val_usd)/1e6, 1) v FROM nport_holdings
            WHERE country != 'US' AND ticker IS NULL GROUP BY isin ORDER BY v DESC LIMIT 8"""):
        print(f"    {r[0][:36]:36s} {r[1] or '-':13s} {r[2] or '-':3s} ${r[3]}M")
    n_adr, n_t = build_adr_links(conn)
    print(f"ADR links: {n_adr} of {n_t} non-US listings have a US depositary receipt")
    # a series whose refresh failed keeps its previous book (reported above);
    # only a series with NO book on file fails the run
    have = {r[0] for r in conn.execute("SELECT DISTINCT series_id FROM nport_holdings")}
    missing = [label for sid, _, label in SERIES if sid not in have and sid not in no_public]
    if missing:
        print(f"  ! no book at all for: {', '.join(missing)}")
    elif failed:
        print(f"  ({failed} refreshes failed — previous books kept; re-run to refresh them)")
    conn.close()
    return len(missing)

if __name__ == "__main__":
    sys.exit(2 if run() else 0)
