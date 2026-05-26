"""
Streamlit screener for the Crypto Trend Engine.

Composites Qullamaggie + Squeeze & Release + Volatility Asymmetry across
timeframes (intraday → monthly), in BOTH absolute and BTC-relative form,
and ranks the chosen universe (Revolut, top-N by mcap, top-N by volume,
or any combination).
"""

from __future__ import annotations

import time
from typing import List, Tuple

import pandas as pd
import streamlit as st

import crypto_universe as cu
import trend_engine as te
from mr_engine import TIMEFRAMES as DEFAULT_TFS


def _tf_picker() -> List[Tuple[str, str]]:
    st.subheader("Timeframes")
    chosen: List[Tuple[str, str]] = []
    defaults = {"1h": True, "4h": True, "1d": True, "1w": True, "1mo": True,
                "15m": False, "5m": False, "1m": False}
    for label, interval in DEFAULT_TFS:
        if st.checkbox(label, value=defaults.get(label, True), key=f"tf_{label}"):
            chosen.append((label, interval))
    return chosen


def _universe_picker() -> List[str]:
    st.subheader("Universe")
    src = st.radio(
        "Source",
        ["Revolut", "Top by Market Cap", "Top by Volume", "Combined (all 3)", "Custom"],
        index=0,
    )
    if src == "Revolut":
        return cu.revolut_universe()
    if src == "Top by Market Cap":
        n = st.number_input("How many", 10, 500, 200, 10)
        return cu.top_yf_cryptos_by_mcap(int(n))
    if src == "Top by Volume":
        n = st.number_input("How many", 10, 500, 200, 10)
        return cu.top_yf_cryptos_by_volume(int(n))
    if src == "Combined (all 3)":
        n = st.number_input("Top-N per source", 10, 500, 200, 10)
        return cu.combined_universe(n_mcap=int(n), n_volume=int(n))
    text = st.text_area("Custom tickers (comma- or newline-separated)", "BTC-USD, ETH-USD, SOL-USD")
    raw = [t.strip().upper() for t in text.replace("\n", ",").split(",") if t.strip()]
    return [t if t.endswith("-USD") else f"{t}-USD" for t in raw]


def main() -> None:
    st.set_page_config(page_title="Crypto Trend Screener", layout="wide")
    st.title("Crypto Trend Screener — Qullamaggie + S&R + Volasym (MTF)")
    st.caption(
        "Ranks the universe by a composite trend score: Qullamaggie's three "
        "setups (breakout / EP / parabolic) combined with Squeeze & Release "
        "and Volatility Asymmetry, computed per timeframe and averaged. "
        "Scores are computed in BOTH absolute and BTC-relative form."
    )

    with st.sidebar:
        st.header("Configuration")
        tfs = _tf_picker()
        st.divider()
        symbols = _universe_picker()
        st.caption(f"{len(symbols)} symbols selected.")
        st.divider()
        st.subheader("Composite weighting")
        rel_weight = st.slider(
            "Weight on BTC-relative score",
            0.0, 1.0, 0.5, 0.05,
            help="combined = rel_weight × rel_net + (1 − rel_weight) × abs_net",
        )
        st.divider()
        st.subheader("Volasym attractiveness band")
        band_low = st.number_input("Band low",  0.0, 100.0, te.VOLASYM_BAND_LOW, 1.0)
        band_high = st.number_input("Band high", 0.0, 100.0, te.VOLASYM_BAND_HIGH, 1.0)
        te.VOLASYM_BAND_LOW = band_low      # type: ignore[assignment]
        te.VOLASYM_BAND_HIGH = band_high    # type: ignore[assignment]
        run = st.button("Run screener", type="primary")

    if not run:
        st.info("Pick a universe and timeframes, then click **Run screener**.")
        st.subheader("Methodology summary")
        st.markdown("""
- **Volatility Asymmetry "attractive"** — above its MA, rising, value within `[band_low, band_high]`
  (default 45–70: near or above 50 but not extended), and a release within the last 10 bars
  following a hyper-squeeze.
- **Squeeze & Release** — Pine port: squeeze = `squeezeValue > squeezeValueMA`, release = crossunder,
  hyper-squeeze = `squeezeValue > 0` and rising over the last 5 bars.
- **Qullamaggie** —
  - *Breakout*: top % returns over 1m / 3m / 6m, orderly consolidation (range tightening + higher lows),
    price surfing the rising 10/20 SMA, breakout of the 20-bar high; stop ≤ ADR.
  - *Episodic Pivot*: gap up ≥ 10% with volume ≥ 3× the 20-bar average, on a dormant base
    (|3-month return| < 30%).
  - *Parabolic*: +50% in 5 bars with ≥ 3 consecutive up bars, stretched > 2 ADR from 10 SMA — fades to MA bounce.
- **Multi-timeframe composite** — equal-weighted mean of per-timeframe `long_score − short_score`,
  in [−100, +100]. Computed twice: on absolute price and on the price/BTC ratio.
        """)
        return

    if not symbols:
        st.warning("Empty universe.")
        return
    if not tfs:
        st.warning("Select at least one timeframe.")
        return

    progress = st.progress(0.0)
    status = st.empty()
    start = time.time()

    def _cb(i: int, n: int, sym: str) -> None:
        progress.progress(i / n)
        elapsed = time.time() - start
        eta = elapsed / i * (n - i) if i else 0
        status.text(f"[{i}/{n}] {sym}  ·  elapsed {elapsed:.0f}s  ·  eta {eta:.0f}s")

    df = te.rank_universe(symbols, timeframes=tfs, rel_weight=rel_weight, progress_cb=_cb)
    progress.empty()
    status.empty()

    if df.empty:
        st.error("No data returned.")
        return

    ok = df[df["combined"].notna()].copy()
    bad = df[df["combined"].isna()].copy()

    # ----- Headline table ----------------------------------------------
    st.subheader(f"Ranked symbols ({len(ok)})")

    summary_cols = ["symbol", "combined", "abs_net", "rel_net",
                    "abs_long", "abs_short", "rel_long", "rel_short",
                    "breakout", "ep", "release_after_squeeze",
                    "volasym_attractive", "parabolic_extended",
                    "inflection_bull_tfs", "inflection_bear_tfs", "inflection_net_tfs"]
    st.dataframe(
        ok[summary_cols].style.format({
            "combined": "{:+.1f}", "abs_net": "{:+.1f}", "rel_net": "{:+.1f}",
            "abs_long": "{:.1f}", "abs_short": "{:.1f}",
            "rel_long": "{:.1f}", "rel_short": "{:.1f}",
        }),
        use_container_width=True,
        hide_index=True,
    )

    # ----- Per-timeframe breakdown -------------------------------------
    with st.expander("Per-timeframe net score (absolute & BTC-relative)"):
        per_tf_cols = ["symbol"] + [c for c in ok.columns if c.startswith("abs_") or c.startswith("rel_")]
        per_tf_cols = [c for c in per_tf_cols if c not in {"abs_net", "abs_long", "abs_short", "rel_net", "rel_long", "rel_short"}]
        st.dataframe(ok[per_tf_cols], use_container_width=True, hide_index=True)

    # ----- Top picks lens ----------------------------------------------
    st.subheader("Active setups")
    tabs = st.tabs([
        "Breakout", "Episodic Pivot", "Release-after-squeeze",
        "Volasym attractive", "Parabolic (short candidate)",
        "Bullish inflection (MFI div)", "Bearish inflection (MFI div)",
    ])
    bull_infl_mask = ok["inflection_bull_tfs"] > 0 if "inflection_bull_tfs" in ok.columns else pd.Series(False, index=ok.index)
    bear_infl_mask = ok["inflection_bear_tfs"] > 0 if "inflection_bear_tfs" in ok.columns else pd.Series(False, index=ok.index)
    setup_masks = [
        ("breakout", ok.get("breakout", pd.Series(False, index=ok.index))),
        ("ep", ok.get("ep", pd.Series(False, index=ok.index))),
        ("release_after_squeeze", ok.get("release_after_squeeze", pd.Series(False, index=ok.index))),
        ("volasym_attractive", ok.get("volasym_attractive", pd.Series(False, index=ok.index))),
        ("parabolic_extended", ok.get("parabolic_extended", pd.Series(False, index=ok.index))),
        ("inflection_bull", bull_infl_mask),
        ("inflection_bear", bear_infl_mask),
    ]
    for tab, (col, _mask) in zip(tabs, setup_masks):
        with tab:
            subset = ok[_mask].copy() if _mask is not None else ok[ok[col]].copy()
            if subset.empty:
                st.caption(f"No symbols currently flagged as `{col}`.")
            else:
                st.dataframe(
                    subset[summary_cols].style.format({
                        "combined": "{:+.1f}", "abs_net": "{:+.1f}", "rel_net": "{:+.1f}",
                        "abs_long": "{:.1f}", "abs_short": "{:.1f}",
                        "rel_long": "{:.1f}", "rel_short": "{:.1f}",
                    }),
                    use_container_width=True, hide_index=True,
                )

    if not bad.empty:
        with st.expander(f"Symbols with no data ({len(bad)})"):
            st.dataframe(bad[["symbol", "error"]], use_container_width=True, hide_index=True)

    st.download_button(
        "Download full results (CSV)",
        df.to_csv(index=False),
        file_name="crypto_trend_rank.csv",
        mime="text/csv",
    )


if __name__ == "__main__":
    main()
