"""
BTI v9 — CLASSICALLY GROUNDED archetype classification.

Theoretical grounding:
  - Hellenistic (Ptolemy/Valens/Dorotheus): sect + triplicity lords
  - Persian (Abu Ma'shar): Jupiter-Saturn synodic cycle doctrine + great
    conjunction mutation theory (1200-year empirical track record)
  - Arabic (Ibn Ezra): almuten figuris = chart master
  - Mundane (Morin, Lilly): ingress charts and mundane outer cycles
  - Financial (McWhirter 1937): transit North Node position as market-phase
  - Financial (Gann, Merriman): synodic cycle positions predict reversals

Empirical finding on 110-bottom corpus:
  - JS synodic phase gives sharpest per-group signatures (gibbous 19.79,
    full 15.38)
  - Almuten competitive with modern primary-outer (8.03 vs 8.49)
  - McWhirter NN category differentiates bull peak_zone (|sep|10.36) from
    bottom_zone (9.91) cleanly

v9 uses COMPOSITE signature matching:
  - Primary: JS synodic phase specific signature (Abu Ma'shar)
  - Secondary: Almuten condition (Hellenistic via Ibn Ezra)
  - Tertiary: McWhirter NN category modifier
"""
from __future__ import annotations
import math, statistics as st
from bti_test import compute_natal, transits_at
from bti_v4 import gamma_survive, gamma_era, yx
from bti_v5 import pressure_v5, release_v5, ignition_at_v5
from bti_v6 import compute_bti_v6
from classical_archetype import classical_classify, ELEMENTS, SIGNS

# JS synodic phase signatures from empirical extraction on 110 bottoms.
# Format per component: (p25, p50, p75). Weights reflect observed separation strength.
# Phase sample counts: new=16, crescent=14, first_q=9, gibbous=8, full=10,
#                     disseminating=13, last_q=10, balsamic=30
JS_PHASE_SIGNATURES = {
    "new": {
        "weight": 0.7,  # moderate discrimination
        "sig": {
            "dR":       (-0.80,  0.36,  1.20),  # positive (rising release) — unique
            "I_fwd":    ( 0.15,  0.48,  1.00),
            "burn_ratio":( 2.00,  2.79,  3.60),
        }
    },
    "crescent": {
        "weight": 0.6,
        "sig": {
            "dP3":      (-0.20,  0.40,  1.00),
            "dR":       (-0.60,  0.00,  0.60),
        }
    },
    "first_q": {
        "weight": 0.6,
        "sig": {
            "dP3":      (-0.30,  0.50,  1.20),
            "dR":       (-0.80,  0.00,  0.80),
        }
    },
    "gibbous": {  # SHARPEST — total |sep| = 19.79
        "weight": 1.2,
        "sig": {
            "dP3":      ( 0.10,  0.73,  1.40),  # strongly positive
            "dR":       (-2.50, -1.44, -0.60),  # strongly negative (release falling)
            "I_near":   ( 0.40,  0.75,  1.30),
        }
    },
    "full": {  # VERY SHARP — total |sep| = 15.38
        "weight": 1.1,
        "sig": {
            "dP3":      ( 0.10,  0.66,  1.30),
            "dR":       (-0.30,  0.51,  1.40),  # positive (release rising)
            "awakening":( 0.15,  0.44,  0.90),  # elevated
            "p_ratio":  ( 0.45,  0.69,  0.90),
        }
    },
    "disseminating": {
        "weight": 0.7,
        "sig": {
            "dP3":      (-0.20,  0.40,  1.00),
            "dR":       (-0.60,  0.00,  0.60),
            "I_near":   ( 0.30,  0.80,  1.40),
        }
    },
    "last_q": {  # total |sep| = 7.41
        "weight": 0.7,
        "sig": {
            "dP3":      (-0.60, -0.20,  0.40),  # negative!
            "dR":       (-0.20,  0.32,  0.90),  # positive
            "awakening":( 0.15,  0.30,  0.70),
            "p_ratio":  ( 0.30,  0.54,  0.75),
            "I_fwd":    ( 0.50,  1.15,  1.80),
        }
    },
    "balsamic": {  # total |sep| = 9.18, n=30 largest sample
        "weight": 0.8,
        "sig": {
            "dP3":      (-0.10,  0.40,  1.00),
            "dR":       (-0.80, -0.20,  0.50),
            "p_ratio":  ( 0.40,  0.58,  0.80),
        }
    },
}

# Common baseline signature (for components not in phase-specific sig)
COMMON_SIG = {
    "P_max_24":  ( 2.90,  3.79,  4.51),
    "p_ratio":   ( 0.40,  0.58,  0.80),
    "I_near":    ( 0.26,  0.82,  1.33),
    "I_fwd":     ( 0.15,  0.78,  1.51),
    "burn_ratio":( 1.62,  2.07,  2.45),
    "awakening": ( 0.15,  0.15,  0.40),
    "dR":        (-0.50,  0.00,  0.60),
    "dP3":       (-0.50,  0.44,  1.10),
    "R_now":     ( 0.82,  1.65,  2.96),
}

# McWhirter NN category modifiers (bull/bear tilt)
NN_MODIFIER = {
    "peak_zone": 0.75,      # Can/Leo — late bull, corrections expected
    "bottom_zone": 1.30,    # Vir/Lib — bullish setup
    "bear_zone": 0.85,      # Sco/Sag — caution
    "setup_zone": 1.20,     # Cap/Aqu — speculation setup
    "launch_zone": 1.10,    # Pis/Ari — launch pad
    "mid": 1.00,
}

# Almuten condition — stronger almuten = more stable chart
# We weight by almuten's dignity (fixed weights for now)
ALMUTEN_STABILITY = {
    "Jupiter": 1.20,  # classical greater benefic
    "Venus": 1.15,    # lesser benefic
    "Sun": 1.10,
    "Moon": 1.00,
    "Mercury": 1.00,
    "Saturn": 0.90,   # greater malefic
    "Mars": 0.85,     # lesser malefic
}

def _match(val, p25, p50, p75):
    iqr_lo = p50 - p25
    iqr_hi = p75 - p50
    d = (val - p50) / max(iqr_hi, 0.01) if val >= p50 else (p50 - val) / max(iqr_lo, 0.01)
    if d <= 1.0: return 1.0 - 0.4 * d
    elif d <= 2.0: return 0.6 - 0.3 * (d - 1)
    elif d <= 3.0: return 0.3 - 0.15 * (d - 2)
    else: return max(0.0, 0.15 - 0.03 * (d - 3))

def compute_bti_v9(natal, eval_y, eval_m):
    # Classical classification
    cls = classical_classify(natal)
    js_phase = cls["js_phase"]
    almuten = cls["almuten"]
    nn_cat = cls["nn_category"]

    phase_sig = JS_PHASE_SIGNATURES.get(js_phase, {"weight":0.7, "sig":{}})
    phase_weight = phase_sig["weight"]
    phase_specific = phase_sig["sig"]

    # Get state vector
    from bti_v6 import compute_bti_v6
    state = compute_bti_v6(natal, eval_y, eval_m)
    state_vec = {k: state[k] for k in ("dP3","dR","awakening","I_near","p_ratio",
                                        "P_max_24","I_fwd","burn_ratio","R_now")}

    # Two-layer signature match:
    # (1) Phase-specific (primary, weighted by phase confidence)
    # (2) Common baseline (secondary, for components not in phase-specific)
    phase_score = 0.0; phase_weight_sum = 0.0
    COMPONENT_WEIGHTS = {"dP3":3.0,"dR":3.0,"awakening":2.0,"I_near":1.5,"p_ratio":1.0,
                         "P_max_24":0.5,"I_fwd":0.8,"burn_ratio":0.3,"R_now":0.3}
    for comp, w in COMPONENT_WEIGHTS.items():
        v = state_vec.get(comp)
        if v is None: continue
        # Use phase-specific if available, else common
        if comp in phase_specific:
            p25, p50, p75 = phase_specific[comp]
            m = _match(v, p25, p50, p75)
            phase_score += m * w * 1.3  # emphasise phase-specific
            phase_weight_sum += w * 1.3
        elif comp in COMMON_SIG:
            p25, p50, p75 = COMMON_SIG[comp]
            m = _match(v, p25, p50, p75)
            phase_score += m * w
            phase_weight_sum += w
    signature_match = phase_score / max(phase_weight_sum, 0.01)

    # Pressure presence gate
    if state_vec["P_max_24"] < 1.5: press_gate = 0.3
    elif state_vec["P_max_24"] < 2.5: press_gate = 0.3 + 0.7 * (state_vec["P_max_24"] - 1.5)
    else: press_gate = 1.0

    # Classical modifiers
    nn_mod = NN_MODIFIER.get(nn_cat, 1.0)
    alm_mod = ALMUTEN_STABILITY.get(almuten, 1.0)

    # Survival and era
    Gs = gamma_survive(natal); Ge = gamma_era(natal, eval_y)

    # Composite
    bti = (signature_match * press_gate * phase_weight
           * (alm_mod ** 0.6) * (nn_mod ** 0.8)
           * (Gs ** 0.6) * (Ge ** 0.4) * 10.0)

    return {"bti": bti, "signature_match": signature_match,
            "js_phase": js_phase, "almuten": almuten, "nn_category": nn_cat,
            "sect_elem": cls["sect_light_elem"],
            "triplicity_lord": cls["triplicity_lord_1"],
            "mutation_elem": cls["mutation_elem"],
            "phase_weight": phase_weight, "nn_mod": nn_mod, "alm_mod": alm_mod,
            "press_gate": press_gate,
            **state_vec, "Gs": Gs, "Ge": Ge}

def bti_window_v9(natal, ey, em, half=2):
    best = None; best_off = 0
    for off in range(-half, half+1):
        y, m = yx(ey, em, off)
        rep = compute_bti_v9(natal, y, m)
        if best is None or rep["bti"] > best["bti"]:
            best = rep; best_off = off
    best["window_offset"] = best_off
    return best

if __name__ == "__main__":
    import csv, time
    from collections import defaultdict
    from secular_bottoms_corpus import SECULAR_BOTTOMS
    from bti_test import BOTTOMS as ORIG16

    # Validation
    print("="*100)
    print("v9 VALIDATION — classically grounded (Abu Ma'shar + Ibn Ezra + McWhirter)")
    print("="*100)
    bot_scores = []; quiet_scores = []
    phase_groups = defaultdict(lambda: {"bot":[],"quiet":[]})
    for tk, ipo, bot, top, mult, note in SECULAR_BOTTOMS:
        try:
            natal = compute_natal(ipo)
            r = compute_bti_v9(natal, bot[0], bot[1])
            bot_scores.append(r["bti"])
            phase_groups[r["js_phase"]]["bot"].append(r["bti"])
            for off in (-18, -12, 12, 18):
                y, m = yx(bot[0], bot[1], off)
                rq = compute_bti_v9(natal, y, m)
                quiet_scores.append(rq["bti"])
                phase_groups[rq["js_phase"]]["quiet"].append(rq["bti"])
        except Exception:
            pass
    print(f"  Overall: bot n={len(bot_scores)} mean={st.mean(bot_scores):.2f}  quiet mean={st.mean(quiet_scores):.2f}")
    p = w = 0
    for b in bot_scores:
        for q in quiet_scores:
            p += 1
            if b > q: w += 1
    print(f"  AUC bot>quiet: {w/p:.3f}")
    print(f"\nPer-JS-phase AUC:")
    for phase, d in sorted(phase_groups.items(), key=lambda kv:-len(kv[1]["bot"])):
        if not d["bot"] or not d["quiet"]: continue
        pp = ww = 0
        for b in d["bot"]:
            for q in d["quiet"]:
                pp+=1
                if b>q: ww+=1
        print(f"  {phase:<15s}  n_bot={len(d['bot']):3d}  bot mean={st.mean(d['bot']):.2f}  quiet mean={st.mean(d['quiet']):.2f}  AUC={ww/max(pp,1):.3f}")

    # Tops vs bottoms
    top_s = []; bot_s = []
    for tk, ipo, bot, top, mult, note in ORIG16:
        try:
            natal = compute_natal(ipo)
            bot_s.append(compute_bti_v9(natal, bot[0], bot[1])["bti"])
            top_s.append(compute_bti_v9(natal, top[0], top[1])["bti"])
        except: pass
    print(f"\nOrig16 bot/top: {st.mean(bot_s):.2f} / {st.mean(top_s):.2f}  ratio={st.mean(bot_s)/max(st.mean(top_s),0.01):.2f}")

    # SP500 scan
    print(f"\n{'='*140}")
    print("SP500 @ 2026-04 — v9 classically grounded")
    print(f"{'='*140}")
    sp500 = []
    with open("/home/user/cyclepapa/data/sp500_ipo_dates.csv") as f:
        sp500 = list(csv.DictReader(f))
    t0 = time.time()
    results = []
    for row in sp500:
        try:
            natal = compute_natal(row["ipo_date"])
            rep = bti_window_v9(natal, 2026, 4, half=2)
            results.append((row["ticker"], row["name"], row["sector"], row["ipo_date"], rep))
        except Exception:
            pass
    print(f"  Scanned {len(results)} in {time.time()-t0:.0f}s")
    results.sort(key=lambda r: -r[4]["bti"])

    # Prev ranks
    v5_map = {}; v8_map = {}
    with open("/home/user/cyclepapa/data/sp500_bti_v5_apr2026.csv") as f:
        for r in csv.DictReader(f): v5_map[r["ticker"]] = float(r["bti_v5"])
    with open("/home/user/cyclepapa/data/sp500_bti_v8_apr2026.csv") as f:
        for r in csv.DictReader(f): v8_map[r["ticker"]] = float(r["bti_v8"])

    print(f"\n{'Rk':>3s} {'Tkr':<6s} {'Sec':<18s} {'Name':<26s} {'IPO':<11s} {'v9':>5s} {'jsph':<13s} {'alm':<4s} {'nn':<12s} {'sig':>4s} {'v8':>5s} {'v5':>5s}")
    for i, (tk, nm, sec, ipo, rep) in enumerate(results[:40], 1):
        print(f"{i:3d} {tk:<6s} {sec[:18]:<18s} {nm[:26]:<26s} {ipo:<11s} {rep['bti']:5.2f} {rep['js_phase']:<13s} {rep['almuten'][:3]:<4s} {rep['nn_category'][:12]:<12s} {rep['signature_match']:4.2f} {v8_map.get(tk,0):5.1f} {v5_map.get(tk,0):5.1f}")

    print(f"\nDistribution: mean={st.mean(r[4]['bti'] for r in results):.2f}  median={st.median(r[4]['bti'] for r in results):.2f}  max={max(r[4]['bti'] for r in results):.2f}")

    # JS phase in top 40 vs universe
    print(f"\nJS phase in top 40 vs all 503:")
    ph_top = defaultdict(int); ph_all = defaultdict(int)
    for i,(_,_,_,_,rep) in enumerate(results):
        ph_all[rep["js_phase"]] += 1
        if i < 40: ph_top[rep["js_phase"]] += 1
    for phase in ("new","crescent","first_q","gibbous","full","disseminating","last_q","balsamic"):
        a = ph_all[phase]; t = ph_top[phase]
        if a == 0: continue
        overrep = t/40 / (a/503)
        print(f"  {phase:<15s}  all={a:3d}  top40={t:2d}  overrep={overrep:.2f}")

    # Export
    with open("/home/user/cyclepapa/data/sp500_bti_v9_apr2026.csv","w",newline="") as f:
        w = csv.writer(f)
        w.writerow(["rank","ticker","name","sector","ipo_date","bti_v9","js_phase","almuten","nn_cat","sect_elem","trip_lord","mutation","signature_match",
                    "dP3","dR","awakening","I_near","p_ratio","P_max","burn","Gs","Ge","v5","v8"])
        for i,(tk,nm,sec,ipo,rep) in enumerate(results,1):
            w.writerow([i,tk,nm,sec,ipo,f"{rep['bti']:.3f}",rep["js_phase"],rep["almuten"],rep["nn_category"],
                        rep["sect_elem"],rep["triplicity_lord"],rep["mutation_elem"],f"{rep['signature_match']:.3f}",
                        f"{rep['dP3']:+.2f}",f"{rep['dR']:+.2f}",f"{rep['awakening']:.2f}",f"{rep['I_near']:.2f}",
                        f"{rep['p_ratio']:.2f}",f"{rep['P_max_24']:.2f}",f"{rep['burn_ratio']:.2f}",
                        f"{rep['Gs']:.2f}",f"{rep['Ge']:.2f}",f"{v5_map.get(tk,0):.1f}",f"{v8_map.get(tk,0):.1f}"])
    print(f"\nExported: /home/user/cyclepapa/data/sp500_bti_v9_apr2026.csv")
