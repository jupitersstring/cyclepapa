"""Enrich the ticker universe with market cap, sector, exchange, ADV.

For the 5,117 distinct tickers in fund_13f_holdings, only 35 have mcap
in `candidates`. This blocks every "is it micro/small" question. Fetch
mcap + sector + price for any ticker that has any smart-money signal
(13F holder or fund_positions or holder_13d).

Data sources (no auth required):
  - Yahoo v8/chart endpoint → price, exchange, name (works without crumb)
  - SEC company_tickers_exchange.json → ticker → CIK mapping
  - SEC companyfacts/CIK{x}.json → shares-outstanding from latest 10-K/Q
  - mcap = shares_outstanding × price (US listings only)

For foreign tickers (.L .TO .HK .T .AX) we still get price + exchange but
no mcap (would need their respective listings API). Stored in ticker_meta.
"""
import json, os, re, sqlite3, subprocess, sys, time

DB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "cyclepapa.db")
UA_BROWSER = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"
UA_SEC = "cyclepapa-research admin@example.com"

# --- Yahoo chart endpoint -----------------------------------------------------
def yahoo_chart_meta(sym):
    """Return (price, exchange, currency, name, adv) for one ticker."""
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?range=3mo&interval=1d"
    out = subprocess.run(["curl", "-sk", "-m", "15", "-A", UA_BROWSER, url],
                         capture_output=True, text=True).stdout
    try:
        j = json.loads(out)
        r = j["chart"]["result"][0]
        meta = r["meta"]
        # average dollar volume over the 3mo window
        vol = r["indicators"]["quote"][0].get("volume", []) or []
        close = r["indicators"]["quote"][0].get("close", []) or []
        avg_dv = sum(v*c for v, c in zip(vol, close) if v and c) / max(1, sum(1 for v in vol if v))
        return {
            "price":    meta.get("regularMarketPrice"),
            "exchange": meta.get("fullExchangeName"),
            "currency": meta.get("currency"),
            "name":     meta.get("longName") or meta.get("shortName"),
            "adv_usd_m": avg_dv / 1e6 if avg_dv else None,
        }
    except Exception:
        return None

# --- SEC company facts: shares outstanding -----------------------------------
_CIK_BY_TKR = None
def cik_for_ticker(t):
    """Lazy-load and lookup SEC ticker → CIK mapping."""
    global _CIK_BY_TKR
    if _CIK_BY_TKR is None:
        out = subprocess.run(["curl","-sk","--compressed","-m","20","-A",UA_SEC,
                              "https://www.sec.gov/files/company_tickers.json"],
                             capture_output=True).stdout
        try:
            j = json.loads(out)
            _CIK_BY_TKR = {v["ticker"].upper(): str(v["cik_str"]) for v in j.values()}
        except Exception:
            _CIK_BY_TKR = {}
    return _CIK_BY_TKR.get(t.upper())

def shares_outstanding(cik):
    """Latest EntityCommonStockSharesOutstanding via the tiny companyconcept
    endpoint (KB vs MB) — much faster than companyfacts."""
    cik10 = str(cik).zfill(10)
    for tag in ("EntityCommonStockSharesOutstanding",):
        url = f"https://data.sec.gov/api/xbrl/companyconcept/CIK{cik10}/dei/{tag}.json"
        out = subprocess.run(["curl","-sk","--compressed","-m","10","-A",UA_SEC, url],
                             capture_output=True).stdout
        try:
            j = json.loads(out)
            units = j.get("units", {})
            best = None
            for _, entries in units.items():
                for e in entries:
                    end = e.get("end") or e.get("fp") or ""
                    if best is None or end > best[0]:
                        best = (end, e.get("val"))
            if best: return best[1]
        except Exception:
            continue
    return None

def init_schema(conn):
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS ticker_meta (
      ticker TEXT PRIMARY KEY,
      name TEXT, exchange TEXT, market TEXT,
      sector TEXT, industry TEXT,
      mcap_m REAL,                 -- market cap in $M
      price REAL, price_currency TEXT,
      adv_3m_usd_m REAL,           -- 3-month avg dollar volume in $M
      shares_out_m REAL,
      pe_ttm REAL, fwd_pe REAL,
      beta REAL,
      asof TEXT
    );
    CREATE INDEX IF NOT EXISTS idx_tm_mcap ON ticker_meta(mcap_m);
    CREATE INDEX IF NOT EXISTS idx_tm_sector ON ticker_meta(sector);
    """)

def universe(conn):
    """Tickers with ANY signal — 13F holder, fund_positions, or holder_13d.

    Returned ordered by SIGNAL PRIORITY (so a limited run hits the most
    important names first):
      1. fund_positions S3/S4 (new major / material adds) — explicit signals
      2. holder_13d subjects (activist filings)
      3. multi-fund 13F holders (≥3 funds = consensus)
      4. single-fund 13F holders (long tail)

    Foreign tickers (containing ".") are deprioritized — we can't get mcap
    for them via SEC.
    """
    s34 = {r[0] for r in conn.execute(
        "SELECT DISTINCT ticker FROM fund_positions WHERE ticker IS NOT NULL AND section IN (3,4)")}
    activist = {r[0] for r in conn.execute(
        "SELECT DISTINCT subject_ticker FROM holder_13d WHERE subject_ticker IS NOT NULL")}
    multi = [(r[0], r[1]) for r in conn.execute(
        """SELECT ticker, COUNT(DISTINCT fund) c FROM fund_13f_holdings
           WHERE ticker IS NOT NULL GROUP BY ticker HAVING c >= 3 ORDER BY c DESC""")]
    single = [r[0] for r in conn.execute(
        """SELECT ticker, COUNT(DISTINCT fund) c FROM fund_13f_holdings
           WHERE ticker IS NOT NULL GROUP BY ticker HAVING c < 3""")]
    fp_all = {r[0] for r in conn.execute(
        "SELECT DISTINCT ticker FROM fund_positions WHERE ticker IS NOT NULL")}

    ordered = []
    seen = set()
    for t in list(s34) + list(activist) + [m[0] for m in multi] + list(fp_all) + single:
        if t in seen: continue
        seen.add(t); ordered.append(t)
    # Move US-listed names (no ".") to the front of each cluster, foreign to back
    us = [t for t in ordered if "." not in t]
    fx = [t for t in ordered if "." in t]
    return us + fx

def is_us_ticker(t):
    if not t or "." in t and not t.endswith((".B", ".A", ".K")):
        # foreign exchange suffix like .L, .TO, .HK, .T → Yahoo handles them
        return True
    return True  # actually let Yahoo decide; it handles .L/.TO/.MI etc

def run(only_missing=True, max_tickers=2000):
    conn = sqlite3.connect(DB)
    init_schema(conn)
    have = {r[0] for r in conn.execute("SELECT ticker FROM ticker_meta WHERE price IS NOT NULL")}
    todo = [t for t in universe(conn) if (not only_missing) or t not in have]
    todo = todo[:max_tickers]
    print(f"enriching {len(todo)} tickers (have={len(have)})")
    n_price = n_mcap = n_fail = 0
    asof = time.strftime("%Y-%m-%d")
    for i, t in enumerate(todo):
        # skip noise tickers
        if not re.match(r'^[A-Z0-9][A-Z0-9.\-]{0,9}$', t):
            n_fail += 1; continue
        # Yahoo chart for price + exchange + ADV
        meta = yahoo_chart_meta(t)
        if not meta or not meta.get("price"):
            n_fail += 1
            continue
        n_price += 1
        # SEC shares-outstanding for US tickers (skip foreign with ".")
        mcap_m = None
        so_m = None
        if "." not in t:
            cik = cik_for_ticker(t)
            if cik:
                so = shares_outstanding(cik)
                if so and meta["price"]:
                    so_m = so / 1e6
                    mcap_m = so_m * meta["price"]
                    n_mcap += 1
        conn.execute("""INSERT OR REPLACE INTO ticker_meta VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (t, meta["name"], meta["exchange"], None,
             None, None,
             mcap_m, meta["price"], meta["currency"],
             meta["adv_usd_m"], so_m,
             None, None, None,
             asof))
        if i % 50 == 0 and i > 0:
            print(f"  [{i+1}/{len(todo)}] {t} ${meta['price']:.2f} mcap=${mcap_m or 0:,.0f}M  px={n_price} mc={n_mcap} fail={n_fail}")
            conn.commit()
        time.sleep(0.12)
    conn.commit()
    print(f"\ndone. price={n_price}, mcap={n_mcap}, failed={n_fail}")
    print(f"\n--- mcap distribution ---")
    for label, lo, hi in [("nano  <$50M",0,50),("micro $50-300M",50,300),
                          ("small $300M-2B",300,2000),("mid   $2-10B",2000,10000),
                          ("large $10B+",10000,1e12)]:
        n = conn.execute("SELECT COUNT(*) FROM ticker_meta WHERE mcap_m>=? AND mcap_m<?",
                         (lo, hi)).fetchone()[0]
        print(f"  {label:<18} {n}")

if __name__ == "__main__":
    run(only_missing=True, max_tickers=int(sys.argv[1]) if sys.argv[1:] else 2000)
