"""
Anomaly detection.

Four classes of anomaly, each answering a different question:

  1. CALIBRATION-vs-LIVE divergence -- where the model's hand-calibrated input
     disagrees with the live print (World Bank / IMF). These are the inputs
     most in need of correction; a large gap means the scanner is acting on a
     stale or wrong assumption.

  2. CROSS-SECTIONAL outliers -- countries whose factor reading is an extreme
     z-score vs the panel. Godley's method is precisely about spotting the
     configuration that "cannot persist"; the statistical outlier is the
     first place to look.

  3. SFC INCONSISTENCY -- where the three-balance identity, reconstructed from
     live data (fiscal + current-account => implied private balance), produces
     a private-sector posture that contradicts the model's archetype. A
     country we class as "mercantilist saver" whose live data implies a
     private deficit is an anomaly worth investigating.

  4. MINSKY REGIME SHIFT -- countries whose fragility index has crossed into
     speculative/Ponzi territory while still carrying a bull composite. The
     2004-07-US-housing pattern: profits look fine, financing posture does not.

Godley's own record (per the literature) is the warrant for this module: his
hits came from spotting *internal inconsistency* in a growth path; his misses
came from *timing* and from *directed-credit* economies that evade the
identity. So we report anomalies as flags to investigate, never as timed
calls, and we down-weight the directed-credit (F) and sanctioned (X)
archetypes where the data itself is suspect.
"""

from __future__ import annotations

import pandas as pd

from . import app as _app  # build_scored
from . import kalecki_levy as KL
from . import minsky_fragility as MF
from .archetypes import COUNTRIES, lookup
from .sources import live


# Map model fields -> live fields for the calibration-vs-live check.
# model credit_impulse is a YoY-change impulse; live domestic_credit_priv is a
# LEVEL (%GDP) -- not directly comparable, so we compare the model's directional
# calibration against the live level's deviation from the panel median instead.
_ARCHETYPE_PRIVATE_POSTURE = {
    # archetype -> expected sign of private-sector balance (S - I)
    "A": "deficit",     # reserve absorber: private oscillates, often deficit
    "B": "deficit",     # Anglo-mimic: household-leveraged
    "C": "surplus",     # mercantilist saver
    "D": "surplus",     # entrepot
    "E": "surplus",     # EMU trap
    "F": "surplus",     # directed-credit (high household saving)
    "G": "surplus",     # commodity rent
    "H": "deficit",     # convergence importer (productive deficit)
    "I": "deficit",     # frontier
    "X": "surplus",     # sanctioned (autarkic surplus)
}


def calibration_vs_live() -> pd.DataFrame:
    """
    Class 1: where calibrated valuation_gap / credit direction disagrees with
    the live World Bank prints. Uses market_cap (%GDP) and domestic credit
    (%GDP) as the live anchors.
    """
    livedf = live.load_cached()
    if livedf is None:
        return pd.DataFrame()
    scored = _app.build_scored()
    rows = []
    # Live market cap %GDP -> a valuation reference. Cross-sectional rank.
    mc = livedf["market_cap"].dropna()
    mc_rank = mc.rank(pct=True)
    cr = livedf["domestic_credit_priv"].dropna()
    cr_rank = cr.rank(pct=True)
    for iso in scored.index:
        if iso not in livedf.index:
            continue
        row = scored.loc[iso]
        flags = []
        # Tobin q vs live market cap: if model q is low (cheap) but live
        # market-cap/GDP is top-quartile, that's a tension.
        if iso in mc_rank.index:
            if row["tobin_q"] < 0.85 and mc_rank[iso] > 0.75:
                flags.append(f"model q cheap ({row['tobin_q']:.2f}) but live mktcap/GDP top-quartile")
            if row["tobin_q"] > 1.25 and mc_rank[iso] < 0.30:
                flags.append(f"model q rich ({row['tobin_q']:.2f}) but live mktcap/GDP bottom-tercile")
        # Credit: model credit_impulse strongly positive but live credit/GDP
        # very low (room to grow -> consistent) vs very high (late-cycle).
        if iso in cr_rank.index and row["credit_impulse"] > 1.0 and cr_rank[iso] > 0.85:
            flags.append(f"strong credit impulse into already-high credit/GDP (top 15%) -- late-cycle")
        if flags:
            rows.append({"iso": iso, "country": row["country"],
                         "archetype": row["archetype"],
                         "live_mktcap_gdp": round(mc.get(iso, float("nan")), 1),
                         "live_credit_gdp": round(cr.get(iso, float("nan")), 1),
                         "anomaly": " ; ".join(flags)})
    return pd.DataFrame(rows)


def cross_sectional_outliers(z_thresh: float = 2.0) -> pd.DataFrame:
    """Class 2: factor z-scores beyond +/- z_thresh."""
    scored = _app.build_scored()
    factor_cols = ["profit_fuel", "credit_impulse", "valuation_gap",
                   "carry_cushion", "crowding", "suddenstop_risk"]
    rows = []
    for iso in scored.index:
        row = scored.loc[iso]
        for c in factor_cols:
            v = row.get(c)
            if pd.notna(v) and abs(v) >= z_thresh:
                rows.append({"iso": iso, "country": row["country"],
                             "archetype": row["archetype"], "factor": c,
                             "z": round(float(v), 2),
                             "direction": "extreme high" if v > 0 else "extreme low"})
    return pd.DataFrame(rows).sort_values("z", key=lambda s: s.abs(), ascending=False) \
        if rows else pd.DataFrame()


def sfc_inconsistency() -> pd.DataFrame:
    """
    Class 3: reconstruct the private balance from live data
    (private = -fiscal + current_account, in net-lending sign convention)
    and flag where its sign contradicts the archetype's expected posture.

    Uses live IMF CA + fiscal where available; falls back to the calibrated
    godley_projection inputs (fiscal_balance_path + goods_and_transfers) so
    the check runs even before the live IMF pull completes.
    """
    from . import godley_projection as GP
    livedf = live.load_cached()
    rows = []
    isos = list(livedf.index) if livedf is not None else [c.iso for c in COUNTRIES]
    gp_inputs = {g.iso: g for g in GP._INPUTS}
    for iso in isos:
        c = lookup(iso)
        if c is None:
            continue
        fiscal = ca = None
        if livedf is not None and iso in livedf.index:
            fiscal = livedf.loc[iso, "fiscal_balance"]
            ca = livedf.loc[iso, "ca_balance"]
        # Fallback to calibrated godley_projection inputs
        if (pd.isna(fiscal) if fiscal is not None else True) or \
           (pd.isna(ca) if ca is not None else True):
            g = gp_inputs.get(iso)
            if g is None:
                continue
            fiscal = g.fiscal_balance_path           # already (G-T)<0 sign as net lending
            # implied CA = goods+transfers + NII(r_ext*NIIP)
            ca = g.goods_and_transfers + g.r_ext * g.niip_pct_gdp / 100.0
        if pd.isna(fiscal) or pd.isna(ca):
            continue
        # Three-balance identity: private NL = -(govt NL) + CA ... in the
        # convention (G-T) = (S-I) + (M-X):  private(S-I) = -(govt balance) + CA
        # govt balance here is net lending (negative = deficit = (G-T)>0).
        # private_balance = govt_deficit + CA_surplus
        govt_deficit = -float(fiscal)          # positive = deficit
        private_balance = govt_deficit + float(ca)
        posture = "surplus" if private_balance > 0 else "deficit"
        expected = _ARCHETYPE_PRIVATE_POSTURE.get(c.primary)
        # Only flag the genuinely surprising / large deviations. A small
        # contradiction is noise; the signal is (a) a large private surplus in
        # a deficit-archetype (the Godley 'everyone net-saving' trap) or (b) a
        # private DEFICIT in a saver/EMU archetype (going against the global
        # post-2022 surplus tilt -- genuinely odd).
        surprise = posture != expected and abs(private_balance) >= 2.5
        contrarian = posture == "deficit" and expected == "surplus"  # rarer, more telling
        if surprise or contrarian:
            rows.append({"iso": iso, "country": c.name, "archetype": c.primary,
                         "live_fiscal": round(float(fiscal), 1),
                         "live_ca": round(float(ca), 1),
                         "implied_private_balance": round(private_balance, 1),
                         "implied_posture": posture,
                         "archetype_expects": expected,
                         "severity": "CONTRARIAN" if contrarian else "trap-tilt",
                         "anomaly": f"private {posture} ({private_balance:+.1f}% GDP), archetype expects {expected}"})
    df = pd.DataFrame(rows)
    return df.sort_values("implied_private_balance", ascending=False) if len(df) else df


def private_surplus_breadth() -> dict:
    """
    Headline statistic: across deficit-archetype economies (A/B/H/I), what
    share now show an IMPLIED PRIVATE SURPLUS? A high share is Godley's
    'failure of the paradox of thrift' -- the configuration that precedes
    synchronised recession (every private sector trying to net-save at once).
    """
    from . import godley_projection as GP
    livedf = live.load_cached()
    gp_inputs = {g.iso: g for g in GP._INPUTS}
    deficit_arch = {"A", "B", "H", "I"}
    total = surplus = 0
    for c in COUNTRIES:
        if c.primary not in deficit_arch:
            continue
        fiscal = ca = None
        if livedf is not None and c.iso in livedf.index:
            fiscal = livedf.loc[c.iso, "fiscal_balance"]
            ca = livedf.loc[c.iso, "ca_balance"]
        if (pd.isna(fiscal) if fiscal is not None else True):
            g = gp_inputs.get(c.iso)
            if not g:
                continue
            fiscal = g.fiscal_balance_path
            ca = g.goods_and_transfers + g.r_ext * g.niip_pct_gdp / 100.0
        if pd.isna(fiscal) or pd.isna(ca):
            continue
        total += 1
        if (-float(fiscal)) + float(ca) > 0:
            surplus += 1
    return {"deficit_archetype_countries": total,
            "of_which_private_surplus": surplus,
            "share": round(surplus / total, 2) if total else None}


def minsky_regime_shifts() -> pd.DataFrame:
    """
    Class 4: countries that are bull-rated by the composite but have crossed
    into speculative/Ponzi financing territory (the 2004-07 US-housing tell).
    """
    scored = _app.build_scored()
    frag = MF.panel()
    rows = []
    for iso in scored.index:
        if iso not in frag.index:
            continue
        regime = scored.loc[iso, "regime"]
        m = frag.loc[iso, "minsky_regime"]
        fragility = frag.loc[iso, "fragility"]
        if regime == "bull" and m in ("ponzi", "speculative") and fragility >= 0.35:
            rows.append({"iso": iso, "country": scored.loc[iso, "country"],
                         "composite_regime": regime, "minsky_regime": m,
                         "fragility": fragility,
                         "anomaly": f"BULL composite but {m} financing (fragility {fragility:.2f})"})
    return pd.DataFrame(rows).sort_values("fragility", ascending=False) if rows else pd.DataFrame()


def report() -> dict[str, pd.DataFrame]:
    """Run all four anomaly classes."""
    return {
        "calibration_vs_live": calibration_vs_live(),
        "cross_sectional_outliers": cross_sectional_outliers(),
        "sfc_inconsistency": sfc_inconsistency(),
        "minsky_regime_shifts": minsky_regime_shifts(),
    }
