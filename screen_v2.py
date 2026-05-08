"""Corrected setup screener.

Methodological fixes vs v1:
  * Base detection: walk backward from the latest bar to find the
    longest contiguous stretch where (max-min)/mean stays below a
    range threshold (default 30%). The volume profile and POC are
    computed *only* over this base — not over the entire chart, which
    biased v1's POC into trends.
  * Phase classification: BASE_QUIET / BASE_ABSORBING / BASE_BREAKOUT
    / POST_RERATING / DECLINING / NO_BASE — the setup we want is
    BASE_ABSORBING (flat price, vol building) or fresh BASE_BREAKOUT.
  * Volume z-score relative to the base's own mean and std, not a
    fixed 26w average. This avoids flagging mechanical block trades
    after a tender as accumulation.
  * 13-week price-change filter to exclude names that have already
    re-rated.
  * Distribution events flagged via dividend/cap-return data so we
    don't read post-distribution price drift as a base entry.
  * Catalyst and NAV-quality tags joined into the output so ranking
    reflects the trade's *type*, not just its chart shape.
"""

from __future__ import annotations

import argparse
import sys
import time
from dataclasses import dataclass

import numpy as np
import pandas as pd
import yfinance as yf

from nav_discount_finder import (
    KNOWN_CANDIDATES,
    all_known_candidates,
    money_flow_index,
)


# ---------------------------------------------------------------------------
# Catalyst + NAV-quality metadata. WIND_DOWN_COMMITTED is the strongest
# pre-rating bucket only when the chart hasn't moved yet — by definition
# many of these will be POST_RERATING.

CATALYST: dict[str, str] = {
    # Confirmed managed wind-down / realisation
    "RSE.L": "WIND_DOWN_COMMITTED",
    "ADIG.L": "WIND_DOWN_COMMITTED",
    "DGI9.L": "WIND_DOWN_COMMITTED",
    "USF.L": "WIND_DOWN_COMMITTED",
    "TENT.L": "WIND_DOWN_COMMITTED",
    "HEIT.L": "WIND_DOWN_COMMITTED",
    "HGEN.L": "WIND_DOWN_COMMITTED",
    "AEET.L": "WIND_DOWN_COMMITTED",
    "AERI.L": "WIND_DOWN_COMMITTED",
    "GSEO.L": "WIND_DOWN_COMMITTED",
    "VSL.L": "WIND_DOWN_COMMITTED",
    "GABI.L": "WIND_DOWN_COMMITTED",
    "RMII.L": "WIND_DOWN_COMMITTED",
    "API.L": "WIND_DOWN_COMMITTED",
    "RESI.L": "WIND_DOWN_COMMITTED",
    "SBO.L": "WIND_DOWN_COMMITTED",
    "SUPP.L": "WIND_DOWN_COMMITTED",
    "MPLS.L": "WIND_DOWN_COMMITTED",
    "HOT.L": "WIND_DOWN_COMMITTED",
    "KPC.L": "WIND_DOWN_COMMITTED",
    "AAS.L": "WIND_DOWN_COMMITTED",
    "GRIO.L": "WIND_DOWN_COMMITTED",
    "TMI.L": "WIND_DOWN_LIKELY",  # capital-return programme; status debated
    # Strategic review / continuation pending — pre-rating territory
    "GCP.L": "STRATEGIC_REVIEW",
    "FGEN.L": "STRATEGIC_REVIEW",
    "SOHO.L": "STRATEGIC_REVIEW",
    "CHRY.L": "RETURN_OF_CAPITAL_LIVE",
    "SSIT.L": "STRATEGIC_REVIEW",
    "AUGM.L": "STRATEGIC_REVIEW",
    "GROW.L": "STRATEGIC_REVIEW",
    # Active activist / Saba campaigns
    "HRI.L": "ACTIVIST_TARGET",
    "USA.L": "ACTIVIST_TARGET",
    "CYN.L": "ACTIVIST_TARGET",
    "ESCT.L": "ACTIVIST_TARGET",
    "EWI.L": "ACTIVIST_TARGET",
    "BNKR.L": "ACTIVIST_TARGET",
    "TEM.L": "ACTIVIST_TARGET",
    "DIVI.L": "ACTIVIST_TARGET",
    "HOME.L": "DISTRESSED",
    # Structural / quality discount, no specific event
    "HVPE.L": "STRUCTURAL_DISCOUNT",
    "NBPE.L": "STRUCTURAL_DISCOUNT",
    "ICGT.L": "STRUCTURAL_DISCOUNT",
    "PIN.L": "STRUCTURAL_DISCOUNT",
    "OCI.L": "STRUCTURAL_DISCOUNT",
    "APAX.L": "STRUCTURAL_DISCOUNT",
    "CTPE.L": "STRUCTURAL_DISCOUNT",
    "HGT.L": "STRUCTURAL_DISCOUNT",
    "UKW.L": "STRUCTURAL_DISCOUNT",
    "TRIG.L": "STRUCTURAL_DISCOUNT",
    "FSFL.L": "STRUCTURAL_DISCOUNT",
    "NESF.L": "STRUCTURAL_DISCOUNT",
    "BSIF.L": "STRUCTURAL_DISCOUNT",
    "JLEN.L": "STRUCTURAL_DISCOUNT",
    "GRID.L": "STRUCTURAL_DISCOUNT",
    "SEIT.L": "STRUCTURAL_DISCOUNT",
    "HICL.L": "STRUCTURAL_DISCOUNT",
    "INPP.L": "STRUCTURAL_DISCOUNT",
    "3IN.L": "STRUCTURAL_DISCOUNT",
    "PINT.L": "STRUCTURAL_DISCOUNT",
    "CORD.L": "STRUCTURAL_DISCOUNT",
    "BPCR.L": "STRUCTURAL_DISCOUNT",
    "VTA.L": "STRUCTURAL_DISCOUNT",
    "NCYF.L": "STRUCTURAL_DISCOUNT",
    "TFIF.L": "STRUCTURAL_DISCOUNT",
    "SEQI.L": "STRUCTURAL_DISCOUNT",
    "SREI.L": "STRUCTURAL_DISCOUNT",
    "CREI.L": "STRUCTURAL_DISCOUNT",
    "RGL.L": "STRUCTURAL_DISCOUNT",
    "AEWU.L": "STRUCTURAL_DISCOUNT",
    "PCTN.L": "STRUCTURAL_DISCOUNT",
    "WHR.L": "STRUCTURAL_DISCOUNT",
    "ESP.L": "STRUCTURAL_DISCOUNT",
    "HLCL.L": "STRUCTURAL_DISCOUNT",
    "PSDL.L": "STRUCTURAL_DISCOUNT",
    "RECI.L": "STRUCTURAL_DISCOUNT",
    "VOF.L": "STRUCTURAL_DISCOUNT",
    "VNH.L": "STRUCTURAL_DISCOUNT",
    "PSH.L": "STRUCTURAL_DISCOUNT",
    "TFG.L": "STRUCTURAL_DISCOUNT",
    "TPOU.L": "STRUCTURAL_DISCOUNT",
    "BHMG.L": "STRUCTURAL_DISCOUNT",
    "NAS.L": "STRUCTURAL_DISCOUNT",
    "CLDN.L": "STRUCTURAL_DISCOUNT",
    "RCP.L": "STRUCTURAL_DISCOUNT",
    "AGT.L": "STRUCTURAL_DISCOUNT",
    "AJOT.L": "STRUCTURAL_DISCOUNT",
    "ONWD.L": "STRUCTURAL_DISCOUNT",
    "OIT.L": "STRUCTURAL_DISCOUNT",
    "SEC.L": "STRUCTURAL_DISCOUNT",
    # Australian LICs
    "LSF.AX": "ACTIVIST_TARGET",         # Saba campaign
    "WAM.AX": "STRUCTURAL_DISCOUNT",
    "WLE.AX": "STRUCTURAL_DISCOUNT",
    "WGB.AX": "STRUCTURAL_DISCOUNT",
    "WAA.AX": "STRUCTURAL_DISCOUNT",
    "TGF.AX": "STRATEGIC_REVIEW",         # discount-control / wind-up
    "HM1.AX": "STRUCTURAL_DISCOUNT",
    "MFF.AX": "STRUCTURAL_DISCOUNT",
    "PIA.AX": "STRATEGIC_REVIEW",         # restructure history
    "PE1.AX": "STRUCTURAL_DISCOUNT",
    "NCC.AX": "STRUCTURAL_DISCOUNT",
    "NSC.AX": "STRUCTURAL_DISCOUNT",
    "GC1.AX": "STRUCTURAL_DISCOUNT",
    "PL8.AX": "STRUCTURAL_DISCOUNT",
    "OBL.AX": "STRUCTURAL_DISCOUNT",
    "SOL.AX": "STRUCTURAL_DISCOUNT",
    "AUI.AX": "STRUCTURAL_DISCOUNT",
    "DUI.AX": "STRUCTURAL_DISCOUNT",
    "WHF.AX": "STRUCTURAL_DISCOUNT",
    "ARG.AX": "STRUCTURAL_DISCOUNT",
    "AFI.AX": "STRUCTURAL_DISCOUNT",
    # Canadian special sits
    "POW.TO": "STRUCTURAL_DISCOUNT",
    "ONEX.TO": "STRUCTURAL_DISCOUNT",
    "BAM.TO": "STRUCTURAL_DISCOUNT",
    "DGS.TO": "STRUCTURAL_DISCOUNT",
    "FTN.TO": "STRUCTURAL_DISCOUNT",
    "LBS.TO": "STRUCTURAL_DISCOUNT",
    "BSP.TO": "STRUCTURAL_DISCOUNT",
    "FFN.TO": "STRUCTURAL_DISCOUNT",
    "LCS.TO": "STRUCTURAL_DISCOUNT",
    # US sum-of-parts / conglomerate
    "IAC": "STRUCTURAL_DISCOUNT",
    "L": "STRUCTURAL_DISCOUNT",
    "FWONK": "STRUCTURAL_DISCOUNT",
    "BATRA": "STRUCTURAL_DISCOUNT",
    "LBRDK": "STRUCTURAL_DISCOUNT",
    "LILA": "STRUCTURAL_DISCOUNT",
    "MSGS": "STRUCTURAL_DISCOUNT",
    "MSGE": "STRUCTURAL_DISCOUNT",
    "LGF.A": "STRUCTURAL_DISCOUNT",
    # Swiss / EU specialist
    "BION.SW": "STRUCTURAL_DISCOUNT",
    "HBMN.SW": "STRUCTURAL_DISCOUNT",
    # UK extras 2
    "MIGO.L": "STRUCTURAL_DISCOUNT",
    "ARR.L": "STRUCTURAL_DISCOUNT",
    "JAM.L": "STRUCTURAL_DISCOUNT",
    "MUT.L": "STRUCTURAL_DISCOUNT",
    "LWDB.L": "STRUCTURAL_DISCOUNT",
    "BIPS.L": "STRUCTURAL_DISCOUNT",
    "FAIR.L": "STRUCTURAL_DISCOUNT",
    "SDP.L": "STRATEGIC_REVIEW",          # merger candidate
    "ATR.L": "STRATEGIC_REVIEW",          # merger candidate
}

# NAV reliability — listed-asset trusts have observable NAV; private/
# infrastructure/biotech NAVs are model-driven and often overstated.
NAV_QUALITY: dict[str, str] = {
    # Listed equity portfolios — clean
    **{t: "LISTED_CLEAN" for t in [
        "NAS.L", "CLDN.L", "RCP.L", "AGT.L", "AJOT.L", "ONWD.L", "SEC.L",
        "OIT.L", "DIVI.L", "HRI.L", "USA.L", "CYN.L", "ESCT.L", "EWI.L",
        "BNKR.L", "TEM.L", "VOF.L", "VNH.L", "BRFI.L", "PHI.L", "PAC.L",
        "MYI.L", "AAIF.L", "JEMI.L", "JMG.L", "FEML.L", "MMIT.L", "FCSS.L",
        "PSH.L", "TPOU.L", "BHMG.L", "ANII.L", "JAGI.L", "JEDT.L", "BRSC.L",
        "THRG.L", "BRWM.L", "BERI.L", "HFEL.L", "SCF.L", "LWI.L", "HHI.L",
        "MRC.L", "BUT.L", "HSL.L", "SCP.L", "SSON.L", "ASL.L", "AGVI.L",
        "BGFD.L", "JFJ.L", "RIII.L", "MNL.L", "KPC.L", "HOT.L", "AUSC.L",
        "ASCI.L", "BBH.L", "IBT.L", "WWH.L", "BIOG.L", "RTW.L", "BRLA.L",
    ]},
    # Debt amortising — pulls to par
    **{t: "DEBT_AMORTISING" for t in [
        "GCP.L", "GABI.L", "RMII.L", "VSL.L", "BPCR.L", "VTA.L", "NCYF.L",
        "TFIF.L", "SEQI.L", "MPLS.L", "RECI.L",
    ]},
    # Infrastructure DCF — model but audited
    **{t: "INFRA_DCF" for t in [
        "HICL.L", "INPP.L", "3IN.L", "PINT.L", "CORD.L", "DGI9.L",
    ]},
    # Renewables / energy infra — model + asset-specific risk
    **{t: "RENEWABLES_DCF" for t in [
        "UKW.L", "TRIG.L", "FSFL.L", "NESF.L", "BSIF.L", "JLEN.L",
        "GRID.L", "SEIT.L", "FGEN.L", "GSEO.L", "HEIT.L", "HGEN.L",
        "AEET.L", "AERI.L", "USF.L", "TENT.L",
    ]},
    # Property — model-driven, can be optimistic in stressed markets
    **{t: "PROPERTY_DCF" for t in [
        "API.L", "RESI.L", "SREI.L", "CREI.L", "RGL.L", "AEWU.L",
        "PCTN.L", "WHR.L", "ESP.L", "HLCL.L", "PSDL.L", "SOHO.L", "GRIO.L",
    ]},
    # Private equity — model-driven, illiquid
    **{t: "PRIVATE_EQUITY" for t in [
        "HVPE.L", "NBPE.L", "ICGT.L", "PIN.L", "OCI.L", "APAX.L",
        "CTPE.L", "HGT.L", "SBO.L", "SUPP.L", "CHRY.L", "SSIT.L",
        "AUGM.L", "GROW.L",
    ]},
    # Real assets — vessels, aircraft (observable secondary market)
    **{t: "REAL_ASSET_OBSERVABLE" for t in [
        "TMI.L", "SHIP.L", "DNA2.L", "DNA3.L", "AA4.L", "DPA.L",
    ]},
    # Distressed / unreliable
    **{t: "DISTRESSED" for t in ["HOME.L", "ADIG.L", "AAS.L", "KKVL.L"]},
    # New universe additions
    **{t: "LISTED_CLEAN" for t in [
        # Australian LICs (mostly listed equity portfolios)
        "LSF.AX", "WAM.AX", "WLE.AX", "WGB.AX", "WAA.AX", "HM1.AX",
        "MFF.AX", "PIA.AX", "NCC.AX", "NSC.AX", "GC1.AX", "PL8.AX",
        "AUI.AX", "DUI.AX", "WHF.AX", "ARG.AX", "AFI.AX",
        # UK extras 2 (listed-equity trusts)
        "MIGO.L", "ARR.L", "JAM.L", "MUT.L", "LWDB.L", "BIPS.L",
        "SDP.L", "ATR.L",
        # Swiss specialist (listed biotech/healthcare)
        "BION.SW", "HBMN.SW",
        # US conglomerate (listed subsidiary stubs)
        "FWONK", "BATRA", "LBRDK", "LILA", "MSGS", "MSGE", "LGF.A",
    ]},
    **{t: "REAL_ASSET_OBSERVABLE" for t in [
        "TGF.AX",  # Tribeca Natural Resources
    ]},
    **{t: "PRIVATE_EQUITY" for t in [
        "PE1.AX",       # Pengana Private Equity
        "ONEX.TO",      # Onex
        "BAM.TO",       # Brookfield AM
        "POW.TO",       # Power Corp (mixed listed/private)
        "SOL.AX",       # Soul Patts (mixed listed/private)
        "OBL.AX",       # Omni Bridgeway (litigation, model-driven)
        "FAIR.L",       # Fair Oaks (CLO equity, model)
    ]},
    # Canadian split corps — debt-amortising-ish capital structure
    **{t: "DEBT_AMORTISING" for t in [
        "DGS.TO", "FTN.TO", "LBS.TO", "BSP.TO", "FFN.TO", "LCS.TO",
    ]},
    # IAC and Loews — sum-of-parts of mostly-listed subsidiaries
    "IAC": "LISTED_CLEAN",
    "L": "LISTED_CLEAN",
}


# ---------------------------------------------------------------------------

@dataclass
class ScreenResult:
    ticker: str
    error: str | None = None
    last_close: float | None = None
    base_start: pd.Timestamp | None = None
    base_length_weeks: int | None = None
    base_range_pct: float | None = None  # (max-min)/mean
    base_low: float | None = None
    base_high: float | None = None
    poc: float | None = None
    poc_distance_pct: float | None = None
    chg_13w_pct: float | None = None
    chg_26w_pct: float | None = None
    last_vol: float | None = None
    base_vol_mean: float | None = None
    vol_z: float | None = None  # latest vol vs base mean/std
    spike_in_base: bool = False  # vol spike printed inside the base, not after a breakout
    mfi: float | None = None
    mfi_rising: bool | None = None
    distribution_recent: bool = False  # > 5% drop in close on a single bar suggests cap return / distribution
    phase: str = "UNKNOWN"
    catalyst: str | None = None
    nav_quality: str | None = None
    score: float = 0.0


def detect_base(df: pd.DataFrame, max_lookback: int = 208,
                range_threshold: float = 0.30,
                min_length: int = 13) -> pd.DataFrame:
    """Return the slice of df representing the longest recent
    contiguous base where rolling range/mean <= threshold."""
    n = len(df)
    if n < min_length:
        return df
    closes = df["Close"].to_numpy()
    end = n
    start = end - 1
    upper = max(0, n - max_lookback)
    while start > upper:
        candidate = start - 1
        window = closes[candidate:end]
        rng = (window.max() - window.min()) / window.mean()
        if rng > range_threshold:
            break
        start = candidate
    if end - start < min_length:
        # widen threshold once for shorter tighter bases (small rangebound trusts)
        return df.tail(min_length)
    return df.iloc[start:end]


def base_volume_profile(base: pd.DataFrame, bins: int = 60):
    """POC computed *only* on the base period."""
    if base.empty:
        return None
    lo = float(base["Low"].min())
    hi = float(base["High"].max())
    if not (np.isfinite(lo) and np.isfinite(hi)) or hi <= lo:
        return None
    edges = np.linspace(lo, hi, bins + 1)
    centers = 0.5 * (edges[:-1] + edges[1:])
    vols = np.zeros(bins)
    for low, high, vol in zip(base["Low"].to_numpy(), base["High"].to_numpy(),
                              base["Volume"].to_numpy()):
        if not (np.isfinite(low) and np.isfinite(high) and np.isfinite(vol)):
            continue
        if high <= low or vol <= 0:
            continue
        lo_idx = max(0, int(np.searchsorted(edges, low, side="right") - 1))
        hi_idx = min(bins - 1, int(np.searchsorted(edges, high, side="right") - 1))
        if hi_idx < lo_idx:
            continue
        n = hi_idx - lo_idx + 1
        vols[lo_idx:hi_idx + 1] += vol / n
    if vols.sum() <= 0:
        return None
    return float(centers[int(np.argmax(vols))])


def classify_phase(*, in_base: bool, vol_z: float | None,
                   chg_13w: float | None, last_close: float, base_high: float,
                   base_low: float, distribution_recent: bool) -> str:
    if distribution_recent:
        return "DISTRIBUTION_DRIVEN"
    if chg_13w is not None and chg_13w > 0.15:
        return "POST_RERATING"
    if not in_base:
        if chg_13w is not None and chg_13w < -0.15:
            return "DOWNTREND"
        return "NO_BASE"
    # in-base
    above_high = last_close > base_high * 1.03
    if above_high and vol_z is not None and vol_z >= 2.0:
        return "BASE_BREAKOUT"
    if vol_z is not None and vol_z >= 1.5:
        return "BASE_ABSORBING"
    if chg_13w is not None and chg_13w < -0.08:
        return "BASE_DECLINING"
    return "BASE_QUIET"


def screen_one(ticker: str, *, max_lookback: int = 208,
               range_threshold: float = 0.30, mfi_period: int = 18) -> ScreenResult:
    res = ScreenResult(ticker=ticker)
    res.catalyst = CATALYST.get(ticker)
    res.nav_quality = NAV_QUALITY.get(ticker)
    try:
        # auto_adjust=True back-adjusts for splits AND dividends, which
        # makes capital-return distributions invisible to price (correct
        # — investor got cash for the difference) and removes spurious
        # 99% drops from splits.
        data = yf.download(ticker, period="5y", interval="1wk",
                           progress=False, auto_adjust=True)
    except Exception as exc:
        res.error = f"download: {exc}"
        return res
    if data is None or data.empty:
        res.error = "no data"
        return res
    if isinstance(data.columns, pd.MultiIndex):
        data.columns = data.columns.get_level_values(0)
    data = data.dropna(subset=["Close", "Volume"])
    # Hygiene: yfinance occasionally returns Low=0 prints from bad
    # ticks. Clamp to bar's open/close to avoid contaminating range
    # statistics.
    bad_lows = (data["Low"] <= 0) | (data["Low"].isna())
    if bad_lows.any():
        data.loc[bad_lows, "Low"] = data.loc[bad_lows, ["Open", "Close"]].min(axis=1)
    if len(data) < 30:
        res.error = "insufficient bars"
        return res

    res.last_close = float(data["Close"].iloc[-1])

    base = detect_base(data, max_lookback=max_lookback,
                       range_threshold=range_threshold)
    res.base_start = base.index[0]
    res.base_length_weeks = len(base)
    # Use Close-based range to avoid one-off bad Low/High prints.
    base_close = base["Close"]
    base_lo = float(base_close.min())
    base_hi = float(base_close.max())
    base_close_mean = float(base_close.mean())
    res.base_low = base_lo
    res.base_high = base_hi
    res.base_range_pct = (base_hi - base_lo) / base_close_mean if base_close_mean > 0 else None

    poc = base_volume_profile(base)
    res.poc = poc
    if poc and poc > 0:
        res.poc_distance_pct = abs(res.last_close - poc) / poc

    if len(data) >= 14:
        res.chg_13w_pct = float(data["Close"].iloc[-1] / data["Close"].iloc[-14] - 1)
    if len(data) >= 27:
        res.chg_26w_pct = float(data["Close"].iloc[-1] / data["Close"].iloc[-27] - 1)

    base_vol = base["Volume"].astype(float)
    res.last_vol = float(data["Volume"].iloc[-1])
    res.base_vol_mean = float(base_vol.mean()) if len(base_vol) else None
    if len(base_vol) >= 5 and base_vol.std() > 0:
        res.vol_z = (res.last_vol - base_vol.mean()) / base_vol.std()

    # Distribution-driven price drop heuristic: any single weekly close
    # decline > 8% in the last 6 weeks is suspicious for a cap-return
    # event we may not want to read as natural price action.
    recent = data["Close"].iloc[-6:]
    if len(recent) >= 2:
        weekly_chg = recent.pct_change().dropna()
        res.distribution_recent = bool((weekly_chg < -0.08).any())

    in_base = res.last_close >= base_lo * 0.95 and res.last_close <= base_hi * 1.05

    res.phase = classify_phase(
        in_base=in_base, vol_z=res.vol_z, chg_13w=res.chg_13w_pct,
        last_close=res.last_close, base_high=base_hi, base_low=base_lo,
        distribution_recent=res.distribution_recent,
    )

    # Spike-in-base means vol_z high while still inside the base
    # range — i.e. accumulation, not breakout-after-the-fact.
    res.spike_in_base = (
        res.vol_z is not None and res.vol_z >= 1.5
        and in_base and not res.distribution_recent
    )

    mfi_series = money_flow_index(data, mfi_period)
    if len(mfi_series.dropna()) >= 2:
        res.mfi = float(mfi_series.iloc[-1])
        res.mfi_rising = float(mfi_series.iloc[-1]) > float(mfi_series.iloc[-2])

    res.score = compute_score(res)
    return res


def compute_score(r: ScreenResult) -> float:
    if r.error or not r.poc or r.last_close is None:
        return 0.0

    # Phase weight
    phase_w = {
        "BASE_ABSORBING": 1.00,
        "BASE_BREAKOUT": 0.80,
        "BASE_QUIET": 0.55,
        "BASE_DECLINING": 0.35,
        "POST_RERATING": 0.05,
        "DISTRIBUTION_DRIVEN": 0.05,
        "DOWNTREND": 0.10,
        "NO_BASE": 0.10,
    }.get(r.phase, 0.10)

    # Catalyst weight (pre-rating pathways score higher)
    cat_w = {
        "STRATEGIC_REVIEW": 1.00,
        "ACTIVIST_TARGET": 0.90,
        "RETURN_OF_CAPITAL_LIVE": 0.80,
        "WIND_DOWN_LIKELY": 0.75,
        "WIND_DOWN_COMMITTED": 0.55,  # committed but often post-event on chart
        "STRUCTURAL_DISCOUNT": 0.40,
        "DISTRESSED": 0.10,
    }.get(r.catalyst, 0.30)

    # NAV reliability weight
    nav_w = {
        "LISTED_CLEAN": 1.00,
        "REAL_ASSET_OBSERVABLE": 0.90,
        "DEBT_AMORTISING": 0.85,
        "INFRA_DCF": 0.75,
        "RENEWABLES_DCF": 0.55,
        "PROPERTY_DCF": 0.55,
        "PRIVATE_EQUITY": 0.40,
        "DISTRESSED": 0.15,
    }.get(r.nav_quality, 0.50)

    # POC proximity scaled by base width — full credit when on POC,
    # zero when at the edge of the base. This stops names whose
    # accumulation has happened lower (price drifting up off POC) from
    # scoring zero just because they're > 10% off POC.
    pd_pct = r.poc_distance_pct or 1.0
    edge = max(r.base_range_pct or 0.10, 0.10)
    poc_w = max(0.0, 1.0 - (pd_pct / edge))

    # Base length — longer base = bigger setup
    bl = r.base_length_weeks or 0
    base_w = min(1.0, bl / 52)  # full credit at 1y+ base

    # Penalise post-rerating outright
    if r.phase == "POST_RERATING":
        return 0.0

    return phase_w * cat_w * nav_w * poc_w * base_w


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--range-threshold", type=float, default=0.30)
    parser.add_argument("--max-lookback", type=int, default=208)
    parser.add_argument("--mfi-period", type=int, default=18)
    parser.add_argument("--top", type=int, default=25)
    parser.add_argument("--tickers", nargs="*", default=None)
    parser.add_argument("--groups", nargs="*", default=None)
    args = parser.parse_args()

    if args.tickers:
        symbols = [t.upper() if "." in t else f"{t.upper()}.L" for t in args.tickers]
    elif args.groups:
        symbols = []
        for g in args.groups:
            for sym in KNOWN_CANDIDATES.get(g, []):
                if sym not in symbols:
                    symbols.append(sym)
    else:
        symbols = all_known_candidates()

    print(f"Screening {len(symbols)} tickers (range_threshold={args.range_threshold}, "
          f"max_lookback={args.max_lookback}, mfi={args.mfi_period})", file=sys.stderr)

    results: list[ScreenResult] = []
    for i, sym in enumerate(symbols, 1):
        r = screen_one(sym, max_lookback=args.max_lookback,
                       range_threshold=args.range_threshold,
                       mfi_period=args.mfi_period)
        results.append(r)
        tag = r.phase if not r.error else "ERR"
        print(f"  [{i:3d}/{len(symbols)}] {sym:<10} {tag:<22} "
              f"base={r.base_length_weeks or 0:>3}w "
              f"chg13={(r.chg_13w_pct or 0)*100:+5.1f}% "
              f"poc_d={(r.poc_distance_pct or 0)*100:5.1f}% "
              f"vol_z={r.vol_z if r.vol_z is not None else float('nan'):+5.2f} "
              f"score={r.score:.3f}",
              file=sys.stderr)
        time.sleep(0.1)

    df = pd.DataFrame([r.__dict__ for r in results])

    def show(title: str, frame: pd.DataFrame, n: int = 15) -> None:
        print(f"\n=== {title} ({len(frame)}) ===")
        if frame.empty:
            print("(none)")
            return
        cols = ["ticker", "phase", "catalyst", "nav_quality",
                "base_length_weeks", "base_range_pct", "chg_13w_pct",
                "poc_distance_pct", "vol_z", "mfi", "score"]
        cols = [c for c in cols if c in frame.columns]
        print(frame[cols].head(n).to_string(index=False))

    df_ranked = df[df["error"].isna()].sort_values("score", ascending=False)

    show("TIER 1 — BASE_ABSORBING (flat tape, vol building, on POC)",
         df_ranked[df_ranked["phase"] == "BASE_ABSORBING"], args.top)

    show("TIER 2 — BASE_BREAKOUT (just broken from base on vol)",
         df_ranked[df_ranked["phase"] == "BASE_BREAKOUT"], args.top)

    show("TIER 3 — BASE_QUIET (long base, on POC, awaiting vol bar)",
         df_ranked[df_ranked["phase"] == "BASE_QUIET"], args.top)

    show("TIER 4 — BASE_DECLINING (still finding the low)",
         df_ranked[df_ranked["phase"] == "BASE_DECLINING"], args.top)

    show("EXCLUDED — POST_RERATING (already moved 13w, late entry)",
         df[df["phase"] == "POST_RERATING"].sort_values("chg_13w_pct", ascending=False),
         args.top)

    show("EXCLUDED — DISTRIBUTION_DRIVEN (single-bar drop suggests cap-return)",
         df[df["phase"] == "DISTRIBUTION_DRIVEN"], args.top)

    show("OVERALL TOP BY SCORE",
         df_ranked.head(args.top), args.top)

    return 0


if __name__ == "__main__":
    sys.exit(main())
