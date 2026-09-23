"""
Mundane scanner — apply v25 forward analysis to country and exchange charts.

For each chart:
  1. Compute v25 24-month forward composite trajectory (Apr 2026 -> Apr 2028)
  2. Identify peak month, improvement, exit penalty
  3. Add mundane-specific signals:
     - Saturn transit to natal Sun/MC (recession/contraction signal)
     - Jupiter on natal MC/Sun (expansion to public reputation)
     - Pluto on natal Sun (transformative pressure)
     - Eclipse hits to natal angles
  4. Rank countries/exchanges by forward outlook

Macro-regime applied with sector="INDEX" (neutral baseline, since country
charts represent a broad equity market not a single sector).
"""
import math, csv, sys, time
import statistics as st
from collections import defaultdict
from bti_test import compute_natal, transits_at, jd_of
from bti_v4 import yx
from eclipse_database import build_eclipse_database, eclipse_hits_natal
from bti_v19_empirical import COMPOUND_RULES, bucket_weight, closest_hard
from bti_v21_forward import saturn_pop_month
from bti_v23_sector_aware import sector_bucket_weight
from bti_v25_empirical import (natal_gc_amplifier, profection_bonus,
                                jupiter_station_bonus, helio_mars_jup_bottom_bonus,
                                helio_jup_sat_peak_penalty, saturn_station_penalty,
                                node_ingress_peak_penalty)
from macro_regime import macro_regime_multiplier, dignity_multiplier
from mundane_charts import COUNTRIES, EXCHANGES

START_Y, START_M = 2026, 4
MONTHS = 24

def score_v25(natal, y, m, db, sector_base, modern_sec, ipo_year):
    trans = transits_at(y, m)
    targets = {p: natal[p]["lon"] for p in ("Sun","Moon","ASC","MC") if p in natal}
    outer_orbs = {}
    for outer in ("Jupiter","Saturn","Uranus","Neptune","Pluto"):
        best = 99
        for tlon in targets.values():
            o = closest_hard(trans[outer]["lon"], tlon)
            if o < best: best = o
        outer_orbs[outer] = best
    single = sum(sector_bucket_weight(p, o, sector_base) * dignity_multiplier(p, trans[p]["lon"])
                 for p, o in outer_orbs.items())
    compound = sum(w for label, fn, w in COMPOUND_RULES if fn(outer_orbs))
    jup_natNep = closest_hard(trans["Jupiter"]["lon"], natal["Neptune"]["lon"])
    nep_sun = closest_hard(trans["Neptune"]["lon"], natal["Sun"]["lon"])
    nep_mc = closest_hard(trans["Neptune"]["lon"], natal["MC"]["lon"]) if "MC" in natal else 99
    jd_c = jd_of(y, m, 15, 12.0)
    hits = eclipse_hits_natal(db, natal, jd_c, months_back=18, months_fwd=3, max_orb=3)
    eclipse = sum((1.5 if "total" in h["eclipse_type"] else 1.0) * (3-h["orb"])/3 for h in hits)
    bubblish = 0
    if jup_natNep <= 3: bubblish += 2.5*(3-jup_natNep)/3
    elif jup_natNep <= 6: bubblish += 1.0*(6-jup_natNep)/6
    if nep_sun <= 3: bubblish += 2.0*(3-nep_sun)/3
    if nep_mc <= 3: bubblish += 1.5*(3-nep_mc)/3
    n_close = sum(1 for o in outer_orbs.values() if o <= 5)
    if n_close >= 3: bubblish += 1.0
    if 8 <= outer_orbs["Pluto"] < 12: bubblish += 1.5
    if 3 <= outer_orbs["Uranus"] < 5: bubblish += 1.2
    prof = profection_bonus(natal, y, m, ipo_year)
    jstn = jupiter_station_bonus(y, m)
    mjh = helio_mars_jup_bottom_bonus(y, m)
    pre_macro = single + compound*1.5 + eclipse*1.3 + bubblish*1.2 + prof + jstn + mjh
    macro = macro_regime_multiplier(modern_sec, y, m)
    return {
        "composite": pre_macro * macro,
        "pre_macro": pre_macro,
        "macro": macro,
        "bubblish": bubblish,
        "eclipse": eclipse,
        "outer_orbs": outer_orbs,
        # Mundane-specific aspects
        "sat_sun": closest_hard(trans["Saturn"]["lon"], natal["Sun"]["lon"]),
        "sat_mc":  closest_hard(trans["Saturn"]["lon"], natal["MC"]["lon"]) if "MC" in natal else 99,
        "jup_mc":  closest_hard(trans["Jupiter"]["lon"], natal["MC"]["lon"]) if "MC" in natal else 99,
        "jup_sun": closest_hard(trans["Jupiter"]["lon"], natal["Sun"]["lon"]),
        "plu_sun": closest_hard(trans["Pluto"]["lon"], natal["Sun"]["lon"]),
        "plu_mc":  closest_hard(trans["Pluto"]["lon"], natal["MC"]["lon"]) if "MC" in natal else 99,
        "ura_sun": closest_hard(trans["Uranus"]["lon"], natal["Sun"]["lon"]),
        "ura_mc":  closest_hard(trans["Uranus"]["lon"], natal["MC"]["lon"]) if "MC" in natal else 99,
    }

def fwd(natal, sy, sm, db, sec, mod, ipo_y, months=24):
    traj = []
    for k in range(months+1):
        y, m = yx(sy, sm, k)
        snap = score_v25(natal, y, m, db, sec, mod, ipo_y)
        snap["k"] = k; snap["y"] = y; snap["m"] = m
        traj.append(snap)
    peak = max(traj, key=lambda s: s["composite"])
    cur = traj[0]
    bpk = max(traj, key=lambda s: s["bubblish"])
    sat_pop = saturn_pop_month(natal, sy, sm, months)
    safe = sat_pop is None or sat_pop > peak["k"]+2
    hjs = helio_jup_sat_peak_penalty(peak["y"], peak["m"])
    sstn = saturn_station_penalty(peak["y"], peak["m"])
    nod = node_ingress_peak_penalty(peak["y"], peak["m"])
    # Find when saturn-sun and saturn-mc go tight in the forward window (recession risk)
    sat_sun_min = min(traj, key=lambda s: s["sat_sun"])
    sat_mc_min = min(traj, key=lambda s: s["sat_mc"])
    jup_mc_max = min(traj, key=lambda s: s["jup_mc"])  # tightest = "max benefit"
    return {
        "cur": cur, "peak": peak, "bpk": bpk, "traj": traj,
        "runway": peak["k"], "safe": safe, "sat_pop": sat_pop,
        "imp": peak["composite"] - cur["composite"],
        "exit_penalty": hjs+sstn+nod,
        "sat_sun_tight": sat_sun_min,
        "sat_mc_tight": sat_mc_min,
        "jup_mc_tight": jup_mc_max,
    }

def analyse_one(label, info, db, kind="country"):
    natal = compute_natal(info["date"])
    ipo_y = int(info["date"][:4])
    fa = fwd(natal, START_Y, START_M, db, "INDEX", "INDEX", ipo_y, MONTHS)
    gc_amp = natal_gc_amplifier(natal)
    now = fa["cur"]["composite"] * gc_amp
    peak = fa["peak"]["composite"] * gc_amp
    imp = peak - now
    return {
        "id": label, "kind": kind,
        "date": info["date"], "name": info.get("label",""),
        "etf": info.get("etf",""),
        "now": now, "peak": peak, "imp": imp,
        "gc_amp": gc_amp,
        "bub_now": fa["cur"]["bubblish"], "bub_peak": fa["bpk"]["bubblish"],
        "macro_now": fa["cur"]["macro"], "macro_peak": fa["peak"]["macro"],
        "peak_y": fa["peak"]["y"], "peak_m": fa["peak"]["m"],
        "runway": fa["runway"], "safe": fa["safe"],
        "exit_penalty": fa["exit_penalty"],
        "sat_sun_min_orb": fa["sat_sun_tight"]["sat_sun"],
        "sat_sun_min_y": fa["sat_sun_tight"]["y"],
        "sat_sun_min_m": fa["sat_sun_tight"]["m"],
        "sat_mc_min_orb": fa["sat_mc_tight"]["sat_mc"],
        "sat_mc_min_y": fa["sat_mc_tight"]["y"],
        "sat_mc_min_m": fa["sat_mc_tight"]["m"],
        "jup_mc_min_orb": fa["jup_mc_tight"]["jup_mc"],
        "jup_mc_min_y": fa["jup_mc_tight"]["y"],
        "jup_mc_min_m": fa["jup_mc_tight"]["m"],
    }

def main():
    print("Building eclipse DB...", file=sys.stderr)
    db = build_eclipse_database(1970, 2030)

    results = []
    for label, info in COUNTRIES.items():
        try:
            results.append(analyse_one(label, info, db, "country"))
        except Exception as e:
            print(f"  {label} fail: {e}", file=sys.stderr)
    for label, info in EXCHANGES.items():
        try:
            results.append(analyse_one(label, info, db, "exchange"))
        except Exception as e:
            print(f"  {label} fail: {e}", file=sys.stderr)

    # Rank
    results.sort(key=lambda r: -r["imp"])

    # Export CSV
    out = "/home/user/cyclepapa/data/mundane_v25.csv"
    with open(out, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["rank","kind","id","label","date","etf",
                    "score_now","score_peak","improvement","gc_amp",
                    "bubblish_now","bubblish_peak",
                    "peak_month","runway","saturn_safe","exit_penalty",
                    "sat_sun_min_orb","sat_sun_min_month",
                    "sat_mc_min_orb","sat_mc_min_month",
                    "jup_mc_min_orb","jup_mc_min_month"])
        for i, r in enumerate(results, 1):
            w.writerow([i, r["kind"], r["id"], r["name"], r["date"], r["etf"],
                        f"{r['now']:.2f}", f"{r['peak']:.2f}", f"{r['imp']:+.2f}",
                        f"{r['gc_amp']:.2f}",
                        f"{r['bub_now']:.2f}", f"{r['bub_peak']:.2f}",
                        f"{r['peak_y']}-{r['peak_m']:02d}", r["runway"],
                        "Y" if r["safe"] else "N", f"{r['exit_penalty']:.2f}",
                        f"{r['sat_sun_min_orb']:.2f}",
                        f"{r['sat_sun_min_y']}-{r['sat_sun_min_m']:02d}",
                        f"{r['sat_mc_min_orb']:.2f}",
                        f"{r['sat_mc_min_y']}-{r['sat_mc_min_m']:02d}",
                        f"{r['jup_mc_min_orb']:.2f}",
                        f"{r['jup_mc_min_y']}-{r['jup_mc_min_m']:02d}"])

    print(f"\n{'='*155}")
    print(f"MUNDANE v25 — Country & Exchange forward outlook (Apr 2026 -> Apr 2028)")
    print(f"{'='*155}")
    print(f"{'Rk':>3s} {'Kind':<8s} {'ID':<11s} {'Date':<11s} {'ETF':<5s} {'Now':>5s} {'Peak':>5s} "
          f"{'Δ':>5s} {'GC':>4s} {'PkMo':<8s} {'BubPk':>5s} {'mPk':>4s} {'Sf':>2s} {'-Exit':>5s}  Label")
    for i, r in enumerate(results, 1):
        # Macro multipliers come out roughly 1.0 for INDEX since macro_regime
        # only has specific sector tags. So we focus on Δ.
        print(f"{i:3d} {r['kind']:<8s} {r['id']:<11s} {r['date']:<11s} {r['etf']:<5s} "
              f"{r['now']:5.1f} {r['peak']:5.1f} {r['imp']:+5.1f} "
              f"{r['gc_amp']:4.2f} {r['peak_y']}-{r['peak_m']:02d}  "
              f"{r['bub_peak']:5.2f} {r['macro_peak']:4.2f} "
              f"{'Y' if r['safe'] else 'N':<2s} {r['exit_penalty']:5.2f}  {r['name']}")

    # ===== COUNTRIES BEARISH WATCH (Saturn arrival warning) =====
    print(f"\n{'='*155}")
    print(f"SATURN-RISK CALENDAR — when Saturn comes tight to natal Sun/MC (recession / contraction signal)")
    print(f"{'='*155}")
    print(f"  Sorted by tightness of Saturn-Sun or Saturn-MC orb in next 24 months")
    print(f"{'ID':<11s} {'Date':<11s} {'ETF':<5s} {'Sat-Sun min':<14s} {'when':<10s} {'Sat-MC min':<14s} {'when':<10s}  Label")
    risk = sorted(results, key=lambda r: min(r["sat_sun_min_orb"], r["sat_mc_min_orb"]))
    for r in risk[:15]:
        print(f"{r['id']:<11s} {r['date']:<11s} {r['etf']:<5s} "
              f"{r['sat_sun_min_orb']:5.2f}°        "
              f"{r['sat_sun_min_y']}-{r['sat_sun_min_m']:02d}    "
              f"{r['sat_mc_min_orb']:5.2f}°        "
              f"{r['sat_mc_min_y']}-{r['sat_mc_min_m']:02d}     {r['name']}")

    # ===== JUPITER-MC TIGHT (favourable national reputation expansion) =====
    print(f"\n{'='*155}")
    print(f"JUPITER-MC TIGHT WINDOWS — expansion of national/exchange reputation (bullish phase)")
    print(f"{'='*155}")
    bull = sorted(results, key=lambda r: r["jup_mc_min_orb"])
    print(f"{'ID':<11s} {'Date':<11s} {'ETF':<5s} {'Jup-MC min':<14s} {'when':<10s}  Label")
    for r in bull[:15]:
        print(f"{r['id']:<11s} {r['date']:<11s} {r['etf']:<5s} "
              f"{r['jup_mc_min_orb']:5.2f}°        "
              f"{r['jup_mc_min_y']}-{r['jup_mc_min_m']:02d}     {r['name']}")

    # ===== ETF IMPLICATIONS =====
    print(f"\n{'='*155}")
    print(f"EQUITY-MARKET IMPLICATIONS — top 15 country/exchange ETF candidates by forward improvement")
    print(f"{'='*155}")
    bull_imp = [r for r in results if r["safe"] and r["imp"] >= 5.0][:15]
    print(f"  Filter: Saturn-safe AND improvement >= 5.0")
    print(f"{'ETF':<6s} {'ID':<11s} {'Score Now':>10s} {'Peak':>6s} {'Δ':>6s}  Why")
    for r in bull_imp:
        why = []
        if r["jup_mc_min_orb"] <= 3: why.append(f"Jup-MC {r['jup_mc_min_orb']:.1f}° in {r['jup_mc_min_y']}-{r['jup_mc_min_m']:02d}")
        if r["bub_peak"] >= 3.0: why.append(f"bubblish {r['bub_peak']:.1f}")
        if r["gc_amp"] > 1.0: why.append("GC")
        if not why: why.append("composite uplift")
        print(f"{r['etf']:<6s} {r['id']:<11s} {r['now']:>9.1f}  {r['peak']:>5.1f} {r['imp']:>+5.1f}  "
              f"{', '.join(why)}")

    # ===== BEARISH SET =====
    print(f"\n{'='*155}")
    print(f"BEARISH WATCHLIST — Saturn arriving on Sun OR MC ≤3° within 24 months")
    print(f"{'='*155}")
    bear = [r for r in results if min(r["sat_sun_min_orb"], r["sat_mc_min_orb"]) <= 3]
    print(f"{'ETF':<6s} {'ID':<11s} {'Sat-Sun':<10s} {'when':<10s} {'Sat-MC':<10s} {'when':<10s}  Label")
    for r in bear:
        print(f"{r['etf']:<6s} {r['id']:<11s} {r['sat_sun_min_orb']:>5.2f}°    "
              f"{r['sat_sun_min_y']}-{r['sat_sun_min_m']:02d}    "
              f"{r['sat_mc_min_orb']:>5.2f}°    "
              f"{r['sat_mc_min_y']}-{r['sat_mc_min_m']:02d}    {r['name']}")

    print(f"\nExported {out}")

if __name__ == "__main__":
    main()
