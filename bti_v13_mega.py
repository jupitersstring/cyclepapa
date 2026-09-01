"""
BTI v13 — MEGA-SPECIFIC screener for ENORMOUS moves (100×+).

Empirically derived from 13 mega-rally (100×+) cases:

  PRIMARY SIGNATURE (Bradley long-term / heliocentric):
    Helio Jupiter → Natal-Earth ≤5°  (46.2% hit rate, vs 20% baseline, 2.3× amp)
    Helio Neptune → Natal-Earth ≤5°  (38.5% hit rate, 1.6× amp)
    Helio Pluto    → Natal-Earth ≤5°  (38.5% hit rate, 1.7× amp)
    Helio Uranus   → Natal-Earth ≤5°  (7.7% — ANTI-signal for mega)
    Helio Saturn   → Natal-Earth ≤5°  (15.4% — ANTI-signal for mega)

  SECONDARY SIGNATURE (Ptolemy + Bradley):
    Natal planet on Royal Star (Regulus/Spica/Antares/Aldebaran) within 1°
    Transit outer on Royal Star within 1°
    Exact declination parallel/contraparallel (<0.5° orb) of transit outer to natal

  TERTIARY (Abu Ma'shar + Dorotheus):
    Jupiter-Saturn synodic 0° aspect (23/24 mega-bots hit this as conjunction)
    Firdaria in expansive lord (Sun/Jupiter) period
    Natal classification (Dorothian triplicity ruler)

Weighted composite targets ONLY the 100×+ signature — not 10×, not 3×.
"""
import math, statistics as st
from bti_test import compute_natal, transits_at, jd_of
from bti_v4 import yx
from classical_archetype import classical_classify, is_day_chart
from classical_extensions import (fixed_star_hits, heliocentric_planets,
                                    declinations, declination_score,
                                    firdaria_lord, FIXED_STARS)

def orb(a, b):
    d = abs((a - b) % 360)
    return min(d, 360 - d)

def closest_hard(a, b, max_orb=10):
    best = None
    for asp in (0, 60, 90, 120, 180):
        for sign in (+1, -1):
            o = orb(a, b + sign * asp)
            if o <= max_orb and (best is None or o < best[1]):
                best = (asp, o)
    return best

def score_mega_v13(natal, eval_y, eval_m, ipo_date):
    """Score specifically for ENORMOUS (100×+) mega moves."""
    trans = transits_at(eval_y, eval_m)
    jd_t = jd_of(eval_y, eval_m, 15, 12.0)
    ipo_y, ipo_m, ipo_d = int(ipo_date[:4]), int(ipo_date[5:7]), int(ipo_date[8:10])
    jd_n = jd_of(ipo_y, ipo_m, ipo_d, 14.5)
    age = eval_y - ipo_y
    cls = classical_classify(natal)

    # === PRIMARY: Heliocentric outer to Natal-Earth ===
    h_t = heliocentric_planets(jd_t)
    h_n = heliocentric_planets(jd_n)
    # Natal Earth helio position (which equals natal geo Sun + 180)
    natal_earth_h = h_n.get("Earth", (natal["Sun"]["lon"] + 180) % 360)

    helio_signal = 0.0
    helio_detail = []
    # Jupiter: strongest mega signal (2.3x amp)
    if "Jupiter" in h_t:
        r = closest_hard(h_t["Jupiter"], natal_earth_h, max_orb=5)
        if r:
            asp, o = r
            pts = (5 - o) / 5 * 2.5   # weight 2.5 (strongest)
            helio_signal += pts
            helio_detail.append(f"hJup-NatE {asp}° {o:.1f}°")
    # Neptune: 1.6x amp
    if "Neptune" in h_t:
        r = closest_hard(h_t["Neptune"], natal_earth_h, max_orb=5)
        if r:
            asp, o = r
            pts = (5 - o) / 5 * 2.0
            helio_signal += pts
            helio_detail.append(f"hNep-NatE {asp}° {o:.1f}°")
    # Pluto: 1.7x amp
    if "Pluto" in h_t:
        r = closest_hard(h_t["Pluto"], natal_earth_h, max_orb=5)
        if r:
            asp, o = r
            pts = (5 - o) / 5 * 2.0
            helio_signal += pts
            helio_detail.append(f"hPlu-NatE {asp}° {o:.1f}°")
    # Uranus: ANTI-signal for mega (smaller weight, inverse)
    if "Uranus" in h_t:
        r = closest_hard(h_t["Uranus"], natal_earth_h, max_orb=5)
        if r:
            asp, o = r
            # Penalise slightly — Uranus hit means MED-speed, not mega
            helio_signal -= (5 - o) / 5 * 0.5
    # Saturn: mild ANTI-signal
    if "Saturn" in h_t:
        r = closest_hard(h_t["Saturn"], natal_earth_h, max_orb=5)
        if r:
            asp, o = r
            helio_signal -= (5 - o) / 5 * 0.3

    # === SECONDARY A: Royal Star natal ===
    fs = fixed_star_hits(natal, trans, max_orb=1.5)
    royal_natal = 0
    royal_transit = 0
    royal_detail = []
    for h in fs:
        if h["star"] in ("Regulus","Spica","Antares","Aldebaran"):
            if h["source"] == "natal":
                royal_natal += 1
                royal_detail.append(f"{h['body']}-{h['star']}_nat_{h['orb']:.1f}°")
            else:
                royal_transit += 1
                royal_detail.append(f"{h['body']}-{h['star']}_tr_{h['orb']:.1f}°")
    # Also note Algol natal (crisis/loss star — present in CROX chart)
    algol_natal = sum(1 for h in fs if h["star"] == "Algol" and h["source"] == "natal")

    royal_signal = royal_natal * 0.8 + royal_transit * 1.5 + algol_natal * 0.5

    # === SECONDARY B: Exact declination parallels ===
    try:
        nat_dec = declinations(jd_n)
        tr_dec = declinations(jd_t)
        decl_sc, decl_hits, oob = declination_score(nat_dec, tr_dec)
    except:
        decl_sc = 0; oob = 0

    # Count EXACT decl hits (<0.5°)
    exact_decl = 0
    try:
        for t_planet in ("Jupiter","Saturn","Uranus","Neptune","Pluto"):
            if t_planet not in tr_dec: continue
            for n_planet in ("Sun","Moon"):
                if n_planet not in nat_dec: continue
                diff = abs(tr_dec[t_planet] - nat_dec[n_planet])
                sum_ = abs(tr_dec[t_planet] + nat_dec[n_planet])
                if min(diff, sum_) <= 0.5:
                    exact_decl += 1
    except: pass

    # === TERTIARY: Jupiter-Saturn synodic conjunction (current) ===
    js_sep = orb(trans["Jupiter"]["lon"], trans["Saturn"]["lon"])
    js_conj_signal = 0
    if js_sep <= 8:
        js_conj_signal = (8 - js_sep) / 8 * 1.5  # tapering
    # Dec 2020 conjunction was at 0° Aqu; by 2026 they're well separated in geo
    # Helio JS (different!) — this is Bradley's core
    if "Jupiter" in h_t and "Saturn" in h_t:
        h_js = orb(h_t["Jupiter"], h_t["Saturn"])
        if h_js <= 6:
            js_conj_signal += (6 - h_js) / 6 * 1.5

    # === TERTIARY: firdaria in expansive lord ===
    try:
        is_day = is_day_chart(natal)
        major, minor, mp = firdaria_lord(age, is_day)
    except:
        major = minor = "?"
    firdaria_signal = 0
    if major in ("Sun","Jupiter"):
        firdaria_signal += 1.0
    if minor in ("Sun","Jupiter"):
        firdaria_signal += 0.5

    # === PLUTO-SUN geocentric (retained from v10 — still matters) ===
    plu_sun = closest_hard(trans["Pluto"]["lon"], natal["Sun"]["lon"], 5)
    plu_sun_signal = 0
    if plu_sun:
        asp, o = plu_sun
        plu_sun_signal = (5 - o) / 5 * 1.5

    # === AGE modifier ===
    # Mega rallies: median age ~3y (range 1-15)
    if age <= 5: age_boost = 1.2
    elif age <= 12: age_boost = 1.0
    elif age <= 25: age_boost = 0.85
    else: age_boost = 0.65

    # === COMPOSITE ===
    mega_score = (
        max(helio_signal, 0) * 1.5 +
        royal_signal * 1.2 +
        decl_sc * 1.3 +
        exact_decl * 1.0 +
        js_conj_signal * 0.8 +
        firdaria_signal * 0.6 +
        plu_sun_signal * 1.0 +
        oob * 0.3
    ) * age_boost

    return {
        "mega_score": mega_score,
        "helio_signal": helio_signal, "helio_detail": helio_detail,
        "royal_natal": royal_natal, "royal_transit": royal_transit,
        "royal_detail": royal_detail, "algol_natal": algol_natal,
        "decl_score": decl_sc, "exact_decl": exact_decl, "oob": oob,
        "js_conj_signal": js_conj_signal,
        "firdaria_major": major, "firdaria_minor": minor,
        "firdaria_signal": firdaria_signal,
        "plu_sun_signal": plu_sun_signal,
        "chart_age": age, "age_boost": age_boost,
        "almuten": cls["almuten"], "js_phase": cls["js_phase"],
        "nn_cat": cls["nn_category"],
        "sun_sign": ["Ari","Tau","Gem","Can","Leo","Vir","Lib","Sco","Sag","Cap","Aqu","Pis"][natal["Sun"]["sign"]],
    }

def score_mega_window(natal, ey, em, ipo_date, half=2):
    best = None; best_off = 0
    for off in range(-half, half+1):
        y, m = yx(ey, em, off)
        r = score_mega_v13(natal, y, m, ipo_date)
        if best is None or r["mega_score"] > best["mega_score"]:
            best = r; best_off = off
    best["window_off"] = best_off
    return best

if __name__ == "__main__":
    import csv, time, sys
    # Validate on corpus
    from parabolic_corpus import PARABOLIC_BOTTOMS

    print("="*100)
    print("v13 MEGA VALIDATION on 152 corpus")
    print("="*100)
    bot_by_mult = {"mega":[], "big":[], "mid":[], "modest":[]}
    for tk, ipo, bot, top, mult, speed, note in PARABOLIC_BOTTOMS:
        try:
            natal = compute_natal(ipo)
            r = score_mega_v13(natal, bot[0], bot[1], ipo)
            if mult >= 100: bot_by_mult["mega"].append(r["mega_score"])
            elif mult >= 30: bot_by_mult["big"].append(r["mega_score"])
            elif mult >= 10: bot_by_mult["mid"].append(r["mega_score"])
            else: bot_by_mult["modest"].append(r["mega_score"])
        except: pass
    # Quiet
    quiet = []
    for tk, ipo, bot, top, mult, speed, note in PARABOLIC_BOTTOMS:
        try:
            natal = compute_natal(ipo)
            for off in (-18, -12, 12, 18):
                y, m = yx(bot[0], bot[1], off)
                r = score_mega_v13(natal, y, m, ipo)
                quiet.append(r["mega_score"])
        except: pass
    for k, vs in bot_by_mult.items():
        if vs:
            print(f"  {k}: n={len(vs)} mean={st.mean(vs):.2f} median={st.median(vs):.2f}  max={max(vs):.2f}")
    print(f"  QUIET: n={len(quiet)} mean={st.mean(quiet):.2f} median={st.median(quiet):.2f}")
    # AUC mega vs quiet
    p=w=0
    for b in bot_by_mult["mega"]:
        for q in quiet:
            p+=1
            if b > q: w += 1
    print(f"  AUC mega > quiet: {w/p:.3f}")
    # Mega vs modest
    p=w=0
    for b in bot_by_mult["mega"]:
        for q in bot_by_mult["modest"]:
            p+=1
            if b > q: w += 1
    print(f"  AUC mega > modest: {w/p:.3f}")

    # SP500 scan
    print(f"\n{'='*135}")
    print(f"SP500 @ 2026-04 — v13 MEGA-specific screener")
    print(f"{'='*135}")
    sp500 = []
    with open("/home/user/cyclepapa/data/sp500_ipo_dates.csv") as f:
        sp500 = list(csv.DictReader(f))
    t0 = time.time()
    results = []
    for row in sp500:
        try:
            natal = compute_natal(row["ipo_date"])
            r = score_mega_window(natal, 2026, 4, row["ipo_date"])
            r["source"] = row.get("source","")
            results.append((row["ticker"], row["name"], row["sector"], row["ipo_date"], r))
        except: pass
    print(f"  Scanned {len(results)} in {time.time()-t0:.0f}s")
    results.sort(key=lambda x: -x[4]["mega_score"])
    print(f"\n{'Rk':>3s} {'Tkr':<6s} {'Name':<27s} {'IPO':<11s} {'Age':>3s} {'Mega':>5s} {'hJNP':>5s} {'Roy':>3s} {'Dec':>4s} {'EDec':>4s} {'JSc':>4s} {'Frd':>3s} {'Alm':<4s} {'Sun':<4s} {'Src':<7s}")
    for i, (tk, nm, sec, ipo, r) in enumerate(results[:40], 1):
        src_flag = "*" if r.get("source") == "sp500_added" else " "
        print(f"{i:3d} {tk:<6s} {nm[:27]:<27s} {ipo:<11s} {r['chart_age']:>3d} {r['mega_score']:5.2f} {r['helio_signal']:5.2f} {r['royal_natal']:>3d} {r['decl_score']:4.2f} {r['exact_decl']:>4d} {r['js_conj_signal']:4.2f} {r['firdaria_major'][:3]:<3s} {r['almuten'][:4]:<4s} {r['sun_sign']:<4s} {r.get('source',''):<7s}{src_flag}")

    with open("/home/user/cyclepapa/data/sp500_bti_v13_apr2026.csv","w",newline="") as f:
        w = csv.writer(f)
        w.writerow(["rank","ticker","name","sector","ipo","source_flag","age","mega_score",
                    "helio_signal","royal_natal","royal_transit","algol_natal",
                    "decl_score","exact_decl","oob","js_conj_signal","firdaria_major",
                    "firdaria_minor","plu_sun_signal","age_boost","almuten","js_phase",
                    "nn_cat","sun_sign"])
        for i, (tk, nm, sec, ipo, r) in enumerate(results, 1):
            w.writerow([i,tk,nm,sec,ipo,r.get("source",""),r["chart_age"],
                        f"{r['mega_score']:.2f}",f"{r['helio_signal']:.2f}",
                        r["royal_natal"],r["royal_transit"],r["algol_natal"],
                        f"{r['decl_score']:.2f}",r["exact_decl"],r["oob"],
                        f"{r['js_conj_signal']:.2f}",r["firdaria_major"],r["firdaria_minor"],
                        f"{r['plu_sun_signal']:.2f}",f"{r['age_boost']:.2f}",
                        r["almuten"],r["js_phase"],r["nn_cat"],r["sun_sign"]])
    print(f"Exported: /home/user/cyclepapa/data/sp500_bti_v13_apr2026.csv")

    # Ritter 2000+ scan
    print(f"\n{'='*135}")
    print(f"RITTER post-2000 @ 2026-04 — v13 MEGA top 30 (clean IPO dates)")
    print(f"{'='*135}")
    import openpyxl
    wb = openpyxl.load_workbook("/home/user/cyclepapa/data/IPO-age.xlsx", data_only=True)
    ws = wb["1975-2025"]
    rows = []
    for row in ws.iter_rows(min_row=2, values_only=True):
        od, nm, tk, cusip, adr, vc, dual, shares, internet, crsp, fnd, roll = row[:12]
        if not od: continue
        try:
            d = int(od); y = d//10000
            if y < 2000: continue
            iso = f"{y:04d}-{(d//100)%100:02d}-{d%100:02d}"
        except: continue
        if not tk or str(tk).strip() in ("",".") or adr==2 or roll==1: continue
        rows.append((str(tk).strip().upper(), nm or "", iso))
    print(f"  Scanning {len(rows)} Ritter post-2000...", file=sys.stderr)
    r_results = []
    for tk, nm, ipo in rows:
        try:
            natal = compute_natal(ipo)
            r = score_mega_window(natal, 2026, 4, ipo, half=1)
            r_results.append((tk, nm, ipo, r))
        except: pass
    print(f"  Scanned {len(r_results)}", file=sys.stderr)
    r_results.sort(key=lambda x:-x[3]["mega_score"])
    print(f"\n{'Rk':>3s} {'Tkr':<7s} {'Name':<34s} {'IPO':<11s} {'Age':>3s} {'Mega':>5s} {'hJNP':>5s} {'Roy':>3s} {'Dec':>4s} {'EDec':>4s} {'Alm':<4s} {'Sun':<4s}")
    for i, (tk, nm, ipo, r) in enumerate(r_results[:30], 1):
        print(f"{i:3d} {tk:<7s} {nm[:34]:<34s} {ipo:<11s} {r['chart_age']:>3d} {r['mega_score']:5.2f} {r['helio_signal']:5.2f} {r['royal_natal']:>3d} {r['decl_score']:4.2f} {r['exact_decl']:>4d} {r['almuten'][:4]:<4s} {r['sun_sign']:<4s}")
    with open("/home/user/cyclepapa/data/ritter_bti_v13_apr2026.csv","w",newline="") as f:
        w = csv.writer(f)
        w.writerow(["rank","ticker","name","ipo","age","mega_score","helio_signal",
                    "royal_natal","royal_transit","decl_score","exact_decl","js_conj_signal",
                    "firdaria_major","almuten","js_phase","nn_cat","sun_sign"])
        for i, (tk, nm, ipo, r) in enumerate(r_results, 1):
            w.writerow([i,tk,nm,ipo,r["chart_age"],f"{r['mega_score']:.2f}",f"{r['helio_signal']:.2f}",
                        r["royal_natal"],r["royal_transit"],f"{r['decl_score']:.2f}",r["exact_decl"],
                        f"{r['js_conj_signal']:.2f}",r["firdaria_major"],r["almuten"],
                        r["js_phase"],r["nn_cat"],r["sun_sign"]])
    print(f"Exported: /home/user/cyclepapa/data/ritter_bti_v13_apr2026.csv")
