"""Governance & capital-allocation signals.

Derived from "Corporate Dark Arts Gone Awry" (yetanothervalueblog) plus
standard accruals / earnings-quality literature. The thesis: management
can dress up aggregate metrics (EBITDA, market cap, headline growth) while
shareholders eat dilution, low-ROI capex, asset firesales, and accruals.
A Munger-style screen must treat these as multiplicative penalties on top
of valuation -- a great-looking P/B with persistent share issuance is a
trap, not an asymmetric bet.

All extractors are best-effort: yfinance's fundamental tables are noisy and
sometimes empty. Functions return `np.nan` when data is missing so callers
can score gracefully.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
import streamlit as st
import yfinance as yf


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _row(df: pd.DataFrame | None, *names: str) -> pd.Series | None:
    """First matching row from a yfinance financials DataFrame."""
    if df is None or df.empty:
        return None
    for n in names:
        if n in df.index:
            s = df.loc[n].dropna()
            if not s.empty:
                # yfinance returns most-recent-first; sort ascending by date
                return s.sort_index()
    return None


def _cagr(series: pd.Series, years: int = 3) -> float:
    if series is None or len(series) < 2:
        return float("nan")
    s = series.dropna()
    if len(s) < 2:
        return float("nan")
    s = s.tail(years + 1) if len(s) > years + 1 else s
    first, last = s.iloc[0], s.iloc[-1]
    if first is None or last is None or first <= 0 or last <= 0:
        return float("nan")
    n = len(s) - 1
    return (last / first) ** (1.0 / n) - 1.0


# ---------------------------------------------------------------------------
# Per-ticker signals
# ---------------------------------------------------------------------------

@dataclass
class GovernanceSignals:
    ticker: str
    share_count_3y_cagr: float            # > 0 = net dilution
    revenue_per_share_cagr: float
    ebitda_per_share_cagr: float
    fcf_per_share_cagr: float
    bvps_cagr: float
    accruals_ratio: float                  # (NI - CFO) / Total Assets, Sloan
    capex_to_depreciation: float           # > ~2 sustained = empire building
    fcf_to_ni: float                       # < 0.6 sustained = quality concern
    buyback_yield: float                   # repurchases / mcap, positive
    issuance_yield: float                  # issuance / mcap, positive
    asset_firesale_flag: bool              # large drop in PPE or assets
    red_flags: list[str]


@st.cache_data(show_spinner=False, ttl=60 * 60 * 6)
def fetch_governance(ticker: str, market_cap: float | None) -> GovernanceSignals | None:
    try:
        t = yf.Ticker(ticker)
        income = t.income_stmt
        cashflow = t.cashflow
        balance = t.balance_sheet
    except Exception:
        return None

    revenue = _row(income, "Total Revenue", "TotalRevenue", "Revenue")
    ebitda = _row(income, "EBITDA", "Normalized EBITDA")
    net_income = _row(income, "Net Income", "Net Income Common Stockholders")
    shares = _row(income, "Diluted Average Shares", "Basic Average Shares")
    if shares is None:
        try:
            sh = t.get_shares_full()
            if sh is not None and not sh.empty:
                shares = sh.resample("YE").last().sort_index()
        except Exception:
            shares = None

    cfo = _row(cashflow, "Operating Cash Flow", "Cash Flow From Continuing Operating Activities")
    capex = _row(cashflow, "Capital Expenditure")
    fcf = _row(cashflow, "Free Cash Flow")
    if fcf is None and cfo is not None and capex is not None:
        fcf = (cfo + capex).dropna()  # capex is negative in yfinance
    repurchases = _row(cashflow, "Repurchase Of Capital Stock", "Common Stock Repurchased")
    issuance = _row(cashflow, "Issuance Of Capital Stock", "Common Stock Issuance")
    depreciation = _row(cashflow, "Depreciation And Amortization",
                        "Depreciation Amortization Depletion")

    total_assets = _row(balance, "Total Assets")
    equity = _row(balance, "Stockholders Equity", "Common Stock Equity",
                  "Total Equity Gross Minority Interest")
    ppe = _row(balance, "Net PPE", "Gross PPE")

    # Per-share series
    def per_share(numer: pd.Series | None) -> pd.Series | None:
        if numer is None or shares is None:
            return None
        joined = pd.concat([numer, shares], axis=1, join="inner").dropna()
        if joined.empty:
            return None
        return joined.iloc[:, 0] / joined.iloc[:, 1]

    rev_ps = per_share(revenue)
    ebitda_ps = per_share(ebitda)
    fcf_ps = per_share(fcf)
    bvps = per_share(equity)

    share_cagr = _cagr(shares) if shares is not None else float("nan")

    # Accruals (Sloan): (NI - CFO) / avg total assets, latest year
    acc = float("nan")
    if net_income is not None and cfo is not None and total_assets is not None:
        try:
            ni_l = net_income.iloc[-1]
            cfo_l = cfo.iloc[-1]
            ta = total_assets.tail(2).mean() if len(total_assets) >= 2 else total_assets.iloc[-1]
            if ta and ta > 0:
                acc = (ni_l - cfo_l) / ta
        except Exception:
            pass

    # Capex / depreciation, recent 3y mean
    cap_dep = float("nan")
    if capex is not None and depreciation is not None:
        try:
            j = pd.concat([capex.abs(), depreciation], axis=1, join="inner").dropna().tail(3)
            if not j.empty:
                cap_dep = (j.iloc[:, 0] / j.iloc[:, 1].replace(0, np.nan)).mean()
        except Exception:
            pass

    # FCF / NI quality, 3y mean
    fcf_ni = float("nan")
    if fcf is not None and net_income is not None:
        try:
            j = pd.concat([fcf, net_income], axis=1, join="inner").dropna().tail(3)
            if not j.empty:
                fcf_ni = (j.iloc[:, 0] / j.iloc[:, 1].replace(0, np.nan)).mean()
        except Exception:
            pass

    # Buyback / issuance yields (latest year)
    bb_y = iss_y = float("nan")
    if market_cap and market_cap > 0:
        if repurchases is not None and len(repurchases):
            bb_y = float(abs(repurchases.iloc[-1])) / market_cap
        if issuance is not None and len(issuance):
            iss_y = float(abs(issuance.iloc[-1])) / market_cap

    # Asset firesale: PPE drops >15% YoY OR total assets drops >15%
    firesale = False
    for s in (ppe, total_assets):
        if s is not None and len(s) >= 2:
            try:
                if (s.iloc[-1] / s.iloc[-2] - 1) < -0.15:
                    firesale = True
                    break
            except Exception:
                pass

    # ------ Binary red flags (article-driven) -----------------------------
    flags: list[str] = []
    if share_cagr is not None and not np.isnan(share_cagr) and share_cagr > 0.02:
        flags.append(f"Persistent dilution: shares +{share_cagr*100:.1f}% CAGR")
    if iss_y > 0.03 and (np.isnan(bb_y) or bb_y < iss_y):
        flags.append(f"Net issuer this year ({iss_y*100:.1f}% of mcap)")
    if not np.isnan(acc) and acc > 0.10:
        flags.append(f"High accruals ({acc*100:.1f}%): NI > CFO")
    if not np.isnan(fcf_ni) and fcf_ni < 0.5:
        flags.append(f"Weak cash conversion (FCF/NI = {fcf_ni:.2f})")
    if not np.isnan(cap_dep) and cap_dep > 2.5:
        flags.append(f"Aggressive capex ({cap_dep:.1f}x depreciation)")
    if firesale:
        flags.append("Possible asset firesale: assets/PPE down >15% YoY")
    # Aggregate-vs-per-share divergence: revenue grew but rev/share didn't
    rev_cagr = _cagr(revenue) if revenue is not None else float("nan")
    rev_ps_cagr = _cagr(rev_ps) if rev_ps is not None else float("nan")
    if (not np.isnan(rev_cagr) and not np.isnan(rev_ps_cagr)
            and rev_cagr > 0.05 and (rev_cagr - rev_ps_cagr) > 0.03):
        flags.append("Aggregate growth outpaces per-share growth (dilution-funded)")

    return GovernanceSignals(
        ticker=ticker,
        share_count_3y_cagr=share_cagr,
        revenue_per_share_cagr=_cagr(rev_ps) if rev_ps is not None else float("nan"),
        ebitda_per_share_cagr=_cagr(ebitda_ps) if ebitda_ps is not None else float("nan"),
        fcf_per_share_cagr=_cagr(fcf_ps) if fcf_ps is not None else float("nan"),
        bvps_cagr=_cagr(bvps) if bvps is not None else float("nan"),
        accruals_ratio=acc,
        capex_to_depreciation=cap_dep,
        fcf_to_ni=fcf_ni,
        buyback_yield=bb_y if not np.isnan(bb_y) else 0.0,
        issuance_yield=iss_y if not np.isnan(iss_y) else 0.0,
        asset_firesale_flag=firesale,
        red_flags=flags,
    )


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

def _ratio01(val: float, target: float, higher_is_better: bool = True) -> float:
    if val is None or np.isnan(val) or target == 0:
        return 0.5
    s = val / target
    if not higher_is_better:
        s = 1.0 / s if s > 0 else 0.0
    return float(np.clip(s, 0.0, 1.0))


def score_governance(g: GovernanceSignals) -> float:
    """0-100. Rewards shrinking share count, growing per-share metrics,
    clean accruals, capex discipline, net buybacks."""
    # Dilution: -2% CAGR (buybacks) -> 1.0; +5% (heavy issuance) -> 0.0
    if np.isnan(g.share_count_3y_cagr):
        dilution = 0.5
    else:
        dilution = float(np.clip((0.05 - g.share_count_3y_cagr) / 0.07, 0.0, 1.0))

    rev_ps = _ratio01(g.revenue_per_share_cagr, 0.10) if not np.isnan(g.revenue_per_share_cagr) else 0.5
    ebitda_ps = _ratio01(g.ebitda_per_share_cagr, 0.12) if not np.isnan(g.ebitda_per_share_cagr) else 0.5
    fcf_ps = _ratio01(g.fcf_per_share_cagr, 0.10) if not np.isnan(g.fcf_per_share_cagr) else 0.5
    bvps = _ratio01(g.bvps_cagr, 0.10) if not np.isnan(g.bvps_cagr) else 0.5

    # Accruals: 0% -> 1.0, 10% -> 0.0
    if np.isnan(g.accruals_ratio):
        acc = 0.5
    else:
        acc = float(np.clip(1.0 - g.accruals_ratio / 0.10, 0.0, 1.0))

    # Capex discipline: 1.0x dep -> 1.0, 3x dep -> 0.0
    if np.isnan(g.capex_to_depreciation):
        capdisc = 0.5
    else:
        capdisc = float(np.clip(1.0 - max(0.0, g.capex_to_depreciation - 1.0) / 2.0, 0.0, 1.0))

    # FCF/NI: 1.0 -> 1.0, 0.4 -> 0.0
    if np.isnan(g.fcf_to_ni):
        fcfq = 0.5
    else:
        fcfq = float(np.clip((g.fcf_to_ni - 0.4) / 0.6, 0.0, 1.0))

    # Net buyback yield: +5% -> 1.0, -5% -> 0.0
    net_bb = (g.buyback_yield - g.issuance_yield)
    bb = float(np.clip((net_bb + 0.05) / 0.10, 0.0, 1.0))

    return 100.0 * (
        0.20 * dilution
        + 0.10 * rev_ps
        + 0.10 * ebitda_ps
        + 0.15 * fcf_ps
        + 0.05 * bvps
        + 0.15 * acc
        + 0.10 * capdisc
        + 0.10 * fcfq
        + 0.05 * bb
    )


def red_flag_penalty(g: GovernanceSignals) -> float:
    """Multiplier in [0.5, 1.0]. -7% per flag, floored at 0.5."""
    n = len(g.red_flags)
    if g.asset_firesale_flag and "Possible asset firesale" not in " ".join(g.red_flags):
        n += 1
    return float(max(0.5, 1.0 - 0.07 * n))


# ---------------------------------------------------------------------------
# Bulk
# ---------------------------------------------------------------------------

def fetch_governance_frame(tickers: list[str], mcaps: dict[str, float]) -> pd.DataFrame:
    rows = []
    progress = st.progress(0.0, text="Pulling governance signals...")
    for i, tk in enumerate(tickers, 1):
        g = fetch_governance(tk, mcaps.get(tk))
        if g is not None:
            d = g.__dict__.copy()
            d["governance_score"] = score_governance(g)
            d["red_flag_penalty"] = red_flag_penalty(g)
            d["red_flag_count"] = len(g.red_flags)
            d["red_flag_summary"] = "; ".join(g.red_flags) if g.red_flags else ""
            rows.append(d)
        progress.progress(i / max(len(tickers), 1), text=f"Governance: {tk}")
    progress.empty()
    return pd.DataFrame(rows) if rows else pd.DataFrame()
