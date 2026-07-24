"""
Kohler EM carry-driven boom-bust cycle classifier.

Karsten Kohler, 'Exchange rate dynamics, balance sheet effects, and capital
flows: A Minskyan model of emerging market boom-bust cycles' (JPKE /
post-Keynesian literature, 2019+), formalises the mechanism Godley's
open-economy models imply for the H/I archetypes:

    interest differential attracts carry inflows
      -> currency appreciates
      -> FX-debtor balance sheets IMPROVE (foreign-currency debt shrinks in
         local terms) -- the Minskyan 'margin of safety' widens
      -> more borrowing, asset prices rise, the boom self-validates
      -> until the differential compresses or global risk appetite turns
      -> outflows, depreciation, balance-sheet DESTRUCTION (FX debt balloons)
      -> forced deleveraging, bust, eventual recovery at a cheaper currency.

The cycle is endogenous: the appreciation phase CREATES the fragility that
the depreciation phase detonates. This is the formal version of the scanner's
I-archetype story, and it gives us a PHASE variable the composite lacks --
the same carry_cushion reading means opposite things in the inflow-boom
phase (ride it) and the late-boom phase (fade it).

Phase classification (heuristic mapping from existing panel factors):

    inflow_boom   high carry + accelerating credit + low/contained mismatch
    late_boom     high carry + hot credit + HIGH mismatch (fragility built)
    reversal      carry compressing / credit decelerating with high mismatch
    bust          credit contracting + mismatch realised (post-depreciation)
    recovery      low carry, cheap currency, credit stabilising, mismatch purged

Applied to EM archetypes only (H, I, G-EM, F-EM); AEs get 'n/a'.
"""

from __future__ import annotations

import pandas as pd

from .archetypes import COUNTRIES, lookup
from .data import default_panel
from . import seven_processes as SP


# Archetypes the carry-cycle logic applies to (EM members).
_EM_ARCHETYPES = {"H", "I"}
_EM_EXTRA = {"CL", "PE", "CO", "KZ", "NG", "ZA", "VN", "MY", "TH"}  # G/F-EM members


def _is_em(iso: str) -> bool:
    c = lookup(iso)
    if c is None:
        return False
    return c.primary in _EM_ARCHETYPES or iso in _EM_EXTRA


def classify(iso: str, carry: float, credit: float, mismatch: float,
             dsr_accel: float) -> str:
    """
    Map (carry, credit impulse, FX mismatch, DSR acceleration) to a Kohler
    phase. Thresholds are calibrated to the panel's z-scored factor units.
    """
    if not _is_em(iso):
        return "n/a"
    hot_credit = credit > 0.8
    contracting = credit < -0.3
    high_carry = carry > 1.5
    high_mismatch = mismatch > 1.0 or dsr_accel > 0.5

    if contracting and high_mismatch:
        return "bust"
    if contracting or (carry < 0 and not high_mismatch):
        return "recovery"
    if hot_credit and high_mismatch:
        # Fragility built. With carry still high the boom self-extends
        # (classic late_boom); with carry gone the credit is running on
        # momentum alone into built mismatch -- the most dangerous corner
        # (Turkey-2021 pattern) -- also late_boom, one notch from reversal.
        return "late_boom"
    if hot_credit and not high_mismatch:
        return "inflow_boom"        # ride it
    if high_mismatch and not hot_credit:
        return "reversal"           # inflows stalling into built fragility
    return "mid_cycle"


# Phase -> how to read a bull composite score in that phase.
PHASE_READING = {
    "inflow_boom": "ride -- appreciation self-validates, fragility not yet built",
    "mid_cycle": "neutral carry backdrop",
    "late_boom": "FADE -- the appreciation phase has built the fragility it will detonate",
    "reversal": "exit -- inflows stalling into built FX mismatch",
    "bust": "avoid until deleveraging completes",
    "recovery": "accumulate -- mismatch purged, currency cheap",
    "n/a": "",
}


def panel() -> pd.DataFrame:
    """Classify every EM in the panel."""
    p = default_panel()
    rows = []
    for c in COUNTRIES:
        iso = c.iso
        if iso not in p.index:
            continue
        r = p.loc[iso]
        phase = classify(
            iso,
            carry=float(r.get("carry_cushion", 0.0)),
            credit=float(r.get("credit_impulse", 0.0)),
            mismatch=float(r.get("suddenstop_risk", 0.0)),
            dsr_accel=SP.DSR_ACCELERATION_4Q.get(iso, 0.0),
        )
        if phase == "n/a":
            continue
        rows.append({"iso": iso, "country": c.name, "archetype": c.primary,
                     "carry": round(float(r.get("carry_cushion", 0.0)), 1),
                     "credit": round(float(r.get("credit_impulse", 0.0)), 1),
                     "fx_mismatch": round(float(r.get("suddenstop_risk", 0.0)), 1),
                     "kohler_phase": phase,
                     "reading": PHASE_READING[phase]})
    return pd.DataFrame(rows).set_index("iso")


def phase_of(iso: str) -> str:
    """Convenience: the Kohler phase for one country."""
    df = panel()
    return df.loc[iso, "kohler_phase"] if iso in df.index else "n/a"
