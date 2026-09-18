"""Backtest the signal stack against historical setups (roadmap #5).

We take a curated set of past (entry-date, ticker) tuples that WOULD have
matched the framework (smart-money-underwater + dated catalyst + insider/
activist Form 4 cluster), then pull historical closes from Yahoo and measure
forward returns at 6/12/18mo vs SPY benchmark.

Quotes the base rate against which any new Tier 1 should be judged.
"""
import json, os, sqlite3, subprocess, sys, time
from datetime import datetime, timedelta

DB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "cyclepapa.db")

# Curated historical events — each one would have fired our 5-criteria stack
# at the date shown. Bucket maps to which sub-signal dominated.
EVENTS = [
    # CEO/founder open-market buy at multi-year low
    ("ROL",  "founder_buy",   "2020-03-18", "Rollins Family Trust +$50M buy COVID low"),
    ("WLY",  "founder_buy",   "2023-11-09", "Wiley insiders bought low"),
    ("SYF",  "founder_buy",   "2018-12-26", "Cooperman + insiders into year-end low"),
    ("APO",  "founder_buy",   "2023-03-23", "Marc Rowan SVB-era buy"),
    ("EFX",  "founder_buy",   "2022-10-13", "CEO Begor open-market at $160"),
    # Activist 13D / cash bid / sale process
    ("BBBY", "activist_13d",  "2022-03-07", "Ryan Cohen 13D ~9.8%"),  # disaster - keep in
    ("HBI",  "activist_13d",  "2024-02-08", "Barington 13D + sale push"),
    ("PINS", "activist_13d",  "2022-07-20", "Elliott 13D"),
    ("DXC",  "activist_13d",  "2021-01-12", "Atlas/Apollo cash bid"),
    ("KSS",  "activist_13d",  "2022-01-21", "Macellum + Acacia bid"),
    ("MCRB", "activist_13d",  "2023-11-29", "Flagship buyout"),
    ("YELP", "activist_13d",  "2022-04-29", "TCS Capital 13D"),
    ("FIVN", "activist_13d",  "2023-05-22", "Anson Funds 13D"),
    # Cash bid rejected
    ("KSS",  "bid_rejected",  "2022-06-15", "Franchise Group raised then deal off"),
    ("EBIX", "bid_rejected",  "2019-12-23", "Eberg consortium bid"),
    # Sale process announced
    ("CWH",  "sale_process",  "2024-09-13", "strategic review"),
    ("LOGM", "sale_process",  "2019-11-04", "Vista take-private"),
    ("ANGI", "sale_process",  "2024-08-13", "IAC strategic review"),
    # Insider Form 4 cluster
    ("META", "insider_cluster","2022-11-09", "Zuckerberg + others post-crash"),
    ("PYPL", "insider_cluster","2023-11-01", "Chriss appointment + buys"),
    # Multi-fund underwater + Form 4 (analog to PRLD/INMD setups)
    ("ACHC", "smart_money_uw","2022-06-15", "multi-fund + activist DOJ-era"),
    ("OPK",  "smart_money_uw","2024-02-15", "Frost insider concentration"),
]

YH = "https://query1.finance.yahoo.com/v8/finance/chart/{sym}?range=5y&interval=1d"

def fetch(sym):
    out = subprocess.run(["curl", "-sk", "-m", "20", "-A", "Mozilla/5.0", YH.format(sym=sym)],
                         capture_output=True, text=True)
    try:
        j = json.loads(out.stdout)
        res = j["chart"]["result"][0]
        return [(time.strftime("%Y-%m-%d", time.gmtime(t)), c)
                for t, c in zip(res["timestamp"], res["indicators"]["quote"][0]["close"]) if c]
    except Exception:
        return []

def close_on_or_after(rows, target):
    for d, c in rows:
        if d >= target: return d, c
    return None, None

def close_on_or_before(rows, target):
    last = (None, None)
    for d, c in rows:
        if d > target: break
        last = (d, c)
    return last

def add_days(d, n):
    return (datetime.strptime(d, "%Y-%m-%d") + timedelta(days=n)).strftime("%Y-%m-%d")

def run():
    conn = sqlite3.connect(DB)
    conn.executescript("DELETE FROM backtest_events; DELETE FROM backtest_results;")
    cache = {}
    for sym in {e[0] for e in EVENTS} | {"SPY"}:
        print(f"  fetching {sym}...")
        cache[sym] = fetch(sym); time.sleep(0.4)

    spy = cache["SPY"]
    print("\nresults:")
    print(f"{'tkr':<6} {'bucket':<18} {'entry':<11} {'ret6m':<8} {'ret12m':<8} {'ret18m':<8} {'sp6':<7} {'sp12':<7} {'ex6m':<8} {'ex12m':<8}")
    for tkr, bucket, edate, desc in EVENTS:
        rows = cache.get(tkr) or []
        if not rows:
            print(f"  {tkr}: no data"); continue
        e_d, e_p = close_on_or_after(rows, edate)
        if not e_p: continue
        out = {}
        for n_days, label in [(180, "6m"), (365, "12m"), (540, "18m")]:
            _, ep = close_on_or_before(rows, add_days(e_d, n_days))
            _, sp = close_on_or_before(spy, add_days(e_d, n_days))
            _, sb = close_on_or_after(spy, edate)
            out[f"ret_{label}"] = (ep/e_p - 1) if ep else None
            out[f"spy_{label}"] = (sp/sb - 1) if (sp and sb) else None
            out[f"ex_{label}"]  = (out[f"ret_{label}"] - out[f"spy_{label}"]) if (out[f"ret_{label}"] is not None and out[f"spy_{label}"] is not None) else None
        cur = conn.execute("""INSERT INTO backtest_events (ticker,bucket,event_date,description)
                              VALUES (?,?,?,?)""", (tkr, bucket, edate, desc))
        eid = cur.lastrowid
        conn.execute("""INSERT INTO backtest_results
            (event_id,entry_date,entry_px,ret_6m,ret_12m,ret_18m,spy_6m,spy_12m,spy_18m,
             excess_6m,excess_12m,excess_18m)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (eid, e_d, e_p, out["ret_6m"], out["ret_12m"], out["ret_18m"],
             out["spy_6m"], out["spy_12m"], out["spy_18m"],
             out["ex_6m"], out["ex_12m"], out["ex_18m"]))
        fmt = lambda x: f"{x*100:+6.1f}%" if x is not None else "  n/a "
        print(f"  {tkr:<6} {bucket:<18} {e_d:<11} {fmt(out['ret_6m'])} {fmt(out['ret_12m'])} {fmt(out['ret_18m'])} {fmt(out['spy_6m'])} {fmt(out['spy_12m'])} {fmt(out['ex_6m'])} {fmt(out['ex_12m'])}")
    conn.commit()
    summary(conn)

def summary(conn):
    print("\nBASE RATES BY BUCKET (excess vs SPY):")
    for bucket, in conn.execute("SELECT DISTINCT bucket FROM backtest_events"):
        rows = conn.execute("""SELECT r.excess_12m, r.excess_18m FROM backtest_results r
                               JOIN backtest_events e ON e.id=r.event_id WHERE e.bucket=?""", (bucket,)).fetchall()
        valid12 = [x for x, _ in rows if x is not None]
        valid18 = [x for _, x in rows if x is not None]
        if not valid12: continue
        hit12 = sum(1 for x in valid12 if x > 0) / len(valid12)
        avg12 = sum(valid12) / len(valid12)
        med12 = sorted(valid12)[len(valid12)//2]
        avg18 = (sum(valid18) / len(valid18)) if valid18 else None
        print(f"  {bucket:<18} n={len(valid12):>2}  hit-rate 12m {hit12*100:.0f}%  avg ex {avg12*100:+.1f}%  med {med12*100:+.1f}%  avg ex 18m {avg18*100:+.1f}%" if avg18 is not None else f"  {bucket:<18} n={len(valid12):>2}  hit-rate 12m {hit12*100:.0f}%  avg ex {avg12*100:+.1f}%  med {med12*100:+.1f}%")
    overall = conn.execute("SELECT excess_12m FROM backtest_results WHERE excess_12m IS NOT NULL").fetchall()
    if overall:
        v = [x[0] for x in overall]
        print(f"\n  OVERALL n={len(v)}  hit-rate 12m {sum(1 for x in v if x>0)/len(v)*100:.0f}%  avg excess {sum(v)/len(v)*100:+.1f}%  median {sorted(v)[len(v)//2]*100:+.1f}%")

if __name__ == "__main__":
    run()
