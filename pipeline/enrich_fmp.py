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
    limited = 0
    for attempt in range(6):
        r = subprocess.run(["curl", "-sS", "--max-time", "180", url],
                           capture_output=True, text=True)
        body = r.stdout
        if body.startswith('"symbol"'):
            return list(csv.DictReader(io.StringIO(body)))
        if body.strip() in ("", "[]"):
            return []
        if "Limit Reach" in body:
            # bulk endpoints sit behind a rolling window (a call that fails now
            # succeeds a minute later): wait it out twice, then give up
            limited += 1
            if limited > 2:
                raise RuntimeError(f"FMP {path}: limit reached")
            time.sleep(65)
            continue
        time.sleep(5 * (attempt + 1))      # transient error
    raise RuntimeError(f"FMP {path} failed: {body[:200]}")

def num(x):
    try:
        v = float(x)
        return v if math.isfinite(v) else None
    except (TypeError, ValueError):
        return None

CACHE = os.path.join(BASE, "data", "fmp_cache")

def cached_bulk(name, fetch, max_age_h=20):
    """Bulk files are big and FMP rate-limits them ("Limit Reach"), so each is
    downloaded at most once a day into data/fmp_cache/. If the limit trips,
    fall back to the last good copy (any age) rather than fail the run."""
    os.makedirs(CACHE, exist_ok=True)
    path = os.path.join(CACHE, f"{name}.csv")
    fresh = os.path.exists(path) and time.time() - os.path.getmtime(path) < max_age_h * 3600
    if not fresh:
        try:
            rows = fetch()
            if not rows:
                raise RuntimeError(f"FMP {name} returned nothing")
            with open(path, "w", newline="") as f:
                w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
                w.writeheader(); w.writerows(rows)
        except RuntimeError as e:
            if not os.path.exists(path):
                raise
            age_h = (time.time() - os.path.getmtime(path)) / 3600
            print(f"  ! {name}: {str(e)[:80]} — using cached copy ({age_h:.0f}h old)", flush=True)
    return list(csv.DictReader(open(path)))

def load_profiles():
    """All FMP company profiles (~90k) — shared by the enrich and the mapper."""
    def fetch():
        rows = []
        for part in range(0, 12):
            chunk = fetch_csv("profile-bulk", part=part)
            if not chunk:
                break
            rows.extend(chunk)
        return rows
    return {r["symbol"]: r for r in cached_bulk("profile_bulk", fetch)}

def is_true(x):
    return str(x).strip().lower() == "true"

def pos(x):
    """Ratio only meaningful when positive (neg EBITDA / neg earnings -> None)."""
    v = num(x)
    return v if (v is not None and v > 0) else None

def _fx_major(ccy):
    """USD per MAJOR unit (aggregates are in major units even for GBp quotes)."""
    from unified_score import fx_major
    return fx_major(ccy)

_NAME_STOP = {"INC", "CORP", "CORPORATION", "CO", "LTD", "PLC", "NV", "SA", "AG", "HOLDINGS",
              "HOLDING", "GROUP", "THE", "COMPANY", "LIMITED", "LLC", "LP"}

def _name_toks(s):
    import re as _re
    return {t for t in _re.split(r"[^A-Z0-9&]+", (s or "").upper()) if len(t) >= 3 and t not in _NAME_STOP}

# every table that stores a ticker a signal is keyed on
ALIAS_TABLES = (("fund_positions", "ticker"), ("holder_13d", "subject_ticker"),
                ("form4_transactions", "ticker"), ("catalysts_8k", "ticker"),
                ("fund_13f_holdings", "ticker"), ("fund_13f_prior", "ticker"), ("broker_13f", "ticker"),
                ("congress_trades", "ticker"), ("corp_actions", "ticker"),
                ("latent_ownership", "ticker"), ("form144", "ticker"), ("form144_signal", "ticker"),
                ("discovery_13d_subjects", "ticker"))

def apply_ticker_aliases(conn, prof):
    """Renamed tickers split a company's signals in two (EchoStar SATS -> ECHO:
    the 13F holders sat on ECHO, an older 13D / Form 144 / researcher position
    on SATS, which was classed 'delisted'). FMP files each listing's CUSIP; an
    INACTIVE symbol whose CUSIP now trades under exactly one ACTIVE symbol is the
    same security under a new ticker (a CUSIP is never reused). Company names
    must agree too — a guard against FMP data errors. Old tickers are rewritten
    in every signal table; ticker_alias records what was merged."""
    from collections import defaultdict
    by = defaultdict(list)
    for s, p in prof.items():
        if p.get("cusip") and "." not in s:
            by[p["cusip"].upper()].append(s)
    alias = {}
    for cu, syms in by.items():
        act = [s for s in syms if is_true(prof[s].get("isActivelyTrading"))]
        if len(act) != 1:
            continue
        new = act[0]
        for old in syms:
            if old != new and str(prof[old].get("isActivelyTrading", "")).lower() == "false" \
                    and _name_toks(prof[old].get("companyName")) & _name_toks(prof[new].get("companyName")):
                alias[old] = (new, cu)
    conn.execute("""CREATE TABLE IF NOT EXISTS ticker_alias (old TEXT PRIMARY KEY, new TEXT,
                    cusip TEXT, asof TEXT)""")
    asof = time.strftime("%Y-%m-%d")
    moved = 0
    for t, col in ALIAS_TABLES:
        try:
            present = {r[0] for r in conn.execute(f"SELECT DISTINCT {col} FROM {t} WHERE {col} IS NOT NULL")}
        except sqlite3.OperationalError:
            continue
        for old in present & alias.keys():
            new, cu = alias[old]
            n = conn.execute(f"UPDATE OR IGNORE {t} SET {col} = ? WHERE {col} = ?", (new, old)).rowcount
            if n:
                moved += n
                conn.execute("INSERT OR REPLACE INTO ticker_alias VALUES (?,?,?,?)", (old, new, cu, asof))
    conn.commit()
    return moved

def run():
    conn = sqlite3.connect(DB, timeout=120)
    conn.execute("PRAGMA busy_timeout=120000")
    conn.row_factory = sqlite3.Row
    cols = [r[1] for r in conn.execute("PRAGMA table_info(ticker_yf)")]
    for col, ty in (("src", "TEXT"), ("is_fund", "INTEGER"), ("ptb_ratio", "REAL"), ("neg_tbv", "INTEGER")):
        if col not in cols:
            conn.execute(f"ALTER TABLE ticker_yf ADD COLUMN {col} {ty}")
            cols.append(col)

    t0 = time.time()
    prof = load_profiles()
    km = {r["symbol"]: r for r in cached_bulk("key_metrics_ttm", lambda: fetch_csv("key-metrics-ttm-bulk"))}
    rt = {r["symbol"]: r for r in cached_bulk("ratios_ttm", lambda: fetch_csv("ratios-ttm-bulk"))}
    print(f"FMP bulk: {len(prof):,} profiles, {len(km):,} key-metrics, "
          f"{len(rt):,} ratios in {time.time() - t0:.0f}s", flush=True)
    n_alias = apply_ticker_aliases(conn, prof)
    print(f"ticker renames: {n_alias:,} signal rows moved from old to current tickers "
          f"({conn.execute('SELECT COUNT(*) FROM ticker_alias').fetchone()[0]} renames on file)", flush=True)

    universe = {r[0] for r in conn.execute("""
        SELECT ticker FROM unified_signal
        UNION SELECT ticker FROM fund_13f_holdings WHERE ticker IS NOT NULL
        UNION SELECT ticker FROM cusip_map WHERE ticker IS NOT NULL""")}
    # the local listings of the global funds' N-PORT books (Tokyo, London,
    # Seoul...): priced and valued like every other name in the books
    if conn.execute("SELECT 1 FROM sqlite_master WHERE name='nport_holdings'").fetchone():
        universe |= {r[0] for r in conn.execute(
            "SELECT DISTINCT ticker FROM nport_holdings WHERE ticker IS NOT NULL")}
    existing = {r["ticker"]: dict(r) for r in conn.execute("SELECT * FROM ticker_yf")}
    asof = time.strftime("%Y-%m-%d")
    conn.execute("CREATE TABLE IF NOT EXISTS yf_dead (ticker TEXT PRIMARY KEY, asof TEXT)")
    n_upd = n_new = n_inactive = n_miss = n_revived = 0
    for tk in sorted(universe):
        p = prof.get(tk)
        if not p:
            n_miss += 1
            continue
        if str(p.get("isActivelyTrading", "")).lower() == "false":
            # FMP says the listing is gone (acquired / taken private — CyberArk,
            # Dayforce, Avidity). Flag it so scoring treats it as delisted rather
            # than an unpriced "unknown mcap" pick.
            conn.execute("INSERT OR REPLACE INTO yf_dead VALUES (?,?)", (tk, asof))
            n_inactive += 1
            # still repair a cut description (the rows stay in reference sheets)
            desc = " ".join((p.get("description") or "").split())
            if desc:
                conn.execute("""UPDATE ticker_yf SET business_summary = ? WHERE ticker = ?
                    AND (business_summary IS NULL OR business_summary = ''
                         OR business_summary LIKE '%…' OR business_summary LIKE '%...'
                         OR length(business_summary) < ?)""", (desc, tk, len(desc)))
            continue
        price, mcap, ccy = num(p.get("price")), num(p.get("marketCap")), p.get("currency") or "USD"
        if not price or not mcap:
            n_miss += 1
            continue
        # FMP says it trades and prices it: a Yahoo "dead" flag is wrong. Yahoo
        # marks a ticker dead after two quote misses, and throttled runs miss
        # live names — 1,052 of 1,936 flags were live (PG&E, CRH, TKO, Air
        # Products, Cognizant, Block), each classed 'delisted' out of every pick.
        n_revived += conn.execute("DELETE FROM yf_dead WHERE ticker=?", (tk,)).rowcount
        row = existing.get(tk) or {c: None for c in cols}
        is_new = tk not in existing
        # Aggregates FMP doesn't overwrite (debt, cash; EV/EBITDA when FMP has
        # no key-metrics row) stay, but must be re-expressed in FMP's currency:
        # a row enrich_fx already converted to USD would otherwise be multiplied
        # by the EUR/GBP rate a second time.
        old_ccy = row.get("currency")
        if not is_new and old_ccy and old_ccy != ccy:
            f_old, f_new = _fx_major(old_ccy), _fx_major(ccy)
            for c in ("enterprise_value_m", "ebitda_m", "total_debt_m", "total_cash_m"):
                if row.get(c) is not None:
                    row[c] = row[c] * f_old / f_new if (f_old and f_new) else None
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
            ev = (mcap * ev_rep / mc_rep / 1e6
                  if (ev_rep is not None and mc_rep and mc_rep > 0) else None)
            row["enterprise_value_m"] = ev
            # EBITDA in the same (listing) currency, sign kept: unified_score
            # only trusts EV/EBITDA when EV > 0 AND EBITDA > 0, so leaving this
            # blank would silently discard every FMP multiple.
            m = num(k.get("evToEBITDATTM"))
            row["ebitda_m"] = ev / m if (ev and m) else None
        if r:
            row["pb_ratio"] = pos(r.get("priceToBookRatioTTM"))
            row["pe_ttm"] = pos(r.get("priceToEarningsRatioTTM"))
            row["peg"] = pos(r.get("priceToEarningsGrowthRatioTTM"))
            # P/TB = P/B x (book / tangible book per share). Book and tangible
            # book are both in the reporting currency, so their ratio is
            # currency-free and inherits P/B's one-currency correctness on ADRs.
            # Tangible book <= 0 (goodwill-heavy / acquisitive) -> no multiple,
            # but flagged: that is information in itself.
            pb_raw = num(r.get("priceToBookRatioTTM"))
            bv, tbv = num(r.get("bookValuePerShareTTM")), num(r.get("tangibleBookValuePerShareTTM"))
            row["ptb_ratio"] = (pb_raw * bv / tbv
                                if (pb_raw and pb_raw > 0 and bv and bv > 0 and tbv and tbv > 0) else None)
            row["neg_tbv"] = int(bool(bv and bv > 0 and tbv is not None and tbv <= 0))
            pm = num(r.get("netProfitMarginTTM"))
            if pm is not None:
                row["profit_margin"] = pm
        # descriptive fields: fill gaps only — downstream filters match Yahoo's
        # industry strings (e.g. 'Shell Companies'), so never overwrite them.
        for col, fk in (("sector", "sector"), ("industry", "industry"), ("long_name", "companyName")):
            if col in row and not row.get(col) and p.get(fk):
                row[col] = p[fk]
        # business summary: FMP's description is complete; replace a missing,
        # cut ('…' — the old 500-char Yahoo store) or shorter stored summary
        desc = " ".join((p.get("description") or "").split())
        cur = row.get("business_summary") or ""
        if desc and (not cur or cur.endswith(("…", "...")) or len(desc) > len(cur)):
            row["business_summary"] = desc
        # FMP's ETF / fund flags: closed-end funds and trusts (ASA, PSLV, MUC,
        # Cornerstone...) otherwise pass the name heuristics and score as stocks
        row["is_fund"] = int(is_true(p.get("isEtf")) or is_true(p.get("isFund")))
        row["asof"] = asof
        row["src"] = "fmp"
        conn.execute(f"INSERT OR REPLACE INTO ticker_yf ({','.join(cols)}) "
                     f"VALUES ({','.join('?' * len(cols))})", [row.get(c) for c in cols])
        n_new += is_new
        n_upd += not is_new
    # the hand-curated watchlist (candidates) prices from the same feed: its
    # Yahoo source (ingest_prices) is refused with HTTP 429, and Tier-1 prices
    # had sat at 2026-06-09. Same symbol quirks as ingest_prices (UA -> UAA).
    try:
        from ingest_prices import MAP as _YMAP
    except Exception:
        _YMAP = {}
    n_cand = 0
    for tk, ccy_c in conn.execute("SELECT ticker, currency FROM candidates").fetchall():
        p = prof.get(_YMAP.get(tk, tk)) or prof.get(tk)
        if not p or not is_true(p.get("isActivelyTrading")) or not num(p.get("price")):
            continue
        usd = (p.get("currency") or "USD") == "USD" and (ccy_c or "USD") == "USD"
        conn.execute("""UPDATE candidates SET price = ?, price_asof = ?,
            mcap_m = CASE WHEN ? THEN ? ELSE mcap_m END WHERE ticker = ?""",
            (num(p["price"]), asof, usd, (num(p.get("marketCap")) or 0) / 1e6 or None, tk))
        n_cand += 1
    print(f"candidates watchlist: {n_cand} prices refreshed from FMP")
    # sweep the rest of the dead list too (tickers that left the universe but
    # keep a stale flag): FMP active + priced = alive
    for (tk,) in conn.execute("SELECT ticker FROM yf_dead").fetchall():
        p = prof.get(tk)
        if p and is_true(p.get("isActivelyTrading")) and num(p.get("price")):
            n_revived += conn.execute("DELETE FROM yf_dead WHERE ticker=?", (tk,)).rowcount
    conn.commit()
    print(f"ticker_yf: {n_upd:,} refreshed + {n_new:,} NEW from FMP | "
          f"{n_inactive} inactive -> yf_dead | {n_revived} wrongly-dead revived | "
          f"{n_miss} not in FMP (Yahoo fallback)")
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
