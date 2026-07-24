"""
Horizon-aware scoring -- the term structure made operational.

The backtest proved Godley's framework is not one signal but three, each
owning a different horizon (highfreq.term_structure):

    NEAR  (<1y)   money growth + credit impulse -- positive
    MID   (2-3y)  credit impulse turns CONTRARIAN (credit booms sow busts)
    LONG  (3-4y)  sectoral-balance fuel -- builds

The live composite collapsed all of this into a single number, which both
over-claims (a 4-year direction signal presented as if actionable now) and
mis-signs credit (used positively everywhere, though it flips negative at
2-3y). This module derives three horizon views from the cross-sectional
factors the scanner already has, with the signs the backtest established:

    near_score = z(credit_impulse) + z(carry)          liquidity/momentum, +
    long_score = z(profit_fuel) + z(valuation) + IRS   fundamental fuel, +
    mid_flag   = credit_impulse high  ->  Minsky warning (bearish 2-3y)

Each country then gets a horizon label -- where its edge actually lives --
so a "bull" is disambiguated into a near-term liquidity bull vs a long-term
fundamental bull, and credit-fuelled setups carry the medium-term caution the
Mian-Sufi evidence demands.
"""

from __future__ import annotations

import pandas as pd


# Backtest-grounded weights (component IC: profit_fuel +0.058, external +0.057,
# valuation +0.030, credit -0.004 at 2y; credit +0.045 at <1y then -0.08 at 3y).
_NEAR_W = {"credit_impulse": 0.6, "carry_cushion": 0.4}
_LONG_W = {"profit_fuel": 0.5, "valuation_gap": 0.3, "institutional": 0.2}
_CREDIT_WARN = 1.0   # credit_impulse z above this = medium-term Minsky risk


def horizon_scores(scored: pd.DataFrame) -> pd.DataFrame:
    """Add near/long horizon scores, a mid-term credit warning, and a label."""
    out = pd.DataFrame(index=scored.index)
    inst = (scored["institutional"] - 0.4) * 2.0 if "institutional" in scored else 0.0
    out["near_score"] = sum(
        w * scored.get(f, 0.0) for f, w in _NEAR_W.items()).round(3)
    out["long_score"] = (
        _LONG_W["profit_fuel"] * scored.get("profit_fuel", 0.0)
        + _LONG_W["valuation_gap"] * scored.get("valuation_gap", 0.0)
        + _LONG_W["institutional"] * inst).round(3)
    out["credit_warning"] = (scored.get("credit_impulse", 0.0) > _CREDIT_WARN)

    def _label(r):
        near, lng, warn = r["near_score"], r["long_score"], r["credit_warning"]
        if near > 0.4 and lng > 0.4:
            base = "bull across horizons"
        elif lng > 0.4 and near <= 0.4:
            base = "long-term (fundamental) bull"
        elif near > 0.4 and lng <= 0.4:
            base = "near-term (liquidity) bull"
        elif near < -0.4 and lng < -0.4:
            base = "bear across horizons"
        elif lng < -0.4:
            base = "long-term bear"
        elif near < -0.4:
            base = "near-term bear"
        else:
            base = "mixed / neutral"
        if warn and "bull" in base:
            base += " — credit-fuelled (2-3y caution)"
        return base

    out["horizon_label"] = out.apply(_label, axis=1)
    return out


def verdict(scored: pd.DataFrame, iso: str) -> str:
    hs = horizon_scores(scored.loc[[iso]]).iloc[0]
    return (f"near {hs['near_score']:+.2f} / long {hs['long_score']:+.2f}"
            + ("  !! credit-fuelled (2-3y caution)" if hs["credit_warning"] else "")
            + f"  — {hs['horizon_label']}")
