"""Sharded version of scan_insider_batch — 6-8× faster.

Same scope as scan_insider_batch (top-signal small/mid caps), but uses
8 concurrent worker threads against EDGAR with a token-bucket governor
holding throughput to ~8 req/sec total (well within SEC's 10/sec limit).

DB writes serialised in the main thread to avoid lock contention.
"""
import json, os, re, sqlite3, subprocess, sys, time
import xml.etree.ElementTree as ET

DB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "cyclepapa.db")
UA = "cyclepapa-research admin@example.com"

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _shard import shard_map

def curl(url):
    return subprocess.run(["curl","-sk","--compressed","-m","12","-A",UA, url],
                          capture_output=True, text=True).stdout

_CIK = None
def cik_for(ticker):
    global _CIK
    if _CIK is None:
        raw = curl("https://www.sec.gov/files/company_tickers.json")
        try:
            j = json.loads(raw)
            _CIK = {v["ticker"].upper(): str(v["cik_str"]).zfill(10) for v in j.values()}
        except Exception:
            _CIK = {}
    return _CIK.get(ticker.upper())

def recent_form4(cik, lookback_days=180):
    j = json.loads(curl(f"https://data.sec.gov/submissions/CIK{cik}.json"))
    rec = j["filings"]["recent"]
    cutoff = time.strftime("%Y-%m-%d", time.localtime(time.time() - lookback_days*86400))
    out = []
    # Walk the ENTIRE recent block (≤1000 entries), not just the first 80 — a
    # fixed cap silently drops in-window Form 4s for high-volume filers.
    forms = rec["form"]
    for i in range(len(forms)):
        if forms[i] == "4" and rec["filingDate"][i] >= cutoff:
            out.append((rec["accessionNumber"][i], rec["primaryDocument"][i], rec["filingDate"][i]))
    return out

def parse_form4(cik, accession, primary_doc, tkr=None):
    acc = accession.replace("-", "")
    raw_doc = primary_doc.split("/")[-1]
    url = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc}/{raw_doc}"
    xml = curl(url)
    out = []
    try:
        root = ET.fromstring(xml)
    except ET.ParseError:
        return out
    # ISSUER symbol from the filing itself. A 10%-owner's Form 4 (Sumitomo buying
    # JEF; Blackstone buying PBLS) surfaces under the OWNER's CIK feed too — if we
    # book it to the scanned ticker, the buy lands on the owner's stock (SMFG/BX)
    # instead of the issuer's. The XML names the true issuer; trust it.
    iss_el = root.find(".//issuer/issuerTradingSymbol")
    issuer_sym = (iss_el.text or "").strip().upper().replace("/", "-") if (iss_el is not None and iss_el.text) else None
    owner = ""
    for o in root.iter("rptOwner"):
        n = o.find(".//rptOwnerName")
        if n is not None and n.text:
            owner = n.text.strip(); break
    role = ""
    for r in root.iter("reportingOwnerRelationship"):
        if r.find("isDirector") is not None and r.find("isDirector").text == "1": role = "Director"
        is_off = r.find("isOfficer")
        title = r.find("officerTitle")
        if is_off is not None and is_off.text == "1":
            role = title.text.strip() if title is not None and title.text else "Officer"
        if r.find("isTenPercentOwner") is not None and r.find("isTenPercentOwner").text == "1": role = "10%+ Owner"
        break
    # 10b5-1 checkbox (since 2023): filing-level "this trade was under a plan".
    # Splits mechanical scheduled selling from discretionary selling.
    plan_el = root.find(".//aff10b5One")
    planned = 1 if (plan_el is not None and (plan_el.text or "").strip() in ("1", "true")) else 0
    for tx in root.iter("nonDerivativeTransaction"):
        code_el = tx.find(".//transactionCode")
        if code_el is None or not code_el.text: continue
        code = code_el.text.strip()
        # equitySwapInvolved: the issuer marks the transaction as part of an
        # equity swap — insider "alignment" that is economically hedged.
        swap_el = tx.find(".//equitySwapInvolved")
        swap_inv = 1 if (swap_el is not None and (swap_el.text or "").strip() in ("1", "true")) else 0
        shares_el = tx.find(".//transactionShares/value")
        price_el  = tx.find(".//transactionPricePerShare/value")
        date_el   = tx.find(".//transactionDate/value")
        a_d_el    = tx.find(".//transactionAcquiredDisposedCode/value")
        if shares_el is None: continue
        try: shares = float(shares_el.text)
        except: continue
        # >100M shares in ONE insider transaction is never a real open-market
        # trade — it's an ADS-ratio filing artifact (SaverOne/VWAVW reported
        # 2.5B ordinary shares at the per-ADS price: 43,200x value inflation).
        # Re-scans would otherwise resurrect rows we corrected in place.
        if shares > 1e8: continue
        price = float(price_el.text) if (price_el is not None and price_el.text) else None
        # Likewise no US share PRICE exceeds ~$1M except BRK-A: corrupted price
        # fields (STNG "px=$1,230,435", FINS px==shares==4e7) get rejected here
        # so re-scans stop resurrecting them.
        if price and price > 2e5 and tkr != "BRK-A": continue
        acquired = 1 if (a_d_el is not None and a_d_el.text == "A") else 0
        out.append({"owner": owner, "role": role, "code": code,
                    "shares": shares, "price": price, "acquired": acquired,
                    "issuer_sym": issuer_sym, "swap_involved": swap_inv,
                    "planned_10b5": planned,
                    "trans_date": date_el.text if date_el is not None else None})
    return out

def target_tickers(conn, max_n, all_us=False):
    if all_us:
        # COMPLETE coverage: every US-listed name held by >=1 fund or with any
        # disclosed signal. No 'have' skip (re-scan refreshes buys AND sells),
        # no mcap cap, no top-N truncation. Foreign (.SUFFIX) excluded — SEC
        # Form 4 is US-only.
        out = []
        for r in conn.execute("""SELECT ticker FROM unified_signal
                WHERE is_us = 1 AND (smart_money_n >= 1 OR s1_top > 0 OR s3_new > 0
                                     OR s4_add > 0 OR activist_filings > 0)"""):
            t = r[0]
            if "." in t: continue
            if not re.match(r"^[A-Z][A-Z0-9\-]{0,5}$", t): continue
            out.append(t)
        return out[:max_n] if max_n else out
    have = {r[0] for r in conn.execute(
        "SELECT DISTINCT ticker FROM form4_transactions WHERE trans_date >= date('now','-180 days')")}
    sig = {}
    for r in conn.execute("""SELECT ticker, COUNT(DISTINCT CASE WHEN section=3 THEN fund END) s3,
        COUNT(DISTINCT CASE WHEN section=4 THEN fund END) s4,
        COUNT(DISTINCT CASE WHEN section=1 THEN fund END) s1
        FROM fund_positions WHERE ticker IS NOT NULL AND section IN (1,3,4) GROUP BY ticker"""):
        sig[r[0]] = sig.get(r[0], 0) + r[1]*3 + r[2]*1.5 + r[3]*1
    for r in conn.execute("SELECT subject_ticker FROM holder_13d WHERE subject_ticker IS NOT NULL"):
        sig[r[0]] = sig.get(r[0], 0) + 2
    for r in conn.execute("""SELECT ticker, COUNT(DISTINCT fund) c FROM fund_13f_holdings
        WHERE ticker IS NOT NULL GROUP BY ticker"""):
        if r[1] >= 3: sig[r[0]] = sig.get(r[0], 0) + min(r[1], 30) * 0.3
    keep = {}
    for tkr, s in sig.items():
        if "." in tkr or tkr in have: continue
        if not re.match(r"^[A-Z][A-Z0-9.\-]{0,5}$", tkr): continue
        mc = conn.execute("SELECT mcap_m FROM ticker_meta WHERE ticker=?", (tkr,)).fetchone()
        if mc and mc[0] and mc[0] > 50000: continue
        keep[tkr] = s
    return [t for t, _ in sorted(keep.items(), key=lambda x: -x[1])][:max_n]

def scan_one_ticker(tkr):
    """Pull open-market insider BUYS (code P) and SELLS (code S) for one ticker.
    These are the two market-signal codes the scorer uses — P drives the buy
    signal, S the sell counter-signal. Compensation/admin codes (A grants,
    F tax, M exercises, …) carry no market signal and are skipped. Worker thread."""
    cik = cik_for(tkr)
    if not cik: return []
    try:
        filings = recent_form4(cik, lookback_days=180)
    except Exception:
        return []
    rows = []
    for acc, doc, dt in filings:
        try:
            txns = parse_form4(cik, acc, doc, tkr=tkr)
        except Exception:
            continue
        for t in txns:
            # P/S = market signal; K = equity swap (insider hedging detector)
            if t["code"] not in ("P", "S", "K"): continue
            rows.append((acc, t.get("issuer_sym") or tkr, t["owner"], t["role"], t["trans_date"],
                         t["code"], t["shares"], t["price"], t["acquired"],
                         t.get("swap_involved", 0), t.get("planned_10b5", 0),
                         f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc.replace('-','')}/{doc}"))
    return rows

def ensure_dedup_index(conn):
    """Remove any duplicate transactions, then enforce uniqueness so re-scans
    are idempotent (INSERT OR IGNORE)."""
    conn.execute("""DELETE FROM form4_transactions WHERE id NOT IN (
        SELECT MIN(id) FROM form4_transactions
        GROUP BY accession, owner, code, trans_date, shares, COALESCE(price,-1))""")
    conn.execute("""CREATE UNIQUE INDEX IF NOT EXISTS ux_form4_txn
        ON form4_transactions(accession, owner, code, trans_date, shares, COALESCE(price,-1))""")
    conn.commit()

def run(max_n=1500, n_workers=8, rps=8, all_us=False):
    conn = sqlite3.connect(DB, timeout=60); conn.execute('PRAGMA busy_timeout=60000')
    ensure_dedup_index(conn)
    targets = target_tickers(conn, max_n if not all_us else 0, all_us=all_us)
    print(f"sharded scan: {len(targets)} tickers, {n_workers} workers, {rps} req/s"
          f"{' [FULL US-held universe, all codes]' if all_us else ''}")

    n_buys = 0
    progress = [0]
    def on_result(tkr, rows):
        nonlocal n_buys
        for row in rows:
            try:
                conn.execute("""INSERT OR IGNORE INTO form4_transactions
                    (accession, ticker, owner, role, trans_date, code, shares, price, acquired,
                     swap_involved, planned_10b5, source_url)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""", row)
                n_buys += 1
            except Exception:
                pass
        progress[0] += 1
        if progress[0] % 100 == 0:
            conn.commit()
            print(f"  [{progress[0]}/{len(targets)}] {tkr} txns_seen={n_buys}")

    def on_error(tkr, exc):
        progress[0] += 1
        if progress[0] % 50 == 0:
            print(f"  [{progress[0]}/{len(targets)}] {tkr} ERR {exc}")

    shard_map(scan_one_ticker, targets, n_workers=n_workers, rps=rps,
              on_result=on_result, on_error=on_error)
    conn.commit()
    # Self-heal: a scan can book a filing under the scan-target ticker while an
    # older row books it under another — resolve via EDGAR's issuer symbol.
    import fix_form4_multiticker
    fix_form4_multiticker.run(conn)
    print(f"\ndone: {n_buys} P-code buys ingested across {len(targets)} tickers scanned")

if __name__ == "__main__":
    args = sys.argv[1:]
    if args and args[0] == "all":
        run(all_us=True)
    else:
        run(max_n=int(args[0]) if args else 1500)
