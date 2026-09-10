"""
HARMONIC PATTERN — PER PLANET PAIR test.

Different harmonic patterns may resonate with different planet pairs.
Test classic Gartley D-point aspects (0.786, 0.886, 1.272, 1.618=phi)
across (a) transit-outer-to-natal-point, (b) transit-INNER-to-natal,
(c) transit-transit pairs.

Gartley-pattern D-point aspects (lesser arc):
  Gartley/Cypher D = 0.786 -> 77.04°
  Bat/Shark D     = 0.886 -> 41.04°
  Butterfly D     = 1.272 -> 97.92°
  Crab/Deep Crab D= 1.618 -> 137.50° (golden angle)

Plus test:
  Mid-leg ratios: 0.382 (137.5°), 0.5 (180°), 0.618 (137.5°)
  Quintile 72°, biquintile 144° (Venus pentagram)
  Sept 51.4° (1/7 — Saturn-Pluto sept), Nov 32.7° (1/11)

Identify the planet-pair × harmonic-angle combos with strongest signal.
"""
import math
import statistics as st
from collections import defaultdict
from bti_test import compute_natal, transits_at, jd_of
from parabolic_corpus import PARABOLIC_BOTTOMS
from three_phase_scrutiny import snapshot, midpoint
import random

ALL_PLANETS = ("Sun","Moon","Mercury","Venus","Mars","Jupiter","Saturn","Uranus","Neptune","Pluto")
TRANSIT_PLANETS = ALL_PLANETS  # all
NATAL_TARGETS = ("Sun","Moon","ASC","MC","Mercury","Venus","Mars","Jupiter","Saturn","Uranus","Neptune","Pluto")

# Harmonic D-point aspects from Gartley/Pesavento/Carney
HARMONIC = {
    "0.786 (Gartley_D)":   77.04,
    "0.886 (Bat/Shark_D)": 41.04,
    "1.272 (Butterfly_D)": 97.92,
    "1.618 (Crab_D / Phi)":137.50,
    "0.50 (Half)":         180.00,
    "Quintile_72":         72.00,
    "Biquintile_144":      144.00,
    "Septile_51.4":        51.43,   # 1/7 — Saturn-Pluto / Mars-Saturn
    "Novile_40":           40.00,   # 1/9
    "Triple_decile_108":   108.00,  # 3/10
}

def aspect_orb(t_lon, n_lon, target):
    d = (t_lon - n_lon) % 360
    return min(abs(d - target), abs(d - (360 - target)))

def main():
    # Load corpus
    cases = []
    for tk, ipo, bot, top, mult, speed, note in PARABOLIC_BOTTOMS:
        try:
            natal = compute_natal(ipo)
            mid = midpoint(bot, top)
            cases.append({
                "tk":tk,"natal":natal,"mult":mult,
                "bot":bot,"mid":mid,"peak":top,
                "trans_bot":transits_at(bot[0],bot[1]),
                "trans_mid":transits_at(mid[0],mid[1]),
                "trans_peak":transits_at(top[0],top[1]),
            })
        except: continue
    N = len(cases)
    print(f"Loaded {N} cases")

    # Random non-event baseline
    random.seed(42)
    baseline = []
    for c in cases:
        for _ in range(3):
            offset = random.choice([-60,-48,-36,-24,12,24,36,48,60])
            y = c["peak"][0]; m = c["peak"][1]
            idx = y*12+m-1+offset
            ny, nm = idx//12, (idx%12)+1
            try:
                baseline.append((c["natal"], transits_at(ny, nm)))
            except: continue
    BN = len(baseline)
    print(f"Baseline pool: {BN}\n")

    # ============================================================
    # PER-PAIR × PER-ASPECT activation rates
    # ============================================================
    print(f"{'='*120}")
    print(f"PLANET-PAIR × HARMONIC-ASPECT activation rates (% within 3° at any phase)")
    print(f"  Showing pairs with peak-bot lift OR vs-baseline lift > 4pp")
    print(f"{'='*120}")

    findings = []
    for asp_name, asp_deg in HARMONIC.items():
        for tp in TRANSIT_PLANETS:
            for nt in NATAL_TARGETS:
                if tp == nt: continue
                bot_hits = 0; mid_hits = 0; peak_hits = 0
                base_hits = 0
                for c in cases:
                    if nt not in c["natal"]: continue
                    nl = c["natal"][nt]["lon"]
                    if tp in c["trans_bot"]:
                        if aspect_orb(c["trans_bot"][tp]["lon"], nl, asp_deg) <= 3: bot_hits += 1
                    if tp in c["trans_mid"]:
                        if aspect_orb(c["trans_mid"][tp]["lon"], nl, asp_deg) <= 3: mid_hits += 1
                    if tp in c["trans_peak"]:
                        if aspect_orb(c["trans_peak"][tp]["lon"], nl, asp_deg) <= 3: peak_hits += 1
                for natal, trans in baseline:
                    if nt not in natal or tp not in trans: continue
                    if aspect_orb(trans[tp]["lon"], natal[nt]["lon"], asp_deg) <= 3: base_hits += 1
                bot_pct = 100*bot_hits/N
                mid_pct = 100*mid_hits/N
                peak_pct = 100*peak_hits/N
                base_pct = 100*base_hits/BN
                # Lift = max phase rate - baseline
                max_phase = max(bot_pct, mid_pct, peak_pct)
                max_lift = max_phase - base_pct
                # Phase contrast
                bot_peak = peak_pct - bot_pct
                if max_lift >= 4 or abs(bot_peak) >= 4:
                    findings.append({
                        "asp":asp_name,"deg":asp_deg,"tp":tp,"nt":nt,
                        "bot":bot_pct,"mid":mid_pct,"peak":peak_pct,
                        "base":base_pct,"max_lift":max_lift,
                        "bot_peak":bot_peak
                    })

    # Sort by absolute lift
    findings.sort(key=lambda f: -abs(f["max_lift"]))
    print(f"\n  TOP 50 by max lift over baseline:")
    print(f"  {'Aspect':<22s} {'Pair':<22s} {'BOT':>5s} {'MID':>5s} {'PEAK':>5s} {'BASE':>5s} {'MaxLift':>7s} {'B-P':>5s}")
    for f in findings[:50]:
        pair = f"t{f['tp'][:3]}-n{f['nt'][:5]}"
        print(f"  {f['asp']:<22s} {pair:<22s} {f['bot']:>4.1f}% {f['mid']:>4.1f}% {f['peak']:>4.1f}% "
              f"{f['base']:>4.1f}% {f['max_lift']:>+6.1f}pp {f['bot_peak']:>+5.1f}")

    # ============================================================
    # AGGREGATE — which HARMONIC ASPECT works most often across pairs?
    # ============================================================
    print(f"\n{'='*120}")
    print(f"  AGGREGATE — for each harmonic aspect, count pairs with >+5pp lift")
    print(f"{'='*120}")
    for asp_name, asp_deg in HARMONIC.items():
        n_pos = sum(1 for f in findings if f["asp"]==asp_name and f["max_lift"]>=5)
        n_neg = sum(1 for f in findings if f["asp"]==asp_name and f["max_lift"]<=-5)
        if n_pos+n_neg==0: continue
        print(f"  {asp_name:<22s} ({asp_deg:>6.2f}°)  POSITIVE pairs: {n_pos}   NEGATIVE: {n_neg}")

    # ============================================================
    # TRANSIT-TRANSIT harmonic test (no natal needed) — pure timing
    # ============================================================
    print(f"\n{'='*120}")
    print(f"  TRANSIT-TRANSIT harmonics — pure planetary cycle timing")
    print(f"  (Asks: are transit Mars-Jup, Venus-Sun, Saturn-Pluto etc. at phi-aspect on event days?)")
    print(f"{'='*120}")
    inner_pairs = [
        ("Mars","Jupiter"),("Venus","Mars"),("Mercury","Mars"),
        ("Mars","Saturn"),("Sun","Mars"),("Sun","Jupiter"),
        ("Venus","Jupiter"),("Mercury","Jupiter"),
        ("Jupiter","Saturn"),("Jupiter","Uranus"),("Saturn","Pluto"),
        ("Uranus","Neptune"),("Saturn","Neptune"),("Mars","Pluto"),
    ]
    print(f"  {'Aspect':<22s} {'Pair':<22s} {'BOT':>5s} {'MID':>5s} {'PEAK':>5s} {'BASE':>5s} {'MaxLift':>7s}")
    for asp_name, asp_deg in HARMONIC.items():
        for pa, pb in inner_pairs:
            bot=mid=pk=base=0
            for c in cases:
                if pa in c["trans_bot"] and pb in c["trans_bot"]:
                    if aspect_orb(c["trans_bot"][pa]["lon"], c["trans_bot"][pb]["lon"], asp_deg) <= 3: bot+=1
                if pa in c["trans_mid"] and pb in c["trans_mid"]:
                    if aspect_orb(c["trans_mid"][pa]["lon"], c["trans_mid"][pb]["lon"], asp_deg) <= 3: mid+=1
                if pa in c["trans_peak"] and pb in c["trans_peak"]:
                    if aspect_orb(c["trans_peak"][pa]["lon"], c["trans_peak"][pb]["lon"], asp_deg) <= 3: pk+=1
            for _, trans in baseline:
                if pa in trans and pb in trans:
                    if aspect_orb(trans[pa]["lon"], trans[pb]["lon"], asp_deg) <= 3: base+=1
            b_p = 100*bot/N; m_p = 100*mid/N; p_p = 100*pk/N; bs = 100*base/BN
            lift = max(b_p, m_p, p_p) - bs
            if lift >= 5 or lift <= -5:
                pair = f"{pa[:3]}-{pb[:3]}"
                print(f"  {asp_name:<22s} {pair:<22s} {b_p:>4.1f}% {m_p:>4.1f}% {p_p:>4.1f}% "
                      f"{bs:>4.1f}% {lift:>+6.1f}pp")

    # ============================================================
    # PESAVENTO PATTERN-COMPLETENESS test
    # Does at-least-one D-point aspect activate at parabolic events?
    # ============================================================
    print(f"\n{'='*120}")
    print(f"  ANY HARMONIC D-POINT ACTIVE — % cases where AT LEAST ONE Gartley D-point")
    print(f"  aspect (0.786, 0.886, 1.272, 1.618=137.5°) hits transit-outer→natal-point ≤2°")
    print(f"{'='*120}")
    D_aspects = [77.04, 41.04, 97.92, 137.50]
    OUTERS_ONLY = ("Jupiter","Saturn","Uranus","Neptune","Pluto")
    NATAL_PRIM = ("Sun","Moon","ASC","MC")
    def any_d_active(natal, trans, orb_thresh=2):
        for tp in OUTERS_ONLY:
            if tp not in trans: continue
            tlon = trans[tp]["lon"]
            for nt in NATAL_PRIM:
                if nt not in natal: continue
                nl = natal[nt]["lon"]
                for asp in D_aspects:
                    if aspect_orb(tlon, nl, asp) <= orb_thresh:
                        return True
        return False

    for thr in (1.5, 2.0, 3.0):
        bot_h = sum(1 for c in cases if any_d_active(c["natal"], c["trans_bot"], thr))
        mid_h = sum(1 for c in cases if any_d_active(c["natal"], c["trans_mid"], thr))
        pk_h = sum(1 for c in cases if any_d_active(c["natal"], c["trans_peak"], thr))
        base_h = sum(1 for natal, trans in baseline if any_d_active(natal, trans, thr))
        print(f"  Orb≤{thr}°:  BOT {100*bot_h/N:>4.0f}%  MID {100*mid_h/N:>4.0f}%  "
              f"PEAK {100*pk_h/N:>4.0f}%  BASE {100*base_h/BN:>4.0f}%   "
              f"max-lift {max(bot_h,mid_h,pk_h)*100/N - 100*base_h/BN:+5.1f}pp")

if __name__ == "__main__":
    main()
