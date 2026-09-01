"""
Per-ALMUTEN-conditional signature extraction.

Test whether the parabolic/secular bottom signature varies by chart ruler
(almuten figuris). Theoretical rationale:
  - Venus-ruled chart: triggered by Venus-adjacent transits + Pluto-Sun
  - Saturn-ruled chart: triggered by Saturn cycle events (return, station)
  - Sun-ruled chart: triggered by solar arc / eclipse on natal
  - Mercury-ruled chart: triggered by Mercury stations + outer on luminary
  - Mars-ruled chart: triggered by Mars stations / Pluto conj Sun
  - Jupiter-ruled chart: triggered by Jupiter ingress / return

Per-ruler signature: for bottoms where almuten=X, which specific outer-hit
pattern is elevated above quiet-month baseline?
"""
import math, statistics as st
from collections import defaultdict
from bti_test import compute_natal, transits_at
from bti_v4 import yx
from classical_archetype import classical_classify
from parabolic_corpus import PARABOLIC_BOTTOMS

SIGNS = ["Ari","Tau","Gem","Can","Leo","Vir","Lib","Sco","Sag","Cap","Aqu","Pis"]

def orb(a, b):
    d = abs((a - b) % 360)
    return min(d, 360 - d)

def closest_hard(a, b, max_orb=10):
    best = None
    for asp in (0, 90, 180):
        for sign in (+1, -1):
            o = orb(a, b + sign * asp)
            if o <= max_orb and (best is None or o < best[1]):
                best = (asp, o)
    return best

def extract_full_state(natal, eval_y, eval_m):
    """Full feature set: transit outer to natal Sun, Moon, AND Almuten planet."""
    trans = transits_at(eval_y, eval_m)
    cls = classical_classify(natal)
    almuten = cls["almuten"]
    # Outer to Sun, Moon, Almuten planet's natal position
    f = {}
    natal_lon = {"Sun": natal["Sun"]["lon"], "Moon": natal["Moon"]["lon"]}
    if almuten in natal:
        natal_lon["Almuten"] = natal[almuten]["lon"]
    for target_name, target_lon in natal_lon.items():
        for outer in ("Jupiter","Saturn","Uranus","Neptune","Pluto"):
            r = closest_hard(trans[outer]["lon"], target_lon, 12)
            f[f"{outer[:3]}_{target_name}"] = r[1] if r else 99
    # Transit Venus and Mars to natal Sun (for fast triggers)
    for fast in ("Venus","Mars","Mercury"):
        r = closest_hard(trans[fast]["lon"], natal["Sun"]["lon"], 6)
        f[f"{fast[:3]}_Sun"] = r[1] if r else 99
    # Transit to natal Almuten planet more specifically
    if almuten in natal:
        for fast in ("Venus","Mars","Mercury","Jupiter"):
            r = closest_hard(trans[fast]["lon"], natal[almuten]["lon"], 6)
            f[f"{fast[:3]}_Alm"] = r[1] if r else 99
    return f, cls, almuten

def main():
    # Process all bottoms + quiet
    per_almuten_bot = defaultdict(list)
    per_almuten_quiet = defaultdict(list)
    per_almuten_mult = defaultdict(list)
    for tk, ipo, bot, top, mult, speed, note in PARABOLIC_BOTTOMS:
        try:
            natal = compute_natal(ipo)
            f, cls, alm = extract_full_state(natal, bot[0], bot[1])
            per_almuten_bot[alm].append({"tk":tk, "mult":mult, "speed":speed, "f":f})
            per_almuten_mult[alm].append(mult)
            for off in (-18, -12, 12, 18):
                y, m = yx(bot[0], bot[1], off)
                fq, _, _ = extract_full_state(natal, y, m)
                per_almuten_quiet[alm].append(fq)
        except Exception:
            pass

    # Per-almuten signature
    print(f"{'='*110}")
    print("PER-ALMUTEN PARABOLIC SIGNATURES (152-bottom corpus)")
    print(f"{'='*110}")
    for alm in ("Venus","Sun","Mercury","Saturn","Mars","Jupiter","Moon"):
        bots = per_almuten_bot[alm]
        quiets = per_almuten_quiet[alm]
        if len(bots) < 5: continue
        print(f"\n--- Almuten = {alm}  (n_bot={len(bots)}, n_quiet={len(quiets)}) ---")
        print(f"  Mean rally mult: {st.mean(per_almuten_mult[alm]):.0f}×  median: {st.median(per_almuten_mult[alm]):.0f}×")
        # % of bot with each outer-Sun ≤ 5° vs quiet
        print(f"  Outer hits at BOT vs QUIET (%≤5°):")
        top_signals = []
        for outer in ("Jup","Sat","Ura","Nep","Plu"):
            for target in ("Sun","Moon","Almuten"):
                k = f"{outer}_{target}"
                bvals = [b["f"].get(k, 99) for b in bots]
                qvals = [q.get(k, 99) for q in quiets]
                bpct = 100*sum(1 for v in bvals if v <= 5)/len(bvals)
                qpct = 100*sum(1 for v in qvals if v <= 5)/max(len(quiets),1)
                diff = bpct - qpct
                top_signals.append((k, bpct, qpct, diff))
        top_signals.sort(key=lambda x:-x[3])
        for k, b, q, d in top_signals[:6]:
            marker = "★★" if d > 10 else ("★" if d > 5 else "")
            if d > 2:
                print(f"    {k:<14s} bot:{b:5.1f}%  quiet:{q:5.1f}%  diff:{d:+5.1f}%  {marker}")
        # Fast-planet triggers
        print(f"  Fast-planet hits to Sun (%≤3°):")
        for fast in ("Ven","Mar","Mer"):
            k = f"{fast}_Sun"
            bvals = [b["f"].get(k, 99) for b in bots]
            qvals = [q.get(k, 99) for q in quiets]
            bpct = 100*sum(1 for v in bvals if v <= 3)/len(bvals)
            qpct = 100*sum(1 for v in qvals if v <= 3)/max(len(quiets),1)
            diff = bpct - qpct
            if diff > 2:
                print(f"    {k:<10s} bot:{bpct:5.1f}%  quiet:{qpct:5.1f}%  diff:{diff:+5.1f}%")
        # Fast to almuten
        print(f"  Fast-planet hits to Almuten natal position (%≤3°):")
        for fast in ("Ven","Mar","Mer","Jup"):
            k = f"{fast}_Alm"
            bvals = [b["f"].get(k, 99) for b in bots]
            qvals = [q.get(k, 99) for q in quiets]
            if not bvals: continue
            bpct = 100*sum(1 for v in bvals if v <= 3)/len(bvals)
            qpct = 100*sum(1 for v in qvals if v <= 3)/max(len(quiets),1)
            diff = bpct - qpct
            if diff > 2:
                print(f"    {k:<10s} bot:{bpct:5.1f}%  quiet:{qpct:5.1f}%  diff:{diff:+5.1f}%")

    # Export
    import csv
    with open("/home/user/cyclepapa/data/almuten_conditional_signatures.csv","w",newline="") as f:
        w = csv.writer(f)
        w.writerow(["almuten","n_bot","feature","bot_pct","quiet_pct","separation"])
        for alm in ("Venus","Sun","Mercury","Saturn","Mars","Jupiter","Moon"):
            bots = per_almuten_bot[alm]
            quiets = per_almuten_quiet[alm]
            if not bots or not quiets: continue
            for outer in ("Jup","Sat","Ura","Nep","Plu"):
                for target in ("Sun","Moon","Almuten"):
                    k = f"{outer}_{target}"
                    bvals = [b["f"].get(k, 99) for b in bots]
                    qvals = [q.get(k, 99) for q in quiets]
                    bpct = 100*sum(1 for v in bvals if v <= 5)/len(bvals)
                    qpct = 100*sum(1 for v in qvals if v <= 5)/max(len(quiets),1)
                    w.writerow([alm, len(bots), k, f"{bpct:.1f}", f"{qpct:.1f}", f"{bpct-qpct:+.1f}"])
    print(f"\nExported per-almuten signatures: /home/user/cyclepapa/data/almuten_conditional_signatures.csv")

if __name__ == "__main__":
    main()
