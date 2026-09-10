"""
SP500 forward shift — HARMONIC ASPECTS ONLY.

Restricts to the 8 phi/Gartley harmonic aspects we tested empirically,
excluding traditional conj/sxt/sq/tri/opp.

Harmonic aspects:
  bat_41    (0.886 Bat-Shark D-point)
  sept_51   (1/7 septile)
  qnt_72    (1/5 quintile, Pentagram of Venus)
  gart_77   (0.786 Gartley D-point)
  butt_98   (1.272 Butterfly D-point — sqrt phi)
  phi_137   (Crab D / Golden Angle)
  biq_144   (2/5 biquintile)
  tridec_108 (3/10 tridecile)

For each SP500 chart, compute harmonic-only score at each forward month
using empirical W-C deltas. Find biggest near-term shifts.
"""
import csv, math, pickle, sys
from datetime import datetime
import swisseph as swe
from bti_test import compute_natal

PIDS = {"Mercury":swe.MERCURY,"Venus":swe.VENUS,"Mars":swe.MARS,
        "Jupiter":swe.JUPITER,"Saturn":swe.SATURN,
        "Uranus":swe.URANUS,"Neptune":swe.NEPTUNE,"Pluto":swe.PLUTO}
NATAL_PTS = ("Sun","Moon","ASC","MC")

# HARMONIC ONLY (exclude conj/sxt/sq/tri/opp)
HARMONIC_ASPECTS = {
    "bat_41":   41.04,
    "sept_51":  51.43,
    "qnt_72":   72.0,
    "gart_77":  77.04,
    "butt_98":  97.92,
    "phi_137":  137.5,
    "biq_144":  144.0,
}

def aspect_orb(a, b, target):
    d = (a - b) % 360
    return min(abs(d - target), abs(d - (360 - target)))

def date_jd(y, m, d=15): return swe.julday(y, m, d, 12.0)

def planet_lons(jd): return {p: swe.calc_ut(jd, pid)[0][0] % 360 for p, pid in PIDS.items()}

def chart_score(natal, lons, valid_keys, orb=2.5):
    score = 0.0; actives = []
    for tp_name, tlon in lons.items():
        for np_name in NATAL_PTS:
            if np_name not in natal: continue
            npon = natal[np_name]["lon"]
            for asp_name, asp_deg in HARMONIC_ASPECTS.items():
                cur_orb = aspect_orb(tlon, npon, asp_deg)
                if cur_orb <= orb:
                    key = (tp_name, np_name, asp_name)
                    if key in valid_keys:
                        d = valid_keys[key]["delta_365"]
                        score += d
                        actives.append((key, d, cur_orb))
    return score, len(actives), actives

def main():
    print("Loading event-study keys (harmonic only)...", file=sys.stderr)
    with open("/home/user/cyclepapa/data/event_study_keys.pkl","rb") as f:
        key_stats = pickle.load(f)
    valid_keys = {k:v for k,v in key_stats.items()
                  if v.get("n_w",0)>=10 and v.get("n_c",0)>=5
                  and "delta_365" in v
                  and k[2] in HARMONIC_ASPECTS}
    print(f"  {len(valid_keys)} valid harmonic keys (out of {len(key_stats)} total)", file=sys.stderr)

    sp500 = []
    with open("/home/user/cyclepapa/data/sp500_ipo_dates.csv") as f:
        for r in csv.DictReader(f):
            tk = r["ticker"].strip().upper()
            ipo = (r.get("ipo_date") or "").strip()
            if not ipo or len(ipo)<10: continue
            sp500.append({"tk":tk,"ipo":ipo,
                          "name":r.get("name","").strip(),
                          "sector":r.get("sector","").strip()})

    months = [(2026, m) for m in range(4, 13)] + [(2027, m) for m in range(1, 5)]
    monthly_lons = {(y,m): planet_lons(date_jd(y,m)) for y, m in months}

    rows = []
    for s in sp500:
        try:
            natal = compute_natal(s["ipo"])
        except: continue
        scores = []
        for (y,m) in months:
            sc, n, actives = chart_score(natal, monthly_lons[(y,m)], valid_keys)
            scores.append({"y":y,"m":m,"score":sc,"n":n,"actives":actives})
        s["scores"] = scores
        s["score_now"] = scores[0]["score"]
        s["score_3mo"] = scores[3]["score"] if len(scores)>3 else s["score_now"]
        s["score_6mo"] = scores[6]["score"] if len(scores)>6 else s["score_now"]
        forward = scores[1:]
        if forward:
            mx = max(forward, key=lambda x:x["score"])
            s["score_max"] = mx["score"]
            s["max_month"] = f"{mx['y']}-{mx['m']:02d}"
            s["delta"] = mx["score"] - s["score_now"]
            s["t_max"] = forward.index(mx) + 1
        else:
            s["score_max"]=s["score_now"]; s["max_month"]=""; s["delta"]=0; s["t_max"]=0
        s["delta_3mo"] = s["score_3mo"] - s["score_now"]
        s["delta_6mo"] = s["score_6mo"] - s["score_now"]
        rows.append(s)

    print(f"\n{'='*200}")
    print(f"SP500 — BIGGEST FORWARD HARMONIC-ASPECT SHIFTS (Apr 2026 → Apr 2027)")
    print(f"  Restricted to: bat_41, sept_51, qnt_72, gart_77, butt_98, phi_137, biq_144")
    print(f"  Filter: today's score moderate, max forward delta ≥ 30")
    print(f"{'='*200}")
    rows.sort(key=lambda r: -r["delta"])
    shifts = [r for r in rows if r["delta"] >= 30 and r["score_now"] < 150]
    print(f"{'#':>3s} {'Tkr':<6s} {'GICS':<22s} {'Now':>5s}→{'Max':>5s}  {'Δ':>5s}  {'PkMo':<8s} {'tMx':>4s} {'+3mo':>5s} {'+6mo':>5s}  Name")
    for i, r in enumerate(shifts[:50], 1):
        nm = (r["name"] or "")[:18]
        gics = (r["sector"] or "")[:21]
        print(f"{i:3d} {r['tk']:<6s} {gics:<22s} {r['score_now']:>+4.0f} →{r['score_max']:>+4.0f}  "
              f"+{r['delta']:>4.0f}  {r['max_month']:<8s} {r['t_max']:>3d}mo "
              f"{r['delta_3mo']:>+4.0f} {r['delta_6mo']:>+4.0f}  {nm}")

    # Imminent (3mo) harmonic shifts
    print(f"\n{'='*200}")
    print(f"IMMINENT HARMONIC SHIFTS — 3-month delta ≥ 25")
    print(f"{'='*200}")
    rows.sort(key=lambda r: -r["delta_3mo"])
    imm = [r for r in rows if r["delta_3mo"] >= 25]
    print(f"{'Tkr':<6s} {'GICS':<22s} {'Now':>5s}→{'Jul26':>5s} {'Δ3mo':>5s}  Top 3 NEW HARMONIC aspects activating")
    for r in imm[:30]:
        nm = (r["name"] or "")[:18]
        gics = (r["sector"] or "")[:21]
        cur_set = set(a[0] for a in r["scores"][0]["actives"])
        fwd_set = set(a[0] for a in r["scores"][3]["actives"])
        new_keys = fwd_set - cur_set
        new_actives = sorted([a for a in r["scores"][3]["actives"] if a[0] in new_keys],
                              key=lambda a: -a[1])
        new_str = " | ".join(f"{a[0][0][:3]}-{a[0][1][:3]} {a[0][2]} (Δ+{a[1]:.0f})" for a in new_actives[:3])
        print(f"{r['tk']:<6s} {gics:<22s} {r['score_now']:>+4.0f} →{r['score_3mo']:>+4.0f} +{r['delta_3mo']:>4.0f}  {nm:<18s}  {new_str}")

    # 6-month shifts
    print(f"\n{'='*200}")
    print(f"6-MONTH HARMONIC SHIFTS — peak by October 2026")
    print(f"{'='*200}")
    rows.sort(key=lambda r: -r["delta_6mo"])
    six = [r for r in rows if r["delta_6mo"] >= 30]
    print(f"{'Tkr':<6s} {'GICS':<22s} {'Now':>5s}→{'Oct26':>5s} {'Δ6mo':>5s}  Top 3 NEW HARMONIC aspects")
    for r in six[:30]:
        nm = (r["name"] or "")[:18]
        gics = (r["sector"] or "")[:21]
        cur_set = set(a[0] for a in r["scores"][0]["actives"])
        fwd_set = set(a[0] for a in r["scores"][6]["actives"])
        new_keys = fwd_set - cur_set
        new_actives = sorted([a for a in r["scores"][6]["actives"] if a[0] in new_keys],
                              key=lambda a: -a[1])
        new_str = " | ".join(f"{a[0][0][:3]}-{a[0][1][:3]} {a[0][2]} (Δ+{a[1]:.0f})" for a in new_actives[:3])
        print(f"{r['tk']:<6s} {gics:<22s} {r['score_now']:>+4.0f} →{r['score_6mo']:>+4.0f} +{r['delta_6mo']:>4.0f}  {nm:<18s}  {new_str}")

    # Per-aspect type — which harmonic produces the most current shifts
    print(f"\n{'='*120}")
    print(f"AGGREGATE — which harmonic type produces the most active 3mo shifts in SP500")
    print(f"{'='*120}")
    asp_counts = {}
    for r in rows:
        cur_set = set(a[0] for a in r["scores"][0]["actives"])
        fwd_set = set(a[0] for a in r["scores"][3]["actives"])
        for k in (fwd_set - cur_set):
            asp_name = k[2]
            asp_counts[asp_name] = asp_counts.get(asp_name, 0) + 1
    print(f"{'Harmonic':<12s} {'#new SP500 hits in next 3mo':>30s}")
    for asp, n in sorted(asp_counts.items(), key=lambda x:-x[1]):
        print(f"{asp:<12s} {n:>10d}")

    # Export
    rows.sort(key=lambda r: -r["delta"])
    with open("/home/user/cyclepapa/data/sp500_forward_harmonic.csv","w",newline="") as f:
        w = csv.writer(f)
        w.writerow(["rank","ticker","name","sector","ipo","score_now","score_3mo",
                    "score_6mo","score_max","max_month","delta_3mo","delta_6mo","delta_max"])
        for i, r in enumerate(rows, 1):
            w.writerow([i,r["tk"],r["name"],r["sector"],r["ipo"],
                        f"{r['score_now']:+.1f}",f"{r['score_3mo']:+.1f}",
                        f"{r['score_6mo']:+.1f}",f"{r['score_max']:+.1f}",
                        r["max_month"],
                        f"{r['delta_3mo']:+.1f}",f"{r['delta_6mo']:+.1f}",
                        f"{r['delta']:+.1f}"])

if __name__ == "__main__":
    main()
