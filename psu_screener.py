"""Developed-market PSU / SOE asymmetric-opportunity screener.

Pipeline:
    universe (curated state-owned enterprises with known sovereign stakes)
    -> fetch fundamentals
    -> score skin-in-the-game (incentive alignment between sovereign
       controlling shareholder and minority holders)
    -> score downside floor (Munger: "invert, always invert")
    -> score upside potential
    -> score governance / capital allocation (per-share growth, accruals,
       capex discipline, buyback vs issuance) -- driven by the
       "Corporate Dark Arts Gone Awry" framework
    -> apply red-flag penalty multiplier
    -> rank by Munger composite.

Why developed-market SOEs are an interesting hunting ground:
- They trade at persistent governance discounts.
- Many have privatization / disinvestment catalysts.
- Strong dividend cultures in Nordics, France, Italy, Singapore.
- The controlling shareholder (state) has *visible*, *legible* incentives
  (fiscal needs, dividend policy, mandate creep) -- exactly the kind of
  setup Munger's "show me the incentive" lens is built for.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import numpy as np
import pandas as pd
import streamlit as st
import yfinance as yf

from governance_signals import (
    fetch_governance_frame,
    score_governance,
    red_flag_penalty,
)


# ---------------------------------------------------------------------------
# Universe -- curated developed-market SOEs with sovereign stakes.
# `state_pct` is hard-coded because yfinance's heldPercentInsiders does not
# reliably surface sovereign / state-holding-company ownership.
# Stakes change; treat these as starting points (the UI lets you override).
# ---------------------------------------------------------------------------

DEFAULT_SOE_UNIVERSE: dict[str, float] = {
    # France (APE)
    "ENGI.PA": 0.24,    # Engie
    "ORA.PA":  0.23,    # Orange
    "RNO.PA":  0.15,    # Renault
    "AIR.PA":  0.26,    # Airbus (France/Germany/Spain combined)
    "HO.PA":   0.26,    # Thales
    "SAF.PA":  0.11,    # Safran
    "ADP.PA":  0.50,    # Aeroports de Paris
    "AF.PA":   0.28,    # Air France-KLM
    # Germany (Bund / KfW)
    "DTE.DE":  0.30,    # Deutsche Telekom
    "DHL.DE":  0.20,    # Deutsche Post / DHL Group
    "CBK.DE":  0.12,    # Commerzbank
    # Norway (Ministry of Trade)
    "EQNR.OL": 0.67,    # Equinor
    "TEL.OL":  0.54,    # Telenor
    "DNB.OL":  0.34,    # DNB
    "YAR.OL":  0.36,    # Yara International
    "NHY.OL":  0.34,    # Norsk Hydro
    # Finland (Solidium / state)
    "FORTUM.HE": 0.51,  # Fortum
    "NESTE.HE":  0.36,  # Neste
    "FIA1S.HE":  0.56,  # Finnair
    # Sweden
    "TELIA.ST": 0.40,   # Telia
    # Italy (MEF / CDP)
    "ENI.MI":  0.30,    # Eni
    "ENEL.MI": 0.24,    # Enel
    "LDO.MI":  0.30,    # Leonardo
    "PST.MI":  0.64,    # Poste Italiane
    "SRG.MI":  0.31,    # Snam
    "TRN.MI":  0.30,    # Terna
    "IG.MI":   0.42,    # Italgas
    # Belgium
    "PROX.BR":  0.53,   # Proximus
    "BPOST.BR": 0.51,   # bpost
    # Austria (OeBAG)
    "OMV.VI":  0.31,    # OMV
    "VER.VI":  0.51,    # Verbund
    "TKA.VI":  0.28,    # Telekom Austria
    "POST.VI": 0.53,    # Oesterreichische Post
    # Switzerland
    "SCMN.SW": 0.51,    # Swisscom
    # Japan (Ministry of Finance)
    "6178.T":  0.60,    # Japan Post Holdings
    "7182.T":  0.60,    # Japan Post Bank (held via JP Holdings)
    "9432.T":  0.33,    # NTT
    "2914.T":  0.33,    # Japan Tobacco
    # Korea (state / state banks)
    "015760.KS": 0.51,  # KEPCO
    "036460.KS": 0.55,  # Korea Gas
    "024110.KS": 0.59,  # Industrial Bank of Korea
    # Singapore (Temasek -- effectively sovereign)
    "Z74.SI": 0.51,     # Singtel
    "D05.SI": 0.29,     # DBS
    "S63.SI": 0.51,     # ST Engineering
    "BN4.SI": 0.21,     # Keppel
    "U96.SI": 0.49,     # Sembcorp Industries
    # UK
    "NWG.L":  0.10,     # NatWest (declining Treasury stake)
    # Canada
    "H.TO":   0.47,     # Hydro One (Ontario)
}


# ---------------------------------------------------------------------------
# Fundamentals fetch
# ---------------------------------------------------------------------------

@dataclass
class SOERow:
    ticker: str
    name: str | None
    sector: str | None
    country: str | None
    currency: str | None
    market_cap: float | None
    price: float | None
    state_pct: float                       # hard-coded sovereign stake
    institutional_holding: float | None
    dividend_yield: float | None
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
def fetch_soe_row(ticker: str, state_pct: float) -> SOERow | None:
    try:
        t = yf.Ticker(ticker)
        info = t.info or {}
    except Exception:
        return None
    if not info:
        return None
    return SOERow(
        ticker=ticker,
        name=info.get("longName") or info.get("shortName"),
        sector=info.get("sector"),
        country=info.get("country"),
        currency=info.get("financialCurrency") or info.get("currency"),
        market_cap=_safe(info, "marketCap"),
        price=_safe(info, "currentPrice") or _safe(info, "regularMarketPrice"),
        state_pct=state_pct,
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


def fetch_universe(universe: dict[str, float]) -> pd.DataFrame:
    rows: list[SOERow] = []
    progress = st.progress(0.0, text="Fetching SOE fundamentals...")
    items = list(universe.items())
    for i, (tk, pct) in enumerate(items, 1):
        r = fetch_soe_row(tk, pct)
        if r is not None:
            rows.append(r)
        progress.progress(i / max(len(items), 1), text=f"Fetched {tk}")
    progress.empty()
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame([r.__dict__ for r in rows])


# ---------------------------------------------------------------------------
# Scoring primitives
# ---------------------------------------------------------------------------

def _clip01(x: pd.Series) -> pd.Series:
    return x.clip(lower=0.0, upper=1.0)


def _ratio_score(values: pd.Series, target: float, higher_is_better: bool = True) -> pd.Series:
    s = values.astype(float) / target
    if not higher_is_better:
        s = 1.0 / s.replace(0, np.nan)
    return _clip01(s)


# ---------------------------------------------------------------------------
# Munger lenses
# ---------------------------------------------------------------------------

def score_skin_in_the_game(df: pd.DataFrame) -> pd.Series:
    """Sovereign control => aligned long-term incentive, but excessive
    state holding caps free-float upside. 51-67% is the sweet spot."""
    state = df["state_pct"].fillna(0.0)
    state_score = pd.Series(
        np.where(
            state >= 0.51,
            1.0 - (state - 0.51).clip(0, 0.49) / 0.49 * 0.4,
            state / 0.51 * 0.7,
        ),
        index=df.index,
    )

    # Use ~4% as a globally reasonable dividend yield benchmark (developed
    # markets). Doubling it earns full marks.
    div_yield = df["dividend_yield"].fillna(0.0)
    div_score = _ratio_score(div_yield, target=0.08, higher_is_better=True)

    payout = df["payout_ratio"].fillna(0.0)
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
        0.45 * state_score
        + 0.30 * div_score
        + 0.15 * payout_score
        + 0.10 * inst_score
    ) * 100.0


def score_downside_floor(df: pd.DataFrame) -> pd.Series:
    pb = df["price_to_book"]
    pb_score = _ratio_score(pb.fillna(10.0), target=1.0, higher_is_better=False)

    de = df["debt_to_equity"]
    de_norm = de.where(de.isna() | (de < 5), de / 100.0)
    de_score = _ratio_score(de_norm.fillna(2.0).clip(lower=0.01), target=0.5, higher_is_better=False)

    mcap = df["market_cap"].replace(0, np.nan)
    net_cash = (df["total_cash"].fillna(0.0) - df["total_debt"].fillna(0.0)) / mcap
    net_cash_score = _clip01((net_cash.fillna(-1.0) + 0.2) / 0.5)

    div_floor = _ratio_score(df["dividend_yield"].fillna(0.0), target=0.05, higher_is_better=True)

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
    pe = df["trailing_pe"].where(df["trailing_pe"] > 0)
    earnings_yield = 1.0 / pe
    ey_score = _ratio_score(earnings_yield.fillna(0.0), target=0.10, higher_is_better=True)

    mcap = df["market_cap"].replace(0, np.nan)
    fcf_yield = df["free_cashflow"] / mcap
    fcf_score = _ratio_score(fcf_yield.fillna(0.0), target=0.08, higher_is_better=True)

    roe_score = _ratio_score(df["return_on_equity"].fillna(0.0), target=0.15, higher_is_better=True)

    rev_g = df["revenue_growth"].fillna(0.0)
    rev_score = _ratio_score(rev_g.clip(lower=0.0), target=0.12, higher_is_better=True)

    eps_g = df["earnings_growth"].fillna(0.0)
    eps_score = _ratio_score(eps_g.clip(lower=0.0), target=0.18, higher_is_better=True)

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
    margin = _ratio_score(df["profit_margin"].fillna(0.0).clip(lower=0.0), target=0.12)
    roe = _ratio_score(df["return_on_equity"].fillna(0.0).clip(lower=0.0), target=0.15)
    return (0.5 * margin + 0.5 * roe) * 100.0


# ---------------------------------------------------------------------------
# Composite (with governance + red-flag penalty)
# ---------------------------------------------------------------------------

def build_scorecard(df: pd.DataFrame, gov: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    out = df.copy()
    out["skin_in_game"] = score_skin_in_the_game(out)
    out["downside_floor"] = score_downside_floor(out)
    out["upside_potential"] = score_upside_potential(out)
    out["quality"] = score_quality(out)
    out["asymmetry"] = np.sqrt(
        out["downside_floor"].clip(lower=0) * out["upside_potential"].clip(lower=0)
    )

    if not gov.empty:
        out = out.merge(
            gov[[
                "ticker", "governance_score", "red_flag_penalty",
                "red_flag_count", "red_flag_summary",
                "share_count_3y_cagr", "fcf_per_share_cagr",
                "ebitda_per_share_cagr", "accruals_ratio",
                "capex_to_depreciation", "fcf_to_ni",
                "buyback_yield", "issuance_yield",
            ]],
            on="ticker", how="left",
        )
    else:
        for c in ("governance_score", "red_flag_penalty", "red_flag_count",
                  "red_flag_summary"):
            out[c] = np.nan if c != "red_flag_summary" else ""
    out["governance_score"] = out["governance_score"].fillna(50.0)
    out["red_flag_penalty"] = out["red_flag_penalty"].fillna(1.0)
    out["red_flag_count"] = out["red_flag_count"].fillna(0).astype(int)
    out["red_flag_summary"] = out["red_flag_summary"].fillna("")

    # Composite: incentives + asymmetry + governance + quality, then
    # multiplied by the red-flag penalty. A name with persistent dilution
    # or a freshly disclosed asset firesale gets actively cut.
    raw = (
        0.30 * out["skin_in_game"]
        + 0.30 * out["asymmetry"]
        + 0.20 * out["governance_score"]
        + 0.20 * out["quality"]
    )
    out["munger_score"] = raw * out["red_flag_penalty"]
    return out.sort_values("munger_score", ascending=False)


# ---------------------------------------------------------------------------
# Streamlit UI
# ---------------------------------------------------------------------------

DISPLAY_COLS = [
    "ticker", "name", "country", "sector", "currency",
    "munger_score", "skin_in_game", "asymmetry",
    "downside_floor", "upside_potential", "governance_score",
    "red_flag_count", "red_flag_summary",
    "state_pct", "dividend_yield", "payout_ratio",
    "price_to_book", "debt_to_equity", "return_on_equity",
    "trailing_pe", "market_cap",
]


def _parse_universe(text: str) -> dict[str, float]:
    out: dict[str, float] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "," in line:
            parts = [p.strip() for p in line.split(",")]
        else:
            parts = line.split()
        if len(parts) >= 2:
            try:
                out[parts[0]] = float(parts[1])
                continue
            except ValueError:
                pass
        out[parts[0]] = 0.0
    return out


def render_psu_screener() -> None:
    st.header("Developed-Market PSU / SOE Asymmetry Screener")
    st.caption(
        "Munger lens applied to listed state-owned enterprises across "
        "developed markets (France, Germany, Nordics, Italy, Japan, "
        "Korea, Singapore, UK, Canada, ...). Composite score weighs "
        "incentive alignment + downside floor x upside potential + "
        "governance / capital allocation, then multiplies by a red-flag "
        "penalty driven by the 'Corporate Dark Arts Gone Awry' framework "
        "(per-share growth, dilution, accruals, capex discipline, "
        "buybacks vs issuance, asset firesales)."
    )

    with st.expander("Universe (ticker, sovereign stake)", expanded=False):
        default_text = "\n".join(
            f"{tk}, {pct:.2f}" for tk, pct in DEFAULT_SOE_UNIVERSE.items()
        )
        raw = st.text_area(
            "One ticker per line. Format: `TICKER, state_pct` (e.g. `EQNR.OL, 0.67`).",
            value=default_text,
            height=260,
        )
        universe = _parse_universe(raw)

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        min_mcap_b = st.number_input("Min market cap (USD bn equiv.)", value=2.0, step=1.0)
    with col2:
        min_state = st.slider("Min sovereign stake", 0.0, 1.0, 0.10, 0.01)
    with col3:
        max_red_flags = st.slider("Max red flags", 0, 8, 6, 1)
    with col4:
        top_n = st.number_input("Show top N", value=15, step=5, min_value=5)

    run_governance = st.checkbox(
        "Pull governance signals (slower; needs historical financials)",
        value=True,
    )

    if not st.button("Run screen", type="primary"):
        return

    df = fetch_universe(universe)
    if df.empty:
        st.error("No data returned. Check tickers / network.")
        return

    # Rough USD market-cap filter using yfinance native marketCap (already in
    # the trading currency). This is approximate; use the same threshold but
    # acknowledge the mixed currencies.
    mcap_threshold_local = min_mcap_b * 1e9
    df = df[df["market_cap"].fillna(0) >= mcap_threshold_local]
    df = df[df["state_pct"].fillna(0) >= min_state]
    if df.empty:
        st.warning("Filters removed every name. Loosen them.")
        return

    if run_governance:
        mcaps = dict(zip(df["ticker"], df["market_cap"]))
        gov = fetch_governance_frame(df["ticker"].tolist(), mcaps)
    else:
        gov = pd.DataFrame()

    scored = build_scorecard(df, gov)
    scored = scored[scored["red_flag_count"] <= max_red_flags]
    if scored.empty:
        st.warning("No names survived the red-flag cap.")
        return

    st.subheader("Top opportunities")
    show = scored.head(int(top_n))[DISPLAY_COLS].copy()
    show["market_cap"] = (show["market_cap"] / 1e9).round(2)
    for c in ("munger_score", "skin_in_game", "asymmetry",
              "downside_floor", "upside_potential", "governance_score"):
        show[c] = show[c].round(1)
    for c in ("state_pct", "dividend_yield", "payout_ratio", "return_on_equity"):
        show[c] = (show[c] * 100).round(2)
    show = show.rename(columns={"market_cap": "mcap_bn_local"})
    st.dataframe(show, hide_index=True, use_container_width=True)

    st.subheader("Score distribution")
    chart = scored.set_index("ticker")[
        ["skin_in_game", "downside_floor", "upside_potential", "governance_score"]
    ].head(int(top_n))
    st.bar_chart(chart)

    st.subheader("Drill-down")
    pick = st.selectbox("Ticker", scored["ticker"].tolist())
    if pick:
        row = scored[scored["ticker"] == pick].iloc[0]
        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("Munger", f"{row['munger_score']:.1f}")
        c2.metric("Skin in game", f"{row['skin_in_game']:.1f}")
        c3.metric("Downside", f"{row['downside_floor']:.1f}")
        c4.metric("Upside", f"{row['upside_potential']:.1f}")
        c5.metric("Governance", f"{row['governance_score']:.1f}")

        if row.get("red_flag_summary"):
            st.error("Red flags: " + row["red_flag_summary"])
        else:
            st.success("No governance red flags detected.")

        with st.expander("Per-share & cap-allocation detail", expanded=True):
            st.json({
                "share_count_3y_cagr": row.get("share_count_3y_cagr"),
                "ebitda_per_share_cagr": row.get("ebitda_per_share_cagr"),
                "fcf_per_share_cagr": row.get("fcf_per_share_cagr"),
                "accruals_ratio": row.get("accruals_ratio"),
                "capex_to_depreciation": row.get("capex_to_depreciation"),
                "fcf_to_ni": row.get("fcf_to_ni"),
                "buyback_yield": row.get("buyback_yield"),
                "issuance_yield": row.get("issuance_yield"),
            })

        st.json({k: row[k] for k in DISPLAY_COLS if k in row})

    st.download_button(
        "Download full scorecard (CSV)",
        scored.to_csv(index=False).encode(),
        file_name="soe_scorecard.csv",
        mime="text/csv",
    )
