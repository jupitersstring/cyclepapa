"""
Minsky Financial Fragility Index (after Tymoigne, Levy WP 654, 2011).

Hyman Minsky (Levy Distinguished Scholar 1990-96) classified financing units
by the relation between their cash flows and their debt obligations:

    HEDGE        operating cash flow covers BOTH interest AND principal,
                 in every period. Self-financing; robust.
    SPECULATIVE  cash flow covers interest but NOT principal -- the unit must
                 continually roll over (refinance) its debt.
    PONZI        cash flow covers NEITHER interest nor principal -- debt must
                 grow, or assets be sold, merely to stay current.

Minsky's core insight (the 'financial instability hypothesis', Levy WP 74,
1992): tranquil, profitable, low-default periods ENDOGENOUSLY push the mix of
units toward speculative and Ponzi finance. Stability breeds fragility.

Tymoigne (Levy WP 654, 'Measuring Macroprudential Risk: Financial Fragility
Indexes') operationalised this into a continuous sector index by weighting:

    fragility = (0.0 * hedge_share) + (0.5 * speculative_share) + (1.0 * ponzi_share)

yielding a 0->1 score (higher = more Ponzi-weighted = more fragile). Applied to
US residential housing, the index flagged Ponzi-finance DOMINANCE from ~2004
to 2007 -- ahead of the crash. WP 896 (Torres Filho et al.) showed firm-level
implementation on Brazilian electricity companies.

This module ports that scheme to the country panel. We approximate each
country's private-sector financing posture from observable macro proxies:

    - Debt-service ratio (BIS DSR) acceleration  -> rising = toward Ponzi
    - Credit impulse                              -> high & rising = speculative+
    - Tobin q vs target                           -> >>1 = asset-price-validated
                                                     (Ponzi tell: debt serviced
                                                      by asset appreciation)
    - Household saving direction                  -> dis-saving into debt = Ponzi
    - Real rate vs growth (r - g)                 -> r > g = principal can't be
                                                     outgrown = structurally
                                                     speculative-or-worse

The result is a 0-1 fragility index per country and a hedge/speculative/Ponzi
regime label. It is a STOCK-of-fragility read, complementary to (not a
substitute for) the Seven-Processes flow diagnostic.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from . import seven_processes as SP
from . import tobin_q as TQ
from . import regime as R


# Tymoigne WP 654 weights.
W_HEDGE, W_SPECULATIVE, W_PONZI = 0.0, 0.5, 1.0


@dataclass
class FragilityInputs:
    """
    Per-country proxies for the Minsky classification, mid-2026.
    All in their natural units; combined into shares below.

    `r_minus_g`: real policy rate minus real GDP growth. When r > g the
        principal cannot be outgrown -- the structural mark of speculative-
        or-Ponzi finance at the sovereign+private level (Blanchard 2019 meets
        Minsky).
    `asset_dependence`: 0-1, how much debt service relies on asset
        appreciation rather than income (high Tobin q + high credit = high).
    `dissaving`: household moving INTO deficit (negative saving impulse).
    """
    iso: str
    r_minus_g: float
    asset_dependence: float
    dissaving: float
    note: str = ""


# Mid-2026 calibration. r_minus_g from policy-rate minus real-growth prints;
# asset_dependence and dissaving from the existing factor panel + Tobin q.
_INPUTS: dict[str, FragilityInputs] = {
    "US": FragilityInputs("US", r_minus_g=+1.8, asset_dependence=0.75, dissaving=0.3,
                          note="wealth-effect consumption; q 1.14; late cycle"),
    "GB": FragilityInputs("GB", +1.2, 0.55, -0.4, note="HH fled to saving; LDI fragility separate"),
    "DE": FragilityInputs("DE", -0.5, 0.20, 0.0, note="low leverage, cheap q, fiscal pivot"),
    "JP": FragilityInputs("JP", -1.5, 0.45, -0.2, note="creditor; q 1.21 but income-backed"),
    "KR": FragilityInputs("KR", +0.5, 0.55, 0.1, note="RE-PF + household debt high"),
    "CN": FragilityInputs("CN", -0.5, 0.70, 0.6, note="property Ponzi unwinding; developer leg"),
    "BR": FragilityInputs("BR", +5.5, 0.25, -0.3, note="punishing real rate; but low asset-dependence"),
    "MX": FragilityInputs("MX", +3.5, 0.20, 0.1, note="high real rate, deep value q 0.48"),
    "IN": FragilityInputs("IN", +1.5, 0.65, 0.2, note="q 1.31 bubble; valuation-validated"),
    "AU": FragilityInputs("AU", +0.8, 0.80, 0.2, note="household debt at extreme; housing Ponzi tell"),
    "CA": FragilityInputs("CA", +0.6, 0.78, 0.1, note="household debt highest in G7; housing"),
    "NZ": FragilityInputs("NZ", +0.7, 0.75, 0.2, note="housing-credit dominated"),
    "TR": FragilityInputs("TR", -3.0, 0.40, 0.0, note="FX-mismatch; DSR accelerating"),
    "ZA": FragilityInputs("ZA", +2.0, 0.45, 0.0),
    "PL": FragilityInputs("PL", +1.5, 0.30, 0.1, note="credit hot but low asset-dependence"),
    "HK": FragilityInputs("HK", +1.0, 0.90, 0.3, note="property finance leverage extreme"),
    "SE": FragilityInputs("SE", +0.5, 0.70, 0.1, note="housing-credit excess"),
    "CH": FragilityInputs("CH", -0.5, 0.65, 0.0),
    "SA": FragilityInputs("SA", -0.5, 0.30, -0.1), "AE": FragilityInputs("AE", -0.5, 0.35, 0.0),
    "ID": FragilityInputs("ID", +2.0, 0.25, 0.0), "TH": FragilityInputs("TH", +0.5, 0.40, 0.1),
    "MY": FragilityInputs("MY", +0.5, 0.45, 0.1), "PH": FragilityInputs("PH", +1.5, 0.30, 0.0),
    "VN": FragilityInputs("VN", +1.0, 0.50, 0.0), "FR": FragilityInputs("FR", +0.5, 0.45, 0.0),
    "IT": FragilityInputs("IT", +0.5, 0.30, 0.0), "ES": FragilityInputs("ES", +0.5, 0.35, -0.1),
    "GR": FragilityInputs("GR", +1.0, 0.30, -0.1), "PT": FragilityInputs("PT", +0.5, 0.40, -0.1),
    "EG": FragilityInputs("EG", -1.0, 0.30, 0.0), "AR": FragilityInputs("AR", +3.0, 0.20, -0.2),
    "PK": FragilityInputs("PK", +1.0, 0.25, 0.0), "LK": FragilityInputs("LK", +0.5, 0.25, -0.1),
    "NG": FragilityInputs("NG", -1.0, 0.20, 0.0), "RU": FragilityInputs("RU", +1.0, 0.35, 0.0),
    "NL": FragilityInputs("NL", -0.3, 0.70, 0.0), "BE": FragilityInputs("BE", +0.3, 0.45, 0.0),
    "AT": FragilityInputs("AT", +0.3, 0.45, 0.0), "FI": FragilityInputs("FI", +0.3, 0.45, 0.0),
    "DK": FragilityInputs("DK", 0.0, 0.65, 0.0), "NO": FragilityInputs("NO", -0.5, 0.40, 0.0),
    "IE": FragilityInputs("IE", -0.5, 0.55, 0.0), "SG": FragilityInputs("SG", 0.0, 0.65, 0.0),
    "TW": FragilityInputs("TW", +0.5, 0.60, 0.0), "QA": FragilityInputs("QA", -0.5, 0.35, 0.0),
    "KW": FragilityInputs("KW", -0.5, 0.30, 0.0), "CL": FragilityInputs("CL", +1.0, 0.45, 0.0),
    "PE": FragilityInputs("PE", +1.0, 0.35, 0.0), "CO": FragilityInputs("CO", +2.0, 0.30, 0.0),
    "HU": FragilityInputs("HU", +1.0, 0.35, 0.1), "CZ": FragilityInputs("CZ", +0.5, 0.40, 0.0),
    "RO": FragilityInputs("RO", +1.5, 0.30, 0.1), "KZ": FragilityInputs("KZ", +0.5, 0.30, 0.0),
    "IR": FragilityInputs("IR", 0.0, 0.25, 0.0), "VE": FragilityInputs("VE", +5.0, 0.20, 0.0),
    "LU": FragilityInputs("LU", -0.3, 0.50, 0.0),
}


def _shares(inp: FragilityInputs) -> tuple[float, float, float]:
    """
    Map proxies to (hedge, speculative, ponzi) shares summing to 1.

    Logic:
      - Start everyone mostly-hedge.
      - r > g (principal can't be outgrown) shifts hedge -> speculative.
      - asset_dependence (debt serviced by appreciation) shifts toward Ponzi.
      - dissaving (household borrowing to spend) shifts toward Ponzi.
      - DSR acceleration (Minsky's own dynamic) shifts toward Ponzi.
    """
    dsr_accel = SP.DSR_ACCELERATION_4Q.get(inp.iso, 0.0)

    # Speculative pressure: r-g gap (only the positive part) + moderate credit
    spec = max(0.0, inp.r_minus_g) * 0.06
    # Ponzi pressure: asset-dependence, dissaving, DSR acceleration
    ponzi = (inp.asset_dependence * 0.45
             + max(0.0, inp.dissaving) * 0.30
             + max(0.0, dsr_accel) * 0.25)
    ponzi = min(ponzi, 0.85)
    spec = min(spec, 0.85 - ponzi if ponzi < 0.85 else 0.0)
    hedge = max(0.0, 1.0 - spec - ponzi)
    # renormalise
    total = hedge + spec + ponzi
    return hedge / total, spec / total, ponzi / total


def fragility_index(iso: str) -> float | None:
    """Tymoigne 0-1 fragility score for one country."""
    inp = _INPUTS.get(iso)
    if inp is None:
        return None
    h, s, p = _shares(inp)
    return W_HEDGE * h + W_SPECULATIVE * s + W_PONZI * p


def regime_label(iso: str) -> str:
    """Dominant Minsky regime for one country."""
    inp = _INPUTS.get(iso)
    if inp is None:
        return "unknown"
    h, s, p = _shares(inp)
    if p >= 0.40:
        return "ponzi"
    if s + p >= 0.45:
        return "speculative"
    return "hedge"


def panel() -> pd.DataFrame:
    """Full fragility panel: shares, index, regime label."""
    rows = []
    for iso, inp in _INPUTS.items():
        h, s, p = _shares(inp)
        rows.append({
            "iso": iso,
            "hedge": round(h, 3),
            "speculative": round(s, 3),
            "ponzi": round(p, 3),
            "fragility": round(fragility_index(iso), 3),
            "minsky_regime": regime_label(iso),
            "note": inp.note,
        })
    return pd.DataFrame(rows).set_index("iso").sort_values("fragility", ascending=False)
