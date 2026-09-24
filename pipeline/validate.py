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
    # mcap floor: a sub-$5M mcap is a collapsed/bankrupt shell (SNBRQ, NOTVQ) —
    # any pre-collapse quarter-end value trips 3x there without being a unit bug.
    n = one("""SELECT COUNT(*) FROM fund_13f_holdings h JOIN ticker_yf y ON y.ticker=h.ticker
        WHERE y.mcap_m>=5 AND h.value_k/1e3 > y.mcap_m*3 AND h.sh_type IN ('SH','')""")
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
          -- debt by structure, not by name: a convertible filed as "MAKEMYTRIP
          -- LIMITED 0 07/.." is principal (PRN) under a lettered issue code
          AND sh_type != 'PRN' AND substr(cusip,7,1) BETWEEN '0' AND '9' AND substr(cusip,8,1) BETWEEN '0' AND '9'
          -- FMP-identified ETFs / closed-end funds stay unticked on holdings by design
          AND cusip NOT IN (SELECT cusip FROM cusip_map WHERE sec_type = 'etf')
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
    #      ...and composite venue tickers ("TRI4EUR", "APLSUSD") must never be
    #      persisted as authority nor carried on holdings rows.
    ccy = "','".join(("EUR","GBP","CHF","JPY","SEK","NOK","DKK","HKD","CAD","AUD","USD"))
    for tbl, col in (("cusip_map","ticker"), ("fund_13f_holdings","ticker")):
        n = one(f"""SELECT COUNT(*) FROM {tbl} WHERE {col} IS NOT NULL
            AND length({col}) >= 6 AND substr({col}, -3) IN ('{ccy}')""")
        if n: fails.append(f"{tbl}: {n} composite venue tickers (ccy-suffix junk, e.g. TRI4EUR)")

    # I8e. CUSIP case: identifiers are case-insensitive, but a lowercase copy
    #      splits one security into two rows and misses cusip_map (471 Ancora
    #      holdings sat unmapped). Ingest upper-cases; nothing may slip through.
    for tbl in ("fund_13f_holdings", "fund_13f_prior", "broker_13f", "cusip_map", "holding_sec_form"):
        n = one(f"SELECT COUNT(*) FROM {tbl} WHERE cusip <> UPPER(cusip)")
        if n: fails.append(f"{tbl}: {n} lowercase CUSIPs (run build_cusip_map.normalize_cusip_case)")
    # I8f. Value units: no single 13F line can exceed $1T. A full-dollar filing
    #      booked as $k does (MUFG's one-line Morgan Stanley book read $78.8T).
    for tbl in ("fund_13f_holdings", "fund_13f_prior", "broker_13f"):
        n = one(f"SELECT COUNT(*) FROM {tbl} WHERE value_k > 1e9")
        if n: fails.append(f"{tbl}: {n} lines above $1T — full-dollar filing not normalized")
    # I8f2. Lines with no market price can't be unit-checked against one: a
    #       whole-dollar line booked as $k shows as an impossible per-share
    #       value (Indaba's lone ON24 line: $7,960 a share, $33.8B booked).
    for tbl in ("fund_13f_holdings", "fund_13f_prior"):
        bad = conn.execute(f"""SELECT h.fund, COALESCE(h.ticker, h.issuer), h.value_k/1e3 FROM {tbl} h
            LEFT JOIN ticker_yf y ON y.ticker = h.ticker AND y.price > 0
            WHERE h.sh_type IN ('SH','') AND h.shares > 0 AND h.value_k * 1000.0 / h.shares > 20000
              AND (y.price IS NULL OR y.price < 5000) ORDER BY h.value_k DESC""").fetchall()
        if any(b[2] >= 100 for b in bad):
            fails.append(f"{tbl}: {sum(b[2] >= 100 for b in bad)} lines of $100M+ at >$20k a share with no price "
                         f"to explain it (unit error): {bad[0][0][:24]} {bad[0][1][:20]} ${bad[0][2]:,.0f}M")
        elif bad:
            warns.append(f"{tbl}: {len(bad)} small lines at >$20k a share (mixed-unit filings), largest "
                         f"{bad[0][0][:24]} {bad[0][1][:20]} ${bad[0][2]:,.1f}M")
    # I8f3. Options are not holdings: a line whose filed title is an option
    #       (Funicular's "PUT" lines carried no putCall flag) must never sit in
    #       a book — $2.4B of puts on MU/NVDA/MSFT once counted as long holders.
    for tbl in ("fund_13f_holdings", "fund_13f_prior"):
        r = conn.execute(f"""SELECT COUNT(*), COALESCE(SUM(h.value_k), 0)/1e3 FROM {tbl} h
            JOIN holding_sec_form f ON f.accession = h.accession AND f.cusip = h.cusip
            WHERE f.sec_form = 'option'""").fetchone()
        if r[0]:
            fails.append(f"{tbl}: {r[0]} option lines (${r[1]:,.0f}M) booked as holdings (run fix_option_lines.py)")
    # I8g. Share class: a line the filer titled COMMON must not carry a
    #      preferred-line ticker (Morgan Stanley common once rode on MS-PQ and
    #      dropped out of every common-stock signal).
    n = one("""SELECT COUNT(*) FROM fund_13f_holdings h JOIN holding_sec_form f
        ON f.accession = h.accession AND f.cusip = h.cusip
        WHERE f.sec_form = 'common' AND h.value_k > 10000
          AND (h.ticker GLOB '*-P' OR h.ticker GLOB '*-P[A-Z]' OR h.ticker GLOB '*-P[A-Z][A-Z]')""")
    if n: fails.append(f"fund_13f_holdings: {n} COMMON lines (>$10M) carry a preferred ticker")

    # I8h. Liveness: a ticker FMP priced as trading ON OR AFTER the day it was
    #      flagged dead is not dead. Yahoo throttling once flagged 1,052 live
    #      names (PG&E, CRH, TKO...), classing each 'delisted' out of every pick.
    try:
        n = one("""SELECT COUNT(*) FROM yf_dead d JOIN ticker_yf y ON y.ticker = d.ticker
            WHERE y.src = 'fmp' AND y.price > 0 AND y.asof >= d.asof""")
        if n: fails.append(f"yf_dead: {n} tickers FMP prices as trading are flagged dead")
    except sqlite3.OperationalError:
        pass

    # I8i. Form 4 owners: every insider trade must name its insider. The sharded
    #      scanner once parsed a non-existent tag and booked ALL trades with a
    #      blank owner — every company's insiders collapsed into one person and
    #      the Insider Clusters sheet came out empty with no error anywhere.
    n_all, n_blank = conn.execute("""SELECT COUNT(*), SUM(COALESCE(owner, '') = '')
        FROM form4_transactions WHERE trans_date >= date('now', '-180 days')""").fetchone()
    if n_all and (n_blank or 0) > 0.02 * n_all:
        fails.append(f"form4_transactions: {n_blank:,} of {n_all:,} recent trades have no owner "
                     f"(run fix_form4_owners.py)")
    n_p = one("""SELECT COUNT(DISTINCT ticker) FROM form4_transactions
        WHERE code = 'P' AND trans_date >= date('now', '-180 days')""")
    if n_p >= 50 and not one("SELECT COUNT(*) FROM insider_clusters WHERE n_insiders >= 2"):
        fails.append(f"insider_clusters: no multi-insider cluster despite buys in {n_p} tickers")

    # I8j. Board seats need tickers: the PitchBook ingest rebuilds pb_affiliation
    #      without them; if the mapper doesn't follow, the people monitor's
    #      Board Signal sheet renders empty with no error anywhere.
    try:
        n_pub = one("SELECT COUNT(*) FROM pb_affiliation WHERE company_type = 'Public Company'")
        n_tk = one("SELECT COUNT(*) FROM pb_affiliation WHERE ticker IS NOT NULL")
        if n_pub >= 20 and n_tk == 0:
            fails.append(f"pb_affiliation: {n_pub} public-company seats, 0 mapped to a ticker (run map_pb_tickers.py)")
    except sqlite3.OperationalError:
        pass

    # I8k. Bond descriptors are not stocks: a ticker with a space ("MSTR 0.625
    #      03-15-30", from OpenFIGI on convertible-note CUSIPs) must never be
    #      classed common, or debt ranks as a stock pick.
    n = one("SELECT COUNT(*) FROM unified_signal WHERE sec_type = 'common' AND ticker LIKE '% %'")
    if n: fails.append(f"unified_signal: {n} bond descriptors (ticker with a space) classed common")

    # I9. 13F quarter roll. In September 2026, 223 funds still showed their Q1
    #     book six weeks after Q2 13Fs were due, and quarter-change diffs ran
    #     two quarters deep: nothing had rolled them and nothing noticed.
    import datetime as _dt
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from ingest_13f import DORMANT_DAYS
    today = _dt.date.today()
    live_cut = (today - _dt.timedelta(days=DORMANT_DAYS)).isoformat()
    # I9a. time-based, needs no EDGAR index: the latest quarter whose 45-day
    #      13F deadline passed 10+ days ago; a live book filed on/before that
    #      quarter's end is an earlier quarter's book.
    qe = [_dt.date(y, m, d) for y in (today.year - 1, today.year)
          for m, d in ((3, 31), (6, 30), (9, 30), (12, 31))]
    due = max(q for q in qe if q + _dt.timedelta(days=55) <= today).isoformat()
    live = one("SELECT COUNT(*) FROM fund_13f_state WHERE last_filed >= ?", (live_cut,))
    behind = [r[0] for r in conn.execute("""SELECT fund FROM fund_13f_state
        WHERE last_filed >= ? AND last_filed <= ? ORDER BY fund""", (live_cut, due))]
    if live and len(behind) > 0.10 * live:
        fails.append(f"13F roll: {len(behind)} of {live} live funds still hold a book from before the "
                     f"{due} quarter, whose 13Fs were due {(_dt.date.fromisoformat(due) + _dt.timedelta(days=45))} "
                     f"(run ingest_13f.py --refresh, then ingest_13f_prior.py)")
    elif behind:
        warns.append(f"13F roll: {len(behind)} live funds have not filed for the {due} quarter yet "
                     f"(late / NT / winding down): {', '.join(b[:28] for b in behind[:8])}")
    try:
        qidx = lambda col: f"(CAST(substr({col},1,4) AS INT)*4 + (CAST(substr({col},6,2) AS INT)-1)/3)"
        cur_p = ("(SELECT period FROM sec_13f_filings g WHERE g.accession = s.last_accession "
                 "AND g.period != '' LIMIT 1)")
        # I9b. against the EDGAR index ingest_13f keeps: a newer-PERIOD 13F-HR
        #      for the fund's CIK that was never ingested (same-period
        #      restatements, like Eminence's empty July re-file, do not count)
        # (dormant funds too: one that filed an EMPTY report is not dormant)
        stale = [r[0] for r in conn.execute(f"""SELECT s.fund FROM fund_13f_state s
            WHERE EXISTS (SELECT 1 FROM sec_13f_filings f
                WHERE f.cik = CAST(CAST(s.cik AS INTEGER) AS TEXT) AND f.form = '13F-HR'
                  AND f.period > {cur_p})""")]
        if stale:
            fails.append(f"13F roll: {len(stale)} funds have a newer-quarter 13F-HR on EDGAR than their "
                         f"stored book (ingest_13f.py --refresh): {', '.join(s[:28] for s in stale[:8])}")
        # I9c. a prior must be the IMMEDIATELY preceding quarter of the current
        #      book, or "Quarter Change" diffs across a gap under its header
        gap = conn.execute(f"""SELECT p.fund, cp, pp FROM (
                SELECT p.fund, {cur_p} cp,
                       (SELECT period FROM sec_13f_filings g WHERE g.accession = p.accession
                        AND g.period != '' LIMIT 1) pp
                FROM fund_13f_prior_state p JOIN fund_13f_state s ON s.fund = p.fund
                WHERE p.accession IS NOT NULL) p
            WHERE cp IS NOT NULL AND pp IS NOT NULL AND {qidx('cp')} - {qidx('pp')} != 1""").fetchall()
        if gap:
            fails.append(f"13F prior: {len(gap)} funds' prior book is not the preceding quarter "
                         f"(e.g. {gap[0][0][:28]}: {gap[0][2]} vs {gap[0][1]}) — run ingest_13f_prior.py")
        # I9d. a 13F-NT newer than the stored book: the holdings are now filed by
        #      another manager (Pershing Square, Q2 2026) — re-point the roster
        nt = [r[0] for r in conn.execute(f"""SELECT DISTINCT s.fund FROM fund_13f_state s
            JOIN sec_13f_filings f ON f.cik = CAST(CAST(s.cik AS INTEGER) AS TEXT)
            WHERE s.last_filed >= ? AND f.form LIKE '13F-NT%' AND f.period > {cur_p}""", (live_cut,))]
        if nt:
            warns.append(f"13F-NT: {len(nt)} funds' newest filing says another manager now reports "
                         f"their holdings (re-point the CIK): {', '.join(x[:28] for x in nt[:8])}")
    except sqlite3.OperationalError:
        warns.append("13F roll: no EDGAR 13F index yet (sec_13f_filings) — run ingest_13f.py --refresh")
    # I9f. quarter-change diffs are share counts: they need the split factors
    try:
        one("SELECT COUNT(*) FROM prior_split_factor")
    except sqlite3.OperationalError:
        fails.append("prior_split_factor missing — quarter-change diffs would read splits as buying "
                     "(run ingest_splits.py)")
    # I9e. dormant books never sit in the live table every sheet reads
    n = one("""SELECT COUNT(DISTINCT h.fund) FROM fund_13f_holdings h
        JOIN fund_13f_state s ON s.fund = h.fund WHERE s.last_filed < ?""", (live_cut,))
    if n: fails.append(f"13F: {n} dormant funds (no 13F-HR in {DORMANT_DAYS} days) still in fund_13f_holdings "
                       f"— shown as current holders (ingest_13f.archive_dormant)")
    # ...and archived, never lost: a re-run once wiped all 29 archived books
    try:
        lost = [r[0] for r in conn.execute("""SELECT s.fund FROM fund_13f_state s
            WHERE s.last_filed < ? AND s.n_holdings > 0
              AND NOT EXISTS (SELECT 1 FROM fund_13f_holdings h WHERE h.fund = s.fund)
              AND NOT EXISTS (SELECT 1 FROM fund_13f_dormant d WHERE d.fund = s.fund)""", (live_cut,))]
        if lost:
            fails.append(f"13F: {len(lost)} dormant funds' books are in neither the live table nor the "
                         f"archive (lost): {', '.join(x[:28] for x in lost[:8])}")
    except sqlite3.OperationalError:
        pass

    # I10. Global books (N-PORT): fresh, and the non-US lines mapped to a
    #      listing — an unmapped line is visible but carries no price/multiples.
    try:
        tot, mapped, newest, n_ser = conn.execute("""SELECT
                SUM(CASE WHEN country != 'US' THEN val_usd END),
                SUM(CASE WHEN country != 'US' AND ticker IS NOT NULL THEN val_usd END),
                MAX(period), COUNT(DISTINCT series_id) FROM nport_holdings""").fetchone()
        if not n_ser:
            warns.append("nport_holdings empty — the global books (non-US holdings) are missing (ingest_nport.py)")
        else:
            if tot and (mapped or 0) < 0.90 * tot:
                fails.append(f"nport_holdings: only {100 * (mapped or 0) / tot:.0f}% of non-US value mapped to a listing")
            if newest and (conn.execute("SELECT julianday('now') - julianday(?)", (newest,)).fetchone()[0] or 0) > 200:
                warns.append(f"nport_holdings stale: newest portfolio {newest} (> 200d) — run ingest_nport.py")
    except sqlite3.OperationalError:
        warns.append("nport_holdings missing — the global books (non-US holdings) are not loaded (ingest_nport.py)")

    # I11. valuation coverage: a blank multiple must mean "no source has it",
    #      not a loss or a fund silently rendered as "—" (the books once showed
    #      ~45% blanks, 90% of them explainable). Priced common stocks only.
    from _style_bw import valuation_lookup
    vals = valuation_lookup(conn)
    commons = [r[0] for r in conn.execute("""SELECT ticker FROM unified_signal
        WHERE sec_type = 'common' AND mcap_m > 0""")]
    if commons:
        blank = [t for t in commons if (vals.get(t) or {}).get("P/E") in (None, "")]
        if len(blank) > 0.10 * len(commons):
            fails.append(f"valuation: {len(blank)} of {len(commons)} priced common stocks have no P/E and no "
                         f"reason label (enrich_fmp.py not run / FMP ratios missing)")
        elif blank:
            warns.append(f"valuation: {len(blank)} of {len(commons)} priced common stocks have no P/E from any "
                         f"source, e.g. {', '.join(blank[:6])}")

    # I12. one vote per filing: a 13F book (accession) stored under two roster
    #      names counts once (unified_score._ONE_BOOK); name them so the roster
    #      duplicates stay visible.
    dup = conn.execute("""SELECT accession, GROUP_CONCAT(DISTINCT fund) FROM fund_13f_holdings
        GROUP BY accession HAVING COUNT(DISTINCT fund) > 1""").fetchall()
    if dup:
        warns.append(f"13F: {len(dup)} books are stored under two roster names and counted once "
                     f"(one vote per filing): " + "; ".join(sorted(d[1].split(",")[0] for d in dup)))

    # I12b. a US / Canadian CUSIP (digit first) mapped to a foreign exchange
    #       code ("HO1", "430", "K4F": Frankfurt lines of US companies whose US
    #       listing ended) reads as nothing to a reader: map it to the US ticker
    #       in map_cusip_fmp.CURATED
    import re as _re
    held = conn.execute("""SELECT cm.cusip, cm.ticker, MAX(h.issuer), COUNT(DISTINCT h.fund) FROM cusip_map cm
        JOIN fund_13f_holdings h ON h.cusip = cm.cusip
        WHERE substr(cm.cusip, 1, 1) BETWEEN '0' AND '9' AND cm.ticker IS NOT NULL
        GROUP BY cm.cusip""").fetchall()
    frgn = [f"{t} ({iss})" for cu, t, iss, n in held
            if _re.fullmatch(r"[0-9][0-9A-Z]{1,4}|[A-Z]{1,3}[0-9][A-Z0-9]?|[0-9A-Z]{2,4}[0-9]|[A-Z]{3,5}GBX", t or "")
            and "." not in t and " " not in t]
    if frgn:
        warns.append(f"cusip_map: {len(frgn)} US CUSIPs held this quarter map to foreign-style codes: "
                     + ", ".join(frgn[:8]))

    # I13. vs-entry is computed on today's price: entry_intact.py runs in the
    #      rebuild; a stale table showed a third "current" price for BABA.
    try:
        n_pair, n_off = conn.execute("""SELECT COUNT(*), SUM(CASE WHEN ABS(e.current_px / y.price - 1) > 0.10
                THEN 1 ELSE 0 END) FROM ticker_entry_intact e JOIN ticker_yf y ON y.ticker = e.ticker
            WHERE e.current_px > 0 AND y.price > 0""").fetchone()
        if n_pair and (n_off or 0) > 0.10 * n_pair:
            warns.append(f"entry anchors: {n_off} of {n_pair} vs-entry prices are 10%+ off today's price "
                         f"(run entry_intact.py)")
    except sqlite3.OperationalError:
        pass

    # I8. feed freshness: warn when the tradeable-signal feeds fall behind.
    for tbl, col, days in [('form4_transactions','trans_date',21), ('holder_13d','filed',30),
                           ('catalysts_8k','filed',30), ('ticker_yf','asof',21),
                           ('congress_trades','disclosure_date',21)]:
        mx = one(f"SELECT MAX({col}) FROM {tbl}")
        if mx and (conn.execute("SELECT julianday('now')-julianday(?)", (mx,)).fetchone()[0] or 0) > days:
            warns.append(f"{tbl} stale: latest {str(mx)[:10]} (> {days}d)")

    for w in warns: print(f"WARN  {w}")
    for f in fails: print(f"FAIL  {f}")
    print(f"\n{len(fails)} failures, {len(warns)} warnings")
    return 1 if fails else 0

if __name__ == '__main__':
    sys.exit(run())
