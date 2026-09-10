"""
HORIZON-BUCKETED ASYMMETRY — 3 / 6 / 12 month windows (from 2026-07-01).

Takes the 189 verified-alive survivors from deep_asymmetric_jul2026.csv,
recomputes monthly forward scores, and buckets the shift by horizon:
  3MO : peak score within Aug-Oct 2026  (window months 1-3)
  6MO : peak score within Nov 2026-Jan 2027 (months 4-6)
  12MO: peak score within Feb-Jul 2027 (months 7-12)

Horizon asymmetry = (window_max - now) x washout multiplier x natal mult
(+ activation bonuses carried from the deep hunt). A name is assigned to
the EARLIEST horizon whose window contains (or nearly matches) its global
peak, and also ranked within every window by its window-specific delta.
"""
import csv, pickle, sys
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

def main():
    with open("/home/user/cyclepapa/data/event_study_keys.pkl","rb") as f:
        key_stats = pickle.load(f)
    key_by_pair = {}
    for (tp, np_, asp_name), v in key_stats.items():
        if v.get("n_w",0)>=10 and v.get("n_c",0)>=5 and "delta_365" in v:
            key_by_pair.setdefault((tp, np_), []).append((ASPECTS[asp_name], v["delta_365"]))

    # months 0..12 from Jul 2026
    months = []
    y, m = 2026, 7
    for _ in range(13):
        months.append((y, m)); m += 1
        if m > 12: m = 1; y += 1
    monthly_lons = [ {p: swe.calc_ut(swe.julday(yy, mm, 15, 12.0), pid)[0][0] % 360
                      for p, pid in PIDS.items()} for (yy, mm) in months ]

    def score(natal, lons):
        s = 0.0
        for tp, tlon in lons.items():
            for np_ in NATAL_PTS:
                if np_ not in natal: continue
                pairs = key_by_pair.get((tp, np_))
                if not pairs: continue
                npon = natal[np_]["lon"]
                for asp_deg, delta in pairs:
                    if aspect_orb(tlon, npon, asp_deg) <= 2.5:
                        s += delta
        return s

    rows = []
    with open("/home/user/cyclepapa/data/deep_asymmetric_jul2026.csv") as f:
        for r in csv.DictReader(f):
            rows.append(r)
    print(f"Survivors loaded: {len(rows)}", file=sys.stderr)

    out_rows = []
    for r in rows:
        try:
            natal = compute_natal(r["ipo"])
        except: continue
        scores = [score(natal, ml) for ml in monthly_lons]
        now = scores[0]
        w3  = max(scores[1:4]);   w3_i  = scores[1:4].index(w3)  + 1
        w6  = max(scores[4:7]);   w6_i  = scores[4:7].index(w6)  + 4
        w12 = max(scores[7:13]);  w12_i = scores[7:13].index(w12) + 7
        d3, d6, d12 = w3 - now, w6 - now, w12 - now

        chg12 = float(r["chg_12mo"]) if r["chg_12mo"] else None
        chg3  = float(r["chg_3mo"]) if r["chg_3mo"] else None
        nat_mult = float(r["natal_mult"])
        wash = 1.0
        if chg12 is not None:
            if chg12 <= -50: wash = 1.5
            elif chg12 <= -30: wash = 1.3
            elif chg12 <= -10: wash = 1.15
            elif chg12 >= 100: wash = 0.7
        recycled = r["recycled_flag"] == "Y"

        def mo_str(i): return f"{months[i][0]}-{months[i][1]:02d}"
        out_rows.append({
            "tk": r["ticker"], "name": r["name"], "ipo": r["ipo"],
            "src": r["source"], "last": r["last_close"],
            "chg3": chg3, "chg12": chg12, "from_low": r["from_low_12"],
            "from_high": r["from_high"], "recycled": recycled,
            "now": now,
            "a3":  d3  * wash * nat_mult, "d3": d3,  "m3": mo_str(w3_i),
            "a6":  d6  * wash * nat_mult, "d6": d6,  "m6": mo_str(w6_i),
            "a12": d12 * wash * nat_mult, "d12": d12,"m12": mo_str(w12_i),
        })

    def report(label, key, dkey, mkey):
        print(f"\n{'='*165}")
        print(f"{label}")
        print(f"{'='*165}")
        rs = sorted([o for o in out_rows if not o["recycled"] and o[dkey] > 0],
                    key=lambda o: -o[key])
        print(f"{'#':>3s} {'Tkr':<6s} {'IPO':<11s} {'Now':>5s} {'Δwin':>5s} {'PkMo':<8s} "
              f"{'pr3':>6s} {'pr12':>6s} {'fHi':>6s} {'$':>9s} {'ASYM':>6s}  Name")
        for i, o in enumerate(rs[:15], 1):
            c3 = f"{o['chg3']:+5.0f}%" if o['chg3'] is not None else "   n/a"
            c12 = f"{o['chg12']:+5.0f}%" if o['chg12'] is not None else "   n/a"
            fh = f"{float(o['from_high']):+5.0f}%" if o['from_high'] else "  n/a"
            print(f"{i:3d} {o['tk']:<6s} {o['ipo']:<11s} {o['now']:>+4.0f} {o[dkey]:>+4.0f} {o[mkey]:<8s} "
                  f"{c3:>6s} {c12:>6s} {fh:>6s} {float(o['last']):>9.2f} {o[key]:>6.0f}  {(o['name'] or '')[:26]}")
        return rs

    r3 = report("3-MONTH HORIZON — peak within Aug-Oct 2026 (exit before/at Node-ingress window)", "a3", "d3", "m3")
    r6 = report("6-MONTH HORIZON — peak within Nov 2026-Jan 2027 (U-P trine #2 Nov 29)", "a6", "d6", "m6")
    r12 = report("12-MONTH HORIZON — peak within Feb-Jul 2027 (trine #3 Jun 15 2027)", "a12", "d12", "m12")

    # Export
    with open("/home/user/cyclepapa/data/horizon_asymmetric_jul2026.csv","w",newline="") as f:
        w = csv.writer(f)
        w.writerow(["ticker","name","ipo","source","last","chg_3mo","chg_12mo","from_high",
                    "score_now","d3","peak3","asym3","d6","peak6","asym6","d12","peak12","asym12","recycled"])
        for o in sorted(out_rows, key=lambda x: -max(x["a3"],x["a6"],x["a12"])):
            w.writerow([o["tk"],o["name"],o["ipo"],o["src"],o["last"],
                        o["chg3"] if o["chg3"] is not None else "",
                        o["chg12"] if o["chg12"] is not None else "",
                        o["from_high"],f"{o['now']:+.0f}",
                        f"{o['d3']:+.0f}",o["m3"],f"{o['a3']:.0f}",
                        f"{o['d6']:+.0f}",o["m6"],f"{o['a6']:.0f}",
                        f"{o['d12']:+.0f}",o["m12"],f"{o['a12']:.0f}",
                        "Y" if o["recycled"] else ""])
    print(f"\nExported -> data/horizon_asymmetric_jul2026.csv")

if __name__ == "__main__":
    main()
