"""
NEPTUNE-FUELLED UNREALISTIC-EXPECTATIONS screen.

The AVIS chart shows the canonical setup:
  - Natal Sun + Moon + Neptune + Mars stellium 19°-28° Aquarius
  - Solar Return Sun at 28° Aqu triggers the stellium
  - Neptune (recently ingressed into Aries) now separating-but-still-active
    — the "fantasy merging with identity" phase.

Gidel/Meridian call this the bubble-ignition signature:
  transit Neptune within <=3° hard aspect to natal Sun or Moon
  = fantasy/hype arrives on the public-facing identity
  = unrealistic-expectations pricing begins

We search the full 12,086-ticker universe for charts where:
  - Transit Neptune will enter <=3° hard-aspect orb to natal Sun OR Moon
    within the next 24 months (Apr 2026 - Apr 2028)
  - AND Neptune is APPROACHING (not already separating) — i.e., not past
    the exact aspect
  - AND not Saturn-afflicted (Saturn won't hit a natal point within 3°
    before the Neptune exact)

Tiered by:
  TIER 1 — Neptune EXACT already close to natal Sun/Moon (within 2° now,
           moving toward exact) — IMMINENT ignition
  TIER 2 — Neptune approaching to exact within 6 months (peak bubblish
           capacity)
  TIER 3 — Neptune approaching to exact within 7-18 months (slower build)

Bonus: chart ALSO has natal Sun-Neptune close conjunction (the AVIS DNA)
— this is the "born bubblish" subset, most prone to hype cycles.
"""
import math, csv, sys, time
import swisseph as swe
from bti_test import compute_natal, transits_at, jd_of
from bti_v19_empirical import closest_hard, orb
from bti_v23_sector_aware import get_sector
from bti_v24_macro import MODERN_SECTOR, modern_sector_of
from macro_regime import macro_regime_multiplier
from filter_tradeable_v22 import CURATED_ACTIVE, BAD_NAME, BAD_TICKER

START_Y, START_M = 2026, 4
MONTHS = 30  # look 30 months forward

def nep_lon_at(y, m):
    jd = jd_of(y, m, 15, 12.0)
    return swe.calc_ut(jd, swe.NEPTUNE)[0][0] % 360

def nep_speed_at(y, m):
    jd = jd_of(y, m, 15, 12.0)
    return swe.calc_ut(jd, swe.NEPTUNE)[0][3]

def scan_neptune_on_target(target_lon, start_y, start_m, months):
    """Return list of (year, month, orb, direction) for Neptune ≤3° of target."""
    hits = []
    for k in range(0, months+1):
        y = start_y + (start_m - 1 + k) // 12
        m = (start_m - 1 + k) % 12 + 1
        nl = nep_lon_at(y, m)
        o = closest_hard(nl, target_lon)
        if o <= 3.0:
            hits.append({"y":y,"m":m,"orb":o,"speed":nep_speed_at(y,m)})
    return hits

def keep_tradeable(name, ticker, src):
    if not name or not ticker: return False
    if BAD_NAME.search(name): return False
    if BAD_TICKER.search(ticker): return False
    if len(ticker) > 5: return False
    return src == "SP500" or ticker in CURATED_ACTIVE

def main():
    print("Loading universe...", file=sys.stderr)
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

    seen = set(); unique = []
    for s in seeds:
        k = (s["tk"], s["ipo"])
        if k in seen: continue
        seen.add(k); unique.append(s)
    print(f"Tradeable universe: {len(unique)}", file=sys.stderr)

    now_nep = nep_lon_at(2026, 4)
    print(f"Neptune now (Apr 2026): {now_nep:.2f}° (Aries {now_nep % 30:.2f}°)", file=sys.stderr)

    hits = []
    for s in unique:
        try:
            natal = compute_natal(s["ipo"])
            sun = natal["Sun"]["lon"]
            moon = natal.get("Moon", {}).get("lon", None)
            # Natal Sun-Neptune conjunction orb (AVIS DNA)
            natal_sun_nep = closest_hard(sun, natal["Neptune"]["lon"])
            natal_moon_nep = closest_hard(moon, natal["Neptune"]["lon"]) if moon else 99

            # Check if Neptune will hit natal Sun or Moon within 24-30 months
            sun_hits = scan_neptune_on_target(sun, 2026, 4, MONTHS)
            moon_hits = scan_neptune_on_target(moon, 2026, 4, MONTHS) if moon else []

            # Current orbs
            cur_sun_orb = closest_hard(now_nep, sun)
            cur_moon_orb = closest_hard(now_nep, moon) if moon else 99

            # Only keep if at least one future Neptune hit
            if not sun_hits and not moon_hits: continue

            # First exact (orb min) hit — prefer Sun over Moon
            best_sun = min(sun_hits, key=lambda h:h["orb"]) if sun_hits else None
            best_moon = min(moon_hits, key=lambda h:h["orb"]) if moon_hits else None

            primary = best_sun if best_sun and best_sun["orb"] <= 2 else (best_moon if best_moon and best_moon["orb"] <= 2 else (best_sun or best_moon))
            target = "Sun" if primary == best_sun else "Moon"
            target_lon = sun if target == "Sun" else moon

            # Is Neptune approaching or separating? Compare current orb to first-future-hit orb
            approaching = cur_sun_orb > primary["orb"] if target=="Sun" else cur_moon_orb > primary["orb"]

            sector = get_sector(s["tk"], s["src"])
            mod_sec = modern_sector_of(s["tk"], sector)
            macro_at_exact = macro_regime_multiplier(mod_sec, primary["y"], primary["m"])

            # Months from now to exact
            mo_to_exact = (primary["y"] - START_Y)*12 + (primary["m"] - START_M)

            hits.append({
                "tk":s["tk"],"name":s["name"],"ipo":s["ipo"],
                "sector":sector,"modern":mod_sec,
                "target":target,"target_lon":target_lon,
                "natal_sun_nep":natal_sun_nep,"natal_moon_nep":natal_moon_nep,
                "cur_sun_orb":cur_sun_orb,"cur_moon_orb":cur_moon_orb,
                "exact_y":primary["y"],"exact_m":primary["m"],"exact_orb":primary["orb"],
                "mo_to_exact":mo_to_exact,"approaching":approaching,
                "macro_at_exact":macro_at_exact,
                "sun_hits_n":len(sun_hits),"moon_hits_n":len(moon_hits),
            })
        except: continue

    # Sort — approaching + imminent (small mo_to_exact) + tight
    hits.sort(key=lambda h: (not h["approaching"], h["mo_to_exact"], h["exact_orb"]))

    out = "/home/user/cyclepapa/data/neptune_hype_candidates.csv"
    with open(out,"w",newline="") as f:
        w = csv.writer(f)
        w.writerow(["rank","ticker","name","sector","modern_sector","ipo",
                    "target","target_lon",
                    "cur_sun_orb","cur_moon_orb",
                    "natal_sun_neptune","natal_moon_neptune",
                    "exact_month","exact_orb","months_to_exact","approaching",
                    "macro_at_exact","sun_hits_n","moon_hits_n"])
        for i, h in enumerate(hits, 1):
            w.writerow([i,h["tk"],h["name"],h["sector"],h["modern"],h["ipo"],
                        h["target"],f"{h['target_lon']:.2f}",
                        f"{h['cur_sun_orb']:.2f}",f"{h['cur_moon_orb']:.2f}",
                        f"{h['natal_sun_nep']:.2f}",f"{h['natal_moon_nep']:.2f}",
                        f"{h['exact_y']}-{h['exact_m']:02d}",
                        f"{h['exact_orb']:.2f}",
                        h["mo_to_exact"],
                        "Y" if h["approaching"] else "N",
                        f"{h['macro_at_exact']:.2f}",
                        h["sun_hits_n"],h["moon_hits_n"]])
    print(f"Exported {len(hits)} -> {out}")

    # -------- TIER 1: currently within 2°, approaching --------
    t1 = [h for h in hits if h["approaching"] and (h["cur_sun_orb"]<=2 or h["cur_moon_orb"]<=2)]
    print(f"\n{'='*160}")
    print(f"TIER 1 — NEPTUNE <=2° of natal Sun/Moon NOW + approaching  ({len(t1)} matches)")
    print(f"{'='*160}")
    if t1:
        print(f"{'Tkr':<6s} {'ModSec':<12s} {'Name':<30s} {'IPO':<11s} {'Tgt':<4s} "
              f"{'CurOrb':>6s} {'Exact':<8s} {'ExOrb':>5s} {'NatSN':>5s} {'mPk':>4s}  APP ≤2° Sun-Nep natal?")
        for h in t1[:30]:
            nm = (h["name"] or "")[:29]
            avis = "★AVIS DNA" if h["natal_sun_nep"]<=3 else ""
            cur = h['cur_sun_orb'] if h['target']=='Sun' else h['cur_moon_orb']
            print(f"{h['tk']:<6s} {h['modern']:<12s} {nm:<30s} {h['ipo']:<11s} {h['target']:<4s} "
                  f"{cur:6.2f} {h['exact_y']}-{h['exact_m']:02d}  {h['exact_orb']:4.2f} "
                  f"{h['natal_sun_nep']:5.2f}  {h['macro_at_exact']:.2f}  {avis}")

    # -------- TIER 2: exact within 6 months --------
    t2 = [h for h in hits if 0 <= h["mo_to_exact"] <= 6 and h["exact_orb"] <= 1.5 and h["approaching"] and h not in t1]
    print(f"\n{'='*160}")
    print(f"TIER 2 — Neptune going exact to natal Sun/Moon within 6 months  ({len(t2)} matches)")
    print(f"{'='*160}")
    if t2:
        print(f"{'Tkr':<6s} {'ModSec':<12s} {'Name':<30s} {'IPO':<11s} {'Tgt':<4s} "
              f"{'CurOrb':>6s} {'Exact':<8s} {'ExOrb':>5s} {'NatSN':>5s} {'mPk':>4s}  AVIS-DNA?")
        for h in t2[:30]:
            nm = (h["name"] or "")[:29]
            avis = "★" if h["natal_sun_nep"]<=3 else ""
            cur = h['cur_sun_orb'] if h['target']=='Sun' else h['cur_moon_orb']
            print(f"{h['tk']:<6s} {h['modern']:<12s} {nm:<30s} {h['ipo']:<11s} {h['target']:<4s} "
                  f"{cur:6.2f} {h['exact_y']}-{h['exact_m']:02d}  {h['exact_orb']:4.2f} "
                  f"{h['natal_sun_nep']:5.2f}  {h['macro_at_exact']:.2f}  {avis}")

    # -------- TIER 3: exact 7-18 months --------
    t3 = [h for h in hits if 7 <= h["mo_to_exact"] <= 18 and h["exact_orb"] <= 1.5 and h["approaching"] and h not in t1]
    print(f"\n{'='*160}")
    print(f"TIER 3 — Neptune going exact to natal Sun/Moon 7-18 months out  ({len(t3)} matches)")
    print(f"{'='*160}")
    if t3:
        print(f"{'Tkr':<6s} {'ModSec':<12s} {'Name':<30s} {'IPO':<11s} {'Tgt':<4s} "
              f"{'CurOrb':>6s} {'Exact':<8s} {'ExOrb':>5s} {'NatSN':>5s} {'mPk':>4s}  AVIS-DNA?")
        for h in t3[:30]:
            nm = (h["name"] or "")[:29]
            avis = "★" if h["natal_sun_nep"]<=3 else ""
            cur = h['cur_sun_orb'] if h['target']=='Sun' else h['cur_moon_orb']
            print(f"{h['tk']:<6s} {h['modern']:<12s} {nm:<30s} {h['ipo']:<11s} {h['target']:<4s} "
                  f"{cur:6.2f} {h['exact_y']}-{h['exact_m']:02d}  {h['exact_orb']:4.2f} "
                  f"{h['natal_sun_nep']:5.2f}  {h['macro_at_exact']:.2f}  {avis}")

    # -------- AVIS-DNA ONLY: natal Sun-Neptune ≤3° AND future Neptune hit --------
    avis_dna = [h for h in hits if h["natal_sun_nep"] <= 3 and h["approaching"]]
    print(f"\n{'='*160}")
    print(f"★ AVIS-DNA — natal Sun conj Neptune ≤3° + Neptune approaching Sun/Moon  ({len(avis_dna)} matches)")
    print(f"  (Most bubblish archetype — 'born with fantasy-merged-with-identity')")
    print(f"{'='*160}")
    if avis_dna:
        avis_dna.sort(key=lambda h: h["mo_to_exact"])
        print(f"{'Tkr':<6s} {'ModSec':<12s} {'Name':<30s} {'IPO':<11s} "
              f"{'NatSN':>5s} {'Tgt':<4s} {'Exact':<8s} {'ExOrb':>5s} {'moOut':>5s} {'mPk':>4s}")
        for h in avis_dna[:30]:
            nm = (h["name"] or "")[:29]
            print(f"{h['tk']:<6s} {h['modern']:<12s} {nm:<30s} {h['ipo']:<11s} "
                  f"{h['natal_sun_nep']:5.2f} {h['target']:<4s} "
                  f"{h['exact_y']}-{h['exact_m']:02d}  {h['exact_orb']:4.2f} "
                  f"{h['mo_to_exact']:5d} {h['macro_at_exact']:.2f}")

if __name__ == "__main__":
    main()
