"""
v17 — 52-week LOW / BOTTOM CATCHER.

Retrospective on 32 real 2022-2025 runup lows showed three signals
are present nearly universally, while Jupiter-activation and tight
natal JN are NOT necessary conditions.

This module uses ONLY signals 1/2/3:
  (1) ECLIPSE PRE-SEEDING — recent eclipse within 2.5° of natal
      Sun/Moon/ASC/MC/Jupiter/Neptune (100% of historical runups)
  (2) CHART AGE ≤ 5 years (Qullamaggie-fresh; median 1yr at lows)
  (3) NEPTUNE CONTACT — transit Neptune within 2.5° of natal
      Sun/Moon/ASC/MC (53% of historical runups)

Explicitly DOES NOT require:
  (4) Jupiter approaching natal (only 12% at low; happens AFTER)
  (5) Tight natal JN < 6° (only 28% — Gidel-archetype is minority)

Target: catch bottoms BEFORE the rally, not flag charts already inflating.
"""
import math, csv, time, sys, statistics as st
from collections import defaultdict
import swisseph as swe
import openpyxl
from bti_test import compute_natal, transits_at, jd_of
from bti_v4 import yx, gamma_survive, gamma_era
from classical_archetype import classical_classify, is_day_chart
from eclipse_database import build_eclipse_database, eclipse_hits_natal

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

ECLIPSE_TYPE_WEIGHT = {
    "total_solar": 1.5, "annular_solar": 1.3, "hybrid_solar": 1.4,
    "partial_solar": 1.0, "solar": 1.0,
    "total_lunar": 1.1, "partial_lunar": 0.8, "penumbral_lunar": 0.5, "lunar": 0.7,
}
NATAL_TARGET_WEIGHT = {
    "Sun": 1.5, "Moon": 1.3, "ASC": 1.4, "MC": 1.3,
    "Jupiter": 1.1, "Neptune": 1.0,
    "Mercury": 0.8, "Venus": 0.9, "Mars": 0.8,
    "Saturn": 0.7, "Uranus": 0.7, "Pluto": 0.7,
}

def score_v17_bottom_catch(natal, eval_y, eval_m, ipo_date, eclipse_db):
    """Bottom-catcher using only signals 1/2/3 from retrospective."""
    ipo_y = int(ipo_date[:4])
    age = eval_y - ipo_y

    # === SIGNAL 1: Eclipse pre-seeding ===
    # Primary: eclipses within last 24 months + next 3 months
    # Weight by type, target importance, orb tightness, recency
    jd_center = jd_of(eval_y, eval_m, 15, 12.0)
    hits = eclipse_hits_natal(eclipse_db, natal, jd_center,
                              months_back=24, months_fwd=3, max_orb=2.5)
    p1_score = 0.0
    p1_detail = []
    tight_hits = 0       # < 1° orb
    very_tight = 0       # < 0.5° orb
    top_eclipses = []
    for h in hits:
        type_w = ECLIPSE_TYPE_WEIGHT.get(h["eclipse_type"], 0.7)
        target_w = NATAL_TARGET_WEIGHT.get(h["natal_body"], 0.7)
        orb_w = (2.5 - h["orb"]) / 2.5
        # Recency: peak at T-12 (typical pre-seed window, Silas)
        days = h["days_offset"]
        if -540 <= days <= 60:
            recency = 1.0
        elif -720 <= days <= -540:
            recency = 0.6
        else:
            recency = 0.3
        # Tight-orb bonus
        tight_bonus = 1.6 if h["orb"] <= 1.0 else (1.2 if h["orb"] <= 2.0 else 1.0)
        pts = type_w * target_w * orb_w * recency * tight_bonus
        p1_score += pts
        if h["orb"] <= 1.0: tight_hits += 1
        if h["orb"] <= 0.5: very_tight += 1
        if pts > 0.5:
            top_eclipses.append((pts, h))
    # Sort detail by importance
    top_eclipses.sort(key=lambda x:-x[0])
    for pts, h in top_eclipses[:3]:
        p1_detail.append(f"{h['eclipse_date']}/{h['eclipse_type'][:6]}→{h['natal_body']}:{h['orb']:.1f}°")

    # === SIGNAL 2: Young chart bonus ===
    # Qullamaggie: median age 1yr at pre-runup low; mean 4.2yr
    if age == 0: p2_score = 1.0  # just IPO'd, no base
    elif age <= 2: p2_score = 3.0
    elif age <= 5: p2_score = 2.5
    elif age <= 8: p2_score = 1.8
    elif age <= 15: p2_score = 1.0
    elif age <= 30: p2_score = 0.5
    else: p2_score = 0.2

    # === SIGNAL 3: Transit Neptune to natal Sun/Moon/ASC/MC ===
    trans = transits_at(eval_y, eval_m)
    nep_lon = trans["Neptune"]["lon"]
    p3_score = 0.0
    p3_detail = []
    for target in ("Sun", "Moon", "ASC", "MC"):
        if target not in natal: continue
        r = closest_hard(nep_lon, natal[target]["lon"], 2.5)
        if r:
            asp, o = r
            w = 1.5 if target in ("Sun","ASC") else 1.2
            pts = w * (2.5 - o) / 2.5
            # Conjunction is sharpest
            if asp == 0: pts *= 1.3
            p3_score += pts
            p3_detail.append(f"trNep {asp}° nat{target} {o:.1f}°")

    # === LIGHT gates (not hard filters) ===
    Gs = gamma_survive(natal)
    Ge = gamma_era(natal, eval_y)

    # === COMPOSITE ===
    # Weight: eclipse is primary (100% of corpus), age is secondary,
    # Neptune is tertiary. Each can independently contribute.
    total = (p1_score * 1.4 + p2_score * 1.0 + p3_score * 1.0) * (Gs ** 0.3) * (Ge ** 0.2)

    # Classification
    if total >= 8: tag = "STRONG_BOTTOM_CATCH"
    elif total >= 5: tag = "BOTTOM_CATCH"
    elif total >= 3: tag = "POSSIBLE_BOTTOM"
    else: tag = "NEUTRAL"

    return {
        "bottom_score": total, "tag": tag,
        "age": age,
        "p1_eclipse": p1_score, "p1_tight_hits": tight_hits, "p1_very_tight": very_tight,
        "p1_detail": p1_detail, "n_eclipses_hit": len(hits),
        "p2_age": p2_score,
        "p3_neptune": p3_score, "p3_detail": p3_detail,
        "Gs": Gs, "Ge": Ge,
    }

def main():
    print("Building eclipse DB...", file=sys.stderr)
    db = build_eclipse_database(1970, 2035)

    # Validate on 32-runup retrospective corpus first
    print("\nVALIDATING v17 on 32 known pre-runup lows", file=sys.stderr)
    from retrospective_prerunup import RECENT_RUNUPS
    val_scores = []
    print(f"\n{'='*150}")
    print(f"V17 BOTTOM-CATCHER validated on historical pre-runup lows")
    print(f"{'='*150}")
    print(f"{'Tkr':<7s} {'IPO':<11s} {'Low':<8s} {'Mult':>4s} {'Age':>3s} {'Total':>5s} {'Ecl':>4s} {'EclTight':>8s} {'Age_b':>5s} {'Nep':>4s} {'Tag':<20s}")
    for tk, ipo, ly, lm, mult, name in RECENT_RUNUPS:
        try:
            natal = compute_natal(ipo)
            r = score_v17_bottom_catch(natal, ly, lm, ipo, db)
            val_scores.append(r["bottom_score"])
            print(f"{tk:<7s} {ipo:<11s} {ly}-{lm:02d}  {mult:>3d}× {r['age']:>3d} {r['bottom_score']:5.2f} {r['p1_eclipse']:4.1f} {r['p1_tight_hits']:>8d} {r['p2_age']:5.1f} {r['p3_neptune']:4.1f} {r['tag']:<20s}")
        except Exception as e:
            pass
    print(f"\n  Validation stats (n={len(val_scores)}):")
    print(f"    Mean={st.mean(val_scores):.2f}  Median={st.median(val_scores):.2f}")
    print(f"    %≥5 (BOTTOM_CATCH+): {100*sum(1 for s in val_scores if s>=5)/len(val_scores):.0f}%")
    print(f"    %≥3 (POSSIBLE_BOTTOM+): {100*sum(1 for s in val_scores if s>=3)/len(val_scores):.0f}%")

    # Quiet baseline from non-bottom months (±18mo from each real low)
    quiet_scores = []
    for tk, ipo, ly, lm, mult, name in RECENT_RUNUPS:
        try:
            natal = compute_natal(ipo)
            for off in (-18, -12, 12, 18):
                y, m = yx(ly, lm, off)
                if y > 2026: continue
                r = score_v17_bottom_catch(natal, y, m, ipo, db)
                quiet_scores.append(r["bottom_score"])
        except: pass
    print(f"  Quiet baseline (±18mo offsets): mean={st.mean(quiet_scores):.2f}  median={st.median(quiet_scores):.2f}  %≥5: {100*sum(1 for s in quiet_scores if s>=5)/len(quiet_scores):.0f}%")
    # AUC
    pairs = wins = 0
    for b in val_scores:
        for q in quiet_scores:
            pairs += 1
            if b > q: wins += 1
    print(f"  AUC pre-runup > quiet: {wins/pairs:.3f}")

    # SP500 scan
    print("\nSP500 scan @ 2026-04...", file=sys.stderr)
    sp500 = []
    with open("/home/user/cyclepapa/data/sp500_ipo_dates.csv") as f:
        sp500 = list(csv.DictReader(f))
    t0 = time.time()
    results = []
    for row in sp500:
        try:
            natal = compute_natal(row["ipo_date"])
            r = score_v17_bottom_catch(natal, 2026, 4, row["ipo_date"], db)
            r["source"] = row.get("source","")
            results.append((row["ticker"], row["name"], row["sector"], row["ipo_date"], r))
        except: pass
    print(f"  SP500 {len(results)} in {time.time()-t0:.0f}s", file=sys.stderr)
    results.sort(key=lambda x: -x[4]["bottom_score"])

    print(f"\n{'='*165}")
    print(f"SP500 BOTTOM-CATCH @ 2026-04 — top 50 (using signals 1/2/3 only)")
    print(f"{'='*165}")
    print(f"{'Rk':>3s} {'Tkr':<6s} {'Name':<28s} {'IPO':<11s} {'Age':>3s} {'Total':>5s} {'Ecl':>4s} {'tight':>5s} {'Age_b':>5s} {'Nep':>4s} {'Tag':<20s} {'Top eclipses'}")
    for i, (tk, nm, sec, ipo, r) in enumerate(results[:50], 1):
        src = "*" if r.get("source") == "sp500_added" else " "
        ecl_d = " | ".join(r["p1_detail"][:2])[:55]
        print(f"{i:3d} {tk:<6s} {nm[:28]:<28s} {ipo:<11s} {r['age']:>3d} {r['bottom_score']:5.2f} {r['p1_eclipse']:4.1f} {r['p1_tight_hits']:>5d} {r['p2_age']:5.1f} {r['p3_neptune']:4.1f} {r['tag']:<20s} {ecl_d}{src}")

    with open("/home/user/cyclepapa/data/sp500_bottom_catch_v17.csv","w",newline="") as f:
        w = csv.writer(f)
        w.writerow(["ticker","name","sector","ipo","source","age","bottom_score","tag",
                    "p1_eclipse","p1_tight_hits","p1_very_tight","n_eclipses_hit",
                    "p2_age","p3_neptune","Gs","Ge","p1_detail","p3_detail"])
        for (tk, nm, sec, ipo, r) in results:
            w.writerow([tk,nm,sec,ipo,r.get("source",""),r["age"],
                        f"{r['bottom_score']:.2f}",r["tag"],
                        f"{r['p1_eclipse']:.2f}",r["p1_tight_hits"],r["p1_very_tight"],
                        r["n_eclipses_hit"],f"{r['p2_age']:.2f}",f"{r['p3_neptune']:.2f}",
                        f"{r['Gs']:.2f}",f"{r['Ge']:.2f}",
                        " | ".join(r["p1_detail"]), " | ".join(r["p3_detail"])])
    print(f"\nExported: data/sp500_bottom_catch_v17.csv")

    # Ritter post-2015 (young charts essential for this)
    print("\nRitter post-2015 scan...", file=sys.stderr)
    wb = openpyxl.load_workbook("/home/user/cyclepapa/data/IPO-age.xlsx", data_only=True)
    ws = wb["1975-2025"]
    rrows = []
    for row in ws.iter_rows(min_row=2, values_only=True):
        od, nm, tk, cusip, adr, vc, dual, shares, internet, crsp, fnd, roll = row[:12]
        if not od: continue
        try:
            d = int(od); y = d//10000
            if y < 2015: continue
            iso = f"{y:04d}-{(d//100)%100:02d}-{d%100:02d}"
        except: continue
        if not tk or str(tk).strip() in ("",".") or adr==2 or roll==1: continue
        rrows.append((str(tk).strip().upper(), nm or "", iso))
    print(f"  Ritter 2015+: {len(rrows)}", file=sys.stderr)
    t0 = time.time()
    rres = []
    for tk, nm, ipo in rrows:
        try:
            natal = compute_natal(ipo)
            r = score_v17_bottom_catch(natal, 2026, 4, ipo, db)
            rres.append((tk, nm, ipo, r))
        except: pass
    print(f"  Scanned {len(rres)} in {time.time()-t0:.0f}s", file=sys.stderr)
    rres.sort(key=lambda x: -x[3]["bottom_score"])

    print(f"\n{'='*165}")
    print(f"RITTER 2015+ BOTTOM-CATCH — top 40")
    print(f"{'='*165}")
    print(f"{'Rk':>3s} {'Tkr':<7s} {'Name':<36s} {'IPO':<11s} {'Age':>3s} {'Total':>5s} {'Ecl':>4s} {'tight':>5s} {'Age_b':>5s} {'Nep':>4s} {'Tag':<20s} {'Eclipses'}")
    for i, (tk, nm, ipo, r) in enumerate(rres[:40], 1):
        ecl_d = " | ".join(r["p1_detail"][:2])[:55]
        print(f"{i:3d} {tk:<7s} {nm[:36]:<36s} {ipo:<11s} {r['age']:>3d} {r['bottom_score']:5.2f} {r['p1_eclipse']:4.1f} {r['p1_tight_hits']:>5d} {r['p2_age']:5.1f} {r['p3_neptune']:4.1f} {r['tag']:<20s} {ecl_d}")

    with open("/home/user/cyclepapa/data/ritter_bottom_catch_v17.csv","w",newline="") as f:
        w = csv.writer(f)
        w.writerow(["ticker","name","ipo","age","bottom_score","tag",
                    "p1_eclipse","p1_tight_hits","p1_very_tight","n_eclipses_hit",
                    "p2_age","p3_neptune","Gs","Ge","p1_detail","p3_detail"])
        for tk, nm, ipo, r in rres:
            w.writerow([tk,nm,ipo,r["age"],f"{r['bottom_score']:.2f}",r["tag"],
                        f"{r['p1_eclipse']:.2f}",r["p1_tight_hits"],r["p1_very_tight"],
                        r["n_eclipses_hit"],f"{r['p2_age']:.2f}",f"{r['p3_neptune']:.2f}",
                        f"{r['Gs']:.2f}",f"{r['Ge']:.2f}",
                        " | ".join(r["p1_detail"]), " | ".join(r["p3_detail"])])
    print(f"\nExported: data/ritter_bottom_catch_v17.csv")

    # Ritter YOUNG ONLY (age 1-5) — the Qullamaggie class
    print(f"\n{'='*165}")
    print(f"RITTER YOUNG ONLY (age 1-5yr) BOTTOM-CATCH — pure Qullamaggie class")
    print(f"{'='*165}")
    young = [x for x in rres if 1 <= x[3]["age"] <= 5]
    young.sort(key=lambda x: -x[3]["bottom_score"])
    for i, (tk, nm, ipo, r) in enumerate(young[:40], 1):
        ecl_d = " | ".join(r["p1_detail"][:2])[:55]
        print(f"{i:3d} {tk:<7s} {nm[:36]:<36s} {ipo:<11s} {r['age']:>3d} {r['bottom_score']:5.2f} {r['p1_eclipse']:4.1f} {r['p1_tight_hits']:>5d} {r['tag']:<20s} {ecl_d}")

if __name__ == "__main__":
    main()
