import sys, time, os, warnings
import pandas as pd, re
import yfinance as yf
from yfsession import SESSION
import financedatabase as fd
warnings.filterwarnings("ignore")

interval = sys.argv[1] if len(sys.argv)>1 else "1wk"
caps_arg = sys.argv[2] if len(sys.argv)>2 else "smallmicro"
region   = sys.argv[3] if len(sys.argv)>3 else "us"   # us|uk|ca|de|fr|nl|au
period   = "20y"
cache = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".cache", f"ohlcvdict_{interval}_{period}.pkl")
minrows = 52 if interval=="1wk" else 60

from midcap_weekly_anomalies import REGIONS          # shared region registry
country, EXCH, CCY, SUFFIX = REGIONS[region]
pat = re.compile(r'^[A-Z]{1,5}(-[A-Z])?$') if SUFFIX is None else \
      re.compile(rf'^[A-Z0-9]{{1,5}}(-[A-Z])?\.{SUFFIX}$')
eq=fd.Equities().select(country=country)
def uni(cap):
    s=eq[eq['market_cap']==cap]
    s=s[s['exchange'].isin(EXCH)&(s['currency']==CCY)]
    if SUFFIX is None:
        return [str(t).replace('.','-') for t in s.index if pat.match(str(t).replace('.','-'))]
    return [str(t) for t in s.index if pat.match(str(t))]
CAPMAP={"mid":["Mid Cap"],"small":["Small Cap"],"micro":["Micro Cap"],
        "large":["Large Cap"],"mega":["Mega Cap"],
        "largemega":["Large Cap","Mega Cap"],
        "smallmicro":["Small Cap","Micro Cap"],
        "all":["Mid Cap","Small Cap","Micro Cap"]}
syms = sorted(set().union(*[set(uni(c)) for c in CAPMAP[caps_arg]]))

import json
have = {}
if os.path.exists(cache):
    try: have = pd.read_pickle(cache)
    except Exception: have = {}
# write-time sanitize: drop any union-index NaN padding lurking in the cache
have = {s: d.dropna() for s, d in have.items() if d is not None and len(d.dropna()) > minrows}

# tombstones: never re-attempt known-dead tickers (skips ~1,600 delisted/run)
tomb_path = os.path.join(os.path.dirname(cache), f"dead_{interval}.json")
dead = set(json.load(open(tomb_path))) if os.path.exists(tomb_path) else set()
todo = [s for s in syms if s not in have and s not in dead]
print(f"[{interval}/{caps_arg}] universe={len(syms)} cached={len([s for s in syms if s in have])} "
      f"dead={len([s for s in syms if s in dead])} todo={len(todo)}", flush=True)

ok=fail=0; new_dead=set()
for i,t in enumerate(todo):
    try:
        h=yf.Ticker(t, session=SESSION).history(period=period, interval=interval, auto_adjust=True)
        if h is not None and "Volume" in h and len(h.dropna())>minrows:
            sub=h[["Close","Volume"]].dropna()
            sub.index=sub.index.tz_localize(None)
            have[t]=sub; ok+=1
        else:
            fail+=1; new_dead.add(t)   # no data -> tombstone
    except Exception:
        fail+=1   # transient error -> retry next run (don't tombstone)
    if (i+1)%50==0:
        pd.to_pickle(have, cache)
        json.dump(sorted(dead | new_dead), open(tomb_path, "w"))
        print(f"[{interval}] {i+1}/{len(todo)}  ok={ok} fail={fail}  cache={len(have)} dead={len(dead|new_dead)}", flush=True)
    time.sleep(0.5)
pd.to_pickle(have, cache)
json.dump(sorted(dead | new_dead), open(tomb_path, "w"))
print(f"[{interval}] DONE ok={ok} fail={fail} cache={len(have)} dead={len(dead|new_dead)}", flush=True)
