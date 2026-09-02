"""Final 13F integrity pass: 2 remaining cross-wires + duplicate-fund collapse.

  - Gotham Asset Management (Greenblatt) was wired to RA Capital's CIK (showing
    RA's biotech book). Re-ingest at Gotham's own CIK 1510387.
  - 180 Degree Capital Corp is a closed-end fund (files N-PORT, not 13F); its
    rows were Wynnefield's (shared CIK 1251567). Delete the junk 13F holdings;
    its curated positions remain.
  - 15 same-manager NAME VARIANTS share one CIK (Pershing Square x4, Greenlight
    x3, Soros/Coatue/Tiger Global/etc x2). Identical books under >1 fund name
    multi-count a manager in smart_money_n. Collapse each CIK's 13F holdings to
    a single canonical fund (the variant with the most curated positions); the
    duplicates keep their curated fund_positions but drop the redundant 13F rows.
"""
import os, sqlite3, statistics, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ingest_13f import (latest_13f_acc, find_infotable, parse_infotable, curl,
                        cusip_ticker_map, name_to_ticker)

DB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "cyclepapa.db")

def reingest(conn, fund, cik, cusip2tkr, name_map):
    acc, filed = latest_13f_acc(str(cik))
    if not acc: return 0
    path = find_infotable(str(cik), acc)
    url = path if path.startswith("http") else "https://www.sec.gov" + path
    rows = parse_infotable(curl(url))
    if not rows: return 0
    agg = {}
    for r in rows:
        k = (r["cusip"], r["type"])
        a = agg.get(k) or agg.setdefault(k, {"issuer": r["issuer"], "value_k": 0, "shares": 0})
        a["value_k"] += r["value_k"]; a["shares"] += r["shares"]
    long_total = sum(a["value_k"] for (cu, ty), a in agg.items() if ty in ("SH", "", None))
    vals = [a["value_k"] for a in agg.values() if a["value_k"] > 0]
    scale = 1000.0 if (vals and statistics.median(vals) > 5_000_000) else 1.0
    conn.execute("DELETE FROM fund_13f_holdings WHERE fund=?", (fund,))
    for (cusip, ty), a in agg.items():
        tkr = cusip2tkr.get(cusip) or name_to_ticker(a["issuer"], name_map)
        pct = (a["value_k"] / long_total * 100) if (ty in ("SH", "", None) and long_total > 0) else None
        conn.execute("INSERT OR REPLACE INTO fund_13f_holdings VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (fund, str(cik), acc, filed, a["issuer"], cusip, tkr, a["value_k"] / scale, a["shares"], ty, pct))
    conn.execute("INSERT OR REPLACE INTO fund_13f_state VALUES (?,?,?,?,?,?,datetime('now'))",
        (fund, str(cik), acc, filed, len(agg), long_total / scale))
    conn.execute("UPDATE fund_resolution_state SET best_cik=? WHERE fund=?", (str(cik), fund))
    return len(agg)

def run():
    conn = sqlite3.connect(DB); conn.execute("PRAGMA busy_timeout=60000")
    cusip2tkr = {r[0]: r[1] for r in conn.execute(
        "SELECT cusip, ticker FROM fund_13f_holdings WHERE ticker IS NOT NULL AND cusip IS NOT NULL GROUP BY cusip")}
    name_map = cusip_ticker_map(conn)

    # 1. Gotham cross-wire -> correct CIK
    gotham = [r[0] for r in conn.execute("SELECT DISTINCT fund FROM fund_13f_holdings WHERE fund LIKE 'Gotham Asset%'")]
    for f in gotham:
        n = reingest(conn, f, "1510387", cusip2tkr, name_map)
        print(f"  Gotham re-ingest {f!r} @1510387 -> {n} holdings")
    conn.commit()

    # 2. 180 Degree Capital is not a 13F filer -> drop junk 13F rows (keep curated)
    for f in [r[0] for r in conn.execute("SELECT DISTINCT fund FROM fund_13f_holdings WHERE fund LIKE '180 Degree%'")]:
        n = conn.execute("DELETE FROM fund_13f_holdings WHERE fund=?", (f,)).rowcount
        conn.execute("DELETE FROM fund_13f_state WHERE fund=?", (f,))
        conn.execute("UPDATE fund_resolution_state SET best_cik='' WHERE fund=?", (f,))
        print(f"  180 Degree junk-deleted {f!r}: {n} rows")
    conn.commit()

    # 3. collapse same-CIK name variants to one canonical fund
    groups = conn.execute("""SELECT cik, COUNT(DISTINCT fund) nf
        FROM fund_13f_holdings WHERE cik IS NOT NULL AND cik!=''
        GROUP BY cik HAVING nf>1""").fetchall()
    collapsed = 0
    for cik, nf in groups:
        variants = [r[0] for r in conn.execute(
            "SELECT DISTINCT fund FROM fund_13f_holdings WHERE cik=?", (cik,))]
        def score(f):
            fp = conn.execute("SELECT COUNT(*) FROM fund_positions WHERE fund=?", (f,)).fetchone()[0]
            hd = conn.execute("SELECT COUNT(*) FROM fund_13f_holdings WHERE fund=?", (f,)).fetchone()[0]
            return (fp, hd, len(f))
        canonical = max(variants, key=score)
        for v in variants:
            if v == canonical: continue
            n = conn.execute("DELETE FROM fund_13f_holdings WHERE fund=?", (v,)).rowcount
            conn.execute("DELETE FROM fund_13f_state WHERE fund=?", (v,))
            collapsed += 1
            print(f"  collapse cik={cik}: drop {v!r} ({n} dup 13F rows) -> keep {canonical!r}")
    conn.commit()
    print(f"\ndone: collapsed {collapsed} duplicate fund entries across {len(groups)} CIKs")

if __name__ == "__main__":
    run()
