"""
The Godley System -- the Bard/Levy corpus reduced to five logical levels.

The scanner grew into 24 modules; this organises them into the principled
hierarchy Godley's own work follows, so a reader can understand a country by
walking down it. Each level answers one question and feeds the next.

  1 IDENTITY   How do the three balances sit? Private + Government + External
               = 0 by construction (Godley & Cripps, New Cambridge). This is
               the frame -- every economy IS a configuration of these three.

  2 FLOWS      Is purchasing power ENTERING private balance sheets? The
               Kalecki-Levy profit identity: profits = investment + govt
               deficit + net exports + dividends - household saving. The flow
               (and its impulse) is what funds spending, profits and prices.

  3 STOCKS     Do the implied stock paths hold or explode? Flows accumulate
               into debt/income and NIIP/GDP; Godley's Seven Unsustainable
               Processes and the medium-term projection test whether the
               configuration can persist (stock-flow norms, Godley-Lavoie).

  4 FRAGILITY  Is the financing hedge, speculative, or Ponzi? As the cycle
               matures, stability breeds fragility (Minsky; Tymoigne WP 654).

  5 REGIME     Given all four: bull or bear, where in the debt cycle, and at
               which horizon (Levy Strategic-Analysis synthesis).

`godley_view(scored_row, balances)` assembles the five levels for one country,
each as a (label, value, plain-reading) triple -- the single structure the
dashboard and the CLI both render.
"""

from __future__ import annotations

import pandas as pd

from . import seven_processes as SP
from . import godley_projection as GP
from . import minsky_fragility as MF


LEVELS = ["Identity", "Flows", "Stocks", "Fragility", "Regime"]


def _identity_reading(b: dict) -> str:
    if not b:
        return "balances unavailable"
    priv, gov, ext = b.get("private", 0), b.get("government", 0), b.get("foreign", 0)
    parts = []
    parts.append(f"govt {'deficit' if gov < 0 else 'surplus'} {gov:+.0f}")
    parts.append(f"private {'surplus' if priv >= 0 else 'deficit'} {priv:+.0f}")
    parts.append(f"external {ext:+.0f}")
    return " · ".join(parts) + " (=0)"


def _flows_reading(profit_fuel: float) -> str:
    if profit_fuel > 1.0:
        return "fuel surging into private sector"
    if profit_fuel > 0.3:
        return "fuel rising"
    if profit_fuel < -0.5:
        return "profit engine draining"
    return "fuel flat"


def _stocks_reading(iso: str) -> tuple[float, str]:
    """Godley sustainability: NIIP projection + seven-process flag count."""
    unsust = GP.unsustainability_score(iso)          # 0 = fine, >1 = explosive
    if unsust > 1.0:
        return unsust, "stock path explosive — unsustainable"
    if unsust > 0.3:
        return unsust, "stock path deteriorating"
    return unsust, "stock path sustainable"


def _fragility_reading(iso: str) -> tuple[float, str]:
    f = MF.fragility_index(iso) or 0.0
    reg = MF.regime_label(iso)
    return f, {"hedge": "income-financed (robust)",
               "speculative": "rollover-dependent",
               "ponzi": "appreciation-financed (fragile)"}.get(reg, "")


def godley_view(row: pd.Series, balances: dict) -> dict:
    """Assemble the five Godley levels for one country."""
    iso = row.name
    pf = float(row.get("profit_fuel", 0.0) or 0.0)
    unsust, stock_txt = _stocks_reading(iso)
    frag, frag_txt = _fragility_reading(iso)
    flags = SP.diagnose(
        pd.DataFrame([row]).set_index(pd.Index([iso])),
        __import__("scanner.kalecki_levy", fromlist=["components_df"]).components_df()
    )
    lit = int(flags["flags_lit"].iloc[0]) if len(flags) else 0
    return {
        "identity": {"label": "3 balances → 0", "reading": _identity_reading(balances),
                     "balances": balances},
        "flows": {"label": "profit fuel", "value": round(pf, 2),
                  "reading": _flows_reading(pf)},
        "stocks": {"label": "sustainability", "value": round(unsust, 2),
                   "flags_lit": lit, "reading": stock_txt},
        "fragility": {"label": "financing", "value": round(frag, 2),
                      "reading": frag_txt},
        "regime": {"label": "verdict", "regime": row.get("regime"),
                   "stage": row.get("fine_stage"),
                   "clock": round(float(row.get("stage_position") or 0)),
                   "opportunity": round(float(row.get("opportunity", 0)), 2)},
    }
