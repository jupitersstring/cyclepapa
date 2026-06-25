"""Normalize 13F value units — fix the post-2023 raw-dollar vs $thousands ambiguity.

Pre-2023, SEC required 13F-HR `value` in $thousands.
Post-2023 (some filers), values are raw dollars. Our parser stores
everything as `value_k` (thousands), so for raw-$ filers the values
are 1000× too large.

Detection: for each fund, sum its `value_k` and compare to the actual
sum implied by the filing's summaryPage tableValueTotal. If the sum
is ~1000× larger than expected (calibrated against AUM), the filer
reported raw dollars.

We use a heuristic: if total_value_k > $50T for ANY single fund,
that's impossible (largest sovereign wealth fund is ~$1.5T).
For those funds, divide all positions by 1000.

Specifically: if total_value_k > 50_000_000_000 ($50 trillion in $K = $50T raw),
the filer is reporting raw dollars. Normalize.
"""
import os, sqlite3, sys

DB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "cyclepapa.db")

# Threshold: $50T in $K units = 50e9. Largest legit 13F is BlackRock ~$5T.
# Anything above $50T total = reading raw dollars as thousands.
RAW_DOLLAR_THRESHOLD = 50_000_000_000   # 50e9 in $K = $50T

def run():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row

    suspicious = list(conn.execute("""
        SELECT fund, total_value_k, n_holdings
        FROM fund_13f_state
        WHERE total_value_k > ?
        ORDER BY total_value_k DESC""", (RAW_DOLLAR_THRESHOLD,)))
    print(f"found {len(suspicious)} funds with implausibly-large total_value_k (raw $ reported as $K):")
    for r in suspicious:
        print(f"  {r['fund'][:40]:<40} ${r['total_value_k']/1e6:,.0f}B → ${r['total_value_k']/1e9:,.0f}B (after /1000)")

    # Normalize: divide every position in fund_13f_holdings by 1000
    # AND fix fund_13f_state.total_value_k
    n_fixed_positions = 0
    for r in suspicious:
        fund = r["fund"]
        n_h = conn.execute("""UPDATE fund_13f_holdings
            SET value_k = value_k / 1000.0
            WHERE fund = ?""", (fund,)).rowcount
        conn.execute("""UPDATE fund_13f_state
            SET total_value_k = total_value_k / 1000.0
            WHERE fund = ?""", (fund,))
        n_fixed_positions += n_h
        print(f"    fixed {n_h} positions for {fund[:40]}")
    conn.commit()
    print(f"\ntotal: normalized {n_fixed_positions} positions across {len(suspicious)} funds")

    # Re-validate
    still_bad = conn.execute("SELECT COUNT(*) FROM fund_13f_state WHERE total_value_k > ?",
                             (RAW_DOLLAR_THRESHOLD,)).fetchone()[0]
    print(f"remaining funds above threshold after fix: {still_bad}")

if __name__ == "__main__":
    run()
