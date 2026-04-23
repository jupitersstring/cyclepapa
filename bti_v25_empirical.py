"""
v25 — INCORPORATES EMPIRICAL IMPROVEMENTS validated on 152 corpus:

New layers on top of v24 macro-regime:
  (a) NATAL Galactic Center proximity: outer planet natally <=3° from 267°
      Sag multiplies composite by 1.4x (empirical: mean rally 164x vs 61x,
      median 15x vs 10x).
  (b) Profection Lord-of-the-Year transit activation at CURRENT month:
      if an outer is within 5° of the LoY's natal longitude, +0.8 bonus.
  (c) Jupiter planetary-station proximity (±10 days) at CURRENT month:
      +1.0 bottom-release bonus (Jupiter stations cluster at bottoms,
      empirical 12.5% vs 4% baseline).
  (d) Saturn station proximity (±10 days) at PEAK month: -1.5 penalty
      to asymmetry (exit signal, 10.5% at peaks vs 5.9% at bottoms).
  (e) Heliocentric Jupiter-Saturn ≤10° hard aspect at PEAK month: -2.0
      penalty on asymmetry (STRONGEST empirical exit signal: 48.7% of
      peaks vs 25% of bottoms).
  (f) True-Node ingress within 30 days of PEAK month: -0.8 penalty
      (30% of peaks vs 17% of bottoms).
  (g) Heliocentric Mars-Jupiter ≤10° at CURRENT month: +0.6 bottom bonus
      (24-27% at bottom/mid vs 14.5% at peak).
  (h) Transit-Mercury retrograde: VOLATILITY flag (not directional) —
      affects bubblish_peak capacity but not directional asymmetry
      (Ni-Wang-Yin 2020).

Universe: full universe_bti_v20.csv (12,086 Ritter + SP500 merged entries,
age 1-40, deduped).
"""
import math, csv, sys, time
import swisseph as swe
from bti_test import compute_natal, transits_at, jd_of
from bti_v4 import yx
from eclipse_database import build_eclipse_database, eclipse_hits_natal
from bti_v19_empirical import SINGLE_PLANET_WEIGHTS, COMPOUND_RULES, bucket_weight, closest_hard, orb
from bti_v21_forward import saturn_pop_month
from bti_v23_sector_aware import SECTOR_WEIGHTS, get_sector, sector_bucket_weight
from bti_v24_macro import MODERN_SECTOR, modern_sector_of
from macro_regime import macro_regime_multiplier, dignity_multiplier

START_Y, START_M = 2026, 4
MONTHS = 24
GC_LON = 267.0

PLANET_IDS = {"Jupiter":swe.JUPITER,"Saturn":swe.SATURN,"Uranus":swe.URANUS,
              "Neptune":swe.NEPTUNE,"Pluto":swe.PLUTO,"Mercury":swe.MERCURY,
              "Venus":swe.VENUS,"Mars":swe.MARS,"Sun":swe.SUN,"Moon":swe.MOON}

# ============================================================
# (a) Natal GC proximity — cached per natal
# ============================================================
def natal_gc_amplifier(natal):
    """Return 1.4 if outer ≤3° of 267° (GC) natally, else 1.0."""
    for outer in ("Jupiter","Saturn","Uranus","Neptune","Pluto"):
        if outer in natal and closest_hard(natal[outer]["lon"], GC_LON) <= 3:
            return 1.4
    return 1.0

# ============================================================
# (b) Profection Lord-of-the-Year activation
# ============================================================
SIGN_RULERS_TRAD = {0:"Mars",1:"Venus",2:"Mercury",3:"Moon",4:"Sun",
                    5:"Mercury",6:"Venus",7:"Mars",8:"Jupiter",
                    9:"Saturn",10:"Saturn",11:"Jupiter"}

def profection_bonus(natal, y, m, ipo_year):
    """If outer transit ≤5° of natal LoY's longitude, return +0.8."""
    try:
        asc_sign = int(natal["ASC"]["lon"] // 30)
    except:
        return 0.0
    age = y - ipo_year
    prof_sign = (asc_sign + (age % 12)) % 12
    ruler_name = SIGN_RULERS_TRAD[prof_sign]
    if ruler_name not in natal: return 0.0
    ruler_lon = natal[ruler_name]["lon"]
    trans = transits_at(y, m)
    best = 99
    for outer in ("Jupiter","Saturn","Uranus","Neptune","Pluto"):
        o = closest_hard(trans[outer]["lon"], ruler_lon)
        if o < best: best = o
    if best <= 5:
        return 0.8 * (5 - best) / 5  # scale: 0 at 5°, 0.8 at exact
    return 0.0

# ============================================================
# (c,d) Planetary station proximity — days to nearest station
# ============================================================
def station_days(planet_id, jd_center, search=30):
    """Days to nearest station within +/-search days (None if beyond)."""
    speeds = []
    for off in range(-search, search+1, 2):
        s = swe.calc_ut(jd_center + off, planet_id)[0][3]
        speeds.append((off, s))
    best = 999
    for i in range(1, len(speeds)):
        if speeds[i-1][1] * speeds[i][1] < 0:
            off = speeds[i][0]
            d = abs(off)
            if d < best: best = d
    return best if best < 999 else None

def jupiter_station_bonus(y, m):
    """+1.0 if Jupiter station within 10 days of phase midpoint."""
    jd = jd_of(y, m, 15, 12.0)
    d = station_days(swe.JUPITER, jd, search=25)
    if d is not None and d <= 10:
        return 1.0 * (10 - d) / 10
    return 0.0

def saturn_station_penalty(y, m):
    """+1.5 asymmetry penalty if Saturn station within 10 days of peak month."""
    jd = jd_of(y, m, 15, 12.0)
    d = station_days(swe.SATURN, jd, search=25)
    if d is not None and d <= 10:
        return 1.5 * (10 - d) / 10
    return 0.0

# ============================================================
# (e) Heliocentric Jupiter-Saturn ≤10° peak penalty
# ============================================================
def helio_lon(pid, jd):
    return swe.calc_ut(jd, pid, swe.FLG_HELCTR)[0][0] % 360

def helio_jup_sat_peak_penalty(y, m):
    """Return penalty 0..2.0 if helio Jup-Sat hard aspect tight at peak month."""
    jd = jd_of(y, m, 15, 12.0)
    jl = helio_lon(swe.JUPITER, jd)
    sl = helio_lon(swe.SATURN, jd)
    o = closest_hard(jl, sl)
    if o <= 10:
        return 2.0 * (10 - o) / 10
    return 0.0

def helio_mars_jup_bottom_bonus(y, m):
    """Return bonus 0..0.6 if helio Mars-Jup ≤10° at bottom/current month."""
    jd = jd_of(y, m, 15, 12.0)
    ml = helio_lon(swe.MARS, jd)
    jl = helio_lon(swe.JUPITER, jd)
    o = closest_hard(ml, jl)
    if o <= 10:
        return 0.6 * (10 - o) / 10
    return 0.0

# ============================================================
# (f) Node ingress proximity at peak
# ============================================================
def node_ingress_days(jd_center):
    cur = int(swe.calc_ut(jd_center, swe.TRUE_NODE)[0][0] // 30)
    best = 999
    for off in range(-60, 61, 2):
        s = int(swe.calc_ut(jd_center + off, swe.TRUE_NODE)[0][0] // 30)
        if s != cur:
            d = abs(off)
            if d < best: best = d
    return best if best < 999 else None

def node_ingress_peak_penalty(y, m):
    jd = jd_of(y, m, 15, 12.0)
    d = node_ingress_days(jd)
    if d is not None and d <= 30:
        return 0.8 * (30 - d) / 30
    return 0.0

# ============================================================
# (h) Mercury retrograde volatility flag
# ============================================================
def mercury_retro_volatility(y, m):
    """Return +0.3 volatility bonus (not asymmetry) if Mercury retrograde."""
    trans = transits_at(y, m)
    return 0.3 if trans["Mercury"]["retro"] else 0.0

# ============================================================
# Score snapshot v25
# ============================================================
def score_snapshot_v25(natal, y, m, db, sector_base, modern_sec, ipo_year):
    trans = transits_at(y, m)
    targets = {p: natal[p]["lon"] for p in ("Sun","Moon","ASC","MC") if p in natal}
    outer_orbs = {}
    for outer in ("Jupiter","Saturn","Uranus","Neptune","Pluto"):
        best = 99
        for tlon in targets.values():
            o = closest_hard(trans[outer]["lon"], tlon)
            if o < best: best = o
        outer_orbs[outer] = best

    # Sector-aware bucket + dignity (v23/v24)
    single_score = 0
    for p, o in outer_orbs.items():
        w = sector_bucket_weight(p, o, sector_base)
        dig = dignity_multiplier(p, trans[p]["lon"])
        single_score += w * dig
    compound = sum(w for label, fn, w in COMPOUND_RULES if fn(outer_orbs))
    jup_natNep = closest_hard(trans["Jupiter"]["lon"], natal["Neptune"]["lon"])
    nep_sun = closest_hard(trans["Neptune"]["lon"], natal["Sun"]["lon"])
    nep_mc = closest_hard(trans["Neptune"]["lon"], natal["MC"]["lon"]) if "MC" in natal else 99
    jd_c = jd_of(y, m, 15, 12.0)
    hits = eclipse_hits_natal(db, natal, jd_c, months_back=18, months_fwd=3, max_orb=3)
    eclipse = 0
    for h in hits:
        tw = 1.5 if "total" in h["eclipse_type"] else (1.0 if "partial" in h["eclipse_type"] or "annular" in h["eclipse_type"] else 0.5)
        eclipse += tw * (3 - h["orb"]) / 3
    bubblish = 0
    if jup_natNep <= 3:     bubblish += 2.5 * (3 - jup_natNep) / 3
    elif jup_natNep <= 6:   bubblish += 1.0 * (6 - jup_natNep) / 6
    if nep_sun <= 3:        bubblish += 2.0 * (3 - nep_sun) / 3
    if nep_mc <= 3:         bubblish += 1.5 * (3 - nep_mc) / 3
    n_close = sum(1 for o in outer_orbs.values() if o <= 5)
    if n_close >= 3:        bubblish += 1.0
    if 8 <= outer_orbs["Pluto"] < 12:   bubblish += 1.5
    if 3 <= outer_orbs["Uranus"] < 5:   bubblish += 1.2
    # v25 NEW layers:
    prof = profection_bonus(natal, y, m, ipo_year)
    jstn = jupiter_station_bonus(y, m)
    mjh = helio_mars_jup_bottom_bonus(y, m)
    merc_vol = mercury_retro_volatility(y, m)  # -> adds to bubblish for vol capacity

    pre_macro = (single_score + compound * 1.5 + eclipse * 1.3
                 + bubblish * 1.2 + prof + jstn + mjh)
    macro_mult = macro_regime_multiplier(modern_sec, y, m)
    composite = pre_macro * macro_mult
    return {"composite": composite, "pre_macro": pre_macro, "macro_mult": macro_mult,
            "single": single_score, "compound": compound, "eclipse": eclipse,
            "bubblish": bubblish + merc_vol,
            "prof": prof, "jstn": jstn, "mjh": mjh,
            "jup_natNep": jup_natNep, "nep_sun": nep_sun, "nep_mc": nep_mc,
            "outer_orbs": outer_orbs}

def forward_v25(natal, sy, sm, db, sector_base, modern_sec, ipo_year, months=24):
    traj = []
    for k in range(0, months+1):
        y, m = yx(sy, sm, k)
        traj.append({"k":k,"y":y,"m":m,
                     **score_snapshot_v25(natal, y, m, db, sector_base, modern_sec, ipo_year)})
    peak = max(traj, key=lambda s:s["composite"])
    cur = traj[0]
    bpk = max(traj, key=lambda s:s["bubblish"])
    sat_pop = saturn_pop_month(natal, sy, sm, months)
    runway = peak["k"]
    safe = sat_pop is None or sat_pop > runway+2
    # v25 EXIT penalties evaluated at PEAK month
    hjs = helio_jup_sat_peak_penalty(peak["y"], peak["m"])
    sstn = saturn_station_penalty(peak["y"], peak["m"])
    nod = node_ingress_peak_penalty(peak["y"], peak["m"])
    exit_penalty = hjs + sstn + nod
    return {"cur":cur,"peak":peak,"bpk":bpk,"traj":traj,
            "runway":runway,"sat_pop":sat_pop,"safe":safe,
            "imp":peak["composite"]-cur["composite"],
            "bub_imp":bpk["bubblish"]-cur["bubblish"],
            "exit_penalty":exit_penalty,
            "hjs":hjs,"sstn":sstn,"nod":nod}

def main():
    print("Building eclipse DB...", file=sys.stderr)
    db = build_eclipse_database(1970, 2035)

    seeds = []
    with open("/home/user/cyclepapa/data/universe_bti_v20.csv") as f:
        for r in csv.DictReader(f):
            tk = (r.get("ticker") or "").strip().upper()
            ipo = (r.get("ipo") or "").strip()
            name = (r.get("name") or "").strip()
            src = (r.get("source") or "").strip()
            if not tk or not ipo or len(ipo) < 10: continue
            try: y = int(ipo[:4])
            except: continue
            age = START_Y - y
            if not (1 <= age <= 40): continue
            seeds.append({"tk":tk,"ipo":ipo,"name":name,"src":src,"age":age})
    seen = set(); unique = []
    for s in seeds:
        k = (s["tk"], s["ipo"])
        if k in seen: continue
        seen.add(k); unique.append(s)
    print(f"Universe: {len(unique)}", file=sys.stderr)

    t0 = time.time()
    rows = []
    for i, s in enumerate(unique):
        if i and i % 500 == 0:
            print(f"  {i}/{len(unique)}  {time.time()-t0:.0f}s kept={len(rows)}", file=sys.stderr)
        sec_base = get_sector(s["tk"], s["src"])
        mod_sec = modern_sector_of(s["tk"], sec_base)
        ipo_year = int(s["ipo"][:4])
        try:
            natal = compute_natal(s["ipo"])
            gc_amp = natal_gc_amplifier(natal)
            fa = forward_v25(natal, START_Y, START_M, db, sec_base, mod_sec, ipo_year, MONTHS)
            # apply GC amplifier (natal magnitude boost)
            now = fa["cur"]["composite"] * gc_amp
            peak = fa["peak"]["composite"] * gc_amp
            imp = peak - now
            bpk = fa["bpk"]["bubblish"]
            run = fa["runway"]
            if run < 1: continue
            if imp < 5.0: continue
            if bpk < 2.0: continue
            if now >= 25.0: continue
            if not fa["safe"]: continue
            rb = 1.0 if 3 <= run <= 12 else 0.7
            # EXIT penalty reduces asymmetry directly
            base_asym = (imp**0.9) * (bpk**1.0) * rb / ((now + 3) ** 0.5)
            asym = base_asym * max(0.4, 1 - fa["exit_penalty"]/5.0)
            pk_d = fa["peak"]; bb_d = fa["bpk"]
            rows.append({"tk":s["tk"],"name":s["name"],"src":s["src"],
                         "sector":sec_base,"modern":mod_sec,"ipo":s["ipo"],"age":s["age"],
                         "now":now,"peak":peak,"imp":imp,"gc_amp":gc_amp,
                         "peak_mo":f"{pk_d['y']}-{pk_d['m']:02d}",
                         "runway":run,"sat_pop":fa["sat_pop"],
                         "bub_now":fa["cur"]["bubblish"],"bub_peak":bpk,
                         "macro_peak":pk_d["macro_mult"],
                         "prof_now":fa["cur"]["prof"],
                         "jstn_now":fa["cur"]["jstn"],
                         "mjh_now":fa["cur"]["mjh"],
                         "exit_penalty":fa["exit_penalty"],
                         "hjs_peak":fa["hjs"],"sstn_peak":fa["sstn"],"nod_peak":fa["nod"],
                         "asym":asym})
        except:
            continue
    print(f"Scan done: {time.time()-t0:.0f}s kept={len(rows)}", file=sys.stderr)

    rows.sort(key=lambda r: -r["asym"])
    out = "/home/user/cyclepapa/data/universe_v25.csv"
    with open(out, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["rank","ticker","name","sector","modern_sector","source","ipo","age",
                    "asymmetry","score_now","score_peak","improvement",
                    "gc_amplifier","peak_month","runway_mo","saturn_pop",
                    "bubblish_now","bubblish_peak","macro_peak",
                    "prof_bonus_now","jstn_bonus_now","mjh_bonus_now",
                    "exit_penalty","hjs_peak","sstn_peak","nod_peak"])
        for i, r in enumerate(rows, 1):
            w.writerow([i, r["tk"], r["name"], r["sector"], r["modern"], r["src"],
                        r["ipo"], r["age"],
                        f"{r['asym']:.3f}", f"{r['now']:.2f}", f"{r['peak']:.2f}",
                        f"{r['imp']:+.2f}", f"{r['gc_amp']:.2f}",
                        r["peak_mo"], r["runway"],
                        r["sat_pop"] if r["sat_pop"] is not None else "",
                        f"{r['bub_now']:.2f}", f"{r['bub_peak']:.2f}",
                        f"{r['macro_peak']:.2f}",
                        f"{r['prof_now']:.2f}", f"{r['jstn_now']:.2f}",
                        f"{r['mjh_now']:.2f}",
                        f"{r['exit_penalty']:.2f}", f"{r['hjs_peak']:.2f}",
                        f"{r['sstn_peak']:.2f}", f"{r['nod_peak']:.2f}"])
    print(f"Exported {len(rows)} -> {out}")

if __name__ == "__main__":
    main()
