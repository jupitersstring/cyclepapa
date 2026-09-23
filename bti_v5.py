"""
BTI v5 — cap-per-transit to fix chart-age inflation.

Instead of summing contributions from every (transit_planet, natal_target) pair,
take the STRONGEST hit per transit_planet and add a log(n_extra+1) bonus
for additional hits. This makes BTI bounded by the number of transiting bodies
actively engaging the chart, not by natal clustering geometry.

All other structure identical to v4.
"""
from __future__ import annotations
import math, statistics as st
import swisseph as swe
from bti_test import (compute_natal, transits_at, gamma_survive, gamma_era,
                      hard_orb, any_aspect_orb, orb, MEAN_SPEEDS,
                      BOTTOMS, NULLS, QUIET_OFFSETS)
from bti_v2 import release_v2 as _release_v2_original
from bti_v4 import yx

NATAL_STRESS_TARGETS = ["Sun","Moon","Venus","Mars"]
NATAL_STRESS_LIGHT   = ["Sun","Moon","ASC","MC"]

def _best_hit_with_extras(transit_lon, natal_targets_lons, max_orb, aspects=(0,90,180)):
    """Return (best_strength, n_extra_hits)."""
    strengths = []
    for nlon in natal_targets_lons:
        r = None
        for asp in aspects:
            o = min(orb(transit_lon, (nlon + asp) % 360), orb(transit_lon, (nlon - asp) % 360))
            if o <= max_orb and (r is None or o < r):
                r = o
        if r is not None:
            strengths.append(max(0, 1 - r / max_orb))
    if not strengths: return 0.0, 0
    strengths.sort(reverse=True)
    return strengths[0], len(strengths) - 1

def _best_hit_soft(transit_lon, natal_targets_lons, max_orb, aspects=(0,60,120)):
    strengths = []
    for nlon in natal_targets_lons:
        for asp in aspects:
            o = min(orb(transit_lon, (nlon + asp) % 360), orb(transit_lon, (nlon - asp) % 360))
            if o <= max_orb:
                strengths.append(max(0, 1 - o / max_orb))
    if not strengths: return 0.0, 0
    strengths.sort(reverse=True)
    return strengths[0], len(strengths) - 1

def pressure_v5(natal, trans):
    p = 0.0
    # Macro stressors — transit-to-transit, unchanged (no natal involvement)
    for (a, b, w) in [("Saturn","Pluto",3.0),("Saturn","Neptune",2.0),
                      ("Uranus","Pluto",2.5),("Saturn","Uranus",1.8)]:
        r = hard_orb(trans[a]["lon"], trans[b]["lon"], 8.0)
        if r: p += w * max(0, 1 - r[1]/8.0)
    # Transit Pluto → natal: CAP to best hit + log extras
    tgts = [natal[n]["lon"] for n in NATAL_STRESS_TARGETS if n in natal]
    s, n_ex = _best_hit_with_extras(trans["Pluto"]["lon"], tgts, 4.0)
    if s > 0: p += 2.0 * s * (1.0 + 0.2 * math.log1p(n_ex))
    # Transit Saturn → natal
    tgts = [natal[n]["lon"] for n in NATAL_STRESS_LIGHT if n in natal]
    s, n_ex = _best_hit_with_extras(trans["Saturn"]["lon"], tgts, 4.0)
    if s > 0: p += 1.5 * s * (1.0 + 0.2 * math.log1p(n_ex))
    # Transit Uranus → natal Sun/Moon/Venus
    tgts = [natal[n]["lon"] for n in ["Sun","Moon","Venus"] if n in natal]
    s, n_ex = _best_hit_with_extras(trans["Uranus"]["lon"], tgts, 4.0)
    if s > 0: p += 1.5 * s * (1.0 + 0.2 * math.log1p(n_ex))
    # Transit Neptune → natal Sun/Mars/Jupiter
    tgts = [natal[n]["lon"] for n in ["Sun","Mars","Jupiter"] if n in natal]
    s, n_ex = _best_hit_with_extras(trans["Neptune"]["lon"], tgts, 4.0)
    if s > 0: p += 1.2 * s * (1.0 + 0.2 * math.log1p(n_ex))
    # Mars retrograde
    if trans["Mars"]["retro"]:
        tgts = [natal[n]["lon"] for n in ["Sun","Moon","Mars","ASC"] if n in natal]
        best = 0
        for nlon in tgts:
            o = orb(trans["Mars"]["lon"], nlon)
            if o <= 6.0: best = max(best, max(0, 1 - o/6.0))
        if best > 0: p += 1.3 * best
    return min(p, 10.0)

def release_v5(natal, trans, prev_trans, next_trans):
    r = 0.0
    # Outer station-direct — cap: one contribution per stationed planet (best natal target)
    for outer in ("Saturn","Uranus","Neptune","Pluto"):
        prev_spd = prev_trans[outer]["speed"]
        curr_spd = trans[outer]["speed"]
        next_spd = next_trans[outer]["speed"]
        is_sd = (prev_spd < 0) and (curr_spd > 0 or next_spd > 0) and abs(curr_spd) < MEAN_SPEEDS[outer]*0.5
        if is_sd:
            tgts = [natal[n]["lon"] for n in ["Sun","Moon","Venus","Mars","Jupiter","ASC","MC"] if n in natal]
            best = 0; n_ex = 0
            for nlon in tgts:
                o = orb(trans[outer]["lon"], nlon)
                if o <= 3.0:
                    s = max(0, 1 - o/3.0)
                    if s > best: best = s
                    n_ex += 1
            if best > 0: r += 3.5 * best * (1.0 + 0.15 * math.log1p(max(0, n_ex-1)))
    # Jupiter ingress — unchanged (single event)
    if int(prev_trans["Jupiter"]["lon"]//30) != int(trans["Jupiter"]["lon"]//30) or \
       int(trans["Jupiter"]["lon"]//30) != int(next_trans["Jupiter"]["lon"]//30):
        new_sign = int(trans["Jupiter"]["lon"]//30)
        mult = 1.0
        if new_sign in (3, 8, 11): mult = 2.0
        if any(natal[p]["sign"] == new_sign for p in ("Sun","Moon","Mercury","Venus","Mars","Jupiter")):
            mult *= 1.5
        r += 2.0 * mult
    # Transit Jupiter to natal — CAP
    tgts = [natal[n]["lon"] for n in ["Sun","Moon","Venus","ASC","MC","Jupiter"] if n in natal]
    s, n_ex = _best_hit_soft(trans["Jupiter"]["lon"], tgts, 5.0)
    if s > 0: r += 2.0 * s * (1.0 + 0.15 * math.log1p(n_ex))
    # Transit Saturn trine/sextile to natal benefic — CAP
    tgts = [natal[n]["lon"] for n in ["Jupiter","Venus","Sun"] if n in natal]
    s, n_ex = _best_hit_soft(trans["Saturn"]["lon"], tgts, 3.0, aspects=(60,120))
    if s > 0: r += 1.0 * s * (1.0 + 0.15 * math.log1p(n_ex))
    # Transit outer trines — CAP per outer
    for outer in ("Uranus","Neptune","Pluto"):
        tgts = [natal[n]["lon"] for n in ["Jupiter","Venus","Sun"] if n in natal]
        s, n_ex = _best_hit_soft(trans[outer]["lon"], tgts, 3.0, aspects=(60,120))
        if s > 0: r += 1.2 * s * (1.0 + 0.15 * math.log1p(n_ex))
    # Transit Venus — unchanged
    tgts = [natal[n]["lon"] for n in ["Sun","ASC","MC"] if n in natal]
    s, n_ex = _best_hit_soft(trans["Venus"]["lon"], tgts, 2.0)
    if s > 0: r += 0.8 * s * (1.0 + 0.1 * math.log1p(n_ex))
    # NN ingress
    nn_sign = int(trans["NN"]["lon"]//30)
    prev_nn_sign = int(prev_trans["NN"]["lon"]//30)
    if nn_sign != prev_nn_sign:
        if any(natal[p]["sign"] == nn_sign for p in ("Sun","Moon","Jupiter","Venus")):
            r += 1.5
    return min(r, 10.0)

def ignition_at_v5(natal, future_transits):
    I = 0.0
    for i, tr in enumerate(future_transits):
        days_out = 30 * i
        prox = (90 - days_out) / 90.0
        i_local = 0.0
        if i > 0:
            prev = future_transits[i-1]
            if prev["Mars"]["retro"] and not tr["Mars"]["retro"]:
                tgts = [natal[n]["lon"] for n in ["Sun","Mars","ASC","Moon"] if n in natal]
                best = 0
                for nlon in tgts:
                    o = orb(tr["Mars"]["lon"], nlon)
                    if o <= 4.0: best = max(best, max(0, 1 - o/4.0))
                if best > 0: i_local += 2.5 * best
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
        # Benefic-to-natal CAP
        for benefic in ("Jupiter","Venus"):
            tgts = [natal[n]["lon"] for n in ["Sun","ASC","MC","Moon"] if n in natal]
            s, n_ex = _best_hit_soft(tr[benefic]["lon"], tgts, 2.0, aspects=(120,60))
            if s > 0: i_local += 1.5 * s * (1.0 + 0.1 * math.log1p(n_ex))
        I = max(I, i_local * prox)
    return I

def compute_bti_v5(natal, eval_y, eval_m):
    P_18, R_18 = [], []
    for k in range(18, -1, -1):
        y, m = yx(eval_y, eval_m, -k)
        tr = transits_at(y, m)
        tr_p = transits_at(*yx(y, m, -1))
        tr_n = transits_at(*yx(y, m, +1))
        P_18.append(pressure_v5(natal, tr))
        R_18.append(release_v5(natal, tr, tr_p, tr_n))
    P_max_18 = max(P_18); P_sum = sum(P_18); R_sum = sum(R_18)
    P_now = P_18[-1]
    P_3 = sum(P_18[-3:]) / 3
    P_pre3 = sum(P_18[-6:-3]) / 3
    dP3 = P_3 - P_pre3
    # Soft gates — same as v4
    if P_max_18 < 1.5: thin_pen = 0.20
    elif P_max_18 < 2.5: thin_pen = 0.20 + 0.55 * (P_max_18 - 1.5)
    elif P_max_18 < 4.0: thin_pen = 0.75 + 0.25 * (P_max_18 - 2.5) / 1.5
    else: thin_pen = 1.0
    rp_ratio = R_sum / max(P_sum, 1.0)
    if rp_ratio < 0.8: ben_pen = 1.0
    elif rp_ratio < 1.5: ben_pen = 1.0 - 0.5 * (rp_ratio - 0.8) / 0.7
    elif rp_ratio < 2.5: ben_pen = 0.5 - 0.3 * (rp_ratio - 1.5)
    else: ben_pen = 0.2
    if dP3 < -0.5: rise_pen = 1.0
    elif dP3 < 0: rise_pen = 0.7 + 0.3 * (-dP3) / 0.5
    elif dP3 < 0.5: rise_pen = 0.7 - 1.0 * dP3
    else: rise_pen = 0.2
    if dP3 > 0.5: E = 0.2
    elif dP3 > 0: E = 0.5 - 0.6 * dP3
    elif dP3 > -1.0: E = 0.5 - 0.5 * dP3
    else: E = 1.0
    p_ratio = P_now / max(P_max_18, 0.1)
    if p_ratio < 0.10: comp_conf = 0.5
    elif p_ratio > 0.95: comp_conf = 0.7
    else: comp_conf = 1.0
    tr_prev = transits_at(*yx(eval_y, eval_m, -1))
    tr_curr = transits_at(eval_y, eval_m)
    tr_next = transits_at(*yx(eval_y, eval_m, +1))
    R_now = release_v5(natal, tr_curr, tr_prev, tr_next)
    tr_prev2 = transits_at(*yx(eval_y, eval_m, -2))
    R_prev = release_v5(natal, tr_prev, tr_prev2, tr_curr)
    dR = R_now - R_prev
    R_dot = 1.0 + max(0, dR / 2.0)
    future = [transits_at(*yx(eval_y, eval_m, +k)) for k in range(0, 4)]
    I = ignition_at_v5(natal, future)
    Gs = gamma_survive(natal); Ge = gamma_era(natal, eval_y)
    P_term = max(P_max_18 / 4.0, 0.4)
    R_term = max(R_now / 4.0, 0.3)
    I_term = 1.0 + I / 5.0
    core = (P_term ** 0.7) * (E ** 0.7) * (R_term ** 0.8) * (R_dot ** 0.5) * \
           (I_term ** 0.5) * (Gs ** 0.6) * (Ge ** 0.4) * comp_conf
    bti = core * thin_pen * ben_pen * rise_pen * 6.0
    return {"bti": bti, "P_max_18": P_max_18, "P_now": P_now, "p_ratio": p_ratio,
            "R_now": R_now, "I_90d": I, "Gs": Gs, "Ge": Ge, "dP3": dP3,
            "thin": thin_pen, "ben": ben_pen, "rise": rise_pen}

def bti_window_v5(natal, ey, em, half=3):
    best = None; best_off = 0
    for off in range(-half, half+1):
        y, m = yx(ey, em, off)
        rep = compute_bti_v5(natal, y, m)
        if best is None or rep["bti"] > best["bti"]:
            best = rep; best_off = off
    best["window_offset"] = best_off
    return best

# ============================================================
# TEST: re-run SP500 + validation corpus with v5 and compare
# ============================================================
if __name__ == "__main__":
    import csv, time
    from bti_v4 import bti_window_v4
    from collections import defaultdict

    # 1. Re-validate on historical bottoms + tops
    print("="*120)
    print("v5 VALIDATION — bottoms + tops")
    print("="*120)
    print(f"{'Case':<8s} {'IPO':<11s} {'Date':<7s} {'v4':>6s} {'v5':>6s} {'Δ':>6s}")
    sum_v4_bot=0; sum_v5_bot=0; sum_v4_top=0; sum_v5_top=0
    for tk, ipo, bot, top, mult, note in BOTTOMS:
        natal = compute_natal(ipo)
        r4 = bti_window_v4(natal, bot[0], bot[1])
        r5 = bti_window_v5(natal, bot[0], bot[1])
        sum_v4_bot += r4["bti"]; sum_v5_bot += r5["bti"]
        print(f"{tk:<8s} {ipo:<11s} {bot[0]}-{bot[1]:02d} {r4['bti']:6.2f} {r5['bti']:6.2f} {r5['bti']-r4['bti']:+6.2f}   (bottom)")
    for tk, ipo, bot, top, mult, note in BOTTOMS:
        natal = compute_natal(ipo)
        r4 = bti_window_v4(natal, top[0], top[1], half=0)
        r5 = bti_window_v5(natal, top[0], top[1], half=0)
        sum_v4_top += r4["bti"]; sum_v5_top += r5["bti"]
    print(f"\n  Avg BOTTOM BTI: v4={sum_v4_bot/len(BOTTOMS):.2f}  v5={sum_v5_bot/len(BOTTOMS):.2f}")
    print(f"  Avg TOP BTI:    v4={sum_v4_top/len(BOTTOMS):.2f}  v5={sum_v5_top/len(BOTTOMS):.2f}")
    print(f"  v5 bot/top ratio: {(sum_v5_bot/len(BOTTOMS))/max((sum_v5_top/len(BOTTOMS)),0.01):.2f}")
    print(f"  v4 bot/top ratio: {(sum_v4_bot/len(BOTTOMS))/max((sum_v4_top/len(BOTTOMS)),0.01):.2f}")

    # 2. SP500 scan with v5
    print("\n" + "="*120)
    print("SP500 @ 2026-04 — v4 vs v5 comparison")
    print("="*120)
    sp500 = []
    with open("/home/user/cyclepapa/data/sp500_ipo_dates.csv") as f:
        sp500 = list(csv.DictReader(f))
    t0 = time.time()
    results = []
    for row in sp500:
        try:
            natal = compute_natal(row["ipo_date"])
            r5 = bti_window_v5(natal, 2026, 4, half=3)
            ipo_yr = int(row["ipo_date"][:4])
            results.append((row["ticker"], row["name"], row["sector"], row["ipo_date"], ipo_yr, r5))
        except Exception:
            pass
    print(f"  Scanned {len(results)} in {time.time()-t0:.0f}s", flush=True)
    results.sort(key=lambda r: -r[5]["bti"])

    # Also load v4 results to compare
    v4_map = {}
    with open("/home/user/cyclepapa/data/sp500_bti_apr2026.csv") as f:
        for row in csv.DictReader(f):
            v4_map[row["ticker"]] = (float(row["bti"]), int(row.get("window_off", 0)))

    print(f"\n{'Rk':>3s} {'Tkr':<6s} {'Sec':<18s} {'Name':<28s} {'IPO':<11s} {'v4':>6s} {'v5':>6s} {'Δ':>6s}")
    print("-"*120)
    for i, (tk, nm, sec, ipo, yr, rep) in enumerate(results[:30], 1):
        v4_bti = v4_map.get(tk, (0,0))[0]
        d = rep["bti"] - v4_bti
        print(f"{i:3d} {tk:<6s} {sec[:18]:<18s} {nm[:28]:<28s} {ipo:<11s} {v4_bti:6.2f} {rep['bti']:6.2f} {d:+6.2f}")

    # Distribution comparison
    btis_v5 = [r[5]["bti"] for r in results]
    btis_v4 = [v4_map[r[0]][0] for r in results if r[0] in v4_map]
    print(f"\nDistribution:")
    print(f"  v4:  mean={st.mean(btis_v4):.2f}  median={st.median(btis_v4):.2f}  max={max(btis_v4):.2f}")
    print(f"  v5:  mean={st.mean(btis_v5):.2f}  median={st.median(btis_v5):.2f}  max={max(btis_v5):.2f}")

    # Age-stratified analysis: how much did v5 compress the old-chart inflation?
    print(f"\nMedian BTI by chart-age decade:")
    by_decade = defaultdict(lambda: {"v4": [], "v5": []})
    for tk, nm, sec, ipo, yr, rep in results:
        dec = (yr // 10) * 10
        by_decade[dec]["v5"].append(rep["bti"])
        if tk in v4_map: by_decade[dec]["v4"].append(v4_map[tk][0])
    for dec in sorted(by_decade.keys()):
        v4m = st.median(by_decade[dec]["v4"]) if by_decade[dec]["v4"] else 0
        v5m = st.median(by_decade[dec]["v5"]) if by_decade[dec]["v5"] else 0
        print(f"  IPO {dec}s (n={len(by_decade[dec]['v5'])}):  v4 median={v4m:5.2f}   v5 median={v5m:5.2f}   ratio={v5m/max(v4m,0.01):.2f}")

    # Export v5
    outp = "/home/user/cyclepapa/data/sp500_bti_v5_apr2026.csv"
    with open(outp, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["ticker","name","sector","ipo_date","ipo_year","bti_v5","window_off",
                    "P_max","R_now","I","Gs","Ge","thin","ben","rise"])
        for (tk,nm,sec,ipo,yr,rep) in results:
            w.writerow([tk,nm,sec,ipo,yr,
                        f"{rep['bti']:.3f}", rep["window_offset"],
                        f"{rep['P_max_18']:.2f}", f"{rep['R_now']:.2f}",
                        f"{rep['I_90d']:.2f}", f"{rep['Gs']:.2f}", f"{rep['Ge']:.2f}",
                        f"{rep['thin']:.2f}", f"{rep['ben']:.2f}", f"{rep['rise']:.2f}"])
    print(f"\nExported: {outp}")
