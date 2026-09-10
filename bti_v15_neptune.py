"""
v15 — Neptune-Aries inflection handler with bullish/bearish bias classification.

Neptune sweep through Aries: 0° (Mar 2025) → 11° (2030).
Each chart with natal sensitive points at 0-15° Aries/Libra/Cancer/Capricorn
gets activated. Additionally, charts with tight natal Jupiter-Neptune aspects
enter the "unreality zone" when transit Neptune crosses natal JN midpoint.

For each candidate:
  1. Compute Neptune pressure NOW and forward peak over 24 months
  2. Classify BULLISH vs BEARISH bias using framework signals:
     BULLISH (meme-parabolic runup):
       + High Gs (natal benefic strength)
       + Ge positive (era-aligned chart)
       + Low burn (chart not already run)
       + McWhirter NN in bottom/setup/launch/peak (bullish zones)
       + Concurrent Jupiter trine/sextile to natal
       + Chart age 1-10 (Qullamaggie-fresh)
       + Dignified almuten
     BEARISH (dissolution/bubble-bust):
       + Low Gs
       + Era misaligned
       + High burn / already ran
       + NN in bear zone
       + Concurrent Saturn hard aspect to natal
       + Old chart
       + Afflicted almuten (Saturn/Mars in weak sign)
"""
import math, csv, time, sys, statistics as st
from collections import defaultdict
import swisseph as swe
import openpyxl
from bti_test import compute_natal, transits_at, jd_of
from bti_v4 import yx, gamma_survive, gamma_era
from classical_archetype import classical_classify, is_day_chart

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

def neptune_lon_at(y, m):
    jd = jd_of(y, m, 15, 12.0)
    res = swe.calc_ut(jd, swe.NEPTUNE)
    return res[0][0] % 360

def natal_jn_aspect(natal):
    """Tightest Jupiter-Neptune aspect orb in natal chart."""
    r = closest_hard(natal["Jupiter"]["lon"], natal["Neptune"]["lon"], 15)
    if r:
        asp, o = r
        return asp, o, (natal["Jupiter"]["lon"] + natal["Neptune"]["lon"]) / 2 % 360
    # Soft aspects too
    for asp in (60, 120):
        for sign in (+1, -1):
            o = orb(natal["Jupiter"]["lon"], natal["Neptune"]["lon"] + sign * asp)
            if o <= 8:
                return asp, o, (natal["Jupiter"]["lon"] + natal["Neptune"]["lon"]) / 2 % 360
    return None, 99, None

def neptune_pressure_at(natal, eval_y, eval_m):
    """Score Neptune's current activation of natal chart (0-15 scale)."""
    nep_lon = neptune_lon_at(eval_y, eval_m)
    score = 0
    detail = []
    # Transit Neptune to natal Sun/Moon/ASC/MC/Jupiter/Neptune
    for target in ("Sun","Moon","ASC","MC","Jupiter","Neptune"):
        if target not in natal: continue
        r = closest_hard(nep_lon, natal[target]["lon"], 5)
        if r:
            asp, o = r
            w = 2.0 if target in ("Sun","Moon","ASC","MC") else 1.5 if target == "Jupiter" else 1.2
            pts = w * (5 - o) / 5
            # Conjunction is the sharpest Neptune activation
            if asp == 0: pts *= 1.3
            score += pts
            detail.append(f"Nep-{target} {asp}° {o:.1f}°")
    # Transit Neptune to natal Jupiter-Neptune midpoint (unreality zone opens)
    asp, jn_o, jn_mp = natal_jn_aspect(natal)
    if jn_mp is not None:
        r = closest_hard(nep_lon, jn_mp, 4)
        if r:
            a2, o2 = r
            pts = 2.5 * (4 - o2) / 4
            # Tight natal JN amplifies
            if jn_o <= 3: pts *= 1.5
            score += pts
            detail.append(f"Nep→JN_mp {a2}° {o2:.1f}° (natal JN {jn_o:.1f}°)")
    return score, detail, nep_lon

def neptune_forward_projection(natal, from_y=2026, from_m=4, months_ahead=36):
    """Scan next 36 months; return (current, peak, peak_month, curve)."""
    curve = []
    current = None
    peak = 0; peak_mo = None
    for k in range(0, months_ahead+1):
        y, m = yx(from_y, from_m, k)
        p, _, _ = neptune_pressure_at(natal, y, m)
        curve.append((y, m, p))
        if k == 0: current = p
        if p > peak:
            peak = p; peak_mo = f"{y}-{m:02d}"
    return {"current": current, "peak": peak, "peak_mo": peak_mo, "curve": curve}

def bullish_bearish_bias(natal, eval_y, eval_m, np_now):
    """Classify Neptune pressure as bullish or bearish per framework signals."""
    trans = transits_at(eval_y, eval_m)
    cls = classical_classify(natal)
    Gs = gamma_survive(natal)
    Ge = gamma_era(natal, eval_y)
    ipo_y = int(natal["_date"][:4])
    age = eval_y - ipo_y
    # Bullish components
    bull = 0
    bear = 0
    reasons = []
    # (1) Survival gate
    if Gs >= 1.10: bull += 1.5; reasons.append(f"Gs={Gs:.2f}(strong)")
    elif Gs >= 1.00: bull += 0.8
    elif Gs >= 0.95: pass  # neutral
    else: bear += 1.2; reasons.append(f"Gs={Gs:.2f}(weak)")
    # (2) Era alignment
    if Ge >= 1.10: bull += 1.0; reasons.append(f"Ge={Ge:.2f}(aligned)")
    elif Ge <= 0.90: bear += 1.0; reasons.append(f"Ge={Ge:.2f}(mis)")
    # (3) McWhirter NN zone
    if cls["nn_category"] in ("launch_zone","setup_zone","bottom_zone","peak_zone"):
        bull += 1.0
        reasons.append(f"NN={cls['nn_category']}(bull)")
    elif cls["nn_category"] == "bear_zone":
        bear += 1.2; reasons.append("NN=bear_zone")
    # (4) Chart age
    if 1 <= age <= 8:
        bull += 1.2; reasons.append(f"age={age}(Qullamaggie)")
    elif age >= 30:
        bear += 0.6; reasons.append(f"age={age}(old)")
    # (5) Concurrent Jupiter support
    ju_lon = trans["Jupiter"]["lon"]
    for target in ("Sun","Moon","Jupiter","Venus","ASC","MC"):
        if target not in natal: continue
        for asp in (0, 60, 120):
            for sign in (+1, -1):
                o = orb(ju_lon, natal[target]["lon"] + sign * asp)
                if o <= 3:
                    bull += 0.6
                    reasons.append(f"trJup {asp}° natal-{target} {o:.1f}°")
                    break
            else: continue
            break
    # (6) Concurrent Saturn hard aspect = bearish concurrent
    sa_lon = trans["Saturn"]["lon"]
    for target in ("Sun","Moon","Venus","ASC","MC","Jupiter"):
        if target not in natal: continue
        r = closest_hard(sa_lon, natal[target]["lon"], 3)
        if r:
            asp, o = r
            if asp in (0, 90, 180):
                bear += 0.7 * (3-o)/3
                reasons.append(f"trSat {asp}° natal-{target} {o:.1f}° (bear)")
                break
    # (7) Almuten stability (Jup/Ven/Sun = strong; Saturn/Mars = fragile)
    if cls["almuten"] in ("Jupiter","Venus","Sun"):
        bull += 0.5; reasons.append(f"almuten={cls['almuten']}(benefic)")
    elif cls["almuten"] == "Mars":
        bear += 0.3
    # (8) JS phase waxing = bullish for Neptunian repricing
    if cls["js_phase"] in ("new","crescent","first_q","gibbous"):
        bull += 0.4
    elif cls["js_phase"] in ("last_q","balsamic"):
        bear += 0.4
    net = bull - bear
    if net >= 3: tag = "BULLISH_STRONG"
    elif net >= 1.5: tag = "BULLISH"
    elif net >= 0.5: tag = "BULLISH_MILD"
    elif net <= -2: tag = "BEARISH_STRONG"
    elif net <= -0.5: tag = "BEARISH"
    else: tag = "NEUTRAL"
    return {"bull": bull, "bear": bear, "net": net, "tag": tag,
            "Gs": Gs, "Ge": Ge, "reasons": reasons, "age": age,
            "nn_cat": cls["nn_category"], "almuten": cls["almuten"],
            "js_phase": cls["js_phase"]}

def score_neptune_inflection(natal, eval_y=2026, eval_m=4):
    """Complete Neptune inflection analysis."""
    asp, jn_o, jn_mp = natal_jn_aspect(natal)
    fwd = neptune_forward_projection(natal, eval_y, eval_m, 36)
    bias = bullish_bearish_bias(natal, eval_y, eval_m, fwd["current"])
    np_now, detail, nep_lon = neptune_pressure_at(natal, eval_y, eval_m)
    # Find when enters zone (crosses 8.0)
    enters_zone = None
    in_zone_months = 0
    peak_above_zone = False
    for y, m, p in fwd["curve"]:
        if p >= 8.0:
            in_zone_months += 1
            if enters_zone is None:
                enters_zone = f"{y}-{m:02d}"
            peak_above_zone = True
    # Inflection sharpness: how fast from current to peak
    months_to_peak = 0
    for i, (y, m, p) in enumerate(fwd["curve"]):
        if p == fwd["peak"]:
            months_to_peak = i; break
    return {
        "np_now": fwd["current"], "np_peak": fwd["peak"], "np_peak_mo": fwd["peak_mo"],
        "natal_JN_orb": jn_o, "natal_JN_aspect": asp,
        "enters_zone": enters_zone, "in_zone_months": in_zone_months,
        "months_to_peak": months_to_peak, "peak_above_zone": peak_above_zone,
        "bull": bias["bull"], "bear": bias["bear"], "net": bias["net"], "tag": bias["tag"],
        "Gs": bias["Gs"], "Ge": bias["Ge"], "age": bias["age"],
        "nn_cat": bias["nn_cat"], "almuten": bias["almuten"], "js_phase": bias["js_phase"],
        "reasons": bias["reasons"],
        "current_detail": detail, "curve": fwd["curve"],
    }

def main():
    # Load SP500
    print("Scanning SP500...", file=sys.stderr)
    sp500 = []
    with open("/home/user/cyclepapa/data/sp500_ipo_dates.csv") as f:
        sp500 = list(csv.DictReader(f))
    results = []
    t0 = time.time()
    for row in sp500:
        try:
            natal = compute_natal(row["ipo_date"])
            r = score_neptune_inflection(natal, 2026, 4)
            results.append((row["ticker"], row["name"], row["sector"], row["ipo_date"], r, row.get("source","")))
        except: pass
    print(f"  SP500 {len(results)} in {time.time()-t0:.0f}s", file=sys.stderr)

    # Rank by Neptune peak
    results.sort(key=lambda x: -x[4]["np_peak"])

    print(f"\n{'='*185}")
    print(f"SP500 NEPTUNE-ARIES INFLECTION @ 2026-04 with BULLISH/BEARISH BIAS CLASSIFICATION")
    print(f"Top 50 by peak Neptune pressure over next 36 months")
    print(f"{'='*185}")
    print(f"{'Rk':>3s} {'Tkr':<6s} {'Name':<26s} {'IPO':<11s} {'Age':>3s} {'NpNow':>5s} {'NpPk':>5s} {'Enters':<10s} {'MoInZ':>5s} {'JNorb':>5s} {'Net':>5s} {'Tag':<16s} {'NN':<11s} {'Alm':<4s} {'Src'}")
    for i, (tk, nm, sec, ipo, r, src) in enumerate(results[:50], 1):
        src_flag = "*" if src == "sp500_added" else " "
        enters = r["enters_zone"] or "-"
        print(f"{i:3d} {tk:<6s} {nm[:26]:<26s} {ipo:<11s} {r['age']:>3d} {r['np_now']:5.2f} {r['np_peak']:5.2f} {enters:<10s} {r['in_zone_months']:>5d} {r['natal_JN_orb']:5.1f} {r['net']:+5.1f} {r['tag']:<16s} {r['nn_cat'][:11]:<11s} {r['almuten'][:4]:<4s}{src_flag}")

    # Separate: BULLISH NEPTUNIAN (peak >= 8) vs BEARISH NEPTUNIAN (peak >= 8)
    print(f"\n{'='*130}")
    print(f"BULLISH NEPTUNIAN — entering unreality zone with POSITIVE framework bias (runup candidates)")
    print(f"{'='*130}")
    bull_zone = [x for x in results if x[4]["peak_above_zone"] and x[4]["net"] >= 1.5]
    bull_zone.sort(key=lambda x: -x[4]["np_peak"])
    print(f"{'Rk':>3s} {'Tkr':<6s} {'Name':<28s} {'IPO':<11s} {'Age':>3s} {'NpPk':>5s} {'Enters':<10s} {'Net':>5s} {'Tag':<16s} {'Why (top reasons)'}")
    for i, (tk, nm, sec, ipo, r, src) in enumerate(bull_zone[:30], 1):
        rsn = " | ".join(r["reasons"][:3])[:55]
        src_flag = " *" if src == "sp500_added" else ""
        print(f"{i:3d} {tk:<6s} {nm[:28]:<28s} {ipo:<11s} {r['age']:>3d} {r['np_peak']:5.2f} {r['enters_zone'] or '-':<10s} {r['net']:+5.1f} {r['tag']:<16s} {rsn}{src_flag}")

    print(f"\n{'='*130}")
    print(f"BEARISH NEPTUNIAN — entering unreality zone with NEGATIVE framework bias (bubble-bust candidates)")
    print(f"{'='*130}")
    bear_zone = [x for x in results if x[4]["peak_above_zone"] and x[4]["net"] <= -0.5]
    bear_zone.sort(key=lambda x: -x[4]["np_peak"])
    print(f"{'Rk':>3s} {'Tkr':<6s} {'Name':<28s} {'IPO':<11s} {'Age':>3s} {'NpPk':>5s} {'Enters':<10s} {'Net':>5s} {'Tag':<16s} {'Why'}")
    for i, (tk, nm, sec, ipo, r, src) in enumerate(bear_zone[:30], 1):
        rsn = " | ".join(r["reasons"][:3])[:55]
        src_flag = " *" if src == "sp500_added" else ""
        print(f"{i:3d} {tk:<6s} {nm[:28]:<28s} {ipo:<11s} {r['age']:>3d} {r['np_peak']:5.2f} {r['enters_zone'] or '-':<10s} {r['net']:+5.1f} {r['tag']:<16s} {rsn}{src_flag}")

    # Highlight tight natal JN charts (< 3°)
    print(f"\n{'='*130}")
    print(f"TIGHT NATAL JUPITER-NEPTUNE (< 3° orb) — the inherently Neptunian charts")
    print(f"{'='*130}")
    tight_jn = [x for x in results if x[4]["natal_JN_orb"] < 3]
    tight_jn.sort(key=lambda x: -x[4]["np_peak"])
    print(f"{'Rk':>3s} {'Tkr':<6s} {'Name':<28s} {'IPO':<11s} {'Age':>3s} {'NpPk':>5s} {'JNorb':>5s} {'Tag':<16s}")
    for i, (tk, nm, sec, ipo, r, src) in enumerate(tight_jn[:25], 1):
        src_flag = " *" if src == "sp500_added" else ""
        print(f"{i:3d} {tk:<6s} {nm[:28]:<28s} {ipo:<11s} {r['age']:>3d} {r['np_peak']:5.2f} {r['natal_JN_orb']:5.2f} {r['tag']:<16s}{src_flag}")

    # Export
    with open("/home/user/cyclepapa/data/sp500_neptune_inflection.csv","w",newline="") as f:
        w = csv.writer(f)
        w.writerow(["ticker","name","sector","ipo","source","age","np_now","np_peak","peak_mo",
                    "natal_JN_orb","enters_zone","in_zone_months","net","tag",
                    "Gs","Ge","nn_cat","almuten","js_phase","bull","bear","top_reason"])
        for (tk, nm, sec, ipo, r, src) in results:
            w.writerow([tk,nm,sec,ipo,src,r["age"],f"{r['np_now']:.2f}",f"{r['np_peak']:.2f}",
                        r["np_peak_mo"],f"{r['natal_JN_orb']:.2f}",r["enters_zone"] or "",
                        r["in_zone_months"],f"{r['net']:+.1f}",r["tag"],
                        f"{r['Gs']:.2f}",f"{r['Ge']:.2f}",r["nn_cat"],r["almuten"],r["js_phase"],
                        f"{r['bull']:.1f}",f"{r['bear']:.1f}",
                        r["reasons"][0] if r["reasons"] else ""])
    print(f"\nExported: data/sp500_neptune_inflection.csv")

    # Also run on Ritter 2000+
    print(f"\nScanning Ritter 2000+...", file=sys.stderr)
    wb = openpyxl.load_workbook("/home/user/cyclepapa/data/IPO-age.xlsx", data_only=True)
    ws = wb["1975-2025"]
    rrows = []
    for row in ws.iter_rows(min_row=2, values_only=True):
        od, nm, tk, cusip, adr, vc, dual, shares, internet, crsp, fnd, roll = row[:12]
        if not od: continue
        try:
            d = int(od); y = d//10000
            if y < 2000: continue
            iso = f"{y:04d}-{(d//100)%100:02d}-{d%100:02d}"
        except: continue
        if not tk or str(tk).strip() in ("",".") or adr==2 or roll==1: continue
        rrows.append((str(tk).strip().upper(), nm or "", iso))
    print(f"  Ritter 2000+: {len(rrows)}", file=sys.stderr)
    rres = []
    for tk, nm, ipo in rrows:
        try:
            natal = compute_natal(ipo)
            r = score_neptune_inflection(natal, 2026, 4)
            rres.append((tk, nm, ipo, r))
        except: pass
    rres.sort(key=lambda x: -x[3]["np_peak"])
    # Top bullish neptunian from Ritter
    print(f"\n{'='*130}")
    print(f"RITTER BULLISH NEPTUNIAN — fresh IPOs entering unreality zone with bullish bias")
    print(f"{'='*130}")
    r_bull = [x for x in rres if x[3]["peak_above_zone"] and x[3]["net"] >= 1.5 and x[3]["age"] <= 15]
    r_bull.sort(key=lambda x: -x[3]["np_peak"])
    print(f"{'Rk':>3s} {'Tkr':<7s} {'Name':<38s} {'IPO':<11s} {'Age':>3s} {'NpPk':>5s} {'Enters':<10s} {'JNorb':>5s} {'Net':>5s} {'Tag':<16s}")
    for i, (tk, nm, ipo, r) in enumerate(r_bull[:30], 1):
        print(f"{i:3d} {tk:<7s} {nm[:38]:<38s} {ipo:<11s} {r['age']:>3d} {r['np_peak']:5.2f} {r['enters_zone'] or '-':<10s} {r['natal_JN_orb']:5.1f} {r['net']:+5.1f} {r['tag']:<16s}")
    with open("/home/user/cyclepapa/data/ritter_neptune_inflection.csv","w",newline="") as f:
        w = csv.writer(f)
        w.writerow(["ticker","name","ipo","age","np_now","np_peak","peak_mo",
                    "natal_JN_orb","enters_zone","in_zone_months","net","tag","Gs","Ge",
                    "nn_cat","almuten","js_phase"])
        for tk, nm, ipo, r in rres:
            w.writerow([tk,nm,ipo,r["age"],f"{r['np_now']:.2f}",f"{r['np_peak']:.2f}",
                        r["np_peak_mo"],f"{r['natal_JN_orb']:.2f}",r["enters_zone"] or "",
                        r["in_zone_months"],f"{r['net']:+.1f}",r["tag"],
                        f"{r['Gs']:.2f}",f"{r['Ge']:.2f}",r["nn_cat"],r["almuten"],r["js_phase"]])
    print(f"\nExported: data/ritter_neptune_inflection.csv")

if __name__ == "__main__":
    main()
