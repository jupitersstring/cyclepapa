"""Expected-return calculator — base-rate-weighted ER per candidate.

For each Tier-1+2 name, take its factor_tags, look up the 12mo excess-vs-SPY
base rate per bucket, weight equally across tags, and emit an ER score.
Also output a re-ranking that respects empirical base rates instead of my
subjective confidence weights.
"""
import os, sqlite3

DB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "cyclepapa.db")

# tags that aren't backtested but have a proxied or assumed prior
PROXY = {
    "activist_anchor": 0.0,     # Fairfax-style anchor isn't pure activist; treat neutral
    "brand_recovery": 0.0,
    "earnings_reset": 0.05,     # mild positive — guidance has a floor effect
    "services": 0.0,
    "asset_light": 0.0,
    "spin_arb": 0.10,           # spin arb has decent academic returns
    "defense": 0.0,
    "small_cap": 0.0,
    "deep_value": 0.0,
    "post_acquisition": 0.0,
    "industrial": 0.0,
    "consumer_discretionary": 0.0,
    "brand": 0.0,
    "holdco": 0.0,
    "nav_discount": 0.05,
    "royalty": 0.05,
    "income": 0.0,
    "defense_recovery": 0.0,
    "take_private_arb": 0.0,
    "net_net": 0.20,            # Graham net-nets have well-documented +20%
}

def run():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    base = {r["factor"]: r["avg_excess_12m"] for r in conn.execute("SELECT factor, avg_excess_12m FROM base_rates")}

    conn.execute("""CREATE TABLE IF NOT EXISTS expected_return (
      ticker TEXT PRIMARY KEY,
      tags_n INTEGER, weighted_excess_12m REAL, best_tag TEXT, best_tag_excess REAL,
      worst_tag TEXT, worst_tag_excess REAL, cluster_live INTEGER, asof TEXT NOT NULL)""")
    conn.execute("DELETE FROM expected_return")

    rows = list(conn.execute("""SELECT c.ticker, c.factor_tags, c.tier,
                                       (SELECT 1 FROM insider_clusters i WHERE i.ticker=c.ticker) AS cluster_live
                                FROM candidates c WHERE c.tier LIKE '1%' OR c.tier LIKE '2%'
                                ORDER BY c.ticker"""))
    out = []
    for r in rows:
        tags = [t.strip() for t in (r["factor_tags"] or "").split(",") if t.strip()]
        if not tags:
            continue
        scored = []
        for t in tags:
            if t in base: scored.append((t, base[t]))
            elif t in PROXY: scored.append((t, PROXY[t]))
            else: scored.append((t, 0.0))
        if not scored:
            continue
        avg = sum(v for _, v in scored) / len(scored)
        best = max(scored, key=lambda x: x[1])
        worst = min(scored, key=lambda x: x[1])
        cluster_bonus = 0.30 if r["cluster_live"] else 0.0  # live cluster = +30pp prior
        weighted = avg + cluster_bonus
        out.append((r["ticker"], len(tags), weighted, best[0], best[1], worst[0], worst[1],
                    r["cluster_live"] or 0))
        conn.execute("""INSERT INTO expected_return VALUES (?,?,?,?,?,?,?,?,date('now'))""",
                     (r["ticker"], len(tags), round(weighted, 3), best[0], round(best[1], 3),
                      worst[0], round(worst[1], 3), r["cluster_live"] or 0))
    conn.commit()

    out.sort(key=lambda x: -x[2])
    print("Base-rate-weighted ER (12mo excess vs SPY), sorted desc:")
    print(f"{'tkr':<8} {'tags':<5} {'ER%':<8} {'best_tag':<22} {'best%':<8} {'worst_tag':<22} {'worst%':<8} {'cluster?'}")
    for r in out:
        print(f"  {r[0]:<8} {r[1]:<5} {r[2]*100:+5.0f}%   {r[3]:<22} {r[4]*100:+5.0f}%   {r[5]:<22} {r[6]*100:+5.0f}%   {'YES' if r[7] else ''}")

    # bucket the new ranking
    print("\nRECOMMENDED TIER STRUCTURE (driven by ER):")
    a = [r for r in out if r[2] >= 0.30]
    b = [r for r in out if 0.0 <= r[2] < 0.30]
    c = [r for r in out if r[2] < 0.0]
    print(f"\nTIER 1 (ER ≥ +30%): {len(a)}")
    for r in a: print(f"  {r[0]} ({r[2]*100:+.0f}% via {r[3]})")
    print(f"\nTIER 2 (0–30%): {len(b)}")
    for r in b: print(f"  {r[0]} ({r[2]*100:+.0f}% via {r[3]})")
    print(f"\nTIER 3 (NEGATIVE — empirically poor without a specific override): {len(c)}")
    for r in c: print(f"  {r[0]} ({r[2]*100:+.0f}% — driven by {r[5]})")

if __name__ == "__main__":
    run()
