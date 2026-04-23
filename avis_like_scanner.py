"""
AVIS-SIMILAR-1-MONTH-AGO screener.

The AVIS event: transit Neptune (in Aquarius, approaching/ingressing Aries)
on the natal Sun-Moon-Neptune stellium at ~26-28° Aquarius, coinciding
with transit Sun returning to natal Sun (solar return) around Feb 17 2026.

Setup to find: stocks where transit Neptune RECENTLY went exact to natal
Sun or Moon (last 1-6 months) and is now separating by 1-3°. These have
had the "fantasy on identity" ignition but the price action often lags —
giving an entry window after the astro signal but before the crowd prices
it in.

Criteria:
  - Transit Neptune within 0.5° orb of natal Sun OR Moon at any month
    between Nov 2025 and Apr 2026 (i.e. last 0-6 months)
  - Currently (Apr 2026) Neptune has passed that exact and is
    1-3° separating
  - Optional: natal Sun-Neptune <=5° (AVIS-DNA - born bubblish)
  - Optional: solar return coincidence — transit Sun within 15° of
    natal Sun in the month of Neptune exact
"""
import csv, sys, time
import swisseph as swe
from bti_test import compute_natal, transits_at, jd_of
from bti_v19_empirical import closest_hard
from bti_v23_sector_aware import get_sector
from bti_v24_macro import modern_sector_of
from macro_regime import macro_regime_multiplier
from filter_tradeable_v22 import CURATED_ACTIVE, BAD_NAME, BAD_TICKER

def nep_lon(y, m):
    jd = jd_of(y, m, 15, 12.0)
    return swe.calc_ut(jd, swe.NEPTUNE)[0][0] % 360

def sun_lon(y, m):
    jd = jd_of(y, m, 15, 12.0)
    return swe.calc_ut(jd, swe.SUN)[0][0] % 360

def keep_tradeable(nm, tk, src):
    if not nm or not tk: return False
    if BAD_NAME.search(nm) or BAD_TICKER.search(tk): return False
    if len(tk)>5: return False
    return src=="SP500" or tk in CURATED_ACTIVE

def find_exact_date(target_lon, start_y, start_m, months_back=6, months_fwd=3):
    """Sample each month in window; return (y, m, orb) of tightest hit."""
    best = None
    for k in range(-months_back, months_fwd+1):
        y = start_y + (start_m - 1 + k) // 12
        m = (start_m - 1 + k) % 12 + 1
        if m <= 0: m += 12; y -= 1
        nl = nep_lon(y, m)
        o = closest_hard(nl, target_lon)
        if best is None or o < best["orb"]:
            best = {"y":y, "m":m, "orb":o}
    return best

def main():
    START_Y, START_M = 2026, 4
    # Neptune position series for the backward window
    print("Building backward Neptune positions...", file=sys.stderr)

    seeds = []
    with open("/home/user/cyclepapa/data/universe_bti_v20.csv") as f:
        for r in csv.DictReader(f):
            tk = (r.get("ticker") or "").strip().upper()
            ipo = (r.get("ipo") or "").strip()
            nm = (r.get("name") or "").strip()
            src = (r.get("source") or "").strip()
            if not tk or not ipo or len(ipo)<10: continue
            try: y = int(ipo[:4])
            except: continue
            age = START_Y - y
            if not (1 <= age <= 40): continue
            if not keep_tradeable(nm, tk, src): continue
            seeds.append({"tk":tk,"ipo":ipo,"name":nm,"src":src})
    seen=set(); unique=[]
    for s in seeds:
        k=(s["tk"],s["ipo"])
        if k in seen: continue
        seen.add(k); unique.append(s)
    print(f"Universe: {len(unique)}", file=sys.stderr)

    now_nep = nep_lon(2026, 4)
    hits = []
    for s in unique:
        try:
            natal = compute_natal(s["ipo"])
            sun_n = natal["Sun"]["lon"]
            moon_n = natal.get("Moon",{}).get("lon", None)
            natal_sun_nep = closest_hard(sun_n, natal["Neptune"]["lon"])
            natal_moon_nep = closest_hard(moon_n, natal["Neptune"]["lon"]) if moon_n else 99

            # Find tightest Neptune-to-Sun and Neptune-to-Moon in past 6 months
            sun_hit = find_exact_date(sun_n, START_Y, START_M, months_back=6, months_fwd=1)
            moon_hit = find_exact_date(moon_n, START_Y, START_M, months_back=6, months_fwd=1) if moon_n else None

            # Current orbs
            cur_sun = closest_hard(now_nep, sun_n)
            cur_moon = closest_hard(now_nep, moon_n) if moon_n else 99

            # Criterion: best Neptune-aspect was within ≤0.5° in past 6 months
            # AND current orb is 1-3° (so it has separated)
            candidates = []
            if sun_hit and sun_hit["orb"] <= 0.5 and 0.5 < cur_sun <= 3.5:
                # was the exact in PAST vs current month?
                exact_k = (sun_hit["y"] - START_Y)*12 + (sun_hit["m"] - START_M)
                if -6 <= exact_k <= 0:
                    candidates.append({"target":"Sun","target_lon":sun_n,
                                       "exact_y":sun_hit["y"],"exact_m":sun_hit["m"],
                                       "exact_orb":sun_hit["orb"],
                                       "cur_orb":cur_sun,"months_ago":-exact_k})
            if moon_hit and moon_hit["orb"] <= 0.5 and 0.5 < cur_moon <= 3.5:
                exact_k = (moon_hit["y"] - START_Y)*12 + (moon_hit["m"] - START_M)
                if -6 <= exact_k <= 0:
                    candidates.append({"target":"Moon","target_lon":moon_n,
                                       "exact_y":moon_hit["y"],"exact_m":moon_hit["m"],
                                       "exact_orb":moon_hit["orb"],
                                       "cur_orb":cur_moon,"months_ago":-exact_k})

            for c in candidates:
                # Check if solar return near the exact — transit Sun within 15° of natal Sun
                sun_at_exact = sun_lon(c["exact_y"], c["exact_m"])
                sun_return_orb = orb_of(sun_at_exact, sun_n)

                sector = get_sector(s["tk"], s["src"])
                mod_sec = modern_sector_of(s["tk"], sector)
                macro_now = macro_regime_multiplier(mod_sec, 2026, 4)

                hits.append({
                    "tk":s["tk"],"name":s["name"],"ipo":s["ipo"],"src":s["src"],
                    "sector":sector,"modern":mod_sec,
                    "target":c["target"],
                    "exact_y":c["exact_y"],"exact_m":c["exact_m"],
                    "exact_orb":c["exact_orb"],"cur_orb":c["cur_orb"],
                    "months_ago":c["months_ago"],
                    "natal_sun_nep":natal_sun_nep,
                    "natal_moon_nep":natal_moon_nep,
                    "sun_return_orb":sun_return_orb,
                    "macro_now":macro_now,
                })
        except: continue

    hits.sort(key=lambda h: (h["months_ago"], h["exact_orb"]))

    out = "/home/user/cyclepapa/data/avis_like_candidates.csv"
    with open(out,"w",newline="") as f:
        w = csv.writer(f)
        w.writerow(["rank","ticker","name","sector","modern_sector","ipo",
                    "target","exact_month","exact_orb","months_ago","current_orb",
                    "natal_sun_neptune","natal_moon_neptune","sun_return_orb_at_exact",
                    "macro_now"])
        for i, h in enumerate(hits, 1):
            w.writerow([i,h["tk"],h["name"],h["sector"],h["modern"],h["ipo"],
                        h["target"],f"{h['exact_y']}-{h['exact_m']:02d}",
                        f"{h['exact_orb']:.2f}",h["months_ago"],f"{h['cur_orb']:.2f}",
                        f"{h['natal_sun_nep']:.2f}",f"{h['natal_moon_nep']:.2f}",
                        f"{h['sun_return_orb']:.1f}",f"{h['macro_now']:.2f}"])
    print(f"Exported {len(hits)} -> {out}")

    print(f"\n{'='*155}")
    print(f"AVIS-LIKE — Neptune recently ignited natal Sun/Moon (exact 0-6 months ago, now 0.5-3.5° separated)")
    print(f"{'='*155}")
    print(f"{'Tkr':<6s} {'ModSec':<13s} {'Name':<30s} {'IPO':<11s} {'Tgt':<4s} "
          f"{'Exact':<8s} {'moAgo':>5s} {'ExOrb':>5s} {'NowOrb':>6s} {'NatSN':>5s} "
          f"{'SunRt':>5s} {'mPk':>4s}  tags")
    for h in hits[:60]:
        nm = (h["name"] or "")[:29]
        avis = "★AVIS" if h["natal_sun_nep"] <= 5 else ""
        sr_tag = "SR!" if h["sun_return_orb"] <= 20 else ""
        print(f"{h['tk']:<6s} {h['modern']:<13s} {nm:<30s} {h['ipo']:<11s} {h['target']:<4s} "
              f"{h['exact_y']}-{h['exact_m']:02d}   {h['months_ago']:5d} {h['exact_orb']:5.2f} "
              f"{h['cur_orb']:6.2f} {h['natal_sun_nep']:5.2f} "
              f"{h['sun_return_orb']:5.1f} {h['macro_now']:.2f}  {avis} {sr_tag}")

    # ------ AVIS DNA subset ------
    avis_subset = [h for h in hits if h["natal_sun_nep"] <= 5]
    print(f"\n{'='*155}")
    print(f"★ AVIS-DNA SUBSET — natal Sun-Neptune ≤5° PLUS recent Neptune ignition to Sun/Moon")
    print(f"{'='*155}")
    for h in sorted(avis_subset, key=lambda x: (x["months_ago"], x["exact_orb"])):
        nm = (h["name"] or "")[:30]
        print(f"{h['tk']:<6s} {h['modern']:<13s} {nm:<30s} {h['ipo']:<11s} {h['target']:<4s} "
              f"{h['exact_y']}-{h['exact_m']:02d}  {h['months_ago']:>3d}mo ago  "
              f"NatSN {h['natal_sun_nep']:5.2f}°  CurOrb {h['cur_orb']:5.2f}°  mPk {h['macro_now']:.2f}")

def orb_of(a, b):
    d = abs((a - b) % 360)
    return min(d, 360 - d)

if __name__ == "__main__":
    main()
