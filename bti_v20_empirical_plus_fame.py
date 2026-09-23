"""
v20 — v19 empirical orb weights + fame/notoriety integration.

Builds on v19's empirical orb-bucket weights with:
  - Lot of Exaltation (Hellenistic/Valens): day: ASC+19°Ari-Sun; night: ASC+3°Tau-Moon
  - Lot of Known-by-Men-and-Revered (Al-Biruni): ASC+Sun-Fortune
  - Lot of Celebrated Persons of Rank (Al-Biruni): ASC+Sun-Saturn
  - Natal Royal Star contacts (Regulus/Spica/Antares/Aldebaran)
  - Transit Jupiter on natal Sun/MC (fame rise)
  - Transit Uranus conj Sun/MC (sudden electrical rise)
  - Transit NN on natal Sun/MC (crowd attention)
  - Transit Saturn on natal Sun/MC PENALTY (fall signal)

Universe: SP500 + full Ritter 1975-2025 (~15k IPOs).
"""
import math, csv, sys, time, statistics as st
from collections import defaultdict
from bti_test import compute_natal, transits_at, jd_of
from bti_v4 import yx, gamma_survive, gamma_era
from eclipse_database import build_eclipse_database, eclipse_hits_natal
from bti_v19_empirical import SINGLE_PLANET_WEIGHTS, COMPOUND_RULES, bucket_weight, closest_hard, orb

ROYAL_STARS = {"Regulus":0.30, "Spica":204.28, "Antares":250.00, "Aldebaran":70.15}

def lot_of_fortune(natal):
    # Day: ASC + Moon - Sun; Night: reversed
    # Simplified: use day formula (most IPO charts are day charts at 9:30 ET)
    return (natal["ASC"]["lon"] + natal["Moon"]["lon"] - natal["Sun"]["lon"]) % 360

def lot_of_exaltation(natal):
    # Day: ASC + 19° Aries - Sun   (19° Aries = 19)
    return (natal["ASC"]["lon"] + 19 - natal["Sun"]["lon"]) % 360

def lot_of_known_revered(natal):
    # Al-Biruni: ASC + Sun - Fortune
    lof = lot_of_fortune(natal)
    return (natal["ASC"]["lon"] + natal["Sun"]["lon"] - lof) % 360

def lot_of_celebrated_rank(natal):
    # Al-Biruni: ASC + Sun - Saturn
    return (natal["ASC"]["lon"] + natal["Sun"]["lon"] - natal["Saturn"]["lon"]) % 360

def royal_star_natal_score(natal):
    """Natal planets conjunct Royal Stars within 2° — inherent fame DNA."""
    score = 0
    hits = []
    for p in ("Sun","Moon","Mercury","Venus","Mars","Jupiter","ASC","MC"):
        if p not in natal: continue
        for star, slon in ROYAL_STARS.items():
            o = orb(natal[p]["lon"], slon)
            if o <= 2:
                w = 2.0 if p in ("Sun","MC","ASC") else 1.0
                pts = w * (2-o)/2
                score += pts
                hits.append(f"{p}-{star}_{o:.1f}")
    return score, hits

def fame_triggers(natal, trans):
    """Current transit triggers for fame RISE (positive)."""
    score = 0
    reasons = []
    # Transit Jupiter on natal Sun/MC/ASC
    for tgt in ("Sun","MC","ASC"):
        if tgt not in natal: continue
        o_ju = closest_hard(trans["Jupiter"]["lon"], natal[tgt]["lon"])
        if o_ju <= 3:
            pts = 1.8 * (3-o_ju)/3
            if tgt == "Sun": pts *= 1.2
            score += pts
            reasons.append(f"trJup-nat{tgt}_{o_ju:.1f}°")
    # Transit Uranus conj natal Sun/MC
    for tgt in ("Sun","MC"):
        if tgt not in natal: continue
        o_ur = closest_hard(trans["Uranus"]["lon"], natal[tgt]["lon"])
        if o_ur <= 3:
            pts = 2.0 * (3-o_ur)/3
            score += pts
            reasons.append(f"trUra-nat{tgt}_{o_ur:.1f}°")
    # Transit NN conj natal Sun/MC
    for tgt in ("Sun","MC"):
        if tgt not in natal: continue
        o_nn = orb(trans["NN"]["lon"], natal[tgt]["lon"])
        if o_nn <= 3:
            pts = 1.5 * (3-o_nn)/3
            score += pts
            reasons.append(f"trNN-nat{tgt}_{o_nn:.1f}°")
    # Transit Jupiter on Royal Star
    for star, slon in ROYAL_STARS.items():
        o = orb(trans["Jupiter"]["lon"], slon)
        if o <= 2:
            score += 1.0 * (2-o)/2
            reasons.append(f"trJup-{star}_{o:.1f}°")
    # Transit on lot of Exaltation
    loe = lot_of_exaltation(natal)
    for tr_planet in ("Jupiter","Uranus","NN"):
        if tr_planet == "NN":
            tr_lon = trans["NN"]["lon"]
        else:
            tr_lon = trans[tr_planet]["lon"]
        o = orb(tr_lon, loe)
        if o <= 3:
            pts = 1.2 * (3-o)/3
            score += pts
            reasons.append(f"tr{tr_planet[:3]}-LoEx_{o:.1f}°")
    # Transit on lot of Known-and-Revered
    lokm = lot_of_known_revered(natal)
    for tr_planet in ("Jupiter","NN"):
        if tr_planet == "NN":
            tr_lon = trans["NN"]["lon"]
        else:
            tr_lon = trans[tr_planet]["lon"]
        o = orb(tr_lon, lokm)
        if o <= 3:
            pts = 1.2 * (3-o)/3
            score += pts
            reasons.append(f"tr{tr_planet[:3]}-LoKnown_{o:.1f}°")
    return score, reasons

def fall_penalty(natal, trans):
    """Transits indicating fame FALL — subtract from score."""
    penalty = 0
    reasons = []
    # Transit Saturn conj/opp natal Sun/MC
    for tgt in ("Sun","MC"):
        if tgt not in natal: continue
        o = closest_hard(trans["Saturn"]["lon"], natal[tgt]["lon"])
        if o <= 3:
            pts = 1.5 * (3-o)/3
            if tgt == "Sun": pts *= 1.2
            penalty += pts
            reasons.append(f"trSat-nat{tgt}_{o:.1f}°")
    # Transit SN on natal Sun/MC
    sn = (trans["NN"]["lon"] + 180) % 360
    for tgt in ("Sun","MC"):
        if tgt not in natal: continue
        o = orb(sn, natal[tgt]["lon"])
        if o <= 3:
            penalty += 0.8 * (3-o)/3
            reasons.append(f"trSN-nat{tgt}_{o:.1f}°")
    return penalty, reasons

def score_v20(natal, eval_y, eval_m, db):
    """v19 empirical orbs + fame/notoriety layer."""
    trans = transits_at(eval_y, eval_m)
    # v19 orb signals
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
    single_score = sum(bucket_weight(p, o) for p, o in outer_orbs.items())
    compound_score = 0
    active_rules = []
    for label, fn, w in COMPOUND_RULES:
        if fn(outer_orbs):
            compound_score += w
            active_rules.append(label)
    # Eclipse
    jd_c = jd_of(eval_y, eval_m, 15, 12.0)
    hits = eclipse_hits_natal(db, natal, jd_c, months_back=18, months_fwd=3, max_orb=3)
    eclipse_score = 0
    for h in hits:
        type_w = 1.5 if "total" in h["eclipse_type"] else (1.2 if "annular" in h["eclipse_type"] else 0.9 if "partial" in h["eclipse_type"] else 0.5)
        target_w = 1.5 if h["natal_body"] in ("Sun","MC","ASC") else 1.0
        orb_w = (3 - h["orb"]) / 3
        eclipse_score += type_w * target_w * orb_w
    # Fame layer
    natal_fame, fame_hits = royal_star_natal_score(natal)
    rise_score, rise_r = fame_triggers(natal, trans)
    fall_pen, fall_r = fall_penalty(natal, trans)
    fame_score = natal_fame * 0.5 + rise_score * 1.2 - fall_pen * 1.0
    # Age bonus
    ipo_y = int(natal["_date"][:4])
    age = eval_y - ipo_y
    if 1 <= age <= 5: age_bonus = 1.5
    elif 6 <= age <= 15: age_bonus = 1.0
    elif 16 <= age <= 30: age_bonus = 0.7
    else: age_bonus = 0.5
    Gs = gamma_survive(natal); Ge = gamma_era(natal, eval_y)
    raw = (single_score * 1.0 + compound_score * 1.5 + eclipse_score * 1.3 +
           fame_score * 1.0 + age_bonus * 0.8)
    composite = raw * (Gs ** 0.4) * (Ge ** 0.25)
    return {
        "composite": composite, "single": single_score, "compound": compound_score,
        "eclipse": eclipse_score, "fame": fame_score, "natal_fame": natal_fame,
        "rise": rise_score, "fall": fall_pen,
        "active_rules": active_rules, "fame_hits": fame_hits,
        "rise_reasons": rise_r, "fall_reasons": fall_r,
        "outer_orbs": outer_orbs, "age": age, "age_bonus": age_bonus,
        "Gs": Gs, "Ge": Ge,
    }

def main():
    print("Building eclipse DB...", file=sys.stderr)
    db = build_eclipse_database(1970, 2035)

    # Validation on 152-corpus (quick)
    from parabolic_corpus import PARABOLIC_BOTTOMS
    vs = []
    for tk, ipo, bot, top, mult, speed, note in PARABOLIC_BOTTOMS:
        try:
            natal = compute_natal(ipo)
            r = score_v20(natal, bot[0], bot[1], db)
            vs.append((r["composite"], mult))
        except: pass
    xs = [x for x,_ in vs]; ys = [math.log(m) for _,m in vs]
    mx,my = st.mean(xs), st.mean(ys)
    num = sum((x-mx)*(y-my) for x,y in zip(xs,ys))
    dx = math.sqrt(sum((x-mx)**2 for x in xs)); dy = math.sqrt(sum((y-my)**2 for y in ys))
    r = num/(dx*dy) if dx*dy else 0
    print(f"v20 validation: n={len(vs)}  r(composite, log_mult)={r:+.3f}", file=sys.stderr)
    # Quartile
    vs.sort(key=lambda p: p[0])
    n = len(vs)
    for qn, lo, hi in [("Q1",0,n//4),("Q2",n//4,n//2),("Q3",n//2,3*n//4),("Q4",3*n//4,n)]:
        ms = [m for _, m in vs[lo:hi]]
        print(f"  {qn}: median={st.median(ms):.1f}×  %≥25×={100*sum(1 for m in ms if m>=25)/len(ms):.0f}%", file=sys.stderr)

    # SP500
    print(f"\nScanning SP500 @ 2026-04...", file=sys.stderr)
    sp500 = []
    with open("/home/user/cyclepapa/data/sp500_ipo_dates.csv") as f:
        sp500 = list(csv.DictReader(f))
    t0 = time.time()
    sp_res = []
    for row in sp500:
        try:
            natal = compute_natal(row["ipo_date"])
            r = score_v20(natal, 2026, 4, db)
            r["ticker"] = row["ticker"]; r["name"] = row["name"]
            r["ipo"] = row["ipo_date"]; r["source"] = row.get("source","")
            r["sector"] = row.get("sector","")
            sp_res.append(r)
        except: pass
    print(f"  SP500 {len(sp_res)} in {time.time()-t0:.0f}s", file=sys.stderr)

    # Full Ritter
    print(f"Scanning Ritter 1975-2025...", file=sys.stderr)
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
    t0 = time.time()
    rit_res = []
    for i, (tk, nm, ipo) in enumerate(rrows):
        try:
            natal = compute_natal(ipo)
            r = score_v20(natal, 2026, 4, db)
            r["ticker"] = tk; r["name"] = nm; r["ipo"] = ipo; r["source"] = "ritter"
            r["sector"] = ""
            rit_res.append(r)
        except: pass
        if (i+1) % 4000 == 0:
            print(f"  {i+1}/{len(rrows)} in {time.time()-t0:.0f}s", file=sys.stderr)
    print(f"  Ritter {len(rit_res)} in {time.time()-t0:.0f}s", file=sys.stderr)

    # Combined universe
    all_u = []
    for r in sp_res: all_u.append(("SP500", r))
    for r in rit_res: all_u.append(("Ritter", r))
    all_u.sort(key=lambda x: -x[1]["composite"])
    seen = set()
    unique = []
    for src, r in all_u:
        if r["ticker"] in seen: continue
        seen.add(r["ticker"])
        unique.append((src, r))

    print(f"\n{'='*175}")
    print(f"UNIVERSE TOP 80 — Most bullish per v20 (empirical orbs + fame layer) @ 2026-04")
    print(f"{'='*175}")
    print(f"{'Rk':>3s} {'Src':<6s} {'Tkr':<7s} {'Name':<32s} {'IPO':<11s} {'Age':>3s} {'Comp':>6s} {'Fame':>5s} {'Rise':>5s} {'Fall':>5s} {'Ecl':>4s} {'Rules':>5s} {'Orbs(JSUNP)':<18s}")
    for i, (src, r) in enumerate(unique[:80], 1):
        orbs = f"{r['outer_orbs']['Jupiter']:3.0f}/{r['outer_orbs']['Saturn']:3.0f}/{r['outer_orbs']['Uranus']:3.0f}/{r['outer_orbs']['Neptune']:3.0f}/{r['outer_orbs']['Pluto']:3.0f}"
        print(f"{i:3d} {src:<6s} {r['ticker']:<7s} {r['name'][:32]:<32s} {r['ipo']:<11s} {r['age']:>3d} {r['composite']:6.2f} {r['fame']:5.2f} {r['rise']:5.2f} {r['fall']:5.2f} {r['eclipse']:4.1f} {len(r['active_rules']):>5d} {orbs:<18s}")

    # Export
    with open("/home/user/cyclepapa/data/universe_bti_v20.csv","w",newline="") as f:
        w = csv.writer(f)
        w.writerow(["rank","source","ticker","name","sector","ipo","age","composite",
                    "single","compound","eclipse","fame","natal_fame","rise","fall",
                    "n_rules","active_rules","fame_hits","rise_reasons","fall_reasons",
                    "jup","sat","ura","nep","plu","Gs","Ge"])
        for i, (src, r) in enumerate(unique, 1):
            w.writerow([i,src,r["ticker"],r["name"],r.get("sector",""),r["ipo"],r["age"],
                        f"{r['composite']:.2f}",f"{r['single']:.2f}",f"{r['compound']:.2f}",
                        f"{r['eclipse']:.2f}",f"{r['fame']:.2f}",f"{r['natal_fame']:.2f}",
                        f"{r['rise']:.2f}",f"{r['fall']:.2f}",len(r["active_rules"]),
                        " | ".join(r["active_rules"])," | ".join(r["fame_hits"]),
                        " | ".join(r["rise_reasons"])," | ".join(r["fall_reasons"]),
                        f"{r['outer_orbs']['Jupiter']:.1f}",f"{r['outer_orbs']['Saturn']:.1f}",
                        f"{r['outer_orbs']['Uranus']:.1f}",f"{r['outer_orbs']['Neptune']:.1f}",
                        f"{r['outer_orbs']['Pluto']:.1f}",f"{r['Gs']:.2f}",f"{r['Ge']:.2f}"])
    print(f"\nExported: data/universe_bti_v20.csv")

    # Most bullish FAME-driven names
    print(f"\n{'='*140}")
    print(f"FAME-DRIVEN TOP 30 (highest fame component regardless of overall rank)")
    print(f"{'='*140}")
    by_fame = sorted(all_u, key=lambda x: -x[1]["fame"])
    seen2 = set()
    for src, r in by_fame[:100]:
        if r["ticker"] in seen2: continue
        seen2.add(r["ticker"])
        if len(seen2) > 30: break
        rise_key = " | ".join(r["rise_reasons"][:2])[:40]
        fame_key = " | ".join(r["fame_hits"][:2])[:30]
        print(f"  {src:<6s} {r['ticker']:<7s} {r['name'][:30]:<30s} age={r['age']:>3d} fame={r['fame']:5.2f} rise={r['rise']:5.2f} [nat:{fame_key}] [rise:{rise_key}]")

if __name__ == "__main__":
    main()
