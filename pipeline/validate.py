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

    # ---- modern data-model invariants (the bug classes fought since the June audit) ----
    def one(sql, params=()):
        r = conn.execute(sql, params).fetchone()
        return r[0] if r else 0

    # I1. 13F value-unit sanity. >3x issuer mcap is impossible (dollars-vs-thousands
    #     1000x stragglers / ADS inflation) -> FAIL. 1.5-3x is usually a stale
    #     quarter-end value on a since-collapsed stock (e.g. post-bankruptcy) -> WARN.
    n = one("""SELECT COUNT(*) FROM fund_13f_holdings h JOIN ticker_yf y ON y.ticker=h.ticker
        WHERE y.mcap_m>0 AND h.value_k/1e3 > y.mcap_m*3 AND h.sh_type IN ('SH','')""")
    if n: fails.append(f"13F: {n} holdings worth >3x issuer mcap (value-unit/ADS inflation)")
    n = one("""SELECT COUNT(*) FROM fund_13f_holdings h JOIN ticker_yf y ON y.ticker=h.ticker
        WHERE y.mcap_m>0 AND h.value_k/1e3 BETWEEN y.mcap_m*1.5 AND y.mcap_m*3 AND h.sh_type IN ('SH','')""")
    if n: warns.append(f"13F: {n} holdings 1.5-3x issuer mcap (likely stale quarter-end value)")

    # I2. Form 4 price sanity: no US share price > $200k except BRK-A (corrupted fields).
    n = one("SELECT COUNT(*) FROM form4_transactions WHERE price>200000 AND ticker!='BRK-A'")
    if n: fails.append(f"Form4: {n} transactions priced >$200k (corrupted price field)")

    # I3. Form 4 share sanity: no single insider transaction > 100M shares (ADS artifact).
    n = one("SELECT COUNT(*) FROM form4_transactions WHERE shares>1e8")
    if n: fails.append(f"Form4: {n} transactions >100M shares (ADS-ratio artifact)")

    # I4. CUSIP-mapping contamination: a COMMON operating ticker must not carry holdings
    #     whose issuer is an ETF/fund vehicle (family-collapse mis-map).
    n = one("""SELECT COUNT(*) FROM fund_13f_holdings h
        WHERE h.ticker IN (SELECT ticker FROM unified_signal WHERE sec_type='common')
        AND (h.issuer LIKE '%EXCH TRD%' OR h.issuer LIKE '% ETF%' OR h.issuer LIKE '%ISHARES%'
             OR h.issuer LIKE '%GLOBAL X%' OR h.issuer LIKE '%SPDR%' OR h.issuer LIKE '%POWERSHARES%')""")
    if n: fails.append(f"13F: {n} fund-issuer holdings mapped onto common operating tickers (mis-map)")

    # I5. pct_book in [0,100]; smart_money_n non-negative; no NULL score.
    n = one("SELECT COUNT(*) FROM fund_13f_holdings WHERE pct_book<0 OR pct_book>100")
    if n: fails.append(f"13F: {n} rows with pct_book outside [0,100]")
    n = one("SELECT COUNT(*) FROM unified_signal WHERE score IS NULL OR smart_money_n<0")
    if n: fails.append(f"unified_signal: {n} rows with NULL score or negative smart_money_n")

    # I6. delisted contamination: a yf_dead ticker must not be classed 'common'.
    n = one("""SELECT COUNT(*) FROM unified_signal WHERE sec_type='common'
        AND ticker IN (SELECT ticker FROM yf_dead)""")
    if n: warns.append(f"{n} yf_dead tickers still classed sec_type='common' (rerun unified_score)")

    # I7. leftover temp tables (snapshot/rebuild cruft).
    for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND "
                          "(name LIKE '%__old' OR name LIKE '%_tmp' OR name LIKE '%_bak')"):
        warns.append(f"leftover temp table: {r[0]}")

    # I8b. SILENT-DROP GATE: real (non-fund, non-foreign) 13F holdings that failed
    #      to map to a ticker are excluded from ALL aggregation. Surface them loudly
    #      — a big unmapped position is smart-money signal we're losing (Brookdale
    #      had 27 holders silently dropped before this gate existed). List the top
    #      offenders by value so they can never disappear silently again.
    unmapped = conn.execute("""SELECT issuer, COUNT(*) n, SUM(value_k)/1e3 vM
        FROM fund_13f_holdings
        WHERE ticker IS NULL AND value_k > 0
          AND issuer NOT LIKE '%ETF%' AND issuer NOT LIKE '%FUND%' AND issuer NOT LIKE '% TR%'
          AND issuer NOT LIKE '%FDS%' AND issuer NOT LIKE '%SHARES%' AND issuer NOT LIKE '%EXCH TRD%'
          AND issuer NOT LIKE '%PORTFOLIO%' AND issuer NOT LIKE '%INDEX%' AND issuer NOT LIKE '%ISHARES%'
          AND issuer NOT LIKE '%NOTE%' AND issuer NOT LIKE '%BOND%' AND issuer NOT LIKE '%CALL%' AND issuer NOT LIKE '%PUT%'
        GROUP BY issuer HAVING vM >= 100 ORDER BY vM DESC""").fetchall()
    if unmapped:
        big = sum(1 for _ in unmapped)
        warns.append(f"{big} unmapped non-fund issuers with >=$100M held (possible dropped real "
                     f"companies) — top: " + "; ".join(f"{r[0][:24]} (${r[2]:,.0f}M)" for r in unmapped[:5]))
        # a very large single unmapped US-looking position is a FAIL (likely a name we can fix)
        us_like = [r for r in unmapped if r[2] >= 400 and ' SA' not in (r[0] or '')
                   and ' NV' not in (r[0] or '') and ' AG' not in (r[0] or '') and ' PLC' not in (r[0] or '')]
        if len(us_like) > 8:
            fails.append(f"{len(us_like)} US-looking issuers with >=$400M held are UNMAPPED — "
                         f"run OpenFIGI recovery (map_cusip_openfigi) / check name normalization")

    # I8c. Form 4 attribution: one accession = one issuer = one ticker. The same
    #      filing under two tickers means an owner-feed misbooking (Sumitomo's JEF
    #      buy shown under SMFG too) — double-counted insider dollars.
    n = one("""SELECT COUNT(*) FROM (SELECT accession FROM form4_transactions
        WHERE ticker IS NOT NULL GROUP BY accession HAVING COUNT(DISTINCT ticker)>1)""")
    if n: fails.append(f"Form4: {n} accessions booked under multiple tickers (owner-vs-issuer misattribution)")

    # I8d. Placeholder-CUSIP hygiene: "000000000"-style CUSIPs come from empty
    #      13F filings ("NONE", "No Securities") and unassigned issues; one such
    #      CUSIP is shared by unrelated rows, so it must never be an authority
    #      key (it once painted 6 empty filings as phantom PRLD holders) and
    #      zero-value/zero-share rows must never be booked at all.
    n = one("""SELECT COUNT(*) FROM cusip_map
        WHERE length(cusip) != 9 OR replace(cusip, substr(cusip,1,1), '') = ''""")
    if n: fails.append(f"cusip_map: {n} placeholder/malformed CUSIPs persisted as authority")
    for tbl in ("fund_13f_holdings", "fund_13f_prior"):
        n = one(f"SELECT COUNT(*) FROM {tbl} WHERE value_k=0 AND shares=0")
        if n: fails.append(f"{tbl}: {n} informationless zero-value/zero-share rows booked")

    # I8. feed freshness: warn when the tradeable-signal feeds fall behind.
    for tbl, col, days in [('form4_transactions','trans_date',21), ('holder_13d','filed',30),
                           ('catalysts_8k','filed',30), ('ticker_yf','asof',21)]:
        mx = one(f"SELECT MAX({col}) FROM {tbl}")
        if mx and (conn.execute("SELECT julianday('now')-julianday(?)", (mx,)).fetchone()[0] or 0) > days:
            warns.append(f"{tbl} stale: latest {str(mx)[:10]} (> {days}d)")

    for w in warns: print(f"WARN  {w}")
    for f in fails: print(f"FAIL  {f}")
    print(f"\n{len(fails)} failures, {len(warns)} warnings")
    return 1 if fails else 0

if __name__ == '__main__':
    sys.exit(run())
