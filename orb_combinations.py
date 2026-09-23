"""
Systematic orb combination analysis on 152-case corpus.

Questions:
  1. What is the OPTIMAL orb for each outer planet vs log(rally)?
     Not just tightest — does moderate or wide beat exact?
  2. What are the best TWO-PLANET combinations?
     e.g. Pluto close + Neptune far, Jupiter close + Saturn far
  3. Combinations must make astrological sense:
     - Transformation without dissolution-noise (Plu close + Nep far)
     - Expansion without constraint (Jup close + Sat far)
     - Fantasy without reality check (Nep close + Sat far)
     - Cult without fantasy-fog (Plu close + Nep far)
     - Revolution + transformation (Ura close + Plu close)

Test each as: mean rally, median rally, %≥25×, %≥100× vs baseline.
Corpus baseline: n=152, mean mult ~86×, median ~12×.
"""
import math, statistics as st
from collections import defaultdict
from bti_test import compute_natal, transits_at
from parabolic_corpus import PARABOLIC_BOTTOMS

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

def main():
    data = []
    for tk, ipo, bot, top, mult, speed, note in PARABOLIC_BOTTOMS:
        try:
            natal = compute_natal(ipo)
            trans = transits_at(bot[0], bot[1])
            # Closest hard orb of each transit outer to any natal sensitive
            # (Sun, Moon, ASC, MC, Neptune, Sun being primary)
            sensitive = {}
            for p in ("Sun","Moon","ASC","MC"):
                if p in natal: sensitive[p] = natal[p]["lon"]
            # Compute outer-to-natal-sensitive closest
            orbs = {}
            for outer in ("Jupiter","Saturn","Uranus","Neptune","Pluto"):
                best = 99
                for tgt_lon in sensitive.values():
                    o = closest_hard(trans[outer]["lon"], tgt_lon)
                    if o < best: best = o
                orbs[outer] = best
            data.append({"tk": tk, "mult": mult, "log_mult": math.log(mult), **orbs})
        except: pass

    print(f"n={len(data)}   baseline mean_mult={st.mean([d['mult'] for d in data]):.1f}×  median={st.median([d['mult'] for d in data]):.1f}×")

    BASELINE_MEDIAN = st.median([d['mult'] for d in data])
    BASELINE_MEAN = st.mean([d['mult'] for d in data])
    BASELINE_PCT25 = 100*sum(1 for d in data if d['mult']>=25)/len(data)
    BASELINE_PCT100 = 100*sum(1 for d in data if d['mult']>=100)/len(data)
    print(f"Baseline: mean={BASELINE_MEAN:.1f}×  med={BASELINE_MEDIAN:.1f}×  %≥25×={BASELINE_PCT25:.0f}%  %≥100×={BASELINE_PCT100:.0f}%\n")

    def summary(subset, label):
        if not subset: return
        mults = [d["mult"] for d in subset]
        mean = st.mean(mults)
        med = st.median(mults)
        p25 = 100*sum(1 for m in mults if m>=25)/len(subset)
        p100 = 100*sum(1 for m in mults if m>=100)/len(subset)
        mean_x = mean / BASELINE_MEAN
        med_x = med / BASELINE_MEDIAN
        p25_x = p25 / BASELINE_PCT25 if BASELINE_PCT25>0 else 0
        p100_x = p100 / BASELINE_PCT100 if BASELINE_PCT100>0 else 0
        return {"label": label, "n": len(subset), "mean": mean, "med": med, "p25": p25, "p100": p100,
                "mean_x": mean_x, "med_x": med_x, "p25_x": p25_x, "p100_x": p100_x}

    # =====================================================
    # PART 1: single-planet optimal orb bucket
    # =====================================================
    print(f"{'='*100}")
    print(f"PART 1: SINGLE PLANET — optimal orb bucket")
    print(f"{'='*100}")
    for outer in ("Jupiter","Saturn","Uranus","Neptune","Pluto"):
        print(f"\n  {outer}:")
        print(f"    {'Bucket':<10s} {'n':>3s} {'mean':>8s} {'med':>6s} {'%≥25×':>6s} {'%≥100×':>7s} {'mn/base':>8s} {'med/base':>8s}")
        for lo, hi in [(0,3),(3,5),(5,8),(8,12),(12,20),(20,99)]:
            subset = [d for d in data if lo <= d[outer] < hi]
            r = summary(subset, f"{outer} {lo}-{hi}°")
            if r:
                print(f"    {lo}-{hi}°    {r['n']:>3d} {r['mean']:8.1f}× {r['med']:6.1f}× {r['p25']:5.0f}% {r['p100']:6.0f}% {r['mean_x']:7.2f} {r['med_x']:7.2f}")

    # =====================================================
    # PART 2: two-planet combinations
    # =====================================================
    print(f"\n{'='*100}")
    print(f"PART 2: TWO-PLANET COMBINATIONS — rank by median-rally uplift")
    print(f"{'='*100}")
    ORB_BUCKETS = [
        ("close", 0, 3),
        ("mod", 3, 8),
        ("far", 8, 20),
        ("veryfar", 20, 99),
    ]
    combos = []
    outers = ["Jupiter","Saturn","Uranus","Neptune","Pluto"]
    for i, o1 in enumerate(outers):
        for o2 in outers[i+1:]:
            for n1, l1, h1 in ORB_BUCKETS:
                for n2, l2, h2 in ORB_BUCKETS:
                    subset = [d for d in data if l1 <= d[o1] < h1 and l2 <= d[o2] < h2]
                    if len(subset) < 5: continue
                    r = summary(subset, f"{o1}-{n1} + {o2}-{n2}")
                    if r:
                        combos.append(r)
    # Rank by median_uplift × p25_uplift (balanced)
    combos.sort(key=lambda c: -(c["med_x"] * c["p25_x"] * math.log(c["n"]+1)))
    print(f"\n  TOP 25 by median×%≥25× × log(n) composite:")
    print(f"    {'Label':<30s} {'n':>3s} {'mean':>8s} {'med':>6s} {'%≥25×':>6s} {'%≥100×':>7s} {'mn/base':>8s} {'med/base':>8s} {'p25/base':>8s}")
    for r in combos[:25]:
        print(f"    {r['label']:<30s} {r['n']:>3d} {r['mean']:8.1f}× {r['med']:6.1f}× {r['p25']:5.0f}% {r['p100']:6.0f}% {r['mean_x']:7.2f} {r['med_x']:7.2f} {r['p25_x']:7.2f}")

    # =====================================================
    # PART 3: astrologically-motivated specific combos
    # =====================================================
    print(f"\n{'='*100}")
    print(f"PART 3: ASTROLOGICALLY-MEANINGFUL COMBINATIONS")
    print(f"{'='*100}")
    specific = [
        ("Cult without dissolution (Plu close + Nep far)",
         lambda d: d["Pluto"] <= 3 and d["Neptune"] >= 12),
        ("Cult + mythology (Plu close + Nep close)",
         lambda d: d["Pluto"] <= 3 and d["Neptune"] <= 3),
        ("Cult + expansion (Plu close + Jup close)",
         lambda d: d["Pluto"] <= 3 and d["Jupiter"] <= 3),
        ("Cult w/o constraint (Plu close + Sat far)",
         lambda d: d["Pluto"] <= 3 and d["Saturn"] >= 12),
        ("Revolutionary rebirth (Plu close + Ura close)",
         lambda d: d["Pluto"] <= 3 and d["Uranus"] <= 3),
        ("Fantasy inflation (Nep close + Jup close)",
         lambda d: d["Neptune"] <= 3 and d["Jupiter"] <= 3),
        ("Unchecked fantasy (Nep close + Sat far)",
         lambda d: d["Neptune"] <= 3 and d["Saturn"] >= 12),
        ("Pure fantasy (Nep close + Jup far + Sat far)",
         lambda d: d["Neptune"] <= 3 and d["Jupiter"] >= 8 and d["Saturn"] >= 8),
        ("Expansion unchecked (Jup close + Sat far)",
         lambda d: d["Jupiter"] <= 3 and d["Saturn"] >= 12),
        ("Electric novelty (Ura close + Jup close)",
         lambda d: d["Uranus"] <= 3 and d["Jupiter"] <= 3),
        ("Shock transformation (Ura close + Plu close)",
         lambda d: d["Uranus"] <= 3 and d["Pluto"] <= 3),
        ("Saturn absent (all non-Sat outers active)",
         lambda d: d["Saturn"] >= 12 and min(d["Jupiter"], d["Uranus"], d["Neptune"], d["Pluto"]) <= 3),
        ("MULTI-OUTER ACTIVATION (3+ close)",
         lambda d: sum(1 for o in ("Jupiter","Saturn","Uranus","Neptune","Pluto") if d[o] <= 3) >= 3),
        ("MULTI-OUTER MODERATE (3+ within 5°)",
         lambda d: sum(1 for o in ("Jupiter","Saturn","Uranus","Neptune","Pluto") if d[o] <= 5) >= 3),
        ("SPARSE (<=1 within 5°)",
         lambda d: sum(1 for o in ("Jupiter","Saturn","Uranus","Neptune","Pluto") if d[o] <= 5) <= 1),
        ("SLOW OUTERS absent (Plu>12 + Nep>12)",
         lambda d: d["Pluto"] >= 12 and d["Neptune"] >= 12),
    ]
    print(f"\n    {'Rule':<55s} {'n':>3s} {'mean':>8s} {'med':>6s} {'%≥25×':>6s} {'%≥100×':>7s} {'mn/base':>8s} {'med/base':>8s}")
    results_s = []
    for label, fn in specific:
        subset = [d for d in data if fn(d)]
        r = summary(subset, label)
        if r:
            results_s.append(r)
            print(f"    {label:<55s} {r['n']:>3d} {r['mean']:8.1f}× {r['med']:6.1f}× {r['p25']:5.0f}% {r['p100']:6.0f}% {r['mean_x']:7.2f} {r['med_x']:7.2f}")

    # =====================================================
    # PART 4: the real winners — rank specific rules
    # =====================================================
    print(f"\n{'='*100}")
    print(f"PART 4: BEST RULES (n>=6, median uplift>1.2x AND %≥25×>=1.3x baseline)")
    print(f"{'='*100}")
    winners = [r for r in combos + results_s if r["n"] >= 6 and r["med_x"] >= 1.2 and r["p25_x"] >= 1.3]
    winners.sort(key=lambda c: -(c["med_x"] * c["p25_x"]))
    print(f"    {'Rule':<50s} {'n':>3s} {'mean':>8s} {'med':>6s} {'%≥25×':>6s} {'med/base':>8s} {'p25/base':>8s}")
    for r in winners[:20]:
        print(f"    {r['label']:<50s} {r['n']:>3d} {r['mean']:8.1f}× {r['med']:6.1f}× {r['p25']:5.0f}% {r['med_x']:7.2f} {r['p25_x']:7.2f}")

if __name__ == "__main__":
    main()
