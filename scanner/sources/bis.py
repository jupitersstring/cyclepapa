"""
BIS data adapter -- live-wiring path documented; falls back to calibration.

BIS publishes via the unified SDMX endpoint at stats.bis.org. Three datasets
are load-bearing for the scanner:

    1. BIS_LBS_DISS -- Locational Banking Statistics, the FX/break-adjusted
       cross-border claim flows that ARE Godley's Process #2.

    2. WS_CREDIT_GAP -- Total Credit to Private Non-Financial Sector + the
       credit-to-GDP gap (Borio-Drehmann early-warning indicator).

    3. WS_DSR_PUB -- Debt Service Ratio for the private non-financial sector,
       32 economies, quarterly. Powers seven_processes.P8.

Endpoint pattern (verified Q2 2026):

    https://stats.bis.org/api/v1/data/BIS,{DATAFLOW},1.0/{KEY}
        ?format=csv&detail=dataonly

The key has 12 dimensions for LBS (FREQ, L_MEASURE, L_POSITION, L_INSTR,
L_DENOM, L_CURR_TYPE, L_PARENT_CTY, L_REP_BANK_TYPE, L_REP_CTY, L_CP_SECTOR,
L_CP_COUNTRY, L_POS_TYPE). Counterparty country is L_CP_COUNTRY (position 11).
Use wildcards for non-essential slots.

Rate limit: ~1 req/sec. Cache locally.

The verifier flagged that BIS LBS is cross-border only; G7 economies need
a domestic-credit complement from WS_CREDIT_GAP. The scanner's
`credit_impulse` should be renamed `cross_border_impulse` if/when wired,
or interpreted as a partial proxy.
"""

from __future__ import annotations

import pandas as pd


# Calibrated mid-2026 cross-border credit YoY% change (4Q rolling, FX-adjusted).
# These are the same values data.py uses for credit_impulse on Tier-1 rows;
# duplicating here so future live wiring has a sanity-check ladder.
_LBS_FALLBACK: dict[str, float] = {
    "BR": 2.4, "SA": 1.6, "DE": 0.6, "PL": 2.6, "MX": 1.2, "JP": 0.4,
    "KR": 0.9, "IN": 0.2, "US": 0.8, "CN": -1.8, "GB": -0.4, "TR": 1.8,
    "EG": 0.6, "AR": 0.4,
    # Calibrated for remaining panel
    "AU": 0.3, "CA": 0.4, "NZ": 0.2, "FR": -0.2, "IT": 0.1, "ES": 0.7,
    "GR": 0.9, "PT": 0.6, "NL": 0.4, "BE": 0.3, "AT": 0.3, "FI": 0.2,
    "DK": 0.4, "SE": 0.5, "CH": 0.2, "IE": 0.5, "LU": 0.2, "SG": 0.6,
    "HK": -0.5, "TW": 1.0, "VN": 1.1, "MY": 0.7, "TH": 0.5, "ID": 0.8,
    "PH": 0.6, "HU": 1.5, "CZ": 1.0, "RO": 0.9, "AE": 1.2, "QA": 1.0,
    "KW": 0.7, "NO": 0.3, "KZ": 0.6, "CL": 0.9, "PE": 0.8, "CO": 0.7,
    "NG": 0.4, "ZA": 0.5, "PK": 0.3, "LK": 0.2,
    "RU": 0.0, "IR": 0.0, "VE": 0.0,
}


def bis_lbs_cross_border_yoy(iso: str) -> float | None:
    """
    Cross-border bank-credit YoY change, % (FX-adjusted, 4Q rolling).

    LIVE: query BIS SDMX at
        /data/BIS,BIS_LBS_DISS,1.0/Q.F.....A.{ISO}.A...
        ?format=csv&startPeriod=2024-Q1
    Then compute (4Q sum at t) / (4Q sum at t-4Q) - 1.

    CURRENT: returns calibrated values from _LBS_FALLBACK.
    """
    return _LBS_FALLBACK.get(iso)


def bis_dsr_acceleration_4q(iso: str) -> float | None:
    """
    BIS Debt Service Ratio acceleration over trailing 4Q, in pp.

    LIVE: query /data/BIS,WS_DSR_PUB,1.0/Q.{ISO}.P (P = total private
    non-financial sector). Compute first-difference over 4Q.

    CURRENT: returns calibrated values from seven_processes.DSR_ACCELERATION_4Q.
    """
    from .. import seven_processes as SP
    return SP.DSR_ACCELERATION_4Q.get(iso)


def panel_lbs() -> pd.DataFrame:
    """Return the full cross-border credit panel."""
    return pd.DataFrame(
        [(iso, v) for iso, v in _LBS_FALLBACK.items()],
        columns=["iso", "lbs_yoy_pct"],
    ).set_index("iso")
