"""
KEY-IN-LOCK SECTOR-SYMPATHY SCREENER — ported from the astro-ipo-asymmetry
branch's MRNA RCA, rebuilt on this branch's provenance-tiered compendium.

Mechanism (the MRNA lesson): a sector catalyst detonates a SECTOR-LOADED
chart. Generic money-point screens miss it. The lock = the stock's own
sector rulers, loaded in the natal chart (dignity, exact fusion,
angularity, station). The key = a slow transit or eclipse hitting the
LOADED ruler.

Upgrades over the source branch:
  - Rulers come from rulership_compendium with our EMPIRICAL tier weights
    (modern 1.0 / classical 0.7), dual rulers for contested signs.
  - Validated on the 152-parabolic corpus BEFORE trusting the forward
    list (loading vs realized multiple).
  - Forward list restricted to price-verified alive names (Aug 2026
    refresh), not training-knowledge guesses.

Scoring:
  natal_loading(planet): domicile +1.0 / exaltation +0.7; fusion bonus
    quadratic in tightness (1.5*(1-orb/3)^2, x2 under 0.25 deg);
    angular conj ASC/MC <=5 +0.6; station +0.5 (Mercury..Saturn).
  sector_loading: sum over rulers of tier_w * loading; x1.3 if >=3
    rulers loaded >=1.0 (full-stack).
  keylock 12mo: monthly Jup/Sat/Ura/Nep/Plu hard aspects <=2.5 deg to
    natal sector-ruler positions, weight = tier_w x (2.0 if that ruler
    loaded >=1.0 else 1.5) x exactness; eclipses <=2.0 deg add 2.0 x
    load-mult. Peak = best rolling 3-month window; position-by = 6 weeks
    prior (Silas).
"""
import csv, math, sys
import swisseph as swe
from bti_test import compute_natal, jd_of
from rulership_compendium import sector_rulers_for
from eclipse_database import build_eclipse_database

DOMICILE = {"Sun":[4],"Moon":[3],"Mercury":[2,5],"Venus":[1,6],"Mars":[0,7],
            "Jupiter":[8,11],"Saturn":[9,10],"Uranus":[10],"Neptune":[11],"Pluto":[7]}
EXALT = {"Sun":0,"Moon":1,"Mercury":5,"Venus":11,"Mars":9,"Jupiter":3,"Saturn":6}
STATION_SPD = {"Mercury":0.06,"Venus":0.05,"Mars":0.03,"Jupiter":0.012,"Saturn":0.008}
SLOW = {"Jupiter":swe.JUPITER,"Saturn":swe.SATURN,"Uranus":swe.URANUS,
        "Neptune":swe.NEPTUNE,"Pluto":swe.PLUTO}
PLANETS = ("Sun","Moon","Mercury","Venus","Mars","Jupiter","Saturn","Uranus","Neptune","Pluto")

def c_orb(a, b):
    d = abs(a - b) % 360
    return min(d, 360 - d)

def hard_orb(a, b):
    return min(min(c_orb(a, b + s*asp) for s in (1,-1)) for asp in (0, 90, 180))

def natal_loading(natal, planet):
    if planet not in natal: return 0.0, []
    p = natal[planet]; load = 0.0; why = []
    if p.get("sign") in DOMICILE.get(planet, []): load += 1.0; why.append("domicile")
    elif EXALT.get(planet) == p.get("sign"): load += 0.7; why.append("exalt")
    fus = min((c_orb(p["lon"], natal[q]["lon"]) for q in PLANETS
               if q != planet and q in natal), default=99)
    if fus <= 3.0:
        b = 1.5 * (1 - fus/3.0)**2
        if fus < 0.25: b *= 2
        load += b; why.append(f"fusion{fus:.2f}")
    ang = min(c_orb(p["lon"], natal[x]["lon"]) for x in ("ASC","MC") if x in natal)
    if ang <= 5.0: load += 0.6; why.append("angular")
    spd = abs(p.get("speed", 1))
    if planet in STATION_SPD and spd < STATION_SPD[planet]:
        load += 0.5; why.append("station")
    return load, why

def sector_loading(natal, sector):
    rulers = sector_rulers_for(sector, "modern")
    total = 0.0; loaded = {}; detail = []
    for planet, tier, w, _src in rulers:
        ld, why = natal_loading(natal, planet)
        if planet in loaded: continue  # dedupe dual-listed rulers
        loaded[planet] = ld
        total += w * ld
        if ld > 0: detail.append(f"{planet}={ld:.1f}({','.join(why)})")
    n_loaded = sum(1 for v in loaded.values() if v >= 1.0)
    if n_loaded >= 3: total *= 1.3; detail.append("FULLSTACK x1.3")
    return total, loaded, detail

def keylock_score(natal, sector, edb, y0, m0, months=13):
    rulers = {p: (w, tier) for p, tier, w, _ in sector_rulers_for(sector, "modern")}
    if not rulers: return 0.0, None, []
    _, loaded, _ = sector_loading(natal, sector)
    mo = []; y, m = y0, m0
    for _ in range(months):
        mo.append((y, m)); m += 1
        if m > 12: m = 1; y += 1
    monthly = []
    for (yy, mm) in mo:
        jd = jd_of(yy, mm, 15, 12.0)
        s = 0.0; hits = []
        for tp, pid in SLOW.items():
            tl = swe.calc_ut(jd, pid)[0][0] % 360
            for rp, (w, _t) in rulers.items():
                if rp not in natal: continue
                o = hard_orb(tl, natal[rp]["lon"])
                if o <= 2.5:
                    lm = 2.0 if loaded.get(rp, 0) >= 1.0 else 1.5
                    s += w * lm * (1 - o/2.5)
                    hits.append(f"{tp}>{rp}")
        for e in edb:
            if abs(e["jd"] - jd) < 16:  # eclipse this month
                for rp, (w, _t) in rulers.items():
                    if rp not in natal: continue
                    if hard_orb(e["lon"], natal[rp]["lon"]) <= 2.0:
                        lm = 2.0 if loaded.get(rp, 0) >= 1.0 else 1.5
                        s += 2.0 * w * lm
                        hits.append(f"ECL>{rp}")
        monthly.append((s, hits))
    best_i, best_w = 0, -1
    for i in range(len(monthly) - 2):
        wsum = sum(monthly[j][0] for j in range(i, i+3))
        if wsum > best_w: best_w, best_i = wsum, i
    peak = f"{mo[best_i+1][0]}-{mo[best_i+1][1]:02d}"
    hits = sorted(set(h for j in range(best_i, best_i+3) for h in monthly[j][1]))
    return best_w, peak, hits

def main():
    edb = build_eclipse_database(2015, 2028)

    # ---------- VALIDATION on 152 corpus ----------
    from parabolic_corpus import PARABOLIC_BOTTOMS
    from sector_astro import SECTOR as CSEC
    xs, ys = [], []
    for tk, ipo, bot, top, mult, speed, note in PARABOLIC_BOTTOMS:
        sec = CSEC.get(tk)
        if not sec: continue
        try: natal = compute_natal(ipo)
        except: continue
        ld, _, _ = sector_loading(natal, sec)
        xs.append(ld); ys.append(math.log10(mult))
    n = len(xs)
    mx, my = sum(xs)/n, sum(ys)/n
    cov = sum((a-mx)*(b-my) for a,b in zip(xs,ys))
    sx = math.sqrt(sum((a-mx)**2 for a in xs)); sy = math.sqrt(sum((b-my)**2 for b in ys))
    r = cov/(sx*sy) if sx*sy else 0
    srt = sorted(zip(xs, ys))
    lo = [b for _, b in srt[:n//3]]; hi = [b for _, b in srt[-(n//3):]]
    med = lambda v: sorted(v)[len(v)//2]
    print(f"VALIDATION (152 corpus): sector_loading vs log10(multiple), n={n}")
    print(f"  Pearson r = {r:+.3f}")
    print(f"  median multiple: bottom-tertile loading {10**med(lo):.1f}x | top-tertile {10**med(hi):.1f}x")

    # ---------- FORWARD key-in-lock on verified-alive labeled names ----------
    from bti_v24_macro import MODERN_SECTOR
    alive = {}
    with open("data/master_scan_aug2026.csv") as f:
        for row in csv.DictReader(f):
            alive[row["ticker"]] = row
    from sector_astro import SECTOR as CSEC2
    labels = dict(MODERN_SECTOR)
    for k, v in CSEC2.items(): labels.setdefault(k, v)
    out = []
    for tk, sec in labels.items():
        if tk not in alive: continue
        row = alive[tk]
        try: natal = compute_natal(row["ipo"])
        except: continue
        ld, loaded, detail = sector_loading(natal, sec)
        ks, peak, hits = keylock_score(natal, sec, edb, 2026, 8)
        if ks is None: continue
        out.append({"tk":tk,"sec":sec,"load":ld,"key":ks,"tot":ld*0.6+ks,
                    "peak":peak,"hits":hits,"detail":detail,
                    "chg12":row["chg12"],"fhi":row["from_high"]})
    out.sort(key=lambda r: -r["tot"])
    print(f"\nKEY-IN-LOCK FORWARD LIST — {len(out)} labeled alive names, next 13mo")
    print(f"{'#':>3s} {'Tkr':<6s} {'Sector':<10s} {'Load':>5s} {'Key':>5s} {'Tot':>5s} {'Peak':<8s} {'pr12':>6s} {'fHi':>6s}  Lock detail | window hits")
    for i, r in enumerate(out[:25], 1):
        print(f"{i:3d} {r['tk']:<6s} {r['sec']:<10s} {r['load']:>5.1f} {r['key']:>5.1f} {r['tot']:>5.1f} "
              f"{r['peak']:<8s} {r['chg12']:>6s} {r['fhi']:>6s}  "
              f"{'; '.join(r['detail'][:3]):<46s} | {','.join(r['hits'][:4])}")
    with open("data/keylock_forward.csv","w",newline="") as f:
        w = csv.writer(f)
        w.writerow(["ticker","sector","loading","keyscore","total","peak_window","chg12","from_high","lock_detail","window_hits"])
        for r in out:
            w.writerow([r["tk"],r["sec"],f"{r['load']:.2f}",f"{r['key']:.2f}",f"{r['tot']:.2f}",
                        r["peak"],r["chg12"],r["fhi"],";".join(r["detail"]),";".join(r["hits"])])
    print("\nExported -> data/keylock_forward.csv")

if __name__ == "__main__":
    main()
