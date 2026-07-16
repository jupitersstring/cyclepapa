"""Score sector-rulership resonance for gate-passed IPOs and join to asym rankings.

For each IPO already in reverse_arch_v8_1_asymmetry.csv:
1. Infer sector from company name (keyword classifier; None -> skipped).
2. Compute per-planet chart emphasis:
     angular (conj ASC/MC <=8deg), hard aspect to Sun (<=3deg) or Moon (<=3deg),
     station, domicile (+ modern co-domicile at reduced weight), exaltation,
     detriment/fall as small penalties.
3. Resonance = sum over the sector's ruling planets of emphasis x tier weight
   (classical 1.0 / modern 0.65 / contested 0.50 / experimental 0.35).
4. Output CSV with resonance, dominant ruler, tier fired, joined asym columns,
   and sector_adj_asym = t0_asym * (1 + resonance/25).

Provenance separation is preserved: a classical-only resonance column is also
emitted so the engine can be filtered to "classical-only" per the compendium.
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from reverse_arch_v8_1_asymmetry import compute_chart, orb, hard_asp
from sector_rulerships import (
    SECTOR_RULERS, TIER_WEIGHT, classify_sector,
    DOMICILE, MODERN_DOMICILE, EXALTATION, DETRIMENT, FALL,
)

PLANETS = ["Sun", "Moon", "Mercury", "Venus", "Mars", "Jupiter", "Saturn", "Uranus", "Neptune", "Pluto"]


def planet_emphasis(c: dict) -> dict[str, float]:
    emph = {}
    for p in PLANETS:
        e = 0.0
        lon = c[p]["lon"]
        for angle in ("ASC", "MC"):
            o = orb(lon, c[angle]["lon"])
            if o <= 8.0:
                e += 3.0 * (8.0 - o) / 8.0
        if p != "Sun":
            r = hard_asp(lon, c["Sun"]["lon"], 3.0)
            if r:
                e += 2.0 * (3.0 - r[1]) / 3.0
        if p != "Moon":
            r = hard_asp(lon, c["Moon"]["lon"], 3.0)
            if r:
                e += 1.5 * (3.0 - r[1]) / 3.0
        if c[p]["station"]:
            e += 2.0
        sign = c[p]["sign"]
        if sign in DOMICILE.get(p, []):
            e += 2.0
        elif sign in MODERN_DOMICILE.get(p, []):
            e += 1.0
        if EXALTATION.get(p) == sign:
            e += 1.5
        if sign in DETRIMENT.get(p, []):
            e -= 1.0
        if FALL.get(p) == sign:
            e -= 0.5
        emph[p] = e
    return emph


def resonance_for(sector: str, emph: dict[str, float]) -> tuple[float, float, str, str]:
    total = 0.0
    classical_only = 0.0
    best = ("", 0.0, "")
    for planet, tier, source in SECTOR_RULERS[sector]:
        contrib = max(emph.get(planet, 0.0), 0.0) * TIER_WEIGHT[tier]
        total += contrib
        if tier == "classical":
            classical_only += contrib
        if contrib > best[1]:
            best = (planet, contrib, tier)
    return total, classical_only, best[0], best[2]


def main():
    asym_rows = list(csv.DictReader(open("/home/user/cyclepapa/asym_inflect_climax.csv")))
    out = []
    for r in asym_rows:
        sector = classify_sector(r["name"])
        if not sector:
            continue
        try:
            c = compute_chart(r["date"])
        except Exception:
            continue
        emph = planet_emphasis(c)
        res, res_classical, top_ruler, tier_fired = resonance_for(sector, emph)
        t0 = float(r["t0_asym"])
        out.append({
            "ticker": r["ticker"], "name": r["name"], "date": r["date"], "sector": sector,
            "resonance": round(res, 2), "resonance_classical": round(res_classical, 2),
            "top_ruler": top_ruler, "tier_fired": tier_fired,
            "t0_asym": t0, "peak_asym": float(r["peak_asym"]),
            "months_to_peak": r["months_to_peak"], "dna": float(r["dna"]),
            "sector_adj_asym": round(t0 * (1 + res / 25.0), 1),
        })

    out.sort(key=lambda x: -x["sector_adj_asym"])
    path = Path("/mnt/user-data/outputs/sector_resonance.csv")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(out[0].keys()))
        w.writeheader()
        w.writerows(out)
    print(f"Wrote {path}  rows={len(out)} (of {len(asym_rows)} gate-passed; rest had no sector match)")

    print("\n=== TOP 25 by sector-adjusted asymmetry ===")
    seen = set()
    n = 0
    for r in out:
        key = (r["date"], r["sector"])
        if key in seen:
            continue
        seen.add(key)
        n += 1
        if n > 25:
            break
        print(f"  {r['ticker']:<6s} {r['name'][:28]:<28s} {r['date']}  sect={r['sector']:<18s} "
              f"res={r['resonance']:5.2f} (cls {r['resonance_classical']:4.2f}) ruler={r['top_ruler']:<8s}[{r['tier_fired'][:4]}] "
              f"t0={r['t0_asym']:5.1f} -> adj={r['sector_adj_asym']:6.1f}")

    print("\n=== TOP 15 CLASSICAL-ONLY resonance (provenance-filtered) ===")
    cls = sorted([r for r in out if r["resonance_classical"] > 0], key=lambda x: -(x["t0_asym"] * (1 + x["resonance_classical"] / 25)))
    seen = set(); n = 0
    for r in cls:
        key = (r["date"], r["sector"])
        if key in seen:
            continue
        seen.add(key); n += 1
        if n > 15:
            break
        print(f"  {r['ticker']:<6s} {r['name'][:28]:<28s} {r['date']}  sect={r['sector']:<18s} "
              f"cls_res={r['resonance_classical']:5.2f}  t0={r['t0_asym']:5.1f}")


if __name__ == "__main__":
    main()
