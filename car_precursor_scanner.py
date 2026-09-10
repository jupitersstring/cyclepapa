"""
CAR PRECURSOR SCANNER — find stocks whose CURRENT chart (April 2026) is
analogous to what Avis Budget Group / CAR had in March 2021 (8 months
before its Nov 2, 2021 squeeze to $545).

CAR (Avis Budget Group) natal: 2006-09-05 NYSE first-trade.
(CAR later moved to NASDAQ; the chart is anchored by the first-trade date
regardless of exchange.)

Step 1 — Compute the CAR chart and map its pre-blow-off transit signature
in March 2021. Capture all transit-outer-to-natal-point orbs ≤6° and
retrograde states.

Step 2 — Define the "signature feature vector": per transit-to-natal
aspect, (planet, target, orb-band).

Step 3 — Scan the full universe. For each ticker, compute its current
(April 2026) transit-to-natal aspects and compute a match score against
the CAR March-2021 template.

Step 4 — Return top matches ranked by similarity to the CAR template,
filtered to tradeable names.
"""
import math, csv, sys
from bti_test import compute_natal, transits_at, jd_of
from bti_v19_empirical import closest_hard
from bti_v23_sector_aware import get_sector
from bti_v24_macro import modern_sector_of
from macro_regime import macro_regime_multiplier
from filter_tradeable_v22 import CURATED_ACTIVE, BAD_NAME, BAD_TICKER

CAR_IPO = "2006-09-05"

OUTERS = ("Jupiter","Saturn","Uranus","Neptune","Pluto")
NATAL_PTS = ("Sun","Moon","ASC","MC")  # primary angles/lights
EXT_NATAL = ("Sun","Moon","ASC","MC","Mars","Jupiter","Saturn","Uranus","Neptune","Pluto")

def aspect_band(orb_deg):
    if orb_deg <= 1: return 1
    if orb_deg <= 3: return 2
    if orb_deg <= 6: return 3
    if orb_deg <= 10: return 4
    return 5

def compute_signature(natal, y, m):
    """Return dict of (transit_outer, natal_point) -> orb (if ≤6°)."""
    trans = transits_at(y, m)
    sig = {}
    for outer in OUTERS:
        for pt in EXT_NATAL:
            if pt not in natal: continue
            o = closest_hard(trans[outer]["lon"], natal[pt]["lon"])
            if o <= 8:
                sig[(outer, pt)] = o
    # Also add retrograde flags for each outer
    retro = {o: trans[o]["retro"] for o in OUTERS}
    return sig, retro

def similarity(sig_a, retro_a, sig_b, retro_b):
    """Score how closely the two signatures match.
    Bonus points for shared tight (≤3°) aspects with same natal point.
    """
    score = 0.0
    matched = []
    # Shared (outer, natal_pt) pairs with aspect ≤6°
    for k, oa in sig_a.items():
        ob = sig_b.get(k)
        if ob is None: continue
        # Both active — check tightness similarity
        diff = abs(oa - ob)
        if diff <= 1.5:
            # Very similar orb
            s = 2.0
        elif diff <= 3:
            s = 1.0
        else:
            s = 0.3
        # Weight by tightness of the CAR (template) aspect
        if oa <= 2:
            s *= 1.5
        elif oa <= 4:
            s *= 1.0
        score += s
        matched.append((k, oa, ob))
    # Retro match for outers
    retro_match = sum(1 for o in OUTERS if retro_a.get(o) == retro_b.get(o))
    score += 0.2 * retro_match
    return score, matched

def keep_tradeable(nm, tk, src):
    if not nm or not tk: return False
    if BAD_NAME.search(nm) or BAD_TICKER.search(tk): return False
    if len(tk)>5: return False
    return src=="SP500" or tk in CURATED_ACTIVE

def main():
    print(f"Loading CAR natal chart {CAR_IPO}...", file=sys.stderr)
    car_natal = compute_natal(CAR_IPO)
    print("\nCAR (Avis Budget Group) natal positions:")
    for p in EXT_NATAL:
        if p in car_natal:
            print(f"  {p:<9s} {car_natal[p]['lon']:7.2f}°")

    # Compute CAR template at several pre-blow-off dates
    PEAK_YM = (2021, 11)
    print(f"\n{'='*100}")
    print(f" CAR TRANSITS AT VARIOUS POINTS BEFORE & DURING THE Nov-2021 BLOW-OFF")
    print(f"{'='*100}")
    checkpoints = [
        ((2020, 3),  "COVID LOW (T-20mo from peak)"),
        ((2020, 11), "T-12mo (mid-rally)"),
        ((2021, 3),  "T-8mo  (MARCH 2021 — the reference date user cited)"),
        ((2021, 6),  "T-5mo"),
        ((2021, 8),  "T-3mo"),
        ((2021, 11), "PEAK Nov 2021"),
    ]
    for (y, m), label in checkpoints:
        sig, retro = compute_signature(car_natal, y, m)
        print(f"\n  {label}  ({y}-{m:02d})")
        sorted_sig = sorted(sig.items(), key=lambda x: x[1])[:8]
        for (outer, pt), o in sorted_sig:
            retro_tag = "rx" if retro.get(outer) else ""
            print(f"    t{outer}→n{pt:<4s} {o:4.2f}° {retro_tag}")
        retro_summary = "  ".join(f"{o}:{'rx' if retro[o] else 'd'}" for o in OUTERS)
        print(f"    retros: {retro_summary}")

    # Use MARCH 2021 as the template — pre-blow-off reference
    template_sig, template_retro = compute_signature(car_natal, 2021, 3)

    # Print the template clearly
    print(f"\n{'='*100}")
    print(f" CAR MARCH-2021 TEMPLATE (the pre-blow-off signature to find today)")
    print(f"{'='*100}")
    for (outer, pt), o in sorted(template_sig.items(), key=lambda x: x[1]):
        if o > 6: continue
        retro_tag = " (rx)" if template_retro.get(outer) else ""
        print(f"  t{outer:<8s}→n{pt:<5s} {o:5.2f}°{retro_tag}")

    # Now scan universe for TODAY's matches
    print(f"\n{'='*100}")
    print(f" Scanning universe for April-2026 charts matching CAR March-2021 template...")
    print(f"{'='*100}")
    seeds = []
    with open("/home/user/cyclepapa/data/universe_bti_v20.csv") as f:
        for r in csv.DictReader(f):
            tk = (r.get("ticker") or "").strip().upper()
            ipo = (r.get("ipo") or "").strip()
            nm = (r.get("name") or "").strip()
            src = (r.get("source") or "").strip()
            if not tk or not ipo or len(ipo) < 10: continue
            try: y = int(ipo[:4])
            except: continue
            age = 2026 - y
            if not (1 <= age <= 40): continue
            seeds.append({"tk":tk,"ipo":ipo,"name":nm,"src":src,"age":age})
    seen=set(); unique=[]
    for s in seeds:
        k=(s["tk"],s["ipo"])
        if k in seen: continue
        seen.add(k); unique.append(s)

    matches = []
    for s in unique:
        try:
            n = compute_natal(s["ipo"])
            if "Sun" not in n: continue
            sig, retro = compute_signature(n, 2026, 4)
            score, matched = similarity(template_sig, template_retro, sig, retro)
            if score < 3: continue  # minimum similarity threshold
            sector = get_sector(s["tk"], s["src"])
            mod = modern_sector_of(s["tk"], sector)
            mac = macro_regime_multiplier(mod, 2026, 4)
            tradeable = keep_tradeable(s["name"], s["tk"], s["src"])
            matches.append({"tk":s["tk"],"name":s["name"],"ipo":s["ipo"],
                            "src":s["src"],"sector":sector,"modern":mod,
                            "macro":mac,"score":score,"matched":matched,
                            "tradeable":tradeable})
        except:
            continue

    matches.sort(key=lambda m: -m["score"])

    # Export full
    out = "/home/user/cyclepapa/data/car_analog_universe.csv"
    with open(out, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["rank","ticker","name","sector","modern_sector","source","ipo",
                    "similarity_score","macro_now","tradeable","matched_aspects"])
        for i, m in enumerate(matches, 1):
            matched_str = " | ".join(f"t{o}-n{p}:{ca:.1f}°~{cb:.1f}°"
                                     for (o,p), ca, cb in m["matched"][:8])
            w.writerow([i, m["tk"], m["name"], m["sector"], m["modern"], m["src"],
                        m["ipo"], f"{m['score']:.2f}", f"{m['macro']:.2f}",
                        "Y" if m["tradeable"] else "N", matched_str])
    print(f"Exported {len(matches)} universe matches -> {out}")

    # Tradeable top 30
    print(f"\n{'='*180}")
    print(f" TOP 30 TRADEABLE STOCKS MATCHING CAR MARCH-2021 PRE-BLOW-OFF TEMPLATE")
    print(f"{'='*180}")
    td_matches = [m for m in matches if m["tradeable"]]
    print(f" Tradeable matches: {len(td_matches)} of {len(matches)}")
    print(f" {'Rk':>3s} {'Tkr':<6s} {'ModSec':<14s} {'IPO':<11s} {'Age':>3s} {'Score':>5s} "
          f"{'Macro':>5s}  TOP SHARED ASPECTS (tCAR-orb ~ tNOW-orb)")
    for i, m in enumerate(td_matches[:30], 1):
        nm = (m["name"] or "")[:26]
        matched_str = " | ".join(f"{o}-{p}:{ca:.1f}~{cb:.1f}"
                                 for (o,p), ca, cb in m["matched"][:4])
        print(f" {i:>3d} {m['tk']:<6s} {m['modern']:<14s} {m['ipo']:<11s} "
              f"{m['age'] if 'age' in m else 2026-int(m['ipo'][:4]):>3d} {m['score']:5.2f} "
              f"{m['macro']:5.2f}  {matched_str}   {nm}")

    # Also show full (untradeable) interesting matches
    print(f"\n{'='*180}")
    print(f" TOP 20 ALL-UNIVERSE SIMILARITY (including untradeable — for broader context)")
    print(f"{'='*180}")
    for i, m in enumerate(matches[:20], 1):
        nm = (m["name"] or "")[:26]
        td = "TR" if m["tradeable"] else "--"
        matched_str = " | ".join(f"{o}-{p}:{ca:.1f}~{cb:.1f}"
                                 for (o,p), ca, cb in m["matched"][:4])
        print(f" {i:>3d} {m['tk']:<6s} {m['modern']:<14s} {m['ipo']:<11s} "
              f"{td} {m['score']:5.2f} {matched_str}   {nm}")

if __name__ == "__main__":
    main()
