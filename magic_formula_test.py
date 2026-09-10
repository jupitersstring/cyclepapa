"""
Test Grace Morris's "Magic Formula" + Kate Silas's eclipse-to-IPO
+ Bill Meridian's Saturn-IC/MC cycle on the 152-parabolic corpus.

Grace Morris claim: Sun-Jupiter-Pluto aspects in IPO chart = extraordinary success.
Kate Silas claim: eclipses on IPO-chart degrees drive 300-500% moves.
Bill Meridian claim: Saturn ascent IC→MC = 14-year bull run.
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

def aspect_orb(a, b, aspects=(0,60,90,120,180), max_orb=8):
    best = None
    for asp in aspects:
        for sign in (+1, -1):
            o = orb(a, b + sign * asp)
            if o <= max_orb and (best is None or o < best[1]):
                best = (asp, o)
    return best

# ============================================================
# (1) GRACE MORRIS: MAGIC FORMULA
# ============================================================
def magic_formula_score(natal, orb_threshold=8):
    """Sun-Jupiter-Pluto mutual aspect count in natal chart.
    Morris: trine/sextile/conjunction = benefic; square/opp = potential still exists.
    Returns: (score, aspects_found).
    """
    aspects = []
    # Sun-Jupiter
    sj = aspect_orb(natal["Sun"]["lon"], natal["Jupiter"]["lon"], max_orb=orb_threshold)
    if sj: aspects.append(("Sun-Jup", sj))
    # Sun-Pluto
    sp = aspect_orb(natal["Sun"]["lon"], natal["Pluto"]["lon"], max_orb=orb_threshold)
    if sp: aspects.append(("Sun-Plu", sp))
    # Jupiter-Pluto
    jp = aspect_orb(natal["Jupiter"]["lon"], natal["Pluto"]["lon"], max_orb=orb_threshold)
    if jp: aspects.append(("Jup-Plu", jp))

    # Score: all three pairs present = full Magic Formula
    # 2 pairs = partial; 1 = weak
    n_pairs = len(aspects)
    # Type weight: trines (120°) + sextiles (60°) + conj (0°) are "benefic" Morris-style
    benefic_types = sum(1 for (_, (asp, _)) in aspects if asp in (0, 60, 120))
    hard_types = sum(1 for (_, (asp, _)) in aspects if asp in (90, 180))

    # Combined score: more benefic aspects + tighter orbs = stronger magic
    score = 0
    for (_, (asp, o)) in aspects:
        weight = 1.5 if asp in (0, 60, 120) else 0.8
        score += weight * (orb_threshold - o) / orb_threshold
    return score, aspects, benefic_types, hard_types

# ============================================================
# (2) BILL MERIDIAN: Saturn IC-MC 14-year cycle
# ============================================================
def saturn_cycle_position(natal, trans):
    """Where is transit Saturn relative to natal IC-MC axis?
    Natal IC = 180° from MC. Natal MC typically cusp of 10th house.
    Saturn rising from IC to MC = bullish 14-yr phase.
    """
    if "MC" not in natal: return None
    mc = natal["MC"]["lon"]
    ic = (mc + 180) % 360
    saturn = trans["Saturn"]["lon"]
    # Angular distance from IC to MC going counterclockwise (matching chart direction)
    # Phase 0 = IC, 180 = MC, 360 = back to IC
    phase = (saturn - ic) % 360
    # Classification per Meridian
    if 0 <= phase < 90:
        cycle = "IC_to_3H_rising"; is_bull = True
    elif 90 <= phase < 180:
        cycle = "3H_to_MC_ascending"; is_bull = True  # strongest
    elif 180 <= phase < 270:
        cycle = "MC_to_9H_descending"; is_bull = False
    else:
        cycle = "9H_to_IC_bottom"; is_bull = False
    return {"phase_deg": phase, "cycle": cycle, "is_bullish_cycle": is_bull,
            "near_MC": orb(saturn, mc), "near_IC": orb(saturn, ic)}

# ============================================================
# (3) KATE SILAS: Eclipse to IPO degree
# ============================================================
# Approximate eclipse dates and degrees for 2020-2026 (sample)
RECENT_ECLIPSES = [
    # (date_yyyy_mm, sun_lon, type)
    ("2019-12", 263, "solar"),   # Dec 26 2019 solar Cap
    ("2020-06", 79,  "solar"),   # Jun 21 2020 solar Can
    ("2020-12", 243, "solar"),   # Dec 14 2020 solar Sag
    ("2021-06", 69,  "solar"),   # Jun 10 2021 solar Gem
    ("2021-12", 251, "solar"),   # Dec 4 2021 solar Sag
    ("2022-04", 19,  "solar"),   # Apr 30 2022 solar Tau
    ("2022-10", 209, "solar"),   # Oct 25 2022 solar Sco
    ("2023-04", 29,  "solar"),   # Apr 20 2023 solar Ari
    ("2023-10", 21,  "solar"),   # Oct 14 2023 solar Lib
    ("2024-04", 19,  "solar"),   # Apr 8 2024 solar Ari (Great American)
    ("2024-10", 9,   "solar"),   # Oct 2 2024 solar Lib
    ("2025-03", 11,  "solar"),   # Mar 29 2025 solar Ari
    ("2025-09", 29,  "solar"),   # Sep 21 2025 solar Vir
    ("2026-02", 29,  "solar"),   # Feb 17 2026 solar Aqu
    ("2026-08", 9,   "solar"),   # Aug 12 2026 solar Leo
]

def eclipse_hits_natal(natal, eclipse_date, eclipse_lon, max_orb=3):
    """Find natal sensitive points within orb of eclipse longitude."""
    hits = []
    for p in ("Sun","Moon","Mercury","Venus","Mars","Jupiter","Saturn","Uranus","Neptune","Pluto","ASC","MC"):
        if p not in natal: continue
        # Only conjunction for eclipse hits (traditional)
        o = orb(eclipse_lon, natal[p]["lon"])
        if o <= max_orb:
            hits.append({"planet": p, "orb": o, "eclipse": eclipse_date})
    return hits

# ============================================================
# Main test
# ============================================================
def main():
    print("="*100)
    print("MAGIC FORMULA TEST: Sun-Jupiter-Pluto aspects in IPO charts")
    print("="*100)

    # Magic formula at IPO for each corpus chart
    by_mult_band = defaultdict(list)
    all_results = []
    for tk, ipo, bot, top, mult, speed, note in PARABOLIC_BOTTOMS:
        try:
            natal = compute_natal(ipo)
            score, aspects, benefic, hard = magic_formula_score(natal, orb_threshold=8)
            all_results.append({"tk":tk, "mult":mult, "speed":speed,
                                "mf_score":score, "n_pairs":len(aspects),
                                "benefic":benefic, "hard":hard, "aspects":aspects})
            band = "mega" if mult>=100 else "big" if mult>=30 else "mid" if mult>=10 else "modest"
            by_mult_band[band].append(score)
        except: pass

    print(f"\n{'Band':<10s} {'n':>3s} {'MF score mean':>14s} {'median':>8s} {'max':>6s}  {'≥3 score':>10s}")
    for b in ("mega","big","mid","modest"):
        vs = by_mult_band[b]
        if vs:
            print(f"{b:<10s} {len(vs):>3d} {st.mean(vs):14.2f} {st.median(vs):8.2f} {max(vs):6.2f} {100*sum(1 for v in vs if v>=3)/len(vs):9.1f}%")

    # ALL THREE pairs present?
    print(f"\n% charts with ALL 3 pairs (Sun-Jup + Sun-Plu + Jup-Plu) within 8°:")
    for b in ("mega","big","mid","modest"):
        subset = [r for r in all_results if (
            "mega" == b and r["mult"] >= 100 or
            "big" == b and 30 <= r["mult"] < 100 or
            "mid" == b and 10 <= r["mult"] < 30 or
            "modest" == b and 3 <= r["mult"] < 10
        )]
        if subset:
            pct = 100 * sum(1 for r in subset if r["n_pairs"] == 3) / len(subset)
            print(f"  {b:<10s} {pct:5.1f}%  (n={len(subset)})")

    # Compare to random baseline — sample 50 random IPO dates between 1975-2020
    print(f"\nRandom IPO baseline (50 random dates 1975-2020):")
    import random
    random.seed(42)
    rand_scores = []
    for _ in range(80):
        y = random.randint(1975, 2020)
        m = random.randint(1, 12)
        d = random.randint(1, 28)
        try:
            natal = compute_natal(f"{y:04d}-{m:02d}-{d:02d}")
            score, _, _, _ = magic_formula_score(natal, orb_threshold=8)
            rand_scores.append(score)
        except: pass
    print(f"  Random: mean={st.mean(rand_scores):.2f}  median={st.median(rand_scores):.2f}  ≥3: {100*sum(1 for v in rand_scores if v>=3)/len(rand_scores):.1f}%")

    # Show Magnificent Seven equivalents
    print(f"\n\nSAMPLE MAGIC FORMULA chart scores (highest in corpus):")
    all_results.sort(key=lambda r:-r["mf_score"])
    for r in all_results[:15]:
        asps = ", ".join(f"{p}{a[0]}°/{a[1]:.1f}°" for p,a in r["aspects"])
        print(f"  {r['tk']:<8s} mult={r['mult']:5d}× MF={r['mf_score']:5.2f}  n_pairs={r['n_pairs']}  benefic={r['benefic']} hard={r['hard']}  [{asps}]")

    # ============================================================
    # BILL MERIDIAN: Saturn IC-MC cycle at bottom
    # ============================================================
    print(f"\n{'='*100}")
    print("BILL MERIDIAN: Saturn IC-MC 14-year cycle at bottom date")
    print(f"{'='*100}")
    cycle_bands = defaultdict(lambda: defaultdict(int))
    for tk, ipo, bot, top, mult, speed, note in PARABOLIC_BOTTOMS:
        try:
            natal = compute_natal(ipo)
            trans = transits_at(bot[0], bot[1])
            cyc = saturn_cycle_position(natal, trans)
            if cyc:
                band = "mega" if mult>=100 else "big" if mult>=30 else "mid" if mult>=10 else "modest"
                cycle_bands[band][cyc["cycle"]] += 1
        except: pass
    print(f"\n{'Band':<10s} {'IC→3H rising':>13s} {'3H→MC asc':>13s} {'MC→9H desc':>12s} {'9H→IC bot':>12s}")
    for b in ("mega","big","mid","modest"):
        d = cycle_bands[b]
        total = sum(d.values())
        if total == 0: continue
        print(f"{b:<10s} {d['IC_to_3H_rising']:>6d}({100*d['IC_to_3H_rising']/total:5.1f}%) {d['3H_to_MC_ascending']:>6d}({100*d['3H_to_MC_ascending']/total:5.1f}%) {d['MC_to_9H_descending']:>5d}({100*d['MC_to_9H_descending']/total:5.1f}%) {d['9H_to_IC_bottom']:>5d}({100*d['9H_to_IC_bottom']/total:5.1f}%)")

    # ============================================================
    # KATE SILAS: Eclipses hitting IPO chart degrees
    # ============================================================
    print(f"\n{'='*100}")
    print("KATE SILAS: Recent eclipse hits on natal sensitive points (within 3°)")
    print(f"Sample of top mega-rally charts")
    print(f"{'='*100}")
    # Just show for top corpus names — current eclipses around bottoms
    for tk, ipo, bot, top, mult, speed, note in PARABOLIC_BOTTOMS:
        if mult < 50: continue  # mega/big only
        try:
            natal = compute_natal(ipo)
            # Find eclipses within 6 months of bottom
            for ed, elon, et in RECENT_ECLIPSES:
                ed_y, ed_m = int(ed[:4]), int(ed[5:7])
                mo_diff = (ed_y - bot[0]) * 12 + (ed_m - bot[1])
                if -6 <= mo_diff <= 6:
                    hits = eclipse_hits_natal(natal, ed, elon, max_orb=3)
                    if hits:
                        h_str = ", ".join(f"{h['planet']}{h['orb']:.1f}°" for h in hits)
                        print(f"  {tk:<8s} mult={mult:5d}× bot={bot[0]}-{bot[1]:02d} eclipse={ed} type={et} hits: {h_str}")
        except: pass

if __name__ == "__main__":
    main()
