"""Earnings-surprise history from FMP: EPS AND revenue, actual vs consensus.

For every common stock in the universe that FMP prices: each reported quarter's
EPS and revenue against the consensus estimate, then a per-ticker scorecard over
the last 8 reported quarters — EPS beat rate, revenue beat rate, last surprise,
current beat streak. Lets the books answer "does smart money pick companies that
beat?" with data instead of anecdote. Revenue matters on its own: growth names
often miss on EPS while beating on sales (TBBB Q2: EPS -0.19 vs -0.156, revenue
$1.49B vs $1.42B).

Source: the per-symbol `earnings` endpoint (EPS + revenue), fetched in parallel
and cached for the day in data/fmp_cache/earnings_by_symbol.csv. If that pass
fails, the EPS-only bulk file (`earnings-surprises-bulk`, one call per year)
fills in.

Tables:
  earnings_surprise(ticker, date, eps_actual, eps_est, surprise_pct,
                    rev_actual, rev_est, rev_surprise_pct)
  earnings_beat(ticker, n_q, beats, beat_rate, last_date, last_surprise_pct,
                streak, rev_n, rev_beats, last_rev_surprise_pct)
"""
import csv, json, os, sqlite3, subprocess, sys, time
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from enrich_fmp import API, CACHE, DB, api_key, cached_bulk, fetch_csv, num

FIELDS = ["symbol", "date", "epsActual", "epsEstimated", "revenueActual", "revenueEstimated"]

def _one(sym, key):
    url = f"{API}/earnings?symbol={sym}&limit=12&apikey={key}"
    for attempt in range(4):
        r = subprocess.run(["curl", "-sS", "--max-time", "60", url], capture_output=True, text=True)
        try:
            d = json.loads(r.stdout)
            if isinstance(d, list):
                return [{k: x.get(k) for k in FIELDS} for x in d]
        except ValueError:
            pass
        time.sleep(2 * (attempt + 1))      # throttled / transient: back off, never "no data"
    return None

def per_symbol(symbols, max_age_h=20):
    """{symbol: rows} for every symbol, via the day's cache when fresh."""
    os.makedirs(CACHE, exist_ok=True)
    path = os.path.join(CACHE, "earnings_by_symbol.csv")
    have = {}
    if os.path.exists(path) and time.time() - os.path.getmtime(path) < max_age_h * 3600:
        for r in csv.DictReader(open(path)):
            have.setdefault(r["symbol"], []).append(r)
    todo = [s for s in symbols if s not in have]
    if todo:
        key = api_key()
        with ThreadPoolExecutor(8) as ex:
            got = list(ex.map(lambda s: (s, _one(s, key)), todo))
        failed = [s for s, rows in got if rows is None]
        for s, rows in got:
            if rows is not None:
                have[s] = rows or [{"symbol": s}]          # empty marker: asked, FMP has none
        with open(path, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=FIELDS)
            w.writeheader()
            for rows in have.values():
                w.writerows(rows)
        print(f"  per-symbol: fetched {len(todo) - len(failed):,}, failed {len(failed):,}", flush=True)
    return have

def bulk_eps(years):
    """EPS-only fallback: one bulk file per year (rate-limited, so cached)."""
    out = {}
    for y in years:
        for r in cached_bulk(f"earnings_{y}", lambda y=y: fetch_csv("earnings-surprises-bulk", year=y)):
            out.setdefault(r.get("symbol"), []).append(r)
    return out

def pct(a, e):
    return round((a - e) / abs(e) * 100, 1) if (a is not None and e is not None and abs(e) >= 0.01) else None

def run():
    conn = sqlite3.connect(DB, timeout=120)
    conn.execute("PRAGMA busy_timeout=120000")
    fund_col = any(r[1] == "is_fund" for r in conn.execute("PRAGMA table_info(ticker_yf)"))
    universe = sorted({r[0] for r in conn.execute(f"""
        SELECT y.ticker FROM ticker_yf y
        WHERE y.src = 'fmp' {'AND COALESCE(y.is_fund, 0) = 0' if fund_col else ''}
          AND y.ticker IN (SELECT ticker FROM unified_signal WHERE sec_type = 'common'
                           UNION SELECT ticker FROM fund_13f_holdings WHERE ticker IS NOT NULL)""")})
    today = time.strftime("%Y-%m-%d")
    print(f"earnings for {len(universe):,} FMP-priced common stocks", flush=True)
    try:
        src = per_symbol(universe)
    except Exception as e:                  # network / key trouble: EPS-only bulk instead
        print(f"  ! per-symbol pass failed ({str(e)[:80]}) — falling back to bulk EPS")
        y = int(today[:4])
        src = bulk_eps([y - 2, y - 1, y])
    # fetch everything BEFORE touching the tables: a failed download must leave
    # the last good scorecard in place, never an empty one
    rows = {}
    for tk in universe:
        for r in src.get(tk, []):
            a, e = num(r.get("epsActual")), num(r.get("epsEstimated"))
            ra, re_ = num(r.get("revenueActual")), num(r.get("revenueEstimated"))
            d = r.get("date") or ""
            if not d or d > today or (a is None and ra is None):
                continue                    # future / unreported quarter
            rows[(tk, d)] = (tk, d, a, e, pct(a, e), ra, re_, pct(ra, re_))
    if not rows:
        raise SystemExit("no earnings rows fetched — keeping the existing tables")
    conn.executescript("""
    DROP TABLE IF EXISTS earnings_surprise;
    CREATE TABLE earnings_surprise (ticker TEXT, date TEXT, eps_actual REAL, eps_est REAL,
        surprise_pct REAL, rev_actual REAL, rev_est REAL, rev_surprise_pct REAL,
        PRIMARY KEY (ticker, date));
    DROP TABLE IF EXISTS earnings_beat;
    CREATE TABLE earnings_beat (ticker TEXT PRIMARY KEY, n_q INTEGER, beats INTEGER,
        beat_rate REAL, last_date TEXT, last_surprise_pct REAL, streak INTEGER,
        rev_n INTEGER, rev_beats INTEGER, last_rev_surprise_pct REAL);
    """)
    conn.executemany("INSERT INTO earnings_surprise VALUES (?,?,?,?,?,?,?,?)", rows.values())
    by = {}
    for r in sorted(rows.values(), key=lambda r: (r[0], r[1]), reverse=True):
        by.setdefault(r[0], []).append(r)
    n_beat = 0
    for tk, qs in by.items():
        qs = qs[:8]                                          # last 8 reported quarters
        eq = [q for q in qs if q[2] is not None and q[3] is not None]
        rq = [q for q in qs if q[5] is not None and q[6] is not None]
        beat = [q[2] > q[3] + 1e-9 for q in eq]
        streak = 0
        for b in beat:
            if not b:
                break
            streak += 1
        if not eq and not rq:
            continue
        conn.execute("INSERT INTO earnings_beat VALUES (?,?,?,?,?,?,?,?,?,?)", (
            tk, len(eq), sum(beat), round(sum(beat) / len(eq), 3) if eq else None,
            qs[0][1], eq[0][4] if eq else None, streak,
            len(rq), sum(q[5] > q[6] for q in rq), rq[0][7] if rq else None))
        n_beat += 1
    conn.commit()
    print(f"earnings_surprise: {len(rows):,} quarter-rows; earnings_beat: {n_beat:,} tickers")
    conn.close()

if __name__ == "__main__":
    run()
