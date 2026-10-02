"""Add per-ticker fundamentals from SEC XBRL company concepts.

For each US-listed ticker with a CIK, pull canonical financial metrics
via the small data.sec.gov/api/xbrl/companyconcept/<concept>.json endpoint:

  - Revenue (TTM)             us-gaap:Revenues / RevenueFromContractWithCustomer
  - Operating cash flow (TTM) us-gaap:NetCashProvidedByOperatingActivities
  - Free cash flow (TTM)      OCF - CapEx
  - Net debt                  long-term debt - cash
  - EPS basic (TTM)           EarningsPerShareBasic
  - Gross margin %            (Revenue - CostOfGoodsSold) / Revenue
  - Operating margin %        OperatingIncomeLoss / Revenue

Computes P/E (price × shares / net income) and EV/Sales (mcap+netdebt/sales).
"""
import json, os, sqlite3, subprocess, sys, time

DB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "cyclepapa.db")
UA = "cyclepapa-research admin@example.com"

def curl(url):
    return subprocess.run(["curl","-sk","--compressed","-m","8","-A",UA, url],
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

def concept(cik, ns, tag):
    """Return list of (end_date, val) entries for a concept, sorted by date."""
    body = curl(f"https://data.sec.gov/api/xbrl/companyconcept/CIK{cik}/{ns}/{tag}.json")
    try:
        j = json.loads(body)
        out = []
        for unit, entries in j.get("units", {}).items():
            for e in entries:
                out.append((e.get("end") or e.get("fp") or "", e.get("val"), e.get("fp")))
        out.sort()
        return out
    except Exception:
        return []

def ttm_sum(entries, recent_months=12):
    """Sum the last 4 quarterly entries OR pick the most recent annual."""
    if not entries: return None
    # filter to non-None values
    entries = [e for e in entries if e[1] is not None]
    if not entries: return None
    # try annual: a single FY entry
    annual = [e for e in entries if e[2] == "FY"]
    if annual:
        annual.sort()
        return annual[-1][1]
    # else sum last 4 quarterly
    quarterly = [e for e in entries if e[2] and e[2].startswith("Q")]
    quarterly.sort()
    if len(quarterly) >= 4:
        return sum(e[1] for e in quarterly[-4:])
    # else return latest
    return entries[-1][1]

def init_schema(conn):
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS ticker_fundamentals (
      ticker TEXT PRIMARY KEY,
      cik TEXT,
      revenue_ttm REAL, ocf_ttm REAL, capex_ttm REAL, fcf_ttm REAL,
      net_debt REAL, cash REAL, total_debt REAL,
      eps_ttm REAL, net_income_ttm REAL,
      gross_margin REAL, operating_margin REAL,
      pe_ttm REAL, ev_sales REAL, ev_ebitda REAL,
      revenue_yoy REAL, fcf_yield REAL,
      asof TEXT);
    CREATE INDEX IF NOT EXISTS idx_tf_fcfy ON ticker_fundamentals(fcf_yield);
    CREATE INDEX IF NOT EXISTS idx_tf_evs ON ticker_fundamentals(ev_sales);
    """)

def fundamentals_for_cik(cik):
    """Pull and compute key fundamentals for one CIK."""
    rev = ttm_sum(concept(cik, "us-gaap", "Revenues")) or \
          ttm_sum(concept(cik, "us-gaap", "RevenueFromContractWithCustomerExcludingAssessedTax")) or \
          ttm_sum(concept(cik, "us-gaap", "SalesRevenueNet")) or \
          ttm_sum(concept(cik, "us-gaap", "RevenueFromContractWithCustomerIncludingAssessedTax"))
    ocf = ttm_sum(concept(cik, "us-gaap", "NetCashProvidedByUsedInOperatingActivities"))
    capex = ttm_sum(concept(cik, "us-gaap", "PaymentsToAcquirePropertyPlantAndEquipment")) or \
            ttm_sum(concept(cik, "us-gaap", "PaymentsForCapitalImprovements"))
    cash = ttm_sum(concept(cik, "us-gaap", "CashAndCashEquivalentsAtCarryingValue")) or \
           ttm_sum(concept(cik, "us-gaap", "Cash"))
    debt_lt = ttm_sum(concept(cik, "us-gaap", "LongTermDebt")) or \
              ttm_sum(concept(cik, "us-gaap", "LongTermDebtNoncurrent"))
    debt_st = ttm_sum(concept(cik, "us-gaap", "LongTermDebtCurrent")) or \
              ttm_sum(concept(cik, "us-gaap", "ShortTermBorrowings"))
    ni = ttm_sum(concept(cik, "us-gaap", "NetIncomeLoss"))
    eps = ttm_sum(concept(cik, "us-gaap", "EarningsPerShareBasic"))
    cogs = ttm_sum(concept(cik, "us-gaap", "CostOfGoodsAndServicesSold")) or \
           ttm_sum(concept(cik, "us-gaap", "CostOfRevenue"))
    op_inc = ttm_sum(concept(cik, "us-gaap", "OperatingIncomeLoss"))
    return {
        "revenue_ttm": rev,
        "ocf_ttm": ocf,
        "capex_ttm": capex,
        "fcf_ttm": (ocf - capex) if ocf is not None and capex is not None else None,
        "cash": cash,
        "total_debt": (debt_lt or 0) + (debt_st or 0) if (debt_lt or debt_st) else None,
        "net_debt": ((debt_lt or 0) + (debt_st or 0)) - (cash or 0) if (debt_lt or debt_st or cash) else None,
        "net_income_ttm": ni,
        "eps_ttm": eps,
        "gross_margin": ((rev - cogs)/rev) if rev and cogs else None,
        "operating_margin": (op_inc/rev) if op_inc and rev else None,
    }

def run(max_n=2500):
    conn = sqlite3.connect(DB)
    init_schema(conn)
    have = {r[0] for r in conn.execute(
        "SELECT ticker FROM ticker_fundamentals WHERE revenue_ttm IS NOT NULL")}
    # Target: tickers in unified_signal with mcap_m known and US-listed
    targets = [r[0] for r in conn.execute(
        """SELECT us.ticker FROM unified_signal us
           JOIN ticker_meta tm ON tm.ticker = us.ticker
           WHERE tm.mcap_m IS NOT NULL
             AND tm.ticker NOT LIKE '%.%'
             AND tm.mcap_m < 50000
           ORDER BY us.score DESC""")]
    todo = [t for t in targets if t not in have][:max_n]
    print(f"fundamentals for {len(todo)} US tickers (skipping {len(have)} done)")
    n_ok = n_skip = 0
    asof = time.strftime("%Y-%m-%d")
    for i, tkr in enumerate(todo):
        cik = cik_for(tkr)
        if not cik:
            n_skip += 1; continue
        f = fundamentals_for_cik(cik)
        time.sleep(0.2)
        # also need mcap to compute ratios
        mc = conn.execute("SELECT mcap_m, price FROM ticker_meta WHERE ticker=?", (tkr,)).fetchone()
        mcap_m = mc[0] if mc else None
        ev_sales = pe = fcf_yield = None
        if mcap_m and f["revenue_ttm"]:
            ev = mcap_m + (f["net_debt"] or 0)/1e6
            ev_sales = ev / (f["revenue_ttm"]/1e6)
        if mcap_m and f["net_income_ttm"] and f["net_income_ttm"] > 0:
            pe = (mcap_m*1e6) / f["net_income_ttm"]
        if mcap_m and f["fcf_ttm"]:
            fcf_yield = (f["fcf_ttm"]/1e6) / mcap_m * 100
        conn.execute("""INSERT OR REPLACE INTO ticker_fundamentals VALUES
            (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (tkr, cik,
             f["revenue_ttm"], f["ocf_ttm"], f["capex_ttm"], f["fcf_ttm"],
             f["net_debt"], f["cash"], f["total_debt"],
             f["eps_ttm"], f["net_income_ttm"],
             f["gross_margin"], f["operating_margin"],
             pe, ev_sales, None,
             None, fcf_yield,
             asof))
        n_ok += 1
        if i % 50 == 0 and i > 0:
            conn.commit()
            print(f"  [{i+1}/{len(todo)}] {tkr} ok={n_ok} skip={n_skip}")
    conn.commit()
    print(f"\ndone. {n_ok} enriched, {n_skip} skipped")

if __name__ == "__main__":
    run(max_n=int(sys.argv[1]) if sys.argv[1:] else 2500)
