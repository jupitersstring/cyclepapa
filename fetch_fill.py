import sys, time, os, warnings
import pandas as pd, re
import yfinance as yf
import financedatabase as fd
warnings.filterwarnings("ignore")

interval = sys.argv[1] if len(sys.argv)>1 else "1wk"
caps_arg = sys.argv[2] if len(sys.argv)>2 else "smallmicro"
period   = "20y"
cache = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".cache", f"ohlcvdict_{interval}_{period}.pkl")
minrows = 52 if interval=="1wk" else 60

eq=fd.Equities().select(country="United States")
US={'NYQ','NMS','NGM','NCM','ASE'}; pat=re.compile(r'^[A-Z]{1,5}(-[A-Z])?$')
def uni(cap):
    s=eq[eq['market_cap']==cap]; s=s[s['exchange'].isin(US)&(s['currency']=='USD')]
    return [str(t).replace('.','-') for t in s.index if pat.match(str(t).replace('.','-'))]
CAPMAP={"mid":["Mid Cap"],"small":["Small Cap"],"micro":["Micro Cap"],
        "smallmicro":["Small Cap","Micro Cap"],
        "all":["Mid Cap","Small Cap","Micro Cap"]}
syms = sorted(set().union(*[set(uni(c)) for c in CAPMAP[caps_arg]]))

have = {}
if os.path.exists(cache):
    try: have = pd.read_pickle(cache)
    except Exception: have = {}
todo = [s for s in syms if s not in have]
print(f"[{interval}/{caps_arg}] universe={len(syms)} cached={len([s for s in syms if s in have])} todo={len(todo)}", flush=True)

ok=fail=0
for i,t in enumerate(todo):
    try:
        h=yf.Ticker(t).history(period=period, interval=interval, auto_adjust=True)
        if h is not None and "Volume" in h and len(h.dropna())>minrows:
            sub=h[["Close","Volume"]].dropna()
            sub.index=sub.index.tz_localize(None)
            have[t]=sub; ok+=1
        else: fail+=1
    except Exception:
        fail+=1
    if (i+1)%50==0:
        pd.to_pickle(have, cache)
        print(f"[{interval}] {i+1}/{len(todo)}  ok={ok} fail={fail}  cache={len(have)}", flush=True)
    time.sleep(0.5)
pd.to_pickle(have, cache)
print(f"[{interval}] DONE ok={ok} fail={fail} cache={len(have)}", flush=True)
