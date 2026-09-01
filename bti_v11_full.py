"""
BTI v11 — ALMUTEN-CONDITIONAL parabolic + secular screener.

Uses per-almuten trigger weights derived empirically from 152-bottom corpus:
  Jupiter-almuten: Saturn-Sun hit triggers (50% signal)
  Mars-almuten:    Saturn-Sun, Ura-Sun, Venus-Sun fast triggers
  Saturn-almuten:  Saturn RETURN on natal Saturn (+19%)
  Mercury-almuten: Saturn-Moon, Jupiter-Moon, Venus-Alm
  Sun-almuten:     Pluto triple (Sun/Moon/Almuten)
  Venus-almuten:   Mercury-Sun, Venus-Sun, Uranus-Alm

Also tags SECULAR vs PARABOLIC setup based on chart age, JS phase,
NN position. Runs on FULL Ritter (16k+) + SP500.
"""
import math, statistics as st
from collections import defaultdict
from bti_test import compute_natal, transits_at
from bti_v4 import yx, gamma_survive, gamma_era
from classical_archetype import classical_classify

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

def tight_hit(val, max_orb):
    if val > max_orb: return 0
    return (max_orb - val) / max_orb

# Per-almuten trigger table: (trigger_key, natal_target, weight)
# trigger_key = (transit_planet, orb_threshold)
ALMUTEN_TRIGGERS = {
    "Jupiter": [
        ("Saturn", "Sun", 5, 4.0),     # +50% signal
        ("Saturn", "Moon", 5, 3.0),    # +25%
        ("Jupiter", "Almuten", 5, 2.5),  # natal Jupiter return
        ("Uranus", "Moon", 5, 1.5),
        ("Neptune", "Moon", 5, 1.5),
    ],
    "Mars": [
        ("Saturn", "Sun", 5, 4.0),     # +25% signal
        ("Uranus", "Sun", 5, 3.0),     # +10%
        ("Venus", "Sun", 3, 2.0),      # +10%
        ("Saturn", "Almuten", 5, 2.0), # transit Saturn on natal Mars
        ("Mars", "Almuten", 3, 1.5),   # Mars return
    ],
    "Saturn": [
        ("Saturn", "Almuten", 5, 4.0), # Saturn return = +19%
        ("Saturn", "Moon", 5, 2.0),    # +5%
        ("Jupiter", "Moon", 5, 1.2),
    ],
    "Mercury": [
        ("Saturn", "Moon", 5, 3.5),   # +15.8%
        ("Jupiter", "Moon", 5, 2.5),   # +11.8%
        ("Jupiter", "Almuten", 5, 2.0),  # +9.2%
        ("Jupiter", "Sun", 5, 2.0),    # +7.9%
        ("Venus", "Almuten", 3, 2.5),  # +11.8%
        ("Venus", "Sun", 3, 2.5),      # +10.5%
    ],
    "Sun": [
        ("Pluto", "Sun", 5, 2.5),      # +3.8%
        ("Pluto", "Moon", 5, 2.0),     # +2.5%
        ("Pluto", "Almuten", 5, 2.5),  # conj natal Sun itself
        ("Neptune", "Sun", 5, 2.0),    # +2.5%
        ("Neptune", "Moon", 5, 2.0),   # +3.8%
        ("Mercury", "Sun", 3, 1.5),    # +5%
    ],
    "Venus": [
        ("Uranus", "Almuten", 5, 1.8), # +2.8% — natal Venus
        ("Neptune", "Moon", 5, 1.5),   # +2.5%
        ("Venus", "Sun", 3, 1.8),      # +3.2%
        ("Mercury", "Sun", 3, 2.0),    # +4.2%
        ("Mars", "Almuten", 3, 1.8),   # +3.9%
    ],
    "Moon": [
        ("Saturn", "Moon", 5, 2.5),
        ("Jupiter", "Moon", 5, 2.0),
        ("Pluto", "Moon", 5, 2.5),
        ("Uranus", "Almuten", 5, 2.0),
    ],
}

def almuten_trigger_score(natal, trans, almuten):
    """Score using almuten-conditional triggers."""
    triggers = ALMUTEN_TRIGGERS.get(almuten, [])
    score = 0.0
    hits = []
    # Natal target longitudes
    natal_lon = {"Sun": natal["Sun"]["lon"], "Moon": natal["Moon"]["lon"]}
    if almuten in natal:
        natal_lon["Almuten"] = natal[almuten]["lon"]
    for trig_planet, target, max_orb, weight in triggers:
        if target not in natal_lon: continue
        r = closest_hard(trans[trig_planet]["lon"], natal_lon[target], max_orb)
        if r:
            asp, o = r
            s = tight_hit(o, max_orb)
            score += s * weight
            if s > 0.3:
                hits.append(f"{trig_planet[:3]}-{target} {asp}° {o:.1f}°")
    return score, hits

def score_parabolic_v11(natal, eval_y, eval_m):
    """v11: almuten-conditional + MEGA/BIG/MED/FAST + secular tag."""
    trans = transits_at(eval_y, eval_m)
    cls = classical_classify(natal)
    almuten = cls["almuten"]

    # Chart age
    ipo_y = int(natal["_date"][:4])
    age = eval_y - ipo_y

    # (1) Almuten-conditional score — the headline signal
    alm_score, alm_hits = almuten_trigger_score(natal, trans, almuten)

    # (2) Generic outer-to-Sun hits
    outer_hits = {}
    for outer in ("Jupiter","Saturn","Uranus","Neptune","Pluto"):
        r = closest_hard(trans[outer]["lon"], natal["Sun"]["lon"], 12)
        outer_hits[outer] = r[1] if r else 99
    stack_sun = sum(1 for v in outer_hits.values() if v <= 5)

    # (3) MEGA archetype (Pluto-Sun + bull NN)
    mega = 0.0
    mega_reasons = []
    if outer_hits["Pluto"] <= 3:
        mega += 2.0 * tight_hit(outer_hits["Pluto"], 3)
        mega_reasons.append(f"Plu-Sun {outer_hits['Pluto']:.1f}°")
    elif outer_hits["Pluto"] <= 5:
        mega += 1.0 * tight_hit(outer_hits["Pluto"], 5)
        mega_reasons.append(f"Plu-Sun {outer_hits['Pluto']:.1f}°")
    if cls["nn_category"] in ("bottom_zone","setup_zone","launch_zone","peak_zone"):
        mega += 1.0

    # (4) BIG archetype (Ura-Sun)
    big = 0.0
    if outer_hits["Uranus"] <= 3:
        big += 2.0 * tight_hit(outer_hits["Uranus"], 3)
    elif outer_hits["Uranus"] <= 5:
        big += 1.0 * tight_hit(outer_hits["Uranus"], 5)
    if 2 <= age <= 10:
        big += 0.5

    # (5) MED Qullamaggie (young + NN bullish)
    med = 0.0
    med_reasons = []
    if age < 5: med += 1.5 * (5 - age) / 5; med_reasons.append(f"young {age}y")
    elif age < 10: med += 0.5
    if cls["nn_category"] in ("peak_zone","setup_zone","launch_zone"): med += 0.8; med_reasons.append(f"NN {cls['nn_category']}")
    if cls["js_phase"] in ("balsamic","new"): med += 0.5
    if stack_sun >= 1: med += 0.5 * stack_sun

    # (6) FAST (Pluto-Sun + JS new + young)
    fast = 0.0
    if outer_hits["Pluto"] <= 5: fast += 1.5 * tight_hit(outer_hits["Pluto"], 5)
    if cls["js_phase"] == "new": fast += 0.8
    elif cls["js_phase"] in ("crescent","first_q"): fast += 0.3
    if age < 5: fast += 0.7 * (5 - age) / 5

    # (7) SECULAR tag: chart in mid-age (5-20y) + Pluto-Sun + JS phase full/gibbous
    secular = 0.0
    secular_reasons = []
    if 5 <= age <= 25:
        secular += 1.0
        secular_reasons.append(f"secular age {age}y")
    if outer_hits["Pluto"] <= 5:
        secular += 1.5 * tight_hit(outer_hits["Pluto"], 5)
        secular_reasons.append(f"Plu-Sun {outer_hits['Pluto']:.1f}°")
    if cls["js_phase"] in ("full","gibbous","disseminating"):
        secular += 1.0
        secular_reasons.append(f"JS {cls['js_phase']}")

    Gs = gamma_survive(natal); Ge = gamma_era(natal, eval_y)
    gate = (Gs ** 0.4) * (Ge ** 0.3)

    composite = (alm_score * 1.2 + mega * 1.3 + big * 0.8 + med * 0.6 + fast * 0.7) * gate
    return {
        "composite": composite,
        "alm_score": alm_score, "alm_hits": alm_hits, "almuten": almuten,
        "mega": mega * gate, "mega_reasons": mega_reasons,
        "big": big * gate,
        "med": med * gate, "med_reasons": med_reasons,
        "fast": fast * gate,
        "secular": secular * gate, "secular_reasons": secular_reasons,
        "Plu_Sun": outer_hits["Pluto"], "Ura_Sun": outer_hits["Uranus"],
        "Nep_Sun": outer_hits["Neptune"], "Sat_Sun": outer_hits["Saturn"],
        "stack_sun": stack_sun,
        "js_phase": cls["js_phase"], "nn_cat": cls["nn_category"],
        "sun_sign": SIGNS[natal["Sun"]["sign"]], "chart_age": age,
        "Gs": Gs, "Ge": Ge,
    }

def score_window(natal, ey, em, half=2):
    best = None; best_off = 0
    for off in range(-half, half+1):
        y, m = yx(ey, em, off)
        r = score_parabolic_v11(natal, y, m)
        if best is None or r["composite"] > best["composite"]:
            best = r; best_off = off
    best["window_off"] = best_off
    return best

if __name__ == "__main__":
    import csv, time, sys
    print(f"v11 FULL Ritter (1975+) scan @ 2026-04", file=sys.stderr)

    # Load ALL Ritter (not just post-1990)
    import openpyxl
    wb = openpyxl.load_workbook("/home/user/cyclepapa/data/IPO-age.xlsx", data_only=True)
    ws = wb["1975-2025"]
    rows = []
    for row in ws.iter_rows(min_row=2, values_only=True):
        od, nm, tk, cusip, adr, vc, dual, shares, internet, crsp, fnd, roll = row[:12]
        if not od: continue
        try:
            d = int(od)
            y, m, dd = d//10000, (d//100)%100, d%100
            iso = f"{y:04d}-{m:02d}-{dd:02d}"
        except: continue
        if not tk or str(tk).strip() in ("", "."): continue
        if adr == 2: continue
        if roll == 1: continue
        rows.append({"ticker": str(tk).strip().upper(), "name": nm or "", "ipo_date": iso})
    print(f"  Universe: {len(rows)} Ritter IPOs (1975-2025 ex ADR/rollup)", file=sys.stderr)

    t0 = time.time()
    results = []
    for i, r in enumerate(rows):
        try:
            natal = compute_natal(r["ipo_date"])
            rep = score_window(natal, 2026, 4, half=1)
            results.append((r["ticker"], r["name"], r["ipo_date"], rep))
        except Exception: pass
        if (i+1) % 2000 == 0:
            print(f"  {i+1}/{len(rows)} in {time.time()-t0:.0f}s", file=sys.stderr)
    print(f"  Scanned {len(results)} in {time.time()-t0:.0f}s", file=sys.stderr)

    # Save full ranked
    with open("/home/user/cyclepapa/data/ritter_bti_v11_apr2026.csv","w",newline="") as f:
        w = csv.writer(f)
        w.writerow(["rank","ticker","name","ipo","chart_age","window_off",
                    "composite","alm_score","almuten","mega","big","med","fast","secular",
                    "Plu_Sun","Ura_Sun","Nep_Sun","Sat_Sun","stack_sun",
                    "js_phase","nn_cat","sun_sign","Gs","Ge"])
        results.sort(key=lambda x:-x[3]["composite"])
        for i, (tk, nm, ipo, r) in enumerate(results, 1):
            w.writerow([i,tk,nm,ipo,r["chart_age"],r["window_off"],
                        f"{r['composite']:.2f}",f"{r['alm_score']:.2f}",r["almuten"],
                        f"{r['mega']:.2f}",f"{r['big']:.2f}",f"{r['med']:.2f}",
                        f"{r['fast']:.2f}",f"{r['secular']:.2f}",
                        f"{r['Plu_Sun']:.1f}",f"{r['Ura_Sun']:.1f}",f"{r['Nep_Sun']:.1f}",
                        f"{r['Sat_Sun']:.1f}",r["stack_sun"],
                        r["js_phase"],r["nn_cat"],r["sun_sign"],
                        f"{r['Gs']:.2f}",f"{r['Ge']:.2f}"])

    # Print top 40 by composite
    print(f"\n{'='*145}")
    print(f"TOP 40 RITTER BY COMPOSITE (ALMUTEN-CONDITIONAL + PARABOLIC + SECULAR)")
    print(f"{'='*145}")
    print(f"{'Rk':>3s} {'Tkr':<7s} {'Name':<30s} {'IPO':<11s} {'Age':>3s} {'Comp':>5s} {'Alm':>4s} {'Meg':>4s} {'Big':>4s} {'Med':>4s} {'Fst':>4s} {'Sec':>4s} {'Ruler':<7s} {'JSph':<12s} {'NN':<12s} {'Sun':<4s}")
    for i, (tk, nm, ipo, r) in enumerate(results[:40], 1):
        print(f"{i:3d} {tk:<7s} {nm[:30]:<30s} {ipo:<11s} {r['chart_age']:>3d} {r['composite']:5.2f} {r['alm_score']:4.2f} {r['mega']:4.2f} {r['big']:4.2f} {r['med']:4.2f} {r['fast']:4.2f} {r['secular']:4.2f} {r['almuten'][:7]:<7s} {r['js_phase']:<12s} {r['nn_cat']:<12s} {r['sun_sign']:<4s}")

    # Dedicated SECULAR screener: top 30 by secular score
    print(f"\n{'='*145}")
    print(f"TOP 30 RITTER BY SECULAR SCORE (pre-multi-year-bull setups)")
    print(f"{'='*145}")
    results.sort(key=lambda x:-x[3]["secular"])
    print(f"{'Rk':>3s} {'Tkr':<7s} {'Name':<30s} {'IPO':<11s} {'Age':>3s} {'Sec':>5s} {'Comp':>5s} {'Alm':>4s} {'Ruler':<7s} {'Sun':<4s} {'NN':<12s} {'Rsn'}")
    for i, (tk, nm, ipo, r) in enumerate(results[:30], 1):
        rsn = " | ".join(r["secular_reasons"])[:60]
        print(f"{i:3d} {tk:<7s} {nm[:30]:<30s} {ipo:<11s} {r['chart_age']:>3d} {r['secular']:5.2f} {r['composite']:5.2f} {r['alm_score']:4.2f} {r['almuten'][:7]:<7s} {r['sun_sign']:<4s} {r['nn_cat']:<12s} {rsn}")

    # Top 30 MEGA parabolic
    print(f"\n{'='*145}")
    print(f"TOP 30 RITTER BY MEGA+ALMUTEN (100×+ style with chart ruler amplification)")
    print(f"{'='*145}")
    results.sort(key=lambda x:-(x[3]["mega"] + x[3]["alm_score"] * 0.5))
    print(f"{'Rk':>3s} {'Tkr':<7s} {'Name':<32s} {'IPO':<11s} {'Age':>3s} {'Meg':>4s} {'Alm':>4s} {'Plu_S':>5s} {'Ruler':<7s} {'Sun':<4s} {'NN':<12s}")
    for i, (tk, nm, ipo, r) in enumerate(results[:30], 1):
        print(f"{i:3d} {tk:<7s} {nm[:32]:<32s} {ipo:<11s} {r['chart_age']:>3d} {r['mega']:4.2f} {r['alm_score']:4.2f} {r['Plu_Sun']:5.1f} {r['almuten'][:7]:<7s} {r['sun_sign']:<4s} {r['nn_cat']:<12s}")

    # Also do SP500
    print(f"\n{'='*145}")
    print(f"SP500 @ 2026-04 — v11 TOP 40 BY COMPOSITE")
    print(f"{'='*145}")
    sp500 = []
    with open("/home/user/cyclepapa/data/sp500_ipo_dates.csv") as f:
        sp500 = list(csv.DictReader(f))
    sp_res = []
    for row in sp500:
        try:
            natal = compute_natal(row["ipo_date"])
            r = score_window(natal, 2026, 4)
            sp_res.append((row["ticker"], row["name"], row["sector"], row["ipo_date"], r))
        except: pass
    sp_res.sort(key=lambda x:-x[4]["composite"])
    print(f"{'Rk':>3s} {'Tkr':<6s} {'Sec':<17s} {'Name':<25s} {'IPO':<11s} {'Age':>3s} {'Comp':>5s} {'Alm':>4s} {'Meg':>4s} {'Sec':>4s} {'Ruler':<7s} {'Sun':<4s}")
    for i, (tk, nm, sec, ipo, r) in enumerate(sp_res[:40], 1):
        print(f"{i:3d} {tk:<6s} {sec[:17]:<17s} {nm[:25]:<25s} {ipo:<11s} {r['chart_age']:>3d} {r['composite']:5.2f} {r['alm_score']:4.2f} {r['mega']:4.2f} {r['secular']:4.2f} {r['almuten'][:7]:<7s} {r['sun_sign']:<4s}")

    with open("/home/user/cyclepapa/data/sp500_bti_v11_apr2026.csv","w",newline="") as f:
        w = csv.writer(f)
        w.writerow(["rank","ticker","name","sector","ipo","age","composite","alm_score",
                    "almuten","mega","big","med","fast","secular","Plu_Sun","Ura_Sun",
                    "js_phase","nn_cat","sun_sign"])
        for i, (tk, nm, sec, ipo, r) in enumerate(sp_res, 1):
            w.writerow([i,tk,nm,sec,ipo,r["chart_age"],f"{r['composite']:.2f}",f"{r['alm_score']:.2f}",
                        r["almuten"],f"{r['mega']:.2f}",f"{r['big']:.2f}",f"{r['med']:.2f}",
                        f"{r['fast']:.2f}",f"{r['secular']:.2f}",
                        f"{r['Plu_Sun']:.1f}",f"{r['Ura_Sun']:.1f}",
                        r["js_phase"],r["nn_cat"],r["sun_sign"]])
