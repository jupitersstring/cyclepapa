"""
THEORY ↔ EMPIRICAL RECONCILIATION

For named stocks across our framework, compute:
  1. Natal signature scores per our theories
  2. Actual historical max-multiple from price data
  3. Reconcile: do the theories' predictions match the realised moves?

Theories tested:
  T1. AVIS-DNA — natal Sun-Neptune ≤5° conjunction
  T2. GC amp — natal outer ≤3° from 267° (Galactic Center)
  T3. Saturn-Neptune Bat — natal Saturn-Neptune at 41° (0.886)
  T4. Mars-Jupiter Butterfly — natal Mars-Jupiter at 98° (1.272)
  T5. Jupiter-Uranus Gartley — natal Jupiter-Uranus at 77° (0.786)
  T6. Uranus-Pluto Septile — natal Uranus-Pluto at 51.4° (the empirical winner)
  T7. Uranus-Pluto Sextile — natal at 60° (the empirical magnitude amplifier)
  T8. Neptune-Pluto Sextile — natal at 60° (broad 1980s-2000s amplifier)
  T9. Stellium — natal 4+ planets within 15°

Picks tested:
  Known parabolic blow-offs from corpus:    GME, AMC, NVDA (since 2016)
  Recent multi-baggers:                     PLTR, APP, SMCI, CVNA, HIMS
  v25 current top picks:                    NXPI, KVYO, NFLX, IVZ, TER
  AVIS-DNA flagged:                         ALAB, CRH, FISV, ERIE, INCY
  CAR analog flagged:                       CHRW, HON, MOS, BLDR
"""
import csv, os, json, subprocess
from datetime import datetime, timezone
from bti_test import compute_natal
from bti_v19_empirical import closest_hard

def aspect_orb(a, b, target):
    d = (a - b) % 360
    return min(abs(d - target), abs(d - (360 - target)))

def conj_orb(a, b):
    d = abs(a - b) % 360
    return min(d, 360 - d)

def fetch_yahoo_max_multiple(tk):
    """Fetch full Yahoo daily history and return (low, high, multiple)."""
    cache = f"/home/user/cyclepapa/data/prices_full/{tk}.csv"
    os.makedirs(os.path.dirname(cache), exist_ok=True)
    if os.path.exists(cache):
        prices = []
        with open(cache) as f:
            next(f)
            for line in f:
                p = line.strip().split(",")
                if len(p) == 2:
                    try: prices.append((p[0], float(p[1])))
                    except: pass
    else:
        # Fetch from earliest possible
        p1 = int(datetime(1990, 1, 1, tzinfo=timezone.utc).timestamp())
        p2 = int(datetime(2026, 4, 22, tzinfo=timezone.utc).timestamp())
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{tk}?period1={p1}&period2={p2}&interval=1d"
        try:
            out = subprocess.run(["curl","-sL","-H","User-Agent: Mozilla/5.0","-m","20",url],
                                  capture_output=True, text=True, timeout=25).stdout
            j = json.loads(out)
            r = j.get("chart",{}).get("result")
            if not r: return None
            ts = r[0]["timestamp"]; cs = r[0]["indicators"]["quote"][0]["close"]
            prices = [(datetime.utcfromtimestamp(t).strftime("%Y-%m-%d"), c) for t,c in zip(ts,cs) if c]
            if prices:
                with open(cache, "w") as f:
                    f.write("date,close\n")
                    for d,c in prices: f.write(f"{d},{c:.4f}\n")
        except: return None
    if not prices: return None
    # Find lifetime low and subsequent high (parabolic test)
    lows_then_highs = []
    for i, (d_low, c_low) in enumerate(prices):
        if c_low <= 0: continue
        future = prices[i:]
        if not future: continue
        max_high = max(c for _,c in future)
        max_idx = max(range(len(future)), key=lambda j: future[j][1])
        d_high = future[max_idx][0]
        mult = max_high / c_low
        lows_then_highs.append((d_low, c_low, d_high, max_high, mult))
    if not lows_then_highs: return None
    best = max(lows_then_highs, key=lambda x: x[4])
    return {
        "first_date": prices[0][0],
        "first_close": prices[0][1],
        "last_close": prices[-1][1],
        "best_low_date": best[0], "best_low": best[1],
        "best_high_date": best[2], "best_high": best[3],
        "max_multiple": best[4],
    }

# Stock list with our theoretical IPO dates
PICKS = [
    # (ticker, ipo_date, category)
    ("GME","2002-02-13","known meme"),
    ("AMC","2013-12-18","known meme"),
    ("NVDA","1999-01-22","megacap"),
    ("PLTR","2020-09-30","recent multi-bagger"),
    ("APP","2021-04-15","recent multi-bagger (961% in backtest)"),
    ("SMCI","2007-03-29","AI compute multi-bagger"),
    ("CVNA","2017-04-28","retail multi-bagger"),
    ("HIMS","2021-01-21","health"),
    ("WDC","1976-08-31","backtest 617% winner"),
    ("CHRW","1997-10-15","CAR-analog flagged"),
    ("HON","1999-12-01","CAR-analog flagged"),
    ("MOS","2011-09-26","Neptune-hype"),
    ("BLDR","2005-06-22","compression-release flagged"),
    ("NXPI","2010-08-05","SEMIS top pick"),
    ("TER","2020-09-21","SEMIS pick"),
    ("KVYO","2023-09-20","TECH new IPO"),
    ("IVZ","2008-08-21","FINANCE top pick"),
    ("NFLX","2002-05-23","STREAMING pick"),
    ("ALAB","2024-03-20","AVIS-DNA structural twin"),
    ("CRH","2025-12-22","AVIS-DNA fresh IPO"),
    ("FISV","1986-09-25","AVIS-DNA"),
    ("INCY","1993-11-05","BIOPHARM, real IPO date"),
    ("DECK","1993-10-14","luxury"),
    ("DASH","2020-12-09","new media"),
    ("META","2012-05-18","megacap"),
    ("TSLA","2010-06-29","megacap"),
]

def compute_signatures(natal):
    """Compute all 9 theory signature flags + scores."""
    sigs = {}
    sun = natal["Sun"]["lon"]
    moon = natal["Moon"]["lon"]
    nep = natal["Neptune"]["lon"]
    sat = natal["Saturn"]["lon"]
    ura = natal["Uranus"]["lon"]
    plu = natal["Pluto"]["lon"]
    jup = natal["Jupiter"]["lon"]
    mars = natal["Mars"]["lon"]
    asc = natal.get("ASC", {}).get("lon", None)
    mc = natal.get("MC", {}).get("lon", None)

    sigs["AVIS_DNA"] = conj_orb(sun, nep)
    # GC: 267° Sag
    GC = 267.0
    gc_orbs = [closest_hard(p, GC) for p in (jup, sat, ura, nep, plu)]
    sigs["GC_min"] = min(gc_orbs)
    sigs["SatNep_Bat"] = aspect_orb(sat, nep, 41.04)
    sigs["MarJup_Butt"] = aspect_orb(mars, jup, 97.92)
    sigs["JupUra_Gart"] = aspect_orb(jup, ura, 77.04)
    sigs["UraPlu_Septile"] = aspect_orb(ura, plu, 51.43)
    sigs["UraPlu_Sextile"] = aspect_orb(ura, plu, 60.0)
    sigs["NepPlu_Sextile"] = aspect_orb(nep, plu, 60.0)
    # Stellium: max cluster within 15°
    positions = [sun, moon, mars, jup, sat, ura, nep, plu]
    if asc: positions.append(asc)
    if mc: positions.append(mc)
    best = 0
    for p in positions:
        c = sum(1 for q in positions if min(abs(q-p), 360-abs(q-p)) <= 15)
        if c > best: best = c
    sigs["Stellium"] = best
    return sigs

def main():
    print(f"{'='*200}")
    print(f"THEORY-EMPIRICAL RECONCILIATION — natal signatures and realised max-multiples")
    print(f"{'='*200}")
    rows = []
    for tk, ipo, cat in PICKS:
        try:
            natal = compute_natal(ipo)
            sigs = compute_signatures(natal)
            mult_data = fetch_yahoo_max_multiple(tk)
            rows.append({"tk":tk,"ipo":ipo,"cat":cat,"sigs":sigs,"mult":mult_data})
        except Exception as e:
            print(f"  {tk} fail: {e}")

    # Header
    print(f"\n{'Tkr':<6s} {'IPO':<11s} {'Category':<32s} | {'AVIS':>4s} {'GC':>4s} {'SaNeBat':>7s} {'MaJuBu':>6s} "
          f"{'JuUrGa':>6s} {'UrPlSep':>7s} {'UrPlSx':>6s} {'NePlSx':>6s} {'Stell':>5s} | {'Max Mult':>8s} {'Low':<10s} {'High':<10s}")
    for r in rows:
        s = r["sigs"]
        m = r["mult"]
        if m:
            mt = f"{m['max_multiple']:>7.1f}×"
            ld = m["best_low_date"]
            hd = m["best_high_date"]
        else:
            mt = "    n/a"
            ld = hd = ""
        # Mark each signature: ★ if active (within key threshold)
        avis_t = "★" if s["AVIS_DNA"] <= 5 else f"{s['AVIS_DNA']:.0f}"
        gc_t = "★" if s["GC_min"] <= 3 else f"{s['GC_min']:.0f}"
        bat_t = "★" if s["SatNep_Bat"] <= 3 else f"{s['SatNep_Bat']:.0f}"
        butt_t = "★" if s["MarJup_Butt"] <= 3 else f"{s['MarJup_Butt']:.0f}"
        gart_t = "★" if s["JupUra_Gart"] <= 3 else f"{s['JupUra_Gart']:.0f}"
        sept_t = "★" if s["UraPlu_Septile"] <= 3 else f"{s['UraPlu_Septile']:.0f}"
        sxt_t = "★" if s["UraPlu_Sextile"] <= 3 else f"{s['UraPlu_Sextile']:.0f}"
        npsxt_t = "★" if s["NepPlu_Sextile"] <= 3 else f"{s['NepPlu_Sextile']:.0f}"
        stell_t = f"{s['Stellium']}"
        print(f"{r['tk']:<6s} {r['ipo']:<11s} {r['cat'][:31]:<32s} | "
              f"{avis_t:>4s} {gc_t:>4s} {bat_t:>7s} {butt_t:>6s} "
              f"{gart_t:>6s} {sept_t:>7s} {sxt_t:>6s} {npsxt_t:>6s} {stell_t:>5s} | "
              f"{mt:>8s} {ld:<10s} {hd:<10s}")

    # Summarise: which theories activated for the BIGGEST movers?
    print(f"\n{'='*100}")
    print(f"  Stocks ranked by realised max-multiple — which natal theories activated?")
    print(f"{'='*100}")
    rows_with_data = [r for r in rows if r["mult"]]
    rows_with_data.sort(key=lambda r: -r["mult"]["max_multiple"])
    for r in rows_with_data[:15]:
        s = r["sigs"]
        active = []
        if s["AVIS_DNA"] <= 5: active.append(f"AVIS-DNA({s['AVIS_DNA']:.1f}°)")
        if s["GC_min"] <= 3: active.append(f"GC({s['GC_min']:.1f}°)")
        if s["SatNep_Bat"] <= 3: active.append(f"SatNepBat({s['SatNep_Bat']:.1f}°)")
        if s["MarJup_Butt"] <= 3: active.append(f"MarJupButt({s['MarJup_Butt']:.1f}°)")
        if s["JupUra_Gart"] <= 3: active.append(f"JupUraGart({s['JupUra_Gart']:.1f}°)")
        if s["UraPlu_Septile"] <= 3: active.append(f"UrPluSept({s['UraPlu_Septile']:.1f}°)")
        if s["UraPlu_Sextile"] <= 3: active.append(f"UrPluSxt({s['UraPlu_Sextile']:.1f}°)")
        if s["NepPlu_Sextile"] <= 3: active.append(f"NePluSxt({s['NepPlu_Sextile']:.1f}°)")
        if s["Stellium"] >= 4: active.append(f"Stellium({s['Stellium']})")
        active_str = ", ".join(active) if active else "(none)"
        print(f"  {r['tk']:<6s} {r['mult']['max_multiple']:>7.1f}×  {r['cat'][:32]:<32s}  active: {active_str}")

    # Predicted vs realised correlation
    print(f"\n{'='*100}")
    print(f"  Theory aggregation — count of active signatures vs realised multiple")
    print(f"{'='*100}")
    for r in rows_with_data:
        n_active = sum([
            r["sigs"]["AVIS_DNA"] <= 5,
            r["sigs"]["GC_min"] <= 3,
            r["sigs"]["SatNep_Bat"] <= 3,
            r["sigs"]["MarJup_Butt"] <= 3,
            r["sigs"]["JupUra_Gart"] <= 3,
            r["sigs"]["UraPlu_Septile"] <= 3,
            r["sigs"]["UraPlu_Sextile"] <= 3,
            r["sigs"]["NepPlu_Sextile"] <= 3,
            r["sigs"]["Stellium"] >= 4,
        ])
        r["n_active"] = n_active
    rows_with_data.sort(key=lambda r: -r["n_active"])
    print(f"  {'Tkr':<6s} {'#Sigs':>5s}  {'MaxMult':>8s}  {'Cat':<35s}")
    for r in rows_with_data:
        print(f"  {r['tk']:<6s} {r['n_active']:>5d}  {r['mult']['max_multiple']:>7.1f}×  {r['cat'][:35]}")

if __name__ == "__main__":
    main()
