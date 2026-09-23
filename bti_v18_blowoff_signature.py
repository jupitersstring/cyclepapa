"""
v18 — EMPIRICAL PRE-BLOWOFF SIGNATURE per 152-case findings:

Counter-intuitive correlations with log(rally_magnitude):
  Jup-Nep transit orb:    +0.276  (Jupiter NOT on natal Neptune = bigger)
  Total outer contacts:   -0.219  (fewer contacts = bigger rally)
  Neptune closest orb:    +0.205  (moderate Neptune beats exact hit)
  Saturn closest orb:     +0.187  (Saturn FAR = bigger rally)
  Natal JN orb:           -0.137  (close natal JN = bigger — only natal)

KILLER RULE:  Saturn FAR (>=8° from natal sensitive) + Neptune CLOSE (<=3°)
              = 132.9× avg rally, 67% produce >=10×
              Only 12% of bottoms have this combo.

Interpretation: fantasy active, reality absent → maximum repricing.

This v18 scores the PRE-BLOWOFF signature using only the empirically
validated signals + three-tool framework:
  (1) Bottom signature — static match to historical pre-blowoff pattern
  (2) Forward pre-positioning — next fast trigger before Saturn arrives
  (3) Unreality score — Neptunian fantasy field active
"""
import math, csv, sys, time, statistics as st
from collections import defaultdict
import swisseph as swe
from bti_test import compute_natal, transits_at, jd_of
from bti_v4 import yx, gamma_survive, gamma_era
from classical_archetype import classical_classify
from classical_extensions import secondary_progressions, progressed_lunation_phase

SIGNS = ["Ari","Tau","Gem","Can","Leo","Vir","Lib","Sco","Sag","Cap","Aqu","Pis"]

def orb(a, b):
    d = abs((a - b) % 360)
    return min(d, 360 - d)

def closest_hard(a, b, max_orb=30):
    best = 99
    for asp in (0, 90, 180):
        for sign in (+1, -1):
            o = orb(a, b + sign * asp)
            if o < best: best = o
    return best

def natal_targets(natal):
    """Sensitive points that transits aim at."""
    return {k: natal[k]["lon"] for k in ("Sun","Moon","Venus","Mars","Jupiter","Saturn","ASC","MC") if k in natal}

def natal_JN_orb(natal):
    r = closest_hard(natal["Jupiter"]["lon"], natal["Neptune"]["lon"])
    # also soft
    for asp in (60, 120):
        for sign in (+1, -1):
            o = orb(natal["Jupiter"]["lon"], natal["Neptune"]["lon"] + sign*asp)
            if o < r: r = o
    return r

def score_blowoff_signature(natal, eval_y, eval_m):
    """Score the empirical pre-blowoff signature."""
    trans = transits_at(eval_y, eval_m)
    tgts = natal_targets(natal)

    # Saturn closest hard aspect to any natal target
    saturn_closest = min(closest_hard(trans["Saturn"]["lon"], lon) for lon in tgts.values())
    # Neptune closest hard aspect
    neptune_closest = min(closest_hard(trans["Neptune"]["lon"], lon) for lon in tgts.values())
    # Jupiter closest
    jupiter_closest = min(closest_hard(trans["Jupiter"]["lon"], lon) for lon in tgts.values())
    # Pluto closest
    pluto_closest = min(closest_hard(trans["Pluto"]["lon"], lon) for lon in tgts.values())
    # Uranus closest
    uranus_closest = min(closest_hard(trans["Uranus"]["lon"], lon) for lon in tgts.values())

    # Total outer contacts within 5° hard aspect
    total_contacts = 0
    for outer in ("Jupiter","Saturn","Uranus","Neptune","Pluto"):
        for lon in tgts.values():
            if closest_hard(trans[outer]["lon"], lon) <= 5:
                total_contacts += 1
                break  # one per transit planet

    # Transit Jupiter-Neptune orb (the +0.276 correlation signal)
    jn_transit_orb = closest_hard(trans["Jupiter"]["lon"], trans["Neptune"]["lon"])

    # Natal JN orb
    nat_jn = natal_JN_orb(natal)

    # ===== SCORING per empirical findings =====
    score = 0
    reasons = []

    # KILLER RULE: Saturn FAR + Neptune CLOSE (132.9× avg, 67% ≥10×)
    if saturn_closest >= 8 and 1 <= neptune_closest <= 3:
        score += 5.0
        reasons.append(f"★KILLER: Sat FAR ({saturn_closest:.1f}°) + Nep CLOSE ({neptune_closest:.1f}°)")
    elif saturn_closest >= 6 and neptune_closest <= 4:
        score += 2.5
        reasons.append(f"MILD killer: Sat {saturn_closest:.1f}° + Nep {neptune_closest:.1f}°")

    # Saturn far alone: +0.187
    if saturn_closest >= 10:
        score += 1.0
    elif saturn_closest >= 6:
        score += 0.5
    elif saturn_closest <= 3:
        score -= 1.0
        reasons.append(f"Saturn too close ({saturn_closest:.1f}°)")

    # Neptune in sweet spot 1-3° (NOT exact, NOT absent)
    if 1 <= neptune_closest <= 3:
        score += 1.5
        reasons.append(f"Neptune sweet-spot ({neptune_closest:.1f}°)")
    elif neptune_closest <= 1:
        score += 0.3  # exact hit is less — penalty vs sweet spot
        reasons.append(f"Neptune too exact ({neptune_closest:.1f}°)")
    elif neptune_closest <= 5:
        score += 0.8
    elif neptune_closest > 15:
        score -= 0.4

    # Jupiter NOT on natal Neptune (+0.276 correlation)
    trans_jup = trans["Jupiter"]["lon"]
    nat_nep = natal["Neptune"]["lon"]
    jup_nep_orb = closest_hard(trans_jup, nat_nep)
    if jup_nep_orb >= 12:
        score += 1.2  # Jupiter far from natal Neptune = good
    elif jup_nep_orb <= 3:
        score -= 0.8  # Jupiter on natal Neptune = bad (already inflated)
        reasons.append(f"Jup on natNep ({jup_nep_orb:.1f}°) — over-inflated")

    # Total contacts: FEWER is better (-0.219)
    if total_contacts <= 2:
        score += 1.5
        reasons.append(f"low_stim ({total_contacts}contacts)")
    elif total_contacts <= 4:
        score += 0.8
    elif total_contacts >= 7:
        score -= 1.5
        reasons.append(f"overstim ({total_contacts}contacts)")
    elif total_contacts >= 6:
        score -= 0.5

    # Natal JN close (+natal-only positive)
    if nat_jn <= 3:
        score += 1.5
        reasons.append(f"tight natal JN ({nat_jn:.1f}°)")
    elif nat_jn <= 6:
        score += 0.8

    # ===== Unreality score (Neptunian field active) =====
    unreality = 0
    if neptune_closest <= 4:
        unreality += (4 - neptune_closest) / 4 * 3.0
    if nat_jn <= 3:
        unreality += 1.5
    # Transit Neptune hard aspect to natal Sun/ASC/MC specifically
    for target in ("Sun","ASC","MC"):
        if target not in natal: continue
        o = closest_hard(trans["Neptune"]["lon"], natal[target]["lon"])
        if o <= 2:
            unreality += (2-o)/2 * 1.5

    # ===== Forward pre-positioning (when does next fast trigger fire, and Saturn arrive?) =====
    # Compute months until trans Jupiter reaches a natal Sun/Neptune hard aspect
    months_to_jup_trigger = None
    for k in range(0, 24):
        y, m = yx(eval_y, eval_m, k)
        jd = jd_of(y, m, 15, 12.0)
        jul_lon = swe.calc_ut(jd, swe.JUPITER)[0][0] % 360
        for target_name in ("Sun","Neptune"):
            if target_name not in natal: continue
            if closest_hard(jul_lon, natal[target_name]["lon"]) <= 3:
                months_to_jup_trigger = k; break
        if months_to_jup_trigger is not None: break
    # Months until Saturn reaches natal Sun/Nep
    months_to_sat_pop = None
    for k in range(0, 36):
        y, m = yx(eval_y, eval_m, k)
        jd = jd_of(y, m, 15, 12.0)
        sat_lon = swe.calc_ut(jd, swe.SATURN)[0][0] % 360
        for target_name in ("Sun","Neptune"):
            if target_name not in natal: continue
            if closest_hard(sat_lon, natal[target_name]["lon"]) <= 3:
                months_to_sat_pop = k; break
        if months_to_sat_pop is not None: break

    # Pre-positioning score: runway between Jupiter trigger and Saturn pop
    prepos = 0
    runway = None
    if months_to_jup_trigger is not None and months_to_sat_pop is not None:
        runway = months_to_sat_pop - months_to_jup_trigger
        if runway >= 12: prepos = 3.0
        elif runway >= 6: prepos = 2.0
        elif runway >= 3: prepos = 1.0
        elif runway >= 0: prepos = 0.5
        else: prepos = -1.0  # Saturn arrives first = already popped
    elif months_to_jup_trigger is not None:
        prepos = 2.0  # Jupiter coming, Saturn not
    elif months_to_sat_pop is not None and months_to_sat_pop <= 6:
        prepos = -1.5  # only Saturn coming, no Jup — pop imminent

    # ===== Style classification =====
    neptunian_squeeze = (neptune_closest <= 3 and total_contacts <= 5 and unreality >= 4)
    bottoming = (score >= 3 and neptune_closest <= 5)
    post_peak = (total_contacts >= 6 and saturn_closest <= 3 and neptune_closest >= 5)

    if neptunian_squeeze: style = "NEPTUNIAN_SQUEEZE"
    elif bottoming: style = "BOTTOMING"
    elif post_peak: style = "POST_PEAK"
    else: style = "NEUTRAL"

    return {
        "bottom_sig": score, "reasons": reasons,
        "saturn_closest": saturn_closest, "neptune_closest": neptune_closest,
        "jupiter_closest": jupiter_closest, "pluto_closest": pluto_closest,
        "uranus_closest": uranus_closest,
        "total_contacts": total_contacts,
        "jup_nep_transit_orb": jn_transit_orb,
        "natal_JN_orb": nat_jn,
        "unreality": unreality,
        "prepos": prepos, "runway": runway,
        "months_to_jup_trigger": months_to_jup_trigger,
        "months_to_sat_pop": months_to_sat_pop,
        "style": style,
    }

def validate_on_corpus():
    """Run on 152 corpus bottoms and compute Pearson r of bottom_sig vs log mult."""
    from parabolic_corpus import PARABOLIC_BOTTOMS
    scored = []
    for tk, ipo, bot, top, mult, speed, note in PARABOLIC_BOTTOMS:
        try:
            natal = compute_natal(ipo)
            s = score_blowoff_signature(natal, bot[0], bot[1])
            scored.append((tk, mult, s["bottom_sig"], s))
        except: pass
    # Pearson r
    if len(scored) > 2:
        xs = [math.log(m) for tk, m, s, _ in scored]
        ys = [s for tk, m, s, _ in scored]
        mx, my = st.mean(xs), st.mean(ys)
        num = sum((x-mx)*(y-my) for x,y in zip(xs,ys))
        denx = math.sqrt(sum((x-mx)**2 for x in xs))
        deny = math.sqrt(sum((y-my)**2 for y in ys))
        r = num/(denx*deny) if denx*deny > 0 else 0
        print(f"\n  Pearson r (bottom_sig vs log-mult): {r:+.3f}  (n={len(scored)})")
    # Killer-rule validation: charts with Sat≥8 + Nep≤3 — subsequent rally
    killer_cases = [(tk, m, sd) for tk, m, sc, sd in scored
                    if sd["saturn_closest"] >= 8 and sd["neptune_closest"] <= 3]
    if killer_cases:
        mults = [m for tk,m,sd in killer_cases]
        print(f"\n  KILLER RULE validation (Saturn ≥8° + Neptune ≤3° at bottom):")
        print(f"    n={len(killer_cases)}  mean rally={st.mean(mults):.0f}×  median={st.median(mults):.0f}×  max={max(mults):.0f}×")
        print(f"    Killer-cases: {', '.join(f'{tk}({m}×)' for tk,m,_ in sorted(killer_cases, key=lambda x:-x[1])[:15])}")
    return scored

def main():
    print("v18 PRE-BLOWOFF SIGNATURE — empirical calibration on 152-case corpus", file=sys.stderr)

    # Validate first
    print("\nVALIDATING bottom_sig on 152-case corpus...")
    _ = validate_on_corpus()

    # SP500 scan
    print("\nScanning SP500 @ 2026-04...", file=sys.stderr)
    sp500 = []
    with open("/home/user/cyclepapa/data/sp500_ipo_dates.csv") as f:
        sp500 = list(csv.DictReader(f))
    t0 = time.time()
    results = []
    for row in sp500:
        try:
            natal = compute_natal(row["ipo_date"])
            s = score_blowoff_signature(natal, 2026, 4)
            s["ticker"] = row["ticker"]
            s["name"] = row["name"]
            s["ipo"] = row["ipo_date"]
            s["source"] = row.get("source","")
            results.append(s)
        except: pass
    print(f"  {len(results)} in {time.time()-t0:.0f}s", file=sys.stderr)
    results.sort(key=lambda r: -r["bottom_sig"])

    # Top 50 by bottom_sig
    print(f"\n{'='*180}")
    print(f"SP500 TOP 50 by PRE-BLOWOFF BOTTOM_SIG (empirical signal per 152-case corpus)")
    print(f"{'='*180}")
    print(f"{'Rk':>3s} {'Tkr':<6s} {'Name':<26s} {'IPO':<11s} {'BtSig':>5s} {'Sat':>4s} {'Nep':>4s} {'Jup':>4s} {'Plu':>4s} {'#ct':>3s} {'JNnat':>5s} {'Unre':>4s} {'PrePos':>5s} {'Runway':>6s} {'Style':<18s} {'Key'}")
    for i, r in enumerate(results[:50], 1):
        runway = r["runway"] if r["runway"] is not None else "-"
        src = "*" if r["source"] == "sp500_added" else " "
        key = "; ".join(r["reasons"][:2])[:50]
        print(f"{i:3d} {r['ticker']:<6s} {r['name'][:26]:<26s} {r['ipo']:<11s} {r['bottom_sig']:5.2f} {r['saturn_closest']:4.1f} {r['neptune_closest']:4.1f} {r['jupiter_closest']:4.1f} {r['pluto_closest']:4.1f} {r['total_contacts']:>3d} {r['natal_JN_orb']:5.1f} {r['unreality']:4.1f} {r['prepos']:+5.1f} {runway!s:>6s} {r['style']:<18s} {key}{src}")

    # Tier by style
    print(f"\nSTYLE DISTRIBUTION:")
    by_style = defaultdict(list)
    for r in results: by_style[r["style"]].append(r)
    for style in ("NEPTUNIAN_SQUEEZE","BOTTOMING","NEUTRAL","POST_PEAK"):
        tickers = [x["ticker"] for x in by_style.get(style, [])[:20]]
        print(f"  {style:<20s} n={len(by_style.get(style,[]))}  top: {', '.join(tickers[:12])}")

    # KILLER RULE charts currently
    killer = [r for r in results if r["saturn_closest"] >= 8 and r["neptune_closest"] <= 3]
    killer.sort(key=lambda r: -r["bottom_sig"])
    print(f"\n{'='*140}")
    print(f"KILLER RULE — stocks currently showing Saturn ≥8° + Neptune ≤3°")
    print(f"(132.9× avg rally historically, 67% produce ≥10×; only 12% of bottoms have this)")
    print(f"{'='*140}")
    print(f"{'Tkr':<6s} {'Name':<30s} {'IPO':<11s} {'BtSig':>5s} {'Sat':>4s} {'Nep':>4s} {'#ct':>3s} {'JN':>5s} {'Unre':>4s} {'Style':<18s}")
    for r in killer[:30]:
        src = " *" if r["source"] == "sp500_added" else ""
        print(f"{r['ticker']:<6s} {r['name'][:30]:<30s} {r['ipo']:<11s} {r['bottom_sig']:5.2f} {r['saturn_closest']:4.1f} {r['neptune_closest']:4.1f} {r['total_contacts']:>3d} {r['natal_JN_orb']:5.1f} {r['unreality']:4.1f} {r['style']:<18s}{src}")

    # Triple convergence check — reference stocks from user's message
    print(f"\n{'='*140}")
    print(f"REFERENCE CHECK — user's triple-convergence stocks")
    print(f"{'='*140}")
    refs = ["DIS","BRK.B","ABT","BA","HD","PRU","COP","LLY","MGM","BRK.A"]
    for r in results:
        if r["ticker"] in refs:
            print(f"  {r['ticker']:<6s} {r['name'][:30]:<30s} BtSig={r['bottom_sig']:5.2f}  Sat={r['saturn_closest']:.1f}°  Nep={r['neptune_closest']:.1f}°  JN={r['natal_JN_orb']:.1f}°  #ct={r['total_contacts']}  Style={r['style']}")

    # Export
    with open("/home/user/cyclepapa/data/sp500_v18_blowoff_sig.csv","w",newline="") as f:
        w = csv.writer(f)
        w.writerow(["ticker","name","ipo","source","bottom_sig","saturn_closest","neptune_closest",
                    "jupiter_closest","pluto_closest","uranus_closest","total_contacts",
                    "natal_JN_orb","jup_nep_trans_orb","unreality","prepos","runway_months",
                    "months_to_jup_trigger","months_to_sat_pop","style","reasons"])
        for r in results:
            w.writerow([r["ticker"],r["name"],r["ipo"],r["source"],
                        f"{r['bottom_sig']:.2f}",f"{r['saturn_closest']:.1f}",
                        f"{r['neptune_closest']:.1f}",f"{r['jupiter_closest']:.1f}",
                        f"{r['pluto_closest']:.1f}",f"{r['uranus_closest']:.1f}",
                        r["total_contacts"],f"{r['natal_JN_orb']:.1f}",
                        f"{r['jup_nep_transit_orb']:.1f}",f"{r['unreality']:.1f}",
                        f"{r['prepos']:.1f}",r["runway"] if r["runway"] is not None else "",
                        r["months_to_jup_trigger"] if r["months_to_jup_trigger"] is not None else "",
                        r["months_to_sat_pop"] if r["months_to_sat_pop"] is not None else "",
                        r["style"], " | ".join(r["reasons"])])
    print(f"\nExported: data/sp500_v18_blowoff_sig.csv")

if __name__ == "__main__":
    main()
