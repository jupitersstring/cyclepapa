"""Daily closes from FMP for every name the tracked funds hold or held.

The old daily series came from Yahoo and stopped on 2026-06-18 when Yahoo
began refusing requests: the broadsheet's trend lines and the entry-price
proxy (the year's 80th-percentile close) froze there. This fills `prices`
from FMP's end-of-day history (split-adjusted closes) from START on, for:
  every ticker in the current, prior and history 13F books, the N-PORT books,
  the scored common stocks, and SPY (the S&P 500 benchmark for track records).
Each symbol's series is cached a day in data/fmp_cache/prices/; later runs
fetch only the days since the cached series ends. A symbol FMP doesn't know
is skipped (reported), never booked with invented prices.
"""
import json, os, re, sqlite3, subprocess, sys, time
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from enrich_fmp import API, CACHE, DB, api_key

START = "2025-03-01"
PCACHE = os.path.join(CACHE, "prices")
BENCH = "SPY"

def _get(url):
    for attempt in range(6):
        body = subprocess.run(["curl", "-sS", "--max-time", "60", url], capture_output=True, text=True).stdout
        if "Limit Reach" in body:
            time.sleep(15 * (attempt + 1))
            continue
        try:
            return json.loads(body)
        except ValueError:
            time.sleep(2)
    return None

def series(sym):
    """[(date, close, volume)] from START, from the cache topped up with FMP."""
    os.makedirs(PCACHE, exist_ok=True)
    fn = os.path.join(PCACHE, re.sub(r"[^A-Za-z0-9._-]", "_", sym) + ".json")
    cached = []
    if os.path.exists(fn):
        cached = json.load(open(fn))
        if time.time() - os.path.getmtime(fn) < 20 * 3600:
            return cached, "cache"
    since = cached[-1][0] if cached else START
    data = _get(f"{API}/historical-price-eod/light?symbol={sym}&from={since}&apikey={api_key()}")
    if data is None:
        return cached, "failed"
    if not isinstance(data, list):
        return cached, "unknown"
    new = sorted((d["date"], d.get("price"), d.get("volume")) for d in data
                 if d.get("date") and d.get("price") is not None)
    merged = {d: (c, v) for d, c, v in cached}
    merged.update({d: (c, v) for d, c, v in new})
    out = sorted((d, c, v) for d, (c, v) in merged.items() if d >= START)
    json.dump(out, open(fn, "w"))
    return out, ("fetched" if new else "empty")

def universe(conn):
    tk = {BENCH}
    for q in ("SELECT DISTINCT ticker FROM fund_13f_holdings WHERE ticker IS NOT NULL",
              "SELECT DISTINCT ticker FROM fund_13f_prior WHERE ticker IS NOT NULL",
              "SELECT DISTINCT ticker FROM fund_13f_history WHERE ticker IS NOT NULL",
              "SELECT DISTINCT ticker FROM nport_holdings WHERE ticker IS NOT NULL",
              "SELECT ticker FROM unified_signal WHERE sec_type = 'common'"):
        try:
            tk |= {r[0] for r in conn.execute(q)}
        except sqlite3.OperationalError:
            pass
    return sorted(t for t in tk if t and " " not in t and len(t) <= 16)

def run():
    conn = sqlite3.connect(DB, timeout=120); conn.execute("PRAGMA busy_timeout=120000")
    syms = universe(conn)
    print(f"prices: {len(syms):,} symbols from {START}", flush=True)
    stats, rows_written, t0 = {}, 0, time.time()
    with ThreadPoolExecutor(8) as ex:
        for i, (sym, (ser, how)) in enumerate(zip(syms, ex.map(series, syms)), 1):
            stats[how] = stats.get(how, 0) + 1
            if ser:
                conn.executemany("INSERT OR REPLACE INTO prices (ticker, date, close, volume) VALUES (?,?,?,?)",
                                 [(sym, d, c, v) for d, c, v in ser])
                rows_written += len(ser)
            if i % 500 == 0:
                conn.commit()
                print(f"  {i:,}/{len(syms):,} symbols ({time.time() - t0:.0f}s)", flush=True)
    conn.commit()
    last = conn.execute("SELECT MAX(date) FROM prices WHERE ticker = ?", (BENCH,)).fetchone()[0]
    print(f"prices: {rows_written:,} closes written; {', '.join(f'{k} {v:,}' for k, v in sorted(stats.items()))}; "
          f"latest {BENCH} close {last}", flush=True)
    conn.close()
    return 2 if stats.get("failed", 0) > 0.05 * len(syms) else 0

if __name__ == "__main__":
    sys.exit(run())
