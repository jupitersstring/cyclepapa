"""
v19 — EMPIRICALLY-CALIBRATED bullish scanner.

Replaces all theoretical weights with empirically-derived orb-bucket
weights from 152-case corpus systematic testing.

Single-planet orb weights (from Part 1 analysis, target: %≥25× / baseline):
  Pluto 8-12°:     47% / 26% = 1.8x  (STRONGEST)
  Uranus 3-5°:     44% / 26% = 1.7x
  Neptune 0-3°:    29% / 26% = 1.1x
  Saturn 3-5°:     22% / 26% = 0.85  (moderate)
  Jupiter 8-12°:   33% / 26% = 1.3x

Compound 2-planet rules (empirically validated, n>=10):
  Saturn-close + Uranus-mod:    55% ≥25× (2.1x)   weight 3.0
  Jupiter-far + Uranus-mod:     47% ≥25× (1.8x)   weight 2.2
  Saturn-close + Pluto-mod:     42% ≥25× (1.6x)   weight 1.8
  Saturn-mod + Neptune-close:   45% ≥25× + 27% ≥100× (mega!) weight 2.5
  Jupiter-far + Pluto-close:    46% ≥25× (1.8x)   weight 2.0
  Uranus-mod + Pluto-mod:       35% ≥25× (1.3x)   weight 1.5
  Neptune-close + Pluto-mod:    44% ≥25× (1.7x)   weight 2.0
  Jupiter-mod + Neptune-close:  36% ≥25× (1.4x)   weight 1.5

Plus: eclipse pre-seeding (100% universal), young chart, Gs/Ge.
"""
import math, csv, sys, time, statistics as st
from collections import defaultdict
from bti_test import compute_natal, transits_at, jd_of
from bti_v4 import yx, gamma_survive, gamma_era
from eclipse_database import build_eclipse_database, eclipse_hits_natal

def orb(a, b):
    d = abs((a - b) % 360)
    return min(d, 360 - d)

def closest_hard(a, b):
    best = 99
    for asp in (0, 90, 180):
        for sign in (+1, -1):
            o = orb(a, b + sign*asp)
            if o < best: best = o
    return best

# Empirical orb-bucket weights per planet (%≥25× / 26% baseline)
SINGLE_PLANET_WEIGHTS = {
    "Jupiter": [(0, 3, 1.08), (3, 5, 0.88), (5, 8, 1.04), (8, 12, 1.27), (12, 20, 1.00), (20, 99, 0.65)],
    "Saturn":  [(0, 3, 1.12), (3, 5, 0.85), (5, 8, 1.31), (8, 12, 1.15), (12, 20, 0.50), (20, 99, 1.27)],
    "Uranus":  [(0, 3, 0.58), (3, 5, 1.69), (5, 8, 1.23), (8, 12, 0.73), (12, 20, 1.35), (20, 99, 0.96)],
    "Neptune": [(0, 3, 1.12), (3, 5, 0.58), (5, 8, 1.27), (8, 12, 0.88), (12, 20, 1.12), (20, 99, 1.19)],
    "Pluto":   [(0, 3, 1.31), (3, 5, 1.12), (5, 8, 0.81), (8, 12, 1.81), (12, 20, 0.54), (20, 99, 0.00)],
}

def bucket_weight(planet, orb):
    for lo, hi, w in SINGLE_PLANET_WEIGHTS[planet]:
        if lo <= orb < hi:
            return w
    return 1.0

COMPOUND_RULES = [
    # (rule_label, condition_fn, weight)
    ("Sat_close_Ura_mod",  lambda o: o["Saturn"] <= 3 and 3 <= o["Uranus"] < 8, 3.0),
    ("Jup_far_Ura_mod",    lambda o: o["Jupiter"] >= 8 and 3 <= o["Uranus"] < 8, 2.2),
    ("Sat_close_Plu_mod",  lambda o: o["Saturn"] <= 3 and 3 <= o["Pluto"] < 8, 1.8),
    ("Sat_mod_Nep_close",  lambda o: 3 <= o["Saturn"] < 8 and o["Neptune"] <= 3, 2.5),
    ("Jup_far_Plu_close",  lambda o: o["Jupiter"] >= 8 and o["Pluto"] <= 3, 2.0),
    ("Ura_mod_Plu_mod",    lambda o: 3 <= o["Uranus"] < 8 and 3 <= o["Pluto"] < 8, 1.5),
    ("Nep_close_Plu_mod",  lambda o: o["Neptune"] <= 3 and 3 <= o["Pluto"] < 8, 2.0),
    ("Jup_mod_Nep_close",  lambda o: 3 <= o["Jupiter"] < 8 and o["Neptune"] <= 3, 1.5),
    ("Pluto_8_12_sweet",   lambda o: 8 <= o["Pluto"] < 12, 2.5),  # standalone Pluto 8-12 empirical sweet spot
    ("Uranus_3_5_sweet",   lambda o: 3 <= o["Uranus"] < 5, 2.2),
]

def score_v19(natal, eval_y, eval_m, db):
    trans = transits_at(eval_y, eval_m)
    # Closest hard aspect of each outer to any natal sensitive (Sun/Moon/ASC/MC)
    targets = {}
    for p in ("Sun","Moon","ASC","MC"):
        if p in natal: targets[p] = natal[p]["lon"]
    outer_orbs = {}
    for outer in ("Jupiter","Saturn","Uranus","Neptune","Pluto"):
        best = 99
        for tlon in targets.values():
            o = closest_hard(trans[outer]["lon"], tlon)
            if o < best: best = o
        outer_orbs[outer] = best

    # Single-planet contribution
    single_score = 0
    for p, o in outer_orbs.items():
        single_score += bucket_weight(p, o)

    # Compound rules
    compound_score = 0
    active_rules = []
    for label, fn, w in COMPOUND_RULES:
        if fn(outer_orbs):
            compound_score += w
            active_rules.append(label)

    # Eclipse pre-seeding (universal empirical — 100% of pre-runup lows)
    jd_c = jd_of(eval_y, eval_m, 15, 12.0)
    hits = eclipse_hits_natal(db, natal, jd_c, months_back=18, months_fwd=3, max_orb=3)
    eclipse_score = 0
    for h in hits:
        type_w = 1.5 if "total" in h["eclipse_type"] else (1.2 if "annular" in h["eclipse_type"] else 0.9 if "partial" in h["eclipse_type"] else 0.5)
        target_w = 1.5 if h["natal_body"] in ("Sun","MC","ASC") else 1.0
        orb_w = (3 - h["orb"]) / 3
        eclipse_score += type_w * target_w * orb_w

    # Chart age bonus (young = Qullamaggie)
    ipo_y = int(natal["_date"][:4])
    age = eval_y - ipo_y
    if 1 <= age <= 5:
        age_bonus = 1.5
    elif 6 <= age <= 15:
        age_bonus = 1.0
    elif 16 <= age <= 30:
        age_bonus = 0.7
    else:
        age_bonus = 0.5

    # Gates
    Gs = gamma_survive(natal)
    Ge = gamma_era(natal, eval_y)

    # Composite
    raw = (single_score * 1.0 + compound_score * 1.5 + eclipse_score * 1.3 + age_bonus * 0.8)
    composite = raw * (Gs ** 0.4) * (Ge ** 0.25)

    return {
        "composite": composite,
        "single_score": single_score, "compound_score": compound_score,
        "eclipse_score": eclipse_score, "active_rules": active_rules,
        "outer_orbs": outer_orbs, "age": age, "age_bonus": age_bonus,
        "Gs": Gs, "Ge": Ge, "n_active_rules": len(active_rules),
    }

def main():
    print("Building eclipse DB...", file=sys.stderr)
    db = build_eclipse_database(1970, 2035)
    print(f"  {len(db)} eclipses", file=sys.stderr)

    # Validation on 152-corpus
    from parabolic_corpus import PARABOLIC_BOTTOMS
    val_scores = []
    for tk, ipo, bot, top, mult, speed, note in PARABOLIC_BOTTOMS:
        try:
            natal = compute_natal(ipo)
            r = score_v19(natal, bot[0], bot[1], db)
            val_scores.append((r["composite"], mult))
        except: pass
    print(f"\nValidation n={len(val_scores)}")
    # Correlation
    if val_scores:
        xs = [x for x, y in val_scores]
        ys = [math.log(y) for x, y in val_scores]
        mx = st.mean(xs); my = st.mean(ys)
        num = sum((x-mx)*(y-my) for x,y in zip(xs,ys))
        dx = math.sqrt(sum((x-mx)**2 for x in xs))
        dy = math.sqrt(sum((y-my)**2 for y in ys))
        r = num/(dx*dy) if dx*dy else 0
        print(f"  Pearson r(composite, log_mult) = {r:+.3f}")
    # Quartile test
    val_scores.sort(key=lambda p: p[0])
    n = len(val_scores)
    for q_name, ql, qh in [("Q1", 0, n//4), ("Q2", n//4, n//2), ("Q3", n//2, 3*n//4), ("Q4", 3*n//4, n)]:
        mults = [m for _, m in val_scores[ql:qh]]
        print(f"  {q_name}: n={len(mults)}  median={st.median(mults):.1f}×  mean={st.mean(mults):.1f}×  %≥25×={100*sum(1 for m in mults if m>=25)/len(mults):.0f}%  %≥100×={100*sum(1 for m in mults if m>=100)/len(mults):.0f}%")

    # SP500 scan
    print(f"\nScanning SP500 @ 2026-04...", file=sys.stderr)
    sp500 = []
    with open("/home/user/cyclepapa/data/sp500_ipo_dates.csv") as f:
        sp500 = list(csv.DictReader(f))
    t0 = time.time()
    results = []
    for row in sp500:
        try:
            natal = compute_natal(row["ipo_date"])
            r = score_v19(natal, 2026, 4, db)
            r["ticker"] = row["ticker"]; r["name"] = row["name"]
            r["ipo"] = row["ipo_date"]; r["source"] = row.get("source","")
            r["sector"] = row.get("sector","")
            results.append(r)
        except: pass
    print(f"  {len(results)} in {time.time()-t0:.0f}s", file=sys.stderr)
    results.sort(key=lambda r: -r["composite"])

    print(f"\n{'='*175}")
    print(f"SP500 TOP 40 v19 (empirically calibrated)")
    print(f"{'='*175}")
    print(f"{'Rk':>3s} {'Tkr':<6s} {'Name':<28s} {'IPO':<11s} {'Age':>3s} {'Comp':>6s} {'Single':>6s} {'Comp_':>6s} {'Ecl':>4s} {'Orbs(J/S/U/N/P)':<30s} {'Rules'}")
    for i, r in enumerate(results[:40], 1):
        src = "*" if r["source"] == "sp500_added" else " "
        orbs = f"{r['outer_orbs']['Jupiter']:3.0f}/{r['outer_orbs']['Saturn']:3.0f}/{r['outer_orbs']['Uranus']:3.0f}/{r['outer_orbs']['Neptune']:3.0f}/{r['outer_orbs']['Pluto']:3.0f}"
        rules = ",".join(r["active_rules"][:3])[:50]
        print(f"{i:3d} {r['ticker']:<6s} {r['name'][:28]:<28s} {r['ipo']:<11s} {r['age']:>3d} {r['composite']:6.2f} {r['single_score']:6.2f} {r['compound_score']:6.2f} {r['eclipse_score']:4.1f} {orbs:<30s} {rules}{src}")

    # Export SP500
    with open("/home/user/cyclepapa/data/sp500_bti_v19.csv","w",newline="") as f:
        w = csv.writer(f)
        w.writerow(["rank","ticker","name","sector","ipo","source","age","composite",
                    "single_score","compound_score","eclipse_score","n_rules","active_rules",
                    "jup_orb","sat_orb","ura_orb","nep_orb","plu_orb","Gs","Ge"])
        for i, r in enumerate(results, 1):
            w.writerow([i,r["ticker"],r["name"],r["sector"],r["ipo"],r["source"],r["age"],
                        f"{r['composite']:.2f}",f"{r['single_score']:.2f}",f"{r['compound_score']:.2f}",
                        f"{r['eclipse_score']:.2f}",r["n_active_rules"]," | ".join(r["active_rules"]),
                        f"{r['outer_orbs']['Jupiter']:.1f}",f"{r['outer_orbs']['Saturn']:.1f}",
                        f"{r['outer_orbs']['Uranus']:.1f}",f"{r['outer_orbs']['Neptune']:.1f}",
                        f"{r['outer_orbs']['Pluto']:.1f}",f"{r['Gs']:.2f}",f"{r['Ge']:.2f}"])
    print(f"\nExported: data/sp500_bti_v19.csv")

    # Full Ritter 1975-2025
    print(f"\nScanning FULL Ritter 1975-2025...", file=sys.stderr)
    import openpyxl
    wb = openpyxl.load_workbook("/home/user/cyclepapa/data/IPO-age.xlsx", data_only=True)
    ws = wb["1975-2025"]
    rrows = []
    for row in ws.iter_rows(min_row=2, values_only=True):
        od, nm, tk, cusip, adr, vc, dual, shares, internet, crsp, fnd, roll = row[:12]
        if not od: continue
        try:
            d = int(od); y = d//10000
            iso = f"{y:04d}-{(d//100)%100:02d}-{d%100:02d}"
        except: continue
        if not tk or str(tk).strip() in ("",".") or adr==2 or roll==1: continue
        rrows.append((str(tk).strip().upper(), nm or "", iso))
    print(f"  Universe: {len(rrows)}", file=sys.stderr)
    t0 = time.time()
    rres = []
    for i, (tk, nm, ipo) in enumerate(rrows):
        try:
            natal = compute_natal(ipo)
            r = score_v19(natal, 2026, 4, db)
            r["ticker"] = tk; r["name"] = nm; r["ipo"] = ipo
            rres.append(r)
        except: pass
        if (i+1) % 3000 == 0:
            print(f"  {i+1}/{len(rrows)} in {time.time()-t0:.0f}s", file=sys.stderr)
    print(f"  Done {len(rres)} in {time.time()-t0:.0f}s", file=sys.stderr)
    rres.sort(key=lambda r: -r["composite"])

    with open("/home/user/cyclepapa/data/ritter_bti_v19.csv","w",newline="") as f:
        w = csv.writer(f)
        w.writerow(["rank","ticker","name","ipo","age","composite","single_score",
                    "compound_score","eclipse_score","n_rules","active_rules",
                    "jup_orb","sat_orb","ura_orb","nep_orb","plu_orb"])
        for i, r in enumerate(rres, 1):
            w.writerow([i,r["ticker"],r["name"],r["ipo"],r["age"],
                        f"{r['composite']:.2f}",f"{r['single_score']:.2f}",
                        f"{r['compound_score']:.2f}",f"{r['eclipse_score']:.2f}",
                        r["n_active_rules"]," | ".join(r["active_rules"]),
                        f"{r['outer_orbs']['Jupiter']:.1f}",f"{r['outer_orbs']['Saturn']:.1f}",
                        f"{r['outer_orbs']['Uranus']:.1f}",f"{r['outer_orbs']['Neptune']:.1f}",
                        f"{r['outer_orbs']['Pluto']:.1f}"])

    print(f"\n{'='*175}")
    print(f"TOP 60 — FULL UNIVERSE (SP500 + Ritter 1975-2025) by v19 composite")
    print(f"{'='*175}")
    # Combine
    all_results = []
    for r in results:
        all_results.append(("SP500", r))
    for r in rres:
        all_results.append(("Ritter", r))
    all_results.sort(key=lambda x: -x[1]["composite"])
    # Dedupe by ticker (keep SP500 first if duplicate)
    seen = set()
    unique = []
    for src, r in all_results:
        key = r["ticker"]
        if key in seen: continue
        seen.add(key)
        unique.append((src, r))
    print(f"{'Rk':>3s} {'Src':<6s} {'Tkr':<7s} {'Name':<34s} {'IPO':<11s} {'Age':>3s} {'Comp':>6s} {'Rules':>5s} {'Orbs(JSUNP)':<18s} {'ActiveRules'}")
    for i, (src, r) in enumerate(unique[:60], 1):
        orbs = f"{r['outer_orbs']['Jupiter']:3.0f}/{r['outer_orbs']['Saturn']:3.0f}/{r['outer_orbs']['Uranus']:3.0f}/{r['outer_orbs']['Neptune']:3.0f}/{r['outer_orbs']['Pluto']:3.0f}"
        rules = ",".join(r["active_rules"][:3])[:45]
        print(f"{i:3d} {src:<6s} {r['ticker']:<7s} {r['name'][:34]:<34s} {r['ipo']:<11s} {r['age']:>3d} {r['composite']:6.2f} {r['n_active_rules']:>5d} {orbs:<18s} {rules}")
    print(f"\nExported: data/sp500_bti_v19.csv and data/ritter_bti_v19.csv")

if __name__ == "__main__":
    main()
