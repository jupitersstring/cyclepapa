"""
Deep dive on the 11 MEGA PARABOLIC rallies (100x+).
Extract exact transit-to-natal configurations at the bottom month.
Find archetype-specific inflection rules.
"""
import math
import statistics as st
from collections import defaultdict
from bti_test import compute_natal, transits_at
from bti_v4 import yx
from secular_bottoms_corpus import SECULAR_BOTTOMS

SIGNS = ["Ari","Tau","Gem","Can","Leo","Vir","Lib","Sco","Sag","Cap","Aqu","Pis"]

def orb(a, b):
    d = abs(a - b) % 360
    return min(d, 360 - d)

def hard_orb_detailed(transit_lon, natal_lon, max_orb=10):
    """Find the closest hard aspect (0/90/180) of transit to natal."""
    best = None
    for asp in (0, 90, 180):
        for offset in (asp, -asp):
            d = abs((transit_lon - natal_lon - offset) % 360)
            d = min(d, 360 - d)
            if d <= max_orb and (best is None or d < best[1]):
                best = (asp, d)
    return best

def examine_chart_at_bottom(tk, ipo, bot, mult, note):
    natal = compute_natal(ipo)
    y, m = bot
    trans = transits_at(y, m)
    print(f"\n{'='*100}")
    print(f"{tk}  IPO={ipo}  Bottom={y}-{m:02d}  Multiple={mult}×  {note}")
    print(f"{'='*100}")

    # Natal luminaries and angles
    print(f"  NATAL:")
    for p in ("Sun","Moon","Mercury","Venus","Mars","Jupiter","Saturn","Uranus","Neptune","Pluto","ASC"):
        if p in natal:
            lon = natal[p]["lon"]
            print(f"    {p:<8s}  {lon:6.2f}°  ({SIGNS[int(lon//30)]} {lon%30:5.2f}°)")

    # Transit outer aspects to natal Sun specifically
    print(f"\n  TRANSIT ACTIVATIONS AT BOTTOM ({y}-{m:02d}):")
    natal_sun = natal["Sun"]["lon"]
    for outer in ("Jupiter","Saturn","Uranus","Neptune","Pluto"):
        t_lon = trans[outer]["lon"]
        # to natal Sun
        r = hard_orb_detailed(t_lon, natal_sun, 10)
        if r:
            asp, o = r
            print(f"    transit {outer:<8s} {t_lon:6.2f}° ({SIGNS[int(t_lon//30)]}) → natal Sun {asp}° asp orb {o:.1f}°")
        # to natal Moon
        nm = natal["Moon"]["lon"]
        r = hard_orb_detailed(t_lon, nm, 6)
        if r:
            asp, o = r
            print(f"    transit {outer:<8s}           → natal Moon {asp}° asp orb {o:.1f}°")
        # to natal outer itself (return/cycle check)
        no = natal[outer]["lon"]
        r = hard_orb_detailed(t_lon, no, 6)
        if r:
            asp, o = r
            print(f"    transit {outer:<8s}           → NATAL {outer} {asp}° asp orb {o:.1f}° (cycle)")
    # Return the key features
    # Number of outers hitting natal Sun within 5° hard aspect
    hits_sun = 0
    hits_sun_detail = []
    for outer in ("Jupiter","Saturn","Uranus","Neptune","Pluto"):
        r = hard_orb_detailed(trans[outer]["lon"], natal_sun, 5)
        if r:
            hits_sun += 1
            hits_sun_detail.append((outer, r[0], r[1]))
    # Conjunction of any two outers
    conjs = 0
    for i, o1 in enumerate(("Jupiter","Saturn","Uranus","Neptune","Pluto")):
        for o2 in ("Jupiter","Saturn","Uranus","Neptune","Pluto")[i+1:]:
            if orb(trans[o1]["lon"], trans[o2]["lon"]) <= 5:
                conjs += 1
    return {"hits_sun": hits_sun, "hits_sun_detail": hits_sun_detail, "conjs": conjs,
            "mult": mult, "sun_sign": SIGNS[natal["Sun"]["sign"]]}

# Filter mega rallies
MEGA = [s for s in SECULAR_BOTTOMS if s[4] >= 100]
print(f"Examining {len(MEGA)} MEGA rallies (100x+):")

features = []
for tk, ipo, bot, top, mult, note in MEGA:
    try:
        f = examine_chart_at_bottom(tk, ipo, bot, mult, note)
        f["tk"] = tk
        features.append(f)
    except Exception as e:
        print(f"{tk}: ERROR {e}")

# Aggregate patterns
print(f"\n{'='*100}")
print(f"AGGREGATE PATTERNS ACROSS {len(features)} MEGA RALLIES")
print(f"{'='*100}")

avg_hits = st.mean(f["hits_sun"] for f in features)
print(f"  Mean outer-to-natal-Sun hits within 5° orb: {avg_hits:.1f}")
print(f"  Charts with ≥1 outer-Sun hit: {sum(1 for f in features if f['hits_sun']>=1)}/{len(features)}")
print(f"  Charts with ≥2 outer-Sun hits: {sum(1 for f in features if f['hits_sun']>=2)}/{len(features)}")
print(f"  Mean outer-outer conjunctions within 5°: {st.mean(f['conjs'] for f in features):.1f}")

# Sun sign distribution
sun_counts = defaultdict(int)
for f in features: sun_counts[f["sun_sign"]] += 1
print(f"  Sun sign: {dict(sun_counts)}")

# What specific outer hits Sun most?
outer_hit_counts = defaultdict(int)
for f in features:
    for outer, asp, o in f["hits_sun_detail"]:
        outer_hit_counts[outer] += 1
print(f"  Outer-to-Sun hit distribution: {dict(outer_hit_counts)}")

# Compare to modest rallies
print(f"\nBaseline — same analysis on 47 MODEST rallies (3-9x):")
MODEST = [s for s in SECULAR_BOTTOMS if 3 <= s[4] < 10]
mod_features = []
for tk, ipo, bot, top, mult, note in MODEST:
    try:
        natal = compute_natal(ipo)
        trans = transits_at(bot[0], bot[1])
        hits = 0
        for outer in ("Jupiter","Saturn","Uranus","Neptune","Pluto"):
            r = hard_orb_detailed(trans[outer]["lon"], natal["Sun"]["lon"], 5)
            if r: hits += 1
        conjs = 0
        for i, o1 in enumerate(("Jupiter","Saturn","Uranus","Neptune","Pluto")):
            for o2 in ("Jupiter","Saturn","Uranus","Neptune","Pluto")[i+1:]:
                if orb(trans[o1]["lon"], trans[o2]["lon"]) <= 5:
                    conjs += 1
        mod_features.append({"hits_sun": hits, "conjs": conjs})
    except Exception:
        pass
print(f"  Mean outer-to-Sun hits: {st.mean(f['hits_sun'] for f in mod_features):.1f}")
print(f"  Charts with ≥1 outer-Sun hit: {sum(1 for f in mod_features if f['hits_sun']>=1)}/{len(mod_features)}")
print(f"  Charts with ≥2 outer-Sun hits: {sum(1 for f in mod_features if f['hits_sun']>=2)}/{len(mod_features)}")
print(f"  Mean outer-outer conjunctions: {st.mean(f['conjs'] for f in mod_features):.1f}")
