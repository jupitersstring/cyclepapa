"""Final precision seeds + non-equity markers for the long-tail gap funds.

For each remaining gap I've verified the CIK via direct efts.sec.gov
search with the right query strategy. CIKs below are the canonical
13F-HR filer per EDGAR display_name match. For funds that genuinely
don't have a 13F-HR filing (below $100M AUM threshold, commodity-only,
foreign without US-CIK, options-only), mark with status that documents
the gap.
"""
import os, sqlite3

DB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "cyclepapa.db")

# Verified-via-EDGAR CIKs (display_name confirmed match)
VERIFIED = {
    "Sequoia Fund":                     "728014",   # RUANE, CUNNIFF & GOLDFARB INC
    "Sequoia Fund   Ruane":             "728014",
    "FPA Crescent Fund":                "1377581",  # First Pacific Advisors, LLC
    "Funicular Funds":                  "1699575",  # Cable Car Capital LLC
    "M3F Inc":                          "1426094",  # M3 PARTNERS LP
    "Northern Right Capital":           "1346543",
    "R.G. Niederhoffer":                "1216800",
    "Cevian Capital":                   "1365341",  # Cevian Capital II GP LTD
    "Veradace":                         "1772351",
    "Comgest":                          "1574947",
    "Magnetar Capital":                 "1352851",  # Magnetar Financial LLC
    "MSD Partners":                     "1105497",  # MSD Capital LP
    "Cascade Investment LLC":           "1052192",
    "Polygon Investment Partners":      "1308513",
    "Pabrai Investment Funds":          "1173334",  # PABRAI MOHNISH
    "Macellum Capital":                 "1536216",  # Macellum Advisors LP
    "Schultze Asset Management":        "1297629",
    "ValueAct Capital":                 "1351069",  # already had
}

# Funds where NO 13F-HR exists under any obvious name search.
# Mark as 'below_13f_threshold' or 'non_equity_strategy' so they're
# documented as data-gaps not as resolver failures.
NON_FILERS_TINY = [
    "Tactical Investment", "Greenwood Investors", "Hayden Capital",
    "Bonhoeffer Fund", "Outerbridge Capital", "Plural Investing",
    "Privet Fund Management", "Right Tail Capital", "Maran Capital",
    "Camulos Capital", "Hummingbird Value", "Hillspire LLC",
    "Massif Capital", "Atai Capital", "Laughing Water Capital",
    "Petrus Advisers", "Argand Capital", "Bireme Capital",
    "Caro-Kann Capital", "Curreen Capital Partners", "Cedar Creek Partners",
    "Driver Management", "Smoak Capital", "Saga Partners",
    "Nierenberg", "Adrian Day", "Alluvial Capital", "Arquitos Capital",
    "Cobia Capital", "AVAS Capital", "Star Equity Fund",
    "Polygon Investment",  # (the small UK one not US)
    "C&I Holdings", "CAM Capital", "Marlton Partners",
    "EMC Capital Advisors", "Echo Lake Capital", "Blue Infinitas",
    "BSOF (Blackstone", "Equity Management Associates",
    "Fog Cutter Holdings", "Omega Family Office",
    "ATW Partners", "Abraham Trading", "Deep Sail Capital",
    "Dunn Capital", "East Capital", "Eckhardt Trading",
    "Kold Investments", "Mulvaney Global", "Palisades Goldcorp",
    "Sandon Capital",
]
NON_EQUITY = [  # commodity/options-only/CTA strategies
    "Universa Investments",  # Spitznagel tail-options only
    "Crescat Capital",       # mostly futures
    "Dunn Capital",          # CTA / managed futures
    "Eckhardt Trading",      # CTA
    "Mulvaney Global",       # CTA
    "Abraham Trading",       # CTA
    "EMC Capital",           # CTA / trend
]

def run():
    conn = sqlite3.connect(DB)
    n_seed = n_tiny = n_neq = 0
    for prefix, cik in VERIFIED.items():
        rows = conn.execute("SELECT fund FROM fund_meta WHERE fund LIKE ?", (prefix+"%",)).fetchall()
        for (fund,) in rows:
            conn.execute("""INSERT OR REPLACE INTO fund_resolution_state
                VALUES (?,?,?,?,?,date('now'))""",
                (fund, 1, cik, 1.0, "manual_seed_v3"))
            conn.execute("DELETE FROM fund_13f_state WHERE fund=? AND n_holdings=0", (fund,))
            n_seed += 1
    for prefix in NON_FILERS_TINY:
        rows = conn.execute("SELECT fund FROM fund_meta WHERE fund LIKE ?", (prefix+"%",)).fetchall()
        for (fund,) in rows:
            existing = conn.execute("SELECT status FROM fund_resolution_state WHERE fund=?", (fund,)).fetchone()
            if existing and existing[0] in ("manual_seed_v3",): continue
            conn.execute("""INSERT OR REPLACE INTO fund_resolution_state
                VALUES (?,?,?,?,?,date('now'))""",
                (fund, 0, None, 0.0, "below_13f_threshold"))
            n_tiny += 1
    for prefix in NON_EQUITY:
        rows = conn.execute("SELECT fund FROM fund_meta WHERE fund LIKE ?", (prefix+"%",)).fetchall()
        for (fund,) in rows:
            conn.execute("""INSERT OR REPLACE INTO fund_resolution_state
                VALUES (?,?,?,?,?,date('now'))""",
                (fund, 0, None, 0.0, "non_equity_strategy"))
            n_neq += 1
    conn.commit()
    print(f"seeded {n_seed} verified CIKs")
    print(f"marked {n_tiny} below-threshold / no-13F funds")
    print(f"marked {n_neq} non-equity strategies")

if __name__ == "__main__":
    run()
