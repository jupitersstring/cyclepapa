"""
v21 — FORWARD TRAJECTORY scanner: find charts where astro is
IMPROVING over next 24 months AND heading to a BUBBLISH peak.

Criteria:
  - Current score moderate/low (not already at peak)
  - Monthly forward scores show rising trajectory
  - Peak score high + 3-18 months ahead (positioning runway)
  - Saturn does NOT arrive at natal Sun/Neptune before peak (no early pop)
  - Bubblish signature at peak: Jupiter on natal Neptune OR
    Neptune on natal Sun/MC OR multi-outer convergence
  - Young-to-mid chart age (1-30 yr)

For each candidate:
  1. Score now (April 2026)
  2. Score each month April 2026 - April 2028
  3. Find peak
  4. Compute runway = months to peak
  5. Check Saturn-arrival to key natal degrees before peak
  6. Compute bubblish signature at peak month
  7. Rank by (peak - current) * bubblish_at_peak * (1 if saturn_safe else 0.4)
"""
import math, csv, sys, time, statistics as st
from collections import defaultdict
import swisseph as swe
from bti_test import compute_natal, transits_at, jd_of
from bti_v4 import yx, gamma_survive, gamma_era
from eclipse_database import build_eclipse_database, eclipse_hits_natal
from bti_v19_empirical import SINGLE_PLANET_WEIGHTS, COMPOUND_RULES, bucket_weight, closest_hard, orb

def score_snapshot(natal, eval_y, eval_m, db):
    """Score at a single month — v19 empirical + eclipse."""
    trans = transits_at(eval_y, eval_m)
    targets = {p: natal[p]["lon"] for p in ("Sun","Moon","ASC","MC") if p in natal}
    outer_orbs = {}
    for outer in ("Jupiter","Saturn","Uranus","Neptune","Pluto"):
        best = 99
        for tlon in targets.values():
            o = closest_hard(trans[outer]["lon"], tlon)
            if o < best: best = o
        outer_orbs[outer] = best
    single_score = sum(bucket_weight(p, o) for p, o in outer_orbs.items())
    compound = sum(w for label, fn, w in COMPOUND_RULES if fn(outer_orbs))
    # Jupiter on natal Neptune (Gidel bubble trigger)
    jup_natNep = closest_hard(trans["Jupiter"]["lon"], natal["Neptune"]["lon"])
    # Neptune on natal Sun/MC (fantasy arrival)
    nep_sun = closest_hard(trans["Neptune"]["lon"], natal["Sun"]["lon"])
    nep_mc = closest_hard(trans["Neptune"]["lon"], natal["MC"]["lon"]) if "MC" in natal else 99
    # Eclipse preseed
    jd_c = jd_of(eval_y, eval_m, 15, 12.0)
    hits = eclipse_hits_natal(db, natal, jd_c, months_back=18, months_fwd=3, max_orb=3)
    eclipse = 0
    for h in hits:
        tw = 1.5 if "total" in h["eclipse_type"] else (1.0 if "partial" in h["eclipse_type"] or "annular" in h["eclipse_type"] else 0.5)
        eclipse += tw * (3 - h["orb"]) / 3
    # Bubblish signature: Jupiter-natNep + Neptune-Sun + compound rules
    bubblish = 0
    if jup_natNep <= 3:
        bubblish += 2.5 * (3 - jup_natNep) / 3
    elif jup_natNep <= 6:
        bubblish += 1.0 * (6 - jup_natNep) / 6
    if nep_sun <= 3:
        bubblish += 2.0 * (3 - nep_sun) / 3
    if nep_mc <= 3:
        bubblish += 1.5 * (3 - nep_mc) / 3
    # Multi-outer close
    n_close = sum(1 for o in outer_orbs.values() if o <= 5)
    if n_close >= 3:
        bubblish += 1.0
    # Pluto 8-12 (empirical top signal)
    if 8 <= outer_orbs["Pluto"] < 12:
        bubblish += 1.5
    # Uranus 3-5 (empirical top)
    if 3 <= outer_orbs["Uranus"] < 5:
        bubblish += 1.2

    composite = single_score + compound * 1.5 + eclipse * 1.3 + bubblish * 1.2
    return {
        "composite": composite, "single": single_score, "compound": compound,
        "eclipse": eclipse, "bubblish": bubblish,
        "jup_natNep": jup_natNep, "nep_sun": nep_sun, "nep_mc": nep_mc,
        "outer_orbs": outer_orbs,
    }

def saturn_pop_month(natal, start_y, start_m, months=24):
    """First month within window where Saturn conjuncts natal Sun/Neptune within 3°."""
    for k in range(0, months):
        y, m = yx(start_y, start_m, k)
        jd = jd_of(y, m, 15, 12.0)
        sat_lon = swe.calc_ut(jd, swe.SATURN)[0][0] % 360
        for tgt in ("Sun", "Neptune"):
            if tgt not in natal: continue
            if closest_hard(sat_lon, natal[tgt]["lon"]) <= 3:
                return k
    return None

def forward_analysis(natal, start_y, start_m, db, months=24):
    """Compute monthly trajectory and find peak + bubblish details."""
    trajectory = []
    for k in range(0, months+1):
        y, m = yx(start_y, start_m, k)
        snap = score_snapshot(natal, y, m, db)
        trajectory.append({"k": k, "y": y, "m": m, **snap})
    # Find peak
    peak = max(trajectory, key=lambda s: s["composite"])
    current = trajectory[0]
    # Peak by bubblish score specifically
    bubblish_peak = max(trajectory, key=lambda s: s["bubblish"])
    # Count months rising from current
    rising_months = 0
    for i in range(1, len(trajectory)):
        if trajectory[i]["composite"] >= trajectory[i-1]["composite"]:
            rising_months += 1
        else:
            if rising_months < 3: rising_months = 0  # reset on early reversal
    # Saturn pop month
    sat_pop = saturn_pop_month(natal, start_y, start_m, months)
    # Is saturn_pop before peak?
    runway_months = peak["k"]
    saturn_safe = (sat_pop is None) or (sat_pop > runway_months + 2)
    improvement = peak["composite"] - current["composite"]
    bubbl_improvement = bubblish_peak["bubblish"] - current["bubblish"]
    return {
        "current": current, "peak": peak, "bubblish_peak": bubblish_peak,
        "trajectory": trajectory, "runway": runway_months,
        "saturn_pop": sat_pop, "saturn_safe": saturn_safe,
        "improvement": improvement, "bubbl_improvement": bubbl_improvement,
    }

def main():
    print("Building eclipse DB...", file=sys.stderr)
    db = build_eclipse_database(1970, 2035)

    # Curated tradeable universe — known names likely interesting
    TRADEABLE = [
        # Recent IPOs / Qullamaggie-fresh
        ("RDDT","2024-03-21"), ("ALAB","2024-03-20"), ("HNGE","2025-05-22"),
        ("RBRK","2024-04-25"), ("OS","2024-07-24"), ("INGM","2024-10-24"),
        ("ARM","2023-09-14"), ("KVYO","2023-09-20"), ("BIRK","2023-10-11"),
        ("GEV","2024-04-02"), ("SMR","2022-05-03"), ("OKLO","2024-05-10"),
        ("NNE","2024-05-08"), ("CRWV","2025-03-28"), ("CEG","2022-02-02"),
        ("VST","2016-10-10"), ("NBIS","2024-10-21"), ("TPL","2024-11-26"),
        ("SOUN","2022-04-28"), ("RGTI","2022-03-02"), ("QBTS","2022-08-08"),
        ("IONQ","2021-10-01"), ("RKLB","2021-08-25"),
        # Recent rallies that may continue or reverse
        ("NVDA","1999-01-22"), ("PLTR","2020-09-30"), ("APP","2021-04-15"),
        ("SMCI","2007-03-29"), ("CVNA","2017-04-28"), ("MSTR","1998-06-11"),
        ("COIN","2021-04-14"), ("HIMS","2021-01-21"), ("HOOD","2021-07-29"),
        ("SOFI","2021-06-01"), ("UPST","2020-12-16"), ("AFRM","2021-01-13"),
        ("TSLA","2010-06-29"), ("META","2012-05-18"), ("NFLX","2002-05-23"),
        ("CRWD","2019-06-12"), ("PANW","2012-07-19"), ("NOW","2012-06-29"),
        ("ANET","2014-06-06"), ("SNOW","2020-09-16"), ("MDB","2017-10-19"),
        ("ZS","2018-03-16"), ("DDOG","2019-09-19"), ("NET","2019-09-13"),
        ("FSLY","2019-05-17"), ("DOCU","2018-04-27"), ("TWLO","2016-06-23"),
        ("OKTA","2017-04-07"), ("TEAM","2015-12-10"), ("DT","2019-08-01"),
        # Depressed / washed out candidates (Qullamaggie-style)
        ("LULU","2007-07-27"), ("ULTA","2007-10-24"), ("ELF","2016-09-22"),
        ("CMG","2006-01-25"), ("DUOL","2021-07-28"), ("PTON","2019-09-26"),
        ("CHWY","2019-06-14"), ("ABNB","2020-12-10"), ("DASH","2020-12-09"),
        ("UBER","2019-05-10"), ("DKNG","2020-04-24"),
        ("WBD","2022-04-11"), ("PARA","2022-01-03"), ("DIS","1957-11-12"),
        ("ROKU","2017-09-28"), ("SNAP","2017-03-02"), ("PINS","2019-04-18"),
        ("FIVE","2012-07-19"), ("ETSY","2015-04-16"), ("W","2014-10-02"),
        # Biotech parabolics
        ("VKTX","2015-09-29"), ("MRNA","2018-12-07"), ("BNTX","2019-10-10"),
        ("RIVN","2021-11-10"), ("LCID","2020-07-31"), ("NIO","2018-09-12"),
        ("XPEV","2020-08-27"), ("LI","2020-07-30"),
        # Classic blue chips
        ("AAPL","1980-12-12"), ("MSFT","1986-03-13"), ("GOOG","2004-08-19"),
        ("AMZN","1997-05-15"), ("BRK.B","1996-05-09"), ("JPM","2000-12-31"),
        # Energy/power
        ("OKLO","2024-05-10"), ("URA","2019-11-04"), ("CCJ","1996-11-04"),
        ("NXE","2013-06-04"),
        # Recent meme / short squeeze candidates
        ("GME","2002-02-13"), ("AMC","2013-12-18"), ("KSS","1992-05-19"),
        ("BBBY","1992-06-04"),
        # Fame DNA tradeables from prior analysis
        ("ABR","2003-11-11"), ("LPSN","2000-04-06"), ("SGMO","2000-04-06"),
        ("AGLE","2016-04-06"), ("ELVT","2017-04-06"), ("SNDR","2017-04-06"),
    ]
    # Dedupe
    seen = set()
    unique = [(t, d) for t, d in TRADEABLE if not (t in seen or seen.add(t))]
    print(f"Universe: {len(unique)} tradeable tickers", file=sys.stderr)

    t0 = time.time()
    results = []
    for tk, ipo in unique:
        try:
            natal = compute_natal(ipo)
            fa = forward_analysis(natal, 2026, 4, db, months=24)
            ipo_y = int(ipo[:4])
            age = 2026 - ipo_y
            results.append({
                "ticker": tk, "ipo": ipo, "age": age,
                "now": fa["current"]["composite"],
                "peak": fa["peak"]["composite"],
                "peak_month": f"{fa['peak']['y']}-{fa['peak']['m']:02d}",
                "runway": fa["runway"],
                "improvement": fa["improvement"],
                "bubbl_now": fa["current"]["bubblish"],
                "bubbl_peak": fa["bubblish_peak"]["bubblish"],
                "bubbl_peak_month": f"{fa['bubblish_peak']['y']}-{fa['bubblish_peak']['m']:02d}",
                "bubbl_improvement": fa["bubbl_improvement"],
                "saturn_pop": fa["saturn_pop"],
                "saturn_safe": fa["saturn_safe"],
                "peak_details": fa["peak"],
                "bubbl_peak_details": fa["bubblish_peak"],
                "trajectory": [(s["k"], s["composite"]) for s in fa["trajectory"]],
            })
        except Exception as e:
            pass
    print(f"  Scanned {len(results)} in {time.time()-t0:.0f}s", file=sys.stderr)

    # Filter: ONLY charts where improvement > threshold, runway 3-18, saturn safe
    improving = [r for r in results
                 if r["improvement"] >= 3.0
                 and 3 <= r["runway"] <= 18
                 and r["saturn_safe"]
                 and r["age"] >= 1]
    improving.sort(key=lambda r: -(r["improvement"] + r["bubbl_improvement"] * 1.5))

    print(f"\n{'='*175}")
    print(f"FORWARD IMPROVING + BUBBLISH PEAK — criteria: improvement>=3, runway 3-18mo, Saturn safe")
    print(f"{'='*175}")
    print(f"{'Rk':>3s} {'Tkr':<7s} {'IPO':<11s} {'Age':>3s} {'Now':>5s} {'Peak':>5s} {'Δ':>4s} {'PeakMo':<8s} {'Run':>3s} {'SatPop':>6s} {'BubNow':>6s} {'BubPk':>5s} {'BubMo':<8s} {'Saf':>3s}")
    for i, r in enumerate(improving[:40], 1):
        sat = str(r['saturn_pop']) if r['saturn_pop'] is not None else 'never'
        safe = "Y" if r['saturn_safe'] else "N"
        print(f"{i:3d} {r['ticker']:<7s} {r['ipo']:<11s} {r['age']:>3d} {r['now']:5.1f} {r['peak']:5.1f} {r['improvement']:+4.1f} {r['peak_month']:<8s} {r['runway']:>3d} {sat:>6s} {r['bubbl_now']:6.1f} {r['bubbl_peak']:5.1f} {r['bubbl_peak_month']:<8s} {safe:>3s}")

    # Show sparkline trajectory for top 20
    print(f"\n{'='*175}")
    print(f"TRAJECTORIES — forward 24-month composite sparklines (top 20 improving)")
    print(f"{'='*175}")
    for r in improving[:20]:
        traj = r["trajectory"]
        max_s = max(s for _, s in traj); min_s = min(s for _, s in traj)
        span = max_s - min_s if max_s > min_s else 1
        # Normalize to 0-9
        bars = "·▁▂▃▄▅▆▇█"
        spark = "".join(bars[min(8, int((s-min_s)/span * 8))] for _, s in traj)
        sat_str = f"Sat@{r['saturn_pop']}mo" if r['saturn_pop'] is not None else "Sat-safe"
        print(f"  {r['ticker']:<7s} [{spark}]  now={r['now']:.1f} peak={r['peak']:.1f}({r['peak_month']}) Δ+{r['improvement']:.1f}  bubblePk={r['bubbl_peak']:.1f}({r['bubbl_peak_month']}) {sat_str}")

    # High-bubblish-improvement specifically
    print(f"\n{'='*170}")
    print(f"MOST BUBBLISH-BOUND — largest increase in bubblish signature specifically")
    print(f"{'='*170}")
    bubbl_sorted = sorted(improving, key=lambda r: -r["bubbl_improvement"])
    print(f"{'Tkr':<7s} {'IPO':<11s} {'Age':>3s} {'BubNow':>6s} {'BubPk':>5s} {'ΔBub':>5s} {'BubMo':<8s} {'PkDetails'}")
    for r in bubbl_sorted[:25]:
        d = r["bubbl_peak_details"]
        details = f"Jup-natNep:{d['jup_natNep']:.1f}° Nep-Sun:{d['nep_sun']:.1f}° Nep-MC:{d['nep_mc']:.1f}° Plu:{d['outer_orbs']['Pluto']:.1f}°"
        print(f"{r['ticker']:<7s} {r['ipo']:<11s} {r['age']:>3d} {r['bubbl_now']:6.1f} {r['bubbl_peak']:5.1f} +{r['bubbl_improvement']:4.1f} {r['bubbl_peak_month']:<8s} {details}")

    # Export
    with open("/home/user/cyclepapa/data/forward_bubblish_v21.csv","w",newline="") as f:
        w = csv.writer(f)
        w.writerow(["ticker","ipo","age","score_now","score_peak","improvement","peak_month",
                    "runway","saturn_pop_mo","saturn_safe","bubblish_now","bubblish_peak",
                    "bubblish_improvement","bubblish_peak_month",
                    "peak_jup_natNep","peak_nep_sun","peak_nep_mc"])
        for r in results:
            d = r["peak_details"]
            w.writerow([r["ticker"],r["ipo"],r["age"],f"{r['now']:.2f}",f"{r['peak']:.2f}",
                        f"{r['improvement']:+.2f}",r["peak_month"],r["runway"],
                        r["saturn_pop"] if r["saturn_pop"] else "",
                        "Y" if r["saturn_safe"] else "N",
                        f"{r['bubbl_now']:.2f}",f"{r['bubbl_peak']:.2f}",
                        f"{r['bubbl_improvement']:+.2f}",r["bubbl_peak_month"],
                        f"{d['jup_natNep']:.2f}",f"{d['nep_sun']:.2f}",f"{d['nep_mc']:.2f}"])
    print(f"\nExported: data/forward_bubblish_v21.csv")

if __name__ == "__main__":
    main()
