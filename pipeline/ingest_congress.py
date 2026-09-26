"""Congressional trading — STOCK Act periodic transaction reports, via FMP.

Members of Congress (and their spouses / dependants) must disclose trades
within 45 days. FMP carries both chambers' reports: member, whose account
(Self / Spouse / Joint / Child), ticker, stock vs option, purchase vs sale,
the official dollar RANGE, trade and disclosure dates, and a link to the
original filing. This is insider-style information read with common sense,
no modelling:
  * several members independently buying the same name is the signal —
    one member's trade is an anecdote;
  * the member's OWN account or an option purchase shows more conviction
    than a spouse's managed account;
  * a disclosure later than the 45-day deadline is worth knowing;
  * amounts are ranges ($15,001 - $50,000): we keep both bounds and use the
    midpoint only for an order-of-magnitude total.

Table: congress_trades (one row per disclosed transaction, both chambers,
trailing two years). Key: env FMP_API_KEY / data/.fmp_key.
"""
import json, os, re, sqlite3, subprocess, sys, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from enrich_fmp import API, DB, api_key

LOOKBACK_DAYS = 730

def _get(path, **p):
    q = "&".join(f"{k}={v}" for k, v in p.items())
    url = f"{API}/{path}?{q}&apikey={api_key()}"
    for attempt in range(4):
        r = subprocess.run(["curl", "-sS", "--max-time", "60", url], capture_output=True, text=True)
        try:
            d = json.loads(r.stdout)
            if isinstance(d, list):
                return d
        except ValueError:
            pass
        time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"FMP {path} page {p.get('page')} failed after retries")

def amount_range(s):
    """'$15,001 - $50,000' -> (15001, 50000); 'Over $50,000,000' -> (50000000, None)."""
    nums = [float(x.replace(",", "")) for x in re.findall(r"\$\s*([\d,]+(?:\.\d+)?)", s or "")]
    if not nums:
        return None, None
    if len(nums) == 1:
        return (nums[0], None) if "over" in (s or "").lower() else (nums[0], nums[0])
    return nums[0], nums[1]

def fetch(chamber, cutoff):
    rows = []
    for page in range(0, 400):
        d = _get(f"{chamber}-latest", page=page, limit=250)
        if not d:
            break
        rows.extend(d)
        if min((x.get("disclosureDate") or "9999") for x in d) < cutoff:
            break                          # feed runs newest disclosure first
    return rows

def run():
    cutoff = time.strftime("%Y-%m-%d", time.gmtime(time.time() - LOOKBACK_DAYS * 86400))
    got = {ch: fetch(ch, cutoff) for ch in ("senate", "house")}
    out = {}
    for ch, rows in got.items():
        for x in rows:
            td = (x.get("transactionDate") or "")[:10]
            dd = (x.get("disclosureDate") or "")[:10]
            if not td or td < cutoff:
                continue
            lo, hi = amount_range(x.get("amount"))
            sym = (x.get("symbol") or "").strip().upper() or None
            member = " ".join(f"{x.get('firstName') or ''} {x.get('lastName') or ''}".split()) \
                or (x.get("office") or "")
            key = (ch, x.get("senateID") or member, sym, td, x.get("type"), lo, x.get("owner"),
                   x.get("link"), x.get("assetDescription"))
            # a blank owner on a House report is the member's own account
            owner = (x.get("owner") or "").strip() or "Self"
            out[key] = (ch, x.get("senateID"), member, x.get("district"), owner, sym,
                        x.get("assetType"), x.get("assetDescription"), x.get("type"),
                        lo, hi, x.get("amount"), td, dd, x.get("link"))
    if not out:
        raise SystemExit("no congressional trades fetched — keeping the existing table")
    # one clean name per member: FMP spells members differently across filings
    # ("Gilbert Cisneros" / "Gilbert Ray Cisneros"; "Scott Mr Franklin")
    from collections import Counter
    names = {}
    for v in out.values():
        clean = " ".join(w for w in v[2].split() if w.rstrip(".").lower() not in ("mr", "mrs", "ms", "dr", "hon"))
        names.setdefault(v[1] or v[2], Counter())[clean] += 1
    best = {k: max(c.items(), key=lambda kv: (kv[1], len(kv[0])))[0] for k, c in names.items()}
    out = {k: v[:2] + (best.get(v[1] or v[2], v[2]),) + v[3:] for k, v in out.items()}
    conn = sqlite3.connect(DB, timeout=120)
    conn.execute("PRAGMA busy_timeout=120000")
    conn.executescript("""
    DROP TABLE IF EXISTS congress_trades;
    CREATE TABLE congress_trades (
      chamber TEXT, member_id TEXT, member TEXT, district TEXT, owner TEXT,
      ticker TEXT, asset_type TEXT, asset_desc TEXT, type TEXT,
      amount_lo REAL, amount_hi REAL, amount_text TEXT,
      trans_date TEXT, disclosure_date TEXT, link TEXT);
    CREATE INDEX idx_congress_ticker ON congress_trades(ticker);
    """)
    conn.executemany("INSERT INTO congress_trades VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", out.values())
    conn.commit()
    n = conn.execute("""SELECT COUNT(*), COUNT(DISTINCT member_id), COUNT(DISTINCT ticker),
        MAX(disclosure_date) FROM congress_trades""").fetchone()
    buys = conn.execute("""SELECT COUNT(*) FROM congress_trades WHERE type = 'Purchase'
        AND asset_type IN ('Stock', 'Stock Option') AND trans_date >= date('now', '-180 days')""").fetchone()[0]
    print(f"congress_trades: {n[0]:,} disclosed trades by {n[1]} members in {n[2]:,} tickers "
          f"(latest disclosure {n[3]}); {buys:,} stock/option purchases in the last 180 days")
    conn.close()

if __name__ == "__main__":
    run()
