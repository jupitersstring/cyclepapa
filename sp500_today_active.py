"""
SP500 TODAY-ACTIVE-ASPECTS scanner.

For each SP500 chart, identify which aspect-keys are CURRENTLY active
(within 2.5° as of April 2026) and sum the empirical expected
12-month forward return delta from event_study_v3 (winners vs controls).

Output: SP500 ranked by today's expected-return-from-aspect-stack.
"""
import csv, os, json, subprocess, math, sys, time, pickle
from datetime import datetime, timezone, timedelta
import statistics as st
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
    print("Loading event-study key statistics...", file=sys.stderr)
    with open("/home/user/cyclepapa/data/event_study_keys.pkl","rb") as f:
        key_stats = pickle.load(f)
    # Filter keys to those with sufficient sample (n_w >= 10 AND n_c >= 5)
    # Use 12mo delta as the expected-return signal
    valid_keys = {}
    for key, stats in key_stats.items():
        if stats.get("n_w",0) >= 10 and stats.get("n_c",0) >= 5 and "delta_365" in stats:
            valid_keys[key] = stats
    print(f"  {len(valid_keys)} keys valid (n_w>=10, n_c>=5)", file=sys.stderr)

    # Load SP500 with IPO dates
    print("Loading SP500...", file=sys.stderr)
    sp500 = []
    with open("/home/user/cyclepapa/data/sp500_ipo_dates.csv") as f:
        for r in csv.DictReader(f):
            tk = r["ticker"].strip().upper()
            ipo = (r.get("ipo_date") or "").strip()
            nm = r.get("name","").strip()
            sec = r.get("sector","").strip()
            if not ipo or len(ipo) < 10: continue
            sp500.append({"tk":tk,"ipo":ipo,"name":nm,"sector":sec})
    print(f"  {len(sp500)} SP500 names", file=sys.stderr)

    # Today's date
    today_jd = swe.julday(2026, 4, 22, 12.0)
    today_lons = {p: swe.calc_ut(today_jd, pid)[0][0] % 360 for p, pid in PIDS.items()}

    # For each SP500 stock, identify active aspects and sum expected fwd-return deltas
    print("Scanning SP500 today-active aspects...", file=sys.stderr)
    results = []
    for s in sp500:
        try:
            natal = compute_natal(s["ipo"])
        except: continue
        active_aspects = []
        for tp_name in PIDS:
            if tp_name in ("Sun","Moon"): continue
            tlon = today_lons[tp_name]
            for np_name in NATAL_PTS:
                if np_name not in natal: continue
                npon = natal[np_name]["lon"]
                for asp_name, asp_deg in ASPECTS.items():
                    cur_orb = aspect_orb(tlon, npon, asp_deg)
                    if cur_orb <= 2.5:
                        key = (tp_name, np_name, asp_name)
                        if key in valid_keys:
                            stats = valid_keys[key]
                            active_aspects.append({
                                "key":key,
                                "orb":cur_orb,
                                "delta_365":stats["delta_365"],
                                "w_med_365":stats.get("w_med_365",0),
                                "c_med_365":stats.get("c_med_365",0),
                                "n_w":stats["n_w"],"n_c":stats["n_c"],
                            })
        # Sum the 12mo deltas as the bullishness score
        total_delta = sum(a["delta_365"] for a in active_aspects)
        # Also compute pure W-median sum (absolute expected return)
        total_w = sum(a["w_med_365"] for a in active_aspects)
        n_active = len(active_aspects)
        n_pos = sum(1 for a in active_aspects if a["delta_365"] > 0)
        n_neg = sum(1 for a in active_aspects if a["delta_365"] < 0)
        if active_aspects:
            top_3 = sorted(active_aspects, key=lambda a: -a["delta_365"])[:3]
            top_str = " | ".join(f"{a['key'][0][:3]}-{a['key'][1][:3]} {a['key'][2]} (Δ{a['delta_365']:+.0f})"
                                 for a in top_3)
        else: top_str = ""
        results.append({**s,"total_delta":total_delta,"total_w":total_w,
                        "n_active":n_active,"n_pos":n_pos,"n_neg":n_neg,"top":top_str})

    # Rank
    results.sort(key=lambda r: -r["total_delta"])

    print(f"\n{'='*200}")
    print(f"SP500 RANKED BY TODAY'S ACTIVE-ASPECT EXPECTED 12-MONTH RETURN")
    print(f"  Sum of empirical W-vs-C deltas across all aspects within 2.5° NOW (Apr 22 2026)")
    print(f"  Higher = more bullish 12mo outlook based on event-study deltas")
    print(f"{'='*200}")
    print(f"{'#':>3s} {'Tkr':<6s} {'GICS':<22s} {'IPO':<11s} {'Σ Δ12mo':>9s} {'Σ W12mo':>9s} {'#act':>4s} {'+/-':>7s}  Top-3 active aspects (Δ12mo)")
    for i, r in enumerate(results[:60], 1):
        gics = (r["sector"] or "")[:21]
        nm = (r["name"] or "")[:18]
        print(f"{i:3d} {r['tk']:<6s} {gics:<22s} {r['ipo']:<11s} "
              f"{r['total_delta']:>+8.1f} {r['total_w']:>+8.1f} "
              f"{r['n_active']:>4d} {r['n_pos']}/{r['n_neg']:<5d}  {r['top']}  ({nm})")

    # Bottom 30
    print(f"\n{'='*200}")
    print(f"SP500 RANKED — MOST BEARISH (avoid/short candidates by today's active-aspect expected delta)")
    print(f"{'='*200}")
    results.sort(key=lambda r: r["total_delta"])
    for i, r in enumerate(results[:30], 1):
        gics = (r["sector"] or "")[:21]
        nm = (r["name"] or "")[:18]
        print(f"{i:3d} {r['tk']:<6s} {gics:<22s} {r['ipo']:<11s} "
              f"{r['total_delta']:>+8.1f} {r['total_w']:>+8.1f} "
              f"{r['n_active']:>4d} {r['n_pos']}/{r['n_neg']:<5d}  ({nm})")

    # Export
    results.sort(key=lambda r: -r["total_delta"])
    with open("/home/user/cyclepapa/data/sp500_today_active.csv","w",newline="") as f:
        w = csv.writer(f)
        w.writerow(["rank","ticker","name","sector","ipo","total_delta_12mo",
                    "total_w_12mo","n_active","n_pos","n_neg","top_aspects"])
        for i, r in enumerate(results, 1):
            w.writerow([i,r["tk"],r["name"],r["sector"],r["ipo"],
                        f"{r['total_delta']:+.2f}",f"{r['total_w']:+.2f}",
                        r["n_active"],r["n_pos"],r["n_neg"],r["top"]])
    print(f"\nExported full ranked list to data/sp500_today_active.csv ({len(results)} names)")

if __name__ == "__main__":
    main()
