"""Systematic gap-closer — orchestrate all backfills in one place.

Closes these gaps identified by the audit:
  1. 272 tickers in unified_signal with no ticker_meta row → enrich them
  2. 981 US tickers with price but no mcap → try more XBRL tags
  3. 285 holder_13d filings with no parsed subject_ticker → re-parse
  4. 649 holder_13d filings with no parsed pct_class → re-parse
  5. Broader Form 4 scan for the smart-money universe

This is a single orchestration script — pulls from existing helpers.
"""
import json, os, re, sqlite3, subprocess, sys, time

DB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "cyclepapa.db")
UA = "cyclepapa-research admin@example.com"

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def curl(url, timeout=12):
    return subprocess.run(["curl","-sk","--compressed","-m",str(timeout),"-A",UA, url],
                          capture_output=True).stdout

# ---- Gap 1: enrich missing ticker_meta rows ---------------------------------
def gap1_missing_meta(conn):
    print("\n=== Gap 1: ticker_meta backfill ===")
    todo = [r[0] for r in conn.execute("""
        SELECT DISTINCT us.ticker FROM unified_signal us
        LEFT JOIN ticker_meta tm ON tm.ticker = us.ticker
        WHERE tm.ticker IS NULL
        ORDER BY us.score DESC""")]
    print(f"  {len(todo)} tickers to enrich")
    from enrich_tickers import yahoo_chart_meta, cik_for_ticker, shares_outstanding
    n_ok = 0
    asof = time.strftime("%Y-%m-%d")
    for i, t in enumerate(todo):
        if not re.match(r'^[A-Z0-9][A-Z0-9.\-]{0,9}$', t): continue
        meta = yahoo_chart_meta(t)
        if not meta or not meta.get("price"): continue
        mcap_m = None; so_m = None
        if "." not in t:
            cik = cik_for_ticker(t)
            if cik:
                so = shares_outstanding(cik)
                if so and meta["price"]:
                    so_m = so / 1e6
                    mcap_m = so_m * meta["price"]
        conn.execute("""INSERT OR REPLACE INTO ticker_meta
            (ticker, name, exchange, market, sector, industry, mcap_m, price,
             price_currency, adv_3m_usd_m, shares_out_m, pe_ttm, fwd_pe, beta, asof)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (t, meta["name"], meta["exchange"], None, None, None,
             mcap_m, meta["price"], meta["currency"],
             meta["adv_usd_m"], so_m, None, None, None, asof))
        n_ok += 1
        if i % 30 == 0 and i > 0:
            conn.commit()
            print(f"    [{i+1}/{len(todo)}] ok={n_ok}")
        time.sleep(0.15)
    conn.commit()
    print(f"  done: {n_ok}/{len(todo)} enriched")

# ---- Gap 2: try harder for mcap on US tickers with price but no mcap --------
SHARE_TAGS = [
    ("us-gaap", "CommonStockSharesOutstanding"),
    ("us-gaap", "CommonStockSharesIssued"),
    ("dei", "EntityCommonStockSharesOutstanding"),
    ("dei", "EntityCommonStockSharesIssued"),
    ("us-gaap", "WeightedAverageNumberOfSharesOutstandingBasic"),
    ("us-gaap", "WeightedAverageNumberOfDilutedSharesOutstanding"),
    ("us-gaap", "SharesOutstanding"),
]
def companyconcept_shares(cik):
    cik10 = str(cik).zfill(10)
    for ns, tag in SHARE_TAGS:
        body = curl(f"https://data.sec.gov/api/xbrl/companyconcept/CIK{cik10}/{ns}/{tag}.json", 8)
        try:
            j = json.loads(body)
            units = j.get("units", {})
            best = None
            for _, entries in units.items():
                for e in entries:
                    end = e.get("end") or ""
                    if best is None or end > best[0]:
                        best = (end, e.get("val"))
            if best and best[1]: return best[1]
        except Exception:
            continue
    return None

def gap2_mcap_backfill(conn):
    print("\n=== Gap 2: mcap backfill (deeper XBRL search) ===")
    from enrich_tickers import cik_for_ticker
    todo = [r[0] for r in conn.execute("""
        SELECT ticker FROM ticker_meta
        WHERE price IS NOT NULL AND mcap_m IS NULL
          AND ticker NOT LIKE '%.%'""")]
    print(f"  {len(todo)} US tickers to retry")
    n_fixed = 0
    for i, t in enumerate(todo):
        cik = cik_for_ticker(t)
        if not cik:
            continue
        so = companyconcept_shares(cik)
        time.sleep(0.15)
        if not so: continue
        price = conn.execute("SELECT price FROM ticker_meta WHERE ticker=?", (t,)).fetchone()[0]
        if not price: continue
        so_m = so / 1e6
        mcap_m = so_m * price
        conn.execute("UPDATE ticker_meta SET shares_out_m=?, mcap_m=? WHERE ticker=?",
                     (so_m, mcap_m, t))
        n_fixed += 1
        if i % 50 == 0 and i > 0:
            conn.commit()
            print(f"    [{i+1}/{len(todo)}] fixed={n_fixed}")
    conn.commit()
    print(f"  done: {n_fixed}/{len(todo)} mcaps resolved")

# ---- Gap 3+4: re-parse holder_13d with no subject_ticker or pct -------------
def gap34_reparse_13d(conn):
    print("\n=== Gap 3+4: holder_13d re-parse ===")
    from ingest_13d import parse_subject, TICKER_BY_CIK
    # Reload ticker map
    import ingest_13d as i13
    try:
        j = json.loads(curl("https://www.sec.gov/files/company_tickers.json"))
        i13.TICKER_BY_CIK = {str(v["cik_str"]): v["ticker"] for v in j.values()}
    except Exception:
        pass

    todo = list(conn.execute("""
        SELECT holder_cik, accession, source_url FROM holder_13d
        WHERE (subject_ticker IS NULL OR pct_class IS NULL)
          AND source_url IS NOT NULL
        LIMIT 800"""))
    print(f"  {len(todo)} filings to re-parse")
    n_fixed_t = n_fixed_p = 0
    for i, (cik, acc, src) in enumerate(todo):
        try:
            subj, tkr, pct, _ = parse_subject(cik, acc, "primary_doc.xml")
        except Exception:
            continue
        time.sleep(0.12)
        if tkr:
            subj_cik_back = next((c for c, t in i13.TICKER_BY_CIK.items() if t == tkr), None)
            conn.execute("""UPDATE holder_13d SET subject_ticker=?, subject_cik=?
                WHERE holder_cik=? AND accession=? AND subject_ticker IS NULL""",
                (tkr, subj_cik_back, cik, acc))
            n_fixed_t += conn.total_changes
        if pct:
            conn.execute("""UPDATE holder_13d SET pct_class=?
                WHERE holder_cik=? AND accession=? AND pct_class IS NULL""",
                (pct, cik, acc))
            n_fixed_p += 1
        if i % 50 == 0 and i > 0:
            conn.commit()
            print(f"    [{i+1}/{len(todo)}] ticker_fixed={n_fixed_t} pct_fixed={n_fixed_p}")
    conn.commit()
    print(f"  done: {n_fixed_t} tickers + {n_fixed_p} pcts re-parsed")

def main():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    which = sys.argv[1] if sys.argv[1:] else "all"
    if which in ("1", "meta", "all"): gap1_missing_meta(conn)
    if which in ("2", "mcap", "all"): gap2_mcap_backfill(conn)
    if which in ("34", "13d", "all"): gap34_reparse_13d(conn)
    print("\nclose_all_gaps complete.")

if __name__ == "__main__":
    main()
