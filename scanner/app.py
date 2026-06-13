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


def build_scored(panel: pd.DataFrame | None = None) -> pd.DataFrame:
    """Score the panel; attach country names + archetype tags for display."""
    panel = default_panel() if panel is None else panel
    archetype_of = {c.iso: c.primary for c in COUNTRIES}
    scored = score_panel(panel, archetype_of)
    scored.insert(0, "country", [lookup(i).name if lookup(i) else i for i in scored.index])
    scored.insert(1, "archetype", [archetype_of.get(i, "?") for i in scored.index])
    scored.insert(2, "etf", [lookup(i).etf if lookup(i) else None for i in scored.index])
    return scored


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
    pd.set_option("display.max_rows", None, "display.width", 140)
    print("\n=== TOP OPPORTUNITIES ===")
    print(top_opportunities(scored, 6)[cols + ["note"]].to_string(index=False))
    print("\n=== AVOID / CROWDED ===")
    print(avoid_list(scored, 5)[cols + ["note"]].to_string(index=False))
    print("\n=== FULL RANKING ===")
    print(scored[cols].to_string(index=False))


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
