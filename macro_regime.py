"""
Macro-regime layer — current outer-planet signs, dignities, Jupiter window,
Uranus-Pluto trine proximity, lunar cycle modifier.

Implements the synthesis from the multi-practitioner financial-astrology
research report:
  - Jupiter in Cancer (EXALTED) through June 30, 2026 → sector tilt to
    food/beverage/homebuilders/residential-REITs/water-util/hospitality.
  - Jupiter moves to Leo on June 30, 2026 → pivot to entertainment/
    creator-economy/luxury/gambling/gold.
  - Saturn in Aries (FALL, permanent Feb 13, 2026) → constrains startups/
    speculative crypto/impulsive discretionary; favors mature defense and
    industrial metals. Mirrors 1937-40 triple-ingress bearish analog.
  - Neptune in Aries (FALL, permanent Jan 26, 2026) → bullish defense/
    aerospace/uranium/precious-metals; bearish long-duration fossil fuels;
    pharma pivots from opioid/pain to gene-editing/trauma.
  - Uranus in Gemini (permanent April 25, 2026) → semis/AI/autonomous/
    drones/satellites/uranium-nuclear/EdTech/streaming.
  - Pluto in Aquarius (permanent Nov 19, 2024 through 2043) → AI
    infrastructure / decentralization / networks / cybersecurity / grid.
  - Uranus-Pluto trine EXACT: 2026-07-18, 2026-11-29, 2027-06-15,
    2028-01-13, 2028-05-09 ("Techno-Renaissance" flagship — Merriman).
  - Lunar cycle (Dichev-Janes 2003, replicated): new-moon ±7 days delivers
    ~2× returns vs full-moon ±7 days.

Modern sector mapping weights from the report:
  CRYPTO        Uranus 50 Pluto 30 Neptune 20
  AI_QUANTUM    Uranus 50 Mercury 25 Pluto 15 Saturn 10
  SEMIS         Uranus 50 Mercury 30
  BIOTECH       Pluto 60 Neptune 30
  CYBERSEC      Pluto 40 Uranus 30
  EV/CLEAN      Uranus 40 Saturn 20 Mars 20 Venus 20
  SPACE         Uranus 50 Jupiter 30 Saturn 20
  STREAMING     Neptune 40 Uranus 30 Sun 30

Dignity boosts: domicile/exaltation +20%; detriment/fall -20%.
"""
import swisseph as swe
from datetime import datetime, date
from bti_test import jd_of

SIGNS = ["Aries","Taurus","Gemini","Cancer","Leo","Virgo",
         "Libra","Scorpio","Sagittarius","Capricorn","Aquarius","Pisces"]
SIGN_IDX = {s:i for i,s in enumerate(SIGNS)}

# Dignity table — planet → {dignity: sign_index}
DIGNITY = {
    "Sun":     {"domicile":[4],   "exalt":[0],  "detriment":[10], "fall":[6]},     # Leo/Aries/Aqu/Lib
    "Moon":    {"domicile":[3],   "exalt":[1],  "detriment":[9],  "fall":[7]},     # Can/Tau/Cap/Sco
    "Mercury": {"domicile":[2,5], "exalt":[5],  "detriment":[8,11],"fall":[11]},   # Gem,Vir/Vir
    "Venus":   {"domicile":[1,6], "exalt":[11], "detriment":[7,0],"fall":[5]},     # Tau,Lib/Pis
    "Mars":    {"domicile":[0,7], "exalt":[9],  "detriment":[6,1],"fall":[3]},     # Ari,Sco/Cap
    "Jupiter": {"domicile":[8,11],"exalt":[3],  "detriment":[2,5],"fall":[9]},     # Sag,Pis/Cancer (CURRENT)
    "Saturn":  {"domicile":[9,10],"exalt":[6],  "detriment":[3,4],"fall":[0]},     # Cap,Aqu/Lib/ARIES (CURRENT FALL)
    "Uranus":  {"domicile":[10],  "exalt":[7],  "detriment":[4],  "fall":[1]},     # Aqu/Sco/Leo/Taurus
    "Neptune": {"domicile":[11],  "exalt":[4],  "detriment":[5],  "fall":[10]},    # Pis/Leo/Vir/Aqu  (Aries = uncomfortable, debated)
    "Pluto":   {"domicile":[7],   "exalt":[0],  "detriment":[1],  "fall":[6]},     # Sco/Ari/Tau/Lib
}

def dignity_multiplier(planet, lon):
    """Return 1.2 if exalt/domicile, 0.8 if detriment/fall, else 1.0."""
    sign = int(lon // 30)
    d = DIGNITY.get(planet, {})
    if sign in d.get("domicile", []) or sign in d.get("exalt", []):
        return 1.20
    if sign in d.get("detriment", []) or sign in d.get("fall", []):
        return 0.80
    return 1.0

def planet_positions(y, m, d=15, hr=12.0):
    jd = jd_of(y, m, d, hr)
    out = {}
    for name, pid in [("Sun",swe.SUN),("Moon",swe.MOON),
                       ("Mercury",swe.MERCURY),("Venus",swe.VENUS),("Mars",swe.MARS),
                       ("Jupiter",swe.JUPITER),("Saturn",swe.SATURN),
                       ("Uranus",swe.URANUS),("Neptune",swe.NEPTUNE),("Pluto",swe.PLUTO)]:
        lon = swe.calc_ut(jd, pid)[0][0] % 360
        out[name] = {"lon": lon, "sign": SIGNS[int(lon//30)], "deg": lon % 30}
    return out

# ======================================================================
# JUPITER-SECTOR WINDOW (Grace Morris / report synthesis)
# ======================================================================
JUPITER_LEO_INGRESS_JD = jd_of(2026, 6, 30, 12.0)

def jupiter_sector_tilt(y, m):
    """Return dict sector → multiplier based on current Jupiter sign."""
    jd = jd_of(y, m, 15, 12.0)
    jup_lon = swe.calc_ut(jd, swe.JUPITER)[0][0] % 360
    jup_sign = int(jup_lon // 30)
    # Cancer (sign 3) — exalted through Jun 30, 2026
    if jup_sign == 3:
        return {"FOOD_BEV": 1.25, "HOMEBUILDER": 1.25, "REIT": 1.20,
                "WATER_UTIL": 1.20, "HOSPITALITY": 1.20, "STAPLES": 1.15,
                "RESTAURANT": 1.15, "RETAIL": 1.08,
                # dignity bonus applies across the board
                "__all__": 1.08}
    # Leo (sign 4)
    if jup_sign == 4:
        return {"ENTERTAINMENT": 1.25, "MEDIA": 1.20, "LUXURY": 1.20,
                "GAMBLING": 1.20, "GOLD": 1.15, "CREATOR_ECONOMY": 1.20,
                "STREAMING": 1.15, "__all__": 1.02}
    # Virgo (5) — health services, work tech
    if jup_sign == 5:
        return {"HEALTH": 1.15, "SAAS": 1.10, "INDUSTRIAL": 1.05, "__all__": 1.0}
    # Libra (6) — partnerships, diplomacy, cosmetics
    if jup_sign == 6:
        return {"FINANCE": 1.10, "LUXURY": 1.10, "LEGAL": 1.10, "__all__": 1.0}
    return {"__all__": 1.0}

# ======================================================================
# OUTER-PLANET-SIGN MACRO TILTS (Neptune, Saturn, Uranus, Pluto)
# ======================================================================
def outer_macro_tilts(y, m):
    """Current outer-planet signs → sector multipliers."""
    jd = jd_of(y, m, 15, 12.0)
    tilts = {}
    def merge(d):
        for k, v in d.items():
            tilts[k] = tilts.get(k, 1.0) * v

    # NEPTUNE sign
    nep_lon = swe.calc_ut(jd, swe.NEPTUNE)[0][0] % 360
    nep_sign = int(nep_lon // 30)
    if nep_sign == 0:   # Aries — fall, fiery dissolution, war
        merge({"DEFENSE":1.25,"AEROSPACE":1.25,"NUCLEAR":1.20,"URANIUM":1.25,
               "METALS":1.15,"PRECIOUS_METALS":1.20,
               "BIOPHARM":1.05,  # pharma pivots, moderate boost
               "FOSSIL":0.80,    # long-duration fossil fuels bearish
               "STREAMING":1.10,"MEDIA":1.05})
    elif nep_sign == 11:  # Pisces — oil, pharma, film (domicile)
        merge({"ENERGY":1.15,"BIOPHARM":1.15,"MEDIA":1.15,"STREAMING":1.15})

    # SATURN sign
    sat_lon = swe.calc_ut(jd, swe.SATURN)[0][0] % 360
    sat_sign = int(sat_lon // 30)
    if sat_sign == 0:  # Aries (fall) — constrains speculative, favors mature
        merge({"DEFENSE":1.15,"INDUSTRIAL":1.10,"METALS":1.10,"UTILS":1.08,
               "CRYPTO":0.80,"MEME":0.75,"AI_QUANTUM":0.90,
               "RETAIL":0.90,"STREAMING":0.95})
    elif sat_sign in (9,10):  # Capricorn/Aquarius (domicile)
        merge({"INDUSTRIAL":1.15,"REIT":1.10,"UTILS":1.10})

    # URANUS sign
    ura_lon = swe.calc_ut(jd, swe.URANUS)[0][0] % 360
    ura_sign = int(ura_lon // 30)
    if ura_sign == 1:  # Taurus (fall) — currency/banking disruption (until Apr 25 2026)
        merge({"CRYPTO":1.20,"FINANCE":1.10,"METALS":1.05})
    elif ura_sign == 2:  # Gemini (domicile-like) — comms/AI/semis/autonomous
        merge({"SEMIS":1.30,"AI_QUANTUM":1.30,"TECH":1.20,
               "SPACE":1.25,"AUTONOMOUS":1.30,"DRONES":1.25,
               "EV":1.15,"SATELLITES":1.25,"MEDIA":1.15,"STREAMING":1.20,
               "NUCLEAR":1.20,"URANIUM":1.20,  # AI-driven electricity demand
               "EDTECH":1.20})
    elif ura_sign == 10:  # Aquarius (domicile)
        merge({"TECH":1.20,"AI_QUANTUM":1.20,"CRYPTO":1.15,"SPACE":1.15})

    # PLUTO sign
    plu_lon = swe.calc_ut(jd, swe.PLUTO)[0][0] % 360
    plu_sign = int(plu_lon // 30)
    if plu_sign == 10:  # Aquarius — AI, networks, decentralization
        merge({"AI_QUANTUM":1.25,"TECH":1.15,"CYBERSEC":1.25,
               "SEMIS":1.20,"NUCLEAR":1.20,"URANIUM":1.20,
               "BIOTECH":1.15,"SPACE":1.15,"CRYPTO":1.10})
    elif plu_sign == 7:  # Scorpio (domicile)
        merge({"BIOTECH":1.20,"BIOPHARM":1.15,"FINANCE":1.10,"NUCLEAR":1.15})

    return tilts

# ======================================================================
# URANUS-PLUTO TRINE proximity (Merriman "Techno-Renaissance")
# ======================================================================
URANUS_PLUTO_TRINE_DATES = [
    (2026, 7, 18), (2026,11,29), (2027, 6,15), (2028, 1,13), (2028, 5, 9)
]

def uranus_pluto_trine_days_to(y, m):
    """Days to nearest Uranus-Pluto trine exact (from 15th of month)."""
    cur = datetime(y, m, 15)
    best = 99999
    for ty, tm, td in URANUS_PLUTO_TRINE_DATES:
        d = abs((datetime(ty, tm, td) - cur).days)
        if d < best: best = d
    return best

def trine_bonus(y, m):
    """1.0 default, up to 1.15 if within 45 days of a Ura-Plu trine exact."""
    d = uranus_pluto_trine_days_to(y, m)
    if d <= 15: return 1.15
    if d <= 30: return 1.08
    if d <= 45: return 1.04
    return 1.0

# ======================================================================
# LUNAR CYCLE (Dichev-Janes)
# ======================================================================
def sun_moon_elong(y, m, d=15):
    """Angular separation Moon from Sun (0 = new, 180 = full)."""
    jd = jd_of(y, m, d, 12.0)
    sun = swe.calc_ut(jd, swe.SUN)[0][0] % 360
    mon = swe.calc_ut(jd, swe.MOON)[0][0] % 360
    diff = abs(mon - sun)
    if diff > 180: diff = 360 - diff
    return diff

def lunar_modifier(y, m, d=15):
    """Elongation 0° = new-moon, 180° = full-moon.
       Dichev-Janes: ±7 day new-moon window returns ~2× full-moon window.
       Return multiplier 1.10 near new moon, 0.95 near full."""
    el = sun_moon_elong(y, m, d)
    # closer to 0 = new; closer to 180 = full
    new_moon_proximity = 1 - min(el, 180 - (180 - el)) / 180   # not quite right; recompute
    # Simpler: distance from new (0) and from full (180)
    d_new = el
    d_full = abs(180 - el)
    if d_new < 30:   return 1.10
    if d_full < 30:  return 0.95
    return 1.0

# ======================================================================
# Combined macro-regime multiplier for a sector at (y, m)
# ======================================================================
def macro_regime_multiplier(sector, y, m):
    """Combine jupiter window × outer tilts × trine × lunar."""
    jup_t = jupiter_sector_tilt(y, m)
    out_t = outer_macro_tilts(y, m)
    mult = 1.0
    mult *= jup_t.get(sector, jup_t.get("__all__", 1.0))
    mult *= out_t.get(sector, 1.0)
    mult *= trine_bonus(y, m)
    mult *= lunar_modifier(y, m)
    return mult

# ======================================================================
# Per-ticker dignity assessment (for strengthening/weakening of its outers)
# ======================================================================
def planet_dignity_mults_now(y, m):
    """Current dignity multiplier for each outer planet."""
    pos = planet_positions(y, m)
    return {p: dignity_multiplier(p, pos[p]["lon"])
            for p in ("Jupiter","Saturn","Uranus","Neptune","Pluto")}

if __name__ == "__main__":
    # Demo print for April 2026
    print("Current planetary signs (2026-04-15):")
    pos = planet_positions(2026, 4)
    for p, v in pos.items():
        d = dignity_multiplier(p, v["lon"]) if p in DIGNITY else 1.0
        tag = "▲EXALT/DOM" if d > 1.1 else ("▼FALL/DET" if d < 0.9 else "")
        print(f"  {p:<9s} {v['lon']:7.2f}°  {v['sign']:<12s} {v['deg']:5.2f}°   {tag}")

    print("\nDignity multipliers (outers, April 2026):")
    for p, m in planet_dignity_mults_now(2026, 4).items():
        print(f"  {p:<9s} {m:.2f}")

    print("\nCurrent sector regime tilts (April 2026):")
    all_tilts = {}
    jt = jupiter_sector_tilt(2026, 4)
    ot = outer_macro_tilts(2026, 4)
    for d in (jt, ot):
        for k, v in d.items():
            if k == "__all__": continue
            all_tilts[k] = all_tilts.get(k, 1.0) * v
    for s, v in sorted(all_tilts.items(), key=lambda x:-x[1]):
        arrow = "▲" if v > 1.1 else ("▼" if v < 0.95 else " ")
        print(f"  {arrow} {s:<18s} {v:.2f}")

    print(f"\nUranus-Pluto trine proximity: {uranus_pluto_trine_days_to(2026, 4)} days to nearest exact")
    print(f"Lunar modifier (Apr 15, 2026): {lunar_modifier(2026, 4, 15):.2f}")

    print("\nForward macro-regime through next 24 months for AI_QUANTUM / SEMIS / URANIUM:")
    for k in range(0, 25, 3):
        my = 2026 + (4 - 1 + k) // 12
        mm = (4 - 1 + k) % 12 + 1
        print(f"  {my}-{mm:02d}  "
              f"AI_QUANTUM {macro_regime_multiplier('AI_QUANTUM', my, mm):.2f}   "
              f"SEMIS {macro_regime_multiplier('SEMIS', my, mm):.2f}   "
              f"URANIUM {macro_regime_multiplier('URANIUM', my, mm):.2f}   "
              f"DEFENSE {macro_regime_multiplier('DEFENSE', my, mm):.2f}   "
              f"GOLD {macro_regime_multiplier('GOLD', my, mm):.2f}   "
              f"HOMEBUILDER {macro_regime_multiplier('HOMEBUILDER', my, mm):.2f}")
