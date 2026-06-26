"""Add EV/EBITDA and P/B valuation ratios for each US ticker.

Pulls from SEC XBRL companyconcept endpoint (no auth needed):
  EBITDA      = OperatingIncomeLoss (TTM) + DepreciationDepletionAndAmortization (TTM)
                fallback: NetIncomeLoss + InterestExpense + IncomeTaxExpense + D&A
  Book value  = StockholdersEquity (most recent)
  Net debt    = (LongTermDebt + current portion) - cash

Then:
  EV       = mcap + net_debt
  EV/EBITDA = EV / EBITDA   (only if EBITDA > 0)
  P/B       = mcap / book_value   (only if book_value > 0)

Sharded for speed (8 workers, token-bucket governor). Stored in new
table ticker_valuation. ADDITIVE — does not touch any existing table.
"""
import json, os, sqlite3, subprocess, sys, time

DB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "cyclepapa.db")
UA = "cyclepapa-research admin@example.com"

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _shard import shard_map

def curl(url):
    return subprocess.run(["curl","-sk","--compressed","-m","10","-A",UA, url],
                          capture_output=True).stdout

_CIK = None
def cik_for(t):
    global _CIK
    if _CIK is None:
        try:
            j = json.loads(curl("https://www.sec.gov/files/company_tickers.json"))
            _CIK = {v["ticker"].upper(): str(v["cik_str"]).zfill(10) for v in j.values()}
        except Exception:
            _CIK = {}
    return _CIK.get(t.upper())

def concept_ttm(cik, ns, tag):
    """Return TTM sum (4 quarters) or latest annual for a flow concept."""
    body = curl(f"https://data.sec.gov/api/xbrl/companyconcept/CIK{cik}/{ns}/{tag}.json")
    try:
        j = json.loads(body)
    except Exception:
        return None
    entries = []
    for unit, items in j.get("units", {}).items():
        for e in items:
            if e.get("val") is None: continue
            entries.append((e.get("end") or "", e.get("val"), e.get("fp"), e.get("form")))
    if not entries: return None
    # Prefer latest annual (FY)
    annual = sorted([e for e in entries if e[2] == "FY"], key=lambda x: x[0])
    if annual:
        return annual[-1][1]
    # else sum last 4 quarterly
    q = sorted([e for e in entries if e[2] and e[2].startswith("Q")], key=lambda x: x[0])
    if len(q) >= 4:
        return sum(e[1] for e in q[-4:])
    return entries[-1][1] if entries else None

def concept_latest(cik, ns, tag):
    """Return most recent point-in-time value (for balance-sheet concepts)."""
    body = curl(f"https://data.sec.gov/api/xbrl/companyconcept/CIK{cik}/{ns}/{tag}.json")
    try:
        j = json.loads(body)
    except Exception:
        return None
    best = None
    for unit, items in j.get("units", {}).items():
        for e in items:
            if e.get("val") is None: continue
            end = e.get("end") or ""
            if best is None or end > best[0]:
                best = (end, e.get("val"))
    return best[1] if best else None

def compute_one(tkr):
    """Compute (ebitda, book_value, net_debt) for one ticker. Worker-thread fn."""
    cik = cik_for(tkr)
    if not cik:
        return None
    # EBITDA components
    op_inc = concept_ttm(cik, "us-gaap", "OperatingIncomeLoss")
    dda = (concept_ttm(cik, "us-gaap", "DepreciationDepletionAndAmortization")
           or concept_ttm(cik, "us-gaap", "DepreciationAmortizationAndAccretionNet")
           or concept_ttm(cik, "us-gaap", "DepreciationAndAmortization"))
    ebitda = None
    if op_inc is not None and dda is not None:
        ebitda = op_inc + dda
    elif op_inc is not None:
        ebitda = op_inc   # EBIT as fallback (conservative — will overstate EV/EBITDA)
    # Book value (total stockholders equity)
    book = (concept_latest(cik, "us-gaap", "StockholdersEquity")
            or concept_latest(cik, "us-gaap", "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"))
    # Net debt
    cash = (concept_latest(cik, "us-gaap", "CashAndCashEquivalentsAtCarryingValue")
            or concept_latest(cik, "us-gaap", "Cash"))
    debt_lt = (concept_latest(cik, "us-gaap", "LongTermDebtNoncurrent")
               or concept_latest(cik, "us-gaap", "LongTermDebt"))
    debt_cur = (concept_latest(cik, "us-gaap", "LongTermDebtCurrent")
                or concept_latest(cik, "us-gaap", "ShortTermBorrowings"))
    net_debt = None
    if debt_lt is not None or debt_cur is not None or cash is not None:
        net_debt = (debt_lt or 0) + (debt_cur or 0) - (cash or 0)
    return {"cik": cik, "ebitda": ebitda, "book": book, "net_debt": net_debt,
            "op_inc": op_inc, "dda": dda, "cash": cash}

def init_schema(conn):
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS ticker_valuation (
      ticker TEXT PRIMARY KEY, cik TEXT,
      ebitda_ttm REAL, book_value REAL, net_debt REAL,
      ev_m REAL, ev_ebitda REAL, pb_ratio REAL,
      ebitda_is_ebit_fallback INTEGER,
      asof TEXT);
    CREATE INDEX IF NOT EXISTS idx_tv_evebitda ON ticker_valuation(ev_ebitda);
    CREATE INDEX IF NOT EXISTS idx_tv_pb ON ticker_valuation(pb_ratio);
    """)

def run(max_n=3000, n_workers=8, rps=8):
    conn = sqlite3.connect(DB)
    init_schema(conn)
    have = {r[0] for r in conn.execute("SELECT ticker FROM ticker_valuation WHERE ev_ebitda IS NOT NULL OR pb_ratio IS NOT NULL")}
    # Target: US tickers in unified_signal with mcap, by score priority
    targets = [r[0] for r in conn.execute("""
        SELECT us.ticker FROM unified_signal us
        JOIN ticker_meta tm ON tm.ticker = us.ticker
        WHERE us.is_us = 1 AND tm.mcap_m IS NOT NULL
        ORDER BY us.score DESC""")]
    todo = [t for t in targets if t not in have][:max_n]
    print(f"valuation enrich: {len(todo)} US tickers (skipping {len(have)} done), {n_workers} workers")

    asof = time.strftime("%Y-%m-%d")
    progress = [0]
    n_ev = n_pb = 0
    def on_result(tkr, res):
        nonlocal n_ev, n_pb
        progress[0] += 1
        if not res:
            return
        mc = conn.execute("SELECT mcap_m FROM ticker_meta WHERE ticker=?", (tkr,)).fetchone()
        mcap_m = mc[0] if mc else None
        ebitda = res["ebitda"]; book = res["book"]; net_debt = res["net_debt"]
        ev_m = ev_ebitda = pb = None
        is_ebit = 1 if (res["op_inc"] is not None and res["dda"] is None) else 0
        if mcap_m is not None:
            ev_m = mcap_m + (net_debt or 0) / 1e6  # net_debt is raw $, mcap_m is $M
            if ebitda and ebitda > 0:
                ev_ebitda = ev_m / (ebitda / 1e6)
                n_ev += 1
            if book and book > 0:
                pb = (mcap_m * 1e6) / book
                n_pb += 1
        conn.execute("""INSERT OR REPLACE INTO ticker_valuation VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (tkr, res["cik"],
             ebitda/1e6 if ebitda else None,
             book/1e6 if book else None,
             net_debt/1e6 if net_debt else None,
             ev_m, ev_ebitda, pb, is_ebit, asof))
        if progress[0] % 100 == 0:
            conn.commit()
            print(f"  [{progress[0]}/{len(todo)}] {tkr} ev/ebitda={n_ev} pb={n_pb}")

    def on_error(tkr, exc):
        progress[0] += 1

    shard_map(compute_one, todo, n_workers=n_workers, rps=rps,
              on_result=on_result, on_error=on_error)
    conn.commit()
    print(f"\ndone: {n_ev} EV/EBITDA, {n_pb} P/B computed")

    # sanity
    print("\n--- sample (top score names) ---")
    for r in conn.execute("""SELECT v.ticker, v.ev_ebitda, v.pb_ratio, v.ebitda_is_ebit_fallback
        FROM ticker_valuation v JOIN unified_signal us ON us.ticker=v.ticker
        WHERE v.ev_ebitda IS NOT NULL ORDER BY us.score DESC LIMIT 15"""):
        flag = " (EBIT)" if r[3] else ""
        print(f"  {r[0]:<6} EV/EBITDA={r[1]:>7.1f}x  P/B={r[2] or 0:>6.2f}x{flag}")

if __name__ == "__main__":
    run(max_n=int(sys.argv[1]) if sys.argv[1:] else 3000)
