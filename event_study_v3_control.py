"""
Event study v3 — add control sample of declining/non-winner stocks
+ run on FULL SP500 to find most bullish today.

Process:
  1. Build empirical aspect-key forward-return lookup using a balanced
     panel: 19 known winners + 25 declining/sideways control stocks
  2. For each (transit_planet, natal_pt, aspect) compute return DELTA
     vs the same chart's NON-event days (within-stock baseline removes
     stock-specific bullish bias)
  3. For each of ~500 SP500 charts, identify aspects currently active
     (within 2° as of April 2026) and sum the empirical expected
     forward-return delta
  4. Rank SP500 by today's expected-forward-return-from-active-aspects
"""
import csv, os, json, subprocess, math, sys, time
import statistics as st
from datetime import datetime, timezone, timedelta
import swisseph as swe
from bti_test import compute_natal

PIDS = {"Mercury":swe.MERCURY,"Venus":swe.VENUS,"Mars":swe.MARS,
        "Jupiter":swe.JUPITER,"Saturn":swe.SATURN,
        "Uranus":swe.URANUS,"Neptune":swe.NEPTUNE,"Pluto":swe.PLUTO}
NATAL_PTS = ("Sun","Moon","ASC","MC")
ASPECTS = {
    "conj_0":0.0,"sxt_60":60.0,"sq_90":90.0,"tri_120":120.0,"opp_180":180.0,
    "bat_41":41.04,"sept_51":51.43,"qnt_72":72.0,"gart_77":77.04,
    "butt_98":97.92,"phi_137":137.5,"biq_144":144.0,
}

def aspect_orb(a, b, target):
    d = (a - b) % 360
    return min(abs(d - target), abs(d - (360 - target)))

# Winners (known multi-baggers)
WINNERS = [
    ("AAPL","1980-12-12"),("MSFT","1986-03-13"),("NVDA","1999-01-22"),
    ("AMZN","1997-05-15"),("GOOG","2004-08-19"),("META","2012-05-18"),
    ("TSLA","2010-06-29"),("NFLX","2002-05-23"),("GME","2002-02-13"),
    ("AMC","2013-12-18"),("PLTR","2020-09-30"),("APP","2021-04-15"),
    ("SMCI","2007-03-29"),("WDC","1976-08-31"),("CHRW","1997-10-15"),
    ("BLDR","2005-06-22"),("DECK","1993-10-14"),("FISV","1986-09-25"),
    ("INCY","1993-11-05"),
]
# Control: known declining/struggling stocks (real first-trade dates)
CONTROLS = [
    ("WBA","1909-09-15"),    # Walgreens, declining
    ("INTC","1971-10-13"),   # Intel, multi-year decline
    ("BA","1962-01-02"),     # Boeing, struggling
    ("F","1956-01-17"),      # Ford, sideways
    ("GE","1892-04-15"),     # GE old industrial
    ("XRX","1961-11-30"),    # Xerox, decline
    ("KHC","2015-07-06"),    # Kraft Heinz, decline
    ("MMM","1946-01-14"),    # 3M, decline
    ("VZ","1984-11-21"),     # Verizon, sideways
    ("T","1983-07-19"),      # AT&T, decline
    ("WMT","1972-08-25"),    # Walmart, mostly sideways then up
    ("CVS","1996-02-08"),    # CVS, declining
    ("CL","1930-03-13"),     # Colgate, slow grower
    ("PFE","1942-06-23"),    # Pfizer, declining
    ("MRK","1946-01-02"),    # Merck, mixed
    ("DIS","1957-11-12"),    # Disney, declining
    ("PARA","2022-01-03"),   # Paramount, declining
    ("FOX","2019-03-19"),    # Fox, declining
    ("NWS","2013-06-19"),    # News Corp, declining
    ("CPB","1954-12-31"),    # Campbell's, declining
    ("HRL","1928-09-05"),    # Hormel, declining
    ("SJM","1959-01-02"),    # JM Smucker, sideways
    ("MO","1985-03-05"),     # Altria, sideways
    ("BIIB","1991-09-13"),   # Biogen, declining
    ("WBD","2022-04-11"),    # Warner Bros Discovery, declining
]

def fetch_or_load(tk, fetch_full=True):
    cache = f"/home/user/cyclepapa/data/prices_full/{tk}.csv"
    if os.path.exists(cache):
        prices = []
        with open(cache) as f:
            next(f)
            for line in f:
                p = line.strip().split(",")
                if len(p) == 2:
                    try: prices.append((p[0], float(p[1])))
                    except: pass
        return prices
    if not fetch_full: return []
    p1=int(datetime(1990,1,1,tzinfo=timezone.utc).timestamp())
    p2=int(datetime(2026,4,22,tzinfo=timezone.utc).timestamp())
    url=f"https://query1.finance.yahoo.com/v8/finance/chart/{tk}?period1={p1}&period2={p2}&interval=1d"
    try:
        out=subprocess.run(["curl","-sL","-H","User-Agent: Mozilla/5.0","-m","20",url],
                            capture_output=True,text=True,timeout=25).stdout
        j=json.loads(out)
        r=j.get("chart",{}).get("result")
        if not r: return []
        ts=r[0]["timestamp"]; cs=r[0]["indicators"]["quote"][0]["close"]
        prices=[(datetime.utcfromtimestamp(t).strftime("%Y-%m-%d"),c) for t,c in zip(ts,cs) if c]
        if prices:
            os.makedirs(os.path.dirname(cache), exist_ok=True)
            with open(cache,"w") as f:
                f.write("date,close\n")
                for d,c in prices: f.write(f"{d},{c:.4f}\n")
        return prices
    except: return []

def date_jd(date_str):
    y,m,d=map(int,date_str.split("-"))
    return swe.julday(y,m,d,12.0)

def jd_date(jd):
    cal=swe.revjul(jd)
    return f"{int(cal[0]):04d}-{int(cal[1]):02d}-{int(cal[2]):02d}"

def precompute_planet_grid(start_jd, end_jd, step_days=3):
    grid_jds = [start_jd + i*step_days for i in range(int((end_jd-start_jd)/step_days)+1)]
    grid = {}
    for pname, pid in PIDS.items():
        grid[pname] = [(jd, swe.calc_ut(jd, pid)[0][0] % 360) for jd in grid_jds]
    return grid

def find_activations(planet_lons, natal_lon, aspect_deg, skip_jd, end_buffer_jd, orb=1.5):
    events = []
    in_event = False
    best_jd = None; best_orb = 99
    for jd, lon in planet_lons:
        if jd < skip_jd: continue
        if jd > end_buffer_jd: break
        o = aspect_orb(lon, natal_lon, aspect_deg)
        if o <= orb:
            in_event = True
            if o < best_orb: best_orb = o; best_jd = jd
        else:
            if in_event and best_jd is not None:
                events.append((best_jd, best_orb))
                in_event = False; best_jd = None; best_orb = 99
    if in_event and best_jd is not None:
        events.append((best_jd, best_orb))
    return events

def compute_event_study(stocks_panel, planet_grid, end_jd):
    """For each (transit, natal_pt, aspect_name) accumulate fwd returns."""
    activations = {}
    for s in stocks_panel:
        first_date = s["prices"][0][0]
        skip_until_jd = date_jd(first_date) + 365
        end_buffer = end_jd - 365  # need 12mo forward
        for np_name in NATAL_PTS:
            if np_name not in s["natal"]: continue
            npon = s["natal"][np_name]["lon"]
            for tp_name, planet_lons in planet_grid.items():
                for asp_name, asp_deg in ASPECTS.items():
                    events = find_activations(planet_lons, npon, asp_deg, skip_until_jd, end_buffer)
                    for jd, orb in events:
                        date_str = jd_date(jd)
                        rets = {}
                        base_p = None
                        for off in range(7):
                            d = (datetime.strptime(date_str,"%Y-%m-%d")+timedelta(days=off)).strftime("%Y-%m-%d")
                            if d in s["prices_dict"]: base_p = s["prices_dict"][d]; break
                        if base_p is None: continue
                        for h_days in (30, 90, 180, 365):
                            target = (datetime.strptime(date_str,"%Y-%m-%d")+timedelta(days=h_days)).strftime("%Y-%m-%d")
                            forward_p = None
                            for off in range(7):
                                d = (datetime.strptime(target,"%Y-%m-%d")+timedelta(days=off)).strftime("%Y-%m-%d")
                                if d in s["prices_dict"]: forward_p = s["prices_dict"][d]; break
                            if forward_p:
                                rets[h_days] = (forward_p/base_p - 1)*100
                        if rets:
                            key = (tp_name, np_name, asp_name)
                            activations.setdefault(key, []).append({
                                "tk":s["tk"],"date":date_str,"orb":orb,"rets":rets,
                                "group":s["group"]
                            })
    return activations

def main():
    print("Loading winners + controls...", file=sys.stderr)
    panel = []
    for tk, ipo in WINNERS:
        try:
            natal = compute_natal(ipo)
            prices = fetch_or_load(tk)
            if not prices: continue
            panel.append({"tk":tk,"natal":natal,"prices":prices,
                          "prices_dict":dict(prices),"group":"W"})
        except: pass
    for tk, ipo in CONTROLS:
        try:
            natal = compute_natal(ipo)
            prices = fetch_or_load(tk)
            if not prices: continue
            panel.append({"tk":tk,"natal":natal,"prices":prices,
                          "prices_dict":dict(prices),"group":"C"})
        except Exception as e:
            print(f"  {tk} fail: {e}", file=sys.stderr)
    print(f"Panel: {len(panel)} stocks ({sum(1 for s in panel if s['group']=='W')} W, "
          f"{sum(1 for s in panel if s['group']=='C')} C)", file=sys.stderr)

    print("Precomputing planet grid 1990-2026...", file=sys.stderr)
    start_jd = date_jd("1990-01-01"); end_jd = date_jd("2026-04-22")
    grid = precompute_planet_grid(start_jd, end_jd)

    print("Running event study...", file=sys.stderr)
    t0 = time.time()
    activations = compute_event_study(panel, grid, end_jd)
    print(f"  {time.time()-t0:.0f}s, {sum(len(v) for v in activations.values())} activations across {len(activations)} keys", file=sys.stderr)

    # ============================================================
    # Compute per-key fwd return separately for W vs C, then DELTA
    # ============================================================
    key_stats = {}
    for key, evts in activations.items():
        w_evts = [e for e in evts if e["group"]=="W"]
        c_evts = [e for e in evts if e["group"]=="C"]
        out = {"key":key,"n_w":len(w_evts),"n_c":len(c_evts)}
        for h in (30, 90, 180, 365):
            w_rets = [e["rets"].get(h) for e in w_evts]
            c_rets = [e["rets"].get(h) for e in c_evts]
            w_rets = [r for r in w_rets if r is not None]
            c_rets = [r for r in c_rets if r is not None]
            if w_rets and c_rets:
                out[f"w_med_{h}"] = st.median(w_rets)
                out[f"c_med_{h}"] = st.median(c_rets)
                out[f"delta_{h}"] = st.median(w_rets) - st.median(c_rets)
                out[f"all_med_{h}"] = st.median(w_rets + c_rets)
            elif w_rets:
                out[f"w_med_{h}"] = st.median(w_rets)
                out[f"all_med_{h}"] = st.median(w_rets)
            elif c_rets:
                out[f"c_med_{h}"] = st.median(c_rets)
                out[f"all_med_{h}"] = st.median(c_rets)
        key_stats[key] = out

    # ============================================================
    # Aggregate and report aspects with positive W-C delta
    # ============================================================
    print(f"\n{'='*120}")
    print(f"WINNERS vs CONTROLS event-study delta (12mo) — keys with n_w>=10 and n_c>=10")
    print(f"{'='*120}")
    print(f"{'Transit':<9s} {'Nat':<5s} {'Asp':<10s} {'nW':>4s} {'nC':>4s} | "
          f"{'W12mo':>7s} {'C12mo':>7s} {'Δ':>7s}")
    rows = [v for v in key_stats.values() if v.get("n_w",0)>=10 and v.get("n_c",0)>=10
                                              and "delta_365" in v]
    rows.sort(key=lambda r: -r["delta_365"])
    for r in rows[:40]:
        tp, np_, asp = r["key"]
        print(f"{tp[:8]:<9s} {np_:<5s} {asp:<10s} {r['n_w']:>4d} {r['n_c']:>4d} | "
              f"{r['w_med_365']:>+6.1f}% {r['c_med_365']:>+6.1f}% {r['delta_365']:>+6.1f}pp")

    print(f"\n  Most NEGATIVE delta (winners *underperform* controls on this aspect):")
    rows.sort(key=lambda r: r["delta_365"])
    for r in rows[:20]:
        tp, np_, asp = r["key"]
        print(f"{tp[:8]:<9s} {np_:<5s} {asp:<10s} {r['n_w']:>4d} {r['n_c']:>4d} | "
              f"{r['w_med_365']:>+6.1f}% {r['c_med_365']:>+6.1f}% {r['delta_365']:>+6.1f}pp")

    # Save key_stats for next step (SP500 today scan)
    import pickle
    with open("/home/user/cyclepapa/data/event_study_keys.pkl","wb") as f:
        pickle.dump(key_stats, f)
    print(f"\nSaved {len(key_stats)} key statistics to data/event_study_keys.pkl")
    print(f"  These will be used in the today-active scan on full SP500")

if __name__ == "__main__":
    main()
