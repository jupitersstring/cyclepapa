"""
BTI v4 — final calibrated. Hybrid of v2 (catches bottoms) + v3 (suppresses tops),
using SOFT penalty multipliers instead of hard zeros so real bottoms aren't lost.

All gates remain pure-astrological (no price data).

Soft gates (multipliers in [0.2, 1.0]):
  - benefic_excess: penalises when 18-mo R_sum > 1.5 × P_sum (top territory)
  - building_pressure: penalises positive 3-month dP (pre-top)
  - thin_compression: penalises P_max_18 < 2.5 (no real stress to release)
"""
from __future__ import annotations
import math
import statistics as st
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

def compute_bti_v4(natal, eval_y, eval_m):
    # 18-month look-back
    P_18, R_18 = [], []
    for k in range(18, -1, -1):
        y, m = yx(eval_y, eval_m, -k)
        tr = transits_at(y, m)
        tr_p = transits_at(*yx(y, m, -1))
        tr_n = transits_at(*yx(y, m, +1))
        P_18.append(pressure_v2(natal, tr))
        R_18.append(release_v2(natal, tr, tr_p, tr_n))
    P_max_18 = max(P_18)
    P_sum = sum(P_18)
    R_sum = sum(R_18)
    P_now = P_18[-1]
    P_3 = sum(P_18[-3:]) / 3
    P_pre3 = sum(P_18[-6:-3]) / 3
    dP3 = P_3 - P_pre3
    dP = P_now - P_18[-2]

    # ---- SOFT GATES ----
    # Gate 1: thin compression (no real pressure built up)
    if P_max_18 < 1.5:
        thin_pen = 0.20
    elif P_max_18 < 2.5:
        thin_pen = 0.20 + 0.55 * (P_max_18 - 1.5)  # 0.20 to 0.75
    elif P_max_18 < 4.0:
        thin_pen = 0.75 + 0.25 * (P_max_18 - 2.5) / 1.5
    else:
        thin_pen = 1.0

    # Gate 2: benefic excess (R dominated P over the period — top territory)
    rp_ratio = R_sum / max(P_sum, 1.0)
    if rp_ratio < 0.8:
        ben_pen = 1.0
    elif rp_ratio < 1.5:
        ben_pen = 1.0 - 0.5 * (rp_ratio - 0.8) / 0.7  # 1.0 → 0.5
    elif rp_ratio < 2.5:
        ben_pen = 0.5 - 0.3 * (rp_ratio - 1.5)  # 0.5 → 0.2
    else:
        ben_pen = 0.2

    # Gate 3: pressure still rising (pre-top)
    if dP3 < -0.5:
        rise_pen = 1.0
    elif dP3 < 0:
        rise_pen = 0.7 + 0.3 * (-dP3) / 0.5
    elif dP3 < 0.5:
        rise_pen = 0.7 - 1.0 * dP3  # 0.7 → 0.2
    else:
        rise_pen = 0.2

    # Easing factor (kept tighter)
    if dP3 > 0.5:
        E = 0.2
    elif dP3 > 0:
        E = 0.5 - 0.6 * dP3
    elif dP3 > -1.0:
        E = 0.5 - 0.5 * dP3  # rises 0.5 to 1.0
    else:
        E = 1.0

    # Compression-confirm: pressure context shape
    p_ratio = P_now / max(P_max_18, 0.1)
    if p_ratio < 0.10:
        comp_conf = 0.5  # pressure too far in the past
    elif p_ratio > 0.95:
        comp_conf = 0.7  # still maxed — turn not yet started
    else:
        comp_conf = 1.0

    # Current release
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

    # Composite (geometric-style with soft floors)
    P_term = max(P_max_18 / 4.0, 0.4)
    R_term = max(R_now / 4.0, 0.3)
    I_term = 1.0 + I / 5.0
    core = (P_term ** 0.7) * (E ** 0.7) * (R_term ** 0.8) * (R_dot ** 0.5) * \
           (I_term ** 0.5) * (Gs ** 0.6) * (Ge ** 0.4) * comp_conf
    bti = core * thin_pen * ben_pen * rise_pen * 6.0
    return {
        "bti": bti, "P_max_18": P_max_18, "P_now": P_now, "p_ratio": p_ratio,
        "P_sum": P_sum, "R_sum": R_sum, "rp": rp_ratio,
        "dP3": dP3, "E": E, "R_now": R_now, "I_90d": I,
        "Gs": Gs, "Ge": Ge, "comp": comp_conf,
        "thin": thin_pen, "ben": ben_pen, "rise": rise_pen
    }

def bti_window_v4(natal, ey, em, half=3):
    best = None; best_off = 0
    for off in range(-half, half+1):
        y, m = yx(ey, em, off)
        rep = compute_bti_v4(natal, y, m)
        if best is None or rep["bti"] > best["bti"]:
            best = rep; best_off = off
    best["window_offset"] = best_off
    return best

def run_v4():
    print("="*165)
    print("BTI v4 — SOFT-GATED (thin/ben/rise penalties; pure-astrological)")
    print("="*165)
    print(f"{'Case':<8s} {'IPO':<11s} {'BotMo':<7s} {'BTIw':>6s} {'+/-':>3s} {'Pmax':>5s} {'pr':>4s} {'rp':>4s} {'dP3':>5s} {'thin':>4s} {'ben':>4s} {'rise':>4s} {'E':>4s} {'Rnow':>5s} {'I':>4s} {'Gs':>4s} {'Note'}")
    print("-"*165)
    bottom_btis = []
    for tk, ipo, bot, top, mult, note in BOTTOMS:
        natal = compute_natal(ipo)
        rep = bti_window_v4(natal, bot[0], bot[1])
        bottom_btis.append((tk, rep["bti"]))
        mo = f"{bot[0]}-{bot[1]:02d}"
        print(f"{tk:<8s} {ipo:<11s} {mo:<7s} {rep['bti']:6.2f} {rep['window_offset']:+3d} {rep['P_max_18']:5.1f} {rep['p_ratio']:4.2f} {rep['rp']:4.2f} {rep['dP3']:+5.2f} {rep['thin']:4.2f} {rep['ben']:4.2f} {rep['rise']:4.2f} {rep['E']:4.2f} {rep['R_now']:5.1f} {rep['I_90d']:4.1f} {rep['Gs']:4.2f} {note[:30]}")
    print()
    print("TOPS")
    print("-"*165)
    top_btis = []
    for tk, ipo, bot, top, mult, note in BOTTOMS:
        natal = compute_natal(ipo)
        rep = compute_bti_v4(natal, top[0], top[1])
        top_btis.append((tk, rep["bti"]))
        mo = f"{top[0]}-{top[1]:02d}"
        print(f"{tk:<8s} top {mo:<7s}  BTI={rep['bti']:6.2f}  Pmax={rep['P_max_18']:.1f} rp={rep['rp']:.2f} dP3={rep['dP3']:+.2f} pen=t{rep['thin']:.2f}b{rep['ben']:.2f}r{rep['rise']:.2f}")
    print()
    print("QUIET MONTHS")
    print("-"*165)
    quiet_btis = []
    for tk, ipo, bot, top, mult, note in BOTTOMS[:8]:
        natal = compute_natal(ipo)
        for off in QUIET_OFFSETS:
            y, m = yx(bot[0], bot[1], off)
            rep = compute_bti_v4(natal, y, m)
            quiet_btis.append((tk, off, rep["bti"]))
        vals = [v for (t,o,v) in quiet_btis if t == tk]
        med_q = sorted(vals)[len(vals)//2] if vals else 0
        bot_bti = next(v for (t,v) in bottom_btis if t == tk)
        print(f"  {tk:<8s} bot={bot_bti:5.2f}  med quiet={med_q:5.2f}  ratio={bot_bti/max(med_q,0.01):5.1f}x")
    print()
    print("NULLS")
    print("-"*165)
    null_btis = []
    for tk, ipo, peak, note in NULLS:
        natal = compute_natal(ipo)
        rep = compute_bti_v4(natal, peak[0], peak[1])
        null_btis.append(rep["bti"])
        mo = f"{peak[0]}-{peak[1]:02d}"
        print(f"{tk:<8s} peak {mo}  BTI={rep['bti']:6.2f}  Gs={rep['Gs']:.2f}  {note}")
    print()
    print("="*165)
    print("v4 SUMMARY")
    print("="*165)
    bvals = [v for (t,v) in bottom_btis]
    qvals = [v for (t,o,v) in quiet_btis]
    tvals = [v for (t,v) in top_btis]
    print(f"  Bottoms:  mean={st.mean(bvals):.2f}  median={st.median(bvals):.2f}  min={min(bvals):.2f}  max={max(bvals):.2f}")
    print(f"  Quiet:    mean={st.mean(qvals):.2f}  median={st.median(qvals):.2f}  max={max(qvals):.2f}")
    print(f"  Tops:     mean={st.mean(tvals):.2f}  median={st.median(tvals):.2f}  max={max(tvals):.2f}")
    print(f"  Nulls:    mean={st.mean(null_btis):.2f}  median={st.median(null_btis):.2f}  max={max(null_btis):.2f}")
    pairs=wins=0
    for b in bvals:
        for q in qvals:
            pairs+=1
            if b > q: wins+=1
    auc_q = wins/pairs if pairs else 0
    pairs=wins=0
    for b in bvals:
        for t in tvals:
            pairs+=1
            if b > t: wins+=1
    auc_t = wins/pairs if pairs else 0
    print(f"  AUC bottom>quiet: {auc_q:.3f}")
    print(f"  AUC bottom>top:   {auc_t:.3f}")
    print(f"  Bottoms > 5.0:    {sum(1 for v in bvals if v > 5)}/{len(bvals)}  (high-confidence bottoms)")
    print(f"  Tops > 5.0:       {sum(1 for v in tvals if v > 5)}/{len(tvals)}  (false positives at threshold)")
    print(f"  Bottoms > 3.0:    {sum(1 for v in bvals if v > 3)}/{len(bvals)}")
    print(f"  Tops > 3.0:       {sum(1 for v in tvals if v > 3)}/{len(tvals)}")

if __name__ == "__main__":
    run_v4()
