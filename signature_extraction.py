"""
Extract empirical astrological signature at secular bottoms.

For each confirmed bottom, compute the full v6 state vector and
characterise the distribution. The median and quartiles define the
"bottom signature" — we then recalibrate v6 gates to maximally fire
on charts matching that signature.

Also computes a "subsequent-rally-magnitude" regression: which
component values at the bottom predict the multiple?
"""
import statistics as st
import math
from collections import defaultdict
from bti_test import compute_natal
from bti_v6 import compute_bti_v6, bti_window_v6
from secular_bottoms_corpus import SECULAR_BOTTOMS

# Component fields to extract
COMPONENTS = ["P_max_24", "P_now", "p_ratio", "dP3", "R_now", "dR", "awakening",
              "I_fwd", "I_near", "burn_ratio", "Gs", "Ge"]

def extract_state(natal, y, m):
    """Get the raw (pre-gate) state vector at (y, m)."""
    rep = compute_bti_v6(natal, y, m)
    return {c: rep[c] for c in COMPONENTS}

def main():
    print(f"Corpus size: {len(SECULAR_BOTTOMS)} secular bottoms")
    print("Extracting state vectors at each bottom...")

    # For each bottom, compute state at the bottom date (no window — pinpoint)
    states = []
    multiples = []
    names = []
    for tk, ipo, bot, top, mult, note in SECULAR_BOTTOMS:
        try:
            natal = compute_natal(ipo)
            s = extract_state(natal, bot[0], bot[1])
            states.append(s)
            multiples.append(mult)
            names.append((tk, bot, mult, note))
        except Exception as e:
            print(f"  SKIP {tk}: {e}")
    print(f"  extracted {len(states)} state vectors")

    # Extract signature: percentiles for each component
    print(f"\n{'='*80}")
    print(f"EMPIRICAL SIGNATURE AT SECULAR BOTTOMS (n={len(states)})")
    print(f"{'='*80}")
    print(f"{'Component':<14s} {'P05':>7s} {'P25':>7s} {'P50':>7s} {'P75':>7s} {'P95':>7s} {'mean':>7s} {'std':>6s}")
    print("-"*70)
    signature = {}
    for c in COMPONENTS:
        vals = sorted(s[c] for s in states)
        n = len(vals)
        def pct(p): return vals[min(n-1, int(p/100 * n))]
        mean = st.mean(vals)
        sd = st.stdev(vals) if len(vals) > 1 else 0
        signature[c] = {"p05": pct(5), "p25": pct(25), "p50": pct(50),
                        "p75": pct(75), "p95": pct(95), "mean": mean, "std": sd}
        print(f"{c:<14s} {pct(5):7.2f} {pct(25):7.2f} {pct(50):7.2f} {pct(75):7.2f} {pct(95):7.2f} {mean:7.2f} {sd:6.2f}")

    # Compare to "quiet month" distribution
    print(f"\n{'='*80}")
    print(f"QUIET-MONTH BASELINE (±12/±18 months from each bottom)")
    print(f"{'='*80}")
    quiet_states = []
    for tk, ipo, bot, top, mult, note in SECULAR_BOTTOMS:
        try:
            natal = compute_natal(ipo)
            for off in (-18, -12, +12, +18):
                y, m = bot[0], bot[1] + off
                while m <= 0: m += 12; y -= 1
                while m > 12: m -= 12; y += 1
                quiet_states.append(extract_state(natal, y, m))
        except Exception:
            pass

    print(f"{'Component':<14s} {'BotMed':>8s} {'QuietMed':>9s} {'Separation':>11s} {'Interpretation'}")
    print("-"*80)
    for c in COMPONENTS:
        b = signature[c]["p50"]
        q = st.median(s[c] for s in quiet_states)
        if abs(q) < 0.01 and abs(b) < 0.01:
            sep = 0
        else:
            sep = (b - q) / max(abs(q), 0.1)
        if abs(sep) > 0.5:
            interp = "STRONG signal" if sep > 0 else "NEG signal"
        elif abs(sep) > 0.2:
            interp = "weak signal"
        else:
            interp = "noise"
        print(f"{c:<14s} {b:8.2f} {q:9.2f} {sep:+11.2f}  {interp}")

    # Which components correlate with rally MAGNITUDE?
    print(f"\n{'='*80}")
    print(f"RALLY-MAGNITUDE PREDICTORS (log multiple)")
    print(f"{'='*80}")
    log_mults = [math.log(m) for m in multiples]
    print(f"  n={len(log_mults)}  log-mult mean={st.mean(log_mults):.2f}  std={st.stdev(log_mults):.2f}")

    def corr(xs, ys):
        if len(xs) < 2: return 0
        mx = st.mean(xs); my = st.mean(ys)
        num = sum((x-mx)*(y-my) for x,y in zip(xs,ys))
        denx = math.sqrt(sum((x-mx)**2 for x in xs))
        deny = math.sqrt(sum((y-my)**2 for y in ys))
        return num / (denx * deny) if denx*deny > 0 else 0

    print(f"{'Component':<14s} {'Pearson r':>10s} {'direction'}")
    print("-"*40)
    corrs = []
    for c in COMPONENTS:
        xs = [s[c] for s in states]
        r = corr(xs, log_mults)
        corrs.append((c, r))
    corrs.sort(key=lambda kv: -abs(kv[1]))
    for c, r in corrs:
        direction = "HIGHER → bigger rally" if r > 0 else "LOWER → bigger rally"
        marker = "★★" if abs(r) > 0.4 else "★" if abs(r) > 0.2 else ""
        print(f"{c:<14s} {r:+10.3f}  {direction}  {marker}")

    # Quartile analysis for rally prediction
    print(f"\n{'='*80}")
    print(f"RALLY-BY-COMPONENT-QUARTILE")
    print(f"{'='*80}")
    print("Split bottoms by component quartile, compare median rally multiple:")
    print(f"{'Component':<14s} {'Q1 med×':>8s} {'Q2 med×':>8s} {'Q3 med×':>8s} {'Q4 med×':>8s} {'Q4/Q1':>6s}")
    for c in COMPONENTS:
        sorted_states = sorted(zip(states, multiples), key=lambda sm: sm[0][c])
        n = len(sorted_states)
        q1 = sorted_states[:n//4]
        q2 = sorted_states[n//4:n//2]
        q3 = sorted_states[n//2:3*n//4]
        q4 = sorted_states[3*n//4:]
        if not q1 or not q4: continue
        m1 = st.median(m for _, m in q1)
        m2 = st.median(m for _, m in q2) if q2 else 0
        m3 = st.median(m for _, m in q3) if q3 else 0
        m4 = st.median(m for _, m in q4)
        ratio = m4 / max(m1, 0.1)
        print(f"{c:<14s} {m1:8.1f} {m2:8.1f} {m3:8.1f} {m4:8.1f} {ratio:6.2f}")

    # Print per-bottom detail for inspection
    print(f"\n{'='*90}")
    print(f"PER-BOTTOM DETAIL (sorted by rally multiple)")
    print(f"{'='*90}")
    zipped = sorted(zip(names, states, multiples), key=lambda z: -z[2])
    print(f"{'Tkr':<7s} {'BotMo':<8s} {'Mult':>5s} {'Pmx':>4s} {'p_r':>4s} {'dP3':>5s} {'awk':>4s} {'Ifw':>4s} {'Ine':>4s} {'burn':>4s} {'Gs':>4s}")
    for (tk, bot, mult, note), s, m in zipped:
        mo = f"{bot[0]}-{bot[1]:02d}"
        print(f"{tk:<7s} {mo:<8s} {m:5d} {s['P_max_24']:4.1f} {s['p_ratio']:4.2f} {s['dP3']:+5.2f} {s['awakening']:4.2f} {s['I_fwd']:4.1f} {s['I_near']:4.1f} {s['burn_ratio']:4.2f} {s['Gs']:4.2f}")

    # Export signature
    import csv
    with open("/home/user/cyclepapa/data/bottom_signature.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["component","p05","p25","p50","p75","p95","mean","std","corr_logmult"])
        corr_map = dict(corrs)
        for c in COMPONENTS:
            s = signature[c]
            w.writerow([c, f"{s['p05']:.3f}", f"{s['p25']:.3f}", f"{s['p50']:.3f}",
                        f"{s['p75']:.3f}", f"{s['p95']:.3f}", f"{s['mean']:.3f}",
                        f"{s['std']:.3f}", f"{corr_map[c]:+.3f}"])
    print(f"\nExported signature: /home/user/cyclepapa/data/bottom_signature.csv")
    return signature, corrs

if __name__ == "__main__":
    main()
