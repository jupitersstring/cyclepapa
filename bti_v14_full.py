"""
BTI v14 — v13 MEGA + Eclipse-to-natal-degree layer (Silas).

Full Ritter 1975-2025 scan. Combines:
  - v13 mega-specific (helio Jup/Nep/Plu to natal-Earth, Royal Stars,
    exact declination parallels, Jupiter-Saturn helio conj, firdaria)
  - Silas eclipse-to-natal-degree layer:
      Eclipse longitude within 3° of natal sensitive point
      Weight by eclipse type (total_solar=1.5, annular_solar=1.3,
        partial_solar=0.9, total_lunar=1.1, partial_lunar=0.7, penumbral=0.4)
      Weight by recency (eclipse within last 18 months most potent)
      Weight by tightness (< 1° orb = high-conviction)
      Eclipses PRE-SEED degrees; combined with current transit triggers
      that hit the same degree = compound signal
"""
import math, csv, time, sys, statistics as st
from collections import defaultdict
import openpyxl
from bti_test import compute_natal, jd_of
from bti_v4 import yx
from bti_v13_mega import score_mega_v13
from eclipse_database import build_eclipse_database, eclipse_hits_natal, orb

ECLIPSE_TYPE_WEIGHT = {
    "total_solar": 1.5, "annular_solar": 1.3, "hybrid_solar": 1.4,
    "partial_solar": 0.9, "solar": 1.0,
    "total_lunar": 1.1, "partial_lunar": 0.7, "penumbral_lunar": 0.4, "lunar": 0.6,
}
NATAL_TARGET_WEIGHT = {
    "Sun": 1.5, "Moon": 1.3, "ASC": 1.4, "MC": 1.3,
    "Mercury": 0.9, "Venus": 1.0, "Mars": 0.9, "Jupiter": 1.1,
    "Saturn": 0.8, "Uranus": 0.9, "Neptune": 0.8, "Pluto": 0.8,
}

def eclipse_layer_score(eclipse_db, natal, eval_y, eval_m):
    """Score eclipse degree-activation layer per Silas.
    Look back 24 months, forward 6 months.
    """
    jd_center = jd_of(eval_y, eval_m, 15, 12.0)
    hits = eclipse_hits_natal(eclipse_db, natal, jd_center,
                              months_back=24, months_fwd=6, max_orb=3)
    score = 0
    detail = []
    for h in hits:
        type_w = ECLIPSE_TYPE_WEIGHT.get(h["eclipse_type"], 0.7)
        target_w = NATAL_TARGET_WEIGHT.get(h["natal_body"], 0.7)
        orb_w = (3 - h["orb"]) / 3
        # Recency: peak weight at T-6mo; tapering back
        days_offset = h["days_offset"]
        if -180 <= days_offset <= 60:
            recency = 1.0
        elif -540 <= days_offset <= -180:
            recency = 0.7
        else:
            recency = 0.3
        # Tight orb bonus (Silas 300-500% move claim)
        if h["orb"] <= 1.0:
            tight_bonus = 1.5
        elif h["orb"] <= 2.0:
            tight_bonus = 1.1
        else:
            tight_bonus = 1.0
        pts = type_w * target_w * orb_w * recency * tight_bonus
        score += pts
        if pts > 0.4:
            detail.append(f"{h['eclipse_date']}/{h['eclipse_type'][:6]}→{h['natal_body']}:{h['orb']:.1f}°")
    return score, detail, len(hits)

def score_v14(natal, eval_y, eval_m, ipo_date, eclipse_db):
    v13 = score_mega_v13(natal, eval_y, eval_m, ipo_date)
    ecl_score, ecl_detail, n_hits = eclipse_layer_score(eclipse_db, natal, eval_y, eval_m)
    v13["eclipse_score"] = ecl_score
    v13["eclipse_hits"] = n_hits
    v13["eclipse_detail"] = ecl_detail
    v13["total_v14"] = v13["mega_score"] + ecl_score * 1.2
    return v13

def window(natal, ey, em, ipo_date, db, half=2):
    best = None; best_off = 0
    for off in range(-half, half+1):
        y, m = yx(ey, em, off)
        r = score_v14(natal, y, m, ipo_date, db)
        if best is None or r["total_v14"] > best["total_v14"]:
            best = r; best_off = off
    best["window_off"] = best_off
    return best

def main():
    print("Building eclipse database 1970-2035...", file=sys.stderr)
    t0 = time.time()
    db = build_eclipse_database(1970, 2035)
    print(f"  {len(db)} eclipses in {time.time()-t0:.0f}s", file=sys.stderr)

    # Load FULL Ritter 1975-2025 (all IPOs, not just post-1990)
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
        if not tk or str(tk).strip() in ("",".") or adr==2 or roll==1: continue
        rows.append((str(tk).strip().upper(), nm or "", iso, vc, fnd))
    print(f"Universe: {len(rows)} Ritter IPOs 1975-2025 (ex ADR, ex rollup)", file=sys.stderr)

    t0 = time.time()
    results = []
    for i, (tk, nm, ipo, vc, fnd) in enumerate(rows):
        try:
            natal = compute_natal(ipo)
            r = window(natal, 2026, 4, ipo, db, half=1)
            r["vc"] = vc; r["founding"] = fnd
            results.append((tk, nm, ipo, r))
        except Exception:
            pass
        if (i+1) % 2500 == 0:
            print(f"  {i+1}/{len(rows)}  in {time.time()-t0:.0f}s", file=sys.stderr)
    print(f"  Done {len(results)} in {time.time()-t0:.0f}s", file=sys.stderr)

    # Rank by total_v14
    results.sort(key=lambda x: -x[3]["total_v14"])

    # Export
    with open("/home/user/cyclepapa/data/ritter_bti_v14_apr2026.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["rank","ticker","name","ipo","vc","founding","age","window_off",
                    "total_v14","mega_v13","eclipse_score","eclipse_hits",
                    "helio_signal","royal_natal","royal_transit","algol_natal",
                    "decl_score","exact_decl","js_conj_signal","firdaria_major",
                    "firdaria_minor","plu_sun_signal","age_boost",
                    "almuten","js_phase","nn_cat","sun_sign"])
        for i, (tk, nm, ipo, r) in enumerate(results, 1):
            w.writerow([i, tk, nm, ipo, r.get("vc",""), r.get("founding",""),
                        r["chart_age"], r["window_off"],
                        f"{r['total_v14']:.2f}", f"{r['mega_score']:.2f}",
                        f"{r['eclipse_score']:.2f}", r["eclipse_hits"],
                        f"{r['helio_signal']:.2f}", r["royal_natal"], r["royal_transit"],
                        r["algol_natal"], f"{r['decl_score']:.2f}", r["exact_decl"],
                        f"{r['js_conj_signal']:.2f}", r["firdaria_major"], r["firdaria_minor"],
                        f"{r['plu_sun_signal']:.2f}", f"{r['age_boost']:.2f}",
                        r["almuten"], r["js_phase"], r["nn_cat"], r["sun_sign"]])
    print(f"Exported: ritter_bti_v14_apr2026.csv  ({len(results)} rows)", file=sys.stderr)

    # Print top 60
    print(f"\n{'='*170}")
    print(f"RITTER FULL 1975-2025 @ 2026-04 — v14 TOTAL (mega_v13 + eclipse layer)")
    print(f"{'='*170}")
    print(f"{'Rk':>3s} {'Tkr':<7s} {'Name':<34s} {'IPO':<11s} {'Age':>3s} {'V14':>5s} {'Meg':>5s} {'Ecl':>4s} {'EclH':>4s} {'hJNP':>5s} {'Roy':>3s} {'EDec':>4s} {'Alm':<4s} {'Sun':<4s} {'NN':<11s}")
    for i, (tk, nm, ipo, r) in enumerate(results[:60], 1):
        print(f"{i:3d} {tk:<7s} {nm[:34]:<34s} {ipo:<11s} {r['chart_age']:>3d} {r['total_v14']:5.2f} {r['mega_score']:5.2f} {r['eclipse_score']:4.2f} {r['eclipse_hits']:>4d} {r['helio_signal']:5.2f} {r['royal_natal']:>3d} {r['exact_decl']:>4d} {r['almuten'][:4]:<4s} {r['sun_sign']:<4s} {r['nn_cat'][:11]:<11s}")

    # Top by SPECIFIC filter — young charts (1-6yr, Qullamaggie)
    print(f"\n{'='*170}")
    print(f"QULLAMAGGIE-AGE (1-6yr) TOP 40 — fresh charts only")
    print(f"{'='*170}")
    young = [x for x in results if 1 <= x[3]["chart_age"] <= 6]
    young.sort(key=lambda x: -x[3]["total_v14"])
    print(f"{'Rk':>3s} {'Tkr':<7s} {'Name':<36s} {'IPO':<11s} {'Age':>3s} {'V14':>5s} {'Meg':>5s} {'Ecl':>4s} {'hJNP':>5s} {'Roy':>3s} {'EDec':>4s} {'Sun':<4s} {'Alm':<4s} {'Ecl details'}")
    for i, (tk, nm, ipo, r) in enumerate(young[:40], 1):
        ecl_d = ";".join(r["eclipse_detail"][:2])[:50]
        print(f"{i:3d} {tk:<7s} {nm[:36]:<36s} {ipo:<11s} {r['chart_age']:>3d} {r['total_v14']:5.2f} {r['mega_score']:5.2f} {r['eclipse_score']:4.2f} {r['helio_signal']:5.2f} {r['royal_natal']:>3d} {r['exact_decl']:>4d} {r['sun_sign']:<4s} {r['almuten'][:4]:<4s} {ecl_d}")

    # Top SECULAR (5-25yr, Pluto-Sun triggered) with eclipse preseed
    print(f"\n{'='*170}")
    print(f"SECULAR-AGE (5-25yr) with eclipse preseed — multi-year bull candidates")
    print(f"{'='*170}")
    mature = [x for x in results if 5 <= x[3]["chart_age"] <= 25 and x[3]["eclipse_score"] > 1.5]
    mature.sort(key=lambda x: -x[3]["total_v14"])
    print(f"{'Rk':>3s} {'Tkr':<7s} {'Name':<36s} {'IPO':<11s} {'Age':>3s} {'V14':>5s} {'Meg':>5s} {'Ecl':>4s} {'hJNP':>5s} {'Roy':>3s} {'EDec':>4s} {'Sun':<4s} {'Ecl details'}")
    for i, (tk, nm, ipo, r) in enumerate(mature[:40], 1):
        ecl_d = ";".join(r["eclipse_detail"][:2])[:50]
        print(f"{i:3d} {tk:<7s} {nm[:36]:<36s} {ipo:<11s} {r['chart_age']:>3d} {r['total_v14']:5.2f} {r['mega_score']:5.2f} {r['eclipse_score']:4.2f} {r['helio_signal']:5.2f} {r['royal_natal']:>3d} {r['exact_decl']:>4d} {r['sun_sign']:<4s} {ecl_d}")

    # SUMMARY distribution
    print(f"\n{'='*80}")
    print(f"v14 SCORE DISTRIBUTION ({len(results)} IPOs)")
    print(f"{'='*80}")
    scores = [x[3]["total_v14"] for x in results]
    print(f"  Mean={st.mean(scores):.2f}  Median={st.median(scores):.2f}  Max={max(scores):.2f}")
    bands = [(0,5),(5,10),(10,15),(15,20),(20,30),(30,99)]
    for lo, hi in bands:
        n = sum(1 for s in scores if lo <= s < hi)
        pct = 100*n/len(scores)
        print(f"  [{lo:>3d}, {hi:>3d}):  {n:5d}  ({pct:4.1f}%)")

if __name__ == "__main__":
    main()
