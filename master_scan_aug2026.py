"""
MASTER SCAN — July 2026. Bullish + bearish per 3/6/12mo horizon + cult/
explosive overlay.

Universe: verified-alive names (horizon_alive + deep_asymmetric survivors)
plus SP500 names with cached prices.

Per chart:
  BULLISH d3/d6/d12 = max(window score) - now   (astro building)
  BEARISH b3/b6/b12 = now - min(window score)   (astro decaying), ranked
     for shorts when current price is elevated (pr12 > +30%) or the chart
     is at a high score now.
  CULT/EXPLOSIVE score = validated magnitude/cult signatures:
     natal UraPlu septile<=3 (+2 | 75x median), UraPlu sextile<=3 (+1.5),
     NepPlu sextile<=3 (+1.5), AVIS-DNA Sun-Nep<=5 (+2), GC<=3 (+1.5),
     stellium>=4 (+1), transit Pluto<=3 to Sun/Moon (+2, MEME doctrine),
     transit Neptune<=3 to Sun/Moon (+2, hype ignition), Jupiter conj
     natal Neptune <=3 within next 6mo (+2, Gidel bubble trigger),
     age<=5 (+1, plastic identity), Silas Jupiter eclipse-degree
     reactivation in next 6mo (+1.5).
  EXPLOSIVE composite = cult x (1 + max(d3,d6,d12)/150) x washout.
"""
import csv, pickle, sys, os, time
from datetime import datetime, timedelta
import swisseph as swe
from bti_test import compute_natal, jd_of
from bti_v19_empirical import closest_hard
from eclipse_database import build_eclipse_database
from silas_rules import eclipse_reactivations, eclipse_exit_flag

TY, TM = 2026, 8
PIDS = {"Mercury":swe.MERCURY,"Venus":swe.VENUS,"Mars":swe.MARS,
        "Jupiter":swe.JUPITER,"Saturn":swe.SATURN,
        "Uranus":swe.URANUS,"Neptune":swe.NEPTUNE,"Pluto":swe.PLUTO}
NATAL_PTS = ("Sun","Moon","ASC","MC")
ASPECTS = {
    "conj_0":0.0,"sxt_60":60.0,"sq_90":90.0,"tri_120":120.0,"opp_180":180.0,
    "bat_41":41.04,"sept_51":51.43,"qnt_72":72.0,"gart_77":77.04,
    "butt_98":97.92,"phi_137":137.5,"biq_144":144.0,
}
GC_LON = 267.0
CACHE = "/home/user/cyclepapa/data/prices_now"

def a_orb(a, b, t):
    d = (a - b) % 360
    return min(abs(d - t), abs(d - (360 - t)))

def c_orb(a, b):
    d = abs(a - b) % 360
    return min(d, 360 - d)

def load_prices(tk):
    p = f"{CACHE}/{tk}.csv"
    if not os.path.exists(p): return []
    out = []
    with open(p) as f:
        next(f)
        for line in f:
            r = line.strip().split(",")
            if len(r)==2:
                try: out.append((r[0], float(r[1])))
                except: pass
    return out

def main():
    with open("/home/user/cyclepapa/data/event_study_keys.pkl","rb") as f:
        ks = pickle.load(f)
    key_by_pair = {}
    for (tp, np_, an), v in ks.items():
        if v.get("n_w",0)>=10 and v.get("n_c",0)>=5 and "delta_365" in v:
            key_by_pair.setdefault((tp, np_), []).append((ASPECTS[an], v["delta_365"]))

    months = []
    y, m = TY, TM
    for _ in range(13):
        months.append((y, m)); m += 1
        if m > 12: m = 1; y += 1
    mlons = [ {p: swe.calc_ut(swe.julday(yy, mm, 15, 12.0), pid)[0][0] % 360
               for p, pid in PIDS.items()} for (yy, mm) in months ]
    def mo_str(i): return f"{months[i][0]}-{months[i][1]:02d}"

    def score(natal, lons):
        s = 0.0
        for tp, tl in lons.items():
            for np_ in NATAL_PTS:
                if np_ not in natal: continue
                prs = key_by_pair.get((tp, np_))
                if not prs: continue
                nl = natal[np_]["lon"]
                for deg, d in prs:
                    if a_orb(tl, nl, deg) <= 2.5:
                        s += d
        return s

    print("Building eclipse DB...", file=sys.stderr)
    edb = build_eclipse_database(2023, 2028)

    # Universe: union of alive cohorts + name/ipo from prior CSVs
    seen = {}
    for path, tkcol, ipocol, ncol in [
        ("/home/user/cyclepapa/data/horizon_alive_jul2026.csv","ticker","ipo","name"),
        ("/home/user/cyclepapa/data/deep_asymmetric_jul2026.csv","ticker","ipo","name"),
        ("/home/user/cyclepapa/data/best_opps_jul2026_spec.csv","ticker","ipo",None),
    ]:
        try:
            with open(path) as f:
                for r in csv.DictReader(f):
                    tk = r[tkcol].strip().upper()
                    ipo = r[ipocol].strip()
                    if r.get("recycled","") == "Y" or r.get("recycled_flag","") == "Y": continue
                    if tk not in seen and ipo:
                        seen[tk] = {"tk":tk,"ipo":ipo,"name":(r.get(ncol,"") if ncol else tk)}
        except FileNotFoundError: pass
    # SP500 with cached prices
    with open("/home/user/cyclepapa/data/sp500_ipo_dates.csv") as f:
        for r in csv.DictReader(f):
            tk = r["ticker"].strip().upper()
            ipo = (r.get("ipo_date") or "").strip()
            if tk in seen or not ipo or len(ipo)<10: continue
            if os.path.exists(f"{CACHE}/{tk}.csv"):
                seen[tk] = {"tk":tk,"ipo":ipo,"name":r.get("name","")}
    U = list(seen.values())
    print(f"Universe: {len(U)}", file=sys.stderr)

    rows = []
    t0 = time.time()
    for i, s in enumerate(U):
        if i and i % 100 == 0: print(f"  {i}/{len(U)} {time.time()-t0:.0f}s", file=sys.stderr)
        try:
            natal = compute_natal(s["ipo"])
        except: continue
        prices = load_prices(s["tk"])
        if not prices or len(prices) < 60: continue
        last_d, last_c = prices[-1]
        if last_c <= 0: continue
        ldt = datetime.strptime(last_d, "%Y-%m-%d")
        if (datetime(2026,8,19) - ldt).days > 10: continue
        pdict = dict(prices)
        chg12 = None
        for off in range(15):
            k = (ldt - timedelta(days=365-off)).strftime("%Y-%m-%d")
            if k in pdict and pdict[k] > 0:
                chg12 = (last_c/pdict[k]-1)*100; break
        hi = max(c for _, c in prices)
        from_high = (last_c/hi - 1)*100 if hi > 0 else None

        sc = [score(natal, ml) for ml in mlons]
        now = sc[0]
        d3  = max(sc[1:4]) - now;  m3  = mo_str(sc[1:4].index(max(sc[1:4])) + 1)
        d6  = max(sc[4:7]) - now;  m6  = mo_str(sc[4:7].index(max(sc[4:7])) + 4)
        d12 = max(sc[7:13]) - now; m12 = mo_str(sc[7:13].index(max(sc[7:13])) + 7)
        b3  = now - min(sc[1:4]);  bm3 = mo_str(sc[1:4].index(min(sc[1:4])) + 1)
        b6  = now - min(sc[4:7]);  bm6 = mo_str(sc[4:7].index(min(sc[4:7])) + 4)
        b12 = now - min(sc[7:13]); bm12 = mo_str(sc[7:13].index(min(sc[7:13])) + 7)

        # Cult / explosive
        sun = natal["Sun"]["lon"]; moon = natal.get("Moon",{}).get("lon")
        nep = natal["Neptune"]["lon"]; ura = natal["Uranus"]["lon"]; plu = natal["Pluto"]["lon"]
        age = TY - int(s["ipo"][:4])
        cult = 0.0; tags = []
        if a_orb(ura, plu, 51.43) <= 3: cult += 2.0; tags.append("UrPl-sept")
        if a_orb(ura, plu, 60.0)  <= 3: cult += 1.5; tags.append("UrPl-sxt")
        if a_orb(nep, plu, 60.0)  <= 3: cult += 1.5; tags.append("NePl-sxt")
        if c_orb(sun, nep) <= 5:        cult += 2.0; tags.append("AVIS")
        if min(closest_hard(natal[p]["lon"], GC_LON)
               for p in ("Jupiter","Saturn","Uranus","Neptune","Pluto") if p in natal) <= 3:
            cult += 1.5; tags.append("GC")
        pos = [natal[p]["lon"] for p in ("Sun","Moon","Mars","Jupiter","Saturn","Uranus","Neptune","Pluto") if p in natal]
        if max(sum(1 for q in pos if c_orb(q, p0) <= 15) for p0 in pos) >= 4:
            cult += 1.0; tags.append("Stell")
        t_now = mlons[0]
        if closest_hard(t_now["Pluto"], sun) <= 3 or (moon is not None and closest_hard(t_now["Pluto"], moon) <= 3):
            cult += 2.0; tags.append("tPlu-light")
        if closest_hard(t_now["Neptune"], sun) <= 3 or (moon is not None and closest_hard(t_now["Neptune"], moon) <= 3):
            cult += 2.0; tags.append("tNep-light")
        jupnep6 = min(c_orb(mlons[k]["Jupiter"], nep) for k in range(0, 7))
        if jupnep6 <= 3: cult += 2.0; tags.append("Gidel-JupNep")
        if age <= 5: cult += 1.0; tags.append("young")
        reacts6 = []
        for k in range(0, 7):
            yy, mm = months[k]
            reacts6 += [r for r in eclipse_reactivations(natal, edb, yy, mm)
                        if r["transiter"] == "Jupiter"]
        if reacts6: cult += 1.5; tags.append("Silas-JupReact")

        wash = 1.0
        if chg12 is not None:
            if chg12 <= -50: wash = 1.5
            elif chg12 <= -30: wash = 1.3
            elif chg12 <= -10: wash = 1.15
            elif chg12 >= 100: wash = 0.75
        explosive = cult * (1 + max(d3, d6, d12)/150.0) * wash

        # Bearish context: fresh-eclipse exit + Saturn reactivation next 6mo
        sat_react = False
        for k in range(0, 7):
            yy, mm = months[k]
            if any(r["transiter"] == "Saturn" for r in eclipse_reactivations(natal, edb, yy, mm)):
                sat_react = True; break

        rows.append({**s,"age":age,"last":last_c,"chg12":chg12,"from_high":from_high,
                     "now":now,"d3":d3,"m3":m3,"d6":d6,"m6":m6,"d12":d12,"m12":m12,
                     "b3":b3,"bm3":bm3,"b6":b6,"bm6":bm6,"b12":b12,"bm12":bm12,
                     "cult":cult,"tags":tags,"wash":wash,"explosive":explosive,
                     "sat_react":sat_react})
    print(f"Scored {len(rows)} alive names", file=sys.stderr)

    def p12(v): return f"{v:+5.0f}%" if v is not None else "  n/a"

    # ---- BULLISH per horizon ----
    for lbl, dk, mk in [("BULLISH 3-MONTH","d3","m3"),
                         ("BULLISH 6-MONTH","d6","m6"),
                         ("BULLISH 12-MONTH","d12","m12")]:
        rs = sorted([r for r in rows if r[dk] > 0], key=lambda r: -r[dk]*r["wash"])
        print(f"\n{'='*150}\n{lbl} — top 15 by Δ x washout\n{'='*150}")
        print(f"{'#':>3s} {'Tkr':<6s} {'Now':>5s} {'Δ':>5s} {'PkMo':<8s} {'pr12':>6s} {'fHi':>6s} {'Cult':>5s} {'Expl':>5s}  Tags / Name")
        for i, r in enumerate(rs[:15], 1):
            print(f"{i:3d} {r['tk']:<6s} {r['now']:>+4.0f} {r[dk]:>+4.0f} {r[mk]:<8s} "
                  f"{p12(r['chg12']):>6s} {r['from_high']:+5.0f}% {r['cult']:>5.1f} {r['explosive']:>5.1f}  "
                  f"{','.join(r['tags'][:4]):<28s} {(r['name'] or '')[:20]}")

    # ---- BEARISH per horizon (decay + elevation) ----
    for lbl, bk, bmk in [("BEARISH 3-MONTH","b3","bm3"),
                          ("BEARISH 6-MONTH","b6","bm6"),
                          ("BEARISH 12-MONTH","b12","bm12")]:
        # bearish rank: astro decay x elevation (ran-up price or high current score)
        def bear_rank(r):
            elev = 1.0
            if r["chg12"] is not None and r["chg12"] >= 100: elev = 1.5
            elif r["chg12"] is not None and r["chg12"] >= 40: elev = 1.25
            if r["sat_react"]: elev *= 1.2
            return r[bk] * elev
        rs = sorted([r for r in rows if r[bk] > 40], key=lambda r: -bear_rank(r))
        print(f"\n{'='*150}\n{lbl} — top 15 by astro-decay x price-elevation (short/avoid candidates)\n{'='*150}")
        print(f"{'#':>3s} {'Tkr':<6s} {'Now':>5s} {'-Δ':>5s} {'LowMo':<8s} {'pr12':>6s} {'fHi':>6s} {'SatR':>4s}  Name")
        for i, r in enumerate(rs[:15], 1):
            print(f"{i:3d} {r['tk']:<6s} {r['now']:>+4.0f} {-r[bk]:>+4.0f} {r[bmk]:<8s} "
                  f"{p12(r['chg12']):>6s} {r['from_high']:+5.0f}% {'Y' if r['sat_react'] else '':>4s}  {(r['name'] or '')[:24]}")

    # ---- CULT / EXPLOSIVE shortlist ----
    rs = sorted(rows, key=lambda r: -r["explosive"])
    print(f"\n{'='*160}\nCULT / EXPLOSIVE SHORTLIST — top 20 by composite (cult signatures x forward build x washout)\n{'='*160}")
    print(f"{'#':>3s} {'Tkr':<6s} {'Age':>3s} {'Now':>5s} {'bestΔ':>5s} {'pr12':>6s} {'fHi':>6s} {'Cult':>5s} {'Expl':>6s}  Tags / Name")
    for i, r in enumerate(rs[:20], 1):
        bd = max(r["d3"], r["d6"], r["d12"])
        print(f"{i:3d} {r['tk']:<6s} {r['age']:>3d} {r['now']:>+4.0f} {bd:>+4.0f} "
              f"{p12(r['chg12']):>6s} {r['from_high']:+5.0f}% {r['cult']:>5.1f} {r['explosive']:>6.1f}  "
              f"{','.join(r['tags']):<40s} {(r['name'] or '')[:18]}")

    # Export
    with open("/home/user/cyclepapa/data/master_scan_aug2026.csv","w",newline="") as f:
        w = csv.writer(f)
        w.writerow(["ticker","name","ipo","age","last","chg12","from_high","score_now",
                    "d3","peak3","d6","peak6","d12","peak12",
                    "b3","low3","b6","low6","b12","low12",
                    "cult","tags","washout","explosive","saturn_reactivation"])
        for r in sorted(rows, key=lambda x: -x["explosive"]):
            w.writerow([r["tk"],r["name"],r["ipo"],r["age"],f"{r['last']:.2f}",
                        f"{r['chg12']:+.1f}" if r['chg12'] is not None else "",
                        f"{r['from_high']:+.1f}",f"{r['now']:+.0f}",
                        f"{r['d3']:+.0f}",r["m3"],f"{r['d6']:+.0f}",r["m6"],
                        f"{r['d12']:+.0f}",r["m12"],
                        f"{r['b3']:+.0f}",r["bm3"],f"{r['b6']:+.0f}",r["bm6"],
                        f"{r['b12']:+.0f}",r["bm12"],
                        f"{r['cult']:.1f}","|".join(r["tags"]),f"{r['wash']:.2f}",
                        f"{r['explosive']:.1f}","Y" if r["sat_react"] else ""])
    print(f"\nExported -> data/master_scan_aug2026.csv")

if __name__ == "__main__":
    main()
