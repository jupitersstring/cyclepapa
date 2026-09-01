"""
BTI v6 — INFLECTION MODE (Pre-Ignition)

Key reframe: the goal is to detect the MOMENT OF CHANGE — pressure just cracking,
benefic release just beginning, detonator arriving 4-9 months AHEAD.
Not current bullish states (which means already running).

Changes from v5:
1. R_awakening: reward (dR > 0 AND R_now LOW), not high R_now.
   - R went 0 -> 2 this month  = STRONG awakening
   - R went 4 -> 6 this month  = ALREADY ACTIVE, penalised
2. I_forward: score detonators 4-9 months ahead, not 0-3.
   Imminent ignition means already priced in.
3. Burn meter: sum of R over months 6-24 ago. High burn = already had window.
4. P_still_active: require P_now > 50% of P_max_18. Pain must still be present.
5. dP_fresh_negative: ideal dP is just-turned-negative (-0.5 to -1.5).
   Not long-easing (pressure gone), not still rising.
"""
from __future__ import annotations
import math, statistics as st
import swisseph as swe
from bti_test import (compute_natal, transits_at, gamma_survive, gamma_era,
                      hard_orb, any_aspect_orb, orb, MEAN_SPEEDS,
                      BOTTOMS, NULLS, QUIET_OFFSETS)
from bti_v5 import pressure_v5, release_v5, ignition_at_v5
from bti_v4 import yx

def compute_bti_v6(natal, eval_y, eval_m):
    # --- 1. Pressure arc: past 24 months (extended window) ---
    P_24 = []; R_24 = []
    for k in range(24, -1, -1):
        y, m = yx(eval_y, eval_m, -k)
        tr = transits_at(y, m)
        tr_p = transits_at(*yx(y, m, -1))
        tr_n = transits_at(*yx(y, m, +1))
        P_24.append(pressure_v5(natal, tr))
        R_24.append(release_v5(natal, tr, tr_p, tr_n))

    P_max_24 = max(P_24)
    P_now = P_24[-1]
    P_sum = sum(P_24)
    # P derivative: current vs 3-month moving avg
    P_3 = sum(P_24[-3:]) / 3
    P_prev3 = sum(P_24[-6:-3]) / 3
    dP3 = P_3 - P_prev3

    # --- 2. BURN METER: R sum over months 6-24 ago (exclude recent 6) ---
    # High burn = chart already had benefic activation = already ran
    burn_sum = sum(R_24[:-6])  # first 19 of 25 values (oldest through 6 months ago)
    burn_recent = sum(R_24[-6:])  # recent 6 months (NOT counted in burn)
    burn_ratio = burn_sum / 19.0  # average monthly R over burn window

    # --- 3. Current release — but we want LOW R, DR rising ---
    tr_prev = transits_at(*yx(eval_y, eval_m, -1))
    tr_curr = transits_at(eval_y, eval_m)
    tr_next = transits_at(*yx(eval_y, eval_m, +1))
    R_now = release_v5(natal, tr_curr, tr_prev, tr_next)
    tr_prev2 = transits_at(*yx(eval_y, eval_m, -2))
    R_prev = release_v5(natal, tr_prev, tr_prev2, tr_curr)
    dR = R_now - R_prev

    # --- 4. AWAKENING SCORE: dR > 0 AND R_now still low ---
    # Peak when dR ~2 and R_now ~1 (fresh emergence from zero)
    # Zero when dR <= 0 (not awakening) or R_now > 6 (already active)
    if dR <= 0:
        awakening = 0.15  # not awakening — but small floor to not zero everything
    else:
        # Rising component: how much dR
        rising = min(dR / 2.0, 1.5)  # cap at 1.5 for strong emergence
        # Virgin component: how much room R has to grow (high when R_now low)
        virgin = max(0, (6 - min(R_now, 6)) / 6)  # 1.0 at R=0, 0 at R=6
        awakening = 0.15 + rising * virgin * 1.5  # 0.15 to ~2.4

    # --- 5. FORWARD IGNITION: months 4-9 ahead (not 0-3) ---
    # Imminent ignition = already triggered = demote
    forward_future = [transits_at(*yx(eval_y, eval_m, +k)) for k in range(4, 10)]
    I_fwd = ignition_at_v5(natal, forward_future)
    # Near-term ignition (0-3 months) — we actively PENALISE this (too late)
    near_future = [transits_at(*yx(eval_y, eval_m, +k)) for k in range(0, 4)]
    I_near = ignition_at_v5(natal, near_future)

    # --- 6. PRESSURE-ACTIVE GATE ---
    # We want CURRENT pain, just starting to break
    p_ratio = P_now / max(P_max_24, 0.1)  # fraction of peak still felt
    if p_ratio < 0.30:
        pressure_gate = 0.25  # pressure long gone — too late, released
    elif p_ratio < 0.55:
        pressure_gate = 0.6  # pressure half-faded
    elif p_ratio <= 0.95:
        pressure_gate = 1.0  # peak-zone pain, breaking point — IDEAL
    else:
        pressure_gate = 0.7  # still maxed out — turn not started yet

    # --- 7. dP gate: ideal is -0.3 to -1.5 (just-turned-negative, fresh break) ---
    if dP3 > 0.3:
        dp_gate = 0.15  # still rising hard = pre-top or still in pain
    elif dP3 > 0:
        dp_gate = 0.4
    elif dP3 > -0.3:
        dp_gate = 0.75  # flat-to-slight-easing — weak signal
    elif dP3 >= -1.5:
        dp_gate = 1.0  # IDEAL: fresh crack
    elif dP3 >= -3.0:
        dp_gate = 0.7  # already broken hard — past the inflection
    else:
        dp_gate = 0.4  # long-collapsed

    # --- 8. BURN GATE: chart must be dormant ---
    if burn_ratio < 1.0:
        burn_gate = 1.0  # quiet chart — eligible
    elif burn_ratio < 2.0:
        burn_gate = 1.0 - (burn_ratio - 1.0) * 0.3  # 1.0 to 0.7
    elif burn_ratio < 3.5:
        burn_gate = 0.7 - (burn_ratio - 2.0) * 0.3  # 0.7 to 0.25
    else:
        burn_gate = 0.25  # heavily burned chart — already had its turn

    # --- 9. IMMINENT-IGNITION DEMOTION ---
    # If I_near > I_fwd, rally already happening or about to happen in weeks
    # Soft penalty
    if I_near > I_fwd + 2:
        imminent_pen = 0.5  # detonator already firing — too late
    elif I_near > I_fwd:
        imminent_pen = 0.75
    else:
        imminent_pen = 1.0

    # --- 10. Survival + era gates ---
    Gs = gamma_survive(natal); Ge = gamma_era(natal, eval_y)

    # --- 11. Composite ---
    P_term = min(P_max_24 / 4.0, 2.0)  # cap at 2 (P_max=8)
    I_fwd_term = 1.0 + I_fwd / 4.0  # reward forward ignition

    core = (P_term ** 0.7) * (awakening ** 0.9) * (I_fwd_term ** 0.6) * \
           (Gs ** 0.6) * (Ge ** 0.4)
    # Gates are hard multipliers (already in 0-1 range)
    bti = core * pressure_gate * dp_gate * burn_gate * imminent_pen * 3.5
    return {
        "bti": bti,
        "P_max_24": P_max_24, "P_now": P_now, "p_ratio": p_ratio,
        "dP3": dP3, "R_now": R_now, "dR": dR, "awakening": awakening,
        "I_fwd": I_fwd, "I_near": I_near,
        "burn_ratio": burn_ratio, "burn_gate": burn_gate,
        "pressure_gate": pressure_gate, "dp_gate": dp_gate,
        "imminent_pen": imminent_pen, "Gs": Gs, "Ge": Ge,
    }

def bti_window_v6(natal, ey, em, half=2):
    """Narrower window — inflection is a tight moment."""
    best = None; best_off = 0
    for off in range(-half, half+1):
        y, m = yx(ey, em, off)
        rep = compute_bti_v6(natal, y, m)
        if best is None or rep["bti"] > best["bti"]:
            best = rep; best_off = off
    best["window_offset"] = best_off
    return best

# ============================================================
# Run and compare
# ============================================================
if __name__ == "__main__":
    import csv, time
    from collections import defaultdict
    from bti_v4 import bti_window_v4
    from bti_v5 import bti_window_v5

    # Validation first
    print("="*130)
    print("v6 INFLECTION-MODE VALIDATION")
    print("="*130)
    print(f"{'Case':<8s} {'IPO':<11s} {'BotMo':<7s} {'v4':>6s} {'v5':>6s} {'v6':>6s} {'Note'}")
    bot_v4, bot_v5, bot_v6 = [], [], []
    for tk, ipo, bot, top, mult, note in BOTTOMS:
        natal = compute_natal(ipo)
        r4 = bti_window_v4(natal, bot[0], bot[1])["bti"]
        r5 = bti_window_v5(natal, bot[0], bot[1])["bti"]
        r6 = bti_window_v6(natal, bot[0], bot[1])["bti"]
        bot_v4.append(r4); bot_v5.append(r5); bot_v6.append(r6)
        print(f"{tk:<8s} {ipo:<11s} {bot[0]}-{bot[1]:02d} {r4:6.2f} {r5:6.2f} {r6:6.2f}  {note[:35]}")
    print(f"\n{'Tops':<8s}")
    top_v4, top_v5, top_v6 = [], [], []
    for tk, ipo, bot, top, mult, note in BOTTOMS:
        natal = compute_natal(ipo)
        r4 = bti_window_v4(natal, top[0], top[1], half=0)["bti"]
        r5 = bti_window_v5(natal, top[0], top[1], half=0)["bti"]
        r6 = bti_window_v6(natal, top[0], top[1], half=0)["bti"]
        top_v4.append(r4); top_v5.append(r5); top_v6.append(r6)
    print(f"\n  bottoms mean: v4={st.mean(bot_v4):.2f}  v5={st.mean(bot_v5):.2f}  v6={st.mean(bot_v6):.2f}")
    print(f"  tops mean:    v4={st.mean(top_v4):.2f}  v5={st.mean(top_v5):.2f}  v6={st.mean(top_v6):.2f}")
    r4_ratio = st.mean(bot_v4) / max(st.mean(top_v4), 0.01)
    r5_ratio = st.mean(bot_v5) / max(st.mean(top_v5), 0.01)
    r6_ratio = st.mean(bot_v6) / max(st.mean(top_v6), 0.01)
    print(f"  bot/top:      v4={r4_ratio:.2f}  v5={r5_ratio:.2f}  v6={r6_ratio:.2f}")

    # SP500 scan
    print("\n" + "="*130)
    print("SP500 @ 2026-04 — v6 INFLECTION MODE")
    print("="*130)
    sp500 = []
    with open("/home/user/cyclepapa/data/sp500_ipo_dates.csv") as f:
        sp500 = list(csv.DictReader(f))
    t0 = time.time()
    results = []
    for row in sp500:
        try:
            natal = compute_natal(row["ipo_date"])
            rep = bti_window_v6(natal, 2026, 4, half=2)
            results.append((row["ticker"], row["name"], row["sector"], row["ipo_date"], rep))
        except Exception:
            pass
    print(f"  Scanned {len(results)} in {time.time()-t0:.0f}s")
    results.sort(key=lambda r: -r[4]["bti"])

    # Load v5 for comparison
    v5_map = {}
    with open("/home/user/cyclepapa/data/sp500_bti_v5_apr2026.csv") as f:
        for r in csv.DictReader(f):
            v5_map[r["ticker"]] = float(r["bti_v5"])

    print(f"\n{'Rk':>3s} {'Tkr':<6s} {'Sec':<20s} {'Name':<28s} {'IPO':<11s} {'v5':>5s} {'v6':>5s} {'Pmax':>4s} {'p_r':>4s} {'dP3':>5s} {'awak':>4s} {'Ifw':>4s} {'burn':>4s} {'Δrank'}")
    print("-"*150)
    # Rank comparison
    v5_ranked = sorted([(tk, v5_map.get(tk,0)) for tk,_,_,_,_ in results], key=lambda x:-x[1])
    v5_rank = {tk:i+1 for i,(tk,_) in enumerate(v5_ranked)}
    for i, (tk, nm, sec, ipo, rep) in enumerate(results[:40], 1):
        v5b = v5_map.get(tk, 0)
        d_rank = v5_rank.get(tk, 999) - i
        d_str = f"+{d_rank}" if d_rank > 0 else str(d_rank)
        print(f"{i:3d} {tk:<6s} {sec[:20]:<20s} {nm[:28]:<28s} {ipo:<11s} {v5b:5.1f} {rep['bti']:5.2f} {rep['P_max_24']:4.1f} {rep['p_ratio']:4.2f} {rep['dP3']:+5.2f} {rep['awakening']:4.2f} {rep['I_fwd']:4.1f} {rep['burn_gate']:4.2f} {d_str:>5s}")

    print(f"\nDistribution: n={len(results)}  mean={st.mean([r[4]['bti'] for r in results]):.2f}  median={st.median([r[4]['bti'] for r in results]):.2f}  max={max(r[4]['bti'] for r in results):.2f}")

    # Names DROPPED from v5 top-20 that v6 demotes
    print(f"\nv5 top 20 names and their v6 position:")
    for tk, v5b in v5_ranked[:20]:
        found = next(((i+1,r) for i,(t,*_,r) in enumerate(results) if t == tk), None)
        if found:
            new_rank, rep = found
            arrow = "↓↓" if new_rank > 40 else ("↓" if new_rank > 20 else ("=" if new_rank <= 20 else ""))
            print(f"  {tk:<6s} v5={v5b:5.1f} (r{v5_rank[tk]})  ->  v6={rep['bti']:4.2f} (r{new_rank})  {arrow}  burn_gate={rep['burn_gate']:.2f}  p_ratio={rep['p_ratio']:.2f}")

    # Export
    with open("/home/user/cyclepapa/data/sp500_bti_v6_apr2026.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["rank","ticker","name","sector","ipo_date","bti_v6","window_off",
                    "P_max_24","P_now","p_ratio","dP3","R_now","awakening",
                    "I_fwd","I_near","burn_ratio","burn_gate","pressure_gate",
                    "dp_gate","imminent_pen","Gs","Ge"])
        for i, (tk,nm,sec,ipo,rep) in enumerate(results, 1):
            w.writerow([i,tk,nm,sec,ipo,f"{rep['bti']:.3f}",rep["window_offset"],
                        f"{rep['P_max_24']:.2f}",f"{rep['P_now']:.2f}",f"{rep['p_ratio']:.2f}",
                        f"{rep['dP3']:+.2f}",f"{rep['R_now']:.2f}",f"{rep['awakening']:.2f}",
                        f"{rep['I_fwd']:.2f}",f"{rep['I_near']:.2f}",f"{rep['burn_ratio']:.2f}",
                        f"{rep['burn_gate']:.2f}",f"{rep['pressure_gate']:.2f}",
                        f"{rep['dp_gate']:.2f}",f"{rep['imminent_pen']:.2f}",
                        f"{rep['Gs']:.2f}",f"{rep['Ge']:.2f}"])
    print(f"\nExported: /home/user/cyclepapa/data/sp500_bti_v6_apr2026.csv")
