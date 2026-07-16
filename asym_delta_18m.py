"""Find IPOs with the biggest asymmetry change between as-of=today and as-of=today+18m.

For each IPO chart, the score at a given as-of date is computed by filtering the
forward-events stack to only events strictly after the as-of date. Everything else
in the engine (DNA, era, jul-cluster) is invariant.

Outputs a CSV with t0_asym, t1_asym, delta, and the top movers in each direction.
"""
from __future__ import annotations

import csv
import json
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from reverse_arch_v8_1_asymmetry import (
    BARBAULT,
    DEFAULT_ALREADY,
    asymmetry_scores,
    classify_window,
    classify_rally,
    compute_chart,
    era_match,
    is_shell,
    load_ipos,
    pre_cult_bucket,
    robust_core,
    score_forward,
    semi_lunar_bucket,
    speculative_bonus,
)

T0 = date(2026, 5, 4)
T1 = T0 + timedelta(days=int(18 * 30.4375))
print(f"as-of t0={T0.isoformat()}  t1={T1.isoformat()}  ({(T1-T0).days} days)")


def filter_events(events: dict, as_of: date) -> dict:
    out = {"eclipses": [], "outer_pair_conj_and_ingress": [], "stations": []}
    cutoff = as_of.isoformat()
    for k in out:
        for ev in events.get(k, []):
            if ev.get("date", "") > cutoff:
                out[k].append(ev)
    return out


def score_at(c: dict, events: dict, as_of: date) -> dict:
    ev = filter_events(events, as_of)
    peak, peak_d, conc, fwd_hits, jul, _, _silas = score_forward(c, ev)
    window, first_year = classify_window(fwd_hits)
    return {"peak": peak, "conc": conc, "jul": jul, "window": window, "first_year": first_year}


def make_row(c: dict, robust: float, semi: float, spec: float, era: float, fwd: dict) -> dict:
    return {
        "total_dna": robust + semi + spec,
        "era": era,
        "peak": fwd["peak"],
        "conc": fwd["conc"],
        "jul": fwd["jul"],
        "window": fwd["window"],
        "first_year": fwd["first_year"],
        "jn_phase": c["_jn_phase"],
        "jn_age": c["_jn_age"],
    }


def main():
    ipos = load_ipos(
        "/home/claude/ipos_expanded.csv",
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
    out_rows = []
    skipped = 0
    for ipo in ipos:
        if ipo["ticker"] in DEFAULT_ALREADY or is_shell(ipo.get("name", "")):
            continue
        try:
            c = compute_chart(ipo["date"])
        except Exception:
            skipped += 1
            continue
        robust, _, gate, _, _ = robust_core(c)
        if not gate:
            continue
        semi, _ = semi_lunar_bucket(c)
        spec, _ = speculative_bonus(c)
        era = era_match(c)

        f0 = score_at(c, events, T0)
        f1 = score_at(c, events, T1)
        r0 = make_row(c, robust, semi, spec, era, f0)
        r1 = make_row(c, robust, semi, spec, era, f1)
        early0, end0, asym0, label0 = asymmetry_scores(r0)
        early1, end1, asym1, label1 = asymmetry_scores(r1)
        out_rows.append({
            "ticker": ipo["ticker"],
            "name": ipo.get("name", "").strip('"'),
            "date": ipo["date"],
            "t0_asym": asym0,
            "t1_asym": asym1,
            "delta": asym1 - asym0,
            "delta_abs": abs(asym1 - asym0),
            "t0_window": r0["window"],
            "t1_window": r1["window"],
            "t0_label": label0,
            "t1_label": label1,
            "t0_peak": r0["peak"],
            "t1_peak": r1["peak"],
            "t0_conc": r0["conc"],
            "t1_conc": r1["conc"],
            "dna": r0["total_dna"],
        })

    out_rows.sort(key=lambda r: -r["delta_abs"])
    out_path = Path("/mnt/user-data/outputs/asym_change_t0_t1.csv")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(out_rows[0].keys()))
        w.writeheader()
        for r in out_rows:
            w.writerow(r)
    print(f"\nWrote {out_path}  rows={len(out_rows)}  skipped={skipped}")

    print("\n=== Biggest INCREASE in asym from t0 to t1 (asymmetry building over next 18m) ===")
    for r in sorted(out_rows, key=lambda x: -x["delta"])[:20]:
        print(
            f"  {r['ticker']:<7s} {r['name'][:32]:<32s} {r['date']}  "
            f"t0={r['t0_asym']:6.1f} -> t1={r['t1_asym']:6.1f} delta={r['delta']:+6.1f} "
            f"win {r['t0_window']:<9s}->{r['t1_window']:<9s} dna={r['dna']:5.1f}"
        )
    print("\n=== Biggest DECREASE in asym from t0 to t1 (asymmetry decaying — best entered now) ===")
    for r in sorted(out_rows, key=lambda x: x["delta"])[:20]:
        print(
            f"  {r['ticker']:<7s} {r['name'][:32]:<32s} {r['date']}  "
            f"t0={r['t0_asym']:6.1f} -> t1={r['t1_asym']:6.1f} delta={r['delta']:+6.1f} "
            f"win {r['t0_window']:<9s}->{r['t1_window']:<9s} dna={r['dna']:5.1f}"
        )


if __name__ == "__main__":
    main()
