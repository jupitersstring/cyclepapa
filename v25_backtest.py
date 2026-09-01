"""
v25 BACKTEST — run the framework as of a PAST date, then measure
actual performance over the subsequent forward window.

Procedure:
  1. Set start = April 2024 (2 years ago).
  2. Run v25 forward analysis on the universe AS IF it were April 2024.
  3. Take top-N candidates by asymmetry.
  4. Fetch each one's actual price Apr 2024 -> Apr 2026.
  5. Compute return, max-drawdown-from-peak, hit rates vs SPY benchmark.
  6. Report aggregate stats for top-N vs random baseline.

This is the genuine "did the screener find big moves before they happened"
test.  Two-year forward window = enough time to capture even slow rallies.
"""
import math, csv, sys, time, os, subprocess, json
from datetime import datetime, timezone, timedelta
import swisseph as swe
from bti_test import compute_natal, transits_at, jd_of
from bti_v4 import yx
from eclipse_database import build_eclipse_database, eclipse_hits_natal
from bti_v19_empirical import SINGLE_PLANET_WEIGHTS, COMPOUND_RULES, bucket_weight, closest_hard
from bti_v21_forward import saturn_pop_month
from bti_v23_sector_aware import SECTOR_WEIGHTS, get_sector, sector_bucket_weight
from bti_v24_macro import MODERN_SECTOR, modern_sector_of
from bti_v25_empirical import (natal_gc_amplifier, profection_bonus,
                                jupiter_station_bonus, helio_mars_jup_bottom_bonus,
                                helio_jup_sat_peak_penalty, saturn_station_penalty,
                                node_ingress_peak_penalty)
from macro_regime import macro_regime_multiplier, dignity_multiplier
from filter_tradeable_v22 import CURATED_ACTIVE, BAD_NAME, BAD_TICKER

START_Y, START_M = 2024, 4   # backtest start
END_Y, END_M = 2026, 4       # backtest end (24 months forward)
MONTHS = 24

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
    single_score = 0
    for p, o in outer_orbs.items():
        w = sector_bucket_weight(p, o, sec_base)
        dig = dignity_multiplier(p, trans[p]["lon"])
        single_score += w * dig
    compound = sum(w for label, fn, w in COMPOUND_RULES if fn(outer_orbs))
    jup_natNep = closest_hard(trans["Jupiter"]["lon"], natal["Neptune"]["lon"])
    nep_sun = closest_hard(trans["Neptune"]["lon"], natal["Sun"]["lon"])
    nep_mc = closest_hard(trans["Neptune"]["lon"], natal["MC"]["lon"]) if "MC" in natal else 99
    jd_c = jd_of(y, m, 15, 12.0)
    hits = eclipse_hits_natal(db, natal, jd_c, months_back=18, months_fwd=3, max_orb=3)
    eclipse = 0
    for h in hits:
        tw = 1.5 if "total" in h["eclipse_type"] else (1.0 if "partial" in h["eclipse_type"] or "annular" in h["eclipse_type"] else 0.5)
        eclipse += tw * (3 - h["orb"]) / 3
    bubblish = 0
    if jup_natNep <= 3: bubblish += 2.5 * (3 - jup_natNep) / 3
    elif jup_natNep <= 6: bubblish += 1.0 * (6 - jup_natNep) / 6
    if nep_sun <= 3: bubblish += 2.0 * (3 - nep_sun) / 3
    if nep_mc <= 3: bubblish += 1.5 * (3 - nep_mc) / 3
    n_close = sum(1 for o in outer_orbs.values() if o <= 5)
    if n_close >= 3: bubblish += 1.0
    if 8 <= outer_orbs["Pluto"] < 12: bubblish += 1.5
    if 3 <= outer_orbs["Uranus"] < 5: bubblish += 1.2
    prof = profection_bonus(natal, y, m, ipo_year)
    jstn = jupiter_station_bonus(y, m)
    mjh = helio_mars_jup_bottom_bonus(y, m)
    pre_macro = (single_score + compound * 1.5 + eclipse * 1.3
                 + bubblish * 1.2 + prof + jstn + mjh)
    macro = macro_regime_multiplier(mod_sec, y, m)
    return pre_macro * macro, bubblish, outer_orbs, jup_natNep, nep_sun, nep_mc

def forward_v25_at(natal, sy, sm, db, sec_base, mod_sec, ipo_year, months=24):
    traj = []
    for k in range(0, months+1):
        y, m = yx(sy, sm, k)
        score, bubbl, _, jn, ns, nm = score_v25(natal, y, m, db, sec_base, mod_sec, ipo_year)
        traj.append({"k":k,"y":y,"m":m,"composite":score,"bubblish":bubbl,
                     "jup_natNep":jn,"nep_sun":ns,"nep_mc":nm})
    peak = max(traj, key=lambda s:s["composite"])
    cur = traj[0]
    bpk = max(traj, key=lambda s:s["bubblish"])
    sat_pop = saturn_pop_month(natal, sy, sm, months)
    runway = peak["k"]
    safe = sat_pop is None or sat_pop > runway+2
    hjs = helio_jup_sat_peak_penalty(peak["y"], peak["m"])
    sstn = saturn_station_penalty(peak["y"], peak["m"])
    nod = node_ingress_peak_penalty(peak["y"], peak["m"])
    return {"cur":cur,"peak":peak,"bpk":bpk,
            "runway":runway,"safe":safe,"sat_pop":sat_pop,
            "imp":peak["composite"]-cur["composite"],
            "exit_penalty":hjs+sstn+nod}

def fetch_prices_yahoo(tk, start_dt, end_dt):
    p1 = int(start_dt.replace(tzinfo=timezone.utc).timestamp())
    p2 = int(end_dt.replace(tzinfo=timezone.utc).timestamp())
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{tk}?period1={p1}&period2={p2}&interval=1d"
    try:
        out = subprocess.run(["curl","-sL","-H","User-Agent: Mozilla/5.0 (X11)","--connect-timeout","10","-m","20",url],
                              capture_output=True, text=True, timeout=25).stdout
        j = json.loads(out)
        r = j.get("chart",{}).get("result")
        if not r: return []
        ts = r[0]["timestamp"]; closes = r[0]["indicators"]["quote"][0]["close"]
        out_data = []
        for t,c in zip(ts, closes):
            if c is None: continue
            d = datetime.utcfromtimestamp(t).strftime("%Y-%m-%d")
            out_data.append((d, c))
        return out_data
    except: return []

def main():
    print(f"Backtest: scoring as of {START_Y}-{START_M:02d}, measuring actual prices through {END_Y}-{END_M:02d}", file=sys.stderr)
    print("Building eclipse DB...", file=sys.stderr)
    db = build_eclipse_database(1970, 2030)

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
            age_at_test = START_Y - y
            if not (1 <= age_at_test <= 40): continue
            # Tradeable filter
            if BAD_NAME.search(nm) or BAD_TICKER.search(tk): continue
            if len(tk)>5: continue
            if not (src=="SP500" or tk in CURATED_ACTIVE): continue
            seeds.append({"tk":tk,"ipo":ipo,"name":nm,"src":src,"age":age_at_test})
    seen=set(); unique=[]
    for s in seeds:
        k=(s["tk"],s["ipo"])
        if k in seen: continue
        seen.add(k); unique.append(s)
    print(f"Tradeable universe at backtest date: {len(unique)}", file=sys.stderr)

    t0 = time.time()
    rows = []
    for i, s in enumerate(unique):
        if i and i%50==0: print(f"  {i}/{len(unique)}  {time.time()-t0:.0f}s kept={len(rows)}", file=sys.stderr)
        sec_base = get_sector(s["tk"], s["src"])
        mod_sec = modern_sector_of(s["tk"], sec_base)
        ipo_year = int(s["ipo"][:4])
        try:
            natal = compute_natal(s["ipo"])
            gc_amp = natal_gc_amplifier(natal)
            fa = forward_v25_at(natal, START_Y, START_M, db, sec_base, mod_sec, ipo_year, MONTHS)
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
            rows.append({"tk":s["tk"],"name":s["name"],"sector":sec_base,
                         "modern":mod_sec,"ipo":s["ipo"],"age":s["age"],
                         "now":now,"peak":peak,"imp":imp,"bpk":bpk,
                         "peak_y":fa["peak"]["y"],"peak_m":fa["peak"]["m"],
                         "runway":run,"asym":asym})
        except: continue
    print(f"Scan done: {time.time()-t0:.0f}s, {len(rows)} candidates", file=sys.stderr)

    rows.sort(key=lambda r: -r["asym"])

    # Take top 50, fetch their actual price action April 2024 - April 2026
    print(f"\nFetching actual price data for top 50...", file=sys.stderr)
    start_dt = datetime(START_Y, START_M, 1)
    end_dt = datetime(END_Y, END_M, 22)

    # SPY benchmark
    spy = fetch_prices_yahoo("SPY", start_dt, end_dt)
    if spy:
        spy_start = spy[0][1]; spy_end = spy[-1][1]
        spy_ret = (spy_end / spy_start - 1) * 100
        spy_max = max(c for _, c in spy)
        spy_max_ret = (spy_max / spy_start - 1) * 100
    else:
        spy_ret = spy_max_ret = 0
    print(f"SPY {start_dt.date()} -> {end_dt.date()}: {spy_ret:+.1f}% (peak {spy_max_ret:+.1f}%)\n")

    results = []
    for i, r in enumerate(rows[:50]):
        tk = r["tk"]
        cache = f"/home/user/cyclepapa/data/prices/{tk}.csv"
        prices = []
        if os.path.exists(cache):
            with open(cache) as f:
                next(f)
                for line in f:
                    p = line.strip().split(",")
                    if len(p)==2:
                        try: prices.append((p[0], float(p[1])))
                        except: pass
        else:
            prices = fetch_prices_yahoo(tk, start_dt, end_dt)
            if prices:
                with open(cache,"w") as f:
                    f.write("date,close\n")
                    for d,c in prices: f.write(f"{d},{c:.4f}\n")
            time.sleep(0.3)
        if not prices: continue
        # Filter to our backtest window
        prices = [(d,c) for (d,c) in prices if start_dt.strftime("%Y-%m-%d") <= d <= end_dt.strftime("%Y-%m-%d")]
        if len(prices) < 50: continue
        p_start = prices[0][1]; p_end = prices[-1][1]
        p_max = max(c for _,c in prices)
        max_date = next(d for d,c in prices if c == p_max)
        ret = (p_end/p_start - 1) * 100
        max_ret = (p_max/p_start - 1) * 100
        excess = ret - spy_ret
        excess_max = max_ret - spy_max_ret
        results.append({"rank":i+1,**r,
                        "p_start":p_start,"p_end":p_end,"p_max":p_max,
                        "ret_pct":ret,"max_ret_pct":max_ret,
                        "excess_ret":excess,"excess_max":excess_max,
                        "max_date":max_date})

    print(f"\n{'='*180}")
    print(f"V25 BACKTEST — picks made {START_Y}-{START_M:02d}, performance through {END_Y}-{END_M:02d} ({MONTHS}mo)")
    print(f"SPY benchmark: {spy_ret:+.1f}% close-to-close (max {spy_max_ret:+.1f}%)")
    print(f"{'='*180}")
    print(f"{'#':>3s} {'Tkr':<6s} {'Sec':<10s} {'Asym':>5s} {'PeakMo':<8s} {'Run':>3s} | "
          f"{'StartP':>7s} {'EndP':>7s} {'MaxP':>7s} | "
          f"{'Ret%':>6s} {'MaxRet%':>7s} {'vsSPY':>6s} {'maxVsSPY':>8s} {'MaxDate':<10s}")
    for r in results:
        nm = r["name"][:18]
        print(f"{r['rank']:3d} {r['tk']:<6s} {r['modern'][:10]:<10s} "
              f"{r['asym']:5.2f} {r['peak_y']}-{r['peak_m']:02d}  {r['runway']:>3d} | "
              f"{r['p_start']:7.2f} {r['p_end']:7.2f} {r['p_max']:7.2f} | "
              f"{r['ret_pct']:+6.1f} {r['max_ret_pct']:+7.1f} {r['excess_ret']:+6.1f} {r['excess_max']:+8.1f} {r['max_date']}  {nm}")

    # Aggregates
    if results:
        rets = [r["ret_pct"] for r in results]
        max_rets = [r["max_ret_pct"] for r in results]
        excess = [r["excess_ret"] for r in results]
        excess_max = [r["excess_max"] for r in results]
        import statistics as st
        print(f"\n{'='*100}")
        print(f"AGGREGATES — top-{len(results)} v25 picks vs SPY:")
        print(f"  Mean return:       {st.mean(rets):+.1f}%   (SPY {spy_ret:+.1f}%, excess +{st.mean(rets)-spy_ret:.1f}%)")
        print(f"  Median return:     {st.median(rets):+.1f}%")
        print(f"  Mean PEAK return:  {st.mean(max_rets):+.1f}%   (SPY peak {spy_max_ret:+.1f}%, excess +{st.mean(max_rets)-spy_max_ret:.1f}%)")
        print(f"  Median PEAK ret:   {st.median(max_rets):+.1f}%")
        print(f"")
        print(f"  Hit rates (peak return achieved at any point):")
        for thresh in (25, 50, 100, 200, 500):
            n = sum(1 for r in max_rets if r >= thresh)
            print(f"    >= +{thresh:>3d}%:    {n:>2d}/{len(results)} ({100*n/len(results):.0f}%)")
        print(f"")
        print(f"  Hit rates (close-to-close return):")
        for thresh in (25, 50, 100, 200):
            n = sum(1 for r in rets if r >= thresh)
            print(f"    >= +{thresh:>3d}%:    {n:>2d}/{len(results)} ({100*n/len(results):.0f}%)")
        print(f"")
        print(f"  Beat SPY (close-to-close): {sum(1 for e in excess if e>0)}/{len(excess)} ({100*sum(1 for e in excess if e>0)/len(excess):.0f}%)")
        print(f"  Beat SPY (peak-to-peak):   {sum(1 for e in excess_max if e>0)}/{len(excess_max)} ({100*sum(1 for e in excess_max if e>0)/len(excess_max):.0f}%)")

    # Export
    out = "/home/user/cyclepapa/data/v25_backtest_apr2024.csv"
    with open(out, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["rank","ticker","name","sector","modern","ipo","age",
                    "predicted_peak","runway","asym",
                    "p_start","p_end","p_max","return_pct","max_return_pct",
                    "excess_vs_spy","max_excess_vs_spy","actual_max_date"])
        for r in results:
            w.writerow([r["rank"],r["tk"],r["name"],r["sector"],r["modern"],
                        r["ipo"],r["age"],
                        f"{r['peak_y']}-{r['peak_m']:02d}",r["runway"],f"{r['asym']:.2f}",
                        f"{r['p_start']:.2f}",f"{r['p_end']:.2f}",f"{r['p_max']:.2f}",
                        f"{r['ret_pct']:+.1f}",f"{r['max_ret_pct']:+.1f}",
                        f"{r['excess_ret']:+.1f}",f"{r['excess_max']:+.1f}",
                        r["max_date"]])
    print(f"\nExported {out}")

if __name__ == "__main__":
    main()
