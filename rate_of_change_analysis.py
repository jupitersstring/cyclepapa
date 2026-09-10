"""
Rate-of-change analysis: do derivatives of astro measures correlate with
price returns (not just levels)?

Classical astrology says applying aspects > separating aspects. Transit
planet MOVING TOWARD natal point (orb decreasing) = building effect;
MOVING AWAY (orb increasing) = releasing.

Test hypothesis: delta-astro correlates better with delta-price than
static astro level does.

Per-month astro measures for key tickers (2019-2026 window):
  - Jupiter to natal Sun orb (signed: negative = approaching)
  - Saturn to natal Sun orb
  - Neptune to natal Sun orb
  - Pluto to natal Sun orb
  - Bottom signature score
  - Fame rise score
  - Fame fall score
  - Eclipse score (eclipses within 12mo)

Then compute rate of change = month_now - month_prior for each.
Correlate with same-month price return, forward 1/3/6 month returns.
"""
import math, csv, sys, time, statistics as st
from collections import defaultdict
from datetime import datetime
import swisseph as swe
from bti_test import compute_natal, transits_at, jd_of
from bti_v4 import yx
from classical_extensions import FIXED_STARS
from fame_esteem_theory import score_fame_potential, score_rise_triggers, score_fall_triggers
from eclipse_database import build_eclipse_database, eclipse_hits_natal
from yf_fetcher import fetch_prices

def orb(a, b):
    d = abs((a - b) % 360)
    return min(d, 360 - d)

def closest_hard(a, b, max_orb=30):
    best = 99
    for asp in (0, 90, 180):
        for sign in (+1, -1):
            o = orb(a, b + sign*asp)
            if o < best: best = o
    return best

def monthly_astro_snapshot(natal, eval_y, eval_m, db):
    """Compute astro measures at a given month."""
    trans = transits_at(eval_y, eval_m)
    # Outer planet orbs to natal Sun
    measures = {
        "jup_sun": closest_hard(trans["Jupiter"]["lon"], natal["Sun"]["lon"]),
        "sat_sun": closest_hard(trans["Saturn"]["lon"], natal["Sun"]["lon"]),
        "ura_sun": closest_hard(trans["Uranus"]["lon"], natal["Sun"]["lon"]),
        "nep_sun": closest_hard(trans["Neptune"]["lon"], natal["Sun"]["lon"]),
        "plu_sun": closest_hard(trans["Pluto"]["lon"], natal["Sun"]["lon"]),
        "jup_natNep": closest_hard(trans["Jupiter"]["lon"], natal["Neptune"]["lon"]),
    }
    # To MC
    if "MC" in natal:
        measures["sat_mc"] = closest_hard(trans["Saturn"]["lon"], natal["MC"]["lon"])
        measures["jup_mc"] = closest_hard(trans["Jupiter"]["lon"], natal["MC"]["lon"])
    # Fame rise/fall
    rise, _ = score_rise_triggers(natal, eval_y, eval_m)
    fall, _ = score_fall_triggers(natal, eval_y, eval_m)
    measures["rise"] = rise
    measures["fall"] = fall
    measures["net"] = rise - fall
    # Eclipse score: sum of inverse-orb weights for recent eclipses
    jd_c = jd_of(eval_y, eval_m, 15, 12.0)
    hits = eclipse_hits_natal(db, natal, jd_c, months_back=12, months_fwd=3, max_orb=3)
    measures["eclipse"] = sum((3 - h["orb"])/3 for h in hits)
    return measures

def price_monthly_returns(prices):
    """Aggregate daily prices to monthly returns (end-of-month close)."""
    by_ym = {}
    for d, c in prices:
        ym = d[:7]
        by_ym[ym] = c  # keeps last
    months = sorted(by_ym.keys())
    returns = {}
    for i in range(1, len(months)):
        prev = by_ym[months[i-1]]
        cur = by_ym[months[i]]
        if prev > 0:
            returns[months[i]] = (cur / prev - 1) * 100
    return returns, by_ym

def forward_return(prices_by_ym, ym, months_fwd):
    """Forward return over next N months from ym."""
    keys = sorted(prices_by_ym.keys())
    if ym not in keys: return None
    i = keys.index(ym)
    if i + months_fwd >= len(keys): return None
    return (prices_by_ym[keys[i+months_fwd]] / prices_by_ym[ym] - 1) * 100

def corr(xs, ys):
    pairs = [(x,y) for x,y in zip(xs,ys) if x is not None and y is not None]
    if len(pairs) < 3: return 0, 0
    xs = [p[0] for p in pairs]; ys = [p[1] for p in pairs]
    mx, my = st.mean(xs), st.mean(ys)
    num = sum((x-mx)*(y-my) for x,y in zip(xs,ys))
    dx = math.sqrt(sum((x-mx)**2 for x in xs))
    dy = math.sqrt(sum((y-my)**2 for y in ys))
    return (num/(dx*dy) if dx*dy else 0, len(pairs))

def main():
    print("Building eclipse DB...", file=sys.stderr)
    db = build_eclipse_database(1970, 2035)
    print(f"  {len(db)} eclipses", file=sys.stderr)

    # Tickers with clear multi-year history that had mega moves
    cases = [
        ("NVDA",  "1999-01-22"),
        ("PLTR",  "2020-09-30"),
        ("APP",   "2021-04-15"),
        ("CVNA",  "2017-04-28"),
        ("MSTR",  "1998-06-11"),
        ("COIN",  "2021-04-14"),
        ("HIMS",  "2021-01-21"),
        ("IONQ",  "2021-10-01"),
        ("RKLB",  "2021-08-25"),
        ("VST",   "2016-10-10"),
        ("RDDT",  "2024-03-21"),
        ("SMCI",  "2007-03-29"),
        ("TSLA",  "2010-06-29"),
        ("META",  "2012-05-18"),
        ("NFLX",  "2002-05-23"),
        ("GME",   "2002-02-13"),
        ("AMC",   "2013-12-18"),
    ]

    # Aggregate across all cases
    all_pairs = {
        "level_vs_same_return": defaultdict(list),
        "delta_vs_same_return": defaultdict(list),
        "level_vs_fwd1_return": defaultdict(list),
        "delta_vs_fwd1_return": defaultdict(list),
        "level_vs_fwd3_return": defaultdict(list),
        "delta_vs_fwd3_return": defaultdict(list),
    }

    per_ticker = []
    for tk, ipo in cases:
        print(f"Processing {tk}...", file=sys.stderr)
        try:
            natal = compute_natal(ipo)
        except Exception as e:
            print(f"  natal err: {e}", file=sys.stderr); continue
        prices = fetch_prices(tk, 2019)
        time.sleep(0.1)
        if not prices or len(prices) < 50:
            print(f"  price data insufficient", file=sys.stderr); continue
        returns_by_ym, prices_by_ym = price_monthly_returns(prices)

        # Snapshot astro monthly 2019-01 through 2026-04
        snapshots = {}
        y, m = 2019, 1
        while (y, m) <= (2026, 4):
            snap = monthly_astro_snapshot(natal, y, m, db)
            snapshots[f"{y:04d}-{m:02d}"] = snap
            m += 1
            if m > 12: m = 1; y += 1

        # Compute pairs: level vs same-month return, delta vs same-month return
        months = sorted(snapshots.keys())
        for i, ym in enumerate(months):
            if i == 0: continue
            prev_snap = snapshots[months[i-1]]
            cur_snap = snapshots[ym]
            ret = returns_by_ym.get(ym)
            if ret is None: continue
            fwd1 = forward_return(prices_by_ym, ym, 1)
            fwd3 = forward_return(prices_by_ym, ym, 3)
            for k, v in cur_snap.items():
                dv = v - prev_snap.get(k, v)
                all_pairs["level_vs_same_return"][k].append((v, ret))
                all_pairs["delta_vs_same_return"][k].append((dv, ret))
                if fwd1 is not None:
                    all_pairs["level_vs_fwd1_return"][k].append((v, fwd1))
                    all_pairs["delta_vs_fwd1_return"][k].append((dv, fwd1))
                if fwd3 is not None:
                    all_pairs["level_vs_fwd3_return"][k].append((v, fwd3))
                    all_pairs["delta_vs_fwd3_return"][k].append((dv, fwd3))
        per_ticker.append(tk)

    print(f"\n  Processed {len(per_ticker)} tickers: {', '.join(per_ticker)}", file=sys.stderr)

    # Correlations
    print(f"\n{'='*140}")
    print(f"LEVEL vs RATE-OF-CHANGE correlations with price returns")
    print(f"{'='*140}")
    print(f"{'Measure':<14s}  {'level→ret(m)':>14s}  {'Δ→ret(m)':>14s}  {'level→fwd1':>14s}  {'Δ→fwd1':>14s}  {'level→fwd3':>14s}  {'Δ→fwd3':>14s}")
    measures = ["jup_sun","sat_sun","ura_sun","nep_sun","plu_sun","jup_natNep","jup_mc","sat_mc","rise","fall","net","eclipse"]
    for k in measures:
        r_lvl_same, n1 = corr([x for x,y in all_pairs["level_vs_same_return"][k]], [y for x,y in all_pairs["level_vs_same_return"][k]])
        r_dlt_same, n2 = corr([x for x,y in all_pairs["delta_vs_same_return"][k]], [y for x,y in all_pairs["delta_vs_same_return"][k]])
        r_lvl_f1, n3 = corr([x for x,y in all_pairs["level_vs_fwd1_return"][k]], [y for x,y in all_pairs["level_vs_fwd1_return"][k]])
        r_dlt_f1, n4 = corr([x for x,y in all_pairs["delta_vs_fwd1_return"][k]], [y for x,y in all_pairs["delta_vs_fwd1_return"][k]])
        r_lvl_f3, n5 = corr([x for x,y in all_pairs["level_vs_fwd3_return"][k]], [y for x,y in all_pairs["level_vs_fwd3_return"][k]])
        r_dlt_f3, n6 = corr([x for x,y in all_pairs["delta_vs_fwd3_return"][k]], [y for x,y in all_pairs["delta_vs_fwd3_return"][k]])
        print(f"{k:<14s}  {r_lvl_same:+10.3f}(n{n1:4d})  {r_dlt_same:+10.3f}(n{n2:4d})  {r_lvl_f1:+10.3f}(n{n3:4d})  {r_dlt_f1:+10.3f}(n{n4:4d})  {r_lvl_f3:+10.3f}(n{n5:4d})  {r_dlt_f3:+10.3f}(n{n6:4d})")

    # Strongest findings
    print(f"\n{'='*80}")
    print(f"STRONGEST CORRELATIONS (|r| >= 0.08 with adequate n)")
    print(f"{'='*80}")
    strong = []
    for bucket_name, bucket in all_pairs.items():
        for k, pairs in bucket.items():
            if len(pairs) < 100: continue
            r, n = corr([x for x,y in pairs], [y for x,y in pairs])
            if abs(r) >= 0.08:
                strong.append((abs(r), r, k, bucket_name, n))
    strong.sort(reverse=True)
    for absr, r, k, bucket, n in strong[:20]:
        print(f"  {k:<14s}  {bucket:<30s}  r={r:+.3f}  n={n}")

    # Condition test: when |delta| is LARGE, is return bigger?
    print(f"\n{'='*100}")
    print(f"CONDITION TEST: does a BIG MOVE IN ASTRO = BIG MOVE IN PRICE?")
    print(f"Bucket same-month Δastro into quartiles, compare mean forward-1mo price return")
    print(f"{'='*100}")
    for k in ("jup_sun","nep_sun","sat_sun","plu_sun","rise","fall","eclipse"):
        pairs = all_pairs["delta_vs_fwd1_return"][k]
        if len(pairs) < 100: continue
        xs = sorted(pairs, key=lambda p: p[0])
        n = len(xs)
        q1 = xs[:n//4]
        q2 = xs[n//4:n//2]
        q3 = xs[n//2:3*n//4]
        q4 = xs[3*n//4:]
        print(f"  {k:<14s} (n={n}):  Q1:{st.mean([y for x,y in q1]):+6.2f}%  Q2:{st.mean([y for x,y in q2]):+6.2f}%  Q3:{st.mean([y for x,y in q3]):+6.2f}%  Q4:{st.mean([y for x,y in q4]):+6.2f}%")

    # Rate-of-change inflection: when Jupiter passes CLOSEST orb (minimum), price peaks before or after?
    print(f"\n{'='*100}")
    print(f"INFLECTION: when transit Jupiter reaches orb minimum to natal Sun, price trajectory?")
    print(f"{'='*100}")
    # For each ticker, find months where jup_sun is local minimum, look at price ±3 months
    # (aggregated check across all cases)

if __name__ == "__main__":
    main()
