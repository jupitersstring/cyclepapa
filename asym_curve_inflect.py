"""Find IPOs whose asymmetry curve INFLECTS UPWARD from today and CLIMAXES SOON.

Computes asym(as_of) at monthly snapshots from 2026-05 through 2030-05.
For each IPO finds:
- t0_asym       = asym at today
- peak_t        = month at which asym is maximised
- peak_asym     = max asym over horizon
- months_to_peak
- 6m_slope      = asym(t0+6m) - asym(t0)
- climb         = peak_asym - t0_asym

Selection criteria for "bullish-now + soon-climax":
- 6m_slope > 0
- months_to_peak <= 18
- climb >= 5 absolute, or peak/t0 >= 1.10

Ranks by `climb` then `1/months_to_peak` then `t0_asym` (to break ties on quality).
"""
from __future__ import annotations

import csv
import json
import os
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from reverse_arch_v8_1_asymmetry import (
    DEFAULT_ALREADY,
    asymmetry_scores,
    classify_window,
    compute_chart,
    era_match,
    is_shell,
    load_ipos,
    robust_core,
    score_forward,
    semi_lunar_bucket,
    speculative_bonus,
)

T0 = date.fromisoformat(os.environ.get("RA_ASOF", date.today().isoformat()))
HORIZON_MONTHS = 48
SNAPSHOT_STEP = 1

snapshots = []
d = T0
for k in range(0, HORIZON_MONTHS + 1, SNAPSHOT_STEP):
    snapshots.append(T0 + timedelta(days=int(k * 30.4375)))
print(f"snapshots: {len(snapshots)} from {snapshots[0]} to {snapshots[-1]}")


def filter_events(events: dict, as_of: date) -> dict:
    out = {"eclipses": [], "outer_pair_conj_and_ingress": [], "stations": []}
    cutoff = as_of.isoformat()
    for k in out:
        for ev in events.get(k, []):
            if ev.get("date", "") > cutoff:
                out[k].append(ev)
    return out


def score_at(c: dict, events: dict, as_of: date, dna: float, era: float) -> float:
    ev = filter_events(events, as_of)
    peak, _, conc, fwd_hits, jul, _, _silas = score_forward(c, ev, as_of=as_of.isoformat())
    window, first_year = classify_window(fwd_hits)
    row = {
        "total_dna": dna,
        "era": era,
        "peak": peak,
        "conc": conc,
        "jul": jul,
        "window": window,
        "first_year": first_year,
        "jn_phase": c["_jn_phase"],
        "jn_age": c["_jn_age"],
    }
    _, _, asym, _ = asymmetry_scores(row)
    return asym


def main():
    ipos = load_ipos(
        None,
        "/home/claude/ritter_full.csv",
        [
            ("RUBI", "Rubicon Project", "2014-04-02"),
            ("EXA", "Exa Corp", "2012-06-28"),
            ("SLTN", "Solectron", "1989-11-15"),
            ("IMGN", "ImmunoGen", "1989-11-16"),
            ("CMLE", "Casual Male", "1988-09-20"),
            ("NRGN", "Neurogen", "1989-10-03"),
            ("LEND", "Accredited Home Lenders", "2003-02-14"),
        ],
    )
    events = json.loads(Path("/home/claude/forward_events.json").read_text())
    rows = []
    for ipo in ipos:
        if ipo["ticker"] in DEFAULT_ALREADY or is_shell(ipo.get("name", "")):
            continue
        try:
            c = compute_chart(ipo["date"])
        except Exception:
            continue
        robust, _, gate, _, _ = robust_core(c)
        if not gate:
            continue
        semi, _ = semi_lunar_bucket(c)
        spec, _ = speculative_bonus(c)
        dna = robust + semi + spec
        era = era_match(c)
        curve = [score_at(c, events, t, dna, era) for t in snapshots]
        t0_asym = curve[0]
        peak_idx = max(range(len(curve)), key=lambda i: curve[i])
        peak_asym = curve[peak_idx]
        months_to_peak = peak_idx * SNAPSHOT_STEP
        slope_6m = curve[min(6, len(curve) - 1)] - t0_asym
        slope_3m = curve[min(3, len(curve) - 1)] - t0_asym
        climb = peak_asym - t0_asym
        rows.append({
            "ticker": ipo["ticker"],
            "name": ipo.get("name", "").strip('"'),
            "date": ipo["date"],
            "dna": dna,
            "t0_asym": t0_asym,
            "peak_asym": peak_asym,
            "months_to_peak": months_to_peak,
            "climb": climb,
            "slope_3m": slope_3m,
            "slope_6m": slope_6m,
            "curve": curve,
        })

    out_path = Path("/mnt/user-data/outputs/asym_inflect_climax.csv")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["ticker", "name", "date", "dna", "t0_asym", "peak_asym", "months_to_peak", "climb", "slope_3m", "slope_6m"])
        for r in rows:
            w.writerow([r["ticker"], r["name"], r["date"], f"{r['dna']:.1f}", f"{r['t0_asym']:.2f}", f"{r['peak_asym']:.2f}", r["months_to_peak"], f"{r['climb']:.2f}", f"{r['slope_3m']:.2f}", f"{r['slope_6m']:.2f}"])
    print(f"\nWrote {out_path}  rows={len(rows)}")

    qualifies = [r for r in rows if r["slope_6m"] > 0 and 0 < r["months_to_peak"] <= 18 and r["climb"] >= 5]
    qualifies.sort(key=lambda r: (-r["climb"], r["months_to_peak"], -r["t0_asym"]))
    print(f"\nQualifying (slope_6m>0, climax<=18m, climb>=5): {len(qualifies)}")
    print("\n=== TOP — bullish inflection FROM TODAY, climax SOON ===")
    seen_dates = set()
    for r in qualifies[:30]:
        marker = ""
        if r["date"] in seen_dates:
            marker = " (same chart)"
        seen_dates.add(r["date"])
        c = r["curve"]
        rough_curve = " ".join(f"{c[i]:5.0f}" for i in range(0, len(c), 6))
        print(
            f"  {r['ticker']:<7s} {r['name'][:30]:<30s} {r['date']}  "
            f"t0={r['t0_asym']:5.1f} peak={r['peak_asym']:5.1f} +{r['climb']:5.1f} @ {r['months_to_peak']:2d}m  "
            f"6m_slope={r['slope_6m']:+5.1f} dna={r['dna']:5.1f} curve@6m: {rough_curve}{marker}"
        )

    by_date = {}
    for r in qualifies:
        if r["date"] not in by_date or r["climb"] > by_date[r["date"]]["climb"]:
            by_date[r["date"]] = r
    print(f"\n=== UNIQUE-CHART top 20 (one representative per IPO date) ===")
    uniq = sorted(by_date.values(), key=lambda r: (-r["climb"], r["months_to_peak"]))
    for r in uniq[:20]:
        c = r["curve"]
        peak_date = T0 + timedelta(days=int(r["months_to_peak"] * 30.4375))
        print(
            f"  {r['ticker']:<7s} {r['name'][:30]:<30s} ipo={r['date']}  "
            f"t0={r['t0_asym']:5.1f} -> peak {r['peak_asym']:5.1f} (+{r['climb']:5.1f}) "
            f"at ~{peak_date.isoformat()} ({r['months_to_peak']}m)  dna={r['dna']:5.1f}"
        )


if __name__ == "__main__":
    main()
