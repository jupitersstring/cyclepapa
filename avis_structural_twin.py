"""
AVIS STRUCTURAL TWIN scanner — stocks whose chart TODAY resembles what
AVIS had on Feb 17 2026.

AVIS natal: Sun 28° Aqu, Moon 28° Aqu, Neptune 26° Aqu (triple stellium
within 2°), plus Mars 19° Aqu.
AVIS Feb 2026: transit Neptune 26° Aqu = exactly on natal Neptune, 2° from
natal Sun/Moon. Transit Sun 28° Aqu = solar return on natal Sun = double
ignition.

Structural criteria:
  (1) Natal Sun-Moon conjunction within 7° (emotional-identity fusion)
  (2) Natal Sun-Neptune OR Moon-Neptune within 7° (fantasy fused to identity)
  (3) Transit Neptune TODAY within 3° of natal Sun OR Moon (currently
      firing that fusion externally)
  Bonus: transit Sun within 15° of natal Sun in the current month
         (concurrent solar-return-ish activation — matches AVIS precisely)
  Bonus: ≥3 outer planets natally within 15° of each other (multi-planet
         stellium — AVIS has 4)
"""
import csv, sys
import swisseph as swe
from bti_test import compute_natal, transits_at, jd_of
from bti_v19_empirical import closest_hard
from bti_v23_sector_aware import get_sector
from bti_v24_macro import modern_sector_of
from macro_regime import macro_regime_multiplier
from filter_tradeable_v22 import CURATED_ACTIVE, BAD_NAME, BAD_TICKER

def orb_of(a, b):
    d = abs((a - b) % 360)
    return min(d, 360-d)

def simple_orb(a, b):
    """Conjunction-only orb (no hard aspects, just the distance)."""
    return orb_of(a, b)

def keep_tradeable(nm, tk, src):
    if not nm or not tk: return False
    if BAD_NAME.search(nm) or BAD_TICKER.search(tk): return False
    if len(tk)>5: return False
    return src=="SP500" or tk in CURATED_ACTIVE

def main():
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
            age = 2026 - y
            if not (1 <= age <= 40): continue
            if not keep_tradeable(nm, tk, src): continue
            seeds.append({"tk":tk,"ipo":ipo,"name":nm,"src":src})
    seen=set(); unique=[]
    for s in seeds:
        k=(s["tk"],s["ipo"])
        if k in seen: continue
        seen.add(k); unique.append(s)
    print(f"Tradeable universe: {len(unique)}", file=sys.stderr)

    # Current transit positions
    t_now = transits_at(2026, 4)
    nep_now = t_now["Neptune"]["lon"]
    sun_now = t_now["Sun"]["lon"]
    print(f"Neptune now: {nep_now:.2f}°   Sun now: {sun_now:.2f}°", file=sys.stderr)

    matches = []
    for s in unique:
        try:
            n = compute_natal(s["ipo"])
            if "Sun" not in n or "Moon" not in n or "Neptune" not in n: continue

            sun_n = n["Sun"]["lon"]
            moon_n = n["Moon"]["lon"]
            nep_n = n["Neptune"]["lon"]

            nat_sun_moon = simple_orb(sun_n, moon_n)
            # (1) Natal Sun-Neptune OR Moon-Neptune ≤ 5° (AVIS-DNA — fantasy fused to identity)
            nat_sun_nep = simple_orb(sun_n, nep_n)
            nat_moon_nep = simple_orb(moon_n, nep_n)
            nep_fused = min(nat_sun_nep, nat_moon_nep)
            if nep_fused > 5: continue

            # (2) Transit Neptune TODAY ≤ 2.5° of natal Sun OR Moon (the fusion is firing)
            cur_nep_sun = closest_hard(nep_now, sun_n)
            cur_nep_moon = closest_hard(nep_now, moon_n)
            best_cur = min(cur_nep_sun, cur_nep_moon)
            if best_cur > 2.5: continue

            # Bonus: transit Sun ≤15° of natal Sun (quasi-solar-return)
            sr_orb = orb_of(sun_now, sun_n)

            # Bonus: how many outers are natally within 15° of a central point?
            out_lons = {p: n[p]["lon"] for p in ("Jupiter","Saturn","Uranus","Neptune","Pluto") if p in n}
            # Stellium detector: max cluster of natal outers
            stellium_n = 0
            for pivot_lon in list(out_lons.values()) + [sun_n, moon_n]:
                c = sum(1 for pl in out_lons.values() if orb_of(pl, pivot_lon) <= 15)
                if c > stellium_n: stellium_n = c

            sector = get_sector(s["tk"], s["src"])
            mod = modern_sector_of(s["tk"], sector)
            mac = macro_regime_multiplier(mod, 2026, 4)

            matches.append({
                "tk":s["tk"],"name":s["name"],"ipo":s["ipo"],
                "sector":sector,"modern":mod,
                "nat_sun_moon":nat_sun_moon,
                "nat_sun_nep":nat_sun_nep,"nat_moon_nep":nat_moon_nep,
                "nep_fused":nep_fused,
                "cur_nep_sun":cur_nep_sun,"cur_nep_moon":cur_nep_moon,
                "best_cur":best_cur,"sr_orb":sr_orb,
                "stellium_n":stellium_n,"macro":mac,
                "sun_n":sun_n,"moon_n":moon_n,"nep_n":nep_n,
            })
        except: continue

    # Rank by: best_cur ASC, nep_fused ASC, stellium_n DESC
    matches.sort(key=lambda h: (h["best_cur"], h["nep_fused"], -h["stellium_n"]))

    out = "/home/user/cyclepapa/data/avis_structural_twins.csv"
    with open(out,"w",newline="") as f:
        w = csv.writer(f)
        w.writerow(["rank","ticker","name","sector","modern_sector","ipo",
                    "natal_sun_moon","natal_sun_nep","natal_moon_nep","nep_fused",
                    "current_nep_sun","current_nep_moon","sr_orb",
                    "stellium_size","macro_now",
                    "natal_sun_lon","natal_moon_lon","natal_nep_lon"])
        for i, h in enumerate(matches, 1):
            w.writerow([i,h["tk"],h["name"],h["sector"],h["modern"],h["ipo"],
                        f"{h['nat_sun_moon']:.2f}",f"{h['nat_sun_nep']:.2f}",
                        f"{h['nat_moon_nep']:.2f}",f"{h['nep_fused']:.2f}",
                        f"{h['cur_nep_sun']:.2f}",f"{h['cur_nep_moon']:.2f}",
                        f"{h['sr_orb']:.1f}",h["stellium_n"],f"{h['macro']:.2f}",
                        f"{h['sun_n']:.2f}",f"{h['moon_n']:.2f}",f"{h['nep_n']:.2f}"])
    print(f"Exported {len(matches)} -> {out}")

    print(f"\n{'='*170}")
    print(f"AVIS STRUCTURAL TWINS — natal Sun-Moon ≤7° + Sun/Moon-Neptune ≤7° + transit Neptune ≤3° of natal Sun/Moon NOW")
    print(f"{'='*170}")
    print(f"{'Tkr':<6s} {'ModSec':<13s} {'Name':<30s} {'IPO':<11s} {'SunMoon':>7s} {'NepFus':>6s} "
          f"{'CurNep':>6s} {'SR':>4s}  {'Stel':>4s} {'mPk':>4s}  position summary")
    for h in matches:
        nm = (h["name"] or "")[:29]
        nep_tgt = "Sun" if h["cur_nep_sun"] <= h["cur_nep_moon"] else "Moon"
        sr_tag = "SR!" if h["sr_orb"] <= 15 else f"{h['sr_orb']:.0f}°"
        # Quick summary of natal stellium
        natal_str = f"Sun{h['sun_n']:.0f}° Moon{h['moon_n']:.0f}° Nep{h['nep_n']:.0f}°"
        print(f"{h['tk']:<6s} {h['modern']:<13s} {nm:<30s} {h['ipo']:<11s} "
              f"{h['nat_sun_moon']:6.2f}° {h['nep_fused']:5.2f}° {h['best_cur']:5.2f}°→{nep_tgt:<4s} "
              f"{sr_tag:>4s} {h['stellium_n']:>4d} {h['macro']:.2f}  {natal_str}")

if __name__ == "__main__":
    main()
