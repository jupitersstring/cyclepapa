"""Forensics: what preceded MRNA's move (as of 2026-08-19), per the engine.

Part 1: full chart + every forward hit for MRNA (IPO 2018-12-07), highlighting
the 2026-06-01..2026-09-30 activation window and the natal DNA.
Part 2 (separate script): archetype screen for charts with analogous upcoming hits.
"""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import swisseph as swe

from reverse_arch_v8_1_asymmetry import (
    SIGNS, compute_chart, era_match, hard_asp, orb, robust_core,
    score_forward, semi_lunar_bucket, speculative_bonus,
)

TODAY = "2026-08-19"


def fmt(lon):
    return f"{lon % 30:5.2f} {SIGNS[int(lon // 30)]}"


def main():
    events = json.loads(Path("/home/claude/forward_events.json").read_text())
    c = compute_chart("2018-12-07")
    print("=== MRNA (Moderna) IPO chart, 2018-12-07 NYSE 9:30 ===")
    for p in ("Sun", "Moon", "Mercury", "Venus", "Mars", "Jupiter", "Saturn", "Uranus", "Neptune", "Pluto", "NN"):
        st = " STATION" if c[p]["station"] else (" Rx" if c[p]["retro"] else "")
        print(f"  {p:<8s} {fmt(c[p]['lon'])}  ({c[p]['lon']:7.2f})  spd={c[p]['speed']:+.3f}{st}")
    print(f"  ASC      {fmt(c['ASC']['lon'])}   MC {fmt(c['MC']['lon'])}")
    print(f"  phase={c['_phase']}  JN {c['_jn_phase']} age={c['_jn_age']:.0f}  eq/sol={c['_equinox_solstice']}")

    robust, r_hits, gate, arch, _ = robust_core(c)
    semi, l_hits = semi_lunar_bucket(c)
    spec, s_hits = speculative_bonus(c)
    print(f"\nNatal DNA: robust={robust:.1f} semi={semi:.1f} spec={spec:.1f}  GATE={gate}  archetype={sorted(arch)}")
    for h in r_hits + l_hits + s_hits:
        print(f"    {h}")

    # ALL forward hits with NO as-of (so we can see what already fired in 2026)
    peak, peak_d, conc, hits, jul, jul_hits, silas = score_forward(c, events)
    print(f"\nForward stack: peak={peak:.1f} conc={conc:.1f}  eclipse_sun={silas['eclipse_sun_events']}  position_by={silas['position_by']}")
    print("\n=== Hits JUNE-SEPT 2026 (the window preceding/spanning today) ===")
    win = [h for h in hits if "2026-06" <= h["date"][:7] <= "2026-09"]
    for h in sorted(win, key=lambda x: x["date"]):
        print(f"  {h['date']:<10s} pts={h['pts']:5.1f}  {h['desc']}")
    print("\n=== Top 12 hits all-time (2026-2036) ===")
    for h in hits[:12]:
        print(f"  {h['date']:<10s} pts={h['pts']:5.1f}  {h['desc']}")

    # exact sky-vs-natal for today: transits of outers + eclipse degree
    print("\n=== Sky today (2026-08-19) vs MRNA natal, hard aspects <=2.0 ===")
    jd = swe.julday(2026, 8, 19, 13.5)
    sky = {nm: swe.calc_ut(jd, pid)[0][0] % 360 for nm, pid in
           [("Jupiter", swe.JUPITER), ("Saturn", swe.SATURN), ("Uranus", swe.URANUS),
            ("Neptune", swe.NEPTUNE), ("Pluto", swe.PLUTO), ("Mars", swe.MARS)]}
    ecl = 140.04  # 2026-08-12 total solar
    for tn, tl in list(sky.items()) + [("ECL-8/12", ecl)]:
        for nn in ("Sun", "Moon", "Mercury", "Venus", "Mars", "Jupiter", "Saturn", "Uranus", "Neptune", "Pluto", "ASC", "MC"):
            r = hard_asp(tl, c[nn]["lon"], 2.0)
            if r:
                print(f"  T.{tn:<9s}{fmt(tl)}  {r[0]:<5s} natal {nn:<8s}{fmt(c[nn]['lon'])}  orb {r[1]:.2f}")
    # Jupiter-Pluto opposition (not in event builder — conjunction-only) — find exactness
    print("\n=== Jupiter-Pluto opposition 2026 (builder gap: oppositions not emitted) ===")
    best = (999, None)
    for k in range(0, 366):
        jdx = swe.julday(2026, 1, 1, 12) + k
        jl = swe.calc_ut(jdx, swe.JUPITER)[0][0] % 360
        pl = swe.calc_ut(jdx, swe.PLUTO)[0][0] % 360
        o = abs(orb(jl, pl) - 180)
        if o < best[0]:
            best = (o, (jdx, jl, pl))
    o, (jdx, jl, pl) = best
    y, m, d, _ = swe.revjul(jdx)
    print(f"  exact {y:04.0f}-{m:02.0f}-{int(d):02d}  Jup {fmt(jl)} opp Plu {fmt(pl)} (orb {o:.2f})")
    for nn in ("Sun", "Moon", "Mercury", "Venus", "Mars", "Jupiter", "Saturn", "Uranus", "Neptune", "Pluto"):
        r = hard_asp(jl, c[nn]["lon"], 2.5)
        if r:
            print(f"    -> aspects MRNA natal {nn} {fmt(c[nn]['lon'])}: {r[0]} orb {r[1]:.2f}")


if __name__ == "__main__":
    main()
