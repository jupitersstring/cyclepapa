"""
Full SP500 scan using v24 macro-regime.
NO filtering — rank all 503 names by multiple criteria so we can see:
  - The absolute asymmetry leaders
  - The macro-regime-aligned leaders
  - The names already at peak (bearish)
  - Sector-by-sector champions
"""
import math, csv, sys, time, re
from bti_test import compute_natal, transits_at, jd_of
from bti_v4 import yx
from eclipse_database import build_eclipse_database, eclipse_hits_natal
from bti_v19_empirical import (SINGLE_PLANET_WEIGHTS, COMPOUND_RULES,
                                 bucket_weight, closest_hard, orb)
from bti_v21_forward import saturn_pop_month
from bti_v23_sector_aware import SECTOR_WEIGHTS, SUBIND_RULES, GICS, sector_bucket_weight
from bti_v24_macro import MODERN_SECTOR, modern_sector_of, score_snapshot_v24, forward_v24
from macro_regime import macro_regime_multiplier

START_Y, START_M = 2026, 4
MONTHS = 24

def gics_to_internal(gsec, gsub):
    # sub-industry override
    for pat, s in SUBIND_RULES:
        if gsub and re.search(pat, gsub, re.I): return s
    return GICS.get(gsec, "UNK")

def main():
    print("Building eclipse DB...", file=sys.stderr)
    db = build_eclipse_database(1970, 2035)

    seeds = []
    with open("/home/user/cyclepapa/data/sp500_ipo_dates.csv") as f:
        rr = csv.DictReader(f)
        for r in rr:
            tk = r["ticker"].strip().upper()
            ipo = (r.get("ipo_date") or "").strip()
            name = r.get("name","").strip()
            gsec = r.get("sector","").strip()
            if not ipo or len(ipo) < 10: continue
            try: y = int(ipo[:4])
            except: continue
            age = START_Y - y
            if age < 1: continue
            if age > 100: continue
            seeds.append({"tk":tk,"ipo":ipo,"name":name,"gics":gsec,"age":age})

    print(f"SP500 to scan: {len(seeds)}", file=sys.stderr)

    t0 = time.time()
    rows = []
    for i, s in enumerate(seeds):
        if i and i % 100 == 0:
            print(f"  {i}/{len(seeds)}  {time.time()-t0:.0f}s", file=sys.stderr)
        sec_base = gics_to_internal(s["gics"], "")
        # Check parabolic SECTOR dict for override (more specific)
        from sector_astro import SECTOR as CORPUS_SECTOR
        from bti_v23_sector_aware import MANUAL_EXTRA, SP500_SEC
        if s["tk"] in CORPUS_SECTOR: sec_base = CORPUS_SECTOR[s["tk"]]
        elif s["tk"] in MANUAL_EXTRA: sec_base = MANUAL_EXTRA[s["tk"]]
        elif s["tk"] in SP500_SEC:    sec_base = SP500_SEC[s["tk"]][0]
        mod_sec = modern_sector_of(s["tk"], sec_base)
        try:
            natal = compute_natal(s["ipo"])
            fa = forward_v24(natal, START_Y, START_M, db, sec_base, mod_sec, MONTHS)
            now = fa["cur"]["composite"]; peak = fa["peak"]["composite"]
            imp = fa["imp"]; bpk = fa["bpk"]["bubblish"]
            run = fa["runway"]
            rb = 1.0 if 3 <= run <= 12 else 0.7
            asym = (max(imp,0.01)**0.9)*(max(bpk,0.01)**1.0)*rb/((now+3)**0.5)
            pk_d = fa["peak"]; bb_d = fa["bpk"]
            rows.append({"tk":s["tk"],"name":s["name"],"gics":s["gics"],
                         "sector":sec_base,"modern":mod_sec,"ipo":s["ipo"],"age":s["age"],
                         "now":now,"peak":peak,"imp":imp,
                         "peak_mo":f"{pk_d['y']}-{pk_d['m']:02d}",
                         "runway":run,"sat_pop":fa["sat_pop"],
                         "safe":fa["safe"],
                         "bub_now":fa["cur"]["bubblish"],"bub_peak":bpk,
                         "macro_now":fa["cur"]["macro_mult"],
                         "macro_peak":pk_d["macro_mult"],
                         "asym":asym})
        except:
            continue
    print(f"Scan done: {time.time()-t0:.0f}s, {len(rows)} SP500 scored", file=sys.stderr)

    # Export
    out = "/home/user/cyclepapa/data/sp500_macro_v24.csv"
    with open(out, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["ticker","name","gics","sector","modern_sector","ipo","age",
                    "asymmetry","score_now","score_peak","improvement",
                    "peak_month","runway_mo","saturn_pop","saturn_safe",
                    "bubblish_now","bubblish_peak","macro_now","macro_peak"])
        # All rows, ranked by asymmetry
        rows.sort(key=lambda r: -r["asym"])
        for r in rows:
            w.writerow([r["tk"], r["name"], r["gics"], r["sector"], r["modern"],
                        r["ipo"], r["age"], f"{r['asym']:.3f}",
                        f"{r['now']:.2f}", f"{r['peak']:.2f}", f"{r['imp']:+.2f}",
                        r["peak_mo"], r["runway"],
                        r["sat_pop"] if r["sat_pop"] is not None else "",
                        "Y" if r["safe"] else "N",
                        f"{r['bub_now']:.2f}", f"{r['bub_peak']:.2f}",
                        f"{r['macro_now']:.2f}", f"{r['macro_peak']:.2f}"])
    print(f"Exported {len(rows)} -> {out}")

    # ---- REPORTS ----
    print(f"\n{'='*170}")
    print(f"TOP 40 SP500 BY V24 ASYMMETRY (macro-regime-aware)")
    print(f"{'='*170}")
    print(f"{'Rk':>3s} {'Tkr':<6s} {'ModSec':<14s} {'GICS':<22s} {'Age':>3s} {'Now':>5s} {'Peak':>5s} {'Δ':>5s} {'Bub':>4s} {'PkMo':<8s} {'Run':>3s} {'mPk':>4s} {'Sf':>2s} {'Asym':>5s}  Name")
    for i, r in enumerate(rows[:40], 1):
        nm = (r["name"] or "")[:26]
        print(f"{i:3d} {r['tk']:<6s} {r['modern']:<14s} {r['gics'][:21]:<22s} "
              f"{r['age']:>3d} {r['now']:5.1f} {r['peak']:5.1f} {r['imp']:+5.1f} "
              f"{r['bub_peak']:4.2f} {r['peak_mo']:<8s} {r['runway']:>3d} "
              f"{r['macro_peak']:4.2f} {'Y' if r['safe'] else 'N':<2s} "
              f"{r['asym']:5.2f}  {nm}")

    # Bottom 20 — names "already at peak" or Saturn-afflicted
    print(f"\n{'='*170}")
    print(f"BOTTOM 20 SP500 — poorly-positioned or already past peak (sell/avoid)")
    print(f"{'='*170}")
    rows.sort(key=lambda r: r["asym"])
    for i, r in enumerate(rows[:20], 1):
        nm = (r["name"] or "")[:26]
        sat = f"Sat@{r['sat_pop']}mo" if r['sat_pop'] is not None else ""
        print(f"{i:3d} {r['tk']:<6s} {r['modern']:<14s} {r['gics'][:21]:<22s} "
              f"{r['age']:>3d} {r['now']:5.1f} {r['peak']:5.1f} {r['imp']:+5.1f} "
              f"{r['bub_peak']:4.2f} {r['peak_mo']:<8s} {r['runway']:>3d} "
              f"{'Y' if r['safe'] else 'N':<2s} {sat:<10s} {r['asym']:5.2f}  {nm}")

    # Per GICS sector top-5
    print(f"\n{'='*170}")
    print(f"TOP 5 PER GICS SECTOR")
    print(f"{'='*170}")
    rows.sort(key=lambda r: -r["asym"])
    from collections import defaultdict
    by_gics = defaultdict(list)
    for r in rows:
        by_gics[r["gics"]].append(r)
    for gsec in sorted(by_gics):
        if not gsec: continue
        sub = by_gics[gsec][:5]
        print(f"\n  {gsec}")
        for r in sub:
            nm = (r["name"] or "")[:30]
            print(f"    {r['tk']:<6s} {r['modern']:<12s} {r['now']:5.1f}→{r['peak']:5.1f} "
                  f"Δ{r['imp']:+5.1f} Bub{r['bub_peak']:4.2f} Pk{r['peak_mo']}({r['runway']}mo) "
                  f"mPk{r['macro_peak']:.2f} Sf{'Y' if r['safe'] else 'N'} "
                  f"Asym{r['asym']:5.2f}  {nm}")

    # Regime-aligned — macro_peak >=1.5 AND asym >=5
    print(f"\n{'='*170}")
    print(f"BEST REGIME-ALIGNED PICKS (macro_peak ≥ 1.5 AND asymmetry ≥ 5 AND Saturn-safe)")
    print(f"{'='*170}")
    regime_aligned = [r for r in rows if r["macro_peak"] >= 1.5 and r["asym"] >= 5 and r["safe"]][:30]
    for i, r in enumerate(regime_aligned, 1):
        nm = (r["name"] or "")[:30]
        print(f"{i:3d} {r['tk']:<6s} {r['modern']:<14s} {r['gics'][:21]:<22s} "
              f"{r['now']:5.1f}→{r['peak']:5.1f} Δ{r['imp']:+5.1f} "
              f"Bub{r['bub_peak']:4.2f} Pk{r['peak_mo']}({r['runway']}mo) "
              f"mPk{r['macro_peak']:.2f}  Asym{r['asym']:5.2f}  {nm}")

if __name__ == "__main__":
    main()
