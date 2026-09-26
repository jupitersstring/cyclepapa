"""Backfill Form 4 owner names — plus owner CIK and post-trade holdings — that
the sharded scanner never captured.

scan_insider_sharded looked for a non-existent <rptOwner> element, so every
stored transaction carried a blank owner: all insiders of a company looked
like one person, no insider cluster could reach two buyers, and the Insider
Clusters sheet came out empty. This re-reads each affected filing's raw XML
from EDGAR (the source_url with the xslF345X rendering segment stripped) and
fills, in place:
  owner        first reporting owner's name (as filed)
  owner_cik    their SEC CIK — counts PEOPLE, not name spellings
  role         only where blank
  owned_after  shares held after each transaction (sharesOwnedFollowingTransaction)

Idempotent: only rows with a blank owner are touched, so a re-run picks up
exactly the filings a previous run failed to fetch. Must run BEFORE the next
scanner pass: the dedup key includes owner, so a re-scan against blank-owner
rows would insert every transaction a second time under its real name.
"""
import os, re, sqlite3, subprocess, sys
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _shard import shard_map
from scan_insider_sharded import DB, UA, ensure_columns, parse_owner

def fetch(item):
    acc, url = item
    raw_url = re.sub(r"/xslF345X\d+/", "/", url)
    xml = subprocess.run(["curl", "-sS", "--compressed", "-m", "20", "-A", UA, raw_url],
                         capture_output=True, text=True).stdout
    root = ET.fromstring(xml)                      # an HTML error page raises -> retried later
    owner, role, owner_cik = parse_owner(root)
    txs = []
    for tx in root.iter("nonDerivativeTransaction"):
        g = lambda p: (tx.find(p).text or "").strip() if (tx.find(p) is not None and tx.find(p).text) else None
        try:
            shares = float(g(".//transactionShares/value"))
        except (TypeError, ValueError):
            continue
        price = g(".//transactionPricePerShare/value")
        owned = g(".//postTransactionAmounts/sharesOwnedFollowingTransaction/value")
        try:
            txs.append((g(".//transactionCode"), g(".//transactionDate/value"), shares,
                        float(price) if price else None, float(owned) if owned else None))
        except ValueError:
            continue
    return owner, role, owner_cik, txs

def run(n_workers=8, rps=8):
    conn = sqlite3.connect(DB, timeout=120)
    conn.execute("PRAGMA busy_timeout=120000")
    ensure_columns(conn)
    todo = conn.execute("""SELECT accession, MIN(source_url) FROM form4_transactions
        WHERE (owner IS NULL OR owner = '') AND source_url LIKE 'http%'
        GROUP BY accession""").fetchall()
    print(f"backfilling owners for {len(todo):,} Form 4 filings ({rps} req/s)", flush=True)
    done, failed, n_rows = [0], [], [0]

    def on_result(item, res):
        acc = item[0]
        owner, role, owner_cik, txs = res
        done[0] += 1
        if not owner:
            failed.append(acc)
            return
        n_rows[0] += conn.execute("""UPDATE form4_transactions
            SET owner = ?, owner_cik = ?,
                role = CASE WHEN COALESCE(role, '') = '' THEN ? ELSE role END
            WHERE accession = ? AND (owner IS NULL OR owner = '')""",
            (owner, owner_cik or None, role, acc)).rowcount
        for code, date, shares, price, owned in txs:
            if owned is None:
                continue
            conn.execute("""UPDATE form4_transactions SET owned_after = ?
                WHERE accession = ? AND code = ? AND trans_date = ? AND ABS(shares - ?) < 0.5
                  AND ABS(COALESCE(price, -1) - COALESCE(?, -1)) < 0.0001""",
                (owned, acc, code, date, shares, price))
        if done[0] % 250 == 0:
            conn.commit()
            print(f"  [{done[0]:,}/{len(todo):,}] rows updated {n_rows[0]:,}, failed {len(failed)}", flush=True)

    def on_error(item, exc):
        done[0] += 1
        failed.append(item[0])

    shard_map(fetch, todo, n_workers=n_workers, rps=rps, on_result=on_result, on_error=on_error)
    conn.commit()
    left = conn.execute("SELECT COUNT(*) FROM form4_transactions WHERE owner IS NULL OR owner = ''").fetchone()[0]
    print(f"done: {n_rows[0]:,} rows got an owner; {len(failed)} filings failed (re-run to retry); "
          f"{left:,} rows still blank")
    conn.close()

if __name__ == "__main__":
    run()
