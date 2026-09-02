"""Normalize 13F value units — fix the post-2023 raw-dollar vs $thousands ambiguity.

Pre-2023, SEC required 13F-HR `value` in $thousands.
Post-2023 (some filers), values are raw dollars. Our parser stores
everything as `value_k` (thousands), so for raw-$ filers the values
are 1000× too large.

Detection (two-pass):
  Pass 1 — total threshold:  funds whose sum exceeds $10T in $K (i.e.
    >$10B raw — already impossible). Catches BIG offenders like
    Citadel showing $618T, Berkshire $263T.
  Pass 2 — median position:  in $K-format, a typical 13F position is
    well under $1M ($K). If a fund's MEDIAN position is > $1M $K
    ($1B raw equivalent for a single position), the fund is almost
    certainly reporting raw dollars. Catches smaller funds (1 Main
    Capital, Bonhoeffer Fund etc.) that slipped below pass-1.
"""
import os, sqlite3, statistics, sys

DB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "cyclepapa.db")

# Pass 1 threshold: $10T in $K format = 1e10
PASS1_THRESHOLD = 10_000_000_000

# Pass 2: per-fund median position. If median value_k > $5M ($K),
# the fund is reporting raw $ (real $K-format funds have median position
# well under $1M $K). A $5M $K position would be a $5B position which
# only ~30 funds in the world hold consistently.
PASS2_MEDIAN_THRESHOLD = 5_000_000


def normalize_fund(conn, fund):
    n_h = conn.execute("""UPDATE fund_13f_holdings
        SET value_k = value_k / 1000.0
        WHERE fund = ?""", (fund,)).rowcount
    conn.execute("""UPDATE fund_13f_state
        SET total_value_k = total_value_k / 1000.0
        WHERE fund = ?""", (fund,))
    return n_h


def run():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row

    # Pass 1
    pass1 = list(conn.execute("""
        SELECT fund, total_value_k, n_holdings
        FROM fund_13f_state
        WHERE total_value_k > ?
        ORDER BY total_value_k DESC""", (PASS1_THRESHOLD,)))
    print(f"PASS 1 (threshold ${PASS1_THRESHOLD/1e9:.0f}B in $K): {len(pass1)} funds")
    total_fixed = 0
    pass1_funds = set()
    for r in pass1:
        n_h = normalize_fund(conn, r["fund"])
        total_fixed += n_h
        pass1_funds.add(r["fund"])
        print(f"  ✓ {r['fund'][:42]:<42} normalized {n_h} positions")
    conn.commit()

    # Pass 2 — per-fund median position check, EXCLUDING already-normalized
    candidates = []
    for fr in conn.execute("""SELECT DISTINCT fund FROM fund_13f_holdings"""):
        f = fr["fund"]
        if f in pass1_funds: continue
        vals = [r[0] for r in conn.execute(
            "SELECT value_k FROM fund_13f_holdings WHERE fund=? AND value_k > 0", (f,))]
        if len(vals) < 3: continue
        med = statistics.median(vals)
        if med > PASS2_MEDIAN_THRESHOLD:
            candidates.append((f, med, len(vals)))

    print(f"\nPASS 2 (median position > ${PASS2_MEDIAN_THRESHOLD/1e6:.0f}M $K): {len(candidates)} funds")
    for f, med, n in sorted(candidates, key=lambda x: -x[1]):
        n_h = normalize_fund(conn, f)
        total_fixed += n_h
        print(f"  ✓ {f[:42]:<42} median ${med/1e6:.1f}M $K → /1000 ({n_h} positions)")
    conn.commit()

    print(f"\nTOTAL: normalized {total_fixed} positions across {len(pass1) + len(candidates)} funds")


if __name__ == "__main__":
    run()
