"""Ingest the LAST 13F-HR for funds that stopped filing.

Schultze, Lawndale, R.G. Niederhoffer, Tiburon and similar historical
filers stopped submitting 13F-HR years ago (defunct or AUM dropped
below threshold) but they DID file before. Pull their LAST 13F-HR so
we have at least one snapshot — better than no data at all.

Stored with section=6 (historical) so conviction can weight them down.
"""
import json, os, re, sqlite3, subprocess, sys, time

DB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "cyclepapa.db")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ingest_13f import find_infotable, parse_infotable, curl, cusip_ticker_map, name_to_ticker

UA = "cyclepapa-research admin@example.com"

def all_13f_filings(cik):
    """Walk recent + older filings JSON for ALL 13F-HR accession numbers."""
    cik10 = cik.zfill(10)
    out = []
    data = curl(f"https://data.sec.gov/submissions/CIK{cik10}.json")
    if not data: return []
    try: d = json.loads(data)
    except: return []
    rec = d.get("filings", {}).get("recent", {})
    for i, form in enumerate(rec.get("form", [])):
        if form == "13F-HR":
            out.append((rec["accessionNumber"][i], rec["filingDate"][i]))
    # also walk older filing-files
    for f in d.get("filings", {}).get("files", []):
        if "file13" not in f.get("name", "").lower() and not f.get("name","").startswith("CIK"):
            continue
        sub_url = f"https://data.sec.gov/submissions/{f['name']}"
        sub_body = curl(sub_url)
        try:
            sj = json.loads(sub_body)
            for i, form in enumerate(sj.get("form", [])):
                if form == "13F-HR":
                    out.append((sj["accessionNumber"][i], sj["filingDate"][i]))
        except: pass
        time.sleep(0.2)
    return out

CIKS = [
    ("Lawndale Capital Management", "1318019"),
    ("R.G. Niederhoffer Capital", "1216800"),
    ("Schultze Asset Management",  "1297629"),
    ("Tiburon Holdings",            "1593514"),
    ("Avenue Capital Group",        "1002858"),
    ("Cascade Investment LLC",      "1052192"),
    ("Crescendo Partners",          "1219602"),
    ("Old Farm Partners",           "1606457"),
    ("Argyle Street Management",    "1361036"),
]

def run():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    print("loading SEC ticker map...")
    name_map = cusip_ticker_map(conn)
    print(f"  {len(name_map)} mappings\n")
    n_total = 0
    for fund_prefix, cik in CIKS:
        # find canonical fund_meta name
        r = conn.execute("SELECT fund FROM fund_meta WHERE fund LIKE ? LIMIT 1",
                         (fund_prefix+"%",)).fetchone()
        if not r:
            print(f"  ? no fund_meta for '{fund_prefix}'")
            continue
        fund = r[0]
        filings = all_13f_filings(cik)
        time.sleep(0.5)
        if not filings:
            print(f"  - {fund[:35]:<35} no 13F-HR found")
            continue
        # pick the LATEST (filings are usually sorted newest first)
        acc, filed = filings[0]
        path = find_infotable(cik, acc)
        url = path if path.startswith("http") else f"https://www.sec.gov{path}"
        body = curl(url)
        rows = parse_infotable(body) if body else []
        if not rows:
            print(f"  - {fund[:35]:<35} parse failed for {acc}")
            continue
        # Insert into fund_positions section=6 (historical) so conviction picks them up
        for rr in rows[:50]:  # cap at top 50 to avoid noise
            tkr = name_to_ticker(rr["issuer"], name_map)
            if not tkr: continue
            raw = f"historical_13f | CIK={cik} | acc={acc} | filed={filed}"
            conn.execute("""INSERT INTO fund_positions
                (fund, ticker, company, section, pct_value, pct_kind, dollar_m,
                 change_text, event_date, raw_text, asof) VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (fund, tkr, rr["issuer"][:60], 6, None, None, None,
                 f"historical_13f_{filed}", filed, raw[:300], "2026-06-20"))
            n_total += 1
        conn.commit()
        print(f"  ✓ {fund[:35]:<35} {len(rows)} holdings from {filed}")
        time.sleep(0.3)
    print(f"\ningested {n_total} historical-filer positions")

if __name__ == "__main__":
    run()
