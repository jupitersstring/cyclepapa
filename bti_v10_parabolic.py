"""
BTI v10 — PARABOLIC screener calibrated on 152 parabolic bottoms.

Targets three separate use cases:

  MEGA (100x+):  Pluto-Sun ≤5° + NN in bullish zone (peak/setup/launch/bottom)
                 observed 22.2% Pluto-Sun hit vs 10.2% quiet; 44.4% bull NN

  BIG (30-99x):  Uranus-Sun ≤5° + young-mature chart (3-5yr)
                 observed 19% Ura-Sun vs 12% quiet

  MED (10-29x): young chart (<5y) + stack_sun ≥1
                median chart age 1yr for momentum rallies

  FAST (squeeze): Pluto-Sun ≤5° + JS phase "new" + very young chart (<5y)
                 observed 17.4% Pluto-Sun vs 10.2% quiet; 39% JS new

All targeting Apr 2026 evaluation with Pluto in Aquarius.
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

def score_parabolic_v10(natal, eval_y, eval_m):
    """Empirically calibrated parabolic scorer."""
    trans = transits_at(eval_y, eval_m)
    cls = classical_classify(natal)

    # Chart age
    ipo_y = int(natal["_date"][:4])
    age = eval_y - ipo_y

    # Outer-to-Sun hard orbs
    hits = {}
    for outer in ("Jupiter","Saturn","Uranus","Neptune","Pluto"):
        r = closest_hard(trans[outer]["lon"], natal["Sun"]["lon"], 12)
        hits[outer] = (r[0], r[1]) if r else (-1, 99)
    # Outer-to-Moon
    hits_m = {}
    for outer in ("Jupiter","Saturn","Uranus","Neptune","Pluto"):
        r = closest_hard(trans[outer]["lon"], natal["Moon"]["lon"], 12)
        hits_m[outer] = (r[0], r[1]) if r else (-1, 99)

    stack_sun = sum(1 for (_, o) in hits.values() if o <= 5)
    stack_moon = sum(1 for (_, o) in hits_m.values() if o <= 5)

    # === MEGA score (100x+ archetype) ===
    # Pluto-Sun ≤5° is the defining feature
    plu_sun_orb = hits["Pluto"][1]
    mega = 0.0
    mega_reasons = []
    if plu_sun_orb <= 3:
        mega += 2.0 * (3 - plu_sun_orb) / 3
        mega_reasons.append(f"Plu-Sun {hits['Pluto'][0]}° orb {plu_sun_orb:.1f}°")
    elif plu_sun_orb <= 5:
        mega += 1.0 * (5 - plu_sun_orb) / 2
        mega_reasons.append(f"Plu-Sun {hits['Pluto'][0]}° orb {plu_sun_orb:.1f}°")
    if cls["nn_category"] in ("bottom_zone","setup_zone","launch_zone","peak_zone"):
        mega += 1.0
        mega_reasons.append(f"NN {cls['nn_category']}")

    # === BIG score (30-99x archetype) ===
    ura_sun_orb = hits["Uranus"][1]
    big = 0.0
    big_reasons = []
    if ura_sun_orb <= 3:
        big += 2.0 * (3 - ura_sun_orb) / 3
        big_reasons.append(f"Ura-Sun {hits['Uranus'][0]}° orb {ura_sun_orb:.1f}°")
    elif ura_sun_orb <= 5:
        big += 1.0 * (5 - ura_sun_orb) / 2
        big_reasons.append(f"Ura-Sun {hits['Uranus'][0]}° orb {ura_sun_orb:.1f}°")
    if 2 <= age <= 7:
        big += 0.5
        big_reasons.append(f"age {age}y")

    # === MED score (10-29x "Qullamaggie momentum") ===
    # Key: young chart + NN bull zone
    med = 0.0
    med_reasons = []
    if age < 5:
        med += 1.5 * (5 - age) / 5
        med_reasons.append(f"young {age}y")
    elif age < 10:
        med += 0.5
    if cls["nn_category"] in ("peak_zone","setup_zone","launch_zone"):
        med += 0.8
        med_reasons.append(f"NN {cls['nn_category']}")
    if cls["js_phase"] in ("balsamic","new"):
        med += 0.5
        med_reasons.append(f"JS {cls['js_phase']}")
    if stack_sun >= 1:
        med += 0.5 * stack_sun
        med_reasons.append(f"stack_sun={stack_sun}")

    # === FAST score (squeeze/parabolic short-fuse) ===
    fast = 0.0
    fast_reasons = []
    if plu_sun_orb <= 5:
        fast += 1.5 * (5 - plu_sun_orb) / 5
        fast_reasons.append(f"Plu-Sun orb {plu_sun_orb:.1f}°")
    if cls["js_phase"] == "new":
        fast += 0.8
        fast_reasons.append("JS new")
    elif cls["js_phase"] in ("crescent","first_q"):
        fast += 0.3
    if age < 5:
        fast += 0.7 * (5 - age) / 5
        fast_reasons.append(f"young {age}y")

    # Gates
    Gs = gamma_survive(natal)
    Ge = gamma_era(natal, eval_y)
    gate = (Gs ** 0.4) * (Ge ** 0.3)

    return {
        "mega": mega * gate,
        "big":  big * gate,
        "med":  med * gate,
        "fast": fast * gate,
        "composite": (mega*1.5 + big*1.0 + med*0.7 + fast*0.8) * gate,
        "mega_reasons": mega_reasons, "big_reasons": big_reasons,
        "med_reasons": med_reasons, "fast_reasons": fast_reasons,
        "Plu_Sun": plu_sun_orb, "Ura_Sun": ura_sun_orb, "Nep_Sun": hits["Neptune"][1],
        "Sat_Sun": hits["Saturn"][1], "Jup_Sun": hits["Jupiter"][1],
        "stack_sun": stack_sun, "stack_moon": stack_moon,
        "js_phase": cls["js_phase"], "nn_cat": cls["nn_category"],
        "almuten": cls["almuten"], "sun_sign": SIGNS[natal["Sun"]["sign"]],
        "chart_age": age, "Gs": Gs, "Ge": Ge,
    }

def score_window(natal, ey, em, half=2):
    best = None; best_off = 0
    for off in range(-half, half+1):
        y, m = yx(ey, em, off)
        r = score_parabolic_v10(natal, y, m)
        if best is None or r["composite"] > best["composite"]:
            best = r; best_off = off
    best["window_off"] = best_off
    return best

if __name__ == "__main__":
    import csv, time
    # Validate on corpus
    from parabolic_corpus import PARABOLIC_BOTTOMS
    print("="*100)
    print("v10 VALIDATION on 152 parabolic corpus")
    print("="*100)
    results = defaultdict(lambda: {"mega":[],"big":[],"med":[],"fast":[],"comp":[]})
    for tk, ipo, bot, top, mult, speed, note in PARABOLIC_BOTTOMS:
        try:
            natal = compute_natal(ipo)
            r = score_parabolic_v10(natal, bot[0], bot[1])
            results[speed]["mega"].append(r["mega"])
            results[speed]["big"].append(r["big"])
            results[speed]["med"].append(r["med"])
            results[speed]["fast"].append(r["fast"])
            results[speed]["comp"].append(r["composite"])
        except Exception: pass
    # Quiet baseline
    quiet = {"mega":[],"big":[],"med":[],"fast":[],"comp":[]}
    for tk, ipo, bot, top, mult, speed, note in PARABOLIC_BOTTOMS:
        try:
            natal = compute_natal(ipo)
            for off in (-18, -12, 12, 18):
                y, m = yx(bot[0], bot[1], off)
                r = score_parabolic_v10(natal, y, m)
                quiet["mega"].append(r["mega"])
                quiet["big"].append(r["big"])
                quiet["med"].append(r["med"])
                quiet["fast"].append(r["fast"])
                quiet["comp"].append(r["composite"])
        except Exception: pass
    print(f"\n{'Speed':<8s} {'N':>4s}  {'mega':>6s} {'big':>6s} {'med':>6s} {'fast':>6s} {'comp':>7s}")
    for speed in ("FAST","MED","SLOW"):
        r = results[speed]
        if not r["mega"]: continue
        print(f"{speed:<8s} {len(r['mega']):>4d}  mean={st.mean(r['mega']):5.2f} {st.mean(r['big']):5.2f} {st.mean(r['med']):5.2f} {st.mean(r['fast']):5.2f} {st.mean(r['comp']):6.2f}")
    print(f"QUIET    {len(quiet['mega']):>4d}  mean={st.mean(quiet['mega']):5.2f} {st.mean(quiet['big']):5.2f} {st.mean(quiet['med']):5.2f} {st.mean(quiet['fast']):5.2f} {st.mean(quiet['comp']):6.2f}")
    # AUCs per subscore
    for subkey in ("mega","big","med","fast","comp"):
        all_bot = []
        for speed in ("FAST","MED","SLOW"):
            all_bot.extend(results[speed][subkey])
        pairs=wins=0
        for b in all_bot:
            for q in quiet[subkey]:
                pairs+=1
                if b > q: wins+=1
        print(f"  AUC {subkey} bot>quiet: {wins/pairs:.3f}")

    # SP500 scan
    print(f"\n{'='*140}")
    print(f"SP500 @ 2026-04 — v10 PARABOLIC SCREENER (top 30 by composite)")
    print(f"{'='*140}")
    sp500 = []
    with open("/home/user/cyclepapa/data/sp500_ipo_dates.csv") as f:
        sp500 = list(csv.DictReader(f))
    sp_results = []
    for row in sp500:
        try:
            natal = compute_natal(row["ipo_date"])
            r = score_window(natal, 2026, 4)
            sp_results.append((row["ticker"], row["name"], row["sector"], row["ipo_date"], r))
        except: pass
    sp_results.sort(key=lambda r: -r[4]["composite"])
    print(f"\n{'Rk':>3s} {'Tkr':<6s} {'Sec':<17s} {'Name':<28s} {'IPO':<11s} {'Age':>3s} {'Comp':>5s} {'Meg':>4s} {'Big':>4s} {'Med':>4s} {'Fst':>4s} {'PluS':>5s} {'UraS':>5s} {'Sun':<4s} {'JSph':<12s} {'NN':<12s}")
    for i, (tk, nm, sec, ipo, r) in enumerate(sp_results[:30], 1):
        print(f"{i:3d} {tk:<6s} {sec[:17]:<17s} {nm[:28]:<28s} {ipo:<11s} {r['chart_age']:>3d} {r['composite']:5.2f} {r['mega']:4.2f} {r['big']:4.2f} {r['med']:4.2f} {r['fast']:4.2f} {r['Plu_Sun']:5.1f} {r['Ura_Sun']:5.1f} {r['sun_sign']:<4s} {r['js_phase']:<12s} {r['nn_cat']:<12s}")

    # Per-category top 10
    print(f"\nTop 10 MEGA (100x+) candidates:")
    mega_sort = sorted(sp_results, key=lambda r:-r[4]["mega"])[:10]
    for i, (tk, nm, sec, ipo, r) in enumerate(mega_sort, 1):
        print(f"  {i:2d} {tk:<6s} {nm[:30]:<30s} age={r['chart_age']:>2d}  mega={r['mega']:.2f}  {' | '.join(r['mega_reasons'])}")

    print(f"\nTop 10 BIG (30-99x) candidates:")
    big_sort = sorted(sp_results, key=lambda r:-r[4]["big"])[:10]
    for i, (tk, nm, sec, ipo, r) in enumerate(big_sort, 1):
        print(f"  {i:2d} {tk:<6s} {nm[:30]:<30s} age={r['chart_age']:>2d}  big={r['big']:.2f}  {' | '.join(r['big_reasons'])}")

    print(f"\nTop 10 MED (10-29x Qullamaggie) candidates:")
    med_sort = sorted(sp_results, key=lambda r:-r[4]["med"])[:10]
    for i, (tk, nm, sec, ipo, r) in enumerate(med_sort, 1):
        print(f"  {i:2d} {tk:<6s} {nm[:30]:<30s} age={r['chart_age']:>2d}  med={r['med']:.2f}  {' | '.join(r['med_reasons'])}")

    print(f"\nTop 10 FAST (squeeze) candidates:")
    fast_sort = sorted(sp_results, key=lambda r:-r[4]["fast"])[:10]
    for i, (tk, nm, sec, ipo, r) in enumerate(fast_sort, 1):
        print(f"  {i:2d} {tk:<6s} {nm[:30]:<30s} age={r['chart_age']:>2d}  fast={r['fast']:.2f}  {' | '.join(r['fast_reasons'])}")

    # Export
    with open("/home/user/cyclepapa/data/sp500_bti_v10_apr2026.csv","w",newline="") as f:
        w = csv.writer(f)
        w.writerow(["rank","ticker","name","sector","ipo_date","chart_age","window_off",
                    "composite","mega","big","med","fast",
                    "Plu_Sun","Ura_Sun","Nep_Sun","Sat_Sun","Jup_Sun","stack_sun",
                    "js_phase","nn_cat","sun_sign","almuten","Gs","Ge"])
        for i, (tk, nm, sec, ipo, r) in enumerate(sp_results, 1):
            w.writerow([i,tk,nm,sec,ipo,r["chart_age"],r["window_off"],
                       f"{r['composite']:.2f}",f"{r['mega']:.2f}",f"{r['big']:.2f}",
                       f"{r['med']:.2f}",f"{r['fast']:.2f}",
                       f"{r['Plu_Sun']:.1f}",f"{r['Ura_Sun']:.1f}",f"{r['Nep_Sun']:.1f}",
                       f"{r['Sat_Sun']:.1f}",f"{r['Jup_Sun']:.1f}",r["stack_sun"],
                       r["js_phase"],r["nn_cat"],r["sun_sign"],r["almuten"],
                       f"{r['Gs']:.2f}",f"{r['Ge']:.2f}"])
    print(f"\nExported: /home/user/cyclepapa/data/sp500_bti_v10_apr2026.csv")

    # Also run on Ritter for broader universe
    print(f"\n{'='*140}")
    print(f"RITTER post-2000 (young charts) @ 2026-04 — top 25 by composite")
    print(f"{'='*140}")
    import openpyxl
    wb = openpyxl.load_workbook("/home/user/cyclepapa/data/IPO-age.xlsx", data_only=True)
    ws = wb["1975-2025"]
    ritter_rows = []
    for row in ws.iter_rows(min_row=2, values_only=True):
        od, nm, tk, cusip, adr, vc, dual, shares, internet, crsp, fnd, roll = row[:12]
        if not od: continue
        try:
            d = int(od); y = d//10000
            if y < 2000: continue
            iso = f"{y:04d}-{(d//100)%100:02d}-{d%100:02d}"
        except: continue
        if not tk or str(tk).strip() in ("", "."): continue
        if adr == 2 or roll == 1: continue
        ritter_rows.append((str(tk).strip().upper(), nm or "", iso))
    print(f"  Universe: {len(ritter_rows)} Ritter post-2000 IPOs", flush=True)
    t0 = time.time()
    r_results = []
    for tk, nm, ipo in ritter_rows:
        try:
            natal = compute_natal(ipo)
            r = score_window(natal, 2026, 4, half=1)
            r_results.append((tk, nm, ipo, r))
        except: pass
    r_results.sort(key=lambda x:-x[3]["composite"])
    print(f"  Scanned {len(r_results)} in {time.time()-t0:.0f}s")
    print(f"\n{'Rk':>3s} {'Tkr':<7s} {'Name':<34s} {'IPO':<11s} {'Age':>3s} {'Comp':>5s} {'Meg':>4s} {'Big':>4s} {'Med':>4s} {'Fst':>4s} {'PluS':>5s} {'UraS':>5s} {'Sun':<4s} {'JSph':<12s} {'NN':<12s}")
    for i, (tk, nm, ipo, r) in enumerate(r_results[:25], 1):
        print(f"{i:3d} {tk:<7s} {nm[:34]:<34s} {ipo:<11s} {r['chart_age']:>3d} {r['composite']:5.2f} {r['mega']:4.2f} {r['big']:4.2f} {r['med']:4.2f} {r['fast']:4.2f} {r['Plu_Sun']:5.1f} {r['Ura_Sun']:5.1f} {r['sun_sign']:<4s} {r['js_phase']:<12s} {r['nn_cat']:<12s}")
    # Export Ritter top
    with open("/home/user/cyclepapa/data/ritter_bti_v10_apr2026.csv","w",newline="") as f:
        w = csv.writer(f)
        w.writerow(["rank","ticker","name","ipo","chart_age","composite","mega","big","med","fast",
                    "Plu_Sun","Ura_Sun","js_phase","nn_cat","sun_sign"])
        for i, (tk, nm, ipo, r) in enumerate(r_results, 1):
            w.writerow([i,tk,nm,ipo,r["chart_age"],f"{r['composite']:.2f}",f"{r['mega']:.2f}",
                        f"{r['big']:.2f}",f"{r['med']:.2f}",f"{r['fast']:.2f}",
                        f"{r['Plu_Sun']:.1f}",f"{r['Ura_Sun']:.1f}",r["js_phase"],r["nn_cat"],r["sun_sign"]])
    print(f"\nExported: /home/user/cyclepapa/data/ritter_bti_v10_apr2026.csv")
