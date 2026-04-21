"""
Extract per-CLASSICAL-archetype signatures and compare discrimination
strength vs v8's modern 'primary outer' classification.

Classical groupings tested:
  (1) Dorothian triplicity lord of sect light (Saturn/Venus/Sun)
  (2) Almuten figuris (most dignified planet)
  (3) Sect light element (fire/earth/air/water)
  (4) Jupiter-Saturn synodic phase at natal (Abu Ma'shar)
  (5) Transit NN position (McWhirter)
  (6) Mutation element (Earth era / Air era)
"""
import statistics as st
from collections import defaultdict
from bti_test import compute_natal
from bti_v6 import compute_bti_v6
from classical_archetype import classical_classify
from secular_bottoms_corpus import SECULAR_BOTTOMS

COMPONENTS = ["dP3","dR","awakening","I_near","p_ratio","P_max_24","I_fwd","burn_ratio"]

def extract_state(natal, y, m):
    r = compute_bti_v6(natal, y, m)
    return {k: r[k] for k in COMPONENTS}

def yx(y, m, off):
    mm, yy = m + off, y
    while mm <= 0: mm += 12; yy -= 1
    while mm > 12: mm -= 12; yy += 1
    return (yy, mm)

def main():
    print("Collecting state vectors for 110 bottoms + quiet months...")
    records = []  # list of (classification_dict, state_dict)
    quiet_records = []
    for tk, ipo, bot, top, mult, note in SECULAR_BOTTOMS:
        try:
            natal = compute_natal(ipo)
            cls = classical_classify(natal)
            s = extract_state(natal, bot[0], bot[1])
            records.append((cls, s))
            for off in (-18, -12, 12, 18):
                y, m = yx(bot[0], bot[1], off)
                q = extract_state(natal, y, m)
                quiet_records.append((cls, q))
        except Exception:
            pass
    print(f"  {len(records)} bottom records, {len(quiet_records)} quiet records")

    def compute_discrimination(group_fn, label):
        """For each group, compute per-component separation. Return total |sep|."""
        print(f"\n{'='*95}")
        print(f"GROUPING BY {label}")
        print(f"{'='*95}")
        groups_bot = defaultdict(list)
        groups_quiet = defaultdict(list)
        for cls, s in records:
            g = group_fn(cls)
            groups_bot[g].append(s)
        for cls, q in quiet_records:
            g = group_fn(cls)
            groups_quiet[g].append(q)
        group_totals = {}
        for g in sorted(groups_bot.keys()):
            bot_n = len(groups_bot[g]); q_n = len(groups_quiet[g])
            if bot_n < 5 or q_n < 5: continue
            print(f"\n  Group: {g}  (n_bot={bot_n}, n_quiet={q_n})")
            total_sep = 0
            sigs = {}
            for c in COMPONENTS:
                bvals = [s[c] for s in groups_bot[g]]
                qvals = [q[c] for q in groups_quiet[g]]
                b = st.median(bvals); q = st.median(qvals)
                sep = (b - q) / max(abs(q), 0.1) if (abs(q) > 0.01 or abs(b) > 0.01) else 0
                sigs[c] = (b, q, sep)
                total_sep += abs(sep)
                marker = " ★★" if abs(sep) > 1.0 else (" ★" if abs(sep) > 0.5 else "")
                if abs(sep) > 0.4:
                    print(f"    {c:<12s} bot={b:6.2f} quiet={q:6.2f} sep={sep:+6.2f}{marker}")
            group_totals[g] = total_sep
            # AUC within group
            p = w = 0
            for b in groups_bot[g]:
                for q in groups_quiet[g]:
                    for c in COMPONENTS[:2]:  # just dP3, dR for quick check
                        pass
            print(f"    total |sep| = {total_sep:.2f}")
        # Aggregate metric: weighted average by group size
        n_bot_total = sum(len(groups_bot[g]) for g in group_totals)
        weighted = sum(group_totals[g] * len(groups_bot[g]) for g in group_totals) / max(n_bot_total,1)
        print(f"\n  ** Weighted mean |sep| for {label}: {weighted:.2f} (n={n_bot_total}) **")
        return weighted

    # Test each classification scheme
    results = {}
    results["triplicity_lord_1"] = compute_discrimination(lambda c: c["triplicity_lord_1"], "Dorothian triplicity lord (sect light)")
    results["sect_light_elem"]   = compute_discrimination(lambda c: c["sect_light_elem"],   "Sect light element")
    results["almuten"]           = compute_discrimination(lambda c: c["almuten"],           "Almuten figuris (Ibn Ezra)")
    results["js_phase"]          = compute_discrimination(lambda c: c["js_phase"],          "Jupiter-Saturn synodic phase (Abu Ma'shar)")
    results["nn_category"]       = compute_discrimination(lambda c: c["nn_category"],       "North Node category (McWhirter)")
    results["mutation_elem"]     = compute_discrimination(lambda c: c["mutation_elem"],     "Great-conjunction mutation element (Abu Ma'shar)")

    # Composite
    def composite_key(c):
        return (c["triplicity_lord_1"], c["sect_light_elem"])
    results["trip+elem"] = compute_discrimination(composite_key, "Triplicity lord × sect-element")

    # Comparison with modern v8 classification
    from archetype_signature import classify as modern_classify
    modern_records = []
    modern_quiet = []
    for tk, ipo, bot, top, mult, note in SECULAR_BOTTOMS:
        try:
            natal = compute_natal(ipo)
            cls = modern_classify(natal)
            s = extract_state(natal, bot[0], bot[1])
            modern_records.append((cls, s))
            for off in (-18, -12, 12, 18):
                y, m = yx(bot[0], bot[1], off)
                q = extract_state(natal, y, m)
                modern_quiet.append((cls, q))
        except Exception: pass
    # Recompute for modern
    def compute_for_modern(group_fn, label):
        groups_bot = defaultdict(list); groups_quiet = defaultdict(list)
        for cls, s in modern_records:
            groups_bot[group_fn(cls)].append(s)
        for cls, q in modern_quiet:
            groups_quiet[group_fn(cls)].append(q)
        group_totals = {}
        for g in groups_bot:
            if len(groups_bot[g]) < 5 or len(groups_quiet[g]) < 5: continue
            t = 0
            for c in COMPONENTS:
                bvals = [s[c] for s in groups_bot[g]]
                qvals = [q[c] for q in groups_quiet[g]]
                b = st.median(bvals); q = st.median(qvals)
                sep = (b - q) / max(abs(q), 0.1) if (abs(q) > 0.01 or abs(b) > 0.01) else 0
                t += abs(sep)
            group_totals[g] = t
        n = sum(len(groups_bot[g]) for g in group_totals)
        w = sum(group_totals[g] * len(groups_bot[g]) for g in group_totals) / max(n,1)
        return w, n
    modern_w, modern_n = compute_for_modern(lambda c: c["primary_outer"], "Modern: primary outer")
    results["modern_primary_outer"] = modern_w
    print(f"\n  Modern primary-outer weighted |sep|: {modern_w:.2f} (n={modern_n})")

    # Final ranking
    print(f"\n{'='*80}")
    print(f"DISCRIMINATION STRENGTH BY CLASSIFICATION SCHEME")
    print(f"{'='*80}")
    print(f"{'Scheme':<42s} {'weighted mean |sep|':>18s}")
    print("-"*80)
    for k, v in sorted(results.items(), key=lambda kv:-kv[1]):
        print(f"  {k:<42s} {v:>18.2f}")

if __name__ == "__main__":
    main()
