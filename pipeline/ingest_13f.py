"""13F-HR information-table ingest from SEC EDGAR primary XML.

For each fund with a known CIK, pull the most recent 13F-HR filing, parse
the information table (issuer name, CUSIP, value, shares), translate CUSIP
to ticker, store in fund_13f_holdings. This replaces the curated-only
fund_positions data with EVERY position a fund reports — 50-500+ per
filer instead of ~15.

Politeness contract per SEC EDGAR rules: ~5 req/sec max, sleep on 429,
exponential backoff. Designed to run as a long-running background job;
state is persisted on the fly so partial runs are resumable.
"""
import json, os, re, sqlite3, statistics, subprocess, time, sys
import xml.etree.ElementTree as ET
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build_cusip_map import debt_ticker

DB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "cyclepapa.db")
UA = "cyclepapa-research admin@example.com"

NS = {'i': 'http://www.sec.gov/edgar/document/thirteenf/informationtable'}

# CIK map for our known funds. Keyed by canonical fund name.
# Add to this as we resolve more CIKs.
FUND_CIK = {
    # --- Concentrated conviction gems (curated from saved-searches sweep, 2026-09) ---
    "AKO Capital (Nicolai Tangen)": "1376879",
    "Acorn Capital": "2054410",
    "Atmos Capital (Brazil)": "1832439",
    "Bain Capital Life Sciences": "1703031",
    "Greenwoods Asset Management (China)": "1848138",
    "Helios Capital (Samir Arora, India)": "1727612",
    "Hyperion Asset Management": "1619844",
    "MFN Partners Management": "1732811",
    "Oldfield Partners": "1492815",
    "Orion Resource Partners (mining)": "2032200",
    "Owl Creek Asset Management": "1313756",
    "Redwood Capital Management": "1316622",
    "Samsara BioCapital": "1744967",
    # --- Conviction multibagger + bleeding-edge growth (saved-searches, 2026-09) ---
    "Rokos Capital Management (Chris Rokos)": "1666335",
    "Old West Investment Management": "1549358",
    "Aldebaran Capital": "1448430",
    "Pembroke Management": "1063497",
    "RiverPark Advisors": "1484256",
    "Lakehouse Capital": "1844830",
    "Equinox Partners (Sean Fieler)": "938552",
    "Oak Hill Advisors": "1164688",
    "Fortress Investment Group": "1380393",
    "Ancient Art (MHR-linked)": "1426749",
    "ARK Investment Management (Cathie Wood)": "1697748",
    "Kora Management": "1659815",
    "Sustainable Growth Advisers": "1290668",
    "Vulcan Value Partners (Fitzpatrick)": "1556785",
    "Tsai Capital (Christopher Tsai)": "1574850",
    "GQG Partners (Rajiv Jain)": "1697233",
    "Kornitzer Capital (Buffalo Funds)": "898358",
    "SoMa Equity Partners": "1680964",
    "Whale Rock Capital Management": "1387322",
    "Dragoneer Investment Group": "1602189",
    "Durable Capital Partners (Ellenbogen)": "1798849",
    "Alkeon Capital Management": "1230239",
    "Tekne Capital Management": "1558971",
    "Greenoaks": "1840735",
    "Skye Global Management": "1675884",
    "Steadfast Capital Management": "1214822",
    # --- Big-swing special-sits/deep-value (from saved-searches, 2026-09) ---
    "Bronte Capital (John Hempton)": "1471085",
    "Farallon Capital Management": "909661",
    "Oaktree Capital Management (Howard Marks)": "949509",
    "Contrarian Capital Management": "1050417",
    "Cyrus Capital Partners": "1166564",
    "Caspian Capital": "1518999",
    "Sabby Management": "1535610",
    "Intrinsic Edge Capital": "1671754",
    "Sands Capital": "1846444",
    "Conestoga Capital Advisors": "1163744",
    # --- Concentrated microcap / special-sits big-swing funds (2026-08) ---
    "Black Diamond Capital (Stephen Deckoff)": "2084285",
    "Newtyn Management": "1569241",
    "Roubaix Capital": "1769700",
    "Hudson Executive Capital (Braunstein)": "1652522",
    "Palogic Value Management": "1532943",
    "North Peak Capital Management": "1747888",
    # --- Under-radar long-term compounders (2026-08) ---
    "Eagle Capital Management (Boykin Curry)": "945631",
    "SRS Investment Mgmt (Karthik Sarma)": "1503174",
    "Atreides Management (Gavin Baker)": "1777813",
    "Markel Group (Tom Gayner)": "1096343",
    "Ensign Peak Advisors (LDS Church)": "1454984",
    "Chou Associates (Francis Chou)": "1389403",
    "Broad Run Investment Mgmt": "1568621",
    "Findlay Park Partners": "1351950",
    "WCM Investment Management": "1061186",
    "Baillie Gifford & Co": "1088875",
    # Pershing Square Inc. (was Pershing Square Holdco) files the combined book
    # from Q2 2026; the adviser (1336528) filed a 13F-NT pointing to it. The
    # adviser still files the 13D/As (ingest_13d keeps 1336528).
    "Pershing Square Capital Managem": "2026053",
    # --- Low-profile / "hidden" exceptional filers (2026-08, verified active) ---
    "Euclidean Capital (Jim Simons FO)":    "1825034",
    "Gates Foundation Trust (Larson)":      "1166559",
    "Longview Asset Mgmt (Crown Family)":   "1086477",
    "Woodbridge Co (Thomson Family)":       "1397960",
    "Summer Road (Sackler FO)":             "1604873",
    "Continental Grain (Fribourg)":         "929607",
    "Koch Inc (Koch Family)":               "2027344",
    "Stockbridge Partners (Berkshire Ptrs)": "1505183",
    "BlueCrest Capital (Michael Platt)":    "1610880",
    "Quadrature Capital (London Quant)":    "1651424",
    "Boxer Capital Management (Tavistock)": "2018299",
    # --- Billionaire family-office gap-fill (2026-08, verified active filers) ---
    "Meritage Group (Nat Simons)":          "1427119",
    "Wildcat Capital (Bonderman FO)":       "1582384",
    "Thiel Macro (Peter Thiel)":            "1562087",
    # --- PitchBook-sourced additions (2026-07, verified active 13F filers) ---
    "Cat Rock Capital Management":          "1654648",
    "Theleme Partners":                     "1511881",
    "Clarkston Capital Partners":           "1562855",
    "Hosking Partners":                     "1650135",
    "Tybourne Capital Management":          "1553936",
    "Man Group":                            "1637460",
    "Mubadala Investment Company":          "1704268",
    "Third Point LLC":                     "1040273",
    "Elliott Investment Management":       "0001791786",
    "Starboard Value LP":                  "1517137",
    "Trian Fund Management":               "1345471",
    "Icahn Capital   Carl Icahn":          "921669",
    "Baupost Group LLC":                   "1061768",
    "ValueAct Capital":                    "1418814",
    "Glenview Capital Management":         "1138995",
    "TCI Fund Management Ltd":             "1647251",
    "Lone Pine Capital LLC":               "1061165",
    "Tiger Global Management LLC":         "1167483",
    "Coatue Management LLC":               "1135730",
    "D1 Capital Partners":                 "1747057",
    "Eminence Capital LP":                 "1107310",
    "Sachem Head Capital Management":      "1582090",
    "Pentwater Capital Management":        "1425851",
    "Magnetar Capital LLC":                "1352851",
    "Suvretta Capital Management":         "1569064",
    "BVF Partners L.P.":                   "1056807",
    "OrbiMed Advisors LLC":                "1055951",
    "Baker Bros. Advisors LP":             "1263508",
    "RA Capital Management LP":            "1346824",
    "Perceptive Advisors LLC":             "1224962",
    "EcoR1 Capital LLC":                   "1587114",
    "Casdin Capital LLC":                  "1534261",
    "Armistice Capital LLC":               "1601086",
    "Marathon Asset Management":           "1279913",
    "Silver Point Capital":                "1332784",
    "Hudson Bay Capital Management L":     "1393825",
    "GoldenTree Asset Management":         "1278951",
    "Mudrick Capital Management":          "1655183",
    "Paulson & Co Inc":                    "1035674",
    "Fairfax Financial Holdings":          "915191",
    "Pelham Capital Management":           "1654111",
    "Engine Capital":                      "1665590",
    "Wynnefield Capital":                  "1251567",
    "ADW Capital Management":              "1745214",
    "Caligan Partners LP":                 "1727492",
    "Buckley Capital Advisors":            "2111611",
    "Harbert Discovery Fund":              "1616659",
    "Cevian Capital":                      "1365341",
    "Cartica Management":                  "1600011",
    "Sessa Capital":                       "1595849",
    "Pzena Investment Management":         "1027796",
    "CAS Investment Partners":             "1697591",
    "Petrus Advisers":                     "1473429",
    "JANA Partners":                       "1998597",
    "Voss Capital":                        "1730145",
    "Marlowe Partners":                    "1624049",
    "Alta Fox Capital Management":         "1858353",
    "Roumell Asset Management":            "1331693",
    "Cove Street Capital":                 "1531612",
    "Donald Smith & Co":                   "814375",
    "Third Avenue Management":             "1099281",
    "Dodge and Cox":                       "200217",
    "Lindsell Train Limited":              "1484150",
    "Yacktman Asset Management LP":        "905567",
    "Wedgewood Partners":                  "859804",
    "Cantillon Capital Management":        "1279936",
    "Dorsey Asset Management":             "1671657",
    "Patient Capital Management":          "1854794",
    "Oakcliff Capital Partners":           "1657335",
    "Greenlea Lane Capital":               "1766504",
    "Daily Journal Corporation":           "783412",
    "Berkshire Hathaway":                  "1067983",
    "Himalaya Capital Management":         "1709323",
    "Sound Shore Management":              "820124",
    "Kahn Brothers Group":                 "1039565",
    "Jensen Investment Management":        "1106129",
    "Atlantic Investment Management":      "1063296",
    "Conifer Management":                  "1773994",
    "Altarock Partners":                   "1631014",
    "FPA Crescent Fund":                   "1377581",
    # --- FMP discovery screen (2026-09): all Q2-2026 13F filers screened for
    #     concentration, patience and a 5-year beat of the S&P, then read by
    #     business model (corporates, VC/PE GPs, wealth managers, ETF books out)
    "Peconic Partners (William Harnisch)": "1050464",
    "Oaktop Capital Management II": "1550660",
    "Analog Century Management": "1753384",
    "Trybe Capital Management": "1807902",
    "Trivest Advisors": "1555623",
    "Sassicaia Capital Advisers": "1692751",
    "Jericho Capital Asset Management (Josh Resnick)": "1525234",
    "Shannon River Fund Management (Spencer Waxman)": "1301050",
    "Kensico Capital Management (Michael Lowenstein)": "1113000",
    "Greenstone Partners": "1845565",
    "Maple Rock Capital Partners": "1658363",
    "Hill City Capital": "1837343",
    "Slate Path Capital (David Greenspan)": "1559706",
    "Abrams Bison Investments": "1317588",
    "Atalan Capital Partners": "1662906",
    "Cobalt Capital Management (Wayne Cooperman)": "1086762",
    "Metavasi Capital": "1864835",
    "Totem Point Management": "1759364",
    "Strategy Capital": "1592413",
    "General Equity Holdings": "1700362",
    "Once Capital Management": "1712892",
    "Kinetic Partners Management": "1911448",
    "Rovida Investment Management": "2053064",
    "Newlands Management": "1908450",
    "Napean Trading & Investment (Singapore family office)": "2011874",
    "Central Asset Investments & Management Holdings": "1583672",
    "Madison Avenue Partners (Eli Samaha)": "1801265",
    "Plustick Management": "1643351",
    "Flat Footed LLC (Marc Andersen)": "1799456",
    "Shah Capital Management (Himanshu Shah)": "1383838",
    "SoftVest Advisors (Eric Oliver)": "1803391",
    "325 Capital": "1873893",
    "Naya Capital Management": "1665012",
    "Liberty 77 Capital (Steven Mnuchin)": "1905374",
    "Whitefort Capital Management": "1884931",
    "OCO Capital Partners": "1764525",
    "Arena Capital Advisors": "1833078",
    "Broad Bay Capital Management": "1759115",
    "Glendon Capital Management (Holly Kim)": "1604350",
    "Wolf Hill Capital Management": "1785988",
    "Apis Capital Advisors": "1386892",
    "Ratan Capital Management (Nehal Chopra)": "1566887",
    "Alta Fundamental Advisers": "1641604",
    "JNE Partners": "1770120",
    "Helikon Investments": "1839497",
    "Moerus Capital Management (Amit Wadhwaney)": "1742647",
    "Juniper Investment Company": "1794034",
    "Altravue Capital": "1740837",
    "Harvey Partners": "1406484",
    "Divisar Capital Management": "1645721",
    "Quaker Capital Investments": "1633648",
    "Valueworks LLC (Charles Lemonides)": "1282189",
    "Steinberg Asset Management": "1169883",
    "Morgens Waterfall Vintiadis": "1016150",
    "Nextech Invest": "1595430",
    "TCG Crossover Management": "1839948",
    "Fairmount Funds Management": "1802528",
    "Commodore Capital": "1831942",
    "Frazier Life Sciences Management": "1892134",
    "Lynx1 Capital Management": "1910456",
    "Paradigm BioCapital Advisors": "1855655",
    "Saturn V Capital Management": "1964437",
    "Krensavage Asset Management": "1609251",
    "Vivo Capital": "1674712",
    "Merk Investments (gold)": "1302842",
    "SailingStone Capital Partners (resources)": "1608904",
    "L1 Capital (Australia)": "1817646",
    "Inca Investments (LatAm)": "1513137",
    "Cape Ann Asset Management (LatAm/resources)": "1768237",
    "Avala Global": "1948899",
    "Keywise Capital Management (HK)": "1474069",
    # --- Saved-searches workbook (2026-09): deep-value / activist / legends
    #     advisers from the PitchBook investor lists, each read by its Q2 book.
    #     Researcher-XLSX names are kept verbatim so the 13F joins their rows.
    "Egerton Capital Ltd": "1581811",          # Egerton Capital (UK) LLP; 1083657 went 13F-NT in 2013
    "EdgePoint (Bousada MacDonald Fa": "1481669",
    "Palliser Capital UK": "1881490",
    "Braden M. Leonard   BML Investm": "1616824",
    "Indaba Capital Management": "1524362",
    "Browning West (Usman Nabi)": "1825564",
    "GMT Capital (Tom Claugus)": "1106191",
    "Great Point Partners": "1281446",
    "Khrom Capital Management": "1877963",
    "Rubric Capital Management (David Rosen)": "1687509",
    "Marathon Asset Management London (Neil Ostrer)": "1861026",
    "Orbis Allan Gray": "1663865",
    "Aegis Financial (Scott Barbee)": "1140753",
    "Cormorant Asset Management (Bihua Chen)": "1583977",
    "Independent Franchise Partners": "1483866",
    "Senvest Management (Richard Mashaal)": "1328785",
    "Soroban Capital Partners (Eric Mandelblatt)": "1517857",
    "Squadra Investimentos (Brazil)": "1577806",
    "Tang Capital Management (Kevin Tang)": "1232621",
    "VR Capital (VR Advisory Services, Richard Deitz)": "1348145",
    "VY Capital Management (Alexander Tamas)": "1628622",
    "Sarissa Capital Management (Alex Denner)": "1577524",
    "P. Schoenfeld Asset Management": "1040198",
    "Standard Investments / 40 North (Winter family)": "1539436",
    "Makaira Partners (Tom Bancroft)": "1540866",
    "Artal Group (Invus, Debbane family)": "1053906",
}

# style label (fund_meta.fund_group) for roster funds with no researcher-XLSX
# row: written by run() so styles_view can place them (FMP discovery adds)
FUND_STYLE_LABEL = {
    "Peconic Partners (William Harnisch)": "Concentrated Quality - ultra-concentrated infrastructure",
    "Oaktop Capital Management II": "Concentrated Quality - long-hold semicap",
    "Analog Century Management": "Concentrated Growth - semis specialist",
    "Trybe Capital Management": "Concentrated Growth - semis/AI",
    "Trivest Advisors": "Concentrated Growth - memory/storage",
    "Sassicaia Capital Advisers": "Concentrated Growth - semis",
    "Jericho Capital Asset Management (Josh Resnick)": "Concentrated Growth - TMT",
    "Shannon River Fund Management (Spencer Waxman)": "Concentrated Growth - tech",
    "Kensico Capital Management (Michael Lowenstein)": "Concentrated Quality compounders",
    "Greenstone Partners": "Concentrated Quality compounders",
    "Maple Rock Capital Partners": "Concentrated Value / Quality",
    "Hill City Capital": "Concentrated Quality - infrastructure/energy",
    "Slate Path Capital (David Greenspan)": "Concentrated Value / Quality",
    "Abrams Bison Investments": "Concentrated Value / Quality",
    "Atalan Capital Partners": "Concentrated Value / Quality",
    "Cobalt Capital Management (Wayne Cooperman)": "Concentrated Value / Quality",
    "Metavasi Capital": "Disruptive Growth / Innovation",
    "Totem Point Management": "Disruptive Growth / Innovation",
    "Strategy Capital": "Disruptive Growth / Innovation",
    "General Equity Holdings": "Disruptive Growth / Innovation",
    "Once Capital Management": "Disruptive Growth / Innovation",
    "Kinetic Partners Management": "Disruptive Growth / Innovation",
    "Rovida Investment Management": "Disruptive Growth / Innovation",
    "Newlands Management": "Disruptive Growth / Innovation",
    "Napean Trading & Investment (Singapore family office)": "Family Office - venture-style concentrated",
    "Central Asset Investments & Management Holdings": "Family Office - concentrated memory/storage",
    "Madison Avenue Partners (Eli Samaha)": "Activists / Special Situations",
    "Plustick Management": "Activists / Special Situations - spectrum",
    "Flat Footed LLC (Marc Andersen)": "Activists / Special Situations",
    "Shah Capital Management (Himanshu Shah)": "Activists / Special Situations",
    "SoftVest Advisors (Eric Oliver)": "Activists / Special Situations",
    "325 Capital": "Activists / Special Situations - micro/small",
    "Naya Capital Management": "Activists / Special Situations",
    "Liberty 77 Capital (Steven Mnuchin)": "Activists / Special Situations - sponsor",
    "Whitefort Capital Management": "Activists / Special Situations",
    "OCO Capital Partners": "Activists / Special Situations",
    "Arena Capital Advisors": "Activists / Special Situations",
    "Broad Bay Capital Management": "Activists / Special Situations",
    "Glendon Capital Management (Holly Kim)": "Distressed / Event-Driven",
    "Wolf Hill Capital Management": "Distressed / Event-Driven",
    "Apis Capital Advisors": "Distressed / Event-Driven",
    "Ratan Capital Management (Nehal Chopra)": "Distressed / Event-Driven",
    "Alta Fundamental Advisers": "Distressed / Event-Driven",
    "JNE Partners": "Distressed / Event-Driven",
    "Helikon Investments": "Distressed / Event-Driven",
    "Moerus Capital Management (Amit Wadhwaney)": "Deep Value / Concentrated Quality",
    "Juniper Investment Company": "Small-cap / Multibagger Specialists",
    "Altravue Capital": "Small-cap / Multibagger Specialists",
    "Harvey Partners": "Small-cap / Multibagger Specialists",
    "Divisar Capital Management": "Small-cap / Multibagger Specialists",
    "Quaker Capital Investments": "Concentrated Value / Quality",
    "Valueworks LLC (Charles Lemonides)": "Deep Value / Concentrated Quality",
    "Steinberg Asset Management": "Concentrated Value / Quality",
    "Morgens Waterfall Vintiadis": "Concentrated Value / Quality",
    "Nextech Invest": "Biotech Specialists",
    "TCG Crossover Management": "Biotech Specialists",
    "Fairmount Funds Management": "Biotech Specialists",
    "Commodore Capital": "Biotech Specialists",
    "Frazier Life Sciences Management": "Biotech Specialists",
    "Lynx1 Capital Management": "Biotech Specialists",
    "Paradigm BioCapital Advisors": "Biotech Specialists",
    "Saturn V Capital Management": "Biotech Specialists",
    "Krensavage Asset Management": "Biotech Specialists",
    "Vivo Capital": "Biotech Specialists",
    "Merk Investments (gold)": "PE / SPAC / Gold / Mining",
    "SailingStone Capital Partners (resources)": "Natural resources - gold and mining",
    "L1 Capital (Australia)": "Global resources long/short (Australia)",
    "Inca Investments (LatAm)": "LatAm EM value",
    "Cape Ann Asset Management (LatAm/resources)": "LatAm EM value",
    "Avala Global": "Global concentrated long/short",
    "Keywise Capital Management (HK)": "Asia TMT concentrated",
}
# saved-searches workbook adds (2026-09); researcher-XLSX funds keep their own
# fund_meta group and need no label here
FUND_STYLE_LABEL_SAVED = {
    "Browning West (Usman Nabi)": "Activists / Special Situations",
    "GMT Capital (Tom Claugus)": "Concentrated Value / Quality",
    "Great Point Partners": "Biotech Specialists",
    "Khrom Capital Management": "Small-cap / Multibagger Specialists",
    "Rubric Capital Management (David Rosen)": "Activists / Special Situations",
    "Marathon Asset Management London (Neil Ostrer)": "European capital-cycle value",
    "Orbis Allan Gray": "Global contrarian value",
    "Aegis Financial (Scott Barbee)": "Small-cap deep value",
    "Cormorant Asset Management (Bihua Chen)": "Biotech Specialists",
    "Independent Franchise Partners": "Concentrated Quality compounders",
    "Senvest Management (Richard Mashaal)": "Small-cap / Multibagger Specialists - big swings",
    "Soroban Capital Partners (Eric Mandelblatt)": "Tiger Cubs / L/S Legends",
    "Squadra Investimentos (Brazil)": "LatAm EM value",
    "Tang Capital Management (Kevin Tang)": "Biotech Specialists",
    "VR Capital (VR Advisory Services, Richard Deitz)": "Distressed / Event-Driven - EM",
    "VY Capital Management (Alexander Tamas)": "Disruptive Growth / Innovation",
    # "healthcare", not "biotech": the biotech rule runs first in STYLE_RULES
    "Sarissa Capital Management (Alex Denner)": "Activists / Special Situations - healthcare",
    "P. Schoenfeld Asset Management": "Distressed / Event-Driven",
    "Standard Investments / 40 North (Winter family)": "Family Office - concentrated",
    "Makaira Partners (Tom Bancroft)": "Concentrated Value / Quality",
    "Artal Group (Invus, Debbane family)": "Family Office - concentrated",
}
FUND_STYLE_LABEL.update(FUND_STYLE_LABEL_SAVED)

def curl(url, retries=6):
    for i in range(retries):
        r = subprocess.run(["curl", "-sk", "--compressed", "-m", "20", "-A", UA, url],
                           capture_output=True)
        out = r.stdout
        # SEC throttle / block page. Detect its actual markers — ANY html page
        # used to count, so every legitimate HTML response burned ~4.5 min of
        # back-off (20+30+...+70s) before giving up.
        head = out[:8000]
        if (head.find(b'Rate Threshold Exceeded') != -1 or head.find(b'Undeclared Automated Tool') != -1
                or (head.find(b'apology_objects') != -1 and not url.rstrip('/').endswith(('.htm', '.html')))):
            wait = 20 + 10 * i
            print(f"  ! rate-limited, waiting {wait}s")
            time.sleep(wait)
            continue
        return out
    return b''

_F13_CACHE = {}

def f13_filings(cik, need_hr=3):
    """Every 13F filing on EDGAR for this CIK, newest first, as dicts
    {form, acc, filed, period}: 13F-HR, 13F-HR/A, 13F-NT, 13F-NT/A.

    The period (report date) makes the quarter logic exact: a quarter-change
    diff must compare the IMMEDIATELY preceding period, and a fund that went
    quiet for a year must not diff against its last book. The submissions
    "recent" block holds only the last ~1000 filings; a 10%-owner like Viking
    files hundreds of Form 4 / SC 13 amendments a quarter, which can push its
    own 13F-HRs out of it, so the paged history is walked (newest first) until
    `need_hr` 13F-HRs are in hand. Cached per process. None = the fetch FAILED
    (SEC throttling), which callers must not read as "files nothing"."""
    key = str(int(cik))
    hit = _F13_CACHE.get(key)
    if hit is not None and hit[0] >= need_hr:
        return hit[1]
    data = curl(f"https://data.sec.gov/submissions/CIK{key.zfill(10)}.json")
    try:
        d = json.loads(data) if data else None
    except json.JSONDecodeError:
        d = None
    if d is None:
        return None

    def pick(rec):
        forms = rec.get("form", [])
        periods = rec.get("reportDate") or [""] * len(forms)
        return [{"form": f, "acc": rec["accessionNumber"][i], "filed": rec["filingDate"][i],
                 "period": periods[i] or ""}
                for i, f in enumerate(forms) if f.startswith("13F")]

    out = pick(d.get("filings", {}).get("recent", {}))
    if sum(x["form"] == "13F-HR" for x in out) < need_hr:
        for pg in sorted(d.get("filings", {}).get("files", []),
                         key=lambda p: p.get("filingTo", ""), reverse=True):
            body = curl(f"https://data.sec.gov/submissions/{pg['name']}")
            try:
                out += pick(json.loads(body)) if body else []
            except json.JSONDecodeError:
                continue
            if sum(x["form"] == "13F-HR" for x in out) >= need_hr:
                break
    out.sort(key=lambda x: (x["filed"], x["acc"]), reverse=True)
    _F13_CACHE[key] = (need_hr, out)
    return out

def record_f13(conn, cik, filings):
    """Keep the EDGAR 13F index: validate.py checks stored books against it
    offline (a newer 13F-HR not ingested, a prior that is not the preceding
    quarter, holdings moved to another filer by a 13F-NT)."""
    conn.execute("""CREATE TABLE IF NOT EXISTS sec_13f_filings (
        cik TEXT, accession TEXT, form TEXT, filed TEXT, period TEXT,
        PRIMARY KEY (cik, accession))""")
    conn.executemany("INSERT OR REPLACE INTO sec_13f_filings VALUES (?,?,?,?,?)",
                     [(str(int(cik)), x["acc"], x["form"], x["filed"], x["period"])
                      for x in filings or []])

def qkey(period):
    """'2026-06-30' -> (2026, 1): the calendar quarter a 13F period falls in."""
    return (int(period[:4]), (int(period[5:7]) - 1) // 3)

def prev_quarter(period):
    """'2026-06-30' -> '2026-03-31' (13F periods are calendar quarter ends)."""
    y, q = qkey(period)
    return f"{y - 1}-12-31" if q == 0 else f"{y}-{('03-31', '06-30', '09-30')[q - 1]}"

def latest_13f_acc(cik):
    """Return (accession, filed_date) of the latest 13F-HR for this CIK."""
    hrs = [x for x in f13_filings(str(cik)) or [] if x["form"] == "13F-HR"]
    return (hrs[0]["acc"], hrs[0]["filed"]) if hrs else (None, None)

def list_13f_accs(cik, k=3):
    """Up to k most recent 13F-HR (accession, filed) pairs, newest first.
    Lets the ingest fall past an empty off-cycle restatement (Eminence filed a
    1-row 13F-HR in July 2026; the real Q1 book was the accession before it)."""
    hrs = [x for x in f13_filings(str(cik), need_hr=max(k, 3)) or [] if x["form"] == "13F-HR"]
    return [(x["acc"], x["filed"]) for x in hrs[:k]]

_BOOK_CACHE = {}

def fetch_book(cik, acc):
    """Holdings rows of one 13F-HR information table: options (reported at
    underlying value with putCall set) and zero rows dropped. [] = the filing
    genuinely lists nothing usable; None = it could not be fetched or parsed
    (block page, truncated transfer), which must not be booked as empty."""
    key = (str(int(cik)), acc)
    if key in _BOOK_CACHE:                        # name variants share one CIK
        return _BOOK_CACHE[key]
    path = find_infotable(cik, acc)
    if not path:
        return None
    body = curl(path if path.startswith("http") else f"https://www.sec.gov{path}")
    if not body:
        return None
    try:
        ET.fromstring(body)
    except ET.ParseError:
        return None
    # Options are not holdings, whether flagged by putCall or only by the
    # title: Funicular files its puts as "PUT" under option CUSIPs with no
    # putCall element, and $2.4B of puts on MU, NVDA, MSFT, TSLA... sat in the
    # book as long positions, mapped to the stocks by issuer name.
    rows = [r for r in parse_infotable(body)
            if not r.get("put_call") and (r["value_k"] or r["shares"])
            and classify_sec_form(r.get("title"), r["type"]) != "option"]
    _BOOK_CACHE[key] = rows
    return rows

def ingest_book(conn, table, fund, cik, acc, filed, rows, cusip_map, name_map, px_map):
    """Write one 13F-HR's holdings for a fund into `table` (fund_13f_holdings
    or fund_13f_prior). One code path for both quarters, so every guard holds
    on either side of a quarter-change diff. Returns (positions, total_value_k)."""
    # A combined report files one line per ACCOUNT per security (Kopernik:
    # 23,960 lines for ~4,400 securities). Sum lines by CUSIP — the old
    # REPLACE-on-PK kept only the last account's slice of each position.
    agg = {}
    for r in rows:
        a = agg.get(r["cusip"])
        if a is None:
            agg[r["cusip"]] = dict(r)
        else:
            a["value_k"] += r["value_k"]
            a["shares"] += r["shares"]
    rows = list(agg.values())
    total_v = sum(r["value_k"] for r in rows)
    ratios = []          # implied-price / actual-price, for value-unit detection
    for r in rows:
        # Empty-filing markers ("NONE", "NA", cusip 000000000) and zero rows
        # carry no information and must never be booked as holdings.
        if not r["value_k"] and not r["shares"]:
            continue
        # Placeholder CUSIPs are shared across unrelated rows: never consult
        # the authority map for them, fall through to name matching.
        cusip_ok = r["cusip"] and len(r["cusip"]) == 9 and len(set(r["cusip"])) > 1
        cm = cusip_map.get(r["cusip"]) if cusip_ok else None
        if cm is not None:                       # CUSIP authority wins
            tkr = cm[0] if cm[1] != "etf" else None
        else:
            tkr = name_to_ticker(r["issuer"], name_map)
        tkr = debt_ticker(tkr, r["cusip"])       # bond lines never pool with the stock
        pct = (r["value_k"] / total_v * 100) if total_v else None
        conn.execute(f"INSERT OR REPLACE INTO {table} VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                     (fund, cik, acc, filed, r["issuer"], r["cusip"], tkr,
                      r["value_k"], r["shares"], r["type"], pct))
        conn.execute("INSERT OR REPLACE INTO holding_sec_form VALUES (?,?,?,?)",
                     (acc, r["cusip"], r.get("title"),
                      classify_sec_form(r.get("title"), r["type"])))
        # PRN rows: shares = bond principal in dollars, which trades near par
        # (~1.0 value per $1) — reference price 1.0 keeps convert-arb books
        # (Linden: mostly bonds, few priced SH rows) inside the detector.
        p = 1.0 if r["type"] == "PRN" else px_map.get(tkr)
        if p and r["shares"] and r["value_k"]:
            ratios.append((r["value_k"] * 1000.0 / r["shares"]) / p)
    # Value-unit sanity: filings since 2023 report FULL DOLLARS; value_k
    # assumes thousands. Implied price (value/shares) vs actual price is a
    # unit-free detector: median ratio ~1000 means full-dollar filing.
    # The old mcap-based check missed megacap-heavy books (a raw-dollar
    # TSM position is still below TSM's mcap) — Gates Trust booked $31.7T.
    # Scoped to this accession: a prior built from two filings (a successor
    # filer's own line) must not divide the other filing's rows again.
    if ratios:
        full_dollar = ((len(ratios) >= 2 and statistics.median(ratios) > 100)
                       or (len(ratios) == 1 and ratios[0] > 100))
    else:
        # No priced line to test against (delisted / unlisted names only):
        # 13F values have been whole dollars since January 2023, so that is
        # the default, not thousands — Indaba's lone ON24 line was booked at
        # $33.8B, 1000x — unless whole dollars would put the typical line
        # under a cent a share (a filer still reporting in thousands).
        per_share = [r["value_k"] / r["shares"] for r in rows
                     if r["shares"] and r["value_k"] and r["type"] != "PRN"]
        full_dollar = ((filed or "") >= "2023-01-03" and bool(per_share)
                       and statistics.median(per_share) >= 0.01)
    if full_dollar:
        conn.execute(f"UPDATE {table} SET value_k=value_k/1000.0 WHERE fund=? AND accession=?",
                     (fund, acc))
        total_v /= 1000.0
        print(f"    [unit] {fund[:36]}: full-dollar filing normalized to $k")
    return len(rows), total_v

def _same_cik(a, b):
    return str(int(a)) == str(int(b))

# A fund that has missed two quarterly 13F cycles is dormant (unified_score
# gates the same books out of the score with this window).
DORMANT_DAYS = 200

def archive_dormant(conn):
    """Move dormant funds' books out of fund_13f_holdings into fund_13f_dormant.

    The score already ignored them, but every book, sheet and dossier reads
    fund_13f_holdings directly: Egerton's 2013 book and Greenlight's pre-rename
    2023 book were still listed as current holders. Archived, not deleted; a
    fund that files again is re-ingested by the refresh and leaves the archive."""
    conn.execute("CREATE TABLE IF NOT EXISTS fund_13f_dormant AS SELECT * FROM fund_13f_holdings WHERE 0")
    cutoff = conn.execute("SELECT date('now', ?)", (f"-{DORMANT_DAYS} days",)).fetchone()[0]
    dormant = [r[0] for r in conn.execute(
        "SELECT fund FROM fund_13f_state WHERE last_filed IS NOT NULL AND last_filed < ?", (cutoff,))]
    moved = 0
    for f in dormant:
        # only a book still in the live table is (re)archived: replacing the
        # archive copy unconditionally wiped every already-archived book on
        # the next run (nothing left in holdings to copy back in)
        if not conn.execute("SELECT 1 FROM fund_13f_holdings WHERE fund=? LIMIT 1", (f,)).fetchone():
            continue
        conn.execute("DELETE FROM fund_13f_dormant WHERE fund=?", (f,))
        conn.execute("INSERT INTO fund_13f_dormant SELECT * FROM fund_13f_holdings WHERE fund=?", (f,))
        moved += conn.execute("DELETE FROM fund_13f_holdings WHERE fund=?", (f,)).rowcount
    live = [r[0] for r in conn.execute("""SELECT DISTINCT d.fund FROM fund_13f_dormant d
        JOIN fund_13f_state s ON s.fund = d.fund WHERE s.last_filed >= ?""", (cutoff,))]
    for f in live:                                   # filed again: the archive copy is history
        conn.execute("DELETE FROM fund_13f_dormant WHERE fund=?", (f,))
    conn.commit()
    return len(dormant), moved

def roll_prior(conn, fund, cik, stored, new, maps):
    """Before a fund's stored book is replaced by a newer filing, make the
    stored book its prior quarter when it IS the immediately preceding period
    (the normal quarterly roll: no refetch, identical mapping). Any other prior
    is dropped, so ingest_13f_prior re-pulls the exact preceding quarter rather
    than leaving a diff that spans two quarters under a quarter-change header."""
    old_cik, old_acc, old_filed, old_n, old_total = stored
    conn.execute("DELETE FROM fund_13f_prior WHERE fund=?", (fund,))
    conn.execute("DELETE FROM fund_13f_prior_state WHERE fund=?", (fund,))
    old_f = f13_filings(str(old_cik)) or []
    old_period = next((x["period"] for x in old_f if x["acc"] == old_acc), "")
    if not (old_period and new["period"]
            and qkey(old_period) == qkey(prev_quarter(new["period"]))):
        return False
    # the stored book may sit in the dormant archive (a fund that went quiet
    # for two cycles, then filed again)
    src = ["fund_13f_holdings"] + (["fund_13f_dormant"] if conn.execute(
        "SELECT 1 FROM sqlite_master WHERE name='fund_13f_dormant'").fetchone() else [])
    for t in src:
        conn.execute(f"INSERT OR REPLACE INTO fund_13f_prior SELECT * FROM {t} WHERE fund=? AND accession=?",
                     (fund, old_acc))
    n, total = conn.execute("SELECT COUNT(*), COALESCE(SUM(value_k), 0) FROM fund_13f_prior WHERE fund=?",
                            (fund,)).fetchone()
    # A re-pointed fund (successor filer): the successor's own filing for the
    # prior period belongs in the prior book too. Pershing Square Inc. filed only
    # its 9M-share HHH stake for Q1 2026 while the adviser filed the funds' book;
    # Q2 arrives combined, so a prior without that line fabricates a 9M-share add.
    if not _same_cik(old_cik, cik):
        for x in f13_filings(str(cik)) or []:
            if x["form"] == "13F-HR" and x["period"] and qkey(x["period"]) == qkey(old_period):
                rows = fetch_book(cik, x["acc"])
                if rows:
                    n2, t2 = ingest_book(conn, "fund_13f_prior", fund, cik, x["acc"],
                                         x["filed"], rows, *maps)
                    n, total = n + n2, total + t2
                break
    conn.execute("INSERT OR REPLACE INTO fund_13f_prior_state VALUES (?,?,?,?,?)",
                 (fund, old_acc, old_filed, n, total))
    return True

def find_infotable(cik, accession):
    """Find the infotable XML file in the filing directory.

    The XML name is filer-controlled and inconsistent — examples seen:
      infotable.xml / informationtable.xml (most common)
      WedgewoodPartners_13f_1Q26.xml (some filers brand the file)
      13F_2026Q1.xml / xslform13fhrxxx-fix.xml (others)

    Strategy: prefer obvious "infotable" / "informationtable" name; else
    fall back to ANY .xml in the directory that isn't primary_doc.xml
    (which is the cover-page form13f wrapper).
    """
    acc = accession.replace("-", "")
    # 1. the structured listing (index.json). SEC now answers plain directory
    #    browsing from automated clients with its "apology" block page, which
    #    lists no files — scraping it silently fell through to a guessed
    #    infotable.xml and lost every filer with a custom name
    #    ("trybe2q2026.inftbl.xml", "WedgewoodPartners_13f_1Q26.xml").
    js = curl(f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc}/index.json")
    try:
        names = [it["name"] for it in json.loads(js)["directory"]["item"]]
    except (ValueError, KeyError, TypeError):
        names = []
    xmls = [n for n in names if n.lower().endswith(".xml") and n.lower() != "primary_doc.xml"]
    base = f"/Archives/edgar/data/{int(cik)}/{acc}/"
    for n in xmls:
        low = n.lower()
        if any(k in low for k in ("infotable", "informationtable", "inftbl", "infotbl", "info_table")):
            return base + n
    if xmls:
        return base + xmls[0]
    # 2. fall back to the HTML directory page
    data = curl(f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc}/")
    if not data: return None
    matches = re.findall(r'href="([^"]+\.xml)"', data.decode("utf-8", errors="ignore"), re.I)
    # Drop noisy hrefs that aren't in our filing dir, and exclude xslForm paths
    # (those are the XSL-rendered HTML versions, not raw data)
    relevant = [m for m in matches if str(int(cik)) in m and acc in m
                and "xslform" not in m.lower()]
    for m in relevant:
        n = m.split("/")[-1].lower()
        if "infotable" in n or "informationtable" in n: return m
    for m in relevant:
        n = m.split("/")[-1].lower()
        if n == "primary_doc.xml": continue
        return m
    return f"/Archives/edgar/data/{int(cik)}/{acc}/infotable.xml"

def _strip_ns(elem):
    """Recursively strip XML namespaces from element tags."""
    if "}" in elem.tag:
        elem.tag = elem.tag.split("}", 1)[1]
    for k in list(elem.attrib):
        if "}" in k:
            elem.attrib[k.split("}", 1)[1]] = elem.attrib.pop(k)
    for child in elem:
        _strip_ns(child)
    return elem

def parse_infotable(xml_bytes):
    """Yield {issuer, cusip, value_k, shares, type} dicts."""
    try:
        root = _strip_ns(ET.fromstring(xml_bytes))
    except ET.ParseError:
        return []
    out = []
    for it in root.findall(".//infoTable"):
        def t(p):
            e = it.find(p)
            return (e.text or "").strip() if e is not None else ""
        try: v = int(t("value"))
        except ValueError: v = 0
        try: sh = int(t("shrsOrPrnAmt/sshPrnamt"))
        except ValueError: sh = 0
        out.append({
            "issuer": t("nameOfIssuer")[:80],
            # upper-case: some filers (Ancora, RiverPark) write lowercase
            # CUSIPs, splitting one security into two rows and missing cusip_map
            "cusip":  t("cusip").upper(),
            "value_k": v,
            "shares":  sh,
            "type":    t("shrsOrPrnAmt/sshPrnamtType"),
            # titleOfClass is the filer's own security-class label ("COM",
            # "PFD", "WARRANT", "CL A", "UNIT", "NOTE", "SPON ADR"...). Lets us
            # tell an add of COMMON (a clean directional bet) from an add of
            # warrants / preferred / converts (optionality or financing).
            "title":  t("titleOfClass")[:40],
            # Derivatives are reported at underlying value with putCall set.
            # Booking them as shares corrupts consensus (a PUT is bearish!) —
            # OrbiMed's $286M MDXH call surfaced as an 11x-mcap "holding".
            "put_call": t("putCall").lower(),
        })
    return out

# titleOfClass -> normalized equity form. Order matters (option/warrant/etf
# before common so "COM WT" reads warrant, "Equity Option" reads option).
# Falls back to sh_type for bonds (PRN=note).
def classify_sec_form(title, sh_type=""):
    tt = (title or "").upper()
    if sh_type == "PRN" or re.search(r"\bNOTE|\bBOND|\bDEB\b|SR NT|% DUE|CONV NT", tt):
        return "note"
    if re.search(r"OPTION|\bCALL\b|\bPUT\b", tt):
        return "option"        # slipped past the putCall filter (filer labels it here)
    if re.search(r"WARRANT|\bWTS?\b|\bWT\b|\bWS\b|\*?W\s+EXP|\bWARR\b", tt):
        return "warrant"
    if re.search(r"\bRIGHT|\bRTS?\b|\bRT\b|CVR|CONTINGENT VALUE", tt):
        return "right"
    if re.search(r"ETF|\bETP\b|EXCH(ANGE)?[\s-]*TRAD|INDX FD|INDEX FUND|"
                 r"CLSD FD|CLOSED[\s-]END|SPDR|ISHARES|\bSPD\b|\bCON\b\s*FD", tt):
        return "etf"
    if re.search(r"\bUNIT", tt):
        return "unit"
    if re.search(r"\bPFD|PREF|PREFERRED|DEP(OSITARY)?\s+SH|DEP\s+REP|% CUM|% SR", tt):
        return "preferred"
    if re.search(r"\bADR|ADS|SPON(SORED)?\s+ADR|AMERICAN DEP", tt):
        return "adr"
    if re.search(r"\bCL\s+[A-Z]\b|CLASS\s+[A-Z]\b|SER(IES)?\s+[A-Z]\b", tt):
        return "class"          # dual-class common (COM CL A / CLASS B)
    # generic common labels: COM/COMMON/ORD/SHS/STK plus the plain "EQUITY",
    # "COMM", "REIT", "LP/LLC unit" tags some filers use for ordinary equity.
    if re.search(r"\bCOM\b|COMMON|\bCOMM\b|\bORD|ORDINARY|\bSHS?\b|SHARES|STK\b|"
                 r"CAP STK|BEN INT|\bSBI\b|\bEQUITY\b|\bREIT\b|\bLP\b|\bLLC\b|\bTR UNIT", tt):
        return "common"
    return "common" if tt == "" else "other"

def cusip_ticker_map(conn):
    """Build CUSIP -> ticker map from any available source.
    We use the SEC's company_tickers_exchange.json which has CIK+name+ticker.
    For now we map by issuer NAME → ticker, since the file doesn't include CUSIP.
    Better mapping requires the OpenFIGI API or a vendor file; this is good enough
    for the names already in our universe."""
    data = curl("https://www.sec.gov/files/company_tickers_exchange.json")
    if not data: return {}
    try:
        d = json.loads(data)
    except json.JSONDecodeError:
        return {}
    # Format: {"fields":["cik","name","ticker","exchange"], "data":[[...],...]}
    # A company appears once per listed line (MS, MS-PA ... MS-PQ): the plain
    # primary ticker must win. Last-row-wins had mapped Morgan Stanley, Goldman,
    # Boeing and Oracle COMMON stock onto preferred lines, which then scored as
    # preferreds and fell out of every common-stock signal.
    def better(new, old):
        return old is None or ("-" in old and "-" not in new)
    by_name = {}
    for row in d.get("data", []):
        if len(row) >= 3:
            cik, name, tkr, exch = row[0], row[1].upper(), row[2], row[3] if len(row)>3 else ""
            if better(tkr, by_name.get(name)):
                by_name[name] = tkr
            nn = _norm_name(name)          # normalized key for fuzzy match
            if nn and better(tkr, by_name.get(nn)):
                by_name[nn] = tkr
    return by_name

def _norm_name(s):
    """Normalise an issuer name for matching: drop punctuation and corporate
    suffixes so 'MOODYS CORP DEL' and 'Moody's Corporation' collide."""
    s = (s or "").upper()
    s = re.sub(r"[.,'/&()\-]", " ", s)
    # Expand SEC's standard abbreviations FIRST so an issuer's "CNX RES CORP" and
    # the SEC file's "CNX Resources Corp" normalize to the same tokens. This is the
    # single biggest source of silently-dropped REAL companies (Brookdale "SR
    # LIVING", VICI "PPTYS", UGI "CORP NEW", Global "PMTS") — expansion makes both
    # sides specific rather than guessing. Expanding NEVER collapses distinct firms.
    s = " " + s + " "
    for ab, full in _ABBREV.items():
        s = re.sub(rf"\b{ab}\b", full, s)
    s = re.sub(r"\b(THE|INC|CORP|CORPORATION|CO|COMPANY|COS|HOLDING|HOLDINGS|HLDGS?|"
               r"GROUP|GRP|LTD|LIMITED|PLC|LP|LLC|NV|SA|AG|ADR|ADS|SP|SPONSORED|"
               r"CLASS|CL|COM|COMMON|ORD|ORDINARY|NEW|DEL|TR|TRUST|REIT|PARTNERS)\b", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s

# SEC issuer-name abbreviations -> full word (both the 13F issuer and the SEC
# ticker file get normalized through this, so they collide).
_ABBREV = {
    "RES": "RESOURCES", "PPTYS": "PROPERTIES", "PPTY": "PROPERTIES", "PROPS": "PROPERTIES",
    "SR": "SENIOR", "PMTS": "PAYMENTS", "PMT": "PAYMENT", "INDS": "INDUSTRIES",
    "IND": "INDUSTRIES", "INVT": "INVESTMENT", "INVTS": "INVESTMENTS", "INV": "INVESTMENT",
    "MGMT": "MANAGEMENT", "MGT": "MANAGEMENT", "INTL": "INTERNATIONAL", "NATL": "NATIONAL",
    "FINL": "FINANCIAL", "FIN": "FINANCIAL", "SVCS": "SERVICES", "SVC": "SERVICE",
    "SYS": "SYSTEMS", "TECHS": "TECHNOLOGIES", "TCHNLGY": "TECHNOLOGY", "COMMTNS": "COMMUNICATIONS",
    "COMM": "COMMUNICATIONS", "COMMUN": "COMMUNICATIONS", "PHARMS": "PHARMACEUTICALS",
    "PHARM": "PHARMACEUTICALS", "PHRM": "PHARMACEUTICALS", "LAB": "LABORATORIES",
    "LABS": "LABORATORIES", "MTLS": "MATERIALS", "MTL": "METALS", "ENGY": "ENERGY",
    "ENRGY": "ENERGY", "PWR": "POWER", "BANCORPORATION": "BANCORP", "BANCSHARES": "BANCSHARES",
    "HLTH": "HEALTH", "HLTHCARE": "HEALTHCARE", "Cap": "CAPITAL", "CAP": "CAPITAL",
    "MFG": "MANUFACTURING", "MFRS": "MANUFACTURERS", "GLBL": "GLOBAL", "SEMICONDUCTOR": "SEMICONDUCTOR",
    "SEMI": "SEMICONDUCTOR", "PROD": "PRODUCTS", "PRODS": "PRODUCTS", "SOLTNS": "SOLUTIONS",
    "SLTNS": "SOLUTIONS", "ENTMT": "ENTERTAINMENT", "ENTERTAINMEN": "ENTERTAINMENT",
}

# ETF / fund-family issuers. A 13F line for "Invesco Exch Trd" or "Global X Fds"
# is an ETF POSITION, not smart money in the operating company that shares a name
# stem (Invesco Ltd / Global Partners LP). Historically the fuzzy matcher
# collapsed whole fund families onto one operating ticker (GLP got 137 phantom
# "Global*" holders; IVZ 302), badly inflating smart_money_n. Fund issuers must
# NOT fuzzy-map to an operating ticker.
# Structural fund-vehicle tokens only — NOT brand names (WisdomTree/Invesco are
# also operating tickers). Real operating companies whose name contains "Trust"
# or "Fund" (Northern Trust=NTRS, Eaton Vance, Franklin) are protected because
# name_to_ticker's raw-exact SEC lookup runs BEFORE this guard; only issuers
# absent from the SEC ticker file (the ETF trust entities) fall through to it.
_FUND_ISSUER_RE = re.compile(
    r"\b(ETF|ETFS|EXCH\s*TRD|EXCHANGE\s*TRD|FDS|SER\s*TR|"
    r"INDEX\s*(FD|FDS|FUND|FUNDS|TR|TRUST)|"
    r"UCITS|SELECT\s*SECTOR|ISHARES|SPDR|POWERSHARES|PROSHARES)\b"
    r"|(\bTR|TRUST|FUND|FUNDS|SHARES|PORTFOLIO)\s*$", re.I)

def _is_fund_issuer(name):
    return bool(_FUND_ISSUER_RE.search(name or ""))

def name_to_ticker(name, name_map):
    if not name: return None
    n = name.upper().strip()
    if n in name_map: return name_map[n]   # raw exact is always safe
    # Fund/ETF issuers stop here: normalization strips the very tokens (TRUST /
    # FUND / TR) that distinguish an ETF from its same-named operating parent, so
    # norm-exact and fuzzy would collapse "WisdomTree Trust" onto WT, "Invesco
    # Exch Trd" onto IVZ. A fund line is an ETF position, not a stock pick.
    if _is_fund_issuer(name):
        return None
    # normalised exact match (handles punctuation + corporate suffixes)
    nn = _norm_name(name)
    if nn and nn in name_map: return name_map[nn]
    # legacy suffix-strip
    cleaned = re.sub(r"\b(INC|CORP|CORPORATION|HOLDINGS?|GROUP|LTD|PLC|LP|LLC|CLASS\s+[A-Z]|COM|COMMON)\b", "", n).strip()
    if cleaned in name_map: return name_map[cleaned]
    # token match: a map key must be a leading prefix of the issuer AND cover most
    # of it (>=60%), so "INVESCO" (7) can't claim "INVESCO EXCH TRD" (16).
    for full_name, tkr in name_map.items():
        if (full_name and len(full_name) > 6
                and n.startswith(full_name) and len(full_name) >= 0.6 * len(n)):
            return tkr
    return None

def run(only=None, refresh=False):
    """Ingest each roster fund's newest non-empty 13F-HR.

    Default: only funds with no stored book, or whose roster CIK changed (a
    successor filer). refresh=True re-checks EVERY stored book against EDGAR
    and rolls it forward when a newer 13F-HR exists — the quarterly roll. Until
    this existed nothing did it with the ingest guards: in September 2026, 223
    funds still showed their Q1 book six weeks after Q2 13Fs were due."""
    conn = sqlite3.connect(DB, timeout=120); conn.execute("PRAGMA busy_timeout=120000")
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS fund_13f_holdings (
      fund TEXT, cik TEXT, accession TEXT, filed TEXT,
      issuer TEXT, cusip TEXT, ticker TEXT, value_k INTEGER, shares INTEGER,
      sh_type TEXT, pct_book REAL,
      PRIMARY KEY (fund, accession, cusip));
    CREATE INDEX IF NOT EXISTS idx_13f_ticker ON fund_13f_holdings(ticker);
    CREATE INDEX IF NOT EXISTS idx_13f_fund ON fund_13f_holdings(fund);
    CREATE TABLE IF NOT EXISTS fund_13f_state (
      fund TEXT PRIMARY KEY, cik TEXT, last_accession TEXT, last_filed TEXT,
      n_holdings INTEGER, total_value_k INTEGER, ingested_at TEXT);
    CREATE TABLE IF NOT EXISTS holding_sec_form (
      accession TEXT, cusip TEXT, title_class TEXT, sec_form TEXT,
      PRIMARY KEY (accession, cusip));
    CREATE TABLE IF NOT EXISTS fund_13f_prior (
      fund TEXT, cik TEXT, accession TEXT, filed TEXT,
      issuer TEXT, cusip TEXT, ticker TEXT, value_k INTEGER, shares INTEGER,
      sh_type TEXT, pct_book REAL,
      PRIMARY KEY (fund, accession, cusip));
    CREATE TABLE IF NOT EXISTS fund_13f_prior_state (
      fund TEXT PRIMARY KEY, accession TEXT, filed TEXT, n_holdings INTEGER, total_value_k INTEGER);
    """)

    print("loading SEC ticker map...")
    name_map = cusip_ticker_map(conn)
    print(f"  {len(name_map)} name-to-ticker mappings loaded")
    # CUSIP authority: persisted resolutions (OpenFIGI + consensus) checked FIRST,
    # so a once-resolved CUSIP is never re-lost to a name quirk and a fund vehicle
    # never re-maps onto an operating ticker. ticker may be None = known-unmappable.
    try:
        cusip_map = {c: (tk, st) for c, tk, st in
                     conn.execute("SELECT cusip, ticker, sec_type FROM cusip_map")}
    except sqlite3.OperationalError:
        cusip_map = {}
    print(f"  {len(cusip_map)} CUSIP-authority mappings loaded")
    try:
        px_map = {t: p for t, p in conn.execute(
            "SELECT ticker, price FROM ticker_yf WHERE price > 0")}
    except sqlite3.OperationalError:
        px_map = {}
    time.sleep(1)

    for name, label in FUND_STYLE_LABEL.items():
        src = "saved-searches-2026-09" if name in FUND_STYLE_LABEL_SAVED else "fmp-discovery-2026-09"
        conn.execute("INSERT OR IGNORE INTO fund_meta VALUES (?,?,?,?)", (name, label, src, 0))
        # code owns these label rows (a researcher-XLSX row is never touched):
        # an edited label must reach the DB, not be frozen by INSERT OR IGNORE
        conn.execute("""UPDATE fund_meta SET fund_group=?, source_block=? WHERE fund=? AND total_rows=0
                        AND source_block IN ('fmp-discovery-2026-09', 'saved-searches-2026-09')""",
                     (label, src, name))
    conn.commit()
    funds = [(name, str(cik)) for name, cik in FUND_CIK.items() if cik]
    if refresh:
        # every other stored book (researcher-XLSX funds resolved by the older
        # CIK resolvers) keeps its stored CIK. Resolver matches that were never
        # ingested stay out: several pointed at unrelated entities.
        funds += [(f, str(k)) for f, k in conn.execute(
            "SELECT fund, cik FROM fund_13f_state WHERE cik IS NOT NULL AND cik != ''")
            if f not in FUND_CIK]
    if only:
        only_set = set(only)
        funds = [f for f in funds if f[0] in only_set or any(o in f[0] for o in only_set)]
    print(f"\nfunds to process: {len(funds)}{' (refresh: every stored book re-checked)' if refresh else ''}")
    maps = (cusip_map, name_map, px_map)
    n_new = n_rolled = n_current = n_skipped = n_failed = n_holdings_total = 0
    for fund_name, cik in funds:
        stored = conn.execute("""SELECT cik, last_accession, last_filed, n_holdings, total_value_k
                                 FROM fund_13f_state WHERE fund=?""", (fund_name,)).fetchone()
        if stored and not stored[1]:
            stored = None
        repoint = bool(stored) and not _same_cik(stored[0], cik)
        if stored and not refresh and not repoint:
            n_skipped += 1
            continue
        filings = f13_filings(cik)
        if filings is None:
            print(f"  [!] {fund_name[:40]}: EDGAR index fetch failed — stored book kept, retried next run")
            n_failed += 1
            continue
        record_f13(conn, cik, filings)
        # Walk recent 13F-HRs newest-first. An EMPTY holdings report is still
        # that quarter's book: Eminence (Q2 2026), Indaba (Q1 and Q2 2026) and
        # Makaira (Q1 2026) filed $0 tables — they held no 13F securities —
        # and falling through to an older quarter showed their old positions
        # as current. Only a same-quarter re-file may stand in for an empty one.
        # Ordered by REPORT PERIOD, newest filing first within a period: a
        # restatement of an old quarter filed as a plain 13F-HR after the
        # current quarter's report must not become the "current" book.
        hrs = sorted((x for x in filings if x["form"] == "13F-HR"),
                     key=lambda x: (x["period"] or "", x["filed"], x["acc"]), reverse=True)[:3]
        stored_period = next((y["period"] for y in filings
                              if stored and y["acc"] == stored[1]), "") if not repoint else ""
        pick, fetch_failed = None, False
        for i, x in enumerate(hrs):
            if stored and not repoint and (x["acc"] == stored[1]
                                           or (stored_period and (x["period"] or "") < stored_period)):
                break                        # reached the stored book: nothing newer is usable
            rows = fetch_book(cik, x["acc"])
            if rows is None:
                fetch_failed = True          # never skip past a book we could not read
                break
            if rows or not any(y["period"] and y["period"] == x["period"] for y in hrs[i + 1:]):
                pick = (x, rows)
                break
            time.sleep(0.4)
        if not pick:
            if fetch_failed:
                print(f"  [!] {fund_name[:40]}: information table fetch failed — retried next run")
                n_failed += 1
            elif stored and not repoint:
                n_current += 1
            else:
                print(f"  [-] {fund_name[:40]}: no usable 13F-HR (empty/derivative-only/missing)")
            continue
        x, rows = pick
        if stored and not repoint and stored_period and (x["period"] or "") < stored_period:
            n_current += 1                   # never regress to an older quarter
            continue
        rolled = None
        if stored:
            rolled = roll_prior(conn, fund_name, cik, stored, x, maps)
            conn.execute("DELETE FROM fund_13f_holdings WHERE fund=?", (fund_name,))
        n, total_v = ingest_book(conn, "fund_13f_holdings", fund_name, cik, x["acc"], x["filed"],
                                 rows, *maps)
        conn.execute("""INSERT OR REPLACE INTO fund_13f_state VALUES
            (?,?,?,?,?,?,datetime('now'))""",
            (fund_name, cik, x["acc"], x["filed"], n, total_v))
        conn.commit()
        n_holdings_total += n
        empty = "  [EMPTY holdings report: no 13F securities held]" if not n else ""
        if stored:
            n_rolled += 1
            print(f"  ↻ {fund_name[:40]:<40} {stored[2]} → {x['filed']} ({x['period']})  {n} holdings  "
                  f"${total_v/1000:,.0f}M{'  [new filer CIK ' + cik + ']' if repoint else ''}  "
                  f"prior: {'previous book' if rolled else 'dropped, re-pulled by ingest_13f_prior'}{empty}")
        else:
            n_new += 1
            print(f"  ✓ {fund_name[:40]:<40} {n} holdings  ${total_v/1000:,.0f}M total ({x['period']}){empty}")
        time.sleep(0.3)  # polite throttle
    conn.commit()
    n_dormant, n_moved = archive_dormant(conn)
    print(f"\nDone: {n_new} new funds, {n_rolled} rolled to a newer filing, {n_current} already current, "
          f"{n_skipped} skipped (no refresh), {n_failed} fetch failures, {n_holdings_total} holdings written")
    print(f"  {n_dormant} dormant funds (no 13F-HR in {DORMANT_DAYS} days) kept out of the live book"
          f"{f' — {n_moved} lines moved to fund_13f_dormant' if n_moved else ''}")
    if n_failed:
        print(f"  ! {n_failed} funds could not be checked (SEC throttling?) — re-run to finish them")
    conn.close()
    return n_failed

if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if a != "--refresh"]
    refresh = "--refresh" in sys.argv[1:]
    only = args or None
    # nonzero when any fund could not be checked, so a chained rebuild stops
    # instead of rendering books with a silently partial quarter roll
    sys.exit(2 if run(only, refresh=refresh) else 0)
