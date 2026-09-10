"""
v22 — FULL UNIVERSE ASYMMETRIC scanner.

Definition of asymmetric:
  Something is asymmetric when the forward upside dwarfs current signal.
  We want: LOW score_now  →  HIGH score_peak (with bubblish signature).
  A chart "already ripping" (now=25, peak=28) is NOT asymmetric.
  A chart at now=5 going to peak=22 IS asymmetric.

Composite asymmetry metric:
  asymmetry = (peak - now)^0.9 * bubblish_peak^1.0 * runway_bonus
             / (now + 3)^0.5
  with runway_bonus = 1.0 if 3<=runway<=12 else 0.7

Filters:
  - age 1 <= age <= 40   (exclude dead names + centenarians)
  - Saturn-safe over runway
  - improvement >= 4.0
  - bubblish_peak >= 2.0
  - peak_month in future (runway >= 1)
  - now < 18 (don't surface stuff that's already at peak)

Universe: data/universe_bti_v20.csv (13,721 names - Ritter + SP500 merged)
"""
import math, csv, sys, time
from bti_test import compute_natal, transits_at, jd_of
from bti_v4 import yx
from eclipse_database import build_eclipse_database, eclipse_hits_natal
from bti_v19_empirical import (
    SINGLE_PLANET_WEIGHTS, COMPOUND_RULES, bucket_weight, closest_hard, orb
)
from bti_v21_forward import score_snapshot, saturn_pop_month, forward_analysis

START_Y, START_M = 2026, 4
MONTHS = 24

def main():
    print("Building eclipse DB...", file=sys.stderr)
    db = build_eclipse_database(1970, 2035)

    seeds = []
    with open("/home/user/cyclepapa/data/universe_bti_v20.csv") as f:
        for r in csv.DictReader(f):
            tk = (r.get("ticker") or "").strip().upper()
            ipo = (r.get("ipo") or "").strip()
            name = (r.get("name") or "").strip()
            sector = (r.get("sector") or "").strip()
            source = (r.get("source") or "").strip()
            if not tk or not ipo or len(ipo) < 10: continue
            try:
                y = int(ipo[:4])
            except:
                continue
            age = START_Y - y
            if not (1 <= age <= 40): continue
            seeds.append({"tk": tk, "ipo": ipo, "name": name, "sector": sector, "src": source, "age": age})

    # Dedupe on (ticker, ipo) — SP500 and Ritter may both have same names
    seen = set(); unique = []
    for s in seeds:
        k = (s["tk"], s["ipo"])
        if k in seen: continue
        seen.add(k); unique.append(s)

    print(f"Universe after age filter + dedupe: {len(unique)}", file=sys.stderr)

    t0 = time.time()
    rows = []
    for i, s in enumerate(unique):
        if i and i % 500 == 0:
            print(f"  {i}/{len(unique)}  {time.time()-t0:.0f}s  (kept: {len(rows)})", file=sys.stderr)
        try:
            natal = compute_natal(s["ipo"])
            fa = forward_analysis(natal, START_Y, START_M, db, months=MONTHS)
            now = fa["current"]["composite"]
            peak = fa["peak"]["composite"]
            imp = fa["improvement"]
            bubbl_peak = fa["bubblish_peak"]["bubblish"]
            if fa["runway"] < 1: continue
            if imp < 4.0: continue
            if bubbl_peak < 2.0: continue
            if now >= 18.0: continue          # already at/near peak — not asymmetric
            if not fa["saturn_safe"]: continue

            run = fa["runway"]
            runway_bonus = 1.0 if 3 <= run <= 12 else 0.7
            asymmetry = (imp ** 0.9) * (bubbl_peak ** 1.0) * runway_bonus / ((now + 3) ** 0.5)

            pk_d = fa["peak"]
            bb_d = fa["bubblish_peak"]
            rows.append({
                "tk": s["tk"], "name": s["name"], "sector": s["sector"], "src": s["src"],
                "ipo": s["ipo"], "age": s["age"],
                "now": now, "peak": peak, "imp": imp,
                "peak_mo": f"{pk_d['y']}-{pk_d['m']:02d}",
                "runway": run,
                "sat_pop": fa["saturn_pop"],
                "bubbl_now": fa["current"]["bubblish"],
                "bubbl_peak": bubbl_peak,
                "bubbl_mo": f"{bb_d['y']}-{bb_d['m']:02d}",
                "asym": asymmetry,
                "jup_natNep_peak": pk_d["jup_natNep"],
                "nep_sun_peak": pk_d["nep_sun"],
                "nep_mc_peak": pk_d["nep_mc"],
                "jup_natNep_bub": bb_d["jup_natNep"],
                "nep_sun_bub": bb_d["nep_sun"],
                "nep_mc_bub": bb_d["nep_mc"],
            })
        except Exception:
            continue

    print(f"Scan done: {time.time()-t0:.0f}s  filtered={len(rows)}", file=sys.stderr)

    rows.sort(key=lambda r: -r["asym"])

    # Export everything that survived the filters, ranked
    out = "/home/user/cyclepapa/data/universe_asymmetric_v22.csv"
    with open(out, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow([
            "rank","ticker","name","sector","source","ipo","age",
            "asymmetry","score_now","score_peak","improvement","peak_month","runway_mo",
            "saturn_pop","bubblish_now","bubblish_peak","bubblish_month",
            "peak_jup_natNep","peak_nep_sun","peak_nep_mc",
            "bubbl_jup_natNep","bubbl_nep_sun","bubbl_nep_mc",
        ])
        for i, r in enumerate(rows, 1):
            w.writerow([
                i, r["tk"], r["name"], r["sector"], r["src"], r["ipo"], r["age"],
                f"{r['asym']:.3f}", f"{r['now']:.2f}", f"{r['peak']:.2f}", f"{r['imp']:+.2f}",
                r["peak_mo"], r["runway"],
                r["sat_pop"] if r["sat_pop"] is not None else "",
                f"{r['bubbl_now']:.2f}", f"{r['bubbl_peak']:.2f}", r["bubbl_mo"],
                f"{r['jup_natNep_peak']:.2f}", f"{r['nep_sun_peak']:.2f}", f"{r['nep_mc_peak']:.2f}",
                f"{r['jup_natNep_bub']:.2f}", f"{r['nep_sun_bub']:.2f}", f"{r['nep_mc_bub']:.2f}",
            ])
    print(f"Exported {len(rows)} rows -> {out}")

    # Print the head
    print(f"\n{'='*165}")
    print(f"TOP 60 MOST ASYMMETRIC (Saturn-safe, improving>=4, bubblish_peak>=2, score_now<18)")
    print(f"{'='*165}")
    print(f"{'Rk':>3s} {'Tkr':<6s} {'IPO':<11s} {'Age':>3s} {'Src':<7s} {'Now':>5s} {'Peak':>5s} {'Δ':>5s} {'PkMo':<8s} {'Run':>3s} {'BubPk':>5s} {'BubMo':<8s} {'Asym':>6s}  Name")
    for i, r in enumerate(rows[:60], 1):
        nm = (r["name"] or "")[:28]
        print(f"{i:3d} {r['tk']:<6s} {r['ipo']:<11s} {r['age']:>3d} {r['src']:<7s} "
              f"{r['now']:5.1f} {r['peak']:5.1f} {r['imp']:+5.1f} {r['peak_mo']:<8s} "
              f"{r['runway']:>3d} {r['bubbl_peak']:5.2f} {r['bubbl_mo']:<8s} {r['asym']:6.2f}  {nm}")

    # By runway bucket
    for (lo, hi, lbl) in [(1, 4, "IMMINENT (1-4 mo)"), (5, 9, "NEAR (5-9 mo)"),
                          (10, 15, "MEDIUM (10-15 mo)"), (16, 24, "LONG (16-24 mo)")]:
        sub = [r for r in rows if lo <= r["runway"] <= hi][:25]
        if not sub: continue
        print(f"\n{'-'*165}")
        print(f"{lbl}  — top 25 by asymmetry")
        print(f"{'-'*165}")
        print(f"{'Rk':>3s} {'Tkr':<6s} {'IPO':<11s} {'Age':>3s} {'Src':<7s} {'Now':>5s} {'Peak':>5s} {'Δ':>5s} {'PkMo':<8s} {'Run':>3s} {'BubPk':>5s} {'Asym':>6s}  Name")
        for i, r in enumerate(sub, 1):
            nm = (r["name"] or "")[:35]
            print(f"{i:3d} {r['tk']:<6s} {r['ipo']:<11s} {r['age']:>3d} {r['src']:<7s} "
                  f"{r['now']:5.1f} {r['peak']:5.1f} {r['imp']:+5.1f} {r['peak_mo']:<8s} "
                  f"{r['runway']:>3d} {r['bubbl_peak']:5.2f} {r['asym']:6.2f}  {nm}")

if __name__ == "__main__":
    main()
