"""
Default dataset (June 2026) and loader hooks.

Each country carries the six raw factor inputs the composite consumes. Values
are sourced from the public releases gathered in the research phase (BIS LBS
Q4 2025, IMF Fiscal Monitor Apr 2026, ECB/Eurostat & ONS Q4 2025 sector
accounts, PBoC Mar 2026, IIF Apr 2026, plus valuation/positioning/rate prints).

Each factor is stored on its NATURAL scale with a documented direction; the
composite z-scores them against the cross-section before weighting, so the raw
units here never enter the score directly. Where a hard number was unavailable
a calibrated ordinal estimate is used and flagged with `estimated=True`.

To go live, replace `default_panel()` with loaders that pull:
    credit_impulse      <- BIS LBS cross-border credit, YoY %, by borrower country
    institutional       <- scanner.institutional registry (regime-event scored)
    valuation_gap       <- CAPE / fwd-PE vs own 10-20y history
    carry_cushion       <- (policy rate - inflation), FX-vol adjusted  [FRED/IFS]
    crowding            <- fund-manager-survey net OW, z-scored
    suddenstop_risk     <- FX-mismatch + external-debt-service / reserves
"""

from __future__ import annotations

from dataclasses import dataclass, asdict

import pandas as pd


@dataclass
class FactorRow:
    iso: str
    # credit_impulse: cross-border + domestic credit impulse, ~YoY % terms
    credit_impulse: float
    # institutional: Institutional Regime Score, 0-5 (dated legislative catalysts)
    institutional: float
    # valuation_gap: cheapness vs own history, + = cheap (std-dev-ish units)
    valuation_gap: float
    # carry_cushion: real policy rate %, FX-stability adjusted
    carry_cushion: float
    # crowding: consensus overweight, + = crowded (penalised)
    crowding: float
    # suddenstop_risk: external fragility, + = fragile (penalised)
    suddenstop_risk: float
    note: str = ""
    estimated: bool = False


# June 2026 snapshot. See module docstring for provenance.
_PANEL: list[FactorRow] = [
    # --- Tier 1 setups -----------------------------------------------------
    FactorRow("BR", credit_impulse=2.4, institutional=3.0, valuation_gap=2.2,
              carry_cushion=10.9, crowding=0.3, suddenstop_risk=0.8,
              note="33% of EMDE Q4 cross-border credit; CAPE 9.7; +10.9% real; Selic easing cycle starting"),
    FactorRow("SA", credit_impulse=1.6, institutional=5.0, valuation_gap=1.1,
              carry_cushion=0.4, crowding=-1.2, suddenstop_risk=0.4,
              note="QFI abolished Feb 2026 + 49% cap review; foreigners structurally absent; TASI -8% from peak"),
    FactorRow("DE", credit_impulse=0.6, institutional=5.0, valuation_gap=0.3,
              carry_cushion=0.5, crowding=-0.4, suddenstop_risk=-1.0,
              note="EUR500bn debt-brake reform; positioning still light despite 37% 2025 rally; ~17x"),
    # --- Tier 2 ------------------------------------------------------------
    FactorRow("PL", credit_impulse=2.6, institutional=4.0, valuation_gap=-1.2,
              carry_cushion=1.5, crowding=1.4, suddenstop_risk=0.2,
              note="EU funds 5x step-up to ~EUR34bn 2026; but WIG +46% TR 12m -- momentum not value"),
    FactorRow("MX", credit_impulse=1.2, institutional=4.0, valuation_gap=0.4,
              carry_cushion=4.5, crowding=0.2, suddenstop_risk=0.6,
              note="Plan Mexico capex-deduction window 2025-26; USMCA 2026 review is a binary overhang"),
    FactorRow("JP", credit_impulse=0.4, institutional=3.5, valuation_gap=-1.1,
              carry_cushion=-1.5, crowding=1.8, suddenstop_risk=-0.8,
              note="CG reform + Code update Jun 2026; but >1SD rich, short-yen crowded $10.1bn, heavily owned"),
    # --- Avoid-now ---------------------------------------------------------
    FactorRow("IN", credit_impulse=0.2, institutional=4.0, valuation_gap=-2.4,
              carry_cushion=1.8, crowding=0.6, suddenstop_risk=0.5,
              note="SWAGAT-FI Jun 2026 plumbing; but 75% premium to EM, ~$26bn 2026 FPI outflows, AI-rotation away"),
    FactorRow("CN", credit_impulse=-1.8, institutional=1.0, valuation_gap=1.0,
              carry_cushion=0.5, crowding=-0.6, suddenstop_risk=0.7,
              note="cross-border credit -15% YoY; M0 +12.5% vs loans +5.7% (liquidity hoarding); no legislative catalyst"),
    FactorRow("GB", credit_impulse=-0.4, institutional=1.0, valuation_gap=0.6,
              carry_cushion=1.2, crowding=-0.2, suddenstop_risk=0.3,
              note="corporate net-lending collapsed 1.0%->0.1% GDP into fiscal tightening"),
    # --- Rest of panel (calibrated estimates pending live wiring) ----------
    FactorRow("US", 0.8, 3.0, -1.5, 1.5, 1.5, -1.5,
              note="wealth-effect-dependent consumption; reserve absorber", estimated=True),
    FactorRow("KR", 0.9, 2.5, 0.5, 1.0, 1.2, -0.5, note="AI/semi earnings cycle pull", estimated=True),
    FactorRow("TW", 1.0, 2.0, -0.3, 0.5, 1.6, -0.4, note="AI/semi cycle, heavily owned", estimated=True),
    FactorRow("FR", -0.2, 2.0, 0.2, 0.5, -0.1, -0.6, note="drifting C->E; rising debt", estimated=True),
    FactorRow("IT", 0.1, 2.0, 0.8, 0.5, 0.0, -0.3, note="EMU trap; post-deleverage", estimated=True),
    FactorRow("ES", 0.7, 2.5, 0.4, 0.5, 0.3, -0.2, note="EZ relative bright spot", estimated=True),
    FactorRow("GR", 0.9, 2.5, 0.6, 0.8, 0.4, 0.1, note="post-crisis re-rating", estimated=True),
    FactorRow("TR", 1.8, 2.0, 0.7, -2.0, 0.5, 1.6,
              note="14.3% of EMDE Q4 inflow but FX-mismatch fragility", estimated=True),
    FactorRow("EG", 0.6, 2.5, 0.9, -1.0, 0.2, 1.8,
              note="stock/flow mismatch; $27bn ext debt service 2026", estimated=True),
    FactorRow("AR", 0.4, 2.0, 1.2, -1.5, 0.6, 1.7,
              note="IIF flags official-flows masking private retreat", estimated=True),
    FactorRow("ZA", 0.5, 1.5, 0.5, 2.0, 0.1, 0.9, note="mining rent + frontier FX risk", estimated=True),
    FactorRow("ID", 0.8, 2.0, 0.3, 2.5, 0.0, 0.4, note="commodity+manufacturing convergence", estimated=True),
    FactorRow("AU", 0.3, 1.0, -0.4, 0.8, 0.2, 0.5, note="household leverage + ToT", estimated=True),
    FactorRow("CA", 0.4, 1.5, -0.2, 0.6, 0.1, 0.4, note="Anglo-mimic + oil ToT", estimated=True),
    FactorRow("CH", 0.2, 1.5, -0.6, -0.5, 0.3, -1.2, note="entrepot; real saving", estimated=True),
    FactorRow("NL", 0.4, 2.5, 0.0, 0.3, 0.0, -0.9, note="C/D hybrid", estimated=True),
    FactorRow("SE", 0.5, 2.0, 0.1, 0.5, 0.0, -0.3, note="saver + housing credit", estimated=True),
    FactorRow("AE", 1.2, 3.5, 0.6, 0.3, -0.3, 0.0, note="diversifying rent state", estimated=True),
    FactorRow("QA", 1.0, 3.0, 0.5, 0.3, -0.4, -0.1, note="LNG rent surplus", estimated=True),
    FactorRow("NO", 0.3, 2.0, 0.2, 0.5, -0.2, -1.4, note="SWF-buffered rent state", estimated=True),
    FactorRow("CL", 0.9, 2.0, 0.7, 2.5, 0.0, 0.3, note="copper rent, open account", estimated=True),
    FactorRow("CO", 0.7, 1.5, 0.8, 3.0, 0.0, 0.7, note="oil + convergence hybrid", estimated=True),
    FactorRow("PE", 0.8, 1.5, 0.6, 1.5, 0.0, 0.4, note="copper/gold; political risk", estimated=True),
    FactorRow("HU", 1.5, 3.5, -0.2, 1.0, 0.5, 0.4, note="EM Europe +26%; EV FDI", estimated=True),
    FactorRow("CZ", 1.0, 3.0, 0.2, 0.5, 0.2, -0.4, note="convergence maturing; AE reclassified", estimated=True),
    FactorRow("RO", 0.9, 2.5, 0.4, 1.5, 0.1, 0.8, note="twin-deficit convergence stress", estimated=True),
    FactorRow("PH", 0.6, 2.0, 0.3, 1.5, 0.0, 0.6, note="remittance surplus; H/I hybrid", estimated=True),
    FactorRow("MY", 0.7, 2.0, 0.4, 1.0, 0.0, 0.3, note="managed FX + commodity convergence", estimated=True),
    FactorRow("TH", 0.5, 1.5, 0.3, 0.8, 0.1, 0.2, note="managed baht + tourism CA", estimated=True),
    FactorRow("VN", 1.1, 2.5, 0.2, 1.0, 0.2, 0.5, note="China-lite managed dong", estimated=True),
    FactorRow("NZ", 0.2, 1.0, -0.3, 0.8, 0.0, 0.4, note="smaller Anglo-mimic", estimated=True),
    FactorRow("PK", 0.3, 2.0, 0.8, -0.5, 0.1, 1.7, note="recurrent IMF; remittance-fragile", estimated=True),
    FactorRow("LK", 0.2, 2.0, 0.9, 0.0, 0.0, 1.5, note="post-default restructuring", estimated=True),
    FactorRow("NG", 0.4, 1.0, 0.7, 1.0, 0.0, 1.4, note="oil rent, FX-disordered", estimated=True),
    FactorRow("KZ", 0.6, 1.5, 0.5, 1.5, 0.0, 0.6, note="oil + China-linked", estimated=True),
    FactorRow("KW", 0.7, 2.0, 0.3, 0.3, -0.3, -0.5, note="pure rent state", estimated=True),
    FactorRow("HK", -0.5, 1.0, 0.4, 0.2, 0.0, 0.3, note="USD-pegged entrepot finance", estimated=True),
    FactorRow("SG", 0.6, 2.5, -0.2, 0.5, 0.3, -1.0, note="MNC distortion + real saving", estimated=True),
    FactorRow("IE", 0.5, 2.5, -0.1, 0.3, 0.2, -0.5, note="MNC-distorted; use modified GNI", estimated=True),
    FactorRow("BE", 0.3, 2.0, 0.2, 0.4, 0.0, -0.2, note="saver, high public debt", estimated=True),
    FactorRow("AT", 0.3, 2.0, 0.1, 0.4, 0.0, -0.3, note="EZ-core saver", estimated=True),
    FactorRow("FI", 0.2, 2.0, 0.3, 0.4, 0.0, -0.2, note="aging-driven surplus", estimated=True),
    FactorRow("DK", 0.4, 2.0, 0.0, 0.4, 0.0, -0.6, note="EUR-pegged, disciplined", estimated=True),
    FactorRow("PT", 0.6, 2.5, 0.5, 0.5, 0.2, -0.1, note="ES family", estimated=True),
    FactorRow("LU", 0.2, 2.0, -0.3, 0.2, 0.0, -0.8, note="fund-domicile distortion", estimated=True),
    FactorRow("RU", 0.0, 0.0, 1.5, 2.0, 0.0, 1.0, note="sanctioned; data unreliable", estimated=True),
    FactorRow("IR", 0.0, 0.0, 1.0, 0.0, 0.0, 1.5, note="sanctioned oil rent", estimated=True),
    FactorRow("VE", 0.0, 0.0, 1.5, 0.0, 0.0, 2.0, note="collapsed; informally dollarised", estimated=True),
]


def default_panel() -> pd.DataFrame:
    """Return the June 2026 factor panel as a DataFrame indexed by ISO."""
    df = pd.DataFrame([asdict(r) for r in _PANEL]).set_index("iso")
    return df


FACTOR_COLUMNS = [
    "credit_impulse",
    "institutional",
    "valuation_gap",
    "carry_cushion",
    "crowding",
    "suddenstop_risk",
]
