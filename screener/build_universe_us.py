"""
Rebuild universe_us.csv from live GitHub sources (both repos auto-update).
Run monthly or before any full screen: python build_universe_us.py
Sources:
  rreichel3/US-Stock-Symbols  — full NYSE/NASDAQ/AMEX ticker lists
  datasets/s-and-p-500-companies — S&P 500 constituents with GICS sectors
"""
import csv, io, re, urllib.request

RAW = "https://raw.githubusercontent.com"
SRC = {ex: f"{RAW}/rreichel3/US-Stock-Symbols/main/{ex}/{ex}_tickers.txt"
       for ex in ("nyse", "nasdaq", "amex")}
SP500 = f"{RAW}/datasets/s-and-p-500-companies/main/data/constituents.csv"

def fetch(url: str) -> str:
    with urllib.request.urlopen(url, timeout=30) as r:
        return r.read().decode()

def clean(sym: str) -> str | None:
    sym = sym.strip().upper()
    if not sym or len(sym) > 6:
        return None
    if re.search(r'[\^/$]', sym):
        return None
    if re.search(r'(W|WS|U|R)$', sym) and len(sym) >= 5:   # warrants/units/rights
        return None
    return sym.replace('.', '-')                            # BRK.B -> BRK-B

def main():
    sp = {}
    for row in csv.DictReader(io.StringIO(fetch(SP500))):
        sp[row['Symbol'].strip()] = (row['Security'], row['GICS Sector'])

    rows, seen = [], set()
    for ex, url in SRC.items():
        for line in fetch(url).splitlines():
            s = clean(line)
            if not s or s in seen:
                continue
            seen.add(s)
            name, sector = sp.get(line.strip(), ('', ''))
            rows.append({'ticker': s, 'exchange': ex.upper(),
                         'index_tag': 'SP500' if line.strip() in sp else '',
                         'name': name, 'sector': sector})

    with open('universe_us.csv', 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=['ticker', 'exchange', 'index_tag',
                                          'name', 'sector'])
        w.writeheader()
        w.writerows(rows)
    print(f"universe_us.csv rebuilt: {len(rows)} tickers "
          f"({sum(1 for r in rows if r['index_tag'])} S&P 500 tagged)")

if __name__ == '__main__':
    main()
