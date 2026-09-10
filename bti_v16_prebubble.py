"""
v16 — PRE-BUBBLE POSITIONING scanner.

Implements the canonical Neptune-bubble thesis per Gidel/Meridian/Silas/
Hogg/Optimesia/QCP convergence:

  "Jupiter-Neptune contact to a stock's natal Sun/Neptune produces
   parabolic overvaluation; Saturn's subsequent arrival at the same
   degree pops the bubble."

For each chart, identify if it is in PRE-BUBBLE POSITION:
  (P1) Natal Jupiter-Neptune tight aspect (< 6°) — inherently Neptunian
  (P2) Transit Jupiter approaching natal JN midpoint OR natal Sun/Neptune
       within next 6-18 months (bubble inflation approach)
  (P3) Transit Neptune approaching natal Sun/ASC/MC within ±2° orb
  (P4) Recent eclipse (last 24 months) within 2-4° of natal sensitive
       (Meridian pre-seeding)
  (P5) Saturn NOT yet reaching that same degree (bubble not popped)
  (P6) Progressed lunation in NEW/CRESCENT/FIRST_QUARTER (waxing)
  (P7) Natal planets in Meridian MUTABLE 0-10° degrees
       (Gem/Vir/Sag/Pis) — amplified activation

Trigger priority (Meridian hierarchy, used to weight activating events):
  solar eclipse > Uranus station > lunar eclipse > Jupiter station >
  Neptune station > Pluto station > outer aspect > Mars/Venus station

Also computes:
  - When Saturn will reach the bubble degree (bubble-pop date)
  - Sector tag per Meridian rulerships
  - Silas "300-500% move" potential flag
"""
import math, csv, time, sys, statistics as st
from collections import defaultdict
import swisseph as swe
import openpyxl
from bti_test import compute_natal, transits_at, jd_of
from bti_v4 import yx, gamma_survive, gamma_era
from classical_archetype import classical_classify, is_day_chart
from classical_extensions import (fixed_star_hits, secondary_progressions,
                                   progressed_lunation_phase, prog_to_natal_aspects)
from eclipse_database import build_eclipse_database, eclipse_hits_natal

SIGNS = ["Ari","Tau","Gem","Can","Leo","Vir","Lib","Sco","Sag","Cap","Aqu","Pis"]
MUTABLE_FIRST_10 = {2, 5, 8, 11}  # Gem=2, Vir=5, Sag=8, Pis=11 — Meridian's rule

# Meridian sector rulerships (keyword → ruler)
SECTOR_KEYWORDS = {
    "Neptune": ["oil","gas","chemical","tobacco","alcohol","beverage","pharma","imaging","film","media","entertainment","music"],
    "Uranus":  ["tech","software","computer","semi","aviation","airline","electric","ev","internet","network","data","ai","quantum"],
    "Pluto":   ["biotech","broker","insurance","m&a","mining","nuclear","power","bank","private equity","merger","acquisition"],
}
def sector_ruler(name):
    n = name.lower()
    for ruler, kw in SECTOR_KEYWORDS.items():
        for k in kw:
            if k in n: return ruler
    return "Mixed"

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

def natal_JN_midpoint(natal):
    """Natal Jupiter-Neptune midpoint."""
    return ((natal["Jupiter"]["lon"] + natal["Neptune"]["lon"]) / 2) % 360

def natal_JN_orb(natal):
    r = closest_hard(natal["Jupiter"]["lon"], natal["Neptune"]["lon"], 15)
    if r: return r[1]
    # Include trines/sextiles
    for asp in (60, 120):
        for sign in (+1, -1):
            o = orb(natal["Jupiter"]["lon"], natal["Neptune"]["lon"] + sign * asp)
            if o <= 8: return o
    return 99

def mutable_natal_count(natal):
    """Meridian rule: count natal planets in first 10° of Gem/Vir/Sag/Pis."""
    count = 0
    bodies = []
    for p in ("Sun","Moon","Mercury","Venus","Mars","Jupiter","Saturn"):
        if p not in natal: continue
        s = natal[p]["sign"]
        deg_in_sign = natal[p]["lon"] % 30
        if s in MUTABLE_FIRST_10 and deg_in_sign <= 10:
            count += 1
            bodies.append((p, SIGNS[s], deg_in_sign))
    return count, bodies

def planet_lon_path(planet_id, from_y, from_m, months=36, step_months=1):
    """Return list of (y, m, lon) for planet over time."""
    path = []
    for k in range(0, months+1, step_months):
        y, m = yx(from_y, from_m, k)
        jd = jd_of(y, m, 15, 12.0)
        res = swe.calc_ut(jd, planet_id)
        path.append((y, m, res[0][0] % 360))
    return path

def months_until_hit(path, target_lon, max_orb=3, aspects=(0,)):
    """Find first month in path where planet comes within max_orb of target via any aspect."""
    for i, (y, m, lon) in enumerate(path):
        for asp in aspects:
            for sign in (+1, -1):
                o = orb(lon, target_lon + sign * asp)
                if o <= max_orb:
                    return i, (y, m), o
    return None

def score_v16_pre_bubble(natal, eval_y, eval_m, ipo_date, name, eclipse_db):
    """Score pre-bubble positioning per Gidel/Meridian/Silas canonical thesis."""
    # Chart age
    ipo_y = int(ipo_date[:4])
    age = eval_y - ipo_y

    # Pressure 1: natal JN orb
    jn_orb = natal_JN_orb(natal)
    jn_mp = natal_JN_midpoint(natal)

    # Tight natal JN = inherently Neptunian
    p1_score = max(0, (6 - jn_orb) / 6) * 3.0 if jn_orb <= 6 else 0

    # Pressure 2: transit Jupiter approaching natal Neptune, Sun, or JN midpoint
    # within next 18 months
    ju_path = planet_lon_path(swe.JUPITER, eval_y, eval_m, months=18)
    p2_score = 0
    p2_detail = []
    bubble_activation_mo = None
    for target, tlon, label in [
        ("natal Neptune", natal["Neptune"]["lon"], "trJup→natNep"),
        ("natal Sun", natal["Sun"]["lon"], "trJup→natSun"),
        ("natal JN mp", jn_mp, "trJup→natJN_mp"),
    ]:
        hit = months_until_hit(ju_path, tlon, max_orb=3, aspects=(0,))
        if hit:
            idx, (y, m), o = hit
            # Peak weight if hitting 3-12 months ahead (enough time to position)
            if 3 <= idx <= 15:
                pts = 2.5 * (3 - o) / 3 * (1.2 if idx <= 9 else 1.0)
                p2_score += pts
                p2_detail.append(f"{label} {y}-{m:02d} ({o:.1f}°)")
                if bubble_activation_mo is None or idx < bubble_activation_mo:
                    bubble_activation_mo = idx

    # Pressure 3: transit Neptune approaching natal Sun/ASC/MC
    ne_path = planet_lon_path(swe.NEPTUNE, eval_y, eval_m, months=36)
    p3_score = 0
    p3_detail = []
    for target_name in ("Sun","Moon","ASC","MC"):
        if target_name not in natal: continue
        hit = months_until_hit(ne_path, natal[target_name]["lon"], max_orb=2.5, aspects=(0, 90, 180))
        if hit:
            idx, (y, m), o = hit
            if 0 <= idx <= 24:
                pts = 2.0 * (2.5 - o) / 2.5
                p3_score += pts
                p3_detail.append(f"trNep→nat{target_name} {y}-{m:02d} ({o:.1f}°)")

    # Pressure 4: Eclipse pre-seeding — any eclipse in last 24 months within 2.5° of natal
    jd_center = jd_of(eval_y, eval_m, 15, 12.0)
    eclipse_hits = eclipse_hits_natal(eclipse_db, natal, jd_center,
                                       months_back=24, months_fwd=3, max_orb=2.5)
    # Weight by Meridian hierarchy: total_solar > annular_solar > lunar types
    TYPE_W = {"total_solar": 1.5, "annular_solar": 1.3, "hybrid_solar": 1.4,
              "partial_solar": 1.0, "total_lunar": 1.1, "partial_lunar": 0.8,
              "penumbral_lunar": 0.5, "solar": 1.0, "lunar": 0.7}
    p4_score = 0
    p4_detail = []
    for h in eclipse_hits:
        w = TYPE_W.get(h["eclipse_type"], 0.8)
        # Privilege hits on Sun/Moon/ASC/MC/Jupiter/Neptune
        body_w = 1.5 if h["natal_body"] in ("Sun","Moon","ASC","MC") else 1.2 if h["natal_body"] in ("Jupiter","Neptune") else 0.8
        # Privilege tight orbs
        orb_w = (2.5 - h["orb"]) / 2.5
        pts = w * body_w * orb_w
        p4_score += pts
        if pts > 0.5:
            p4_detail.append(f"{h['eclipse_date']}/{h['eclipse_type'][:6]}→{h['natal_body']}:{h['orb']:.1f}°")

    # Pressure 5 (ANTI): Saturn NOT yet reaching natal Neptune/Sun degree
    sa_path = planet_lon_path(swe.SATURN, eval_y, eval_m, months=36)
    p5_penalty = 0
    p5_detail = []
    saturn_to_bubble_deg_mo = None
    for target_name in ("Neptune","Sun","Jupiter"):
        if target_name not in natal: continue
        hit = months_until_hit(sa_path, natal[target_name]["lon"], max_orb=3, aspects=(0,))
        if hit:
            idx, (y, m), o = hit
            # IF Saturn arrives BEFORE the bubble peaks, it pops it first (bearish)
            if idx <= 6:
                p5_penalty += 2.0 * (3-o)/3  # Saturn already here — reversal zone
                p5_detail.append(f"Saturn {y}-{m:02d} natNep/Sun ({o:.1f}°) — POP")
                if saturn_to_bubble_deg_mo is None:
                    saturn_to_bubble_deg_mo = idx
            elif idx <= 24:
                p5_detail.append(f"Saturn {y}-{m:02d} natNep/Sun ({o:.1f}°) — upcoming")
                if saturn_to_bubble_deg_mo is None:
                    saturn_to_bubble_deg_mo = idx

    # Pressure 6: progressed lunation phase — waxing = inflating
    try:
        prog, age_yrs = secondary_progressions(ipo_date, f"{eval_y:04d}-{eval_m:02d}-15")
        prog_phase = progressed_lunation_phase(prog)
    except:
        prog_phase = "unknown"
    if prog_phase in ("prog_new", "prog_crescent", "prog_first_q"):
        p6_score = 1.5
    elif prog_phase in ("prog_gibbous", "prog_full"):
        p6_score = 0.8
    else:
        p6_score = 0.3

    # Pressure 7: Meridian mutable degrees
    mut_count, mut_bodies = mutable_natal_count(natal)
    p7_score = mut_count * 0.7

    # Sector ruler match
    sector = sector_ruler(name)
    sector_bonus = 0
    if sector == "Neptune" and jn_orb < 6:
        sector_bonus = 0.8  # Neptune-ruled sector + Neptunian chart = double match
    elif sector in ("Neptune","Uranus","Pluto"):
        sector_bonus = 0.4

    # Framework gates
    Gs = gamma_survive(natal)
    Ge = gamma_era(natal, eval_y)

    # Age modifier
    if 1 <= age <= 8:
        age_mod = 1.2
    elif 9 <= age <= 25:
        age_mod = 1.0
    elif age >= 26:
        age_mod = 0.85
    else:
        age_mod = 0.7

    # COMPOSITE
    base = (p1_score + p2_score * 1.3 + p3_score + p4_score * 1.2 +
            p6_score + p7_score + sector_bonus)
    # Saturn-penalty subtracts from the positioning score
    pre_bubble = (base - p5_penalty * 1.0) * age_mod * (Gs ** 0.5) * (Ge ** 0.3)

    # Classification
    saturn_imminent = saturn_to_bubble_deg_mo is not None and saturn_to_bubble_deg_mo <= 6
    has_bubble_setup = p2_score + p3_score + p4_score > 2.5
    if saturn_imminent:
        tag = "SATURN_POP_NEAR"
    elif has_bubble_setup and pre_bubble >= 6 and jn_orb <= 6:
        tag = "PRE_BUBBLE_PRIME"
    elif has_bubble_setup and pre_bubble >= 4:
        tag = "PRE_BUBBLE"
    elif pre_bubble >= 3 and p4_score > 1:
        tag = "ECLIPSE_PRESEED"
    else:
        tag = "NEUTRAL"

    return {
        "pre_bubble": pre_bubble, "tag": tag,
        "age": age, "jn_orb": jn_orb, "jn_mp": jn_mp,
        "p1_natal_JN": p1_score, "p2_tr_Jup": p2_score, "p2_detail": p2_detail,
        "p3_tr_Nep": p3_score, "p3_detail": p3_detail,
        "p4_eclipse": p4_score, "p4_detail": p4_detail,
        "p5_saturn_penalty": p5_penalty, "p5_detail": p5_detail,
        "p6_prog": p6_score, "prog_phase": prog_phase,
        "p7_mutable": p7_score, "mut_bodies": mut_bodies, "mut_count": mut_count,
        "sector_ruler": sector, "sector_bonus": sector_bonus,
        "bubble_activation_mo": bubble_activation_mo,
        "saturn_pop_mo": saturn_to_bubble_deg_mo,
        "Gs": Gs, "Ge": Ge,
    }

def main():
    print("Building eclipse DB 1970-2035...", file=sys.stderr)
    t0 = time.time()
    db = build_eclipse_database(1970, 2035)
    print(f"  {len(db)} eclipses ({time.time()-t0:.0f}s)", file=sys.stderr)

    # SP500 scan
    sp500 = []
    with open("/home/user/cyclepapa/data/sp500_ipo_dates.csv") as f:
        sp500 = list(csv.DictReader(f))
    t0 = time.time()
    results = []
    for row in sp500:
        try:
            natal = compute_natal(row["ipo_date"])
            r = score_v16_pre_bubble(natal, 2026, 4, row["ipo_date"], row["name"], db)
            r["source"] = row.get("source","")
            results.append((row["ticker"], row["name"], row["sector"], row["ipo_date"], r))
        except Exception:
            pass
    print(f"  SP500 {len(results)} in {time.time()-t0:.0f}s", file=sys.stderr)
    results.sort(key=lambda x: -x[4]["pre_bubble"])

    # PRE_BUBBLE_PRIME shortlist
    print(f"\n{'='*165}")
    print(f"PRE-BUBBLE PRIME — inherently Neptunian charts with bubble activation ahead, Saturn NOT yet arriving")
    print(f"(Gidel/Meridian/Silas canonical positioning)")
    print(f"{'='*165}")
    prime = [x for x in results if x[4]["tag"] == "PRE_BUBBLE_PRIME"]
    prime.sort(key=lambda x: -x[4]["pre_bubble"])
    print(f"{'Rk':>3s} {'Tkr':<6s} {'Name':<26s} {'IPO':<11s} {'Age':>3s} {'Score':>5s} {'JN':>4s} {'Act':>3s} {'Pop':>3s} {'Sec':<8s} {'Triggers'}")
    for i, (tk, nm, sec, ipo, r) in enumerate(prime[:30], 1):
        act = r["bubble_activation_mo"] if r["bubble_activation_mo"] is not None else "-"
        pop = r["saturn_pop_mo"] if r["saturn_pop_mo"] is not None else "-"
        triggers = "|".join((r["p2_detail"] + r["p3_detail"] + r["p4_detail"][:1])[:3])[:70]
        src_flag = "*" if r.get("source") == "sp500_added" else " "
        print(f"{i:3d} {tk:<6s} {nm[:26]:<26s} {ipo:<11s} {r['age']:>3d} {r['pre_bubble']:5.2f} {r['jn_orb']:4.1f} {act!s:>3s} {pop!s:>3s} {r['sector_ruler']:<8s} {triggers}{src_flag}")

    # PRE_BUBBLE (broader)
    print(f"\n{'='*165}")
    print(f"PRE_BUBBLE (broader) + ECLIPSE_PRESEED (non-prime but positioned)")
    print(f"{'='*165}")
    bubble = [x for x in results if x[4]["tag"] in ("PRE_BUBBLE","ECLIPSE_PRESEED")]
    bubble.sort(key=lambda x: -x[4]["pre_bubble"])
    for i, (tk, nm, sec, ipo, r) in enumerate(bubble[:40], 1):
        act = r["bubble_activation_mo"] if r["bubble_activation_mo"] is not None else "-"
        pop = r["saturn_pop_mo"] if r["saturn_pop_mo"] is not None else "-"
        triggers = "|".join((r["p2_detail"] + r["p3_detail"] + r["p4_detail"][:1])[:3])[:70]
        src_flag = "*" if r.get("source") == "sp500_added" else " "
        print(f"{i:3d} {tk:<6s} {nm[:26]:<26s} {ipo:<11s} {r['age']:>3d} {r['pre_bubble']:5.2f} {r['jn_orb']:4.1f} {act!s:>3s} {pop!s:>3s} {r['tag']:<17s} {triggers}{src_flag}")

    # Avoid list — Saturn pop near
    print(f"\n{'='*165}")
    print(f"SATURN_POP_NEAR — Saturn arriving at bubble-degree within 6 months (AVOID / bearish)")
    print(f"{'='*165}")
    avoid = [x for x in results if x[4]["tag"] == "SATURN_POP_NEAR"]
    avoid.sort(key=lambda x: -x[4]["pre_bubble"])
    for i, (tk, nm, sec, ipo, r) in enumerate(avoid[:20], 1):
        pop = r["saturn_pop_mo"]
        triggers = "|".join((r["p5_detail"] + r["p4_detail"][:1])[:3])[:60]
        src_flag = "*" if r.get("source") == "sp500_added" else " "
        print(f"{i:3d} {tk:<6s} {nm[:26]:<26s} {ipo:<11s} {r['age']:>3d} pop_in={pop}mo  {triggers}{src_flag}")

    # Export
    with open("/home/user/cyclepapa/data/sp500_pre_bubble_v16.csv","w",newline="") as f:
        w = csv.writer(f)
        w.writerow(["ticker","name","sector","ipo","source","age","pre_bubble","tag",
                    "jn_orb","bubble_activation_mo","saturn_pop_mo","p1","p2","p3","p4","p5",
                    "prog_phase","mut_count","sector_ruler","Gs","Ge",
                    "p2_detail","p3_detail","p4_detail","p5_detail"])
        for (tk, nm, sec, ipo, r) in results:
            w.writerow([tk,nm,sec,ipo,r.get("source",""),r["age"],
                        f"{r['pre_bubble']:.2f}",r["tag"],f"{r['jn_orb']:.2f}",
                        r["bubble_activation_mo"] or "",r["saturn_pop_mo"] or "",
                        f"{r['p1_natal_JN']:.2f}",f"{r['p2_tr_Jup']:.2f}",
                        f"{r['p3_tr_Nep']:.2f}",f"{r['p4_eclipse']:.2f}",
                        f"{r['p5_saturn_penalty']:.2f}",
                        r["prog_phase"],r["mut_count"],r["sector_ruler"],
                        f"{r['Gs']:.2f}",f"{r['Ge']:.2f}",
                        " | ".join(r["p2_detail"]),
                        " | ".join(r["p3_detail"]),
                        " | ".join(r["p4_detail"][:3]),
                        " | ".join(r["p5_detail"])])
    print(f"\nExported: data/sp500_pre_bubble_v16.csv")

    # Ritter post-2015 (younger charts more relevant for pre-bubble)
    print(f"\nScanning Ritter post-2010...", file=sys.stderr)
    wb = openpyxl.load_workbook("/home/user/cyclepapa/data/IPO-age.xlsx", data_only=True)
    ws = wb["1975-2025"]
    rrows = []
    for row in ws.iter_rows(min_row=2, values_only=True):
        od, nm, tk, cusip, adr, vc, dual, shares, internet, crsp, fnd, roll = row[:12]
        if not od: continue
        try:
            d = int(od); y = d//10000
            if y < 2010: continue
            iso = f"{y:04d}-{(d//100)%100:02d}-{d%100:02d}"
        except: continue
        if not tk or str(tk).strip() in ("",".") or adr==2 or roll==1: continue
        rrows.append((str(tk).strip().upper(), nm or "", iso))
    print(f"  Universe: {len(rrows)}", file=sys.stderr)
    t0 = time.time()
    rres = []
    for tk, nm, ipo in rrows:
        try:
            natal = compute_natal(ipo)
            r = score_v16_pre_bubble(natal, 2026, 4, ipo, nm, db)
            rres.append((tk, nm, ipo, r))
        except: pass
    print(f"  Scanned {len(rres)} in {time.time()-t0:.0f}s", file=sys.stderr)
    rres.sort(key=lambda x: -x[3]["pre_bubble"])

    # Ritter PRE_BUBBLE_PRIME
    print(f"\n{'='*165}")
    print(f"RITTER PRE_BUBBLE_PRIME — fresh IPOs positioned for parabolic runup")
    print(f"{'='*165}")
    r_prime = [x for x in rres if x[3]["tag"] == "PRE_BUBBLE_PRIME"]
    r_prime.sort(key=lambda x: -x[3]["pre_bubble"])
    print(f"{'Rk':>3s} {'Tkr':<7s} {'Name':<36s} {'IPO':<11s} {'Age':>3s} {'Score':>5s} {'JN':>4s} {'Act':>3s} {'Pop':>3s} {'Sec':<8s} {'Triggers'}")
    for i, (tk, nm, ipo, r) in enumerate(r_prime[:40], 1):
        act = r["bubble_activation_mo"] if r["bubble_activation_mo"] is not None else "-"
        pop = r["saturn_pop_mo"] if r["saturn_pop_mo"] is not None else "-"
        triggers = "|".join((r["p2_detail"] + r["p3_detail"] + r["p4_detail"][:1])[:3])[:60]
        print(f"{i:3d} {tk:<7s} {nm[:36]:<36s} {ipo:<11s} {r['age']:>3d} {r['pre_bubble']:5.2f} {r['jn_orb']:4.1f} {act!s:>3s} {pop!s:>3s} {r['sector_ruler']:<8s} {triggers}")

    with open("/home/user/cyclepapa/data/ritter_pre_bubble_v16.csv","w",newline="") as f:
        w = csv.writer(f)
        w.writerow(["ticker","name","ipo","age","pre_bubble","tag","jn_orb",
                    "bubble_activation_mo","saturn_pop_mo","p1","p2","p3","p4","p5",
                    "prog_phase","mut_count","sector_ruler","Gs","Ge",
                    "p2_detail","p3_detail","p4_detail","p5_detail"])
        for tk, nm, ipo, r in rres:
            w.writerow([tk,nm,ipo,r["age"],f"{r['pre_bubble']:.2f}",r["tag"],
                        f"{r['jn_orb']:.2f}",r["bubble_activation_mo"] or "",
                        r["saturn_pop_mo"] or "",
                        f"{r['p1_natal_JN']:.2f}",f"{r['p2_tr_Jup']:.2f}",
                        f"{r['p3_tr_Nep']:.2f}",f"{r['p4_eclipse']:.2f}",
                        f"{r['p5_saturn_penalty']:.2f}",
                        r["prog_phase"],r["mut_count"],r["sector_ruler"],
                        f"{r['Gs']:.2f}",f"{r['Ge']:.2f}",
                        " | ".join(r["p2_detail"]),
                        " | ".join(r["p3_detail"]),
                        " | ".join(r["p4_detail"][:3]),
                        " | ".join(r["p5_detail"])])
    print(f"Exported: data/ritter_pre_bubble_v16.csv")

if __name__ == "__main__":
    main()
