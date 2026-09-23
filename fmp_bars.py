"""Fetch ~4y daily EOD from FMP for the fundamentals panel and resample to
weekly OHLCV — the price history needed to detect MU-style long consolidation
bases across the full panel. Cache: /tmp/fmp_bars/<ticker>.csv (resume-safe).
Key from gitignored .fmp_key.
"""
import os, sys, json, time, urllib.parse, urllib.request
from datetime import datetime, timedelta
import pandas as pd

BASE = "https://financialmodelingprep.com/stable/"
CACHE = "/tmp/fmp_bars"
KEYFILE = "/home/user/cyclepapa/.fmp_key"
PANEL = "/tmp/fmp_panel.csv"


def _key():
    return open(KEYFILE).read().strip()


def _get(sym, key, retries=3):
    frm = (datetime.utcnow() - timedelta(days=4 * 365 + 30)).strftime("%Y-%m-%d")
    to = datetime.utcnow().strftime("%Y-%m-%d")
    url = BASE + "historical-price-eod/full?" + urllib.parse.urlencode(
        {"symbol": sym, "from": frm, "to": to, "apikey": key})
    for a in range(retries):
        try:
            with urllib.request.urlopen(url, timeout=30) as r:
                return json.loads(r.read().decode())
        except Exception:
            time.sleep(1.0 * (a + 1))
    return None


def to_weekly(rows):
    df = pd.DataFrame(rows)
    if df.empty or "close" not in df:
        return None
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date").sort_index()
    w = df.resample("W-FRI").agg(Open=("open", "first"), High=("high", "max"),
                                 Low=("low", "min"), Close=("close", "last"),
                                 Volume=("volume", "sum")).dropna(subset=["Close"])
    return w


def main():
    os.makedirs(CACHE, exist_ok=True)
    key = _key()
    if "--universe" in sys.argv:
        tickers = json.load(open(sys.argv[sys.argv.index("--universe") + 1]))
    else:
        tickers = pd.read_csv(PANEL)["ticker"].astype(str).tolist()
    done = {f[:-4] for f in os.listdir(CACHE)}
    todo = [t for t in tickers if t.replace("/", "__") not in done]
    print(f"weekly bars: {len(tickers)} panel, to fetch {len(todo)}", file=sys.stderr)
    ok = 0
    for i, t in enumerate(todo):
        rows = _get(t, key)
        if rows:
            w = to_weekly(rows)
            if w is not None and len(w) > 20:
                w.to_csv(os.path.join(CACHE, t.replace("/", "__") + ".csv"))
                ok += 1
        if (i + 1) % 100 == 0:
            print(f"  {i+1}/{len(todo)} (ok {ok})", file=sys.stderr)
        time.sleep(0.03)
    print(f"bars fetch complete: {ok} tickers with weekly bars")


if __name__ == "__main__":
    main()
