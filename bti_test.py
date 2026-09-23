"""
Self-contained BTI (Bottom Turn Index) test.

Implements the formalised measure:
  BTI(t) = P_hat(t) * E(t) * R(t) * R_dot(t) * (1 + I(t)) * Gamma_survive(natal) * Gamma_era(t)

Tests against known bottoms, known tops, and random non-bottom months.
"""
from __future__ import annotations
import swisseph as swe
import math
from datetime import date, timedelta
from collections import defaultdict

# --- BASIC CHART HELPERS ---------------------------------------------------

SIGNS = ["Ari","Tau","Gem","Can","Leo","Vir","Lib","Sco","Sag","Cap","Aqu","Pis"]
PLANET_IDS = {
    "Sun": swe.SUN, "Moon": swe.MOON, "Mercury": swe.MERCURY, "Venus": swe.VENUS,
    "Mars": swe.MARS, "Jupiter": swe.JUPITER, "Saturn": swe.SATURN,
    "Uranus": swe.URANUS, "Neptune": swe.NEPTUNE, "Pluto": swe.PLUTO,
    "NN": swe.MEAN_NODE,
}
MEAN_SPEEDS = {"Mars":0.524,"Jupiter":0.083,"Saturn":0.034,"Uranus":0.012,"Neptune":0.006,"Pluto":0.004}

def jd_of(y, m, d, hr=17.0):
    return swe.julday(y, m, d, hr)

def orb(a, b):
    d = abs((a - b) % 360)
    return min(d, 360 - d)

def hard_orb(a, b, max_orb):
    """Closest hard aspect (conj/sq/opp). Returns (aspect_deg, orb) or None."""
    best = None
    for asp in (0, 90, 180):
        o = min(orb(a, (b + asp) % 360), orb(a, (b - asp) % 360))
        if o <= max_orb and (best is None or o < best[1]):
            best = (asp, o)
    return best

def any_aspect_orb(a, b, targets, max_orb):
    """Closest aspect from targets. Returns (aspect_deg, orb) or None."""
    best = None
    for asp in targets:
        o = min(orb(a, (b + asp) % 360), orb(a, (b - asp) % 360))
        if o <= max_orb and (best is None or o < best[1]):
            best = (asp, o)
    return best

def compute_natal(date_str, hr=14.5):
    """IPO chart at 14:30 UT (~9:30 ET for NY). Geocentric lons + speed."""
    y, m, d = int(date_str[:4]), int(date_str[5:7]), int(date_str[8:10])
    jd = jd_of(y, m, d, hr)
    c = {"_jd": jd, "_date": date_str}
    for nm, pid in PLANET_IDS.items():
        res = swe.calc_ut(jd, pid)
        lon = res[0][0] % 360
        speed = res[0][3]
        c[nm] = {"lon": lon, "speed": speed, "sign": int(lon // 30), "retro": speed < 0}
    try:
        _, ascmc = swe.houses(jd, 40.7069, -74.0113, b'P')
        c["ASC"] = {"lon": ascmc[0] % 360, "sign": int((ascmc[0] % 360)//30)}
        c["MC"] = {"lon": ascmc[1] % 360, "sign": int((ascmc[1] % 360)//30)}
    except Exception:
        c["ASC"] = {"lon": 0, "sign": 0}; c["MC"] = {"lon": 0, "sign": 0}
    return c

_transit_cache = {}

def transits_at(y, m, d=15, hr=12.0):
    """Planet positions at a given date. Cached across all callers."""
    key = (y, m, d, hr)
    if key in _transit_cache:
        return _transit_cache[key]
    jd = jd_of(y, m, d, hr)
    t = {"_jd": jd}
    for nm, pid in PLANET_IDS.items():
        res = swe.calc_ut(jd, pid)
        t[nm] = {"lon": res[0][0] % 360, "speed": res[0][3], "retro": res[0][3] < 0}
    _transit_cache[key] = t
    return t

# --- DIGNITIES (used by Gamma_survive) -------------------------------------

DIGNITIES = {
    "Sun":{4:1.20,0:1.15,10:0.85,6:0.80},
    "Moon":{3:1.20,1:1.15,9:0.85,7:0.80},
    "Mercury":{2:1.20,5:1.20,8:0.85,11:0.80},
    "Venus":{1:1.20,6:1.20,11:1.15,0:0.85,7:0.85,5:0.80},
    "Mars":{0:1.20,7:1.20,9:1.15,1:0.85,6:0.85,3:0.80},
    "Jupiter":{8:1.20,11:1.20,3:1.15,2:0.85,5:0.85,9:0.80},
    "Saturn":{9:1.20,10:1.20,6:1.15,3:0.85,4:0.85,0:0.80},
}

def gamma_survive(natal):
    """Survival gate: dignity of Jupiter+Venus + Jup-Ven aspect + sect benefic condition."""
    jup_d = DIGNITIES.get("Jupiter",{}).get(natal["Jupiter"]["sign"], 1.0)
    ven_d = DIGNITIES.get("Venus",{}).get(natal["Venus"]["sign"], 1.0)
    g = 0.5 * jup_d + 0.4 * ven_d + 0.1
    jv = any_aspect_orb(natal["Jupiter"]["lon"], natal["Venus"]["lon"], [0,60,90,120,180], 6.0)
    if jv:
        asp, o = jv
        if asp in (0, 60, 120):
            g += 0.15 * (6 - o)/6
        elif asp in (90, 180):
            g += 0.05 * (6 - o)/6
    return max(0.3, min(1.3, g))

# --- ERA GATE --------------------------------------------------------------

def gamma_era(natal, year):
    """Reward natal planet occupancy of signs hosting current macro outers.
    2008-2024 era: Pluto-Cap, Neptune-Pis, Uranus-Tau → fits memetic/Pisces era charts.
    2025-2040 era: Pluto-Aqu, Neptune-Ari, Uranus-Gem → fits air/Aries charts.
    """
    # Current transit signs depend on the evaluation year.
    if year < 2008: signs_hosted = [6, 11, 2]  # pre-2008 varied, use default
    elif year < 2024: signs_hosted = [9, 11, 1]  # Cap, Pis, Tau
    else: signs_hosted = [10, 0, 2]  # Aqu, Ari, Gem
    count = sum(1 for p in ("Sun","Moon","Mercury","Venus","Jupiter")
                if natal[p]["sign"] in signs_hosted)
    return 0.85 + 0.10 * count  # 0.85 to 1.35

# --- P(t) PRESSURE ACCUMULATOR ---------------------------------------------

NATAL_STRESS_TARGETS = ["Sun","Moon","Venus","Mars"]
NATAL_STRESS_LIGHT = ["Sun","Moon","ASC","MC"]

def pressure(natal, trans):
    p = 0.0
    # Macro stressors: Saturn-Pluto, Saturn-Neptune, Uranus-Pluto, Saturn-Uranus
    for (a, b, w) in [("Saturn","Pluto",3.0),("Saturn","Neptune",2.0),
                      ("Uranus","Pluto",2.5),("Saturn","Uranus",1.8)]:
        r = hard_orb(trans[a]["lon"], trans[b]["lon"], 8.0)
        if r: p += w * max(0, 1 - r[1]/8.0)
    # Transit Pluto hard to natal Sun/Moon/Venus/Mars
    for nt in NATAL_STRESS_TARGETS:
        r = hard_orb(trans["Pluto"]["lon"], natal[nt]["lon"], 3.0)
        if r: p += 2.0 * max(0, 1 - r[1]/3.0)
    # Transit Saturn hard to natal Sun/Moon/ASC/MC
    for nt in NATAL_STRESS_LIGHT:
        if nt in natal:
            r = hard_orb(trans["Saturn"]["lon"], natal[nt]["lon"], 3.0)
            if r: p += 1.5 * max(0, 1 - r[1]/3.0)
    # Transit Uranus hard to natal Sun/Moon/Venus
    for nt in ["Sun","Moon","Venus"]:
        r = hard_orb(trans["Uranus"]["lon"], natal[nt]["lon"], 3.0)
        if r: p += 1.5 * max(0, 1 - r[1]/3.0)
    # Transit Neptune hard to natal Sun/Mars/Jupiter
    for nt in ["Sun","Mars","Jupiter"]:
        r = hard_orb(trans["Neptune"]["lon"], natal[nt]["lon"], 3.0)
        if r: p += 1.2 * max(0, 1 - r[1]/3.0)
    # Mars retrograde within 5° of natal sensitive
    if trans["Mars"]["retro"]:
        for nt in ["Sun","Moon","Mars","ASC"]:
            if nt in natal:
                o = orb(trans["Mars"]["lon"], natal[nt]["lon"])
                if o <= 5.0: p += 1.3 * max(0, 1 - o/5.0)
    # Normalize approx to 0-10
    return min(p, 10.0)

# --- R(t) RELEASE EMERGER --------------------------------------------------

def release(natal, trans, prev_trans, next_trans):
    """Release strength. Uses prev/next months to detect stations and ingresses."""
    r = 0.0
    # Outer station-direct: speed was negative last month, positive this or next
    for outer in ("Saturn","Uranus","Neptune","Pluto"):
        prev_spd = prev_trans[outer]["speed"]
        curr_spd = trans[outer]["speed"]
        next_spd = next_trans[outer]["speed"]
        is_station_direct = (prev_spd < 0) and (curr_spd > 0 or next_spd > 0) and abs(curr_spd) < MEAN_SPEEDS[outer]*0.5
        if is_station_direct:
            for nt in ["Sun","Moon","Venus","Mars","Jupiter","ASC","MC"]:
                if nt in natal:
                    o = orb(trans[outer]["lon"], natal[nt]["lon"])
                    if o <= 2.0:
                        r += 3.5 * max(0, 1 - o/2.0)
    # Jupiter sign-ingress within ±60 days (check sign change between prev/curr/next)
    if int(prev_trans["Jupiter"]["lon"]//30) != int(trans["Jupiter"]["lon"]//30) or \
       int(trans["Jupiter"]["lon"]//30) != int(next_trans["Jupiter"]["lon"]//30):
        new_sign = int(trans["Jupiter"]["lon"]//30)
        mult = 1.0
        if new_sign in (3, 8, 11):  # Cancer, Sag, Pis (exalt + domiciles)
            mult = 2.0
        # Natal occupancy: any natal planet in the new sign?
        occupied = any(natal[p]["sign"] == new_sign for p in ("Sun","Moon","Mercury","Venus","Mars","Jupiter"))
        if occupied: mult *= 1.5
        r += 2.0 * mult
    # Transit Jupiter within 3° of natal Sun/Venus/ASC/MC (trine/sextile/conj)
    for nt in ["Sun","Venus","ASC","MC"]:
        if nt in natal:
            ar = any_aspect_orb(trans["Jupiter"]["lon"], natal[nt]["lon"], [0,60,120], 3.0)
            if ar: r += 2.0 * max(0, 1 - ar[1]/3.0)
    # Transit Venus within 2°
    for nt in ["Sun","ASC","MC"]:
        if nt in natal:
            ar = any_aspect_orb(trans["Venus"]["lon"], natal[nt]["lon"], [0,60,120], 2.0)
            if ar: r += 0.8 * max(0, 1 - ar[1]/2.0)
    # North Node entering sign of natal Sun/Moon/Jupiter/Venus
    nn_sign = int(trans["NN"]["lon"]//30)
    prev_nn_sign = int(prev_trans["NN"]["lon"]//30)
    if nn_sign != prev_nn_sign:
        if any(natal[p]["sign"] == nn_sign for p in ("Sun","Moon","Jupiter","Venus")):
            r += 1.5
    return min(r, 10.0)

# --- I(t) IGNITION PROXIMITY (next 90d) ------------------------------------

def ignition_at(natal, future_transits):
    """Max detonator strength in next 90 days (given list of 3 monthly transits)."""
    I = 0.0
    for i, tr in enumerate(future_transits):
        days_out = 30 * i
        prox = (90 - days_out) / 90.0
        i_local = 0.0
        # Mars station: speed near zero and flipping
        if i > 0:
            prev = future_transits[i-1]
            if prev["Mars"]["retro"] and not tr["Mars"]["retro"]:
                # station-direct this month
                for nt in ["Sun","Mars","ASC"]:
                    if nt in natal:
                        o = orb(tr["Mars"]["lon"], natal[nt]["lon"])
                        if o <= 3.0: i_local += 2.5 * max(0, 1 - o/3.0)
        # Jupiter-Uranus synodic conjunction exact
        ju_ur = orb(tr["Jupiter"]["lon"], tr["Uranus"]["lon"])
        if ju_ur <= 3.0: i_local += 3.0 * max(0, 1 - ju_ur/3.0)
        # Jupiter-Neptune conjunction
        ju_ne = orb(tr["Jupiter"]["lon"], tr["Neptune"]["lon"])
        if ju_ne <= 3.0: i_local += 3.0 * max(0, 1 - ju_ne/3.0)
        # Outer ingress: sign change vs prior month
        if i > 0:
            prev = future_transits[i-1]
            for outer in ("Saturn","Uranus","Neptune","Pluto"):
                if int(prev[outer]["lon"]//30) != int(tr[outer]["lon"]//30):
                    # Base 2.0, double if natal occupancy
                    new_sign = int(tr[outer]["lon"]//30)
                    bump = 2.0
                    if any(natal[p]["sign"] == new_sign for p in ("Sun","Moon","Jupiter","Venus")):
                        bump *= 2.0
                    i_local += bump
        # Benefic-to-natal exact trine within orb
        for nt in ["Sun","ASC","MC"]:
            if nt in natal:
                for benefic in ("Jupiter","Venus"):
                    ar = any_aspect_orb(tr[benefic]["lon"], natal[nt]["lon"], [120], 1.5)
                    if ar: i_local += 1.5 * max(0, 1 - ar[1]/1.5)
        I = max(I, i_local * prox)
    return I

# --- COMPOSITE BTI ---------------------------------------------------------

def compute_bti(natal, eval_y, eval_m):
    """Compute BTI at (eval_y, eval_m) with 7-month trailing window for pressure,
    3-month forward window for ignition."""
    # Past 6 months for P-hat and P-derivative
    past_p = []
    prev_y, prev_m = eval_y, eval_m
    for k in range(0, 7):  # 0..6 months back
        y, m = eval_y, eval_m
        m -= k
        while m <= 0:
            m += 12; y -= 1
        past_p.append((y, m))
    past_p.reverse()  # oldest first
    # Current transits + prev + next for release station/ingress detection
    def yx(y, m, offset):
        mm = m + offset
        yy = y
        while mm <= 0:
            mm += 12; yy -= 1
        while mm > 12:
            mm -= 12; yy += 1
        return (yy, mm)
    # Compute pressure series
    P_series = []
    for (y, m) in past_p:
        tr_prev = transits_at(*yx(y, m, -1))
        tr_curr = transits_at(y, m)
        P_series.append(pressure(natal, tr_curr))
    P_max_6 = max(P_series)
    P_now = P_series[-1]
    P_prev = P_series[-2] if len(P_series) >= 2 else P_now
    dP_dt = P_now - P_prev  # negative => easing
    # Easing factor E(t)
    E = 0.3 + 0.7 * max(0, -dP_dt / 2.0)  # scaled: 2 unit drop = 1.0 easing
    E = min(E, 1.0)

    # Release at current month (need prev/next transits)
    tr_prev = transits_at(*yx(eval_y, eval_m, -1))
    tr_curr = transits_at(eval_y, eval_m)
    tr_next = transits_at(*yx(eval_y, eval_m, +1))
    R_now = release(natal, tr_curr, tr_prev, tr_next)
    # R previous for derivative
    tr_prev2 = transits_at(*yx(eval_y, eval_m, -2))
    R_prev = release(natal, tr_prev, tr_prev2, tr_curr)
    dR_dt = R_now - R_prev
    R_dot = 1.0 + max(0, dR_dt / 2.0)  # scaled
    # Ignition (next 90 days)
    future = [transits_at(*yx(eval_y, eval_m, +k)) for k in range(0, 4)]
    I = ignition_at(natal, future)
    # Survival + era gates
    Gs = gamma_survive(natal)
    Ge = gamma_era(natal, eval_y)
    # Composite
    bti = (P_max_6 / 3.0) * E * (R_now / 3.0) * R_dot * (1.0 + I / 5.0) * Gs * Ge
    return {
        "bti": bti,
        "P_max_6": P_max_6, "P_now": P_now, "dP_dt": dP_dt, "E": E,
        "R_now": R_now, "dR_dt": dR_dt, "R_dot": R_dot,
        "I_90d": I, "Gs": Gs, "Ge": Ge,
    }

# --- TEST HARNESS ----------------------------------------------------------

# Each entry: (ticker, ipo_date, known_bottom_month, known_top_month, description)
BOTTOMS = [
    # ticker, IPO date, bottom Y-M, top Y-M, multiplier, note
    ("TSLA",  "2010-06-29", (2019, 6),  (2021, 11), 12,   "Tesla 2019-2021 run"),
    ("NVDA",  "1999-01-22", (2022, 10), (2024, 6),  13,   "Nvidia AI era bottom"),
    ("NVDA16","1999-01-22", (2016, 2),  (2018, 10), 12,   "Nvidia 2016-2018 run"),
    ("GME",   "2002-02-13", (2020, 4),  (2021, 1),  160,  "GameStop squeeze"),
    ("AMC",   "2013-12-18", (2021, 1),  (2021, 6),  31,   "AMC meme squeeze"),
    ("PLTR",  "2020-09-30", (2022, 12), (2024, 12), 13,   "Palantir AI era"),
    ("CVNA",  "2017-04-28", (2022, 12), (2024, 11), 75,   "Carvana recovery"),
    ("MSTR",  "1998-06-11", (2022, 12), (2024, 11), 4,    "MicroStrategy BTC"),
    ("COIN",  "2021-04-14", (2023, 1),  (2024, 12), 10,   "Coinbase recovery"),
    ("SHOP",  "2015-05-21", (2016, 2),  (2018, 8),  10,   "Shopify early"),
    ("SHOP2", "2015-05-21", (2020, 3),  (2021, 11), 5,    "Shopify COVID"),
    ("CROX",  "2006-02-08", (2008, 11), (2021, 10), 180,  "Crocs long cycle"),
    ("AAPL",  "1980-12-12", (2003, 4),  (2007, 12), 28,   "Apple iPod era"),
    ("AMZN",  "1997-05-15", (2001, 10), (2007, 10), 17,   "Amazon dot-com recovery"),
    ("NFLX",  "2002-05-23", (2012, 8),  (2015, 7),  16,   "Netflix streaming"),
    ("SMCI",  "2007-03-29", (2022, 10), (2024, 3),  17,   "Super Micro AI"),
]

# Null cases: these blew off then died or went flat
NULLS = [
    ("BYND",  "2019-05-02", (2019, 5),  "Beyond Meat peaked at IPO"),
    ("PTON",  "2019-09-26", (2021, 1),  "Peloton peak, collapsed"),
    ("ZM",    "2019-04-18", (2020, 10), "Zoom peak, collapsed"),
    ("SPCE",  "2019-10-28", (2021, 2),  "Virgin Galactic peak"),
    ("HOOD",  "2021-07-29", (2021, 8),  "Robinhood peaked at IPO"),
]

# Test quiet months (no bottom, no top — should be low BTI)
QUIET_OFFSETS = [-18, -12, -6, 6, 12, 18]  # months away from bottom

def run_test():
    print("="*130)
    print("BTI VALIDATION TEST")
    print("="*130)
    print(f"{'Case':<8s} {'IPO':<11s} {'EvMo':<7s} {'BTI':>6s} {'Pmax':>5s} {'Pnow':>5s} {'dP':>5s} {'E':>4s} {'Rnow':>5s} {'dR':>5s} {'Rdot':>4s} {'I90d':>5s} {'Gs':>4s} {'Ge':>4s} {'Mult':>5s} {'Note'}")
    print("-"*130)

    # --- BOTTOMS ---
    bottom_btis = []
    for tk, ipo, bot, top, mult, note in BOTTOMS:
        natal = compute_natal(ipo)
        rep = compute_bti(natal, bot[0], bot[1])
        bottom_btis.append((tk, rep["bti"]))
        mo = f"{bot[0]}-{bot[1]:02d}"
        print(f"{tk:<8s} {ipo:<11s} {mo:<7s} {rep['bti']:6.2f} {rep['P_max_6']:5.1f} {rep['P_now']:5.1f} {rep['dP_dt']:5.2f} {rep['E']:4.2f} {rep['R_now']:5.1f} {rep['dR_dt']:5.2f} {rep['R_dot']:4.2f} {rep['I_90d']:5.1f} {rep['Gs']:4.2f} {rep['Ge']:4.2f} {mult:5d}× {note}")

    # --- QUIET MONTHS (baseline) ---
    print()
    print("QUIET MONTHS (± offset from each bottom) — should be LOWER than bottom BTI")
    print("-"*130)
    quiet_btis = []
    for tk, ipo, bot, top, mult, note in BOTTOMS[:8]:  # first 8 for brevity
        natal = compute_natal(ipo)
        for off in QUIET_OFFSETS:
            y, m = bot[0], bot[1] + off
            while m <= 0: m += 12; y -= 1
            while m > 12: m -= 12; y += 1
            rep = compute_bti(natal, y, m)
            quiet_btis.append((tk, off, rep["bti"]))
        vals = [v for (t, o, v) in quiet_btis if t == tk]
        med_q = sorted(vals)[len(vals)//2] if vals else 0
        bot_bti = next(v for (t, v) in bottom_btis if t == tk)
        print(f"  {tk:<8s} bottom BTI={bot_bti:5.2f}  median quiet BTI={med_q:5.2f}  ratio={bot_bti/max(med_q,0.01):5.2f}x")

    # --- TOPS (should have LOW BTI — low pressure, low release) ---
    print()
    print("TOPS — BTI should be LOW (no pressure to release)")
    print("-"*130)
    for tk, ipo, bot, top, mult, note in BOTTOMS:
        natal = compute_natal(ipo)
        rep = compute_bti(natal, top[0], top[1])
        mo = f"{top[0]}-{top[1]:02d}"
        print(f"{tk:<8s} top {mo:<7s}  BTI={rep['bti']:6.2f}  (P_max={rep['P_max_6']:.1f} R={rep['R_now']:.1f} I={rep['I_90d']:.1f})")

    # --- NULLS (peaks that didn't survive) — BTI at the peak should be SUSPICIOUSLY HIGH ---
    print()
    print("NULLS — BTI at the blow-off peak (Gamma_survive should be low)")
    print("-"*130)
    for tk, ipo, peak, note in NULLS:
        natal = compute_natal(ipo)
        rep = compute_bti(natal, peak[0], peak[1])
        mo = f"{peak[0]}-{peak[1]:02d}"
        print(f"{tk:<8s} peak {mo:<7s}  BTI={rep['bti']:6.2f}  Gs={rep['Gs']:.2f}  {note}")

    # --- SUMMARY STATS ---
    print()
    print("="*130)
    print("SUMMARY")
    print("="*130)
    import statistics as st
    bvals = [v for (t, v) in bottom_btis]
    qvals = [v for (t, o, v) in quiet_btis]
    print(f"  Bottom BTIs:  mean={st.mean(bvals):.2f}  median={st.median(bvals):.2f}  min={min(bvals):.2f}  max={max(bvals):.2f}")
    print(f"  Quiet BTIs:   mean={st.mean(qvals):.2f}  median={st.median(qvals):.2f}  max={max(qvals):.2f}")
    # Discrimination: fraction of bottom BTIs above 90th percentile of quiet BTIs
    q_sorted = sorted(qvals)
    q90 = q_sorted[int(len(q_sorted)*0.90)]
    frac_above = sum(1 for v in bvals if v > q90) / len(bvals)
    print(f"  Discrimination: {frac_above*100:.0f}% of bottoms have BTI > 90th-percentile quiet ({q90:.2f})")
    q50 = q_sorted[len(q_sorted)//2]
    frac_above50 = sum(1 for v in bvals if v > 2 * q50) / len(bvals)
    print(f"                  {frac_above50*100:.0f}% of bottoms have BTI > 2× median quiet ({2*q50:.2f})")

if __name__ == "__main__":
    run_test()
