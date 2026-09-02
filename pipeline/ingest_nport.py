"""N-PORT-P monthly holdings — fresher-than-13F, and it shows FOREIGN names.

Registered funds file Form N-PORT-P monthly (disclosed on a rolling basis,
~60-day lag). Unlike a 13F it (a) refreshes monthly, (b) reports the fund's
FOREIGN listings too (Sequoia's Rolls-Royce, Eurofins), which 13F omits. One
N-PORT-P = one series (fund); a fund family's trust files several. We read a
curated set of trusts known for star single-manager funds, auto-label each
filing by its <seriesName>, and store the top holdings.

Stored SEPARATELY in nport_holdings (this is RIC data, monthly, not 13F) and
never counted as 13F smart money. It supplements the freshness/foreign gaps.
"""
import json, os, re, sqlite3, subprocess, sys, time

DB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "cyclepapa.db")
UA = "cyclepapa-research admin@example.com"

# Trusts whose series include marquee single-manager equity funds (registrant
# CIKs verified to file NPORT-P for the named equity series).
TRUSTS = {
    "89043":   "Sequoia Fund (Ruane Cunniff)",
    "1293967": "PRIMECAP Odyssey Funds",
    "1217673": "Baron Select Funds",
    "71701":   "Davis New York Venture (Chris Davis)",
}
TOP_N = 40      # keep each series' top-N holdings by value
# Skip leveraged/index/bond/commodity series that share a trust with equity funds.
SKIP_SERIES = re.compile(
    r"direxion|bull|bear|index|treasury|commodit|liquid asset|money market|"
    r"tactical income|ultra|inverse|bond fund|govt|municipal", re.I)

def curl(url, t=40):
    return subprocess.run(["curl", "-sk", "--compressed", "-m", str(t), "-A", UA, url],
                          capture_output=True).stdout

def latest_nport_accs(cik, k=8):
    d = json.loads(curl(f"https://data.sec.gov/submissions/CIK{int(cik):010d}.json").decode() or "{}")
    rec = d.get("filings", {}).get("recent", {})
    out = []
    for i in range(len(rec.get("form", []))):
        if rec["form"][i] in ("NPORT-P", "NPORT-P/A"):
            out.append((rec["accessionNumber"][i], rec["filingDate"][i]))
        if len(out) >= k:
            break
    return out

def parse_nport(cik, acc):
    accn = acc.replace("-", "")
    body = curl(f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accn}/primary_doc.xml").decode("utf-8", "ignore")
    if "<invstOrSec>" not in body:
        return None, []
    sname = re.search(r"<seriesName>([^<]+)</seriesName>", body)
    series = sname.group(1).strip() if sname else None
    rows = []
    for b in re.findall(r"<invstOrSec>.*?</invstOrSec>", body, re.S):
        nm = re.search(r"<name>([^<]+)</name>", b)
        v = re.search(r"<valUSD>([\d\.]+)</valUSD>", b)
        tk = re.search(r"<ticker[^>]*>([^<]+)</ticker>", b)
        cu = re.search(r"<cusip>([^<]+)</cusip>", b)
        pctv = re.search(r"<pctVal>([\-\d\.]+)</pctVal>", b)
        if nm and v:
            rows.append({"issuer": nm.group(1).strip()[:60],
                         "ticker": (tk.group(1).strip().upper() if tk else None),
                         "cusip": (cu.group(1).strip() if cu else None),
                         "val_usd": float(v.group(1)),
                         "pct": float(pctv.group(1)) if pctv else None})
    rows.sort(key=lambda r: -r["val_usd"])
    return series, rows[:TOP_N]

def run():
    conn = sqlite3.connect(DB, timeout=60); conn.execute("PRAGMA busy_timeout=60000")
    conn.executescript("""
    DROP TABLE IF EXISTS nport_holdings;
    CREATE TABLE nport_holdings (
      trust TEXT, series TEXT, filed TEXT, issuer TEXT, ticker TEXT,
      cusip TEXT, val_usd REAL, pct REAL);
    CREATE INDEX idx_nport_tk ON nport_holdings(ticker);
    CREATE INDEX idx_nport_series ON nport_holdings(series);
    """)
    # CUSIP authority to fill tickers N-PORT leaves blank
    cmap = {c: t for c, t in conn.execute(
        "SELECT cusip, ticker FROM cusip_map WHERE ticker IS NOT NULL")}
    n_series = 0
    for cik, label in TRUSTS.items():
        seen_series = set()
        for acc, filed in latest_nport_accs(cik, k=12):
            series, rows = parse_nport(cik, acc)
            if not rows or series in seen_series:
                continue
            if series and SKIP_SERIES.search(series):
                continue        # not a single-manager equity fund
            seen_series.add(series)
            for r in rows:
                tk = r["ticker"] or cmap.get(r["cusip"])
                conn.execute("INSERT INTO nport_holdings VALUES (?,?,?,?,?,?,?,?)",
                             (label, series or label, filed, r["issuer"], tk,
                              r["cusip"], r["val_usd"], r["pct"]))
            n_series += 1
            print(f"  {label[:24]:26s} | {(series or '?')[:34]:36s} {filed}  {len(rows)} holdings", flush=True)
            time.sleep(0.3)
        conn.commit()
        time.sleep(0.3)
    tot = conn.execute("SELECT COUNT(*), COUNT(DISTINCT series) FROM nport_holdings").fetchone()
    print(f"DONE: {tot[0]} holdings across {tot[1]} fund series", flush=True)
    # foreign names 13F would miss
    print("\ntop foreign/ADR holdings captured (not in 13F):")
    for r in conn.execute("""SELECT series, issuer, ROUND(val_usd/1e6,1) FROM nport_holdings
        WHERE ticker IS NULL AND val_usd > 5e7 ORDER BY val_usd DESC LIMIT 12"""):
        print(f"  {r[0][:28]:30s} {r[1][:34]:36s} ${r[2]}M")
    conn.close()

if __name__ == "__main__":
    run()
