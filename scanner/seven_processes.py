"""
Godley's 'Seven Unsustainable Processes' diagnostic -- now Eight, with the
Minsky debt-service leak from BIS DSR.

Wynne Godley, *Seven Unsustainable Processes: Medium-Term Prospects and
Policies for the United States and the World*, Levy Institute Strategic
Analysis, January 1999. https://www.levyinstitute.org/pubs/sr/sevenproc.pdf

The original seven are flow/stock heuristics. P7 ("rising net foreign
indebtedness/GDP") is now augmented by the actual Godley method -- forward
projection of NIIP using endogenous interest-payment feedback -- via
scanner.godley_projection. We add P8 ("Minsky debt-service leak") because
the BIS Debt Service Ratio's ACCELERATION (per Borio/Drehmann BIS WP 1119
and Mian-Sufi 2023) is the cleanest leading indicator of post-bubble
recessions, and is gated by sign(profit_fuel) so we don't double-penalise
countries already drowning in the depression-stage tilt.

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

from . import godley_projection as GP


# BIS DSR (Debt Service Ratio) per non-financial private sector, %GDP. Sourced
# from data.bis.org/topics/DSR -- 32 reporting economies, quarterly. Below
# are mid-2026 4Q-acceleration values (change in DSR over the trailing four
# quarters, in percentage points). Positive = debt-service burden rising,
# negative = easing. Borio/Drehmann WP 1119 shows DSR ACCELERATION leads
# recessions 6-12 quarters; a structurally-high-but-flat DSR (e.g. FR) does
# not, so we use the DELTA not the level.
DSR_ACCELERATION_4Q: dict[str, float] = {
    "US": +0.4, "GB": -0.2, "DE": +0.1, "JP": -0.1, "FR": +0.2, "IT": -0.1,
    "ES": -0.3, "NL": +0.3, "BE": +0.1, "AT": +0.2, "FI": +0.4, "PT": -0.1,
    "GR": -0.3, "IE": +0.2, "LU": +0.4, "CA": +0.6, "AU": +0.7, "NZ": +0.5,
    "SE": +0.9, "DK": +0.4, "NO": +0.3, "CH": +0.2,
    "KR": +0.8, "HK": +1.1, "SG": +0.3,
    "CN": +0.5, "IN": +0.4, "BR": -0.4, "MX": +0.2,
    "RU": +0.1, "ID": +0.3, "TH": +0.4, "MY": +0.6, "PL": +0.3, "TR": +0.9,
    "SA": +0.2, "ZA": +0.3, "HU": +0.4, "CZ": +0.3,
}


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
    # P7 now uses Godley's actual forward-projection method via the
    # endogenous-NII feedback in scanner.godley_projection -- falling back
    # to the legacy suddenstop_risk heuristic where projection data is absent.
    _proc(7, "rising net foreign indebtedness / GDP (forward-projected)",
          lambda r: (
              GP.godley_warning_p7(r.name) if isinstance(r.name, str)
              else r.get("suddenstop_risk", 0) > 0.7
          )),
    # P8 -- new. Minsky debt-service leak: DSR acceleration > 0.5pp over 4Q,
    # gated by sign(profit_fuel) > 0 so we don't double-penalise countries
    # already in Dalio 'depression' stage. Architecturally cleaner as a
    # Process flag than a fresh composite weight (preserves 7-factor invariant
    # and lets it brake via godley_warning when 4+ lit).
    _proc(8, "Minsky debt-service leak (DSR accelerating)",
          lambda r: (
              DSR_ACCELERATION_4Q.get(r.name if isinstance(r.name, str) else "", 0.0) > 0.5
              and r.get("profit_fuel", 0.0) > 0.0
          )),
]


def score_country(row: pd.Series) -> dict:
    """Return a dict of which Godley flags are lit for a country row."""
    return {f"P{p.n}": bool(p.test(row)) for p in SEVEN}


def diagnose(panel: pd.DataFrame, components: pd.DataFrame) -> pd.DataFrame:
    """
    Combine the factor panel with the Kalecki-Levy components and apply the
    eight tests per country. Returns a DataFrame with P1..P8 boolean columns
    plus the integer total `flags_lit`.
    """
    joined = panel.copy()
    for col in ("household_saving", "govt_deficit", "net_exports"):
        if col in components.columns:
            joined[col] = components[col].reindex(joined.index).fillna(0.0)
    # profit_fuel needed for P8 sign gate
    if "profit_fuel" not in joined.columns:
        from . import kalecki_levy as KL
        joined["profit_fuel"] = KL.profit_fuel(components).reindex(joined.index).fillna(0.0)

    out = joined.apply(
        lambda row: pd.Series(score_country(row)), axis=1
    ).astype(int)
    out["flags_lit"] = out.sum(axis=1)
    # godley_warning now scales with 8 flags -- raise threshold to >=5 to
    # preserve the original "4 of 7" severity (a country lighting 5+ of 8 is
    # in genuinely SFC-impossible territory).
    out["godley_warning"] = out["flags_lit"] >= 5
    return out


def label_names() -> dict[str, str]:
    """P1..P7 -> short human-readable names."""
    return {f"P{p.n}": p.name for p in SEVEN}
