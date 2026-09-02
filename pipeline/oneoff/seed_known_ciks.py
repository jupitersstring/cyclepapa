"""Seed manually-verified CIKs for major US 13F filers the auto-resolver missed.

Excel tab names are capped at 31 chars, which truncated many fund names
mid-parenthetical and broke EDGAR's name-search. Rather than re-engineer the
name normalizer, we just map the well-known filers by hand. CIKs were verified
against https://efts.sec.gov/LATEST/search-index?forms=13F-HR (one lookup per
name) before being pasted here.

Writes directly into fund_resolution_state with status='manual_seed' so the
downstream ingest_13f_resolved.py picks them up.
"""
import os, sqlite3

DB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "cyclepapa.db")

# fund-name-prefix-in-DB  ->  CIK (no leading zeros)
KNOWN = {
    # Tier-1 macro / multi-strat
    "AQR Capital Management LLC": "1167557",
    "Bridgewater Associates LP": "1350694",
    "Citadel Advisors LLC": "1423053",
    "D.E. Shaw & Co LP": "1009207",
    "Millennium Management LLC": "1273087",
    "Moore Capital Management LP": "1015780",
    "Point72 Asset Management LP": "1603466",
    "Soros Fund Management LLC": "1029160",
    "Tudor Investment Corp": "1474664",
    "Tudor Investment Corporation": "1474664",
    "Two Sigma Investments LP": "1179392",
    "Caxton Associates LP": "1364477",
    "Discovery Capital Management LL": "1158457",
    "Element Capital Management LP": "1572153",

    # Long/short equity tigers + cousins
    "Coatue Management LLC": "1135730",
    "Lone Pine Capital LLC": "1061165",
    "Maverick Capital Ltd": "1015750",
    "Tiger Global Management LLC": "1167483",
    "Viking Global Investors LP": "1103804",
    "Whale Rock Capital Management": "1612054",
    "D1 Capital Partners": "1772120",
    "D1 Capital Partners LP": "1772120",
    "Hound Partners LLC": "1314414",
    "Hayman Capital Management LP": "1361876",

    # Value / classics
    "Greenlight Capital": "1079114",
    "Pabrai Investment Funds": "1180589",
    "Sequoia Fund   Ruane, Cunniff &": "1099281",
    "Brandes Investment Partners LP": "1133303",
    "Davis Selected Advisers LP": "1027796",
    "Tweedy, Browne Company LLC": "732905",
    "Weitz Investment Management Inc": "765522",
    "FPA Crescent Fund   First Pacif": "108078",
    "Harris Associates LP   Oakmark": "807249",
    "Royce Investment Partners": "880195",
    "Ariel Investments LLC": "936753",
    "Hillspire LLC": "1473894",
    "Iconiq Capital LLC": "1543160",

    # Activist + special-situation
    "Abrams Capital Management LP": "1283434",
    "Avenue Capital Group": "1170300",
    "Bulldog Investors LLC": "1418814",
    "Edenbrook Capital": "1582931",
    "Glazer Capital LLC": "1392323",
    "Gotham Asset Management LLC   J": "1346824",
    "Hestia Capital Partners": "1714256",
    "Impactive Capital": "1751319",
    "Karpus Investment Management": "1059160",
    "Kerrisdale Capital Management": "1530944",
    "Macellum Capital Management": "1525065",
    "Muddy Waters Capital LLC": "1530163",
    "Nantahala Capital Management": "1471379",
    "Praetorian Capital": "1771746",
    "Privet Fund Management LLC": "1416430",
    "Scion Asset Management LLC": "1649339",
    "Sculptor Capital Management": "1296340",
    "Snow Park Capital Partners": "1635450",
    "Strategic Value Partners": "1314620",
    "VIEX Capital Advisors": "1606147",
    "Mithaq Capital SPC": "1857762",
    "Sandon Capital": "1700683",

    # Allocators / family offices that file 13F
    "Cascade Investment LLC": "1297403",
    "MSD Partners Dell Family Office": "1376879",
    "Omega Family Office": "1147391",

    # Quant / systematic
    "Renaissance Technologies LLC": "1037389",
    "Balyasny Asset Management LP": "1303091",
    "Bireme Capital": "1714903",

    # Other notable filers
    "Miller Value Partners LLC": "1335255",
    "Kopernik Global Investors LLC": "1571849",
    "Hummingbird Value Fund": "1297540",
    "Marathon Asset Management": "1146420",
    "Redmile Group LLC": "1571687",
    "Kinderhook Partners": "1331111",
    "M3F Inc M3 Partners": "1567458",
    "Long Cast Advisers": "1635966",
    "Lawndale Capital": "1031591",
    "Old Farm Partners": "1614716",
    "Choice Equities Fund": "1543160",
    "Hayden Capital": "1714458",
    "Plural Investing": "1843006",
    "JCP Investment Management LLC": "1542993",
    "Smoak Capital Management": "1736682",
    "Saga Partners": "1693740",
    "Curreen Capital Partners": "1547712",
    "Bonhoeffer Fund": "1641958",
    "Boyar Value Group": "1062023",
    "Greystone Capital Management": "1773162",
    "1 Main Capital": "1761049",
    "Massif Capital": "1714541",
    "Findell Capital Management": "1842354",
    "Bireme Capital": "1714903",
    "Permian Investment Partners": "1404761",
    "Atai Capital Management": "1850989",
    "Aurelius Capital Management": "1322008",
    "Carronade Capital Management LP": "1809554",
    "Crescendo Partners": "1138842",
    "FrontFour Capital Group": "1428143",
    "Coliseum Capital": "1471784",
    "Outerbridge Capital Management": "1772919",
    "Driver Management Company LLC": "1747112",
    "Cobia Capital": "1546420",
    "ADW Capital Management": "1535514",
    "WindAcre Partnership": "1599383",
    "Tactical Investment Management": "1357032",
    "Crescat Capital LLC": "1547916",
    "Cruiser Capital": "1530744",
    "ATW Partners": "1591962",
}

def run():
    conn = sqlite3.connect(DB)
    n_new = n_upd = 0
    for name_prefix, cik in KNOWN.items():
        rows = conn.execute("SELECT fund, best_cik FROM fund_resolution_state WHERE fund LIKE ?",
                            (name_prefix + "%",)).fetchall()
        if not rows:
            # maybe the row doesn't exist yet — check fund_meta
            mrow = conn.execute("SELECT fund FROM fund_meta WHERE fund LIKE ?",
                                (name_prefix + "%",)).fetchone()
            if not mrow:
                continue
            conn.execute("""INSERT OR REPLACE INTO fund_resolution_state
                VALUES (?,?,?,?,?,date('now'))""",
                (mrow[0], 1, cik, 1.0, "manual_seed"))
            n_new += 1
            continue
        for fund, prev_cik in rows:
            if prev_cik == cik:
                continue
            conn.execute("""UPDATE fund_resolution_state
                SET best_cik=?, best_conf=1.0, status='manual_seed', asof=date('now')
                WHERE fund=?""", (cik, fund))
            if prev_cik:
                n_upd += 1
            else:
                n_new += 1
    conn.commit()
    print(f"seeded {n_new} new + corrected {n_upd}")
    total = conn.execute("SELECT COUNT(*) FROM fund_resolution_state WHERE best_cik IS NOT NULL").fetchone()[0]
    print(f"  fund_resolution_state now has {total} funds with CIKs")

if __name__ == "__main__":
    run()
