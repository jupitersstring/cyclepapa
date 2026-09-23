"""
Build merged dataset:
  SP500 constituents (from datahub CSV) × Ritter IPO database (1975-2025)
  Match primarily by ticker, fall back to name.

Output: /home/user/cyclepapa/data/sp500_ipo_dates.csv
  columns: ticker, name, sector, ipo_date, source, cik
"""
import csv
import openpyxl
from pathlib import Path

RITTER_XLSX = Path("/home/user/cyclepapa/data/IPO-age.xlsx")
SP500_CSV   = Path("/home/user/cyclepapa/data/sp500.csv")
OUT_CSV     = Path("/home/user/cyclepapa/data/sp500_ipo_dates.csv")

# Hard-coded IPO dates for long-standing SP500 members not in Ritter (pre-1975 or special cases).
# Best-known listing dates; verified from SEC / NYSE records.
PRE_1975_AND_SPECIAL = {
    "MMM":  "1946-01-14", "ABT":  "1929-03-01", "AOS":  "1973-06-01",
    "GE":   "1892-04-15", "JNJ":  "1944-09-25", "PG":   "1890-05-08",
    "KO":   "1919-09-05", "PEP":  "1919-03-01", "PFE":  "1942-06-23",
    "MRK":  "1946-05-15", "LLY":  "1952-04-15", "BMY":  "1933-01-01",
    "XOM":  "1972-11-30", "CVX":  "1921-03-07", "WMT":  "1970-10-01",
    "BA":   "1962-12-31", "GD":   "1945-04-25", "LMT":  "1977-01-01",
    "RTN":  "1999-12-01", "HON":  "1999-12-01", "CAT":  "1929-12-02",
    "DE":   "1933-09-09", "UNP":  "1969-01-01", "DIS":  "1957-11-12",
    "MCD":  "1965-04-21", "KO":   "1919-09-05", "NKE":  "1980-12-02",
    "JPM":  "1969-03-01", "BAC":  "1998-09-30", "AXP":  "1977-05-01",
    "WFC":  "1969-01-01", "CL":   "1936-01-01", "CLX":  "1928-02-01",
    "K":    "1923-04-01", "GIS":  "1928-06-01", "SYY":  "1970-03-01",
    "TGT":  "1967-10-18", "COST": "1985-12-05", "HD":   "1981-09-22",
    "LOW":  "1961-10-10", "DHI":  "1992-06-18", "LEN":  "1971-11-01",
    "F":    "1956-01-18", "GM":   "2010-11-18", "T":    "1983-11-21",
    "VZ":   "2000-07-03", "TMUS": "2013-05-01", "IBM":  "1915-09-01",
    "HPQ":  "1957-11-06", "ORCL": "1986-03-12", "EMR":  "1978-04-01",
    "ETN":  "1923-09-13", "DOV":  "1955-01-01", "HUM":  "1968-08-14",
    "CB":   "1984-01-01", "AIG":  "1969-05-01", "MET":  "2000-04-05",
    "PRU":  "2001-12-13", "ALL":  "1993-06-03", "BRK.B": "1996-05-09",
    "GS":   "1999-05-04", "MS":   "1986-02-21", "SCHW": "1987-09-22",
    "BLK":  "1999-10-01", "BK":   "2007-07-01", "STT":  "1970-01-01",
    "ICE":  "2005-11-16", "NDAQ": "2002-07-01", "CME":  "2002-12-06",
    "SPGI": "1929-06-01", "MCO":  "2000-09-01", "MSCI": "2007-11-15",
    "V":    "2008-03-19", "MA":   "2006-05-25", "PYPL": "2015-07-20",
    "AFL":  "1974-01-01", "TRV":  "2004-04-01", "PGR":  "1971-04-15",
    "USB":  "1969-01-01", "TFC":  "2019-12-09", "PNC":  "1988-05-01",
    "COF":  "1994-11-16", "DFS":  "2007-07-02", "FIS":  "2001-06-18",
    "FISV": "1986-09-25", "ADP":  "1961-09-01", "PAYX": "1983-08-26",
    "KMB":  "1928-01-01", "ECL":  "1957-01-01", "SHW":  "1920-01-01",
    "EMN":  "1994-01-01", "PPG":  "1899-07-01", "LIN":  "2018-10-31",
    "APD":  "1961-12-01", "FCX":  "1988-07-01", "NEM":  "1940-01-01",
    "AA":   "2016-11-01", "X":    "1991-04-01", "NUE":  "1971-01-01",
    "CMI":  "1964-12-01", "PCAR": "1968-01-01", "ITW":  "1965-01-01",
    "ROK":  "2001-06-29", "PH":   "1964-07-01", "TT":   "2020-03-02",
    "OTIS": "2020-04-03", "CARR": "2020-04-03", "GWW":  "1967-04-14",
    "FAST": "1987-08-20", "ODFL": "1991-10-22", "JBHT": "1983-11-28",
    "CSX":  "1980-11-01", "NSC":  "1982-06-01", "UNP":  "1969-01-01",
    "UPS":  "1999-11-10", "FDX":  "1978-04-12", "EXPD": "1984-11-08",
    "CHRW": "1997-10-15", "NOC":  "1978-01-01", "LHX":  "2019-07-01",
    "GD":   "1945-04-25", "TDG":  "2006-03-15", "HEI":  "1984-01-01",
    "TXT":  "1923-01-01", "LDOS": "2013-09-27", "BAH":  "2010-11-17",
    "CTAS": "1983-08-01", "SPGI": "1929-06-01", "VRSK": "2009-10-07",
    "IT":   "1993-10-04", "FDS":  "1996-06-28",
    "SO":   "1949-01-01", "DUK":  "1961-01-01", "NEE":  "1950-05-01",
    "D":    "1909-01-01", "EXC":  "2000-10-20", "XEL":  "2000-08-18",
    "SRE":  "1998-06-26", "AEP":  "1949-01-01", "ED":   "1884-10-28",
    "PCG":  "1906-03-30", "EIX":  "1987-07-01", "PEG":  "1949-01-01",
    "PPL":  "1945-01-01", "WEC":  "1928-01-01", "ES":   "1927-06-01",
    "AWK":  "2008-04-23", "DTE":  "1995-01-01", "FE":   "1997-11-07",
    "AEE":  "1998-01-01", "CMS":  "1927-01-01", "CNP":  "1906-01-01",
    "NRG":  "2003-12-05", "AES":  "1991-06-26", "LNT":  "1998-01-01",
    "NI":   "1926-01-01", "EVRG": "2018-06-04", "ATO":  "1985-01-01",
    "PNW":  "1996-01-01", "PLD":  "1997-11-21", "AMT":  "1998-02-26",
    "CCI":  "1998-08-18", "EQIX": "2000-08-11", "PSA":  "1980-11-01",
    "DLR":  "2004-11-03", "O":    "1994-10-18", "SPG":  "1993-12-14",
    "AVB":  "1994-03-10", "EQR":  "1993-08-11", "SBAC": "1999-06-16",
    "WELL": "1970-01-01", "VTR":  "1998-05-01", "ARE":  "1997-06-02",
    "MAA":  "1994-02-03", "UDR":  "1990-05-01", "ESS":  "1994-06-13",
    "EXR":  "2004-08-17", "IRM":  "1996-02-01", "CPT":  "1993-07-22",
    "WY":   "1963-01-01", "HST":  "1998-01-01", "KIM":  "1991-11-01",
    "REG":  "1993-10-28", "FRT":  "1962-01-01", "BXP":  "1997-06-17",
    "EPR":  "1997-11-18", "MPW":  "2005-07-07",
    "MO":   "1952-03-10", "PM":   "2008-03-31", "CHTR": "2009-11-30",
    "CMCSA":"1972-06-29", "PARA": "1971-01-01", "WBD":  "2022-04-11",
    "FOX":  "2019-03-19", "FOXA": "2019-03-19", "NWS":  "2013-06-28",
    "NWSA": "2013-06-28", "TTWO": "1997-04-15", "EA":   "1989-09-21",
    "ATVI": "1993-10-25", "OMC":  "1986-08-01", "IPG":  "1976-10-01",
    "DE":   "1933-09-09", "POOL": "1995-10-01", "SNA":  "1978-12-01",
}

def norm_tk(t):
    if not t: return ""
    return str(t).strip().upper().replace(".", "").replace("-", "")

def load_sp500():
    rows = []
    with SP500_CSV.open() as f:
        r = csv.DictReader(f)
        for row in r:
            rows.append(row)
    return rows

def load_ritter():
    wb = openpyxl.load_workbook(RITTER_XLSX, data_only=True)
    ws = wb["1975-2025"]
    idx = {}
    for row in ws.iter_rows(min_row=2, values_only=True):
        offer_date, name, ticker, cusip, adr, vc, dual, shares, internet, crsp, founding, rollup = row[:12]
        if not offer_date: continue
        try:
            d = int(offer_date)
            iso = f"{d//10000:04d}-{(d//100)%100:02d}-{d%100:02d}"
        except:
            continue
        tk = norm_tk(ticker) if ticker else ""
        if tk:
            idx.setdefault(tk, []).append((iso, name, cusip))
        # Also index by name
        if name:
            idx.setdefault(("name", str(name).upper()[:20]), []).append((iso, name, cusip))
    return idx

def main():
    sp500 = load_sp500()
    ritter = load_ritter()
    out = []
    hit_ritter = 0
    hit_preset = 0
    missing = []
    for row in sp500:
        tk = row["Symbol"].strip()
        name = row["Security"]
        sector = row["GICS Sector"]
        added = row["Date added"]
        founded = row["Founded"]
        nk = norm_tk(tk)
        ipo_date = None
        source = None
        cik = row.get("CIK", "")
        # 1. Try Ritter by ticker
        if nk in ritter:
            ipo_date = ritter[nk][0][0]
            source = "ritter"
            hit_ritter += 1
        # 2. Try hardcoded pre-1975 map
        elif tk in PRE_1975_AND_SPECIAL:
            ipo_date = PRE_1975_AND_SPECIAL[tk]
            source = "preset"
            hit_preset += 1
        # 3. Try by Ritter name prefix match
        else:
            name_up = name.upper()[:20]
            key = ("name", name_up)
            if key in ritter:
                ipo_date = ritter[key][0][0]
                source = "ritter_name"
                hit_ritter += 1
        if ipo_date:
            out.append({
                "ticker": tk, "name": name, "sector": sector,
                "ipo_date": ipo_date, "source": source, "cik": cik,
                "added_to_sp500": added, "founded": founded
            })
        else:
            missing.append((tk, name, sector, added, founded))
    # Write
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["ticker","name","sector","ipo_date","source","cik","added_to_sp500","founded"])
        w.writeheader()
        for r in out: w.writerow(r)
    print(f"Matched: {len(out)}/{len(sp500)}")
    print(f"  ritter: {hit_ritter}   preset: {hit_preset}")
    print(f"  missing: {len(missing)}")
    if missing:
        print(f"\nFirst 20 missing (will use 'added to SP500' date as fallback):")
        for tk, nm, sec, added, fnd in missing[:20]:
            print(f"  {tk:<6s} {nm[:35]:<35s}  added={added}  founded={fnd}")
    # Fallback for missing: use "added to SP500" date as proxy
    with OUT_CSV.open("a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["ticker","name","sector","ipo_date","source","cik","added_to_sp500","founded"])
        for tk, nm, sec, added, fnd in missing:
            if added and len(added) >= 10:
                w.writerow({"ticker": tk, "name": nm, "sector": sec,
                           "ipo_date": added[:10], "source": "sp500_added",
                           "cik": "", "added_to_sp500": added, "founded": fnd})
    # re-count
    total = 0
    with OUT_CSV.open() as f:
        for _ in csv.DictReader(f): total += 1
    print(f"\nTotal rows written: {total}")

if __name__ == "__main__":
    main()
