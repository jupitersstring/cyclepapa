"""
Assembly-theoretic reading of the Godley framework.

Assembly theory (Cronin & Walker) characterises an object by two quantities:
its ASSEMBLY INDEX a -- the minimum number of joining operations needed to
construct it from elementary building blocks, permitting reuse of intermediates
-- and its COPY NUMBER n. Assembly is then

    A  =  sum_i  e^(a_i) * (n_i - 1) / N_T

and the claim is that a high assembly index occurring at high copy number
cannot be explained by chance: it implies SELECTION, a causal history that
made those particular objects rather than others.

WHY THIS FITS GODLEY (three genuine correspondences, not a metaphor):

1. STOCKS ARE ACCUMULATED FLOWS. This is Godley's second accounting principle.
   A balance sheet IS an assembly pathway -- today's debt stock is the
   accumulated record of the flows that built it, and cannot exist without
   them. Godley's "accounting system with no black holes" (WP 281) -- every row
   and column of the transactions matrix sums to zero, no stock without a
   traceable flow history -- is exactly an assembly-pathway validity condition.
   Quadruple-entry bookkeeping is the joining operation, and financial
   instruments are the reused intermediates: one sector's liability is another's
   asset, the same object serving twice.

2. MINSKY'S LADDER IS AN ASSEMBLY INDEX. Hedge finance requires ONE operation
   to sustain a position (income services it). Speculative requires TWO (income
   plus rollover). Ponzi requires THREE or more (income, rollover, and asset
   sale or fresh borrowing). Tymoigne's 0 / 0.5 / 1.0 fragility weights are a
   linearisation of what is really a count of construction steps -- so the
   assembly index recovers the structure Minsky described and grades it
   multiplicatively rather than linearly, which matters because each additional
   required operation is a separate point of failure.

3. COPY NUMBER IS THE SYSTEMIC DIMENSION A COUNTRY-BY-COUNTRY MODEL LACKS.
   Our configuration taxonomy already counts how many economies share a
   structure. Assembly theory says the danger is not a fragile structure but a
   fragile structure REPLICATED: e^a scaling means systemic exposure rises
   exponentially in the step-count and linearly in the copy number. This is the
   fallacy of composition given a magnitude -- if twelve economies are all in
   the savers-trap configuration, the world cannot resolve them all at once,
   and the assembly measure says how badly.

HONEST SCOPE. Assembly theory is a physics/chemistry framework; the mapping
here is a structured analogy with real formal content (a genuine minimal-step
count, a genuine copy number, the published A formula applied unchanged), not a
claim that economies are molecules. What it buys us is (a) a principled
reason to grade fragility multiplicatively, (b) a systemic aggregate our
country-wise model could not otherwise produce, and (c) a validity test on the
accounting that is Godley's own.
"""

from __future__ import annotations

import math

import pandas as pd

from . import configuration as CF
from . import minsky_fragility as MF
from .archetypes import COUNTRIES, lookup


# ---------------------------------------------------------------------------
# 1. Assembly index of a financing structure (Minsky's ladder as step-count)
# ---------------------------------------------------------------------------

# Operations required to SUSTAIN a position for one more period. Each is a
# distinct point of failure, which is why the measure is a count and not a
# score.
_OPERATIONS = {
    "income": "operating cash flow services the position",
    "rollover": "the liability must be refinanced at maturity",
    "asset_sale": "assets must be realised to meet obligations",
    "new_borrowing": "fresh credit is required to service existing credit",
    "fx_access": "foreign-currency funding must remain available",
}


def assembly_index(iso: str) -> dict:
    """
    Minimum number of operations required to sustain the sector's position --
    the Minsky ladder recovered as a construction step-count.

    hedge        a = 1   income alone
    speculative  a = 2   income + rollover
    ponzi        a = 3   income + rollover + (asset sale OR new borrowing)
    + 1          where foreign-currency funding is a separate dependency
                 (an FX-mismatched borrower needs one more thing to go right)
    """
    regime = MF.regime_label(iso)
    ops = ["income"]
    if regime in ("speculative", "ponzi"):
        ops.append("rollover")
    if regime == "ponzi":
        ops.append("new_borrowing")
    # an external-currency dependency is a genuinely separate operation
    c = lookup(iso)
    if c and c.primary == "I":                    # frontier dollar-dependent
        ops.append("fx_access")
    cfg = CF.configure(iso)
    if cfg and cfg["configuration"] == "external-dependent":
        if "fx_access" not in ops:
            ops.append("fx_access")
    return {"iso": iso, "assembly_index": len(ops), "operations": ops,
            "minsky_regime": regime}


# ---------------------------------------------------------------------------
# 2. Copy number: how widely is each configuration replicated?
# ---------------------------------------------------------------------------

def copy_numbers() -> dict:
    """Copy number of each Godley configuration across the panel."""
    p = CF.panel()
    if p.empty:
        return {}
    return p["configuration"].value_counts().to_dict()


# ---------------------------------------------------------------------------
# 3. Assembly A -- the systemic measure
# ---------------------------------------------------------------------------

def assembly(weighted: bool = True) -> dict:
    """
    A = sum_i e^(a_i) * (n_i - 1) / N_T, applied over CONFIGURATION classes.

    Objects are (configuration, assembly-index) classes; n_i is how many
    economies instantiate that class; a_i is the mean sustaining step-count of
    its members. The (n-1) term is the published form: a structure existing in
    a single copy carries no evidence of selection.

    Returns A, the per-class contributions, and the class contributing most --
    which is the systemically-loaded structure.
    """
    p = CF.panel()
    if p.empty:
        return {}
    rows = []
    for iso in p.index:
        ai = assembly_index(iso)
        rows.append({"iso": iso, "configuration": p.loc[iso, "configuration"],
                     "a": ai["assembly_index"]})
    df = pd.DataFrame(rows)
    N_T = len(df)
    contribs = {}
    for cfg, grp in df.groupby("configuration"):
        n = len(grp)
        a = float(grp["a"].mean())
        contribs[cfg] = {"copy_number": n, "mean_assembly_index": round(a, 2),
                         "contribution": round(math.exp(a) * (n - 1) / N_T, 3)}
    A = round(sum(v["contribution"] for v in contribs.values()), 3)
    worst = max(contribs.items(), key=lambda kv: kv[1]["contribution"])
    return {"assembly_A": A, "n_objects": N_T, "by_configuration": contribs,
            "most_loaded": worst[0],
            "reading": (
                f"A = {A}. The most systemically loaded structure is "
                f"'{worst[0]}' -- assembly index {worst[1]['mean_assembly_index']} "
                f"replicated across {worst[1]['copy_number']} economies. "
                "Assembly theory's claim is that a high step-count structure at "
                "high copy number is not chance but selection: these economies "
                "arrived at the same configuration because the same forces put "
                "them there, and they cannot all exit it simultaneously.")}


# ---------------------------------------------------------------------------
# 4. Assembly-pathway validity -- Godley's "no black holes", as a test
# ---------------------------------------------------------------------------

def pathway_check(iso: str) -> dict | None:
    """
    Is the current stock reconstructible from its own flow history? In assembly
    terms: does the object have a valid construction pathway, or does part of it
    appear from nowhere?

    Godley's test (WP 281): the world/stock identity is deliberately left OUT of
    the solved system and used as a diagnostic. Here we cumulate the current-
    account flow history and compare the implied external stock change with the
    flows that are supposed to have produced it. A large residual means either
    revaluation (legitimate -- capital gains are in the revaluation account, not
    the transactions account) or a measurement black hole.
    """
    path = CF.balance_path(iso)
    if path is None or len(path) < 10:
        return None
    from . import godley_projection as GP
    ca = -path["foreign"]                       # current account = -(RoW balance)
    cumulated = float(ca.sum())
    yrs = f"{int(path.index[0])}-{int(path.index[-1])}"
    g = next((x for x in GP._INPUTS if x.iso == iso), None)
    niip = float(g.niip_pct_gdp) if g else None
    gap = round(niip - cumulated, 1) if niip is not None else None
    verdict = None
    if gap is not None:
        if abs(gap) < 25:
            verdict = "pathway reconciles: stock ≈ cumulated flows"
        elif gap < 0:
            verdict = (f"VALUATION LOSS of {abs(gap):.0f}pp of GDP -- the country "
                       "saved abroad and has less to show for it than the flows "
                       "imply. A flow-only projection will OVER-state its stock.")
        else:
            verdict = (f"VALUATION GAIN of {gap:.0f}pp of GDP -- the stock exceeds "
                       "cumulated flows; a flow-only projection UNDER-states it.")
    return {"iso": iso, "years": yrs,
            "cumulated_ca_pct_gdp": round(cumulated, 1),
            "actual_niip_pct_gdp": niip,
            "revaluation_gap_pct_gdp": gap,
            "verdict": verdict,
            "note": ("the external stock must equal cumulated flows PLUS "
                     "revaluations; the gap isolates the revaluation channel that "
                     "the transactions account excludes by construction"),
            "caveat": ("the gap is revaluation PLUS a denominator effect: summing "
                       "annual flows expressed as %-of-that-year's-GDP and "
                       "comparing with a current-year stock over-weights early "
                       "flows wherever nominal GDP has grown a lot (Singapore, "
                       "Malaysia). To isolate pure revaluation, cumulate in USD "
                       "levels and compare with the USD stock. Read the ranking "
                       "as indicative of where the revaluation channel matters, "
                       "not as a measured valuation loss.")}


def pathway_panel() -> pd.DataFrame:
    """Flow-vs-stock reconciliation across the panel -- the black-hole test."""
    rows = []
    for c in COUNTRIES:
        r = pathway_check(c.iso)
        if r and r["revaluation_gap_pct_gdp"] is not None:
            rows.append({"iso": c.iso, "country": c.name,
                         "cumulated_ca": r["cumulated_ca_pct_gdp"],
                         "actual_niip": r["actual_niip_pct_gdp"],
                         "reval_gap": r["revaluation_gap_pct_gdp"]})
    return (pd.DataFrame(rows).set_index("iso")
            .sort_values("reval_gap") if rows else pd.DataFrame())


def assembly_fragility(iso: str) -> float | None:
    """
    Fragility graded MULTIPLICATIVELY in the step-count, the assembly-compatible
    form of Tymoigne's index.

    Tymoigne weights hedge/speculative/Ponzi 0 / 0.5 / 1.0 -- linear in the
    ladder. But each additional operation required to sustain a position is a
    separate, independently-failing dependency, so the exposure compounds rather
    than adds. Assembly theory's e^a scaling is the principled form:

        assembly_fragility = (e^(a-1) - 1) / (e^(a_max-1) - 1)

    normalised to [0,1] over a_max = 4, so it stays comparable with the existing
    index while grading the tail correctly: going from 2 to 3 required
    operations is a bigger deterioration than 1 to 2.
    """
    ai = assembly_index(iso)
    a = ai["assembly_index"]
    a_max = 4
    num = math.exp(a - 1) - 1
    den = math.exp(a_max - 1) - 1
    return round(min(1.0, num / den), 3)


def compatibility_audit() -> dict:
    """
    Does the implementation satisfy the assembly-theoretic requirements?

    R1 PATHWAY VALIDITY -- every stock reconstructible from its flow history,
       no object appearing from nowhere (Godley's "no black holes").
    R2 CONSERVED JOINING OPERATIONS -- the joining operation (quadruple-entry)
       must conserve: the balances sum to zero at every point.
    R3 REUSE OF INTERMEDIATES -- the same instrument serves as one sector's
       asset and another's liability, counted once.
    R4 MULTIPLICATIVE GRADING IN STEP-COUNT -- fragility must compound in the
       number of required operations, not add.
    R5 COPY NUMBER CARRIED -- the systemic dimension must be represented, not
       just the per-object index.
    """
    p = CF.panel()
    # R2: does the identity close for every country?
    closes = 0
    total = 0
    for iso in p.index:
        cfg = CF.configure(iso)
        if not cfg:
            continue
        total += 1
        s = cfg["private"] + cfg["government"] + cfg["foreign"]
        if abs(s) < 0.15:
            closes += 1
    return {
        "R1_pathway_validity": {
            "status": "SATISFIED (partial)",
            "how": "balance_path() reconstructs all three balances from IMF flow "
                   "history; godley_projection cumulates flows into the external "
                   "stock. GAP: the projection omits revaluations, so the stock "
                   "path is flow-only -- legitimate capital gains are "
                   "indistinguishable from a black hole.",
        },
        "R2_conserved_joining": {
            "status": f"SATISFIED ({closes}/{total} identities close to <0.15pp)",
            "how": "the three balances are constructed to sum to zero and are "
                   "checked; sfc_integrity carries per-country tolerance bands.",
        },
        "R3_reuse_of_intermediates": {
            "status": "SATISFIED",
            "how": "one sector's liability is another's asset by construction -- "
                   "foreign = -(current account), private = residual. No "
                   "double-counting.",
        },
        "R4_multiplicative_grading": {
            "status": "NOW SATISFIED",
            "how": "assembly_fragility() grades e^(a-1); the legacy "
                   "minsky_fragility index remains linear (Tymoigne form) and is "
                   "retained for comparability.",
        },
        "R5_copy_number": {
            "status": "NOW SATISFIED",
            "how": "copy_numbers() and assembly() carry the configuration copy "
                   "number and compute A = sum e^a (n-1)/N_T.",
        },
    }


def panel() -> pd.DataFrame:
    """Assembly index and operations for every country."""
    rows = []
    for c in COUNTRIES:
        ai = assembly_index(c.iso)
        cfg = CF.configure(c.iso)
        rows.append({"iso": c.iso, "country": c.name,
                     "configuration": cfg["configuration"] if cfg else None,
                     "assembly_index": ai["assembly_index"],
                     "minsky": ai["minsky_regime"],
                     "operations": ", ".join(ai["operations"])})
    return (pd.DataFrame(rows).set_index("iso")
            .sort_values("assembly_index", ascending=False))
