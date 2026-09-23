"""Fetch insider-transaction history from FMP for the liquid core, to build the
insider-buying conviction measure.

Form 4 data carries a transaction DATE, not an intraday time, so literal
"outside market hours" execution is not observable. What we can measure:
  * genuine OPEN-MARKET purchases (transactionType 'P-Purchase', real price) —
    excludes option exercises / RSU vesting / awards, which are not conviction
  * senior-insider cluster buys (CEO/CFO/Chair/President/Director)
  * a transaction DATED on a non-trading day (weekend/holiday) — the closest
    real proxy to an off-market / privately-negotiated buy

Cache: /tmp/fmp_insider/<ticker>.json (resume-safe). Key from gitignored file.
"""
import os, sys, json, time, urllib.parse, urllib.request
import pandas as pd

BASE = "https://financialmodelingprep.com/stable/"
CACHE = "/tmp/fmp_insider"
MASTER = "/tmp/master_full_universe.csv"
KEYFILE = "/home/user/cyclepapa/.fmp_key"


def _key():
    return open(KEYFILE).read().strip()


def _get(endpoint, params, key, retries=3):
    params = dict(params); params["apikey"] = key
    url = BASE + endpoint + "?" + urllib.parse.urlencode(params)
    for a in range(retries):
        try:
            with urllib.request.urlopen(url, timeout=30) as r:
                return json.loads(r.read().decode())
        except Exception:
            time.sleep(1.2 * (a + 1))
    return None


def main():
    n = 500
    if "--n" in sys.argv:
        n = int(sys.argv[sys.argv.index("--n") + 1])
    os.makedirs(CACHE, exist_ok=True)
    key = _key()
    if "--universe" in sys.argv:
        uni = json.load(open(sys.argv[sys.argv.index("--universe") + 1]))
    else:
        m = pd.read_csv(MASTER, low_memory=False)
        uni = m[m.adv_usd.notna()].sort_values("adv_usd", ascending=False).ticker.astype(str).head(n).tolist()
    done = {f[:-5] for f in os.listdir(CACHE)}
    todo = [t for t in uni if t.replace("/", "__") not in done]
    print(f"insider: universe {len(uni)}, to fetch {len(todo)}", file=sys.stderr)
    ok = 0
    for i, t in enumerate(todo):
        rows = _get("insider-trading/search", {"symbol": t, "limit": 100}, key)
        with open(os.path.join(CACHE, t.replace("/", "__") + ".json"), "w") as f:
            json.dump(rows or [], f)
        if rows:
            ok += 1
        if (i + 1) % 50 == 0:
            print(f"  {i+1}/{len(todo)} (with data: {ok})", file=sys.stderr)
        time.sleep(0.05)
    print(f"insider fetch complete: {ok} with data")


if __name__ == "__main__":
    main()
