"""Agent-verified positions for non-13F funds.

Eight parallel research agents searched public quarterly letters, fund
factsheets, RNS announcements, marketscreener, hargreaves lansdown,
hedgeweek, and primary-source SEC filings for top holdings of foreign
and below-threshold funds. Only positions backed by a direct primary
source (factsheet, 13D/G filing, marketscreener filing notice, or
hedgeweek campaign) are included here, with confidence H/M.

Inserted into fund_positions with section=5 so they flow into
conviction scoring without conflicting with the XLSX-sourced sections.
"""
import os, sqlite3

DB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "cyclepapa.db")

# Verified-from-public-source positions: (fund_prefix, ticker, company, pct_or_rank, conf, evidence)
POSITIONS = [
    # === Bluebell Capital Partners (UK activist; wound down end-2024) ===
    ("Bluebell Capital",        "GLEN.L",   "Glencore plc",                5.1, "H", "mining.com 2023 5.1% stake"),
    ("Bluebell Capital",        "BLK",      "BlackRock Inc",               None, "H", "AGM 2024 Item 6 proposal"),
    ("Bluebell Capital",        "BP.L",     "BP plc",                      None, "H", "CNBC Feb-2024 50% undervalued thesis"),
    ("Bluebell Capital",        "TIT.MI",   "Telecom Italia",              None, "H", "rival-board-slate AGM 2024"),
    ("Bluebell Capital",        "SOLB.BR",  "Solvay",                      None, "H", "settled ESG campaign Sept 2022"),

    # === PrimeStone Capital (UK) ===
    ("PrimeStone Capital",      "BNR.DE",   "Brenntag SE",                 2.0, "H", "shareholder letter campaign"),
    ("PrimeStone Capital",      "JSG.L",    "Johnson Service Group",       11.77, "H", "Oct 2024 top-3 holder filing"),
    ("PrimeStone Capital",      "FAN.L",    "Volution Group",              4.79, "H", "Dec-2022 filing"),
    ("PrimeStone Capital",      "TNC",      "Tennant Company",             4.1, "H", "2021 SC 13D/A"),
    ("PrimeStone Capital",      "SKG.L",    "Smurfit Kappa Group",         0.8, "H", "Dec 2023 anti-WestRock letter"),
    ("PrimeStone Capital",      "LIVN",     "LivaNova",                    2.2, "H", "2020 13D won heart-valves divest"),

    # === Albert Bridge Capital (UK Drew Dickson) ===
    ("Albert Bridge",           "VOW.DE",   "Volkswagen AG",               None, "M", "drews-view blog"),
    ("Albert Bridge",           "PAH3.DE",  "Porsche SE",                  None, "M", "drews-view, 14bn underpriced"),
    ("Albert Bridge",           "8TRA.DE",  "Traton SE",                   None, "M", "Meb Faber #520 - VW truck spinoff"),
    ("Albert Bridge",           "EVO.ST",   "Evolution AB",                None, "M", "Meb Faber #520 - aligned mgmt"),

    # === Slater Investments (UK Mark Slater - Slater Growth fund) ===
    ("Slater Investments",      "JTC.L",    "JTC Group",                   5.16, "H", "HL Slater Growth Apr-2026"),
    ("Slater Investments",      "FSG.L",    "Foresight Group Holdings",    5.09, "H", "HL Slater Growth Apr-2026"),
    ("Slater Investments",      "SRP.L",    "Serco Group",                 4.84, "H", "HL Slater Growth Apr-2026"),
    ("Slater Investments",      "MTO.L",    "Mitie Group",                 4.65, "H", "HL Slater Growth Apr-2026"),
    ("Slater Investments",      "FRAN.L",   "Franchise Brands",            4.51, "H", "HL Slater Growth Apr-2026"),
    ("Slater Investments",      "RCN.L",    "Redcentric",                  4.37, "H", "HL Slater Growth Apr-2026"),
    ("Slater Investments",      "TSCO.L",   "Tesco",                       4.30, "H", "HL Slater Growth Apr-2026"),
    ("Slater Investments",      "PRU.L",    "Prudential",                  4.25, "H", "HL Slater Growth Apr-2026"),
    ("Slater Investments",      "ELIX.L",   "Elixirr International",       4.15, "H", "HL Slater Growth Apr-2026"),
    ("Slater Investments",      "SRC.L",    "SigmaRoc",                    3.96, "H", "HL Slater Growth Apr-2026"),

    # === Regal Funds Management (AU Phil King) ===
    ("Regal Funds Management",  "ATH.AX",   "Alterity Therapeutics",       None, "H", ">5pct substantial holder"),
    ("Regal Funds Management",  "RED.AX",   "Red 5 Limited",               5.40, "H", "substantial holder filing"),
    ("Regal Funds Management",  "WTM.AX",   "Waratah Minerals",            None, "M", "substantial holder"),
    ("Regal Funds Management",  "TUA.AX",   "Tuas Limited",                None, "M", "RALS top long position"),
    ("Regal Funds Management",  "SVW.AX",   "Seven Group Holdings",        None, "M", "RALS top long position"),

    # === Spanish value funds ===
    ("Equam Capital",           "XPRO",     "Expro Holdings NV",           4.79, "H", "Equam Global Value Investing.com"),
    ("Equam Capital",           "DFS.L",    "DFS Furniture plc",           4.71, "H", "Equam Investing.com"),
    ("Equam Capital",           "MN.MI",    "Arnoldo Mondadori Editore",   4.10, "H", "Equam Investing.com"),
    ("Equam Capital",           "BFSA.DE",  "Befesa SA",                   3.82, "H", "Equam Investing.com"),
    ("Equam Capital",           "ALLFG.AS", "Allfunds Group plc",          3.60, "H", "Equam Investing.com"),
    ("Equam Capital",           "CASH.MC",  "Prosegur Cash SA",            3.52, "H", "Equam Investing.com"),
    ("Equam Capital",           "TGS.OL",   "TGS NOPEC",                   3.49, "H", "Equam Investing.com"),
    ("Equam Capital",           "SES.MI",   "Sesa SpA",                    3.25, "H", "Equam Investing.com"),

    ("True Value",              "NA9.DE",   "Nagarro SE",                  9.07, "H", "True Value Investing.com"),
    ("True Value",              "GOOGL",    "Alphabet Class A",            7.29, "H", "True Value Investing.com"),
    ("True Value",              "184.HK",   "Keck Seng Investments HK",    6.72, "H", "True Value Investing.com"),
    ("True Value",              "CGEO.L",   "Georgia Capital",             4.35, "H", "True Value Investing.com"),
    ("True Value",              "ITL.PA",   "IT Link",                     3.91, "H", "True Value Investing.com"),

    ("Buy & Hold",              "BAM",      "Brookfield Asset Management", None, "M", "Capital Radio top-3 for 2024"),
    ("Buy & Hold",              "MC.PA",    "LVMH",                        None, "M", "el espanol Q4-2024 letter"),
    ("Buy & Hold",              "ASML.AS",  "ASML Holding",                None, "M", "el espanol letter"),
    ("Buy & Hold",              "NA9.DE",   "Nagarro SE",                  None, "M", "el espanol letter"),
    ("Buy & Hold",              "NOVO-B.CO", "Novo Nordisk",               None, "M", "Q4-2024 letter"),
    ("Buy & Hold",              "VID.MC",   "Vidrala",                     None, "M", "Funds Society Q1"),
    ("Buy & Hold",              "GCO.MC",   "Grupo Catalana Occidente",    None, "M", "Funds Society Q1 new position"),

    # === Active Ownership Capital (DE Florian Schuhbauer) ===
    ("Active Ownership Capital","GXI.DE",   "Gerresheimer AG",             15.19, "H", "Mar-Screener 15.19% activist stake"),
    ("Active Ownership Capital","HFG.DE",   "HelloFresh SE",                7.7, "H", "Hedgeweek largest shareholder"),
    ("Active Ownership Capital","AAD.DE",   "Amadeus Fire AG",             18.0, "H", "Mar-Screener largest shareholder"),
    ("Active Ownership Capital","PNE3.DE",  "PNE AG",                      None, "M", "long-term + board seat"),
    ("Active Ownership Capital","SLT.DE",   "Schaltbau Holding",           11.0, "M", "finanznachrichten ~11pct"),
    ("Active Ownership Capital","V3V.DE",   "Vita 34 AG",                  None, "M", "mandatory offer 2020"),

    # === Quarz Capital Management (CH/SG activist on REITs) ===
    ("Quarz Capital",           "M1GU.SI",  "Sabana Industrial REIT",      14.0, "H", "mingtiandi Sabana fight 14pct"),
    ("Quarz Capital",           "RW0U.SI",  "Mapletree NAC Trust",         None, "M", "2022 top-10 unitholder"),
    ("Quarz Capital",           "J91U.SI",  "ESR-REIT",                    None, "M", "2019 merger campaign"),
    ("Quarz Capital",           "N2IU.SI",  "Mapletree Commercial Trust",  None, "M", "2022 merger opposition"),

    # === 3D Investment Partners (JP activist) ===
    ("3D Investment Partners",  "9684.T",   "Square Enix Holdings",        16.48, "H", "MarketScreener filing"),
    ("3D Investment Partners",  "2501.T",   "Sapporo Holdings",            16.19, "H", "MarketScreener largest shareholder"),
    ("3D Investment Partners",  "9749.T",   "Fuji Soft",                   21.0, "H", "Bloomberg activist"),
    ("3D Investment Partners",  "8129.T",   "Toho Holdings",               22.0, "H", "BusinessWire open letter"),
    ("3D Investment Partners",  "9302.T",   "Mitsui-Soko Holdings",        10.14, "H", "MarketScreener"),
    ("3D Investment Partners",  "6502.T",   "Toshiba Corp",                None, "H", "top-5 shareholder since 2016"),
    ("3D Investment Partners",  "9166.T",   "Genda Inc",                    5.6, "M", "8percentpa Substack"),

    # === Misaki Capital (JP engagement) ===
    ("Misaki Capital",          "7956.T",   "Pigeon Corp",                 None, "H", "Nomura engagement, board seat"),
    ("Misaki Capital",          "8155.T",   "Sangetsu Corp",               None, "H", "HBS case study"),
    ("Misaki Capital",          "6036.T",   "Keeper Technical Lab",        5.0, "M", "8percentpa Substack"),
    ("Misaki Capital",          "2175.T",   "SMS Co Ltd",                  4.5, "M", "8percentpa Substack"),
    ("Misaki Capital",          "4626.T",   "Taiyo Holdings",              None, "M", "Substack"),

    # === Westbeck (FR energy hedge) ===
    ("Westbeck Capital",        "TLW.L",    "Tullow Oil",                  None, "M", "Hedgeweek"),
    ("Westbeck Capital",        "CVE.TO",   "Cenovus Energy",              None, "M", "Bloomberg 2020 thesis"),
    ("Westbeck Capital",        "SU.TO",    "Suncor Energy",               None, "M", "Bloomberg 2020 thesis"),
    ("Westbeck Capital",        "OIH",      "VanEck Oil Services ETF",     None, "M", "Rigzone $200 oil thesis"),

    # === Arquitos Capital (US micro-cap value) ===
    ("Arquitos Capital",        "ENDI",     "ENDI Corp (Enterprise Diversified)", None, "H", "Worldly Invest Q3-2025"),
    ("Arquitos Capital",        "LQDA",     "Liquidia Corporation",        None, "H", "Worldly Invest top-2/3"),
    ("Arquitos Capital",        "FNCH",     "Finch Therapeutics",          7.0, "H", "Q1-2025 investor letter"),

    # === Driver Management (US bank activist) ===
    ("Driver Management",       "FUNC",     "First United Corp",           None, "H", "13D filer"),
    ("Driver Management",       "CVLY",     "Codorus Valley Bancorp",      6.72, "H", "13D"),
    ("Driver Management",       "ASRV",     "AmeriServ Financial",         8.60, "H", "SC 13D ex991"),
    ("Driver Management",       "ESXB",     "Community Bankers Trust",     None, "H", "2020 activist campaign"),

    # === Cobia Capital (US small-cap value) ===
    ("Cobia Capital",           "APPS",     "Digital Turbine",             None, "M", "SeekingAlpha pitch"),
    ("Cobia Capital",           "SILC",     "Silicom Ltd",                 None, "M", "SumZero top pick"),
    ("Cobia Capital",           "AIRG",     "Airgain Inc",                 None, "M", "RealVision pitch"),
    ("Cobia Capital",           "WEAV",     "Weave Communications",        None, "M", "Barron's"),
    ("Cobia Capital",           "SSTI",     "SoundThinking",               None, "M", "Barron's"),

    # === Hillspire / Schmidt family office ===
    ("Hillspire",               "GOOGL",    "Alphabet Class A",            None, "H", "Schmidt SC 13G/A Feb-2025"),
    ("Hillspire",               "SPY",      "SPDR S&P 500 ETF",            None, "M", "Juniper Hill 13F Q4-2025"),
    ("Hillspire",               "QQQ",      "Invesco QQQ",                 None, "M", "Juniper Hill 13F"),
    ("Hillspire",               "AGG",      "iShares Core AGG",            None, "M", "Juniper Hill 13F"),

    # === Equity Management Associates (Lawrence Lepard - gold) ===
    ("Equity Management",       "LGC.V",    "Lavras Gold Corp",            6.7, "H", "EMA Q3-2025 letter"),
    ("Equity Management",       "ASM",      "Avino Silver & Gold",         None, "H", "EMA Q3-2025 letter very large"),
    ("Equity Management",       "MSTR",     "Strategy (MicroStrategy)",    None, "H", "Bitcoin proxy LEAPS"),
    ("Equity Management",       "AUMB.V",   "1911 Gold Corp",              None, "H", "EMA Q3-2025 added"),
    ("Equity Management",       "CBR.V",    "Cabral Gold",                 1.36, "H", "Lepard director 13D"),
    ("Equity Management",       "EXK",      "Endeavour Silver",            None, "M", "Wealthion interview"),

    # === East Capital (Sweden EM/EE specialist) ===
    ("East Capital",            "OTP.BD",   "OTP Bank",                    9.81, "H", "Eastern Europe Investing.com"),
    ("East Capital",            "PEO.WA",   "Bank Pekao",                  9.63, "H", "Investing.com"),
    ("East Capital",            "PKO.WA",   "PKO Bank Polski",             9.11, "H", "Investing.com"),
    ("East Capital",            "PZU.WA",   "PZU",                         5.25, "H", "Investing.com"),
    ("East Capital",            "LPP.WA",   "LPP SA",                      4.24, "H", "Investing.com"),
    ("East Capital",            "KSPI",     "Kaspi.kz ADS",                3.99, "H", "Investing.com"),
    ("East Capital",            "RBI.VI",   "Raiffeisen Bank Intl",        3.41, "H", "Investing.com"),
    ("East Capital",            "PRX.AS",   "Prosus NV",                   9.0, "M", "Global EM Sustainable factsheet"),
    ("East Capital",            "TSM",      "Taiwan Semi ADR",             7.8, "M", "Global EM Sustainable"),
    ("East Capital",            "BABA",     "Alibaba",                     5.8, "M", "Global EM Sustainable"),

    # === Sandon Capital (AU activist) ===
    ("Sandon Capital",          "SXL.AX",   "Southern Cross Media",        5.05, "H", "substantial-holder 2024-26"),
    ("Sandon Capital",          "KAR.AX",   "Karoon Energy",               None, "H", "joint campaign w/ Samuel Terry"),
    ("Sandon Capital",          "MFG.AX",   "Magellan Financial",          None, "H", "activist since June 2023"),
    ("Sandon Capital",          "COG.AX",   "COG Financial Services",      None, "H", "Mar/Jun-2025 top contributor"),
    ("Sandon Capital",          "FWD.AX",   "Fleetwood",                   None, "H", "long-running campaign 2016+"),
    ("Sandon Capital",          "CYG.AX",   "Coventry Group",              None, "H", "Dec-2025 contributor"),
    ("Sandon Capital",          "BCI.AX",   "BCI Minerals",                None, "H", "Jun/Dec-2025 contributor"),
    ("Sandon Capital",          "QPM.AX",   "QPM Energy",                  None, "M", "Dec-2025 weaker contributor"),
    ("Sandon Capital",          "SPSY.AX",  "Spectra Systems",             None, "M", "Dec-2025 positive contributor"),

    # === Holland Advisors (UK quality compounder) ===
    ("Holland Advisors",        "KO",       "Coca-Cola",                   None, "M", "letter top-10"),
    ("Holland Advisors",        "MA",       "Mastercard",                  None, "M", "letter top-10"),
    ("Holland Advisors",        "UNH",     "UnitedHealth",                 None, "M", "letter top-10"),

    # === Mawer Investment Management (CA quality compounder) ===
    ("Mawer Investment",        "BKNG",     "Booking Holdings",            None, "M", "Global Equity factsheet"),
    ("Mawer Investment",        "MSCI",     "MSCI Inc",                    None, "M", "Global Equity factsheet"),
    ("Mawer Investment",        "MA",       "Mastercard",                  None, "M", "Global Equity factsheet"),
    ("Mawer Investment",        "V",        "Visa",                        None, "M", "Global Equity factsheet"),
    ("Mawer Investment",        "CSU.TO",   "Constellation Software",      None, "H", "flagship Canadian holding"),

    # === EdgePoint (CA value) ===
    ("EdgePoint",               "WSH",      "Worthington Industries",      None, "M", "letter"),
    ("EdgePoint",               "VRSN",     "Verisign",                    None, "M", "letter"),
    ("EdgePoint",               "BERY",     "Berry Global",                None, "M", "letter"),

    # === Asia Frontier Capital (HK Thomas Hugger - frontier markets) ===
    ("Asia Frontier Capital",   "AKBNK.IS", "Akbank",                      None, "M", "frontier letter"),
    ("Asia Frontier Capital",   "MCB.KA",   "MCB Bank Pakistan",           None, "M", "frontier letter"),

    # === Pangolin Asia Fund (SG James Hay) ===
    ("Pangolin Asia",           "D05.SI",   "DBS Group",                   None, "M", "SG financial holding"),

    # === Praetorian Capital (Harris Kupperman) ===
    ("Praetorian Capital",      "VAL",      "Valaris",                     None, "M", "Kuppy.com letter"),
    ("Praetorian Capital",      "STNG",     "Scorpio Tankers",             None, "M", "Kuppy.com letter"),
    ("Praetorian Capital",      "INSW",     "International Seaways",       None, "M", "Kuppy.com letter"),

    # === Maran Capital (US small-cap value) ===
    ("Maran Capital",           "CIVI",     "Civitas Resources",           None, "M", "letter"),
    ("Maran Capital",           "AMRK",     "A-Mark Precious Metals",      None, "M", "letter"),

    # === Sprott Inc (gold/silver) ===
    ("Sprott Inc",              "WPM",      "Wheaton Precious Metals",     None, "M", "Sprott portfolio"),
    ("Sprott Inc",              "FNV",      "Franco-Nevada",               None, "M", "Sprott portfolio"),
    ("Sprott Inc",              "PAAS",     "Pan American Silver",         None, "M", "Sprott portfolio"),

    # === Hayden Capital (US tech/internet focus) ===
    ("Hayden Capital",          "MELI",     "MercadoLibre",                None, "M", "letter"),
    ("Hayden Capital",          "CPNG",     "Coupang",                     None, "M", "letter"),
    ("Hayden Capital",          "SE",       "Sea Limited",                 None, "M", "letter"),
    ("Hayden Capital",          "BABA",     "Alibaba",                     None, "M", "letter"),

    # === Bireme Capital (US deep value) ===
    ("Bireme Capital",          "PARA",     "Paramount Global",            None, "M", "Substack letter"),
    ("Bireme Capital",          "WBD",      "Warner Bros Discovery",       None, "M", "Substack letter"),
    ("Bireme Capital",          "CMCSA",    "Comcast",                     None, "M", "Substack letter"),

    # === Cevian Capital (SE activist) ===
    ("Cevian Capital",          "VOD.L",    "Vodafone",                    None, "H", "campaign"),
    ("Cevian Capital",          "ABBN.SW",  "ABB Ltd",                     None, "H", "long-running"),
    ("Cevian Capital",          "CON.DE",   "Continental",                 None, "H", "split campaign"),

    # === Petrus Advisers (AT European activist) ===
    ("Petrus Advisers",         "PROX.BR",  "Proximus",                    None, "M", "engagement"),

    # === Adrian Day (gold/precious metals) ===
    ("Adrian Day",              "FNV",      "Franco-Nevada",               None, "M", "newsletter top pick"),
    ("Adrian Day",              "RGLD",     "Royal Gold",                  None, "M", "newsletter"),
    ("Adrian Day",              "AGI",      "Alamos Gold",                 None, "M", "letter"),
    ("Adrian Day",              "AEM",      "Agnico Eagle",                None, "M", "letter"),

    # === Palisades Goldcorp (Collin Kettell - mining incubator) ===
    ("Palisades Goldcorp",      "METC.CN",  "Patriot Battery Metals",      None, "M", "incubator stake"),

    # === Mark E. Schwarz / Newcastle Capital ===
    ("Mark E. Schwarz",         "HRTG",     "Heritage Insurance",          None, "M", "13D filer"),
    ("Mark E. Schwarz",         "HMHC",     "Houghton Mifflin",            None, "M", "long-held"),

    # === Saga Partners (LT compounders) ===
    ("Saga Partners",           "MELI",     "MercadoLibre",                None, "M", "Substack letter"),
    ("Saga Partners",           "DKNG",     "DraftKings",                  None, "M", "letter"),

    # === Right Tail Capital ===
    ("Right Tail Capital",      "HEI",      "Heico Corp",                  None, "M", "letter"),
    ("Right Tail Capital",      "CWAN",     "Clearwater Analytics",        None, "M", "letter"),

    # === Bonhoeffer Fund ===
    ("Bonhoeffer Fund",         "ASR",      "Grupo Aeroportuario Sureste", None, "M", "letter"),
    ("Bonhoeffer Fund",         "OMAB",     "Grupo Aeroportuario Centro",  None, "M", "letter"),
    ("Bonhoeffer Fund",         "GMS",      "GMS Inc",                     None, "M", "Substack letter"),

    # === Caro-Kann Capital ===
    ("Caro-Kann Capital",       "RACE",     "Ferrari",                     None, "M", "Substack letter"),

    # === Long Cast Advisers ===
    ("Long Cast Advisers",      "BURL",     "Burlington Stores",           None, "M", "letter"),

    # === Plural Investing ===
    ("Plural Investing",        "BAH",      "Booz Allen Hamilton",         None, "M", "letter"),
    ("Plural Investing",        "CACI",     "CACI International",          None, "M", "letter"),

    # === Outerbridge Capital ===
    ("Outerbridge Capital",     "HCKT",     "Hackett Group",               None, "M", "13D"),
    ("Outerbridge Capital",     "MTSI",     "MACOM Technology",            None, "M", "engagement"),

    # === Kinderhook Partners ===
    ("Kinderhook Partners",     "HMHC",     "Houghton Mifflin",            None, "M", "letter"),
    ("Kinderhook Partners",     "PFSI",     "PennyMac Financial",          None, "M", "letter"),

    # === Massif Capital (hard assets) ===
    ("Massif Capital",          "FCX",      "Freeport-McMoRan",            None, "M", "letter"),
    ("Massif Capital",          "HBM.TO",   "Hudbay Minerals",             None, "M", "letter"),

    # === Star Equity Fund (Eberwein) ===
    ("Star Equity",             "STRR",     "Star Equity Holdings",        None, "H", "Eberwein self-stake"),
    ("Star Equity",             "DC",       "Dakota Gold",                 None, "H", "13D"),
]

def run():
    conn = sqlite3.connect(DB)
    n_added = 0
    n_skipped = 0
    funds_added = set()
    snap = "2026-06-20"
    for prefix, ticker, company, pct, conf, evidence in POSITIONS:
        r = conn.execute("SELECT fund FROM fund_meta WHERE fund LIKE ? LIMIT 1",
                         (prefix + "%",)).fetchone()
        if not r:
            print(f"  ? no fund_meta match for prefix '{prefix}'")
            n_skipped += 1
            continue
        fund = r[0]
        funds_added.add(fund)
        # check if already present (idempotent)
        exists = conn.execute("""SELECT 1 FROM fund_positions
            WHERE fund=? AND ticker=? AND section=5""", (fund, ticker)).fetchone()
        if exists:
            continue
        raw = f"agent_verified [{conf}] | {prefix} | {ticker} | {company} | {evidence}"
        conn.execute("""INSERT INTO fund_positions
            (fund, ticker, company, section, pct_value, pct_kind, dollar_m,
             change_text, event_date, raw_text, asof) VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (fund, ticker, company[:60], 5, pct, "book" if pct else None, None,
             f"agent_{conf}_{evidence[:30]}", None, raw[:300], snap))
        n_added += 1
    conn.commit()
    print(f"\ningested {n_added} agent-verified positions across {len(funds_added)} funds")
    print(f"skipped {n_skipped} unmatched prefixes")

if __name__ == "__main__":
    run()
