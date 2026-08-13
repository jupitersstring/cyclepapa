"""Authoritative valuation + mcap from the yfinance package (Yahoo Finance).

Yahoo pre-computes marketCap, enterpriseValue, EV/EBITDA, P/B, P/E etc.
handling dual-class shares, ADRs, and currency correctly — which the raw
SEC-XBRL path struggles with. Crucially Yahoo also covers FOREIGN listings
(.L London, .T Tokyo, .HK, .AX, .TO), so this fills the non-US gap too.

Proxy notes (this environment):
  - yfinance's default curl_cffi backend fails TLS through the agent proxy.
  - Fix: pass a requests.Session pointed at the CA bundle + HTTPS_PROXY,
    and warm up cookies by hitting finance.yahoo.com first. Then .info
    (Yahoo quoteSummary) returns full fundamentals.

Writes to ticker_yf (separate table — additive, authoritative). The
unified_score join prefers ticker_yf values when present, else falls back
to the SEC-derived ticker_valuation / ticker_meta.
"""
import math, os, sqlite3, sys, time, threading

DB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "cyclepapa.db")
CA = "/root/.ccr/ca-bundle.crt"

os.environ.setdefault("REQUESTS_CA_BUNDLE", CA)
os.environ.setdefault("SSL_CERT_FILE", CA)

import requests

_CRUMB = [None]

def make_session():
    """Session with Yahoo's cookie+crumb handshake.

    RCA (2026-07): Yahoo REQUIRES a crumb tied to an A3 cookie on quoteSummary —
    without it every call is 401 "Invalid Crumb", which masqueraded as
    throttling. finance.yahoo.com sets NO cookies here; the working handshake is
    fc.yahoo.com (404 but sets A3) -> /v1/test/getcrumb -> pass crumb= on every
    call. Symbols that still 404 afterwards are genuinely delisted (the 2025-26
    M&A wave: COOP/PBPB/HOLX/CYBR/AL/SEE/ASGN/EXAS...), not fetch failures.
    """
    s = requests.Session()
    s.verify = CA
    proxy = os.environ.get("https_proxy") or os.environ.get("HTTPS_PROXY")
    if proxy:
        s.proxies = {"https": proxy, "http": proxy}
    s.headers.update({"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"})
    try:
        s.get("https://fc.yahoo.com", timeout=10)      # sets the A3 cookie
    except Exception:
        pass
    try:
        c = s.get("https://query1.finance.yahoo.com/v1/test/getcrumb", timeout=15)
        if c.ok and c.text and "<" not in c.text:
            _CRUMB[0] = c.text.strip()
    except Exception:
        pass
    return s

def _raw(node, mod, key):
    v = (node.get(mod) or {}).get(key)
    return v.get("raw") if isinstance(v, dict) else v

def quote_summary_info(tkr, session):
    """Flat info dict via a DIRECT crumb-authenticated quoteSummary v10 call —
    replaces yfinance .info, whose internal auth cannot see our crumb."""
    try:
        r = session.get(
            f"https://query1.finance.yahoo.com/v10/finance/quoteSummary/{tkr}",
            params={"modules": "price,summaryDetail,defaultKeyStatistics,"
                               "financialData,assetProfile",
                    "crumb": _CRUMB[0] or ""},
            timeout=15)
        if not r.ok:
            return None
        res = r.json().get("quoteSummary", {}).get("result")
        if not res:
            return None
        d = res[0]
    except Exception:
        return None
    prof = d.get("assetProfile") or {}
    px = d.get("price") or {}
    return {
        "marketCap":            _raw(d, "price", "marketCap"),
        "enterpriseValue":      _raw(d, "defaultKeyStatistics", "enterpriseValue"),
        "enterpriseToEbitda":   _raw(d, "defaultKeyStatistics", "enterpriseToEbitda"),
        "priceToBook":          _raw(d, "defaultKeyStatistics", "priceToBook"),
        "trailingPE":           _raw(d, "summaryDetail", "trailingPE"),
        "forwardPE":            _raw(d, "summaryDetail", "forwardPE")
                                or _raw(d, "defaultKeyStatistics", "forwardPE"),
        "enterpriseToRevenue":  _raw(d, "defaultKeyStatistics", "enterpriseToRevenue"),
        "pegRatio":             _raw(d, "defaultKeyStatistics", "pegRatio"),
        "currentPrice":         _raw(d, "financialData", "currentPrice"),
        "regularMarketPrice":   _raw(d, "price", "regularMarketPrice"),
        "currency":             px.get("currency"),
        "sharesOutstanding":    _raw(d, "defaultKeyStatistics", "sharesOutstanding"),
        "ebitda":               _raw(d, "financialData", "ebitda"),
        "totalDebt":            _raw(d, "financialData", "totalDebt"),
        "totalCash":            _raw(d, "financialData", "totalCash"),
        "profitMargins":        _raw(d, "financialData", "profitMargins")
                                or _raw(d, "defaultKeyStatistics", "profitMargins"),
        "revenueGrowth":        _raw(d, "financialData", "revenueGrowth"),
        "sector":               prof.get("sector"),
        "industry":             prof.get("industry"),
        "longName":             px.get("longName"),
        "longBusinessSummary":  prof.get("longBusinessSummary"),
    }

def init_schema(conn):
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS ticker_yf (
      ticker TEXT PRIMARY KEY,
      mcap_m REAL, enterprise_value_m REAL,
      ev_ebitda REAL, pb_ratio REAL, pe_ttm REAL, fwd_pe REAL,
      ev_revenue REAL, peg REAL,
      price REAL, currency TEXT,
      shares_out_m REAL, ebitda_m REAL, total_debt_m REAL, total_cash_m REAL,
      profit_margin REAL, rev_growth REAL,
      sector TEXT, industry TEXT,
      asof TEXT);
    CREATE INDEX IF NOT EXISTS idx_yf_evebitda ON ticker_yf(ev_ebitda);
    CREATE INDEX IF NOT EXISTS idx_yf_pb ON ticker_yf(pb_ratio);
    """)

def fetch_one(tkr, session):
    """Return dict of yahoo fundamentals for one ticker, or None."""
    info = quote_summary_info(tkr, session)
    if not info or (info.get("marketCap") is None and info.get("enterpriseValue") is None
                    and info.get("trailingPE") is None):
        return None
    def fin(x):
        # reject inf / nan / non-numeric — Yahoo returns inf P/E for ~zero-EPS
        # names, which SQLite stores as the text "Infinity" and breaks round().
        return x if isinstance(x, (int, float)) and math.isfinite(x) else None
    def m(x):
        x = fin(x)
        return (x / 1e6) if x is not None else None
    # EV/EBITDA is only meaningful with positive EV AND positive EBITDA; a
    # negative on either side (or neg/neg, which fakes a cheap positive) is junk.
    _ev, _ebitda = fin(info.get("enterpriseValue")), fin(info.get("ebitda"))
    _ev_ebitda = fin(info.get("enterpriseToEbitda")) if (
        _ev and _ev > 0 and _ebitda and _ebitda > 0) else None
    return {
        "mcap_m":   m(info.get("marketCap")),
        "ev_m":     m(info.get("enterpriseValue")),
        "ev_ebitda": _ev_ebitda,
        "pb":       fin(info.get("priceToBook")),
        "pe":       fin(info.get("trailingPE")),
        "fwd_pe":   fin(info.get("forwardPE")),
        "ev_rev":   fin(info.get("enterpriseToRevenue")),
        "peg":      fin(info.get("trailingPegRatio") or info.get("pegRatio")),
        "price":    fin(info.get("currentPrice") or info.get("regularMarketPrice")),
        "currency": info.get("currency"),
        "shares_m": m(info.get("sharesOutstanding")),
        "ebitda_m": m(info.get("ebitda")),
        "debt_m":   m(info.get("totalDebt")),
        "cash_m":   m(info.get("totalCash")),
        "margin":   fin(info.get("profitMargins")),
        "rev_g":    fin(info.get("revenueGrowth")),
        "sector":   info.get("sector"),
        "industry": info.get("industry"),
    }

def run(max_n=4000, rps=3.0):
    conn = sqlite3.connect(DB, timeout=60); conn.execute('PRAGMA busy_timeout=60000')
    init_schema(conn)
    conn.execute("""CREATE TABLE IF NOT EXISTS yf_dead (
        ticker TEXT PRIMARY KEY, asof TEXT)""")
    # FRESH = enriched within the last 10 days. Older rows re-enrich so prices
    # and mcaps track the market instead of freezing at their first fetch.
    fresh = {r[0] for r in conn.execute(
        "SELECT ticker FROM ticker_yf WHERE (mcap_m IS NOT NULL OR ev_ebitda IS NOT NULL) "
        "AND asof >= date('now','-10 days')")}
    # Known-dead (delisted/acquired): quote 404s with valid crumb auth. Skip —
    # but retest each ticker every ~30 days in case of relisting.
    dead = {r[0] for r in conn.execute(
        "SELECT ticker FROM yf_dead WHERE asof >= date('now','-30 days')")}
    # Universe: everything in unified_signal with a signal, by score priority.
    # Include FOREIGN tickers (Yahoo covers them) — fills the non-US gap.
    targets = [r[0] for r in conn.execute("""
        SELECT ticker FROM unified_signal ORDER BY score DESC""")]
    todo = [t for t in targets if t not in fresh and t not in dead][:max_n]
    print(f"yfinance enrich: {len(todo)} tickers (skip {len(fresh)} fresh, {len(dead)} dead), ~{rps} req/s")

    session = make_session()
    asof = time.strftime("%Y-%m-%d")
    interval = 1.0 / rps
    n_ok = n_ev = n_fail = 0
    last = [time.time() - interval]
    lock = threading.Lock()

    # Single-threaded with steady pacing — Yahoo .info rate-limits hard under
    # concurrency. One warmed session, ~3 req/s is the sweet spot.
    for i, tkr in enumerate(todo):
        wait = max(0, last[0] + interval - time.time())
        if wait > 0: time.sleep(wait)
        last[0] = time.time()
        res = fetch_one(tkr, session)
        if not res:
            n_fail += 1
            # With crumb auth working, a no-quote US ticker is DELISTED (the
            # 2025-26 M&A wave), not a fetch failure. But a TRANSIENT blip also
            # returns None (bulk-run verification found live ETFs marked dead),
            # so only mark dead after a fresh-session CONFIRMING second miss.
            # Foreign tickers (suffix mismatches) are never marked — ambiguous.
            if _CRUMB[0] and "." not in tkr and tkr.isalpha():
                time.sleep(1.0)
                confirm = make_session()
                if _CRUMB[0] and fetch_one(tkr, confirm) is None:
                    conn.execute("INSERT OR REPLACE INTO yf_dead VALUES (?,?)", (tkr, asof))
                    conn.commit()
                session = confirm
            # periodic session refresh on repeated failures
            elif n_fail % 25 == 0:
                session = make_session()
            continue
        # Column-explicit UPSERT: update only the valuation columns and leave
        # business_summary / long_name (set by enrich_summaries) intact.
        conn.execute("""INSERT INTO ticker_yf
            (ticker, mcap_m, enterprise_value_m, ev_ebitda, pb_ratio, pe_ttm, fwd_pe,
             ev_revenue, peg, price, currency, shares_out_m, ebitda_m, total_debt_m,
             total_cash_m, profit_margin, rev_growth, sector, industry, asof)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(ticker) DO UPDATE SET
                mcap_m=excluded.mcap_m, enterprise_value_m=excluded.enterprise_value_m,
                ev_ebitda=excluded.ev_ebitda, pb_ratio=excluded.pb_ratio,
                pe_ttm=excluded.pe_ttm, fwd_pe=excluded.fwd_pe,
                ev_revenue=excluded.ev_revenue, peg=excluded.peg,
                price=excluded.price, currency=excluded.currency,
                shares_out_m=excluded.shares_out_m, ebitda_m=excluded.ebitda_m,
                total_debt_m=excluded.total_debt_m, total_cash_m=excluded.total_cash_m,
                profit_margin=excluded.profit_margin, rev_growth=excluded.rev_growth,
                sector=excluded.sector, industry=excluded.industry, asof=excluded.asof""",
            (tkr, res["mcap_m"], res["ev_m"], res["ev_ebitda"], res["pb"],
             res["pe"], res["fwd_pe"], res["ev_rev"], res["peg"],
             res["price"], res["currency"], res["shares_m"], res["ebitda_m"],
             res["debt_m"], res["cash_m"], res["margin"], res["rev_g"],
             res["sector"], res["industry"], asof))
        n_ok += 1
        if res["ev_ebitda"] is not None: n_ev += 1
        if i % 50 == 0 and i > 0:
            conn.commit()
            print(f"  [{i}/{len(todo)}] {tkr} ok={n_ok} ev={n_ev} fail={n_fail}")
    conn.commit()
    print(f"\ndone: {n_ok} enriched ({n_ev} with EV/EBITDA), {n_fail} failed")

    print("\n--- spot check ---")
    for t in ("LEVI","MA","NCLH","HHH","KSS","GT","NRP"):
        r = conn.execute("SELECT mcap_m, ev_ebitda, pb_ratio, pe_ttm FROM ticker_yf WHERE ticker=?", (t,)).fetchone()
        if r:
            print(f"  {t:<6} mcap=${r[0] or 0:,.0f}M  EV/EBITDA={r[1]}  P/B={r[2]}  P/E={r[3]}")

if __name__ == "__main__":
    run(max_n=int(sys.argv[1]) if sys.argv[1:] else 4000)
