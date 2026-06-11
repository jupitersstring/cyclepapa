#!/usr/bin/env python3
"""
waterfall.py — Monte Carlo over the candidate waterfall (§2.5 fix).

Three-scenario tables flatten the distribution. This samples joint
(EBITDA percentile, multiple percentile) with positive correlation,
then a dilution event indicator, to produce a real return distribution.

Usage:
    python -m src.waterfall data/candidates/WLN.yaml
"""

from __future__ import annotations

import math
import random
import sys
from pathlib import Path
from statistics import median, quantiles

try:
    import yaml
except ImportError:
    print("Install PyYAML", file=sys.stderr)
    sys.exit(1)

N_DRAWS = 10_000


def correlated_uniforms(rho: float, n: int) -> list[tuple[float, float]]:
    """Two correlated U(0,1) draws via Gaussian copula."""
    out = []
    for _ in range(n):
        z1 = random.gauss(0, 1)
        z2 = rho * z1 + math.sqrt(1 - rho * rho) * random.gauss(0, 1)
        # Phi (standard normal CDF) approximation
        u1 = 0.5 * (1 + math.erf(z1 / math.sqrt(2)))
        u2 = 0.5 * (1 + math.erf(z2 / math.sqrt(2)))
        out.append((u1, u2))
    return out


def percentile_to_factor(p: float) -> float:
    """Map U(0,1) into a fan of EBITDA factors (0.4x at 0, 1.0x at 0.5, 2.5x at 1.0)."""
    if p < 0.25:
        return 0.4 + (p / 0.25) * 0.4   # 0.4 → 0.8 across bottom quartile
    if p < 0.75:
        return 0.8 + ((p - 0.25) / 0.50) * 0.7  # 0.8 → 1.5 across IQR
    return 1.5 + ((p - 0.75) / 0.25) * 1.0      # 1.5 → 2.5 across top quartile


def simulate(candidate: dict, n: int = N_DRAWS, rho: float = 0.6) -> dict:
    """Return distribution of return multiples."""
    wf = candidate["waterfall"]
    # Anchor scenarios as percentile centers
    bear_mult = wf["bear"]["return_multiple"]
    base_mult = wf["base"]["return_multiple"]
    bull_mult = wf["bull"]["return_multiple"]

    # Re-derive a smooth mapping from (EBITDA pct, multiple pct) to return.
    # Linear interp between scenario anchors.
    def interp(p: float) -> float:
        if p < 0.25:
            return bear_mult + (p / 0.25) * (base_mult - bear_mult) * 0.5
        if p < 0.75:
            return base_mult * (0.7 + 0.6 * (p - 0.25))
        return base_mult + ((p - 0.75) / 0.25) * (bull_mult - base_mult)

    # Probability of a forced dilutive event scales with bear probability
    p_dilution = wf["bear"]["p"] * 0.6  # most bear paths involve another raise

    draws = correlated_uniforms(rho, n)
    returns = []
    for u1, u2 in draws:
        # Joint percentile is a blend (since both cycle-driven)
        joint = (u1 + u2) / 2
        r = interp(joint)
        if random.random() < p_dilution:
            r *= 0.5  # 50% haircut from dilution event
        returns.append(r)

    returns.sort()
    q = quantiles(returns, n=20)  # 5th-percentile increments
    return {
        "ticker": candidate.get("ticker"),
        "n_draws": n,
        "rho": rho,
        "p_dilution_event": p_dilution,
        "median": median(returns),
        "mean": sum(returns) / n,
        "p05": q[0],
        "p25": q[4],
        "p50": q[9],
        "p75": q[14],
        "p95": q[18],
        "prob_loss_gt_50pct": sum(1 for r in returns if r < 0.5) / n,
        "prob_3x_or_more": sum(1 for r in returns if r >= 3.0) / n,
        "prob_5x_or_more": sum(1 for r in returns if r >= 5.0) / n,
    }


def main():
    if len(sys.argv) < 2:
        print(__doc__, file=sys.stderr)
        sys.exit(2)
    random.seed(42)  # deterministic for reproducible reports
    for p in sys.argv[1:]:
        with open(p) as f:
            data = yaml.safe_load(f)
        if not data.get("waterfall"):
            print(f"{p}: no waterfall, skipping")
            continue
        result = simulate(data)
        print(f"\n{result['ticker']} ({Path(p).name}):")
        print(f"  draws={result['n_draws']}, rho={result['rho']}, "
              f"p(dilution event)={result['p_dilution_event']:.2f}")
        print(f"  median return:    {result['median']:.2f}x")
        print(f"  mean return:      {result['mean']:.2f}x")
        print(f"  P05/P25/P50/P75/P95: "
              f"{result['p05']:.2f} / {result['p25']:.2f} / "
              f"{result['p50']:.2f} / {result['p75']:.2f} / {result['p95']:.2f}")
        print(f"  P(loss >50%):     {result['prob_loss_gt_50pct']:.1%}")
        print(f"  P(≥3x):           {result['prob_3x_or_more']:.1%}")
        print(f"  P(≥5x):           {result['prob_5x_or_more']:.1%}")


if __name__ == "__main__":
    main()
