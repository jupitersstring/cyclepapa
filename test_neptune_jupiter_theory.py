"""
Test the Neptune-alone-vs-Neptune-plus-Jupiter theory on 152-case corpus.

Theory claims:
  1. Neptune active + Jupiter ABSENT at bottom = THE BOTTOM (pure dissolution)
  2. Jupiter arriving at natal Neptune after bottom = IGNITION
  3. Both active simultaneously = PARABOLIC
  4. Saturn arriving at activated degree = reality check

Tests:
  A) Split corpus into 4 quadrants (Nep-close/far × Jup-close/far at bottom).
     Is "Nep-close + Jup-far" the highest-rally quadrant? (the claim)
  B) After the bottom, how long until transit Jupiter reaches natal Neptune?
     Does rally magnitude correlate with this timing?
  C) Does rally actually peak around the Jupiter-to-natal-Neptune event?
"""
import math, statistics as st
from collections import defaultdict
import swisseph as swe
from bti_test import compute_natal, transits_at, jd_of
from bti_v4 import yx
from parabolic_corpus import PARABOLIC_BOTTOMS

def orb(a, b):
    d = abs((a - b) % 360)
    return min(d, 360 - d)

def closest_hard(a, b, max_orb=30):
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

            # Neptune: closest hard aspect to natal Sun/Moon/ASC/MC/Neptune
            nep_min = 99
            for tgt_name in ("Sun","Moon","ASC","MC","Neptune"):
                if tgt_name not in natal: continue
                o = closest_hard(trans["Neptune"]["lon"], natal[tgt_name]["lon"])
                if o < nep_min: nep_min = o
            # Jupiter: closest hard aspect to natal Sun/Moon/ASC/MC/Neptune
            jup_min_natal = 99
            for tgt_name in ("Sun","Moon","ASC","MC","Neptune"):
                if tgt_name not in natal: continue
                o = closest_hard(trans["Jupiter"]["lon"], natal[tgt_name]["lon"])
                if o < jup_min_natal: jup_min_natal = o
            # Jupiter to NATAL Neptune specifically
            jup_to_nat_nep = closest_hard(trans["Jupiter"]["lon"], natal["Neptune"]["lon"])

            # Find months from bottom until transit Jupiter reaches natal Neptune (hard orb <=3)
            months_to_jup_natNep = None
            for k in range(0, 24):
                y, m = yx(bot[0], bot[1], k)
                jd = jd_of(y, m, 15, 12.0)
                jup_lon = swe.calc_ut(jd, swe.JUPITER)[0][0] % 360
                if closest_hard(jup_lon, natal["Neptune"]["lon"]) <= 3:
                    months_to_jup_natNep = k; break

            # Months until Saturn reaches natal Neptune
            months_to_sat_natNep = None
            for k in range(0, 36):
                y, m = yx(bot[0], bot[1], k)
                jd = jd_of(y, m, 15, 12.0)
                sat_lon = swe.calc_ut(jd, swe.SATURN)[0][0] % 360
                if closest_hard(sat_lon, natal["Neptune"]["lon"]) <= 3:
                    months_to_sat_natNep = k; break

            data.append({
                "ticker": tk, "mult": mult, "log_mult": math.log(mult),
                "nep_min": nep_min, "jup_min_natal": jup_min_natal,
                "jup_to_nat_nep": jup_to_nat_nep,
                "months_to_jup_natNep": months_to_jup_natNep,
                "months_to_sat_natNep": months_to_sat_natNep,
            })
        except: pass

    print(f"n={len(data)}")

    # =====================================================
    # TEST A: Four-quadrant analysis
    # =====================================================
    print(f"\n{'='*100}")
    print(f"TEST A: 4-QUADRANT Neptune-close × Jupiter-close at bottom")
    print(f"{'='*100}")
    # Thresholds: "close" = <=4°, "far" = >=6° (corpus median Jup-close = ~5°)
    quadrants = defaultdict(list)
    for d in data:
        np_close = d["nep_min"] <= 4
        jp_close = d["jup_min_natal"] <= 4
        q = ("NepClose" if np_close else "NepFar", "JupClose" if jp_close else "JupFar")
        quadrants[q].append(d)
    print(f"  {'Quadrant':<30s} {'n':>3s} {'MeanMult':>8s} {'MedMult':>8s} {'Max':>5s} {'%≥10×':>6s} {'%≥30×':>6s}")
    for q, ds in sorted(quadrants.items()):
        mults = [d["mult"] for d in ds]
        label = f"{q[0]} + {q[1]}"
        if ds:
            pct10 = 100*sum(1 for m in mults if m>=10)/len(mults)
            pct30 = 100*sum(1 for m in mults if m>=30)/len(mults)
            print(f"  {label:<30s} {len(ds):>3d} {st.mean(mults):8.1f}× {st.median(mults):8.1f}× {max(mults):>4.0f}× {pct10:>5.0f}% {pct30:>5.0f}%")

    # =====================================================
    # TEST B: Does months-to-Jupiter-on-natal-Neptune correlate with rally?
    # =====================================================
    print(f"\n{'='*100}")
    print(f"TEST B: Correlation of 'months until Jupiter reaches natal Neptune' with rally")
    print(f"{'='*100}")
    have_data = [d for d in data if d["months_to_jup_natNep"] is not None]
    if have_data:
        mts = [d["months_to_jup_natNep"] for d in have_data]
        lm = [d["log_mult"] for d in have_data]
        mx, my = st.mean(mts), st.mean(lm)
        num = sum((x-mx)*(y-my) for x,y in zip(mts,lm))
        denx = math.sqrt(sum((x-mx)**2 for x in mts))
        deny = math.sqrt(sum((y-my)**2 for y in lm))
        r = num/(denx*deny) if denx*deny else 0
        print(f"  n={len(have_data)}  Pearson r (months→Jup, log_mult) = {r:+.3f}")
    # Bucket:
    buckets = defaultdict(list)
    for d in data:
        mts = d["months_to_jup_natNep"]
        if mts is None: b = "NEVER"
        elif mts <= 3: b = "0-3mo"
        elif mts <= 6: b = "4-6mo"
        elif mts <= 12: b = "7-12mo"
        else: b = "13-24mo"
        buckets[b].append(d["mult"])
    print(f"\n  Months until Jupiter reaches natal Neptune → mean subsequent rally:")
    for b in ("0-3mo","4-6mo","7-12mo","13-24mo","NEVER"):
        if b in buckets:
            m = buckets[b]
            print(f"    {b:<10s} n={len(m):>3d}  mean={st.mean(m):6.1f}×  median={st.median(m):6.1f}×  max={max(m):>4.0f}×  %≥10×={100*sum(1 for x in m if x>=10)/len(m):.0f}%")

    # =====================================================
    # TEST C: Jupiter AT natal Neptune at bottom — what happens?
    # =====================================================
    print(f"\n{'='*100}")
    print(f"TEST C: Jupiter-at-natal-Neptune distance AT the bottom (claim: far = bigger rally)")
    print(f"{'='*100}")
    orb_buckets = defaultdict(list)
    for d in data:
        o = d["jup_to_nat_nep"]
        if o <= 3: b = "A_close_0-3°"
        elif o <= 8: b = "B_moderate_3-8°"
        elif o <= 20: b = "C_far_8-20°"
        else: b = "D_veryfar_20°+"
        orb_buckets[b].append(d["mult"])
    print(f"  Jupiter-to-natal-Neptune orb bucket at bottom → subsequent rally:")
    for b in sorted(orb_buckets.keys()):
        m = orb_buckets[b]
        print(f"    {b:<16s} n={len(m):>3d}  mean={st.mean(m):6.1f}×  median={st.median(m):6.1f}×  max={max(m):>4.0f}×  %≥10×={100*sum(1 for x in m if x>=10)/len(m):.0f}%")

    # =====================================================
    # TEST D: Neptune active + Jupiter FAR at bottom — highest-mult pattern?
    # =====================================================
    print(f"\n{'='*100}")
    print(f"TEST D: KEY — Neptune active (≤4°) AND Jupiter far from natal Neptune (≥12°)")
    print(f"(this is the 'pure dissolution bottom' archetype per user's theory)")
    print(f"{'='*100}")
    pure_dissolution = [d for d in data if d["nep_min"] <= 4 and d["jup_to_nat_nep"] >= 12]
    nep_only = [d for d in data if d["nep_min"] <= 4 and d["jup_min_natal"] >= 6]
    both = [d for d in data if d["nep_min"] <= 4 and d["jup_min_natal"] <= 4]
    neither = [d for d in data if d["nep_min"] > 4 and d["jup_min_natal"] > 4]
    for name, group in [
        ("PURE DISSOLUTION (Nep≤4, JupNatNep≥12)", pure_dissolution),
        ("Nep active + Jup-any-natal far (≥6)", nep_only),
        ("BOTH active (Nep≤4 + Jup≤4)", both),
        ("NEITHER active", neither),
    ]:
        if group:
            m = [d["mult"] for d in group]
            print(f"  {name:<45s}  n={len(group):>3d}  mean={st.mean(m):6.1f}×  median={st.median(m):6.1f}×  %≥10×={100*sum(1 for x in m if x>=10)/len(m):.0f}%  %≥30×={100*sum(1 for x in m if x>=30)/len(m):.0f}%")
    print(f"  Overall corpus mean: {st.mean([d['mult'] for d in data]):.1f}×")

    # =====================================================
    # TEST E: Saturn timing — when Saturn arrives at natal Nep
    # =====================================================
    print(f"\n{'='*100}")
    print(f"TEST E: Saturn reaching natal Neptune — timing relative to bottom")
    print(f"{'='*100}")
    sat_buckets = defaultdict(list)
    for d in data:
        mts = d["months_to_sat_natNep"]
        if mts is None: b = "NEVER"
        elif mts <= 6: b = "0-6mo (too soon — may pop)"
        elif mts <= 12: b = "7-12mo"
        elif mts <= 24: b = "13-24mo"
        else: b = "25-36mo"
        sat_buckets[b].append(d["mult"])
    print(f"  Months until Saturn reaches natal Neptune → rally:")
    for b in sorted(sat_buckets.keys()):
        m = sat_buckets[b]
        print(f"    {b:<30s} n={len(m):>3d}  mean={st.mean(m):6.1f}×  median={st.median(m):6.1f}×  %≥10×={100*sum(1 for x in m if x>=10)/len(m):.0f}%")

    # =====================================================
    # TEST F: The full chain — Nep-active + Jupiter-coming-3-12mo + Saturn-not-for-24+mo
    # =====================================================
    print(f"\n{'='*100}")
    print(f"TEST F: FULL CHAIN — Neptune active at bottom + Jupiter arriving 3-12mo + Saturn ≥24mo away")
    print(f"{'='*100}")
    chain = [d for d in data
             if d["nep_min"] <= 4
             and d["months_to_jup_natNep"] is not None
             and 3 <= d["months_to_jup_natNep"] <= 12
             and (d["months_to_sat_natNep"] is None or d["months_to_sat_natNep"] >= 24)]
    if chain:
        m = [d["mult"] for d in chain]
        print(f"  FULL CHAIN  n={len(chain)}  mean={st.mean(m):.1f}×  median={st.median(m):.1f}×  %≥10×={100*sum(1 for x in m if x>=10)/len(m):.0f}%")
        print(f"  Cases: {', '.join(sorted([d['ticker'] for d in chain]))}")
    else:
        print(f"  No matches")

if __name__ == "__main__":
    main()
