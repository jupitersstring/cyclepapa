"""Broker Swap Radar — outsized single-desk share-count jumps.

Reads broker_13f (current vs prior quarter per broker), diffs share counts at
the ticker level, and flags names where ONE desk absorbed a block that is
large relative to shares outstanding. That pattern is the classic footprint
of a total-return-swap hedge for a stake someone is NOT yet disclosing
(cash-settled swaps stay off the client's 13F/13D until conversion).

Distinguishing signal from noise:
  - idio_pct: this broker's delta as a share of the summed |deltas| across
    all tracked desks. Index rebalances and ETF baskets move EVERY desk;
    a swap hedge concentrates in ONE. >60% = idiosyncratic.
  - mcap window: mega-caps are dominated by index flow; sub-$100M books
    are custody noise. Radar window: $150M – $75B.
  - context joins: recent 13D/G filers and which of OUR activist-style
    funds already hold the name (an Elliott swap often precedes/parallels
    a small disclosed toe-hold, or follows their known campaign style).

Output: broker_swap_radar table + console top-30.
"""
import os, sqlite3

DB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "cyclepapa.db")

MIN_PCT_OUT = 0.35        # delta must be >= 0.35% of shares outstanding
MIN_DELTA_M = 15.0        # ...and worth >= $15M
MCAP_LO, MCAP_HI = 150, 75000

def run():
    conn = sqlite3.connect(DB, timeout=60)
    conn.execute("PRAGMA busy_timeout=60000")
    conn.row_factory = sqlite3.Row
    conn.executescript("""
    DROP TABLE IF EXISTS broker_swap_radar;
    CREATE TABLE broker_swap_radar (
      ticker TEXT, name TEXT, broker TEXT,
      delta_sh_m REAL,          -- share-count change, millions
      pct_out REAL,             -- delta as % of shares outstanding
      delta_m REAL,             -- delta at current price, $M
      cur_m REAL,               -- broker's current position, $M
      idio_pct REAL,            -- broker delta / sum |all broker deltas|
      mcap_m REAL, score REAL,
      recent_13d TEXT,          -- 13D/G filers on this name, last 12 months
      activist_holders TEXT,    -- our activist-style funds currently holding
      PRIMARY KEY (ticker, broker));
    """)

    # ticker-level share sums per broker per quarter-rank (cusip_map collapses
    # share-class/CUSIP churn the same way the fund QoQ diff does)
    deltas = {}
    for r in conn.execute("""
        WITH ok AS (
             -- partial-prior guard: a restated/subset prior accession (JPM's
             -- 361-row "Q1" vs 6,818-row Q2) would fabricate thousands of
             -- adds. Require the prior book within [40%, 250%] of current.
             SELECT c.broker FROM
               (SELECT broker, SUM(value_k) v FROM broker_13f WHERE qrank=0 GROUP BY broker) c
               JOIN (SELECT broker, SUM(value_k) v FROM broker_13f WHERE qrank=1 GROUP BY broker) p
               ON p.broker = c.broker
             WHERE c.v > 0 AND p.v BETWEEN c.v*0.4 AND c.v*2.5),
        b AS (SELECT b.broker, COALESCE(cm.ticker, b.ticker) tk, b.qrank,
                          SUM(b.shares) sh
                   FROM broker_13f b LEFT JOIN cusip_map cm ON cm.cusip = b.cusip
                   WHERE b.sh_type IN ('SH','') AND COALESCE(cm.ticker, b.ticker) IS NOT NULL
                     AND b.broker IN (SELECT broker FROM ok)
                   GROUP BY b.broker, tk, b.qrank)
        SELECT cur.broker, cur.tk,
               cur.sh - COALESCE(pri.sh, 0) AS d_sh
        FROM (SELECT * FROM b WHERE qrank = 0) cur
        LEFT JOIN (SELECT * FROM b WHERE qrank = 1) pri
             ON pri.broker = cur.broker AND pri.tk = cur.tk"""):
        deltas.setdefault(r["tk"], {})[r["broker"]] = r["d_sh"]
    skipped = [r[0] for r in conn.execute("""
        SELECT broker FROM broker_13f_state WHERE broker NOT IN (
          SELECT c.broker FROM
            (SELECT broker, SUM(value_k) v FROM broker_13f WHERE qrank=0 GROUP BY broker) c
            JOIN (SELECT broker, SUM(value_k) v FROM broker_13f WHERE qrank=1 GROUP BY broker) p
            ON p.broker = c.broker
          WHERE c.v > 0 AND p.v BETWEEN c.v*0.4 AND c.v*2.5)""")]
    if skipped:
        print(f"NOTE: brokers excluded for partial/incomparable prior: {skipped}")

    yf = {r["ticker"]: r for r in conn.execute(
        "SELECT ticker, price, mcap_m, shares_out_m FROM ticker_yf WHERE price > 0")}
    sig = {r["ticker"]: r for r in conn.execute(
        "SELECT ticker, name, score, sec_type FROM unified_signal")}
    d13 = {}
    for r in conn.execute("""SELECT subject_ticker t, GROUP_CONCAT(DISTINCT holder) h
            FROM holder_13d WHERE filed >= date('now','-12 months') AND subject_ticker IS NOT NULL
            GROUP BY subject_ticker"""):
        d13[r["t"]] = r["h"]
    actv = {}
    for r in conn.execute("""SELECT h.ticker t, GROUP_CONCAT(DISTINCT COALESCE(fc.canon, h.fund)) f
            FROM fund_13f_holdings h
            JOIN fund_style fs ON fs.fund = h.fund AND fs.macro_style = 'Activists / Special Situations'
            LEFT JOIN fund_canon fc ON fc.fund = h.fund
            WHERE h.ticker IS NOT NULL AND h.value_k > 10000
            GROUP BY h.ticker"""):
        actv[r["t"]] = r["f"]

    n = 0
    for tk, per_broker in deltas.items():
        y = yf.get(tk)
        s = sig.get(tk)
        if not y or not y["shares_out_m"] or not y["price"]:
            continue
        if s and s["sec_type"] not in (None, "common"):
            continue
        if not (MCAP_LO <= (y["mcap_m"] or 0) <= MCAP_HI):
            continue
        tot_abs = sum(abs(v) for v in per_broker.values()) or 1
        for broker, d_sh in per_broker.items():
            if d_sh <= 0:
                continue
            pct_out = d_sh / (y["shares_out_m"] * 1e6) * 100
            delta_m = d_sh * y["price"] / 1e6
            if pct_out < MIN_PCT_OUT or delta_m < MIN_DELTA_M:
                continue
            cur_m = conn.execute("""SELECT SUM(b.value_k)/1e3 FROM broker_13f b
                LEFT JOIN cusip_map cm ON cm.cusip = b.cusip
                WHERE b.broker=? AND b.qrank=0
                  AND COALESCE(cm.ticker, b.ticker)=?""", (broker, tk)).fetchone()[0]
            conn.execute("INSERT OR REPLACE INTO broker_swap_radar VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (tk, (s["name"] if s else None), broker,
                 round(d_sh / 1e6, 2), round(pct_out, 2), round(delta_m, 1),
                 round(cur_m or 0, 1), round(abs(d_sh) / tot_abs * 100, 0),
                 round(y["mcap_m"] or 0, 0), (s["score"] if s else None),
                 d13.get(tk), actv.get(tk)))
            n += 1
    conn.commit()

    print(f"broker_swap_radar: {n} flags\n")
    print(f"{'tkr':6s} {'broker':20s} {'Δsh(M)':>7s} {'%out':>5s} {'Δ$M':>7s} {'idio':>4s}  13D/activist context")
    for r in conn.execute("""SELECT * FROM broker_swap_radar
            ORDER BY pct_out * (idio_pct/100.0) DESC LIMIT 30"""):
        ctx = (r["recent_13d"] or "")[:40]
        if r["activist_holders"]:
            ctx += (" | " if ctx else "") + r["activist_holders"][:40]
        print(f"{r['ticker']:6s} {r['broker'][:20]:20s} {r['delta_sh_m']:7.1f} "
              f"{r['pct_out']:5.2f} {r['delta_m']:7.0f} {r['idio_pct']:4.0f}  {ctx}")
    conn.close()

if __name__ == "__main__":
    run()
