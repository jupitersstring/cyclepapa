"""Social arbitrage dashboard.

Run with:

    streamlit run streamlit_social_arb.py

Pages:
    1. Universe browser (financedatabase-derived)
    2. Live leaderboards (Apewisdom)
    3. Ticker drill-down (mentions + anomaly z-score + price overlay)
    4. Collector control panel
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from social_arb import universe as uni_mod
from social_arb.anomaly import AnomalyParams, ewma_zscore, joint_signal
from social_arb.collectors.apewisdom import fetch_top
from social_arb.config import Config
from social_arb.pipeline import Pipeline
from social_arb.prices import daily_close


st.set_page_config(page_title="Social Arbitrage", layout="wide")


@st.cache_resource
def get_pipeline() -> Pipeline:
    return Pipeline.build()


@st.cache_data(ttl=600)
def cached_apewisdom_top(filter_name: str, page: int) -> pd.DataFrame:
    cfg = Config()
    try:
        return fetch_top(cfg, filter_name=filter_name, page=page)
    except Exception as exc:  # noqa: BLE001
        st.warning(f"apewisdom unavailable: {exc}")
        return pd.DataFrame()


@st.cache_data(ttl=3600)
def cached_close(ticker: str, days: int) -> pd.Series:
    end = datetime.utcnow()
    start = end - timedelta(days=days)
    return daily_close(ticker, start, end)


def page_universe(pipe: Pipeline) -> None:
    st.header("Universe (financedatabase)")
    q = st.text_input("Search by symbol or name", "")
    df = pipe.universe_df
    if q:
        df = uni_mod.search(df, q, limit=200)
    st.write(f"{len(df):,} rows")
    st.dataframe(df, use_container_width=True, height=600)


def page_leaderboards() -> None:
    st.header("Apewisdom leaderboards")
    c1, c2 = st.columns(2)
    filter_name = c1.selectbox(
        "Filter",
        ["wallstreetbets", "stocks", "stockmarket", "options", "investing", "cryptocurrency", "all-stocks", "all"],
        index=0,
    )
    pages = c2.number_input("Pages", min_value=1, max_value=5, value=1)
    rows = []
    for p in range(1, int(pages) + 1):
        df = cached_apewisdom_top(filter_name, p)
        if not df.empty:
            rows.append(df)
    if not rows:
        st.info("No data returned.")
        return
    out = pd.concat(rows, ignore_index=True)
    out["mentions_delta"] = pd.to_numeric(out.get("mentions"), errors="coerce") - pd.to_numeric(
        out.get("mentions_24h_ago"), errors="coerce"
    )
    st.dataframe(out, use_container_width=True)


def page_drilldown(pipe: Pipeline) -> None:
    st.header("Ticker drill-down")
    tickers = pipe.all_tickers()
    if not tickers:
        st.warning("No mentions stored yet -- run a collector first.")
        return
    c1, c2, c3 = st.columns(3)
    ticker = c1.selectbox("Ticker", tickers)
    halflife = c2.slider("EWMA half-life (days)", 3, 60, 14)
    z_thresh = c3.slider("z threshold", 1.0, 6.0, 3.0, 0.1)

    counts = pipe.daily_counts(ticker=ticker)
    if counts.empty:
        st.info("No mentions for this ticker.")
        return
    agg = counts.groupby("date").agg(mentions=("mentions", "sum"), sentiment=("sentiment_mean", "mean"))
    agg.index = pd.to_datetime(agg.index)
    agg = agg.asfreq("D", fill_value=0.0)

    z = ewma_zscore(agg["mentions"], AnomalyParams(halflife, z_thresh))
    sig = joint_signal(agg["mentions"], agg["sentiment"])

    days = (agg.index.max() - agg.index.min()).days + 30
    close = cached_close(ticker, max(int(days), 90))

    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(go.Bar(x=agg.index, y=agg["mentions"], name="Mentions", marker_color="#888"), secondary_y=False)
    fig.add_trace(go.Scatter(x=z.index, y=z["z"], name="z", line=dict(color="#e45756")), secondary_y=True)
    if not close.empty:
        fig.add_trace(
            go.Scatter(x=close.index, y=close.values, name=f"{ticker} close", line=dict(color="#4c78a8")),
            secondary_y=True,
        )
    flagged = z[z["anomaly"]]
    if not flagged.empty:
        fig.add_trace(
            go.Scatter(
                x=flagged.index, y=flagged["z"], mode="markers",
                marker=dict(color="red", size=10, symbol="x"),
                name="Anomaly",
            ),
            secondary_y=True,
        )
    fig.update_layout(height=520, title=f"{ticker} -- mentions + z-score + close")
    fig.update_yaxes(title_text="Mentions / day", secondary_y=False)
    fig.update_yaxes(title_text="z-score / price", secondary_y=True)
    st.plotly_chart(fig, use_container_width=True)

    st.subheader("Joint-signal days (mention spike AND sentiment shift)")
    fired = sig[sig["signal"]]
    if fired.empty:
        st.write("None.")
    else:
        st.dataframe(fired.tail(30))


def page_collectors(pipe: Pipeline) -> None:
    st.header("Collectors")
    tabs = st.tabs(["Reddit (PullPush)", "Apewisdom", "GDELT", "Stocktwits"])

    with tabs[0]:
        c1, c2, c3 = st.columns(3)
        subreddit = c1.text_input("subreddit", "wallstreetbets")
        query = c2.text_input("query (optional)", "")
        days = c3.number_input("days back", 1, 30, 1)
        include_comments = st.checkbox("include comments", False)
        if st.button("Run Reddit", type="primary"):
            with st.spinner("Fetching from PullPush..."):
                n = pipe.run_reddit(
                    subreddit=subreddit or None, query=query or None,
                    days_back=int(days), include_comments=include_comments,
                )
            st.success(f"stored {n} mentions")

    with tabs[1]:
        c1, c2 = st.columns(2)
        filt = c1.selectbox(
            "filter",
            ["wallstreetbets", "stocks", "stockmarket", "options", "investing", "cryptocurrency", "all-stocks"],
        )
        pages = c2.number_input("pages", 1, 5, 1)
        if st.button("Run Apewisdom", type="primary"):
            n = pipe.run_apewisdom(filter_name=filt, pages=int(pages))
            st.success(f"stored {n} mention rows")

    with tabs[2]:
        c1, c2 = st.columns(2)
        gquery = c1.text_input("GDELT query", '"Mattel" OR "Barbie"')
        hours = c2.number_input("hours back", 1, 168, 24)
        if st.button("Run GDELT", type="primary"):
            n = pipe.run_gdelt(query=gquery, hours_back=int(hours))
            st.success(f"stored {n} mentions")

    with tabs[3]:
        t = st.text_input("ticker", "NVDA")
        if st.button("Run Stocktwits", type="primary"):
            n = pipe.run_stocktwits(ticker=t)
            st.success(f"stored {n} mentions")


def main() -> None:
    st.title("Social Arbitrage")
    st.caption(
        "Free-tier social-arb pipeline: Reddit (PullPush) + Apewisdom + GDELT + Stocktwits + yfinance + financedatabase + VADER."
    )
    pipe = get_pipeline()
    page = st.sidebar.radio(
        "Page",
        ["Universe", "Leaderboards", "Drill-down", "Collectors"],
        index=2,
    )
    if page == "Universe":
        page_universe(pipe)
    elif page == "Leaderboards":
        page_leaderboards()
    elif page == "Drill-down":
        page_drilldown(pipe)
    elif page == "Collectors":
        page_collectors(pipe)


if __name__ == "__main__":
    main()
