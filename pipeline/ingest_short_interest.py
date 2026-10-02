"""Short interest from FINRA (consolidated, every US-listed and OTC stock).

Brokers report short positions twice a month (the 15th and month end,
published about nine business days later). FINRA's public API serves each
settlement date as one partition. This loads the latest settlement and the
one about three months before it, so the books can say how crowded a short
is (short shares against shares outstanding, and days of average volume to
cover) and whether the bears are adding or leaving. No key needed.

Table short_interest(ticker, settlement_date, short_shares, prev_short_shares,
adv, days_to_cover, market) — both settlements kept.
"""
import datetime as dt
import json, os, sqlite3, subprocess, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

DB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "cyclepapa.db")
URL = "https://api.finra.org/data/group/otcMarket/name/consolidatedShortInterest"
FIELDS = ["symbolCode", "settlementDate", "currentShortPositionQuantity", "previousShortPositionQuantity",
          "averageDailyVolumeQuantity", "daysToCoverQuantity", "marketClassCode"]

def post(body):
    for attempt in range(5):
        out = subprocess.run(["curl", "-sS", "-m", "90", "-X", "POST", "-H", "Content-Type: application/json",
                              "-H", "Accept: application/json", URL, "-d", json.dumps(body)],
                             capture_output=True, text=True).stdout
        try:
            d = json.loads(out)
        except ValueError:
            time.sleep(5 * (attempt + 1))
            continue
        if isinstance(d, list):
            return d
        time.sleep(5 * (attempt + 1))
    return None

def settlement_candidates(today, days=150):
    """Settlement dates newest first: the 15th and the last business day of
    each month (a weekend date moves to the business day before)."""
    out, d = [], today
    while (today - d).days <= days:
        for day in (15, None):
            if day:
                x = dt.date(d.year, d.month, 15)
            else:
                nxt = dt.date(d.year + (d.month == 12), d.month % 12 + 1, 1)
                x = nxt - dt.timedelta(days=1)
            while x.weekday() >= 5:
                x -= dt.timedelta(days=1)
            if x <= today and x not in out:
                out.append(x)
        d = dt.date(d.year - (d.month == 1), (d.month - 2) % 12 + 1, 1)
    return sorted(out, reverse=True)

def fetch(date):
    rows, off = [], 0
    while True:
        page = post({"limit": 5000, "offset": off, "fields": FIELDS,
                     "compareFilters": [{"compareType": "EQUAL", "fieldName": "settlementDate",
                                         "fieldValue": date.isoformat()}]})
        if page is None:
            return None
        rows.extend(page)
        if len(page) < 5000:
            return rows
        off += 5000

def run():
    conn = sqlite3.connect(DB, timeout=120); conn.execute("PRAGMA busy_timeout=120000")
    conn.execute("""CREATE TABLE IF NOT EXISTS short_interest (
        ticker TEXT, settlement_date TEXT, short_shares REAL, prev_short_shares REAL, adv REAL,
        days_to_cover REAL, market TEXT, PRIMARY KEY (ticker, settlement_date))""")
    cands = settlement_candidates(dt.date.today())
    latest = None
    for d in cands:
        rows = fetch(d)
        if rows is None:
            print(f"  ! FINRA request failed for {d}"); return 2
        if rows:
            latest = (d, rows)
            break
    if not latest:
        print("  ! no FINRA settlement found in 150 days"); return 2
    older = None
    for d in cands:
        if (latest[0] - d).days >= 80:
            rows = fetch(d)
            if rows:
                older = (d, rows)
                break
    def ticker(sym):
        return (sym or "").replace(".", "-").replace("/", "-").strip()
    conn.execute("DELETE FROM short_interest")
    for d, rows in [x for x in (latest, older) if x]:
        conn.executemany("INSERT OR REPLACE INTO short_interest VALUES (?,?,?,?,?,?,?)",
                         [(ticker(r.get("symbolCode")), d.isoformat(), r.get("currentShortPositionQuantity"),
                           r.get("previousShortPositionQuantity"), r.get("averageDailyVolumeQuantity"),
                           r.get("daysToCoverQuantity"), r.get("marketClassCode")) for r in rows if r.get("symbolCode")])
    conn.commit()
    held = conn.execute("""SELECT COUNT(*) FROM short_interest s JOIN unified_signal u ON u.ticker = s.ticker
        WHERE s.settlement_date = ? AND u.sec_type = 'common'""", (latest[0].isoformat(),)).fetchone()[0]
    print(f"short interest: {len(latest[1]):,} securities settled {latest[0]}"
          f"{f', {len(older[1]):,} settled {older[0]} for the 3-month change' if older else ''}; "
          f"{held:,} of them common stocks in the books", flush=True)
    conn.close()
    return 0

if __name__ == "__main__":
    sys.exit(run())
