"""Refresh 13F holdings to each fund's LATEST 13F-HR.

The original ingester (ingest_13f_resolved) skips funds already in
fund_13f_state, so any fund that filed a newer 13F after its first ingest was
stuck on stale holdings. This re-checks every known 13F CIK against EDGAR's
latest 13F-HR accession and, when it differs, re-parses the full information
table and REPLACES that fund's holdings. Sharded for speed; the latest-accession
probe runs in worker threads, all DB writes are serialized in the main thread.

Run AFTER: nothing special.  Run BEFORE: normalize_13f_values.py (units),
map_13f_tickers.py (any new issuers), then unified_score + renderers.
"""
import os, sqlite3, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ingest_13f import (curl, latest_13f_acc, find_infotable, parse_infotable,
                        cusip_ticker_map, name_to_ticker)
from _shard import shard_map

DB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "cyclepapa.db")
NAME_MAP = {}

def worker(item):
    """(fund, cik, stored_acc) -> result dict. Probes EDGAR for the latest
    13F-HR; only fetches/parses the infotable when the accession is new."""
    fund, cik, stored_acc = item
    if not cik:
        return {"fund": fund, "changed": False}
    acc, filed = latest_13f_acc(str(cik))
    if not acc or acc == stored_acc:
        return {"fund": fund, "changed": False}
    path = find_infotable(str(cik), acc)
    url = path if path.startswith("http") else "https://www.sec.gov" + path
    body = curl(url)
    rows = parse_infotable(body) if body else []
    return {"fund": fund, "cik": cik, "changed": True,
            "acc": acc, "filed": filed, "rows": rows}

def run(n_workers=8, rps=8):
    conn = sqlite3.connect(DB)
    global NAME_MAP
    print("loading SEC ticker map...")
    NAME_MAP = cusip_ticker_map(conn)
    print(f"  {len(NAME_MAP)} name->ticker mappings")

    targets = {}
    for r in conn.execute("""SELECT fund, cik, last_accession FROM fund_13f_state
                             WHERE cik IS NOT NULL AND cik != ''"""):
        targets[r[0]] = (r[0], r[1], r[2])
    for r in conn.execute("""SELECT fr.fund, fr.best_cik FROM fund_resolution_state fr
                             WHERE fr.best_cik IS NOT NULL AND fr.best_cik != ''
                             AND NOT EXISTS (SELECT 1 FROM fund_13f_state s WHERE s.fund = fr.fund)"""):
        targets.setdefault(r[0], (r[0], r[1], None))
    items = list(targets.values())
    print(f"checking {len(items)} 13F CIK funds for newer filings, {n_workers} workers\n")

    n_ref = [0]; n_hold = [0]; n_empty = [0]; prog = [0]
    def on_result(item, res):
        prog[0] += 1
        if res and res.get("changed"):
            fund, cik, acc, filed, rows = (res["fund"], res["cik"], res["acc"],
                                           res["filed"], res["rows"])
            if rows:
                total_v = sum(r["value_k"] for r in rows)
                conn.execute("DELETE FROM fund_13f_holdings WHERE fund=?", (fund,))
                for r in rows:
                    tkr = name_to_ticker(r["issuer"], NAME_MAP)
                    pct = (r["value_k"] / total_v * 100) if total_v else None
                    conn.execute("""INSERT OR REPLACE INTO fund_13f_holdings
                        VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                        (fund, cik, acc, filed, r["issuer"], r["cusip"], tkr,
                         r["value_k"], r["shares"], r["type"], pct))
                conn.execute("""INSERT OR REPLACE INTO fund_13f_state
                    VALUES (?,?,?,?,?,?,datetime('now'))""",
                    (fund, cik, acc, filed, len(rows), total_v))
                n_ref[0] += 1; n_hold[0] += len(rows)
                print(f"  ✓ {fund[:40]:<40} -> {len(rows):>4} holdings ({filed})")
            else:
                conn.execute("""INSERT OR REPLACE INTO fund_13f_state
                    VALUES (?,?,?,?,?,?,datetime('now'))""",
                    (fund, cik, acc, filed, 0, 0))
                n_empty[0] += 1
        if prog[0] % 50 == 0:
            conn.commit()
            print(f"  [{prog[0]}/{len(items)}] refreshed={n_ref[0]}")

    shard_map(worker, items, n_workers=n_workers, rps=rps,
              on_result=on_result, on_error=lambda i, e: None)
    conn.commit()
    print(f"\ndone: {n_ref[0]} funds refreshed to a newer 13F "
          f"({n_hold[0]} holdings), {n_empty[0]} newer-but-empty")

if __name__ == "__main__":
    run()
