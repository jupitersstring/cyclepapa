"""
HORIZON-BUCKETED ASYMMETRY — ENTIRE UNIVERSE (13.6k charts), from 2026-07-01.

For every chart in universe_bti_v20.csv (age 0-50):
  score[0..12] monthly -> d3 = max(m1-3)-now, d6 = max(m4-6)-now,
  d12 = max(m7-12)-now.
Rank each horizon. For the union of top-150 per horizon, verify aliveness
via Yahoo quote (cached) and pull washout metrics. Report top alive names
per horizon; export full universe CSV.
"""
import csv, pickle, sys, os, time, json, subprocess
from datetime import datetime, timezone, timedelta
import swisseph as swe
from bti_test import compute_natal
from filter_tradeable_v22 import CURATED_ACTIVE, BAD_NAME, BAD_TICKER

TODAY_DT = datetime(2026, 7, 1)
PIDS = {"Mercury":swe.MERCURY,"Venus":swe.VENUS,"Mars":swe.MARS,
        "Jupiter":swe.JUPITER,"Saturn":swe.SATURN,
        "Uranus":swe.URANUS,"Neptune":swe.NEPTUNE,"Pluto":swe.PLUTO}
NATAL_PTS = ("Sun","Moon","ASC","MC")
ASPECTS = {
    "conj_0":0.0,"sxt_60":60.0,"sq_90":90.0,"tri_120":120.0,"opp_180":180.0,
    "bat_41":41.04,"sept_51":51.43,"qnt_72":72.0,"gart_77":77.04,
    "butt_98":97.92,"phi_137":137.5,"biq_144":144.0,
}
CACHE_DIR = "/home/user/cyclepapa/data/prices_now"

def aspect_orb(a, b, target):
    d = (a - b) % 360
    return min(abs(d - target), abs(d - (360 - target)))

def fetch_prices(tk):
    cache = f"{CACHE_DIR}/{tk}.csv"
    if os.path.exists(cache):
        prices = []
        with open(cache) as f:
            next(f)
            for line in f:
                p = line.strip().split(",")
                if len(p)==2:
                    try: prices.append((p[0], float(p[1])))
                    except: pass
        return prices
    p1 = int(datetime(2024,1,1,tzinfo=timezone.utc).timestamp())
    p2 = int(datetime(2026,7,1,tzinfo=timezone.utc).timestamp())
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{tk}?period1={p1}&period2={p2}&interval=1d"
    try:
        out = subprocess.run(["curl","-sL","-H","User-Agent: Mozilla/5.0","-m","12",url],
                              capture_output=True, text=True, timeout=15).stdout
        j = json.loads(out)
        r = j.get("chart",{}).get("result")
        if not r: return []
        ts = r[0]["timestamp"]; cs = r[0]["indicators"]["quote"][0]["close"]
        prices = [(datetime.utcfromtimestamp(t).strftime("%Y-%m-%d"), c) for t,c in zip(ts,cs) if c]
        if prices:
            os.makedirs(CACHE_DIR, exist_ok=True)
            with open(cache,"w") as f:
                f.write("date,close\n")
                for d,c in prices: f.write(f"{d},{c:.4f}\n")
        time.sleep(0.1)
        return prices
    except: return []

def main():
    with open("/home/user/cyclepapa/data/event_study_keys.pkl","rb") as f:
        key_stats = pickle.load(f)
    key_by_pair = {}
    for (tp, np_, asp_name), v in key_stats.items():
        if v.get("n_w",0)>=10 and v.get("n_c",0)>=5 and "delta_365" in v:
            key_by_pair.setdefault((tp, np_), []).append((ASPECTS[asp_name], v["delta_365"]))

    months = []
    y, m = 2026, 7
    for _ in range(13):
        months.append((y, m)); m += 1
        if m > 12: m = 1; y += 1
    monthly_lons = [ {p: swe.calc_ut(swe.julday(yy, mm, 15, 12.0), pid)[0][0] % 360
                      for p, pid in PIDS.items()} for (yy, mm) in months ]
    def mo_str(i): return f"{months[i][0]}-{months[i][1]:02d}"

    def score(natal, lons):
        s = 0.0
        for tp, tlon in lons.items():
            for np_ in NATAL_PTS:
                if np_ not in natal: continue
                pairs = key_by_pair.get((tp, np_))
                if not pairs: continue
                npon = natal[np_]["lon"]
                for asp_deg, delta in pairs:
                    if aspect_orb(tlon, npon, asp_deg) <= 2.5:
                        s += delta
        return s

    seeds = []
    with open("/home/user/cyclepapa/data/universe_bti_v20.csv") as f:
        for r in csv.DictReader(f):
            tk = (r.get("ticker") or "").strip().upper()
            ipo = (r.get("ipo") or "").strip()
            nm = (r.get("name") or "").strip()
            src = (r.get("source") or "").strip()
            if not tk or not ipo or len(ipo) < 10: continue
            try: yy = int(ipo[:4])
            except: continue
            if not (0 <= 2026 - yy <= 50): continue
            seeds.append({"tk":tk,"ipo":ipo,"name":nm,"src":src})
    seen = set(); unique = []
    for s in seeds:
        k = (s["tk"], s["ipo"])
        if k in seen: continue
        seen.add(k); unique.append(s)
    print(f"Universe: {len(unique)}", file=sys.stderr)

    t0 = time.time()
    rows = []
    for i, s in enumerate(unique):
        if i and i % 2000 == 0:
            print(f"  {i}/{len(unique)}  {time.time()-t0:.0f}s", file=sys.stderr)
        try:
            natal = compute_natal(s["ipo"])
        except: continue
        sc = [score(natal, ml) for ml in monthly_lons]
        now = sc[0]
        w3, w6, w12 = max(sc[1:4]), max(sc[4:7]), max(sc[7:13])
        rows.append({**s, "now":now,
                     "d3":w3-now,  "m3":mo_str(sc[1:4].index(w3)+1),
                     "d6":w6-now,  "m6":mo_str(sc[4:7].index(w6)+4),
                     "d12":w12-now,"m12":mo_str(sc[7:13].index(w12)+7),
                     "tradeable": (src := s["src"]) == "SP500" or s["tk"] in CURATED_ACTIVE})
    print(f"Scored {len(rows)} in {time.time()-t0:.0f}s", file=sys.stderr)

    # Export full universe
    with open("/home/user/cyclepapa/data/horizon_universe_jul2026.csv","w",newline="") as f:
        w = csv.writer(f)
        w.writerow(["ticker","name","source","ipo","score_now",
                    "d3","peak3","d6","peak6","d12","peak12","tradeable"])
        for r in sorted(rows, key=lambda x: -max(x["d3"],x["d6"],x["d12"])):
            w.writerow([r["tk"],r["name"],r["src"],r["ipo"],f"{r['now']:+.0f}",
                        f"{r['d3']:+.0f}",r["m3"],f"{r['d6']:+.0f}",r["m6"],
                        f"{r['d12']:+.0f}",r["m12"],"Y" if r["tradeable"] else "N"])

    # Union of top-150 per horizon -> aliveness check
    cand = {}
    for dkey in ("d3","d6","d12"):
        for r in sorted(rows, key=lambda x: -x[dkey])[:150]:
            cand[(r["tk"], r["ipo"])] = r
    # Always include tradeable top-60 per horizon too
    for dkey in ("d3","d6","d12"):
        for r in sorted([x for x in rows if x["tradeable"]], key=lambda x: -x[dkey])[:60]:
            cand[(r["tk"], r["ipo"])] = r
    print(f"Aliveness-checking {len(cand)} candidates...", file=sys.stderr)

    alive = []
    t1 = time.time()
    for i, r in enumerate(cand.values()):
        if i and i % 50 == 0:
            print(f"  {i}/{len(cand)}  {time.time()-t1:.0f}s alive={len(alive)}", file=sys.stderr)
        prices = fetch_prices(r["tk"])
        if not prices or len(prices) < 60: continue
        last_d, last_c = prices[-1]
        if (TODAY_DT - datetime.strptime(last_d, "%Y-%m-%d")).days > 10: continue
        recycled = prices[0][0] > "2024-06-30" and r["ipo"] < "2023-01-01"
        pdict = dict(prices)
        last_dt = datetime.strptime(last_d, "%Y-%m-%d")
        chg12 = None
        for off in range(15):
            check = (last_dt - timedelta(days=365-off)).strftime("%Y-%m-%d")
            if check in pdict and pdict[check] > 0:
                chg12 = (last_c/pdict[check]-1)*100; break
        hi = max(c for _,c in prices)
        if hi <= 0 or last_c <= 0: continue
        alive.append({**r, "last":last_c, "chg12":chg12,
                      "from_high":(last_c/hi-1)*100, "recycled":recycled})
    print(f"Alive: {len(alive)}", file=sys.stderr)

    def wash(r):
        c = r["chg12"]
        if c is None: return 1.0
        if c <= -50: return 1.5
        if c <= -30: return 1.3
        if c <= -10: return 1.15
        if c >= 100: return 0.7
        return 1.0

    for label, dkey, mkey, note in [
        ("3-MONTH (peak Aug-Oct 2026)", "d3", "m3", "exit at/before Node ingress + trine #1 fade"),
        ("6-MONTH (peak Nov 2026-Jan 2027)", "d6", "m6", "U-P trine #2 Nov 29"),
        ("12-MONTH (peak Feb-Jul 2027)", "d12", "m12", "trine #3 Jun 15 2027"),
    ]:
        rs = sorted([a for a in alive if not a["recycled"] and a[dkey] > 0],
                    key=lambda a: -a[dkey]*wash(a))
        print(f"\n{'='*160}")
        print(f"{label} — top 20 alive, ranked by Δwindow x washout   [{note}]")
        print(f"{'='*160}")
        print(f"{'#':>3s} {'Tkr':<6s} {'Src':<7s} {'IPO':<11s} {'Now':>5s} {'Δwin':>5s} {'PkMo':<8s} "
              f"{'pr12':>6s} {'fHi':>6s} {'$':>9s} {'Trd':>3s} {'ASYM':>6s}  Name")
        for i, a in enumerate(rs[:20], 1):
            c12 = f"{a['chg12']:+5.0f}%" if a['chg12'] is not None else "   n/a"
            print(f"{i:3d} {a['tk']:<6s} {a['src']:<7s} {a['ipo']:<11s} {a['now']:>+4.0f} {a[dkey]:>+4.0f} {a[mkey]:<8s} "
                  f"{c12:>6s} {a['from_high']:+5.0f}% {a['last']:>9.2f} "
                  f"{'Y' if a['tradeable'] else 'N':>3s} {a[dkey]*wash(a):>6.0f}  {(a['name'] or '')[:26]}")

    with open("/home/user/cyclepapa/data/horizon_alive_jul2026.csv","w",newline="") as f:
        w = csv.writer(f)
        w.writerow(["ticker","name","source","ipo","score_now","last","chg_12mo","from_high",
                    "d3","peak3","asym3","d6","peak6","asym6","d12","peak12","asym12",
                    "tradeable","recycled"])
        for a in sorted(alive, key=lambda x: -max(x["d3"],x["d6"],x["d12"])*wash(x)):
            w.writerow([a["tk"],a["name"],a["src"],a["ipo"],f"{a['now']:+.0f}",
                        f"{a['last']:.2f}",
                        f"{a['chg12']:+.1f}" if a['chg12'] is not None else "",
                        f"{a['from_high']:+.1f}",
                        f"{a['d3']:+.0f}",a["m3"],f"{a['d3']*wash(a):.0f}",
                        f"{a['d6']:+.0f}",a["m6"],f"{a['d6']*wash(a):.0f}",
                        f"{a['d12']:+.0f}",a["m12"],f"{a['d12']*wash(a):.0f}",
                        "Y" if a["tradeable"] else "N","Y" if a["recycled"] else ""])
    print(f"\nExported -> data/horizon_universe_jul2026.csv (all) + data/horizon_alive_jul2026.csv (alive)")

if __name__ == "__main__":
    main()
