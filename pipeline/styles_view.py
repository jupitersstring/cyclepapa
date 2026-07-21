"""Mega-Sheet: 445 funds, 107 sub-groups, collapsed to ~13 macro styles.

Restores the original "funds organized by investing style" view that the
foundational workbook used, layered with the new conviction / Form-4 /
entry-intact lenses. For each macro style we produce:
  - the funds belonging to that style
  - that style's top-consensus tickers (what the style as a whole likes)
  - which of those tickers also hits the empirical filters (entry-intact,
    insider cluster, in Tier 1)
"""
import os, re, sqlite3
DB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "cyclepapa.db")

# Macro-style collapse: regex on fund_group -> style name. Order matters.
STYLE_RULES = [
    (r"biotech",                              "Biotech Specialists"),
    (r"warrant",                              "Warrant Specialists"),
    (r"cta|trend",                            "CTA / Trend Followers"),
    (r"quant|multi[\s-]?strat",               "Mega Multi-Strats / Quants"),
    (r"tiger\s*cub|l/?s\s+legends",           "Tiger Cubs / L/S Legends"),
    (r"family[\s-]?office|individual",        "Family Offices / Individual Filers"),
    (r"microcap[\s-]?tactical",               "Microcap-Tactical"),
    (r"small[\s-]?cap|multibagger",           "Small-cap / Multibagger Specialists"),
    (r"distressed|event[\s-]?driven",         "Distressed / Event-Driven"),
    (r"japan|european|asia|global|EM",        "Foreign / EM Value"),
    (r"activist|special\s+sits|sponsor",      "Activists / Special Situations"),
    (r"value|quality|compounder|skin|fat[\s-]?pitch|VIC|concentrated", "Value / Concentrated Quality"),
    (r"\bPE\b|\bLBO\b|private\s+equity|SPAC|gold|mining", "PE / SPAC / Gold / Mining"),
    (r"macro|trend",                          "Macro / Trend"),
]

def macro_style(group):
    g = (group or "").lower()
    for pat, name in STYLE_RULES:
        if re.search(pat, g, re.I):
            return name
    return "Other / Unclassified"

def run():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    conn.executescript("""
    DROP TABLE IF EXISTS fund_style;
    DROP TABLE IF EXISTS style_summary;
    DROP TABLE IF EXISTS style_consensus;
    CREATE TABLE fund_style (
      fund TEXT PRIMARY KEY, sub_group TEXT, macro_style TEXT,
      total_rows INTEGER, conviction_n INTEGER, threshold_n INTEGER,
      new_n INTEGER, adds_n INTEGER);
    CREATE TABLE style_summary (
      macro_style TEXT PRIMARY KEY,
      n_funds INTEGER, total_rows INTEGER,
      n_conviction INTEGER, n_threshold INTEGER, n_new INTEGER, n_adds INTEGER,
      top_funds TEXT, top_consensus TEXT);
    CREATE TABLE style_consensus (
      macro_style TEXT, ticker TEXT, n_funds INTEGER, dollar_m REAL,
      sections_seen TEXT, in_tier1 INTEGER, has_cluster INTEGER, entry_bucket TEXT,
      PRIMARY KEY (macro_style, ticker));
    """)

    funds = list(conn.execute("""SELECT fm.fund, fm.fund_group,
                                        SUM(CASE WHEN fp.section=1 THEN 1 ELSE 0 END) AS c1,
                                        SUM(CASE WHEN fp.section=2 THEN 1 ELSE 0 END) AS c2,
                                        SUM(CASE WHEN fp.section=3 THEN 1 ELSE 0 END) AS c3,
                                        SUM(CASE WHEN fp.section=4 THEN 1 ELSE 0 END) AS c4,
                                        COUNT(*) AS total
                                 FROM fund_meta fm LEFT JOIN fund_positions fp ON fp.fund=fm.fund
                                 GROUP BY fm.fund"""))
    for f in funds:
        m = macro_style(f["fund_group"])
        conn.execute("INSERT INTO fund_style VALUES (?,?,?,?,?,?,?,?)",
                     (f["fund"], f["fund_group"], m, f["total"] or 0,
                      f["c1"] or 0, f["c2"] or 0, f["c3"] or 0, f["c4"] or 0))

    # joins for consensus enrichment
    in_tier1 = {r[0] for r in conn.execute("SELECT ticker FROM candidates WHERE tier LIKE '1%'")}
    has_cluster = {r[0] for r in conn.execute("SELECT ticker FROM insider_clusters")}
    bucket = {r[0]: r[1] for r in conn.execute("SELECT ticker, bucket FROM ticker_entry_intact")}

    # style summaries + per-ticker consensus
    styles = sorted({macro_style(r["fund_group"]) for r in funds})
    for style in styles:
        # funds in this style
        member_funds = [r["fund"] for r in conn.execute(
            "SELECT fund FROM fund_style WHERE macro_style=?", (style,))]
        if not member_funds: continue
        ph = ",".join("?"*len(member_funds))
        agg = conn.execute(f"""SELECT COUNT(DISTINCT COALESCE(
                (SELECT canon FROM fund_canon fc WHERE fc.fund=fund_positions.fund), fund)) n, COUNT(*) total,
            SUM(CASE WHEN section=1 THEN 1 ELSE 0 END) c1,
            SUM(CASE WHEN section=2 THEN 1 ELSE 0 END) c2,
            SUM(CASE WHEN section=3 THEN 1 ELSE 0 END) c3,
            SUM(CASE WHEN section=4 THEN 1 ELSE 0 END) c4
            FROM fund_positions WHERE fund IN ({ph})""", member_funds).fetchone()
        top_funds = [r["fund"] for r in conn.execute(
            f"SELECT fund FROM fund_style WHERE macro_style=? ORDER BY total_rows DESC LIMIT 6", (style,))]
        # consensus tickers within this style — appearing in >=2 funds
        consensus = list(conn.execute(f"""
            SELECT ticker, COUNT(DISTINCT COALESCE(fc.canon, fp.fund)) AS nf, SUM(dollar_m) AS dm,
                   GROUP_CONCAT(DISTINCT section) AS secs
            FROM fund_positions fp
            LEFT JOIN fund_canon fc ON fc.fund = fp.fund
            WHERE fp.fund IN ({ph}) AND fp.ticker IS NOT NULL AND fp.ticker NOT IN
              ('AMZN','MSFT','GOOGL','GOOG','NVDA','META','AAPL','TSLA','SPY','QQQ','IWM','IVV','IEF','BABA','TSM','BAC','BRK.B','BRK.A','NFLX','JPM','CRM','JNJ','WMT','H2','SEC','GOOG')
            GROUP BY ticker HAVING nf >= 2
            ORDER BY nf DESC, dm DESC LIMIT 40""", member_funds))
        top_picks = ", ".join(f"{r['ticker']}({r['nf']})" for r in consensus[:10])

        conn.execute("""INSERT INTO style_summary VALUES (?,?,?,?,?,?,?,?,?)""",
                     (style, agg["n"], agg["total"] or 0, agg["c1"] or 0, agg["c2"] or 0,
                      agg["c3"] or 0, agg["c4"] or 0,
                      "; ".join(top_funds), top_picks))
        for c in consensus:
            conn.execute("""INSERT INTO style_consensus VALUES (?,?,?,?,?,?,?,?)""",
                         (style, c["ticker"], c["nf"], round(c["dm"] or 0, 1),
                          c["secs"],
                          1 if c["ticker"] in in_tier1 else 0,
                          1 if c["ticker"] in has_cluster else 0,
                          bucket.get(c["ticker"], "")))
    conn.commit()

    print("MEGA STYLE OVERVIEW (445 funds, 107 sub-groups, 13 macro styles):\n")
    print(f"{'style':<38} {'funds':<6} {'rows':<6} {'conv':<5} {'13D':<4} {'new':<4} {'adds':<5} top consensus")
    for r in conn.execute("SELECT * FROM style_summary ORDER BY n_funds DESC"):
        print(f"  {r['macro_style']:<38} {r['n_funds']:<6} {r['total_rows']:<6} "
              f"{r['n_conviction']:<5} {r['n_threshold']:<4} {r['n_new']:<4} {r['n_adds']:<5} {r['top_consensus'][:90]}")

if __name__ == "__main__":
    run()
