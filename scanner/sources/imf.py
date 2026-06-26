"""
IMF adapter -- WEO + External Sector Report + IFS BoP.

The IMF data ecosystem has three relevant endpoints for the scanner:

    1. WEO via datamapper API: a flat-file endpoint at
         https://www.imf.org/external/datamapper/api/v1/{INDICATOR}/{ISO}
       returning JSON {Years -> Values}. Used by godley_projection for
       fiscal-balance + growth projections.

    2. IFS BoP via SDMX:
         https://dataservices.imf.org/REST/SDMX_JSON.svc/CompactData/BOP/
       Quarterly current account, financial account, NIIP per country.

    3. External Sector Report (annual PDF + Excel tables) -- staff-assessed
       CA_GAP / NIIP_NORM. Annual, machine-unreadable (the verifier
       correctly rejected the SDMX path for this; only the PDF tables are
       available). Manual annual update is the realistic path.

Key indicators used by godley_projection.py:

    GGXCNL_NGDP  General gov net lending (% GDP)
    BCA_NGDPD    Current account (% GDP)
    BCAS_NGDPD   Current account (% GDP, alt definition)
    NGDP_RPCH    Real GDP growth (% YoY)
    NGDPDPC      GDP per capita ($)
"""

from __future__ import annotations

import pandas as pd


# Mid-2026 calibration for IMF WEO indicators we use.
# These are the same values godley_projection._INPUTS uses for the projection;
# this module is the documented live-replacement path.
WEO_FISCAL_BALANCE_5Y: dict[str, float] = {
    "US": -6.5, "GB": -4.0, "DE": -2.5, "JP": -5.0, "KR": -2.5, "CN": -7.0,
    "BR": -5.5, "MX": -3.5, "IN": -4.3, "ID": -2.5, "PL": -5.0, "HU": -4.5,
    "CZ": -2.5, "RO": -7.0, "TR": -4.0, "EG": -6.0, "AR": -1.0, "PK": -7.0,
    "LK": -5.0, "NG": -4.0, "SA": -2.5, "AE": +1.0, "QA": +5.0, "KW": +3.0,
    "NO": +10.0, "KZ": -2.0, "CL": -2.0, "PE": -2.0, "CO": -4.5, "ZA": -5.0,
    "AU": -2.0, "CA": -1.5, "NZ": -2.0, "FR": -5.5, "IT": -3.5, "ES": -3.0,
    "PT": -2.0, "GR": -1.0, "NL": -2.0, "BE": -4.0, "AT": -3.0, "FI": -3.5,
    "DK": +1.0, "SE": -1.0, "CH": +0.5, "IE": +1.5, "LU": +1.0, "SG": +0.5,
    "HK": +1.5, "TW": +0.0, "VN": -3.0, "MY": -4.0, "TH": -3.5, "PH": -5.5,
    "RU": +0.0, "IR": -3.0, "VE": -8.0,
}


def weo_indicator(indicator: str, iso: str) -> float | None:
    """
    Live: datamapper API pull.

        import requests
        url = f"https://www.imf.org/external/datamapper/api/v1/{indicator}/{iso}"
        data = requests.get(url).json()
        years = data['values'][indicator][iso]
        return float(years[max(years.keys())])

    Current: pulls from calibration dict if indicator is recognised.
    """
    if indicator == "GGXCNL_NGDP":
        return WEO_FISCAL_BALANCE_5Y.get(iso)
    return None
