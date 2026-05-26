"""
Streamlit UI for the Crypto MR engine (TD Sequential leg).

Mirrors the Pine v5 "Enhanced MTF TD Sequential" panel: Inputs tab for
timeframe selection and methodology toggles, Style tab for which Net
measures appear in the rank. Per the user-supplied screenshots, only the
ticked measures (Net Signal, Net Setup, Net Countdown, Net Perfect,
Net Stealth Setup, Net Triple Setup) drive the final rank; the unticked
measures (Composite, Composite Z-Score, Aggressive, Recycle, Price Flip,
Double Setup) are computed but excluded from the rank.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

import mr_engine as mre


PINE_DEFAULT_TFS = [
    ("1m",  "1m",  True),
    ("5m",  "5m",  True),
    ("15m", "15m", True),
    ("1h",  "60m", True),
    ("4h",  "4h",  True),
    ("1d",  "1d",  True),
    ("1w",  "1wk", True),
    ("1mo", "1mo", True),   # extension beyond the Pine's 7 → monthly
]


def main() -> None:
    st.set_page_config(page_title="Crypto MR Engine — TD Sequential", layout="wide")
    st.title("Crypto MR Engine — TD Sequential (MTF)")

    with st.sidebar:
        st.header("Symbol")
        symbol = st.text_input("Crypto ticker (yfinance)", value="BTC-USD")

        st.header("Inputs")
        tfs: list[tuple[str, str]] = []
        for label, interval, default in PINE_DEFAULT_TFS:
            if st.checkbox(label, value=default, key=f"tf_{label}"):
                tfs.append((label, interval))

        st.subheader("Methodology toggles")
        # These match the "Show X" toggles in the Pine Inputs tab. They are
        # all on by default per the user's screenshots and do not change the
        # computation — only what the engine surfaces is governed by the
        # Style ticks below.
        for k, lbl in [
            ("perfection", "Show Setup Perfection"),
            ("aggressive", "Show Aggressive Counts"),
            ("price_flip", "Show Price Flip"),
            ("risk_lines", "Show Risk Lines"),
            ("stealth", "Show Stealth Setups"),
            ("double", "Show Double Setups"),
            ("triple", "Show Triple Setups"),
        ]:
            st.checkbox(lbl, value=True, key=f"show_{k}", disabled=True)

        st.subheader("Numeric inputs")
        st.number_input("Volume Confirmation Threshold", value=mre.VOLUME_THRESHOLD, step=0.1, disabled=True)
        st.number_input("Fibonacci Factor for Recycling", value=mre.FIB_FACTOR, step=0.001, disabled=True)
        st.number_input("Risk Factor", value=mre.RISK_FACTOR, step=0.1, disabled=True)

        st.header("Style — measures in the rank")
        # The "ticked" set per the Style-tab screenshot.
        ticked = {
            "setup":      st.checkbox("Net Setup",         value=True),
            "countdown":  st.checkbox("Net Countdown",     value=True),
            "perfect":    st.checkbox("Net Perfect",       value=True),
            "stealth":    st.checkbox("Net Stealth Setup", value=True),
            "triple":     st.checkbox("Net Triple Setup",  value=True),
        }
        with st.expander("Unticked (computed, not in rank)"):
            st.checkbox("Net Composite",         value=False, disabled=True)
            st.checkbox("Net Composite Z-Score", value=False, disabled=True)
            st.checkbox("Net Aggressive",        value=False, disabled=True)
            st.checkbox("Net Recycle",           value=False, disabled=True)
            st.checkbox("Net Price Flip",        value=False, disabled=True)
            st.checkbox("Net Double Setup",      value=False, disabled=True)
        show_background = st.checkbox("Background Color", value=True)

        run = st.button("Run engine", type="primary")

    if not run:
        st.info("Configure the symbol and timeframes, then click **Run engine**.")
        return

    active_measures = tuple(m for m, on in ticked.items() if on)
    if not active_measures:
        st.warning("Tick at least one measure under Style to produce a rank.")
        return

    with st.spinner(f"Fetching multi-timeframe data for {symbol}…"):
        raw = mre.fetch_multitf(symbol, timeframes=tfs)
    if not raw:
        st.error(f"No OHLCV data fetched for {symbol}.")
        return

    per_tf = {label: mre.td_sequential(df) for label, df in raw.items() if len(df) > 30}
    if not per_tf:
        st.error("Not enough bars on any timeframe to compute TD Sequential.")
        return

    # Patch the active set into the engine's TICKED_MEASURES for this run so
    # the user's Style choices flow through.
    mre.TICKED_MEASURES = active_measures  # type: ignore[assignment]

    result = mre.aggregate_across_tfs(per_tf)
    history = mre.aggregate_history(per_tf)

    # --- Headline rank --------------------------------------------------
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Net Signal (MR rank)", f"{result.net_signal:+.2f}")
    c2.metric("Bullish Signal",       f"{result.bullish_signal:.2f}")
    c3.metric("Bearish Signal",       f"{result.bearish_signal:.2f}")
    c4.metric("Vol-confirmed %",      f"{result.volume_confirmed_prop:.1f}%")

    direction = "BULLISH" if result.net_signal > 0 else "BEARISH" if result.net_signal < 0 else "NEUTRAL"
    if show_background:
        tint = "#1b5e20" if result.net_signal > 0 else "#7f1d1d" if result.net_signal < 0 else "#374151"
        st.markdown(
            f"<div style='background:{tint};padding:8px;border-radius:6px;color:white'>"
            f"<b>MR bias: {direction}</b></div>",
            unsafe_allow_html=True,
        )

    # --- Per-timeframe rank --------------------------------------------
    st.subheader("Per-timeframe rank")
    st.caption("Net per measure = (buy% − sell%) using Pine-style proportions. `net_signal` averages the ticked measures.")
    st.dataframe(mre.rank_table(result), use_container_width=True, hide_index=True)

    # --- Full methodology (every measure) ------------------------------
    with st.expander("Full methodology table (all measures, including unticked)"):
        st.dataframe(mre.full_methodology_table(result), use_container_width=True, hide_index=True)

    # --- History plot ---------------------------------------------------
    st.subheader("Net signal — historical (highest-freq grid)")
    cols_plot = ["net_signal"] + [f"net_{m}" for m in active_measures]
    st.line_chart(history[cols_plot], height=300)

    with st.expander("Composite & z-score (full methodology, not in rank)"):
        st.line_chart(history[["net_composite", "net_composite_z"]], height=240)


if __name__ == "__main__":
    main()
