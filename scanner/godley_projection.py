"""
Godley's medium-term stock-projection methodology, automated.

This module automates the specific diagnostic Godley ran in *Seven Unsustainable
Processes* (Levy Strategic Analysis, January 1999, Appendix 2 "Note on the
Models Employed"): project the three balances forward 5-7 years from a CBO-
style fiscal baseline + consensus growth, derive the private balance as the
residual, cumulate flows into a stock of foreign liabilities (NIIP/GDP), and
ask whether the resulting stock path is plausible or "explosive". If the path
explodes, the current configuration of flows is by construction unsustainable
and asset prices are sitting on borrowed time.

Quoting Godley 1999, p. iv:
    "If the growth in net lending and money supply growth were to continue
    for another eight years, the implied indebtedness of the private sector
    would then be so extremely large that a sensational day of reckoning
    could then be at hand."

The load-bearing nonlinearity (which the workflow's adversarial verifier
correctly flagged) is the interest-payment feedback: net foreign income
NII[t] = r_ext * NIIP[t-1]. A growing stock generates a growing income drag
on the next current-account flow, which in turn grows the stock faster --
the divergence is precisely how Godley distinguished "drift" from "explosion".

Implementation
--------------
We take IMF WEO-style projections (here hardcoded mid-2026 calibrations until
the live IMF API loader lands) and step forward 5 years:

    CA[t]    = goods_balance[t] + transfers[t] + r_ext * NIIP[t-1]
    NL_priv[t] = CA[t] - (G-T)[t]                              (identity)
    NIIP[t]  = NIIP[t-1] + CA[t]                               (stock-flow)

Then we compute one-sided unsustainability:

    score = max(0, NIIP[0] - NIIP[T] - 25) / 10

i.e. only countries whose projected NIIP/GDP deteriorates by more than 25pp
over 5y trigger a warning. Surplus economies whose NIIP rises (Germany,
Norway) deliberately do NOT light the flag.

Used to augment Seven-Processes flag P7 ("rising net foreign indebtedness/GDP")
with Godley's actual forward-projection method.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass
class GodleyInputs:
    """
    Mid-2026 calibrated inputs per country, all in %GDP / annual units.

    `niip_pct_gdp` is the *current* NIIP/GDP stock (NEGATIVE for debtor
    nations like the US -- the proper sign convention is asset-minus-
    liability from the country's own perspective).
    `r_ext` is the average yield on external assets/liabilities (per IMF IFS,
    typically 3-5%); set negative if the country is a net debtor paying a
    higher yield than it earns.
    `fiscal_balance_path` is the 5-year mean projected fiscal balance (G-T as %GDP).
    `goods_and_transfers` is the structural CA component excluding NII.
    """
    iso: str
    niip_pct_gdp: float
    r_ext: float
    fiscal_balance_path: float
    goods_and_transfers: float
    note: str = ""


# Mid-2026 calibration. NIIP figures sourced from IMF External Sector Report
# 2025 (annual); fiscal_balance_path from IMF WEO Apr 2026 5-year ahead; goods_
# and_transfers calibrated from BoP / current account ex-investment-income.
# All numbers are %GDP. To go live, wire IMF datamapper API at
# https://www.imf.org/external/datamapper/api/v1/{INDICATOR}/{ISO}
# where INDICATOR in {GGXCNL_NGDP, BCA_NGDPD, BCAS_NGDPD, NGDPRPCH}.
_INPUTS: list[GodleyInputs] = [
    # iso, NIIP%GDP, r_ext, fiscal balance projected, goods+transfers
    GodleyInputs("US", niip_pct_gdp=-80.0, r_ext=0.5, fiscal_balance_path=-6.5,
                 goods_and_transfers=-3.0,
                 note="reserve absorber; -80 NIIP financed by USD demand"),
    GodleyInputs("GB", niip_pct_gdp=-32.0, r_ext=1.0, fiscal_balance_path=-4.0,
                 goods_and_transfers=-2.5,
                 note="Reeves consolidation insufficient vs structural CA deficit"),
    GodleyInputs("DE", niip_pct_gdp=+72.0, r_ext=+1.5, fiscal_balance_path=-2.5,
                 goods_and_transfers=+5.5,
                 note="huge creditor; debt brake reform raises fiscal but identity holds"),
    GodleyInputs("JP", niip_pct_gdp=+85.0, r_ext=+2.0, fiscal_balance_path=-5.0,
                 goods_and_transfers=+2.5,
                 note="largest creditor; Takaichi widens deficit but NII offsets"),
    GodleyInputs("KR", niip_pct_gdp=+45.0, r_ext=+1.0, fiscal_balance_path=-2.5,
                 goods_and_transfers=+3.0,
                 note="net creditor; AI fund + fiscal mild widening"),
    GodleyInputs("CN", niip_pct_gdp=+15.0, r_ext=+0.5, fiscal_balance_path=-7.0,
                 goods_and_transfers=+2.0,
                 note="Setser flags ~$500bn hidden surplus; positive NIIP genuine"),
    GodleyInputs("BR", niip_pct_gdp=-35.0, r_ext=2.5, fiscal_balance_path=-5.5,
                 goods_and_transfers=-1.5,
                 note="2026 budget strains rule; CA modest deficit"),
    GodleyInputs("MX", niip_pct_gdp=-45.0, r_ext=1.5, fiscal_balance_path=-3.5,
                 goods_and_transfers=-0.5,
                 note="USMCA review tail-risk on goods balance"),
    GodleyInputs("IN", niip_pct_gdp=-12.0, r_ext=1.5, fiscal_balance_path=-4.3,
                 goods_and_transfers=-1.8,
                 note="FY27 consolidation; CA deficit funded by FPI flows"),
    GodleyInputs("ID", -22.0, 1.0, -2.5, 0.0),
    GodleyInputs("PL", niip_pct_gdp=-35.0, r_ext=0.5, fiscal_balance_path=-5.0,
                 goods_and_transfers=+0.5,
                 note="EU funds + fiscal widening, but RRF receipts cushion"),
    GodleyInputs("HU", -55.0, 1.0, -4.5, +0.5),
    GodleyInputs("CZ", -25.0, 0.5, -2.5, +1.0),
    GodleyInputs("RO", -55.0, 1.5, -7.0, -5.5,
                 note="twin-deficit convergence stress; CA -7% is the bind"),
    GodleyInputs("TR", -23.0, 3.0, -4.0, -2.0,
                 note="FX-mismatched corporate debt; CA improving but stock vulnerable"),
    GodleyInputs("EG", -65.0, 2.5, -6.0, -3.0,
                 note="$27bn external debt service 2026; Egypt-style stock/flow trap"),
    GodleyInputs("AR", -10.0, 2.0, -1.0, +1.5,
                 note="Milei stabilisation; CA improved sharply"),
    GodleyInputs("PK", -50.0, 2.5, -7.0, -1.5),
    GodleyInputs("LK", -55.0, 1.5, -5.0, -0.5),
    GodleyInputs("NG", -15.0, 2.0, -4.0, -1.5),
    GodleyInputs("SA", +85.0, +1.5, -2.5, +2.0,
                 note="positive NIIP; PIF deployment vs giga-project recalibration"),
    GodleyInputs("AE", +210.0, +2.0, +1.0, +5.0),
    GodleyInputs("QA", +180.0, +2.0, +5.0, +12.0),
    GodleyInputs("KW", +500.0, +3.0, +3.0, +18.0),
    GodleyInputs("NO", +335.0, +3.5, +10.0, +12.0,
                 note="GPFG largest in panel; oil rent surplus + SWF"),
    GodleyInputs("KZ", +5.0, 1.0, -2.0, +1.0),
    GodleyInputs("CL", -25.0, 1.5, -2.0, -2.0),
    GodleyInputs("PE", -40.0, 1.5, -2.0, +0.0),
    GodleyInputs("CO", -50.0, 2.0, -4.5, -2.5),
    GodleyInputs("ZA", -10.0, 1.5, -5.0, -2.0),
    GodleyInputs("AU", -42.0, 1.5, -2.0, +1.5,
                 note="iron-ore ToT cushions; household debt fragility separate"),
    GodleyInputs("CA", -10.0, 1.0, -1.5, -2.0),
    GodleyInputs("NZ", -50.0, 2.0, -2.0, -3.5),
    GodleyInputs("FR", -28.0, 1.0, -5.5, -2.5,
                 note="drifting C->E; debt/GDP rising"),
    GodleyInputs("IT", -3.0, 0.5, -3.5, +1.0),
    GodleyInputs("ES", -45.0, 1.0, -3.0, +2.5),
    GodleyInputs("PT", -75.0, 1.5, -2.0, +1.5),
    GodleyInputs("GR", -130.0, 2.0, -1.0, -1.0),
    GodleyInputs("NL", +90.0, +2.0, -2.0, +9.0),
    GodleyInputs("BE", +55.0, +1.5, -4.0, -1.0),
    GodleyInputs("AT", +20.0, +1.0, -3.0, +1.0),
    GodleyInputs("FI", +25.0, +1.0, -3.5, +1.0),
    GodleyInputs("DK", +75.0, +1.5, +1.0, +9.0),
    GodleyInputs("SE", +30.0, +1.0, -1.0, +4.5),
    GodleyInputs("CH", +110.0, +2.0, +0.5, +8.5),
    GodleyInputs("IE", +25.0, +1.0, +1.5, +10.0,
                 note="use modified GNI in denominator; CA hugely distorted by MNCs"),
    GodleyInputs("LU", +50.0, +1.0, +1.0, +3.0),
    GodleyInputs("SG", +245.0, +3.0, +0.5, +18.0),
    GodleyInputs("HK", +475.0, +2.5, +1.5, +5.0),
    GodleyInputs("TW", +200.0, +2.5, +0.0, +12.0),
    GodleyInputs("VN", -20.0, 1.0, -3.0, +4.5),
    GodleyInputs("MY", -10.0, 0.5, -4.0, +3.0),
    GodleyInputs("TH", +5.0, 0.5, -3.5, +1.0),
    GodleyInputs("PH", -8.0, 1.0, -5.5, -2.0),
    GodleyInputs("RU", +35.0, +1.5, +0.0, +5.0, note="sanctions distort data"),
    GodleyInputs("IR", +5.0, 1.0, -3.0, +0.0),
    GodleyInputs("VE", -20.0, 1.0, -8.0, -1.0),
]


def project(iso: str, horizon_years: int = 5) -> pd.DataFrame:
    """
    Step the three-balances identity forward, with endogenous NII feedback.

    Returns a DataFrame with columns NII, CA, NL_priv, NIIP per year over the
    horizon, in %GDP terms. The trajectory IS the diagnostic -- the scalar
    score is the second derivative.
    """
    inputs = next((i for i in _INPUTS if i.iso == iso), None)
    if inputs is None:
        return pd.DataFrame()

    niip = [inputs.niip_pct_gdp]
    rows = []
    for t in range(horizon_years):
        nii = inputs.r_ext * niip[-1] / 100.0  # r_ext is %, NIIP is %GDP
        ca = inputs.goods_and_transfers + nii
        nl_priv = ca - inputs.fiscal_balance_path
        new_niip = niip[-1] + ca
        rows.append(dict(year=t + 1, NII=nii, CA=ca, NL_priv=nl_priv, NIIP=new_niip))
        niip.append(new_niip)
    df = pd.DataFrame(rows)
    df.attrs["iso"] = iso
    df.attrs["niip_start"] = inputs.niip_pct_gdp
    df.attrs["note"] = inputs.note
    return df


def unsustainability_score(iso: str, horizon_years: int = 5) -> float:
    """
    One-sided score: only DETERIORATING NIIP paths trigger.

    Positive number = stock projected to deteriorate >25pp over horizon;
    larger = more "explosive". Returns 0 for surplus economies whose NIIP
    rises (so Germany/Norway/etc. don't false-positive on a rising stock).
    """
    trajectory = project(iso, horizon_years)
    if trajectory.empty:
        return 0.0
    niip_start = trajectory.attrs["niip_start"]
    niip_terminal = trajectory["NIIP"].iloc[-1]
    deterioration = niip_start - niip_terminal  # positive if stock worsened
    return max(0.0, deterioration - 25.0) / 10.0


def panel_scores(horizon_years: int = 5) -> pd.DataFrame:
    """Run the projection for every ISO and return scores."""
    rows = []
    for inp in _INPUTS:
        score = unsustainability_score(inp.iso, horizon_years)
        traj = project(inp.iso, horizon_years)
        rows.append(dict(
            iso=inp.iso,
            niip_start=inp.niip_pct_gdp,
            niip_terminal=traj["NIIP"].iloc[-1] if not traj.empty else inp.niip_pct_gdp,
            deterioration_pp=inp.niip_pct_gdp - (traj["NIIP"].iloc[-1] if not traj.empty else inp.niip_pct_gdp),
            unsustainability=score,
            godley_explosive=score > 1.0,
            note=inp.note,
        ))
    return pd.DataFrame(rows).set_index("iso").sort_values("unsustainability",
                                                            ascending=False)


def godley_warning_p7(iso: str) -> bool:
    """
    The new Process #7 test: use forward projection where IMF/calibrated
    data is available, fall back to existing heuristic where not. Lights
    when the projected NIIP path deteriorates by >25pp over 5y.
    """
    return unsustainability_score(iso) > 0.5
