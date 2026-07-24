"""
Strategic-Analysis-style diagnostics (the Levy SA signature method).

The Levy Economics Institute Strategic Analysis series (Godley 1999 onward;
continued by Papadimitriou-Zezza-Nikiforos-Yajima) does something the rest of
the scanner does not: it INVERTS the three-balance identity to ask the
question that actually matters --

    "For this country to hit its growth target, given its fiscal stance and
     its external position, what must the PRIVATE sector's financial balance
     do -- and is that plausible?"

This is the diagnostic that made Godley's record. In *Seven Unsustainable
Processes* (1999) and again in *The U.S. Economy: Is There a Way Out of the
Woods?* (2007) he showed that maintaining projected US growth required the
private sector to run an ever-deeper financial deficit -- household borrowing
"would have to reach 14 percent of GDP by 2010," which he and Zezza called
"wildly implausible." The crisis arrived when the private sector refused.

The identity (net-lending convention, % GDP):

    b_priv + b_govt + b_row = 0,    b_row = -CAB
    => b_priv = -b_govt + CAB = (govt deficit) + (current account balance)

The SA inversion holds growth as the target and lets the private balance be the
residual that must adjust:

    CAB(g)        = CAB_now - m * (g - g_trend)     faster growth -> more imports
                                                     (m = marginal import leakage)
    b_govt(stance)= policy-set fiscal balance
    b_priv_req    = -b_govt(stance) + CAB(g)

If `b_priv_req` is pushed to an implausible extreme -- a deep, deteriorating
private deficit (Anglo/convergence/frontier: the unsustainable-credit case) OR
a private surplus so large it cannot be spent down (savers/EMU: the
output-gap/recession case) -- the growth target is not financeable on the
current policy mix. That is the Godley flag.

This module also runs the SA SCENARIO grid (baseline / fiscal consolidation /
fiscal expansion) and reports the three balances under each, exactly as the SA
papers present them.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from . import godley_projection as GP
from .archetypes import lookup, COUNTRIES
from .sources import live


# Marginal import leakage by archetype: how much a point of extra growth
# worsens the current account. Open/convergence economies leak more; large
# closed-ish economies leak less.
_IMPORT_LEAKAGE = {
    "A": 0.25,  # US: large, relatively closed
    "B": 0.45,  # Anglo-mimic: import-hungry
    "C": 0.30,  # mercantilist: export-strong, moderate leak
    "D": 0.70,  # entrepot: extreme trade openness
    "E": 0.40,  # EMU: open within union
    "F": 0.25,  # directed-credit: managed trade
    "G": 0.35,  # commodity: imports rise with domestic demand
    "H": 0.50,  # convergence: capital-goods import-dependent
    "I": 0.55,  # frontier: import-dependent, FX-constrained
    "X": 0.30,
}

# Trend (potential) growth by archetype, %; the target the private balance is
# solved against. EMs higher, AEs lower.
_TREND_GROWTH = {
    "A": 2.0, "B": 2.0, "C": 1.5, "D": 2.5, "E": 1.2,
    "F": 4.5, "G": 3.0, "H": 4.0, "I": 4.0, "X": 1.5,
}

# Plausibility band for the private financial balance, % GDP. Outside this the
# configuration is historically rare and hard to sustain (Godley's "sensational
# day of reckoning" lives below the lower bound).
PRIV_BALANCE_FLOOR = -6.0   # private deficit deeper than this = credit-fuelled, fragile
PRIV_BALANCE_CEIL = +8.0    # private surplus larger than this = chronic demand drain

# The "demand-draining-surplus" warning is only meaningful for economies whose
# growth must come from DOMESTIC private demand -- mercantilist savers (C) and
# the EMU trap (E). For entrepots (D) and commodity rentiers (G) a large
# structural private surplus is the normal external-led model, not a warning.
_DOMESTIC_DEMAND_DEPENDENT = {"C", "E", "B", "A"}

# Aspiration growth premium over trend: the SA test bites when a country REACHES
# for above-trend growth, forcing the CA (and hence the private balance) to
# adjust. At exactly trend the import-leakage term is zero and the test is
# static, so we stress at trend + this premium.
ASPIRATION_PREMIUM = 1.0


@dataclass
class SAResult:
    iso: str
    country: str
    archetype: str
    growth_target: float
    fiscal_balance: float        # b_govt, % GDP (negative = deficit)
    ca_now: float                # current CA balance, % GDP
    ca_at_target: float          # CA after import leakage at target growth
    priv_balance_now: float
    priv_balance_required: float # the SA residual
    required_shift_pp: float     # how far the private balance must move
    implausible: bool
    direction: str               # 'credit-fuelled-deficit' | 'demand-draining-surplus' | 'ok'
    note: str = ""


def _inputs(iso: str) -> tuple[float, float] | None:
    """Return (fiscal_balance, ca_balance) preferring live, else calibrated."""
    fiscal = ca = None
    livedf = live.load_cached()
    if livedf is not None and iso in livedf.index:
        fiscal = livedf.loc[iso, "fiscal_balance"]
        ca = livedf.loc[iso, "ca_balance"]
    if (pd.isna(fiscal) if fiscal is not None else True) or \
       (pd.isna(ca) if ca is not None else True):
        g = next((x for x in GP._INPUTS if x.iso == iso), None)
        if g is None:
            return None
        fiscal = g.fiscal_balance_path
        ca = g.goods_and_transfers + g.r_ext * g.niip_pct_gdp / 100.0
    if pd.isna(fiscal) or pd.isna(ca):
        return None
    return float(fiscal), float(ca)


def evaluate(iso: str, growth_target: float | None = None,
             fiscal_override: float | None = None) -> SAResult | None:
    """Run the SA required-private-balance test for one country."""
    c = lookup(iso)
    if c is None:
        return None
    vals = _inputs(iso)
    if vals is None:
        return None
    fiscal_now, ca_now = vals
    arch = c.primary
    g_trend = _TREND_GROWTH.get(arch, 2.0)
    # Default target is trend + aspiration premium so the import-leakage
    # mechanism actually bites (at exactly trend the test is static).
    g_target = growth_target if growth_target is not None else g_trend + ASPIRATION_PREMIUM
    m = _IMPORT_LEAKAGE.get(arch, 0.4)
    fiscal = fiscal_override if fiscal_override is not None else fiscal_now

    # Current private balance (identity)
    priv_now = -fiscal_now + ca_now
    # CA deteriorates as growth exceeds trend (import leakage)
    ca_target = ca_now - m * (g_target - g_trend)
    # Required private balance to be consistent with target growth + fiscal stance
    priv_req = -fiscal + ca_target
    shift = priv_req - priv_now

    # Credit-fuelled-deficit floor applies to everyone (it is always fragile).
    # Demand-draining-surplus ceiling only warns for domestic-demand-dependent
    # archetypes -- for entrepots/rentiers a big private surplus is normal.
    deficit_breach = priv_req < PRIV_BALANCE_FLOOR
    surplus_breach = (priv_req > PRIV_BALANCE_CEIL
                      and arch in _DOMESTIC_DEMAND_DEPENDENT)
    implausible = deficit_breach or surplus_breach
    if deficit_breach:
        direction = "credit-fuelled-deficit"
    elif surplus_breach:
        direction = "demand-draining-surplus"
    else:
        direction = "ok"

    return SAResult(
        iso=iso, country=c.name, archetype=arch,
        growth_target=round(g_target, 1),
        fiscal_balance=round(fiscal, 1),
        ca_now=round(ca_now, 1), ca_at_target=round(ca_target, 1),
        priv_balance_now=round(priv_now, 1),
        priv_balance_required=round(priv_req, 1),
        required_shift_pp=round(shift, 1),
        implausible=implausible, direction=direction,
    )


def panel() -> pd.DataFrame:
    """Run the SA test across all countries."""
    rows = []
    for c in COUNTRIES:
        r = evaluate(c.iso)
        if r is None:
            continue
        rows.append(vars(r))
    df = pd.DataFrame(rows).set_index("iso")
    return df.sort_values("priv_balance_required")


def scenarios(iso: str) -> pd.DataFrame:
    """
    SA scenario grid for one country: the three balances under
    baseline / fiscal consolidation (+2pp) / fiscal expansion (-2pp).
    Shows the required private balance the growth target implies in each.
    """
    vals = _inputs(iso)
    if vals is None:
        return pd.DataFrame()
    fiscal_now, _ = vals
    rows = []
    for label, fb in [("fiscal expansion (-2pp)", fiscal_now - 2.0),
                       ("baseline", fiscal_now),
                       ("fiscal consolidation (+2pp)", fiscal_now + 2.0)]:
        r = evaluate(iso, fiscal_override=fb)
        if r:
            rows.append({"scenario": label, "govt_balance": r.fiscal_balance,
                         "ca_at_target": r.ca_at_target,
                         "required_private_balance": r.priv_balance_required,
                         "implausible": r.implausible, "direction": r.direction})
    return pd.DataFrame(rows)


def implausibility_flag(iso: str) -> bool:
    """True if the country's trend-growth target requires an implausible private balance."""
    r = evaluate(iso)
    return bool(r and r.implausible)


def godley_2007_borrowing_test(horizon_years: int = 4) -> pd.DataFrame:
    """
    Godley's 2007 metric, generalised. In *Is There a Way Out of the Woods?*
    (Levy SA, Nov 2007) he converted the required private-balance path into
    the implied GROSS flow of net lending to households -- 'borrowing would
    have to reach 14 percent of GDP by 2010' -- and called it wildly
    implausible. The gross-flow restatement bites harder than the net
    balance because it is what the credit system must actually originate.

    We approximate: sustaining target growth for `horizon_years` requires the
    private balance to move to `priv_balance_required` and stay there; the
    cumulative required swing in the private NET position, plus the normal
    churn of gross origination (~3x the net flow, per flow-of-funds
    regularities), gives the implied gross borrowing flow at horizon end:

        gross_borrowing_required ~= 3 * max(0, -priv_balance_required)
                                    + max(0, -required_shift_pp) * horizon/4

    Flag when it exceeds 10% of GDP -- the level Godley treated as absurd.
    """
    rows = []
    for c in COUNTRIES:
        r = evaluate(c.iso)
        if r is None:
            continue
        net_deficit = max(0.0, -r.priv_balance_required)
        swing = max(0.0, -r.required_shift_pp) * horizon_years / 4.0
        gross = 3.0 * net_deficit + swing
        rows.append({"iso": c.iso, "country": c.name,
                     "priv_balance_required": r.priv_balance_required,
                     "required_shift_pp": r.required_shift_pp,
                     "gross_borrowing_required_pct_gdp": round(gross, 1),
                     "godley_2007_flag": gross > 10.0})
    return (pd.DataFrame(rows).set_index("iso")
            .sort_values("gross_borrowing_required_pct_gdp", ascending=False))
