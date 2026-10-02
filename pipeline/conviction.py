"""Multi-factor conviction scoring — STYLE-WEIGHTED.

The user's call: the fund-style DNA SHOULD be the basis of the positioning
tracker. A 5% position at a Value Legend (which holds 8 names total) is
not the same as 5% at a Mega Multi-Strat (which holds 600). This version
applies style multipliers so concentrated styles' signals are louder.

Per (fund, ticker) signals — same 11 as before:
  HYPER_CONVICTION   pct_of_book >= 10%
  TOP_PICK           >= 5% book OR 'top-5' mention
  ACTIVIST_13D       sec 2 row containing '13D'
  THRESHOLD_13G      sec 2 row that's a 13G
  NEW_INIT_LARGE     sec 3 (new position sized large)
  MATERIAL_ADD       sec 4
  PUBLIC_LETTER      letter / thesis / pitch / campaign / Sohn
  FOLLOW_ON          PIPE / follow-on / financing at known price
  HOLDING_PERSIST    appears across multiple sections of one fund
  INSIDER_COBUY      ticker has live EDGAR Form-4 cluster
  MULTI_FUND_PEER    >=3 other funds also hold conviction-side

STYLE WEIGHT (multiplies the per-row score):

  Value / Concentrated Quality            1.6    (8-30 names typical)
  Tiger Cubs / L/S Legends                1.4    (concentrated growth)
  Skin-in-Game / Fat-Pitch                1.5    (in 'Value' macro)
  Family Offices / Individual Filers      1.5    (own capital)
  Activists / Special Situations          1.4    (concentrated by mandate)
  Biotech Specialists                     1.3    (concentrated by sector)
  Distressed / Event-Driven               1.2
  Small-cap / Multibagger Specialists     1.2
  Microcap-Tactical                       1.2
  Foreign / EM Value                      1.0
  CTA / Trend Followers                   0.6    (mostly leverage signals)
  Warrant Specialists                     0.7    (binary, not conviction)
  Mega Multi-Strats / Quants              0.4    (hold thousands of names)
  Macro / Trend                           0.6
  PE / SPAC / Gold / Mining               0.7
  Other / Unclassified                    1.0
"""
import os, re, sqlite3
DB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "cyclepapa.db")

WEIGHTS = {
    "HYPER_CONVICTION":  4.0, "TOP_PICK": 3.0, "ACTIVIST_13D": 3.0,
    "THRESHOLD_13G": 1.5, "NEW_INIT_LARGE": 2.0, "MATERIAL_ADD": 2.0,
    "PUBLIC_LETTER": 2.5, "FOLLOW_ON": 2.5, "HOLDING_PERSIST": 1.5,
    "INSIDER_COBUY": 3.5, "MULTI_FUND_PEER": 1.0,
}
STYLE_W = {
    "Value / Concentrated Quality": 1.6,
    "Activists / Special Situations": 1.4,
    "Tiger Cubs / L/S Legends": 1.4,
    "Family Offices / Individual Filers": 1.5,
    "Biotech Specialists": 1.3,
    "Distressed / Event-Driven": 1.2,
    "Small-cap / Multibagger Specialists": 1.2,
    "Microcap-Tactical": 1.2,
    "Foreign / EM Value": 1.0,
    "Other / Unclassified": 1.0,
    "Warrant Specialists": 0.7,
    "PE / SPAC / Gold / Mining": 0.7,
    "CTA / Trend Followers": 0.6,
    "Macro / Trend": 0.6,
    "Mega Multi-Strats / Quants": 0.4,
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
    DROP TABLE IF EXISTS ticker_style_conviction;
    CREATE TABLE fund_conviction (
      fund TEXT, ticker TEXT, signals TEXT, raw_score REAL, style_weight REAL,
      score REAL, macro_style TEXT,
      pct_book REAL, pct_company REAL, dollar_m REAL,
      PRIMARY KEY (fund, ticker));
    CREATE TABLE ticker_conviction (
      ticker TEXT PRIMARY KEY, score REAL, raw_score REAL, n_funds INTEGER,
      n_hyper INTEGER, n_top_pick INTEGER, n_activist_13d INTEGER, n_passive_13g INTEGER,
      n_new_init INTEGER, n_material_add INTEGER, n_public_letter INTEGER,
      n_follow_on INTEGER, n_persist INTEGER, has_insider_cobuy INTEGER,
      sum_dollar_m REAL, max_pct_book REAL, max_pct_company REAL,
      fund_signals_summary TEXT, styles_summary TEXT);
    CREATE TABLE ticker_style_conviction (
      ticker TEXT, macro_style TEXT, score REAL, n_funds INTEGER,
      n_hyper INTEGER, dollar_m REAL,
      PRIMARY KEY (ticker, macro_style));
    """)

    cobuy = {r[0] for r in conn.execute("SELECT ticker FROM insider_clusters")}
    from _canon import canon as _cn
    # Persist the fund -> canonical-manager mapping so SQL consumers (renderers)
    # can COUNT(DISTINCT canon) instead of multi-counting name variants.
    conn.execute("CREATE TABLE IF NOT EXISTS fund_canon (fund TEXT PRIMARY KEY, canon TEXT)")
    conn.execute("DELETE FROM fund_canon")
    _all_funds = {r[0] for r in conn.execute("SELECT DISTINCT fund FROM fund_positions")}
    _all_funds |= {r[0] for r in conn.execute("SELECT DISTINCT fund FROM fund_13f_holdings")}
    _all_funds |= {r[0] for r in conn.execute("SELECT DISTINCT fund FROM fund_meta")}
    conn.executemany("INSERT OR REPLACE INTO fund_canon VALUES (?,?)",
                     [(f, _cn(f)) for f in _all_funds if f])
    _peer_mgrs = {}
    for tk, f in conn.execute("SELECT DISTINCT ticker, fund FROM fund_positions WHERE section=1"):
        _peer_mgrs.setdefault(tk, set()).add(_cn(f))
    peer = {tk: len(m) for tk, m in _peer_mgrs.items()}
    fund_style = {r[0]: r[1] for r in conn.execute("SELECT fund, macro_style FROM fund_style")}

    # Group by CANONICAL manager, not raw fund string — the same manager appears
    # under several name variants ("CAS Investment Partners", "... (Cliff",
    # "... Sosin"), and counting each variant as its own fund inflated n_funds /
    # signal counts. A representative raw name is kept for display + style lookup.
    from _canon import canon
    grouped = {}
    for r in conn.execute("""SELECT fund, ticker, section, pct_value, pct_kind, dollar_m, raw_text
                             FROM fund_positions WHERE ticker IS NOT NULL"""):
        grouped.setdefault((canon(r["fund"]), r["ticker"]), []).append(dict(r))

    for (_ck, tkr), rows in grouped.items():
        # representative variant: prefer one that has a style classification
        fund = rows[0]["fund"]
        for rr in rows:
            if rr["fund"] in fund_style:
                fund = rr["fund"]; break
        signals = set()
        max_book = max((r["pct_value"] for r in rows if r["pct_kind"]=="book" and r["pct_value"]), default=None)
        max_co   = max((r["pct_value"] for r in rows if r["pct_kind"]=="company" and r["pct_value"]), default=None)
        sum_d    = sum((r["dollar_m"] or 0) for r in rows)
        sections = {r["section"] for r in rows}
        text = " ".join(r["raw_text"] or "" for r in rows)

        if max_book and max_book >= 10.0: signals.add("HYPER_CONVICTION")
        if max_book and max_book >= 5.0:  signals.add("TOP_PICK")
        elif TOP5_RE.search(text):         signals.add("TOP_PICK")
        if 2 in sections:
            if "13D" in text: signals.add("ACTIVIST_13D")
            elif "13G" in text or "13g" in text: signals.add("THRESHOLD_13G")
        if 3 in sections: signals.add("NEW_INIT_LARGE")
        if 4 in sections: signals.add("MATERIAL_ADD")
        if LETTER_RE.search(text): signals.add("PUBLIC_LETTER")
        if FOLLOWON_RE.search(text): signals.add("FOLLOW_ON")
        if len(sections) >= 2: signals.add("HOLDING_PERSIST")
        if tkr in cobuy: signals.add("INSIDER_COBUY")
        if peer.get(tkr, 0) >= 3: signals.add("MULTI_FUND_PEER")

        if not signals: continue
        raw = sum(WEIGHTS.get(s, 0) for s in signals)
        style = fund_style.get(fund, "Other / Unclassified")
        sw = STYLE_W.get(style, 1.0)
        score = round(raw * sw, 2)
        conn.execute("""INSERT OR REPLACE INTO fund_conviction VALUES (?,?,?,?,?,?,?,?,?,?)""",
                     (fund, tkr, ",".join(sorted(signals)), round(raw,2), sw, score, style,
                      max_book, max_co, sum_d))

    # aggregate to ticker
    agg = {}
    style_agg = {}
    for r in conn.execute("SELECT * FROM fund_conviction"):
        a = agg.setdefault(r["ticker"], {
            "score":0, "raw":0, "n_funds":0,
            "n_hyper":0,"n_top_pick":0,"n_activist_13d":0,"n_passive_13g":0,
            "n_new_init":0,"n_material_add":0,"n_public_letter":0,"n_follow_on":0,"n_persist":0,
            "has_insider_cobuy":0,"sum":0,"max_book":0,"max_co":0,
            "fund_sigs":[], "styles":{}})
        a["score"] += r["score"]; a["raw"] += r["raw_score"]; a["n_funds"] += 1
        for s in (r["signals"] or "").split(","):
            k = {"HYPER_CONVICTION":"n_hyper","TOP_PICK":"n_top_pick","ACTIVIST_13D":"n_activist_13d",
                 "THRESHOLD_13G":"n_passive_13g","NEW_INIT_LARGE":"n_new_init","MATERIAL_ADD":"n_material_add",
                 "PUBLIC_LETTER":"n_public_letter","FOLLOW_ON":"n_follow_on","HOLDING_PERSIST":"n_persist"}.get(s)
            if k: a[k] += 1
            if s == "INSIDER_COBUY": a["has_insider_cobuy"] = 1
        a["sum"] += r["dollar_m"] or 0
        a["max_book"] = max(a["max_book"], r["pct_book"] or 0)
        a["max_co"]   = max(a["max_co"],   r["pct_company"] or 0)
        a["fund_sigs"].append(f"{r['fund'][:24]}={r['score']:.0f}")
        st = r["macro_style"]
        sa = a["styles"].setdefault(st, {"score":0, "n":0, "hyper":0, "dm":0})
        sa["score"] += r["score"]; sa["n"] += 1
        if "HYPER_CONVICTION" in (r["signals"] or ""): sa["hyper"] += 1
        sa["dm"] += r["dollar_m"] or 0
        style_agg.setdefault(r["ticker"], {})[st] = sa

    for tkr, a in agg.items():
        styles_sum = "; ".join(f"{s}({d['n']}, {d['score']:.0f})" for s, d in sorted(a["styles"].items(), key=lambda x: -x[1]["score"])[:4])
        conn.execute("""INSERT INTO ticker_conviction VALUES (?,?,?,?, ?,?,?,?, ?,?,?, ?,?,?, ?,?,?, ?,?)""",
            (tkr, round(a["score"],1), round(a["raw"],1), a["n_funds"],
             a["n_hyper"], a["n_top_pick"], a["n_activist_13d"], a["n_passive_13g"],
             a["n_new_init"], a["n_material_add"], a["n_public_letter"],
             a["n_follow_on"], a["n_persist"], a["has_insider_cobuy"],
             round(a["sum"],1), round(a["max_book"],1) if a["max_book"] else None,
             round(a["max_co"],1) if a["max_co"] else None,
             ";".join(sorted(a["fund_sigs"], key=lambda s: -float(s.split('=')[1]))[:6]),
             styles_sum))
        for st, d in a["styles"].items():
            conn.execute("INSERT INTO ticker_style_conviction VALUES (?,?,?,?,?,?)",
                         (tkr, st, round(d["score"],1), d["n"], d["hyper"], round(d["dm"],1)))
    conn.commit()

    print("Top 20 style-weighted conviction names ex mega-cap:")
    mega = ("AMZN","MSFT","GOOGL","GOOG","NVDA","META","AAPL","TSLA","SPY","QQQ","IWM","IVV","IEF","BABA","TSM","BAC","BRK.B","BRK.A","NFLX","JPM","CRM","JNJ","WMT","H2","SEC","BN","AVGO")
    ph = ",".join("?"*len(mega))
    print(f"{'tkr':<7} {'score':<7} {'raw':<6} {'funds':<6} {'hyper':<6} {'styles converging'}")
    for r in conn.execute(f"""SELECT * FROM ticker_conviction WHERE ticker NOT IN ({ph})
                              ORDER BY score DESC LIMIT 20""", mega):
        print(f"  {r['ticker']:<7} {r['score']:<7} {r['raw_score']:<6} {r['n_funds']:<6} {r['n_hyper']:<6} {r['styles_summary'][:100]}")

if __name__ == "__main__":
    run()
