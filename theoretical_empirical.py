"""
Empirical tests of UNDER-USED astrological techniques on the 152-case
parabolic corpus, to see which theoretical refinements would add signal
if folded into v25.

Tested:
  (A) PLANETARY STATIONS — % of bottoms/peaks within 7 days of an outer
      station (Rx or D). Stations are "release points" in mundane astrology.
  (B) OUT-OF-BOUNDS DECLINATION — % with at least one outer OOB (|δ|>23.5°).
      OOB planets are said to produce extreme price swings.
  (C) HELIOCENTRIC ASPECTS — Bradley siderograph territory. Does
      helio Mars-Jupiter conjunction ≤10° cluster at bottoms?
  (D) HELLENISTIC ANNUAL PROFECTIONS — for each case compute age-rotated
      "Lord of the Year" sign (age 0→ASC sign, 1→2nd-house sign, etc.).
      Check if the planetary ruler of that sign is activated at bottom/peak.
  (E) NODAL INGRESSES — days-to-nearest Node sign change (18-month cycle).
      Dave George: market turns cluster near Node ingresses.
  (F) GALACTIC CENTER — transits to 27° Sag. GC activation theorised as
      high-magnitude signal.

Each test reports: bottom_rate, mid_rate, peak_rate, random baseline,
and whether it's statistically interesting (≥2× baseline or ≥2pp over mid-peak).
"""
import math, statistics as st, sys
from datetime import datetime, timedelta
from collections import Counter
import swisseph as swe
from bti_test import compute_natal, transits_at, jd_of
from parabolic_corpus import PARABOLIC_BOTTOMS
from three_phase_scrutiny import snapshot, midpoint, closest_hard, orb

OUTERS = ("Jupiter","Saturn","Uranus","Neptune","Pluto")
INNERS = ("Mercury","Venus","Mars")

# ============================================================
# (A) PLANETARY STATIONS — find station dates via daily speed sign-change
# ============================================================
def nearest_station_days(planet_id, jd_center, search=60):
    """Find the nearest station (speed=0) date to jd_center, within +/-search days."""
    speeds = []
    for off in range(-search, search+1, 2):
        s = swe.calc_ut(jd_center + off, planet_id)[0][3]
        speeds.append((off, s))
    best = 999
    for i in range(1, len(speeds)):
        if speeds[i-1][1] * speeds[i][1] < 0:
            # speed changed sign -> station between these
            off = speeds[i][0]
            d = abs(off)
            if d < best: best = d
    return best if best < 999 else None

PLANET_IDS = {"Jupiter":swe.JUPITER,"Saturn":swe.SATURN,
              "Uranus":swe.URANUS,"Neptune":swe.NEPTUNE,"Pluto":swe.PLUTO,
              "Mercury":swe.MERCURY,"Venus":swe.VENUS,"Mars":swe.MARS}

def test_stations(cases):
    print("\n" + "="*90)
    print(" (A) PLANETARY STATIONS near bottom/mid/peak (within 7 days)")
    print("="*90)
    print(f"  {'Planet':<9s} {'BOT%':>6s} {'MID%':>6s} {'PEAK%':>6s}   baseline ≈ 14/365 per planet = ~4%")
    for pname, pid in PLANET_IDS.items():
        counts = {"bot":0,"mid":0,"peak":0}
        for c in cases:
            for phase in ("bot","mid","peak"):
                yy = c[f"{phase}_y"]; mm = c[f"{phase}_m"]
                jd = jd_of(yy, mm, 15, 12.0)
                d = nearest_station_days(pid, jd, search=30)
                if d is not None and d <= 7:
                    counts[phase] += 1
        N = len(cases)
        print(f"  {pname:<9s} {100*counts['bot']/N:5.1f}% {100*counts['mid']/N:5.1f}% "
              f"{100*counts['peak']/N:5.1f}%")

# ============================================================
# (B) OUT-OF-BOUNDS DECLINATION
# ============================================================
def declination(planet_id, jd):
    # ecl lon + lat -> equatorial dec via swisseph flag
    res = swe.calc_ut(jd, planet_id, swe.FLG_EQUATORIAL)
    return res[0][1]  # declination

def test_oob(cases):
    print("\n" + "="*90)
    print(" (B) OUT-OF-BOUNDS DECLINATION (|δ|>23.5°) at each phase")
    print("="*90)
    print(f"  {'Planet':<9s} {'BOT%':>6s} {'MID%':>6s} {'PEAK%':>6s}")
    for pname, pid in PLANET_IDS.items():
        counts = {"bot":0,"mid":0,"peak":0}
        for c in cases:
            for phase in ("bot","mid","peak"):
                yy = c[f"{phase}_y"]; mm = c[f"{phase}_m"]
                jd = jd_of(yy, mm, 15, 12.0)
                dec = declination(pid, jd)
                if abs(dec) > 23.5:
                    counts[phase] += 1
        N = len(cases)
        print(f"  {pname:<9s} {100*counts['bot']/N:5.1f}% {100*counts['mid']/N:5.1f}% "
              f"{100*counts['peak']/N:5.1f}%")
    # OOB NATAL — does having an OOB natal planet predict magnitude?
    print(f"\n  NATAL OOB (does chart-born-with-OOB predict bigger rallies?)")
    mult_by_oob = []
    for c in cases:
        nat_oob = False
        for _, pid in PLANET_IDS.items():
            jd = jd_of(int(c["ipo"][:4]), int(c["ipo"][5:7]), int(c["ipo"][8:10]), 12.0)
            if abs(declination(pid, jd)) > 23.5:
                nat_oob = True; break
        mult_by_oob.append((nat_oob, c["mult"]))
    has_oob = [m for o, m in mult_by_oob if o]
    no_oob =  [m for o, m in mult_by_oob if not o]
    print(f"    With OOB natal: n={len(has_oob)}  mean_mult={st.mean(has_oob):.1f}  med={st.median(has_oob):.1f}")
    print(f"    No  OOB natal: n={len(no_oob)}  mean_mult={st.mean(no_oob):.1f}  med={st.median(no_oob):.1f}")

# ============================================================
# (C) HELIOCENTRIC ASPECTS (Bradley)
# ============================================================
def helio_lon(planet_id, jd):
    """Return heliocentric ecliptic longitude."""
    res = swe.calc_ut(jd, planet_id, swe.FLG_HELCTR)
    return res[0][0] % 360

def test_helio(cases):
    print("\n" + "="*90)
    print(" (C) HELIOCENTRIC ASPECTS — Mars-Jupiter conj/opp (Bradley core)")
    print("="*90)
    # For each case, check helio Mars-Jup/Jup-Sat/Ven-Mars orbs at each phase
    pairs = [("Mars","Jupiter"),("Venus","Mars"),("Jupiter","Saturn"),
             ("Mars","Saturn"),("Earth","Mars"),("Earth","Jupiter")]
    # SWE doesn't directly give Earth helio but helio Sun = 0, so Earth = 0+180 = opposite of geo-Sun is non-trivial
    # For simplicity use heliocentric pairs excluding Earth
    pair_ids = {"Mars":swe.MARS,"Jupiter":swe.JUPITER,"Saturn":swe.SATURN,
                "Venus":swe.VENUS,"Mercury":swe.MERCURY,"Neptune":swe.NEPTUNE,
                "Pluto":swe.PLUTO,"Uranus":swe.URANUS}
    pairs_strict = [(a,b) for a,b in pairs if a in pair_ids and b in pair_ids]
    print(f"  {'Pair':<20s} {'BOT≤10°':>8s} {'MID≤10°':>8s} {'PEAK≤10°':>8s}  (hard aspect closest)")
    for pa, pb in pairs_strict:
        counts = {"bot":0,"mid":0,"peak":0}
        for c in cases:
            for phase in ("bot","mid","peak"):
                yy = c[f"{phase}_y"]; mm = c[f"{phase}_m"]
                jd = jd_of(yy, mm, 15, 12.0)
                la = helio_lon(pair_ids[pa], jd)
                lb = helio_lon(pair_ids[pb], jd)
                if closest_hard(la, lb) <= 10: counts[phase] += 1
        N = len(cases)
        print(f"  {pa+'-'+pb:<20s} {100*counts['bot']/N:7.1f}% {100*counts['mid']/N:7.1f}% "
              f"{100*counts['peak']/N:7.1f}%")

# ============================================================
# (D) HELLENISTIC ANNUAL PROFECTIONS — Lord of the Year
# ============================================================
# Age 0 = 1st house (ASC sign). Age 1 = 2nd house. Profection advances
# one sign per year. Age-of-chart at each phase = (year of phase) - (ipo year).
SIGN_RULERS_TRAD = {0:"Mars",1:"Venus",2:"Mercury",3:"Moon",4:"Sun",
                    5:"Mercury",6:"Venus",7:"Mars",8:"Jupiter",
                    9:"Saturn",10:"Saturn",11:"Jupiter"}
def profected_sign(ipo_date, phase_year):
    """Return profected sign-index for age = phase_year - ipo_year."""
    ipo_y = int(ipo_date[:4])
    age = phase_year - ipo_y
    # ASC sign from natal — we need ASC longitude
    # Use simplified: age % 12 profection cycles through houses from 1st.
    # Without knowing ASC sign we return just the house count (age % 12)
    return age % 12

def test_profections(cases):
    print("\n" + "="*90)
    print(" (D) HELLENISTIC PROFECTIONS — Lord of the Year (LoY) active at phase?")
    print("="*90)
    print(f"  Does the profected LoY's natal position receive close outer-planet")
    print(f"  transit (≤5°) at the bottom/peak?")
    results = []
    for c in cases:
        try:
            natal = compute_natal(c["ipo"])
            asc_lon = natal["ASC"]["lon"]
            asc_sign = int(asc_lon // 30)
            ipo_y = int(c["ipo"][:4])
            for phase in ("bot","mid","peak"):
                yy = c[f"{phase}_y"]
                age = yy - ipo_y
                house = age % 12
                prof_sign = (asc_sign + house) % 12
                ruler_name = SIGN_RULERS_TRAD[prof_sign]
                # Where is natal ruler_name?
                if ruler_name not in natal: continue
                ruler_lon = natal[ruler_name]["lon"]
                # Check if any outer transits ruler's natal position
                mm = c[f"{phase}_m"]
                trans = transits_at(yy, mm)
                best = 99
                for outer in OUTERS:
                    o = closest_hard(trans[outer]["lon"], ruler_lon)
                    if o < best: best = o
                results.append((phase, best))
        except: continue
    from collections import defaultdict
    by_phase = defaultdict(list)
    for ph, o in results: by_phase[ph].append(o)
    print(f"  {'Phase':<6s} {'n':>4s}  {'mean_orb':>8s}  {'%≤3°':>6s}  {'%≤5°':>6s}")
    for ph in ("bot","mid","peak"):
        vs = by_phase[ph]
        if not vs: continue
        p3 = 100*sum(1 for v in vs if v<=3)/len(vs)
        p5 = 100*sum(1 for v in vs if v<=5)/len(vs)
        print(f"  {ph:<6s} {len(vs):>4d}  {st.mean(vs):>8.2f}  {p3:5.1f}% {p5:5.1f}%")

# ============================================================
# (E) NODAL INGRESSES — 18-month sign changes
# ============================================================
NODE_INGRESSES = [  # Approximate mean-node ingress dates (True Node varies)
    # Let's compute dynamically using swe.TRUE_NODE
]

def test_node_ingresses(cases):
    print("\n" + "="*90)
    print(" (E) NODAL INGRESSES — days to nearest True-Node sign change")
    print("="*90)
    # For each phase date, compute days to nearest node ingress.
    # Scan back/fwd 180 days to find where node crosses next 30° boundary
    def days_to_node_ingress(jd_center):
        cur_sign = int(swe.calc_ut(jd_center, swe.TRUE_NODE)[0][0] // 30)
        best = 999
        for off in range(-180, 181):
            s = int(swe.calc_ut(jd_center + off, swe.TRUE_NODE)[0][0] // 30)
            if s != cur_sign:
                d = abs(off)
                if d < best: best = d
        return best if best < 999 else None
    by_phase = {"bot":[], "mid":[], "peak":[]}
    for c in cases:
        for phase in ("bot","mid","peak"):
            yy = c[f"{phase}_y"]; mm = c[f"{phase}_m"]
            jd = jd_of(yy, mm, 15, 12.0)
            d = days_to_node_ingress(jd)
            if d is not None: by_phase[phase].append(d)
    print(f"  {'Phase':<6s} {'n':>4s}  {'mean':>6s}  {'med':>5s}  {'%≤30d':>7s}  {'%≤60d':>7s}")
    for ph in ("bot","mid","peak"):
        vs = by_phase[ph]
        p30 = 100*sum(1 for v in vs if v<=30)/len(vs)
        p60 = 100*sum(1 for v in vs if v<=60)/len(vs)
        print(f"  {ph:<6s} {len(vs):>4d}  {st.mean(vs):6.1f}  {st.median(vs):5.0f}  {p30:6.1f}% {p60:6.1f}%")

# ============================================================
# (F) GALACTIC CENTER (27° Sag = 267°) activation
# ============================================================
def test_gc(cases):
    print("\n" + "="*90)
    print(" (F) GALACTIC CENTER (27° Sagittarius = 267°) — outer close to natal?")
    print("="*90)
    GC = 267.0
    # 1) At each phase, how close is any transiting outer to GC?
    by_phase = {"bot":[], "mid":[], "peak":[]}
    for c in cases:
        for phase in ("bot","mid","peak"):
            yy = c[f"{phase}_y"]; mm = c[f"{phase}_m"]
            trans = transits_at(yy, mm)
            best = 99
            for outer in OUTERS:
                o = closest_hard(trans[outer]["lon"], GC)
                if o < best: best = o
            by_phase[phase].append(best)
    print(f"  Transit outer to GC (≤3° = strong signal):")
    for ph in ("bot","mid","peak"):
        vs = by_phase[ph]
        p3 = 100*sum(1 for v in vs if v<=3)/len(vs)
        p5 = 100*sum(1 for v in vs if v<=5)/len(vs)
        print(f"    {ph:<6s} mean_orb={st.mean(vs):.2f}°  ≤3°={p3:.0f}%  ≤5°={p5:.0f}%")
    # 2) Natal chart with outer near GC — predicts magnitude?
    natal_gc = []
    for c in cases:
        try:
            jd = jd_of(int(c["ipo"][:4]), int(c["ipo"][5:7]), int(c["ipo"][8:10]), 12.0)
            best = 99
            for outer in OUTERS:
                lon = swe.calc_ut(jd, PLANET_IDS[outer])[0][0] % 360
                o = closest_hard(lon, GC)
                if o < best: best = o
            natal_gc.append((best, c["mult"]))
        except: continue
    tight = [m for o, m in natal_gc if o <= 3]
    loose = [m for o, m in natal_gc if o > 3]
    print(f"\n  NATAL: outer ≤3° from GC: n={len(tight)}  mean_mult={st.mean(tight):.1f}  med={st.median(tight):.1f}")
    print(f"         outer >3° from GC: n={len(loose)}  mean_mult={st.mean(loose):.1f}  med={st.median(loose):.1f}")

# ============================================================
# Build test cases
# ============================================================
def load_cases():
    cases = []
    for tk, ipo, bot, top, mult, speed, note in PARABOLIC_BOTTOMS:
        mid = midpoint(bot, top)
        cases.append({"tk":tk,"ipo":ipo,"mult":mult,"speed":speed,
                      "bot_y":bot[0],"bot_m":bot[1],
                      "mid_y":mid[0],"mid_m":mid[1],
                      "peak_y":top[0],"peak_m":top[1]})
    return cases

def main():
    cases = load_cases()
    print(f"Loaded {len(cases)} cases from parabolic corpus")
    test_stations(cases)
    test_oob(cases)
    test_helio(cases)
    test_profections(cases)
    test_node_ingresses(cases)
    test_gc(cases)

if __name__ == "__main__":
    main()
