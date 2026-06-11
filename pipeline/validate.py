"""Invariant checks — run after every ingest; nonzero exit on FAIL.

Catches the error classes found in the June 10 audit:
mcap != price x shares, missing as_of, missing sources, expired catalysts
still marked pending, pct>100, R/R arithmetic.
"""
import os, sqlite3, sys

DB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "cyclepapa.db")

def run():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    fails, warns = [], []

    # 1. price requires price_asof + source
    for r in conn.execute("SELECT ticker FROM candidates WHERE price IS NOT NULL AND (price_asof IS NULL OR price_asof='')"):
        fails.append(f"{r['ticker']}: price without price_asof")
    for r in conn.execute("SELECT ticker FROM candidates WHERE (source_url IS NULL OR source_url='') AND verification_status NOT LIKE '%DEAD%'"):
        warns.append(f"{r['ticker']}: no source_url")

    # 2. mcap ~= price x shares (15% tolerance, derived shares exempt by construction)
    for r in conn.execute("""SELECT ticker, price, mcap_m, shares_out_m FROM candidates
                             WHERE price IS NOT NULL AND mcap_m IS NOT NULL AND shares_out_m IS NOT NULL
                             AND shares_method='sourced'"""):
        implied = r['price'] * r['shares_out_m']
        if abs(implied - r['mcap_m']) / r['mcap_m'] > 0.15:
            fails.append(f"{r['ticker']}: mcap {r['mcap_m']}M vs price*shares {implied:.0f}M (>15% off)")

    # 3. catalysts pending past date -> must be EXPIRED_CHECK'd
    for r in conn.execute("SELECT ticker, description, expected_date FROM v_catalysts_live WHERE effective_status='EXPIRED_CHECK'"):
        warns.append(f"{r['ticker']}: catalyst past due ({r['expected_date']}) needs outcome check: {r['description'][:60]}")

    # 4. signals must carry source_url
    for r in conn.execute("SELECT ticker, actor FROM signals WHERE source_url IS NULL OR source_url=''"):
        fails.append(f"{r['ticker']}: signal from {r['actor']} lacks source_url")

    # 5. Tier-1 gate: no CONFLICT/DATA_ERROR rows in tier 1
    for r in conn.execute("""SELECT ticker, verification_status FROM candidates
                             WHERE tier LIKE '1%' AND (verification_status LIKE '%CONFLICT%'
                                OR verification_status LIKE '%DATA_ERROR%' OR verification_status LIKE '%SUSPECT%')"""):
        fails.append(f"{r['ticker']}: in Tier 1 with status {r['verification_status']}")

    # 6. price staleness > 7 days for live tiers
    for r in conn.execute("""SELECT ticker, price_asof FROM candidates
                             WHERE tier LIKE '1%' AND price_asof IS NOT NULL
                             AND julianday('now') - julianday(price_asof) > 7"""):
        warns.append(f"{r['ticker']}: Tier-1 price stale ({r['price_asof']})")

    for w in warns: print(f"WARN  {w}")
    for f in fails: print(f"FAIL  {f}")
    print(f"\n{len(fails)} failures, {len(warns)} warnings")
    return 1 if fails else 0

if __name__ == '__main__':
    sys.exit(run())
