"""
DEEP ASYMMETRIC HUNT — July 2026.

Pipeline:
  1. From full_universe_jul2026.csv take the union of:
       - top 400 by forward 12mo delta
       - top 400 by delta among low-base (score_now < 60)
     (dedupe by ticker, keep best delta)
  2. ALIVENESS filter: fetch current prices from Yahoo. Names with no
     quote or last trade older than 10 days are dropped (dead/delisted).
  3. For survivors compute:
       - Price washout: 12mo change, % above 12mo low, % below 2023+ high
       - Natal magnitude signatures (validated on 152-corpus + 26-stock
         reconciliation): Uranus-Pluto septile 51.4° (median 75x),
         Uranus-Pluto sextile 60° (25x), Neptune-Pluto sextile 60° (17x),
         AVIS-DNA (Sun-Neptune <=5°), Galactic Center (outer <=3° of 267°)
       - Current transformation activations: Neptune/Pluto to natal
         Sun/Moon <=3°, multi-outer convergence
  4. Composite asymmetry score and ranked report.

Caveat: recycled tickers can return a different company's quote — names
whose price history starts after 2023-06 while the chart IPO is older
are flagged RECYCLED?.
"""
import csv, math, pickle, sys, os, subprocess, json, time
from datetime import datetime, timezone, timedelta
import swisseph as swe
from bti_test import compute_natal
from bti_v19_empirical import closest_hard

TODAY_DT = datetime(2026, 7, 1)
PIDS = {"Mercury":swe.MERCURY,"Venus":swe.VENUS,"Mars":swe.MARS,
        "Jupiter":swe.JUPITER,"Saturn":swe.SATURN,
        "Uranus":swe.URANUS,"Neptune":swe.NEPTUNE,"Pluto":swe.PLUTO}
NATAL_PTS = ("Sun","Moon","ASC","MC")
GC_LON = 267.0
CACHE_DIR = "/home/user/cyclepapa/data/prices_now"

def aspect_orb(a, b, target):
    d = (a - b) % 360
    return min(abs(d - target), abs(d - (360 - target)))

def conj_orb(a, b):
    d = abs(a - b) % 360
    return min(d, 360 - d)

def fetch_prices(tk):
    cache = f"{CACHE_DIR}/{tk}.csv"
    if os.path.exists(cache):
        prices = []
        with open(cache) as f:
            next(f)
            for line in f:
                p = line.strip().split(",")
                if len(p)==2:
                    try: prices.append((p[0], float(p[1])))
                    except: pass
        return prices
    p1 = int(datetime(2023,1,1,tzinfo=timezone.utc).timestamp())
    p2 = int(datetime(2026,7,1,tzinfo=timezone.utc).timestamp())
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{tk}?period1={p1}&period2={p2}&interval=1d"
    try:
        out = subprocess.run(["curl","-sL","-H","User-Agent: Mozilla/5.0","-m","15",url],
                              capture_output=True, text=True, timeout=20).stdout
        j = json.loads(out)
        r = j.get("chart",{}).get("result")
        if not r: return []
        ts = r[0]["timestamp"]; cs = r[0]["indicators"]["quote"][0]["close"]
        prices = [(datetime.utcfromtimestamp(t).strftime("%Y-%m-%d"), c) for t,c in zip(ts,cs) if c]
        if prices:
            os.makedirs(CACHE_DIR, exist_ok=True)
            with open(cache,"w") as f:
                f.write("date,close\n")
                for d,c in prices: f.write(f"{d},{c:.4f}\n")
        time.sleep(0.12)
        return prices
    except: return []

def main():
    # 1. Candidate pool from full-universe scan
    rows = []
    with open("/home/user/cyclepapa/data/full_universe_jul2026.csv") as f:
        for r in csv.DictReader(f):
            r["delta"] = float(r["delta"])
            r["score_now"] = float(r["score_now"])
            r["score_peak"] = float(r["score_peak"])
            rows.append(r)
    by_delta = sorted(rows, key=lambda r: -r["delta"])[:400]
    low_base = sorted([r for r in rows if r["score_now"] < 60],
                      key=lambda r: -r["delta"])[:400]
    pool = {}
    for r in by_delta + low_base:
        tk = r["ticker"]
        if tk not in pool or r["delta"] > pool[tk]["delta"]:
            pool[tk] = r
    print(f"Candidate pool: {len(pool)} unique tickers", file=sys.stderr)

    # 2 + 3. Aliveness + metrics
    survivors = []
    t0 = time.time()
    for i, (tk, r) in enumerate(pool.items()):
        if i and i % 50 == 0:
            print(f"  {i}/{len(pool)}  {time.time()-t0:.0f}s  alive={len(survivors)}", file=sys.stderr)
        prices = fetch_prices(tk)
        if not prices or len(prices) < 60: continue
        last_d, last_c = prices[-1]
        last_dt = datetime.strptime(last_d, "%Y-%m-%d")
        if (TODAY_DT - last_dt).days > 10: continue  # stale = dead
        first_d = prices[0][0]
        recycled = first_d > "2023-06-30" and r["ipo"] < "2022-01-01"

        pdict = dict(prices)
        m = {}
        for days_back, label in [(90,"chg3"),(365,"chg12")]:
            base = None
            for off in range(15):
                check = (last_dt - timedelta(days=days_back-off)).strftime("%Y-%m-%d")
                if check in pdict: base = pdict[check]; break
            m[label] = (last_c/base - 1)*100 if base and base > 0 else None
        yr = [c for (d,c) in prices if d >= (last_dt - timedelta(days=365)).strftime("%Y-%m-%d")]
        m["from_low"] = (last_c/min(yr) - 1)*100 if yr else None
        hi_all = max(c for _,c in prices)
        m["from_high"] = (last_c/hi_all - 1)*100

        try:
            natal = compute_natal(r["ipo"])
        except: continue
        sun = natal["Sun"]["lon"]; moon = natal.get("Moon",{}).get("lon")
        nep = natal["Neptune"]["lon"]; ura = natal["Uranus"]["lon"]; plu = natal["Pluto"]["lon"]
        sig = {
            "urplu_sept": aspect_orb(ura, plu, 51.43),
            "urplu_sxt":  aspect_orb(ura, plu, 60.0),
            "neplu_sxt":  aspect_orb(nep, plu, 60.0),
            "avis":       conj_orb(sun, nep),
            "gc":         min(closest_hard(natal[p]["lon"], GC_LON)
                              for p in ("Jupiter","Saturn","Uranus","Neptune","Pluto") if p in natal),
        }
        jd_now = swe.julday(2026, 7, 1, 12.0)
        lons = {p: swe.calc_ut(jd_now, pid)[0][0] % 360 for p, pid in PIDS.items()}
        act = {
            "nep_sun": closest_hard(lons["Neptune"], sun),
            "nep_moon": closest_hard(lons["Neptune"], moon) if moon is not None else 99,
            "plu_sun": closest_hard(lons["Pluto"], sun),
            "plu_moon": closest_hard(lons["Pluto"], moon) if moon is not None else 99,
        }
        n_tight = sum(1 for p in ("Jupiter","Saturn","Uranus","Neptune","Pluto")
                      if min((closest_hard(lons[p], natal[pt]["lon"])
                             for pt in NATAL_PTS if pt in natal), default=99) <= 5)

        # 4. Composite asymmetry
        asym = r["delta"]
        chg12 = m["chg12"]
        if chg12 is not None:
            if chg12 <= -50: asym *= 1.5
            elif chg12 <= -30: asym *= 1.3
            elif chg12 <= -10: asym *= 1.15
            elif chg12 >= 100: asym *= 0.7   # already ran
        if m["from_low"] is not None and m["from_low"] <= 15: asym *= 1.1
        nat_mult = 1.0
        if sig["urplu_sept"] <= 3: nat_mult *= 1.3
        if sig["urplu_sxt"] <= 3:  nat_mult *= 1.2
        if sig["neplu_sxt"] <= 3:  nat_mult *= 1.2
        if sig["avis"] <= 5:       nat_mult *= 1.25
        if sig["gc"] <= 3:         nat_mult *= 1.15
        asym *= nat_mult
        if min(act["nep_sun"], act["nep_moon"]) <= 3: asym += 40
        if min(act["plu_sun"], act["plu_moon"]) <= 3: asym += 30
        if n_tight >= 3: asym += 25
        if r["score_now"] < 40: asym *= 1.1   # low base

        survivors.append({**r, **m, "sig":sig, "act":act, "n_tight":n_tight,
                          "recycled":recycled, "last":last_c, "asym":asym,
                          "nat_mult":nat_mult})
    print(f"Alive survivors: {len(survivors)} of {len(pool)}", file=sys.stderr)

    survivors.sort(key=lambda s: -s["asym"])

    out = "/home/user/cyclepapa/data/deep_asymmetric_jul2026.csv"
    with open(out, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["rank","ticker","name","source","ipo","age","score_now","score_peak",
                    "delta","peak_month","chg_3mo","chg_12mo","from_low_12","from_high",
                    "last_close","urplu_sept","urplu_sxt","neplu_sxt","avis_dna","gc",
                    "nep_sun","nep_moon","plu_sun","plu_moon","n_tight","natal_mult",
                    "recycled_flag","asymmetry"])
        for i, s in enumerate(survivors, 1):
            w.writerow([i, s["ticker"], s["name"], s["source"], s["ipo"], s["age"],
                        f"{s['score_now']:+.0f}", f"{s['score_peak']:+.0f}",
                        f"{s['delta']:+.0f}", s["peak_month"],
                        f"{s['chg3']:+.1f}" if s['chg3'] is not None else "",
                        f"{s['chg12']:+.1f}" if s['chg12'] is not None else "",
                        f"{s['from_low']:+.1f}" if s['from_low'] is not None else "",
                        f"{s['from_high']:+.1f}",
                        f"{s['last']:.2f}",
                        f"{s['sig']['urplu_sept']:.1f}", f"{s['sig']['urplu_sxt']:.1f}",
                        f"{s['sig']['neplu_sxt']:.1f}", f"{s['sig']['avis']:.1f}",
                        f"{s['sig']['gc']:.1f}",
                        f"{s['act']['nep_sun']:.1f}", f"{s['act']['nep_moon']:.1f}",
                        f"{s['act']['plu_sun']:.1f}", f"{s['act']['plu_moon']:.1f}",
                        s["n_tight"], f"{s['nat_mult']:.2f}",
                        "Y" if s["recycled"] else "",
                        f"{s['asym']:.0f}"])
    print(f"Exported {len(survivors)} -> {out}")

    print(f"\n{'='*205}")
    print(f"DEEP ASYMMETRIC HUNT — top 50 (alive, scored {len(survivors)})   [Rcy = possible recycled ticker: verify identity before acting]")
    print(f"{'='*205}")
    print(f"{'#':>3s} {'Tkr':<6s} {'Src':<7s} {'IPO':<11s} {'Now':>5s}→{'Pk':>5s} {'Δ':>5s} {'PkMo':<8s} "
          f"{'pr3':>6s} {'pr12':>6s} {'fLow':>6s} {'fHi':>6s} {'$':>8s} "
          f"{'Spt':>4s} {'Sxt':>4s} {'NpS':>4s} {'AVI':>4s} {'GC':>4s} {'NpSn':>5s} {'PlSn':>5s} {'#t':>2s} {'Rcy':>3s} {'ASYM':>6s}  Name")
    for i, s in enumerate(survivors[:50], 1):
        nm = (s["name"] or "")[:24]
        c3 = f"{s['chg3']:+5.0f}%" if s['chg3'] is not None else "   n/a"
        c12 = f"{s['chg12']:+5.0f}%" if s['chg12'] is not None else "   n/a"
        fl = f"{s['from_low']:+5.0f}%" if s['from_low'] is not None else "  n/a"
        fh = f"{s['from_high']:+5.0f}%"
        spt = "★" if s['sig']['urplu_sept'] <= 3 else " "
        sxt = "★" if s['sig']['urplu_sxt'] <= 3 else " "
        nps = "★" if s['sig']['neplu_sxt'] <= 3 else " "
        avi = "★" if s['sig']['avis'] <= 5 else " "
        gc = "★" if s['sig']['gc'] <= 3 else " "
        rcy = "?" if s["recycled"] else " "
        print(f"{i:3d} {s['ticker']:<6s} {s['source']:<7s} {s['ipo']:<11s} "
              f"{s['score_now']:>+4.0f}→{s['score_peak']:>+4.0f} {s['delta']:>+4.0f} {s['peak_month']:<8s} "
              f"{c3:>6s} {c12:>6s} {fl:>6s} {fh:>6s} {s['last']:>8.2f} "
              f"{spt:>4s} {sxt:>4s} {nps:>4s} {avi:>4s} {gc:>4s} "
              f"{s['act']['nep_sun']:>4.1f}° {s['act']['plu_sun']:>4.1f}° {s['n_tight']:>2d} {rcy:>3s} {s['asym']:>6.0f}  {nm}")

    # Washout-only view
    wo = [s for s in survivors if s["chg12"] is not None and s["chg12"] <= -30
          and not s["recycled"]]
    print(f"\n{'='*160}")
    print(f"DEEP-WASHOUT SUBSET (pr12 <= -30%, non-recycled): {len(wo)} names")
    print(f"{'='*160}")
    for i, s in enumerate(wo[:25], 1):
        nm = (s["name"] or "")[:28]
        print(f"{i:3d} {s['ticker']:<6s} {s['ipo']:<11s} {s['score_now']:>+4.0f}→{s['score_peak']:>+4.0f} "
              f"(Δ{s['delta']:+.0f}) pk {s['peak_month']}  pr12 {s['chg12']:+.0f}%  fLow {s['from_low']:+.0f}%  "
              f"${s['last']:.2f}  ASYM {s['asym']:.0f}  {nm}")

if __name__ == "__main__":
    main()
