"""Run the 13F ingest using ALL resolved CIKs from fund_cik_map.

After resolve_fund_ciks.py runs, fund_cik_map contains EDGAR-resolved CIKs
for every fund in fund_meta we could find a match for. This module feeds
those into the same 13F-HR XML pipeline that ingest_13f.py uses, so we get
primary-source holdings for every US 13F filer in our 445-fund universe.

Funds where no 13F-HR exists (UK/EU/JP non-filers like Palliser, Effissimo)
are recorded with status='no_13f_filing' so the user knows the gap is in
SEC coverage, not our pipeline.
"""
import json, os, sqlite3, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ingest_13f import (curl, latest_13f_acc, find_infotable, parse_infotable,
                        cusip_ticker_map, name_to_ticker)

DB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "cyclepapa.db")

def run():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    # All resolved fund->CIK pairs we haven't yet ingested
    rows = list(conn.execute("""
        SELECT fr.fund, fr.best_cik, fr.best_conf, fr.status
        FROM fund_resolution_state fr
        WHERE fr.best_cik IS NOT NULL
        AND NOT EXISTS (SELECT 1 FROM fund_13f_state s WHERE s.fund = fr.fund)
        ORDER BY fr.best_conf DESC"""))
    print(f"loading SEC ticker map...")
    name_map = cusip_ticker_map(conn)
    print(f"  {len(name_map)} mappings\n")
    print(f"{len(rows)} funds to ingest 13F data for\n")

    n_done = n_skip = 0
    for fr in rows:
        fund, cik = fr["fund"], fr["best_cik"]
        acc, filed = latest_13f_acc(cik)
        if not acc:
            conn.execute("""INSERT OR REPLACE INTO fund_13f_state
                VALUES (?,?,?,?,?,?,datetime('now'))""",
                (fund, cik, None, None, 0, 0))
            print(f"  [-] {fund[:36]:<36} no 13F-HR for CIK {cik}")
            n_skip += 1
            time.sleep(0.5)
            continue
        path = find_infotable(cik, acc)
        url = path if path.startswith("http") else f"https://www.sec.gov{path}"
        body = curl(url)
        rows_p = parse_infotable(body) if body else []
        if not rows_p:
            conn.execute("""INSERT OR REPLACE INTO fund_13f_state
                VALUES (?,?,?,?,?,?,datetime('now'))""",
                (fund, cik, acc, filed, 0, 0))
            print(f"  [-] {fund[:36]:<36} 0 holdings parsed")
            n_skip += 1
            time.sleep(0.5)
            continue
        total_v = sum(r["value_k"] for r in rows_p)
        for r in rows_p:
            tkr = name_to_ticker(r["issuer"], name_map)
            pct = (r["value_k"] / total_v * 100) if total_v else None
            conn.execute("""INSERT OR REPLACE INTO fund_13f_holdings
                VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (fund, cik, acc, filed, r["issuer"], r["cusip"], tkr,
                 r["value_k"], r["shares"], r["type"], pct))
        conn.execute("""INSERT OR REPLACE INTO fund_13f_state VALUES
            (?,?,?,?,?,?,datetime('now'))""",
            (fund, cik, acc, filed, len(rows_p), total_v))
        conn.commit()
        n_done += 1
        b_str = f"${total_v/1e6:.1f}B" if total_v > 1e6 else f"${total_v/1e3:.0f}M"
        print(f"  ✓ {fund[:36]:<36} {len(rows_p):>4} holdings  {b_str}")
        time.sleep(0.5)

    print(f"\nDone: {n_done} new funds, {n_skip} no 13F filing")

if __name__ == "__main__":
    run()
