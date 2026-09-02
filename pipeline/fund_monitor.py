"""Fund-Positioning Monitor — rebuilt from typed DB.

Mirrors the original conviction / 13D / new-position / material-adds monitor
the user built, but now driven by the ingested fund_positions table so every
ticker, %, and $ amount is queryable. Also adds the things the prior
monitor lacked: dedup, multi-fund convergence by section, and a join to live
EDGAR Form-4 cluster + empirical Tier-1 so the most-active funds in the
universe are surfaced against the live signal.
"""
import os, sqlite3
DB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "cyclepapa.db")

VIEWS = """
DROP VIEW IF EXISTS v_top_conviction;
CREATE VIEW v_top_conviction AS
  SELECT ticker, COUNT(DISTINCT fund) AS funds, SUM(dollar_m) AS dollar_m,
         MAX(pct_value) AS max_pct, MIN(pct_value) AS min_pct
  FROM fund_positions WHERE section=1 AND ticker IS NOT NULL
  GROUP BY ticker;

DROP VIEW IF EXISTS v_top_material_adds;
CREATE VIEW v_top_material_adds AS
  SELECT ticker, COUNT(DISTINCT fund) AS funds, SUM(dollar_m) AS dollar_m,
         MAX(pct_value) AS max_pct, GROUP_CONCAT(DISTINCT fund) AS funds_list
  FROM fund_positions WHERE section=4 AND ticker IS NOT NULL
  GROUP BY ticker;

DROP VIEW IF EXISTS v_top_new_positions;
CREATE VIEW v_top_new_positions AS
  SELECT ticker, COUNT(DISTINCT fund) AS funds, SUM(dollar_m) AS dollar_m,
         GROUP_CONCAT(DISTINCT fund) AS funds_list
  FROM fund_positions WHERE section=3 AND ticker IS NOT NULL
  GROUP BY ticker;

DROP VIEW IF EXISTS v_top_13d_filings;
CREATE VIEW v_top_13d_filings AS
  SELECT ticker, COUNT(DISTINCT fund) AS funds, MAX(pct_value) AS max_pct_company,
         GROUP_CONCAT(DISTINCT fund) AS funds_list
  FROM fund_positions WHERE section=2 AND ticker IS NOT NULL
  GROUP BY ticker;

DROP VIEW IF EXISTS v_fund_activity;
CREATE VIEW v_fund_activity AS
  SELECT fund,
         SUM(CASE WHEN section=1 THEN 1 ELSE 0 END) AS conviction_n,
         SUM(CASE WHEN section=2 THEN 1 ELSE 0 END) AS threshold_n,
         SUM(CASE WHEN section=3 THEN 1 ELSE 0 END) AS new_pos_n,
         SUM(CASE WHEN section=4 THEN 1 ELSE 0 END) AS adds_n,
         COUNT(*) AS total
  FROM fund_positions GROUP BY fund;
"""

def run():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    conn.executescript(VIEWS)
    conn.commit()

    print("=== TOP MATERIAL ADDS — names being accumulated across the universe ===")
    print(f"{'tkr':<8} {'#funds':<7} {'$M':<10} 'max%' funds")
    for r in conn.execute("""SELECT * FROM v_top_material_adds
                             WHERE funds >= 2 ORDER BY funds DESC, dollar_m DESC LIMIT 25"""):
        d = f"${r['dollar_m']:.0f}M" if r['dollar_m'] else ""
        mx = f"{r['max_pct']:.0f}%" if r['max_pct'] else ""
        print(f"  {r['ticker']:<8} {r['funds']:<7} {d:<10} {mx:<6} {r['funds_list'][:80]}")

    print("\n=== TOP NEW POSITIONS — names initiated by multiple funds ===")
    for r in conn.execute("""SELECT * FROM v_top_new_positions
                             WHERE funds >= 2 ORDER BY funds DESC, dollar_m DESC LIMIT 20"""):
        d = f"${r['dollar_m']:.0f}M" if r['dollar_m'] else ""
        print(f"  {r['ticker']:<8} {r['funds']:<7} {d:<10} {r['funds_list'][:80]}")

    print("\n=== TOP 13D / 13G THRESHOLD — multi-filer activist consensus ===")
    for r in conn.execute("""SELECT * FROM v_top_13d_filings
                             WHERE funds >= 2 ORDER BY funds DESC, max_pct_company DESC LIMIT 20"""):
        mx = f"{r['max_pct_company']:.1f}%" if r['max_pct_company'] else ""
        print(f"  {r['ticker']:<8} {r['funds']:<7} {mx:<7} {r['funds_list'][:80]}")

    print("\n=== HIGHEST-CONVICTION HOLDINGS (sec 1) — multi-fund top picks ===")
    for r in conn.execute("""SELECT * FROM v_top_conviction
                             WHERE funds >= 3 ORDER BY funds DESC, dollar_m DESC LIMIT 25"""):
        d = f"${r['dollar_m']:.0f}M" if r['dollar_m'] else ""
        mx = f"{r['max_pct']:.0f}%" if r['max_pct'] else ""
        print(f"  {r['ticker']:<8} {r['funds']:<7} {d:<10} max_book%={mx}")

    print("\n=== MOST ACTIVE FUNDS (rows tracked) ===")
    for r in conn.execute("""SELECT * FROM v_fund_activity ORDER BY total DESC LIMIT 20"""):
        print(f"  {r['fund'][:36]:<36}  conv {r['conviction_n']:<3} 13D {r['threshold_n']:<3} new {r['new_pos_n']:<3} adds {r['adds_n']:<3} total {r['total']}")

    # Join to live signal: which fund-monitor names also appear in current EDGAR cluster?
    print("\n=== INTERSECTION: fund-monitor multi-fund adds × live EDGAR insider cluster ===")
    for r in conn.execute("""
        SELECT m.ticker, m.funds, m.dollar_m, ic.n_insiders, ic.total_usd_m AS insider_m
        FROM v_top_material_adds m
        JOIN insider_clusters ic ON ic.ticker = m.ticker
        WHERE m.funds >= 2 ORDER BY m.funds DESC"""):
        print(f"  {r['ticker']:<8} fund-adds:{r['funds']} ${r['dollar_m']:.0f}M  |  "
              f"insider-cluster:{r['n_insiders']} insiders ${r['insider_m']}M")

if __name__ == "__main__":
    run()
