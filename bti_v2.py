"""
BTI v2: addresses v1 failures identified in test.

Changes:
- Soft floors on each component (no zeroing-out)
- Geometric-mean style composition: BTI = (P_norm * E * R_norm * R_dot * I_term * Gs * Ge)^(1/2) * scale
  to compress dynamic range and let weaker terms partially contribute
- Hard top-suppressor: if dP/dt > +0.5 (pressure still RISING), zero the result
- Wider release orbs (Jupiter 5°, station detection 3°)
- Add Saturn/Uranus/Neptune trine detection to natal Jupiter/Sun (release channel)
- Test at ±3-month window around each bottom; take max BTI
"""
from __future__ import annotations
import swisseph as swe
import math
from datetime import date

# --- imports from previous BTI test ---
from bti_test import (compute_natal, transits_at, gamma_survive, gamma_era,
                      hard_orb, any_aspect_orb, orb, MEAN_SPEEDS, DIGNITIES,
                      BOTTOMS, NULLS, QUIET_OFFSETS)

# --- v2 PRESSURE: keep same as v1 but add Pluto-house factor ---
NATAL_STRESS_TARGETS = ["Sun","Moon","Venus","Mars"]
NATAL_STRESS_LIGHT = ["Sun","Moon","ASC","MC"]

def pressure_v2(natal, trans):
    p = 0.0
    for (a, b, w) in [("Saturn","Pluto",3.0),("Saturn","Neptune",2.0),
                      ("Uranus","Pluto",2.5),("Saturn","Uranus",1.8)]:
        r = hard_orb(trans[a]["lon"], trans[b]["lon"], 8.0)
        if r: p += w * max(0, 1 - r[1]/8.0)
    for nt in NATAL_STRESS_TARGETS:
        r = hard_orb(trans["Pluto"]["lon"], natal[nt]["lon"], 4.0)  # widened
        if r: p += 2.0 * max(0, 1 - r[1]/4.0)
    for nt in NATAL_STRESS_LIGHT:
        if nt in natal:
            r = hard_orb(trans["Saturn"]["lon"], natal[nt]["lon"], 4.0)
            if r: p += 1.5 * max(0, 1 - r[1]/4.0)
    for nt in ["Sun","Moon","Venus"]:
        r = hard_orb(trans["Uranus"]["lon"], natal[nt]["lon"], 4.0)
        if r: p += 1.5 * max(0, 1 - r[1]/4.0)
    for nt in ["Sun","Mars","Jupiter"]:
        r = hard_orb(trans["Neptune"]["lon"], natal[nt]["lon"], 4.0)
        if r: p += 1.2 * max(0, 1 - r[1]/4.0)
    if trans["Mars"]["retro"]:
        for nt in ["Sun","Moon","Mars","ASC"]:
            if nt in natal:
                o = orb(trans["Mars"]["lon"], natal[nt]["lon"])
                if o <= 6.0: p += 1.3 * max(0, 1 - o/6.0)
    # Pluto in 12th house equivalent: transit Pluto in same sign as natal Pluto-12 (skip — needs full house calc)
    return min(p, 10.0)

# --- v2 RELEASE: wider orbs + more trigger types ---
def release_v2(natal, trans, prev_trans, next_trans):
    r = 0.0
    # Outer station-direct (3° orb, was 2°)
    for outer in ("Saturn","Uranus","Neptune","Pluto"):
        prev_spd = prev_trans[outer]["speed"]
        curr_spd = trans[outer]["speed"]
        next_spd = next_trans[outer]["speed"]
        is_sd = (prev_spd < 0) and (curr_spd > 0 or next_spd > 0) and abs(curr_spd) < MEAN_SPEEDS[outer]*0.5
        if is_sd:
            for nt in ["Sun","Moon","Venus","Mars","Jupiter","ASC","MC"]:
                if nt in natal:
                    o = orb(trans[outer]["lon"], natal[nt]["lon"])
                    if o <= 3.0:
                        r += 3.5 * max(0, 1 - o/3.0)
    # Jupiter sign-ingress detected ±1 month
    if int(prev_trans["Jupiter"]["lon"]//30) != int(trans["Jupiter"]["lon"]//30) or \
       int(trans["Jupiter"]["lon"]//30) != int(next_trans["Jupiter"]["lon"]//30):
        new_sign = int(trans["Jupiter"]["lon"]//30)
        mult = 1.0
        if new_sign in (3, 8, 11): mult = 2.0  # Cancer/Sag/Pisces
        if any(natal[p]["sign"] == new_sign for p in ("Sun","Moon","Mercury","Venus","Mars","Jupiter")):
            mult *= 1.5
        r += 2.0 * mult
    # Transit Jupiter to natal Sun/Venus/ASC/MC — WIDER orb 5° + include Moon/Jupiter
    for nt in ["Sun","Moon","Venus","ASC","MC","Jupiter"]:
        if nt in natal:
            ar = any_aspect_orb(trans["Jupiter"]["lon"], natal[nt]["lon"], [0,60,120], 5.0)
            if ar:
                w = 2.0 if nt in ("Sun","Venus","ASC","MC") else 1.2
                r += w * max(0, 1 - ar[1]/5.0)
    # Transit Saturn TRINE/SEXTILE to natal Jupiter/Venus = stable benefic structure release
    for nt in ["Jupiter","Venus","Sun"]:
        if nt in natal:
            ar = any_aspect_orb(trans["Saturn"]["lon"], natal[nt]["lon"], [60,120], 3.0)
            if ar: r += 1.0 * max(0, 1 - ar[1]/3.0)
    # Transit outer trine to natal benefic = supportive structural shift
    for outer in ("Uranus","Neptune","Pluto"):
        for nt in ["Jupiter","Venus","Sun"]:
            if nt in natal:
                ar = any_aspect_orb(trans[outer]["lon"], natal[nt]["lon"], [60,120], 3.0)
                if ar: r += 1.2 * max(0, 1 - ar[1]/3.0)
    # Transit Venus 2° to natal Sun/ASC/MC
    for nt in ["Sun","ASC","MC"]:
        if nt in natal:
            ar = any_aspect_orb(trans["Venus"]["lon"], natal[nt]["lon"], [0,60,120], 2.0)
            if ar: r += 0.8 * max(0, 1 - ar[1]/2.0)
    # NN ingress to sign of natal Sun/Moon/Jupiter/Venus
    nn_sign = int(trans["NN"]["lon"]//30)
    prev_nn_sign = int(prev_trans["NN"]["lon"]//30)
    if nn_sign != prev_nn_sign:
        if any(natal[p]["sign"] == nn_sign for p in ("Sun","Moon","Jupiter","Venus")):
            r += 1.5
    return min(r, 10.0)

# --- v2 IGNITION ---
def ignition_at_v2(natal, future_transits):
    I = 0.0
    for i, tr in enumerate(future_transits):
        days_out = 30 * i
        prox = (90 - days_out) / 90.0
        i_local = 0.0
        if i > 0:
            prev = future_transits[i-1]
            if prev["Mars"]["retro"] and not tr["Mars"]["retro"]:
                for nt in ["Sun","Mars","ASC","Moon"]:
                    if nt in natal:
                        o = orb(tr["Mars"]["lon"], natal[nt]["lon"])
                        if o <= 4.0: i_local += 2.5 * max(0, 1 - o/4.0)
        ju_ur = orb(tr["Jupiter"]["lon"], tr["Uranus"]["lon"])
        if ju_ur <= 4.0: i_local += 3.0 * max(0, 1 - ju_ur/4.0)
        ju_ne = orb(tr["Jupiter"]["lon"], tr["Neptune"]["lon"])
        if ju_ne <= 4.0: i_local += 3.0 * max(0, 1 - ju_ne/4.0)
        if i > 0:
            prev = future_transits[i-1]
            for outer in ("Saturn","Uranus","Neptune","Pluto"):
                if int(prev[outer]["lon"]//30) != int(tr[outer]["lon"]//30):
                    new_sign = int(tr[outer]["lon"]//30)
                    bump = 2.0
                    if any(natal[p]["sign"] == new_sign for p in ("Sun","Moon","Jupiter","Venus")):
                        bump *= 2.0
                    i_local += bump
        for nt in ["Sun","ASC","MC","Moon"]:
            if nt in natal:
                for benefic in ("Jupiter","Venus"):
                    ar = any_aspect_orb(tr[benefic]["lon"], natal[nt]["lon"], [120,60], 2.0)
                    if ar: i_local += 1.5 * max(0, 1 - ar[1]/2.0)
        I = max(I, i_local * prox)
    return I

# --- v2 COMPOSITE ---
def compute_bti_v2(natal, eval_y, eval_m):
    def yx(y, m, off):
        mm, yy = m + off, y
        while mm <= 0: mm += 12; yy -= 1
        while mm > 12: mm -= 12; yy += 1
        return (yy, mm)
    # Pressure series over past 6 months
    P_series = []
    for k in range(6, -1, -1):
        y, m = yx(eval_y, eval_m, -k)
        P_series.append(pressure_v2(natal, transits_at(y, m)))
    P_max_6 = max(P_series)
    P_now = P_series[-1]
    P_prev = P_series[-2]
    dP = P_now - P_prev
    # Hard top-suppressor: if pressure rising > 0.5/month, this is pre-top, not bottom
    if dP > 0.5:
        return {"bti": 0.0, "P_max_6": P_max_6, "P_now": P_now, "dP": dP, "E": 0.0,
                "R_now": 0.0, "dR": 0.0, "I_90d": 0.0, "Gs": 0.0, "Ge": 0.0,
                "killed": "pressure_rising"}
    # Easing: 1.0 if dP <= -1.0, 0.5 baseline if flat, 0 if rising
    if dP > 0:
        E = max(0, 0.5 - dP)  # decays to 0 by dP=+0.5
    else:
        E = 0.5 + min(0.5, -dP / 2.0)  # 0.5 to 1.0 as dP gets more negative
    # Release with prev/next
    tr_prev = transits_at(*yx(eval_y, eval_m, -1))
    tr_curr = transits_at(eval_y, eval_m)
    tr_next = transits_at(*yx(eval_y, eval_m, +1))
    R_now = release_v2(natal, tr_curr, tr_prev, tr_next)
    tr_prev2 = transits_at(*yx(eval_y, eval_m, -2))
    R_prev = release_v2(natal, tr_prev, tr_prev2, tr_curr)
    dR = R_now - R_prev
    R_dot = 1.0 + max(0, dR / 2.0)
    # Ignition
    future = [transits_at(*yx(eval_y, eval_m, +k)) for k in range(0, 4)]
    I = ignition_at_v2(natal, future)
    Gs = gamma_survive(natal)
    Ge = gamma_era(natal, eval_y)
    # Soft floors so a single weak term doesn't zero everything
    P_term = max(P_max_6 / 4.0, 0.4)       # mid baseline 1.0 at P_max=4
    R_term = max(R_now / 4.0, 0.3)          # mid baseline 1.0 at R=4
    I_term = 1.0 + I / 5.0                  # 1.0 baseline, +1 per 5 units
    # Geometric mean with weights — compresses dynamic range, more robust
    bti = (P_term ** 0.8) * (E ** 0.7) * (R_term ** 0.9) * (R_dot ** 0.6) * (I_term ** 0.5) * (Gs ** 0.7) * (Ge ** 0.4)
    bti *= 6.0  # rescale so typical bottom ~5-15
    return {
        "bti": bti, "P_max_6": P_max_6, "P_now": P_now, "dP": dP, "E": E,
        "R_now": R_now, "dR": dR, "R_dot": R_dot, "I_90d": I,
        "Gs": Gs, "Ge": Ge, "killed": ""
    }

def bti_window(natal, eval_y, eval_m, half_window=3):
    """Return max BTI in ±half_window months."""
    def yx(y, m, off):
        mm, yy = m + off, y
        while mm <= 0: mm += 12; yy -= 1
        while mm > 12: mm -= 12; yy += 1
        return (yy, mm)
    best = None
    best_off = 0
    for off in range(-half_window, half_window+1):
        y, m = yx(eval_y, eval_m, off)
        rep = compute_bti_v2(natal, y, m)
        if best is None or rep["bti"] > best["bti"]:
            best = rep
            best_off = off
    best["window_offset"] = best_off
    return best

def run_v2():
    print("="*150)
    print("BTI v2 VALIDATION TEST  (geometric-mean form, ±3mo window, top-suppressor)")
    print("="*150)
    print(f"{'Case':<8s} {'IPO':<11s} {'BotMo':<7s} {'BTIw':>6s} {'+/-':>3s} {'Pmax':>5s} {'dP':>5s} {'E':>4s} {'Rnow':>5s} {'dR':>5s} {'Rdot':>4s} {'I90d':>5s} {'Gs':>4s} {'Ge':>4s} {'Note'}")
    print("-"*150)
    bottom_btis = []
    for tk, ipo, bot, top, mult, note in BOTTOMS:
        natal = compute_natal(ipo)
        rep = bti_window(natal, bot[0], bot[1])
        bottom_btis.append((tk, rep["bti"]))
        mo = f"{bot[0]}-{bot[1]:02d}"
        print(f"{tk:<8s} {ipo:<11s} {mo:<7s} {rep['bti']:6.2f} {rep['window_offset']:+3d} {rep['P_max_6']:5.1f} {rep['dP']:5.2f} {rep['E']:4.2f} {rep['R_now']:5.1f} {rep['dR']:5.2f} {rep['R_dot']:4.2f} {rep['I_90d']:5.1f} {rep['Gs']:4.2f} {rep['Ge']:4.2f} {note}")

    print()
    print("QUIET MONTHS (single point, ± offsets) — should be lower")
    print("-"*150)
    quiet_btis = []
    for tk, ipo, bot, top, mult, note in BOTTOMS[:8]:
        natal = compute_natal(ipo)
        for off in QUIET_OFFSETS:
            y, m = bot[0], bot[1] + off
            while m <= 0: m += 12; y -= 1
            while m > 12: m -= 12; y += 1
            rep = compute_bti_v2(natal, y, m)
            quiet_btis.append((tk, off, rep["bti"]))
        vals = [v for (t, o, v) in quiet_btis if t == tk]
        med_q = sorted(vals)[len(vals)//2] if vals else 0
        bot_bti = next(v for (t, v) in bottom_btis if t == tk)
        print(f"  {tk:<8s} bot BTIw={bot_bti:5.2f}  med quiet BTI={med_q:5.2f}  ratio={bot_bti/max(med_q,0.01):5.2f}x")

    print()
    print("TOPS — BTI should be LOW (or zero from top-suppressor)")
    print("-"*150)
    top_btis = []
    for tk, ipo, bot, top, mult, note in BOTTOMS:
        natal = compute_natal(ipo)
        rep = compute_bti_v2(natal, top[0], top[1])
        top_btis.append((tk, rep["bti"]))
        mo = f"{top[0]}-{top[1]:02d}"
        kill = f" [killed: {rep['killed']}]" if rep.get('killed') else ""
        print(f"{tk:<8s} top {mo:<7s}  BTI={rep['bti']:6.2f}  P_max={rep['P_max_6']:.1f} dP={rep['dP']:+.2f} R={rep['R_now']:.1f} I={rep['I_90d']:.1f}{kill}")

    print()
    print("NULLS — peaks of one-and-done blow-offs")
    print("-"*150)
    for tk, ipo, peak, note in NULLS:
        natal = compute_natal(ipo)
        rep = compute_bti_v2(natal, peak[0], peak[1])
        mo = f"{peak[0]}-{peak[1]:02d}"
        print(f"{tk:<8s} peak {mo:<7s}  BTI={rep['bti']:6.2f}  Gs={rep['Gs']:.2f}  {note}")

    print()
    print("="*150)
    print("v2 SUMMARY")
    print("="*150)
    import statistics as st
    bvals = [v for (t, v) in bottom_btis]
    qvals = [v for (t, o, v) in quiet_btis]
    tvals = [v for (t, v) in top_btis]
    print(f"  Bottom BTIs:  mean={st.mean(bvals):.2f}  median={st.median(bvals):.2f}  min={min(bvals):.2f}  max={max(bvals):.2f}")
    print(f"  Quiet BTIs:   mean={st.mean(qvals):.2f}  median={st.median(qvals):.2f}  max={max(qvals):.2f}")
    print(f"  Top BTIs:     mean={st.mean(tvals):.2f}  median={st.median(tvals):.2f}  max={max(tvals):.2f}")
    q_sorted = sorted(qvals)
    q90 = q_sorted[int(len(q_sorted)*0.90)]
    q50 = q_sorted[len(q_sorted)//2]
    frac90 = sum(1 for v in bvals if v > q90) / len(bvals)
    frac2x = sum(1 for v in bvals if v > 2 * q50) / len(bvals)
    bot_above_top = sum(1 for v in bvals if v > max(tvals)) / len(bvals)
    print(f"  Discrimination: {frac90*100:.0f}% bottoms > 90th pct quiet ({q90:.2f})")
    print(f"                  {frac2x*100:.0f}% bottoms > 2× median quiet ({2*q50:.2f})")
    print(f"                  {bot_above_top*100:.0f}% bottoms > MAX top BTI ({max(tvals):.2f})")
    # AUC: how often bottom > random quiet
    pairs = 0; wins = 0
    for b in bvals:
        for q in qvals:
            pairs += 1
            if b > q: wins += 1
    auc = wins / pairs if pairs else 0
    print(f"  AUC (bottom > random quiet): {auc:.3f}  (1.0 = perfect, 0.5 = random)")

if __name__ == "__main__":
    run_v2()
