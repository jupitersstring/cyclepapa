"""
Parabolic-rally screener — archetype-specific triggers.

From deep-dive on 9 MEGA (100x+) bottoms:
  - WMT 1974: Pluto conjunct natal Sun 1° orb (PLUTO-SUN archetype)
  - CSCO 1990: Pluto conjunct natal Moon 1.9° + outer-returns stack
  - CROX 2008: Neptune conjunct natal Sun 1.8° (NEPTUNE-SUN archetype)
  - HD 1985: Neptune square natal Sun 2.5° (NEPTUNE-SUN archetype)
  - MARA 2020: multi-outer-return stack at COVID + macro panic
  - HKD 2022: just-IPO'd, Pluto opposing natal Sun 4.4° (parabolic short-fuse)
  - BKNG 2002: Saturn-Moon sq + outer-returns
  - ORCL 1990: Saturn-Moon sq + Neptune-Moon sq
  - GME 2020 (known): Saturn+Jupiter+Pluto stacking on Sun Aqu

Archetypes distilled:
  TYPE A "Pluto-Sun/Moon transformation" — transit Pluto hard aspect to Sun/Moon within 4°
  TYPE B "Neptune-Sun inflation/rebirth" — transit Neptune hard aspect to Sun within 4°
  TYPE C "Multi-stack trigger" — ≥2 outers within 5° of natal luminary at same time
  TYPE D "Great-conjunction on Sun" — transit Ju-Sa or Ju-Ur exact within 5° of natal Sun

For the evaluator, score candidate charts on these parabolic triggers.
"""
import math
import statistics as st
from collections import defaultdict
from bti_test import compute_natal, transits_at
from bti_v4 import yx

SIGNS = ["Ari","Tau","Gem","Can","Leo","Vir","Lib","Sco","Sag","Cap","Aqu","Pis"]

def orb(a, b):
    d = abs((a - b) % 360)
    return min(d, 360 - d)

def aspect_orb(a, b, aspects=(0, 90, 180), max_orb=10):
    """Closest hard-aspect orb between a and b. Returns (aspect, orb) or None."""
    best = None
    for asp in aspects:
        for sign in (+1, -1):
            o = orb(a, b + sign * asp)
            if o <= max_orb and (best is None or o < best[1]):
                best = (asp, o)
    return best

def parabolic_score(natal, eval_y, eval_m):
    """Score a chart for parabolic-rally setup at (eval_y, eval_m).
    Returns a dict with trigger scores per archetype.
    """
    trans = transits_at(eval_y, eval_m)
    # TYPE A: Pluto hard to Sun/Moon
    type_a = 0.0; type_a_detail = []
    for nt in ("Sun", "Moon"):
        if nt in natal:
            r = aspect_orb(trans["Pluto"]["lon"], natal[nt]["lon"], (0,90,180), 4)
            if r:
                asp, o = r
                pts = (4 - o) / 4 * (1.0 if asp == 0 else 0.85 if asp == 180 else 0.7)
                if nt == "Sun": pts *= 1.2
                type_a += pts
                type_a_detail.append(f"Plu-{nt} {asp}° {o:.1f}°")

    # TYPE B: Neptune hard to Sun
    type_b = 0.0; type_b_detail = []
    r = aspect_orb(trans["Neptune"]["lon"], natal["Sun"]["lon"], (0,90,180), 4)
    if r:
        asp, o = r
        type_b = (4 - o) / 4 * (1.0 if asp == 0 else 0.85 if asp == 180 else 0.75)
        type_b_detail.append(f"Nep-Sun {asp}° {o:.1f}°")
    r2 = aspect_orb(trans["Neptune"]["lon"], natal["Moon"]["lon"], (0,90,180), 4)
    if r2:
        asp, o = r2
        type_b += 0.7 * (4 - o) / 4
        type_b_detail.append(f"Nep-Moon {asp}° {o:.1f}°")

    # TYPE C: Multi-stack — count outers within 5° hard aspect to Sun/Moon
    stack_sun = 0; stack_moon = 0
    stack_detail = []
    for outer in ("Jupiter","Saturn","Uranus","Neptune","Pluto"):
        r = aspect_orb(trans[outer]["lon"], natal["Sun"]["lon"], (0,90,180), 5)
        if r:
            stack_sun += 1
            stack_detail.append(f"{outer[:3]}-Sun {r[0]}°")
        r2 = aspect_orb(trans[outer]["lon"], natal["Moon"]["lon"], (0,90,180), 5)
        if r2:
            stack_moon += 1
    stack_total = stack_sun + stack_moon * 0.7
    if stack_total >= 2: type_c = (stack_total - 1) * 1.5
    else: type_c = 0

    # TYPE D: Transit great conjunction (Jup-Sat, Jup-Ur) hard to natal Sun within 5°
    type_d = 0.0; type_d_detail = []
    # Current JS midpoint
    js_mp = (trans["Jupiter"]["lon"] + trans["Saturn"]["lon"]) / 2
    r = aspect_orb(js_mp, natal["Sun"]["lon"], (0,90,180), 5)
    # But only if Jup-Sat are close (conj or opp)
    ju_sa = orb(trans["Jupiter"]["lon"], trans["Saturn"]["lon"])
    if ju_sa < 15 or ju_sa > 165:  # conj or opposition
        if r:
            type_d += (5 - r[1]) / 5
            type_d_detail.append(f"JS-Sun {r[0]}° {r[1]:.1f}°")
    # Jup-Ur
    ju_ur_mp = (trans["Jupiter"]["lon"] + trans["Uranus"]["lon"]) / 2
    ju_ur = orb(trans["Jupiter"]["lon"], trans["Uranus"]["lon"])
    if ju_ur < 10:
        r = aspect_orb(ju_ur_mp, natal["Sun"]["lon"], (0,90,180), 5)
        if r:
            type_d += (5 - r[1]) / 5
            type_d_detail.append(f"JU-Sun {r[0]}° {r[1]:.1f}°")

    # Aggregate
    parab = type_a + type_b + type_c * 0.8 + type_d * 1.2
    # Archetype classification — dominant type
    scores = {"A_pluto_lumin": type_a, "B_neptune_lumin": type_b,
              "C_multi_stack": type_c, "D_great_conj": type_d}
    dominant = max(scores, key=scores.get) if max(scores.values()) > 0 else "none"

    return {
        "parabolic": parab,
        "type_a": type_a, "type_a_detail": type_a_detail,
        "type_b": type_b, "type_b_detail": type_b_detail,
        "type_c": type_c, "stack_sun": stack_sun, "stack_moon": stack_moon, "stack_detail": stack_detail,
        "type_d": type_d, "type_d_detail": type_d_detail,
        "dominant": dominant,
    }

# Validate on 9 mega rallies
if __name__ == "__main__":
    from secular_bottoms_corpus import SECULAR_BOTTOMS
    MEGA = [s for s in SECULAR_BOTTOMS if s[4] >= 100]
    MODEST = [s for s in SECULAR_BOTTOMS if 3 <= s[4] < 10]
    SECULAR_ONLY = [s for s in SECULAR_BOTTOMS if 10 <= s[4] < 100]

    print(f"\n{'='*100}")
    print(f"MEGA RALLIES (100×+) — parabolic trigger scores at bottom")
    print(f"{'='*100}")
    mega_scores = []
    for tk, ipo, bot, top, mult, note in MEGA:
        try:
            natal = compute_natal(ipo)
            p = parabolic_score(natal, bot[0], bot[1])
            mega_scores.append(p["parabolic"])
            print(f"  {tk:<8s} mult={mult:5d}x  parab={p['parabolic']:5.2f}  dom={p['dominant']:<18s}  A={p['type_a']:.2f} B={p['type_b']:.2f} C={p['type_c']:.2f} D={p['type_d']:.2f}")
            if p["type_a_detail"] or p["type_b_detail"] or p["stack_detail"] or p["type_d_detail"]:
                print(f"           {' | '.join(p['type_a_detail'] + p['type_b_detail'] + p['stack_detail'] + p['type_d_detail'])}")
        except Exception as e:
            print(f"  {tk}: ERR {e}")

    print(f"\n{'='*100}")
    print(f"SECULAR 10-99× (n={len(SECULAR_ONLY)}) — sample scores")
    print(f"{'='*100}")
    sec_scores = []
    for tk, ipo, bot, top, mult, note in SECULAR_ONLY[:20]:
        try:
            natal = compute_natal(ipo)
            p = parabolic_score(natal, bot[0], bot[1])
            sec_scores.append(p["parabolic"])
            print(f"  {tk:<8s} mult={mult:4d}x  parab={p['parabolic']:5.2f}  dom={p['dominant']:<18s}  A={p['type_a']:.2f} B={p['type_b']:.2f} C={p['type_c']:.2f}")
        except Exception:
            pass

    print(f"\n{'='*100}")
    print(f"MODEST 3-9× (n={len(MODEST)}) — scoring distribution")
    print(f"{'='*100}")
    mod_scores = []
    for tk, ipo, bot, top, mult, note in MODEST:
        try:
            natal = compute_natal(ipo)
            p = parabolic_score(natal, bot[0], bot[1])
            mod_scores.append(p["parabolic"])
        except Exception: pass

    print(f"\nSUMMARY:")
    print(f"  MEGA scores:    mean={st.mean(mega_scores):.2f}  median={st.median(mega_scores):.2f}  max={max(mega_scores):.2f}")
    print(f"  SECULAR scores: mean={st.mean(sec_scores):.2f}  median={st.median(sec_scores):.2f}  max={max(sec_scores):.2f}")
    print(f"  MODEST scores:  mean={st.mean(mod_scores):.2f}  median={st.median(mod_scores):.2f}  max={max(mod_scores):.2f}")

    # Baseline: quiet months
    quiet_scores = []
    for tk, ipo, bot, top, mult, note in SECULAR_BOTTOMS:
        try:
            natal = compute_natal(ipo)
            for off in (-18, -12, 12, 18):
                y, m = yx(bot[0], bot[1], off)
                p = parabolic_score(natal, y, m)
                quiet_scores.append(p["parabolic"])
        except Exception: pass
    print(f"  QUIET scores:   mean={st.mean(quiet_scores):.2f}  median={st.median(quiet_scores):.2f}  max={max(quiet_scores):.2f}")

    # AUC MEGA vs QUIET
    p = w = 0
    for m in mega_scores:
        for q in quiet_scores:
            p += 1
            if m > q: w += 1
    print(f"\n  AUC MEGA > QUIET: {w/p:.3f}")
    # AUC MEGA vs MODEST
    p = w = 0
    for m in mega_scores:
        for q in mod_scores:
            p += 1
            if m > q: w += 1
    print(f"  AUC MEGA > MODEST: {w/p:.3f}")

    # Run on SP500
    import csv
    print(f"\n{'='*120}")
    print(f"SP500 @ 2026-04 — PARABOLIC SCREENER (top 40)")
    print(f"{'='*120}")
    sp500 = []
    with open("/home/user/cyclepapa/data/sp500_ipo_dates.csv") as f:
        sp500 = list(csv.DictReader(f))
    results = []
    for row in sp500:
        try:
            natal = compute_natal(row["ipo_date"])
            # Scan ±3 months
            best = None; best_off = 0
            for off in range(-2, 3):
                y, m = yx(2026, 4, off)
                p = parabolic_score(natal, y, m)
                if best is None or p["parabolic"] > best["parabolic"]:
                    best = p; best_off = off
            best["window_off"] = best_off
            results.append((row["ticker"], row["name"], row["sector"], row["ipo_date"], best))
        except Exception: pass
    results.sort(key=lambda r: -r[4]["parabolic"])
    print(f"\n{'Rk':>3s} {'Tkr':<6s} {'Sec':<18s} {'Name':<28s} {'IPO':<11s} {'Parab':>6s} {'Dom':<18s} {'A':>5s} {'B':>5s} {'C':>5s} {'D':>5s} {'Detail'}")
    for i, (tk, nm, sec, ipo, p) in enumerate(results[:40], 1):
        detail = " | ".join(p["type_a_detail"] + p["type_b_detail"] + p["stack_detail"] + p["type_d_detail"])[:50]
        print(f"{i:3d} {tk:<6s} {sec[:18]:<18s} {nm[:28]:<28s} {ipo:<11s} {p['parabolic']:6.2f} {p['dominant']:<18s} {p['type_a']:5.2f} {p['type_b']:5.2f} {p['type_c']:5.2f} {p['type_d']:5.2f} {detail}")
    with open("/home/user/cyclepapa/data/sp500_parabolic_apr2026.csv","w",newline="") as f:
        w = csv.writer(f)
        w.writerow(["rank","ticker","name","sector","ipo_date","parabolic","dominant",
                    "type_a_pluto","type_b_neptune","type_c_multi","type_d_great_conj",
                    "stack_sun","stack_moon"])
        for i, (tk,nm,sec,ipo,p) in enumerate(results,1):
            w.writerow([i,tk,nm,sec,ipo,f"{p['parabolic']:.3f}",p["dominant"],
                        f"{p['type_a']:.2f}",f"{p['type_b']:.2f}",
                        f"{p['type_c']:.2f}",f"{p['type_d']:.2f}",
                        p["stack_sun"],p["stack_moon"]])
    print(f"\nExported: /home/user/cyclepapa/data/sp500_parabolic_apr2026.csv")
