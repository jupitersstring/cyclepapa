"""Unified per-ticker score combining every signal we have.

Inputs (joined per ticker):
  - fund_13f_holdings       smart money holding count + position size
  - fund_positions          XLSX-derived signals by section
  - holder_13d              SC 13D/G filings + activist pct
  - insider_clusters        live insider buy cluster (window_end ≤180d)
  - form4_transactions      recent open-market buys (code=P)
  - ticker_meta             mcap, exchange, ADV, price (from enrich_tickers.py)
  - candidates              curated qualitative tier + sector
  - expected_return         base-rate weighted ER

Output table: unified_signal (ticker, components, score, mcap_bucket)
Score formula:
  smart_money       =  log(1 + n_funds_13F)
  S3_new_init       =  3 * n_funds_section3
  S4_material_add   =  1.5 * n_funds_section4
  S1_top_pick       =  2 * n_funds_section1
  activist_13G_pct  =  0.5 * max_pct_class (capped at 30)
  insider_cluster   =  +5 if live cluster, +10 if 3+ insiders, +15 if 5+
  form4_buying      =  log(1 + cumulative_open_market_$M)
  micro_bonus       =  +5 if mcap <$300M, +3 if <$2B
  expected_return   =  ER% * 0.5
"""
import math, os, sqlite3, sys

DB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "cyclepapa.db")

def run():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    conn.executescript("""
    DROP TABLE IF EXISTS unified_signal;
    CREATE TABLE unified_signal (
      ticker TEXT PRIMARY KEY,
      name TEXT, exchange TEXT, sector TEXT, mcap_m REAL, price REAL,
      mcap_bucket TEXT,
      smart_money_n INTEGER,
      s1_top INTEGER, s2_thresh INTEGER, s3_new INTEGER, s4_add INTEGER,
      activist_filings INTEGER, activist_max_pct REAL,
      insider_cluster_dollars_m REAL, insider_n INTEGER,
      form4_buy_usd_m REAL,
      expected_return_pct REAL,
      score REAL,
      components TEXT
    );
    CREATE INDEX idx_us_score ON unified_signal(score DESC);
    CREATE INDEX idx_us_bucket ON unified_signal(mcap_bucket);
    """)

    # Per-ticker signals
    sm = {r[0]: r[1] for r in conn.execute(
        "SELECT ticker, COUNT(DISTINCT fund) FROM fund_13f_holdings WHERE ticker IS NOT NULL GROUP BY ticker")}
    s_by = {}
    for r in conn.execute("""SELECT ticker, section, COUNT(DISTINCT fund) c
        FROM fund_positions WHERE ticker IS NOT NULL GROUP BY ticker, section"""):
        s_by.setdefault(r["ticker"], {})[r["section"]] = r["c"]
    act = {}
    for r in conn.execute("""SELECT subject_ticker, COUNT(*) n, MAX(pct_class) m
        FROM holder_13d WHERE subject_ticker IS NOT NULL GROUP BY subject_ticker"""):
        act[r["subject_ticker"]] = (r["n"], r["m"] or 0)
    cl = {}
    for r in conn.execute("""SELECT ticker, n_insiders, total_usd_m FROM insider_clusters
        WHERE DATE(window_end) >= DATE('now', '-180 days')"""):
        cl[r["ticker"]] = (r["n_insiders"], r["total_usd_m"] or 0)
    f4 = {}
    for r in conn.execute("""SELECT ticker, SUM(shares*price)/1e6 usd_m
        FROM form4_transactions
        WHERE code='P' AND acquired=1
          AND trans_date >= date('now','-180 days')
        GROUP BY ticker"""):
        f4[r["ticker"]] = r["usd_m"] or 0
    er = {r[0]: r[1] for r in conn.execute(
        "SELECT ticker, est_return_pct FROM expected_return")
        if conn.execute("SELECT 1 FROM sqlite_master WHERE name='expected_return'").fetchone()}
    tm = {}
    for r in conn.execute("""SELECT ticker, name, exchange, sector, mcap_m, price
        FROM ticker_meta"""):
        tm[r["ticker"]] = dict(r)
    # backfill curated candidates for tickers not in ticker_meta yet
    for r in conn.execute("""SELECT ticker, name, sector, mcap_m, price FROM candidates"""):
        if r["ticker"] not in tm:
            tm[r["ticker"]] = {"ticker": r["ticker"], "name": r["name"], "exchange": None,
                               "sector": r["sector"], "mcap_m": r["mcap_m"], "price": r["price"]}

    universe = set(sm) | set(s_by) | set(act) | set(cl)
    print(f"scoring {len(universe)} tickers")
    n = 0
    for tkr in universe:
        n13f = sm.get(tkr, 0)
        sec_counts = s_by.get(tkr, {})
        s1 = sec_counts.get(1, 0); s2 = sec_counts.get(2, 0)
        s3 = sec_counts.get(3, 0); s4 = sec_counts.get(4, 0)
        n13d, pct = act.get(tkr, (0, 0))
        ins_n, ins_m = cl.get(tkr, (0, 0))
        f4m = f4.get(tkr, 0)
        er_pct = er.get(tkr, 0) or 0
        meta = tm.get(tkr, {})
        mcap = meta.get("mcap_m") or 0

        # scoring
        smart_money       = math.log1p(n13f) * 2
        s3_new_init       = 3.0 * s3
        s4_material_add   = 1.5 * s4
        s1_top_pick       = 2.0 * s1
        activist_pct      = 0.5 * min(pct, 30)
        insider_cluster   = (5 if ins_n >= 1 else 0) + (5 if ins_n >= 3 else 0) + (5 if ins_n >= 5 else 0)
        insider_dollars   = math.log1p(ins_m) * 3 if ins_m > 0 else 0
        form4_buying      = math.log1p(f4m) * 2 if f4m > 0 else 0
        micro_bonus       = (5 if 0 < mcap < 300 else 3 if 0 < mcap < 2000 else 0)
        er_contribution   = er_pct * 0.5

        score = (smart_money + s3_new_init + s4_material_add + s1_top_pick +
                 activist_pct + insider_cluster + insider_dollars + form4_buying +
                 micro_bonus + er_contribution)

        bucket = ("nano" if 0 < mcap < 50 else
                  "micro" if mcap < 300 else
                  "small" if mcap < 2000 else
                  "mid" if mcap < 10000 else
                  "large" if mcap > 0 else "unknown")

        components = (f"sm={smart_money:.1f} s3*={s3_new_init:.1f} s4*={s4_material_add:.1f} "
                      f"s1*={s1_top_pick:.1f} act={activist_pct:.1f} clust={insider_cluster:.0f} "
                      f"clust$={insider_dollars:.1f} f4={form4_buying:.1f} mic={micro_bonus:.0f} er={er_contribution:.1f}")

        conn.execute("""INSERT INTO unified_signal VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (tkr, meta.get("name"), meta.get("exchange"), meta.get("sector"),
             mcap, meta.get("price"), bucket,
             n13f, s1, s2, s3, s4,
             n13d, pct, ins_m, ins_n, f4m,
             er_pct, score, components))
        n += 1
    conn.commit()
    print(f"wrote {n} unified_signal rows")

    # Summary by bucket
    print("\n=== TOP 25 BY SCORE (ex mega/ETF) ===")
    MEGA = {'AMZN','MSFT','NVDA','META','GOOGL','GOOG','AAPL','TSLA','BRK-A','BRK-B',
            'JPM','BAC','WFC','UNH','JNJ','V','MA','XOM','CVX','HD','PG','KO','PEP',
            'COST','AVGO','ORCL','WMT','DIS','NFLX','CRM','ABBV','TMO','ABT','MRK',
            'LLY','NKE','MCD','CSCO','INTC','AMD','ADBE','QCOM','TXN','HON',
            'SPY','QQQ','VOO','IWM','IEF','GLD','SLV','TLT','EFA','EEM','BIL','IVV',
            'HYG','XBI'}
    print(f"{'tkr':<8} {'score':>6} {'mcap$M':>9} {'buc':<5} {'13F':>3} {'S3':>2} {'S4':>2} {'S1':>2} {'13D':>2} {'pct%':>4} {'clu$M':>5}")
    rank = 0
    for r in conn.execute("""SELECT ticker, score, mcap_m, mcap_bucket, smart_money_n,
        s3_new, s4_add, s1_top, activist_filings, activist_max_pct,
        insider_cluster_dollars_m FROM unified_signal ORDER BY score DESC"""):
        if r[0] in MEGA: continue
        rank += 1; mc = r[2] or 0
        print(f"  {r[0]:<6} {r[1]:>6.1f} ${mc:>7,.0f} {r[3]:<5} {r[4]:>3} {r[5]:>2} {r[6]:>2} {r[7]:>2} {r[8]:>2} {r[9] or 0:>4.1f} ${r[10] or 0:>3.0f}")
        if rank >= 25: break

    print("\n=== MICRO/SMALL CAP LEADERBOARD ===")
    rank = 0
    for r in conn.execute("""SELECT ticker, score, mcap_m, mcap_bucket, smart_money_n,
        s3_new, s4_add, s1_top, activist_max_pct, insider_cluster_dollars_m, sector, name
        FROM unified_signal WHERE mcap_bucket IN ('nano','micro','small')
        ORDER BY score DESC LIMIT 25"""):
        if r[0] in MEGA: continue
        rank += 1; mc = r[2] or 0
        print(f"  {r[0]:<6} {r[1]:>6.1f} ${mc:>7,.0f} {r[3]:<5} {r[4]:>3} S3={r[5]} S4={r[6]} S1={r[7]} act={r[8] or 0:.1f}% clu=${r[9] or 0:.1f}M  {(r[10] or '')[:25]:<25} {(r[11] or '')[:30]}")

if __name__ == "__main__":
    run()
