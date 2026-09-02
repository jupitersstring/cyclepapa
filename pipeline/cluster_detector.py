"""Insider-cluster detector — applies the +109% backtest bucket criteria.

A "cluster" = 3+ distinct insiders OR a single C-suite buy >$1M, OR aggregate
>$1.5M, in code=P (open-market purchase), within a 60-day window.

Surfaces names where the historically strongest signal is currently live.
"""
import os, sqlite3
from datetime import datetime, timedelta

DB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "cyclepapa.db")

WINDOW_DAYS = 60
MIN_INSIDERS = 3
MIN_SINGLE_CSUITE_M = 1.0
MIN_AGGREGATE_M = 1.5

def run():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    conn.execute("""CREATE TABLE IF NOT EXISTS insider_clusters (
      ticker TEXT PRIMARY KEY,
      window_start TEXT, window_end TEXT,
      n_insiders INTEGER, total_usd_m REAL,
      avg_price REAL, top_buyer TEXT, top_buyer_usd_m REAL,
      trigger TEXT,                -- 'CLUSTER' | 'BIG_CSUITE' | 'AGGREGATE'
      asof TEXT NOT NULL
    )""")
    conn.execute("DELETE FROM insider_clusters")

    # Same sanity guard as unified_score: a trade worth more than the company's
    # market cap, or priced wildly off market (>5x / <0.10x), is a parse artifact
    # (ADS-ratio mismatch, local-currency price, corrupted field) — never a real
    # open-market buy. SVRE's "$22.4B cluster" on a $2.7M nano came from this.
    rows = list(conn.execute("""SELECT ticker, owner, role, trans_date, shares, price
                                FROM form4_transactions
                                WHERE code='P' AND acquired=1 AND shares > 0 AND price > 0
                                  AND NOT EXISTS (SELECT 1 FROM ticker_yf y
                                      WHERE y.ticker = form4_transactions.ticker
                                        AND ((y.mcap_m > 0 AND form4_transactions.shares
                                              * form4_transactions.price/1e6 > y.mcap_m)
                                          OR (y.price > 0
                                              AND (form4_transactions.price > y.price*5
                                                OR form4_transactions.price < y.price*0.10))))
                                  AND NOT (form4_transactions.shares*form4_transactions.price/1e6 > 250
                                           AND NOT EXISTS (SELECT 1 FROM ticker_yf y2
                                               WHERE y2.ticker = form4_transactions.ticker))
                                ORDER BY ticker, trans_date"""))
    # group by ticker
    by_t = {}
    for r in rows:
        by_t.setdefault(r["ticker"], []).append(dict(r))

    found = []
    today = datetime.today()
    for tkr, txns in by_t.items():
        # find the densest 60-day window ending in the last 180 days
        txns.sort(key=lambda x: x["trans_date"])
        best = None
        for i, anchor in enumerate(txns):
            ad = (anchor["trans_date"] or "").split("T")[0].split(" ")[0][:10]
            try:
                anchor_dt = datetime.strptime(ad, "%Y-%m-%d")
            except (TypeError, ValueError):
                continue
            if (today - anchor_dt).days > 180:
                continue
            window_start = anchor_dt - timedelta(days=WINDOW_DAYS)
            def _pdate(s):
                if not s: return None
                s = s.split("T")[0].split(" ")[0][:10]
                try: return datetime.strptime(s, "%Y-%m-%d")
                except ValueError: return None
            wnd = [t for t in txns if _pdate(t["trans_date"]) and
                   window_start <= _pdate(t["trans_date"]) <= anchor_dt]
            if not wnd:
                continue
            insiders = set(t["owner"] for t in wnd)
            total = sum(t["shares"] * t["price"] / 1e6 for t in wnd)
            buyers_by_size = sorted(
                [(o, sum(t["shares"]*t["price"]/1e6 for t in wnd if t["owner"]==o)) for o in insiders],
                key=lambda x: -x[1])
            top_buyer, top_usd = buyers_by_size[0]
            top_role = next((t["role"] or "" for t in wnd if t["owner"] == top_buyer), "")

            trig = None
            if len(insiders) >= MIN_INSIDERS:
                trig = "CLUSTER"
            elif total >= MIN_AGGREGATE_M:
                trig = "AGGREGATE"
            elif top_usd >= MIN_SINGLE_CSUITE_M and any(k in (top_role or "").lower()
                                                        for k in ("ceo","cfo","coo","chief","president")):
                trig = "BIG_CSUITE"
            if not trig:
                continue
            score = (len(insiders) * 2) + total
            if not best or score > best["score"]:
                best = {
                    "ticker": tkr,
                    "window_start": (anchor_dt - timedelta(days=WINDOW_DAYS)).strftime("%Y-%m-%d"),
                    "window_end": anchor["trans_date"],
                    "n_insiders": len(insiders),
                    "total_usd_m": round(total, 3),
                    "avg_price": round(sum(t["price"] for t in wnd) / len(wnd), 2),
                    "top_buyer": top_buyer,
                    "top_buyer_usd_m": round(top_usd, 3),
                    "trigger": trig,
                    "score": score,
                }
        if best:
            best.pop("score")
            best["asof"] = today.strftime("%Y-%m-%d")
            conn.execute("""INSERT INTO insider_clusters
              (ticker,window_start,window_end,n_insiders,total_usd_m,avg_price,
               top_buyer,top_buyer_usd_m,trigger,asof)
              VALUES (:ticker,:window_start,:window_end,:n_insiders,:total_usd_m,:avg_price,
                      :top_buyer,:top_buyer_usd_m,:trigger,:asof)""", best)
            found.append(best)
    conn.commit()

    found.sort(key=lambda x: -(x["n_insiders"]*2 + x["total_usd_m"]))
    print(f"Detected {len(found)} live insider clusters (window ≤60d, ≤180d ago):\n")
    print(f"{'tkr':<6} {'trigger':<11} {'window_end':<12} {'#insiders':<10} {'total $M':<10} {'avg px':<8} {'top buyer'}")
    for c in found:
        print(f"  {c['ticker']:<6} {c['trigger']:<11} {c['window_end']:<12} {c['n_insiders']:<10} "
              f"${c['total_usd_m']:<8.2f} ${c['avg_price']:<6} {(c['top_buyer'] or '')[:24]} (${c['top_buyer_usd_m']:.2f}M)")

if __name__ == "__main__":
    run()
