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
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build_cusip_map import debt_ticker

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
    # --- Lowkey desks: the PBs/swap entities activists actually use because
    # nobody watches them. Several are the SEPARATE swap subsidiary whose
    # parent's consolidated 13F hides the real book (BNPP Financial Markets
    # vs BNP Paribas's 333-row shell; SG Americas after SocGen's parent
    # stopped filing in 2016; Mizuho Markets Americas).
    "Jefferies":           "96223",
    "Royal Bank of Canada": "1000275",
    "Bank of Nova Scotia": "9631",
    "Bank of Montreal":    "927971",
    "Toronto-Dominion":    "947263",
    "Sumitomo Mitsui FG":  "1022837",
    "Mitsubishi UFJ FG":   "67088",
    "Macquarie Group":     "1418333",
    "Natixis":             "1274981",
    "BNPP Financial Mkts": "1166588",
    "SG Americas":         "1313360",
    "Mizuho Markets Amer": "1825516",
    "MUFG Securities Can": "1656187",
    "StoneX Group":        "913760",
    "Clear Street":        "1881567",
    "Daiwa Securities":    "1481045",
    "Marex Group":         "1997464",
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
        tkr = debt_ticker(tkr, r["cusip"])           # bond lines never pool with the stock
        out.append((broker, cik, acc, filed, qrank, r["issuer"], r["cusip"], tkr,
                    r["value_k"], r["shares"], r["type"]))
    # full-dollar filing (value/shares ~1000x the price). A one-line book counts
    # too: MUFG's 13F is just its strategic Morgan Stanley stake, filed in
    # dollars — booked as-is it put $78.8 TRILLION on MS.
    unit_fix = ((len(ratios) >= 2 and statistics.median(ratios) > 100)
                or (len(ratios) == 1 and ratios[0] > 100))
    for row in out:
        row = list(row)
        if unit_fix:
            row[8] = row[8] / 1000.0
        conn.execute("INSERT OR REPLACE INTO broker_13f VALUES (?,?,?,?,?,?,?,?,?,?,?)", row)
    conn.commit()
    return len(out)

def repair_units(conn):
    """Apply the full-dollar rule to books already stored (idempotent: once
    divided, a book's implied prices sit at ~1x and never re-trigger)."""
    px_map = {t: p for t, p in conn.execute("SELECT ticker, price FROM ticker_yf WHERE price > 0")}
    ratios = {}
    for broker, acc, tkr, v, sh, typ in conn.execute("""SELECT broker, accession, ticker,
            value_k, shares, sh_type FROM broker_13f WHERE value_k > 0 AND shares > 0"""):
        p = 1.0 if typ == "PRN" else px_map.get(tkr)
        if p:
            ratios.setdefault((broker, acc), []).append(v * 1000.0 / sh / p)
    fixed = []
    for (broker, acc), rs in ratios.items():
        if (len(rs) >= 2 and statistics.median(rs) > 100) or (len(rs) == 1 and rs[0] > 100):
            conn.execute("UPDATE broker_13f SET value_k = value_k / 1000.0 WHERE broker=? AND accession=?",
                         (broker, acc))
            fixed.append(f"{broker} {acc}")
    conn.commit()
    return fixed

def run():
    conn = sqlite3.connect(DB, timeout=60)
    conn.execute("PRAGMA busy_timeout=60000")
    init(conn)
    for f in repair_units(conn):
        print(f"  [unit] {f}: full-dollar book normalized to $k")
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
