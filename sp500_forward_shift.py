"""
Forward shift scanner — find SP500 stocks whose today-active-aspect score
will SHIFT bullishly in the next 1-6 months.

For each chart, compute the today-active score at:
  Apr 2026 (now)
  May 2026 (+1mo)
  Jun 2026 (+2mo)
  Jul 2026 (+3mo)
  Aug 2026 (+4mo)
  Sep 2026 (+5mo)
  Oct 2026 (+6mo)

Identify stocks where the score JUMPS most in the forward window.
Different from absolute today-bullish; this is rate-of-change bullish.
"""
import csv, math, pickle, sys
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

def date_jd(y, m, d=15):
    return swe.julday(y, m, d, 12.0)

def planet_lons(jd):
    return {p: swe.calc_ut(jd, pid)[0][0] % 360 for p, pid in PIDS.items()}

def chart_score(natal, lons, valid_keys, orb=2.5):
    score = 0.0
    n_active = 0
    actives = []
    for tp_name, tlon in lons.items():
        for np_name in NATAL_PTS:
            if np_name not in natal: continue
            npon = natal[np_name]["lon"]
            for asp_name, asp_deg in ASPECTS.items():
                cur_orb = aspect_orb(tlon, npon, asp_deg)
                if cur_orb <= orb:
                    key = (tp_name, np_name, asp_name)
                    if key in valid_keys:
                        d = valid_keys[key]["delta_365"]
                        score += d
                        n_active += 1
                        actives.append((key, d, cur_orb))
    return score, n_active, actives

def main():
    print("Loading keys + SP500...", file=sys.stderr)
    with open("/home/user/cyclepapa/data/event_study_keys.pkl","rb") as f:
        key_stats = pickle.load(f)
    valid_keys = {k:v for k,v in key_stats.items()
                  if v.get("n_w",0)>=10 and v.get("n_c",0)>=5 and "delta_365" in v}
    print(f"  {len(valid_keys)} valid keys", file=sys.stderr)

    sp500 = []
    with open("/home/user/cyclepapa/data/sp500_ipo_dates.csv") as f:
        for r in csv.DictReader(f):
            tk = r["ticker"].strip().upper()
            ipo = (r.get("ipo_date") or "").strip()
            if not ipo or len(ipo)<10: continue
            sp500.append({"tk":tk,"ipo":ipo,
                          "name":r.get("name","").strip(),
                          "sector":r.get("sector","").strip()})
    print(f"  {len(sp500)} SP500", file=sys.stderr)

    # Forward months — use months from Apr 2026 to Apr 2027
    months = [(2026, m) for m in range(4, 13)] + [(2027, m) for m in range(1, 5)]
    print(f"  {len(months)} forward months: Apr 2026 → Apr 2027", file=sys.stderr)

    # Precompute planet positions for each month
    monthly_lons = {}
    for y, m in months:
        jd = date_jd(y, m)
        monthly_lons[(y,m)] = planet_lons(jd)

    print("Scanning SP500 forward trajectory...", file=sys.stderr)
    rows = []
    for s in sp500:
        try:
            natal = compute_natal(s["ipo"])
        except: continue
        scores = []
        for (y, m) in months:
            sc, n_act, actives = chart_score(natal, monthly_lons[(y,m)], valid_keys)
            scores.append({"y":y,"m":m,"score":sc,"n":n_act,"actives":actives})
        s["scores"] = scores
        # Today's score
        s["score_now"] = scores[0]["score"]
        # Find max forward score
        forward = scores[1:]  # months after current
        if forward:
            max_fwd = max(forward, key=lambda x:x["score"])
            s["score_max"] = max_fwd["score"]
            s["max_month"] = f"{max_fwd['y']}-{max_fwd['m']:02d}"
            s["delta"] = max_fwd["score"] - s["score_now"]
            # Time to max
            s["t_to_max"] = forward.index(max_fwd) + 1
        else:
            s["score_max"] = s["score_now"]
            s["max_month"] = ""
            s["delta"] = 0
            s["t_to_max"] = 0
        # Look at 3-month forward delta specifically
        if len(scores) >= 4:
            s["score_3mo"] = scores[3]["score"]
            s["delta_3mo"] = scores[3]["score"] - s["score_now"]
        else:
            s["score_3mo"] = s["score_now"]
            s["delta_3mo"] = 0
        if len(scores) >= 7:
            s["score_6mo"] = scores[6]["score"]
            s["delta_6mo"] = scores[6]["score"] - s["score_now"]
        else:
            s["score_6mo"] = s["score_now"]
            s["delta_6mo"] = 0
        rows.append(s)

    # Rank by largest forward shift (delta to max)
    rows.sort(key=lambda r: -r["delta"])

    # Filter to those where today's score is moderate or low (not already at peak)
    # AND the shift is meaningful (>= 50pp)
    shifts = [r for r in rows if r["delta"] >= 50 and r["score_now"] < 200]

    print(f"\n{'='*200}")
    print(f"SP500 — BIGGEST FORWARD SHIFTS in next 12 months (Apr 2026 → Apr 2027)")
    print(f"  Filter: today's score < 200 (not yet maxed) AND forward Δ ≥ 50")
    print(f"  Shows: shift from current to max forward score within next year")
    print(f"{'='*200}")
    print(f"{'#':>3s} {'Tkr':<6s} {'GICS':<22s} {'Now':>6s} → {'Max':>6s}  {'Δ':>6s}  {'PeakMo':<8s} {'tMax':>4s}  {'Now+3':>6s} {'Δ3mo':>6s}  {'Now+6':>6s} {'Δ6mo':>6s}  Name")
    for i, r in enumerate(shifts[:50], 1):
        nm = (r["name"] or "")[:18]
        gics = (r["sector"] or "")[:21]
        print(f"{i:3d} {r['tk']:<6s} {gics:<22s} {r['score_now']:>+5.0f}  →{r['score_max']:>+5.0f}  "
              f"+{r['delta']:>4.0f}  {r['max_month']:<8s} {r['t_to_max']:>3d}mo  "
              f"{r['score_3mo']:>+5.0f}  {r['delta_3mo']:>+5.0f}  "
              f"{r['score_6mo']:>+5.0f}  {r['delta_6mo']:>+5.0f}  {nm}")

    # Specific 3-month shifts (most imminent)
    print(f"\n{'='*200}")
    print(f"BIGGEST IMMINENT SHIFTS — 3-month forward delta (peak by July 2026)")
    print(f"{'='*200}")
    rows.sort(key=lambda r: -r["delta_3mo"])
    imminent = [r for r in rows if r["delta_3mo"] >= 30 and r["score_now"] < 200]
    print(f"{'Tkr':<6s} {'GICS':<22s} {'Now':>6s} → {'Jul26':>6s}  {'Δ3mo':>5s}  {'Δ6mo':>5s}  Top 3 NEW aspects activating")
    for r in imminent[:30]:
        nm = (r["name"] or "")[:18]
        gics = (r["sector"] or "")[:21]
        # Find aspects in scores[3] that are NOT in scores[0]
        cur_set = set(a[0] for a in r["scores"][0]["actives"])
        fwd_set = set(a[0] for a in r["scores"][3]["actives"])
        new_keys = fwd_set - cur_set
        new_actives = sorted([a for a in r["scores"][3]["actives"] if a[0] in new_keys],
                              key=lambda a: -a[1])
        new_str = " | ".join(f"{a[0][0][:3]}-{a[0][1][:3]} {a[0][2]} (Δ+{a[1]:.0f})" for a in new_actives[:3])
        print(f"{r['tk']:<6s} {gics:<22s} {r['score_now']:>+5.0f}  →{r['score_3mo']:>+5.0f}  "
              f"+{r['delta_3mo']:>4.0f}  {r['delta_6mo']:>+5.0f}  {nm:<18s}  {new_str}")

    # Specific 6-month shifts
    print(f"\n{'='*200}")
    print(f"BIGGEST 6-MONTH SHIFTS — peaking by October 2026")
    print(f"{'='*200}")
    rows.sort(key=lambda r: -r["delta_6mo"])
    six = [r for r in rows if r["delta_6mo"] >= 50 and r["score_now"] < 200]
    print(f"{'Tkr':<6s} {'GICS':<22s} {'Now':>6s} → {'Oct26':>6s}  {'Δ6mo':>5s}  Top 3 NEW aspects")
    for r in six[:30]:
        nm = (r["name"] or "")[:18]
        gics = (r["sector"] or "")[:21]
        cur_set = set(a[0] for a in r["scores"][0]["actives"])
        fwd_set = set(a[0] for a in r["scores"][6]["actives"])
        new_keys = fwd_set - cur_set
        new_actives = sorted([a for a in r["scores"][6]["actives"] if a[0] in new_keys],
                              key=lambda a: -a[1])
        new_str = " | ".join(f"{a[0][0][:3]}-{a[0][1][:3]} {a[0][2]} (Δ+{a[1]:.0f})" for a in new_actives[:3])
        print(f"{r['tk']:<6s} {gics:<22s} {r['score_now']:>+5.0f}  →{r['score_6mo']:>+5.0f}  "
              f"+{r['delta_6mo']:>4.0f}  {nm:<18s}  {new_str}")

    # Export
    rows.sort(key=lambda r: -r["delta"])
    with open("/home/user/cyclepapa/data/sp500_forward_shift.csv","w",newline="") as f:
        w = csv.writer(f)
        w.writerow(["rank","ticker","name","sector","ipo","score_now","score_3mo",
                    "score_6mo","score_max","max_month","delta_3mo","delta_6mo","delta_max"])
        for i, r in enumerate(rows, 1):
            w.writerow([i,r["tk"],r["name"],r["sector"],r["ipo"],
                        f"{r['score_now']:+.1f}",f"{r['score_3mo']:+.1f}",
                        f"{r['score_6mo']:+.1f}",f"{r['score_max']:+.1f}",r["max_month"],
                        f"{r['delta_3mo']:+.1f}",f"{r['delta_6mo']:+.1f}",f"{r['delta']:+.1f}"])

if __name__ == "__main__":
    main()
