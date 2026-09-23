"""
Heliocentric pattern analysis — Bradley / Gann core methodology.

Bradley's siderograph: "Siderograph = 5 × (Long-term Helio + Declinations) + Mid-term Geo"
→ Helio has the HIGHEST weight in the only empirically-audited astro-finance formula.

Gann: heliocentric longitudes for both time and price (1° = 1 day in certain setups).

Theoretical claims to test:
  (T1) Helio outer-to-outer synodic positions at bottoms vs quiet months
  (T2) Helio Jupiter-Neptune / Jupiter-Uranus / Saturn-Neptune / Saturn-Uranus / Uranus-Neptune
       cycles positions at bottoms
  (T3) Helio outer-to-natal-Sun aspects (helio resolves retrograde ambiguity)
  (T4) Heliocentric midpoints of outer-outer on natal Sun
  (T5) Earth-Jupiter-Saturn "master time factor" alignment (Gann)
"""
import math
import statistics as st
from collections import defaultdict
import swisseph as swe
from bti_test import jd_of, compute_natal, transits_at
from bti_v4 import yx
from parabolic_corpus import PARABOLIC_BOTTOMS

def helio_longitudes(jd):
    """Heliocentric longitudes of planets (ecliptic)."""
    h = {}
    for name, pid in [("Mercury", swe.MERCURY), ("Venus", swe.VENUS),
                      ("Earth", None),  # computed from Sun+180
                      ("Mars", swe.MARS), ("Jupiter", swe.JUPITER),
                      ("Saturn", swe.SATURN), ("Uranus", swe.URANUS),
                      ("Neptune", swe.NEPTUNE), ("Pluto", swe.PLUTO)]:
        if name == "Earth":
            res = swe.calc_ut(jd, swe.SUN)
            h["Earth"] = (res[0][0] + 180) % 360
        else:
            try:
                res = swe.calc_ut(jd, pid, swe.FLG_HELCTR)
                h[name] = res[0][0] % 360
            except: pass
    return h

def orb(a, b):
    d = abs((a - b) % 360)
    return min(d, 360 - d)

def hard_aspect_orb(a, b, max_orb=8):
    best = None
    for asp in (0, 60, 90, 120, 180):
        for sign in (+1, -1):
            o = orb(a, b + sign * asp)
            if o <= max_orb and (best is None or o < best[1]):
                best = (asp, o)
    return best

def synodic_separation(a, b):
    """Signed difference in ecliptic longitude (0-360)."""
    return (a - b) % 360

def extract_helio_features(natal, eval_y, eval_m):
    """Full heliocentric feature set at evaluation date."""
    jd = jd_of(eval_y, eval_m, 15, 12.0)
    h = helio_longitudes(jd)
    ipo_d = natal.get("_date", "2000-01-01")
    jd_n = jd_of(int(ipo_d[:4]), int(ipo_d[5:7]), int(ipo_d[8:10]), 14.5)
    hn = helio_longitudes(jd_n)

    f = {}
    # (T1, T2) Transit helio outer-to-outer synodic separations
    for a in ("Jupiter","Saturn","Uranus","Neptune","Pluto"):
        for b in ("Jupiter","Saturn","Uranus","Neptune","Pluto"):
            if a >= b: continue
            if a not in h or b not in h: continue
            sep = synodic_separation(h[a], h[b])
            f[f"he_{a[:3]}-{b[:3]}_sep"] = sep
            # Is it within orb of a hard aspect?
            for asp in (0, 60, 90, 120, 180):
                if orb(sep, asp) <= 6:
                    f[f"he_{a[:3]}-{b[:3]}_asp"] = asp
                    break

    # (T3) Helio outer-to-natal-Sun-HELIO (which is Earth opposition)
    # Natal chart's Earth helio position = natal chart's Sun geocentric + 180
    if "Earth" in hn:
        natal_earth_helio = hn["Earth"]  # = geo natal Sun + 180
        for outer in ("Jupiter","Saturn","Uranus","Neptune","Pluto"):
            if outer not in h: continue
            r = hard_aspect_orb(h[outer], natal_earth_helio, 6)
            if r:
                f[f"he_{outer[:3]}_NatEarth"] = r[1]  # orb of hard aspect
            else:
                f[f"he_{outer[:3]}_NatEarth"] = 99

    # (T5) Gann: Earth-Jupiter-Saturn alignment (all within 10° of a line)
    if all(p in h for p in ("Earth","Jupiter","Saturn")):
        # Check if Earth is conjunct or opposite the Jupiter-Saturn midpoint
        js_mp = ((h["Jupiter"] + h["Saturn"]) / 2) % 360
        e_js = orb(h["Earth"], js_mp)
        f["he_Earth_JS_mp"] = e_js
        # Is Earth opp or conj JS midpoint?
        e_js_opp = min(orb(h["Earth"], js_mp), orb(h["Earth"], (js_mp+180)%360))
        f["he_Earth_JS_mp_or_opp"] = e_js_opp

    # (T4) Helio midpoints on natal Sun
    if "Earth" in hn:
        nse = hn["Earth"]
        for a in ("Jupiter","Neptune","Uranus"):
            for b in ("Jupiter","Neptune","Uranus","Pluto"):
                if a >= b: continue
                if a not in h or b not in h: continue
                mp = ((h[a] + h[b]) / 2) % 360
                r = hard_aspect_orb(mp, nse, 4)
                if r:
                    f[f"he_{a[:3]}{b[:3]}_mid_NatE"] = r[1]
                else:
                    f[f"he_{a[:3]}{b[:3]}_mid_NatE"] = 99

    # Retrograde Count geocentric (for comparison, not helio — planets never go retro heliocentrically)
    return f, h, hn

def analyse_corpus():
    """Find the heliocentric signatures at 152 parabolic bottoms."""
    bots = []
    quiets = []
    for tk, ipo, bot, top, mult, speed, note in PARABOLIC_BOTTOMS:
        try:
            natal = compute_natal(ipo)
            f, h, hn = extract_helio_features(natal, bot[0], bot[1])
            bots.append({"tk": tk, "mult": mult, "speed": speed, "f": f})
            for off in (-18, -12, 12, 18):
                y, m = yx(bot[0], bot[1], off)
                fq, _, _ = extract_helio_features(natal, y, m)
                quiets.append(fq)
        except Exception:
            pass
    print(f"Extracted {len(bots)} bottoms, {len(quiets)} quiet")

    # For each helio outer-to-natal-Earth feature, compute %≤5° at bot vs quiet
    FEATS_NATEARTH = [f"he_{p}_NatEarth" for p in ("Jup","Sat","Ura","Nep","Plu")]
    print(f"\n{'='*100}")
    print("HELIO OUTER-TO-NATAL-EARTH (native-heliocentric natal-Sun-equivalent)")
    print(f"{'='*100}")
    print(f"{'Feature':<20s} {'Bot%≤5':>7s} {'Q%≤5':>7s} {'Diff':>7s}")
    for k in FEATS_NATEARTH:
        bpct = 100*sum(1 for b in bots if b["f"].get(k,99) <= 5)/len(bots)
        qpct = 100*sum(1 for q in quiets if q.get(k,99) <= 5)/len(quiets)
        d = bpct - qpct
        marker = "★★" if d > 8 else ("★" if d > 4 else "")
        print(f"  {k:<20s} {bpct:7.1f} {qpct:7.1f} {d:+7.1f}%  {marker}")

    # Outer-outer synodic phase distributions
    print(f"\n{'='*100}")
    print("HELIO OUTER-OUTER SYNODIC ASPECTS (hard aspect at the moment of bottom)")
    print(f"{'='*100}")
    print(f"  % of bottoms where helio X-Y are within 6° of a hard aspect (0/60/90/120/180)")
    pairs = ["Jup-Nep","Jup-Ura","Jup-Sat","Jup-Plu","Sat-Nep","Sat-Ura","Sat-Plu","Ura-Nep","Ura-Plu","Nep-Plu"]
    for pair in pairs:
        key = f"he_{pair}_asp"
        bpct = 100*sum(1 for b in bots if key in b["f"])/len(bots)
        qpct = 100*sum(1 for q in quiets if key in q)/len(quiets)
        d = bpct - qpct
        marker = "★★" if d > 10 else ("★" if d > 5 else "")
        # Aspect-type breakdown
        bot_asps = defaultdict(int)
        for b in bots:
            a = b["f"].get(key)
            if a is not None: bot_asps[a] += 1
        print(f"  {pair:<10s} bot:{bpct:5.1f}% q:{qpct:5.1f}% diff:{d:+5.1f}% asp_dist:{dict(bot_asps)} {marker}")

    # Earth-Jupiter-Saturn alignment (Gann)
    print(f"\n{'='*100}")
    print("GANN MASTER TIME FACTOR: Earth-Jupiter-Saturn alignment (within 5°)")
    print(f"{'='*100}")
    bpct = 100*sum(1 for b in bots if b["f"].get("he_Earth_JS_mp_or_opp",99) <= 5)/len(bots)
    qpct = 100*sum(1 for q in quiets if q.get("he_Earth_JS_mp_or_opp",99) <= 5)/len(quiets)
    print(f"  Bot:{bpct:.1f}%  Q:{qpct:.1f}%  diff:{bpct-qpct:+.1f}%")

    # Helio midpoints on natal Earth (natal Sun helio-equivalent)
    print(f"\n{'='*100}")
    print("HELIO OUTER-PAIR MIDPOINTS on NATAL EARTH (within 4°)")
    print(f"{'='*100}")
    for pair in ("JupNep","JupUra","JupPlu","NepUra","NepPlu","UraPlu"):
        key = f"he_{pair}_mid_NatE"
        bpct = 100*sum(1 for b in bots if b["f"].get(key,99) <= 4)/len(bots)
        qpct = 100*sum(1 for q in quiets if q.get(key,99) <= 4)/len(quiets)
        d = bpct - qpct
        marker = "★★" if d > 6 else ("★" if d > 3 else "")
        print(f"  {pair:<8s}_mid  bot:{bpct:5.1f}% q:{qpct:5.1f}% diff:{d:+5.1f}%  {marker}")

    # Per speed class
    print(f"\n{'='*100}")
    print("HELIO OUTER-TO-NATAL-EARTH BY SPEED CLASS")
    print(f"{'='*100}")
    for speed in ("FAST","MED","SLOW"):
        subset = [b for b in bots if b["speed"] == speed]
        if not subset: continue
        print(f"\n--- {speed} (n={len(subset)}) ---")
        for k in FEATS_NATEARTH:
            bpct = 100*sum(1 for b in subset if b["f"].get(k,99) <= 5)/len(subset)
            qpct = 100*sum(1 for q in quiets if q.get(k,99) <= 5)/len(quiets)
            d = bpct - qpct
            if d > 3:
                print(f"  {k:<20s} bot:{bpct:5.1f}% q:{qpct:5.1f}% diff:{d:+5.1f}% ★")

    # Per magnitude
    print(f"\n{'='*100}")
    print("HELIO NEP-NATAL-EARTH & HELIO PLU-NATAL-EARTH BY RALLY MAGNITUDE")
    print(f"{'='*100}")
    bins = [(3,10), (10,30), (30,100), (100,9999)]
    for lo, hi in bins:
        subset = [b for b in bots if lo <= b["mult"] < hi]
        if not subset: continue
        print(f"\n--- {lo}-{hi}× (n={len(subset)}) ---")
        for k in FEATS_NATEARTH:
            bpct = 100*sum(1 for b in subset if b["f"].get(k,99) <= 5)/len(subset)
            print(f"  {k:<20s} bot:{bpct:5.1f}%")

if __name__ == "__main__":
    analyse_corpus()
