"""Audit EVERY roster fund with a 13F CIK for missed positions.

For each fund that should have a 13F, fetch EDGAR's latest 13F-HR, parse the
FULL information table, and compare against what we have stored. Flags three
failure modes:

  STALE      latest accession != our stored accession (a newer 13F exists)
  TRUNCATED  same accession, but the filing has MORE positions than we stored
             (a historical parse dropped rows)
  MISSING    CIK known + filing has positions, but we stored none

Read-only: writes a report to scratchpad/verify_13f.json. Re-ingest of flagged
funds is a separate, reviewed step.
"""
import json, os, sqlite3, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ingest_13f import (latest_13f_acc, find_infotable, parse_infotable, curl,
                        FUND_CIK)
from _shard import shard_map

DB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "cyclepapa.db")
OUT = "/tmp/claude-0/-home-user-cyclepapa/397c23d0-231d-5c3a-866d-8af2219f3cb2/scratchpad/verify_13f.json"

def collect_targets(conn):
    """fund -> {cik, stored_acc, stored_count}. Union of every CIK source."""
    t = {}
    # 1. funds we have ingested 13F state for
    for fund, cik, acc, n in conn.execute(
            "SELECT fund, cik, last_accession, n_holdings FROM fund_13f_state "
            "WHERE cik IS NOT NULL AND cik != ''"):
        t[fund] = {"cik": str(cik), "stored_acc": acc, "stored_n": n or 0}
    # 2. resolution-state best_cik (covers newly resolved funds)
    for fund, cik in conn.execute(
            "SELECT fund, best_cik FROM fund_resolution_state "
            "WHERE best_cik IS NOT NULL AND best_cik != ''"):
        t.setdefault(fund, {"cik": str(cik), "stored_acc": None, "stored_n": 0})
    # 3. the hardcoded canonical map
    for fund, cik in FUND_CIK.items():
        t.setdefault(fund, {"cik": str(cik), "stored_acc": None, "stored_n": 0})
    # actual stored holding COUNT (n_holdings field can be stale)
    for fund in t:
        c = conn.execute("SELECT COUNT(*) FROM fund_13f_holdings WHERE fund=?", (fund,)).fetchone()[0]
        t[fund]["actual_n"] = c
    return t

def worker(item):
    fund, meta = item
    cik = meta["cik"]
    acc, filed = latest_13f_acc(cik)
    if not acc:
        return {"fund": fund, "cik": cik, "no_13f": True}
    path = find_infotable(cik, acc)
    url = path if path.startswith("http") else "https://www.sec.gov" + path
    body = curl(url)
    rows = parse_infotable(body) if body else []
    return {"fund": fund, "cik": cik, "latest_acc": acc, "filed": filed,
            "parsed_n": len(rows)}

def run(n_workers=8, rps=8):
    conn = sqlite3.connect(DB)
    targets = collect_targets(conn)
    items = list(targets.items())
    print(f"auditing {len(items)} CIK funds against EDGAR latest 13F-HR\n")

    flagged = {"stale": [], "truncated": [], "missing": [], "no_13f": [], "ok": 0}
    prog = [0]
    def on_result(item, res):
        prog[0] += 1
        fund = res["fund"]
        meta = targets[fund]
        if res.get("no_13f"):
            flagged["no_13f"].append({"fund": fund, "cik": res["cik"]})
        else:
            stored_acc = meta["stored_acc"]
            actual_n = meta["actual_n"]
            parsed_n = res["parsed_n"]
            rec = {"fund": fund, "cik": res["cik"], "latest_acc": res["latest_acc"],
                   "filed": res["filed"], "parsed_n": parsed_n,
                   "stored_acc": stored_acc, "actual_n": actual_n}
            if stored_acc and res["latest_acc"] != stored_acc:
                flagged["stale"].append(rec)
            elif actual_n == 0 and parsed_n > 0:
                flagged["missing"].append(rec)
            elif parsed_n > actual_n + 1:   # +1 tolerance for dedup/rounding
                flagged["truncated"].append(rec)
            else:
                flagged["ok"] += 1
        if prog[0] % 40 == 0:
            print(f"  [{prog[0]}/{len(items)}] stale={len(flagged['stale'])} "
                  f"trunc={len(flagged['truncated'])} miss={len(flagged['missing'])}")

    shard_map(worker, items, n_workers=n_workers, rps=rps,
              on_result=on_result, on_error=lambda i, e: print(f"  ! {i[0][:30]} {e}"))

    for k in ("stale", "truncated", "missing"):
        flagged[k].sort(key=lambda r: -(r["parsed_n"] - r.get("actual_n", 0)))
    print(f"\n=== AUDIT SUMMARY ===")
    print(f"  ok (up to date):     {flagged['ok']}")
    print(f"  STALE (newer 13F):   {len(flagged['stale'])}")
    print(f"  TRUNCATED (missed):  {len(flagged['truncated'])}")
    print(f"  MISSING (none):      {len(flagged['missing'])}")
    print(f"  no 13F on EDGAR:     {len(flagged['no_13f'])}")
    for k in ("truncated", "missing", "stale"):
        if flagged[k]:
            print(f"\n--- {k.upper()} ---")
            for r in flagged[k][:40]:
                print(f"  {r['fund'][:38]:<38} stored={r['actual_n']:>3} latest_filing={r['parsed_n']:>3} "
                      f"({r['filed']})")
    json.dump(flagged, open(OUT, "w"), indent=1)
    print(f"\nreport -> {OUT}")
    return flagged

if __name__ == "__main__":
    run()
