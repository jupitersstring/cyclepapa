"""Earnings-surprise history from FMP (bulk, one call per year).

For every ticker in the universe: EPS actual vs consensus for each reported
quarter, then a per-ticker scorecard over the last 8 reported quarters —
beat rate, last surprise, current beat streak. Lets the books answer "does
smart money pick companies that beat?" with data instead of anecdote.

Tables:
  earnings_surprise(ticker, date, eps_actual, eps_est, surprise_pct)
  earnings_beat(ticker, n_q, beats, beat_rate, last_date, last_surprise_pct, streak)
"""
import os, sqlite3, sys, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from enrich_fmp import fetch_csv, cached_bulk, num, DB

def run(years=None):
    years = years or [int(time.strftime("%Y")) - 2, int(time.strftime("%Y")) - 1, int(time.strftime("%Y"))]
    conn = sqlite3.connect(DB, timeout=120)
    conn.execute("PRAGMA busy_timeout=120000")
    conn.executescript("""
    DROP TABLE IF EXISTS earnings_surprise;
    CREATE TABLE earnings_surprise (ticker TEXT, date TEXT, eps_actual REAL, eps_est REAL,
                                    surprise_pct REAL, PRIMARY KEY (ticker, date));
    DROP TABLE IF EXISTS earnings_beat;
    CREATE TABLE earnings_beat (ticker TEXT PRIMARY KEY, n_q INTEGER, beats INTEGER,
        beat_rate REAL, last_date TEXT, last_surprise_pct REAL, streak INTEGER);
    """)
    universe = {r[0] for r in conn.execute("""
        SELECT ticker FROM unified_signal
        UNION SELECT ticker FROM fund_13f_holdings WHERE ticker IS NOT NULL""")}
    today = time.strftime("%Y-%m-%d")
    n = 0
    for y in years:
        for r in cached_bulk(f"earnings_{y}", lambda y=y: fetch_csv("earnings-surprises-bulk", year=y)):
            tk = r.get("symbol")
            a, e = num(r.get("epsActual")), num(r.get("epsEstimated"))
            d = r.get("date") or ""
            if tk not in universe or a is None or e is None or not d or d > today:
                continue
            sp = (a - e) / abs(e) * 100 if abs(e) >= 0.01 else None
            conn.execute("INSERT OR REPLACE INTO earnings_surprise VALUES (?,?,?,?,?)",
                         (tk, d, a, e, round(sp, 1) if sp is not None else None))
            n += 1
    by = {}
    for tk, d, a, e, sp in conn.execute(
            "SELECT ticker, date, eps_actual, eps_est, surprise_pct FROM earnings_surprise ORDER BY ticker, date DESC"):
        by.setdefault(tk, []).append((d, a, e, sp))
    for tk, qs in by.items():
        qs = qs[:8]
        beat = [a > e + 1e-9 for _, a, e, _ in qs]
        streak = 0
        for b in beat:
            if not b:
                break
            streak += 1
        conn.execute("INSERT INTO earnings_beat VALUES (?,?,?,?,?,?,?)",
                     (tk, len(qs), sum(beat), round(sum(beat) / len(qs), 3),
                      qs[0][0], qs[0][3], streak))
    conn.commit()
    print(f"earnings_surprise: {n:,} quarter-rows; earnings_beat: {len(by):,} tickers")
    conn.close()

if __name__ == "__main__":
    run()
