"""
Long-horizon astro shift + price hasn't moved yet.

For each SP500 chart, compute:
  - 12-month forward max-aspect-score delta
  - 18-month forward max-aspect-score delta
  - 36-month forward max-aspect-score delta
  - Recent 12-month PRICE change (to verify it hasn't run already)

Filter to:
  - Big forward astro shift on at least one horizon
  - Price has been quiet (12mo change |Δ| < 20% — neither big rally nor crash)
  - Or close to multi-year lows

Output: ranked list of "quiet now, big shift ahead" candidates.
"""
import csv, math, pickle, sys, os, subprocess, json, time
from datetime import datetime, timezone, timedelta
import statistics as st
import swisseph as swe
from bti_test import compute_natal

PIDS = {"Mercury":swe.MERCURY,"Venus":swe.VENUS,"Mars":swe.MARS,
        "Jupiter":swe.JUPITER,"Saturn":swe.SATURN,
        "Uranus":swe.URANUS,"Neptune":swe.NEPTUNE,"Pluto":swe.PLUTO}
NATAL_PTS = ("Sun","Moon","ASC","MC")
ASPECTS = {
    "conj_0":0.0,"sxt_60":60.0,"sq_90":90.0,"tri_120":120.0,"opp_180":180.0,
    "bat_41":41.04,"sept_51":51.43,"qnt_72":72.0,"gart_77":77.04,
    "butt_98":97.92,"phi_137":137.5,"biq_144":144.0,
}

def aspect_orb(a, b, target):
    d = (a - b) % 360
    return min(abs(d - target), abs(d - (360 - target)))

def date_jd(y, m, d=15):
    return swe.julday(y, m, d, 12.0)

def planet_lons(jd):
    return {p: swe.calc_ut(jd, pid)[0][0] % 360 for p, pid in PIDS.items()}

def chart_score(natal, lons, valid_keys, orb=2.5):
    s = 0.0
    actives = []
    for tp, tlon in lons.items():
        for np_ in NATAL_PTS:
            if np_ not in natal: continue
            npon = natal[np_]["lon"]
            for asp_name, asp_deg in ASPECTS.items():
                o = aspect_orb(tlon, npon, asp_deg)
                if o <= orb:
                    key = (tp, np_, asp_name)
                    if key in valid_keys:
                        d = valid_keys[key]["delta_365"]
                        s += d
                        actives.append((key, d, o))
    return s, actives

def fetch_or_load(tk):
    cache = f"/home/user/cyclepapa/data/prices_full/{tk}.csv"
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
    p1 = int(datetime(2020,1,1,tzinfo=timezone.utc).timestamp())
    p2 = int(datetime(2026,4,22,tzinfo=timezone.utc).timestamp())
    url=f"https://query1.finance.yahoo.com/v8/finance/chart/{tk}?period1={p1}&period2={p2}&interval=1d"
    try:
        out=subprocess.run(["curl","-sL","-H","User-Agent: Mozilla/5.0","-m","20",url],
                            capture_output=True,text=True,timeout=25).stdout
        j=json.loads(out)
        r=j.get("chart",{}).get("result")
        if not r: return []
        ts=r[0]["timestamp"]; cs=r[0]["indicators"]["quote"][0]["close"]
        prices=[(datetime.utcfromtimestamp(t).strftime("%Y-%m-%d"),c) for t,c in zip(ts,cs) if c]
        if prices:
            os.makedirs(os.path.dirname(cache), exist_ok=True)
            with open(cache,"w") as f:
                f.write("date,close\n")
                for d,c in prices: f.write(f"{d},{c:.4f}\n")
        return prices
    except: return []

def price_change(prices, days_back):
    """Pct change from 'days_back' days ago to most recent close."""
    if not prices: return None
    last_d, last_c = prices[-1]
    last_dt = datetime.strptime(last_d, "%Y-%m-%d")
    target = (last_dt - timedelta(days=days_back)).strftime("%Y-%m-%d")
    pdict = dict(prices)
    base_c = None
    for off in range(15):
        check = (last_dt - timedelta(days=days_back-off)).strftime("%Y-%m-%d")
        if check in pdict: base_c = pdict[check]; break
    if base_c is None or base_c <= 0: return None
    return (last_c/base_c - 1) * 100

def price_from_low(prices, days):
    """Pct above the LOW of the last `days` days."""
    if not prices: return None
    last_d, last_c = prices[-1]
    last_dt = datetime.strptime(last_d, "%Y-%m-%d")
    cutoff = (last_dt - timedelta(days=days)).strftime("%Y-%m-%d")
    recent = [(d,c) for (d,c) in prices if d >= cutoff]
    if not recent: return None
    low = min(c for _,c in recent)
    return (last_c/low - 1) * 100

def main():
    print("Loading event-study keys...", file=sys.stderr)
    with open("/home/user/cyclepapa/data/event_study_keys.pkl","rb") as f:
        key_stats = pickle.load(f)
    valid_keys = {k:v for k,v in key_stats.items()
                  if v.get("n_w",0)>=10 and v.get("n_c",0)>=5
                  and "delta_365" in v}

    sp500 = []
    with open("/home/user/cyclepapa/data/sp500_ipo_dates.csv") as f:
        for r in csv.DictReader(f):
            tk = r["ticker"].strip().upper()
            ipo = (r.get("ipo_date") or "").strip()
            if not ipo or len(ipo)<10: continue
            sp500.append({"tk":tk,"ipo":ipo,
                          "name":r.get("name","").strip(),
                          "sector":r.get("sector","").strip()})
    print(f"  {len(sp500)} SP500 names", file=sys.stderr)

    # Forward 36 months grid (every 1 month)
    months = []
    y, m = 2026, 4
    for _ in range(37):
        months.append((y, m))
        m += 1
        if m > 12: m = 1; y += 1
    monthly_lons = {(y,m): planet_lons(date_jd(y,m)) for y,m in months}

    t0 = time.time()
    rows = []
    for i, s in enumerate(sp500):
        if i and i % 50 == 0:
            print(f"  {i}/{len(sp500)} {time.time()-t0:.0f}s", file=sys.stderr)
        try:
            natal = compute_natal(s["ipo"])
        except: continue
        # Compute monthly scores forward 36 months
        scores = []
        for (y,m) in months:
            sc, _ = chart_score(natal, monthly_lons[(y,m)], valid_keys)
            scores.append({"y":y,"m":m,"score":sc})
        score_now = scores[0]["score"]
        # 12-month window: months 1-12
        score_12_max = max(scores[1:13], key=lambda x:x["score"])
        score_18_max = max(scores[1:19], key=lambda x:x["score"])
        score_36_max = max(scores[1:37], key=lambda x:x["score"])
        delta_12 = score_12_max["score"] - score_now
        delta_18 = score_18_max["score"] - score_now
        delta_36 = score_36_max["score"] - score_now

        # Price data
        prices = fetch_or_load(s["tk"])
        chg_12 = price_change(prices, 365) if prices else None
        chg_6 = price_change(prices, 180) if prices else None
        chg_3 = price_change(prices, 90) if prices else None
        from_low_12 = price_from_low(prices, 365) if prices else None
        from_low_24 = price_from_low(prices, 730) if prices else None

        rows.append({**s,
                     "score_now":score_now,
                     "score_12":score_12_max["score"],"month_12":f"{score_12_max['y']}-{score_12_max['m']:02d}",
                     "score_18":score_18_max["score"],"month_18":f"{score_18_max['y']}-{score_18_max['m']:02d}",
                     "score_36":score_36_max["score"],"month_36":f"{score_36_max['y']}-{score_36_max['m']:02d}",
                     "delta_12":delta_12,"delta_18":delta_18,"delta_36":delta_36,
                     "chg_12mo":chg_12,"chg_6mo":chg_6,"chg_3mo":chg_3,
                     "from_low_12":from_low_12,"from_low_24":from_low_24})

    print(f"  Done. {time.time()-t0:.0f}s", file=sys.stderr)

    # Filter: huge forward shift + price hasn't moved much
    def quiet(r):
        # Price quietness: 12mo change between -25% and +25% OR within 25% of 12mo low
        if r["chg_12mo"] is None: return False
        if abs(r["chg_12mo"]) <= 25: return True
        if r["from_low_12"] is not None and r["from_low_12"] <= 25: return True
        return False

    # 12mo shift
    print(f"\n{'='*200}")
    print(f"BIG 12-MONTH ASTRO SHIFT + PRICE QUIET (12mo Δ within ±25% OR within 25% of 12mo low)")
    print(f"{'='*200}")
    rows.sort(key=lambda r: -r["delta_12"])
    candidates = [r for r in rows if r["delta_12"] >= 100 and quiet(r)]
    print(f"{'#':>3s} {'Tkr':<6s} {'GICS':<22s} {'Now':>5s}→{'12mo':>5s}  {'Δ12':>5s}  {'PkMo':<8s}  {'pr3mo':>6s} {'pr6mo':>6s} {'pr12mo':>6s} {'fr-low':>6s}  Name")
    for i, r in enumerate(candidates[:30], 1):
        nm = (r["name"] or "")[:18]
        gics = (r["sector"] or "")[:21]
        chg3 = f"{r['chg_3mo']:+5.0f}%" if r['chg_3mo'] is not None else "  n/a"
        chg6 = f"{r['chg_6mo']:+5.0f}%" if r['chg_6mo'] is not None else "  n/a"
        chg12 = f"{r['chg_12mo']:+5.0f}%" if r['chg_12mo'] is not None else "  n/a"
        from_low = f"{r['from_low_12']:+5.0f}%" if r['from_low_12'] is not None else "  n/a"
        print(f"{i:3d} {r['tk']:<6s} {gics:<22s} {r['score_now']:>+4.0f} →{r['score_12']:>+4.0f}  +{r['delta_12']:>4.0f}  {r['month_12']:<8s}  "
              f"{chg3:>6s} {chg6:>6s} {chg12:>6s} {from_low:>6s}  {nm}")

    # 18mo shift
    print(f"\n{'='*200}")
    print(f"BIG 18-MONTH SHIFT + PRICE QUIET")
    print(f"{'='*200}")
    rows.sort(key=lambda r: -r["delta_18"])
    cand18 = [r for r in rows if r["delta_18"] >= 100 and quiet(r)]
    print(f"{'#':>3s} {'Tkr':<6s} {'GICS':<22s} {'Now':>5s}→{'18mo':>5s}  {'Δ18':>5s}  {'PkMo':<8s}  {'pr12mo':>6s} {'fr-low':>6s}  Name")
    for i, r in enumerate(cand18[:30], 1):
        nm = (r["name"] or "")[:18]
        gics = (r["sector"] or "")[:21]
        chg12 = f"{r['chg_12mo']:+5.0f}%" if r['chg_12mo'] is not None else "  n/a"
        from_low = f"{r['from_low_12']:+5.0f}%" if r['from_low_12'] is not None else "  n/a"
        print(f"{i:3d} {r['tk']:<6s} {gics:<22s} {r['score_now']:>+4.0f} →{r['score_18']:>+4.0f}  +{r['delta_18']:>4.0f}  {r['month_18']:<8s}  "
              f"{chg12:>6s} {from_low:>6s}  {nm}")

    # 36mo shift
    print(f"\n{'='*200}")
    print(f"BIG 36-MONTH SHIFT + PRICE QUIET (multi-year compression-release plays)")
    print(f"{'='*200}")
    rows.sort(key=lambda r: -r["delta_36"])
    cand36 = [r for r in rows if r["delta_36"] >= 150 and quiet(r)]
    print(f"{'#':>3s} {'Tkr':<6s} {'GICS':<22s} {'Now':>5s}→{'36mo':>5s}  {'Δ36':>5s}  {'PkMo':<8s}  {'pr12mo':>6s} {'fr-low':>6s}  Name")
    for i, r in enumerate(cand36[:30], 1):
        nm = (r["name"] or "")[:18]
        gics = (r["sector"] or "")[:21]
        chg12 = f"{r['chg_12mo']:+5.0f}%" if r['chg_12mo'] is not None else "  n/a"
        from_low = f"{r['from_low_12']:+5.0f}%" if r['from_low_12'] is not None else "  n/a"
        print(f"{i:3d} {r['tk']:<6s} {gics:<22s} {r['score_now']:>+4.0f} →{r['score_36']:>+4.0f}  +{r['delta_36']:>4.0f}  {r['month_36']:<8s}  "
              f"{chg12:>6s} {from_low:>6s}  {nm}")

    # Combo: appears in 12+18+36 lists
    sets_12 = set(r["tk"] for r in cand36 if r["delta_12"] >= 80)
    sets_long = set(r["tk"] for r in cand36 if r["delta_36"] >= 150)
    sets_quiet = set(r["tk"] for r in rows if quiet(r))
    triple_play = sets_long & sets_12 & sets_quiet
    print(f"\n{'='*200}")
    print(f"TRIPLE-CONFLUENCE PICKS — big 12mo AND big 36mo AND price quiet ({len(triple_play)} names)")
    print(f"{'='*200}")
    triple_rows = [r for r in rows if r["tk"] in triple_play]
    triple_rows.sort(key=lambda r: -(r["delta_12"] + r["delta_36"]))
    print(f"{'Tkr':<6s} {'GICS':<22s} {'Now':>5s}  {'Δ12':>5s} {'PkMo':<8s} {'Δ18':>5s} {'Δ36':>5s} {'PkMo':<8s}  {'pr12mo':>6s} {'fr-low':>6s}  Name")
    for r in triple_rows[:25]:
        nm = (r["name"] or "")[:18]
        gics = (r["sector"] or "")[:21]
        chg12 = f"{r['chg_12mo']:+5.0f}%" if r['chg_12mo'] is not None else "  n/a"
        from_low = f"{r['from_low_12']:+5.0f}%" if r['from_low_12'] is not None else "  n/a"
        print(f"{r['tk']:<6s} {gics:<22s} {r['score_now']:>+4.0f}  +{r['delta_12']:>4.0f} {r['month_12']:<8s} "
              f"+{r['delta_18']:>4.0f} +{r['delta_36']:>4.0f} {r['month_36']:<8s}  "
              f"{chg12:>6s} {from_low:>6s}  {nm}")

    # Export
    rows.sort(key=lambda r: -(r["delta_12"] + 0.7*r["delta_18"] + 0.5*r["delta_36"]))
    with open("/home/user/cyclepapa/data/sp500_quiet_long_horizon.csv","w",newline="") as f:
        w = csv.writer(f)
        w.writerow(["rank","ticker","name","sector","ipo","score_now",
                    "delta_12mo","peak_12mo","delta_18mo","peak_18mo","delta_36mo","peak_36mo",
                    "price_chg_3mo","price_chg_6mo","price_chg_12mo","pct_above_12mo_low"])
        for i, r in enumerate(rows, 1):
            w.writerow([i,r["tk"],r["name"],r["sector"],r["ipo"],
                        f"{r['score_now']:+.1f}",
                        f"{r['delta_12']:+.1f}",r["month_12"],
                        f"{r['delta_18']:+.1f}",r["month_18"],
                        f"{r['delta_36']:+.1f}",r["month_36"],
                        f"{r['chg_3mo']:+.1f}" if r['chg_3mo'] is not None else "",
                        f"{r['chg_6mo']:+.1f}" if r['chg_6mo'] is not None else "",
                        f"{r['chg_12mo']:+.1f}" if r['chg_12mo'] is not None else "",
                        f"{r['from_low_12']:+.1f}" if r['from_low_12'] is not None else ""])
    print(f"\nExported -> data/sp500_quiet_long_horizon.csv")

if __name__ == "__main__":
    main()
