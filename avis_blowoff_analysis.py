"""
Analyse the astro PRECEDING the AVIS/CAR speculative blow-off.

CAR (Avis Budget Group) squeeze history:
  - Nov 2, 2021 : massive single-day squeeze $80 -> $545
  - Broader move: $20 (Mar 2020 COVID low) -> $545 (Nov 2021 peak)
  - The 28x move over 20 months is the canonical parabolic blow-off

Two candidate natal charts tested:
  A. 2006-10-01 (Cendant spinoff NYSE re-listing)
  B. 2011-01-01 09:30 EST Manhattan (chart the user shared)

For the peak date 2021-11-02 we compute transits preceding:
  - 24 months before (Nov 2019)
  - 18 months before (May 2020 = COVID bottom)
  - 12 months before (Nov 2020 = mid-rally)
  - 9 months before (Feb 2021)
  - 6 months before (May 2021)
  - 3 months before (Aug 2021)
  - At peak (Nov 2021)
  - 3 months after (Feb 2022)

Key signatures to identify:
  1. When did transit Neptune first touch natal Sun/Moon?
  2. When did Uranus-natal activations fire?
  3. When did Jupiter transit key natal points?
  4. Solar-return coincidences?
  5. Eclipse proximity?

Then apply this template to screen universe for stocks currently in the
same precursor position relative to a future blow-off.
"""
import math, csv, sys
from datetime import datetime, timedelta
import swisseph as swe
from bti_test import compute_natal, transits_at, jd_of
from bti_v19_empirical import closest_hard, orb
from eclipse_database import build_eclipse_database, eclipse_hits_natal
from bti_v23_sector_aware import get_sector
from bti_v24_macro import modern_sector_of
from filter_tradeable_v22 import CURATED_ACTIVE, BAD_NAME, BAD_TICKER

def transits_at_date(y, m, d=15):
    return transits_at(y, m, d, 12.0)

def aspects_table(natal, trans):
    """Full table of transit-outer -> natal-point orbs."""
    out = {}
    for outer in ("Jupiter","Saturn","Uranus","Neptune","Pluto"):
        for pt in ("Sun","Moon","ASC","MC","Mars","Jupiter","Saturn","Uranus","Neptune","Pluto"):
            if pt not in natal: continue
            o = closest_hard(trans[outer]["lon"], natal[pt]["lon"])
            if o <= 8:
                out[f"t{outer}-n{pt}"] = o
    return out

def analyse_avis(natal_date, label):
    print(f"\n{'='*100}")
    print(f" AVIS/CAR analysis  natal={natal_date}  ({label})")
    print(f"{'='*100}")
    natal = compute_natal(natal_date)
    # Print natal
    print("  Natal positions:")
    for p in ("Sun","Moon","ASC","MC","Mars","Jupiter","Saturn","Uranus","Neptune","Pluto"):
        if p in natal:
            lon = natal[p]["lon"]
            print(f"    {p:<9s} {lon:7.2f}°")
    sn = natal["Sun"]["lon"]; mn = natal["Moon"]["lon"]; nn = natal["Neptune"]["lon"]
    print(f"\n  Natal Sun-Moon conj: {min(abs((sn-mn)%360),360-abs((sn-mn)%360)):.2f}°")
    print(f"  Natal Sun-Neptune conj: {min(abs((sn-nn)%360),360-abs((sn-nn)%360)):.2f}°")
    print(f"  Natal Moon-Neptune conj: {min(abs((mn-nn)%360),360-abs((mn-nn)%360)):.2f}°")

    # Peak Nov 2 2021
    peak = (2021, 11)
    phases = [
        (-24, "T-24mo (Nov 2019)"),
        (-20, "T-20mo (Mar 2020 COVID low)"),
        (-18, "T-18mo (May 2020)"),
        (-12, "T-12mo (Nov 2020 mid-rally)"),
        (-9,  "T-9mo  (Feb 2021)"),
        (-6,  "T-6mo  (May 2021)"),
        (-3,  "T-3mo  (Aug 2021)"),
        ( 0,  "PEAK   (Nov 2021)"),
        (+3,  "T+3mo  (Feb 2022)"),
    ]
    for off, lbl in phases:
        idx = peak[0]*12 + peak[1] - 1 + off
        y = idx // 12; m = (idx % 12) + 1
        t = transits_at_date(y, m)
        asp = aspects_table(natal, t)
        asp_sorted = sorted(asp.items(), key=lambda x: x[1])[:6]
        # Also: retro count
        retro_n = sum(1 for p in ("Mercury","Venus","Mars","Jupiter","Saturn","Uranus","Neptune","Pluto") if t[p]["retro"])
        print(f"\n  {lbl:<28s} y={y} m={m:02d}  retro#={retro_n}")
        for k, v in asp_sorted:
            print(f"      {k:<20s} {v:4.2f}°")

def find_similar_stocks(template_aspects, universe, at_month):
    """Find stocks whose current transits match the template aspects at `at_month`."""
    pass  # placeholder

def main():
    # Two candidate natals
    analyse_avis("2006-10-01", "Cendant spinoff NYSE re-listing")
    analyse_avis("2011-01-01", "chart shared by user")

if __name__ == "__main__":
    main()
