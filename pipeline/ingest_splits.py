"""Stock splits between each fund's prior and current 13F periods (FMP).

The quarter-change views diff SHARE counts (unit-free, unlike values). A split
inside the window multiplies every holder's count: Booking's 25:1 (Apr 2026),
Carvana's 5:1 and KLA's 10:1 read as 30+ funds "adding" +400-999% and topped
the Quarter Change sheet and the broadsheet's builders — pure mechanics.

Loads FMP's splits calendar into stock_splits, then writes the product of
numerator/denominator over splits dated after a book's prior report period and
on or before its current one: prior_split_factor(fund, ticker, factor) for the
13F diffs (periods from the EDGAR 13F index) and nport_split_factor(series_id,
ticker, factor) for the N-PORT diffs. Views multiply prior shares by it. Only
factors != 1 are stored.
"""
import datetime as dt, os, sqlite3, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from discover_funds_fmp import _get
from enrich_fmp import DB

def _windows(conn):
    """(13F windows per fund, N-PORT windows per fund series): (key, prior
    period, current period) for every live book that has a prior to diff."""
    periods = conn.execute("""SELECT s.fund,
            (SELECT period FROM sec_13f_filings g WHERE g.accession = s.last_accession AND g.period != '' LIMIT 1),
            (SELECT period FROM sec_13f_filings g WHERE g.accession = p.accession AND g.period != '' LIMIT 1)
        FROM fund_13f_state s JOIN fund_13f_prior_state p ON p.fund = s.fund
        WHERE p.accession IS NOT NULL
          AND EXISTS (SELECT 1 FROM fund_13f_holdings h WHERE h.fund = s.fund)""").fetchall()
    # live books only: a dormant fund's archived book is never diffed
    f13 = [(f, pp, cp) for f, cp, pp in periods if cp and pp and pp < cp]
    try:
        npt = [(sid, pp, cp) for sid, pp, cp in conn.execute("""SELECT c.series_id, MAX(p.period), MAX(c.period)
            FROM nport_holdings c JOIN nport_prior p ON p.series_id = c.series_id
            GROUP BY c.series_id""") if pp and cp and pp < cp]
    except sqlite3.OperationalError:
        npt = []
    return f13, npt

def run():
    conn = sqlite3.connect(DB, timeout=120); conn.execute("PRAGMA busy_timeout=120000")
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS stock_splits (
      symbol TEXT, date TEXT, numerator REAL, denominator REAL, split_type TEXT,
      PRIMARY KEY (symbol, date));
    DROP TABLE IF EXISTS prior_split_factor;
    CREATE TABLE prior_split_factor (fund TEXT, ticker TEXT, factor REAL, PRIMARY KEY (fund, ticker));
    DROP TABLE IF EXISTS nport_split_factor;
    CREATE TABLE nport_split_factor (series_id TEXT, ticker TEXT, factor REAL, PRIMARY KEY (series_id, ticker));
    """)
    f13, npt = _windows(conn)
    if not (f13 or npt):
        print("no book has both periods on file — nothing to adjust")
        return 0
    start = min(pp for _, pp, _ in f13 + npt)
    end = max(cp for _, _, cp in f13 + npt)
    # the calendar in quarter-sized requests (one wide request can be capped)
    d0, n_rows, failed = dt.date.fromisoformat(start), 0, 0
    while d0.isoformat() < end:
        d1 = min(d0 + dt.timedelta(days=92), dt.date.fromisoformat(end))
        rows = _get("splits-calendar", **{"from": d0.isoformat(), "to": d1.isoformat()})
        if rows is None:
            failed += 1
        else:
            conn.executemany("INSERT OR REPLACE INTO stock_splits VALUES (?,?,?,?,?)",
                             [(r["symbol"], r["date"][:10], r.get("numerator"), r.get("denominator"),
                               r.get("splitType")) for r in rows
                              if r.get("symbol") and r.get("numerator") and r.get("denominator")])
            n_rows += len(rows)
        d0 = d1 + dt.timedelta(days=1)
    conn.commit()
    splits = {}
    for sym, d, num, den in conn.execute(
            "SELECT symbol, date, numerator, denominator FROM stock_splits WHERE date > ? AND date <= ?",
            (start, end)):
        splits.setdefault(sym, []).append((d, num / den))

    def factors(windows, prior_sql, table):
        out = []
        for key, pp, cp in windows:
            for (tk,) in conn.execute(prior_sql, (key,)):
                f = 1.0
                for d, r in splits.get(tk, ()):
                    if pp < d <= cp:
                        f *= r
                if abs(f - 1.0) > 1e-9:
                    out.append((key, tk, f))
        conn.executemany(f"INSERT OR REPLACE INTO {table} VALUES (?,?,?)", out)
        return out

    out = factors(f13, "SELECT DISTINCT ticker FROM fund_13f_prior WHERE fund=? AND ticker IS NOT NULL",
                  "prior_split_factor")
    out_n = factors(npt, "SELECT DISTINCT ticker FROM nport_prior WHERE series_id=? AND ticker IS NOT NULL",
                    "nport_split_factor")
    conn.commit()
    tks = sorted({(tk, round(f, 4)) for _, tk, f in out + out_n}, key=lambda x: -abs(x[1] - 1))
    print(f"splits calendar {start} -> {end}: {n_rows} rows{f' ({failed} requests failed)' if failed else ''}; "
          f"{len(out)} 13F and {len(out_n)} N-PORT prior books split-adjusted across "
          f"{len({t for t, _ in tks})} tickers: " + ", ".join(f"{t} x{f:g}" for t, f in tks[:12]))
    conn.close()
    return failed

if __name__ == "__main__":
    sys.exit(2 if run() else 0)
