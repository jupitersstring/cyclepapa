"""Find IPOs RISING NOW into a PERSISTENTLY, EXTREMELY BULLISH PLATEAU.

Monthly asym snapshots from RA_ASOF (default today) over 48 months.
Metrics per chart:
- t0_asym, peak_asym, months_to_peak, climb, slope_3m/6m
- plateau_months : consecutive months AFTER the peak with curve >= 92% of peak
- sustain_12m    : min(curve[peak..peak+12]) / peak
- avg_2y         : mean of first 24 months (absolute persistent level)

Selection (rising -> extreme -> persistent):
  slope_6m > 0, months_to_peak <= 12, peak_asym >= 70, plateau_months >= 12
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
    DEFAULT_ALREADY, asymmetry_scores, classify_window, compute_chart,
    era_match, is_already_cult, is_shell, load_ipos, robust_core,
    score_forward, semi_lunar_bucket, speculative_bonus,
)

T0 = date.fromisoformat(os.environ.get("RA_ASOF", date.today().isoformat()))
HORIZON = 48
snapshots = [T0 + timedelta(days=int(k * 30.4375)) for k in range(HORIZON + 1)]
print(f"as_of={T0}  snapshots={len(snapshots)} to {snapshots[-1]}")


def filter_events(events, as_of):
    cutoff = as_of.isoformat()
    return {k: [e for e in events.get(k, [])
                if e.get("date", "") > cutoff]
            for k in ("eclipses", "outer_pair_conj_and_ingress", "stations")}


def score_at(c, events, as_of, dna, era):
    ev = filter_events(events, as_of)
    peak, _, conc, fwd_hits, jul, _, _ = score_forward(c, ev, as_of=as_of.isoformat())
    window, first_year = classify_window(fwd_hits)
    row = {"total_dna": dna, "era": era, "peak": peak, "conc": conc, "jul": jul,
           "window": window, "first_year": first_year,
           "jn_phase": c["_jn_phase"], "jn_age": c["_jn_age"]}
    return asymmetry_scores(row)[2]


def main():
    ipos = load_ipos(None, "/home/claude/ritter_full.csv", [
        ("RUBI", "Rubicon Project", "2014-04-02"), ("EXA", "Exa Corp", "2012-06-28"),
        ("SLTN", "Solectron", "1989-11-15"), ("IMGN", "ImmunoGen", "1989-11-16"),
        ("CMLE", "Casual Male", "1988-09-20"), ("NRGN", "Neurogen", "1989-10-03"),
        ("LEND", "Accredited Home Lenders", "2003-02-14"),
    ])
    if len(ipos) < 100:
        raise SystemExit(f"ABORT universe={len(ipos)}")
    events = json.loads(Path("/home/claude/forward_events.json").read_text())
    rows = []
    for ipo in ipos:
        if is_already_cult(ipo["ticker"], ipo["date"], DEFAULT_ALREADY) or is_shell(ipo.get("name", "")):
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
        t0a = curve[0]
        pk_i = max(range(len(curve)), key=lambda i: curve[i])
        pk = curve[pk_i]
        plateau = 0
        for v in curve[pk_i + 1:]:
            if v >= 0.92 * pk:
                plateau += 1
            else:
                break
        seg = curve[pk_i: pk_i + 13]
        sustain = (min(seg) / pk) if pk > 0 else 0
        rows.append({
            "ticker": ipo["ticker"], "name": ipo.get("name", "").strip('"'), "date": ipo["date"],
            "dna": round(dna, 1), "t0_asym": round(t0a, 1), "peak_asym": round(pk, 1),
            "months_to_peak": pk_i, "climb": round(pk - t0a, 1),
            "slope_3m": round(curve[3] - t0a, 1), "slope_6m": round(curve[6] - t0a, 1),
            "plateau_months": plateau, "sustain_12m": round(sustain, 3),
            "avg_2y": round(sum(curve[:25]) / 25, 1),
        })

    out = Path("/mnt/user-data/outputs/plateau_scan.csv")
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader(); w.writerows(rows)
    print(f"Wrote {out} rows={len(rows)}")

    sel = [r for r in rows if r["slope_6m"] > 0 and r["months_to_peak"] <= 12
           and r["peak_asym"] >= 70 and r["plateau_months"] >= 12]
    sel.sort(key=lambda r: (-r["peak_asym"] * r["sustain_12m"], -r["plateau_months"]))
    print(f"\nQualifying rising->extreme->persistent: {len(sel)}")
    seen = set()
    for r in sel[:25]:
        mark = " (same chart)" if r["date"] in seen else ""
        seen.add(r["date"])
        print(f"  {r['ticker']:<7s}{r['name'][:28]:<28s}{r['date']}  t0={r['t0_asym']:6.1f} -> pk={r['peak_asym']:6.1f} @{r['months_to_peak']:2d}m  "
              f"plateau={r['plateau_months']:2d}m sustain12={r['sustain_12m']:.2f} avg2y={r['avg_2y']:6.1f} dna={r['dna']:5.1f}{mark}")


if __name__ == "__main__":
    main()
