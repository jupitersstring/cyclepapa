"""
Run BTI v4 on a representative SP500 sample at current date (Apr 2026)
and across the past 18 months to show where the index has been firing.

Universe: ~70 well-known SP500 constituents with reliable IPO/listing dates,
spanning all major sectors and IPO eras (1980s through 2021).
"""
from __future__ import annotations
import statistics as st
from collections import defaultdict
from bti_test import compute_natal
from bti_v4 import compute_bti_v4, bti_window_v4, yx

# (ticker, IPO/listing date, sector, name)
SP500_SAMPLE = [
    # Tech / Communication
    ("AAPL",  "1980-12-12", "Tech", "Apple"),
    ("MSFT",  "1986-03-13", "Tech", "Microsoft"),
    ("ORCL",  "1986-03-12", "Tech", "Oracle"),
    ("CSCO",  "1990-02-16", "Tech", "Cisco"),
    ("INTC",  "1971-10-13", "Tech", "Intel"),
    ("NVDA",  "1999-01-22", "Tech", "Nvidia"),
    ("ADBE",  "1986-08-20", "Tech", "Adobe"),
    ("QCOM",  "1991-12-13", "Tech", "Qualcomm"),
    ("AMZN",  "1997-05-15", "Tech", "Amazon"),
    ("GOOGL", "2004-08-19", "Tech", "Alphabet"),
    ("META",  "2012-05-18", "Tech", "Meta"),
    ("CRM",   "2004-06-23", "Tech", "Salesforce"),
    ("AVGO",  "2009-08-06", "Tech", "Broadcom"),
    ("AMD",   "1972-09-27", "Tech", "AMD"),
    ("MU",    "1984-06-01", "Tech", "Micron"),
    ("TXN",   "1953-10-01", "Tech", "Texas Instruments"),
    ("NOW",   "2012-06-29", "Tech", "ServiceNow"),
    ("SHOP",  "2015-05-21", "Tech", "Shopify"),
    ("PLTR",  "2020-09-30", "Tech", "Palantir"),
    ("CRWD",  "2019-06-12", "Tech", "CrowdStrike"),
    ("SNOW",  "2020-09-16", "Tech", "Snowflake"),
    ("DDOG",  "2019-09-19", "Tech", "Datadog"),
    ("PYPL",  "2015-07-20", "Tech", "PayPal"),
    ("SQ",    "2015-11-19", "Tech", "Block"),
    ("NFLX",  "2002-05-23", "Tech", "Netflix"),

    # Healthcare
    ("JNJ",   "1944-09-25", "Health", "Johnson & Johnson"),
    ("UNH",   "1984-10-17", "Health", "UnitedHealth"),
    ("LLY",   "1952-04-15", "Health", "Eli Lilly"),
    ("PFE",   "1942-06-23", "Health", "Pfizer"),
    ("MRK",   "1946-05-15", "Health", "Merck"),
    ("ABBV",  "2013-01-02", "Health", "AbbVie"),
    ("AMGN",  "1983-06-17", "Health", "Amgen"),
    ("GILD",  "1992-01-22", "Health", "Gilead"),
    ("VRTX",  "1991-07-23", "Health", "Vertex"),
    ("REGN",  "1991-04-02", "Health", "Regeneron"),
    ("BIIB",  "1991-09-25", "Health", "Biogen"),
    ("TMO",   "1956-08-01", "Health", "Thermo Fisher"),
    ("DHR",   "1969-12-31", "Health", "Danaher"),
    ("HUM",   "1968-08-14", "Health", "Humana"),

    # Financials
    ("V",     "2008-03-19", "Fin",   "Visa"),
    ("MA",    "2006-05-25", "Fin",   "Mastercard"),
    ("JPM",   "2000-12-31", "Fin",   "JPMorgan (post Chase merger)"),
    ("BAC",   "1998-09-30", "Fin",   "Bank of America (post NationsBank)"),
    ("GS",    "1999-05-04", "Fin",   "Goldman Sachs"),
    ("MS",    "1986-02-21", "Fin",   "Morgan Stanley"),
    ("BLK",   "1999-10-01", "Fin",   "BlackRock"),
    ("AXP",   "1977-05-01", "Fin",   "American Express"),
    ("SCHW",  "1987-09-22", "Fin",   "Charles Schwab"),
    ("COIN",  "2021-04-14", "Fin",   "Coinbase"),
    ("HOOD",  "2021-07-29", "Fin",   "Robinhood"),

    # Consumer
    ("WMT",   "1970-10-01", "Cons",  "Walmart"),
    ("HD",    "1981-09-22", "Cons",  "Home Depot"),
    ("COST",  "1985-12-05", "Cons",  "Costco"),
    ("MCD",   "1965-04-21", "Cons",  "McDonald's"),
    ("SBUX",  "1992-06-26", "Cons",  "Starbucks"),
    ("NKE",   "1980-12-02", "Cons",  "Nike"),
    ("LOW",   "1961-10-10", "Cons",  "Lowe's"),
    ("TGT",   "1967-10-18", "Cons",  "Target"),
    ("DIS",   "1957-11-12", "Cons",  "Disney"),
    ("ABNB",  "2020-12-10", "Cons",  "Airbnb"),
    ("UBER",  "2019-05-10", "Cons",  "Uber"),
    ("DASH",  "2020-12-09", "Cons",  "DoorDash"),

    # Energy/Industrial
    ("XOM",   "1999-11-30", "Eng",   "ExxonMobil (post merger)"),
    ("CVX",   "2001-10-09", "Eng",   "Chevron (post Texaco)"),
    ("OXY",   "1957-04-01", "Eng",   "Occidental"),
    ("CEG",   "2022-02-02", "Eng",   "Constellation Energy (Exelon spinoff)"),
    ("VST",   "2016-10-10", "Eng",   "Vistra"),
    ("BA",    "1962-12-31", "Ind",   "Boeing"),
    ("CAT",   "1929-12-02", "Ind",   "Caterpillar"),
    ("DE",    "1933-09-09", "Ind",   "Deere"),
    ("LMT",   "1995-03-15", "Ind",   "Lockheed Martin (post merger)"),
    ("RTX",   "2020-04-03", "Ind",   "RTX Corp (post merger)"),
    ("GE",    "1962-01-01", "Ind",   "GE"),
    ("GEV",   "2024-04-02", "Ind",   "GE Vernova"),
    ("UNP",   "1969-01-01", "Ind",   "Union Pacific"),
    ("HON",   "1999-12-01", "Ind",   "Honeywell"),

    # Other
    ("TSLA",  "2010-06-29", "Cons",  "Tesla"),
    ("BRK.B", "1996-05-09", "Fin",   "Berkshire Class B"),
    ("RIVN",  "2021-11-10", "Cons",  "Rivian"),
    ("SMCI",  "2007-03-29", "Tech",  "Super Micro"),
    ("MSTR",  "1998-06-11", "Tech",  "MicroStrategy"),
    ("APP",   "2021-04-15", "Tech",  "AppLovin"),
]

EVAL_Y, EVAL_M = 2026, 4

def main():
    print(f"="*155)
    print(f"BTI v4 SCAN — SP500 sample ({len(SP500_SAMPLE)} names) at {EVAL_Y}-{EVAL_M:02d}")
    print(f"="*155)
    results = []
    for tk, ipo, sec, name in SP500_SAMPLE:
        try:
            natal = compute_natal(ipo)
            rep = bti_window_v4(natal, EVAL_Y, EVAL_M, half=3)
            results.append((tk, sec, name, ipo, rep))
        except Exception as e:
            print(f"  {tk}: ERROR {e}")
    results.sort(key=lambda r: -r[4]["bti"])

    print(f"\n{'Rk':>2s} {'Tkr':<6s} {'Sec':<5s} {'Name':<28s} {'IPO':<11s} {'BTIw':>6s} {'+/-':>3s} {'Pmax':>5s} {'rp':>4s} {'dP3':>5s} {'thin':>4s} {'ben':>4s} {'rise':>4s} {'Rnow':>5s} {'I':>4s} {'Gs':>4s}")
    print("-"*155)
    for i, (tk, sec, name, ipo, rep) in enumerate(results, 1):
        print(f"{i:2d} {tk:<6s} {sec:<5s} {name[:28]:<28s} {ipo:<11s} {rep['bti']:6.2f} {rep['window_offset']:+3d} {rep['P_max_18']:5.1f} {rep['rp']:4.2f} {rep['dP3']:+5.2f} {rep['thin']:4.2f} {rep['ben']:4.2f} {rep['rise']:4.2f} {rep['R_now']:5.1f} {rep['I_90d']:4.1f} {rep['Gs']:4.2f}")

    print(f"\n{'='*155}")
    print(f"DISTRIBUTION at {EVAL_Y}-{EVAL_M:02d}")
    print(f"{'='*155}")
    btis = [r[4]["bti"] for r in results]
    print(f"  N={len(btis)}  mean={st.mean(btis):.2f}  median={st.median(btis):.2f}  max={max(btis):.2f}")
    bands = [(0, 1), (1, 2), (2, 3), (3, 5), (5, 10), (10, 999)]
    for lo, hi in bands:
        n = sum(1 for b in btis if lo <= b < hi)
        bar = "█" * n
        print(f"  BTI [{lo:>4.1f}, {hi:>4.1f}):  {n:3d}  {bar}")

    # Sector-level summary
    by_sector = defaultdict(list)
    for r in results:
        by_sector[r[1]].append(r[4]["bti"])
    print(f"\nSector medians:")
    for sec, vals in sorted(by_sector.items(), key=lambda kv: -st.median(kv[1])):
        print(f"  {sec:<6s}  n={len(vals):2d}  median={st.median(vals):5.2f}  max={max(vals):5.2f}  ({sum(1 for v in vals if v>3)} above 3)")

    # Check past 18 months trajectory for top 5
    print(f"\n{'='*155}")
    print(f"PAST 18-MONTH TRAJECTORY for top 5 candidates")
    print(f"{'='*155}")
    for tk, sec, name, ipo, rep in results[:5]:
        natal = compute_natal(ipo)
        traj = []
        for k in range(18, -1, -1):
            y, m = yx(EVAL_Y, EVAL_M, -k)
            r = compute_bti_v4(natal, y, m)
            traj.append((y, m, r["bti"]))
        line = f"  {tk:<6s} {name[:20]:<20s}: "
        for (y, m, b) in traj:
            ch = "█" if b >= 5 else "▓" if b >= 3 else "▒" if b >= 1.5 else "·"
            line += ch
        line += f"  [{traj[-1][2]:.2f}]"
        print(line)
        # Show months where BTI was high
        hot = [(y,m,b) for (y,m,b) in traj if b >= 3]
        if hot:
            tagged = "    hot months: " + ", ".join(f"{y}-{m:02d}={b:.1f}" for (y,m,b) in hot)
            print(tagged)

if __name__ == "__main__":
    main()
