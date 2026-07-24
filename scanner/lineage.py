"""
Cambridge-lineage diagnostics -- techniques from Godley's students & collaborators.

Three implementable techniques salvaged from the corpus sweep of Godley's
direct students and closest collaborators:

1. CRIPPS CLOSED-WORLD CONSTRAINT (Francis Cripps, CEPG -> Alphametrics CAM
   world model; Cripps & Izurieta, UN Global Policy Model).
   The world is a closed system: current-account balances must sum to zero
   across all countries. A panel whose GDP-weighted CA balances imply "the
   world runs a surplus with itself" (the famous exports-to-Mars problem --
   the real-world global discrepancy has at times exceeded $300bn) carries a
   measurement bias that should be reported, not ignored. Cripps' practice:
   allocate the discrepancy, never drop it.

2. SHAIKH INCREMENTAL RATE OF PROFIT (Anwar Shaikh, New School; Levy macro
   team 2000-05; *Measuring the Wealth of Nations*).
   IROP = change in gross profit / prior-period gross investment. Far more
   turning-point-sensitive than the average profit rate, because the margin
   on NEW capital leads the margin on the whole stock. We proxy it as
   profit_fuel (the Kalecki-Levy impulse = the change in profit sources)
   divided by the investment share of GDP: countries generating a large
   profit impulse off a SMALL investment base have a high marginal return
   on capital -- the classical bull signal; a large investment base
   producing no profit impulse is the classical overaccumulation signal.

3. MARTIN INFLATION-LOSS ADJUSTMENT (Bill Martin, CBR WP 384, 'An Augmented
   UK Private Expenditure Function').
   Measured household saving overstates TRUE saving under inflation, because
   part of measured saving merely replaces the inflation erosion of net
   financial assets: inflation_tax = pi * NFA/income. In high-inflation
   economies (TR, AR, EG, NG) the household sector can appear to be a big
   net saver while its real financial position is shrinking. Martin's data
   practice -- adjust income and saving for inflation losses on net
   financial assets -- materially changes the Godley read for the
   high-inflation cohort.

Also documented (not yet computed): the FIEBIGER GROSS-FLOWS CAVEAT
(real-world economics review 64, 2013): a stable NET sectoral balance can
mask ballooning GROSS balance sheets (the 2000s shadow-banking buildup); the
2007 crisis was better signalled by gross household borrowing flows than by
the net balance. Our net-balance diagnostics inherit this blind spot; the
NBFI leverage score and Minsky fragility index are partial compensations.

The April 2026 Levy Strategic Analysis (Zezza et al.) baseline -- 'future
growth will depend on an increase in private sector indebtedness' -- is the
Levy team's own statement of the same configuration our paradox-of-thrift
anomaly flags: with fiscal consolidating and the external deficit sticky,
the identity requires re-leveraging or stagnation.
"""

from __future__ import annotations

import pandas as pd

from . import kalecki_levy as KL
from .archetypes import COUNTRIES, lookup
from .sources import live


# --- 1. Cripps closed-world constraint ------------------------------------

# Approximate 2025 nominal GDP, USD trillions (IMF WEO). Used only as weights
# for the world adding-up check; precision to ~5% is ample for the purpose.
GDP_USD_TN: dict[str, float] = {
    "US": 29.2, "CN": 18.7, "DE": 4.7, "JP": 4.1, "IN": 4.1, "GB": 3.6,
    "FR": 3.2, "IT": 2.4, "BR": 2.2, "CA": 2.2, "RU": 2.1, "MX": 1.9,
    "AU": 1.8, "KR": 1.8, "ES": 1.7, "ID": 1.5, "NL": 1.2, "TR": 1.3,
    "SA": 1.1, "CH": 0.95, "PL": 0.9, "TW": 0.8, "BE": 0.65, "AR": 0.65,
    "SE": 0.62, "IE": 0.6, "TH": 0.55, "AT": 0.53, "NO": 0.5, "AE": 0.55,
    "SG": 0.55, "PH": 0.48, "VN": 0.47, "MY": 0.45, "DK": 0.42, "HK": 0.41,
    "CO": 0.4, "ZA": 0.4, "EG": 0.35, "PK": 0.34, "CL": 0.33, "FI": 0.3,
    "CZ": 0.35, "RO": 0.4, "PT": 0.3, "NZ": 0.26, "PE": 0.29, "GR": 0.25,
    "QA": 0.22, "HU": 0.23, "KZ": 0.29, "KW": 0.16, "NG": 0.2, "LK": 0.09,
    "LU": 0.09, "IR": 0.4, "VE": 0.1,
}


def world_ca_check() -> dict:
    """
    Cripps closed-world test: GDP-weighted sum of CA balances across the
    panel. Should be ~0 for a world-spanning panel; our 57 countries cover
    ~90% of world GDP so a modest residual is expected, but a LARGE implied
    world surplus/deficit marks either measurement bias (hidden surpluses --
    cf. Setser on China) or panel-coverage bias. Returns the implied world
    balance in USD bn and as % of panel GDP, plus the largest contributors.
    """
    from . import godley_projection as GP
    livedf = live.load_cached()
    gp = {g.iso: g for g in GP._INPUTS}
    contribs = {}
    total_gdp = 0.0
    for c in COUNTRIES:
        gdp = GDP_USD_TN.get(c.iso)
        if gdp is None:
            continue
        ca = None
        if livedf is not None and c.iso in livedf.index:
            v = livedf.loc[c.iso, "ca_balance"]
            if v is not None and v == v:
                ca = float(v)
        if ca is None:
            g = gp.get(c.iso)
            if g is None:
                continue
            ca = g.goods_and_transfers + g.r_ext * g.niip_pct_gdp / 100.0
        contribs[c.iso] = ca / 100.0 * gdp * 1000.0  # USD bn
        total_gdp += gdp
    world_bn = sum(contribs.values())
    top = sorted(contribs.items(), key=lambda kv: -abs(kv[1]))[:8]
    return {
        "implied_world_balance_usd_bn": round(world_bn, 0),
        "as_pct_panel_gdp": round(world_bn / (total_gdp * 1000.0) * 100.0, 2),
        "panel_gdp_usd_tn": round(total_gdp, 1),
        "largest_contributors_usd_bn": {k: round(v, 0) for k, v in top},
        "verdict": ("exports-to-Mars bias: panel implies the world runs a "
                    "surplus with itself" if world_bn > 300 else
                    "world implied in deficit with itself" if world_bn < -300
                    else "within normal global-discrepancy range"),
    }


# --- 2. Shaikh incremental rate of profit ---------------------------------

def shaikh_irop() -> pd.DataFrame:
    """
    Incremental rate of profit proxy: Kalecki-Levy profit impulse per unit of
    investment share. High = strong marginal return on new capital (classical
    bull); negative with a large investment base = overaccumulation.

    Uses live World Bank investment (%GDP) where cached, calibrated Kalecki-
    Levy investment component as fallback base.
    """
    comps = KL.components_df()
    pf = KL.profit_fuel(comps)
    livedf = live.load_cached()
    rows = []
    for iso in comps.index:
        inv_share = None
        if livedf is not None and iso in livedf.index:
            v = livedf.loc[iso, "investment"]
            if v is not None and v == v:
                inv_share = float(v)
        if inv_share is None or inv_share <= 5.0:
            inv_share = 22.0  # world-typical GFCF share fallback
        irop = float(pf.get(iso, 0.0)) / (inv_share / 100.0)
        rows.append({"iso": iso, "profit_impulse": round(float(pf.get(iso, 0.0)), 2),
                     "investment_share_gdp": round(inv_share, 1),
                     "irop_proxy": round(irop, 2)})
    df = pd.DataFrame(rows).set_index("iso")
    sd = df["irop_proxy"].std(ddof=0)
    df["irop_z"] = ((df["irop_proxy"] - df["irop_proxy"].mean()) / sd).clip(-3, 3).round(2)
    return df.sort_values("irop_proxy", ascending=False)


# --- 3. Martin inflation-loss adjustment ----------------------------------

# Mid-2026 CPI inflation, % YoY (IMF WEO / national prints; calibrated).
INFLATION: dict[str, float] = {
    "US": 2.9, "GB": 3.2, "DE": 2.2, "JP": 2.4, "KR": 2.2, "CN": 0.6,
    "BR": 4.6, "MX": 3.9, "IN": 4.5, "ID": 2.6, "PL": 4.0, "HU": 4.3,
    "CZ": 2.4, "RO": 5.2, "TR": 32.0, "EG": 14.0, "AR": 28.0, "PK": 8.5,
    "LK": 4.5, "NG": 22.0, "SA": 2.0, "AE": 2.1, "QA": 1.5, "KW": 2.6,
    "NO": 2.8, "KZ": 8.0, "CL": 3.8, "PE": 2.4, "CO": 5.0, "ZA": 4.4,
    "AU": 3.0, "CA": 2.4, "NZ": 2.7, "FR": 2.1, "IT": 1.7, "ES": 2.3,
    "PT": 2.2, "GR": 2.6, "NL": 2.7, "BE": 2.9, "AT": 2.8, "FI": 1.8,
    "DK": 1.9, "SE": 2.1, "CH": 1.1, "IE": 2.0, "LU": 2.2, "SG": 1.8,
    "HK": 1.9, "TW": 2.0, "VN": 3.5, "MY": 2.4, "TH": 1.1, "PH": 3.4,
    "RU": 8.0, "IR": 35.0, "VE": 60.0,
}


def martin_inflation_tax(iso: str) -> float | None:
    """
    Inflation erosion of household net financial assets, % of GDP per year:
        inflation_tax ~= pi * NFA/GDP
    NFA/GDP proxied from the V/YD wealth ratio (kalecki_levy.V_YD_ACTUAL)
    scaled by a 0.45 financial share of net wealth and a 0.6 YD/GDP ratio.
    Measured household saving overstates TRUE saving by roughly this amount:
    in Turkey (~32% inflation) the erosion is several % of GDP -- the
    household sector can look like a net saver while its real financial
    position shrinks.
    """
    pi = INFLATION.get(iso)
    v_yd = KL.V_YD_ACTUAL.get(iso)
    if pi is None or v_yd is None:
        return None
    nfa_gdp = v_yd * 0.45 * 0.6  # financial share x YD/GDP, as a ratio of GDP
    # pi is in %, nfa_gdp is a ratio of GDP -> product is in % of GDP
    return round(pi * nfa_gdp, 1)


def panel_inflation_adjustment() -> pd.DataFrame:
    """True-saving adjustment across the panel, largest erosion first."""
    rows = []
    for iso in INFLATION:
        tax = martin_inflation_tax(iso)
        if tax is None:
            continue
        rows.append({"iso": iso, "inflation_pct": INFLATION[iso],
                     "inflation_tax_pct_gdp": tax,
                     "true_saving_overstated": tax > 2.0})
    return (pd.DataFrame(rows).set_index("iso")
            .sort_values("inflation_tax_pct_gdp", ascending=False))
