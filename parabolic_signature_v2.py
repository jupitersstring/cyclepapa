"""
Per-speed-class + per-archetype signature extraction on 152 parabolic bottoms.

Goal: find the specific trigger pattern for FAST (squeeze), MED (momentum),
SLOW (secular) parabolas, tailored to natal archetype.
"""
import statistics as st
import math
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

def extract_features(natal, eval_y, eval_m):
    """Full feature vector at a given date."""
    trans = transits_at(eval_y, eval_m)
    f = {}
    # 1. Transit outer-to-natal-Sun hard orbs (closest per outer)
    for outer in ("Jupiter","Saturn","Uranus","Neptune","Pluto"):
        r = closest_hard(trans[outer]["lon"], natal["Sun"]["lon"], 12)
        f[f"{outer[:3]}_Sun"] = r[1] if r else 99
        f[f"{outer[:3]}_Sun_asp"] = r[0] if r else -1
    # 2. Transit outer-to-natal-Moon hard orbs
    for outer in ("Jupiter","Saturn","Uranus","Neptune","Pluto"):
        r = closest_hard(trans[outer]["lon"], natal["Moon"]["lon"], 12)
        f[f"{outer[:3]}_Moon"] = r[1] if r else 99
    # 3. Stack count — # outers within 5° of natal Sun (all hard aspects)
    f["stack_sun"] = sum(1 for outer in ("Jupiter","Saturn","Uranus","Neptune","Pluto")
                         if f[f"{outer[:3]}_Sun"] <= 5)
    f["stack_moon"] = sum(1 for outer in ("Jupiter","Saturn","Uranus","Neptune","Pluto")
                          if f[f"{outer[:3]}_Moon"] <= 5)
    # 4. Transit JS synodic state
    js_diff = (trans["Jupiter"]["lon"] - trans["Saturn"]["lon"]) % 360
    f["tr_js_diff"] = js_diff
    # 5. Transit JU state
    f["tr_ju_diff"] = (trans["Jupiter"]["lon"] - trans["Uranus"]["lon"]) % 360
    # 6. Retrograde counts
    f["n_retro"] = sum(1 for p in ("Mercury","Venus","Mars","Jupiter","Saturn","Uranus","Neptune","Pluto")
                       if trans[p]["retro"])
    # 7. Transit Nodes position (McWhirter)
    f["nn_sign"] = int(trans["NN"]["lon"] // 30)
    # 8. Transit Mars retro flag
    f["mars_retro"] = 1 if trans["Mars"]["retro"] else 0
    # 9. Age of chart at evaluation (years)
    ipo_y = int(natal.get("_date", "2000")[:4])
    f["chart_age"] = eval_y - ipo_y
    return f

def main():
    print(f"Corpus: {len(PARABOLIC_BOTTOMS)} parabolic bottoms")
    bottoms = []
    for tk, ipo, bot, top, mult, speed, note in PARABOLIC_BOTTOMS:
        try:
            natal = compute_natal(ipo)
            cls = classical_classify(natal)
            f = extract_features(natal, bot[0], bot[1])
            bottoms.append({"tk":tk, "ipo":ipo, "bot":bot, "mult":mult, "speed":speed,
                           "cls":cls, "features":f})
        except Exception:
            pass
    print(f"  Extracted {len(bottoms)}")

    # Quiet baseline
    quiet = []
    for rec in bottoms:
        for off in (-18, -12, 12, 18):
            y, m = yx(rec["bot"][0], rec["bot"][1], off)
            try:
                natal = compute_natal(rec["ipo"])
                f = extract_features(natal, y, m)
                quiet.append(f)
            except Exception: pass
    print(f"  Quiet baseline: {len(quiet)}")

    # ============================================================
    # (A) FEATURES that DISCRIMINATE bottoms from quiet (overall)
    # ============================================================
    FEATURE_KEYS = [f"{p}_Sun" for p in ("Jup","Sat","Ura","Nep","Plu")] + \
                   [f"{p}_Moon" for p in ("Jup","Sat","Ura","Nep","Plu")] + \
                   ["stack_sun","stack_moon","n_retro","mars_retro"]

    print(f"\n{'='*100}")
    print("FEATURE DISCRIMINATION: bottoms vs quiet (all 152 parabolic bottoms)")
    print(f"{'='*100}")
    print(f"{'Feature':<16s} {'BotMed':>7s} {'QuietMed':>9s} {'Separ':>7s} {'%≤5':>6s}")
    print("-"*70)
    for k in FEATURE_KEYS:
        bvals = [b["features"][k] for b in bottoms]
        qvals = [q[k] for q in quiet]
        bm = st.median(bvals); qm = st.median(qvals)
        # For orb-type features, want LOWER at bottoms
        if k.endswith("Sun") or k.endswith("Moon"):
            # Pct with orb ≤ 5 at bottom vs quiet
            bpct = 100*sum(1 for v in bvals if v <= 5)/len(bvals)
            qpct = 100*sum(1 for v in qvals if v <= 5)/len(qvals)
            sep = bpct - qpct
            print(f"  {k:<14s} {bm:7.2f} {qm:9.2f} sep_pct={sep:+5.1f}%  bot≤5:{bpct:4.1f}%  q≤5:{qpct:4.1f}%")
        else:
            sep = (bm - qm) / max(abs(qm), 0.1)
            print(f"  {k:<14s} {bm:7.2f} {qm:9.2f} sep={sep:+7.2f}")

    # ============================================================
    # (B) Per-SPEED class signatures
    # ============================================================
    print(f"\n{'='*100}")
    print("PER-SPEED-CLASS SIGNATURE")
    print(f"{'='*100}")
    for speed in ("FAST","MED","SLOW"):
        subset = [b for b in bottoms if b["speed"] == speed]
        if not subset: continue
        print(f"\n--- {speed}  (n={len(subset)}) ---")
        # Compute outer-Sun hit distribution
        print(f"  Outer-to-natal-Sun hits within 5° orb:")
        for outer in ("Jup","Sat","Ura","Nep","Plu"):
            k = f"{outer}_Sun"
            pct = 100*sum(1 for b in subset if b["features"][k] <= 5)/len(subset)
            pct_q = 100*sum(1 for q in quiet if q[k] <= 5)/len(quiet)
            marker = "★★" if pct - pct_q > 10 else ("★" if pct - pct_q > 5 else "")
            print(f"    {k:<10s} bot:{pct:5.1f}%  quiet:{pct_q:5.1f}%  diff:{pct-pct_q:+5.1f}%  {marker}")
        # Stack distribution
        bstack = [b["features"]["stack_sun"] for b in subset]
        qstack = [q["stack_sun"] for q in quiet]
        print(f"  Stack-on-Sun (# outers): bot mean={st.mean(bstack):.2f}  bot≥2:{100*sum(1 for s in bstack if s>=2)/len(bstack):.1f}%  quiet≥2:{100*sum(1 for s in qstack if s>=2)/len(qstack):.1f}%")
        # Chart age
        ages = [b["features"]["chart_age"] for b in subset]
        print(f"  Chart age: median={st.median(ages):.1f}y  {'young' if st.median(ages) < 10 else 'mature'}")
        # Sun-sign distribution
        sc = defaultdict(int)
        for b in subset:
            natal = compute_natal(b["ipo"])
            sc[SIGNS[natal["Sun"]["sign"]]] += 1
        top3 = sorted(sc.items(), key=lambda x:-x[1])[:5]
        print(f"  Sun sign top: {top3}")
        # McWhirter NN
        nn = defaultdict(int)
        for b in subset:
            nn[b["cls"]["nn_category"]] += 1
        print(f"  NN category: {dict(nn)}")
        # JS phase
        jsp = defaultdict(int)
        for b in subset:
            jsp[b["cls"]["js_phase"]] += 1
        print(f"  JS phase:    {dict(jsp)}")

    # ============================================================
    # (C) Per-MAGNITUDE-BAND analysis
    # ============================================================
    print(f"\n{'='*100}")
    print("PER-MAGNITUDE-BAND: what distinguishes bigger rallies?")
    print(f"{'='*100}")
    bins = [(3,10),(10,30),(30,100),(100,999)]
    band_labels = ["3-9×","10-29×","30-99×","100×+"]
    for (lo,hi), label in zip(bins, band_labels):
        subset = [b for b in bottoms if lo <= b["mult"] < hi]
        if not subset: continue
        print(f"\n--- {label} (n={len(subset)}) ---")
        # Chart age
        ages = [b["features"]["chart_age"] for b in subset]
        print(f"  Chart age: median={st.median(ages):.1f}y  p25={sorted(ages)[len(ages)//4]:.0f}  p75={sorted(ages)[3*len(ages)//4]:.0f}")
        # Stack
        stacks = [b["features"]["stack_sun"] for b in subset]
        print(f"  Stack-Sun mean: {st.mean(stacks):.2f}  stack≥2: {100*sum(1 for s in stacks if s>=2)/len(stacks):.1f}%")
        # % with each outer ≤ 5° of Sun
        for outer in ("Sat","Ura","Nep","Plu"):
            pct = 100*sum(1 for b in subset if b["features"][f"{outer}_Sun"]<=5)/len(subset)
            print(f"  {outer}-Sun ≤5°: {pct:5.1f}%")
        # % with NN in bull zones
        nn_bull = sum(1 for b in subset if b["cls"]["nn_category"] in ("bottom_zone","setup_zone","launch_zone"))
        print(f"  NN in bullish zone: {100*nn_bull/len(subset):.1f}%")

    # Export
    import csv
    with open("/home/user/cyclepapa/data/parabolic_corpus_features.csv","w",newline="") as f:
        w = csv.writer(f)
        w.writerow(["ticker","ipo","bot_y","bot_m","mult","speed","chart_age",
                    "js_phase","almuten","nn_cat","sect_elem",
                    "Jup_Sun","Sat_Sun","Ura_Sun","Nep_Sun","Plu_Sun",
                    "Jup_Moon","Sat_Moon","Ura_Moon","Nep_Moon","Plu_Moon",
                    "stack_sun","stack_moon","n_retro"])
        for b in bottoms:
            feat = b["features"]; cls = b["cls"]
            w.writerow([b["tk"], b["ipo"], b["bot"][0], b["bot"][1], b["mult"], b["speed"],
                        feat["chart_age"], cls["js_phase"], cls["almuten"], cls["nn_category"],
                        cls["sect_light_elem"],
                        f"{feat['Jup_Sun']:.1f}",f"{feat['Sat_Sun']:.1f}",f"{feat['Ura_Sun']:.1f}",
                        f"{feat['Nep_Sun']:.1f}",f"{feat['Plu_Sun']:.1f}",
                        f"{feat['Jup_Moon']:.1f}",f"{feat['Sat_Moon']:.1f}",f"{feat['Ura_Moon']:.1f}",
                        f"{feat['Nep_Moon']:.1f}",f"{feat['Plu_Moon']:.1f}",
                        feat["stack_sun"], feat["stack_moon"], feat["n_retro"]])
    print(f"\nExported feature matrix: /home/user/cyclepapa/data/parabolic_corpus_features.csv")

if __name__ == "__main__":
    main()
