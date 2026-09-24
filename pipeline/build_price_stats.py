"""Momentum / drawdown stats for every name we price: price_stats(ticker,
mom_3mo, mom_20d, off_high, last_close, n_pts, asof).

The books use these for the entry-timing lens the score lacks: a name 40%
off its high with insiders buying is a very different setup from one at highs.

Source: FMP's end-of-day bulk file (every listed symbol's close for a date in
one call) for three dates — the latest session, ~20 and ~63 trading days
earlier — plus the 52-week range from the FMP company profiles. This replaced
a Yahoo 3-month series for ~800 names that stopped updating when Yahoo began
refusing requests (HTTP 429): the dossier's "3mo %" and "% off high" had been
frozen at 2026-06-18 while presented as current. A name FMP doesn't price gets
NO stats rather than stale ones.

  mom_3mo   close vs ~63 trading days ago (%)
  mom_20d   close vs ~20 trading days ago (%)
  off_high  close vs the 52-week high (%, <= 0)
"""
import os, sqlite3, sys, time
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from enrich_fmp import DB, cached_bulk, fetch_csv, load_profiles, num

def eod(d):
    """{symbol: close} for a date; {} on a non-trading day. Past sessions never
    change, so each day's file is cached for good."""
    rows = cached_bulk(f"eod_{d}", lambda: fetch_csv("eod-bulk", date=d) or [{"symbol": "", "close": ""}],
                       max_age_h=24 * 3650)
    return {r["symbol"]: num(r.get("close")) for r in rows if r.get("symbol") and num(r.get("close"))}

def session_on_or_before(d, max_back=7):
    for i in range(max_back):
        dd = (d - timedelta(days=i)).isoformat()
        px = eod(dd)
        if len(px) > 5000:                   # a real session, not a holiday stub
            return dd, px
    return None, {}

def run():
    conn = sqlite3.connect(DB, timeout=120)
    conn.execute("PRAGMA busy_timeout=120000")
    conn.execute("""CREATE TABLE IF NOT EXISTS price_stats (
        ticker TEXT PRIMARY KEY, mom_3mo REAL, mom_20d REAL, off_high REAL,
        last_close REAL, n_pts INTEGER, asof TEXT)""")
    today = date.today()
    d0, p0 = session_on_or_before(today - timedelta(days=1))
    if not d0:
        raise SystemExit("no recent FMP end-of-day session found — price_stats left unchanged")
    base = date.fromisoformat(d0)
    d20, p20 = session_on_or_before(base - timedelta(days=28))
    d63, p63 = session_on_or_before(base - timedelta(days=91))
    prof = load_profiles()
    universe = {r[0] for r in conn.execute("""SELECT ticker FROM unified_signal
        UNION SELECT ticker FROM fund_13f_holdings WHERE ticker IS NOT NULL""")}
    rows = []
    for tk in universe:
        last = p0.get(tk)
        if not last or last < 1.0:          # penny stocks: % moves are noise
            continue
        a63, a20 = p63.get(tk), p20.get(tk)
        rng = (prof.get(tk) or {}).get("range") or ""
        try:
            hi52 = float(rng.split("-")[-1]) if "-" in rng else None
        except ValueError:
            hi52 = None
        hi = max(hi52, last) if hi52 else None
        rows.append((tk,
                     (last / a63 - 1) * 100 if a63 and a63 >= 0.5 else None,
                     (last / a20 - 1) * 100 if a20 else None,
                     (last / hi - 1) * 100 if hi else None,
                     last, 3, d0))
    if len(rows) < 500:
        raise SystemExit(f"only {len(rows)} names priced — price_stats left unchanged")
    conn.execute("DELETE FROM price_stats")
    conn.executemany("INSERT OR REPLACE INTO price_stats VALUES (?,?,?,?,?,?,?)", rows)
    conn.commit()
    print(f"price_stats: {len(rows):,} tickers (as-of {d0}; 20d base {d20}, 3mo base {d63}; "
          f"off-high vs 52-week high)")
    conn.close()

if __name__ == "__main__":
    run()
