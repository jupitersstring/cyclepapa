"""Fetch the fundamentals panel (F/I/R/S + catalyst) from Financial Modeling
Prep for the liquid core of the universe, to power Model A (monster candidate)
and real CatalystVerified for Model B (ignition).

FMP 'stable' API. Covers our global universe with the SAME symbols as yfinance
(AAPL, 005930.KS, 2330.TW, IOLCP.NS ...), and is not subject to the Yahoo
throttle. The API key is read from the gitignored /home/user/cyclepapa/.fmp_key
— it is never printed, logged, or committed.

Per ticker we pull:
  income-statement (quarter, 8q)  -> revenue/gross/operating/net/eps/R&D  => F
  earnings         (12)           -> epsActual vs epsEstimated + dates     => I + CatalystVerified
  grades-consensus                -> analyst counts (coverage)             => R
  analyst-estimates (annual, 2)   -> revenue Low/High spread (dispersion)  => R
  shares-float                    -> floatShares / freeFloat%              => S

Raw JSON is cached under /tmp/fmp_cache/<ticker>.json (resume-safe). Run
fmp_features.py afterwards to distil the processed panel into data/fmp/.

Usage:
  python fmp_fetch.py [--n 500] [--all]     # fetch liquid top-N (default 500)
"""

import os
import sys
import json
import time
import urllib.parse
import urllib.request

import pandas as pd

BASE = "https://financialmodelingprep.com/stable/"
CACHE = "/tmp/fmp_cache"
MASTER = "/tmp/master_full_universe.csv"
KEYFILE = "/home/user/cyclepapa/.fmp_key"


def _key():
    with open(KEYFILE) as f:
        return f.read().strip()


def _get(endpoint, params, key, retries=3):
    params = dict(params); params["apikey"] = key
    url = BASE + endpoint + "?" + urllib.parse.urlencode(params)
    for a in range(retries):
        try:
            with urllib.request.urlopen(url, timeout=30) as r:
                return json.loads(r.read().decode())
        except Exception:
            time.sleep(1.5 * (a + 1))
    return None


def liquid_universe(n):
    m = pd.read_csv(MASTER, low_memory=False)
    m = m[m["adv_usd"].notna()].sort_values("adv_usd", ascending=False)
    return m["ticker"].astype(str).head(n).tolist()


def fetch_one(t, key):
    """Fetch all endpoints for one ticker into a single dict."""
    d = {"symbol": t}
    d["income"] = _get("income-statement", {"symbol": t, "period": "quarter", "limit": 8}, key)
    d["earnings"] = _get("earnings", {"symbol": t, "limit": 12}, key)
    d["grades"] = _get("grades-consensus", {"symbol": t}, key)
    d["estimates"] = _get("analyst-estimates", {"symbol": t, "period": "annual", "limit": 2}, key)
    d["float"] = _get("shares-float", {"symbol": t}, key)
    return d


def main():
    n = 500
    if "--n" in sys.argv:
        n = int(sys.argv[sys.argv.index("--n") + 1])
    if "--all" in sys.argv:
        n = 10_000_000
    os.makedirs(CACHE, exist_ok=True)
    key = _key()
    if "--universe" in sys.argv:
        uni = json.load(open(sys.argv[sys.argv.index("--universe") + 1]))
    else:
        uni = liquid_universe(n)
    have = {os.path.splitext(f)[0].replace("__", "/") for f in os.listdir(CACHE)}
    todo = [t for t in uni if t.replace("/", "__") not in {f[:-5] for f in os.listdir(CACHE)}]
    print(f"Universe {len(uni)}; cached {len(uni)-len(todo)}; to fetch {len(todo)}", file=sys.stderr)
    ok = 0
    for i, t in enumerate(todo):
        try:
            d = fetch_one(t, key)
            with open(os.path.join(CACHE, t.replace("/", "__") + ".json"), "w") as f:
                json.dump(d, f)
            if d.get("income"):
                ok += 1
        except Exception as e:
            print(f"  {t}: {e}", file=sys.stderr)
        if (i + 1) % 50 == 0:
            print(f"  {i+1}/{len(todo)} (with income: {ok})", file=sys.stderr)
        time.sleep(0.05)
    print(f"fetch complete: {ok} with fundamentals")


if __name__ == "__main__":
    main()
