"""Find MRNA-analog SETUPS: tight temporal convergence of the confirmed mechanism.

MRNA's real move (May-Aug 2026, +75% then the Aug-19 news pop) decomposed as:
  NATAL FUEL      Mars-Neptune exact 0.01 Pisces (pharma/narrative) + Mercury
                  station at IPO (news sensitivity)
  SLOW SUBSTRATE  T.Pluto sq natal Venus (money), T.Uranus opp natal Jupiter
                  (sudden-speculative) -- months-long background potential
  FAST TRIGGER    Jupiter-Pluto opposition on natal Venus (Jul 20) + the
                  2026-08-28 eclipse sq natal Jupiter -- detonates the window

Rather than count loose components over 8 months (archetype_screen.py), this
finds the single tightest ~90-day window where a slow substrate is live AND a
fast trigger fires, then ranks by fuel x convergence x tightness. That
simultaneity is what made MRNA explosive rather than a slow grind.

Outputs mrna_convergence.csv sorted by setup_score, annotated by IPO era for
tradeability (2015+ far more likely still listed).
"""
from __future__ import annotations

import csv
import json
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import swisseph as swe

from reverse_arch_v8_1_asymmetry import (
    SIGNS, exchange_open_jd, hard_asp, load_ipos, orb,
)

START = date(2026, 8, 19)          # today
END = date(2028, 6, 1)             # 21-month forward horizon
STEP_DAYS = 10
WINDOW_DAYS = 95                   # ~3-month convergence window
WINDOW_SAMPLES = WINDOW_DAYS // STEP_DAYS

SLOW = [("Pluto", swe.PLUTO), ("Uranus", swe.URANUS), ("Neptune", swe.NEPTUNE)]
FAST = [("Jupiter", swe.JUPITER)]  # Mars removed: too promiscuous over 2yr (RCA)
SLOW_TARGETS = ("Venus", "Jupiter", "Sun")   # money / growth / identity
FAST_TARGETS = ("Venus", "Sun", "Jupiter")
SLOW_ORB = 1.5
FAST_ORB = 1.2
ECL_ORB = 1.5

NAT = [("Sun", swe.SUN), ("Moon", swe.MOON), ("Mercury", swe.MERCURY), ("Venus", swe.VENUS),
       ("Mars", swe.MARS), ("Jupiter", swe.JUPITER), ("Saturn", swe.SATURN),
       ("Uranus", swe.URANUS), ("Neptune", swe.NEPTUNE), ("Pluto", swe.PLUTO)]


def natal(date_str):
    jd, _, _ = exchange_open_jd(date_str)
    return {nm: {"lon": swe.calc_ut(jd, pid)[0][0] % 360, "speed": swe.calc_ut(jd, pid)[0][3]}
            for nm, pid in NAT}


def sky_samples():
    out = []
    d = START
    while d <= END:
        jd = swe.julday(d.year, d.month, d.day, 13.5)
        pos = {nm: swe.calc_ut(jd, pid)[0][0] % 360 for nm, pid in SLOW + FAST}
        out.append((d, pos))
        d += timedelta(days=STEP_DAYS)
    return out


def main():
    samples = sky_samples()
    events = json.loads(Path("/home/claude/forward_events.json").read_text())
    ecl = [(date.fromisoformat(e["date"]), e["lon"], e["type"])
           for e in events["eclipses"] if START.isoformat() < e["date"] <= END.isoformat()]
    print(f"samples={len(samples)}  eclipses in horizon={len(ecl)}")

    ipos = load_ipos(None, "/home/claude/ritter_full.csv", [
        ("RUBI", "Rubicon Project", "2014-04-02"), ("EXA", "Exa Corp", "2012-06-28"),
        ("SLTN", "Solectron", "1989-11-15"), ("IMGN", "ImmunoGen", "1989-11-16"),
        ("CMLE", "Casual Male", "1988-09-20"), ("NRGN", "Neurogen", "1989-10-03"),
        ("LEND", "Accredited Home Lenders", "2003-02-14"),
    ])
    if len(ipos) < 100:
        raise SystemExit("ABORT universe collapsed")

    rows = []
    for ipo in ipos:
        try:
            n = natal(ipo["date"])
        except Exception:
            continue

        # natal fuel (multiplier)
        mn = hard_asp(n["Mars"]["lon"], n["Neptune"]["lon"], 2.0)
        merc_station = abs(n["Mercury"]["speed"]) < 0.24
        fuel = 1.0 + (0.6 if mn else 0.0) + (0.25 if merc_station else 0.0)

        # per-sample component activity
        slow_active = []   # list over samples of set of "planet>target" strings
        fast_active = []
        for d, pos in samples:
            s = set()
            for pn, _ in SLOW:
                for tgt in SLOW_TARGETS:
                    r = hard_asp(pos[pn], n[tgt]["lon"], SLOW_ORB)
                    if r:
                        s.add(f"{pn}>{tgt}")
            f = set()
            for pn, _ in FAST:
                for tgt in FAST_TARGETS:
                    r = hard_asp(pos[pn], n[tgt]["lon"], FAST_ORB)
                    if r:
                        f.add(f"{pn}>{tgt}")
            slow_active.append(s)
            fast_active.append(f)

        # eclipse triggers mapped onto nearest sample index
        ecl_hits = {}   # sample_idx -> list of "date:tgt"
        for ed, elon, etype in ecl:
            idx = min(range(len(samples)), key=lambda i: abs((samples[i][0] - ed).days))
            for tgt in ("Jupiter", "Venus", "Sun"):
                r = hard_asp(elon, n[tgt]["lon"], ECL_ORB)
                if r:
                    ecl_hits.setdefault(idx, []).append(f"{ed.isoformat()}:{r[0]}{tgt}")

        # slide the convergence window, score each
        best = None
        for i in range(len(samples) - WINDOW_SAMPLES + 1):
            js = range(i, i + WINDOW_SAMPLES)
            slow_set = set().union(*(slow_active[j] for j in js))
            fast_set = set().union(*(fast_active[j] for j in js))
            ecl_set = [h for j in js for h in ecl_hits.get(j, [])]
            n_slow = len(slow_set)
            n_fast = len(fast_set) + len(ecl_set)
            if n_slow == 0 or n_fast == 0:
                continue      # MRNA needs BOTH substrate and trigger
            center = samples[i + WINDOW_SAMPLES // 2][0]
            conv = n_slow + n_fast
            score = conv * fuel
            if best is None or score > best["score"]:
                best = {"score": round(score, 2), "conv": conv, "n_slow": n_slow,
                        "n_fast": n_fast, "center": center.isoformat(),
                        "slow": "/".join(sorted(slow_set)), "fast": "/".join(sorted(fast_set)),
                        "ecl": "/".join(ecl_set)}
        if best is None:
            continue

        yr = int(ipo["date"][:4])
        era = "2018-21" if yr >= 2017 else ("2010-16" if yr >= 2010 else "pre-2010")
        rows.append({
            "ticker": ipo["ticker"], "name": ipo.get("name", "").strip('"'), "date": ipo["date"], "era": era,
            "setup_score": best["score"], "convergence": best["conv"],
            "n_slow": best["n_slow"], "n_fast": best["n_fast"],
            "peak_window": best["center"], "position_by": (date.fromisoformat(best["center"]) - timedelta(days=42)).isoformat(),
            "fuel": round(fuel, 2), "mars_nep": round(mn[1], 2) if mn else None,
            "merc_station": merc_station,
            "slow_substrate": best["slow"], "fast_trigger": best["fast"], "eclipse_trigger": best["ecl"],
        })

    rows.sort(key=lambda r: -r["setup_score"])
    out = Path("/mnt/user-data/outputs/mrna_convergence.csv")
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader(); w.writerows(rows)
    print(f"Wrote {out}  rows={len(rows)} of {len(ipos)}")

    # MRNA's own rank as self-validation
    mrna = next((i for i, r in enumerate(rows) if r["ticker"] == "MRNA"), None)
    if mrna is not None:
        r = rows[mrna]
        print(f"\nMRNA self-check: rank #{mrna+1}/{len(rows)}  score={r['setup_score']} peak={r['peak_window']} fuel={r['fuel']}")

    print("\n=== TOP SETUPS overall ===")
    seen = set()
    for r in rows[:20]:
        m = " (same chart)" if r["date"] in seen else ""
        seen.add(r["date"])
        print(f"  {r['ticker']:<7s}{r['name'][:24]:<24s}{r['date']} [{r['era']:<7s}] score={r['setup_score']:5.1f} "
              f"conv={r['convergence']}(s{r['n_slow']}/f{r['n_fast']}) peak={r['peak_window']} fuel={r['fuel']} "
              f"| {r['slow_substrate']} + {r['fast_trigger']}{'/ECL:'+r['eclipse_trigger'] if r['eclipse_trigger'] else ''}")

    print("\n=== TOP SETUPS, 2017+ IPOs (most likely still tradeable) ===")
    seen = set()
    n = 0
    for r in rows:
        if r["era"] != "2018-21" or r["date"] in seen:
            continue
        seen.add(r["date"]); n += 1
        if n > 20:
            break
        print(f"  {r['ticker']:<7s}{r['name'][:24]:<24s}{r['date']} score={r['setup_score']:5.1f} "
              f"conv={r['convergence']}(s{r['n_slow']}/f{r['n_fast']}) peak={r['peak_window']} pos_by={r['position_by']} "
              f"fuel={r['fuel']} | {r['slow_substrate']} + {r['fast_trigger']}{'/ECL' if r['eclipse_trigger'] else ''}")


if __name__ == "__main__":
    main()
