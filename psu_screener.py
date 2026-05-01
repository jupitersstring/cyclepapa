"""PSU asymmetric-opportunity screener.

Pipeline (Munger-style "follow the incentives"):
    universe -> fetch fundamentals -> score skin-in-the-game
             -> score downside floor -> score upside potential
             -> compute Asymmetry & Munger composite -> rank.

Designed to plug into the existing Streamlit app in `cycle`, but
the scoring functions are pure and can be called from any pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import numpy as np
import pandas as pd
import streamlit as st
import yfinance as yf


# ---------------------------------------------------------------------------
# Universe
# ---------------------------------------------------------------------------

# Curated NSE-listed central PSU universe. Edit freely from the UI.
DEFAULT_PSU_UNIVERSE: list[str] = [
    # Energy
    "ONGC.NS", "OIL.NS", "COALINDIA.NS", "GAIL.NS",
    "IOC.NS", "BPCL.NS", "HPCL.NS", "MGL.NS", "IGL.NS",
    # Power
    "NTPC.NS", "POWERGRID.NS", "NHPC.NS", "SJVN.NS", "NLCINDIA.NS",
    # Metals & mining
    "SAIL.NS", "NMDC.NS", "MOIL.NS", "HINDCOPPER.NS",
    # Defence & engineering
    "HAL.NS", "BEL.NS", "BEML.NS", "BHEL.NS",
    "MAZDOCK.NS", "COCHINSHIP.NS", "GRSE.NS",
    # Railways & logistics
    "IRCTC.NS", "IRFC.NS", "RVNL.NS", "RAILTEL.NS",
    "CONCOR.NS", "IRCON.NS",
    # Financials
    "SBIN.NS", "BANKBARODA.NS", "PNB.NS", "CANBK.NS",
    "UNIONBANK.NS", "INDIANB.NS", "BANKINDIA.NS",
    "LICI.NS", "GICRE.NS", "NIACL.NS",
    "PFC.NS", "RECLTD.NS", "IRFC.NS", "HUDCO.NS", "IFCI.NS",
    # Trading / agri / fertilisers
    "MMTC.NS", "STCINDIA.NS", "RCF.NS", "NFL.NS", "FACT.NS",
]


# ---------------------------------------------------------------------------
# Data fetch
# ---------------------------------------------------------------------------

@dataclass
class PSURow:
    ticker: str
    name: str | None
    sector: str | None
    market_cap: float | None
    price: float | None
    promoter_holding: float | None       # % held by insiders (proxy for govt holding)
    institutional_holding: float | None
    dividend_yield: float | None         # decimal, e.g. 0.045
    payout_ratio: float | None
    price_to_book: float | None
    debt_to_equity: float | None
    return_on_equity: float | None
    profit_margin: float | None
    revenue_growth: float | None
    earnings_growth: float | None
    free_cashflow: float | None
    total_cash: float | None
    total_debt: float | None
    trailing_pe: float | None
    forward_pe: float | None
    peg_ratio: float | None
    fifty_two_week_low: float | None
    fifty_two_week_high: float | None


def _safe(info: dict, key: str) -> float | None:
    v = info.get(key)
    if v is None:
        return None
    try:
        f = float(v)
        if np.isnan(f) or np.isinf(f):
            return None
        return f
    except (TypeError, ValueError):
        return None


@st.cache_data(show_spinner=False, ttl=60 * 60 * 6)
def fetch_psu_row(ticker: str) -> PSURow | None:
    """Pull a single PSU's fundamentals from Yahoo Finance."""
    try:
        t = yf.Ticker(ticker)
        info = t.info or {}
    except Exception:
        return None
    if not info:
        return None
    return PSURow(
        ticker=ticker,
        name=info.get("longName") or info.get("shortName"),
        sector=info.get("sector"),
        market_cap=_safe(info, "marketCap"),
        price=_safe(info, "currentPrice") or _safe(info, "regularMarketPrice"),
        promoter_holding=_safe(info, "heldPercentInsiders"),
        institutional_holding=_safe(info, "heldPercentInstitutions"),
        dividend_yield=_safe(info, "dividendYield"),
        payout_ratio=_safe(info, "payoutRatio"),
        price_to_book=_safe(info, "priceToBook"),
        debt_to_equity=_safe(info, "debtToEquity"),
        return_on_equity=_safe(info, "returnOnEquity"),
        profit_margin=_safe(info, "profitMargins"),
        revenue_growth=_safe(info, "revenueGrowth"),
        earnings_growth=_safe(info, "earningsGrowth"),
        free_cashflow=_safe(info, "freeCashflow"),
        total_cash=_safe(info, "totalCash"),
        total_debt=_safe(info, "totalDebt"),
        trailing_pe=_safe(info, "trailingPE"),
        forward_pe=_safe(info, "forwardPE"),
        peg_ratio=_safe(info, "pegRatio"),
        fifty_two_week_low=_safe(info, "fiftyTwoWeekLow"),
        fifty_two_week_high=_safe(info, "fiftyTwoWeekHigh"),
    )


def fetch_universe(tickers: Iterable[str]) -> pd.DataFrame:
    rows: list[PSURow] = []
    progress = st.progress(0.0, text="Fetching PSU fundamentals...")
    tickers = list(tickers)
    for i, tk in enumerate(tickers, 1):
        r = fetch_psu_row(tk)
        if r is not None:
            rows.append(r)
        progress.progress(i / max(len(tickers), 1), text=f"Fetched {tk}")
    progress.empty()
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame([r.__dict__ for r in rows])


# ---------------------------------------------------------------------------
# Scoring primitives
# ---------------------------------------------------------------------------

def _clip01(x: pd.Series) -> pd.Series:
    return x.clip(lower=0.0, upper=1.0)


def _percentile(series: pd.Series, higher_is_better: bool = True) -> pd.Series:
    s = series.astype(float)
    if s.notna().sum() < 2:
        return pd.Series(np.where(s.notna(), 0.5, np.nan), index=s.index)
    ranks = s.rank(pct=True, na_option="keep")
    if not higher_is_better:
        ranks = 1.0 - ranks
    return ranks


def _ratio_score(values: pd.Series, target: float, higher_is_better: bool = True) -> pd.Series:
    """Score where `target` maps to 1.0; clipped to [0, 1]."""
    s = values.astype(float) / target
    if not higher_is_better:
        s = 1.0 / s.replace(0, np.nan)
    return _clip01(s)


# ---------------------------------------------------------------------------
# Munger lenses
# ---------------------------------------------------------------------------
# "Show me the incentive and I'll show you the outcome." For Indian central
# PSUs the dominant principal is the Government of India: it is the controlling
# shareholder, sets the dividend policy, runs disinvestment, and signs off on
# capex. So "skin in the game" here means the government's economic incentives
# are tightly coupled with minority shareholders -- chiefly via cash returned
# (dividends + buybacks) and a stable, large promoter stake.

def score_skin_in_the_game(df: pd.DataFrame) -> pd.Series:
    promoter = df["promoter_holding"].fillna(0.0)
    # Government holdings >51% = control; 51-75% is the sweet spot
    # (high enough alignment, room for re-rating via disinvestment).
    promoter_score = np.where(
        promoter >= 0.51,
        1.0 - (promoter - 0.51).clip(0, 0.49) / 0.49 * 0.3,
        promoter / 0.51 * 0.7,
    )
    promoter_score = pd.Series(promoter_score, index=df.index)

    div_yield = df["dividend_yield"].fillna(0.0)
    # 7% Indian 10Y G-Sec is the benchmark; double that = full marks.
    div_score = _ratio_score(div_yield, target=0.14, higher_is_better=True)

    payout = df["payout_ratio"].fillna(0.0)
    # 30-70% is healthy; >100% suggests unsustainable.
    payout_score = pd.Series(
        np.where(
            (payout >= 0.30) & (payout <= 0.70), 1.0,
            np.where(payout > 0.70, np.maximum(0.0, 1.0 - (payout - 0.70) / 0.6),
                     payout / 0.30),
        ),
        index=df.index,
    )

    inst = df["institutional_holding"].fillna(0.0)
    inst_score = _ratio_score(inst, target=0.20, higher_is_better=True)

    return (
        0.45 * promoter_score
        + 0.30 * div_score
        + 0.15 * payout_score
        + 0.10 * inst_score
    ) * 100.0


def score_downside_floor(df: pd.DataFrame) -> pd.Series:
    """How protected is the downside? Low P/B, net cash, dividend cushion."""
    pb = df["price_to_book"]
    pb_score = _ratio_score(pb.fillna(10.0), target=1.0, higher_is_better=False)

    de = df["debt_to_equity"]
    # yfinance reports D/E in percent for some tickers; normalise.
    de_norm = de.where(de.isna() | (de < 5), de / 100.0)
    de_score = _ratio_score(de_norm.fillna(2.0).clip(lower=0.01), target=0.5, higher_is_better=False)

    mcap = df["market_cap"].replace(0, np.nan)
    net_cash = (df["total_cash"].fillna(0.0) - df["total_debt"].fillna(0.0)) / mcap
    net_cash_score = _clip01((net_cash.fillna(-1.0) + 0.2) / 0.5)  # -20% net debt -> 0, +30% net cash -> 1

    div_floor = _ratio_score(df["dividend_yield"].fillna(0.0), target=0.07, higher_is_better=True)

    # Distance from 52w low (closer to low = more downside already realised)
    price = df["price"]
    low = df["fifty_two_week_low"]
    high = df["fifty_two_week_high"]
    drawdown = pd.Series(
        np.where(
            high.notna() & price.notna() & (high > 0),
            (price - low) / (high - low).replace(0, np.nan),
            0.5,
        ),
        index=df.index,
    )
    drawdown_score = 1.0 - drawdown.fillna(0.5).clip(0, 1)

    return (
        0.30 * pb_score
        + 0.20 * de_score
        + 0.20 * net_cash_score
        + 0.20 * div_floor
        + 0.10 * drawdown_score
    ) * 100.0


def score_upside_potential(df: pd.DataFrame) -> pd.Series:
    """Earnings yield vs bond, FCF yield, ROE, growth."""
    pe = df["trailing_pe"].where(df["trailing_pe"] > 0)
    earnings_yield = 1.0 / pe
    ey_score = _ratio_score(earnings_yield.fillna(0.0), target=0.12, higher_is_better=True)

    mcap = df["market_cap"].replace(0, np.nan)
    fcf_yield = df["free_cashflow"] / mcap
    fcf_score = _ratio_score(fcf_yield.fillna(0.0), target=0.10, higher_is_better=True)

    roe_score = _ratio_score(df["return_on_equity"].fillna(0.0), target=0.18, higher_is_better=True)

    rev_g = df["revenue_growth"].fillna(0.0)
    rev_score = _ratio_score(rev_g.clip(lower=0.0), target=0.15, higher_is_better=True)

    eps_g = df["earnings_growth"].fillna(0.0)
    eps_score = _ratio_score(eps_g.clip(lower=0.0), target=0.20, higher_is_better=True)

    peg = df["peg_ratio"].where(df["peg_ratio"] > 0)
    peg_score = _ratio_score(peg.fillna(5.0), target=1.0, higher_is_better=False)

    return (
        0.25 * ey_score
        + 0.20 * fcf_score
        + 0.20 * roe_score
        + 0.15 * rev_score
        + 0.10 * eps_score
        + 0.10 * peg_score
    ) * 100.0


def score_quality(df: pd.DataFrame) -> pd.Series:
    margin = _ratio_score(df["profit_margin"].fillna(0.0).clip(lower=0.0), target=0.15)
    roe = _ratio_score(df["return_on_equity"].fillna(0.0).clip(lower=0.0), target=0.18)
    return (0.5 * margin + 0.5 * roe) * 100.0


# ---------------------------------------------------------------------------
# Composite
# ---------------------------------------------------------------------------

def build_scorecard(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    out = df.copy()
    out["skin_in_game"] = score_skin_in_the_game(out)
    out["downside_floor"] = score_downside_floor(out)
    out["upside_potential"] = score_upside_potential(out)
    out["quality"] = score_quality(out)

    # Asymmetry = geometric mean of downside and upside; a stock only scores
    # high if BOTH legs are intact (Munger's aversion to single-point risk).
    out["asymmetry"] = np.sqrt(
        out["downside_floor"].clip(lower=0) * out["upside_potential"].clip(lower=0)
    )

    # Munger composite: incentives weigh heaviest, then asymmetry, then quality.
    out["munger_score"] = (
        0.40 * out["skin_in_game"]
        + 0.40 * out["asymmetry"]
        + 0.20 * out["quality"]
    )
    return out.sort_values("munger_score", ascending=False)


# ---------------------------------------------------------------------------
# Streamlit UI
# ---------------------------------------------------------------------------

DISPLAY_COLS = [
    "ticker", "name", "sector",
    "munger_score", "skin_in_game", "asymmetry",
    "downside_floor", "upside_potential", "quality",
    "promoter_holding", "dividend_yield", "payout_ratio",
    "price_to_book", "debt_to_equity", "return_on_equity",
    "trailing_pe", "market_cap",
]


def render_psu_screener() -> None:
    st.header("PSU Asymmetry Screener")
    st.caption(
        "Munger lens: weight what aligns the controlling shareholder "
        "(Government of India) with minority holders -- promoter stake, "
        "dividend extraction, payout discipline -- then rank by "
        "downside floor X upside potential."
    )

    with st.expander("Universe", expanded=False):
        raw = st.text_area(
            "Tickers (one per line, NSE suffix .NS)",
            value="\n".join(DEFAULT_PSU_UNIVERSE),
            height=200,
        )
        tickers = [t.strip() for t in raw.splitlines() if t.strip()]

    col1, col2, col3 = st.columns(3)
    with col1:
        min_mcap_cr = st.number_input("Min market cap (INR Cr)", value=1000, step=500)
    with col2:
        min_promoter = st.slider("Min promoter holding", 0.0, 1.0, 0.51, 0.01)
    with col3:
        top_n = st.number_input("Show top N", value=15, step=5, min_value=5)

    if not st.button("Run screen", type="primary"):
        return

    df = fetch_universe(tickers)
    if df.empty:
        st.error("No data returned. Check tickers / network.")
        return

    df = df[df["market_cap"].fillna(0) >= min_mcap_cr * 1e7]
    df = df[df["promoter_holding"].fillna(0) >= min_promoter]
    if df.empty:
        st.warning("Filters removed every name. Loosen them.")
        return

    scored = build_scorecard(df)

    st.subheader("Top opportunities")
    show = scored.head(int(top_n))[DISPLAY_COLS].copy()
    show["market_cap"] = (show["market_cap"] / 1e7).round(0)  # to Crores
    for c in ("munger_score", "skin_in_game", "asymmetry",
              "downside_floor", "upside_potential", "quality"):
        show[c] = show[c].round(1)
    for c in ("promoter_holding", "dividend_yield", "payout_ratio",
              "return_on_equity"):
        show[c] = (show[c] * 100).round(2)
    show = show.rename(columns={"market_cap": "mcap_cr"})
    st.dataframe(show, hide_index=True, use_container_width=True)

    st.subheader("Score distribution")
    chart = scored.set_index("ticker")[
        ["skin_in_game", "downside_floor", "upside_potential"]
    ].head(int(top_n))
    st.bar_chart(chart)

    st.subheader("Drill-down")
    pick = st.selectbox("Ticker", scored["ticker"].tolist())
    if pick:
        row = scored[scored["ticker"] == pick].iloc[0]
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Munger score", f"{row['munger_score']:.1f}")
        c2.metric("Skin in game", f"{row['skin_in_game']:.1f}")
        c3.metric("Downside floor", f"{row['downside_floor']:.1f}")
        c4.metric("Upside potential", f"{row['upside_potential']:.1f}")
        st.json({k: row[k] for k in DISPLAY_COLS if k in row})

    st.download_button(
        "Download full scorecard (CSV)",
        scored.to_csv(index=False).encode(),
        file_name="psu_scorecard.csv",
        mime="text/csv",
    )
