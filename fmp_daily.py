"""Fetch ~4y daily EOD (OHLCV) from FMP for the panel and SAVE DAILY (one cache
that vwap_features resamples to weekly/monthly). Resume-safe. Key gitignored.
"""
import os, sys, json, time, urllib.parse, urllib.request
from datetime import datetime, timedelta
import pandas as pd

BASE = "https://financialmodelingprep.com/stable/"
CACHE = "/tmp/fmp_daily"
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


def main():
    os.makedirs(CACHE, exist_ok=True)
    key = _key()
    if "--universe" in sys.argv:
        tickers = json.load(open(sys.argv[sys.argv.index("--universe") + 1]))
    else:
        tickers = pd.read_csv(PANEL)["ticker"].astype(str).tolist()
    done = {f[:-4] for f in os.listdir(CACHE)}
    todo = [t for t in tickers if t.replace("/", "__") not in done]
    print(f"daily bars: {len(tickers)} panel, to fetch {len(todo)}", file=sys.stderr)
    ok = 0
    for i, t in enumerate(todo):
        rows = _get(t, key)
        if rows and isinstance(rows, list):
            df = pd.DataFrame(rows)
            if "close" in df and len(df) > 60:
                df = df[["date", "open", "high", "low", "close", "volume"]].copy()
                df.columns = ["date", "Open", "High", "Low", "Close", "Volume"]
                df = df.set_index("date").sort_index()
                df.to_csv(os.path.join(CACHE, t.replace("/", "__") + ".csv"))
                ok += 1
        if (i + 1) % 100 == 0:
            print(f"  {i+1}/{len(todo)} (ok {ok})", file=sys.stderr)
        time.sleep(0.03)
    print(f"daily fetch complete: {ok}")


if __name__ == "__main__":
    main()
