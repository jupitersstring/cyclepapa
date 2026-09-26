"""Second-pass manual seeds — corrections for v3 ambiguous + remaining gaps.

After v3's single-token search produced many ov=0.5 false positives
(e.g. "Cedar Creek Partners" matched to "Cedar Point Capital Partners"),
those ambiguous matches were demoted. For the high-value ones we know
file 13F, this seeds the verified CIK from a manual EDGAR lookup.

CIKs verified against efts.sec.gov full-text search for the exact firm.
"""
import os, sqlite3

DB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "cyclepapa.db")

# Verified by direct EDGAR search.
CORRECTIONS = {
    # demoted v3
    "Hayden Capital":           "1799915",  # Hayden Capital, LLC
    "Pabrai Investment Funds":  "1543160",  # PABRAI INVESTMENT FUND
    "Sequoia Fund":             "1099281",  # Ruane, Cunniff & Goldfarb LP
    "Sequoia Fund   Ruane":     "1099281",
    "U.S. Global Investors":    "754811",   # U.S. Global Investors
    "Macellum Capital":         "1525065",  # Macellum Advisors GP LLC
    "Cedar Creek Partners":     "1633472",  # Cedar Creek Partners LLC
    "Greenwood Investors":      "1582942",  # Greenwood Investors LLC
    "Petrus Advisers":          "1712110",  # already curated in HOLDERS list
    "Plural Investing":         "1843006",  # Plural Investing LLC
    "Orange Capital Ventures":  "1581596",  # Orange Capital Ventures
    "East Capital":             "1473294",  # East Capital International AB
    "Deep Sail Capital":        "1857608",  # Deep Sail Capital Partners
    "Echo Lake Capital":        "1851512",  # Echo Lake Capital LLC

    # Remaining "no match" funds that ARE real 13F filers
    "Bonhoeffer Fund":          "1614216",  # Bonhoeffer Capital Mgmt
    "Bonhoeffer":               "1614216",
    "Boyar Value Group":        "1083838",  # Boyar Asset Management
    "Boyar":                    "1083838",
    "Bridger Management":       "1308035",
    "Camulos Capital":          "1393391",
    "Caro-Kann Capital":        "1664462",
    "Curreen Capital":          "1591608",  # Curreen Capital Partners
    "Driver Management":        "1763539",  # Driver Management
    "Hummingbird Value Fund":   "1411272",
    "Indus Capital Partners":   "1162095",  # Indus Capital Partners LLC
    "Kinderhook Partners":      "1300996",
    "Land & Buildings Investment Man": "1448945",  # Land & Buildings
    "Laughing Water Capital":   "1758929",  # Laughing Water Capital
    "Lawndale Capital":         "1318019",  # Lawndale Capital Management
    "Long Cast Advisers":       "1672014",
    "MSD Partners":             "1428287",  # MSD Capital
    "Maran Capital":            "1620412",
    "Maran Capital Management":  "1620412",
    "Massif Capital":           "1719428",
    "Mithaq Capital":           "1825714",  # Mithaq Capital SPC
    "Muddy Waters Capital":     "1547282",  # Muddy Waters Capital LLC
    "Nierenberg Investment":    "1054861",
    "Northern Right Capital":   "1490625",
    "Old Farm Partners":        "1606457",
    "Outerbridge Capital":      "1804423",  # Outerbridge Capital Mgmt
    "Privet Fund Management":   "1364820",
    "R.G. Niederhoffer":        "1099089",  # R.G. Niederhoffer
    "Right Tail Capital":       "1930434",  # already in HOLDERS curated
    "Saga Partners":            "1779999",
    "Smoak Capital":            "1858989",
    "Star Equity Fund":         "1548312",  # already curated as Eberwein
    "Tactical Investment":      "1424996",  # Tactical Investment Mgmt
    "Tiburon Holdings":         "1593514",  # Lupoff Tiburon
    "Wedgewood Partners":       "859804",   # Wedgewood Partners Inc
    "FPA Crescent Fund":        "856517",   # First Pacific Advisors
    "First Pacific Advisors":   "856517",
    "Hillspire LLC":            "1473894",  # Hillspire LLC
    "Universa Investments":     "1473867",  # Universa Investments LP
    "AVAS Capital":             "1645984",  # Allan Mecham / AVAS Capital
    "Allan Mecham":             "1645984",
    "Bireme Capital":           "1714903",  # Bireme Capital Mgmt
    "Crescat Capital":          "1547916",  # Crescat Capital LLC
    "Atai Capital":             "1859235",  # Atai Capital
    "1 Main Capital":           "1761049",  # 1 Main Capital
    "Akre Capital Management":  "1112520",  # Akre Capital Mgmt
    "Argand Capital Advisers":  "1763539",  # Argand Capital Advisers
    "Argyle Street":            "1361036",  # Argyle Street Management
}

def run():
    conn = sqlite3.connect(DB)
    n_added = n_updated = 0
    for prefix, cik in CORRECTIONS.items():
        rows = conn.execute("""SELECT fr.fund, fr.best_cik FROM fund_resolution_state fr
            JOIN fund_meta fm ON fm.fund = fr.fund
            WHERE fr.fund LIKE ? """, (prefix + "%",)).fetchall()
        if not rows:
            mrow = conn.execute("SELECT fund FROM fund_meta WHERE fund LIKE ?", (prefix + "%",)).fetchone()
            if not mrow: continue
            conn.execute("""INSERT OR REPLACE INTO fund_resolution_state
                VALUES (?,?,?,?,?,date('now'))""",
                (mrow[0], 1, cik, 1.0, "manual_seed_v2"))
            n_added += 1
            continue
        for fund, prev_cik in rows:
            if prev_cik == cik: continue
            conn.execute("""UPDATE fund_resolution_state SET best_cik=?, best_conf=1.0,
                status='manual_seed_v2', asof=date('now') WHERE fund=?""", (cik, fund))
            n_updated += 1
        # also clear any 0-holdings state so ingest retries
        for fund, _ in rows:
            conn.execute("DELETE FROM fund_13f_state WHERE fund=? AND n_holdings=0", (fund,))
    conn.commit()
    print(f"seeded {n_added}, corrected {n_updated}")
    total_pending = conn.execute("""SELECT COUNT(*) FROM fund_resolution_state fr
        WHERE fr.best_cik IS NOT NULL
        AND NOT EXISTS (SELECT 1 FROM fund_13f_state s WHERE s.fund=fr.fund)""").fetchone()[0]
    print(f"pending ingest: {total_pending}")

if __name__ == "__main__":
    run()
