"""
EVENT-STUDY v2 — efficient version. Pre-computes planet longitudes on
a 3-day grid for the full window, then scans for activations vectorised.

For each stock + each (transit_planet, natal_pt, aspect_angle):
  - Find activation dates (orb <= 1.5°, take tightest in 30-day window)
  - Measure forward return at 21d, 63d, 126d, 252d
  - Aggregate across stocks

Output: per-aspect-type expected forward return profile.
"""
import csv, os, json, subprocess, math
import statistics as st
from datetime import datetime, timezone, timedelta
import swisseph as swe
from bti_test import compute_natal

PIDS = {"Mercury":swe.MERCURY,"Venus":swe.VENUS,"Mars":swe.MARS,
        "Jupiter":swe.JUPITER,"Saturn":swe.SATURN,
        "Uranus":swe.URANUS,"Neptune":swe.NEPTUNE,"Pluto":swe.PLUTO}

NATAL_PTS = ("Sun","Moon","ASC","MC")

ASPECTS = {
    "conj_0":   0.0,
    "sxt_60":   60.0,
    "sq_90":    90.0,
    "tri_120":  120.0,
    "opp_180":  180.0,
    "bat_41":   41.04,
    "sept_51":  51.43,
    "qnt_72":   72.0,
    "gart_77":  77.04,
    "butt_98":  97.92,
    "phi_137":  137.5,
    "biq_144":  144.0,
}

def aspect_orb(a, b, target):
    d = (a - b) % 360
    return min(abs(d - target), abs(d - (360 - target)))

STOCKS = [
    ("AAPL","1980-12-12"), ("MSFT","1986-03-13"), ("NVDA","1999-01-22"),
    ("AMZN","1997-05-15"), ("GOOG","2004-08-19"), ("META","2012-05-18"),
    ("TSLA","2010-06-29"), ("NFLX","2002-05-23"),
    ("GME","2002-02-13"), ("AMC","2013-12-18"),
    ("PLTR","2020-09-30"), ("APP","2021-04-15"),
    ("SMCI","2007-03-29"), ("WDC","1976-08-31"),
    ("CHRW","1997-10-15"), ("BLDR","2005-06-22"),
    ("DECK","1993-10-14"), ("FISV","1986-09-25"),
    ("INCY","1993-11-05"),
]

def fetch_or_load(tk):
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

def main():
    print("Loading stocks...")
    stocks = []
    for tk, ipo in STOCKS:
        try:
            natal = compute_natal(ipo)
            prices = fetch_or_load(tk)
            if not prices: continue
            prices_dict = dict(prices)
            stocks.append({"tk":tk,"ipo":ipo,"natal":natal,
                           "prices":prices,"prices_dict":prices_dict})
        except: pass
    print(f"  {len(stocks)} stocks loaded")

    # Precompute planet longitudes on 3-day grid 1990-2026
    print("Precomputing planet longitudes (3-day grid)...")
    start_jd = swe.julday(1990, 1, 1, 12.0)
    end_jd = swe.julday(2026, 4, 22, 12.0)
    grid_jds = [start_jd + i*3 for i in range(int((end_jd-start_jd)/3)+1)]
    planet_grid = {}  # planet -> list of (jd, lon)
    for pname, pid in PIDS.items():
        lons = [(jd, swe.calc_ut(jd, pid)[0][0] % 360) for jd in grid_jds]
        planet_grid[pname] = lons
    print(f"  Grid: {len(grid_jds)} dates, {len(PIDS)} planets")

    # For each stock skip first year of price history
    activations = {}

    for s in stocks:
        first_date = s["prices"][0][0]
        skip_until = (datetime.strptime(first_date, "%Y-%m-%d") + timedelta(days=365)).strftime("%Y-%m-%d")
        skip_jd = swe.julday(*[int(x) for x in skip_until.split("-")], 12.0)

        for np_name in NATAL_PTS:
            if np_name not in s["natal"]: continue
            npon = s["natal"][np_name]["lon"]
            for tp_name, lons in planet_grid.items():
                for asp_name, asp_deg in ASPECTS.items():
                    # Scan grid for dates with orb ≤ 1.5°
                    in_event = False
                    best_jd = None; best_orb = 99
                    for jd, lon in lons:
                        if jd < skip_jd: continue
                        if jd > end_jd - 252*1.5: continue  # need 12mo forward
                        o = aspect_orb(lon, npon, asp_deg)
                        if o <= 1.5:
                            in_event = True
                            if o < best_orb:
                                best_orb = o; best_jd = jd
                        else:
                            if in_event and best_jd is not None:
                                # Record activation
                                cal = swe.revjul(best_jd)
                                date_str = f"{int(cal[0]):04d}-{int(cal[1]):02d}-{int(cal[2]):02d}"
                                # Forward returns
                                rets = {}
                                for h_days in (30, 90, 180, 365):
                                    target = (datetime.strptime(date_str,"%Y-%m-%d")+timedelta(days=h_days)).strftime("%Y-%m-%d")
                                    base_p = None
                                    for off in range(7):
                                        d = (datetime.strptime(date_str,"%Y-%m-%d")+timedelta(days=off)).strftime("%Y-%m-%d")
                                        if d in s["prices_dict"]: base_p = s["prices_dict"][d]; break
                                    forward_p = None
                                    for off in range(7):
                                        d = (datetime.strptime(target,"%Y-%m-%d")+timedelta(days=off)).strftime("%Y-%m-%d")
                                        if d in s["prices_dict"]: forward_p = s["prices_dict"][d]; break
                                    if base_p and forward_p:
                                        rets[h_days] = (forward_p/base_p - 1)*100
                                if rets:
                                    key = (tp_name, np_name, asp_name)
                                    activations.setdefault(key, []).append({"tk":s["tk"],"date":date_str,"orb":best_orb,"rets":rets})
                                in_event = False; best_jd = None; best_orb = 99
                    # End of scan — record any final
                    if in_event and best_jd is not None:
                        cal = swe.revjul(best_jd)
                        date_str = f"{int(cal[0]):04d}-{int(cal[1]):02d}-{int(cal[2]):02d}"
                        rets = {}
                        for h_days in (30, 90, 180, 365):
                            target = (datetime.strptime(date_str,"%Y-%m-%d")+timedelta(days=h_days)).strftime("%Y-%m-%d")
                            base_p = None
                            for off in range(7):
                                d = (datetime.strptime(date_str,"%Y-%m-%d")+timedelta(days=off)).strftime("%Y-%m-%d")
                                if d in s["prices_dict"]: base_p = s["prices_dict"][d]; break
                            forward_p = None
                            for off in range(7):
                                d = (datetime.strptime(target,"%Y-%m-%d")+timedelta(days=off)).strftime("%Y-%m-%d")
                                if d in s["prices_dict"]: forward_p = s["prices_dict"][d]; break
                            if base_p and forward_p:
                                rets[h_days] = (forward_p/base_p - 1)*100
                        if rets:
                            key = (tp_name, np_name, asp_name)
                            activations.setdefault(key, []).append({"tk":s["tk"],"date":date_str,"orb":best_orb,"rets":rets})

    print(f"  {sum(len(v) for v in activations.values())} total activations across {len(activations)} unique aspect-keys")

    # ============================================================
    # Aggregate
    # ============================================================
    print(f"\n{'='*120}")
    print(f"PER-ASPECT-KEY FORWARD-RETURN PROFILES (n>=10 minimum)")
    print(f"  Median forward return at 1mo / 3mo / 6mo / 12mo")
    print(f"{'='*120}")
    rows = []
    for key, evts in activations.items():
        if len(evts) < 10: continue
        med = {}
        pos = {}
        for h in (30, 90, 180, 365):
            rets = [e["rets"].get(h) for e in evts]
            rets = [r for r in rets if r is not None]
            if rets:
                med[h] = st.median(rets)
                pos[h] = 100*sum(1 for r in rets if r>0)/len(rets)
        rows.append({"key":key,"n":len(evts),"med":med,"pos":pos})

    print(f"\nTOP 50 BULLISH by 12mo median forward return:")
    print(f"{'tPlanet':<9s} {'natPt':<5s} {'Aspect':<10s} {'n':>4s} | {'1mo':>6s} {'3mo':>6s} {'6mo':>6s} {'12mo':>6s}  |  {'pos%@12mo':>9s}")
    rows.sort(key=lambda r: -r["med"].get(365, -999))
    for r in rows[:50]:
        tp, np_, asp = r["key"]
        m1 = r["med"].get(30,0); m3 = r["med"].get(90,0)
        m6 = r["med"].get(180,0); m12 = r["med"].get(365,0)
        p12 = r["pos"].get(365,0)
        marker = " ★" if (m12 > 25 and r["n"] >= 15) else ""
        print(f"{tp[:8]:<9s} {np_:<5s} {asp:<10s} {r['n']:>4d} | {m1:>+5.1f}% {m3:>+5.1f}% {m6:>+5.1f}% {m12:>+5.1f}%  |  {p12:>7.0f}%{marker}")

    print(f"\nBOTTOM 25 BEARISH by 12mo median:")
    rows.sort(key=lambda r: r["med"].get(365, 999))
    for r in rows[:25]:
        tp, np_, asp = r["key"]
        m1 = r["med"].get(30,0); m3 = r["med"].get(90,0)
        m6 = r["med"].get(180,0); m12 = r["med"].get(365,0)
        p12 = r["pos"].get(365,0)
        print(f"{tp[:8]:<9s} {np_:<5s} {asp:<10s} {r['n']:>4d} | {m1:>+5.1f}% {m3:>+5.1f}% {m6:>+5.1f}% {m12:>+5.1f}%  |  {p12:>7.0f}%")

    # Aggregate by aspect
    print(f"\n{'='*120}")
    print(f"AGGREGATE BY ASPECT TYPE — average across all (planet, natal-pt) keys")
    print(f"{'='*120}")
    by_asp = {}
    for r in rows:
        by_asp.setdefault(r["key"][2], []).append(r)
    print(f"{'Aspect':<12s} {'keys':>5s} {'totN':>6s} | {'avg1mo':>7s} {'avg3mo':>7s} {'avg6mo':>7s} {'avg12mo':>8s}")
    asp_ag = []
    for asp, items in by_asp.items():
        tot_n = sum(i["n"] for i in items)
        m1 = st.mean([i["med"].get(30,0) for i in items])
        m3 = st.mean([i["med"].get(90,0) for i in items])
        m6 = st.mean([i["med"].get(180,0) for i in items])
        m12 = st.mean([i["med"].get(365,0) for i in items])
        asp_ag.append((asp, len(items), tot_n, m1, m3, m6, m12))
    asp_ag.sort(key=lambda x: -x[6])
    for a in asp_ag:
        print(f"{a[0]:<12s} {a[1]:>5d} {a[2]:>6d} | {a[3]:>+6.1f}% {a[4]:>+6.1f}% {a[5]:>+6.1f}% {a[6]:>+7.1f}%")

    # By transit planet
    print(f"\n{'='*120}")
    print(f"AGGREGATE BY TRANSIT PLANET")
    print(f"{'='*120}")
    by_tp = {}
    for r in rows:
        by_tp.setdefault(r["key"][0], []).append(r)
    print(f"{'tPlanet':<9s} {'keys':>5s} {'totN':>6s} | {'avg1mo':>7s} {'avg3mo':>7s} {'avg6mo':>7s} {'avg12mo':>8s}")
    for tp in sorted(by_tp):
        items = by_tp[tp]
        tot_n = sum(i["n"] for i in items)
        m1 = st.mean([i["med"].get(30,0) for i in items])
        m3 = st.mean([i["med"].get(90,0) for i in items])
        m6 = st.mean([i["med"].get(180,0) for i in items])
        m12 = st.mean([i["med"].get(365,0) for i in items])
        print(f"{tp:<9s} {len(items):>5d} {tot_n:>6d} | {m1:>+6.1f}% {m3:>+6.1f}% {m6:>+6.1f}% {m12:>+7.1f}%")

    # Export
    with open("/home/user/cyclepapa/data/event_study_v2.csv","w",newline="") as f:
        w = csv.writer(f)
        w.writerow(["transit","natal","aspect","n","med_1mo","med_3mo","med_6mo","med_12mo","pos_1mo","pos_3mo","pos_6mo","pos_12mo"])
        for r in rows:
            tp, np_, asp = r["key"]
            w.writerow([tp, np_, asp, r["n"],
                        f"{r['med'].get(30,0):+.2f}",f"{r['med'].get(90,0):+.2f}",
                        f"{r['med'].get(180,0):+.2f}",f"{r['med'].get(365,0):+.2f}",
                        f"{r['pos'].get(30,0):.1f}",f"{r['pos'].get(90,0):.1f}",
                        f"{r['pos'].get(180,0):.1f}",f"{r['pos'].get(365,0):.1f}"])

if __name__ == "__main__":
    main()
