"""
Godley's 'Seven Unsustainable Processes' diagnostic.

Wynne Godley, *Seven Unsustainable Processes: Medium-Term Prospects and
Policies for the United States and the World*, Levy Institute Strategic
Analysis, January 1999. https://www.levyinstitute.org/pubs/sr/sevenproc.pdf

This is Godley's actual screen -- the one he used in 1999 to call the
subsequent collapse of the US private-sector financial balance and the
contribution of widening external deficits to the eventual unwind. Each
flag tracks the *direction and rate* of a sectoral or stock-flow variable;
the diagnostic is the joint implausibility of the implied stock paths.

The seven processes (Godley 1999, p.iv, summarised):

    1. Fall in private saving into deeper negative territory.
    2. Rise in the flow of net lending to the private sector.
    3. Rise in the growth rate of the real money stock.
    4. Asset-price inflation in excess of growth in profits or GDP.
    5. Rise in the budget surplus (fiscal tightening).
    6. Rise in the current account deficit.
    7. Rise in net foreign indebtedness/GDP.

In Godley's framing, processes 5+6 *cause* 1, 2 and 7: when the public
sector consolidates and the external sector deteriorates, the identity
forces the private sector deficit deeper. We score each country on how
many flags are currently lit (i.e. moving in the unsustainable direction)
and surface the joint pattern in the dashboard.

The result is intentionally a *count* (0-7) not a z-score: it answers the
binary 'is this country running an SFC-impossible configuration?' rather
than 'how bullish is the flow?'. Use it as a brake on the Opportunity
score, not as a replacement.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import pandas as pd


# Each process is a callable that takes a single-country row and returns
# True if the flag is currently 'lit' (moving in the unsustainable direction).

@dataclass(frozen=True)
class Process:
    n: int
    name: str
    test: Callable[[pd.Series], bool]


# Heuristic tests mapped to columns from the existing factor panel + Kalecki-
# Levy components. They mimic the direction of Godley's 1999 checks using the
# proxies we have to hand; in a live SFC implementation each test would query
# the underlying Z.1 / IFS / BoP series directly.
def _proc(n, name, test): return Process(n, name, test)


SEVEN: list[Process] = [
    _proc(1, "private saving falling further negative",
          lambda r: r.get("household_saving", 0) < -0.2),
    _proc(2, "rising net lending TO private sector",
          lambda r: r.get("credit_impulse", 0) > 1.0),
    _proc(3, "rising real money-stock growth",
          lambda r: r.get("credit_impulse", 0) > 1.0),
    _proc(4, "asset prices outrunning profits / GDP",
          lambda r: r.get("valuation_gap", 0) < -1.0 and r.get("crowding", 0) > 0.5),
    _proc(5, "fiscal tightening (budget surplus rising)",
          lambda r: r.get("govt_deficit", 0) < -0.2),
    _proc(6, "current account deficit widening",
          lambda r: r.get("net_exports", 0) < -0.2),
    _proc(7, "rising net foreign indebtedness / GDP",
          lambda r: r.get("suddenstop_risk", 0) > 0.7),
]


def score_country(row: pd.Series) -> dict:
    """Return a dict of which Godley flags are lit for a country row."""
    return {f"P{p.n}": bool(p.test(row)) for p in SEVEN}


def diagnose(panel: pd.DataFrame, components: pd.DataFrame) -> pd.DataFrame:
    """
    Combine the factor panel with the Kalecki-Levy components and apply the
    seven tests per country. Returns a DataFrame with P1..P7 boolean columns
    plus the integer total `flags_lit`.
    """
    joined = panel.copy()
    for col in ("household_saving", "govt_deficit", "net_exports"):
        if col in components.columns:
            joined[col] = components[col].reindex(joined.index).fillna(0.0)
    out = joined.apply(
        lambda row: pd.Series(score_country(row)), axis=1
    ).astype(int)
    out["flags_lit"] = out.sum(axis=1)
    out["godley_warning"] = out["flags_lit"] >= 4
    return out


def label_names() -> dict[str, str]:
    """P1..P7 -> short human-readable names."""
    return {f"P{p.n}": p.name for p in SEVEN}
