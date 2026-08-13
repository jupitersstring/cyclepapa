"""Swap-desk broker 13F ingest — the hidden-activist radar feed.

An activist building via total-return swaps appears on NO 13F/13D of their
own (cash-settled swaps), but the counterparty desk hedges by buying the
physical shares — which print in the BROKER's 13F. A large single-broker
share-count jump in a mid-cap (UBS +31M CCC the day their Q2 13F hit) is
therefore a candidate swap-hedge footprint for an undisclosed stake.

Brokers are stored in their OWN tables (broker_13f / broker_13f_state) and
are NEVER counted as smart money — their books are custody + market-making
+ index inventory. The signal is the QoQ DELTA, not the level, and even the
delta is only suggestive: ETF create/redeem baskets, index rebalances, and
ordinary client flows move these books too. broker_swap_radar.py applies the
filters (mid-cap, idiosyncratic, large vs shares out) and joins activist
context.
"""
import os, sqlite3, statistics, sys, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ingest_13f as m

DB = m.DB

# Big equity-swap counterparty desks with active 13F-HR programs (verified
# 2026-08). SocGen stopped filing 13F-HR in 2016 — excluded.
BROKER_CIK = {
    "UBS Group AG":        "1610520",
    "Goldman Sachs Group": "886982",
    "Morgan Stanley":      "895421",
    "JPMorgan Chase":      "19617",
    "Bank of America":     "70858",
    "Citigroup":           "831001",
    "Barclays PLC":        "312069",
    "BNP Paribas":         "872786",
    "Nomura Holdings":     "1163653",
    "Deutsche Bank AG":    "948046",
    "Wells Fargo":         "72971",
}

def curl_big(url, timeout=240):
    """Broker infotables run 10-100MB — the standard 20s curl gives up."""
    import subprocess
    out = subprocess.run(["curl", "-sk", "--compressed", "-m", str(timeout),
                          "-A", m.UA, url], capture_output=True).stdout
    return out

def init(conn):
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS broker_13f (
      broker TEXT, cik TEXT, accession TEXT, filed TEXT, qrank INTEGER,
      issuer TEXT, cusip TEXT, ticker TEXT, value_k REAL, shares INTEGER,
      sh_type TEXT,
      PRIMARY KEY (broker, accession, cusip));
    CREATE INDEX IF NOT EXISTS idx_broker13f_tk ON broker_13f(ticker);
    CREATE TABLE IF NOT EXISTS broker_13f_state (
      broker TEXT PRIMARY KEY, cik TEXT,
      cur_accession TEXT, cur_filed TEXT,
      prior_accession TEXT, prior_filed TEXT,
      n_cur INTEGER, n_prior INTEGER, asof TEXT);
    """)

def ingest_accession(conn, broker, cik, acc, filed, qrank, cusip_map, name_map, px_map):
    if conn.execute("SELECT 1 FROM broker_13f WHERE broker=? AND accession=? LIMIT 1",
                    (broker, acc)).fetchone():
        # rank may have shifted (prior quarter's latest is this quarter's prior)
        conn.execute("UPDATE broker_13f SET qrank=? WHERE broker=? AND accession=?",
                     (qrank, broker, acc))
        return conn.execute("SELECT COUNT(*) FROM broker_13f WHERE broker=? AND accession=?",
                            (broker, acc)).fetchone()[0]
    path = m.find_infotable(cik, acc)
    if not path:
        print(f"  [-] {broker}: no infotable in {acc}")
        return 0
    url = path if path.startswith("http") else f"https://www.sec.gov{path}"
    body = curl_big(url)
    if not body:
        print(f"  [-] {broker}: infotable fetch failed for {acc}")
        return 0
    rows = m.parse_infotable(body)
    rows = [r for r in rows if not r.get("put_call")]
    rows = [r for r in rows if r["value_k"] or r["shares"]]
    # aggregate multi-line (per-desk / per-account) entries by CUSIP
    agg = {}
    for r in rows:
        a = agg.get(r["cusip"])
        if a is None:
            agg[r["cusip"]] = dict(r)
        else:
            a["value_k"] += r["value_k"]
            a["shares"]  += r["shares"]
    rows = list(agg.values())
    ratios = []
    out = []
    for r in rows:
        cusip_ok = r["cusip"] and len(r["cusip"]) == 9 and len(set(r["cusip"])) > 1
        cm = cusip_map.get(r["cusip"]) if cusip_ok else None
        tkr = (cm[0] if cm[1] != "etf" else None) if cm is not None \
            else m.name_to_ticker(r["issuer"], name_map)
        p = 1.0 if r["type"] == "PRN" else px_map.get(tkr)
        if p and r["shares"] and r["value_k"]:
            ratios.append((r["value_k"] * 1000.0 / r["shares"]) / p)
        out.append((broker, cik, acc, filed, qrank, r["issuer"], r["cusip"], tkr,
                    r["value_k"], r["shares"], r["type"]))
    unit_fix = len(ratios) >= 2 and statistics.median(ratios) > 100
    for row in out:
        row = list(row)
        if unit_fix:
            row[8] = row[8] / 1000.0
        conn.execute("INSERT OR REPLACE INTO broker_13f VALUES (?,?,?,?,?,?,?,?,?,?,?)", row)
    conn.commit()
    return len(out)

def run():
    conn = sqlite3.connect(DB, timeout=60)
    conn.execute("PRAGMA busy_timeout=60000")
    init(conn)
    name_map = m.cusip_ticker_map(conn)
    cusip_map = {c: (tk, st) for c, tk, st in
                 conn.execute("SELECT cusip, ticker, sec_type FROM cusip_map")}
    px_map = {t: p for t, p in conn.execute(
        "SELECT ticker, price FROM ticker_yf WHERE price > 0")}
    asof = time.strftime("%Y-%m-%d")
    for broker, cik in BROKER_CIK.items():
        accs = m.list_13f_accs(cik, k=2)
        if not accs or not accs[0][0]:
            print(f"  [-] {broker}: no 13F-HR found")
            continue
        (cur_acc, cur_filed) = accs[0]
        (pri_acc, pri_filed) = accs[1] if len(accs) > 1 else (None, None)
        # drop rows from accessions we no longer track (rolled off)
        keep = [a for a in (cur_acc, pri_acc) if a]
        ph = ",".join("?" * len(keep))
        conn.execute(f"DELETE FROM broker_13f WHERE broker=? AND accession NOT IN ({ph})",
                     [broker] + keep)
        n_cur = ingest_accession(conn, broker, cik, cur_acc, cur_filed, 0,
                                 cusip_map, name_map, px_map)
        n_pri = 0
        if pri_acc:
            n_pri = ingest_accession(conn, broker, cik, pri_acc, pri_filed, 1,
                                     cusip_map, name_map, px_map)
        conn.execute("INSERT OR REPLACE INTO broker_13f_state VALUES (?,?,?,?,?,?,?,?,?)",
                     (broker, cik, cur_acc, cur_filed, pri_acc, pri_filed,
                      n_cur, n_pri, asof))
        conn.commit()
        print(f"  ✓ {broker:22s} cur {cur_filed} ({n_cur:6d} pos)  "
              f"prior {pri_filed} ({n_pri:6d} pos)")
        time.sleep(0.5)
    conn.close()

if __name__ == "__main__":
    run()
