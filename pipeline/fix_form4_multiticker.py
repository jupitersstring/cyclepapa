"""Resolve Form 4 accessions booked under multiple tickers.

One accession = one issuer. Multi-ticker bookings happen when an owner-feed
scan (scanning fund X's filings) books a filing under the scan target while
a later issuer-feed scan books it under the true issuer. EDGAR's raw XML
names the issuer — fetch it and keep only matching rows. Called at the end
of every insider scan; also runnable standalone.
"""
import os, re, sqlite3, subprocess, sys, time

DB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "cyclepapa.db")
UA = "cyclepapa-research admin@example.com"

def run(conn=None):
    own = conn is None
    if own:
        conn = sqlite3.connect(DB, timeout=60)
        conn.execute("PRAGMA busy_timeout=60000")
    accs = [r[0] for r in conn.execute("""SELECT accession FROM form4_transactions
        WHERE ticker IS NOT NULL GROUP BY accession HAVING COUNT(DISTINCT ticker) > 1""")]
    if not accs:
        if own: conn.close()
        return 0
    print(f"form4 multi-ticker fixer: {len(accs)} accessions", flush=True)
    fixed = 0
    for acc in accs:
        row = conn.execute("""SELECT source_url FROM form4_transactions
            WHERE accession=? AND source_url IS NOT NULL LIMIT 1""", (acc,)).fetchone()
        if not row or not row[0]:
            continue
        url = re.sub(r"xslF345X\d+/", "", row[0])
        body = subprocess.run(["curl", "-sk", "--compressed", "-m", "20", "-A", UA, url],
                              capture_output=True).stdout
        m = re.search(rb"<issuerTradingSymbol>([^<]+)</issuerTradingSymbol>", body or b"")
        if not m:
            continue
        sym = m.group(1).decode().strip().upper().replace(".", "-")
        have = {r[0] for r in conn.execute(
            "SELECT DISTINCT ticker FROM form4_transactions WHERE accession=?", (acc,))}
        if sym in have:
            conn.execute("DELETE FROM form4_transactions WHERE accession=? AND ticker != ?",
                         (acc, sym))
        else:
            conn.execute("UPDATE form4_transactions SET ticker=? WHERE accession=?", (acc, sym))
        fixed += 1
        time.sleep(0.2)
    conn.commit()
    print(f"form4 multi-ticker fixer: {fixed} resolved", flush=True)
    if own:
        conn.close()
    return fixed

if __name__ == "__main__":
    sys.exit(0 if run() is not None else 1)
