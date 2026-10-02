"""Mark funds that we know don't file 13F-HR with SEC so they're not stuck
in 'no_match' limbo.

UK/EU/JP/CA fund managers without US clients don't have to file Form 13F.
Single-person investors (Eric Sprott, Charles Frischer, Joshua Schechter etc)
have personal holdings disclosed elsewhere (Form 4 / SEDI). Tracker tabs
("# Concentrated Value", "# Warrant-Specialist Investors") aren't funds at
all — they're our own meta-rollups.

Setting status to a descriptive value here keeps these out of repeated
auto-resolver attempts and makes the data-gap explicit in any audit.
"""
import os, sqlite3

DB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "cyclepapa.db")

NON_FILERS = {
    # UK
    "Palliser Capital UK": "uk_non_filer",
    "Asset Value Investors   AVI": "uk_non_filer",  # actually filed (CIK seeded above)
    "RIT Capital Partners plc": "uk_non_filer",
    "Lindsell Train Limited": "uk_non_filer",
    "Slater Investments": "uk_non_filer",
    "TT International Investment Man": "uk_non_filer",
    "Crystal Amber Fund": "uk_non_filer",
    "Findlay Park Partners": "uk_non_filer",
    "Holland Advisors": "uk_non_filer",
    "Knight Vinke Asset Management": "uk_non_filer",
    "Bluebell Capital Partners": "uk_non_filer",
    "Caius Capital LLP": "uk_non_filer",
    "Albert Bridge Capital": "uk_non_filer",
    "PrimeStone Capital": "uk_non_filer",
    "The Children's Investment Fund": "uk_non_filer",  # TCI does file in US too — CIK 1647824
    "Mobius Capital Partners": "uk_non_filer",
    "Aspect Capital": "uk_non_filer",
    "ISAM": "uk_non_filer",
    "Tellworth (Premier Miton)": "uk_non_filer",
    "Sanford DeLand Buffettology": "uk_non_filer",
    "Argyle Street Management": "uk_non_filer",
    "Troy Asset Mgmt Trojan Fund": "uk_non_filer",
    "Aubrey Capital Management": "uk_non_filer",
    "L1 Capital — L1 Gold Fund": "au_non_filer",
    "Langdon Equity Partners": "ca_non_filer",
    "Lancero Capital": "uk_non_filer",

    # EU
    "Effissimo Capital Management": "jp_non_filer",
    "Horos Asset Management": "es_non_filer",
    "azValor Asset Management": "es_non_filer",
    "Cobas Asset Management": "es_non_filer",
    "Magallanes Value Investors": "es_non_filer",
    "Buy & Hold": "es_non_filer",
    "Numantia Patrimonio Global": "es_non_filer",
    "Valentum AM": "es_non_filer",
    "True Value": "es_non_filer",
    "Equam Capital": "es_non_filer",
    "Comgest (France)": "fr_non_filer",
    "CIAM": "fr_non_filer",
    "Andurand Capital Management": "fr_non_filer",
    "Westbeck Capital": "fr_non_filer",
    "Active Ownership Capital": "de_non_filer",
    "Quarz Capital Management": "ch_non_filer",
    "Mawer Investment Management": "ca_non_filer",
    "Burgundy Asset Management": "ca_non_filer",
    "Donville Kent": "ca_non_filer",
    "Pender Fund Capital": "ca_non_filer",
    "EdgePoint": "ca_non_filer",
    "HGC Investment Management": "ca_non_filer",
    "Lester Asset Management": "ca_non_filer",
    "ThreeD Capital Inc": "ca_non_filer",
    "Periscope Capital Inc": "ca_non_filer",
    "West Face Capital": "ca_non_filer",

    # JP
    "Misaki Capital": "jp_non_filer",
    "Hibiki Path Advisors": "jp_non_filer",
    "SPARX Group": "jp_non_filer",
    "Strategic Capital Inc": "jp_non_filer",
    "Taiyo Pacific Partners": "jp_non_filer",
    "Symphony Financial Partners": "jp_non_filer",
    "Nippon Active Value Fund": "uk_non_filer",
    "3D Investment Partners": "jp_non_filer",
    "C&I Holdings   Murakami Family": "jp_non_filer",

    # AU/AsiaPac
    "Pangolin Asia Fund": "sg_non_filer",
    "Lion Selection Group": "au_non_filer",
    "Regal Funds Management": "au_non_filer",
    "Tribeca Global Natural Resource": "au_non_filer",
    "Aoris Investment Management": "au_non_filer",
    "Asia Frontier Capital": "hk_non_filer",
    "African Lions Fund": "za_non_filer",

    # Brazil
    "Dynamo Administração de Recurso": "br_non_filer",

    # Individuals / personal SMA
    "Eric Sprott PERSONAL": "individual",
    "Charles L. Frischer": "individual",
    "Joshua Schechter": "individual",
    "Ronald L. Chez": "individual",
    "Marc Cohodes": "individual",
    "Peter H. Kamin": "individual",
    "Eric Shahinian": "individual",
    "Mark E. Schwarz": "individual",
    "Bradley L. Radoff": "individual",
    "Braden M. Leonard": "individual",

    # Meta tabs / not real funds
    "# Concentrated Value": "meta_rollup",
    "# Warrant-Specialist Investors": "meta_rollup",
    "Additional manager covered": "meta_rollup",

    # Aggregators / not filers
    "Hibiki Path Advisors": "jp_non_filer",
    "Whitebridge Tactical Strategy": "skip_no_aum",
    "Park Lane Family Office": "private_office",
    "Woodlock House Family Capital": "private_office",
}

def run():
    conn = sqlite3.connect(DB)
    n = 0
    for name_prefix, status in NON_FILERS.items():
        rows = conn.execute("SELECT fund FROM fund_resolution_state WHERE fund LIKE ? AND best_cik IS NULL",
                            (name_prefix + "%",)).fetchall()
        for (fund,) in rows:
            conn.execute("""UPDATE fund_resolution_state SET status=?, asof=date('now')
                WHERE fund=?""", (status, fund))
            n += 1
    conn.commit()
    print(f"marked {n} non-13F filers")
    print("\n--- by status ---")
    for r in conn.execute("SELECT status, COUNT(*) FROM fund_resolution_state GROUP BY status ORDER BY 2 DESC"):
        print(f"  {r[0]:<20} {r[1]}")

if __name__ == "__main__":
    run()
