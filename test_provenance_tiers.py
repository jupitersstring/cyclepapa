"""
EMPIRICAL TEST of the provenance-tier hypothesis on the 152-case corpus.

Compendium recommendation: weight classical-core rulerships above modern
conventions, and score contested signs on EITHER ruler. Does the data
support tier-weighting?

Test: for each parabolic case, at BOTTOM and PEAK, check whether the
sector's tier-filtered rulers were within 5° (any hard aspect) of natal
Sun/Moon/ASC/MC. Compare hit-rates:
  A) CLASSICAL-tier rulers only
  B) MODERN-tier rulers only (incl. those tagged from prior empirics)
  C) EITHER (dual-ruler policy)
against the per-case all-planet baseline hit-rate (chance of any given
planet being <=5° of a natal point on a random month ~= sector-agnostic).
Note: asteroid/experimental tiers carry weight 0 by design — not tested.
"""
import statistics as st
from collections import defaultdict
from bti_test import compute_natal, transits_at
from parabolic_corpus import PARABOLIC_BOTTOMS
from sector_astro import SECTOR as CORPUS_SECTOR
from rulership_compendium import SECTOR_RULERSHIP

NATAL_PTS = ("Sun","Moon","ASC","MC")
SEVEN = ("Sun","Moon","Mercury","Venus","Mars","Jupiter","Saturn")
ALL_10 = SEVEN + ("Uranus","Neptune","Pluto")

def orb(a, b):
    d = abs((a - b) % 360)
    return min(d, 360 - d)

def closest_hard(a, b):
    best = 99
    for asp in (0, 90, 180):
        for sign in (+1, -1):
            o = orb(a, b + sign*asp)
            if o < best: best = o
    return best

def planet_hit(natal, trans, planet, thresh=5.0):
    if planet not in trans: return False
    for pt in NATAL_PTS:
        if pt not in natal: continue
        if closest_hard(trans[planet]["lon"], natal[pt]["lon"]) <= thresh:
            return True
    return False

# Map corpus sector labels to compendium sector labels where they differ
SECTOR_MAP = {
    "TECH":"TECH","BIOPHARM":"BIOPHARM","ENERGY":"ENERGY","EV":"EV",
    "FINANCE":"FINANCE","MEME":"MEME","CRYPTO":"CRYPTO","CANNABIS":"CANNABIS",
    "RETAIL":"RETAIL","METALS":"METALS","MEDIA":"MEDIA",
}

def tier_rulers(sector, tiers):
    return sorted(set(p for p, t, s in SECTOR_RULERSHIP.get(sector, []) if t in tiers))

def main():
    cases = []
    for tk, ipo, bot, top, mult, speed, note in PARABOLIC_BOTTOMS:
        sec = SECTOR_MAP.get(CORPUS_SECTOR.get(tk, "UNK"))
        if not sec: continue
        try:
            natal = compute_natal(ipo)
            cases.append({"tk":tk,"sec":sec,"mult":mult,
                          "natal":natal,
                          "t_bot":transits_at(bot[0],bot[1]),
                          "t_peak":transits_at(top[0],top[1])})
        except: continue
    print(f"Cases with mapped sector: {len(cases)}")

    # Per-case all-planet baseline: fraction of the 10 planets <=5° at bottom
    base_rates = []
    for c in cases:
        hits = sum(1 for p in ALL_10 if planet_hit(c["natal"], c["t_bot"], p))
        base_rates.append(hits / len(ALL_10))
    baseline = 100 * st.mean(base_rates)
    print(f"All-planet baseline hit-rate at bottoms: {baseline:.1f}% per planet\n")

    print(f"{'='*120}")
    print(f"PROVENANCE-TIER TEST — sector-ruler hit-rate at BOTTOM (<=5° any hard aspect to Sun/Moon/ASC/MC)")
    print(f"  Hit = at least one tier-ruler active. Expected-by-chance rises with # rulers; shown for context.")
    print(f"{'='*120}")
    print(f"{'Sector':<10s} {'n':>3s} | {'CLASSICAL':>22s} | {'MODERN':>22s} | {'EITHER':>22s}")
    agg = {"classical": [], "modern": [], "either": []}
    for sec in sorted(set(c["sec"] for c in cases)):
        sub = [c for c in cases if c["sec"] == sec]
        if len(sub) < 5: continue
        row = {}
        for label, tiers in [("classical",("classical",)),
                              ("modern",("modern",)),
                              ("either",("classical","modern"))]:
            rulers = tier_rulers(sec, tiers)
            if not rulers:
                row[label] = (None, 0, [])
                continue
            hits = sum(1 for c in sub
                       if any(planet_hit(c["natal"], c["t_bot"], p) for p in rulers))
            rate = 100*hits/len(sub)
            # chance of >=1 of k planets hitting, if each ~baseline%
            k = len(rulers)
            expected = 100*(1 - (1 - baseline/100)**k)
            row[label] = (rate, expected, rulers)
            agg[label].append(rate - expected)
        def fmt(v):
            rate, exp, rl = v
            if rate is None: return f"{'—':>22s}"
            return f"{rate:5.0f}% (exp {exp:3.0f}%, k={len(rl)})"
        print(f"{sec:<10s} {len(sub):>3d} | {fmt(row['classical']):>22s} | {fmt(row['modern']):>22s} | {fmt(row['either']):>22s}")

    print(f"\nAGGREGATE lift over chance-expected (mean across sectors):")
    for label in ("classical","modern","either"):
        if agg[label]:
            print(f"  {label:<10s} {st.mean(agg[label]):+.1f}pp  (n={len(agg[label])} sectors)")

    # Same at PEAK
    print(f"\n{'='*120}")
    print(f"SAME TEST AT PEAK")
    print(f"{'='*120}")
    base_rates_pk = []
    for c in cases:
        hits = sum(1 for p in ALL_10 if planet_hit(c["natal"], c["t_peak"], p))
        base_rates_pk.append(hits / len(ALL_10))
    baseline_pk = 100 * st.mean(base_rates_pk)
    print(f"All-planet baseline at peaks: {baseline_pk:.1f}%")
    agg_pk = {"classical": [], "modern": [], "either": []}
    for sec in sorted(set(c["sec"] for c in cases)):
        sub = [c for c in cases if c["sec"] == sec]
        if len(sub) < 5: continue
        for label, tiers in [("classical",("classical",)),
                              ("modern",("modern",)),
                              ("either",("classical","modern"))]:
            rulers = tier_rulers(sec, tiers)
            if not rulers: continue
            hits = sum(1 for c in sub
                       if any(planet_hit(c["natal"], c["t_peak"], p) for p in rulers))
            rate = 100*hits/len(sub)
            k = len(rulers)
            expected = 100*(1 - (1 - baseline_pk/100)**k)
            agg_pk[label].append(rate - expected)
    for label in ("classical","modern","either"):
        if agg_pk[label]:
            print(f"  {label:<10s} {st.mean(agg_pk[label]):+.1f}pp  (n={len(agg_pk[label])} sectors)")

    # Contested-sign dual-ruler check: for cases whose natal SUN sign is
    # Scorpio/Aquarius/Pisces, does the trad or modern sign-ruler transit
    # activate at bottom more often?
    print(f"\n{'='*120}")
    print(f"CONTESTED-SIGN DUAL-RULER CHECK — natal Sun in Scorpio/Aquarius/Pisces")
    print(f"  Which domicile ruler (traditional vs modern) transits <=5° of natal points at BOTTOM?")
    print(f"{'='*120}")
    from rulership_compendium import SIGN_RULERS
    counts = defaultdict(lambda: {"n":0,"trad":0,"mod":0,"either":0})
    for c in cases:
        sun_sign = int(c["natal"]["Sun"]["lon"] // 30)
        if sun_sign not in (7, 10, 11): continue
        trad, mod = SIGN_RULERS[sun_sign]
        rec = counts[sun_sign]
        rec["n"] += 1
        t_hit = planet_hit(c["natal"], c["t_bot"], trad)
        m_hit = planet_hit(c["natal"], c["t_bot"], mod)
        if t_hit: rec["trad"] += 1
        if m_hit: rec["mod"] += 1
        if t_hit or m_hit: rec["either"] += 1
    names = {7:"Scorpio",10:"Aquarius",11:"Pisces"}
    for s, rec in sorted(counts.items()):
        if rec["n"] == 0: continue
        trad, mod = SIGN_RULERS[s]
        print(f"  {names[s]:<10s} n={rec['n']:>2d}  {trad}(trad): {100*rec['trad']/rec['n']:3.0f}%  "
              f"{mod}(mod): {100*rec['mod']/rec['n']:3.0f}%  either: {100*rec['either']/rec['n']:3.0f}%  "
              f"(baseline/planet ~{baseline:.0f}%)")

if __name__ == "__main__":
    main()
