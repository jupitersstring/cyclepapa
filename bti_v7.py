"""
BTI v7 — EMPIRICALLY CALIBRATED on 110-bottom corpus.

Signature extraction showed:
- dP3 at bottoms is POSITIVE (pressure still peaking), not negative
- dR near zero (release paused, not rising)
- I_near slightly elevated (near-term detonator)
- Other components = baseline (no discrimination)

v7 scoring:
- CORE: match to empirical signature distribution (Mahalanobis-like)
- Score highest when (dP3, dR, I_near, p_ratio) ≈ bottom signature quartiles
- Gs + Ge for survival/era modifiers (multiplicative)
- Log-scaled rally-magnitude proxy via (P_max_24, I_fwd) sum
"""
from __future__ import annotations
import math, statistics as st
import swisseph as swe
from bti_test import compute_natal, transits_at
from bti_v4 import gamma_survive, gamma_era, yx
from bti_v5 import pressure_v5, release_v5, ignition_at_v5

# Empirical signature quartiles from 110-bottom extraction
# Format: (p25, p50, p75)
SIGNATURE = {
    "dP3":       (-0.47,  0.44,  1.08),   # pressure still building/peaking
    "dR":        (-1.11,  0.00,  0.64),   # release paused
    "I_near":    ( 0.26,  0.82,  1.33),   # near-term detonator elevated
    "p_ratio":   ( 0.40,  0.58,  0.80),   # pain near peak
    "P_max_24":  ( 2.90,  3.79,  4.51),   # real pressure was present
    "R_now":     ( 0.82,  1.65,  2.96),   # moderate release presence
    "I_fwd":     ( 0.15,  0.78,  1.51),   # forward ignition
    "burn_ratio":( 1.62,  2.07,  2.45),   # moderate burn
}

# Weights by separation strength from baseline
WEIGHTS = {
    "dP3":      3.0,   # strongest signal
    "dR":       2.0,   # strong
    "I_near":   1.5,   # weak-medium
    "p_ratio":  1.2,   # weak
    "P_max_24": 0.5,   # baseline — just wants SOME pressure
    "R_now":    0.5,
    "I_fwd":    0.8,
    "burn_ratio":0.3,
}

def _match_score(val, p25, p50, p75):
    """1.0 at p50, falls to 0.3 at p25/p75, 0.0 at 2*(p25-p50)+p50."""
    if val is None: return 0.5
    iqr_lo = p50 - p25
    iqr_hi = p75 - p50
    if val >= p50:
        d = (val - p50) / max(iqr_hi, 0.01)
    else:
        d = (p50 - val) / max(iqr_lo, 0.01)
    # Bell-curve-ish match
    if d <= 1.0: return 1.0 - 0.4 * d  # 1.0 to 0.6
    elif d <= 2.0: return 0.6 - 0.3 * (d - 1)  # 0.6 to 0.3
    elif d <= 3.0: return 0.3 - 0.15 * (d - 2)  # 0.3 to 0.15
    else: return max(0.0, 0.15 - 0.03 * (d - 3))

def compute_bti_v7(natal, eval_y, eval_m):
    # Past 24 months
    P_24, R_24 = [], []
    for k in range(24, -1, -1):
        y, m = yx(eval_y, eval_m, -k)
        tr = transits_at(y, m)
        tr_p = transits_at(*yx(y, m, -1))
        tr_n = transits_at(*yx(y, m, +1))
        P_24.append(pressure_v5(natal, tr))
        R_24.append(release_v5(natal, tr, tr_p, tr_n))
    P_max_24 = max(P_24)
    P_now = P_24[-1]
    P_3 = sum(P_24[-3:]) / 3
    P_pre3 = sum(P_24[-6:-3]) / 3
    dP3 = P_3 - P_pre3
    burn_ratio = sum(R_24[:-6]) / 19.0
    # Current R + dR
    tr_prev = transits_at(*yx(eval_y, eval_m, -1))
    tr_curr = transits_at(eval_y, eval_m)
    tr_next = transits_at(*yx(eval_y, eval_m, +1))
    R_now = release_v5(natal, tr_curr, tr_prev, tr_next)
    tr_prev2 = transits_at(*yx(eval_y, eval_m, -2))
    R_prev = release_v5(natal, tr_prev, tr_prev2, tr_curr)
    dR = R_now - R_prev
    # Ignition: near and forward
    near_future = [transits_at(*yx(eval_y, eval_m, +k)) for k in range(0, 4)]
    forward_future = [transits_at(*yx(eval_y, eval_m, +k)) for k in range(4, 10)]
    I_near = ignition_at_v5(natal, near_future)
    I_fwd = ignition_at_v5(natal, forward_future)
    p_ratio = P_now / max(P_max_24, 0.1)

    vals = {"dP3":dP3,"dR":dR,"I_near":I_near,"p_ratio":p_ratio,
            "P_max_24":P_max_24,"R_now":R_now,"I_fwd":I_fwd,"burn_ratio":burn_ratio}
    # Weighted sum of match scores
    total_weight = sum(WEIGHTS.values())
    match_total = 0.0
    match_components = {}
    for k, v in vals.items():
        p25, p50, p75 = SIGNATURE[k]
        m = _match_score(v, p25, p50, p75)
        match_components[k] = m
        match_total += m * WEIGHTS[k]
    signature_match = match_total / total_weight  # 0 to 1

    # Minimum pressure gate (no hits if no pressure)
    if P_max_24 < 1.5:
        press_gate = 0.3
    elif P_max_24 < 2.5:
        press_gate = 0.3 + 0.7 * (P_max_24 - 1.5)
    else:
        press_gate = 1.0

    Gs = gamma_survive(natal)
    Ge = gamma_era(natal, eval_y)

    # Composite: signature match amplified by survival + era
    bti = signature_match * press_gate * (Gs ** 0.8) * (Ge ** 0.5) * 10.0

    return {"bti": bti, "signature_match": signature_match,
            "P_max_24": P_max_24, "P_now": P_now, "p_ratio": p_ratio,
            "dP3": dP3, "R_now": R_now, "dR": dR,
            "I_near": I_near, "I_fwd": I_fwd, "burn_ratio": burn_ratio,
            "press_gate": press_gate, "Gs": Gs, "Ge": Ge,
            "components": match_components}

def bti_window_v7(natal, ey, em, half=2):
    best = None; best_off = 0
    for off in range(-half, half+1):
        y, m = yx(ey, em, off)
        rep = compute_bti_v7(natal, y, m)
        if best is None or rep["bti"] > best["bti"]:
            best = rep; best_off = off
    best["window_offset"] = best_off
    return best

if __name__ == "__main__":
    import csv, time
    from collections import defaultdict
    from secular_bottoms_corpus import SECULAR_BOTTOMS

    # 1. Validate v7 against the 110-bottom corpus
    print("="*100)
    print("v7 VALIDATION against 110-bottom corpus")
    print("="*100)
    bot_scores = []
    quiet_scores = []
    for tk, ipo, bot, top, mult, note in SECULAR_BOTTOMS:
        try:
            natal = compute_natal(ipo)
            r = compute_bti_v7(natal, bot[0], bot[1])
            bot_scores.append(r["bti"])
            for off in (-18, -12, 12, 18):
                y, m = yx(bot[0], bot[1], off)
                rq = compute_bti_v7(natal, y, m)
                quiet_scores.append(rq["bti"])
        except Exception:
            pass
    print(f"  Bottoms:  n={len(bot_scores)}  mean={st.mean(bot_scores):.2f}  median={st.median(bot_scores):.2f}")
    print(f"  Quiet:    n={len(quiet_scores)}  mean={st.mean(quiet_scores):.2f}  median={st.median(quiet_scores):.2f}")
    pairs = wins = 0
    for b in bot_scores:
        for q in quiet_scores:
            pairs += 1
            if b > q: wins += 1
    print(f"  AUC:      {wins/pairs:.3f}")

    # 2. Tops comparison (using original 16)
    from bti_test import BOTTOMS as ORIG16
    top_scores = []
    for tk, ipo, bot, top, mult, note in ORIG16:
        try:
            natal = compute_natal(ipo)
            r = compute_bti_v7(natal, top[0], top[1])
            top_scores.append(r["bti"])
        except Exception:
            pass
    print(f"\n  Orig16 tops:  n={len(top_scores)}  mean={st.mean(top_scores):.2f}")
    b16 = []
    for tk, ipo, bot, top, mult, note in ORIG16:
        try:
            natal = compute_natal(ipo)
            r = compute_bti_v7(natal, bot[0], bot[1])
            b16.append(r["bti"])
        except: pass
    print(f"  Orig16 bot:   n={len(b16)}  mean={st.mean(b16):.2f}")
    print(f"  bot/top:      {st.mean(b16)/max(st.mean(top_scores),0.01):.2f}")

    # 3. SP500 scan
    print(f"\n{'='*100}")
    print(f"SP500 @ 2026-04  —  v7")
    print(f"{'='*100}")
    sp500 = []
    with open("/home/user/cyclepapa/data/sp500_ipo_dates.csv") as f:
        sp500 = list(csv.DictReader(f))
    t0 = time.time()
    results = []
    for row in sp500:
        try:
            natal = compute_natal(row["ipo_date"])
            rep = bti_window_v7(natal, 2026, 4, half=2)
            results.append((row["ticker"], row["name"], row["sector"], row["ipo_date"], rep))
        except Exception:
            pass
    print(f"  Scanned {len(results)} in {time.time()-t0:.0f}s")
    results.sort(key=lambda r: -r[4]["bti"])

    # Load prev-version ranks for comparison
    v5_map = {}; v6_map = {}
    with open("/home/user/cyclepapa/data/sp500_bti_v5_apr2026.csv") as f:
        for r in csv.DictReader(f): v5_map[r["ticker"]] = float(r["bti_v5"])
    with open("/home/user/cyclepapa/data/sp500_bti_v6_apr2026.csv") as f:
        for r in csv.DictReader(f):
            v6_map[r["ticker"]] = float(r["bti_v6"])

    print(f"\n{'Rk':>3s} {'Tkr':<6s} {'Sec':<20s} {'Name':<28s} {'IPO':<11s} {'v7':>5s} {'sig':>4s} {'Pmx':>4s} {'p_r':>4s} {'dP3':>5s} {'dR':>5s} {'Ine':>4s} {'burn':>4s} {'v5':>5s} {'v6':>5s}")
    for i, (tk, nm, sec, ipo, rep) in enumerate(results[:40], 1):
        v5b = v5_map.get(tk, 0); v6b = v6_map.get(tk, 0)
        print(f"{i:3d} {tk:<6s} {sec[:20]:<20s} {nm[:28]:<28s} {ipo:<11s} {rep['bti']:5.2f} {rep['signature_match']:4.2f} {rep['P_max_24']:4.1f} {rep['p_ratio']:4.2f} {rep['dP3']:+5.2f} {rep['dR']:+5.2f} {rep['I_near']:4.1f} {rep['burn_ratio']:4.1f} {v5b:5.1f} {v6b:5.1f}")

    print(f"\nDistribution: mean={st.mean(r[4]['bti'] for r in results):.2f}  median={st.median(r[4]['bti'] for r in results):.2f}  max={max(r[4]['bti'] for r in results):.2f}")

    # Export
    with open("/home/user/cyclepapa/data/sp500_bti_v7_apr2026.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["rank","ticker","name","sector","ipo_date","bti_v7","window_off","signature_match",
                    "P_max_24","P_now","p_ratio","dP3","R_now","dR","I_near","I_fwd","burn_ratio",
                    "Gs","Ge","v5","v6"])
        for i, (tk,nm,sec,ipo,rep) in enumerate(results, 1):
            w.writerow([i,tk,nm,sec,ipo,f"{rep['bti']:.3f}",rep["window_offset"],
                        f"{rep['signature_match']:.3f}",
                        f"{rep['P_max_24']:.2f}",f"{rep['P_now']:.2f}",f"{rep['p_ratio']:.2f}",
                        f"{rep['dP3']:+.2f}",f"{rep['R_now']:.2f}",f"{rep['dR']:+.2f}",
                        f"{rep['I_near']:.2f}",f"{rep['I_fwd']:.2f}",f"{rep['burn_ratio']:.2f}",
                        f"{rep['Gs']:.2f}",f"{rep['Ge']:.2f}",
                        f"{v5_map.get(tk,0):.2f}",f"{v6_map.get(tk,0):.2f}"])
    print(f"\nExported: /home/user/cyclepapa/data/sp500_bti_v7_apr2026.csv")
