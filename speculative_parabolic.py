"""
Off-SP500 speculative parabolic R/R scanner.

Targets the broader Ritter universe for genuinely-explosive (5x+ capable)
candidates that the SP500 framework misses by definition.

Target buckets:
  AI_QUANTUM   — IONQ, RGTI, QBTS, PLTR, BBAI, SOUN, ALAB, CRWV
  URANIUM      — NXE, OKLO, CCJ, UEC, UUUU, URA, URNM, DNN, LEU
  NUCLEAR_GEN  — CEG, VST, SMR, NNE, TLN
  SPACE        — RKLB, ASTS, LUNR, IRDM, KTOS, AVAV
  BIOTECH_SMALL — anything with Pluto-Sun/Moon tight + young chart
  FRESH_IPO    — anything IPO >= 2022 with AVIS-DNA or multi-aspect convergence

Filters:
  - Age 0-7 years (young chart, plastic identity)
  - Tradeable (we have price data or can fetch)
  - Sector aligned with macro regime (Uranus-Gemini, Pluto-Aquarius)

Scoring layers:
  1. Event-study delta sum (today + 3mo + 6mo + 12mo forward)
  2. AVIS-DNA bonus (natal Sun-Neptune ≤5°): x1.5
  3. Galactic Center bonus (natal outer ≤3° of 267°): x1.4
  4. Uranus-Gemini macro sector boost (1.5-2.0×)
  5. Current Neptune-Sun/Moon active bonus (+50)
  6. Pluto-Sun/Moon active (small-cap biotech catalyst)
  7. Bubblish multi-aspect (3+ outers within 5°): +30
  8. Penalty for already-elevated: score >= 100 today → -30%
"""
import csv, math, pickle, sys, os, subprocess, json, time
from datetime import datetime, timezone, timedelta
import statistics as st
import swisseph as swe
from bti_test import compute_natal
from bti_v19_empirical import closest_hard

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

# Curated tradeable off-SP500 speculative universe
SPECULATIVE_TICKERS = {
    # AI / QUANTUM
    "IONQ":"AI_QUANTUM","RGTI":"AI_QUANTUM","QBTS":"AI_QUANTUM",
    "BBAI":"AI_QUANTUM","SOUN":"AI_QUANTUM","ALAB":"AI_QUANTUM",
    "CRWV":"AI_QUANTUM","PLTR":"AI_QUANTUM","AI":"AI_QUANTUM",
    "ARM":"AI_QUANTUM","SMCI":"AI_QUANTUM","ANET":"AI_QUANTUM",
    "TEM":"AI_QUANTUM","RKLB":"SPACE",
    # URANIUM
    "NXE":"URANIUM","UEC":"URANIUM","UUUU":"URANIUM","DNN":"URANIUM",
    "LEU":"URANIUM","URG":"URANIUM","URA":"URANIUM","URNM":"URANIUM",
    "CCJ":"URANIUM","SLOW":"URANIUM","ASPI":"URANIUM",
    # NUCLEAR
    "CEG":"NUCLEAR","VST":"NUCLEAR","SMR":"NUCLEAR","OKLO":"NUCLEAR",
    "NNE":"NUCLEAR","TLN":"NUCLEAR","NPWR":"NUCLEAR",
    # SPACE/DRONES
    "ASTS":"SPACE","LUNR":"SPACE","KTOS":"DRONES","AVAV":"DRONES",
    "IRDM":"SATELLITES","SATS":"SATELLITES","ACHR":"AUTONOMOUS","JOBY":"AUTONOMOUS",
    # SMALL BIOTECH (speculative)
    "VKTX":"BIOTECH","BNTX":"BIOTECH","ARCT":"BIOTECH","CRSP":"BIOTECH",
    "NTLA":"BIOTECH","BEAM":"BIOTECH","EDIT":"BIOTECH","SGMO":"BIOTECH",
    "VOR":"BIOTECH","RXRX":"BIOTECH","RCEL":"BIOTECH","ABOS":"BIOTECH",
    "MIST":"BIOTECH","CRDF":"BIOTECH","IMGN":"BIOTECH","TGTX":"BIOTECH",
    # EV / NEW MOBILITY
    "RIVN":"EV","LCID":"EV","NIO":"EV","XPEV":"EV","LI":"EV",
    # CRYPTO INFRA
    "MSTR":"CRYPTO","COIN":"CRYPTO","MARA":"CRYPTO","RIOT":"CRYPTO",
    "CLSK":"CRYPTO","HUT":"CRYPTO","WULF":"CRYPTO","BTBT":"CRYPTO",
    # FRESH/IPO and meme-capable
    "GME":"MEME","AMC":"MEME","BBBY":"MEME","NVTS":"FRESH",
    "HIMS":"HEALTH","RDDT":"FRESH","CRH":"FRESH","NBIS":"FRESH",
    "RBRK":"CYBERSEC","S":"CYBERSEC","SNOW":"TECH","NET":"TECH",
    # AI-adjacent and growth
    "APP":"AI_QUANTUM","DUOL":"TECH","INGM":"TECH","KVYO":"TECH",
    "HOOD":"FINANCE","SOFI":"FINANCE","UPST":"FINANCE","AFRM":"FINANCE",
    "MELI":"TECH","SE":"TECH","CVNA":"AUTO_RETAIL","HCAT":"HEALTH",
    # EV/SOLAR/CLEAN
    "ENPH":"CLEAN","SEDG":"CLEAN","FSLR":"CLEAN","PLUG":"CLEAN",
    "BE":"CLEAN","NOVA":"CLEAN","STEM":"CLEAN",
    # Other speculative growth
    "ROOT":"FINANCE","OPEN":"FINTECH","DNUT":"RETAIL","CART":"RETAIL",
}

# Macro multipliers (April 2026)
MACRO_MULTIPLIER = {
    "AI_QUANTUM":1.89,"URANIUM":2.32,"NUCLEAR":2.23,"SPACE":1.85,
    "DRONES":1.85,"SATELLITES":1.85,"BIOTECH":1.15,"EV":1.15,
    "AUTONOMOUS":1.30,"CRYPTO":1.10,"CYBERSEC":1.25,"TECH":1.50,
    "MEME":0.75,"FRESH":1.10,"HEALTH":1.10,"FINANCE":1.05,
    "AUTO_RETAIL":1.00,"CLEAN":1.30,"FINTECH":1.05,"RETAIL":0.95,
}

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

def fetch_or_load_recent(tk):
    cache_dir = "/home/user/cyclepapa/data/prices_full"
    cache = f"{cache_dir}/{tk}.csv"
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
    p1 = int(datetime(2018,1,1,tzinfo=timezone.utc).timestamp())
    p2 = int(datetime(2026,4,22,tzinfo=timezone.utc).timestamp())
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
            os.makedirs(cache_dir, exist_ok=True)
            with open(cache,"w") as f:
                f.write("date,close\n")
                for d,c in prices: f.write(f"{d},{c:.4f}\n")
        return prices
    except: return []

def price_metrics(prices):
    if not prices: return None
    last_d, last_c = prices[-1]
    last_dt = datetime.strptime(last_d, "%Y-%m-%d")
    pdict = dict(prices)
    metrics = {}
    for days_back, label in [(90,"chg_3mo"),(180,"chg_6mo"),(365,"chg_12mo")]:
        target = (last_dt - timedelta(days=days_back)).strftime("%Y-%m-%d")
        base = None
        for off in range(15):
            check = (last_dt - timedelta(days=days_back-off)).strftime("%Y-%m-%d")
            if check in pdict: base = pdict[check]; break
        if base and base > 0:
            metrics[label] = (last_c/base - 1)*100
    # % above low
    for days, label in [(365,"from_low_12"),(730,"from_low_24")]:
        cutoff = (last_dt - timedelta(days=days)).strftime("%Y-%m-%d")
        recent = [(d,c) for (d,c) in prices if d >= cutoff]
        if recent:
            low = min(c for _,c in recent)
            metrics[label] = (last_c/low - 1)*100
    metrics["last_close"] = last_c
    return metrics

def main():
    print("Loading event-study keys...", file=sys.stderr)
    with open("/home/user/cyclepapa/data/event_study_keys.pkl","rb") as f:
        key_stats = pickle.load(f)
    valid_keys = {k:v for k,v in key_stats.items()
                  if v.get("n_w",0)>=10 and v.get("n_c",0)>=5
                  and "delta_365" in v}

    # Load IPO dates for our speculative universe from universe_bti_v20.csv
    print("Looking up IPO dates...", file=sys.stderr)
    ipo_lookup = {}
    with open("/home/user/cyclepapa/data/universe_bti_v20.csv") as f:
        for r in csv.DictReader(f):
            tk = (r.get("ticker") or "").strip().upper()
            ipo = (r.get("ipo") or "").strip()
            nm = (r.get("name") or "").strip()
            if tk in SPECULATIVE_TICKERS and ipo and len(ipo) >= 10:
                # Take first non-misdated
                if tk not in ipo_lookup or "2025-03-24" not in ipo:
                    ipo_lookup[tk] = {"ipo":ipo,"name":nm}

    # Add manual overrides for known misdates
    manual_overrides = {
        "COIN":{"ipo":"2021-04-14","name":"Coinbase"},
        "RDDT":{"ipo":"2024-03-21","name":"Reddit"},
        "ALAB":{"ipo":"2024-03-20","name":"Astera Labs"},
        "CRWV":{"ipo":"2025-03-28","name":"CoreWeave"},
        "OKLO":{"ipo":"2024-05-10","name":"Oklo"},
        "NNE":{"ipo":"2024-05-08","name":"Nano Nuclear"},
        "SMR":{"ipo":"2022-05-03","name":"NuScale Power"},
        "CRH":{"ipo":"2025-12-22","name":"CRH plc"},
        "RDDT":{"ipo":"2024-03-21","name":"Reddit"},
        "TEM":{"ipo":"2024-06-14","name":"Tempus AI"},
        "AI":{"ipo":"2020-12-09","name":"C3.ai"},
        "ARM":{"ipo":"2023-09-14","name":"Arm Holdings"},
        "RGTI":{"ipo":"2022-03-02","name":"Rigetti Computing"},
        "QBTS":{"ipo":"2022-08-08","name":"D-Wave Quantum"},
        "IONQ":{"ipo":"2021-10-01","name":"IonQ"},
        "ASPI":{"ipo":"2024-02-15","name":"ASP Isotopes"},
        "NBIS":{"ipo":"2024-10-21","name":"Nebius Group"},
    }
    for tk, info in manual_overrides.items():
        ipo_lookup[tk] = info

    # Today's positions
    today_jd = date_jd(2026, 4, 22)
    today_lons = planet_lons(today_jd)

    # Forward months
    months = []
    y, m = 2026, 4
    for _ in range(24):
        months.append((y,m))
        m += 1
        if m > 12: m = 1; y += 1
    monthly_lons = {(y,m): planet_lons(date_jd(y,m)) for y,m in months}

    print("Scanning speculative universe...", file=sys.stderr)
    rows = []
    for tk, sector in SPECULATIVE_TICKERS.items():
        if tk not in ipo_lookup:
            print(f"  {tk} no IPO date — skipping", file=sys.stderr)
            continue
        ipo = ipo_lookup[tk]["ipo"]
        name = ipo_lookup[tk]["name"]
        try:
            ipo_y = int(ipo[:4])
            age = 2026 - ipo_y
            natal = compute_natal(ipo)
        except: continue

        # Event-study score now and forward
        score_now, actives_now = chart_event_score(natal, today_lons, valid_keys)
        scores_fwd = []
        for ym in months[:13]:
            sc, _ = chart_event_score(natal, monthly_lons[ym], valid_keys)
            scores_fwd.append({"y":ym[0],"m":ym[1],"score":sc})
        peak_fwd = max(scores_fwd, key=lambda x:x["score"])
        score_max = peak_fwd["score"]
        delta_max = score_max - score_now

        # AVIS-DNA: natal Sun-Neptune ≤5° conjunction
        sun_n = natal["Sun"]["lon"]; nep_n = natal["Neptune"]["lon"]
        avis_dna_orb = conj_orb(sun_n, nep_n)
        avis_dna = avis_dna_orb <= 5

        # GC: outer ≤3° of 267°
        gc_min = min(closest_hard(natal[p]["lon"], GC_LON)
                     for p in ("Jupiter","Saturn","Uranus","Neptune","Pluto") if p in natal)
        gc_amp = gc_min <= 3

        # Current Neptune-Sun/Moon active
        nep_now = today_lons["Neptune"]
        nep_sun = closest_hard(nep_now, sun_n)
        nep_moon = closest_hard(nep_now, natal["Moon"]["lon"]) if "Moon" in natal else 99
        nep_active = nep_sun <= 3 or nep_moon <= 3

        # Current Pluto-Sun/Moon active (transformation catalyst)
        plu_now = today_lons["Pluto"]
        plu_sun = closest_hard(plu_now, sun_n)
        plu_moon = closest_hard(plu_now, natal["Moon"]["lon"]) if "Moon" in natal else 99
        plu_active = plu_sun <= 3 or plu_moon <= 3

        # Multi-outer bubblish
        n_outer_tight = sum(1 for p in ("Jupiter","Saturn","Uranus","Neptune","Pluto")
                            if min((closest_hard(today_lons[p], natal[pt]["lon"])
                                   for pt in NATAL_PTS if pt in natal), default=99) <= 5)

        # Compose convexity score
        macro = MACRO_MULTIPLIER.get(sector, 1.0)
        convexity = (score_now + delta_max * 1.5) * macro
        if avis_dna: convexity *= 1.5
        if gc_amp: convexity *= 1.4
        if nep_active: convexity += 50
        if plu_active: convexity += 40
        if n_outer_tight >= 3: convexity += 30
        if age <= 5: convexity *= 1.2  # plastic-identity bonus
        # Penalize if already elevated (already running)
        if score_now > 100: convexity *= 0.7

        # Price data
        prices = fetch_or_load_recent(tk)
        pm = price_metrics(prices) if prices else {}
        chg_12 = pm.get("chg_12mo")
        from_low_24 = pm.get("from_low_24")
        last_price = pm.get("last_close")

        rows.append({"tk":tk,"name":name,"sector":sector,"ipo":ipo,"age":age,
                     "score_now":score_now,"score_max":score_max,
                     "delta_max":delta_max,
                     "peak_month":f"{peak_fwd['y']}-{peak_fwd['m']:02d}",
                     "macro":macro,"convexity":convexity,
                     "avis_dna":avis_dna,"gc_amp":gc_amp,
                     "nep_sun":nep_sun,"nep_moon":nep_moon,"nep_active":nep_active,
                     "plu_sun":plu_sun,"plu_moon":plu_moon,"plu_active":plu_active,
                     "n_tight":n_outer_tight,
                     "chg_12mo":chg_12,"from_low_24":from_low_24,
                     "last_price":last_price})

    # Rank by convexity score
    rows.sort(key=lambda r: -r["convexity"])

    print(f"\n{'='*220}")
    print(f"OFF-SP500 PARABOLIC R/R CANDIDATES — composite convexity score")
    print(f"  Score combines: event-study delta forward + AVIS-DNA + GC + macro × sector + Neptune/Pluto activation + multi-aspect + age bonus - elevated penalty")
    print(f"{'='*220}")
    print(f"{'Rk':>3s} {'Tkr':<5s} {'ModSec':<13s} {'Age':>3s} {'Now':>4s} {'Pk':>4s} {'Δ':>4s} {'PkMo':<8s} {'Mac':>4s} {'AVI':>3s} {'GC':>3s} {'NpSn':>5s} {'NpMo':>5s} {'PlSn':>5s} {'#tt':>3s} {'pr12':>5s} {'$':>5s} {'CVX':>6s}  Name")
    for i, r in enumerate(rows[:40], 1):
        nm = (r["name"] or "")[:18]
        avi = "★" if r["avis_dna"] else f"{conj_orb(0,0):.0f}"  # dummy
        avi_t = "★" if r["avis_dna"] else " "
        gc_t = "★" if r["gc_amp"] else " "
        chg12 = f"{r['chg_12mo']:+4.0f}%" if r['chg_12mo'] is not None else "  n/a"
        price = f"{r['last_price']:5.1f}" if r['last_price'] is not None else "  n/a"
        print(f"{i:3d} {r['tk']:<5s} {r['sector']:<13s} {r['age']:>3d} "
              f"{r['score_now']:>+3.0f} {r['score_max']:>+3.0f} +{r['delta_max']:>3.0f} {r['peak_month']:<8s} "
              f"{r['macro']:>4.2f} {avi_t:>3s} {gc_t:>3s} "
              f"{r['nep_sun']:>4.1f}° {r['nep_moon']:>4.1f}° {r['plu_sun']:>4.1f}° "
              f"{r['n_tight']:>3d} {chg12:>5s} {price:>5s} {r['convexity']:>+6.0f}  {nm}")

    # Tier breakdown by sector
    print(f"\n{'='*120}")
    print(f"TOP 5 PER MACRO-FAVORED SECTOR")
    print(f"{'='*120}")
    HIGH_MACRO_SECTORS = ["AI_QUANTUM","URANIUM","NUCLEAR","SPACE","DRONES","CYBERSEC","CLEAN","TECH","BIOTECH","EV","CRYPTO","MEME"]
    from collections import defaultdict
    by_sec = defaultdict(list)
    for r in rows: by_sec[r["sector"]].append(r)
    for sec in HIGH_MACRO_SECTORS:
        sub = by_sec.get(sec, [])
        if not sub: continue
        sub.sort(key=lambda r:-r["convexity"])
        print(f"\n  {sec} (macro {MACRO_MULTIPLIER.get(sec,1.0):.2f}×):")
        for r in sub[:5]:
            chg = f"{r['chg_12mo']:+5.0f}%" if r['chg_12mo'] is not None else "  n/a"
            print(f"    {r['tk']:<6s} Age{r['age']:>2d}  Score {r['score_now']:>+4.0f}→{r['score_max']:>+4.0f} "
                  f"(+{r['delta_max']:>3.0f})  Peak {r['peak_month']}  AVIS:{r['avis_dna']!s:<5s}  GC:{r['gc_amp']!s:<5s}  "
                  f"NepSun:{r['nep_sun']:>4.1f}°  pr12:{chg}  Conv:{r['convexity']:>+6.0f}  ({r['name']})")

    # Export
    with open("/home/user/cyclepapa/data/speculative_parabolic.csv","w",newline="") as f:
        w = csv.writer(f)
        w.writerow(["rank","ticker","name","sector","ipo","age","score_now","score_max","delta_max","peak_month",
                    "macro","avis_dna_orb","gc_min_orb","nep_sun_orb","nep_moon_orb","plu_sun_orb","n_tight_outers",
                    "price_chg_12mo","pct_above_24mo_low","last_close","convexity"])
        for i, r in enumerate(rows, 1):
            w.writerow([i,r["tk"],r["name"],r["sector"],r["ipo"],r["age"],
                        f"{r['score_now']:+.1f}",f"{r['score_max']:+.1f}",f"{r['delta_max']:+.1f}",
                        r["peak_month"],f"{r['macro']:.2f}",
                        f"{(0 if r['avis_dna'] else 99):.1f}",
                        "0" if r['gc_amp'] else "99",
                        f"{r['nep_sun']:.2f}",f"{r['nep_moon']:.2f}",f"{r['plu_sun']:.2f}",
                        r["n_tight"],
                        f"{r['chg_12mo']:+.1f}" if r['chg_12mo'] is not None else "",
                        f"{r['from_low_24']:+.1f}" if r['from_low_24'] is not None else "",
                        f"{r['last_price']:.2f}" if r['last_price'] is not None else "",
                        f"{r['convexity']:+.1f}"])
    print(f"\nExported -> data/speculative_parabolic.csv")

if __name__ == "__main__":
    main()
