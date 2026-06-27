"""Convert foreign-listing absolute-dollar fields in ticker_yf to USD.

yfinance returns marketCap / enterpriseValue / ebitda / debt / cash / price in
each listing's NATIVE currency. enrich_yfinance.py divided by 1e6 but never
FX-converted, so e.g. a Korean (.KS) mcap was left in KRW millions — showing
absurd USD figures. Valuation RATIOS (EV/EBITDA, P/B, P/E) are currency-neutral
and were always correct; only the absolute magnitudes were wrong.

This pass:
  - finds every non-USD currency in ticker_yf (excluding the manually-ingested
    frontier rows, whose values were already entered in USD),
  - fetches the live FX rate (USD per 1 unit) from Yahoo, with a static
    fallback and minor-unit handling (GBp/GBX pence, ZAc cents, ILA agorot),
  - multiplies the absolute-$ columns by the rate and stamps currency='USD'
    so re-runs don't double-convert.

Run AFTER enrich_yfinance / enrich_summaries, BEFORE unified_score, so the
recomputed mcap buckets use USD.
"""
import os, sqlite3, time

DB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "cyclepapa.db")
CA = "/root/.ccr/ca-bundle.crt"
os.environ.setdefault("REQUESTS_CA_BUNDLE", CA)
os.environ.setdefault("SSL_CERT_FILE", CA)
import requests, yfinance as yf

# minor-unit currencies: (major pair currency, divisor)
MINOR = {"GBp": ("GBP", 100.0), "GBX": ("GBP", 100.0),
         "ZAc": ("ZAR", 100.0), "ZAX": ("ZAR", 100.0),
         "ILA": ("ILS", 100.0)}

# static fallback USD-per-major-unit (only if live fetch fails)
FALLBACK = {
    "EUR": 1.08, "JPY": 0.0064, "GBP": 1.27, "AUD": 0.66, "CAD": 0.73,
    "CHF": 1.10, "HKD": 0.128, "KRW": 0.00073, "TWD": 0.031, "INR": 0.012,
    "NOK": 0.094, "SEK": 0.095, "SGD": 0.74, "DKK": 0.145, "PLN": 0.25,
    "CNY": 0.14, "BRL": 0.18, "MXN": 0.055, "ZAR": 0.055, "ILS": 0.27,
    "THB": 0.028, "IDR": 0.000062, "TRY": 0.030, "AED": 0.27, "SAR": 0.27,
    "NZD": 0.60, "PHP": 0.017, "MYR": 0.22, "CLP": 0.0011,
}

def make_session():
    s = requests.Session(); s.verify = CA
    proxy = os.environ.get("https_proxy") or os.environ.get("HTTPS_PROXY")
    if proxy:
        s.proxies = {"https": proxy, "http": proxy}
    s.headers.update({"User-Agent": "Mozilla/5.0"})
    try: s.get("https://finance.yahoo.com", timeout=12)
    except Exception: pass
    return s

def live_rate(cur, session):
    """USD per 1 unit of `cur` from Yahoo, or None."""
    try:
        h = yf.Ticker(f"{cur}USD=X", session=session).history(period="5d")
        cl = h["Close"].dropna()
        if len(cl):
            return float(cl.iloc[-1])
    except Exception:
        pass
    return None

def resolve_rate(cur, session, cache):
    """Return (agg_rate, price_rate) USD multipliers.

    Yahoo reports aggregate amounts (marketCap, EV, ebitda, debt, cash) in the
    MAJOR currency even for pence/cents-quoted listings, but quotes the PRICE in
    the minor unit. So for GBp/ZAc/ILA the aggregate rate is the major-currency
    rate while the price rate is that divided by 100.
    """
    if cur in cache:
        return cache[cur]
    if cur in MINOR:
        major, div = MINOR[cur]
        base = live_rate(major, session) or FALLBACK.get(major)
        out = (base, base / div) if base else (None, None)
    else:
        rate = live_rate(cur, session) or FALLBACK.get(cur)
        out = (rate, rate)
    cache[cur] = out
    return out

AGG_COLS = ["mcap_m", "enterprise_value_m", "ebitda_m", "total_debt_m", "total_cash_m"]

def run():
    conn = sqlite3.connect(DB)
    # currencies needing conversion: non-USD, not the frontier manual rows
    currs = [r[0] for r in conn.execute("""
        SELECT DISTINCT currency FROM ticker_yf
        WHERE currency IS NOT NULL AND currency != 'USD'
          AND (sector IS NULL OR sector != 'Frontier Markets')""")]
    print(f"currencies to convert: {currs}")
    session = make_session()
    cache = {}
    total = 0
    for cur in currs:
        agg_rate, px_rate = resolve_rate(cur, session, cache)
        if not agg_rate or agg_rate <= 0:
            print(f"  {cur}: NO RATE — skipped (left unconverted)")
            continue
        sets = ", ".join(f"{c} = {c} * ?" for c in AGG_COLS)
        params = [agg_rate] * len(AGG_COLS) + [px_rate, cur]
        cur_n = conn.execute(f"""UPDATE ticker_yf SET {sets}, price = price * ?, currency='USD'
            WHERE currency = ? AND (sector IS NULL OR sector != 'Frontier Markets')""",
            params).rowcount
        total += cur_n
        print(f"  {cur:<5} agg={agg_rate:<12.8g} px={px_rate:<12.8g} converted {cur_n} rows")
    conn.commit()
    print(f"\ndone: {total} foreign rows converted to USD")
    # spot check
    for t in ("005930.KS", "000660.KS", "NESN.SW", "ASML.AS", "7203.T", "CSU.TO"):
        r = conn.execute("SELECT ticker, mcap_m, currency FROM ticker_yf WHERE ticker=?", (t,)).fetchone()
        if r:
            print(f"  {r[0]:<10} mcap_m=${r[1]:,.0f}M  {r[2]}")

if __name__ == "__main__":
    run()
