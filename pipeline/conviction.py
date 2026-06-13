"""Multi-factor conviction scoring — % of book is just one input.

Conviction signals we now combine per (fund, ticker):

  HYPER_CONVICTION   pct_of_book >= 10% (rare for diversified funds)
  TOP_PICK           position is top-5 in the fund's holdings
  ACTIVIST_13D       sec 2 row that contains '13D' (active intent > passive)
  THRESHOLD_13G      sec 2 row that's a 13G (passive but meaningful)
  NEW_INIT_LARGE     sec 3 (NEW position sized large)
  MATERIAL_ADD       sec 4 (existing position materially increased)
  PUBLIC_LETTER      raw_text mentions 'letter', 'thesis', 'campaign', 'memo'
  FOLLOW_ON          fund participated in follow-on/PIPE at a specific px
  HOLDING_PERSIST    appears in multiple sections of the same fund (long-held + still adding)
  INSIDER_COBUY      ticker has a verified live insider Form-4 cluster too
  MULTI_FUND_PEER    >=3 other funds also hold; activist >=2 other filers

Each signal carries a weight; per-(fund,ticker) score = sum of weights.
Ticker-level aggregate sums across funds, AUM-weighted (proxy: top-pick +
hyper-conviction in concentrated funds count for more).
"""
import os, re, sqlite3
DB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "cyclepapa.db")

WEIGHTS = {
    "HYPER_CONVICTION":  4.0,
    "TOP_PICK":          3.0,
    "ACTIVIST_13D":      3.0,
    "THRESHOLD_13G":     1.5,
    "NEW_INIT_LARGE":    2.0,
    "MATERIAL_ADD":      2.0,
    "PUBLIC_LETTER":     2.5,
    "FOLLOW_ON":         2.5,
    "HOLDING_PERSIST":   1.5,
    "INSIDER_COBUY":     3.5,
    "MULTI_FUND_PEER":   1.0,
}

LETTER_RE = re.compile(r"\b(letter|thesis|memo|campaign|pitch|sohn|deep[\s-]?dive|presentation)\b", re.I)
FOLLOWON_RE = re.compile(r"\b(follow[\s-]?on|PIPE|registered\s+offering|secondary|anchored?|financing\s+at\s+\$)\b", re.I)
TOP5_RE = re.compile(r"\btop[\s-]?5\b", re.I)

def run():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    conn.executescript("""
    DROP TABLE IF EXISTS fund_conviction;
    DROP TABLE IF EXISTS ticker_conviction;
    CREATE TABLE fund_conviction (
      fund TEXT, ticker TEXT, signals TEXT, score REAL,
      pct_book REAL, pct_company REAL, dollar_m REAL,
      PRIMARY KEY (fund, ticker));
    CREATE TABLE ticker_conviction (
      ticker TEXT PRIMARY KEY,
      score REAL, n_funds INTEGER,
      n_hyper INTEGER, n_top_pick INTEGER, n_activist_13d INTEGER,
      n_passive_13g INTEGER, n_new_init INTEGER, n_material_add INTEGER,
      n_public_letter INTEGER, n_follow_on INTEGER, n_persist INTEGER,
      has_insider_cobuy INTEGER, sum_dollar_m REAL,
      max_pct_book REAL, max_pct_company REAL,
      fund_signals_summary TEXT);
    """)

    # known live insider-cluster tickers (the +109% bucket)
    cobuy = {r[0] for r in conn.execute("SELECT ticker FROM insider_clusters")}

    # multi-fund peer counts (>=3 other funds hold the ticker conviction-side)
    peer = {r[0]: r[1] for r in conn.execute(
        "SELECT ticker, COUNT(DISTINCT fund) FROM fund_positions WHERE section=1 GROUP BY ticker")}

    # process per-(fund, ticker) — group all rows for one fund/ticker pair to
    # combine signals from different sections
    grouped = {}
    for r in conn.execute("""SELECT fund, ticker, section, pct_value, pct_kind, dollar_m, raw_text
                             FROM fund_positions WHERE ticker IS NOT NULL"""):
        key = (r["fund"], r["ticker"])
        grouped.setdefault(key, []).append(dict(r))

    for (fund, tkr), rows in grouped.items():
        signals = set()
        max_book = max((r["pct_value"] for r in rows if r["pct_kind"]=="book" and r["pct_value"]), default=None)
        max_co   = max((r["pct_value"] for r in rows if r["pct_kind"]=="company" and r["pct_value"]), default=None)
        sum_d    = sum((r["dollar_m"] or 0) for r in rows)
        sections = {r["section"] for r in rows}
        all_text = " ".join(r["raw_text"] or "" for r in rows)

        if max_book and max_book >= 10.0: signals.add("HYPER_CONVICTION")
        if max_book and max_book >= 5.0:  signals.add("TOP_PICK")
        elif TOP5_RE.search(all_text):     signals.add("TOP_PICK")
        if 2 in sections:
            if "13D" in all_text and "13D/A" in all_text:
                signals.add("ACTIVIST_13D")
            elif "13D" in all_text:
                signals.add("ACTIVIST_13D")
            elif "13G" in all_text or "13g" in all_text:
                signals.add("THRESHOLD_13G")
        if 3 in sections: signals.add("NEW_INIT_LARGE")
        if 4 in sections: signals.add("MATERIAL_ADD")
        if LETTER_RE.search(all_text): signals.add("PUBLIC_LETTER")
        if FOLLOWON_RE.search(all_text): signals.add("FOLLOW_ON")
        if len(sections) >= 2: signals.add("HOLDING_PERSIST")
        if tkr in cobuy: signals.add("INSIDER_COBUY")
        if peer.get(tkr, 0) >= 3: signals.add("MULTI_FUND_PEER")

        score = round(sum(WEIGHTS.get(s, 0) for s in signals), 2)
        if not signals: continue
        conn.execute("""INSERT OR REPLACE INTO fund_conviction VALUES (?,?,?,?,?,?,?)""",
                     (fund, tkr, ",".join(sorted(signals)), score, max_book, max_co, sum_d))

    # aggregate to ticker level
    aggregated = {}
    for r in conn.execute("SELECT * FROM fund_conviction"):
        a = aggregated.setdefault(r["ticker"], {
            "score": 0, "n_funds": 0,
            "n_hyper":0,"n_top_pick":0,"n_activist_13d":0,"n_passive_13g":0,
            "n_new_init":0,"n_material_add":0,"n_public_letter":0,"n_follow_on":0,"n_persist":0,
            "has_insider_cobuy":0,"sum_dollar_m":0,"max_pct_book":0,"max_pct_company":0,
            "fund_signals":[]})
        a["score"] += r["score"]; a["n_funds"] += 1
        for s in (r["signals"] or "").split(","):
            k = {"HYPER_CONVICTION":"n_hyper","TOP_PICK":"n_top_pick","ACTIVIST_13D":"n_activist_13d",
                 "THRESHOLD_13G":"n_passive_13g","NEW_INIT_LARGE":"n_new_init","MATERIAL_ADD":"n_material_add",
                 "PUBLIC_LETTER":"n_public_letter","FOLLOW_ON":"n_follow_on","HOLDING_PERSIST":"n_persist"}.get(s)
            if k: a[k] += 1
            if s == "INSIDER_COBUY": a["has_insider_cobuy"] = 1
        a["sum_dollar_m"] += r["dollar_m"] or 0
        a["max_pct_book"] = max(a["max_pct_book"], r["pct_book"] or 0)
        a["max_pct_company"] = max(a["max_pct_company"], r["pct_company"] or 0)
        a["fund_signals"].append(f"{r['fund'][:24]}={r['score']:.0f}")

    for tkr, a in aggregated.items():
        conn.execute("""INSERT INTO ticker_conviction VALUES
            (?,?,?, ?,?,?, ?,?,?, ?,?,?, ?,?, ?,?, ?)""",
            (tkr, round(a["score"],1), a["n_funds"],
             a["n_hyper"], a["n_top_pick"], a["n_activist_13d"],
             a["n_passive_13g"], a["n_new_init"], a["n_material_add"],
             a["n_public_letter"], a["n_follow_on"], a["n_persist"],
             a["has_insider_cobuy"], round(a["sum_dollar_m"],1),
             round(a["max_pct_book"],1) if a["max_pct_book"] else None,
             round(a["max_pct_company"],1) if a["max_pct_company"] else None,
             ";".join(sorted(a["fund_signals"], key=lambda s: -float(s.split('=')[1]))[:6])))
    conn.commit()

    print("Top 25 multi-factor conviction names (ex mega-caps):")
    mega = ("AMZN","MSFT","GOOGL","GOOG","NVDA","META","AAPL","TSLA","SPY","QQQ","IWM","IVV","IEF","BABA","TSM","BAC","BRK.B","BRK.A","NFLX","COIN","JPM","CRM","JNJ","WMT")
    placeholders = ",".join("?"*len(mega))
    print(f"{'tkr':<8} {'score':<7} {'#funds':<7} {'hyper':<6} {'13D':<5} {'13G':<5} {'NEW':<5} {'+ADD':<5} {'letter':<7} {'cobuy':<6} {'$M':<10} {'top fund signals'}")
    for r in conn.execute(f"""SELECT * FROM ticker_conviction WHERE ticker NOT IN ({placeholders})
                              ORDER BY score DESC LIMIT 25""", mega):
        print(f"  {r['ticker']:<8} {r['score']:<7} {r['n_funds']:<7} {r['n_hyper']:<6} "
              f"{r['n_activist_13d']:<5} {r['n_passive_13g']:<5} {r['n_new_init']:<5} {r['n_material_add']:<5} "
              f"{r['n_public_letter']:<7} {'Y' if r['has_insider_cobuy'] else '':<6} "
              f"${r['sum_dollar_m']:<9.0f} {r['fund_signals_summary'][:64]}")

    print("\nWeights applied:")
    for k, v in WEIGHTS.items(): print(f"  {k:<22} {v}")

if __name__ == "__main__":
    run()
