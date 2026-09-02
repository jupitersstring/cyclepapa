"""Re-parse the 8-K Item codes for filings already in catalysts_8k.

The original ingest_8k.parse_8k_items couldn't handle SEC's descriptive
header format ('ITEM INFORMATION: Other Events') and wrote empty items
for all 6,464 filings. Parser now fixed — this script re-fetches each
filing and re-parses items, updating the row in place.

Sharded for speed.
"""
import os, sqlite3, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _shard import shard_map
from ingest_8k import parse_8k_items, ITEM_LABELS

DB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "cyclepapa.db")

def reparse_one(row):
    """row = (ticker, cik, accession). Returns parsed items list."""
    ticker, cik, accession = row
    try:
        return parse_8k_items(cik, accession)
    except Exception:
        return []

def run(n_workers=8, rps=8):
    conn = sqlite3.connect(DB)
    todo = list(conn.execute("""
        SELECT ticker, cik, accession FROM catalysts_8k
        WHERE items IS NULL OR items = ''
        ORDER BY filed DESC"""))
    print(f"re-parsing {len(todo)} 8-K filings with empty items")

    progress = [0]
    n_parsed = 0
    def on_result(row, items):
        nonlocal n_parsed
        ticker, cik, accession = row
        labels = ", ".join(f"{x}: {ITEM_LABELS.get(x, x)}" for x in items)
        flags = {
            "ma":        1 if any(x in items for x in ("1.01","2.01")) else 0,
            "dir":       1 if "5.02" in items else 0,
            "earn":      1 if "2.02" in items else 0,
            "bnk":       1 if "1.03" in items else 0,
            "pipe":      1 if "3.02" in items else 0,
            "ctrl":      1 if "5.01" in items else 0,
        }
        conn.execute("""UPDATE catalysts_8k
            SET items=?, item_labels=?,
                has_ma=?, has_director=?, has_earnings=?,
                has_bankruptcy=?, has_pipe=?, has_control=?
            WHERE cik=? AND accession=?""",
            (",".join(items), labels,
             flags["ma"], flags["dir"], flags["earn"],
             flags["bnk"], flags["pipe"], flags["ctrl"],
             cik, accession))
        if items: n_parsed += 1
        progress[0] += 1
        if progress[0] % 100 == 0:
            conn.commit()
            print(f"  [{progress[0]}/{len(todo)}] {ticker} items={items} (parsed_so_far={n_parsed})")

    def on_error(row, exc):
        progress[0] += 1

    shard_map(reparse_one, todo, n_workers=n_workers, rps=rps,
              on_result=on_result, on_error=on_error)
    conn.commit()
    print(f"\ndone: {n_parsed} of {len(todo)} got non-empty items")

    # Summary
    print(f"\n--- item code distribution ---")
    for r in conn.execute("""SELECT items, COUNT(*) c FROM catalysts_8k
        WHERE items != '' GROUP BY items ORDER BY c DESC LIMIT 15"""):
        print(f"  {r[0]:<25} {r[1]}")

    for flag, lbl in [("has_ma","M&A"), ("has_director","director change"),
                      ("has_control","control change"), ("has_pipe","PIPE/dilution"),
                      ("has_bankruptcy","bankruptcy"), ("has_earnings","earnings")]:
        n = conn.execute(f"SELECT COUNT(DISTINCT ticker) FROM catalysts_8k WHERE {flag}=1").fetchone()[0]
        print(f"  tickers with {lbl}: {n}")

if __name__ == "__main__":
    run()
