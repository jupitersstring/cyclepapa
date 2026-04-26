"""
Multi-period backtest of v25 — runs the framework as of multiple
historical start dates and measures actual outcomes over each
24-month forward window. The 2022 bear-market period is the real test.

Periods:
  Apr 2021 -> Apr 2023  (covers 2022 crash)
  Apr 2022 -> Apr 2024  (covers 2022 trough + 2023 recovery)
  Apr 2023 -> Apr 2025  (2023-24 AI bull leg)
  Apr 2024 -> Apr 2026  (already run — this is the headline)
"""
import math, csv, sys, time, os, subprocess, json
from datetime import datetime, timezone
import statistics as st
from bti_test import compute_natal, transits_at, jd_of
from bti_v4 import yx
from eclipse_database import build_eclipse_database, eclipse_hits_natal
from bti_v19_empirical import COMPOUND_RULES, bucket_weight, closest_hard
from bti_v21_forward import saturn_pop_month
from bti_v23_sector_aware import get_sector, sector_bucket_weight
from bti_v24_macro import modern_sector_of
from bti_v25_empirical import (natal_gc_amplifier, profection_bonus,
                                jupiter_station_bonus, helio_mars_jup_bottom_bonus,
                                helio_jup_sat_peak_penalty, saturn_station_penalty,
                                node_ingress_peak_penalty)
from macro_regime import macro_regime_multiplier, dignity_multiplier
from filter_tradeable_v22 import CURATED_ACTIVE, BAD_NAME, BAD_TICKER

def keep(nm, tk, src):
    if not nm or not tk: return False
    if BAD_NAME.search(nm) or BAD_TICKER.search(tk): return False
    if len(tk) > 5: return False
    return src == "SP500" or tk in CURATED_ACTIVE

def score_v25(natal, y, m, db, sec_base, mod_sec, ipo_year):
    trans = transits_at(y, m)
    targets = {p: natal[p]["lon"] for p in ("Sun","Moon","ASC","MC") if p in natal}
    outer_orbs = {}
    for outer in ("Jupiter","Saturn","Uranus","Neptune","Pluto"):
        best = 99
        for tlon in targets.values():
            o = closest_hard(trans[outer]["lon"], tlon)
            if o < best: best = o
        outer_orbs[outer] = best
    single = sum(sector_bucket_weight(p, o, sec_base) * dignity_multiplier(p, trans[p]["lon"])
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
    macro = macro_regime_multiplier(mod_sec, y, m)
    return pre_macro * macro, bubblish

def fwd(natal, sy, sm, db, sec, mod, ipo_y, months=24):
    traj = []
    for k in range(months+1):
        y, m = yx(sy, sm, k)
        sc, bb = score_v25(natal, y, m, db, sec, mod, ipo_y)
        traj.append({"k":k,"y":y,"m":m,"composite":sc,"bubblish":bb})
    peak = max(traj, key=lambda s:s["composite"])
    cur = traj[0]
    bpk = max(traj, key=lambda s:s["bubblish"])
    sat_pop = saturn_pop_month(natal, sy, sm, months)
    safe = sat_pop is None or sat_pop > peak["k"]+2
    hjs = helio_jup_sat_peak_penalty(peak["y"], peak["m"])
    sstn = saturn_station_penalty(peak["y"], peak["m"])
    nod = node_ingress_peak_penalty(peak["y"], peak["m"])
    return {"cur":cur,"peak":peak,"bpk":bpk,"runway":peak["k"],"safe":safe,
            "imp":peak["composite"]-cur["composite"],
            "exit_penalty":hjs+sstn+nod}

def fetch_yahoo(tk, sd, ed):
    p1=int(sd.replace(tzinfo=timezone.utc).timestamp())
    p2=int(ed.replace(tzinfo=timezone.utc).timestamp())
    url=f"https://query1.finance.yahoo.com/v8/finance/chart/{tk}?period1={p1}&period2={p2}&interval=1d"
    try:
        out=subprocess.run(["curl","-sL","-H","User-Agent: Mozilla/5.0","-m","20",url],
                            capture_output=True,text=True,timeout=25).stdout
        j=json.loads(out)
        r=j.get("chart",{}).get("result")
        if not r: return []
        ts=r[0]["timestamp"]; cs=r[0]["indicators"]["quote"][0]["close"]
        return [(datetime.utcfromtimestamp(t).strftime("%Y-%m-%d"),c) for t,c in zip(ts,cs) if c]
    except: return []

def run_period(sy, sm, ey, em, db):
    """Run v25 forward as of (sy,sm), measure prices through (ey,em). Returns top 50 with realized."""
    seeds = []
    with open("/home/user/cyclepapa/data/universe_bti_v20.csv") as f:
        for r in csv.DictReader(f):
            tk = (r.get("ticker") or "").strip().upper()
            ipo = (r.get("ipo") or "").strip()
            nm = (r.get("name") or "").strip()
            src = (r.get("source") or "").strip()
            if not tk or not ipo or len(ipo)<10: continue
            try: y = int(ipo[:4])
            except: continue
            age = sy - y
            if not (1 <= age <= 40): continue
            if not keep(nm, tk, src): continue
            seeds.append({"tk":tk,"ipo":ipo,"name":nm,"src":src,"age":age})
    seen=set(); unique=[]
    for s in seeds:
        k=(s["tk"],s["ipo"])
        if k in seen: continue
        seen.add(k); unique.append(s)

    rows = []
    t0 = time.time()
    for i, s in enumerate(unique):
        sec = get_sector(s["tk"], s["src"])
        mod = modern_sector_of(s["tk"], sec)
        ipo_year = int(s["ipo"][:4])
        try:
            natal = compute_natal(s["ipo"])
            gc_amp = natal_gc_amplifier(natal)
            fa = fwd(natal, sy, sm, db, sec, mod, ipo_year, 24)
            now = fa["cur"]["composite"] * gc_amp
            peak = fa["peak"]["composite"] * gc_amp
            imp = peak - now
            bpk = fa["bpk"]["bubblish"]
            run = fa["runway"]
            if run < 1: continue
            if imp < 5.0: continue
            if bpk < 2.0: continue
            if now >= 25.0: continue
            if not fa["safe"]: continue
            rb = 1.0 if 3 <= run <= 12 else 0.7
            base_asym = (imp**0.9) * (bpk**1.0) * rb / ((now+3)**0.5)
            asym = base_asym * max(0.4, 1 - fa["exit_penalty"]/5.0)
            rows.append({"tk":s["tk"],"name":s["name"],"sector":sec,"modern":mod,
                         "ipo":s["ipo"],"age":s["age"],"now":now,"peak":peak,
                         "imp":imp,"bpk":bpk,"runway":run,"asym":asym,
                         "peak_y":fa["peak"]["y"],"peak_m":fa["peak"]["m"]})
        except: continue
    rows.sort(key=lambda r: -r["asym"])
    print(f"  Period {sy}-{sm:02d}: scanned {len(unique)} kept {len(rows)} in {time.time()-t0:.0f}s", file=sys.stderr)
    # Take top 50 — fetch prices
    start_dt = datetime(sy, sm, 1)
    end_dt = datetime(ey, em, 22)
    spy = fetch_yahoo("SPY", start_dt, end_dt)
    spy_ret = (spy[-1][1]/spy[0][1]-1)*100 if spy else 0
    spy_max = (max(c for _,c in spy)/spy[0][1]-1)*100 if spy else 0
    results = []
    for i, r in enumerate(rows[:50]):
        cache=f"/home/user/cyclepapa/data/prices/{r['tk']}.csv"
        prices = []
        if os.path.exists(cache):
            with open(cache) as f:
                next(f)
                for line in f:
                    p=line.strip().split(",")
                    if len(p)==2:
                        try: prices.append((p[0],float(p[1])))
                        except: pass
        else:
            prices = fetch_yahoo(r["tk"], datetime(2018,1,1), datetime(2026,5,1))
            if prices:
                with open(cache,"w") as f:
                    f.write("date,close\n")
                    for d,c in prices: f.write(f"{d},{c:.4f}\n")
            time.sleep(0.2)
        if not prices: continue
        prices_w = [(d,c) for d,c in prices if start_dt.strftime("%Y-%m-%d")<=d<=end_dt.strftime("%Y-%m-%d")]
        if len(prices_w) < 50: continue
        s_p, e_p = prices_w[0][1], prices_w[-1][1]
        m_p = max(c for _,c in prices_w)
        m_d = next(d for d,c in prices_w if c == m_p)
        results.append({"rank":i+1,**r,
                        "p_start":s_p,"p_end":e_p,"p_max":m_p,
                        "ret":(e_p/s_p-1)*100,"max_ret":(m_p/s_p-1)*100,
                        "max_date":m_d,"spy_ret":spy_ret,"spy_max":spy_max})
    return results, spy_ret, spy_max

def main():
    print("Building eclipse DB (1970-2027)...", file=sys.stderr)
    db = build_eclipse_database(1970, 2027)
    periods = [
        (2021, 4, 2023, 4),
        (2022, 4, 2024, 4),
        (2023, 4, 2025, 4),
    ]
    all_results = []
    for sy, sm, ey, em in periods:
        print(f"\n  Running {sy}-{sm:02d} -> {ey}-{em:02d}...", file=sys.stderr)
        res, spy_r, spy_m = run_period(sy, sm, ey, em, db)
        for r in res: r["period"] = f"{sy}-{sm:02d}"
        all_results.append({"period":f"{sy}-{sm:02d}","results":res,"spy_ret":spy_r,"spy_max":spy_m})

    # Add Apr 2024 from existing file
    print(f"\n  Loading Apr 2024 results from prior run...", file=sys.stderr)
    apr24 = []
    with open("/home/user/cyclepapa/data/v25_backtest_apr2024.csv") as f:
        for r in csv.DictReader(f):
            r["period"]="2024-04"
            r["ret"] = float(r["return_pct"])
            r["max_ret"] = float(r["max_return_pct"])
            r["max_date"] = r["actual_max_date"]
            r["peak_y"], r["peak_m"] = int(r["predicted_peak"][:4]), int(r["predicted_peak"][5:7])
            r["asym"] = float(r["asym"])
            r["rank"] = int(r["rank"])
            r["modern"] = r["modern"]
            apr24.append(r)
    all_results.append({"period":"2024-04","results":apr24,"spy_ret":34.8,"spy_max":36.0})

    # ===== AGGREGATE =====
    print(f"\n{'='*150}")
    print(f" MULTI-PERIOD BACKTEST RESULTS (top-50 v25 picks per period)")
    print(f"{'='*150}")
    print(f"{'Period':<10s} {'n':>4s}  {'Mean Ret':>9s} {'Med Ret':>8s}  {'Mean Peak':>10s} {'Med Peak':>9s}  "
          f"{'Hit≥50%':>8s} {'Hit≥100%':>9s}  {'SPY Ret':>8s} {'SPY Pk':>7s}  {'Excess Pk':>9s} {'BeatSPY':>8s}")
    grand = []
    for ar in all_results:
        rs = [r["ret"] for r in ar["results"]]
        ms = [r["max_ret"] for r in ar["results"]]
        spy_r, spy_m = ar["spy_ret"], ar["spy_max"]
        if not rs: continue
        h50 = 100*sum(1 for v in ms if v>=50)/len(ms)
        h100 = 100*sum(1 for v in ms if v>=100)/len(ms)
        beat_spy = 100*sum(1 for r in rs if r > spy_r)/len(rs)
        excess_pk = st.mean(ms) - spy_m
        print(f"{ar['period']:<10s} {len(rs):>4d}  {st.mean(rs):>+8.1f}% {st.median(rs):>+7.1f}%  "
              f"{st.mean(ms):>+9.1f}% {st.median(ms):>+8.1f}%  "
              f"{h50:>7.0f}% {h100:>8.0f}%  {spy_r:>+7.1f}% {spy_m:>+6.1f}%  "
              f"{excess_pk:>+8.1f}pp {beat_spy:>7.0f}%")
        grand.extend(ar["results"])

    # Pooled across all periods
    g_ret = [r["ret"] for r in grand]
    g_max = [r["max_ret"] for r in grand]
    g_spy_max = [ar["spy_max"] for ar in all_results for _ in ar["results"]]
    g_excess = [r["max_ret"] - sm for r, sm in zip(grand, g_spy_max)]
    print(f"\n{'POOLED':<10s} {len(g_ret):>4d}  {st.mean(g_ret):>+8.1f}% {st.median(g_ret):>+7.1f}%  "
          f"{st.mean(g_max):>+9.1f}% {st.median(g_max):>+8.1f}%  "
          f"{100*sum(1 for v in g_max if v>=50)/len(g_max):>7.0f}% "
          f"{100*sum(1 for v in g_max if v>=100)/len(g_max):>8.0f}%")
    print(f"{'POOLED EXCESS over SPY peak':<35s}: mean {st.mean(g_excess):+.1f}pp  median {st.median(g_excess):+.1f}pp")

    # Quintile stratification across pooled data
    print(f"\n{'='*100}")
    print(f" POOLED QUINTILE STRATIFICATION (sort each period by asym, bucket, then aggregate)")
    print(f"{'='*100}")
    bucketed = [[] for _ in range(5)]
    for ar in all_results:
        n = len(ar["results"])
        if n < 5: continue
        q = n // 5
        for i, r in enumerate(ar["results"]):
            qi = min(4, i // q)
            bucketed[qi].append(r)
    print(f"{'Quintile':<8s} {'n':>4s}  {'Mean Ret':>9s} {'Med Ret':>8s}  {'Mean Peak':>10s} {'Med Peak':>9s}  Hit≥50% Hit≥100%")
    for i, b in enumerate(bucketed):
        if not b: continue
        rs = [r["ret"] for r in b]
        ms = [r["max_ret"] for r in b]
        h50 = 100*sum(1 for v in ms if v>=50)/len(ms)
        h100 = 100*sum(1 for v in ms if v>=100)/len(ms)
        print(f"Q{i+1}      {len(b):>4d}  {st.mean(rs):>+8.1f}% {st.median(rs):>+7.1f}%  "
              f"{st.mean(ms):>+9.1f}% {st.median(ms):>+8.1f}%  "
              f"{h50:>7.0f}% {h100:>8.0f}%")

    # Peak-month accuracy across pooled
    print(f"\n{'='*100}\n PEAK-MONTH FORECAST ACCURACY across all periods\n{'='*100}")
    errs = []
    for r in grand:
        if r["max_ret"] < 50: continue
        try:
            pred = datetime.strptime(f"{r['peak_y']}-{r['peak_m']:02d}-15","%Y-%m-%d")
            actual = datetime.strptime(r["max_date"],"%Y-%m-%d")
            errs.append(abs((actual-pred).days))
        except: continue
    print(f"  {len(errs)} picks with peak return >=+50% pooled")
    if errs:
        print(f"  Median |days off|: {st.median(errs):.0f} days")
        print(f"  Mean   |days off|: {st.mean(errs):.0f} days")
        print(f"  Within  60d: {sum(1 for d in errs if d<=60):>3d}/{len(errs)} ({100*sum(1 for d in errs if d<=60)/len(errs):.0f}%)")
        print(f"  Within  90d: {sum(1 for d in errs if d<=90):>3d}/{len(errs)} ({100*sum(1 for d in errs if d<=90)/len(errs):.0f}%)")
        print(f"  Within 180d: {sum(1 for d in errs if d<=180):>3d}/{len(errs)} ({100*sum(1 for d in errs if d<=180)/len(errs):.0f}%)")

    # Export
    with open("/home/user/cyclepapa/data/v25_multiperiod.csv","w",newline="") as f:
        w = csv.writer(f)
        w.writerow(["period","rank","ticker","name","modern","ipo","peak_predicted",
                    "asym","return_pct","max_return_pct","max_date"])
        for r in grand:
            tk = r.get("tk") or r.get("ticker","")
            nm = r.get("name","")
            mod = r.get("modern","")
            ipo = r.get("ipo","")
            pred = f"{r['peak_y']}-{r['peak_m']:02d}" if 'peak_y' in r else r.get("predicted_peak","")
            w.writerow([r["period"], r["rank"], tk, nm, mod, ipo, pred,
                        f"{r['asym']:.2f}",f"{r['ret']:+.1f}",f"{r['max_ret']:+.1f}",r["max_date"]])

if __name__ == "__main__":
    main()
