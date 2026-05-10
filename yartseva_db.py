"""Yartseva-inspired multibagger fundamentals database.

Pulls the Italian equity universe from `financedatabase`, then for each ticker
pulls quarterly income statement, cash flow, balance sheet and price history
from yfinance.  Computes:

    * Yartseva multibagger composite score (growth + margin trend + cash
      quality + ROCE + balance-sheet strength + valuation-vs-growth).
    * Inflection / acceleration signals on Sales, EBITDA, Operating Cash
      Flow and Free Cash Flow on YoY (4Q vs 4Q ago), QoQ (4-quarter trailing
      vs prior 4-quarter trailing) and sequential (latest quarter vs prior
      quarter) bases.
    * "Not priced in" divergence: fundamental momentum minus price /
      multiple movement over the same window.

Usage:
    python yartseva_db.py --max 50 --out italian_yartseva.csv

Use ``--max 0`` to scan the whole Italian universe (slow, ~hour).
"""

from __future__ import annotations

import argparse
import math
import sys
import time
import warnings
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, asdict
from typing import Optional

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

# Map yfinance row label aliases - yfinance row names drift between releases.
INCOME_ALIASES = {
    "revenue": ["Total Revenue", "Operating Revenue", "TotalRevenue"],
    "ebitda": ["EBITDA", "Normalized EBITDA"],
    "ebit": ["EBIT", "Operating Income"],
    "net_income": ["Net Income", "Net Income Common Stockholders"],
}
CASHFLOW_ALIASES = {
    "cfo": ["Operating Cash Flow", "Total Cash From Operating Activities"],
    "capex": ["Capital Expenditure", "Capital Expenditures"],
    "fcf": ["Free Cash Flow"],
}
BALANCE_ALIASES = {
    "total_assets": ["Total Assets"],
    "current_liab": ["Current Liabilities", "Total Current Liabilities"],
    "total_debt": ["Total Debt"],
    "net_debt": ["Net Debt"],
    "cash": ["Cash And Cash Equivalents", "Cash"],
    "equity": ["Stockholders Equity", "Common Stock Equity", "Total Stockholder Equity"],
    "invested_capital": ["Invested Capital"],
}


def first_row(df: pd.DataFrame, names: list[str]) -> Optional[pd.Series]:
    if df is None or df.empty:
        return None
    for n in names:
        if n in df.index:
            return df.loc[n]
    return None


def safe_div(a, b):
    try:
        if b is None or pd.isna(b) or b == 0:
            return np.nan
        return a / b
    except Exception:
        return np.nan


def pct_change(curr, prior) -> float:
    if curr is None or prior is None or pd.isna(curr) or pd.isna(prior):
        return np.nan
    if prior == 0:
        return np.nan
    return (curr - prior) / abs(prior)


def trailing_sum(series: pd.Series, n: int = 4) -> Optional[float]:
    """Sum the most recent n columns of a yfinance financial series.

    yfinance returns columns ordered newest-first as Timestamps.
    """
    if series is None or len(series) < n:
        return None
    vals = series.iloc[:n].astype(float)
    if vals.isna().any():
        return None
    return float(vals.sum())


@dataclass
class TickerRow:
    symbol: str
    name: str
    sector: str
    industry: str
    market_cap_bucket: str
    currency: str
    market_cap: float
    enterprise_value: float
    price: float
    # Trailing levels (TTM)
    revenue_ttm: float
    ebitda_ttm: float
    cfo_ttm: float
    fcf_ttm: float
    # Margins
    ebitda_margin: float
    fcf_margin: float
    # Quality / capital efficiency
    cash_conversion: float  # CFO / EBITDA
    roce: float  # EBIT / (Equity + Debt - Cash)
    net_debt_ebitda: float
    # Valuation
    ev_sales: float
    ev_ebitda: float
    fcf_yield: float
    # Yoy growth (TTM vs prior TTM)
    rev_yoy: float
    ebitda_yoy: float
    cfo_yoy: float
    fcf_yoy: float
    # Margin delta YoY (pp)
    ebitda_margin_delta_yoy: float
    fcf_margin_delta_yoy: float
    # QoQ growth (latest 4Q TTM vs prior 4Q TTM, i.e. 1-quarter shift)
    rev_qoq_ttm: float
    ebitda_qoq_ttm: float
    cfo_qoq_ttm: float
    fcf_qoq_ttm: float
    # Sequential (latest single quarter vs prior single quarter)
    rev_seq: float
    ebitda_seq: float
    cfo_seq: float
    fcf_seq: float
    # Acceleration: change in YoY growth between latest and prior quarter
    rev_accel: float
    ebitda_accel: float
    cfo_accel: float
    fcf_accel: float
    # Inflection flags (sign-flip negative -> positive on growth, single quarter)
    rev_inflection: int
    ebitda_inflection: int
    cfo_inflection: int
    fcf_inflection: int
    # Price vs fundamentals divergence (what's not priced in)
    price_yoy: float
    price_minus_rev_yoy: float
    price_minus_ebitda_yoy: float
    price_minus_fcf_yoy: float
    ev_sales_change_yoy: float
    not_priced_in_score: float
    # Yartseva composite
    yartseva_score: float
    notes: str


# -------------- core fetch + compute -----------------

def fetch_ticker(symbol: str, info_meta: dict) -> Optional[TickerRow]:
    import yfinance as yf

    try:
        t = yf.Ticker(symbol)
        qis = t.quarterly_income_stmt
        qcf = t.quarterly_cashflow
        qbs = t.quarterly_balance_sheet
        ais = t.income_stmt          # annual
        acf = t.cashflow             # annual
        abs_ = t.balance_sheet       # annual
        info = t.info or {}
    except Exception:
        return None

    # If neither quarterly nor annual income statement is present, skip.
    have_any = (qis is not None and not qis.empty) or (ais is not None and not ais.empty)
    if not have_any:
        return None

    def sort_cols(df):
        if df is None or df.empty:
            return df
        return df.reindex(sorted(df.columns, reverse=True), axis=1)

    qis = sort_cols(qis); qcf = sort_cols(qcf); qbs = sort_cols(qbs)
    ais = sort_cols(ais); acf = sort_cols(acf); abs_ = sort_cols(abs_)

    rev_q = first_row(qis, INCOME_ALIASES["revenue"])
    ebitda_q = first_row(qis, INCOME_ALIASES["ebitda"])
    ebit_q = first_row(qis, INCOME_ALIASES["ebit"])
    cfo_q = first_row(qcf, CASHFLOW_ALIASES["cfo"])
    fcf_q = first_row(qcf, CASHFLOW_ALIASES["fcf"])
    capex_q = first_row(qcf, CASHFLOW_ALIASES["capex"])

    rev_a = first_row(ais, INCOME_ALIASES["revenue"])
    ebitda_a = first_row(ais, INCOME_ALIASES["ebitda"])
    ebit_a = first_row(ais, INCOME_ALIASES["ebit"])
    cfo_a = first_row(acf, CASHFLOW_ALIASES["cfo"])
    fcf_a = first_row(acf, CASHFLOW_ALIASES["fcf"])
    capex_a = first_row(acf, CASHFLOW_ALIASES["capex"])

    # Build FCF if missing on either cadence.
    if fcf_q is None and cfo_q is not None and capex_q is not None:
        idx = cfo_q.index.intersection(capex_q.index)
        fcf_q = cfo_q.reindex(idx).astype(float) + capex_q.reindex(idx).astype(float)
    if fcf_a is None and cfo_a is not None and capex_a is not None:
        idx = cfo_a.index.intersection(capex_a.index)
        fcf_a = cfo_a.reindex(idx).astype(float) + capex_a.reindex(idx).astype(float)

    def col_count(s):
        return 0 if s is None else len(s)

    have_q = col_count(rev_q) >= 5  # enough quarters for single-Q YoY
    have_q_ttm = col_count(rev_q) >= 8  # enough for full TTM YoY
    have_a = col_count(rev_a) >= 2

    # ---- Pick TTM level: prefer 4-quarter trailing if dense enough, else most recent annual ----
    def ttm_or_annual(qseries, aseries):
        if qseries is not None and len(qseries) >= 4:
            v = trailing_sum(qseries, 4)
            if v is not None:
                return v
        if aseries is not None and len(aseries) >= 1:
            v = aseries.iloc[0]
            return float(v) if pd.notna(v) else None
        return None

    rev_ttm = ttm_or_annual(rev_q, rev_a)
    ebitda_ttm = ttm_or_annual(ebitda_q, ebitda_a)
    cfo_ttm = ttm_or_annual(cfo_q, cfo_a)
    fcf_ttm = ttm_or_annual(fcf_q, fcf_a)
    ebit_ttm = ttm_or_annual(ebit_q, ebit_a)

    # Prior TTM (8q->4q earlier) or prior annual
    def ttm_prev_or_annual(qseries, aseries):
        if qseries is not None and len(qseries) >= 8:
            v = trailing_sum(qseries.iloc[4:], 4)
            if v is not None:
                return v
        if aseries is not None and len(aseries) >= 2:
            v = aseries.iloc[1]
            return float(v) if pd.notna(v) else None
        return None

    rev_ttm_prev = ttm_prev_or_annual(rev_q, rev_a)
    ebitda_ttm_prev = ttm_prev_or_annual(ebitda_q, ebitda_a)
    cfo_ttm_prev = ttm_prev_or_annual(cfo_q, cfo_a)
    fcf_ttm_prev = ttm_prev_or_annual(fcf_q, fcf_a)

    # 1-quarter shifted TTM (only meaningful with full quarterly data)
    rev_ttm_q1 = trailing_sum(rev_q.iloc[1:], 4) if (rev_q is not None and len(rev_q) >= 5) else None
    ebitda_ttm_q1 = trailing_sum(ebitda_q.iloc[1:], 4) if (ebitda_q is not None and len(ebitda_q) >= 5) else None
    cfo_ttm_q1 = trailing_sum(cfo_q.iloc[1:], 4) if (cfo_q is not None and len(cfo_q) >= 5) else None
    fcf_ttm_q1 = trailing_sum(fcf_q.iloc[1:], 4) if (fcf_q is not None and len(fcf_q) >= 5) else None

    # Aliases for downstream code that expects q-series; fall back to annual if quarterly missing.
    rev = rev_q if rev_q is not None else rev_a
    ebitda = ebitda_q if ebitda_q is not None else ebitda_a
    cfo = cfo_q if cfo_q is not None else cfo_a
    fcf = fcf_q if fcf_q is not None else fcf_a
    ebit = ebit_q if ebit_q is not None else ebit_a

    # ---- Single-quarter ----
    def q(series, i):
        if series is None or len(series) <= i:
            return np.nan
        v = series.iloc[i]
        return float(v) if pd.notna(v) else np.nan

    rev_q0, rev_q1, rev_q4, rev_q5 = q(rev, 0), q(rev, 1), q(rev, 4), q(rev, 5)
    ebitda_q0, ebitda_q1, ebitda_q4, ebitda_q5 = q(ebitda, 0), q(ebitda, 1), q(ebitda, 4), q(ebitda, 5)
    cfo_q0, cfo_q1, cfo_q4, cfo_q5 = q(cfo, 0), q(cfo, 1), q(cfo, 4), q(cfo, 5)
    fcf_q0, fcf_q1, fcf_q4, fcf_q5 = q(fcf, 0), q(fcf, 1), q(fcf, 4), q(fcf, 5)

    # YoY growth on single-quarter and on TTM
    rev_yoy_q = pct_change(rev_q0, rev_q4)
    rev_yoy_q_prev = pct_change(rev_q1, rev_q5)
    ebitda_yoy_q = pct_change(ebitda_q0, ebitda_q4)
    ebitda_yoy_q_prev = pct_change(ebitda_q1, ebitda_q5)
    cfo_yoy_q = pct_change(cfo_q0, cfo_q4)
    cfo_yoy_q_prev = pct_change(cfo_q1, cfo_q5)
    fcf_yoy_q = pct_change(fcf_q0, fcf_q4)
    fcf_yoy_q_prev = pct_change(fcf_q1, fcf_q5)

    rev_yoy = pct_change(rev_ttm, rev_ttm_prev)
    ebitda_yoy = pct_change(ebitda_ttm, ebitda_ttm_prev)
    cfo_yoy = pct_change(cfo_ttm, cfo_ttm_prev)
    fcf_yoy = pct_change(fcf_ttm, fcf_ttm_prev)

    # QoQ on TTM = roll-forward TTM 1 quarter
    rev_qoq_ttm = pct_change(rev_ttm, rev_ttm_q1)
    ebitda_qoq_ttm = pct_change(ebitda_ttm, ebitda_ttm_q1)
    cfo_qoq_ttm = pct_change(cfo_ttm, cfo_ttm_q1)
    fcf_qoq_ttm = pct_change(fcf_ttm, fcf_ttm_q1)

    # Sequential = single Q vs prior single Q (subject to seasonality, kept raw)
    rev_seq = pct_change(rev_q0, rev_q1)
    ebitda_seq = pct_change(ebitda_q0, ebitda_q1)
    cfo_seq = pct_change(cfo_q0, cfo_q1)
    fcf_seq = pct_change(fcf_q0, fcf_q1)

    # Quarterly-based acceleration / inflection
    rev_accel = (rev_yoy_q - rev_yoy_q_prev) if (pd.notna(rev_yoy_q) and pd.notna(rev_yoy_q_prev)) else np.nan
    ebitda_accel = (ebitda_yoy_q - ebitda_yoy_q_prev) if (pd.notna(ebitda_yoy_q) and pd.notna(ebitda_yoy_q_prev)) else np.nan
    cfo_accel = (cfo_yoy_q - cfo_yoy_q_prev) if (pd.notna(cfo_yoy_q) and pd.notna(cfo_yoy_q_prev)) else np.nan
    fcf_accel = (fcf_yoy_q - fcf_yoy_q_prev) if (pd.notna(fcf_yoy_q) and pd.notna(fcf_yoy_q_prev)) else np.nan

    # Annual fallback for acceleration: needs 3 years (yoy_now - yoy_prev).
    def annual_yoy(s, lag):
        if s is None or len(s) < lag + 2:
            return np.nan
        c = q(s, lag); p = q(s, lag + 1)
        return pct_change(c, p)

    if pd.isna(rev_accel):
        rev_accel = (annual_yoy(rev_a, 0) - annual_yoy(rev_a, 1)) if (rev_a is not None and len(rev_a) >= 3) else np.nan
    if pd.isna(ebitda_accel):
        ebitda_accel = (annual_yoy(ebitda_a, 0) - annual_yoy(ebitda_a, 1)) if (ebitda_a is not None and len(ebitda_a) >= 3) else np.nan
    if pd.isna(cfo_accel):
        cfo_accel = (annual_yoy(cfo_a, 0) - annual_yoy(cfo_a, 1)) if (cfo_a is not None and len(cfo_a) >= 3) else np.nan
    if pd.isna(fcf_accel):
        fcf_accel = (annual_yoy(fcf_a, 0) - annual_yoy(fcf_a, 1)) if (fcf_a is not None and len(fcf_a) >= 3) else np.nan

    # Inflections: prior YoY <= 0 and current YoY > 0 (sign-flip up).
    def inflect(curr, prev):
        if pd.isna(curr) or pd.isna(prev):
            return 0
        return int(prev <= 0 and curr > 0)

    rev_inflection = inflect(rev_yoy_q, rev_yoy_q_prev)
    ebitda_inflection = inflect(ebitda_yoy_q, ebitda_yoy_q_prev)
    cfo_inflection = inflect(cfo_yoy_q, cfo_yoy_q_prev)
    fcf_inflection = inflect(fcf_yoy_q, fcf_yoy_q_prev)

    # Annual fallback for inflection: most recent annual YoY positive while prior year negative.
    if not rev_inflection and rev_a is not None and len(rev_a) >= 3:
        rev_inflection = inflect(annual_yoy(rev_a, 0), annual_yoy(rev_a, 1))
    if not ebitda_inflection and ebitda_a is not None and len(ebitda_a) >= 3:
        ebitda_inflection = inflect(annual_yoy(ebitda_a, 0), annual_yoy(ebitda_a, 1))
    if not cfo_inflection and cfo_a is not None and len(cfo_a) >= 3:
        cfo_inflection = inflect(annual_yoy(cfo_a, 0), annual_yoy(cfo_a, 1))
    if not fcf_inflection and fcf_a is not None and len(fcf_a) >= 3:
        fcf_inflection = inflect(annual_yoy(fcf_a, 0), annual_yoy(fcf_a, 1))

    # Margins
    ebitda_margin = safe_div(ebitda_ttm, rev_ttm)
    fcf_margin = safe_div(fcf_ttm, rev_ttm)
    cash_conversion = safe_div(cfo_ttm, ebitda_ttm)
    ebitda_margin_prev = safe_div(ebitda_ttm_prev, rev_ttm_prev)
    fcf_margin_prev = safe_div(fcf_ttm_prev, rev_ttm_prev)
    ebitda_margin_delta_yoy = (ebitda_margin - ebitda_margin_prev) if (pd.notna(ebitda_margin) and pd.notna(ebitda_margin_prev)) else np.nan
    fcf_margin_delta_yoy = (fcf_margin - fcf_margin_prev) if (pd.notna(fcf_margin) and pd.notna(fcf_margin_prev)) else np.nan

    # Capital efficiency / leverage – prefer quarterly, fall back to annual
    def first_row_with_fallback(qdf, adf, names):
        s = first_row(qdf, names) if qdf is not None else None
        if s is None or s.empty:
            s = first_row(adf, names) if adf is not None else None
        return s

    equity = first_row_with_fallback(qbs, abs_, BALANCE_ALIASES["equity"])
    debt = first_row_with_fallback(qbs, abs_, BALANCE_ALIASES["total_debt"])
    cash_bs = first_row_with_fallback(qbs, abs_, BALANCE_ALIASES["cash"])
    net_debt_row = first_row_with_fallback(qbs, abs_, BALANCE_ALIASES["net_debt"])

    eq_v = q(equity, 0)
    debt_v = q(debt, 0)
    cash_v = q(cash_bs, 0)
    nd_v = q(net_debt_row, 0)
    if pd.isna(nd_v) and pd.notna(debt_v) and pd.notna(cash_v):
        nd_v = debt_v - cash_v

    invested_capital = (eq_v + debt_v - cash_v) if (pd.notna(eq_v) and pd.notna(debt_v) and pd.notna(cash_v)) else np.nan
    roce = safe_div(ebit_ttm, invested_capital) if pd.notna(invested_capital) else np.nan
    net_debt_ebitda = safe_div(nd_v, ebitda_ttm) if pd.notna(nd_v) else np.nan

    # Valuation
    market_cap = info.get("marketCap")
    enterprise_value = info.get("enterpriseValue") or (
        (market_cap or 0) + (nd_v if pd.notna(nd_v) else 0)
    )
    price = info.get("currentPrice") or info.get("regularMarketPrice") or np.nan
    ev_sales = safe_div(enterprise_value, rev_ttm) if rev_ttm else np.nan
    ev_ebitda = safe_div(enterprise_value, ebitda_ttm) if ebitda_ttm else np.nan
    fcf_yield = safe_div(fcf_ttm, market_cap) if market_cap else np.nan

    # Price 1y change vs fundamentals (what's not priced in)
    try:
        hist = t.history(period="2y", interval="1d", auto_adjust=True)
        if hist is not None and not hist.empty:
            close = hist["Close"].dropna()
            price_now = float(close.iloc[-1])
            # Approx price 1y ago = ~252 trading days back (or first available)
            idx_1y = max(0, len(close) - 252)
            price_1y = float(close.iloc[idx_1y])
            price_yoy = pct_change(price_now, price_1y)
        else:
            price_yoy = np.nan
    except Exception:
        price_yoy = np.nan

    # Approx prior EV/Sales using prior TTM and current EV deflated by price change
    if pd.notna(price_yoy) and pd.notna(ev_sales) and rev_ttm_prev:
        ev_prev_est = enterprise_value / (1 + price_yoy) if (1 + price_yoy) != 0 else np.nan
        ev_sales_prev = safe_div(ev_prev_est, rev_ttm_prev)
        ev_sales_change_yoy = pct_change(ev_sales, ev_sales_prev)
    else:
        ev_sales_change_yoy = np.nan

    price_minus_rev_yoy = (price_yoy - rev_yoy) if (pd.notna(price_yoy) and pd.notna(rev_yoy)) else np.nan
    price_minus_ebitda_yoy = (price_yoy - ebitda_yoy) if (pd.notna(price_yoy) and pd.notna(ebitda_yoy)) else np.nan
    price_minus_fcf_yoy = (price_yoy - fcf_yoy) if (pd.notna(price_yoy) and pd.notna(fcf_yoy)) else np.nan

    # "Not priced in" score: positive when fundamentals up but multiple compressed / price lagged
    components_npi = []
    if pd.notna(rev_yoy) and pd.notna(price_yoy):
        components_npi.append(rev_yoy - price_yoy)
    if pd.notna(ebitda_yoy) and pd.notna(price_yoy):
        components_npi.append(ebitda_yoy - price_yoy)
    if pd.notna(fcf_yoy) and pd.notna(price_yoy):
        components_npi.append(fcf_yoy - price_yoy)
    if pd.notna(ev_sales_change_yoy) and pd.notna(rev_yoy) and rev_yoy > 0:
        # Multiple compressed while sales grew = "not priced in"
        components_npi.append(-ev_sales_change_yoy)
    not_priced_in_score = float(np.mean(components_npi)) if components_npi else np.nan

    # ----- Yartseva composite -----
    # Soft logistic-style scoring. Each sub-score in [0,1].
    def clip01(x):
        if pd.isna(x):
            return np.nan
        return float(max(0.0, min(1.0, x)))

    growth_score = clip01((rev_yoy + 0.05) / 0.40) if pd.notna(rev_yoy) else np.nan  # 0% -> 0.125, 35%+ -> 1
    accel_score = clip01((rev_accel + 0.05) / 0.30) if pd.notna(rev_accel) else np.nan
    margin_score = clip01((ebitda_margin_delta_yoy + 0.01) / 0.05) if pd.notna(ebitda_margin_delta_yoy) else np.nan
    cash_quality = clip01((cash_conversion - 0.5) / 0.7) if pd.notna(cash_conversion) else np.nan
    roce_score = clip01((roce - 0.05) / 0.20) if pd.notna(roce) else np.nan
    leverage_score = (
        clip01((3.0 - net_debt_ebitda) / 4.0) if pd.notna(net_debt_ebitda) else 0.5
    )
    # Valuation vs growth: lower EV/Sales relative to growth = higher score.
    if pd.notna(ev_sales) and ev_sales > 0 and pd.notna(rev_yoy):
        peg_like = ev_sales / max(rev_yoy + 0.05, 0.05)  # lower is better
        valuation_score = clip01((6.0 - peg_like) / 6.0)
    else:
        valuation_score = np.nan
    fcf_yield_score = clip01((fcf_yield - 0.0) / 0.12) if pd.notna(fcf_yield) else np.nan

    weights = {
        "growth": 0.20,
        "accel": 0.15,
        "margin": 0.15,
        "cash_quality": 0.10,
        "roce": 0.15,
        "leverage": 0.05,
        "valuation": 0.10,
        "fcf_yield": 0.10,
    }
    parts = {
        "growth": growth_score,
        "accel": accel_score,
        "margin": margin_score,
        "cash_quality": cash_quality,
        "roce": roce_score,
        "leverage": leverage_score,
        "valuation": valuation_score,
        "fcf_yield": fcf_yield_score,
    }
    total_w = 0.0
    total_v = 0.0
    for k, v in parts.items():
        if pd.notna(v):
            total_w += weights[k]
            total_v += weights[k] * v
    yartseva_score = (total_v / total_w) if total_w > 0 else np.nan

    notes_parts = []
    if rev_inflection or ebitda_inflection or fcf_inflection:
        notes_parts.append("inflection")
    if pd.notna(rev_accel) and rev_accel > 0.05:
        notes_parts.append("accelerating sales")
    if pd.notna(not_priced_in_score) and not_priced_in_score > 0.10:
        notes_parts.append("under-priced vs fundamentals")
    notes = "; ".join(notes_parts)

    return TickerRow(
        symbol=symbol,
        name=info_meta.get("name", info.get("shortName", "")),
        sector=info_meta.get("sector", ""),
        industry=info_meta.get("industry", ""),
        market_cap_bucket=info_meta.get("market_cap", ""),
        currency=info_meta.get("currency", info.get("currency", "")),
        market_cap=float(market_cap) if market_cap else np.nan,
        enterprise_value=float(enterprise_value) if enterprise_value else np.nan,
        price=float(price) if pd.notna(price) else np.nan,
        revenue_ttm=rev_ttm if rev_ttm else np.nan,
        ebitda_ttm=ebitda_ttm if ebitda_ttm else np.nan,
        cfo_ttm=cfo_ttm if cfo_ttm else np.nan,
        fcf_ttm=fcf_ttm if fcf_ttm else np.nan,
        ebitda_margin=ebitda_margin,
        fcf_margin=fcf_margin,
        cash_conversion=cash_conversion,
        roce=roce,
        net_debt_ebitda=net_debt_ebitda,
        ev_sales=ev_sales,
        ev_ebitda=ev_ebitda,
        fcf_yield=fcf_yield,
        rev_yoy=rev_yoy,
        ebitda_yoy=ebitda_yoy,
        cfo_yoy=cfo_yoy,
        fcf_yoy=fcf_yoy,
        ebitda_margin_delta_yoy=ebitda_margin_delta_yoy,
        fcf_margin_delta_yoy=fcf_margin_delta_yoy,
        rev_qoq_ttm=rev_qoq_ttm,
        ebitda_qoq_ttm=ebitda_qoq_ttm,
        cfo_qoq_ttm=cfo_qoq_ttm,
        fcf_qoq_ttm=fcf_qoq_ttm,
        rev_seq=rev_seq,
        ebitda_seq=ebitda_seq,
        cfo_seq=cfo_seq,
        fcf_seq=fcf_seq,
        rev_accel=rev_accel,
        ebitda_accel=ebitda_accel,
        cfo_accel=cfo_accel,
        fcf_accel=fcf_accel,
        rev_inflection=rev_inflection,
        ebitda_inflection=ebitda_inflection,
        cfo_inflection=cfo_inflection,
        fcf_inflection=fcf_inflection,
        price_yoy=price_yoy,
        price_minus_rev_yoy=price_minus_rev_yoy,
        price_minus_ebitda_yoy=price_minus_ebitda_yoy,
        price_minus_fcf_yoy=price_minus_fcf_yoy,
        ev_sales_change_yoy=ev_sales_change_yoy,
        not_priced_in_score=not_priced_in_score,
        yartseva_score=yartseva_score,
        notes=notes,
    )


def get_italian_universe(min_bucket: Optional[str] = None) -> pd.DataFrame:
    import financedatabase as fd

    eq = fd.Equities()
    italy = eq.select(country="Italy")
    # Restrict to .MI listing where actual quarterly fundamentals are reachable.
    italy = italy[italy.index.str.endswith(".MI")]
    if min_bucket:
        order = ["Nano Cap", "Micro Cap", "Small Cap", "Mid Cap", "Large Cap", "Mega Cap"]
        if min_bucket in order:
            allowed = set(order[order.index(min_bucket):])
            italy = italy[italy["market_cap"].isin(allowed)]
    return italy


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--max", type=int, default=40, help="max tickers to fetch (0 = all)")
    parser.add_argument("--min-bucket", default="Small Cap",
                        help="minimum financedatabase market_cap bucket (Nano/Micro/Small/Mid/Large)")
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--out", default="italian_yartseva.csv")
    parser.add_argument("--top", type=int, default=15, help="rows printed in console summary")
    args = parser.parse_args()

    print(f"[1/3] Loading Italian universe (min bucket={args.min_bucket}) ...", file=sys.stderr)
    universe = get_italian_universe(args.min_bucket)
    print(f"      universe size = {len(universe)}", file=sys.stderr)

    if args.max and args.max > 0:
        universe = universe.head(args.max)
    print(f"      scanning {len(universe)} tickers with {args.workers} workers", file=sys.stderr)

    rows: list[TickerRow] = []
    start = time.time()
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futures = {
            ex.submit(fetch_ticker, sym, meta.to_dict()): sym
            for sym, meta in universe.iterrows()
        }
        done = 0
        for fut in as_completed(futures):
            sym = futures[fut]
            done += 1
            try:
                row = fut.result()
            except Exception as e:
                print(f"   {sym}: {e}", file=sys.stderr)
                row = None
            if row is not None:
                rows.append(row)
            if done % 10 == 0:
                print(f"      {done}/{len(universe)} done ({len(rows)} kept) "
                      f"elapsed {time.time()-start:.0f}s", file=sys.stderr)

    if not rows:
        print("No tickers produced data.", file=sys.stderr)
        sys.exit(1)

    df = pd.DataFrame([asdict(r) for r in rows])
    df = df.sort_values("yartseva_score", ascending=False, na_position="last")
    df.to_csv(args.out, index=False)
    print(f"\n[2/3] wrote {len(df)} rows -> {args.out}", file=sys.stderr)

    # Console summary
    pd.set_option("display.width", 220)
    pd.set_option("display.max_columns", 12)
    pd.set_option("display.float_format", lambda x: f"{x:.3f}")

    print("\n=== TOP BY YARTSEVA MULTIBAGGER SCORE ===")
    cols = ["symbol", "name", "sector", "yartseva_score",
            "rev_yoy", "ebitda_yoy", "fcf_yoy", "rev_accel",
            "ebitda_margin", "roce", "ev_sales", "fcf_yield"]
    print(df.head(args.top)[cols].to_string(index=False))

    print("\n=== INFLECTIONS (rev/ebitda/fcf YoY sign-flip up) ===")
    inf = df[(df["rev_inflection"] == 1) | (df["ebitda_inflection"] == 1) | (df["fcf_inflection"] == 1)]
    cols = ["symbol", "name", "rev_inflection", "ebitda_inflection", "fcf_inflection",
            "rev_yoy", "ebitda_yoy", "fcf_yoy", "yartseva_score"]
    print(inf.head(args.top)[cols].to_string(index=False) if len(inf) else "  (none)")

    print("\n=== TOP 'NOT PRICED IN' (fundamentals ahead of price/multiple) ===")
    cols = ["symbol", "name", "not_priced_in_score", "price_yoy",
            "rev_yoy", "ebitda_yoy", "fcf_yoy", "ev_sales_change_yoy", "yartseva_score"]
    npi = df.sort_values("not_priced_in_score", ascending=False)
    print(npi.head(args.top)[cols].to_string(index=False))

    print("\n=== TOP ACCELERATION (latest quarter YoY growth - prior quarter YoY growth) ===")
    cols = ["symbol", "name", "rev_accel", "ebitda_accel", "fcf_accel",
            "rev_yoy", "ebitda_yoy", "yartseva_score"]
    accel = df.sort_values("rev_accel", ascending=False)
    print(accel.head(args.top)[cols].to_string(index=False))

    print(f"\n[3/3] done in {time.time()-start:.0f}s", file=sys.stderr)


if __name__ == "__main__":
    main()
