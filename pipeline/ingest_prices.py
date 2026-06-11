"""Daily price + liquidity ingest from Yahoo chart API (verified reachable).

- updates candidates.price/price_asof/mcap_m (mcap via constant-shares derivation)
- stores 3mo daily closes in prices
- computes 20d ADV (shares + USD) and days-to-exit into liquidity   (roadmap #9)
Usage: python3 pipeline/ingest_prices.py [TICKER ...]   (default: all live tiers)
"""
import json, os, sqlite3, subprocess, sys, time

DB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "cyclepapa.db")
YH = "https://query1.finance.yahoo.com/v8/finance/chart/{sym}?range=3mo&interval=1d"
MAP = {'MTY.TO': 'MTY.TO', 'BZU.IM': 'BZU.MI', 'UA': 'UAA'}  # yahoo symbol quirks

def fetch(sym):
    url = YH.format(sym=MAP.get(sym, sym))
    out = subprocess.run(["curl", "-sk", "-m", "15", "-A", "Mozilla/5.0", url],
                         capture_output=True, text=True)
    try:
        j = json.loads(out.stdout)
        res = j["chart"]["result"][0]
        ts = res["timestamp"]
        q = res["indicators"]["quote"][0]
        rows = [(time.strftime("%Y-%m-%d", time.gmtime(t)), c, v)
                for t, c, v in zip(ts, q["close"], q["volume"]) if c]
        return rows
    except Exception as e:
        print(f"  {sym}: fetch failed ({e})")
        return None

def run(tickers=None):
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    if not tickers:
        tickers = [r["ticker"] for r in conn.execute(
            "SELECT ticker FROM candidates WHERE tier NOT IN ('DEAD','KILLED') AND verification_status NOT LIKE '%DEAD%'")]
    for t in tickers:
        rows = fetch(t)
        time.sleep(0.4)
        if not rows:
            continue
        conn.executemany("INSERT OR REPLACE INTO prices (ticker,date,close,volume) VALUES (?,?,?,?)",
                         [(t, d, c, v) for d, c, v in rows])
        last_date, last_close, _ = rows[-1]
        cur = conn.execute("SELECT price, mcap_m, shares_out_m FROM candidates WHERE ticker=?", (t,)).fetchone()
        if cur:
            shares = cur["shares_out_m"] or (cur["mcap_m"] / cur["price"] if cur["mcap_m"] and cur["price"] else None)
            new_mcap = round(shares * last_close, 1) if shares else cur["mcap_m"]
            conn.execute("""UPDATE candidates SET price=?, price_asof=?, mcap_m=?,
                            shares_out_m=COALESCE(shares_out_m,?), shares_method=COALESCE(shares_method,'derived')
                            WHERE ticker=?""", (last_close, last_date, new_mcap, shares, t))
        # liquidity: 20d ADV
        tail = rows[-20:]
        adv_sh = sum(v for _, _, v in tail if v) / max(1, len([v for _, _, v in tail if v]))
        adv_usd_m = adv_sh * last_close / 1e6
        mcap = conn.execute("SELECT mcap_m FROM candidates WHERE ticker=?", (t,)).fetchone()["mcap_m"]
        dte = round((0.01 * mcap) / (0.10 * adv_usd_m), 1) if (mcap and adv_usd_m) else None
        conn.execute("""INSERT OR REPLACE INTO liquidity (ticker,adv_shares,adv_usd_m,asof,days_to_exit_1pct_adv10)
                        VALUES (?,?,?,?,?)""", (t, round(adv_sh), round(adv_usd_m, 2), last_date, dte))
        print(f"  {t}: {last_close} ({last_date})  ADV ${adv_usd_m:.1f}M  exit-days {dte}")
    conn.commit()

if __name__ == '__main__':
    run(sys.argv[1:] or None)
