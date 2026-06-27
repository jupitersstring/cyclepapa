"""
Godley Bull-Market Scanner -- Streamlit dashboard.

Run:  streamlit run scanner/app.py

Renders:
  1. The ranked Opportunity scorecard (all countries).
  2. Top opportunities and the avoid-list with the reasoning note.
  3. The nine-panel archetype grid (factor z-scores by archetype).
  4. The sectoral-identity reminder and factor-weight transparency.
"""

from __future__ import annotations

import pandas as pd

from .archetypes import ARCHETYPES, COUNTRIES, lookup, by_archetype
from .composite import (
    WEIGHTS, score_panel, top_opportunities, avoid_list,
)
from .data import default_panel, FACTOR_COLUMNS
from . import kalecki_levy as KL
from . import seven_processes as SEVEN
from . import godley_projection as GP
from . import tobin_q as TQ


def build_scored(panel: pd.DataFrame | None = None) -> pd.DataFrame:
    """Score the panel; attach country names + archetype tags for display."""
    panel = default_panel() if panel is None else panel
    archetype_of = {c.iso: c.primary for c in COUNTRIES}
    scored = score_panel(panel, archetype_of)
    scored.insert(0, "country", [lookup(i).name if lookup(i) else i for i in scored.index])
    scored.insert(1, "archetype", [archetype_of.get(i, "?") for i in scored.index])
    scored.insert(2, "etf", [lookup(i).etf if lookup(i) else None for i in scored.index])
    return scored


def build_kalecki_table() -> pd.DataFrame:
    """Per-country Kalecki-Levy profit-source decomposition."""
    comp = KL.components_df()
    comp.insert(0, "country",
                [lookup(i).name if lookup(i) else i for i in comp.index])
    comp["profit_fuel"] = KL.profit_fuel(comp)
    return comp.sort_values("profit_fuel", ascending=False)


def build_seven_processes_table() -> pd.DataFrame:
    """Run Godley's 1999 seven-flag diagnostic over the cross-section."""
    panel = default_panel()
    components = KL.components_df()
    flags = SEVEN.diagnose(panel, components)
    flags.insert(0, "country",
                 [lookup(i).name if lookup(i) else i for i in flags.index])
    return flags.sort_values("flags_lit", ascending=False)


def _run_streamlit() -> None:
    import streamlit as st

    st.set_page_config(page_title="Godley Bull-Market Scanner", layout="wide")
    st.title("Godley Bull-Market Scanner")
    st.caption(
        "Stock-flow-consistent regime detection. Identity: (G-T) == (S-I) + (M-X). "
        "Asset prices rise where net new financing into private balance sheets is "
        "expanding and accelerating -- and where that fuel is not already priced in."
    )

    scored = build_scored()

    # --- Headline opportunities ------------------------------------------
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("Top opportunities")
        st.dataframe(
            top_opportunities(scored, 5)[["country", "archetype", "etf",
                                          "opportunity", "regime", "note"]],
            use_container_width=True, hide_index=True,
        )
    with c2:
        st.subheader("Avoid / crowded")
        st.dataframe(
            avoid_list(scored, 5)[["country", "archetype", "etf",
                                   "opportunity", "regime", "note"]],
            use_container_width=True, hide_index=True,
        )

    # --- Full scorecard ---------------------------------------------------
    st.subheader("Full scorecard")
    show = scored[["country", "archetype", "etf"] + FACTOR_COLUMNS +
                  ["opportunity", "percentile", "regime", "estimated"]]
    st.dataframe(
        show.style.background_gradient(subset=["opportunity"], cmap="RdYlGn"),
        use_container_width=True, hide_index=True,
    )

    # --- Kalecki-Levy profit decomposition --------------------------------
    st.subheader("Kalecki-Levy profit-source decomposition")
    st.caption(
        "Profits = Investment + GovtDeficit + NetExports + Dividends - HouseholdSaving  "
        "(after Levy Forecasting Center, Where Profits Come From, 2008)"
    )
    kl = build_kalecki_table()
    st.dataframe(
        kl[["country", "investment", "govt_deficit", "net_exports",
            "dividends", "household_saving", "profit_fuel", "note"]]
          .style.background_gradient(subset=["profit_fuel"], cmap="RdYlGn"),
        use_container_width=True, hide_index=True,
    )

    # --- Policy registry (qualitative leg) --------------------------------
    st.subheader("Named-policy registry (qualitative leg)")
    st.caption(
        "Legislative/fiscal events mapped to the Kalecki-Levy lever they pull. "
        "weighted_impulse = sign x magnitude(pp GDP) x status_weight"
    )
    policies = KL.policies_df()
    policies = policies.merge(
        pd.DataFrame({"iso": [c.iso for c in COUNTRIES],
                      "country": [c.name for c in COUNTRIES]}),
        on="iso", how="left",
    )
    st.dataframe(
        policies[["country", "name", "lever", "sign", "magnitude_pp",
                  "status", "weighted_impulse", "source", "note"]]
          .sort_values("weighted_impulse", ascending=False),
        use_container_width=True, hide_index=True,
    )

    # --- Seven Unsustainable Processes diagnostic -------------------------
    st.subheader("Godley's Seven Unsustainable Processes (1999) -- live diagnostic")
    labels = SEVEN.label_names()
    with st.expander("What each flag tests"):
        for k, v in labels.items():
            st.write(f"**{k}** -- {v}")
    sp = build_seven_processes_table()
    st.dataframe(
        sp.style.background_gradient(subset=["flags_lit"], cmap="Reds"),
        use_container_width=True, hide_index=True,
    )

    # --- Archetype grid ---------------------------------------------------
    st.subheader("Archetype grid")
    groups = by_archetype()
    for tag, arc in ARCHETYPES.items():
        members = groups.get(tag, [])
        if not members:
            continue
        with st.expander(f"{tag} -- {arc.name}  ({len(members)} countries)"):
            st.caption(f"Signature: {arc.signature}  |  Adjustment: {arc.adjustment}")
            isos = [c.iso for c in members]
            sub = scored.loc[scored.index.isin(isos),
                             ["country", "opportunity", "regime", "note"]]
            st.dataframe(sub, use_container_width=True, hide_index=True)

    # --- Weights transparency --------------------------------------------
    with st.sidebar:
        st.header("Factor weights")
        for k, v in WEIGHTS.items():
            st.write(f"`{v:+.2f}`  {k}")
        st.caption("Negative weights (crowding, sudden-stop) are what separate "
                   "a flow from an opportunity.")


def main_cli() -> None:
    """Print the scorecard to stdout (no Streamlit needed)."""
    scored = build_scored()
    cols = ["country", "archetype", "etf", "opportunity", "regime"]
    pd.set_option("display.max_rows", None, "display.width", 160)
    print("\n=== TOP OPPORTUNITIES ===")
    print(top_opportunities(scored, 6)[cols + ["note"]].to_string(index=False))
    print("\n=== AVOID / CROWDED ===")
    print(avoid_list(scored, 5)[cols + ["note"]].to_string(index=False))

    print("\n=== KALECKI-LEVY PROFIT-SOURCE DECOMPOSITION (top 12) ===")
    kl = build_kalecki_table().head(12)
    print(kl[["country", "investment", "govt_deficit", "net_exports",
              "dividends", "household_saving", "profit_fuel", "note"]]
          .to_string(index=False))

    print("\n=== KALECKI-LEVY PROFIT-DRAGS (bottom 6) ===")
    kl_bottom = build_kalecki_table().tail(6).iloc[::-1]
    print(kl_bottom[["country", "investment", "govt_deficit", "net_exports",
                     "dividends", "household_saving", "profit_fuel", "note"]]
          .to_string(index=False))

    print("\n=== GODLEY SEVEN UNSUSTAINABLE PROCESSES (countries with >=3 flags) ===")
    sp = build_seven_processes_table()
    print(sp[sp["flags_lit"] >= 3][["country", "P1", "P2", "P3", "P4",
                                    "P5", "P6", "P7", "flags_lit",
                                    "godley_warning"]]
          .to_string(index=False))

    print("\n=== REGIME OVERLAY (Keen / Dalio / Marathon / Napier / NBFI) ===")
    cols = ["country", "dalio_stage", "keen_accel", "marathon_squeeze",
            "napier_repression", "nbfi_leverage", "tobin_q", "q_investment_adj",
            "data_confidence", "opportunity", "regime"]
    print(scored[cols].head(15).to_string(index=False))

    print("\n=== GODLEY 5-YR NIIP PROJECTION (most explosive trajectories) ===")
    gp = GP.panel_scores().head(10)
    print(gp[["niip_start", "niip_terminal", "deterioration_pp",
              "unsustainability", "godley_explosive"]].to_string())

    print("\n=== TOBIN'S Q (cross-section) ===")
    qp = TQ.panel_q().head(15)
    print(qp[["market_cap_pct_gdp", "nfc_debt_pct_gdp",
              "replacement_k_pct_gdp", "q_enterprise"]].to_string())

    print("\n=== MINSKY FINANCIAL FRAGILITY (Tymoigne WP 654) -- most fragile ===")
    from . import minsky_fragility as MF
    print(MF.panel().head(10)[["hedge", "speculative", "ponzi",
                               "fragility", "minsky_regime", "note"]].to_string())

    print("\n=== STRATEGIC ANALYSIS: required-private-balance test (Levy SA method) ===")
    from . import strategic_analysis as SA
    sap = SA.panel()
    imp = sap[sap["implausible"]]
    print(f"  {len(imp)} of {len(sap)} countries: trend+1pp growth requires an IMPLAUSIBLE private balance.")
    if len(imp):
        print(imp[["country", "archetype", "fiscal_balance",
                   "priv_balance_now", "priv_balance_required",
                   "direction"]].to_string())
    print("\n  Germany scenario grid (the Maastricht surplus-trap):")
    print("  " + SA.scenarios("DE").to_string(index=False).replace("\n", "\n  "))

    print("\n=== ANOMALIES ===")
    from . import anomalies as AN
    breadth = AN.private_surplus_breadth()
    print(f"  Paradox-of-thrift breadth: {breadth['of_which_private_surplus']}/"
          f"{breadth['deficit_archetype_countries']} deficit-archetype economies "
          f"({int(breadth['share']*100)}%) now run PRIVATE SURPLUSES "
          f"-- Godley's synchronised-net-saving recession setup.")
    shifts = AN.minsky_regime_shifts()
    if len(shifts):
        print("  Minsky regime shifts (bull composite but Ponzi/speculative financing):")
        print(shifts[["country", "minsky_regime", "fragility", "anomaly"]].to_string(index=False))
    sfc = AN.sfc_inconsistency()
    contrarian = sfc[sfc["severity"] == "CONTRARIAN"] if len(sfc) else sfc
    if len(contrarian):
        print("  Contrarian SFC posture (against the global surplus tilt):")
        print(contrarian[["country", "archetype", "implied_private_balance",
                          "anomaly"]].to_string(index=False))


if __name__ == "__main__":
    try:
        import streamlit  # noqa: F401
        from streamlit.runtime.scriptrunner import get_script_run_ctx
        if get_script_run_ctx() is not None:
            _run_streamlit()
        else:
            main_cli()
    except Exception:
        main_cli()
