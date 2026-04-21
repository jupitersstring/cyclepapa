"""
BTI v12 — v11 + classical-tradition boosts:
  - Fixed stars (Ptolemy/Lilly/Merriman/Crawford)
  - Heliocentric outer-to-natal aspects (Bradley long-term)
  - Declination parallels + OOB (Bradley)
  - Secondary progressions + prog-to-natal (Merriman/Crawford)
  - Firdaria time-lord (Al-Biruni/Abu Ma'shar)
"""
import math, statistics as st
import swisseph as swe
from bti_test import compute_natal, transits_at, jd_of
from classical_archetype import classical_classify, is_day_chart
from classical_extensions import (fixed_star_hits, heliocentric_planets,
                                    declinations, declination_score,
                                    secondary_progressions, progressed_lunation_phase,
                                    prog_to_natal_aspects, firdaria_lord, FIXED_STARS)
from bti_v11_full import score_parabolic_v11, score_window as v11_window, yx

def score_classical_boost(natal, eval_y, eval_m, ipo_date):
    """Return classical-extension boost score."""
    trans = transits_at(eval_y, eval_m)
    jd_t = jd_of(eval_y, eval_m, 15, 12.0)
    # Natal jd
    ipo_y, ipo_m, ipo_d = int(ipo_date[:4]), int(ipo_date[5:7]), int(ipo_date[8:10])
    jd_n = jd_of(ipo_y, ipo_m, ipo_d, 14.5)

    # (1) Fixed stars
    fs = fixed_star_hits(natal, trans, max_orb=1.5)
    fs_score = 0.0
    royal_natal = 0
    for h in fs:
        w = h["weight"]
        # Natal planet on Royal star = permanent feature
        if h["source"] == "natal":
            if h["star"] in ("Regulus","Spica","Antares","Aldebaran"):
                royal_natal += 1
                fs_score += w * 0.5 * (1 - h["orb"]/1.5)  # inherent signal
        # Transit planet on Royal star = acute event
        else:
            if h["star"] in ("Regulus","Spica","Antares","Aldebaran","Algol"):
                fs_score += w * 1.0 * (1 - h["orb"]/1.5)

    # (2) Heliocentric outer-to-natal
    try:
        h_p = heliocentric_planets(jd_t)
        helio_score = 0
        # Helio outer hard aspect to natal Sun
        for outer in ("Jupiter","Saturn","Uranus","Neptune","Pluto"):
            if outer not in h_p: continue
            for asp in (0, 90, 180):
                for sign in (+1, -1):
                    o = abs((h_p[outer] - natal["Sun"]["lon"] - sign * asp) % 360)
                    o = min(o, 360 - o)
                    if o <= 2.0:
                        helio_score += (2 - o) / 2 * 0.8
                        break
    except:
        helio_score = 0

    # (3) Declination parallels + OOB
    try:
        nat_dec = declinations(jd_n)
        tr_dec = declinations(jd_t)
        decl_sc, decl_hits, oob = declination_score(nat_dec, tr_dec)
    except:
        decl_sc = 0; decl_hits = []; oob = 0

    # (4) Progressions
    try:
        prog, age_yrs = secondary_progressions(ipo_date, f"{eval_y:04d}-{eval_m:02d}-15")
        prog_phase = progressed_lunation_phase(prog)
        pto_n = prog_to_natal_aspects(natal, prog, max_orb=1.5)
        prog_score = 0
        prog_reasons = []
        # Score prog-to-natal hard aspects (stronger) and soft (lighter)
        for h in pto_n:
            if h["aspect"] in (0, 90, 180):
                prog_score += (1.5 - h["orb"]) / 1.5 * 0.8
                prog_reasons.append(f"prog-{h['prog']} {h['aspect']}° natal-{h['natal']}")
            elif h["aspect"] in (60, 120):
                prog_score += (1.5 - h["orb"]) / 1.5 * 0.5
        # Progressed New or Full phase = major cycle marker
        if prog_phase in ("prog_new", "prog_full"):
            prog_score += 1.0
            prog_reasons.append(f"prog {prog_phase}")
        elif prog_phase in ("prog_balsamic", "prog_gibbous"):
            prog_score += 0.5
    except:
        prog_score = 0; prog_phase = "unknown"; prog_reasons = []; age_yrs = 0

    # (5) Firdaria
    try:
        is_day = is_day_chart(natal)
        major, minor, mp = firdaria_lord(age_yrs, is_day)
    except:
        major = minor = "?"; mp = 0

    return {
        "fs_score": fs_score, "royal_natal": royal_natal,
        "fs_hits": [(h["body"], h["star"], h["orb"], h["source"]) for h in fs],
        "helio_score": helio_score,
        "decl_score": decl_sc, "oob_fast": oob, "decl_hits": decl_hits,
        "prog_score": prog_score, "prog_phase": prog_phase, "prog_reasons": prog_reasons,
        "firdaria_major": major, "firdaria_minor": minor,
    }

def score_v12(natal, eval_y, eval_m, ipo_date):
    v11 = score_parabolic_v11(natal, eval_y, eval_m)
    cl = score_classical_boost(natal, eval_y, eval_m, ipo_date)
    # Classical boost weighting: these add confirmatory signal on top of v11
    classical_boost = (cl["fs_score"] * 1.2 +       # fixed stars — strong in Ptolemy/Lilly
                       cl["helio_score"] * 1.0 +    # Bradley's helio weight
                       cl["decl_score"] * 1.3 +     # Bradley declination weight (1/6 siderograph)
                       cl["prog_score"] * 1.5 +     # progressions add internal cycle
                       cl["oob_fast"] * 0.4 +       # OOB boost
                       cl["royal_natal"] * 0.8)     # royal-star natal = permanent boost
    v11["classical_boost"] = classical_boost
    v11["total_v12"] = v11["composite"] + classical_boost
    v11.update(cl)
    return v11

def v12_window(natal, ey, em, ipo_date, half=2):
    best = None; best_off = 0
    for off in range(-half, half+1):
        y, m = yx(ey, em, off)
        r = score_v12(natal, y, m, ipo_date)
        if best is None or r["total_v12"] > best["total_v12"]:
            best = r; best_off = off
    best["window_off"] = best_off
    return best

if __name__ == "__main__":
    import csv, time
    print("Running v12 on SP500 @ 2026-04 ...")
    sp500 = []
    with open("/home/user/cyclepapa/data/sp500_ipo_dates.csv") as f:
        sp500 = list(csv.DictReader(f))
    t0 = time.time()
    results = []
    for row in sp500:
        try:
            natal = compute_natal(row["ipo_date"])
            rep = v12_window(natal, 2026, 4, row["ipo_date"])
            results.append((row["ticker"], row["name"], row["sector"], row["ipo_date"], rep))
        except Exception:
            pass
    print(f"  Scanned {len(results)} in {time.time()-t0:.0f}s")
    results.sort(key=lambda r: -r[4]["total_v12"])

    # Top 30 by total_v12
    print(f"\n{'='*165}")
    print(f"SP500 @ 2026-04 — v12 TOTAL (v11 composite + classical boost)")
    print(f"{'='*165}")
    print(f"{'Rk':>3s} {'Tkr':<6s} {'Name':<28s} {'IPO':<11s} {'Age':>3s} {'Total':>5s} {'v11':>5s} {'Bst':>4s} {'FS':>4s} {'Hel':>4s} {'Dec':>4s} {'Prg':>4s} {'Roy':>3s} {'Firdar':<12s} {'PrgPh':<13s} {'FS_Natal'}")
    for i, (tk, nm, sec, ipo, r) in enumerate(results[:30], 1):
        roy = r["royal_natal"]
        nfs = [h for h in r["fs_hits"] if h[3] == "natal"]
        fs_str = ",".join(f"{h[0]}-{h[1]}" for h in nfs[:2])[:28]
        firdar = f"{r['firdaria_major'][:3]}/{r['firdaria_minor'][:3]}"
        print(f"{i:3d} {tk:<6s} {nm[:28]:<28s} {ipo:<11s} {r['chart_age']:>3d} {r['total_v12']:5.2f} {r['composite']:5.2f} {r['classical_boost']:4.2f} {r['fs_score']:4.2f} {r['helio_score']:4.2f} {r['decl_score']:4.2f} {r['prog_score']:4.2f} {roy:>3d} {firdar:<12s} {r['prog_phase']:<13s} {fs_str}")

    # Standout fixed-star natals (Royal-star chart IDs)
    print(f"\n{'='*120}")
    print(f"CHARTS WITH NATAL PLANET ON ROYAL STAR (Regulus/Spica/Antares/Aldebaran) within 1.5°")
    print(f"{'='*120}")
    royal_charts = []
    for (tk, nm, sec, ipo, r) in results:
        nfs = [h for h in r["fs_hits"] if h[3] == "natal" and h[1] in ("Regulus","Spica","Antares","Aldebaran")]
        if nfs:
            royal_charts.append((tk, nm, ipo, r, nfs))
    royal_charts.sort(key=lambda x:-x[3]["total_v12"])
    for tk, nm, ipo, r, nfs in royal_charts[:20]:
        for h in nfs:
            print(f"  {tk:<6s} {nm[:30]:<30s}  {ipo}  {h[0]:<8s} on {h[1]:<10s} ({h[2]:.2f}°)  total_v12={r['total_v12']:.1f}")

    # Export
    with open("/home/user/cyclepapa/data/sp500_bti_v12_apr2026.csv","w",newline="") as f:
        w = csv.writer(f)
        w.writerow(["rank","ticker","name","sector","ipo","age","total_v12","v11_composite",
                    "classical_boost","fs_score","helio_score","decl_score","prog_score",
                    "royal_natal","oob_fast","firdaria_major","firdaria_minor","prog_phase",
                    "almuten","js_phase","nn_cat","sun_sign","Plu_Sun"])
        for i, (tk, nm, sec, ipo, r) in enumerate(results, 1):
            w.writerow([i,tk,nm,sec,ipo,r["chart_age"],
                        f"{r['total_v12']:.2f}",f"{r['composite']:.2f}",f"{r['classical_boost']:.2f}",
                        f"{r['fs_score']:.2f}",f"{r['helio_score']:.2f}",f"{r['decl_score']:.2f}",
                        f"{r['prog_score']:.2f}",r["royal_natal"],r["oob_fast"],
                        r["firdaria_major"],r["firdaria_minor"],r["prog_phase"],
                        r["almuten"],r["js_phase"],r["nn_cat"],r["sun_sign"],f"{r['Plu_Sun']:.1f}"])
    print(f"\nExported: /home/user/cyclepapa/data/sp500_bti_v12_apr2026.csv")
