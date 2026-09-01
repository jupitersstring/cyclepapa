"""
BTI v8 — ARCHETYPE-CONDITIONAL signature matching.

Theory: each chart's bottom signature differs by its dominant outer-planet-to-Sun
aspect. Pluto-primary charts bottom differently than Neptune-primary charts.
v7's aggregate signature smoothed over these real differences.

For each candidate, classify by primary outer, then score against that
specific archetype's empirical signature.
"""
from __future__ import annotations
import math, statistics as st
import swisseph as swe
from bti_test import compute_natal, transits_at
from bti_v4 import gamma_survive, gamma_era, yx
from bti_v5 import pressure_v5, release_v5, ignition_at_v5
from archetype_signature import classify, extract_state
from bti_v6 import compute_bti_v6

# Archetype-conditional signatures from extraction (p25, p50, p75)
# From archetype_signature.py output, per primary outer (strongest grouping)
ARCHETYPE_SIGNATURES = {
    "Saturn": {
        "dP3":       (-0.33,  0.47,  1.03),
        "dR":        (-0.44,  0.11,  0.66),
        "awakening": ( 0.15,  0.23,  0.53),
        "I_near":    ( 0.27,  0.80,  1.36),
        "p_ratio":   ( 0.40,  0.58,  0.80),
        "P_max_24":  ( 2.90,  3.79,  4.51),
        "R_now":     ( 0.82,  1.65,  2.96),
        "I_fwd":     ( 0.15,  0.78,  1.51),
    },
    "Uranus": {
        "dP3":       (-0.47,  0.20,  0.86),
        "dR":        (-1.33, -0.17,  0.42),
        "awakening": ( 0.15,  0.15,  0.35),
        "I_near":    ( 0.26,  0.82,  1.33),
        "p_ratio":   ( 0.40,  0.58,  0.80),
        "P_max_24":  ( 2.90,  3.79,  4.51),
        "R_now":     ( 0.82,  1.65,  2.96),
        "I_fwd":     ( 0.15,  0.78,  1.51),
    },
    "Neptune": {
        "dP3":       (-0.29,  0.69,  1.32),
        "dR":        (-1.66, -0.40,  0.51),
        "awakening": ( 0.15,  0.15,  0.38),
        "I_near":    ( 0.25,  0.82,  1.28),
        "p_ratio":   ( 0.40,  0.58,  0.80),
        "P_max_24":  ( 2.90,  3.79,  4.51),
        "R_now":     ( 0.82,  1.65,  2.96),
        "I_fwd":     ( 0.15,  0.78,  1.51),
    },
    "Pluto": {
        "dP3":       (-0.42,  0.44,  1.12),
        "dR":        (-0.53,  0.48,  1.78),   # positive median!
        "awakening": ( 0.15,  0.39,  1.05),   # ELEVATED
        "I_near":    ( 0.28,  0.85,  1.41),
        "p_ratio":   ( 0.40,  0.58,  0.80),
        "P_max_24":  ( 2.90,  3.79,  4.51),
        "R_now":     ( 0.82,  1.65,  2.96),
        "I_fwd":     ( 0.15,  0.78,  1.51),
    },
}

# Weights per archetype (based on observed separation strength)
ARCHETYPE_WEIGHTS = {
    "Saturn":  {"dP3":3.0,"dR":2.0,"awakening":1.5,"I_near":1.2,"p_ratio":0.8,"P_max_24":0.5,"R_now":0.3,"I_fwd":0.5},
    "Uranus":  {"dP3":2.5,"dR":2.5,"awakening":0.8,"I_near":1.0,"p_ratio":0.8,"P_max_24":0.5,"R_now":0.3,"I_fwd":0.5},
    "Neptune": {"dP3":3.5,"dR":2.3,"awakening":0.8,"I_near":1.2,"p_ratio":0.8,"P_max_24":0.5,"R_now":0.3,"I_fwd":0.5},
    "Pluto":   {"dP3":3.0,"dR":3.5,"awakening":2.5,"I_near":1.3,"p_ratio":0.8,"P_max_24":0.5,"R_now":0.3,"I_fwd":0.5},
}

def _match_score(val, p25, p50, p75):
    if val is None: return 0.5
    iqr_lo = p50 - p25
    iqr_hi = p75 - p50
    if val >= p50:
        d = (val - p50) / max(iqr_hi, 0.01)
    else:
        d = (p50 - val) / max(iqr_lo, 0.01)
    if d <= 1.0: return 1.0 - 0.4 * d
    elif d <= 2.0: return 0.6 - 0.3 * (d - 1)
    elif d <= 3.0: return 0.3 - 0.15 * (d - 2)
    else: return max(0.0, 0.15 - 0.03 * (d - 3))

def compute_bti_v8(natal, eval_y, eval_m):
    # Classify chart
    cls = classify(natal)
    archetype = cls["primary_outer"]
    sig = ARCHETYPE_SIGNATURES[archetype]
    weights = ARCHETYPE_WEIGHTS[archetype]

    # Extract state (reuses v6's state computation)
    state = extract_state(natal, eval_y, eval_m)

    # Signature match weighted by archetype-specific weights
    total_weight = sum(weights.values())
    match_sum = 0.0
    comp_scores = {}
    for comp, w in weights.items():
        v = state.get(comp)
        if v is None or comp not in sig: continue
        p25, p50, p75 = sig[comp]
        m = _match_score(v, p25, p50, p75)
        comp_scores[comp] = m
        match_sum += m * w
    signature_match = match_sum / total_weight

    # Archetype-clean gate: only score well if chart is CLEANLY archetype-typed
    # (primary outer orb to Sun must be reasonable)
    orb = cls["primary_outer_orb"]
    if orb > 12: archetype_gate = 0.6   # weak primary — less confident
    elif orb > 8: archetype_gate = 0.8
    else: archetype_gate = 1.0

    # Pressure presence gate
    if state["P_max_24"] < 1.5: press_gate = 0.3
    elif state["P_max_24"] < 2.5: press_gate = 0.3 + 0.7 * (state["P_max_24"] - 1.5)
    else: press_gate = 1.0

    Gs = gamma_survive(natal); Ge = gamma_era(natal, eval_y)
    bti = signature_match * press_gate * archetype_gate * (Gs ** 0.8) * (Ge ** 0.5) * 10.0

    return {"bti": bti, "signature_match": signature_match, "archetype": archetype,
            "primary_orb": orb, "press_gate": press_gate, "archetype_gate": archetype_gate,
            **state, "Gs": Gs, "Ge": Ge, "components": comp_scores}

def bti_window_v8(natal, ey, em, half=2):
    best = None; best_off = 0
    for off in range(-half, half+1):
        y, m = yx(ey, em, off)
        rep = compute_bti_v8(natal, y, m)
        if best is None or rep["bti"] > best["bti"]:
            best = rep; best_off = off
    best["window_offset"] = best_off
    return best

if __name__ == "__main__":
    import csv, time
    from collections import defaultdict
    from secular_bottoms_corpus import SECULAR_BOTTOMS
    from bti_test import BOTTOMS as ORIG16

    # 1. Validation against 110-bottom corpus
    print("="*100)
    print("v8 VALIDATION — archetype-conditional, 110-bottom corpus")
    print("="*100)
    bot_scores = []
    quiet_scores = []
    by_arche = defaultdict(lambda: {"bot":[], "quiet":[]})
    for tk, ipo, bot, top, mult, note in SECULAR_BOTTOMS:
        try:
            natal = compute_natal(ipo)
            r = compute_bti_v8(natal, bot[0], bot[1])
            bot_scores.append(r["bti"])
            by_arche[r["archetype"]]["bot"].append(r["bti"])
            for off in (-18, -12, 12, 18):
                y, m = yx(bot[0], bot[1], off)
                rq = compute_bti_v8(natal, y, m)
                quiet_scores.append(rq["bti"])
                by_arche[rq["archetype"]]["quiet"].append(rq["bti"])
        except Exception:
            pass
    print(f"  Overall: bot n={len(bot_scores)} mean={st.mean(bot_scores):.2f}  quiet mean={st.mean(quiet_scores):.2f}")
    pairs = wins = 0
    for b in bot_scores:
        for q in quiet_scores:
            pairs += 1
            if b > q: wins += 1
    print(f"  AUC bot>quiet: {wins/pairs:.3f}")
    print(f"\nPer-archetype AUC:")
    for arche, d in by_arche.items():
        if not d["bot"] or not d["quiet"]: continue
        p = w = 0
        for b in d["bot"]:
            for q in d["quiet"]:
                p += 1
                if b > q: w += 1
        print(f"  {arche:<8s}  bot n={len(d['bot']):3d}  mean={st.mean(d['bot']):.2f}  quiet mean={st.mean(d['quiet']):.2f}  AUC={w/max(p,1):.3f}")

    # Tops comparison
    print(f"\nTops vs bottoms (orig16):")
    top_s = []; bot_s = []
    for tk, ipo, bot, top, mult, note in ORIG16:
        try:
            natal = compute_natal(ipo)
            top_s.append(compute_bti_v8(natal, top[0], top[1])["bti"])
            bot_s.append(compute_bti_v8(natal, bot[0], bot[1])["bti"])
        except: pass
    print(f"  Bottoms mean: {st.mean(bot_s):.2f}  Tops mean: {st.mean(top_s):.2f}  bot/top: {st.mean(bot_s)/max(st.mean(top_s),0.01):.2f}")

    # 2. SP500 scan
    print(f"\n{'='*120}")
    print("SP500 @ 2026-04 — v8 archetype-conditional")
    print(f"{'='*120}")
    sp500 = []
    with open("/home/user/cyclepapa/data/sp500_ipo_dates.csv") as f:
        sp500 = list(csv.DictReader(f))
    t0 = time.time()
    results = []
    for row in sp500:
        try:
            natal = compute_natal(row["ipo_date"])
            rep = bti_window_v8(natal, 2026, 4, half=2)
            results.append((row["ticker"], row["name"], row["sector"], row["ipo_date"], rep))
        except Exception:
            pass
    print(f"  Scanned {len(results)} in {time.time()-t0:.0f}s")
    results.sort(key=lambda r: -r[4]["bti"])

    # Load prev ranks
    v5_map = {}; v6_map = {}; v7_map = {}
    with open("/home/user/cyclepapa/data/sp500_bti_v5_apr2026.csv") as f:
        for r in csv.DictReader(f): v5_map[r["ticker"]] = float(r["bti_v5"])
    with open("/home/user/cyclepapa/data/sp500_bti_v6_apr2026.csv") as f:
        for r in csv.DictReader(f): v6_map[r["ticker"]] = float(r["bti_v6"])
    with open("/home/user/cyclepapa/data/sp500_bti_v7_apr2026.csv") as f:
        for r in csv.DictReader(f): v7_map[r["ticker"]] = float(r["bti_v7"])

    print(f"\n{'Rk':>3s} {'Tkr':<6s} {'Sec':<18s} {'Name':<26s} {'IPO':<11s} {'v8':>5s} {'arche':<7s} {'sig':>4s} {'dP3':>5s} {'dR':>5s} {'awk':>4s} {'Ine':>4s} {'v7':>5s} {'v6':>5s} {'v5':>5s}")
    for i, (tk, nm, sec, ipo, rep) in enumerate(results[:40], 1):
        print(f"{i:3d} {tk:<6s} {sec[:18]:<18s} {nm[:26]:<26s} {ipo:<11s} {rep['bti']:5.2f} {rep['archetype']:<7s} {rep['signature_match']:4.2f} {rep['dP3']:+5.2f} {rep['dR']:+5.2f} {rep['awakening']:4.2f} {rep['I_near']:4.1f} {v7_map.get(tk,0):5.1f} {v6_map.get(tk,0):5.1f} {v5_map.get(tk,0):5.1f}")

    print(f"\nDistribution: mean={st.mean(r[4]['bti'] for r in results):.2f}  median={st.median(r[4]['bti'] for r in results):.2f}  max={max(r[4]['bti'] for r in results):.2f}")

    # Archetype distribution of top 40
    print(f"\nArchetype in top 40 vs all 503:")
    a_top = defaultdict(int); a_all = defaultdict(int)
    for i, (_,_,_,_,rep) in enumerate(results):
        a_all[rep["archetype"]] += 1
        if i < 40: a_top[rep["archetype"]] += 1
    for a in ("Saturn","Uranus","Neptune","Pluto"):
        print(f"  {a:<8s}  top40: {a_top[a]:2d}/40  all503: {a_all[a]:3d}/503  overrep={a_top[a]/40 / max(a_all[a]/503,0.001):.2f}")

    # Export
    with open("/home/user/cyclepapa/data/sp500_bti_v8_apr2026.csv","w",newline="") as f:
        w = csv.writer(f)
        w.writerow(["rank","ticker","name","sector","ipo_date","bti_v8","archetype","primary_orb",
                    "signature_match","P_max_24","P_now","p_ratio","dP3","R_now","dR","awakening",
                    "I_near","I_fwd","burn_ratio","Gs","Ge","v5","v6","v7"])
        for i,(tk,nm,sec,ipo,rep) in enumerate(results,1):
            w.writerow([i,tk,nm,sec,ipo,f"{rep['bti']:.3f}",rep["archetype"],f"{rep['primary_orb']:.1f}",
                        f"{rep['signature_match']:.3f}",
                        f"{rep['P_max_24']:.2f}",f"{rep['P_now']:.2f}",f"{rep['p_ratio']:.2f}",
                        f"{rep['dP3']:+.2f}",f"{rep['R_now']:.2f}",f"{rep['dR']:+.2f}",
                        f"{rep['awakening']:.2f}",f"{rep['I_near']:.2f}",f"{rep['I_fwd']:.2f}",
                        f"{rep['burn_ratio']:.2f}",f"{rep['Gs']:.2f}",f"{rep['Ge']:.2f}",
                        f"{v5_map.get(tk,0):.1f}",f"{v6_map.get(tk,0):.1f}",f"{v7_map.get(tk,0):.1f}"])
    print(f"\nExported: /home/user/cyclepapa/data/sp500_bti_v8_apr2026.csv")
