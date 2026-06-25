"""Layer pair-correlation matrix.

S1.4 from AUDIT.md: "ADT fires 8 layers" but how independent are those
8? PSU + opportunistic insiders + verified buyback + bb-insider
overlay all reward "company doing right by shareholders" -- they are
positively correlated. Each isn't an independent confirmation.

This module computes Spearman rank correlation across the universe
for every pair of layers in full_universe_consensus.csv. Outputs:
  layer_correlation_matrix.csv   (symmetric matrix)
  layer_correlation_pairs.csv    (pair list, sorted by correlation)

Plus an effective-independence score that collapses pairs > 0.6
correlation into shared weight for transparency.

NOTHING IS REMOVED. Pure analysis -- existing scoring weights stay.
"""

from __future__ import annotations

import csv
import json
from itertools import combinations
from pathlib import Path

ROOT = Path("/home/user/cyclepapa")
OUT_MAT = ROOT / "layer_correlation_matrix.csv"
OUT_PAIRS = ROOT / "layer_correlation_pairs.csv"
OUT_EFF = ROOT / "effective_layers.json"


def rank(x: list[float]) -> list[float]:
    """Average rank (ties get average)."""
    sx = sorted(enumerate(x), key=lambda t: t[1])
    rk = [0.0] * len(x)
    i = 0
    while i < len(sx):
        j = i
        while j + 1 < len(sx) and sx[j+1][1] == sx[i][1]:
            j += 1
        avg = (i + j + 2) / 2  # ranks 1-indexed
        for k in range(i, j+1):
            rk[sx[k][0]] = avg
        i = j + 1
    return rk


def pearson(x: list[float], y: list[float]) -> float:
    n = len(x)
    if n < 2: return 0.0
    mx = sum(x) / n
    my = sum(y) / n
    num = sum((xi - mx) * (yi - my) for xi, yi in zip(x, y))
    dx = sum((xi - mx) ** 2 for xi in x)
    dy = sum((yi - my) ** 2 for yi in y)
    if dx == 0 or dy == 0: return 0.0
    return num / (dx ** 0.5 * dy ** 0.5)


def spearman(x: list[float], y: list[float]) -> float:
    return pearson(rank(x), rank(y))


def main() -> int:
    rows = list(csv.DictReader(open(ROOT / "full_universe_consensus.csv")))
    print(f"loaded {len(rows)} rows")

    # All _pts columns are the per-layer scores
    layer_cols = [k for k in rows[0].keys() if k.endswith("_pts")]
    print(f"layer columns: {len(layer_cols)}")
    for c in layer_cols:
        print(f"  {c}")

    # Extract per-layer numeric series
    series = {c: [] for c in layer_cols}
    for r in rows:
        for c in layer_cols:
            try:
                series[c].append(float(r[c] or 0))
            except Exception:
                series[c].append(0.0)

    # Compute correlation matrix
    n = len(layer_cols)
    mat = {a: {b: 1.0 for b in layer_cols} for a in layer_cols}
    pairs = []
    print(f"computing {n*(n-1)//2} pair correlations...")
    for a, b in combinations(layer_cols, 2):
        rho = spearman(series[a], series[b])
        mat[a][b] = rho
        mat[b][a] = rho
        pairs.append((a, b, rho))

    pairs.sort(key=lambda x: -abs(x[2]))

    # Write matrix
    with OUT_MAT.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["layer"] + layer_cols)
        for a in layer_cols:
            w.writerow([a] + [round(mat[a][b], 3) for b in layer_cols])
    print(f"wrote {OUT_MAT}")

    # Write pairs
    with OUT_PAIRS.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["layer_a", "layer_b", "spearman_rho", "abs_rho", "interpretation"])
        for a, b, rho in pairs:
            interp = ("very_high" if abs(rho) > 0.6
                      else "high" if abs(rho) > 0.4
                      else "moderate" if abs(rho) > 0.25
                      else "weak" if abs(rho) > 0.1
                      else "negligible")
            w.writerow([a, b, round(rho, 3), round(abs(rho), 3), interp])
    print(f"wrote {OUT_PAIRS}")

    # Effective independence -- group pairs > 0.6 correlation into clusters
    # using union-find
    parent = {c: c for c in layer_cols}
    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    for a, b, rho in pairs:
        if abs(rho) > 0.6:
            union(a, b)

    clusters = {}
    for c in layer_cols:
        r = find(c)
        clusters.setdefault(r, []).append(c)
    cluster_list = list(clusters.values())

    n_effective = len(cluster_list)
    OUT_EFF.write_text(json.dumps({
        "n_raw_layers": n,
        "n_effective_layers_at_06": n_effective,
        "clusters": cluster_list,
    }, indent=2))
    print(f"wrote {OUT_EFF}")
    print(f"\nRaw layer count:        {n}")
    print(f"Effective at rho>0.6:  {n_effective}")

    print(f"\n=== Top 20 correlated pairs ===")
    for a, b, rho in pairs[:20]:
        print(f"  {rho:>+6.3f}  {a:<28} {b}")

    print(f"\n=== Clusters with multiple layers (would collapse) ===")
    for cluster in cluster_list:
        if len(cluster) > 1:
            print(f"  - {cluster}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
