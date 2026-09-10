"""
Test the other-chat fame-signature claims + search for MAGNITUDE predictors.

Claims to validate on 152-corpus:
  Pluto MC ≤3° at bottom         = 249.3× avg, 36% ≥25×
  Jup≤3° + Nep≤5° (inflated myth) = 211.0× avg, 38% ≥25×
  Plu≤3° + Nep≤3° (cult + myth)   = 497.1× avg, 30% ≥25×
  Jup≤3° + Sat>8° (fame unchecked)= 184.7× avg, 27% ≥25×
  Jup angular ≤3° (rising fame)   = 144.9× avg, 32% ≥25×

And test natal features as MAGNITUDE predictors:
  Natal Pluto-MC orb (the claim: natal DNA sets capacity)
  Natal Sun-MC orb, Sun-ASC orb (angular Sun = fame capacity)
  Royal Star natal contacts (Regulus/Spica/Antares/Aldebaran)
  Chart age at bottom
  Lot of Exaltation position
"""
import math, statistics as st
from collections import defaultdict
import swisseph as swe
from bti_test import compute_natal, transits_at, jd_of
from bti_v4 import yx
from classical_extensions import FIXED_STARS
from parabolic_corpus import PARABOLIC_BOTTOMS

def orb(a, b):
    d = abs((a - b) % 360)
    return min(d, 360 - d)

def closest_hard(a, b, aspects=(0,90,180), max_orb=30):
    best = (None, 99)
    for asp in aspects:
        for sign in (+1, -1):
            o = orb(a, b + sign*asp)
            if o < best[1]: best = (asp, o)
    return best

def angular_orb(trans_lon, natal):
    """Closest hard aspect of transit planet to any natal angle (ASC or MC)."""
    best = 99
    for ang in ("ASC","MC"):
        if ang not in natal: continue
        _, o = closest_hard(trans_lon, natal[ang]["lon"])
        if o < best: best = o
    return best

def main():
    data = []
    for tk, ipo, bot, top, mult, speed, note in PARABOLIC_BOTTOMS:
        try:
            natal = compute_natal(ipo)
            trans = transits_at(bot[0], bot[1])

            # Transit Pluto to natal MC
            plu_mc = closest_hard(trans["Pluto"]["lon"], natal["MC"]["lon"])[1] if "MC" in natal else 99
            # Transit Jupiter to any natal angle (angular = ASC or MC)
            jup_ang = angular_orb(trans["Jupiter"]["lon"], natal)
            # Transit Neptune to natal Sun
            nep_sun = closest_hard(trans["Neptune"]["lon"], natal["Sun"]["lon"])[1]
            # Transit Saturn to natal Sun
            sat_sun = closest_hard(trans["Saturn"]["lon"], natal["Sun"]["lon"])[1]
            # Transit Pluto to natal Sun
            plu_sun = closest_hard(trans["Pluto"]["lon"], natal["Sun"]["lon"])[1]
            # Transit Jupiter to natal Sun
            jup_sun = closest_hard(trans["Jupiter"]["lon"], natal["Sun"]["lon"])[1]

            # NATAL features (for magnitude prediction)
            # Natal Pluto to MC
            nat_plu_mc = closest_hard(natal["Pluto"]["lon"], natal["MC"]["lon"])[1] if "MC" in natal else 99
            # Natal Sun angular
            nat_sun_mc = closest_hard(natal["Sun"]["lon"], natal["MC"]["lon"])[1] if "MC" in natal else 99
            nat_sun_asc = closest_hard(natal["Sun"]["lon"], natal["ASC"]["lon"])[1] if "ASC" in natal else 99
            nat_sun_ang = min(nat_sun_mc, nat_sun_asc)

            # Royal Star contacts to natal Sun/MC/ASC
            ROYAL = {"Regulus":0.30,"Spica":204.28,"Antares":250.00,"Aldebaran":70.15}
            royal_contact = 99
            for star, slon in ROYAL.items():
                for body in ("Sun","MC","ASC","Jupiter"):
                    if body not in natal: continue
                    o = orb(natal[body]["lon"], slon)
                    if o < royal_contact: royal_contact = o

            # Natal Jupiter-Neptune orb
            nat_jn = closest_hard(natal["Jupiter"]["lon"], natal["Neptune"]["lon"])[1]

            # Chart age at bottom
            age = bot[0] - int(ipo[:4])

            data.append({
                "ticker": tk, "mult": mult, "log_mult": math.log(mult),
                "plu_mc": plu_mc, "jup_ang": jup_ang, "nep_sun": nep_sun,
                "sat_sun": sat_sun, "plu_sun": plu_sun, "jup_sun": jup_sun,
                "nat_plu_mc": nat_plu_mc, "nat_sun_ang": nat_sun_ang,
                "royal_contact": royal_contact, "nat_jn": nat_jn,
                "age": age,
            })
        except: pass

    print(f"n={len(data)}")

    # =====================================================
    # TEST each claimed rule
    # =====================================================
    print(f"\n{'='*100}")
    print(f"TESTING OTHER-CHAT FAME-SIGNATURE CLAIMS on 152-corpus")
    print(f"{'='*100}")
    print(f"{'Rule':<35s} {'n':>3s} {'MeanMult':>9s} {'MedMult':>8s} {'%≥25×':>7s} {'Claim'}")

    tests = [
        ("Pluto-MC ≤3° at bot",
         lambda d: d["plu_mc"] <= 3,
         "249.3× / 36% ≥25×"),
        ("Jup≤3° + Nep≤5° (inflated myth)",
         lambda d: d["jup_sun"] <= 3 and d["nep_sun"] <= 5,
         "211× / 38% ≥25×"),
        ("Plu≤3° + Nep≤3° (cult+myth)",
         lambda d: d["plu_sun"] <= 3 and d["nep_sun"] <= 3,
         "497× / 30% ≥25×"),
        ("Jup≤3° + Sat>8° (fame unchecked)",
         lambda d: d["jup_sun"] <= 3 and d["sat_sun"] > 8,
         "184.7× / 27% ≥25×"),
        ("Jup angular ≤3° (rising fame)",
         lambda d: d["jup_ang"] <= 3,
         "144.9× / 32% ≥25×"),
    ]
    for label, fn, claim in tests:
        subset = [d for d in data if fn(d)]
        if not subset:
            print(f"  {label:<35s} {0:>3d}  N/A       N/A      N/A     [{claim}]")
            continue
        mults = [d["mult"] for d in subset]
        mean_m = st.mean(mults)
        med_m = st.median(mults)
        pct25 = 100 * sum(1 for m in mults if m >= 25) / len(subset)
        marker = " ⚠" if mean_m < 80 else (" ≈" if abs(mean_m - float(claim.split("×")[0])) < 100 else "")
        print(f"  {label:<35s} {len(subset):>3d}  {mean_m:8.1f}× {med_m:8.1f}× {pct25:6.0f}%  [{claim}]{marker}")

    # =====================================================
    # Independent Pluto-MC analysis at DIFFERENT orbs
    # =====================================================
    print(f"\n{'='*100}")
    print(f"PLUTO-to-NATAL-MC orb buckets")
    print(f"{'='*100}")
    for lo, hi in [(0,3),(3,5),(5,10),(10,20),(20,99)]:
        subset = [d for d in data if lo <= d["plu_mc"] < hi]
        if not subset: continue
        mults = [d["mult"] for d in subset]
        p25 = 100*sum(1 for m in mults if m>=25)/len(subset)
        p10 = 100*sum(1 for m in mults if m>=10)/len(subset)
        print(f"  {lo}-{hi}°:  n={len(subset):>3d}  mean={st.mean(mults):6.1f}×  med={st.median(mults):6.1f}×  %≥10×={p10:.0f}%  %≥25×={p25:.0f}%")

    # =====================================================
    # MAGNITUDE PREDICTION: natal features
    # =====================================================
    print(f"\n{'='*100}")
    print(f"MAGNITUDE PREDICTORS — natal features correlation with log(mult)")
    print(f"{'='*100}")
    def corr(xs, ys):
        if len(xs)<3: return 0
        mx,my = st.mean(xs), st.mean(ys)
        num = sum((x-mx)*(y-my) for x,y in zip(xs,ys))
        dx = math.sqrt(sum((x-mx)**2 for x in xs))
        dy = math.sqrt(sum((y-my)**2 for y in ys))
        return num/(dx*dy) if dx*dy else 0

    log_mult = [d["log_mult"] for d in data]
    feats = [
        ("nat Pluto-MC orb", "nat_plu_mc"),
        ("nat Sun-angular orb", "nat_sun_ang"),
        ("natal Royal Star contact", "royal_contact"),
        ("natal JN orb", "nat_jn"),
        ("chart age at bottom", "age"),
    ]
    for label, key in feats:
        xs = [d[key] for d in data]
        r = corr(xs, log_mult)
        direction = "CLOSE=bigger" if r < 0 else "CLOSE=smaller"
        print(f"  {label:<30s} r={r:+.3f}  {direction}")

    # =====================================================
    # Bucket natal Pluto-MC by orb and compare rallies
    # =====================================================
    print(f"\n{'='*100}")
    print(f"NATAL PLUTO-MC orb buckets (capacity for cult-fame per other chat's claim)")
    print(f"{'='*100}")
    for lo, hi in [(0,3),(3,8),(8,20),(20,40),(40,99)]:
        subset = [d for d in data if lo <= d["nat_plu_mc"] < hi]
        if not subset: continue
        mults = [d["mult"] for d in subset]
        print(f"  nat_plu_mc {lo}-{hi}°:  n={len(subset):>3d}  mean={st.mean(mults):6.1f}×  med={st.median(mults):6.1f}×  %≥25×={100*sum(1 for m in mults if m>=25)/len(subset):.0f}%  %≥100×={100*sum(1 for m in mults if m>=100)/len(subset):.0f}%")

    # Natal Sun angular
    print(f"\n  natal Sun angular orb:")
    for lo, hi in [(0,3),(3,8),(8,20),(20,99)]:
        subset = [d for d in data if lo <= d["nat_sun_ang"] < hi]
        if not subset: continue
        mults = [d["mult"] for d in subset]
        print(f"  nat_sun_ang {lo}-{hi}°: n={len(subset):>3d}  mean={st.mean(mults):6.1f}×  med={st.median(mults):6.1f}×  %≥25×={100*sum(1 for m in mults if m>=25)/len(subset):.0f}%  %≥100×={100*sum(1 for m in mults if m>=100)/len(subset):.0f}%")

    # Natal Royal Star
    print(f"\n  natal Royal Star contact (Sun/MC/ASC/Jup on Reg/Spic/Ant/Ald):")
    for lo, hi in [(0,1),(1,3),(3,8),(8,99)]:
        subset = [d for d in data if lo <= d["royal_contact"] < hi]
        if not subset: continue
        mults = [d["mult"] for d in subset]
        print(f"  royal {lo}-{hi}°: n={len(subset):>3d}  mean={st.mean(mults):6.1f}×  med={st.median(mults):6.1f}×  %≥25×={100*sum(1 for m in mults if m>=25)/len(subset):.0f}%  %≥100×={100*sum(1 for m in mults if m>=100)/len(subset):.0f}%")

    # =====================================================
    # Compound: natal cult-capacity + transit trigger
    # =====================================================
    print(f"\n{'='*100}")
    print(f"COMPOUND: natal Pluto-MC tight AND transit Pluto-MC tight")
    print(f"{'='*100}")
    for nat_cut in (3, 5, 8):
        for tr_cut in (3, 5):
            subset = [d for d in data if d["nat_plu_mc"] <= nat_cut and d["plu_mc"] <= tr_cut]
            if not subset: continue
            mults = [d["mult"] for d in subset]
            print(f"  nat≤{nat_cut} + trans≤{tr_cut}: n={len(subset):>3d}  mean={st.mean(mults):6.1f}×  med={st.median(mults):6.1f}×  %≥25×={100*sum(1 for m in mults if m>=25)/len(subset):.0f}%  %≥100×={100*sum(1 for m in mults if m>=100)/len(subset):.0f}%  cases: {[d['ticker'] for d in subset][:10]}")

    # The "cult + myth" extreme test
    print(f"\n{'='*100}")
    print(f"EXTREME: Plu≤3° Nep≤3° at bottom — cult+myth claim 497× / 30% ≥25×")
    print(f"{'='*100}")
    cult_myth = [d for d in data if d["plu_sun"] <= 3 and d["nep_sun"] <= 3]
    if cult_myth:
        mults = [d["mult"] for d in cult_myth]
        print(f"  n={len(cult_myth)}  mean={st.mean(mults):.1f}×  med={st.median(mults):.1f}×  max={max(mults)}×")
        print(f"  Cases: {sorted([(d['ticker'], d['mult']) for d in cult_myth], key=lambda x: -x[1])[:15]}")
        print(f"  %≥25×={100*sum(1 for m in mults if m>=25)/len(cult_myth):.0f}%")
        print(f"  %≥100×={100*sum(1 for m in mults if m>=100)/len(cult_myth):.0f}%")

if __name__ == "__main__":
    main()
