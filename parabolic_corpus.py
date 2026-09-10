"""
Expanded PARABOLIC / MEME bottom corpus.

Definition: bottoms leading to ≥3× return within ≤24 months (Qullamaggie-style
episodic breakouts + meme-squeeze parabolas). Tagged by speed (fast/med/slow)
and magnitude class.

Each entry: (ticker, IPO/listing_date, bottom_ym, top_ym, multiple, speed_class, note)

Speed classes:
  FAST  = <6 months from bottom to peak (squeezes, parabolic short-fuse)
  MED   = 6-18 months (momentum runs, Qullamaggie-style episodic)
  SLOW  = 18+ months (secular multi-year bulls)
"""

PARABOLIC_BOTTOMS = [
    # ============================================================
    # FAST (<6mo) — SQUEEZES AND PARABOLIC SHORT-FUSE
    # ============================================================
    ("GME",    "2002-02-13", (2021, 1),  (2021, 1),  5,   "FAST", "GME Jan 2021 from $40 to $483"),
    ("AMC",    "2013-12-18", (2021, 4),  (2021, 6),  17,  "FAST", "AMC Apr-Jun 2021"),
    ("BBBY",   "1992-06-04", (2022, 7),  (2022, 8),  5,   "FAST", "Bed Bath Aug 2022 squeeze"),
    ("HKD",    "2022-07-15", (2022, 7),  (2022, 8),  327, "FAST", "AMTD Digital 300x squeeze"),
    ("DWAC",   "2021-09-03", (2021, 10), (2021, 10), 17,  "FAST", "DWAC Trump SPAC spike"),
    ("TLRY",   "2018-07-19", (2018, 7),  (2018, 9),  18,  "FAST", "Tilray 18x in 8 weeks"),
    ("IRNT",   "2017-07-14", (2021, 9),  (2021, 10), 5,   "FAST", "IronNet SPAC squeeze"),
    ("OPAD",   "2021-09-02", (2021, 10), (2021, 11), 4,   "FAST", "Offerpad SPAC"),
    ("CLOV",   "2021-01-08", (2021, 6),  (2021, 6),  3,   "FAST", "Clover meme Jun 2021"),
    ("ATER",   "1988-12-28", (2021, 7),  (2021, 9),  10,  "FAST", "Aterian 2021 squeeze"),
    ("MMAT",   "2021-06-30", (2021, 8),  (2021, 10), 5,   "FAST", "Meta Materials 2021"),
    ("KOSS",   "1985-01-02", (2021, 1),  (2021, 1),  25,  "FAST", "Koss Jan 2021 meme"),
    ("EXPR",   "2010-05-12", (2021, 1),  (2021, 1),  8,   "FAST", "Express Jan 2021 meme"),
    ("NAKD",   "2013-07-15", (2021, 1),  (2021, 1),  12,  "FAST", "Naked Brand Jan 2021"),
    ("SNDL",   "2019-08-01", (2021, 1),  (2021, 2),  8,   "FAST", "Sundial Growers"),
    ("SUNW",   "2010-05-06", (2020, 12), (2021, 2),  22,  "FAST", "Sunworks solar spike"),
    ("MULN",   "2021-11-04", (2022, 2),  (2022, 3),  9,   "FAST", "Mullen Auto"),
    ("ACRS",   "2016-10-06", (2023, 8),  (2023, 10), 3,   "FAST", "Aclaris Therapeutics"),
    ("FFIE",   "2021-07-22", (2024, 5),  (2024, 6),  40,  "FAST", "Faraday Future May 2024"),
    ("DJT",    "2024-03-26", (2024, 3),  (2024, 3),  3,   "FAST", "Trump Media peak at IPO"),
    ("GME2",   "2002-02-13", (2024, 5),  (2024, 5),  4,   "FAST", "GME Roaring Kitty return"),
    ("SOS",    "2017-08-09", (2021, 1),  (2021, 3),  10,  "FAST", "SOS Limited"),
    ("CFVI",   "2020-11-23", (2021, 10), (2021, 11), 11,  "FAST", "CF Acquisition Rumble SPAC"),

    # ============================================================
    # MED (6-18mo) — QULLAMAGGIE-STYLE MOMENTUM RUNS
    # ============================================================
    ("PLUG",   "1999-09-29", (2020, 2),  (2021, 1),  25,  "MED",  "Plug Power 25x in 11mo"),
    ("WKHS",   "2010-07-22", (2020, 3),  (2021, 2),  28,  "MED",  "Workhorse 28x"),
    ("BLNK",   "2018-02-13", (2020, 10), (2021, 2),  21,  "MED",  "Blink Charging"),
    ("MARA",   "2017-08-18", (2020, 10), (2021, 11), 70,  "MED",  "Marathon Digital 70x"),
    ("RIOT",   "2003-12-01", (2020, 9),  (2021, 2),  20,  "MED",  "Riot Blockchain leg"),
    ("FUBO",   "2020-10-08", (2020, 10), (2020, 12), 8,   "MED",  "fuboTV"),
    ("SPCE",   "2019-10-28", (2019, 12), (2021, 2),  9,   "MED",  "Virgin Galactic"),
    ("PTON",   "2019-09-26", (2020, 3),  (2021, 1),  9,   "MED",  "Peloton COVID"),
    ("ZM",     "2019-04-18", (2019, 5),  (2020, 10), 15,  "MED",  "Zoom COVID"),
    ("DKNG",   "2020-04-24", (2020, 5),  (2021, 3),  7,   "MED",  "DraftKings"),
    ("SE",     "2017-10-20", (2020, 3),  (2020, 10), 6,   "MED",  "Sea Limited phase 1"),
    ("CCIV",   "2020-07-31", (2020, 9),  (2021, 2),  7,   "MED",  "Churchill CCIV/Lucid"),
    ("QS",     "2020-11-25", (2020, 11), (2020, 12), 8,   "MED",  "QuantumScape"),
    ("NKLA",   "2020-06-03", (2020, 5),  (2020, 6),  9,   "MED",  "Nikola SPAC peak"),
    ("RIDE",   "2020-10-23", (2020, 11), (2021, 1),  4,   "MED",  "Lordstown"),
    ("GOEV",   "2020-08-18", (2020, 11), (2021, 2),  3,   "MED",  "Canoo"),
    ("HYLN",   "2020-10-01", (2020, 9),  (2020, 9),  4,   "MED",  "Hyliion SPAC"),
    ("UPST",   "2020-12-16", (2021, 1),  (2021, 10), 12,  "MED",  "Upstart 12x"),
    ("AFRM",   "2021-01-13", (2022, 12), (2024, 12), 14,  "MED",  "Affirm recovery"),
    ("HOOD",   "2021-07-29", (2022, 6),  (2025, 2),  10,  "MED",  "Robinhood recovery"),
    ("SOFI",   "2021-06-01", (2022, 12), (2024, 11), 5,   "MED",  "SoFi recovery"),
    ("CRWD",   "2019-06-12", (2019, 8),  (2021, 11), 4,   "MED",  "CrowdStrike 4x"),
    ("SNOW",   "2020-09-16", (2020, 9),  (2020, 12), 3,   "MED",  "Snowflake post-IPO"),
    ("DDOG",   "2019-09-19", (2020, 3),  (2021, 11), 8,   "MED",  "Datadog 8x"),
    ("NET",    "2019-09-13", (2020, 3),  (2021, 11), 11,  "MED",  "Cloudflare 11x"),
    ("FSLY",   "2019-05-17", (2019, 8),  (2020, 10), 13,  "MED",  "Fastly 13x"),
    ("DOCU",   "2018-04-27", (2020, 3),  (2021, 9),  5,   "MED",  "DocuSign COVID"),
    ("TWLO",   "2016-06-23", (2020, 3),  (2021, 2),  4,   "MED",  "Twilio COVID"),

    # 2023-2025 AI/meme cohort
    ("NVDA",   "1999-01-22", (2022, 10), (2024, 6),  13,  "MED",  "Nvidia AI rally"),
    ("SMCI",   "2007-03-29", (2022, 10), (2024, 3),  17,  "MED",  "Super Micro 17x"),
    ("APP",    "2021-04-15", (2022, 12), (2024, 12), 40,  "MED",  "AppLovin 40x"),
    ("PLTR",   "2020-09-30", (2022, 12), (2024, 12), 13,  "MED",  "Palantir AI"),
    ("MSTR",   "1998-06-11", (2022, 12), (2024, 11), 4,   "MED",  "MicroStrategy BTC"),
    ("COIN",   "2021-04-14", (2023, 1),  (2024, 12), 10,  "MED",  "Coinbase recovery"),
    ("HIMS",   "2021-01-21", (2023, 5),  (2025, 2),  12,  "MED",  "Hims & Hers 12x"),
    ("IONQ",   "2021-10-01", (2023, 5),  (2025, 1),  16,  "MED",  "IonQ quantum"),
    ("RKLB",   "2021-08-25", (2023, 2),  (2024, 11), 7,   "MED",  "Rocket Lab"),
    ("RGTI",   "2022-03-02", (2022, 12), (2025, 1),  30,  "MED",  "Rigetti quantum"),
    ("QBTS",   "2022-08-08", (2022, 12), (2025, 1),  20,  "MED",  "D-Wave quantum"),
    ("NNE",    "2024-05-01", (2024, 5),  (2024, 12), 6,   "MED",  "Nano Nuclear"),
    ("SOUN",   "2022-04-28", (2023, 5),  (2024, 3),  15,  "MED",  "SoundHound AI"),
    ("VST",    "2016-10-10", (2023, 1),  (2024, 10), 9,   "MED",  "Vistra power/AI"),
    ("CEG",    "2022-02-02", (2022, 9),  (2024, 5),  4,   "MED",  "Constellation Energy"),
    ("TLN",    "2023-05-22", (2023, 10), (2024, 8),  3,   "MED",  "Talen Energy"),
    ("SMR",    "2022-05-03", (2023, 8),  (2024, 12), 15,  "MED",  "NuScale Power"),
    ("OKLO",   "2024-05-10", (2024, 9),  (2025, 1),  4,   "MED",  "Oklo nuclear"),
    ("GEV",    "2024-04-02", (2024, 4),  (2024, 10), 2.5, "MED",  "GE Vernova"),
    ("MRNA",   "2018-12-07", (2019, 12), (2021, 8),  17,  "MED",  "Moderna COVID"),
    ("BNTX",   "2019-10-10", (2020, 3),  (2021, 8),  16,  "MED",  "BioNTech"),
    ("NVAX",   "1995-12-19", (2020, 3),  (2021, 2),  50,  "MED",  "Novavax COVID"),
    ("SAVA",   "2017-11-21", (2020, 4),  (2021, 7),  30,  "MED",  "Cassava Sciences"),
    ("VKTX",   "2015-09-29", (2023, 10), (2024, 3),  10,  "MED",  "Viking Therapeutics"),
    ("CELH",   "2006-07-18", (2020, 3),  (2022, 3),  100, "MED",  "Celsius Holdings 100x"),
    ("DRCT",   "2022-02-15", (2023, 11), (2024, 3),  15,  "MED",  "Direct Digital Holdings"),
    ("SEZL",   "2023-06-01", (2024, 3),  (2024, 12), 30,  "MED",  "Sezzle 30x"),
    ("CVNA",   "2017-04-28", (2022, 12), (2024, 11), 75,  "MED",  "Carvana 75x"),
    ("CLSK",   "1987-01-01", (2020, 9),  (2021, 4),  28,  "MED",  "CleanSpark"),
    ("HUT",    "2018-03-09", (2020, 3),  (2021, 2),  30,  "MED",  "Hut 8 Mining"),
    ("CAN",    "2019-11-21", (2020, 11), (2021, 4),  10,  "MED",  "Canaan miner"),
    ("EBON",   "2020-06-26", (2020, 10), (2021, 2),  8,   "MED",  "Ebang miner"),
    ("SOS",    "2017-08-09", (2021, 1),  (2021, 3),  10,  "MED",  "SOS Limited"),
    ("LK",     "2019-05-17", (2019, 9),  (2020, 1),  4,   "MED",  "Luckin Coffee"),
    ("PDD",    "2018-07-26", (2018, 8),  (2021, 2),  6,   "MED",  "Pinduoduo"),
    ("TME",    "2018-12-12", (2019, 12), (2021, 3),  3,   "MED",  "Tencent Music"),
    ("FUTU",   "2019-03-08", (2019, 9),  (2021, 2),  14,  "MED",  "Futu Holdings"),
    ("TIGR",   "2019-03-20", (2019, 4),  (2021, 2),  6,   "MED",  "UP Fintech"),
    ("OZON",   "2020-11-24", (2020, 11), (2021, 2),  2.5, "MED",  "Ozon Holdings"),
    ("ATOS",   "2012-05-11", (2020, 4),  (2021, 2),  15,  "MED",  "Atossa Therapeutics"),
    ("BBIG",   "2017-03-31", (2021, 9),  (2021, 11), 6,   "MED",  "Vinco Ventures"),
    ("PROG",   "2020-08-25", (2021, 8),  (2021, 10), 15,  "MED",  "Progenity"),

    # Earlier era momentum
    ("TSLA12", "2010-06-29", (2013, 1),  (2014, 3),  5,   "MED",  "Tesla 2013 first run"),
    ("TSLA19", "2010-06-29", (2019, 6),  (2021, 11), 12,  "MED",  "Tesla 2019-2021"),
    ("SHOP",   "2015-05-21", (2016, 2),  (2018, 8),  10,  "MED",  "Shopify early"),
    ("DDD",    "2011-05-25", (2012, 7),  (2014, 1),  8,   "MED",  "3D Systems"),
    ("PLUG14", "1999-09-29", (2013, 2),  (2014, 3),  75,  "MED",  "Plug 2013-14 75x"),
    ("FCEL14", "1992-06-25", (2013, 4),  (2014, 4),  11,  "MED",  "FuelCell 2013-14"),
    ("BIOS",   "1996-02-13", (2013, 3),  (2014, 9),  8,   "MED",  "BioScrip"),
    ("AMD16",  "1972-09-27", (2016, 2),  (2018, 9),  21,  "MED",  "AMD turnaround"),
    ("NVDA16", "1999-01-22", (2016, 2),  (2018, 10), 12,  "MED",  "Nvidia first AI"),
    ("MU16",   "1984-06-01", (2016, 5),  (2018, 5),  7,   "MED",  "Micron 2016"),
    ("TWTR",   "2013-11-07", (2016, 5),  (2021, 2),  6,   "MED",  "Twitter 2016 bot"),

    # 2017-2018 Crypto/Pot
    ("TLRY18", "2018-07-19", (2018, 7),  (2018, 9),  18,  "MED",  "Tilray"),
    ("CGC",    "2014-04-03", (2017, 8),  (2018, 10), 7,   "MED",  "Canopy Growth"),
    ("ACB",    "2017-11-15", (2018, 2),  (2018, 10), 5,   "MED",  "Aurora Cannabis"),
    ("CRON",   "2018-02-27", (2018, 3),  (2019, 3),  5,   "MED",  "Cronos"),
    ("XNET",   "2017-07-31", (2017, 10), (2017, 11), 6,   "MED",  "Xunlei crypto"),

    # Post-dot-com 2003-2007 momentum
    ("NFLX",   "2002-05-23", (2004, 10), (2005, 12), 5,   "MED",  "Netflix 2004-05"),
    ("CROX",   "2006-02-08", (2006, 2),  (2007, 10), 4.5, "MED",  "Crocs post-IPO run"),
    ("BIDU",   "2005-08-05", (2005, 8),  (2007, 11), 5,   "MED",  "Baidu early"),
    ("RIMM",   "1999-02-04", (2003, 1),  (2008, 6),  60,  "MED",  "BlackBerry"),

    # ============================================================
    # SLOW (18+mo) — SECULAR BULLS
    # ============================================================
    ("AAPL",   "1980-12-12", (2003, 4),  (2007, 12), 28,  "SLOW", "Apple iPod"),
    ("AMZN",   "1997-05-15", (2001, 10), (2007, 10), 17,  "SLOW", "Amazon dotcom recovery"),
    ("NFLX12", "2002-05-23", (2012, 8),  (2015, 7),  16,  "SLOW", "Netflix streaming"),
    ("CMG",    "2006-01-25", (2009, 3),  (2015, 7),  15,  "SLOW", "Chipotle GFC"),
    ("LVS",    "2004-12-14", (2009, 3),  (2014, 3),  64,  "SLOW", "Las Vegas Sands"),
    ("PCLN",   "1999-03-30", (2002, 10), (2014, 3),  225, "SLOW", "Priceline/Booking"),
    ("WYNN",   "2002-10-25", (2009, 3),  (2014, 3),  20,  "SLOW", "Wynn Resorts"),
    ("LULU",   "2007-07-27", (2009, 3),  (2011, 6),  25,  "SLOW", "Lululemon GFC"),
    ("SBUX",   "1992-06-26", (2009, 3),  (2015, 11), 10,  "SLOW", "Starbucks GFC"),
    ("CSCO",   "1990-02-16", (1990, 10), (2000, 3),  1300,"SLOW", "Cisco 1990-2000"),
    ("ORCL",   "1986-03-12", (1990, 8),  (2000, 9),  550, "SLOW", "Oracle 1990-2000"),
    ("MSFT",   "1986-03-13", (1990, 10), (1999, 12), 85,  "SLOW", "Microsoft 1990s"),
    ("INTC",   "1971-10-13", (1990, 10), (2000, 9),  50,  "SLOW", "Intel 1990s"),
    ("DELL",   "1988-06-22", (1991, 1),  (2000, 3),  2900,"SLOW", "Dell 1991-2000"),
    ("YHOO",   "1996-04-12", (1998, 10), (2000, 1),  40,  "SLOW", "Yahoo bubble"),
    ("QCOM",   "1991-12-13", (1999, 1),  (2000, 1),  16,  "SLOW", "Qualcomm 1999"),
    ("AMZN99", "1997-05-15", (1998, 10), (1999, 12), 75,  "SLOW", "Amazon dotcom peak"),
    ("EBAY99", "1998-09-24", (1998, 9),  (2000, 3),  40,  "SLOW", "eBay dotcom"),
    ("AOL",    "1992-03-19", (1994, 9),  (1999, 12), 300, "SLOW", "AOL 1994-1999"),
    ("JDSU",   "1993-11-15", (1998, 10), (2000, 3),  120, "SLOW", "JDSU dotcom"),

    # 1974-1982 secular era
    ("WMT",    "1970-10-01", (1974, 12), (1999, 12), 2000,"SLOW", "Walmart secular"),
    ("HD",     "1981-09-22", (1985, 1),  (1999, 12), 2000,"SLOW", "Home Depot secular"),
    ("MCD74",  "1965-04-21", (1974, 10), (1999, 11), 80,  "SLOW", "McDonald's 1974 low"),
    ("MO",     "1952-03-10", (1974, 10), (1987, 9),  30,  "SLOW", "Altria"),

    # GFC-era secular
    ("BAC",    "1998-09-30", (2009, 3),  (2010, 4),  7,   "SLOW", "BoA GFC"),
    ("F",      "1956-01-18", (2008, 11), (2011, 1),  15,  "SLOW", "Ford GFC"),
    ("GMCR",   "1993-09-17", (2009, 3),  (2011, 9),  52,  "SLOW", "Green Mountain"),
    ("DECK",   "1993-10-15", (2008, 11), (2011, 10), 5,   "SLOW", "Deckers"),
    ("CROX08", "2006-02-08", (2008, 11), (2021, 10), 180, "SLOW", "Crocs 2008-2021"),

    # Commodity cycles
    ("NEM",    "1940-05-01", (2000, 11), (2011, 9),  10,  "SLOW", "Newmont 2000-2011"),
    ("FCX",    "1988-07-01", (2001, 10), (2007, 5),  30,  "SLOW", "Freeport copper"),
    ("AEM",    "1983-09-29", (2001, 4),  (2011, 9),  13,  "SLOW", "Agnico Eagle"),
    ("CCJ",    "1996-11-04", (2001, 10), (2007, 6),  25,  "SLOW", "Cameco uranium"),
    ("FSLR",   "2006-11-17", (2006, 11), (2008, 5),  12,  "SLOW", "First Solar"),

    # AI era pre-rally
    ("META",   "2012-05-18", (2022, 11), (2024, 2),  6,   "MED",  "Meta recovery"),
    ("GOOG",   "2004-08-19", (2022, 11), (2024, 2),  2,   "MED",  "Alphabet AI"),
    ("AMZN22", "1997-05-15", (2022, 12), (2024, 12), 2,   "MED",  "Amazon AI era"),

    # Misc large moves
    ("ETH",    "2015-07-30", (2016, 12), (2018, 1),  190, "MED",  "Ethereum bubble"),
    ("XRP",    "2012-08-08", (2017, 3),  (2018, 1),  565, "MED",  "XRP 2017"),
]

def by_class():
    from collections import defaultdict
    c = defaultdict(list)
    for entry in PARABOLIC_BOTTOMS:
        c[entry[5]].append(entry)
    return c

if __name__ == "__main__":
    from collections import defaultdict
    print(f"Total parabolic bottoms: {len(PARABOLIC_BOTTOMS)}")
    c = defaultdict(lambda: {"n":0, "mults":[]})
    for tk, ipo, bot, top, mult, speed, note in PARABOLIC_BOTTOMS:
        c[speed]["n"] += 1
        c[speed]["mults"].append(mult)
    for speed, d in c.items():
        import statistics as st
        print(f"\n  {speed}: n={d['n']}  median_mult={st.median(d['mults']):.0f}×  max={max(d['mults']):.0f}×")
    print(f"\nBy magnitude:")
    bins = [(3,5),(5,10),(10,30),(30,100),(100,999)]
    for lo, hi in bins:
        n = sum(1 for e in PARABOLIC_BOTTOMS if lo <= e[4] < hi)
        print(f"  [{lo:3d}x, {hi:3d}x):  {n:3d}")
