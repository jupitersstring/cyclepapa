"""MRNA-archetype screen: who has the same setup coming up.

The RCA of MRNA's 2026-08 move (see mrna_forensics.py):
  NATAL   A. exact Mars-Neptune hard aspect (narrative/pharma fuel, orb 0.01)
          B. news-sensitivity marker (Mercury station at IPO)
  TRIGGER C. transiting URANUS hard natal JUPITER  (orb 0.98 at move)
          D. transiting PLUTO  hard natal VENUS    (orb 0.82 at move)
          E. Jupiter-Pluto opposition (2026-07-20) square natal Venus (1.5)
          F. eclipse hard natal Jupiter within a month ahead (2026-08-28, 1.6)
  Confluence: 4+ simultaneous components ("3 or more things" rule).

Screen: for every IPO in the universe (gate NOT required — MRNA's own gate
was marginal), compute natal longitudes (fast path, no heavy chart scans) and
test over the next 8 months (2026-09 .. 2027-04):
  comp_natal  : Mars-Neptune hard <=1.5
  comp_merc   : Mercury station at IPO (|speed| < 0.24)
  comp_uraJup : min-orb T.Uranus hard natal Jupiter <=1.2 in window
  comp_pluVen : min-orb T.Pluto  hard natal Venus  <=1.2 in window
  comp_JPopp  : Jupiter-Pluto opp degree (4.4 Leo/Aqu) hard natal Venus/Sun <=1.5
  comp_ecl    : any eclipse in window hard natal Jupiter or Venus <=1.5
archetype_score = weighted count; report >=3 components.
"""
from __future__ import annotations

import csv
import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import swisseph as swe

from reverse_arch_v8_1_asymmetry import (
    SIGNS, exchange_open_jd, hard_asp, load_ipos, orb,
)

TODAY = "2026-08-19"
WINDOW_END = "2027-04-30"
JP_OPP_LEO = 124.42   # Jupiter 4.42 Leo at exact opposition 2026-07-20
JP_OPP_AQU = 304.44

PLANETS = [("Sun", swe.SUN), ("Moon", swe.MOON), ("Mercury", swe.MERCURY), ("Venus", swe.VENUS),
           ("Mars", swe.MARS), ("Jupiter", swe.JUPITER), ("Saturn", swe.SATURN),
           ("Uranus", swe.URANUS), ("Neptune", swe.NEPTUNE), ("Pluto", swe.PLUTO)]


def natal_fast(date_str):
    jd, _, _ = exchange_open_jd(date_str)
    out = {}
    for nm, pid in PLANETS:
        r = swe.calc_ut(jd, pid)
        out[nm] = {"lon": r[0][0] % 360, "speed": r[0][3]}
    return out


def month_samples():
    # mid-month sample JDs from 2026-09 through 2027-04
    pts = []
    for y, m in [(2026, 9), (2026, 10), (2026, 11), (2026, 12), (2027, 1), (2027, 2), (2027, 3), (2027, 4)]:
        pts.append((f"{y}-{m:02d}", swe.julday(y, m, 15, 12)))
    return pts


def main():
    samples = month_samples()
    ura = [(lbl, swe.calc_ut(jd, swe.URANUS)[0][0] % 360) for lbl, jd in samples]
    plu = [(lbl, swe.calc_ut(jd, swe.PLUTO)[0][0] % 360) for lbl, jd in samples]

    events = json.loads(Path("/home/claude/forward_events.json").read_text())
    ecl_win = [e for e in events["eclipses"] if TODAY < e["date"] <= WINDOW_END]
    print(f"eclipses in window: {[(e['date'], round(e['lon'],1)) for e in ecl_win]}")

    ipos = load_ipos(None, "/home/claude/ritter_full.csv", [
        ("RUBI", "Rubicon Project", "2014-04-02"), ("EXA", "Exa Corp", "2012-06-28"),
        ("SLTN", "Solectron", "1989-11-15"), ("IMGN", "ImmunoGen", "1989-11-16"),
        ("CMLE", "Casual Male", "1988-09-20"), ("NRGN", "Neurogen", "1989-10-03"),
        ("LEND", "Accredited Home Lenders", "2003-02-14"),
    ])
    if len(ipos) < 100:
        raise SystemExit("ABORT: universe collapsed")

    rows = []
    for ipo in ipos:
        try:
            n = natal_fast(ipo["date"])
        except Exception:
            continue
        comps = {}
        r = hard_asp(n["Mars"]["lon"], n["Neptune"]["lon"], 1.5)
        comps["natal_MarsNep"] = round(r[1], 2) if r else None
        comps["merc_station"] = round(abs(n["Mercury"]["speed"]), 3) if abs(n["Mercury"]["speed"]) < 0.24 else None

        best_uj, best_uj_m = None, ""
        for lbl, ul in ura:
            r = hard_asp(ul, n["Jupiter"]["lon"], 1.2)
            if r and (best_uj is None or r[1] < best_uj):
                best_uj, best_uj_m = r[1], f"{lbl} {r[0]}"
        comps["T.Ura_natJup"] = (round(best_uj, 2), best_uj_m) if best_uj is not None else None

        best_pv, best_pv_m = None, ""
        for lbl, pl in plu:
            r = hard_asp(pl, n["Venus"]["lon"], 1.2)
            if r and (best_pv is None or r[1] < best_pv):
                best_pv, best_pv_m = r[1], f"{lbl} {r[0]}"
        comps["T.Plu_natVen"] = (round(best_pv, 2), best_pv_m) if best_pv is not None else None

        jp = None
        for tgt in ("Venus", "Sun"):
            r = hard_asp(JP_OPP_LEO, n[tgt]["lon"], 1.5)
            if r and (jp is None or r[1] < jp[0]):
                jp = (round(r[1], 2), f"{tgt} {r[0]}")
        comps["JPopp_hit"] = jp

        ec = None
        for e in ecl_win:
            for tgt in ("Jupiter", "Venus"):
                r = hard_asp(e["lon"], n[tgt]["lon"], 1.5)
                if r and (ec is None or r[1] < ec[0]):
                    ec = (round(r[1], 2), f"{e['date']} {r[0]} {tgt}")
        comps["ecl_hit"] = ec

        score = 0.0
        if comps["natal_MarsNep"] is not None: score += 1.5   # the archetype core
        if comps["merc_station"] is not None: score += 0.5
        if comps["T.Ura_natJup"]: score += 1.0
        if comps["T.Plu_natVen"]: score += 1.0
        if comps["JPopp_hit"]: score += 0.75
        if comps["ecl_hit"]: score += 1.0
        n_comp = sum(1 for v in comps.values() if v is not None)
        if n_comp >= 3:
            rows.append({
                "ticker": ipo["ticker"], "name": ipo.get("name", "").strip('"'), "date": ipo["date"],
                "score": round(score, 2), "n_components": n_comp,
                "natal_MarsNep": comps["natal_MarsNep"], "merc_station": comps["merc_station"],
                "T.Ura_natJup": comps["T.Ura_natJup"], "T.Plu_natVen": comps["T.Plu_natVen"],
                "JPopp_hit": comps["JPopp_hit"], "ecl_hit": comps["ecl_hit"],
            })

    rows.sort(key=lambda r: (-r["score"], -r["n_components"]))
    out = Path("/mnt/user-data/outputs/mrna_archetype_screen.csv")
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader(); w.writerows(rows)
    print(f"Wrote {out}  qualifying(>=3 comps)={len(rows)} of {len(ipos)}")
    print("\n=== TOP MRNA-archetype charts, next 8 months ===")
    for r in rows[:30]:
        print(f"  {r['ticker']:<7s}{r['name'][:26]:<26s}{r['date']}  score={r['score']:4.2f} n={r['n_components']}  "
              f"MarsNep={r['natal_MarsNep']} merc={r['merc_station']} UraJup={r['T.Ura_natJup']} "
              f"PluVen={r['T.Plu_natVen']} JPopp={r['JPopp_hit']} ecl={r['ecl_hit']}")


if __name__ == "__main__":
    main()
