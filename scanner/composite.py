"""
The Opportunity score and regime classifier.

Opportunity = +0.25 * CreditImpulse_z      (external + internal fuel)
            + 0.20 * Institutional          (dated legislative catalyst, IRS/5)
            + 0.20 * ValuationGap_z         (cheap re-rates; expensive snaps)
            + 0.15 * CarryCushion_z         (FX-adjusted real-rate buffer)
            - 0.15 * Crowding_z             (consensus OW has no marginal buyer)
            - 0.05 * SuddenStopRisk_z       (FX-mismatch / rollover fragility)

The two negative terms are what separate a *flow* from an *opportunity*: they
stop the model buying the top of a consensus trade (the India/Japan trap).

All factors are z-scored across the cross-section before weighting so the score
is dimensionless. Institutional enters as a 0-1 catalyst intensity (IRS / 5),
not z-scored, because its meaning is absolute (a passed law is a passed law).

A `bull`/`bear`/`neutral` regime label is applied with a persistence-ready
threshold; in a live series the >=2-consecutive-period filter prevents whipsaw.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from . import transforms as T


WEIGHTS = {
    "credit_impulse": 0.25,
    "institutional": 0.20,
    "valuation_gap": 0.20,
    "carry_cushion": 0.15,
    "crowding": -0.15,
    "suddenstop_risk": -0.05,
}

# Archetype-conditional sign/scale tweaks. The same raw factor means different
# things by configuration; these multiply the factor's contribution per
# primary archetype. 1.0 = neutral. (Kept conservative and legible.)
ARCHETYPE_TILTS: dict[str, dict[str, float]] = {
    # Anglo-mimic: rising saving / falling credit is a bigger negative
    "B": {"credit_impulse": 1.3, "suddenstop_risk": 1.2},
    # Directed-credit: a credit signal is policy-administered -> discount it
    "F": {"credit_impulse": 0.7, "institutional": 1.2},
    # Frontier: sudden-stop risk dominates; carry can be a value-trap lure
    "I": {"suddenstop_risk": 2.0, "carry_cushion": 0.7},
    # Entrepot: flow/FDI signal is mostly accounting noise -> heavily discount
    "D": {"credit_impulse": 0.4, "valuation_gap": 0.6},
    # EMU trap: only the eurozone-wide cycle matters; mute idiosyncratic credit
    "E": {"credit_impulse": 0.6},
    # Commodity rent: market-opening (institutional) is the real lever
    "G": {"institutional": 1.3},
    # Sanctioned: signal unreliable -> mute everything
    "X": {"credit_impulse": 0.2, "institutional": 0.2, "valuation_gap": 0.2,
          "carry_cushion": 0.2, "crowding": 0.2, "suddenstop_risk": 0.5},
}


def _zscore_cross_section(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    """Z-score each column across the cross-section, winsorised to +/-3."""
    z = pd.DataFrame(index=df.index)
    for c in cols:
        s = df[c].astype(float)
        sd = s.std(ddof=0)
        zc = (s - s.mean()) / sd if sd else s * 0.0
        z[c] = zc.clip(-3, 3)
    return z


def score_panel(panel: pd.DataFrame, archetype_of: dict[str, str]) -> pd.DataFrame:
    """
    Compute the Opportunity score for the whole panel.

    Parameters
    ----------
    panel : DataFrame indexed by ISO with the six factor columns + 'note'.
    archetype_of : ISO -> primary archetype tag, used for the tilts.

    Returns a DataFrame with z-scored factors, weighted contributions,
    the composite `opportunity` score, percentile rank, and regime label.
    """
    z_cols = ["credit_impulse", "valuation_gap", "carry_cushion",
              "crowding", "suddenstop_risk"]
    z = _zscore_cross_section(panel, z_cols)
    # Institutional enters as absolute catalyst intensity (IRS / 5), in [0,1].
    z["institutional"] = (panel["institutional"].astype(float) / 5.0).clip(0, 1)

    contrib = pd.DataFrame(index=panel.index)
    for factor, w in WEIGHTS.items():
        col = z[factor].copy()
        # apply archetype tilts row-by-row
        tilt = panel.index.map(
            lambda iso: ARCHETYPE_TILTS.get(archetype_of.get(iso, ""), {}).get(factor, 1.0)
        )
        contrib[factor] = w * col.values * np.asarray(tilt, dtype=float)

    out = z.copy()
    out["opportunity"] = contrib.sum(axis=1)
    out["percentile"] = T.cross_sectional_percentile(out["opportunity"])
    out["regime"] = out["opportunity"].apply(_regime)
    out["note"] = panel["note"]
    out["estimated"] = panel.get("estimated", False)
    return out.sort_values("opportunity", ascending=False)


def _regime(score: float, bull: float = 0.15, bear: float = -0.15) -> str:
    """Label a regime. In a live time series, require >=2 consecutive periods."""
    if score >= bull:
        return "bull"
    if score <= bear:
        return "bear"
    return "neutral"


def top_opportunities(scored: pd.DataFrame, n: int = 5) -> pd.DataFrame:
    """The n highest-scoring setups."""
    return scored.head(n)


def avoid_list(scored: pd.DataFrame, n: int = 5) -> pd.DataFrame:
    """The n lowest-scoring / most-crowded setups to avoid."""
    return scored.tail(n).iloc[::-1]
