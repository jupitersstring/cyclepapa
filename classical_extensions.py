"""
Classical-tradition extensions filling v11's theoretical gaps:

  (1) Fixed stars (Ptolemy / Abu Ma'shar / Lilly / Crawford / Merriman):
      Royal Stars + critical fixed stars with 2026 longitudes.

  (2) Heliocentric aspects (Bradley siderograph core component):
      Compute helio longitudes via swisseph, add helio outer-to-natal term.

  (3) Declination parallels + out-of-bounds (Bradley):
      Transit declinations, parallels/contraparallels to natal, OOB flag.

  (4) Secondary progressions (Merriman / Crawford / Meridian):
      1 day = 1 year. Progressed Sun/Moon/Mercury/Venus/Mars aspects
      to natal; progressed-lunation cycle phase.
"""
import math
import swisseph as swe
from bti_test import jd_of, PLANET_IDS

# =====================================================================
# (1) FIXED STARS — Ptolemy's Royal Stars + critical additional ones.
# Longitudes at J2000, precessing ~1°/72 yr (~+0.36° by 2026).
# =====================================================================
FIXED_STARS = {
    # Royal Stars (Ptolemy / Lilly / Merriman use these)
    "Regulus":    {"lon_2026": 0.30,    "sign": "Vir", "nature": "royal_power",      "weight": 1.5},
    "Spica":      {"lon_2026": 204.28,  "sign": "Lib", "nature": "brilliance_wealth","weight": 1.4},
    "Antares":    {"lon_2026": 250.00,  "sign": "Sag", "nature": "mars_intensity",   "weight": 1.4},
    "Aldebaran":  {"lon_2026": 70.15,   "sign": "Gem", "nature": "fortune_effort",   "weight": 1.4},
    # Additional critical stars
    "Algol":      {"lon_2026": 56.52,   "sign": "Tau", "nature": "crisis_loss",      "weight": 1.2},
    "Sirius":     {"lon_2026": 104.60,  "sign": "Can", "nature": "success_heat",     "weight": 1.1},
    "Procyon":    {"lon_2026": 126.30,  "sign": "Can", "nature": "sudden_success",   "weight": 1.0},
    "Castor":     {"lon_2026": 110.85,  "sign": "Can", "nature": "duality_shift",    "weight": 0.9},
    "Pollux":     {"lon_2026": 113.80,  "sign": "Can", "nature": "daring_venture",   "weight": 0.9},
    "Fomalhaut":  {"lon_2026": 4.38,    "sign": "Pis", "nature": "inspired_fame",    "weight": 1.2},
    "Vega":       {"lon_2026": 15.75,   "sign": "Cap", "nature": "artistic_refined", "weight": 0.9},
    "Rigel":      {"lon_2026": 77.60,   "sign": "Gem", "nature": "strong_ambition",  "weight": 1.0},
    "Betelgeuse": {"lon_2026": 89.30,   "sign": "Gem", "nature": "power_authority",  "weight": 1.0},
    "Capella":    {"lon_2026": 82.30,   "sign": "Gem", "nature": "new_beginnings",   "weight": 1.0},
    "Deneb Algedi":{"lon_2026": 323.96, "sign": "Aqu", "nature": "saturn_wisdom",    "weight": 0.8},
}

def fixed_star_hits(natal, trans=None, max_orb=1.5):
    """Check fixed-star conjunctions of natal + optional transit planets.
    Returns list of (body, star, orb, nature)."""
    hits = []
    # Natal planets on fixed stars
    for body in ("Sun","Moon","Mercury","Venus","Mars","Jupiter","Saturn","Uranus","Neptune","Pluto","ASC","MC"):
        if body not in natal: continue
        blon = natal[body]["lon"]
        for star, info in FIXED_STARS.items():
            o = abs((blon - info["lon_2026"]) % 360)
            o = min(o, 360 - o)
            if o <= max_orb:
                hits.append({"body": body, "star": star, "orb": o, "nature": info["nature"],
                             "weight": info["weight"], "source": "natal"})
    # Transit planets on fixed stars (near major royal stars only)
    if trans:
        for body in ("Jupiter","Saturn","Uranus","Neptune","Pluto"):
            blon = trans[body]["lon"]
            for star in ("Regulus","Spica","Antares","Aldebaran","Algol"):
                info = FIXED_STARS[star]
                o = abs((blon - info["lon_2026"]) % 360)
                o = min(o, 360 - o)
                if o <= max_orb:
                    hits.append({"body": body, "star": star, "orb": o, "nature": info["nature"],
                                 "weight": info["weight"], "source": "transit"})
    return hits

# =====================================================================
# (2) HELIOCENTRIC — Bradley core methodology
# =====================================================================
def heliocentric_planets(jd):
    """Return heliocentric longitudes (Earth = 180° from geocentric Sun).
    Used by Bradley siderograph for long-term component."""
    h = {}
    for name, pid in PLANET_IDS.items():
        if name in ("Moon","NN"): continue  # These don't have meaningful helio
        try:
            res = swe.calc_ut(jd, pid, swe.FLG_HELCTR)
            h[name] = res[0][0] % 360
        except:
            pass
    # Heliocentric Earth = geocentric Sun + 180
    res_sun = swe.calc_ut(jd, swe.SUN)
    h["Earth"] = (res_sun[0][0] + 180) % 360
    return h

def helio_aspect_orb(h_a, h_b, aspects=(0,60,90,120,180), max_orb=3):
    best = None
    for asp in aspects:
        for sign in (+1, -1):
            o = abs((h_a - h_b - sign * asp) % 360)
            o = min(o, 360 - o)
            if o <= max_orb and (best is None or o < best[1]):
                best = (asp, o)
    return best

# =====================================================================
# (3) DECLINATION + OUT-OF-BOUNDS (Bradley)
# =====================================================================
OOB_THRESHOLD = 23.4367  # tropical axis tilt

def declinations(jd):
    """Get equatorial declinations for major planets."""
    d = {}
    for name, pid in PLANET_IDS.items():
        if name in ("NN",): continue
        try:
            res = swe.calc_ut(jd, pid, swe.FLG_SWIEPH | swe.FLG_EQUATORIAL)
            d[name] = res[0][1]  # declination in degrees
        except:
            pass
    return d

def parallel_check(d_a, d_b, max_orb=1.0):
    """Parallel (same sign + close) or contraparallel (opposite sign + close)."""
    diff = abs(d_a - d_b)
    if diff <= max_orb and (d_a * d_b >= 0):  # same sign
        return ("parallel", diff)
    sum_ = abs(d_a + d_b)
    if sum_ <= max_orb:  # opposite signs, close in magnitude
        return ("contraparallel", sum_)
    return None

def is_out_of_bounds(decl):
    return abs(decl) > OOB_THRESHOLD

def declination_score(natal_decl, trans_decl):
    """Score declination parallels/contraparallels between transit and natal.
    Transit outer parallel/contraparallel to natal Sun/Moon/Venus/Mars = signal."""
    score = 0
    hits = []
    for t_planet in ("Jupiter","Saturn","Uranus","Neptune","Pluto"):
        if t_planet not in trans_decl: continue
        for n_planet in ("Sun","Moon","Venus","Mars","Jupiter"):
            if n_planet not in natal_decl: continue
            r = parallel_check(trans_decl[t_planet], natal_decl[n_planet], max_orb=1.0)
            if r:
                kind, o = r
                w = 1.0 if kind == "parallel" else 0.85
                s = w * (1.0 - o)
                score += s
                hits.append((t_planet, n_planet, kind, o))
    # OOB boost
    oob_count = sum(1 for p in ("Mars","Venus","Mercury") if p in trans_decl and is_out_of_bounds(trans_decl[p]))
    return score, hits, oob_count

# =====================================================================
# (4) SECONDARY PROGRESSIONS
# =====================================================================
def secondary_progressions(natal_date_str, eval_date_str):
    """Compute progressed planet positions.
    1 day after birth = 1 year of life.
    eval_date in YYYY-MM-DD."""
    from datetime import date
    n_y, n_m, n_d = [int(x) for x in natal_date_str[:10].split("-")]
    e_y, e_m, e_d = [int(x) for x in eval_date_str[:10].split("-")]
    n_dt = date(n_y, n_m, n_d)
    e_dt = date(e_y, e_m, e_d)
    years_lived = (e_dt - n_dt).days / 365.2422
    # Progressed date = natal + years_lived days
    from datetime import timedelta
    prog_dt = n_dt + timedelta(days=years_lived)
    prog_jd = swe.julday(prog_dt.year, prog_dt.month, prog_dt.day, 14.5)
    prog = {}
    for name, pid in PLANET_IDS.items():
        if name == "NN": continue
        res = swe.calc_ut(prog_jd, pid)
        prog[name] = {"lon": res[0][0] % 360, "speed": res[0][3]}
    return prog, years_lived

def progressed_lunation_phase(prog):
    """Progressed Sun-Moon phase — 29.5 yr cycle."""
    diff = (prog["Moon"]["lon"] - prog["Sun"]["lon"]) % 360
    if diff < 45: return "prog_new"
    elif diff < 90: return "prog_crescent"
    elif diff < 135: return "prog_first_q"
    elif diff < 180: return "prog_gibbous"
    elif diff < 225: return "prog_full"
    elif diff < 270: return "prog_disseminating"
    elif diff < 315: return "prog_last_q"
    else: return "prog_balsamic"

def prog_to_natal_aspects(natal, prog, max_orb=2.0):
    """Aspects of progressed planets to natal sensitive points."""
    hits = []
    for p_planet in ("Sun","Moon","Mercury","Venus","Mars"):
        for n_planet in ("Sun","Moon","Venus","Mars","Jupiter","Saturn"):
            if n_planet not in natal or p_planet not in prog: continue
            for asp in (0, 60, 90, 120, 180):
                for sign in (+1, -1):
                    o = abs((prog[p_planet]["lon"] - natal[n_planet]["lon"] - sign * asp) % 360)
                    o = min(o, 360 - o)
                    if o <= max_orb:
                        hits.append({"prog": p_planet, "natal": n_planet, "aspect": asp, "orb": o})
                        break
    return hits

# =====================================================================
# (5) FIRDARIA (Persian time lord, Al-Biruni)
# =====================================================================
# Day chart: Sun→Venus→Mercury→Moon→Saturn→Jupiter→Mars→NN→SN, total 75 years
# Each planet's period: Sun 10y, Venus 8y, Mercury 13y, Moon 9y, Saturn 11y, Jupiter 12y, Mars 7y, NN 3y, SN 2y
FIRDARIA_PERIODS = [
    ("Sun", 10), ("Venus", 8), ("Mercury", 13), ("Moon", 9),
    ("Saturn", 11), ("Jupiter", 12), ("Mars", 7), ("NN", 3), ("SN", 2),
]
FIRDARIA_NIGHT = [
    ("Moon", 9), ("Saturn", 11), ("Jupiter", 12), ("Mars", 7),
    ("NN", 3), ("SN", 2), ("Sun", 10), ("Venus", 8), ("Mercury", 13),
]

def firdaria_lord(age_years, is_day):
    """Return (current major lord, minor lord) for age in years."""
    periods = FIRDARIA_PERIODS if is_day else FIRDARIA_NIGHT
    total_cycle = sum(p[1] for p in periods)
    age = age_years % total_cycle
    remaining = age
    major = None; major_period = 0
    for lord, years in periods:
        if remaining < years:
            major = lord; major_period = years; break
        remaining -= years
    else:
        major = periods[-1][0]; major_period = periods[-1][1]
    # Minor lord: the major's period is subdivided into 7 sub-periods, each ruled by a planet
    # Sub-periods use the "7 visible planets" order: major→next→next... (simplified)
    sub_len = major_period / 7.0
    sub_idx = min(6, int(remaining / sub_len))
    # Simplified minor: cycle through the 7 visible planets starting from major
    sequence_all = ["Sun","Venus","Mercury","Moon","Saturn","Jupiter","Mars"]
    try:
        start = sequence_all.index(major)
    except ValueError:
        start = 0  # for NN/SN, fallback
    minor = sequence_all[(start + sub_idx) % 7]
    return major, minor, major_period
