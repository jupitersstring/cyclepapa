"""Populate Tier 1 metadata: factor_tags + kill_criteria.

Each tag corresponds to a backtest bucket so we can compute basket-weighted
expected excess return from base rates.
"""
import os, sqlite3
DB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "cyclepapa.db")

# (ticker, factor_tags, kill_criteria)
META = [
    ("UA",   "founder_buy,activist_anchor,brand_recovery",
     "Fairfax sells; UAA-class falls below $4 on no insider response; FY27 EBITDA guide cut > 20%"),
    ("NSP",  "founder_buy,earnings_reset,services",
     "Sarvadi sells; Q3 2026 EPS < $0.50; dividend cut signals B/S stress"),
    ("SEER", "bid_rejected,net_net,activist_13d",
     "Cash balance reported < $200M (kills bid math); Radoff loses proxy + no competing bid by Aug 2026"),
    ("MNRO", "sale_process,small_cap,deep_value",
     "Sale process terminated with no deal by Q4 2026; dividend cut; same-store sales -5%+"),
    ("RPAY", "bid_rejected,activist_13d,take_private_arb",
     "Forager withdraws below $4 or AGM result entrenches board; FY26 rev guide cut"),
    ("INMD", "founder_buy,smart_money_uw,asset_light",
     "Mizrahy sells; Steel sells; Q2 2026 rev < $80M; cash balance breached"),
    ("KBR",  "insider_cluster,spin_arb,defense",
     "MTS spin delayed past June 2027; > 2 director sells; Engine exits; classaction outcome adverse"),
    ("ROCK", "insider_cluster,post_acquisition,industrial",
     "Bosway or Metcalf sells; FY26 EPS guide < $3.00; OmniMax write-down"),
    ("SONO", "activist_form4_cluster,brand,consumer_discretionary",
     "Coliseum sells; Q3 holiday rev miss; product launch delayed"),
    ("HHH",  "sponsor_anchor,nav_discount,holdco",
     "Ackman sells common; HHH stays below $70 12mo post-Vantage; insurance leverage > 4x"),
    ("NRP",  "family_anchor,royalty,income",
     "Distribution cut; family <30%; Sisecam cap-call > $50M H2 2026"),
    ("CDRE", "activist_13d,defense_recovery,small_cap",
     "Wynnefield trims < 15%; FY26 sales > 5% miss; gov order pipeline drops"),
]

# Backtest base rates (computed) → assign to factor tags
# founder_buy +14.3%, insider_cluster +109%, smart_money_uw +17%, activist_13d -25.7%,
# bid_rejected -61.3%, sale_process -45.9%
BASE_RATES = {
    "founder_buy":           {"hit": 0.60, "avg_excess_12m": 0.143, "n": 5},
    "insider_cluster":       {"hit": 1.00, "avg_excess_12m": 1.095, "n": 2},
    "smart_money_uw":        {"hit": 0.50, "avg_excess_12m": 0.170, "n": 2},
    "activist_form4_cluster":{"hit": 0.50, "avg_excess_12m": 0.170, "n": 2},  # proxy
    "activist_13d":          {"hit": 0.14, "avg_excess_12m": -0.257, "n": 7},
    "bid_rejected":          {"hit": 0.00, "avg_excess_12m": -0.613, "n": 1},
    "sale_process":          {"hit": 0.00, "avg_excess_12m": -0.459, "n": 2},
    "sponsor_anchor":        {"hit": 0.50, "avg_excess_12m": 0.170, "n": 0},  # proxied
    "family_anchor":         {"hit": 0.50, "avg_excess_12m": 0.170, "n": 0},  # proxied
}

def run():
    conn = sqlite3.connect(DB)
    conn.execute("""CREATE TABLE IF NOT EXISTS base_rates (
      factor TEXT PRIMARY KEY, hit_rate REAL, avg_excess_12m REAL, sample_n INTEGER)""")
    for f, d in BASE_RATES.items():
        conn.execute("INSERT OR REPLACE INTO base_rates VALUES (?,?,?,?)",
                     (f, d["hit"], d["avg_excess_12m"], d["n"]))
    for tkr, tags, kill in META:
        conn.execute("UPDATE candidates SET factor_tags=?, kill_criteria=? WHERE ticker=?",
                     (tags, kill, tkr))
    conn.commit()

    # factor view: roll up Tier 1 by best/worst-rate tag
    print("Tier 1 by primary factor (backtest base-rate at 12mo):\n")
    print(f"{'tkr':<6} {'primary_tag':<26} {'hit':<6} {'avg_excess':<11} {'n':<3}")
    for r in conn.execute("""SELECT c.ticker, c.factor_tags FROM candidates c
                             WHERE c.tier LIKE '1%' ORDER BY c.ticker"""):
        tags = (r[1] or "").split(",")
        # rank by avg_excess descending — primary = the bucket that drives the thesis
        primary = max(tags, key=lambda t: BASE_RATES.get(t.strip(), {"avg_excess_12m": -1})["avg_excess_12m"])
        br = BASE_RATES.get(primary.strip(), {})
        print(f"  {r[0]:<6} {primary.strip():<26} {br.get('hit',0)*100:>4.0f}%  {br.get('avg_excess_12m',0)*100:+6.1f}%   {br.get('n',0)}")

    # Bucket-by-bucket count in Tier 1
    print("\nFactor exposure (count, sum of % weights NOT computed — equal-weight basket assumption):")
    counts = {}
    for r in conn.execute("SELECT factor_tags FROM candidates WHERE tier LIKE '1%'"):
        for t in (r[0] or "").split(","):
            t = t.strip()
            if t: counts[t] = counts.get(t, 0) + 1
    for k, v in sorted(counts.items(), key=lambda x: -x[1]):
        br = BASE_RATES.get(k)
        marker = " ⚠ low base rate" if (br and br["avg_excess_12m"] < 0) else ""
        print(f"  {k:<28} n={v}{marker}")

if __name__ == "__main__":
    run()
