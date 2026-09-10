"""
RS-BOTTOM and RS-BREAKOUT astro signature study.

Two question classes:

  (1) When stocks make a major RS low vs SPY, what's the astro signature?
  (2) When stocks break OUT to new RS-highs vs SPY, what's the astro signature?

We want actionable patterns:
  bottoms -> when to accumulate
  breakouts -> when momentum is blessed + astro will confirm the move

Events detected:
  RS_LOW       : RS within 2% of its 3-yr lookback min, and subsequent
                 recovery >= 40% RS from that point.
  RS_BREAKOUT  : RS makes a new high relative to any previous high in the
                 3-yr lookback, AND the stock's price is within 10% of its
                 ATH at that moment (filters noise).

For each event, compute natal-to-transit signatures using v19 empirical
orb weights + compound rules + eclipse hits + Jup-natNep + Nep-Sun + Nep-MC.

Aggregate across all events and all tickers. Report:
  - Mean/median orb of each outer at events, vs baseline (non-event days)
  - Frequency of each compound rule firing at events vs baseline
  - Jupiter-natNep / Nep-Sun / Nep-MC orb distribution at events

Universe: top v22 tradeable picks + parabolic corpus + meme legends.
"""
import csv, os, sys, math, time, statistics as st
from datetime import datetime, timedelta
from bti_test import compute_natal, transits_at, jd_of
from bti_v4 import yx
from bti_v19_empirical import (
    SINGLE_PLANET_WEIGHTS, COMPOUND_RULES, bucket_weight, closest_hard, orb
)
from eclipse_database import build_eclipse_database, eclipse_hits_natal
from yf_fetcher import fetch_prices

DATE_END = "2026-04-22"

# Curated universe: v22 asymmetric top picks + parabolic corpus + megacaps
UNIVERSE = [
    # v22 top asymmetric
    ("IVZ","2008-08-21"), ("CHRW","1997-10-15"), ("DKS","2002-10-15"),
    ("HON","1999-12-01"), ("IBKR","2007-05-04"), ("TER","2020-09-21"),
    ("NFLX","2002-05-23"), ("KVYO","2023-09-20"), ("TPG","2022-01-13"),
    ("BLDR","2005-06-22"), ("KDP","2022-06-21"), ("DVN","2000-08-30"),
    ("BX","2007-06-21"), ("DECK","1993-10-14"), ("CE","2005-01-20"),
    ("WM","1998-08-31"), ("TTD","2016-09-21"),
    # v21 forward picks
    ("TEAM","2015-12-10"), ("GME","2002-02-13"), ("RGTI","2022-03-02"),
    ("ZS","2018-03-16"), ("CEG","2022-02-02"), ("SMR","2022-05-03"),
    ("NET","2019-09-13"), ("SNOW","2020-09-16"), ("RKLB","2021-08-25"),
    ("NXE","2013-06-04"), ("MRNA","2018-12-07"), ("LULU","2007-07-27"),
    ("ULTA","2007-10-24"), ("CMG","2006-01-25"),
    # Recent parabolic winners (to study their breakouts)
    ("NVDA","1999-01-22"), ("PLTR","2020-09-30"), ("APP","2021-04-15"),
    ("SMCI","2007-03-29"), ("CVNA","2017-04-28"), ("MSTR","1998-06-11"),
    ("COIN","2021-04-14"), ("HOOD","2021-07-29"), ("SOFI","2021-06-01"),
    ("UPST","2020-12-16"), ("HIMS","2021-01-21"), ("ELF","2016-09-22"),
    ("AMC","2013-12-18"), ("TSLA","2010-06-29"), ("META","2012-05-18"),
    # Classical large-moves
    ("AAPL","1980-12-12"), ("MSFT","1986-03-13"), ("GOOG","2004-08-19"),
    ("AMZN","1997-05-15"), ("AVGO","2000-09-26"), ("CRWD","2019-06-12"),
    ("ANET","2014-06-06"), ("NOW","2012-06-29"), ("PANW","2012-07-19"),
    # Bio/recent movers
    ("VKTX","2015-09-29"), ("BNTX","2019-10-10"), ("RIVN","2021-11-10"),
    ("LCID","2020-07-31"), ("XPEV","2020-08-27"), ("ROKU","2017-09-28"),
    ("SNAP","2017-03-02"), ("DUOL","2021-07-28"), ("ABNB","2020-12-10"),
    ("DASH","2020-12-09"), ("UBER","2019-05-10"), ("DKNG","2020-04-24"),
]

def load_spy():
    out = []
    with open("/home/user/cyclepapa/data/spy_prices.csv") as f:
        rr = csv.DictReader(f)
        for r in rr:
            out.append((r["date"], float(r["close"])))
    return out

def rs_series(stock_data, spx_map):
    s0 = None; x0 = None
    rs = []
    for d, c in stock_data:
        if d not in spx_map: continue
        if s0 is None: s0 = c; x0 = spx_map[d]
        rs.append((d, (c/s0) / (spx_map[d]/x0)))
    return rs

def find_rs_lows(rs, lookback_years=3, recovery_threshold=0.35):
    """RS lows: at each i, check if rs[i] is within 2% of 3-yr trailing min
    AND subsequent 6-month max > rs[i] * (1+recovery_threshold)."""
    events = []
    n = len(rs)
    for i in range(20, n - 120):
        cur_r = rs[i][1]
        cur_dt = datetime.strptime(rs[i][0], "%Y-%m-%d")
        lb_start = cur_dt - timedelta(days=365*lookback_years)
        lb_vals = [r for (d, r) in rs[:i+1]
                   if datetime.strptime(d, "%Y-%m-%d") >= lb_start]
        if not lb_vals: continue
        lb_min = min(lb_vals)
        if cur_r > lb_min * 1.02: continue
        # Forward 6-month max
        fwd_end = cur_dt + timedelta(days=180)
        fwd_vals = [r for (d, r) in rs[i+1:]
                    if datetime.strptime(d, "%Y-%m-%d") <= fwd_end]
        if not fwd_vals: continue
        fwd_max = max(fwd_vals)
        if fwd_max < cur_r * (1 + recovery_threshold): continue
        events.append(rs[i][0])
    # Dedupe — one event per 60 days
    deduped = []
    last_dt = None
    for d in events:
        dt = datetime.strptime(d, "%Y-%m-%d")
        if last_dt and (dt - last_dt).days < 60: continue
        deduped.append(d); last_dt = dt
    return deduped

def find_rs_breakouts(rs, lookback_years=3, min_run_pct=0.4):
    """RS breakouts: rs[i] exceeds its prior N-year running max (at least
    lookback_years old OR an all-time high from inception), AND trailing
    6-mo RS run >= min_run_pct (avoid sideways chop with single-day spikes)."""
    events = []
    n = len(rs)
    for i in range(250, n):
        cur_r = rs[i][1]
        cur_dt = datetime.strptime(rs[i][0], "%Y-%m-%d")
        # Prior 3-yr high excluding last 60 days
        lb_start = cur_dt - timedelta(days=365*lookback_years)
        lb_end = cur_dt - timedelta(days=60)
        lb_vals = [r for (d, r) in rs[:i]
                   if lb_start <= datetime.strptime(d, "%Y-%m-%d") <= lb_end]
        if not lb_vals: continue
        lb_max = max(lb_vals)
        if cur_r < lb_max * 1.005: continue
        # Trailing 6-mo run
        t6_dt = cur_dt - timedelta(days=180)
        t6_rs = [r for (d, r) in rs[:i+1]
                 if datetime.strptime(d, "%Y-%m-%d") >= t6_dt]
        if not t6_rs: continue
        t6_min = min(t6_rs)
        if cur_r / t6_min < (1 + min_run_pct): continue
        events.append(rs[i][0])
    deduped = []
    last_dt = None
    for d in events:
        dt = datetime.strptime(d, "%Y-%m-%d")
        if last_dt and (dt - last_dt).days < 120: continue
        deduped.append(d); last_dt = dt
    return deduped

def astro_snapshot(natal, date_str, db):
    y, m, d = map(int, date_str.split("-"))
    trans = transits_at(y, m)
    targets = {p: natal[p]["lon"] for p in ("Sun","Moon","ASC","MC") if p in natal}
    outer_orbs = {}
    for outer in ("Jupiter","Saturn","Uranus","Neptune","Pluto"):
        best = 99
        for tlon in targets.values():
            o = closest_hard(trans[outer]["lon"], tlon)
            if o < best: best = o
        outer_orbs[outer] = best
    jup_natNep = closest_hard(trans["Jupiter"]["lon"], natal["Neptune"]["lon"])
    nep_sun = closest_hard(trans["Neptune"]["lon"], natal["Sun"]["lon"])
    nep_mc = closest_hard(trans["Neptune"]["lon"], natal["MC"]["lon"]) if "MC" in natal else 99
    plu_sun = closest_hard(trans["Pluto"]["lon"], natal["Sun"]["lon"])
    plu_mc = closest_hard(trans["Pluto"]["lon"], natal["MC"]["lon"]) if "MC" in natal else 99
    ura_sun = closest_hard(trans["Uranus"]["lon"], natal["Sun"]["lon"])
    sat_sun = closest_hard(trans["Saturn"]["lon"], natal["Sun"]["lon"])
    # Compound rules fired
    fired = [lbl for lbl, fn, _ in COMPOUND_RULES if fn(outer_orbs)]
    jd_c = jd_of(y, m, d, 12.0)
    hits = eclipse_hits_natal(db, natal, jd_c, months_back=18, months_fwd=3, max_orb=3)
    ecl_count = len(hits)
    return {
        "outer": outer_orbs, "fired": fired,
        "jup_natNep": jup_natNep, "nep_sun": nep_sun, "nep_mc": nep_mc,
        "plu_sun": plu_sun, "plu_mc": plu_mc, "ura_sun": ura_sun, "sat_sun": sat_sun,
        "ecl": ecl_count,
    }

def main():
    print("Building eclipse DB...", file=sys.stderr)
    db = build_eclipse_database(1970, 2035)
    spy = load_spy()
    spy_map = dict(spy)

    # Fetch/cache prices for universe
    price_cache_dir = "/home/user/cyclepapa/data/prices"
    os.makedirs(price_cache_dir, exist_ok=True)

    rs_events_low = []       # list of (ticker, date, snap)
    rs_events_breakout = []
    baseline_snaps = []      # random non-event days per ticker for comparison

    for i, (tk, ipo) in enumerate(UNIVERSE):
        cache = f"{price_cache_dir}/{tk}.csv"
        if os.path.exists(cache):
            stock = []
            with open(cache) as f:
                next(f)
                for line in f:
                    parts = line.strip().split(",")
                    if len(parts) == 2:
                        stock.append((parts[0], float(parts[1])))
        else:
            print(f"  fetch {tk}...", file=sys.stderr, end=" ", flush=True)
            stock = fetch_prices(tk, 2018)
            print(f"{len(stock)} days", file=sys.stderr)
            if len(stock) < 60:
                time.sleep(0.5)
                continue
            with open(cache,"w") as f:
                f.write("date,close\n")
                for d, c in stock:
                    f.write(f"{d},{c:.4f}\n")
            time.sleep(0.3)
        if len(stock) < 250: continue

        rs = rs_series(stock, spy_map)
        if len(rs) < 250: continue

        lows = find_rs_lows(rs, lookback_years=3, recovery_threshold=0.30)
        breakouts = find_rs_breakouts(rs, lookback_years=3, min_run_pct=0.35)

        try:
            natal = compute_natal(ipo)
        except:
            continue

        for d in lows:
            try:
                snap = astro_snapshot(natal, d, db)
                rs_events_low.append((tk, d, snap))
            except: pass
        for d in breakouts:
            try:
                snap = astro_snapshot(natal, d, db)
                rs_events_breakout.append((tk, d, snap))
            except: pass

        # Baseline: sample every 180th trading day from rs[250:]
        for k in range(250, len(rs), 180):
            try:
                snap = astro_snapshot(natal, rs[k][0], db)
                baseline_snaps.append((tk, rs[k][0], snap))
            except: pass

    print(f"\nUniverse: {len(UNIVERSE)} tickers", file=sys.stderr)
    print(f"  RS_LOW events:     {len(rs_events_low)}", file=sys.stderr)
    print(f"  RS_BREAKOUT events:{len(rs_events_breakout)}", file=sys.stderr)
    print(f"  Baseline snaps:    {len(baseline_snaps)}", file=sys.stderr)

    # Export raw events
    with open("/home/user/cyclepapa/data/rs_event_astro.csv","w",newline="") as f:
        w = csv.writer(f)
        w.writerow(["kind","ticker","date","Jup","Sat","Ura","Nep","Plu",
                    "jup_natNep","nep_sun","nep_mc","plu_sun","plu_mc","ura_sun","sat_sun",
                    "ecl","n_compound","compounds"])
        for kind, events in [("LOW", rs_events_low), ("BREAKOUT", rs_events_breakout)]:
            for tk, d, s in events:
                w.writerow([kind, tk, d,
                            f"{s['outer']['Jupiter']:.1f}",
                            f"{s['outer']['Saturn']:.1f}",
                            f"{s['outer']['Uranus']:.1f}",
                            f"{s['outer']['Neptune']:.1f}",
                            f"{s['outer']['Pluto']:.1f}",
                            f"{s['jup_natNep']:.1f}", f"{s['nep_sun']:.1f}",
                            f"{s['nep_mc']:.1f}", f"{s['plu_sun']:.1f}",
                            f"{s['plu_mc']:.1f}", f"{s['ura_sun']:.1f}",
                            f"{s['sat_sun']:.1f}",
                            s['ecl'], len(s['fired']), " | ".join(s['fired'])])

    def pct_in(vals, lo, hi):
        return 100 * sum(1 for v in vals if lo <= v < hi) / max(len(vals),1)

    def summary_for_group(name, snaps):
        if not snaps:
            print(f"\n{name}: 0 events"); return
        print(f"\n{'='*85}")
        print(f"{name}  n={len(snaps)}")
        print(f"{'='*85}")
        # Per outer planet orb distribution
        print(f"  {'Planet':<9s}  {'≤3°':>4s} {'3-5°':>4s} {'5-8°':>4s} {'8-12°':>5s} {'12-20°':>6s} {'>20°':>5s}  {'mean':>5s} {'med':>5s}")
        for p in ("Jupiter","Saturn","Uranus","Neptune","Pluto"):
            vals = [s["outer"][p] for (_,_,s) in snaps]
            print(f"  {p:<9s}  {pct_in(vals,0,3):3.0f}% {pct_in(vals,3,5):3.0f}% {pct_in(vals,5,8):3.0f}% {pct_in(vals,8,12):4.0f}% {pct_in(vals,12,20):5.0f}% {pct_in(vals,20,99):4.0f}%  {st.mean(vals):5.2f} {st.median(vals):5.2f}")
        # Compound rule fire rates
        print(f"\n  Compound rule fire-rate:")
        all_rules = set()
        for (_,_,s) in snaps: all_rules.update(s["fired"])
        for rule in sorted(all_rules):
            hits = sum(1 for (_,_,s) in snaps if rule in s["fired"])
            print(f"    {rule:<35s} {hits:3d}/{len(snaps)}  {100*hits/len(snaps):4.0f}%")
        # Jup-natNep / Nep-Sun / Nep-MC / Plu-Sun / Plu-MC tight orbs
        print(f"\n  Special transits (% ≤3° orb):")
        for key, label in [("jup_natNep","Jup-natNep"),("nep_sun","Nep-natSun"),
                           ("nep_mc","Nep-natMC"),("plu_sun","Plu-natSun"),
                           ("plu_mc","Plu-natMC"),("ura_sun","Ura-natSun"),
                           ("sat_sun","Sat-natSun")]:
            vals = [s[key] for (_,_,s) in snaps if s[key] < 99]
            if not vals: continue
            p3 = 100*sum(1 for v in vals if v<=3)/len(vals)
            p6 = 100*sum(1 for v in vals if v<=6)/len(vals)
            print(f"    {label:<13s}  ≤3°: {p3:4.0f}%   ≤6°: {p6:4.0f}%   mean {st.mean(vals):5.2f}°")
        # Eclipse presence
        ecls = [s['ecl'] for (_,_,s) in snaps]
        print(f"\n  Eclipse hits ≤3° of natal: mean={st.mean(ecls):.2f}  %with_any={100*sum(1 for v in ecls if v>0)/len(ecls):.0f}%")

    summary_for_group("RS LOWS — stocks bottoming vs SPY", rs_events_low)
    summary_for_group("RS BREAKOUTS — new highs vs SPY (confirmed strength)", rs_events_breakout)
    summary_for_group("BASELINE — random non-event days", baseline_snaps)

    # Direct comparisons
    print(f"\n{'='*85}")
    print("LOW vs BREAKOUT vs BASELINE — % ≤3° orb for each transit (signature comparison)")
    print(f"{'='*85}")
    print(f"  {'Transit':<15s}  {'LOW%':>6s}  {'BRKT%':>6s}  {'BASE%':>6s}   LOW/BASE  BRKT/BASE")
    def pct3(g, key):
        vals = [s[key] for (_,_,s) in g if s[key] < 99]
        return 100*sum(1 for v in vals if v<=3)/max(len(vals),1)
    for key, label in [("jup_natNep","Jup-natNep"),("nep_sun","Nep-natSun"),
                       ("nep_mc","Nep-natMC"),("plu_sun","Plu-natSun"),
                       ("plu_mc","Plu-natMC"),("ura_sun","Ura-natSun"),
                       ("sat_sun","Sat-natSun")]:
        pl = pct3(rs_events_low, key)
        pb = pct3(rs_events_breakout, key)
        pbase = pct3(baseline_snaps, key)
        l_r = pl/pbase if pbase else float("inf")
        b_r = pb/pbase if pbase else float("inf")
        print(f"  {label:<15s}  {pl:5.1f}%  {pb:5.1f}%  {pbase:5.1f}%   {l_r:>5.2f}x    {b_r:>5.2f}x")

if __name__ == "__main__":
    main()
