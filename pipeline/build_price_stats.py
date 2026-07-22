"""Derive momentum / drawdown stats from the (previously dormant) prices table.

prices holds ~3 months of daily closes for ~815 tickers but was read by zero
pick renderers. This distills it into price_stats(ticker, mom_3mo, mom_20d,
off_high, last_close, asof) so the workbooks can show the entry-timing lens the
score lacks: a name -20% off its high with insiders buying is a very different
setup from one at highs.
"""
import os, sqlite3

DB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "cyclepapa.db")

def run():
    conn = sqlite3.connect(DB)
    conn.execute("""CREATE TABLE IF NOT EXISTS price_stats (
        ticker TEXT PRIMARY KEY, mom_3mo REAL, mom_20d REAL, off_high REAL,
        last_close REAL, n_pts INTEGER, asof TEXT)""")
    conn.execute("DELETE FROM price_stats")
    asof = conn.execute("SELECT MAX(date) FROM prices").fetchone()[0]
    series = {}
    for tk, close in conn.execute("SELECT ticker, close FROM prices WHERE close > 0 ORDER BY date"):
        series.setdefault(tk, []).append(close)
    n = 0
    for tk, pts in series.items():
        if len(pts) < 10:
            continue
        first, last, hi = pts[0], pts[-1], max(pts)
        mom_3mo = (last / first - 1) * 100 if first else None
        mom_20d = (last / pts[-20] - 1) * 100 if len(pts) >= 20 and pts[-20] else None
        off_high = (last / hi - 1) * 100 if hi else None
        conn.execute("INSERT OR REPLACE INTO price_stats VALUES (?,?,?,?,?,?,?)",
                     (tk, mom_3mo, mom_20d, off_high, last, len(pts), asof))
        n += 1
    conn.commit()
    print(f"price_stats: {n} tickers (as-of {asof})")
    conn.close()

if __name__ == "__main__":
    run()
