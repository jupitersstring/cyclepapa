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
      form4_buy_usd_m REAL, form4_sell_usd_m REAL,
      form4_buy_30d_m REAL, form4_sell_30d_m REAL,
      max_pct_book REAL, n_funds_5pct_book INTEGER,
      global_score REAL,        -- score using only signals that work cross-listing
      is_us INTEGER,            -- 1 if US-registered (no dot suffix), 0 otherwise
      cat8k_ma INTEGER, cat8k_dir INTEGER, cat8k_ctrl INTEGER,
      cat8k_pipe INTEGER, cat8k_bnk INTEGER, cat8k_n INTEGER,
      ev_ebitda REAL, pb_ratio REAL,
      revealed_pref REAL,       -- active accumulation: 2*s3 + s4 + 0.5*s1
      expected_return_pct REAL,
      entry_bucket TEXT, vs_entry_pct REAL, anchor_px REAL, anchor_source TEXT,
      score REAL,
      components TEXT
    );
    CREATE INDEX idx_us_score ON unified_signal(score DESC);
    CREATE INDEX idx_us_bucket ON unified_signal(mcap_bucket);
    CREATE INDEX idx_us_pb ON unified_signal(max_pct_book DESC);
    CREATE INDEX idx_us_entry ON unified_signal(entry_bucket);
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
    # Form 4 buys (P-code, acquired) — time-decayed weighting:
    #   ≤30 days   : weight 1.0
    #   31–60 days : weight 0.6
    #   61–120 days: weight 0.3
    #   121–180    : weight 0.1
    # Recent buying is much more informative than 6-month-old buying.
    f4 = {}                   # weighted dollar exposure
    f4_raw = {}               # unweighted 180d sum (for display)
    f4_30 = {}                # ≤30d dollar exposure (very-recent signal)
    for r in conn.execute("""
        SELECT ticker, SUM(shares*price)/1e6 AS usd_m,
               julianday('now') - julianday(trans_date) AS days_old
        FROM form4_transactions
        WHERE code='P' AND acquired=1 AND price IS NOT NULL
          AND trans_date >= date('now','-180 days')
        GROUP BY ticker, days_old"""):
        tk = r["ticker"]; d = r["days_old"] or 0; u = r["usd_m"] or 0
        if   d <= 30:  w = 1.0
        elif d <= 60:  w = 0.6
        elif d <= 120: w = 0.3
        else:          w = 0.1
        f4[tk] = f4.get(tk, 0) + u * w
        f4_raw[tk] = f4_raw.get(tk, 0) + u
        if d <= 30:
            f4_30[tk] = f4_30.get(tk, 0) + u

    f4_sell = {}              # weighted dollar exposure
    f4_sell_raw = {}
    f4_sell_30 = {}
    for r in conn.execute("""
        SELECT ticker, SUM(shares*price)/1e6 AS usd_m,
               julianday('now') - julianday(trans_date) AS days_old
        FROM form4_transactions
        WHERE code='S' AND price IS NOT NULL
          AND trans_date >= date('now','-180 days')
        GROUP BY ticker, days_old"""):
        tk = r["ticker"]; d = r["days_old"] or 0; u = r["usd_m"] or 0
        if   d <= 30:  w = 1.0
        elif d <= 60:  w = 0.6
        elif d <= 120: w = 0.3
        else:          w = 0.1
        f4_sell[tk] = f4_sell.get(tk, 0) + u * w
        f4_sell_raw[tk] = f4_sell_raw.get(tk, 0) + u
        if d <= 30:
            f4_sell_30[tk] = f4_sell_30.get(tk, 0) + u
    # entry-intact / in-the-money — current price vs smart-money entry anchor
    entry = {}
    for r in conn.execute("""SELECT ticker, bucket, vs_entry_pct, anchor_px, anchor_source
        FROM ticker_entry_intact"""):
        entry[r["ticker"]] = (r["bucket"], r["vs_entry_pct"], r["anchor_px"], r["anchor_source"])

    # Valuation ratios — EV/EBITDA and P/B (from enrich_valuation.py)
    valn = {}
    try:
        for r in conn.execute("SELECT ticker, ev_ebitda, pb_ratio FROM ticker_valuation"):
            valn[r["ticker"]] = (r["ev_ebitda"], r["pb_ratio"])
    except Exception:
        pass  # table may not exist yet on first run

    # 8-K catalysts — count of each material item type in the last 180d
    cat8k = {}     # ticker -> dict of has_ma/has_director/has_control/has_pipe/has_bankruptcy
    for r in conn.execute("""SELECT ticker,
            MAX(has_ma) AS ma, MAX(has_director) AS dir, MAX(has_control) AS ctrl,
            MAX(has_pipe) AS pipe, MAX(has_bankruptcy) AS bnk,
            SUM(has_ma + has_director + has_control + has_pipe + has_bankruptcy) AS event_count,
            MAX(filed) AS latest
        FROM catalysts_8k
        WHERE filed >= date('now','-180 days')
        GROUP BY ticker"""):
        cat8k[r["ticker"]] = {
            "ma":   r["ma"] or 0,
            "dir":  r["dir"] or 0,
            "ctrl": r["ctrl"] or 0,
            "pipe": r["pipe"] or 0,
            "bnk":  r["bnk"] or 0,
            "n":    r["event_count"] or 0,
            "latest": r["latest"],
        }
    # pct_book — highest %-of-fund-book any single fund has assigned to this ticker
    pct_book_max = {}
    pct_book_n5 = {}
    for r in conn.execute("""SELECT ticker, MAX(pct_book) AS m,
        SUM(CASE WHEN pct_book >= 5 THEN 1 ELSE 0 END) AS n5
        FROM fund_13f_holdings
        WHERE ticker IS NOT NULL AND pct_book IS NOT NULL
          AND pct_book <= 100
        GROUP BY ticker"""):
        pct_book_max[r["ticker"]] = r["m"] or 0
        pct_book_n5[r["ticker"]] = r["n5"] or 0
    er = {r[0]: r[1] for r in conn.execute(
        "SELECT ticker, weighted_excess_12m FROM expected_return")}
    tm = {}
    for r in conn.execute("""SELECT ticker, name, exchange, sector, mcap_m, price
        FROM ticker_meta"""):
        tm[r["ticker"]] = dict(r)
    # backfill curated candidates for tickers not in ticker_meta yet
    for r in conn.execute("""SELECT ticker, name, sector, mcap_m, price FROM candidates"""):
        if r["ticker"] not in tm:
            tm[r["ticker"]] = {"ticker": r["ticker"], "name": r["name"], "exchange": None,
                               "sector": r["sector"], "mcap_m": r["mcap_m"], "price": r["price"]}

    universe = set(sm) | set(s_by) | set(act) | set(cl) | set(pct_book_max)
    print(f"scoring {len(universe)} tickers")
    n = 0
    for tkr in universe:
        n13f = sm.get(tkr, 0)
        sec_counts = s_by.get(tkr, {})
        s1 = sec_counts.get(1, 0); s2 = sec_counts.get(2, 0)
        s3 = sec_counts.get(3, 0); s4 = sec_counts.get(4, 0)
        n13d, pct = act.get(tkr, (0, 0))
        ins_n, ins_m = cl.get(tkr, (0, 0))
        f4m = f4.get(tkr, 0)               # time-decayed (recent buys weighted more)
        f4m_raw = f4_raw.get(tkr, 0)       # raw 180d sum for display
        f4m_30 = f4_30.get(tkr, 0)         # ≤30d buys
        f4sell_m = f4_sell.get(tkr, 0)     # time-decayed sells
        f4sell_raw = f4_sell_raw.get(tkr, 0)
        f4sell_30 = f4_sell_30.get(tkr, 0)
        max_pb = pct_book_max.get(tkr, 0)
        n5_pb = pct_book_n5.get(tkr, 0)
        er_pct = er.get(tkr, 0) or 0
        meta = tm.get(tkr, {})
        mcap = meta.get("mcap_m") or 0
        e = entry.get(tkr, (None, None, None, None))
        entry_bucket, vs_entry_pct, anchor_px, anchor_src = e
        c8 = cat8k.get(tkr, {})
        c8_ma   = c8.get("ma",   0)
        c8_dir  = c8.get("dir",  0)
        c8_ctrl = c8.get("ctrl", 0)
        c8_pipe = c8.get("pipe", 0)
        c8_bnk  = c8.get("bnk",  0)
        ev_ebitda, pb_ratio = valn.get(tkr, (None, None))
        # Revealed preference — what funds are ACTIVELY doing (not just holding):
        # new major positions weigh 2×, material adds 1×, top-conviction holds 0.5×
        revealed_pref = 2.0 * s3 + 1.0 * s4 + 0.5 * s1

        # scoring
        smart_money       = math.log1p(n13f) * 2
        s3_new_init       = 3.0 * s3
        s4_material_add   = 1.5 * s4
        s1_top_pick       = 2.0 * s1
        activist_pct      = 0.5 * min(pct, 30)
        # max_pct_book of 10%+ = HIGH conviction; 20%+ = HYPER
        max_pb_term       = 0.6 * min(max_pb, 25)
        cluster_pct_book  = 1.5 * n5_pb
        insider_cluster   = (5 if ins_n >= 1 else 0) + (5 if ins_n >= 3 else 0) + (5 if ins_n >= 5 else 0)
        insider_dollars   = math.log1p(ins_m) * 3 if ins_m > 0 else 0
        # form4_buying uses time-decayed sum: recent buys weight more
        form4_buying      = math.log1p(f4m) * 2 if f4m > 0 else 0
        # extra kicker for very-recent (≤30d) buying — heaviest signal
        form4_recent_bonus = math.log1p(f4m_30) * 2 if f4m_30 > 0 else 0
        form4_selling     = -math.log1p(f4sell_m) * 1.5 if f4sell_m > 0 else 0
        # very-recent sells hit harder
        form4_recent_sell_penalty = -math.log1p(f4sell_30) * 1.5 if f4sell_30 > 0 else 0
        micro_bonus       = (5 if 0 < mcap < 300 else 3 if 0 < mcap < 2000 else 0)
        er_contribution   = er_pct * 0.5
        # in-the-money / entry-intact — REVISED per adversarial review.
        # Reviewers found pattern: drawdowns >50% almost always signal
        # (a) stale anchor from pre-event cohort, (b) busted thesis with
        # stuck holders, or (c) parse errors. Sweet spot is -30 to -5%.
        entry_bonus       = 0
        if entry_bucket == "BELOW_ENTRY" and vs_entry_pct:
            x = abs(vs_entry_pct)
            if 5 <= x <= 30:
                entry_bonus = x / 6.0      # peaks at +5 around -30%
            elif 30 < x <= 50:
                entry_bonus = 5.0 - (x - 30) * 0.25  # tapers from +5 → 0
            else:  # x > 50  — busted thesis territory
                entry_bonus = -3.0
        elif entry_bucket == "NEAR_ENTRY":
            entry_bonus = 1.5
        elif entry_bucket == "WELL_ABOVE":
            entry_bonus = -3.0

        # NEW: sponsor-stake / sole-concentrator detection.
        # If single fund concentration is >50% AND no cluster of other funds
        # >=5%, treat as a legacy / sponsor stake not a smart-money conviction
        # cluster. Cap the pct_book contribution.
        if max_pb > 50 and n5_pb < 3:
            max_pb_term = 0.3 * min(max_pb, 25)   # halve the bonus

        # NEW: 8-K catalyst bonuses/penalties
        #   M&A entry (1.01) or completion (2.01)  = +5  (takeover catalyst)
        #   Control change (5.01)                  = +4  (often pre-takeover)
        #   Director change (5.02)                 = +1  (could be activist)
        #   PIPE / dilution (3.02)                 = -3  (counter-signal)
        #   Bankruptcy (1.03)                      = -10 (counter-signal)
        catalyst_8k = (5 * c8_ma + 4 * c8_ctrl + 1 * c8_dir
                       - 3 * c8_pipe - 10 * c8_bnk)

        score = (smart_money + s3_new_init + s4_material_add + s1_top_pick +
                 activist_pct + max_pb_term + cluster_pct_book +
                 insider_cluster + insider_dollars +
                 form4_buying + form4_recent_bonus +
                 form4_selling + form4_recent_sell_penalty +
                 micro_bonus + er_contribution + entry_bonus +
                 catalyst_8k)

        # GLOBAL-FAIR score: drops the US-only terms (Form 4, insider clusters)
        # so foreign-exchange tickers (.L .T .TO .HK .AX etc.) — which can never
        # have those signals because SEC doesn't cover them — rank fairly.
        # Used for the Global Picks sheet.
        global_score = (smart_money + s3_new_init + s4_material_add + s1_top_pick +
                        activist_pct + max_pb_term + cluster_pct_book +
                        micro_bonus + er_contribution + entry_bonus)
        is_us = 0 if "." in tkr else 1

        if not mcap or mcap <= 0:
            bucket = "unknown"
        elif mcap < 50:    bucket = "nano"
        elif mcap < 300:   bucket = "micro"
        elif mcap < 2000:  bucket = "small"
        elif mcap < 10000: bucket = "mid"
        else:              bucket = "large"

        components = (f"sm={smart_money:.1f} s3*={s3_new_init:.1f} s4*={s4_material_add:.1f} "
                      f"s1*={s1_top_pick:.1f} act={activist_pct:.1f} pb_max={max_pb_term:.1f} "
                      f"pb_n5={cluster_pct_book:.1f} clust={insider_cluster:.0f} "
                      f"clust$={insider_dollars:.1f} f4buy={form4_buying:.1f} f4rec+={form4_recent_bonus:.1f} "
                      f"f4sell={form4_selling:.1f} f4recsell={form4_recent_sell_penalty:.1f} "
                      f"mic={micro_bonus:.0f} er={er_contribution:.1f} entry={entry_bonus:.1f} cat8k={catalyst_8k:.0f}")

        conn.execute("""INSERT INTO unified_signal VALUES
            (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (tkr, meta.get("name"), meta.get("exchange"), meta.get("sector"),
             mcap, meta.get("price"), bucket,
             n13f, s1, s2, s3, s4,
             n13d, pct, ins_m, ins_n,
             f4m_raw, f4sell_raw,
             f4m_30, f4sell_30,
             max_pb, n5_pb,
             global_score, is_us,
             c8_ma, c8_dir, c8_ctrl, c8_pipe, c8_bnk, c8.get("n", 0),
             ev_ebitda, pb_ratio, revealed_pref,
             er_pct,
             entry_bucket, vs_entry_pct, anchor_px, anchor_src,
             score, components))
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
