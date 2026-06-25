"""Sharded 8-K ingest — 6-8× faster than ingest_8k.py."""
import json, os, re, sqlite3, subprocess, sys, time

DB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "cyclepapa.db")
UA = "cyclepapa-research admin@example.com"

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _shard import shard_map
from ingest_8k import ITEM_LABELS, init_schema, cik_for, recent_8k, parse_8k_items, target_tickers

def scan_one_ticker(tkr):
    """Pull recent 8-K filings + items for one ticker."""
    cik = cik_for(tkr)
    if not cik: return []
    filings = recent_8k(cik, lookback_days=180)
    rows = []
    for acc, doc, dt in filings:
        try:
            items = parse_8k_items(cik, acc)
        except Exception:
            items = []
        labels = ", ".join(f"{x}: {ITEM_LABELS.get(x, x)}" for x in items)
        rows.append((tkr, cik, acc, dt, ",".join(items), labels,
                     1 if any(x in items for x in ("1.01","2.01")) else 0,
                     1 if "5.02" in items else 0,
                     1 if "2.02" in items else 0,
                     1 if "1.03" in items else 0,
                     1 if "3.02" in items else 0,
                     1 if "5.01" in items else 0,
                     f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc.replace('-','')}/"))
    return rows

def run(max_n=1200, n_workers=8, rps=8):
    conn = sqlite3.connect(DB)
    init_schema(conn)
    targets = target_tickers(conn, max_n)
    print(f"sharded 8-K scan: {len(targets)} tickers, {n_workers} workers")

    n_filings = 0
    progress = [0]
    def on_result(tkr, rows):
        nonlocal n_filings
        for row in rows:
            try:
                conn.execute("""INSERT OR IGNORE INTO catalysts_8k
                    (ticker, cik, accession, filed, items, item_labels,
                     has_ma, has_director, has_earnings, has_bankruptcy, has_pipe, has_control, source_url)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""", row)
                n_filings += 1
            except Exception:
                pass
        progress[0] += 1
        if progress[0] % 50 == 0:
            conn.commit()
            print(f"  [{progress[0]}/{len(targets)}] {tkr} total_8K={n_filings}")

    def on_error(tkr, exc):
        progress[0] += 1

    shard_map(scan_one_ticker, targets, n_workers=n_workers, rps=rps,
              on_result=on_result, on_error=on_error)
    conn.commit()
    print(f"\ndone: {n_filings} 8-K filings across {len(targets)} tickers")

if __name__ == "__main__":
    run(max_n=int(sys.argv[1]) if sys.argv[1:] else 1200)
