"""
HARMONIC ASPECT EMPIRICAL TEST.

Tests Gartley/Fibonacci/phi-derived angular aspects on the 152-case
parabolic corpus to see if any of them cluster at parabolic phases.

Angular aspects derived from Gartley ratios on the 360° circle (lesser arc):
  137.5°   = 360 × 0.382 (Golden Angle / phi-aspect)
   77.04°  = 360 × 0.786 - 360 (lesser arc)
   41.04°  = 360 × 0.886 - 360 (lesser arc)
   97.92°  = 360 × 1.272 mod 360 (lesser arc)

Quintile family (Pentagram of Venus / 5-fold):
   72°, 144°, 36°, 108°

Tested for transit outer (Jup/Sat/Ura/Nep/Plu) to natal Sun/Moon/ASC/MC.

For each aspect, count cases at each phase (bottom/mid/peak) where
at least one transit-natal pair has orb ≤3° to that aspect.
Compare against same-corpus random-day baseline.
"""
import math, statistics as st
from collections import defaultdict
from bti_test import compute_natal, transits_at, jd_of
from parabolic_corpus import PARABOLIC_BOTTOMS
from three_phase_scrutiny import snapshot, midpoint, OUTERS, NATAL_PTS

def angular_orb(a, b):
    """Smaller arc between two longitudes."""
    d = abs((a - b) % 360)
    return min(d, 360 - d)

# Define harmonic aspects (lesser-arc target degrees)
HARMONIC_ASPECTS = {
    "PHI_137.5": 137.5,         # 0.382 × 360 / 0.618 × 360 lesser arc
    "PHI_77.04": 77.04,         # 0.786
    "PHI_41.04": 41.04,         # 0.886
    "PHI_97.92": 97.92,         # 1.272
    "QUINT_72": 72.0,           # 1/5
    "BIQUINT_144": 144.0,       # 2/5
    "DECILE_36": 36.0,          # 1/10
    "TRIDEC_108": 108.0,        # 3/10
}

# Standard hard-aspect baseline (for comparison)
TRADITIONAL_HARD = {
    "CONJ_0":   0.0,
    "SQ_90":    90.0,
    "OPP_180":  180.0,
}

# Standard soft (Ptolemy):
TRADITIONAL_SOFT = {
    "SEXT_60":  60.0,
    "TRINE_120": 120.0,
}

ALL_ASPECTS = {**TRADITIONAL_HARD, **TRADITIONAL_SOFT, **HARMONIC_ASPECTS}

def aspect_orb(transit_lon, natal_lon, target_aspect):
    """Orb between transit and natal at the specified aspect angle.
    Considers both directions (e.g. natal+72° and natal-72°)."""
    d = (transit_lon - natal_lon) % 360
    o1 = abs(d - target_aspect)
    o2 = abs(d - (360 - target_aspect))  # opposite direction
    return min(o1, o2, 360 - o1, 360 - o2)

def best_aspect_orb(transit_lon, natal_lon, target):
    """Symmetric — distance from the transit-natal angle to the target."""
    d = (transit_lon - natal_lon) % 360
    return min(abs(d - target), abs(d - (360 - target)), abs(d + target - 360))

def aspect_active(natal, trans, target_deg):
    """Return min orb across all transit-outer to natal-point pairs at this aspect."""
    best = 99
    for outer in OUTERS:
        if outer not in trans: continue
        tlon = trans[outer]["lon"]
        for pt in NATAL_PTS:
            if pt not in natal: continue
            nlon = natal[pt]["lon"]
            o = aspect_orb(tlon, nlon, target_deg)
            if o < best: best = o
    return best

def main():
    cases = []
    for tk, ipo, bot, top, mult, speed, note in PARABOLIC_BOTTOMS:
        try:
            natal = compute_natal(ipo)
            mid = midpoint(bot, top)
            cases.append({
                "tk":tk,"mult":mult,
                "natal":natal,
                "bot":bot,"mid":mid,"peak":top,
                "trans_bot":transits_at(bot[0],bot[1]),
                "trans_mid":transits_at(mid[0],mid[1]),
                "trans_peak":transits_at(top[0],top[1]),
            })
        except: continue
    N = len(cases)
    print(f"Loaded {N} cases\n")

    # For each aspect, count % cases with min orb ≤3° at each phase
    print(f"{'='*100}")
    print(f" HARMONIC + TRADITIONAL ASPECT ACTIVATION RATES — % cases with any transit-outer to natal-point ≤3°")
    print(f"{'='*100}")
    print(f"{'Aspect':<14s} {'angle':>6s}  {'BOT %≤3°':>9s} {'MID %≤3°':>9s} {'PEAK %≤3°':>10s}  {'BOT-PEAK':>10s}")

    results = []
    for name, deg in ALL_ASPECTS.items():
        bot_hits = sum(1 for c in cases if aspect_active(c["natal"], c["trans_bot"], deg) <= 3)
        mid_hits = sum(1 for c in cases if aspect_active(c["natal"], c["trans_mid"], deg) <= 3)
        pk_hits  = sum(1 for c in cases if aspect_active(c["natal"], c["trans_peak"], deg) <= 3)
        b = 100*bot_hits/N; m = 100*mid_hits/N; p = 100*pk_hits/N
        results.append({"name":name,"deg":deg,"bot":b,"mid":m,"peak":p})
        print(f"{name:<14s} {deg:>6.2f}°  {b:>8.1f}% {m:>8.1f}% {p:>9.1f}%   {b-p:>+8.1f}pp")

    # Baseline: random day. Generate from same cases, ±60 months from peak (off-event days)
    print(f"\n{'='*100}")
    print(f" BASELINE — same charts, RANDOM non-event months (sampled at ±60 months from each peak)")
    print(f"{'='*100}")
    import random
    random.seed(42)
    BASELINE_SAMPLES = N * 3
    baseline_pool = []
    for c in cases:
        for _ in range(3):
            offset = random.choice([-60,-48,-36,-24,12,24,36,48,60])
            y = c["peak"][0]; m = c["peak"][1]
            idx = y*12+m-1+offset
            ny, nm = idx//12, (idx%12)+1
            try:
                baseline_pool.append((c["natal"], transits_at(ny, nm)))
            except: continue
    print(f"  Baseline pool size: {len(baseline_pool)}")

    print(f"\n{'Aspect':<14s} {'angle':>6s}  {'Base %≤3°':>10s}  {'BOT lift':>9s} {'MID lift':>9s} {'PEAK lift':>10s}")
    for r in results:
        base_hits = sum(1 for natal, trans in baseline_pool
                        if aspect_active(natal, trans, r["deg"]) <= 3)
        base_pct = 100*base_hits/len(baseline_pool)
        bot_lift = r["bot"] - base_pct
        mid_lift = r["mid"] - base_pct
        peak_lift = r["peak"] - base_pct
        marker = ""
        if abs(bot_lift) > 5 or abs(mid_lift) > 5 or abs(peak_lift) > 5:
            marker = " <<"
        print(f"{r['name']:<14s} {r['deg']:>6.2f}°  {base_pct:>9.1f}%   "
              f"{bot_lift:>+8.1f} {mid_lift:>+8.1f} {peak_lift:>+9.1f}{marker}")

    # ----- Tighter test: ≤1° (near-exact) -----
    print(f"\n{'='*100}")
    print(f" TIGHT (≤1°) — does any harmonic aspect EXACT cluster at events?")
    print(f"{'='*100}")
    print(f"{'Aspect':<14s} {'angle':>6s}  {'Base %≤1°':>10s}  {'BOT %≤1°':>9s} {'MID %≤1°':>9s} {'PEAK %≤1°':>10s}")
    for name, deg in ALL_ASPECTS.items():
        bot_hits = sum(1 for c in cases if aspect_active(c["natal"], c["trans_bot"], deg) <= 1)
        mid_hits = sum(1 for c in cases if aspect_active(c["natal"], c["trans_mid"], deg) <= 1)
        pk_hits = sum(1 for c in cases if aspect_active(c["natal"], c["trans_peak"], deg) <= 1)
        base_hits = sum(1 for natal, trans in baseline_pool if aspect_active(natal, trans, deg) <= 1)
        base = 100*base_hits/len(baseline_pool)
        b = 100*bot_hits/N; m = 100*mid_hits/N; p = 100*pk_hits/N
        marker = " <<" if max(b,m,p) - base > 3 else ""
        print(f"{name:<14s} {deg:>6.2f}°  {base:>9.1f}%   "
              f"{b:>8.1f}% {m:>8.1f}% {p:>9.1f}%{marker}")

    # ----- Per-planet breakdown for the strongest harmonic finding -----
    # Find the strongest harmonic-aspect lift across all phases
    best_harm = None; best_lift = 0
    for r in results:
        if r["name"].startswith("PHI_") or r["name"].startswith("QUINT_") or r["name"].startswith("BIQUINT") or r["name"].startswith("DECILE_") or r["name"].startswith("TRIDEC_"):
            for ph_v in [r["bot"], r["mid"], r["peak"]]:
                if ph_v - 5 > best_lift:  # rough threshold
                    best_lift = ph_v
                    best_harm = r
    if best_harm:
        deg = best_harm["deg"]
        print(f"\n{'='*100}")
        print(f" PER-PLANET BREAKDOWN — best harmonic aspect: {best_harm['name']} ({deg:.2f}°)")
        print(f"{'='*100}")
        print(f"{'Pair':<16s} {'BOT %≤3°':>10s} {'MID %≤3°':>10s} {'PEAK %≤3°':>11s}")
        for outer in OUTERS:
            for pt in NATAL_PTS:
                bot_hit = sum(1 for c in cases if c["natal"].get(pt) and outer in c["trans_bot"]
                              and aspect_orb(c["trans_bot"][outer]["lon"], c["natal"][pt]["lon"], deg) <= 3)
                mid_hit = sum(1 for c in cases if c["natal"].get(pt) and outer in c["trans_mid"]
                              and aspect_orb(c["trans_mid"][outer]["lon"], c["natal"][pt]["lon"], deg) <= 3)
                pk_hit = sum(1 for c in cases if c["natal"].get(pt) and outer in c["trans_peak"]
                             and aspect_orb(c["trans_peak"][outer]["lon"], c["natal"][pt]["lon"], deg) <= 3)
                if (bot_hit + mid_hit + pk_hit) >= 5:
                    print(f"{outer}-{pt:<8s} {100*bot_hit/N:>9.1f}% {100*mid_hit/N:>9.1f}% {100*pk_hit/N:>10.1f}%")

if __name__ == "__main__":
    main()
