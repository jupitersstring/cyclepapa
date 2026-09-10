"""
Classical chart archetype classification grounded in:
  - Hellenistic: Ptolemy, Vettius Valens — sect
  - Dorotheus: triplicity rulers (day/night/participating)
  - Persian/Islamicate: Abu Ma'shar — great-conjunction mutation element
  - Ibn Ezra: almuten figuris computation (simplified)
  - Mundane: McWhirter — transit node position as bullish/bearish classifier
  - Financial: Merriman — synodic-phase relation Jupiter-Saturn

The sect light (Sun for day, Moon for night) is the chart's primary significator
per all Hellenistic sources. Its triplicity ruler is the chart's "master planet"
in the Dorothian system used throughout Persian and medieval traditions.
"""
import math
from collections import defaultdict

SIGNS = ["Ari","Tau","Gem","Can","Leo","Vir","Lib","Sco","Sag","Cap","Aqu","Pis"]
ELEMENTS = {0:"fire",4:"fire",8:"fire",  1:"earth",5:"earth",9:"earth",
            2:"air",6:"air",10:"air",    3:"water",7:"water",11:"water"}
MODALITY = {0:"card",3:"card",6:"card",9:"card",  1:"fix",4:"fix",7:"fix",10:"fix",
            2:"mut",5:"mut",8:"mut",11:"mut"}

# Dorothian triplicity rulers (day / night / participating)
TRIPLICITY = {
    "fire":  {"day": "Sun",     "night": "Jupiter", "part": "Saturn"},
    "earth": {"day": "Venus",   "night": "Moon",    "part": "Mars"},
    "air":   {"day": "Saturn",  "night": "Mercury", "part": "Jupiter"},
    "water": {"day": "Venus",   "night": "Mars",    "part": "Moon"},
}

# Domicile rulers (traditional)
DOMICILE = {
    0:"Mars",1:"Venus",2:"Mercury",3:"Moon",4:"Sun",5:"Mercury",
    6:"Venus",7:"Mars",8:"Jupiter",9:"Saturn",10:"Saturn",11:"Jupiter"
}
# Exaltation (sign : planet)
EXALTATION = {0:"Sun",1:"Moon",3:"Jupiter",5:"Mercury",6:"Saturn",9:"Mars",11:"Venus"}

# Sect — day chart has Sun above horizon; night chart has Sun below
def is_day_chart(natal):
    """Sun above horizon = day chart. Use ASC/DSC angle."""
    sun_asc_arc = (natal["Sun"]["lon"] - natal["ASC"]["lon"]) % 360
    # Houses 1-6 (below horizon): Sun within 0-180° counterclockwise from ASC
    # Houses 7-12 (above horizon): Sun within 180-360° counterclockwise from ASC
    return sun_asc_arc > 180

def essential_dignity_score(natal, planet, point_lon):
    """Ibn Ezra-style essential dignity score of `planet` at zodiacal degree `point_lon`.
    Domicile=5, Exaltation=4, Triplicity=3, Bounds=2, Face=1.
    Simplified: uses only sign, exaltation, triplicity (the strongest three).
    """
    sign_idx = int(point_lon // 30)
    score = 0
    if DOMICILE.get(sign_idx) == planet:
        score += 5
    if EXALTATION.get(sign_idx) == planet:
        score += 4
    elem = ELEMENTS[sign_idx]
    is_day = is_day_chart(natal)
    trip = TRIPLICITY[elem]
    if trip["day" if is_day else "night"] == planet:
        score += 3
    if trip["part"] == planet:
        score += 1  # participating
    return score

def almuten_figuris(natal):
    """Ibn Ezra-style almuten: most dignified planet across 4 key points.
    Survey points: Sun, Moon, ASC, Lot of Fortune. (Skipping prev-syzygy for speed.)
    """
    # Lot of Fortune (day): ASC + Moon - Sun
    is_day = is_day_chart(natal)
    lof = (natal["ASC"]["lon"] + (natal["Moon"]["lon"] - natal["Sun"]["lon"] if is_day
                                    else natal["Sun"]["lon"] - natal["Moon"]["lon"])) % 360
    points = {
        "Sun": natal["Sun"]["lon"],
        "Moon": natal["Moon"]["lon"],
        "ASC": natal["ASC"]["lon"],
        "LOF": lof,
    }
    scores = {}
    for planet in ("Sun","Moon","Mercury","Venus","Mars","Jupiter","Saturn"):
        total = sum(essential_dignity_score(natal, planet, lon) for lon in points.values())
        scores[planet] = total
    # Best planet
    return max(scores, key=scores.get), scores

def abu_mashar_mutation(year):
    """Which great-conjunction element was active at `year`?
    Current sequence (with bleedthrough, simplified):
      1802-2020: Earth (1842 conjunction in Virgo inaugural)
      2020-  :   Air (Dec 21 2020 at 0° Aqu full mutation)
      1603-1842: Fire
    """
    if year >= 2020: return "air"
    elif year >= 1842: return "earth"
    elif year >= 1603: return "fire"
    elif year >= 1405: return "water"
    elif year >= 1186: return "air"
    else: return "unknown"

def jupiter_saturn_synodic_phase(natal):
    """Position in Jupiter-Saturn synodic cycle at natal.
    0° = conjunction (new), 180° = opposition (full). 20-year cycle.
    Phases: balsamic(300-360), new(0-45), crescent(45-90), first(90-135),
            gibbous(135-180), full(180-225), disseminating(225-270), last(270-300)
    """
    diff = (natal["Jupiter"]["lon"] - natal["Saturn"]["lon"]) % 360
    if diff < 45: return "new"
    elif diff < 90: return "crescent"
    elif diff < 135: return "first_q"
    elif diff < 180: return "gibbous"
    elif diff < 225: return "full"
    elif diff < 270: return "disseminating"
    elif diff < 300: return "last_q"
    else: return "balsamic"

def mcwhirter_node_category(nn_sign_idx):
    """McWhirter's classification of transit/natal NN position relevant to markets.
    Cancer/Leo: bullish peaks (prosperity crest)
    Virgo/Libra: bullish bottoms (setup for next expansion)
    Scorpio/Sag: transition/bear
    Capricorn/Aqu: setup for speculation
    """
    sign = SIGNS[nn_sign_idx]
    if sign in ("Can","Leo"): return "peak_zone"
    elif sign in ("Vir","Lib"): return "bottom_zone"
    elif sign in ("Sco","Sag"): return "bear_zone"
    elif sign in ("Cap","Aqu"): return "setup_zone"
    elif sign in ("Pis","Ari"): return "launch_zone"
    else: return "mid"

def classical_classify(natal):
    """Complete classical classification."""
    is_day = is_day_chart(natal)
    sect_light_name = "Sun" if is_day else "Moon"
    sect_light_sign_idx = natal[sect_light_name]["sign"]
    sect_light_elem = ELEMENTS[sect_light_sign_idx]
    trip = TRIPLICITY[sect_light_elem]
    trip_lord_day = trip["day"]
    trip_lord_night = trip["night"]
    trip_lord_part = trip["part"]
    primary_trip_lord = trip["day" if is_day else "night"]

    almuten_planet, scores = almuten_figuris(natal)

    ipo_year = natal.get("_date", "2000")[:4]
    try: yr = int(ipo_year)
    except: yr = 2000
    mutation = abu_mashar_mutation(yr)

    js_phase = jupiter_saturn_synodic_phase(natal)
    nn_category = mcwhirter_node_category(natal["NN"]["sign"])

    return {
        "sect": "day" if is_day else "night",
        "sect_light": sect_light_name,
        "sect_light_elem": sect_light_elem,
        "sect_light_sign": SIGNS[sect_light_sign_idx],
        "triplicity_lord_1": primary_trip_lord,
        "triplicity_lord_day": trip_lord_day,
        "triplicity_lord_night": trip_lord_night,
        "triplicity_lord_part": trip_lord_part,
        "almuten": almuten_planet,
        "mutation_elem": mutation,
        "js_phase": js_phase,
        "nn_category": nn_category,
    }

if __name__ == "__main__":
    from bti_test import compute_natal
    from secular_bottoms_corpus import SECULAR_BOTTOMS

    # Distribution of classical categories across 110 bottoms
    print(f"Classical classification of {len(SECULAR_BOTTOMS)} secular bottoms")
    print("="*80)
    counts = defaultdict(lambda: defaultdict(int))
    for tk, ipo, bot, top, mult, note in SECULAR_BOTTOMS:
        try:
            natal = compute_natal(ipo)
            cls = classical_classify(natal)
            for k, v in cls.items():
                counts[k][v] += 1
        except Exception:
            pass
    for key in ["sect","sect_light_elem","triplicity_lord_1","almuten","mutation_elem","js_phase","nn_category"]:
        print(f"\n{key}:")
        for v, n in sorted(counts[key].items(), key=lambda x:-x[1]):
            print(f"  {v:<15s} {n:3d}")
