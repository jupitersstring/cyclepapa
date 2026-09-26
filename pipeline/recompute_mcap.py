"""Recompute mcap for all US tickers using the DATE-AWARE shares-outstanding.

The original ticker_meta mcap used a stale shares concept that froze for
dual-class companies (LEVI, MA, GOOGL, etc.), understating their mcap by
3-10x. enrich_tickers.shares_outstanding is now date-aware and dual-class-
aware. This re-derives shares + mcap for every US ticker that has a price.

Sharded. Updates ticker_meta.shares_out_m and mcap_m in place.
"""
import os, sqlite3, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _shard import shard_map
from enrich_tickers import shares_outstanding, cik_for_ticker

DB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "cyclepapa.db")

def recompute_one(tkr):
    cik = cik_for_ticker(tkr)
    if not cik:
        return None
    so = shares_outstanding(cik)
    return so   # raw shares

def run(n_workers=8, rps=8):
    conn = sqlite3.connect(DB)
    todo = [r[0] for r in conn.execute("""
        SELECT ticker FROM ticker_meta
        WHERE price IS NOT NULL AND ticker NOT LIKE '%.%'""")]
    print(f"recomputing mcap for {len(todo)} US tickers, {n_workers} workers")

    progress = [0]; n_changed = 0
    def on_result(tkr, so):
        nonlocal n_changed
        progress[0] += 1
        if not so:
            return
        row = conn.execute("SELECT price, mcap_m FROM ticker_meta WHERE ticker=?", (tkr,)).fetchone()
        if not row or not row[0]:
            return
        price, old_mcap = row
        so_m = so / 1e6
        new_mcap = so_m * price
        # only update if materially different (>2%) to avoid churn
        if old_mcap is None or abs((new_mcap - old_mcap) / (old_mcap or 1)) > 0.02:
            n_changed += 1
        conn.execute("UPDATE ticker_meta SET shares_out_m=?, mcap_m=? WHERE ticker=?",
                     (so_m, new_mcap, tkr))
        if progress[0] % 200 == 0:
            conn.commit()
            print(f"  [{progress[0]}/{len(todo)}] {tkr} changed={n_changed}")

    def on_error(tkr, exc):
        progress[0] += 1

    shard_map(recompute_one, todo, n_workers=n_workers, rps=rps,
              on_result=on_result, on_error=on_error)
    conn.commit()
    print(f"\ndone: {n_changed} mcaps materially updated")

    # sanity
    print("\n--- spot check ---")
    for t in ("LEVI","MA","GOOGL","KSS","GT","HHH"):
        r = conn.execute("SELECT mcap_m, shares_out_m, price FROM ticker_meta WHERE ticker=?", (t,)).fetchone()
        if r:
            print(f"  {t:<6} mcap=${r[0]:,.0f}M  shares={r[1]:.0f}M  px=${r[2]}")

if __name__ == "__main__":
    run()
