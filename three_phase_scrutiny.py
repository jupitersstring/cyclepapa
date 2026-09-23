"""
THREE-PHASE CLAIM SCRUTINY

Directly test the three-phase model (BOTTOM / MID-RALLY / PEAK) against
the 152-case parabolic corpus.

Each case has: ticker, IPO, bottom (y,m), top (y,m), multiple, speed_class.

For each case, compute three snapshots:
  - BOTTOM snapshot: at bottom date
  - MID snapshot: midpoint date between bottom and peak
  - PEAK snapshot: at peak date

At each snapshot, per outer planet, compute:
  - Orb to natal Sun, Moon, ASC, MC SEPARATELY  (not min — separately)
  - Retrograde flag

Then test each claim verbatim:

BOTTOM signals (should be elevated at BOTTOM vs PEAK):
  [B1] Neptune on MC ≤3°        claim: net -6 (bottom - peak)
  [B2] Neptune on ASC ≤3°       claim: net -5
  [B3] Saturn far ≥12° (any)    claim: net -8
  [B4] ≥4 retrogrades total     claim: net -8
  [B5] Pluto-Sun ≤3°            claim: net -4

MID-RALLY signals (should peak at MID vs bottom + peak):
  [M1] Neptune retrograde       claim: 36/54/38 (bottom/mid/peak %)
  [M2] Jupiter on ASC ≤3°       claim: 13/16/11
  [M3] ≥4 retrogrades           claim: 15/20/10

PEAK signals (turned ON at peak vs bottom):
  [P1] Jupiter on MC ≤5°        claim: turned ON +12
  [P2] Jupiter retrograde       claim: turned ON +14
  [P3] Pluto on MC ≤3°          claim: +4
  [P4] Saturn on MC ≤3° in ≥25× moves  claim: 12% vs 3% in <10×
  [P5] Saturn ≤3° (any natal)   claim: 57% of all peaks
  [P6] Saturn ≤5° (any natal)   claim: 73% of all peaks
  [P7] Median Saturn orb at peak: 2.5°

For each claim, print ACTUAL observed % and whether it matches the claim.
"""
import math, statistics as st, sys
from datetime import datetime
from collections import defaultdict
import swisseph as swe
from bti_test import compute_natal, transits_at, jd_of
from parabolic_corpus import PARABOLIC_BOTTOMS

OUTERS = ("Jupiter","Saturn","Uranus","Neptune","Pluto")
ALL_PLANETS = ("Sun","Moon","Mercury","Venus","Mars","Jupiter","Saturn","Uranus","Neptune","Pluto")
NATAL_PTS   = ("Sun","Moon","ASC","MC")

def orb(a, b):
    d = abs((a - b) % 360)
    return min(d, 360 - d)

def closest_hard(a, b):
    """Min orb to a hard aspect (0, 90, 180) from b."""
    best = 99
    for asp in (0, 90, 180):
        for sign in (+1, -1):
            o = orb(a, b + sign*asp)
            if o < best: best = o
    return best

def ym_to_date(y, m):
    return (y, m, 15)

def midpoint(bot, top):
    """Halfway between (y,m) bottom and (y,m) top."""
    by, bm = bot; ty, tm = top
    b_idx = by*12 + bm
    t_idx = ty*12 + tm
    mid = (b_idx + t_idx) // 2
    return (mid // 12, mid % 12 if mid%12 else 12)

def snapshot(natal, ym):
    y, m = ym
    trans = transits_at(y, m)
    # Per-outer orb to each of 4 natal points (separately)
    per_point = {}  # {outer: {point: orb_closest_hard}}
    for outer in OUTERS:
        per_point[outer] = {}
        for pt in NATAL_PTS:
            if pt not in natal:
                per_point[outer][pt] = 99
                continue
            per_point[outer][pt] = closest_hard(trans[outer]["lon"], natal[pt]["lon"])
    # Pluto/Ura/Sat to Sun specifically for extra claims
    retro = {p: trans[p]["retro"] for p in ALL_PLANETS}
    # Count of retrogrades across all (non-lumin) planets: Merc/Ven/Mars/Jup/Sat/Ura/Nep/Plu (8 possible)
    retro_count_all = sum(1 for p in ("Mercury","Venus","Mars","Jupiter","Saturn","Uranus","Neptune","Pluto") if retro[p])
    retro_count_outers = sum(1 for p in OUTERS if retro[p])
    return {"per_point": per_point, "retro": retro,
            "retro_count_all": retro_count_all, "retro_count_outers": retro_count_outers}

def main():
    cases = []
    for tk, ipo, bot, top, mult, speed, note in PARABOLIC_BOTTOMS:
        try:
            natal = compute_natal(ipo)
            b_snap = snapshot(natal, bot)
            p_snap = snapshot(natal, top)
            mid = midpoint(bot, top)
            m_snap = snapshot(natal, mid)
            cases.append({"tk": tk, "mult": mult, "speed": speed,
                          "bot": b_snap, "mid": m_snap, "peak": p_snap,
                          "same_mo": bot == top})
        except:
            continue

    N = len(cases)
    print(f"Corpus loaded: {N} cases (of {len(PARABOLIC_BOTTOMS)})")
    same_mo = sum(1 for c in cases if c["same_mo"])
    print(f"  same-month bottom=peak: {same_mo}  (mid=bottom=peak for these)")

    def pct_of(cases, fn, phase):
        # phase in {"bot","mid","peak"}
        return 100 * sum(1 for c in cases if fn(c[phase])) / N

    # ------------- BOTTOM CLAIMS ------------- #
    print("\n" + "="*85)
    print(" BOTTOM CLAIMS  (claim: elevated at BOTTOM vs PEAK; net = bot% - peak%)")
    print("="*85)

    def P_test(label, claim_net, fn):
        pb = pct_of(cases, fn, "bot")
        pm = pct_of(cases, fn, "mid")
        pp = pct_of(cases, fn, "peak")
        net = pb - pp
        status = "✓" if ((claim_net > 0 and net > 0) or (claim_net < 0 and net < 0)) and abs(net) >= 2 else "✗"
        print(f"  {status} {label:<46s}  bot {pb:5.1f}%  mid {pm:5.1f}%  peak {pp:5.1f}%   (bot-peak: {net:+5.1f}  claim: {claim_net:+d})")

    # [B1] Neptune on MC ≤3°
    P_test("[B1] Neptune on MC ≤3°",
           -6, lambda s: s["per_point"]["Neptune"]["MC"] <= 3)
    # [B2] Neptune on ASC ≤3°
    P_test("[B2] Neptune on ASC ≤3°",
           -5, lambda s: s["per_point"]["Neptune"]["ASC"] <= 3)
    # [B3] Saturn far ≥12° (min orb across any natal point ≥ 12)
    P_test("[B3] Saturn far (min ≥12° to all natal)",
           -8, lambda s: min(s["per_point"]["Saturn"].values()) >= 12)
    # [B4] ≥4 retrogrades
    P_test("[B4] ≥4 retrogrades (among 8 non-luminary)",
           -8, lambda s: s["retro_count_all"] >= 4)
    # [B5] Pluto-Sun ≤3°
    P_test("[B5] Pluto-Sun ≤3°",
           -4, lambda s: s["per_point"]["Pluto"]["Sun"] <= 3)
    # Also: Saturn absent specifically from Sun/MC:
    P_test("[B3'] Saturn far from Sun+MC ≥12° (both)",
           -8, lambda s: s["per_point"]["Saturn"]["Sun"] >= 12 and s["per_point"]["Saturn"]["MC"] >= 12)

    # ------------- MID-RALLY CLAIMS ------------- #
    print("\n" + "="*85)
    print(" MID-RALLY CLAIMS  (claim: peaks at MID, higher than both BOTTOM and PEAK)")
    print("="*85)

    def mid_test(label, bot_claim, mid_claim, peak_claim, fn):
        pb = pct_of(cases, fn, "bot")
        pm = pct_of(cases, fn, "mid")
        pp = pct_of(cases, fn, "peak")
        is_mid_peak = pm > pb and pm > pp
        print(f"  {'✓' if is_mid_peak else '✗'} {label:<46s}  bot {pb:5.1f}%  mid {pm:5.1f}%  peak {pp:5.1f}%   (claim: {bot_claim}/{mid_claim}/{peak_claim})")

    # [M1] Neptune retrograde
    mid_test("[M1] Neptune retrograde",
             36, 54, 38, lambda s: s["retro"]["Neptune"])
    # [M2] Jupiter on ASC ≤3°
    mid_test("[M2] Jupiter on ASC ≤3°",
             13, 16, 11, lambda s: s["per_point"]["Jupiter"]["ASC"] <= 3)
    # [M3] ≥4 retrogrades
    mid_test("[M3] ≥4 retrogrades",
             15, 20, 10, lambda s: s["retro_count_all"] >= 4)

    # ------------- PEAK CLAIMS ------------- #
    print("\n" + "="*85)
    print(" PEAK CLAIMS  (claim: signals TURN ON at peak vs bottom)")
    print("="*85)

    # [P1] Jupiter on MC ≤5°
    P_test("[P1] Jupiter on MC ≤5°",
           +12, lambda s: s["per_point"]["Jupiter"]["MC"] <= 5)
    # Also Jupiter on MC ≤3° (stricter)
    P_test("[P1'] Jupiter on MC ≤3°",
           +8, lambda s: s["per_point"]["Jupiter"]["MC"] <= 3)
    # [P2] Jupiter retrograde
    P_test("[P2] Jupiter retrograde",
           +14, lambda s: s["retro"]["Jupiter"])
    # [P3] Pluto on MC ≤3°
    P_test("[P3] Pluto on MC ≤3°",
           +4, lambda s: s["per_point"]["Pluto"]["MC"] <= 3)

    # [P4] Saturn on MC ≤3° in ≥25× moves (vs <10×)
    big   = [c for c in cases if c["mult"] >= 25]
    small = [c for c in cases if c["mult"] < 10]
    p_big = 100*sum(1 for c in big   if c["peak"]["per_point"]["Saturn"]["MC"] <= 3)/max(len(big),1)
    p_sml = 100*sum(1 for c in small if c["peak"]["per_point"]["Saturn"]["MC"] <= 3)/max(len(small),1)
    print(f"  {'✓' if p_big > p_sml + 2 else '✗'} [P4] Saturn on MC ≤3° at peak of ≥25× moves "
          f" {p_big:5.1f}%  (n={len(big)})  vs <10×: {p_sml:5.1f}% (n={len(small)}) "
          f" claim: 12% vs 3%")

    # [P5] Saturn ≤3° (any of Sun/Moon/ASC/MC)
    p5 = 100*sum(1 for c in cases if min(c["peak"]["per_point"]["Saturn"].values()) <= 3)/N
    print(f"  {'✓' if abs(p5 - 57) <= 7 else '✗'} [P5] Saturn ≤3° any-natal at peak:    "
          f" {p5:5.1f}%  (claim: 57%)")

    # [P6] Saturn ≤5°
    p6 = 100*sum(1 for c in cases if min(c["peak"]["per_point"]["Saturn"].values()) <= 5)/N
    print(f"  {'✓' if abs(p6 - 73) <= 7 else '✗'} [P6] Saturn ≤5° any-natal at peak:    "
          f" {p6:5.1f}%  (claim: 73%)")

    # [P7] Median Saturn orb at peak (min across natal points)
    sat_min = [min(c["peak"]["per_point"]["Saturn"].values()) for c in cases]
    med_sat = st.median(sat_min)
    print(f"  {'✓' if abs(med_sat - 2.5) <= 1.5 else '✗'} [P7] Median Saturn min-orb at peak:    "
          f" {med_sat:4.2f}°  (claim: 2.5°)")

    # Also show peak Saturn-Sun, Saturn-MC distribution
    print(f"\n  Saturn at peak diagnostic:")
    for pt in NATAL_PTS:
        vals = [c["peak"]["per_point"]["Saturn"][pt] for c in cases if c["peak"]["per_point"]["Saturn"][pt] < 99]
        p3 = 100*sum(1 for v in vals if v<=3)/max(len(vals),1)
        p5b = 100*sum(1 for v in vals if v<=5)/max(len(vals),1)
        print(f"    Saturn-{pt:<3s}: ≤3°={p3:5.1f}%  ≤5°={p5b:5.1f}%  mean={st.mean(vals):5.2f}°  med={st.median(vals):5.2f}°")

    # ------------- COMPREHENSIVE PHASE COMPARISON ------------- #
    print("\n" + "="*85)
    print(" COMPREHENSIVE: every outer × every point × phase")
    print("="*85)
    print(f"  % with orb ≤3° to natal point, per phase")
    print(f"  {'Transit':<18s}  {'BOT':>5s}  {'MID':>5s}  {'PEAK':>5s}   {'bot-peak':>8s}  signature")
    for outer in OUTERS:
        for pt in NATAL_PTS:
            bot = 100*sum(1 for c in cases if c["bot"]["per_point"][outer][pt] <= 3)/N
            mid = 100*sum(1 for c in cases if c["mid"]["per_point"][outer][pt] <= 3)/N
            pk = 100*sum(1 for c in cases if c["peak"]["per_point"][outer][pt] <= 3)/N
            net = bot - pk
            sig = ""
            if bot > pk + 5 and bot > mid: sig = "BOTTOM"
            elif pk > bot + 5 and pk > mid: sig = "PEAK"
            elif mid > max(bot, pk) + 3:    sig = "MID"
            print(f"  {outer}-{pt:<4s}     {bot:5.1f}  {mid:5.1f}  {pk:5.1f}    {net:+8.1f}   {sig}")

    # Retrograde signatures
    print(f"\n  Retrograde signature per phase:")
    for planet in ("Jupiter","Saturn","Uranus","Neptune","Pluto"):
        bot = 100*sum(1 for c in cases if c["bot"]["retro"][planet])/N
        mid = 100*sum(1 for c in cases if c["mid"]["retro"][planet])/N
        pk  = 100*sum(1 for c in cases if c["peak"]["retro"][planet])/N
        print(f"    {planet:<9s} retrograde:  BOT {bot:5.1f}%  MID {mid:5.1f}%  PEAK {pk:5.1f}%   Δ(peak-bot) {pk-bot:+5.1f}")
    # All retro
    for thr in (3,4,5):
        bot = 100*sum(1 for c in cases if c["bot"]["retro_count_all"] >= thr)/N
        mid = 100*sum(1 for c in cases if c["mid"]["retro_count_all"] >= thr)/N
        pk  = 100*sum(1 for c in cases if c["peak"]["retro_count_all"] >= thr)/N
        print(f"    ≥{thr} retrograde:        BOT {bot:5.1f}%  MID {mid:5.1f}%  PEAK {pk:5.1f}%   Δ(peak-bot) {pk-bot:+5.1f}")

    # Output as CSV for reproducibility
    import csv
    with open("/home/user/cyclepapa/data/three_phase_signature.csv","w",newline="") as f:
        w = csv.writer(f)
        w.writerow(["ticker","mult","speed","phase","outer","point","orb","retro"])
        for c in cases:
            for phase in ("bot","mid","peak"):
                snap = c[phase]
                for outer in OUTERS:
                    for pt in NATAL_PTS:
                        w.writerow([c["tk"], c["mult"], c["speed"], phase, outer, pt,
                                    f"{snap['per_point'][outer][pt]:.2f}",
                                    1 if snap["retro"][outer] else 0])
    print("\nExported: data/three_phase_signature.csv")

if __name__ == "__main__":
    main()
