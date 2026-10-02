"""Master 13F integrity fix — corrects wrong filer CIKs and the lot-collapse bug.

Two systematic bugs found by auditing every roster fund:

  1. WRONG FILER CIKs. Several famous funds were wired to the wrong EDGAR CIK,
     so their stored holdings were a DIFFERENT firm's book (Baupost showed Lone
     Pine; Harris/Oakmark showed GAMCO's 1007 names; Sequoia showed Third Avenue;
     Fundsmith/Lindsell/Sessa/Iconiq/Pabrai all shared a junk CIK 1543160). This
     both injected wrong holdings AND hid the real ones. Group A re-ingests each
     with its verified correct CIK.

  2. LOT COLLAPSE. The holdings PK was (fund, accession, cusip); a 13F that
     reports one issuer across several manager sub-accounts (Berkshire's AAPL =
     12 lots) had its rows collapsed by INSERT OR REPLACE, KEEPING ONE LOT'S
     VALUE instead of SUMMING. Berkshire's $58B Apple stake was stored as $958M,
     wrecking pct_book / concentration for every multi-lot filer. We migrate the
     PK to (fund, accession, cusip, sh_type) and re-ingest aggregating value and
     shares per (cusip, sh_type).

Run BEFORE: map_cusip_openfigi (any new unmapped), unified_score, renderers.
"""
import json, os, sqlite3, statistics, sys
from collections import defaultdict
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ingest_13f import (latest_13f_acc, find_infotable, parse_infotable, curl,
                        cusip_ticker_map, name_to_ticker)
from _shard import shard_map

DB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "cyclepapa.db")
SCR = "/tmp/claude-0/-home-user-cyclepapa/397c23d0-231d-5c3a-866d-8af2219f3cb2/scratchpad"

def migrate_pk(conn):
    cur = conn.execute("SELECT sql FROM sqlite_master WHERE name='fund_13f_holdings'").fetchone()[0]
    if "cusip, sh_type" in cur.replace("\n", " "):
        print("PK already migrated"); return
    print("migrating PK -> (fund, accession, cusip, sh_type)")
    conn.executescript("""
    CREATE TABLE fund_13f_holdings_new (
      fund TEXT, cik TEXT, accession TEXT, filed TEXT,
      issuer TEXT, cusip TEXT, ticker TEXT, value_k REAL, shares INTEGER,
      sh_type TEXT, pct_book REAL,
      PRIMARY KEY (fund, accession, cusip, sh_type));
    INSERT OR IGNORE INTO fund_13f_holdings_new
      SELECT fund,cik,accession,filed,issuer,cusip,ticker,value_k,shares,sh_type,pct_book
      FROM fund_13f_holdings;
    DROP TABLE fund_13f_holdings;
    ALTER TABLE fund_13f_holdings_new RENAME TO fund_13f_holdings;
    CREATE INDEX idx_13f_ticker ON fund_13f_holdings(ticker);
    CREATE INDEX idx_13f_fund ON fund_13f_holdings(fund);
    """)
    conn.commit()

def build_cusip_map(conn):
    """cusip -> ticker, from the best mapping already in the table (OpenFIGI +
    curated + mismap-corrected). Preserves prior mapping work."""
    m = {}
    for cusip, tkr, n in conn.execute("""SELECT cusip, ticker, COUNT(*) c
            FROM fund_13f_holdings WHERE ticker IS NOT NULL AND cusip IS NOT NULL
            GROUP BY cusip, ticker ORDER BY c DESC"""):
        m.setdefault(cusip, tkr)   # most common ticker per cusip wins
    return m

def worker(item):
    fund, cik = item
    acc, filed = latest_13f_acc(str(cik))
    if not acc:
        return {"fund": fund, "cik": cik, "rows": None}
    path = find_infotable(str(cik), acc)
    url = path if path.startswith("http") else "https://www.sec.gov" + path
    body = curl(url)
    rows = parse_infotable(body) if body else []
    return {"fund": fund, "cik": str(cik), "acc": acc, "filed": filed, "rows": rows}

def run():
    plan = json.load(open(os.path.join(SCR, "fix_plan.json")))
    group_a = plan["group_a"]              # fund -> correct cik
    delete_junk = plan["delete_junk"]      # funds whose 13F holdings are junk
    truncated = json.load(open(os.path.join(SCR, "verify_13f.json")))["truncated"]

    conn = sqlite3.connect(DB); conn.execute("PRAGMA busy_timeout=60000")
    migrate_pk(conn)
    cusip2tkr = build_cusip_map(conn)
    name_map = cusip_ticker_map(conn)
    print(f"cusip map: {len(cusip2tkr)}; name map: {len(name_map)}")

    # delete confirmed-junk holdings (non-filers wired to an unrelated CIK)
    for fund in delete_junk:
        n = conn.execute("DELETE FROM fund_13f_holdings WHERE fund=?", (fund,)).rowcount
        conn.execute("DELETE FROM fund_13f_state WHERE fund=?", (fund,))
        conn.execute("UPDATE fund_resolution_state SET best_cik='' WHERE fund=?", (fund,))
        print(f"  junk-deleted {fund!r}: {n} rows")
    conn.commit()

    # build targets: Group A (correct cik) wins; then the 77 multi-lot funds
    targets = {}
    for fund, cik in group_a.items():
        targets[fund] = str(cik).lstrip("0")
    for r in truncated:
        targets.setdefault(r["fund"], str(r["cik"]).lstrip("0"))
    items = list(targets.items())
    print(f"\nre-ingesting {len(items)} funds ({len(group_a)} corrected-CIK + "
          f"{len(items)-len(group_a)} lot-aggregation) with value summing\n")

    stats = {"ok": 0, "rows": 0, "no13f": 0, "empty": 0}
    prog = [0]
    def on_result(item, res):
        prog[0] += 1
        fund = res["fund"]
        rows = res["rows"]
        if rows is None:
            stats["no13f"] += 1; return
        if not rows:
            stats["empty"] += 1; return
        cik, acc, filed = res["cik"], res["acc"], res["filed"]
        # aggregate by (cusip, sh_type): SUM value + shares across manager lots
        agg = {}
        for r in rows:
            k = (r["cusip"], r["type"])
            a = agg.get(k)
            if a is None:
                a = agg[k] = {"issuer": r["issuer"], "value_k": 0, "shares": 0}
            a["value_k"] += r["value_k"]; a["shares"] += r["shares"]
        # long equity book = SH / blank type (options excluded from book + pct)
        long_total = sum(a["value_k"] for (cu, ty), a in agg.items() if ty in ("SH", "", None))
        vals = [a["value_k"] for a in agg.values() if a["value_k"] > 0]
        # per-fund raw-dollar (1000x) detection: $K-format medians are << $5M
        scale = 1000.0 if (vals and statistics.median(vals) > 5_000_000) else 1.0
        conn.execute("DELETE FROM fund_13f_holdings WHERE fund=?", (fund,))
        for (cusip, ty), a in agg.items():
            tkr = cusip2tkr.get(cusip) or name_to_ticker(a["issuer"], name_map)
            pct = (a["value_k"] / long_total * 100) if (ty in ("SH", "", None) and long_total > 0) else None
            conn.execute("INSERT OR REPLACE INTO fund_13f_holdings VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (fund, cik, acc, filed, a["issuer"], cusip, tkr,
                 a["value_k"] / scale, a["shares"], ty, pct))
        conn.execute("INSERT OR REPLACE INTO fund_13f_state VALUES (?,?,?,?,?,?,datetime('now'))",
            (fund, cik, acc, filed, len(agg), long_total / scale))
        if fund in group_a:
            conn.execute("UPDATE fund_resolution_state SET best_cik=? WHERE fund=?", (cik, fund))
        stats["ok"] += 1; stats["rows"] += len(agg)
        tag = "★CIK" if fund in group_a else " agg"
        print(f"  [{tag}] {fund[:38]:<38} -> {len(agg):>4} holdings ({filed})")
        if prog[0] % 25 == 0:
            conn.commit()

    shard_map(worker, items, n_workers=6, rps=7, on_result=on_result,
              on_error=lambda i, e: print(f"  ! {i[0][:30]} {e}"))
    conn.commit()
    print(f"\ndone: {stats['ok']} funds re-ingested ({stats['rows']} aggregated holdings), "
          f"{stats['no13f']} no-13F, {stats['empty']} empty")

if __name__ == "__main__":
    run()
