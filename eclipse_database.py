"""
Full Saros-series eclipse database 1970-2035.

Uses Swiss Ephemeris iteratively to find every solar and lunar eclipse
in the window, extracts:
  - Exact date/time
  - Zodiacal longitude (Sun for solar, Moon for lunar — same as Sun±180)
  - Eclipse type (total / annular / partial / hybrid)
  - Magnitude (obscuration)
  - Saros series number (18.03-year cycle identifier)

Implements Kate Silas's eclipse-to-IPO-chart technique:
  - For each eclipse, check if its longitude hits natal sensitive points
  - Count eclipse hits within ±12 months of a bottom
  - Compare to quiet-month baseline
"""
import math, statistics as st
from collections import defaultdict
from datetime import datetime, timedelta
import swisseph as swe

def build_eclipse_database(start_year=1970, end_year=2035):
    """Generate all solar + lunar eclipses with metadata."""
    eclipses = []
    jd_start = swe.julday(start_year, 1, 1, 0)
    jd_end = swe.julday(end_year, 12, 31, 23.99)

    # Solar eclipses
    jd = jd_start
    while jd < jd_end:
        try:
            res = swe.sol_eclipse_when_glob(jd, 0)
            if not res or not res[1]:
                jd += 180; continue
            jd_ecl = res[1][0]
            if jd_ecl > jd_end: break
            flags = res[0]
            # Determine type
            if flags & swe.ECL_TOTAL: etype = "total_solar"
            elif flags & swe.ECL_ANNULAR: etype = "annular_solar"
            elif flags & swe.ECL_ANNULAR_TOTAL: etype = "hybrid_solar"
            elif flags & swe.ECL_PARTIAL: etype = "partial_solar"
            else: etype = "solar"
            # Sun longitude at eclipse moment = solar eclipse longitude
            sun_res = swe.calc_ut(jd_ecl, swe.SUN)
            elon = sun_res[0][0] % 360
            moon_res = swe.calc_ut(jd_ecl, swe.MOON)
            mlon = moon_res[0][0] % 360
            y, m, d, h = swe.revjul(jd_ecl)
            eclipses.append({
                "jd": jd_ecl, "date": f"{y:04d}-{m:02d}-{d:02d}",
                "type": etype, "lon": elon, "moon_lon": mlon,
                "magnitude": res[1][2] if len(res[1]) > 2 else 1.0,
            })
            jd = jd_ecl + 20  # next eclipse at least ~20 days later
        except Exception as e:
            jd += 180

    # Lunar eclipses
    jd = jd_start
    while jd < jd_end:
        try:
            res = swe.lun_eclipse_when(jd, 0, 0)
            if not res or not res[1]:
                jd += 180; continue
            jd_ecl = res[1][0]
            if jd_ecl > jd_end: break
            flags = res[0]
            if flags & swe.ECL_TOTAL: etype = "total_lunar"
            elif flags & swe.ECL_PARTIAL: etype = "partial_lunar"
            elif flags & swe.ECL_PENUMBRAL: etype = "penumbral_lunar"
            else: etype = "lunar"
            moon_res = swe.calc_ut(jd_ecl, swe.MOON)
            mlon = moon_res[0][0] % 360
            sun_res = swe.calc_ut(jd_ecl, swe.SUN)
            slon = sun_res[0][0] % 360
            y, m, d, h = swe.revjul(jd_ecl)
            eclipses.append({
                "jd": jd_ecl, "date": f"{y:04d}-{m:02d}-{d:02d}",
                "type": etype, "lon": mlon, "moon_lon": mlon, "sun_lon": slon,
                "magnitude": res[1][0] if len(res[1]) > 0 else 1.0,
            })
            jd = jd_ecl + 15
        except Exception as e:
            jd += 180
    eclipses.sort(key=lambda e: e["jd"])
    return eclipses

def orb(a, b):
    d = abs((a - b) % 360)
    return min(d, 360 - d)

def eclipse_hits_natal(eclipses, natal, jd_center, months_back=12, months_fwd=6, max_orb=3):
    """Find eclipses within the time window that hit natal sensitive points.
    Silas's technique: eclipses to IPO-chart degrees drive big moves.
    Returns list of (eclipse, natal_body, orb).
    """
    jd_back = jd_center - months_back * 30.5
    jd_fwd = jd_center + months_fwd * 30.5
    hits = []
    natal_targets = {}
    for p in ("Sun","Moon","Mercury","Venus","Mars","Jupiter","Saturn","Uranus","Neptune","Pluto","ASC","MC"):
        if p in natal:
            natal_targets[p] = natal[p]["lon"]
    for e in eclipses:
        if e["jd"] < jd_back or e["jd"] > jd_fwd: continue
        for body, blon in natal_targets.items():
            o = orb(e["lon"], blon)
            # Eclipses use conjunction only (traditional)
            if o <= max_orb:
                days_offset = (e["jd"] - jd_center)
                hits.append({
                    "eclipse_date": e["date"], "eclipse_type": e["type"],
                    "eclipse_lon": e["lon"],
                    "natal_body": body, "orb": o,
                    "days_offset": days_offset,
                })
            # Also check opposition for lunar eclipses (Sun-Moon axis)
            if "lunar" in e["type"]:
                o_opp = orb((e["lon"] + 180) % 360, blon)
                if o_opp <= max_orb:
                    hits.append({
                        "eclipse_date": e["date"], "eclipse_type": e["type"],
                        "eclipse_lon": e["lon"],
                        "natal_body": body, "orb": o_opp,
                        "days_offset": (e["jd"] - jd_center),
                        "aspect": "opp"
                    })
    return hits

if __name__ == "__main__":
    import sys, time
    print("Building eclipse database 1970-2035...", file=sys.stderr)
    t0 = time.time()
    db = build_eclipse_database(1970, 2035)
    print(f"Generated {len(db)} eclipses in {time.time()-t0:.1f}s", file=sys.stderr)

    # Save
    import csv
    with open("/home/user/cyclepapa/data/eclipse_db_1970_2035.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["jd","date","type","longitude","magnitude"])
        for e in db:
            w.writerow([f"{e['jd']:.3f}", e["date"], e["type"], f"{e['lon']:.2f}", f"{e['magnitude']:.3f}"])
    print(f"Saved to data/eclipse_db_1970_2035.csv", file=sys.stderr)

    # Distribution by type
    from collections import Counter
    types = Counter(e["type"] for e in db)
    print(f"\nEclipse type distribution:")
    for t, n in types.most_common():
        print(f"  {t:<18s} {n}")

    # Sample recent eclipses
    print(f"\nRecent eclipses (2022-2026):")
    for e in db:
        if "2022" <= e["date"][:4] <= "2026":
            print(f"  {e['date']}  {e['type']:<18s}  lon={e['lon']:6.2f}° (sign {int(e['lon']//30)})  mag={e['magnitude']:.2f}")

    # Now test on parabolic corpus
    print(f"\n{'='*100}")
    print("SILAS ECLIPSE-TO-NATAL TEST on 152-corpus")
    print(f"{'='*100}")
    from bti_test import compute_natal, jd_of
    from parabolic_corpus import PARABOLIC_BOTTOMS

    # For each bottom, count eclipse hits in [-12, +6] month window
    by_band = defaultdict(lambda: {"hits":[], "eclipses_in_window":[], "bot_hit_total":0})
    for tk, ipo, bot, top, mult, speed, note in PARABOLIC_BOTTOMS:
        try:
            natal = compute_natal(ipo)
            jd_b = jd_of(bot[0], bot[1], 15, 12.0)
            hits = eclipse_hits_natal(db, natal, jd_b, months_back=12, months_fwd=6, max_orb=3)
            band = "mega" if mult>=100 else "big" if mult>=30 else "mid" if mult>=10 else "modest"
            by_band[band]["hits"].append(len(hits))
            by_band[band]["bot_hit_total"] += 1 if hits else 0
        except: pass
    print(f"\n{'Band':<10s} {'n':>4s}  {'mean_hits':>10s}  {'max_hits':>9s}  {'%_with_hits':>12s}")
    for b in ("mega","big","mid","modest"):
        d = by_band[b]
        if d["hits"]:
            print(f"{b:<10s} {len(d['hits']):>4d}  {st.mean(d['hits']):10.2f}  {max(d['hits']):9d}  {100*d['bot_hit_total']/len(d['hits']):11.1f}%")

    # Quiet baseline
    from bti_v4 import yx
    quiet_hits = []
    quiet_has_hit = 0
    for tk, ipo, bot, top, mult, speed, note in PARABOLIC_BOTTOMS:
        try:
            natal = compute_natal(ipo)
            for off in (-36, -24, 24, 36):
                y, m = yx(bot[0], bot[1], off)
                jd_q = jd_of(y, m, 15, 12.0)
                hits = eclipse_hits_natal(db, natal, jd_q, months_back=12, months_fwd=6, max_orb=3)
                quiet_hits.append(len(hits))
                if hits: quiet_has_hit += 1
        except: pass
    print(f"{'QUIET':<10s} {len(quiet_hits):>4d}  {st.mean(quiet_hits):10.2f}  {max(quiet_hits):9d}  {100*quiet_has_hit/len(quiet_hits):11.1f}%")

    # Now: specific eclipse-type breakdown — total/annular solar most powerful per Silas
    print(f"\n{'='*100}")
    print("ECLIPSE TYPE BREAKDOWN by band (total/annular solar = strongest per tradition)")
    print(f"{'='*100}")
    type_band = defaultdict(lambda: defaultdict(int))
    for tk, ipo, bot, top, mult, speed, note in PARABOLIC_BOTTOMS:
        try:
            natal = compute_natal(ipo)
            jd_b = jd_of(bot[0], bot[1], 15, 12.0)
            hits = eclipse_hits_natal(db, natal, jd_b, months_back=12, months_fwd=6, max_orb=3)
            band = "mega" if mult>=100 else "big" if mult>=30 else "mid" if mult>=10 else "modest"
            for h in hits:
                type_band[band][h["eclipse_type"]] += 1
        except: pass
    print(f"{'Band':<10s} {'total_s':>7s} {'annul_s':>7s} {'partial_s':>9s} {'total_l':>7s} {'partial_l':>9s} {'penum_l':>7s}")
    for b in ("mega","big","mid","modest"):
        d = type_band[b]
        print(f"{b:<10s} {d['total_solar']:>7d} {d['annular_solar']:>7d} {d['partial_solar']:>9d} {d['total_lunar']:>7d} {d['partial_lunar']:>9d} {d['penumbral_lunar']:>7d}")

    # Tight-orb (< 1°) special check — Silas says these produce biggest moves
    print(f"\n{'='*100}")
    print("TIGHT-ORB eclipse hits (< 1° orb) = 'Silas 300-500% move' candidates")
    print(f"{'='*100}")
    for tk, ipo, bot, top, mult, speed, note in PARABOLIC_BOTTOMS:
        try:
            natal = compute_natal(ipo)
            jd_b = jd_of(bot[0], bot[1], 15, 12.0)
            hits = eclipse_hits_natal(db, natal, jd_b, months_back=12, months_fwd=6, max_orb=1.0)
            if hits and mult >= 10:
                band = "mega" if mult >= 100 else "big" if mult >= 30 else "mid"
                for h in hits:
                    print(f"  {tk:<8s} mult={mult:5d}× {band:<6s} bot={bot[0]}-{bot[1]:02d}  eclipse {h['eclipse_date']} {h['eclipse_type']:<16s} hits {h['natal_body']:<5s} orb {h['orb']:.2f}°  offset {h['days_offset']:.0f}d")
        except: pass
