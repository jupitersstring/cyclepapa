"""Ingest manually-researched frontier-market valuations into ticker_yf.

Frontier exchanges (Tanzania DSE, Rwanda RSE, Ghana GSE, BRVM, Colombo CSE,
Pakistan PSX, Vietnam) aren't covered by Yahoo Finance. These valuations
come from local-exchange / annual-report research.

Input CSV: TICKER|COMPANY|MCAP_USD_M|PE|PB|CURRENCY|SOURCE
"""
import os, sqlite3, sys, time

DB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "cyclepapa.db")

def num(x):
    try:
        return float(str(x).replace(",", "").strip())
    except Exception:
        return None

def run(text):
    conn = sqlite3.connect(DB)
    # ensure ticker_yf exists
    conn.execute("""CREATE TABLE IF NOT EXISTS ticker_yf (
      ticker TEXT PRIMARY KEY, mcap_m REAL, enterprise_value_m REAL,
      ev_ebitda REAL, pb_ratio REAL, pe_ttm REAL, fwd_pe REAL,
      ev_revenue REAL, peg REAL, price REAL, currency TEXT,
      shares_out_m REAL, ebitda_m REAL, total_debt_m REAL, total_cash_m REAL,
      profit_margin REAL, rev_growth REAL, sector TEXT, industry TEXT, asof TEXT)""")
    asof = time.strftime("%Y-%m-%d")
    n = 0
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "|" not in line: continue
        p = [x.strip() for x in line.split("|")]
        if len(p) < 3: continue
        ticker = p[0].upper()
        mcap = num(p[2]) if len(p) > 2 else None
        if mcap is None or "NO_DATA" in line.upper(): continue
        pe = num(p[3]) if len(p) > 3 else None
        pb = num(p[4]) if len(p) > 4 else None
        cur = p[5] if len(p) > 5 else None
        conn.execute("""INSERT OR REPLACE INTO ticker_yf
            (ticker, mcap_m, pe_ttm, pb_ratio, currency, sector, asof)
            VALUES (?,?,?,?,?,?,?)""",
            (ticker, mcap, pe, pb, cur, "Frontier Markets", asof))
        n += 1
        print(f"  {ticker:<14} mcap=${mcap:,.0f}M PE={pe} PB={pb} {cur}")
    conn.commit()
    print(f"\ningested {n} frontier valuations")

if __name__ == "__main__":
    text = sys.stdin.read() if not sys.argv[1:] else open(sys.argv[1]).read()
    run(text)
