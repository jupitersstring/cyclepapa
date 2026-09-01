"""
NATAL HARMONIC TEST — Does natal-chart geometry predict parabolic susceptibility?

Compares natal-natal harmonic-aspect activations between:
  GROUP A: 152 parabolic-bottom cases (PARABOLIC_BOTTOMS)
  GROUP B: 300+ random non-parabolic IPOs from same Ritter universe

For each pair of natal planets and each harmonic aspect, count what
fraction of charts have the pair within 3° of that aspect.

If parabolic charts show a meaningfully higher rate of certain natal
configurations, those are "predisposing" patterns — they don't predict
TIMING but predict CHART SUSCEPTIBILITY to big moves.

Tests:
  - Sun-Neptune at 0° (AVIS-DNA conjunction)
  - Mars-Jupiter at 1.272 (98°) — Butterfly natal
  - Jupiter-Uranus at 0.786 (77°) — Gartley natal
  - Saturn-Neptune at 0.886 (41°) — Bat natal
  - Sun-Pluto at 0.886 — transformative natal
  - Outer-outer septile 51.4° — fated natal
  - All harmonic angles tested across all luminary/angle/outer pairs
"""
import math, csv, random
import statistics as st
from collections import defaultdict
from bti_test import compute_natal
from parabolic_corpus import PARABOLIC_BOTTOMS

PLANETS = ("Sun","Moon","ASC","MC","Mercury","Venus","Mars","Jupiter","Saturn","Uranus","Neptune","Pluto")
INNER = ("Sun","Moon","Mercury","Venus","Mars","ASC","MC")
OUTER = ("Jupiter","Saturn","Uranus","Neptune","Pluto")

HARMONIC = {
    "CONJ_0":         0.0,
    "0.886 (Bat)":    41.04,
    "Septile_51":     51.43,
    "Sextile_60":     60.0,
    "Quintile_72":    72.0,
    "0.786 (Gart)":   77.04,
    "SQ_90":          90.0,
    "1.272 (Butt)":   97.92,
    "TriDec_108":     108.0,
    "Trine_120":      120.0,
    "Phi_137.5":      137.5,
    "Biquint_144":    144.0,
    "OPP_180":        180.0,
}

def aspect_orb(a, b, target):
    d = (a - b) % 360
    return min(abs(d - target), abs(d - (360 - target)))

def chart_has_natal_aspect(natal, p1, p2, target_deg, orb=3):
    if p1 not in natal or p2 not in natal: return False
    return aspect_orb(natal[p1]["lon"], natal[p2]["lon"], target_deg) <= orb

def main():
    # Group A: parabolic
    para_charts = []
    para_tk = set()
    for tk, ipo, bot, top, mult, speed, note in PARABOLIC_BOTTOMS:
        try:
            n = compute_natal(ipo)
            para_charts.append({"tk":tk,"ipo":ipo,"natal":n,"mult":mult})
            para_tk.add(tk)
        except: continue

    # Group B: random Ritter sample (NOT in parabolic corpus)
    baseline_charts = []
    with open("/home/user/cyclepapa/data/universe_bti_v20.csv") as f:
        all_rows = list(csv.DictReader(f))
    # Filter to Ritter source, not in parabolic corpus, age 1-50
    candidates = []
    for r in all_rows:
        tk = (r.get("ticker") or "").strip().upper()
        ipo = (r.get("ipo") or "").strip()
        src = (r.get("source") or "").strip()
        if src != "Ritter": continue
        if tk in para_tk: continue
        if not ipo or len(ipo)<10: continue
        try: y = int(ipo[:4])
        except: continue
        if y < 1975 or y > 2024: continue
        candidates.append({"tk":tk,"ipo":ipo})
    random.seed(7)
    random.shuffle(candidates)
    for c in candidates[:300]:
        try:
            n = compute_natal(c["ipo"])
            baseline_charts.append({"tk":c["tk"],"ipo":c["ipo"],"natal":n})
            if len(baseline_charts) >= 300: break
        except: continue

    NA = len(para_charts)
    NB = len(baseline_charts)
    print(f"Parabolic corpus: {NA} charts")
    print(f"Random baseline:  {NB} charts")

    # ============================================================
    # PART 1: Per-pair × per-aspect natal activation rate
    # ============================================================
    print(f"\n{'='*120}")
    print(f"NATAL ASPECT ACTIVATION — % of charts with natal aspect within 3°")
    print(f"  PARABOLIC (n={NA}) vs RANDOM (n={NB})")
    print(f"  Showing pairs where parabolic rate >= random + 4pp (or <= -4pp)")
    print(f"{'='*120}")

    findings = []
    pairs_tested = set()
    for asp_name, asp_deg in HARMONIC.items():
        for i, p1 in enumerate(PLANETS):
            for p2 in PLANETS[i+1:]:
                if (p1, p2) in pairs_tested and asp_deg == 0: continue
                a_hits = sum(1 for c in para_charts if chart_has_natal_aspect(c["natal"], p1, p2, asp_deg))
                b_hits = sum(1 for c in baseline_charts if chart_has_natal_aspect(c["natal"], p1, p2, asp_deg))
                a_pct = 100*a_hits/NA
                b_pct = 100*b_hits/NB
                lift = a_pct - b_pct
                if abs(lift) >= 4:
                    findings.append({
                        "asp":asp_name,"deg":asp_deg,"p1":p1,"p2":p2,
                        "para":a_pct,"base":b_pct,"lift":lift,
                        "para_n":a_hits,"base_n":b_hits
                    })

    findings.sort(key=lambda f: -abs(f["lift"]))
    print(f"\n  TOP 50 by absolute lift (parabolic vs random):")
    print(f"  {'Aspect':<14s} {'Pair':<22s} {'Para %':>7s} {'Rand %':>7s}  {'Lift':>7s}")
    for f in findings[:50]:
        pair = f"{f['p1'][:5]}-{f['p2'][:5]}"
        marker = " ★" if abs(f["lift"]) >= 8 else ""
        print(f"  {f['asp']:<14s} {pair:<22s} {f['para']:>6.1f}% {f['base']:>6.1f}%  {f['lift']:>+5.1f}pp{marker}")

    # ============================================================
    # PART 2: Aggregate by aspect — which harmonics distinguish parabolic charts?
    # ============================================================
    print(f"\n{'='*120}")
    print(f"AGGREGATE — # of pairs where parabolic > random by 5pp+ for each aspect")
    print(f"{'='*120}")
    for asp_name, asp_deg in HARMONIC.items():
        n_pos = sum(1 for f in findings if f["asp"]==asp_name and f["lift"]>=5)
        n_neg = sum(1 for f in findings if f["asp"]==asp_name and f["lift"]<=-5)
        if n_pos+n_neg == 0: continue
        print(f"  {asp_name:<14s} (±{asp_deg:>6.2f}°)  para-lifted: {n_pos}   random-lifted: {n_neg}")

    # ============================================================
    # PART 3: Magnitude correlation — within parabolic corpus,
    #   do bigger rallies have stronger natal harmonic activations?
    # ============================================================
    print(f"\n{'='*120}")
    print(f"WITHIN-PARABOLIC: do top harmonic configurations associate with BIGGER rallies?")
    print(f"  (Median rally for charts WITH the aspect vs WITHOUT)")
    print(f"{'='*120}")
    print(f"  {'Aspect':<14s} {'Pair':<22s} {'WITH median':>12s} {'WITHOUT med':>12s} {'Lift':>6s} {'WITH n':>6s}")
    for f in findings[:30]:
        with_charts = [c for c in para_charts if chart_has_natal_aspect(c["natal"], f["p1"], f["p2"], f["deg"])]
        without_charts = [c for c in para_charts if not chart_has_natal_aspect(c["natal"], f["p1"], f["p2"], f["deg"])]
        if len(with_charts) < 5: continue
        with_med = st.median([c["mult"] for c in with_charts])
        without_med = st.median([c["mult"] for c in without_charts])
        if with_med > 0 and without_med > 0:
            lift = with_med - without_med
            pair = f"{f['p1'][:5]}-{f['p2'][:5]}"
            marker = " ★" if abs(lift) >= 5 else ""
            print(f"  {f['asp']:<14s} {pair:<22s} {with_med:>11.1f}× {without_med:>11.1f}× {lift:>+5.1f}× {len(with_charts):>5d}{marker}")

    # ============================================================
    # PART 4: STELLIUM detection — chart with multiple planets clustered
    # ============================================================
    print(f"\n{'='*120}")
    print(f"STELLIUM DETECTION — charts with 4+ planets within 15° of each other")
    print(f"  Parabolic vs random baseline rate")
    print(f"{'='*120}")
    def max_stellium_size(natal, orb=15):
        positions = [natal[p]["lon"] for p in PLANETS if p in natal]
        best = 0
        for i, lon in enumerate(positions):
            count = sum(1 for x in positions if min(abs(x-lon), 360-abs(x-lon)) <= orb)
            if count > best: best = count
        return best
    for thr in (3, 4, 5, 6):
        a = sum(1 for c in para_charts if max_stellium_size(c["natal"]) >= thr)
        b = sum(1 for c in baseline_charts if max_stellium_size(c["natal"]) >= thr)
        a_pct = 100*a/NA; b_pct = 100*b/NB
        print(f"  ≥{thr} planets within 15°: PARA {a_pct:>5.1f}%   BASE {b_pct:>5.1f}%   lift {a_pct-b_pct:+5.1f}pp")

    # Magnitude correlation with stellium size
    print(f"\n  Within parabolic corpus — does stellium size predict rally magnitude?")
    by_size = defaultdict(list)
    for c in para_charts:
        s = max_stellium_size(c["natal"])
        by_size[s].append(c["mult"])
    print(f"  {'Stellium':>9s} {'n':>4s}  {'Mean':>6s} {'Med':>5s} {'Max':>6s}")
    for s in sorted(by_size):
        v = by_size[s]
        if len(v) < 3: continue
        print(f"  ≥{s:>3d}      {len(v):>4d}  {st.mean(v):>5.1f}× {st.median(v):>4.1f}× {max(v):>5.0f}×")

    # ============================================================
    # PART 5: Composite "natal harmonic score" — sum of activations
    # ============================================================
    print(f"\n{'='*120}")
    print(f"NATAL HARMONIC LOAD — total # of harmonic activations per chart")
    print(f"  (Counting hits across all (pair, harmonic-aspect) combinations within 3°)")
    print(f"{'='*120}")
    def harmonic_load(natal):
        n = 0
        for asp_name, asp_deg in HARMONIC.items():
            for i, p1 in enumerate(PLANETS):
                for p2 in PLANETS[i+1:]:
                    if chart_has_natal_aspect(natal, p1, p2, asp_deg, orb=3):
                        n += 1
        return n
    para_loads = [harmonic_load(c["natal"]) for c in para_charts]
    base_loads = [harmonic_load(c["natal"]) for c in baseline_charts]
    print(f"  Parabolic mean load: {st.mean(para_loads):.1f}  median: {st.median(para_loads):.0f}")
    print(f"  Random    mean load: {st.mean(base_loads):.1f}  median: {st.median(base_loads):.0f}")
    # Magnitude vs load within parabolic
    pairs = list(zip(para_loads, [c["mult"] for c in para_charts]))
    pairs.sort(key=lambda x:-x[0])
    high = pairs[:NA//3]
    low = pairs[2*NA//3:]
    print(f"  Top-tertile by load (n={len(high)}): mean mult {st.mean([m for l,m in high]):.1f}, med {st.median([m for l,m in high]):.1f}")
    print(f"  Bot-tertile by load (n={len(low)}):  mean mult {st.mean([m for l,m in low]):.1f}, med {st.median([m for l,m in low]):.1f}")

if __name__ == "__main__":
    main()
