"""
BTI v3: address remaining false positives at tops.

Core insight from v2: a "turn" looks the same astrologically whether you're turning up
from a bottom or down from a top. Without price data, we need a sky-only proxy for
"are we coming from a long compression phase, or from a long benefic phase?"

v3 adds:
- Pressure HISTORY signal: was pressure ACTUALLY built up (not just briefly elevated)?
  Use a longer 18-month look-back. Sum of P over the period proxies for "compression mass".
- Benefic-history suppressor: if benefic transits dominated the prior 18 months
  (R high more than P), suppress the BTI -- this is a top, not a bottom.
- Stricter dP gate: any positive dP zeroes E.
- Compression-confirm: P_now must be at least 30% of P_max_18 (still feeling the strain).
"""
from __future__ import annotations
import swisseph as swe
from bti_test import (compute_natal, transits_at, gamma_survive, gamma_era,
                      hard_orb, any_aspect_orb, orb, MEAN_SPEEDS,
                      BOTTOMS, NULLS, QUIET_OFFSETS)
from bti_v2 import pressure_v2, release_v2, ignition_at_v2

def yx(y, m, off):
    mm, yy = m + off, y
    while mm <= 0: mm += 12; yy -= 1
    while mm > 12: mm -= 12; yy += 1
    return (yy, mm)

def compute_bti_v3(natal, eval_y, eval_m):
    # 18-month look-back of pressure AND release for "compression mass" + "benefic dominance"
    P_18 = []
    R_18 = []
    for k in range(18, -1, -1):
        y, m = yx(eval_y, eval_m, -k)
        tr = transits_at(y, m)
        tr_p = transits_at(*yx(y, m, -1))
        tr_n = transits_at(*yx(y, m, +1))
        P_18.append(pressure_v2(natal, tr))
        R_18.append(release_v2(natal, tr, tr_p, tr_n))
    P_max_18 = max(P_18)
    P_sum_18 = sum(P_18)
    R_sum_18 = sum(R_18)
    P_now = P_18[-1]
    P_prev = P_18[-2]
    P_3mo_avg = sum(P_18[-3:]) / 3
    P_6_to_3_avg = sum(P_18[-6:-3]) / 3
    dP = P_now - P_prev
    dP_3m = P_3mo_avg - P_6_to_3_avg  # smoother derivative

    # COMPRESSION CONFIRM: pressure must have been substantial AND dominant over release
    if P_max_18 < 2.5:
        return _zeroed(P_max_18, P_now, dP, "no_real_compression")
    if R_sum_18 > P_sum_18 * 1.3:  # benefic-dominant period = top territory
        return _zeroed(P_max_18, P_now, dP, "benefic_dominated_period")
    # Strict dP gate — pressure must be flat-or-easing
    if dP_3m > 0.2:
        return _zeroed(P_max_18, P_now, dP, "pressure_still_building")

    # Easing factor
    if dP_3m > 0:
        E = max(0, 0.4 - dP_3m * 2)
    else:
        E = 0.5 + min(0.5, -dP_3m / 1.0)

    # P-confirm: are we in a recent-pressure context?
    # Score peaks when P_now is between 30% and 80% of P_max_18 (felt pain, easing)
    p_ratio = P_now / max(P_max_18, 0.1)
    if p_ratio < 0.20:  # pressure long gone — too late
        compression_confirm = 0.4
    elif p_ratio > 0.95:  # still maximum stress, no easing
        compression_confirm = 0.6
    else:
        compression_confirm = 1.0

    # Release at current month
    tr_prev = transits_at(*yx(eval_y, eval_m, -1))
    tr_curr = transits_at(eval_y, eval_m)
    tr_next = transits_at(*yx(eval_y, eval_m, +1))
    R_now = release_v2(natal, tr_curr, tr_prev, tr_next)
    tr_prev2 = transits_at(*yx(eval_y, eval_m, -2))
    R_prev = release_v2(natal, tr_prev, tr_prev2, tr_curr)
    dR = R_now - R_prev
    R_dot = 1.0 + max(0, dR / 2.0)
    # Ignition next 90d
    future = [transits_at(*yx(eval_y, eval_m, +k)) for k in range(0, 4)]
    I = ignition_at_v2(natal, future)
    Gs = gamma_survive(natal)
    Ge = gamma_era(natal, eval_y)

    # Compose with geometric-style aggregation
    P_term = max(P_max_18 / 4.0, 0.4)
    R_term = max(R_now / 4.0, 0.3)
    I_term = 1.0 + I / 5.0
    bti = (P_term ** 0.7) * (E ** 0.8) * (R_term ** 0.8) * (R_dot ** 0.5) * \
          (I_term ** 0.5) * (Gs ** 0.6) * (Ge ** 0.4) * compression_confirm
    bti *= 6.0
    return {
        "bti": bti, "P_max_18": P_max_18, "P_now": P_now, "p_ratio": p_ratio,
        "P_sum": P_sum_18, "R_sum": R_sum_18,
        "dP_3m": dP_3m, "E": E, "R_now": R_now, "dR": dR, "R_dot": R_dot,
        "I_90d": I, "Gs": Gs, "Ge": Ge, "comp_conf": compression_confirm, "killed": ""
    }

def _zeroed(P, P_now, dP, why):
    return {"bti": 0.0, "P_max_18": P, "P_now": P_now, "p_ratio": 0,
            "P_sum": 0, "R_sum": 0, "dP_3m": dP, "E": 0, "R_now": 0,
            "dR": 0, "R_dot": 0, "I_90d": 0, "Gs": 0, "Ge": 0,
            "comp_conf": 0, "killed": why}

def bti_window_v3(natal, eval_y, eval_m, half=3):
    best = None; best_off = 0
    for off in range(-half, half+1):
        y, m = yx(eval_y, eval_m, off)
        rep = compute_bti_v3(natal, y, m)
        if best is None or rep["bti"] > best["bti"]:
            best = rep; best_off = off
    best["window_offset"] = best_off
    return best

def run_v3():
    print("="*155)
    print("BTI v3 VALIDATION  (18-mo compression mass + benefic-dominance suppressor + strict dP)")
    print("="*155)
    print(f"{'Case':<8s} {'IPO':<11s} {'BotMo':<7s} {'BTIw':>6s} {'+/-':>3s} {'Pmax':>5s} {'p_r':>4s} {'Psum':>5s} {'Rsum':>5s} {'dP3m':>5s} {'E':>4s} {'Rnow':>5s} {'I':>4s} {'Gs':>4s} {'Ge':>4s} {'killed/note'}")
    print("-"*155)
    bottom_btis = []
    for tk, ipo, bot, top, mult, note in BOTTOMS:
        natal = compute_natal(ipo)
        rep = bti_window_v3(natal, bot[0], bot[1])
        bottom_btis.append((tk, rep["bti"]))
        mo = f"{bot[0]}-{bot[1]:02d}"
        marker = rep.get("killed") or note[:35]
        print(f"{tk:<8s} {ipo:<11s} {mo:<7s} {rep['bti']:6.2f} {rep['window_offset']:+3d} {rep['P_max_18']:5.1f} {rep['p_ratio']:4.2f} {rep['P_sum']:5.1f} {rep['R_sum']:5.1f} {rep['dP_3m']:+5.2f} {rep['E']:4.2f} {rep['R_now']:5.1f} {rep['I_90d']:4.1f} {rep['Gs']:4.2f} {rep['Ge']:4.2f} {marker}")

    print()
    print("TOPS — should be killed by gates")
    print("-"*155)
    top_btis = []
    for tk, ipo, bot, top, mult, note in BOTTOMS:
        natal = compute_natal(ipo)
        rep = compute_bti_v3(natal, top[0], top[1])
        top_btis.append((tk, rep["bti"]))
        mo = f"{top[0]}-{top[1]:02d}"
        marker = rep.get("killed", "")
        print(f"{tk:<8s} top {mo:<7s}  BTI={rep['bti']:6.2f}  Psum={rep['P_sum']:.1f} Rsum={rep['R_sum']:.1f}  dP={rep['dP_3m']:+.2f}  {marker}")

    print()
    print("QUIET MONTHS — should be lower than bottoms")
    print("-"*155)
    quiet_btis = []
    for tk, ipo, bot, top, mult, note in BOTTOMS[:8]:
        natal = compute_natal(ipo)
        for off in QUIET_OFFSETS:
            y, m = yx(bot[0], bot[1], off)
            rep = compute_bti_v3(natal, y, m)
            quiet_btis.append((tk, off, rep["bti"]))
        vals = [v for (t, o, v) in quiet_btis if t == tk]
        med_q = sorted(vals)[len(vals)//2] if vals else 0
        bot_bti = next(v for (t, v) in bottom_btis if t == tk)
        print(f"  {tk:<8s} bot BTIw={bot_bti:5.2f}  med quiet={med_q:5.2f}  ratio={bot_bti/max(med_q,0.01):5.1f}x")

    print()
    print("NULLS")
    print("-"*155)
    null_btis = []
    for tk, ipo, peak, note in NULLS:
        natal = compute_natal(ipo)
        rep = compute_bti_v3(natal, peak[0], peak[1])
        null_btis.append(rep["bti"])
        mo = f"{peak[0]}-{peak[1]:02d}"
        print(f"{tk:<8s} peak {mo}  BTI={rep['bti']:6.2f}  Gs={rep['Gs']:.2f}  killed={rep.get('killed','')}  {note}")

    print()
    print("="*155)
    print("v3 SUMMARY")
    print("="*155)
    import statistics as st
    bvals = [v for (t,v) in bottom_btis]
    qvals = [v for (t,o,v) in quiet_btis]
    tvals = [v for (t,v) in top_btis]
    print(f"  Bottoms:  mean={st.mean(bvals):.2f}  median={st.median(bvals):.2f}  min={min(bvals):.2f}  max={max(bvals):.2f}")
    print(f"  Quiet:    mean={st.mean(qvals):.2f}  median={st.median(qvals):.2f}  max={max(qvals):.2f}")
    print(f"  Tops:     mean={st.mean(tvals):.2f}  median={st.median(tvals):.2f}  max={max(tvals):.2f}")
    print(f"  Nulls:    mean={st.mean(null_btis):.2f}  median={st.median(null_btis):.2f}  max={max(null_btis):.2f}")
    pairs = wins = 0
    for b in bvals:
        for q in qvals:
            pairs += 1
            if b > q: wins += 1
    auc_q = wins/pairs if pairs else 0
    pairs = wins = 0
    for b in bvals:
        for t in tvals:
            pairs += 1
            if b > t: wins += 1
    auc_t = wins/pairs if pairs else 0
    print(f"  AUC bottom>quiet: {auc_q:.3f}")
    print(f"  AUC bottom>top:   {auc_t:.3f}")
    n_bot_killed = sum(1 for v in bvals if v == 0)
    n_top_killed = sum(1 for v in tvals if v == 0)
    print(f"  Bottoms zeroed:   {n_bot_killed}/{len(bvals)}  (false negatives — should be low)")
    print(f"  Tops zeroed:      {n_top_killed}/{len(tvals)}  (true negatives — should be high)")
    n_null_killed = sum(1 for v in null_btis if v == 0)
    print(f"  Nulls zeroed:     {n_null_killed}/{len(null_btis)}  (true negatives for one-and-done)")

if __name__ == "__main__":
    run_v3()
