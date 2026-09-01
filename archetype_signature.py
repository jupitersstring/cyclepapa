"""
Per-archetype signature extraction.

Theory: a chart's bottom signature depends on WHICH of its natal planets
is being activated. A tech IPO with heavy Aquarian natal planets bottoms
at different transits than a value stock with Taurean/Capricornian natal.

Classify each of 110 bottoms by:
  - Element dominance (fire/earth/air/water count of Sun,Moon,Merc,Ven,Mars,Jup)
  - Modality dominance (cardinal/fixed/mutable)
  - Sun element
  - Natal Pluto generation (Leo/Vir/Lib/Sco/Sag/Cap)
  - Primary outer-to-Sun aspect (which outer most affects the Sun)

Extract per-group signatures. Compare separation from baseline per-group.
"""
import math
import statistics as st
from collections import defaultdict
from bti_test import compute_natal
from bti_v6 import compute_bti_v6
from secular_bottoms_corpus import SECULAR_BOTTOMS

SIGNS = ["Ari","Tau","Gem","Can","Leo","Vir","Lib","Sco","Sag","Cap","Aqu","Pis"]
ELEMENTS = {0:"fire",4:"fire",8:"fire",  1:"earth",5:"earth",9:"earth",
            2:"air",6:"air",10:"air",    3:"water",7:"water",11:"water"}
MODALITY = {0:"card",3:"card",6:"card",9:"card",  1:"fix",4:"fix",7:"fix",10:"fix",
            2:"mut",5:"mut",8:"mut",11:"mut"}

def classify(natal):
    """Return dict of natal archetype features."""
    elem_ct = defaultdict(int)
    mode_ct = defaultdict(int)
    for p in ("Sun","Moon","Mercury","Venus","Mars","Jupiter"):
        s = natal[p]["sign"]
        elem_ct[ELEMENTS[s]] += 1
        mode_ct[MODALITY[s]] += 1
    elem_dom = max(elem_ct, key=elem_ct.get)
    mode_dom = max(mode_ct, key=mode_ct.get)
    sun_elem = ELEMENTS[natal["Sun"]["sign"]]
    sun_sign = SIGNS[natal["Sun"]["sign"]]
    pluto_sign = SIGNS[natal["Pluto"]["sign"]]
    # Primary outer-to-Sun aspect
    primary_outer = None
    best_orb = 999
    for outer in ("Saturn","Uranus","Neptune","Pluto"):
        for asp in (0, 90, 180, 120, 60):
            diff = abs((natal[outer]["lon"] - natal["Sun"]["lon"]) % 360 - asp)
            diff = min(diff, 360 - diff) if asp in (120,60) else diff
            if asp == 0 or asp == 180:
                d = min(abs((natal[outer]["lon"] - natal["Sun"]["lon"]) % 360),
                        abs((natal[outer]["lon"] - natal["Sun"]["lon"]) % 360 - 180))
            else:
                continue
        # Simpler: min orb to Sun across hard aspects
        best_to_this_outer = 999
        for asp in (0, 90, 180):
            o1 = abs((natal[outer]["lon"] - natal["Sun"]["lon"] - asp) % 360)
            o1 = min(o1, 360 - o1)
            best_to_this_outer = min(best_to_this_outer, o1)
        if best_to_this_outer < best_orb:
            best_orb = best_to_this_outer
            primary_outer = outer
    return {
        "elem_dom": elem_dom, "mode_dom": mode_dom,
        "sun_elem": sun_elem, "sun_sign": sun_sign,
        "pluto_sign": pluto_sign,
        "primary_outer": primary_outer, "primary_outer_orb": best_orb,
    }

def extract_state(natal, y, m):
    rep = compute_bti_v6(natal, y, m)
    return {k: rep[k] for k in ("P_max_24","P_now","p_ratio","dP3","R_now","dR",
                                 "I_near","I_fwd","burn_ratio","Gs","Ge","awakening")}

def main():
    print(f"Classifying {len(SECULAR_BOTTOMS)} bottoms by natal archetype...")
    classifications = []
    all_states = []
    all_quiet = []
    multiples = []
    names = []
    for tk, ipo, bot, top, mult, note in SECULAR_BOTTOMS:
        try:
            natal = compute_natal(ipo)
            cls = classify(natal)
            s = extract_state(natal, bot[0], bot[1])
            classifications.append(cls)
            all_states.append(s)
            multiples.append(mult)
            names.append(tk)
            for off in (-18, -12, 12, 18):
                y, m = bot[0], bot[1] + off
                while m <= 0: m += 12; y -= 1
                while m > 12: m -= 12; y += 1
                q = extract_state(natal, y, m)
                all_quiet.append((cls, q))
        except Exception as e:
            pass

    # ============================================================
    # Archetype distribution
    # ============================================================
    print(f"\n{'='*80}")
    print("ARCHETYPE DISTRIBUTION IN CORPUS")
    print(f"{'='*80}")
    for key in ("elem_dom","mode_dom","sun_elem","primary_outer"):
        c = defaultdict(int)
        for cls in classifications: c[cls[key]] += 1
        print(f"\n{key}:")
        for k, v in sorted(c.items(), key=lambda x:-x[1]):
            print(f"  {k:<10s} {v:3d}")

    # ============================================================
    # Per-element signatures
    # ============================================================
    print(f"\n{'='*100}")
    print("PER-ELEMENT SIGNATURE (p50) vs BASELINE (same-element quiet months)")
    print(f"{'='*100}")
    COMPONENTS = ["dP3","dR","I_near","p_ratio","P_max_24","awakening","burn_ratio","I_fwd","Gs","Ge"]

    # Split
    element_states = defaultdict(list)
    element_quiet = defaultdict(list)
    for cls, s in zip(classifications, all_states):
        element_states[cls["elem_dom"]].append(s)
    for cls, q in all_quiet:
        element_quiet[cls["elem_dom"]].append(q)

    # Print per-element signature
    print(f"\n{'Element':<8s} {'Comp':<12s} {'BotMed':>8s} {'QuietMed':>9s} {'Separ':>7s} {'n_bot':>5s}")
    all_seps = defaultdict(dict)
    for elem in ("fire","earth","air","water"):
        if not element_states[elem]: continue
        for c in COMPONENTS:
            bvals = [s[c] for s in element_states[elem]]
            qvals = [q[c] for q in element_quiet[elem]]
            if not bvals or not qvals: continue
            b = st.median(bvals); q = st.median(qvals)
            sep = (b - q) / max(abs(q), 0.1) if abs(q) > 0.01 or abs(b) > 0.01 else 0
            all_seps[elem][c] = sep
            marker = " ★★" if abs(sep) > 1.0 else (" ★" if abs(sep) > 0.5 else "")
            print(f"{elem:<8s} {c:<12s} {b:8.2f} {q:9.2f} {sep:+7.2f}  n={len(bvals)}{marker}")
        print()

    # ============================================================
    # Per-sun-element signatures (narrower grouping)
    # ============================================================
    print(f"\n{'='*100}")
    print("PER-SUN-ELEMENT signature — tighter grouping")
    print(f"{'='*100}")
    sun_states = defaultdict(list)
    sun_quiet = defaultdict(list)
    for cls, s in zip(classifications, all_states):
        sun_states[cls["sun_elem"]].append(s)
    for cls, q in all_quiet:
        sun_quiet[cls["sun_elem"]].append(q)
    print(f"\n{'SunElem':<8s} {'Comp':<12s} {'BotMed':>8s} {'QuietMed':>9s} {'Separ':>7s} {'n':>4s}")
    for elem in ("fire","earth","air","water"):
        if not sun_states[elem]: continue
        print(f"--- SUN in {elem.upper()} element  (n={len(sun_states[elem])}) ---")
        for c in COMPONENTS:
            bvals = [s[c] for s in sun_states[elem]]
            qvals = [q[c] for q in sun_quiet[elem]]
            if not bvals or not qvals: continue
            b = st.median(bvals); q = st.median(qvals)
            sep = (b - q) / max(abs(q), 0.1) if abs(q) > 0.01 or abs(b) > 0.01 else 0
            marker = " ★★" if abs(sep) > 1.0 else (" ★" if abs(sep) > 0.5 else "")
            if abs(sep) > 0.3:  # only show non-noise
                print(f"  {c:<12s} {b:8.2f} {q:9.2f} {sep:+7.2f}{marker}")

    # ============================================================
    # Per-primary-outer signatures
    # ============================================================
    print(f"\n{'='*100}")
    print("PER-PRIMARY-OUTER-TO-SUN signature")
    print(f"{'='*100}")
    outer_states = defaultdict(list)
    outer_quiet = defaultdict(list)
    for cls, s in zip(classifications, all_states):
        outer_states[cls["primary_outer"]].append(s)
    for cls, q in all_quiet:
        outer_quiet[cls["primary_outer"]].append(q)
    for outer in ("Saturn","Uranus","Neptune","Pluto"):
        if not outer_states[outer]: continue
        print(f"\n--- Primary outer = {outer}  (n={len(outer_states[outer])}) ---")
        for c in COMPONENTS:
            bvals = [s[c] for s in outer_states[outer]]
            qvals = [q[c] for q in outer_quiet[outer]]
            if not bvals or not qvals: continue
            b = st.median(bvals); q = st.median(qvals)
            sep = (b - q) / max(abs(q), 0.1) if abs(q) > 0.01 or abs(b) > 0.01 else 0
            marker = " ★★" if abs(sep) > 1.0 else (" ★" if abs(sep) > 0.5 else "")
            if abs(sep) > 0.3:
                print(f"  {c:<12s} {b:8.2f} {q:9.2f} {sep:+7.2f}{marker}")

    # ============================================================
    # AGGREGATE STRENGTH OF DISCRIMINATION PER GROUP
    # ============================================================
    print(f"\n{'='*100}")
    print("DISCRIMINATION STRENGTH PER GROUP (sum of |sep| across components)")
    print(f"{'='*100}")

    print(f"\nBy element dominance:")
    for elem in ("fire","earth","air","water"):
        if elem in all_seps:
            total = sum(abs(v) for v in all_seps[elem].values())
            print(f"  {elem:<8s} total |sep|={total:.2f}  n={len(element_states[elem])}")

    print(f"\nBy Sun element:")
    sun_seps = defaultdict(dict)
    for elem in ("fire","earth","air","water"):
        if not sun_states[elem]: continue
        for c in COMPONENTS:
            bvals = [s[c] for s in sun_states[elem]]
            qvals = [q[c] for q in sun_quiet[elem]]
            if not bvals or not qvals: continue
            b = st.median(bvals); q = st.median(qvals)
            sep = (b - q) / max(abs(q), 0.1) if abs(q) > 0.01 or abs(b) > 0.01 else 0
            sun_seps[elem][c] = sep
    for elem in ("fire","earth","air","water"):
        if elem in sun_seps:
            total = sum(abs(v) for v in sun_seps[elem].values())
            print(f"  Sun-{elem:<6s} total |sep|={total:.2f}  n={len(sun_states[elem])}")

    print(f"\nBy primary outer:")
    outer_seps = defaultdict(dict)
    for outer in ("Saturn","Uranus","Neptune","Pluto"):
        if not outer_states[outer]: continue
        for c in COMPONENTS:
            bvals = [s[c] for s in outer_states[outer]]
            qvals = [q[c] for q in outer_quiet[outer]]
            if not bvals or not qvals: continue
            b = st.median(bvals); q = st.median(qvals)
            sep = (b - q) / max(abs(q), 0.1) if abs(q) > 0.01 or abs(b) > 0.01 else 0
            outer_seps[outer][c] = sep
    for outer in ("Saturn","Uranus","Neptune","Pluto"):
        if outer in outer_seps:
            total = sum(abs(v) for v in outer_seps[outer].values())
            print(f"  {outer:<8s} total |sep|={total:.2f}  n={len(outer_states[outer])}")

    # Export per-archetype signatures
    import csv
    with open("/home/user/cyclepapa/data/archetype_signatures.csv","w",newline="") as f:
        w = csv.writer(f)
        w.writerow(["group_type","group","component","bot_median","quiet_median","separation","n"])
        for elem in ("fire","earth","air","water"):
            for c in COMPONENTS:
                if elem in element_states and element_states[elem]:
                    bvals = [s[c] for s in element_states[elem]]
                    qvals = [q[c] for q in element_quiet[elem]]
                    b=st.median(bvals); q=st.median(qvals)
                    sep = (b - q) / max(abs(q),0.1)
                    w.writerow(["elem_dom",elem,c,f"{b:.3f}",f"{q:.3f}",f"{sep:+.3f}",len(bvals)])
        for elem in ("fire","earth","air","water"):
            for c in COMPONENTS:
                if elem in sun_states and sun_states[elem]:
                    bvals = [s[c] for s in sun_states[elem]]
                    qvals = [q[c] for q in sun_quiet[elem]]
                    b=st.median(bvals); q=st.median(qvals)
                    sep = (b - q) / max(abs(q),0.1)
                    w.writerow(["sun_elem",elem,c,f"{b:.3f}",f"{q:.3f}",f"{sep:+.3f}",len(bvals)])
        for outer in ("Saturn","Uranus","Neptune","Pluto"):
            for c in COMPONENTS:
                if outer in outer_states and outer_states[outer]:
                    bvals = [s[c] for s in outer_states[outer]]
                    qvals = [q[c] for q in outer_quiet[outer]]
                    b=st.median(bvals); q=st.median(qvals)
                    sep = (b - q) / max(abs(q),0.1)
                    w.writerow(["primary_outer",outer,c,f"{b:.3f}",f"{q:.3f}",f"{sep:+.3f}",len(bvals)])
    print(f"\nExported: /home/user/cyclepapa/data/archetype_signatures.csv")

if __name__ == "__main__":
    main()
