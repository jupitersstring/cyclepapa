"""
Robustness & uncertainty -- knowing what the scanner knows.

Three methodological instruments that address the scanner's biggest honest
weakness: it reports point estimates from largely calibrated inputs, drawing
hard regime lines through gaps far smaller than the input uncertainty.

1. UNCERTAINTY PROPAGATION. Each factor carries a sigma scaled by its data
   confidence (a live World Bank print is tighter than a hand-calibrated
   estimate). We propagate these analytically through the composite's linear
   weight x archetype-tilt structure to a sigma on the opportunity score, then
   convert the regime call into a PROBABILITY:
       sigma_opp = sqrt( sum_f (w_f * tilt_f * sigma_f)^2 + sigma_overlay^2 )
       P(bull) = 1 - Phi((bull_threshold - opp)/sigma_opp)
   A regime labelled 'bull' at 55% confidence is honestly different from one
   at 95%, and the label alone hid that.

2. ATTRIBUTION. Decomposes each country's opportunity into the signed
   contribution of every factor, so "why is this country ranked here" is
   answerable -- the driver, not just the score.

3. FACTOR REDUNDANCY. The composite sums factors as if independent, but
   profit-fuel, credit and carry co-move. We report the cross-sectional
   correlation and an effective-number-of-independent-factors so the user
   knows how much genuinely independent information the score contains.

Phi via math.erf -- no scipy dependency.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

from . import composite as CMP


# Per-factor base uncertainty, in z-units. Institutional is a dated catalyst
# score (fairly certain); the market factors are noisier.
_BASE_SIGMA = {
    "profit_fuel": 0.55, "credit_impulse": 0.50, "valuation_gap": 0.45,
    "carry_cushion": 0.40, "crowding": 0.50, "suddenstop_risk": 0.55,
    "institutional": 0.15,
}
# Data-confidence multiplier on every factor sigma for that country.
_CONF_MULT = {"high": 0.6, "medium": 1.0, "low": 1.8}
# Fixed uncertainty from the additive overlays (marathon/napier/nbfi/minsky/q/sa).
_SIGMA_OVERLAY = 0.06


def _phi(x: float) -> float:
    """Standard normal CDF."""
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _tilt(factor: str, arch: str) -> float:
    return CMP.ARCHETYPE_TILTS.get(arch, {}).get(factor, 1.0)


def propagate(scored: pd.DataFrame) -> pd.DataFrame:
    """
    Add opportunity uncertainty and regime probabilities to the scored frame.
    `scored` must carry the z-scored factor columns, archetype, data_confidence,
    stage_threshold_tilt and opportunity (as composite.score_panel emits).
    """
    out = scored.copy()
    factors = list(_BASE_SIGMA)
    sig_opp, p_bull, p_bear, p_neu = [], [], [], []
    for iso, r in out.iterrows():
        arch = r.get("archetype", "")
        conf = _CONF_MULT.get(r.get("data_confidence", "medium"), 1.0)
        var = _SIGMA_OVERLAY ** 2
        for f in factors:
            w = CMP.WEIGHTS.get(f, 0.0)
            sig_f = _BASE_SIGMA[f] * conf
            var += (w * _tilt(f, arch) * sig_f) ** 2
        s = math.sqrt(var)
        opp = float(r["opportunity"])
        tilt = float(r.get("stage_threshold_tilt", 0.0) or 0.0)
        bull_thr = 0.15 + tilt
        bear_thr = -0.15 - abs(tilt) * 0.5
        pb = 1.0 - _phi((bull_thr - opp) / s)
        pbe = _phi((bear_thr - opp) / s)
        pn = max(0.0, 1.0 - pb - pbe)
        sig_opp.append(s); p_bull.append(pb); p_bear.append(pbe); p_neu.append(pn)
    out["opp_sigma"] = np.round(sig_opp, 3)
    out["p_bull"] = np.round(p_bull, 2)
    out["p_bear"] = np.round(p_bear, 2)
    out["p_neutral"] = np.round(p_neu, 2)
    out["regime_confidence"] = out.apply(
        lambda r: round(float({"bull": r["p_bull"], "bear": r["p_bear"],
                               "neutral": r["p_neutral"]}.get(r["regime"], 0.0)), 2),
        axis=1)
    return out


def attribution(scored: pd.DataFrame) -> pd.DataFrame:
    """Per-country signed factor contributions to the opportunity score."""
    rows = {}
    for iso, r in scored.iterrows():
        arch = r.get("archetype", "")
        contrib = {}
        for f in _BASE_SIGMA:
            z = float(r.get(f, 0.0) or 0.0)
            contrib[f] = round(CMP.WEIGHTS.get(f, 0.0) * _tilt(f, arch) * z, 3)
        rows[iso] = contrib
    df = pd.DataFrame(rows).T
    df["core_sum"] = df.sum(axis=1).round(3)
    return df


def top_drivers(scored: pd.DataFrame, iso: str, n: int = 3) -> list[tuple[str, float]]:
    """The n factors moving a country's score most (signed)."""
    att = attribution(scored.loc[[iso]]).drop(columns=["core_sum"]).iloc[0]
    return sorted(att.items(), key=lambda kv: -abs(kv[1]))[:n]


def factor_redundancy(scored: pd.DataFrame) -> dict:
    """
    Cross-sectional correlation of the z-scored factors + an effective number
    of independent factors (via the participation ratio of the correlation
    matrix eigenvalues). 7 factors summed as independent may carry far fewer
    than 7 bets.
    """
    cols = [c for c in _BASE_SIGMA if c in scored.columns]
    M = scored[cols].astype(float)
    corr = M.corr()
    # participation ratio of eigenvalues: (sum lambda)^2 / sum(lambda^2)
    ev = np.linalg.eigvalsh(corr.fillna(0).values)
    ev = np.clip(ev, 0, None)
    eff = float((ev.sum() ** 2) / (np.square(ev).sum())) if np.square(ev).sum() else len(cols)
    # redundant pairs |rho| > 0.5
    pairs = []
    for i in range(len(cols)):
        for j in range(i + 1, len(cols)):
            rho = corr.iloc[i, j]
            if abs(rho) > 0.5:
                pairs.append((cols[i], cols[j], round(float(rho), 2)))
    return {"correlation": corr.round(2),
            "effective_independent_factors": round(eff, 2),
            "nominal_factors": len(cols),
            "redundant_pairs": sorted(pairs, key=lambda p: -abs(p[2]))}
