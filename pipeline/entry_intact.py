"""Entry-Intact scoring — high conviction × stock not moved from entry.

For each ticker with material conviction, estimate the fund's effective entry
price using three independent sources (in priority order):

  1. Explicit $X anchor in raw_text (e.g. "anchored $86 follow-on",
     "PIPE at $4.44", "Ackman $100 cost basis")
  2. Verified EDGAR Form-4 insider P-buy price within the last 180 days
     (institutional adds often cluster around insider buying windows)
  3. 1-yr price ANCHOR proxy = 80th percentile close — funds tend to build
     mid-cycle, not at extremes; gives a defensible "they probably bought
     around here" benchmark

vs_entry_pct = (current_price / entry_anchor - 1) * 100

Output: ticker_entry_intact joining conviction score × vs-entry status.
The bucket users will care about: NEAR_OR_BELOW_ENTRY with high conviction.
"""
import os, re, sqlite3
DB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "cyclepapa.db")

# $ amount token. Group 2 captures a magnitude suffix (M/B/K/million…) — when
# present the figure is a POSITION VALUE ("$6.30M", "$50.1M"), NOT a per-share
# price, and must be rejected (this was the cause of absurd "+387% vs entry":
# Cipher's $6.30M stake parsed as a $6 entry vs $29 price).
MONEY_RE = re.compile(r"(?<![\d.])\$\s?(\d{1,4}(?:\.\d{1,2})?)\s*([MBK]|mm|bn|mn|million|billion|thousand)?\b", re.I)
# context words near an entry anchor (filters out target prices / sums)
ENTRY_CTX = re.compile(r"\b(at|cost|basis|anchored|PIPE|follow[\s-]?on|offering|financing|@|bought|purchas|priced)\b", re.I)
TARGET_CTX = re.compile(r"\b(PT|target|upside|to\s+\$|reaches|valued|peak)\b", re.I)

def extract_anchors(text):
    """Return list of plausible per-share entry prices from raw_text.
    Rejects magnitude-suffixed dollar amounts (position values) and percentages."""
    out = []
    if not text: return out
    for m in MONEY_RE.finditer(text):
        if m.group(2):                      # $NM / $N billion = position size, skip
            continue
        ctx = text[max(0, m.start()-40):m.end()+20]
        if TARGET_CTX.search(ctx) and not ENTRY_CTX.search(ctx):
            continue
        try:
            v = float(m.group(1))
            if 0.10 <= v <= 4000:
                out.append(v)
        except ValueError:
            pass
    return out

def run():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    conn.executescript("""
    DROP TABLE IF EXISTS ticker_entry_intact;
    CREATE TABLE ticker_entry_intact (
      ticker TEXT PRIMARY KEY,
      current_px REAL, anchor_px REAL, anchor_source TEXT,
      vs_entry_pct REAL, bucket TEXT,
      conviction_score REAL, n_funds INTEGER,
      n_hyper INTEGER, has_insider_cobuy INTEGER, sum_dollar_m REAL,
      anchors_seen TEXT);
    """)

    # candidate tickers = anything with a conviction score
    tickers = [r["ticker"] for r in conn.execute(
        "SELECT ticker FROM ticker_conviction WHERE score >= 6 ORDER BY score DESC")]

    # source 0: explicit cost_basis from the candidates table (highest trust)
    anchors_by_ticker = {}
    for r in conn.execute("SELECT ticker, known_issues FROM candidates"):
        if not r["known_issues"]: continue
        for px in extract_anchors(r["known_issues"]):
            anchors_by_ticker.setdefault(r["ticker"], []).append(("candidates", px))

    # source 1: explicit anchors from raw_text per (fund, ticker)
    for r in conn.execute("""SELECT ticker, raw_text FROM fund_positions
                             WHERE ticker IN ({})""".format(",".join("?"*len(tickers))), tickers):
        for px in extract_anchors(r["raw_text"]):
            anchors_by_ticker.setdefault(r["ticker"], []).append(("raw_text", px))

    # source 2: Form-4 P-buy avg price (last 180d) per ticker
    for r in conn.execute("""SELECT ticker, AVG(price) AS px, COUNT(*) AS n
                             FROM form4_transactions
                             WHERE code='P' AND acquired=1 AND price > 0
                             AND julianday('now') - julianday(trans_date) <= 180
                             GROUP BY ticker"""):
        anchors_by_ticker.setdefault(r["ticker"], []).append(("form4_p_buy", r["px"]))

    # source 3: 1-yr 80th-pctile close per ticker that has prices
    for tkr in tickers:
        rows = [r["close"] for r in conn.execute(
            "SELECT close FROM prices WHERE ticker=? ORDER BY date", (tkr,))]
        if len(rows) < 20: continue
        s = sorted(rows)
        p80 = s[int(len(s) * 0.80)]
        anchors_by_ticker.setdefault(tkr, []).append(("p80_close", p80))

    # current price — prices-table close, OVERLAID with ticker_yf.price where
    # available (the yfinance enrich runs more recently than the prices ingest,
    # so yf is the fresher quote; the prices table only covers ~800 tickers and
    # can lag by weeks, which skewed every vs-entry % it fed).
    last_px = {r["ticker"]: r["close"] for r in conn.execute(
        "SELECT ticker, close FROM prices WHERE date = (SELECT MAX(date) FROM prices p2 WHERE p2.ticker = prices.ticker)")}
    for r in conn.execute("SELECT ticker, price FROM ticker_yf WHERE price > 0"):
        last_px[r["ticker"]] = r["price"]

    rows = []
    for tkr in tickers:
        cur = last_px.get(tkr)
        if not cur: continue
        anchors = anchors_by_ticker.get(tkr, [])
        if not anchors: continue
        # priority: candidates cost_basis > raw_text > form4 > p80. Use the first
        # source with a PLAUSIBLE anchor; a parsed price implying >+150%/<-60% vs
        # today is almost always a mis-parse (or an ancient entry), so fall to the
        # next source — p80_close (a real price-derived proxy) is the safety net.
        anchor = top_src = None
        for src in ("candidates", "raw_text", "form4_p_buy", "p80_close"):
            pxs = sorted(px for s, px in anchors if s == src and 0.40 <= (px / cur) <= 2.5)
            if pxs:
                anchor = pxs[len(pxs) // 2]; top_src = src; break
        if anchor is None:
            continue
        vs = (cur / anchor - 1) * 100

        if vs <= -15:    bucket = "BELOW_ENTRY"
        elif vs <= 15:   bucket = "NEAR_ENTRY"
        elif vs <= 40:   bucket = "MODERATELY_ABOVE"
        else:            bucket = "WELL_ABOVE"

        cv = conn.execute(
            "SELECT score,n_funds,n_hyper,has_insider_cobuy,sum_dollar_m FROM ticker_conviction WHERE ticker=?",
            (tkr,)).fetchone()
        if not cv: continue
        anchors_seen = "; ".join(f"{src}={px}" for src, px in anchors[:5])
        rows.append((tkr, round(cur,2), round(anchor,2), top_src, round(vs,1), bucket,
                     cv["score"], cv["n_funds"], cv["n_hyper"], cv["has_insider_cobuy"],
                     cv["sum_dollar_m"], anchors_seen))
        conn.execute("""INSERT INTO ticker_entry_intact VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                     rows[-1])
    conn.commit()

    rows.sort(key=lambda r: (-r[6], r[4]))  # high conviction first, then most below entry
    print("HIGH-CONVICTION × NEAR-OR-BELOW ENTRY (ex mega-caps):")
    print(f"{'tkr':<7} {'cur':<8} {'anchor':<8} {'src':<14} {'vs%':<7} {'bucket':<18} {'score':<6} {'funds':<6} {'hyp':<4} {'cobuy':<6} {'$M':<8}")
    mega = {"AMZN","MSFT","GOOGL","GOOG","NVDA","META","AAPL","TSLA","SPY","QQQ","IWM","IVV","IEF","BABA","TSM","BAC","BRK.B","BRK.A","NFLX","JPM","CRM","JNJ","WMT","H2","SEC"}
    for r in rows:
        if r[0] in mega: continue
        if r[5] not in ("BELOW_ENTRY", "NEAR_ENTRY"): continue
        print(f"  {r[0]:<7} {r[1]:<8} {r[2]:<8} {r[3]:<14} {r[4]:<+7.1f} {r[5]:<18} {r[6]:<6} {r[7]:<6} {r[8]:<4} "
              f"{'Y' if r[9] else '':<6} ${r[10]:<7.0f}")

    print(f"\nBucket counts:")
    for b, n in conn.execute("SELECT bucket, COUNT(*) FROM ticker_entry_intact GROUP BY bucket ORDER BY bucket"):
        print(f"  {b:<22} {n}")

if __name__ == "__main__":
    run()
