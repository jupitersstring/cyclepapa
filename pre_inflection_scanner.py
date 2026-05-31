"""
PRE-INFLECTION SIGNATURE SCANNER.

Different question: not 'what aspects predict 12mo return' but specifically
'what aspect conditions cluster in the 3-6 months BEFORE explosive inflections'.

Process:
  1. In our panel (winners + controls), find every 'explosive inflection':
     a date where price had FORWARD 6-month return >= +100% (doubling).
  2. Look 3 months and 6 months BEFORE each inflection.
  3. Aggregate aspect activations during these pre-inflection windows.
  4. Compare to baseline of random non-pre-inflection months.
  5. Identify the strongest 'pre-inflection signature' aspects.
  6. Scan SP500 today: stocks with these signatures active NOW.

Outputs:
  - Pre-inflection signature ranking
  - SP500 ranked by today's match to this signature
"""
import csv, math, pickle, sys, time
import statistics as st
from datetime import datetime, timedelta
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

def date_jd(date_str):
    y,m,d=map(int,date_str.split("-"))
    return swe.julday(y,m,d,12.0)

def jd_date(jd):
    cal=swe.revjul(jd)
    return f"{int(cal[0]):04d}-{int(cal[1]):02d}-{int(cal[2]):02d}"

def planet_lons_at(jd):
    return {p: swe.calc_ut(jd, pid)[0][0] % 360 for p, pid in PIDS.items()}

PANEL = [
    # Winners
    ("AAPL","1980-12-12"),("MSFT","1986-03-13"),("NVDA","1999-01-22"),
    ("AMZN","1997-05-15"),("GOOG","2004-08-19"),("META","2012-05-18"),
    ("TSLA","2010-06-29"),("NFLX","2002-05-23"),("GME","2002-02-13"),
    ("AMC","2013-12-18"),("PLTR","2020-09-30"),("APP","2021-04-15"),
    ("SMCI","2007-03-29"),("WDC","1976-08-31"),("CHRW","1997-10-15"),
    ("BLDR","2005-06-22"),("DECK","1993-10-14"),("FISV","1986-09-25"),
    ("INCY","1993-11-05"),
    # Controls
    ("WBA","1909-09-15"),("INTC","1971-10-13"),("BA","1962-01-02"),
    ("F","1956-01-17"),("XRX","1961-11-30"),("KHC","2015-07-06"),
    ("MMM","1946-01-14"),("VZ","1984-11-21"),("T","1983-07-19"),
    ("CVS","1996-02-08"),("PFE","1942-06-23"),("DIS","1957-11-12"),
    ("BIIB","1991-09-13"),("WBD","2022-04-11"),
]

def load_prices(tk):
    cache = f"/home/user/cyclepapa/data/prices_full/{tk}.csv"
    if not __import__("os").path.exists(cache): return []
    prices = []
    with open(cache) as f:
        next(f)
        for line in f:
            p = line.strip().split(",")
            if len(p)==2:
                try: prices.append((p[0], float(p[1])))
                except: pass
    return prices

def find_explosive_inflections(prices, forward_days=180, threshold=2.0):
    """Find dates where price doubles over the next 6 months."""
    pdict = dict(prices)
    inflections = []
    for i, (d, c) in enumerate(prices):
        target_dt = datetime.strptime(d, "%Y-%m-%d") + timedelta(days=forward_days)
        target = target_dt.strftime("%Y-%m-%d")
        forward_close = None
        for off in range(15):
            check = (datetime.strptime(target, "%Y-%m-%d") + timedelta(days=off)).strftime("%Y-%m-%d")
            if check in pdict: forward_close = pdict[check]; break
        if forward_close is None: continue
        ratio = forward_close / c
        if ratio >= threshold:
            inflections.append({"date":d, "ratio":ratio, "fwd_date":target})
    # Dedupe: only keep one inflection per 90-day window (the lowest start)
    dedup = []
    last_dt = None
    for inf in inflections:
        cur = datetime.strptime(inf["date"], "%Y-%m-%d")
        if last_dt is None or (cur - last_dt).days >= 90:
            dedup.append(inf); last_dt = cur
    return dedup

def aspects_active_at(natal, jd):
    lons = planet_lons_at(jd)
    active = []
    for tp_name, tlon in lons.items():
        for np_name in NATAL_PTS:
            if np_name not in natal: continue
            npon = natal[np_name]["lon"]
            for asp_name, asp_deg in ASPECTS.items():
                o = aspect_orb(tlon, npon, asp_deg)
                if o <= 2.5:
                    active.append((tp_name, np_name, asp_name, o))
    return active

def main():
    # Step 1: find inflections across panel
    print("Loading panel + finding explosive inflections (6mo +100%)...", file=sys.stderr)
    inflection_events = []
    baseline_events = []  # non-pre-inflection sample
    for tk, ipo in PANEL:
        prices = load_prices(tk)
        if not prices: continue
        try:
            natal = compute_natal(ipo)
        except: continue
        inflections = find_explosive_inflections(prices, threshold=2.0)
        if not inflections: continue
        # For each inflection, sample T-3mo and T-6mo
        for inf in inflections:
            inf_jd = date_jd(inf["date"])
            # T-3mo (90 days before)
            inflection_events.append({
                "tk":tk,"natal":natal,"inflection_date":inf["date"],
                "pre_jd":inf_jd - 90,
                "pre_label":"T-3mo","ratio":inf["ratio"]
            })
            # T-6mo (180 days before)
            inflection_events.append({
                "tk":tk,"natal":natal,"inflection_date":inf["date"],
                "pre_jd":inf_jd - 180,
                "pre_label":"T-6mo","ratio":inf["ratio"]
            })
        # Baseline: random 3 dates per stock from price history, not within 12mo of any inflection
        import random
        random.seed(hash(tk)&0xffff)
        inf_jds = [date_jd(i["date"]) for i in inflections]
        first_p = date_jd(prices[0][0]) + 365
        last_p = date_jd(prices[-1][0]) - 365
        for _ in range(5):
            for attempt in range(20):
                jd = first_p + random.random() * (last_p - first_p)
                if all(abs(jd - inf_jd) > 365 for inf_jd in inf_jds):
                    baseline_events.append({"tk":tk,"natal":natal,"pre_jd":jd})
                    break

    print(f"  {len(inflection_events)} pre-inflection windows (3mo + 6mo)", file=sys.stderr)
    print(f"  {len(baseline_events)} baseline windows", file=sys.stderr)
    inflection_dates = set((e["tk"],e["inflection_date"]) for e in inflection_events)
    print(f"  {len(inflection_dates)} unique inflection events", file=sys.stderr)
    # Count per ticker
    by_tk = {}
    for e in inflection_events:
        by_tk.setdefault(e["tk"], set()).add(e["inflection_date"])
    print(f"  Inflections per ticker:", file=sys.stderr)
    for tk, dates in sorted(by_tk.items(), key=lambda x:-len(x[1]))[:15]:
        print(f"    {tk:<6s} {len(dates):>2d}", file=sys.stderr)

    # Step 2: aspect activation rates in pre-inflection vs baseline
    print("\nAggregating aspect activations in pre-inflection vs baseline...", file=sys.stderr)
    inf_active_counts = {}  # key=(tp,np,asp) -> # events with that aspect active
    base_active_counts = {}
    for e in inflection_events:
        active = aspects_active_at(e["natal"], e["pre_jd"])
        seen = set()
        for tp, np_, asp, _ in active:
            key = (tp, np_, asp)
            if key in seen: continue
            seen.add(key)
            inf_active_counts[key] = inf_active_counts.get(key, 0) + 1
    for e in baseline_events:
        active = aspects_active_at(e["natal"], e["pre_jd"])
        seen = set()
        for tp, np_, asp, _ in active:
            key = (tp, np_, asp)
            if key in seen: continue
            seen.add(key)
            base_active_counts[key] = base_active_counts.get(key, 0) + 1

    NI = len(inflection_events); NB = len(baseline_events)
    print(f"\n{'='*120}")
    print(f"PRE-INFLECTION SIGNATURES — % of pre-inflection windows with aspect active vs baseline")
    print(f"{'='*120}")
    print(f"{'Transit':<9s} {'Nat':<5s} {'Aspect':<10s} {'inf_n':>6s} {'inf%':>6s} {'base%':>6s}  {'lift':>6s}")
    rows = []
    all_keys = set(inf_active_counts) | set(base_active_counts)
    for key in all_keys:
        inf_n = inf_active_counts.get(key, 0)
        base_n = base_active_counts.get(key, 0)
        inf_pct = 100*inf_n/NI
        base_pct = 100*base_n/NB
        lift = inf_pct - base_pct
        if inf_n >= 10 and abs(lift) >= 4:  # require sufficient sample
            rows.append({"key":key,"inf_pct":inf_pct,"base_pct":base_pct,
                         "lift":lift,"inf_n":inf_n,"base_n":base_n})
    rows.sort(key=lambda r: -r["lift"])
    print(f"\n  TOP 30 BULLISH pre-inflection signatures (% lift over baseline):")
    for r in rows[:30]:
        tp, np_, asp = r["key"]
        print(f"  {tp[:8]:<9s} {np_:<5s} {asp:<10s} {r['inf_n']:>5d} {r['inf_pct']:>5.1f}% "
              f"{r['base_pct']:>5.1f}%  {r['lift']:>+5.1f}pp")

    print(f"\n  BOTTOM 15 BEARISH (aspects LESS COMMON in pre-inflection):")
    rows.sort(key=lambda r: r["lift"])
    for r in rows[:15]:
        tp, np_, asp = r["key"]
        print(f"  {tp[:8]:<9s} {np_:<5s} {asp:<10s} {r['inf_n']:>5d} {r['inf_pct']:>5.1f}% "
              f"{r['base_pct']:>5.1f}%  {r['lift']:>+5.1f}pp")

    # Step 3: Save signature for SP500 scan
    sig_lifts = {r["key"]:r["lift"] for r in rows if r["lift"] >= 4}
    # Also include all keys with n>=5 even if smaller lift
    for key in all_keys:
        inf_n = inf_active_counts.get(key, 0)
        base_n = base_active_counts.get(key, 0)
        if inf_n >= 5 and key not in sig_lifts:
            inf_pct = 100*inf_n/NI
            base_pct = 100*base_n/NB
            lift = inf_pct - base_pct
            sig_lifts[key] = lift

    # Step 4: Score each SP500 chart by today's match to bullish pre-inflection signature
    print(f"\n{'='*150}")
    print(f"SP500 — STOCKS WITH MOST PRE-INFLECTION SIGNATURE ACTIVE TODAY")
    print(f"  Higher score = chart most resembles historical 'about-to-double' configurations")
    print(f"{'='*150}")
    sp500 = []
    with open("/home/user/cyclepapa/data/sp500_ipo_dates.csv") as f:
        for r in csv.DictReader(f):
            tk = r["ticker"].strip().upper()
            ipo = (r.get("ipo_date") or "").strip()
            if not ipo or len(ipo) < 10: continue
            sp500.append({"tk":tk,"ipo":ipo,
                          "name":r.get("name","").strip(),
                          "sector":r.get("sector","").strip()})

    today_jd = date_jd("2026-04-22")
    today_lons = planet_lons_at(today_jd)

    sp500_scored = []
    for s in sp500:
        try:
            natal = compute_natal(s["ipo"])
        except: continue
        active = aspects_active_at(natal, today_jd)
        score = 0.0
        matched_pos = []
        matched_neg = []
        for tp, np_, asp, orb in active:
            key = (tp, np_, asp)
            if key in sig_lifts:
                lift = sig_lifts[key]
                # Weight by orb closeness
                weight = (2.5 - orb) / 2.5
                contrib = lift * weight
                score += contrib
                if lift >= 4:
                    matched_pos.append((key, lift, orb))
                elif lift <= -4:
                    matched_neg.append((key, lift, orb))
        s["score"] = score
        s["matched_pos"] = matched_pos
        s["matched_neg"] = matched_neg
        s["n_pos"] = len(matched_pos)
        s["n_neg"] = len(matched_neg)
        sp500_scored.append(s)

    sp500_scored.sort(key=lambda s: -s["score"])
    print(f"{'Rk':>3s} {'Tkr':<6s} {'GICS':<22s} {'Score':>7s} {'#pos':>4s} {'#neg':>4s}  Top pre-inflection signatures matched today (lift)")
    for i, s in enumerate(sp500_scored[:40], 1):
        nm = (s["name"] or "")[:18]
        gics = (s["sector"] or "")[:21]
        top = sorted(s["matched_pos"], key=lambda x:-x[1])[:3]
        top_str = " | ".join(f"{k[0][:3]}-{k[1][:3]} {k[2]} (+{l:.0f})" for k,l,o in top)
        print(f"{i:3d} {s['tk']:<6s} {gics:<22s} {s['score']:>+6.1f} {s['n_pos']:>4d} {s['n_neg']:>4d}  {top_str}   ({nm})")

    # Export
    with open("/home/user/cyclepapa/data/sp500_pre_inflection.csv","w",newline="") as f:
        w = csv.writer(f)
        w.writerow(["rank","ticker","name","sector","ipo","pre_inflection_score","n_pos_signatures","n_neg_signatures","top_signatures"])
        for i, s in enumerate(sp500_scored, 1):
            top = sorted(s["matched_pos"], key=lambda x:-x[1])[:5]
            top_str = " | ".join(f"{k[0]}-{k[1]} {k[2]} (+{l:.1f})" for k,l,o in top)
            w.writerow([i,s["tk"],s["name"],s["sector"],s["ipo"],
                        f"{s['score']:+.2f}",s["n_pos"],s["n_neg"],top_str])
    print(f"\nExported {len(sp500_scored)} ranked SP500 -> data/sp500_pre_inflection.csv")

if __name__ == "__main__":
    main()
