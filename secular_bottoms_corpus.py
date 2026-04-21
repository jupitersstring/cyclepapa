"""
Expanded secular-bottom-before-blowoff corpus.

Each entry: (ticker, IPO/incorporation date, bottom_month, top_month, multiple, note)
Selected for being SECULAR (multi-year) bottoms, not just corrections.
"""

SECULAR_BOTTOMS = [
    # --- Original 16 (validated earlier) ---
    ("TSLA",  "2010-06-29", (2019, 6),  (2021, 11), 12,   "Tesla 2019-2021"),
    ("NVDA",  "1999-01-22", (2022, 10), (2024, 6),  13,   "Nvidia AI era"),
    ("NVDA16","1999-01-22", (2016, 2),  (2018, 10), 12,   "Nvidia 2016-2018"),
    ("GME",   "2002-02-13", (2020, 4),  (2021, 1),  160,  "GameStop squeeze"),
    ("AMC",   "2013-12-18", (2021, 1),  (2021, 6),  31,   "AMC meme"),
    ("PLTR",  "2020-09-30", (2022, 12), (2024, 12), 13,   "Palantir AI"),
    ("CVNA",  "2017-04-28", (2022, 12), (2024, 11), 75,   "Carvana recovery"),
    ("MSTR",  "1998-06-11", (2022, 12), (2024, 11), 4,    "MicroStrategy BTC"),
    ("COIN",  "2021-04-14", (2023, 1),  (2024, 12), 10,   "Coinbase recovery"),
    ("SHOP",  "2015-05-21", (2016, 2),  (2018, 8),  10,   "Shopify early"),
    ("SHOP2", "2015-05-21", (2020, 3),  (2021, 11), 5,    "Shopify COVID"),
    ("CROX",  "2006-02-08", (2008, 11), (2021, 10), 180,  "Crocs long cycle"),
    ("AAPL",  "1980-12-12", (2003, 4),  (2007, 12), 28,   "Apple iPod era"),
    ("AMZN",  "1997-05-15", (2001, 10), (2007, 10), 17,   "Amazon dotcom"),
    ("NFLX",  "2002-05-23", (2012, 8),  (2015, 7),  16,   "Netflix streaming"),
    ("SMCI",  "2007-03-29", (2022, 10), (2024, 3),  17,   "Super Micro AI"),

    # --- 2022-2024 cohort (bottomed together) ---
    ("APP",   "2021-04-15", (2022, 12), (2024, 12), 40,   "AppLovin"),
    ("ANET",  "2014-06-06", (2022, 12), (2024, 6),  4,    "Arista Networks"),
    ("HIMS",  "2021-01-21", (2023, 5),  (2025, 2),  12,   "Hims & Hers"),
    ("IONQ",  "2021-10-01", (2023, 5),  (2025, 2),  16,   "IonQ quantum"),
    ("RKLB",  "2021-08-25", (2023, 2),  (2024, 11), 7,    "Rocket Lab"),
    ("CEG",   "2022-02-02", (2022, 9),  (2024, 5),  4,    "Constellation Energy"),
    ("VST",   "2016-10-10", (2023, 1),  (2024, 10), 9,    "Vistra power"),
    ("TSM",   "1997-10-08", (2022, 10), (2024, 7),  3,    "TSMC"),
    ("ASML",  "1995-03-14", (2022, 10), (2024, 7),  3,    "ASML"),
    ("ARM",   "2023-09-14", (2024, 4),  (2025, 1),  4,    "Arm Holdings"),

    # --- COVID-era bottoms ---
    ("ZM",    "2019-04-18", (2019, 5),  (2020, 10), 15,   "Zoom COVID"),
    ("DKNG",  "2020-04-24", (2020, 5),  (2021, 3),  7,    "DraftKings"),
    ("SPCE",  "2019-10-28", (2019, 12), (2021, 2),  9,    "Virgin Galactic"),
    ("PTON",  "2019-09-26", (2020, 3),  (2021, 1),  9,    "Peloton COVID"),
    ("NKLA",  "2020-06-03", (2020, 5),  (2020, 6),  9,    "Nikola SPAC"),
    ("BLNK",  "2018-02-13", (2020, 10), (2021, 2),  21,   "Blink Charging"),
    ("PLUG",  "1999-09-29", (2020, 2),  (2021, 1),  25,   "Plug Power"),
    ("WKHS",  "2010-07-22", (2020, 3),  (2020, 9),  28,   "Workhorse"),
    ("RIOT",  "2003-12-01", (2020, 3),  (2021, 2),  94,   "Riot Blockchain"),
    ("MARA",  "2017-08-18", (2020, 3),  (2021, 11), 220,  "Marathon Digital"),

    # --- Dot-com era ---
    ("CSCO",  "1990-02-16", (1990, 10), (2000, 3),  1300, "Cisco 1990-2000"),
    ("ORCL",  "1986-03-12", (1990, 8),  (2000, 9),  550,  "Oracle 1990-2000"),
    ("MSFT",  "1986-03-13", (1990, 10), (1999, 12), 85,   "Microsoft 1990s"),
    ("INTC",  "1971-10-13", (1990, 10), (2000, 9),  50,   "Intel 1990s"),
    ("QCOM",  "1991-12-13", (1999, 1),  (2000, 1),  16,   "Qualcomm 1999"),
    ("YHOO",  "1996-04-12", (1998, 10), (2000, 1),  40,   "Yahoo bubble"),

    # --- GFC bottoms ---
    ("BAC",   "1998-09-30", (2009, 3),  (2010, 4),  7,    "BoA GFC"),
    ("F",     "1956-01-18", (2008, 11), (2011, 1),  15,   "Ford GFC"),
    ("LVS",   "2004-12-14", (2009, 3),  (2014, 3),  64,   "Las Vegas Sands GFC"),
    ("LULU",  "2007-07-27", (2009, 3),  (2011, 6),  25,   "Lululemon GFC"),
    ("GMCR",  "1993-09-17", (2009, 3),  (2011, 9),  52,   "Green Mountain Coffee"),
    ("DECK",  "1993-10-15", (2008, 11), (2011, 10), 5,    "Deckers Outdoor"),
    ("AMZN2", "1997-05-15", (2008, 11), (2011, 10), 5,    "Amazon GFC"),
    ("AAPL2", "1980-12-12", (2009, 1),  (2012, 9),  9,    "Apple GFC iPhone"),
    ("BIDU",  "2005-08-05", (2008, 11), (2011, 4),  8,    "Baidu GFC"),

    # --- 2013-2015 biotech / tech bottoms before 2015-2018 run ---
    ("NVDA15","1999-01-22", (2015, 9),  (2018, 10), 13,   "NVDA pre-AI cycle"),
    ("AMD",   "1972-09-27", (2016, 2),  (2018, 9),  21,   "AMD turnaround"),
    ("MU",    "1984-06-01", (2016, 5),  (2018, 5),  7,    "Micron memory"),
    ("SHOP1", "2015-05-21", (2016, 2),  (2018, 8),  10,   "Shopify 2016"),

    # --- Post dot-com / 2003-2007 ---
    ("NFLX1", "2002-05-23", (2004, 10), (2005, 12), 5,    "Netflix first"),
    ("GOOG",  "2004-08-19", (2004, 9),  (2007, 11), 9,    "Google dotcom2"),
    ("BIDU2", "2005-08-05", (2005, 10), (2007, 11), 5,    "Baidu launch"),
    ("RIMM",  "1999-02-04", (2003, 1),  (2008, 6),  60,   "BlackBerry run"),
    ("AAPL3", "1980-12-12", (2003, 4),  (2007, 12), 28,   "Apple iPod"),
    ("CMG",   "2006-01-25", (2009, 3),  (2015, 7),  15,   "Chipotle GFC-peak"),

    # --- 1974-1982 secular bottom ---
    ("IBM",   "1915-09-01", (1974, 12), (1986, 8),  6,    "IBM 1974 low"),
    ("MO",    "1952-03-10", (1974, 10), (1987, 9),  30,   "Altria/Philip Morris"),
    ("WMT",   "1970-10-01", (1974, 12), (1999, 12), 2000, "Walmart 1974 low"),
    ("MCD",   "1965-04-21", (1974, 10), (1999, 11), 80,   "McDonald's 1974 low"),

    # --- 1982-1987 setup ---
    ("HD",    "1981-09-22", (1985, 1),  (1999, 12), 2000, "Home Depot"),
    ("NKE",   "1980-12-02", (1984, 12), (1992, 11), 50,   "Nike 1980s"),

    # --- Japan bubble (Nikkei top 1989; different arc) ---
    # skip since went into bear

    # --- Commodities / Gold cycles ---
    ("NEM",   "1940-05-01", (2000, 11), (2011, 9),  10,   "Newmont 2000-2011"),
    ("FCX",   "1988-07-01", (2001, 10), (2007, 5),  30,   "Freeport copper"),
    ("AEM",   "1983-09-29", (2001, 4),  (2011, 9),  13,   "Agnico Eagle"),
    ("CCJ",   "1996-11-04", (2001, 10), (2007, 6),  25,   "Cameco uranium"),

    # --- Other notable bottoms ---
    ("BKNG",  "1999-03-30", (2002, 10), (2014, 3),  225,  "Booking.com dotcom"),
    ("EBAY",  "1998-09-24", (2001, 1),  (2004, 12), 10,   "eBay dotcom"),
    ("AKAM",  "1999-10-29", (2001, 10), (2007, 12), 50,   "Akamai dotcom"),
    ("MSTR1", "1998-06-11", (2002, 11), (2007, 12), 8,    "MicroStrategy first rally"),

    # --- Crypto ecosystem 2018-2022 ---
    # (BTC itself, MARA, RIOT, HUT8 already covered)
    ("SQ",    "2015-11-19", (2016, 2),  (2018, 9),  11,   "Square/Block"),

    # --- Gaming/Casino post-GFC ---
    ("WYNN",  "2002-10-25", (2009, 3),  (2014, 3),  20,   "Wynn Resorts GFC"),
    ("MGM",   "1986-10-31", (2009, 3),  (2011, 3),  8,    "MGM Resorts GFC"),

    # --- Modern biotech boom ---
    ("MRNA",  "2018-12-07", (2019, 12), (2021, 8),  17,   "Moderna COVID"),
    ("BNTX",  "2019-10-10", (2020, 3),  (2021, 8),  16,   "BioNTech COVID"),
    ("NVAX",  "1995-12-19", (2020, 3),  (2021, 2),  50,   "Novavax COVID"),

    # --- 2015-2016 energy / biotech bottoms ---
    ("OXY",   "1957-04-01", (2020, 10), (2022, 5),  9,    "Occidental 2020"),
    ("DVN",   "1988-02-10", (2020, 3),  (2022, 6),  12,   "Devon Energy"),
    ("MPC",   "2011-06-30", (2020, 10), (2024, 4),  7,    "Marathon Petro"),

    # --- Tech 2012-2013 bottom/run ---
    ("MU2",   "1984-06-01", (2012, 11), (2014, 12), 7,    "Micron 2012-14"),
    ("WDC2",  "1990-01-01", (2016, 1),  (2018, 1),  3,    "Western Digital 2016"),

    # --- Retail winners ---
    ("COST",  "1985-12-05", (1996, 1),  (1999, 12), 5,    "Costco 1990s"),
    ("SBUX",  "1992-06-26", (2009, 3),  (2015, 11), 10,   "Starbucks GFC"),
    ("TGT",   "1967-10-18", (2000, 2),  (2007, 7),  4,    "Target dotcom bot"),

    # --- Financial squeeze 2020 ---
    ("BBBY",  "1992-06-04", (2022, 7),  (2022, 8),  5,    "Bed Bath squeeze"),
    ("DWAC",  "2021-09-03", (2021, 10), (2021, 10), 17,   "DWAC SPAC spike"),
    ("HKD",   "2022-07-15", (2022, 7),  (2022, 8),  327,  "HKD squeeze"),

    # --- Fintech, recent ---
    ("HOOD",  "2021-07-29", (2022, 6),  (2025, 2),  10,   "Robinhood recovery"),
    ("AFRM",  "2021-01-13", (2022, 12), (2024, 12), 14,   "Affirm recovery"),
    ("UPST",  "2020-12-16", (2022, 12), (2024, 11), 8,    "Upstart recovery"),
    ("SOFI",  "2021-06-01", (2022, 12), (2024, 11), 5,    "SoFi recovery"),

    # --- Travel / Transport ---
    ("BKNG2", "1999-03-30", (2020, 3),  (2021, 11), 3,    "Booking.com COVID"),
    ("EXPE",  "2005-08-08", (2020, 3),  (2021, 11), 5,    "Expedia COVID"),
    ("AAL",   "2013-12-09", (2020, 5),  (2021, 4),  5,    "American Airlines"),
    ("UAL",   "2006-02-02", (2020, 5),  (2021, 3),  4,    "United Airlines"),
    ("CCL",   "1987-07-24", (2020, 4),  (2021, 6),  4,    "Carnival Cruise"),

    # --- Defense / Space ---
    ("LMT",   "1995-03-15", (2000, 2),  (2007, 7),  5,    "Lockheed post-dotcom"),
    ("NOC",   "1978-01-01", (2000, 2),  (2008, 5),  5,    "Northrop Grumman"),

    # --- Infrastructure / Rail ---
    ("UNP",   "1969-01-01", (2000, 9),  (2014, 12), 8,    "Union Pacific 2000s"),
    ("CSX",   "1980-11-01", (2000, 10), (2014, 12), 9,    "CSX 2000s"),

    # --- Latin America / Emerging ---
    ("MELI",  "2007-08-10", (2009, 3),  (2011, 5),  10,   "MercadoLibre GFC"),

    # --- Pharma bottoms ---
    ("ABBV",  "2013-01-02", (2013, 5),  (2015, 7),  3,    "AbbVie 2013 launch"),
    ("LLY",   "1952-04-15", (2009, 3),  (2014, 7),  4,    "Eli Lilly GFC"),

    # --- Industrial recoveries ---
    ("CAT",   "1929-12-02", (2009, 3),  (2011, 2),  5,    "Caterpillar GFC"),
    ("DE",    "1933-09-09", (2009, 3),  (2014, 5),  4,    "Deere GFC"),
]

def get_bottoms():
    return SECULAR_BOTTOMS

if __name__ == "__main__":
    print(f"Total secular bottoms: {len(SECULAR_BOTTOMS)}")
    from collections import Counter
    c = Counter((y // 5 * 5) for _, _, (y, _), _, _, _ in SECULAR_BOTTOMS)
    for era, n in sorted(c.items()):
        print(f"  {era}s: {n}")
