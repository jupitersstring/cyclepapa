"""FMP (Financial Modeling Prep) market-data layer — primary price/valuation feed.

Why it exists: Yahoo (enrich_yfinance) is throttled (~20 min for 4k tickers,
crumb auth, DB-lock contention) and mixes currencies on foreign ADRs (TSM showed
EV $15.4T, P/B 88). FMP's bulk endpoints return the whole market in a handful
of calls (~10 s), cover ~94% of our universe (Yahoo ~83%), and compute
valuation ratios within ONE currency, so ADR metrics come out right.

It writes INTO ticker_yf (the table every scorer/renderer already reads) with
src='fmp'. Yahoo stays the fallback: run this FIRST — its rows are stamped
today, so enrich_yfinance's 10-day freshness gate then only fetches the names
FMP doesn't cover.

Currency conventions match Yahoo's (verified): price in the quote currency
(GBp / ZAc / ILA are MINOR units), market cap in MAJOR units of the listing
currency. unified_score's FX table converts both.

Key: env FMP_API_KEY, else data/.fmp_key (gitignored). Never committed.
"""
import csv, io, math, os, sqlite3, subprocess, time

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(BASE, "data", "cyclepapa.db")
API = "https://financialmodelingprep.com/stable"
MINOR = {"GBp": 100.0, "GBX": 100.0, "ZAc": 100.0, "ILA": 100.0}   # minor-unit quotes

def api_key():
    k = os.environ.get("FMP_API_KEY", "").strip()
    if not k:
        p = os.path.join(BASE, "data", ".fmp_key")
        if os.path.exists(p):
            k = open(p).read().strip()
    if not k:
        raise SystemExit("FMP_API_KEY not set (env var or data/.fmp_key)")
    return k

def fetch_csv(path, **params):
    q = "&".join(f"{k}={v}" for k, v in params.items())
    url = f"{API}/{path}?{q}{'&' if q else ''}apikey={api_key()}"
    for attempt in range(4):
        r = subprocess.run(["curl", "-sS", "--max-time", "180", url],
                           capture_output=True, text=True)
        body = r.stdout
        if body.startswith('"symbol"'):
            return list(csv.DictReader(io.StringIO(body)))
        if body.strip() in ("", "[]"):
            return []
        time.sleep(5 * (attempt + 1))      # bulk endpoints are rate-limited
    raise RuntimeError(f"FMP {path} failed: {body[:200]}")

def num(x):
    try:
        v = float(x)
        return v if math.isfinite(v) else None
    except (TypeError, ValueError):
        return None

def pos(x):
    """Ratio only meaningful when positive (neg EBITDA / neg earnings -> None)."""
    v = num(x)
    return v if (v is not None and v > 0) else None

def run():
    conn = sqlite3.connect(DB, timeout=120)
    conn.execute("PRAGMA busy_timeout=120000")
    conn.row_factory = sqlite3.Row
    cols = [r[1] for r in conn.execute("PRAGMA table_info(ticker_yf)")]
    if "src" not in cols:
        conn.execute("ALTER TABLE ticker_yf ADD COLUMN src TEXT")
        cols.append("src")

    t0 = time.time()
    prof = {}
    for part in range(0, 12):
        rows = fetch_csv("profile-bulk", part=part)
        if not rows:
            break
        for r in rows:
            prof[r["symbol"]] = r
    km = {r["symbol"]: r for r in fetch_csv("key-metrics-ttm-bulk")}
    rt = {r["symbol"]: r for r in fetch_csv("ratios-ttm-bulk")}
    print(f"FMP bulk: {len(prof):,} profiles, {len(km):,} key-metrics, "
          f"{len(rt):,} ratios in {time.time() - t0:.0f}s", flush=True)

    universe = {r[0] for r in conn.execute("""
        SELECT ticker FROM unified_signal
        UNION SELECT ticker FROM fund_13f_holdings WHERE ticker IS NOT NULL
        UNION SELECT ticker FROM cusip_map WHERE ticker IS NOT NULL""")}
    existing = {r["ticker"]: dict(r) for r in conn.execute("SELECT * FROM ticker_yf")}
    asof = time.strftime("%Y-%m-%d")
    n_upd = n_new = n_inactive = n_miss = 0
    for tk in sorted(universe):
        p = prof.get(tk)
        if not p:
            n_miss += 1
            continue
        if str(p.get("isActivelyTrading", "")).lower() == "false":
            n_inactive += 1                  # stale quote — leave any Yahoo row alone
            continue
        price, mcap, ccy = num(p.get("price")), num(p.get("marketCap")), p.get("currency") or "USD"
        if not price or not mcap:
            n_miss += 1
            continue
        row = existing.get(tk) or {c: None for c in cols}
        is_new = tk not in existing
        row["ticker"] = tk
        row["price"] = price
        row["currency"] = ccy
        row["mcap_m"] = mcap / 1e6
        row["shares_out_m"] = mcap / (price / MINOR.get(ccy, 1.0)) / 1e6
        k, r = km.get(tk), rt.get(tk)
        if k:
            row["ev_ebitda"] = pos(k.get("evToEBITDATTM"))
            row["ev_revenue"] = pos(k.get("evToSalesTTM"))
            # FMP's EV is in the REPORTING currency (TSM: TWD). EV/mktcap is
            # currency-free, so rescale onto the listing-currency market cap.
            ev_rep, mc_rep = num(k.get("enterpriseValueTTM")), num(k.get("marketCap"))
            row["enterprise_value_m"] = (mcap * ev_rep / mc_rep / 1e6
                                         if (ev_rep is not None and mc_rep and mc_rep > 0) else None)
        if r:
            row["pb_ratio"] = pos(r.get("priceToBookRatioTTM"))
            row["pe_ttm"] = pos(r.get("priceToEarningsRatioTTM"))
            pm = num(r.get("netProfitMarginTTM"))
            if pm is not None:
                row["profit_margin"] = pm
        # descriptive fields: fill gaps only — downstream filters match Yahoo's
        # industry strings (e.g. 'Shell Companies'), so never overwrite them.
        for col, fk in (("sector", "sector"), ("industry", "industry"),
                        ("business_summary", "description"), ("long_name", "companyName")):
            if col in row and not row.get(col) and p.get(fk):
                row[col] = p[fk]
        row["asof"] = asof
        row["src"] = "fmp"
        conn.execute(f"INSERT OR REPLACE INTO ticker_yf ({','.join(cols)}) "
                     f"VALUES ({','.join('?' * len(cols))})", [row.get(c) for c in cols])
        n_new += is_new
        n_upd += not is_new
    conn.commit()
    print(f"ticker_yf: {n_upd:,} refreshed + {n_new:,} NEW from FMP | "
          f"{n_inactive} inactive skipped | {n_miss} not in FMP (Yahoo fallback)")
    for tk in ("TSM", "ASML", "SAP", "BUD", "AAPL", "RR.L"):
        x = conn.execute("""SELECT price, currency, ROUND(mcap_m) m, ROUND(enterprise_value_m) ev,
                            ROUND(ev_ebitda,1), ROUND(pb_ratio,1), ROUND(pe_ttm,1), src
                            FROM ticker_yf WHERE ticker=?""", (tk,)).fetchone()
        if x:
            print(f"  {tk:5s} px={x[0]} {x[1]} mcap_m={x[2]:,.0f} ev_m={x[3]} "
                  f"EV/EBITDA={x[4]} P/B={x[5]} P/E={x[6]} [{x[7]}]")
    conn.close()

if __name__ == "__main__":
    run()
