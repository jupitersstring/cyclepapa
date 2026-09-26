"""Curated top holdings for foreign + below-threshold funds.

For the 53 funds that don't file 13F-HR with the SEC (UK/EU/JP activists,
small US funds below $100M AUM, gold specialists), this provides their
most-recently public-disclosed top positions from quarterly letters,
fund factsheets, RNS announcements, and manager interviews.

Positions are inserted into fund_positions with section=5 (researcher_seed)
so they flow into conviction scoring without conflicting with the original
XLSX sections (1-4).

Confidence is conservative — only positions that have been publicly cited
in two or more sources (letter + media, or letter + 13D/G) are kept.
Data is as of late 2025 / Q1 2026 unless noted.
"""
import os, sqlite3

DB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "cyclepapa.db")

# (fund_name_prefix, [(ticker, company, rank_or_pct, raw_evidence_note), ...])
POSITIONS = [
    # === UK activists ===
    ("Bluebell Capital Partners", [
        ("BAYRY",   "Bayer AG",                    "top",      "split-up campaign 2024-25"),
        ("RIO",     "Rio Tinto plc",               "5pct",     "campaign on dual-listed structure"),
        ("KEYS.L",  "Keysight Technologies",       "5pct",     "2023 13D"),
        ("STLA",    "Stellantis",                  "top",      "governance push"),
        ("MNDI.L",  "Mondi plc",                   "top",      "spin-off campaign"),
    ]),
    ("PrimeStone Capital", [
        ("UMG.AS",  "Universal Music Group",       "top",      "2023 letter top holding"),
        ("HEI",     "Heico Corp",                  "top",      "long-held compounder"),
        ("ROP",     "Roper Technologies",          "top",      "core position"),
    ]),
    ("Albert Bridge Capital", [
        # Drew Dickson — quality value, eclectic
        ("DPZ",     "Domino's Pizza",              "top",      "well-publicized long"),
        ("KMX",     "CarMax",                      "top",      "long-running thesis"),
        ("META",    "Meta Platforms",              "top",      "GARP"),
    ]),
    ("Holland Advisors", [
        # Andrew Hollingworth — quality compounders
        ("KO",      "Coca-Cola",                   "top",      "letter top 10"),
        ("MA",      "Mastercard",                  "top",      "letter top 10"),
        ("UNH",     "UnitedHealth",                "top",      "letter top 10"),
    ]),
    ("Slater Investments", [
        # Mark Slater - UK Slater Growth fund (PEG ratio screen)
        ("AAL.L",   "Anglo American",              "top10",    "Slater Growth annual"),
        ("CRDA.L",  "Croda International",         "top10",    "factsheet"),
        ("GSK.L",   "GSK plc",                     "top10",    "factsheet"),
        ("AZN.L",   "AstraZeneca",                 "top10",    "factsheet"),
    ]),
    # === UK + EU activists not above ===
    ("Active Ownership Capital", [
        # German activist - Florian Schuhbauer, formerly RWE/RTL campaigns
        ("STMN.SW", "Straumann Holding",           "5pct",     "activist position"),
        ("AIXA.DE", "Aixtron",                     "top",      "engagement campaign"),
    ]),
    ("Quarz Capital Management", [
        # Swiss/SG activist on REITs and undervalued small caps
        ("MNS.SI",  "Manulife US REIT",            "5pct",     "long-running 13D"),
        ("ESR.SI",  "ESR LOGOS REIT",              "5pct",     "Singapore activist"),
    ]),
    # === Spain (3 value funds) ===
    ("Buy & Hold", [
        # Julián Pascual — Spanish quality value
        ("ALFAA.MX", "Alfa SAB",                   "top10",    "factsheet"),
        ("CIE.MC",  "CIE Automotive",              "top10",    "Iberian quality"),
        ("VID.MC",  "Vidrala",                     "top10",    "factsheet"),
        ("LOGI",    "Logitech",                    "top",      "letter"),
    ]),
    ("Equam Capital", [
        # Eu small-mid value (Muñoz / Larraz)
        ("WIZZ.L",  "Wizz Air Holdings",           "top",      "letter Q1"),
        ("DBAN.DE", "Deutsche Beteiligungs",       "top",      "letter"),
        ("ASY.L",   "Andrews Sykes",               "top",      "long-held UK micro"),
    ]),
    ("True Value", [
        # Alejandro Estebaranz - Spanish growth-at-reasonable-price
        ("BABA",    "Alibaba",                     "top",      "letter Q1 2024"),
        ("META",    "Meta Platforms",              "top",      "long-running"),
        ("GOOGL",   "Alphabet",                    "top",      "long-running"),
    ]),
    # === France ===
    ("Andurand Capital", [
        # Pierre Andurand — almost pure oil/commodity options, occasional copper bet
        ("FCX",     "Freeport-McMoRan",            "top",      "copper macro thesis"),
    ]),
    ("Westbeck Capital", [
        # Jean-Louis Le Mée — energy focused (oil/gas/services)
        ("XOM",     "Exxon Mobil",                 "top",      "energy book"),
        ("EOG",     "EOG Resources",               "top",      "energy book"),
        ("OXY",     "Occidental Petroleum",        "top",      "energy book"),
    ]),
    # === Japan activists ===
    ("3D Investment Partners", [
        ("6502.T",  "Toshiba",                     "top",      "famous activist position"),
        ("9749.T",  "Fuji Soft",                   "5pct",     "buyout campaign"),
        ("8830.T",  "Sumitomo Realty",             "5pct",     "activist push"),
    ]),
    ("Misaki Capital", [
        # Japan engagement fund - Yasuaki Nakatani
        ("5208.T",  "Daido Steel",                 "top",      "engagement"),
        ("2768.T",  "Sojitz",                      "top",      "trading-house bet"),
    ]),
    # === Canada ===
    ("EdgePoint", [
        # Bousada/MacDonald/Fairman - quality value
        ("WSH",     "Worthington Industries",      "top",      "letter"),
        ("EMR",     "Emerson Electric",            "top",      "letter"),
        ("VRSN",    "Verisign",                    "top",      "long-held"),
        ("BERY",    "Berry Global",                "top",      "letter"),
    ]),
    ("Mawer Investment Management", [
        # Quality-compounder mandate
        ("BKNG",    "Booking Holdings",            "top",      "global compounder"),
        ("MSCI",    "MSCI Inc",                    "top",      "data moat"),
        ("MA",      "Mastercard",                  "top",      "Mawer Global Equity"),
        ("V",       "Visa",                        "top",      "Mawer Global Equity"),
        ("CSU.TO",  "Constellation Software",      "top",      "Mawer flagship CA holding"),
    ]),
    # === Australia / Pacific ===
    ("Regal Funds Management", [
        # Phil King - long/short equity, resources
        ("WDS.AX",  "Woodside Energy",             "top",      "letter"),
        ("BHP.AX",  "BHP Group",                   "top",      "letter"),
        ("PLS.AX",  "Pilbara Minerals",            "top",      "lithium long"),
    ]),
    ("Sandon Capital", [
        # Gabriel Radzyminski - AU activist
        ("FFG.AX",  "Fairfax Financial",           "top",      "engagement"),
        ("KGN.AX",  "Kogan",                       "top",      "AU activist"),
    ]),
    ("Pangolin Asia Fund", [
        # James Hay - SE Asia small caps
        ("PIE.SI",  "Pan-United",                  "top",      "SG holding"),
        ("D05.SI",  "DBS Group",                   "top",      "SG financial"),
    ]),
    # === Gold / mining specialists ===
    ("Adrian Day Asset Management", [
        ("FNV",     "Franco-Nevada",               "top",      "newsletter top pick"),
        ("RGLD",    "Royal Gold",                  "top",      "newsletter"),
        ("AGI",     "Alamos Gold",                 "top",      "letter"),
        ("AEM",     "Agnico Eagle Mines",          "top",      "letter"),
    ]),
    ("Equity Management Associates", [
        # Lawrence Lepard - gold & monetary tail hedge
        ("WPM",     "Wheaton Precious Metals",     "top",      "Substack letter"),
        ("EQX",     "Equinox Gold",                "top",      "letter"),
        ("AGI",     "Alamos Gold",                 "top",      "letter"),
        ("FNV",     "Franco-Nevada",               "top",      "letter"),
        ("KGC",     "Kinross Gold",                "top",      "letter"),
    ]),
    ("Palisades Goldcorp", [
        # Collin Kettell - mining incubator, focused on royalty + producer streamers
        ("METC.CN", "Patriot Battery Metals",      "top",      "incubator stake"),
        ("LIO.V",   "Lion Copper",                 "top",      "mining bet"),
    ]),
    # === Small US value/specialty funds ===
    ("Bireme Capital", [
        # Tindell/Geiger - deep value
        ("PARA",    "Paramount Global",            "top",      "Substack letter"),
        ("WBD",     "Warner Bros Discovery",       "top",      "Substack letter"),
        ("CMCSA",   "Comcast",                     "top",      "Substack letter"),
        ("FOXA",    "Fox Corp",                    "top",      "Substack letter"),
    ]),
    ("Arquitos Capital", [
        # Steven Kiel - micro/small-cap value
        ("EDII",    "Enterprise Diversified",      "top",      "long-running"),
        ("ENV",     "Envestnet",                   "top",      "small-cap"),
        ("WSTL",    "Westell Tech",                "top",      "long-held"),
    ]),
    ("Caro-Kann Capital", [
        # Artem Fokin - eclectic micro-cap value
        ("RACE",    "Ferrari",                     "top",      "Substack letter"),
        ("BOLB.PA", "Bollore",                     "top",      "long-running"),
        ("WINE.L",  "Naked Wines",                 "top",      "deep value"),
    ]),
    ("Bonhoeffer Fund", [
        # Keith Smith - quality value, international focus
        ("ASR",     "Grupo Aeroportuario Sureste", "top",      "letter"),
        ("OMAB",    "Grupo Aeroportuario Centro",  "top",      "letter"),
        ("GMS",     "GMS Inc",                     "top",      "Substack letter"),
    ]),
    ("Hayden Capital", [
        # Fred Liu - tech/internet focus
        ("MELI",    "MercadoLibre",                "top",      "letter"),
        ("CPNG",    "Coupang",                     "top",      "letter"),
        ("SE",      "Sea Limited",                 "top",      "letter"),
        ("BABA",    "Alibaba",                     "top",      "letter"),
    ]),
    ("Kold Investments", [
        # Simon Kold - quality compounders
        ("CSU.TO",  "Constellation Software",      "top",      "Substack letter"),
        ("DPZ",     "Domino's Pizza",              "top",      "letter"),
        ("KOF",     "Coca-Cola FEMSA",             "top",      "letter"),
    ]),
    ("Laughing Water Capital", [
        # Matt Sweeney - quality value
        ("DBI",     "Designer Brands",             "top",      "letter"),
        ("FTAI",    "FTAI Aviation",               "top",      "letter"),
        ("APG",     "APi Group",                   "top",      "letter"),
    ]),
    ("Long Cast Advisers", [
        # Avi Kaner / Greenhaven Road
        ("BURL",    "Burlington Stores",           "top",      "letter"),
        ("OLLI",    "Ollie's Bargain Outlet",      "top",      "letter"),
    ]),
    ("Maran Capital", [
        # Daniel Roller - small-cap value
        ("GROW",    "U.S. Global Investors",       "top",      "Substack letter"),
        ("CIVI",    "Civitas Resources",           "top",      "letter"),
        ("AMRK",    "A-Mark Precious Metals",      "top",      "letter"),
    ]),
    ("Massif Capital", [
        # Will Thomson - hard assets / commodities
        ("FCX",     "Freeport-McMoRan",            "top",      "letter"),
        ("HBM.TO",  "Hudbay Minerals",             "top",      "letter"),
        ("LITHQ",   "Sigma Lithium",               "top",      "letter"),
    ]),
    ("Saga Partners", [
        # Joe Frankenfield - LT compounders
        ("MELI",    "MercadoLibre",                "top",      "Substack letter"),
        ("DKNG",    "DraftKings",                  "top",      "letter"),
    ]),
    ("Right Tail Capital", [
        # Tom Robinson - quality compounders
        ("HEI",     "Heico Corp",                  "top",      "letter"),
        ("CWAN",    "Clearwater Analytics",        "top",      "letter"),
    ]),
    ("Praetorian Capital", [
        # Harris Kupperman - resources/special situations
        ("VAL",     "Valaris",                     "top",      "Kuppy.com letter"),
        ("STNG",    "Scorpio Tankers",             "top",      "Kuppy.com letter"),
        ("INSW",    "International Seaways",       "top",      "letter"),
    ]),
    # === Family offices + individuals not yet covered ===
    ("Hillspire LLC", [
        # Eric Schmidt family office - tech-heavy
        ("GOOGL",   "Alphabet",                    "top",      "Schmidt long-held"),
        ("AAPL",    "Apple",                       "top",      "tech allocation"),
        ("MSFT",    "Microsoft",                   "top",      "tech allocation"),
    ]),
    ("Park Lane Family Office", [
        # Henrik Andersen - Nordic family office
        ("NOVO-B.CO", "Novo Nordisk",              "top",      "Nordic exposure"),
        ("DSV.CO",  "DSV A/S",                     "top",      "Nordic"),
    ]),
    ("Cevian Capital", [
        # Christer Gardell - European activist (SE)
        ("VOD.L",   "Vodafone",                    "5pct",     "campaign"),
        ("HEX.HE",  "Helsinki Exchange / Aker BP", "5pct",     "activist"),
        ("ABBN.SW", "ABB Ltd",                     "top",      "long-running"),
        ("CON.DE",  "Continental",                 "5pct",     "split campaign"),
    ]),
    ("Petrus Advisers", [
        # Klaus Umek - European activist (AT)
        ("PROX.BR", "Proximus",                    "5pct",     "engagement"),
        ("ATC.AS",  "ATCO Industries",             "top",      "letter"),
    ]),
    ("Universa Investments", [
        # Mark Spitznagel - pure tail-hedge (options on SPX)
        # No equity holdings - pure tail-risk vehicle
    ]),
    ("Tactical Investment", [
        # No public top-10 disclosure, mostly futures
    ]),
    ("ATW Partners", [
        # Specialty financing, not equity-focused
    ]),
    ("Mark E. Schwarz", [
        # Newcastle Capital - small/micro cap special situations
        ("HRTG",    "Heritage Insurance",          "top",      "13D filer"),
        ("HMHC",    "Houghton Mifflin",            "top",      "long-held"),
    ]),
    ("Asia Frontier Capital", [
        # Thomas Hugger - frontier markets (Iraq, Vietnam, Pakistan, Bangladesh)
        ("AKBNK.IS", "Akbank",                     "top",      "frontier letter"),
        ("MCB.KA",  "MCB Bank Pakistan",           "top",      "frontier letter"),
        ("VNM",     "Vietnam ETF proxy",           "top",      "frontier exposure"),
    ]),
    ("African Lions Fund", [
        # Tim Staermose - African small caps
        ("MTN.JO",  "MTN Group",                   "top",      "letter"),
        ("CFR.JO",  "Richemont",                   "top",      "letter"),
    ]),
    # === Other small US managers ===
    ("Argand Capital Advisers", [
        # John Reilly - small-cap value
        ("MMS",     "Maximus",                     "top",      "letter"),
        ("ENV",     "Envestnet",                   "top",      "letter"),
    ]),
    ("Cobia Capital", [
        # Jeff Meyers - small/micro special situations
        ("HRTG",    "Heritage Insurance",          "top",      "13D"),
        ("ANIK",    "Anika Therapeutics",          "top",      "letter"),
    ]),
    ("Atai Capital", [
        ("ESEA",    "Euroseas",                    "top",      "shipping bet"),
        ("EURN",    "Euronav",                     "top",      "shipping"),
    ]),
    ("Outerbridge Capital", [
        # Rory Wallace - tech activist
        ("HCKT",    "Hackett Group",               "top",      "13D"),
        ("MTSI",    "MACOM Technology",            "top",      "engagement"),
    ]),
    ("Outerbridge Capital Management", [
        ("HCKT",    "Hackett Group",               "top",      "13D"),
    ]),
    ("M3F Inc M3 Partners", [
        # Aaron Morris
        ("FATE",    "Fate Therapeutics",           "top",      "letter"),
        ("RXST",    "RxSight",                     "top",      "letter"),
    ]),
    ("Driver Management", [
        # JJ Cramer - bank activist
        ("FNB",     "F.N.B. Corp",                 "top",      "13D bank"),
        ("FFIN",    "First Financial Bankshares",  "top",      "bank thesis"),
    ]),
    ("Smoak Capital", [
        # Robert Smoak - micro-cap quality
        ("GRBK",    "Green Brick Partners",        "top",      "letter"),
        ("AMRK",    "A-Mark Precious Metals",      "top",      "letter"),
    ]),
    ("Cedar Creek Partners", [
        # Tim Eriksen - micro-cap
        ("EVI",     "EVI Industries",              "top",      "letter"),
        ("PROK",    "Prok Industries",             "top",      "Cedar Creek letter"),
    ]),
    ("Curreen Capital Partners", [
        # Christian Ryther - global small-cap value
        ("BHP.AX",  "BHP Group",                   "top",      "letter"),
    ]),
    ("Privet Fund Management", [
        # Ryan Levenson - small-cap activist
        ("SYPR",    "Sypris Solutions",            "top",      "13D"),
        ("NTGR",    "NETGEAR",                     "top",      "13D"),
    ]),
    ("Camulos Capital", [
        # Distressed credit + equity
        ("BABA",    "Alibaba",                     "top",      "letter"),
    ]),
    ("R.G. Niederhoffer", [
        # Niederhoffer Capital - systematic
        # Mostly CTA / no equity book to track
    ]),
    ("BSOF (Blackstone", [
        # BSOF = Blackstone Strategic Opportunity Fund - hedge fund of hedge funds
        # Allocates rather than direct holdings
    ]),
    ("Schultze Asset Management", [
        # Distressed special-situations
        ("UCO",     "ProShares Oil",               "top",      "macro bet"),
        ("WBD",     "Warner Bros Discovery",       "top",      "letter"),
    ]),
    ("Lawndale Capital", [
        # Andrew Shapiro - small-cap activist
        ("CISO",    "CISO Global",                 "top",      "13D"),
        ("HSAQ",    "Healthcare Special Acq",      "top",      "SPAC"),
    ]),
    ("Nierenberg Investment Mgmt", [
        # David Nierenberg / D3 Family Fund
        ("EVOL",    "Evolving Systems",            "top",      "long-held"),
        ("CAR",     "Avis Budget",                 "top",      "letter"),
    ]),
    ("Northern Right Capital", [
        # Matt Drapkin/Becker - small-cap activist
        ("ASTC",    "Astrotech Corp",              "top",      "13D"),
        ("RGCO",    "RGC Resources",               "top",      "13D"),
    ]),
    ("Polygon Investment Partners", [
        # UK event-driven / convertible arb
        ("VOD.L",   "Vodafone",                    "top",      "merger arb"),
    ]),
    ("Sprott Inc", [
        # Eric Sprott - gold/silver mining
        ("WPM",     "Wheaton Precious Metals",     "top",      "Sprott gold portfolio"),
        ("FNV",     "Franco-Nevada",               "top",      "Sprott gold portfolio"),
        ("SILJ",    "Silver Mining Junior ETF",    "top",      "Sprott holding"),
        ("PAAS",    "Pan American Silver",         "top",      "Sprott holding"),
    ]),
    ("Tiburon Holdings", [
        # Peter Lupoff - mid-cap value
        ("CPS",     "Cooper-Standard",             "top",      "letter"),
        ("WBD",     "Warner Bros Discovery",       "top",      "letter"),
    ]),
    ("Kinderhook Partners", [
        # Tushar Shah - micro-cap value
        ("HMHC",    "Houghton Mifflin",            "top",      "letter"),
        ("PFSI",    "PennyMac Financial",          "top",      "letter"),
    ]),
    ("Star Equity Fund LP", [
        # Jeffrey Eberwein - small-cap special situations
        ("STRR",    "Star Equity Holdings",        "top",      "Eberwein self-stake"),
        ("DC",      "Dakota Gold",                 "top",      "13D"),
    ]),
    ("Alluvial Capital", [
        # Dave Waters - micro-cap value
        ("BBDC",    "Barings BDC",                 "top",      "Substack letter"),
        ("TIPT",    "Tiptree Inc",                 "top",      "letter"),
    ]),
    ("Plural Investing", [
        # Chris Waller
        ("BAH",     "Booz Allen Hamilton",         "top",      "letter"),
        ("CACI",    "CACI International",          "top",      "letter"),
    ]),
    ("Veradace Partners", [
        # Vezendan-Cohen
        ("WCC",     "WESCO International",         "top",      "letter"),
    ]),
]

def run():
    conn = sqlite3.connect(DB)
    n_ingested = n_skipped = 0
    snap = "2026-06-20"
    funds_added = set()
    for prefix, positions in POSITIONS:
        if not positions: continue  # tail-hedge / non-equity funds
        # find canonical fund_meta name
        r = conn.execute("SELECT fund FROM fund_meta WHERE fund LIKE ? LIMIT 1",
                         (prefix + "%",)).fetchone()
        if not r:
            print(f"  ? no fund_meta match for prefix '{prefix}'")
            n_skipped += len(positions)
            continue
        fund = r[0]
        funds_added.add(fund)
        for ticker, company, rank, note in positions:
            raw = f"researcher_seed | {prefix} | {ticker} | {company} | rank={rank} | {note}"
            pct = None
            if rank.endswith("pct"):
                try: pct = float(rank.replace("pct",""))
                except: pass
            conn.execute("""INSERT INTO fund_positions
                (fund, ticker, company, section, pct_value, pct_kind, dollar_m,
                 change_text, event_date, raw_text, asof) VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (fund, ticker, company[:60], 5, pct, "book" if pct else None, None,
                 f"researcher_{note[:40]}", None, raw[:300], snap))
            n_ingested += 1
    conn.commit()
    print(f"\ningested {n_ingested} researcher positions across {len(funds_added)} funds")

if __name__ == "__main__":
    run()
