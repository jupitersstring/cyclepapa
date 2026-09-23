"""
RERUN — best opportunities as of TODAY (2026-07-01).

Re-dates the two decision scanners to July 1 2026 and refreshes prices:
  (A) Off-SP500 speculative parabolic convexity
  (B) SP500 long-horizon shift + price-quiet

Macro state changes since the April run:
  - Jupiter entered LEO on Jun 30 2026 (entertainment/luxury/gambling/gold IN;
    food/staples/homebuilders/REIT window CLOSED)
  - Uranus firmly in Gemini (ingress Apr 25)
  - Uranus-Pluto trine #1 EXACT Jul 18 2026 — 17 days out
  - Node ingress ~Aug 2026 approaching (empirical peak/exit signal)
Uses macro_regime.macro_regime_multiplier(y=2026, m=7) so all of this is
picked up dynamically rather than from the stale April constants.
"""
import csv, math, pickle, sys, os, subprocess, json, time
from datetime import datetime, timezone, timedelta
import statistics as st
import swisseph as swe
from bti_test import compute_natal
from bti_v19_empirical import closest_hard
from macro_regime import macro_regime_multiplier

TODAY = "2026-07-01"
TY, TM, TD = 2026, 7, 1

PIDS = {"Mercury":swe.MERCURY,"Venus":swe.VENUS,"Mars":swe.MARS,
        "Jupiter":swe.JUPITER,"Saturn":swe.SATURN,
        "Uranus":swe.URANUS,"Neptune":swe.NEPTUNE,"Pluto":swe.PLUTO}
NATAL_PTS = ("Sun","Moon","ASC","MC")
ASPECTS = {
    "conj_0":0.0,"sxt_60":60.0,"sq_90":90.0,"tri_120":120.0,"opp_180":180.0,
    "bat_41":41.04,"sept_51":51.43,"qnt_72":72.0,"gart_77":77.04,
    "butt_98":97.92,"phi_137":137.5,"biq_144":144.0,
}
GC_LON = 267.0
CACHE_DIR = "/home/user/cyclepapa/data/prices_now"

def aspect_orb(a, b, target):
    d = (a - b) % 360
    return min(abs(d - target), abs(d - (360 - target)))

def conj_orb(a, b):
    d = abs(a - b) % 360
    return min(d, 360 - d)

def date_jd(y, m, d=15):
    return swe.julday(y, m, d, 12.0)

def planet_lons(jd):
    return {p: swe.calc_ut(jd, pid)[0][0] % 360 for p, pid in PIDS.items()}

def chart_event_score(natal, lons, valid_keys, orb=2.5):
    s = 0.0
    for tp, tlon in lons.items():
        for np_ in NATAL_PTS:
            if np_ not in natal: continue
            npon = natal[np_]["lon"]
            for asp_name, asp_deg in ASPECTS.items():
                o = aspect_orb(tlon, npon, asp_deg)
                if o <= orb:
                    key = (tp, np_, asp_name)
                    if key in valid_keys:
                        s += valid_keys[key]["delta_365"]
    return s

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
        out = subprocess.run(["curl","-sL","-H","User-Agent: Mozilla/5.0","-m","20",url],
                              capture_output=True, text=True, timeout=25).stdout
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
        time.sleep(0.15)
        return prices
    except: return []

def price_metrics(prices):
    if not prices: return {}
    last_d, last_c = prices[-1]
    last_dt = datetime.strptime(last_d, "%Y-%m-%d")
    pdict = dict(prices)
    m = {"last_close": last_c, "last_date": last_d}
    for days_back, label in [(90,"chg_3mo"),(180,"chg_6mo"),(365,"chg_12mo")]:
        base = None
        for off in range(15):
            check = (last_dt - timedelta(days=days_back-off)).strftime("%Y-%m-%d")
            if check in pdict: base = pdict[check]; break
        if base and base > 0:
            m[label] = (last_c/base - 1)*100
    for days, label in [(365,"from_low_12")]:
        cutoff = (last_dt - timedelta(days=days)).strftime("%Y-%m-%d")
        recent = [c for (d,c) in prices if d >= cutoff]
        if recent:
            m[label] = (last_c/min(recent) - 1)*100
    return m

SPEC = {
    "IONQ":("AI_QUANTUM","2021-10-01"),"RGTI":("AI_QUANTUM","2022-03-02"),
    "QBTS":("AI_QUANTUM","2022-08-08"),"ALAB":("SEMIS","2024-03-20"),
    "CRWV":("AI_QUANTUM","2025-03-28"),"PLTR":("AI_QUANTUM","2020-09-30"),
    "AI":("AI_QUANTUM","2020-12-09"),"ARM":("SEMIS","2023-09-14"),
    "SMCI":("SEMIS","2007-03-29"),"ANET":("TECH","2014-06-06"),
    "TEM":("AI_QUANTUM","2024-06-14"),"APP":("AI_QUANTUM","2021-04-15"),
    "NXE":("URANIUM","2013-06-04"),"ASPI":("URANIUM","2024-02-15"),
    "CCJ":("URANIUM","1996-11-04"),"URA":("URANIUM","2019-11-04"),
    "CEG":("NUCLEAR","2022-02-02"),"VST":("NUCLEAR","2016-10-10"),
    "SMR":("NUCLEAR","2022-05-03"),"OKLO":("NUCLEAR","2024-05-10"),
    "NNE":("NUCLEAR","2024-05-08"),
    "RKLB":("SPACE","2021-08-25"),"LUNR":("SPACE","2023-02-13"),
    "AVAV":("DRONES","2007-01-23"),
    "VKTX":("BIOTECH","2015-09-29"),"CRSP":("BIOTECH","2016-10-19"),
    "NTLA":("BIOTECH","2016-05-06"),"BEAM":("BIOTECH","2020-02-06"),
    "EDIT":("BIOTECH","2016-02-03"),"RXRX":("BIOTECH","2021-04-16"),
    "RIVN":("EV","2021-11-10"),"NIO":("EV","2018-09-12"),
    "XPEV":("EV","2020-08-27"),"LI":("EV","2020-07-30"),
    "MSTR":("CRYPTO","1998-06-11"),"COIN":("CRYPTO","2021-04-14"),
    "GME":("MEME","2002-02-13"),"AMC":("MEME","2013-12-18"),
    "RDDT":("ENTERTAINMENT","2024-03-21"),"CRH":("INDUSTRIAL","2025-12-22"),
    "NBIS":("AI_QUANTUM","2024-10-21"),"RBRK":("CYBERSEC","2024-04-25"),
    "S":("CYBERSEC","2021-06-30"),"NET":("CYBERSEC","2019-09-13"),
    "SNOW":("TECH","2020-09-16"),"DUOL":("TECH","2021-07-28"),
    "INGM":("TECH","2024-10-24"),"KVYO":("TECH","2023-09-20"),
    "HOOD":("FINANCE","2021-07-29"),"SOFI":("FINANCE","2021-06-01"),
    "UPST":("FINANCE","2020-12-16"),"AFRM":("FINANCE","2021-01-13"),
    "ROOT":("FINANCE","2020-10-28"),"SE":("TECH","2017-10-20"),
    "MELI":("TECH","2007-08-10"),"CVNA":("RETAIL","2017-04-28"),
    "HIMS":("BIOTECH","2021-01-21"),
    "ENPH":("CLEAN","2012-03-30"),"SEDG":("CLEAN","2015-03-26"),
    "FSLR":("CLEAN","2006-11-17"),"PLUG":("CLEAN","1999-10-29"),
    "BE":("CLEAN","2018-07-25"),
    # Jupiter-Leo NEW-REGIME names (entertainment/luxury/gambling/creator)
    "NFLX":("STREAMING","2002-05-23"),"SPOT":("STREAMING","2018-04-03"),
    "RBLX":("CREATOR_ECONOMY","2021-03-10"),"DKNG":("GAMBLING","2020-04-24"),
    "FLUT":("GAMBLING","2024-01-29"),"PENN":("GAMBLING","1994-05-26"),
    "LYV":("ENTERTAINMENT","2005-12-21"),"TKO":("ENTERTAINMENT","2023-09-12"),
    "WYNN":("HOSPITALITY","2002-10-25"),"LVS":("HOSPITALITY","2004-12-15"),
    "TPR":("LUXURY","2000-10-05"),"RL":("LUXURY","1997-06-12"),
    "DECK":("LUXURY","1993-10-14"),"BIRK":("LUXURY","2023-10-11"),
    "NEM":("PRECIOUS_METALS","1940-01-02"),"AEM":("PRECIOUS_METALS","1972-01-25"),
    "GDX":("PRECIOUS_METALS","2006-05-16"),"KGC":("PRECIOUS_METALS","1993-09-01"),
}

def main():
    print(f"Scan date: {TODAY}", file=sys.stderr)
    with open("/home/user/cyclepapa/data/event_study_keys.pkl","rb") as f:
        key_stats = pickle.load(f)
    valid_keys = {k:v for k,v in key_stats.items()
                  if v.get("n_w",0)>=10 and v.get("n_c",0)>=5 and "delta_365" in v}

    today_lons = planet_lons(swe.julday(TY, TM, TD, 12.0))
    # forward 12 months from July 2026
    months = []
    y, m = TY, TM
    for _ in range(13):
        months.append((y,m))
        m += 1
        if m > 12: m = 1; y += 1
    monthly_lons = {(y,m): planet_lons(date_jd(y,m)) for y,m in months}

    print(f"Jupiter now: {today_lons['Jupiter']:.1f}° (Leo {today_lons['Jupiter']-120:.1f}°)" if 120<=today_lons['Jupiter']<150 else f"Jupiter now: {today_lons['Jupiter']:.1f}°", file=sys.stderr)

    # ================= (A) SPECULATIVE =================
    rows = []
    for tk, (sector, ipo) in SPEC.items():
        try:
            natal = compute_natal(ipo)
        except: continue
        age = TY - int(ipo[:4])
        score_now = chart_event_score(natal, today_lons, valid_keys)
        fwd = []
        for ym in months[1:]:
            fwd.append({"ym":ym,"score":chart_event_score(natal, monthly_lons[ym], valid_keys)})
        pk = max(fwd, key=lambda x:x["score"])
        delta = pk["score"] - score_now
        macro = macro_regime_multiplier(sector, TY, TM)
        macro_pk = macro_regime_multiplier(sector, pk["ym"][0], pk["ym"][1])

        sun_n = natal["Sun"]["lon"]; nep_n = natal["Neptune"]["lon"]
        avis = conj_orb(sun_n, nep_n) <= 5
        gc = min(closest_hard(natal[p]["lon"], GC_LON)
                 for p in ("Jupiter","Saturn","Uranus","Neptune","Pluto") if p in natal) <= 3
        nep_sun = closest_hard(today_lons["Neptune"], sun_n)
        nep_moon = closest_hard(today_lons["Neptune"], natal["Moon"]["lon"]) if "Moon" in natal else 99
        plu_sun = closest_hard(today_lons["Pluto"], sun_n)
        n_tight = sum(1 for p in ("Jupiter","Saturn","Uranus","Neptune","Pluto")
                      if min((closest_hard(today_lons[p], natal[pt]["lon"])
                             for pt in NATAL_PTS if pt in natal), default=99) <= 5)

        pm = price_metrics(fetch_prices(tk))
        chg12 = pm.get("chg_12mo"); chg3 = pm.get("chg_3mo")
        from_low = pm.get("from_low_12"); last = pm.get("last_close")

        conv = (score_now + delta * 1.5) * macro_pk
        if avis: conv *= 1.5
        if gc: conv *= 1.4
        if nep_sun <= 3 or nep_moon <= 3: conv += 50
        if plu_sun <= 3: conv += 40
        if n_tight >= 3: conv += 30
        if age <= 5: conv *= 1.2
        if score_now > 100: conv *= 0.7
        # Price quietness bonus: washed out = better R/R
        if chg12 is not None and chg12 < 0: conv *= 1.15
        if chg3 is not None and chg3 < -15: conv *= 1.1

        rows.append({"tk":tk,"sector":sector,"ipo":ipo,"age":age,
                     "now":score_now,"peak":pk["score"],"delta":delta,
                     "pk_mo":f"{pk['ym'][0]}-{pk['ym'][1]:02d}",
                     "macro":macro,"macro_pk":macro_pk,"avis":avis,"gc":gc,
                     "nep_sun":nep_sun,"nep_moon":nep_moon,"plu_sun":plu_sun,
                     "n_tight":n_tight,"chg3":chg3,"chg12":chg12,
                     "from_low":from_low,"last":last,"conv":conv})

    rows.sort(key=lambda r: -r["conv"])
    print(f"\n{'='*205}")
    print(f"(A) SPECULATIVE PARABOLIC — re-scanned {TODAY}  |  Jupiter->Leo Jun 30, U-P trine exact Jul 18 (17d), Node ingress ~Aug")
    print(f"{'='*205}")
    print(f"{'#':>3s} {'Tkr':<6s} {'Sector':<14s} {'Age':>3s} {'Now':>5s}→{'Pk':>5s} {'Δ':>5s} {'PkMo':<8s} {'mNow':>5s} {'mPk':>5s} {'AV':>2s} {'GC':>2s} {'NpSn':>5s} {'PlSn':>5s} {'#t':>2s} {'pr3':>6s} {'pr12':>6s} {'fLow':>5s} {'$':>7s} {'CVX':>6s}")
    for i, r in enumerate(rows[:40], 1):
        av = "★" if r["avis"] else " "
        gc = "★" if r["gc"] else " "
        c3 = f"{r['chg3']:+5.0f}%" if r['chg3'] is not None else "   n/a"
        c12 = f"{r['chg12']:+5.0f}%" if r['chg12'] is not None else "   n/a"
        fl = f"{r['from_low']:+4.0f}%" if r['from_low'] is not None else "  n/a"
        px = f"{r['last']:7.2f}" if r['last'] is not None else "    n/a"
        print(f"{i:3d} {r['tk']:<6s} {r['sector']:<14s} {r['age']:>3d} {r['now']:>+4.0f}→{r['peak']:>+4.0f} {r['delta']:>+4.0f} {r['pk_mo']:<8s} "
              f"{r['macro']:>5.2f} {r['macro_pk']:>5.2f} {av:>2s} {gc:>2s} {r['nep_sun']:>4.1f}° {r['plu_sun']:>4.1f}° {r['n_tight']:>2d} "
              f"{c3:>6s} {c12:>6s} {fl:>5s} {px:>7s} {r['conv']:>+6.0f}")

    with open("/home/user/cyclepapa/data/best_opps_jul2026_spec.csv","w",newline="") as f:
        w = csv.writer(f)
        w.writerow(["rank","ticker","sector","ipo","age","score_now","score_peak","delta","peak_month",
                    "macro_now","macro_peak","avis_dna","gc","nep_sun_orb","plu_sun_orb","n_tight",
                    "chg_3mo","chg_12mo","from_low_12","last_close","convexity"])
        for i, r in enumerate(rows, 1):
            w.writerow([i,r["tk"],r["sector"],r["ipo"],r["age"],
                        f"{r['now']:+.1f}",f"{r['peak']:+.1f}",f"{r['delta']:+.1f}",r["pk_mo"],
                        f"{r['macro']:.2f}",f"{r['macro_pk']:.2f}",
                        "Y" if r["avis"] else "N","Y" if r["gc"] else "N",
                        f"{r['nep_sun']:.2f}",f"{r['plu_sun']:.2f}",r["n_tight"],
                        f"{r['chg3']:+.1f}" if r['chg3'] is not None else "",
                        f"{r['chg12']:+.1f}" if r['chg12'] is not None else "",
                        f"{r['from_low']:+.1f}" if r['from_low'] is not None else "",
                        f"{r['last']:.2f}" if r['last'] is not None else "",
                        f"{r['conv']:+.1f}"])

    # ================= (B) SP500 QUIET + SHIFT =================
    print(f"\n(B) SP500 quiet-price + forward-shift as of {TODAY}...", file=sys.stderr)
    sp500 = []
    with open("/home/user/cyclepapa/data/sp500_ipo_dates.csv") as f:
        for r in csv.DictReader(f):
            tk = r["ticker"].strip().upper()
            ipo = (r.get("ipo_date") or "").strip()
            if not ipo or len(ipo)<10: continue
            sp500.append({"tk":tk,"ipo":ipo,"name":r.get("name","").strip(),
                          "sector":r.get("sector","").strip()})

    sp_rows = []
    for s in sp500:
        try:
            natal = compute_natal(s["ipo"])
        except: continue
        score_now = chart_event_score(natal, today_lons, valid_keys)
        fwd = [{"ym":ym,"score":chart_event_score(natal, monthly_lons[ym], valid_keys)}
               for ym in months[1:]]
        pk = max(fwd, key=lambda x:x["score"])
        delta = pk["score"] - score_now
        sp_rows.append({**s,"now":score_now,"peak":pk["score"],"delta":delta,
                        "pk_mo":f"{pk['ym'][0]}-{pk['ym'][1]:02d}"})

    # Fetch prices only for the top-shift candidates (to limit fetches)
    sp_rows.sort(key=lambda r: -r["delta"])
    top_shift = sp_rows[:80]
    quiet = []
    for r in top_shift:
        pm = price_metrics(fetch_prices(r["tk"]))
        r["chg3"] = pm.get("chg_3mo"); r["chg12"] = pm.get("chg_12mo")
        r["from_low"] = pm.get("from_low_12"); r["last"] = pm.get("last_close")
        if r["chg12"] is None: continue
        if abs(r["chg12"]) <= 25 or (r["from_low"] is not None and r["from_low"] <= 25):
            quiet.append(r)

    print(f"\n{'='*180}")
    print(f"(B) SP500 BIG 12-MONTH SHIFT + PRICE QUIET — re-scanned {TODAY}")
    print(f"{'='*180}")
    print(f"{'#':>3s} {'Tkr':<6s} {'GICS':<22s} {'Now':>5s}→{'Pk':>5s}  {'Δ':>5s}  {'PkMo':<8s} {'pr3mo':>6s} {'pr12mo':>7s} {'fLow':>6s}  Name")
    for i, r in enumerate(quiet[:30], 1):
        nm = (r["name"] or "")[:20]
        gics = (r["sector"] or "")[:21]
        c3 = f"{r['chg3']:+5.0f}%" if r['chg3'] is not None else "   n/a"
        c12 = f"{r['chg12']:+5.0f}%" if r['chg12'] is not None else "   n/a"
        fl = f"{r['from_low']:+5.0f}%" if r['from_low'] is not None else "  n/a"
        print(f"{i:3d} {r['tk']:<6s} {gics:<22s} {r['now']:>+4.0f}→{r['peak']:>+4.0f}  +{r['delta']:>4.0f}  {r['pk_mo']:<8s} {c3:>6s} {c12:>7s} {fl:>6s}  {nm}")

    with open("/home/user/cyclepapa/data/best_opps_jul2026_sp500.csv","w",newline="") as f:
        w = csv.writer(f)
        w.writerow(["rank","ticker","name","sector","ipo","score_now","score_peak","delta","peak_month",
                    "chg_3mo","chg_12mo","from_low_12","last_close"])
        for i, r in enumerate(quiet, 1):
            w.writerow([i,r["tk"],r["name"],r["sector"],r["ipo"],
                        f"{r['now']:+.1f}",f"{r['peak']:+.1f}",f"{r['delta']:+.1f}",r["pk_mo"],
                        f"{r['chg3']:+.1f}" if r['chg3'] is not None else "",
                        f"{r['chg12']:+.1f}" if r['chg12'] is not None else "",
                        f"{r['from_low']:+.1f}" if r['from_low'] is not None else "",
                        f"{r['last']:.2f}" if r.get('last') is not None else ""])

    print(f"\nExported: data/best_opps_jul2026_spec.csv + data/best_opps_jul2026_sp500.csv")

if __name__ == "__main__":
    main()
