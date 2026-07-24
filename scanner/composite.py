"""
The Opportunity score and regime classifier.

Opportunity = +0.25 * ProfitFuel_z          (Kalecki-Levy -- mechanical bridge to EPS)
            + 0.20 * CreditImpulse_z        (external + internal credit fuel)
            + 0.15 * Institutional          (dated legislative catalyst, IRS/5)
            + 0.15 * ValuationGap_z         (cheap re-rates; expensive snaps)
            + 0.10 * CarryCushion_z         (FX-adjusted real-rate buffer)
            - 0.15 * Crowding_z             (consensus OW has no marginal buyer)
            - 0.05 * SuddenStopRisk_z       (FX-mismatch / rollover fragility)

ProfitFuel is the new dominant term. The Levy Forecasting Center's contemporary
methodology (David A. Levy et al., *Where Profits Come From*, 2008) treats the
profit cycle as the load-bearing variable for equity prices. By making it the
highest-weighted factor we promote the mechanical link from sectoral accounting
to EPS over softer 'flow' signals.

The two negative terms separate a *flow* from an *opportunity*: they stop the
model buying the top of a consensus trade (the India / Japan trap).

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
from . import kalecki_levy as KL
from . import regime as R
from . import tobin_q as TQ
from . import sfc_integrity as SI
from . import minsky_fragility as MF


# Setser China hidden-surplus haircut. CFR "Follow the Money" Feb 2026 +
# May 2026 Foreign Affairs piece quantify ~$500bn gap between reported and
# implied CN current account; we discount all CN factor contributions by
# this multiplier so the model doesn't act on a known-biased input for the
# F-archetype's largest weight. Applied AFTER archetype tilts.
DATA_CONFIDENCE_HAIRCUT: dict[str, float] = {
    "CN": 0.6,           # Setser hidden-FX + state-bank backdoor intervention
    "RU": 0.4,           # sanctions data refusal
    "IR": 0.3,
    "VE": 0.2,
}


# Weights, re-calibrated to the historical backtest (backtest.component_ic):
# at the 2-year horizon the reconstructed profit-fuel (+0.058) and external
# (+0.057) legs led forward returns, valuation was modest (+0.030), and the
# credit-impulse leg added ~nothing (-0.004) -- it leads only <1y and turns
# CONTRARIAN at 2-3y. So credit is trimmed from 0.20 -> 0.12 (it earns its
# keep as a near-term signal, surfaced separately in horizon.py, not as a
# medium-term fundamental), and the weight is moved to the validated legs:
# profit_fuel 0.25 -> 0.28 and valuation 0.15 -> 0.20.
WEIGHTS = {
    "profit_fuel": 0.28,     # strongest validated leg (backtest IC +0.058)
    "credit_impulse": 0.12,  # trimmed: ~0 at annual horizon, contrarian at 2-3y
    "institutional": 0.15,
    "valuation_gap": 0.20,   # raised: mean-reversion validated (+0.030)
    "carry_cushion": 0.10,
    "crowding": -0.15,
    "suddenstop_risk": -0.05,
}

# Archetype-conditional sign/scale tweaks. The same raw factor means different
# things by configuration; these multiply the factor's contribution per
# primary archetype. 1.0 = neutral. (Kept conservative and legible.)
ARCHETYPE_TILTS: dict[str, dict[str, float]] = {
    # Anglo-mimic: rising saving / falling credit is a bigger negative; the
    # household-saving drag on profits matters extra here
    "B": {"credit_impulse": 1.3, "suddenstop_risk": 1.2, "profit_fuel": 1.2},
    # Mercantilist saver: profit fuel from fiscal pivot IS the thesis (DE, JP)
    "C": {"profit_fuel": 1.3, "institutional": 1.1},
    # Entrepot: flow/FDI signal is MNC noise -> heavily discount; profits MNC-distorted
    "D": {"credit_impulse": 0.4, "valuation_gap": 0.6, "profit_fuel": 0.5},
    # EMU trap: only eurozone-wide cycle matters. RRF disbursements partially
    # offset the profit_fuel discount for IT/ES/PT/GR (handled via new POLICIES
    # entries). TARGET2 stress channelled through suddenstop_risk amplifier.
    "E": {"credit_impulse": 0.6, "profit_fuel": 0.9, "suddenstop_risk": 1.5},
    # Directed-credit: credit signal policy-administered -> discount; profit
    # equation noisy because gov deficit offset by household-saving surge (CN)
    "F": {"credit_impulse": 0.7, "institutional": 1.2, "profit_fuel": 0.7},
    # Commodity rent: market-opening (institutional) + fiscal capex are the levers
    "G": {"institutional": 1.3, "profit_fuel": 1.1},
    # Frontier: sudden-stop dominates; profit-fuel via fiscal expansion is
    # often hot-money-financed and fragile -> discount
    "I": {"suddenstop_risk": 2.0, "carry_cushion": 0.7, "profit_fuel": 0.8},
    # Sanctioned: signal unreliable -> mute everything
    "X": {"credit_impulse": 0.2, "institutional": 0.2, "valuation_gap": 0.2,
          "carry_cushion": 0.2, "crowding": 0.2, "suddenstop_risk": 0.5,
          "profit_fuel": 0.2},
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
    # Join the Kalecki-Levy profit-fuel impulse onto the panel (left-join so
    # any country missing from kalecki_levy._COMPONENTS gets a 0).
    kl_components = KL.components_df()
    panel = panel.copy()
    panel["profit_fuel"] = KL.profit_fuel(kl_components).reindex(panel.index).fillna(0.0)

    z_cols = ["profit_fuel", "credit_impulse", "valuation_gap",
              "carry_cushion", "crowding", "suddenstop_risk"]
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

    # --- Regime overlay (Keen / Dalio / Marathon / Napier / NBFI) ---------
    overlay = R.overlay(panel)
    out = out.join(overlay, how="left")

    # Marathon capex-squeeze enters as an explicit additive overlay (small
    # weight: it's a contrarian *micro* signal not a macro signal).
    out["opportunity_raw"] = out["opportunity"]
    out["opportunity"] = out["opportunity"] + 0.10 * out["marathon_squeeze"].fillna(0.0)
    # Napier repression amplifies bull setups in C-archetype countries where
    # captive savings are being deployed (joins the institutional leg morally).
    out["opportunity"] = out["opportunity"] + 0.05 * (
        out["napier_repression"].fillna(0.0) - 1.0  # de-mean
    )
    # NBFI continuous-leverage penalty (replaces 0/1 flag). Penalises
    # bull-regime confidence where aggregate balances hide sub-sector
    # fragility (UK-2022-LDI lesson).
    out["opportunity"] = out["opportunity"] - 0.06 * out["nbfi_leverage"].fillna(0.5).clip(0, 3)
    # Minsky financial-fragility penalty (Tymoigne WP 654). A profit boom in a
    # Ponzi-financed configuration ends like US housing 2007 -- penalise the
    # opportunity score by the 0-1 fragility index. De-meaned at 0.3 so the
    # robust-hedge majority is broadly neutral and only the Ponzi tail is hit.
    out["minsky_fragility"] = out.index.map(MF.fragility_index)
    out["minsky_regime"] = out.index.map(MF.regime_label)
    out["opportunity"] = out["opportunity"] - 0.20 * (
        out["minsky_fragility"].fillna(0.3) - 0.3
    ).clip(lower=0)
    # Tobin-q endogeneity: penalise the investment leg when q is above its
    # stage-conditioned target (capex deferral / buyback substitution); lift
    # it when q is below target (portfolio rebalancing pushes equity issuance).
    out["tobin_q"] = out.index.map(TQ.lookup_q)
    out["q_investment_adj"] = out.apply(
        lambda row: TQ.investment_penalty(row.name, row.get("dalio_stage", "expansion")),
        axis=1,
    )
    out["opportunity"] = out["opportunity"] + 0.08 * out["q_investment_adj"].fillna(0.0)
    # Strategic-Analysis required-private-balance test (Levy SA signature).
    # credit-fuelled-deficit is the crash-risk direction (penalise lightly);
    # demand-draining-surplus is a growth-ceiling, not a crash -- surfaced
    # informationally, no penalty.
    from . import strategic_analysis as SA
    sa_dir = {}
    for iso in out.index:
        r = SA.evaluate(iso)
        sa_dir[iso] = r.direction if r else "n/a"
    out["sa_direction"] = pd.Series(sa_dir).reindex(out.index).fillna("n/a")
    out["opportunity"] = out["opportunity"] - 0.10 * (
        out["sa_direction"] == "credit-fuelled-deficit").astype(float)

    # SFC integrity check -- data confidence per country
    integrity = SI.panel_report()
    out["data_confidence"] = integrity["data_confidence"].reindex(out.index).fillna("medium")
    # Setser-style haircut on known-biased data systems (CN, sanctioned).
    # Multiply the *positive* component contributions by the haircut so a
    # bull score on a discounted-data country needs more to clear neutral.
    haircut = pd.Series(DATA_CONFIDENCE_HAIRCUT).reindex(out.index).fillna(1.0)
    out["opportunity"] = out["opportunity"] * haircut

    out["percentile"] = T.cross_sectional_percentile(out["opportunity"])
    out["regime"] = out.apply(
        lambda r: R.regime_from_tilt(r["opportunity"],
                                     float(r.get("stage_threshold_tilt", 0.0) or 0.0)),
        axis=1,
    )
    out["note"] = panel["note"]
    out["estimated"] = panel.get("estimated", False)
    # Uncertainty propagation: sigma on the score + regime probabilities.
    # Imported here (not at module top) to avoid a circular import.
    from . import robustness as RB
    out = RB.propagate(out)
    return out.sort_values("opportunity", ascending=False)


def top_opportunities(scored: pd.DataFrame, n: int = 5) -> pd.DataFrame:
    """The n highest-scoring setups."""
    return scored.head(n)


def avoid_list(scored: pd.DataFrame, n: int = 5) -> pd.DataFrame:
    """The n lowest-scoring / most-crowded setups to avoid."""
    return scored.tail(n).iloc[::-1]
