"""
Household distribution mask -- the pre-2007 pattern detector.

The aggregate household financial balance can conceal opposite behavior at
the two ends of the distribution. In the US 2003-2007, the AGGREGATE
household balance looked only mildly negative while the BOTTOM ~80% ran a
deep, debt-financed deficit -- the top quintile's saving masked it. Zezza
('US Growth, the Housing Market, and the Distribution of Income', JPKE
2008-ish) modelled exactly this top-5%-vs-rest split in the Godley US model;
the modern Levy work (the distributional Financial Accounts strand) and
Fiebiger's gross-flows critique (rwer 64, 2013) make the same point: NET
sectoral aggregates hide GROSS distributional fragility.

The mask indicator:

    bottom80_balance ~= aggregate_hh_balance - top20_saving_contribution

where the top-20% saving contribution is estimated from the top-decile
income share (higher concentration => more of the aggregate saving is done
at the top => the masked bottom-80 position is weaker).

    top20_saving = aggregate_hh_saving_flow * top20_saving_share
    top20_saving_share ~= clip(0.5 + (top10_income_share - 0.30) * 2.0, 0.5, 0.95)

Calibration: top-10% income shares from WID.world (World Inequality
Database, 2022-23 vintages). The household aggregate balance comes from the
same live/calibrated inputs the SFC-inconsistency check uses.

MASK FLAG fires when: aggregate household balance >= 0 (looks safe) but the
implied bottom-80 balance < -1% of GDP (the fragile majority is deficit-
spending behind the aggregate).

LIVE-WIRING PATH:
  US: Fed Distributional Financial Accounts (DFA), quarterly CSV,
      https://www.federalreserve.gov/releases/z1/dataviz/dfa/ -- direct
      download, no key. Gives net worth AND its change by percentile group.
  EZ: ECB Distributional Wealth Accounts (DWA), quarterly, launched Jan 2024,
      via ECB Data Portal -- net wealth by decile for each euro country.
  Other: WID.world API for income/wealth shares (annual).
"""

from __future__ import annotations

import pandas as pd

from .archetypes import COUNTRIES, lookup
from .sources import eurostat as ES


# Top-10% pre-tax income share (WID.world, ~2022-23). Higher = more of
# aggregate household saving is done at the top.
TOP10_INCOME_SHARE: dict[str, float] = {
    "US": 0.455, "GB": 0.360, "DE": 0.375, "JP": 0.445, "KR": 0.465,
    "CN": 0.435, "BR": 0.585, "MX": 0.575, "IN": 0.575, "ID": 0.480,
    "PL": 0.375, "HU": 0.345, "CZ": 0.315, "RO": 0.395, "TR": 0.545,
    "EG": 0.485, "AR": 0.425, "PK": 0.425, "LK": 0.455, "NG": 0.425,
    "SA": 0.540, "AE": 0.505, "QA": 0.510, "KW": 0.510, "NO": 0.295,
    "KZ": 0.395, "CL": 0.585, "PE": 0.560, "CO": 0.545, "ZA": 0.650,
    "AU": 0.335, "CA": 0.395, "NZ": 0.345, "FR": 0.325, "IT": 0.325,
    "ES": 0.345, "PT": 0.365, "GR": 0.355, "NL": 0.310, "BE": 0.320,
    "AT": 0.345, "FI": 0.330, "DK": 0.305, "SE": 0.305, "CH": 0.335,
    "IE": 0.355, "LU": 0.340, "SG": 0.445, "HK": 0.475, "TW": 0.385,
    "VN": 0.425, "MY": 0.475, "TH": 0.515, "PH": 0.455, "RU": 0.465,
    "IR": 0.475, "VE": 0.435,
}


def _hh_balance(iso: str) -> float | None:
    """Aggregate household net-lending %GDP: Eurostat/ONS calibration where
    available, else a share of the implied private balance."""
    v = ES.HH_NL_PCT_GDP.get(iso)
    if v is not None:
        return float(v)
    # Fallback: households typically carry ~70% of the private balance
    from . import godley_projection as GP
    g = next((x for x in GP._INPUTS if x.iso == iso), None)
    if g is None:
        return None
    priv = -(g.fiscal_balance_path) + (g.goods_and_transfers
                                       + g.r_ext * g.niip_pct_gdp / 100.0)
    return round(0.7 * priv, 1)


def top20_saving_share(iso: str) -> float | None:
    """Share of aggregate household saving done by the top quintile."""
    s = TOP10_INCOME_SHARE.get(iso)
    if s is None:
        return None
    return max(0.5, min(0.95, 0.5 + (s - 0.30) * 2.0))


def evaluate(iso: str) -> dict | None:
    """
    The mask decomposition for one country.

    The key point is that the top quintile's saving can EXCEED the aggregate
    balance -- which is exactly when the bottom-80 is in deficit behind a
    safe-looking aggregate. We estimate the gross household saving flow as
    the aggregate balance plus a bottom-dissaving flow that scales with
    inequality (high-concentration economies have more debt-financed
    consumption at the bottom -- the Zezza/DFA empirical pattern):

        S_gross  = agg + 12 * (top10_share - 0.28)
        top20    = share * S_gross
        bottom80 = agg - top20
    """
    agg = _hh_balance(iso)
    share = top20_saving_share(iso)
    s10 = TOP10_INCOME_SHARE.get(iso)
    if agg is None or share is None or s10 is None:
        return None
    dissave_flow = max(0.0, 12.0 * (s10 - 0.28))
    s_gross = agg + dissave_flow
    top20 = share * s_gross
    bottom80 = agg - top20
    masked = agg >= 0 and bottom80 < -1.0
    return {"iso": iso,
            "aggregate_hh_balance": round(agg, 1),
            "top20_share_of_saving": round(share, 2),
            "top20_balance": round(top20, 1),
            "bottom80_balance": round(bottom80, 1),
            "mask_flag": masked}


def panel() -> pd.DataFrame:
    """The distribution mask across the panel, weakest bottom-80 first."""
    rows = [evaluate(c.iso) for c in COUNTRIES]
    rows = [r for r in rows if r]
    return (pd.DataFrame(rows).set_index("iso")
            .sort_values("bottom80_balance"))


def fragile_majority() -> pd.DataFrame:
    """Countries where the fragile-majority pattern is present: bottom-80
    in or near deficit while the aggregate looks fine. High-inequality
    economies dominate by construction -- the point is the RANKING and the
    size of the wedge between the aggregate and the bottom-80 reading."""
    p = panel()
    return p[p["bottom80_balance"] < 0.5]
