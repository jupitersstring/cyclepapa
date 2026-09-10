"""
FULL-UNIVERSE July 2026 scan — every name in universe_bti_v20.csv.

For all ~12k charts (age 0-50): event-study aspect score as of 2026-07-01
and forward 12 months; rank by forward delta and peak. No price fetch at
this scale — pure astro ranking. Tradeable subset flagged via the
SP500-source + curated allowlist.
"""
import csv, pickle, sys, time
import swisseph as swe
from bti_test import compute_natal
from filter_tradeable_v22 import CURATED_ACTIVE, BAD_NAME, BAD_TICKER

TY, TM = 2026, 7

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

def planet_lons(jd):
    return {p: swe.calc_ut(jd, pid)[0][0] % 360 for p, pid in PIDS.items()}

def keep_tradeable(nm, tk, src):
    if not nm or not tk: return False
    if BAD_NAME.search(nm) or BAD_TICKER.search(tk): return False
    if len(tk) > 5: return False
    return src == "SP500" or tk in CURATED_ACTIVE

def main():
    with open("/home/user/cyclepapa/data/event_study_keys.pkl","rb") as f:
        key_stats = pickle.load(f)
    valid_keys = {k:v for k,v in key_stats.items()
                  if v.get("n_w",0)>=10 and v.get("n_c",0)>=5 and "delta_365" in v}
    # Pre-index: for speed, restructure as {(tp, np): [(asp_deg, delta), ...]}
    key_by_pair = {}
    for (tp, np_, asp_name), v in valid_keys.items():
        key_by_pair.setdefault((tp, np_), []).append((ASPECTS[asp_name], v["delta_365"]))

    months = []
    y, m = TY, TM
    for _ in range(13):
        months.append((y, m))
        m += 1
        if m > 12: m = 1; y += 1
    monthly_lons = [planet_lons(swe.julday(y, m, 15, 12.0)) for (y, m) in months]

    seeds = []
    with open("/home/user/cyclepapa/data/universe_bti_v20.csv") as f:
        for r in csv.DictReader(f):
            tk = (r.get("ticker") or "").strip().upper()
            ipo = (r.get("ipo") or "").strip()
            nm = (r.get("name") or "").strip()
            src = (r.get("source") or "").strip()
            if not tk or not ipo or len(ipo) < 10: continue
            try: yy = int(ipo[:4])
            except: continue
            age = TY - yy
            if not (0 <= age <= 50): continue
            seeds.append({"tk":tk,"ipo":ipo,"name":nm,"src":src,"age":age})
    seen = set(); unique = []
    for s in seeds:
        k = (s["tk"], s["ipo"])
        if k in seen: continue
        seen.add(k); unique.append(s)
    print(f"Universe: {len(unique)}", file=sys.stderr)

    def score(natal, lons):
        s = 0.0
        for tp, tlon in lons.items():
            for np_ in NATAL_PTS:
                if np_ not in natal: continue
                npon = natal[np_]["lon"]
                pairs = key_by_pair.get((tp, np_))
                if not pairs: continue
                for asp_deg, delta in pairs:
                    if aspect_orb(tlon, npon, asp_deg) <= 2.5:
                        s += delta
        return s

    t0 = time.time()
    rows = []
    for i, s in enumerate(unique):
        if i and i % 1000 == 0:
            print(f"  {i}/{len(unique)}  {time.time()-t0:.0f}s", file=sys.stderr)
        try:
            natal = compute_natal(s["ipo"])
        except: continue
        now = score(natal, monthly_lons[0])
        best = now; best_i = 0
        for j in range(1, 13):
            sc = score(natal, monthly_lons[j])
            if sc > best: best = sc; best_i = j
        delta = best - now
        rows.append({**s, "now":now, "peak":best, "delta":delta,
                     "pk_mo":f"{months[best_i][0]}-{months[best_i][1]:02d}",
                     "tradeable": keep_tradeable(s["name"], s["tk"], s["src"])})
    print(f"Scored {len(rows)} in {time.time()-t0:.0f}s", file=sys.stderr)

    rows.sort(key=lambda r: -r["delta"])
    out = "/home/user/cyclepapa/data/full_universe_jul2026.csv"
    with open(out, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["rank","ticker","name","source","ipo","age","score_now",
                    "score_peak","delta","peak_month","tradeable"])
        for i, r in enumerate(rows, 1):
            w.writerow([i, r["tk"], r["name"], r["src"], r["ipo"], r["age"],
                        f"{r['now']:+.1f}", f"{r['peak']:+.1f}", f"{r['delta']:+.1f}",
                        r["pk_mo"], "Y" if r["tradeable"] else "N"])
    print(f"Exported {len(rows)} -> {out}")

    print(f"\n{'='*140}")
    print(f"TOP 40 ALL-UNIVERSE by forward 12mo delta (as of 2026-07-01)")
    print(f"{'='*140}")
    print(f"{'#':>3s} {'Tkr':<7s} {'Src':<7s} {'IPO':<11s} {'Age':>3s} {'Now':>6s}→{'Pk':>6s} {'Δ':>6s} {'PkMo':<8s} {'Trd':>3s}  Name")
    for i, r in enumerate(rows[:40], 1):
        nm = (r["name"] or "")[:30]
        print(f"{i:3d} {r['tk']:<7s} {r['src']:<7s} {r['ipo']:<11s} {r['age']:>3d} "
              f"{r['now']:>+5.0f}→{r['peak']:>+5.0f} {r['delta']:>+5.0f} {r['pk_mo']:<8s} "
              f"{'Y' if r['tradeable'] else 'N':>3s}  {nm}")

    tr = [r for r in rows if r["tradeable"]]
    print(f"\n{'='*140}")
    print(f"TOP 40 TRADEABLE by forward 12mo delta ({len(tr)} tradeable)")
    print(f"{'='*140}")
    for i, r in enumerate(tr[:40], 1):
        nm = (r["name"] or "")[:30]
        print(f"{i:3d} {r['tk']:<7s} {r['src']:<7s} {r['ipo']:<11s} {r['age']:>3d} "
              f"{r['now']:>+5.0f}→{r['peak']:>+5.0f} {r['delta']:>+5.0f} {r['pk_mo']:<8s}  {nm}")

    # Also: tradeable low-base (now < 50) big-delta
    lb = [r for r in tr if r["now"] < 50 and r["delta"] >= 100]
    print(f"\n{'='*140}")
    print(f"TRADEABLE LOW-BASE (now<50) + BIG SHIFT (Δ>=100): {len(lb)} names")
    print(f"{'='*140}")
    for i, r in enumerate(lb[:40], 1):
        nm = (r["name"] or "")[:30]
        print(f"{i:3d} {r['tk']:<7s} {r['src']:<7s} {r['ipo']:<11s} {r['age']:>3d} "
              f"{r['now']:>+5.0f}→{r['peak']:>+5.0f} {r['delta']:>+5.0f} {r['pk_mo']:<8s}  {nm}")

if __name__ == "__main__":
    main()
