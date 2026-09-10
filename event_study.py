"""
EVENT-STUDY: per-aspect-activation forward returns on multiple time frames.

For each stock with full price history:
  1. For every (transit-planet, natal-point, aspect-angle) triple:
  2. Find every date when that aspect activates within ≤2° orb
  3. Measure forward return at 1mo / 3mo / 6mo / 12mo from that date
  4. Aggregate across stocks and across activations

This isolates the SPECIFIC reaction-window for each aspect type:
  Mars aspects might produce 1-week effects
  Jupiter aspects → 1-3 month effects
  Saturn aspects → 6-12 month effects
  Outer-outer aspects → 1-3 year effects

Different planets have different natural reaction periods.
"""
import csv, os, json, subprocess, math
import statistics as st
from datetime import datetime, timezone, timedelta
from bisect import bisect_left
import swisseph as swe
from bti_test import compute_natal, jd_of

# Planets & their swisseph IDs
PIDS = {"Sun":swe.SUN,"Moon":swe.MOON,"Mercury":swe.MERCURY,"Venus":swe.VENUS,
        "Mars":swe.MARS,"Jupiter":swe.JUPITER,"Saturn":swe.SATURN,
        "Uranus":swe.URANUS,"Neptune":swe.NEPTUNE,"Pluto":swe.PLUTO}

OUTERS = ("Jupiter","Saturn","Uranus","Neptune","Pluto")
INNERS = ("Mars","Venus","Mercury","Sun")
NATAL_PTS = ("Sun","Moon","ASC","MC")

# Aspects to test (lesser-arc target angle in degrees)
ASPECTS = {
    "conj_0":   0.0,
    "sxt_60":   60.0,
    "sq_90":    90.0,
    "tri_120":  120.0,
    "opp_180":  180.0,
    "bat_41":   41.04,    # 0.886 Bat-Shark D
    "sept_51":  51.43,    # 1/7 septile
    "qnt_72":   72.0,     # quintile
    "gart_77":  77.04,    # 0.786 Gartley D
    "butt_98":  97.92,    # 1.272 Butterfly D
    "phi_137":  137.5,    # Crab D / golden angle
    "biq_144":  144.0,    # biquintile
}

def aspect_orb(a, b, target):
    d = (a - b) % 360
    return min(abs(d - target), abs(d - (360 - target)))

def planet_lon_at(jd, pid):
    return swe.calc_ut(jd, pid)[0][0] % 360

def find_aspect_dates(start_jd, end_jd, planet_id, natal_lon, target_aspect, orb=2.0, sample_days=3):
    """Find dates within window where transit-planet hits the aspect."""
    dates = []
    d = start_jd
    prev_orb = None
    while d <= end_jd:
        lon = planet_lon_at(d, planet_id)
        cur_orb = aspect_orb(lon, natal_lon, target_aspect)
        if cur_orb <= orb:
            # Find tightest within window
            best_d = d; best_orb = cur_orb
            d2 = d
            while d2 <= min(d + 30, end_jd):
                lon2 = planet_lon_at(d2, planet_id)
                o2 = aspect_orb(lon2, natal_lon, target_aspect)
                if o2 < best_orb: best_orb = o2; best_d = d2
                if o2 > orb: break
                d2 += 1
            dates.append((best_d, best_orb))
            d = d2 + 30  # skip ahead to avoid duplicates
        else:
            d += sample_days
    return dates

def fetch_or_load_prices(tk):
    cache = f"/home/user/cyclepapa/data/prices_full/{tk}.csv"
    if os.path.exists(cache):
        prices = []
        with open(cache) as f:
            next(f)
            for line in f:
                p = line.strip().split(",")
                if len(p) == 2:
                    try: prices.append((p[0], float(p[1])))
                    except: pass
        return prices
    p1 = int(datetime(1990,1,1,tzinfo=timezone.utc).timestamp())
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
            os.makedirs(os.path.dirname(cache), exist_ok=True)
            with open(cache,"w") as f:
                f.write("date,close\n")
                for d,c in prices: f.write(f"{d},{c:.4f}\n")
        return prices
    except: return []

def jd_to_date(jd):
    cal = swe.revjul(jd)
    return f"{int(cal[0]):04d}-{int(cal[1]):02d}-{int(cal[2]):02d}"

def date_to_jd(date_str):
    y,m,d = map(int, date_str.split("-"))
    return swe.julday(y, m, d, 12.0)

def price_at_or_after(prices_dict, target_date):
    """Get close at target_date or first trading day after."""
    target = target_date
    for offset in range(0, 7):
        d = (datetime.strptime(target, "%Y-%m-%d") + timedelta(days=offset)).strftime("%Y-%m-%d")
        if d in prices_dict: return prices_dict[d]
    return None

def forward_return(prices_dict, base_date, days_ahead):
    base = price_at_or_after(prices_dict, base_date)
    if base is None: return None
    target = (datetime.strptime(base_date, "%Y-%m-%d") + timedelta(days=days_ahead)).strftime("%Y-%m-%d")
    forward = price_at_or_after(prices_dict, target)
    if forward is None: return None
    return (forward / base - 1) * 100

# Use a curated set of liquid named stocks with full history
STOCKS = [
    ("AAPL","1980-12-12"), ("MSFT","1986-03-13"), ("NVDA","1999-01-22"),
    ("AMZN","1997-05-15"), ("GOOG","2004-08-19"), ("META","2012-05-18"),
    ("TSLA","2010-06-29"), ("NFLX","2002-05-23"),
    ("GME","2002-02-13"), ("AMC","2013-12-18"),
    ("PLTR","2020-09-30"), ("APP","2021-04-15"),
    ("SMCI","2007-03-29"), ("WDC","1976-08-31"),
    ("CHRW","1997-10-15"), ("BLDR","2005-06-22"),
    ("DECK","1993-10-14"), ("FISV","1986-09-25"),
    ("INCY","1993-11-05"),
]

def main():
    # Load all natal charts and price data
    print("Loading stock charts and prices...")
    stocks = []
    for tk, ipo in STOCKS:
        try:
            natal = compute_natal(ipo)
            prices = fetch_or_load_prices(tk)
            if not prices: continue
            prices_dict = dict(prices)
            ipo_jd = date_to_jd(ipo)
            # Use price history starting 1 year after IPO (skip noisy first months)
            first_price_date = prices[0][0]
            first_jd = max(date_to_jd(first_price_date), ipo_jd) + 365
            stocks.append({"tk":tk,"ipo":ipo,"natal":natal,"prices":prices,
                           "prices_dict":prices_dict,"first_jd":first_jd})
            print(f"  {tk} loaded ({len(prices)} days)")
        except Exception as e:
            print(f"  {tk} fail: {e}")

    end_jd = date_to_jd("2026-04-22")
    horizons = [21, 63, 126, 252]  # 1mo, 3mo, 6mo, 12mo trading days

    # Aggregate per (transit_planet, natal_pt, aspect_name) → list of forward returns
    print(f"\nScanning aspect activations...")
    activations = {}  # key=(tp,np,asp), value=list of (forward_returns_dict, stock)

    for s in stocks:
        for tp_name, tp_id in PIDS.items():
            if tp_name in ("Sun","Moon"): continue  # too fast for slow signal
            for np_name in NATAL_PTS:
                if np_name not in s["natal"]: continue
                npon = s["natal"][np_name]["lon"]
                for asp_name, asp_deg in ASPECTS.items():
                    # Only test outer planets at slow aspects, inner at fast
                    if tp_name in OUTERS and asp_deg in (60.0, 120.0):
                        continue  # outer trines/sextiles too rare to be meaningful
                    dates = find_aspect_dates(s["first_jd"], end_jd, tp_id, npon, asp_deg, orb=1.5)
                    for jd, orb in dates:
                        date_str = jd_to_date(jd)
                        ret_dict = {}
                        for h in horizons:
                            r = forward_return(s["prices_dict"], date_str, int(h * 1.46))  # 1 trading day = ~1.46 calendar days
                            if r is not None:
                                ret_dict[h] = r
                        if ret_dict:
                            key = (tp_name, np_name, asp_name)
                            activations.setdefault(key, []).append({
                                "tk":s["tk"],"date":date_str,"orb":orb,
                                "rets":ret_dict
                            })

    # Aggregate
    print(f"\n{'='*120}")
    print(f"PER-ASPECT FORWARD-RETURN STATISTICS")
    print(f"{'='*120}")
    print(f"{'tPlanet':<9s} {'natPt':<5s} {'Aspect':<10s} {'n':>4s} | "
          f"{'1mo':>6s} {'3mo':>6s} {'6mo':>6s} {'12mo':>6s}  |  "
          f"{'1mo>0':>5s} {'3mo>0':>5s} {'6mo>0':>5s} {'12mo>0':>5s}")
    rows = []
    for key, evts in activations.items():
        if len(evts) < 8: continue  # need minimum sample
        tp, np_, asp = key
        med = {}
        pct_pos = {}
        for h in horizons:
            rets = [e["rets"].get(h) for e in evts if h in e["rets"]]
            rets = [r for r in rets if r is not None]
            if rets:
                med[h] = st.median(rets)
                pct_pos[h] = 100*sum(1 for r in rets if r>0)/len(rets)
        rows.append({"key":key,"n":len(evts),"med":med,"pct":pct_pos})

    # Sort by 12mo median return descending
    rows.sort(key=lambda r: -r["med"].get(252, -999))
    for r in rows[:60]:
        tp, np_, asp = r["key"]
        m1 = r["med"].get(21, 0); m3 = r["med"].get(63, 0)
        m6 = r["med"].get(126, 0); m12 = r["med"].get(252, 0)
        p1 = r["pct"].get(21, 0); p3 = r["pct"].get(63, 0)
        p6 = r["pct"].get(126, 0); p12 = r["pct"].get(252, 0)
        marker = " ★" if (m12 > 15 and r["n"] >= 15) else (" ↓" if m12 < -10 else "")
        print(f"{tp[:8]:<9s} {np_:<5s} {asp:<10s} {r['n']:>4d} | "
              f"{m1:>+5.1f}% {m3:>+5.1f}% {m6:>+5.1f}% {m12:>+5.1f}% |  "
              f"{p1:>4.0f}% {p3:>4.0f}% {p6:>4.0f}% {p12:>4.0f}%{marker}")

    # Bottom rankings
    print(f"\n{'='*120}")
    print(f"BOTTOM 25 by 12-month median (BEARISH transits)")
    print(f"{'='*120}")
    rows.sort(key=lambda r: r["med"].get(252, 999))
    for r in rows[:25]:
        tp, np_, asp = r["key"]
        m1 = r["med"].get(21, 0); m3 = r["med"].get(63, 0)
        m6 = r["med"].get(126, 0); m12 = r["med"].get(252, 0)
        p12 = r["pct"].get(252, 0)
        print(f"{tp[:8]:<9s} {np_:<5s} {asp:<10s} {r['n']:>4d} | "
              f"{m1:>+5.1f}% {m3:>+5.1f}% {m6:>+5.1f}% {m12:>+5.1f}%  pct>0: {p12:.0f}%")

    # Aggregate by aspect (across all transit planets and natal points)
    print(f"\n{'='*120}")
    print(f"AGGREGATE BY ASPECT TYPE — average across all (planet, natal-pt) combinations")
    print(f"{'='*120}")
    by_asp = {}
    for r in rows:
        asp = r["key"][2]
        by_asp.setdefault(asp, []).append(r)
    print(f"{'Aspect':<12s} {'pairs':>6s} {'tot n':>7s} | {'avg_1mo':>8s} {'avg_3mo':>8s} {'avg_6mo':>8s} {'avg_12mo':>9s}")
    asp_summary = []
    for asp, items in by_asp.items():
        tot_n = sum(i["n"] for i in items)
        m1 = st.mean([i["med"].get(21,0) for i in items])
        m3 = st.mean([i["med"].get(63,0) for i in items])
        m6 = st.mean([i["med"].get(126,0) for i in items])
        m12 = st.mean([i["med"].get(252,0) for i in items])
        asp_summary.append((asp, len(items), tot_n, m1, m3, m6, m12))
    asp_summary.sort(key=lambda x: -x[6])
    for asp, np_count, tot_n, m1, m3, m6, m12 in asp_summary:
        print(f"{asp:<12s} {np_count:>6d} {tot_n:>7d} | {m1:>+7.1f}% {m3:>+7.1f}% {m6:>+7.1f}% {m12:>+8.1f}%")

    # Aggregate by transit planet
    print(f"\n{'='*120}")
    print(f"AGGREGATE BY TRANSIT PLANET")
    print(f"{'='*120}")
    by_tp = {}
    for r in rows:
        tp = r["key"][0]
        by_tp.setdefault(tp, []).append(r)
    print(f"{'tPlanet':<9s} {'rows':>5s} {'tot n':>7s} | {'avg_1mo':>8s} {'avg_3mo':>8s} {'avg_6mo':>8s} {'avg_12mo':>9s}")
    for tp in sorted(by_tp):
        items = by_tp[tp]
        tot_n = sum(i["n"] for i in items)
        m1 = st.mean([i["med"].get(21,0) for i in items])
        m3 = st.mean([i["med"].get(63,0) for i in items])
        m6 = st.mean([i["med"].get(126,0) for i in items])
        m12 = st.mean([i["med"].get(252,0) for i in items])
        print(f"{tp[:8]:<9s} {len(items):>5d} {tot_n:>7d} | {m1:>+7.1f}% {m3:>+7.1f}% {m6:>+7.1f}% {m12:>+8.1f}%")

if __name__ == "__main__":
    main()
