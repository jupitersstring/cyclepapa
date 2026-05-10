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
    ev_ebit: float
    pb: float
    fcf_yield: float
    ncav: float
    ncav_pct_mcap: float
    # Cheapness composites (lower = cheaper)
    cheapness_growth_blend: float        # 1/3 sales + 1/3 ebitda + 1/6 fcf + 1/6 ncav%
    cheapness_ev_ebit_vs_growth: float   # ev_ebit / cheapness_growth_blend
    cheapness_under_7x_flag: int         # ev_ebit < 7 AND blend > 0
    cheapness_blend_vs_growth: float     # ((pb+ev_ebit)/2) / ((sales_yoy+ebitda_yoy)/2)
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
    # YoY-growth sign-flip up (growth rate crossed zero from below)
    rev_inflection: int
    ebitda_inflection: int
    cfo_inflection: int
    fcf_inflection: int
    # Level sign-flip: prior period <= 0, current period > 0 (first positive print)
    ebitda_first_positive: int
    cfo_first_positive: int
    fcf_first_positive: int
    net_income_first_positive: int
    # ROCE inflection
    roce_prev: float
    roce_delta_yoy: float
    roce_inflection: int
    roce_first_positive: int
    # Forward-projected break-even (linear run-rate of improvement)
    fcf_run_rate_delta: float
    fcf_eta_quarters: float
    fcf_eta_years: float
    ebitda_eta_years: float
    cfo_eta_years: float
    ni_eta_years: float
    fcf_projected_positive_in_n: int
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

    # Retry yfinance calls a few times on transient rate-limit errors.
    attempts = 4
    last_err = None
    for attempt in range(attempts):
        try:
            t = yf.Ticker(symbol)
            qis = t.quarterly_income_stmt
            qcf = t.quarterly_cashflow
            qbs = t.quarterly_balance_sheet
            ais = t.income_stmt          # annual
            acf = t.cashflow             # annual
            abs_ = t.balance_sheet       # annual
            info = t.info or {}
            break
        except Exception as e:
            last_err = e
            msg = str(e)
            transient = (
                "401" in msg or "429" in msg or "Crumb" in msg
                or "Too Many Requests" in msg or "Rate limit" in msg
                or "rate limit" in msg or "YFRateLimitError" in msg
            )
            if transient and attempt < attempts - 1:
                time.sleep(5 * (attempt + 1))
                continue
            return None
    else:
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
    ni_q = first_row(qis, INCOME_ALIASES["net_income"])
    cfo_q = first_row(qcf, CASHFLOW_ALIASES["cfo"])
    fcf_q = first_row(qcf, CASHFLOW_ALIASES["fcf"])
    capex_q = first_row(qcf, CASHFLOW_ALIASES["capex"])

    rev_a = first_row(ais, INCOME_ALIASES["revenue"])
    ebitda_a = first_row(ais, INCOME_ALIASES["ebitda"])
    ebit_a = first_row(ais, INCOME_ALIASES["ebit"])
    ni_a = first_row(ais, INCOME_ALIASES["net_income"])
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
    ni_ttm = ttm_or_annual(ni_q, ni_a)

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
    ni_ttm_prev = ttm_prev_or_annual(ni_q, ni_a)

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

    # Level sign-flip ("first positive"): current TTM/annual > 0 while prior <= 0.
    # Distinct from the YoY-growth flip above: this is the level itself crossing
    # zero from below (e.g. first positive FCF print after years of burn).
    def first_pos(curr, prev):
        if curr is None or prev is None or pd.isna(curr) or pd.isna(prev):
            return 0
        return int(prev <= 0 and curr > 0)

    ebitda_first_positive = first_pos(ebitda_ttm, ebitda_ttm_prev)
    cfo_first_positive = first_pos(cfo_ttm, cfo_ttm_prev)
    fcf_first_positive = first_pos(fcf_ttm, fcf_ttm_prev)
    net_income_first_positive = first_pos(ni_ttm, ni_ttm_prev)

    # ROCE inflection — needs prior-period ROCE = EBIT_prev / IC_prev.
    # Use prior-year balance sheet column where available; if ROCE was already
    # computed below, we recompute it here in a self-contained block since
    # the balance-sheet rows are needed.
    def prior_bs_value(qdf, adf, names):
        # Prefer second annual column (i.e. one year ago) if present, else
        # second quarterly column (one quarter ago) as a fallback.
        adf_row = first_row(adf, names) if adf is not None else None
        if adf_row is not None and len(adf_row) >= 2:
            v = adf_row.iloc[1]
            if pd.notna(v):
                return float(v)
        qdf_row = first_row(qdf, names) if qdf is not None else None
        if qdf_row is not None and len(qdf_row) >= 5:
            v = qdf_row.iloc[4]  # 4 quarters back
            if pd.notna(v):
                return float(v)
        return None

    eq_prev = prior_bs_value(qbs, abs_, BALANCE_ALIASES["equity"])
    debt_prev = prior_bs_value(qbs, abs_, BALANCE_ALIASES["total_debt"])
    cash_prev = prior_bs_value(qbs, abs_, BALANCE_ALIASES["cash"])
    ic_prev = (eq_prev + debt_prev - cash_prev) if (eq_prev is not None and debt_prev is not None and cash_prev is not None) else None

    ebit_ttm_prev = ttm_prev_or_annual(ebit_q, ebit_a)
    roce_prev = (ebit_ttm_prev / ic_prev) if (ebit_ttm_prev is not None and ic_prev not in (None, 0)) else np.nan

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

    # ROCE inflection signals
    roce_delta_yoy = (roce - roce_prev) if (pd.notna(roce) and pd.notna(roce_prev)) else np.nan
    # YoY-improvement inflection: ROCE delta turns positive (improving)
    roce_inflection = int(pd.notna(roce_delta_yoy) and pd.notna(roce_prev) and roce_delta_yoy > 0 and roce_prev <= 0.0)
    # Level first-positive: ROCE itself crossed zero from below
    roce_first_positive = first_pos(roce, roce_prev) if (pd.notna(roce) and pd.notna(roce_prev)) else 0

    # Forward-projected break-even: linear extrapolation of the latest improvement
    # in FCF (and EBITDA, CFO). If current is negative and improving, periods-to-zero
    # = -current / period_delta. Period unit is whichever cadence was used to
    # compute the prior level (TTM-rolled-1y when annual fallback, else 1q-shift TTM).
    def periods_to_positive(curr, prev, prev_seq=None):
        # prev_seq is the most recent available "shorter horizon" prior for cadence:
        # if quarterly TTM-shifted-1q is available we use that for a 1-quarter-step
        # projection; otherwise fall back to annual step.
        if curr is None or pd.isna(curr):
            return np.nan, np.nan
        # Prefer the shorter cadence delta when available so the eta is in quarters
        ref_prev = prev_seq if (prev_seq is not None and pd.notna(prev_seq)) else prev
        if ref_prev is None or pd.isna(ref_prev):
            return np.nan, np.nan
        delta = curr - ref_prev
        if delta <= 0:
            return np.nan, np.nan  # not improving, no meaningful eta
        if curr >= 0:
            return 0.0, delta  # already positive
        eta = -curr / delta  # number of cadence-units to break-even
        return float(eta), float(delta)

    # FCF projection: prefer 1q-step (TTM rolled fwd 1q) if quarters dense, else 1y-step
    fcf_eta_quarters = np.nan
    fcf_eta_years = np.nan
    fcf_run_rate_delta = np.nan
    if pd.notna(fcf_ttm) and pd.notna(fcf_ttm_q1):
        eta_q, d_q = periods_to_positive(fcf_ttm, None, prev_seq=fcf_ttm_q1)
        fcf_eta_quarters = eta_q
        fcf_run_rate_delta = d_q
    if pd.notna(fcf_ttm) and pd.notna(fcf_ttm_prev):
        eta_y, d_y = periods_to_positive(fcf_ttm, None, prev_seq=fcf_ttm_prev)
        fcf_eta_years = eta_y
        if pd.isna(fcf_run_rate_delta):
            fcf_run_rate_delta = d_y

    # Same for EBITDA and CFO (lighter touch — reported in years only)
    def annual_eta(curr, prev):
        eta, _ = periods_to_positive(curr, None, prev_seq=prev)
        return eta

    ebitda_eta_years = annual_eta(ebitda_ttm, ebitda_ttm_prev) if pd.notna(ebitda_ttm) and pd.notna(ebitda_ttm_prev) else np.nan
    cfo_eta_years = annual_eta(cfo_ttm, cfo_ttm_prev) if pd.notna(cfo_ttm) and pd.notna(cfo_ttm_prev) else np.nan
    ni_eta_years = annual_eta(ni_ttm, ni_ttm_prev) if pd.notna(ni_ttm) and pd.notna(ni_ttm_prev) else np.nan

    # Binary projection flag: improving + still negative + reaches positive
    # within the user-defined horizon (set on the module via PROJECTION_N_PERIODS;
    # default 4 periods).
    n_periods = globals().get("PROJECTION_N_PERIODS", 4)
    if pd.notna(fcf_eta_quarters):
        fcf_projected_positive_in_n = int(0 < fcf_eta_quarters <= n_periods)
    elif pd.notna(fcf_eta_years):
        # n_periods interpreted in quarters when only annual cadence is available -> /4
        fcf_projected_positive_in_n = int(0 < fcf_eta_years <= max(1, n_periods / 4))
    else:
        fcf_projected_positive_in_n = 0

    # Valuation
    market_cap = info.get("marketCap")
    enterprise_value = info.get("enterpriseValue") or (
        (market_cap or 0) + (nd_v if pd.notna(nd_v) else 0)
    )
    price = info.get("currentPrice") or info.get("regularMarketPrice") or np.nan
    ev_sales = safe_div(enterprise_value, rev_ttm) if rev_ttm else np.nan
    ev_ebitda = safe_div(enterprise_value, ebitda_ttm) if ebitda_ttm else np.nan
    ev_ebit = safe_div(enterprise_value, ebit_ttm) if (ebit_ttm and ebit_ttm > 0) else np.nan
    pb = safe_div(market_cap, eq_v) if (market_cap and pd.notna(eq_v) and eq_v > 0) else np.nan
    fcf_yield = safe_div(fcf_ttm, market_cap) if market_cap else np.nan

    # NCAV (Graham): current assets - total liabilities. Use balance sheet rows
    # with annual fallback. NCAV % of market cap is a "cigar butt" cheapness gauge.
    cur_assets = first_row_with_fallback(qbs, abs_, ["Current Assets", "Total Current Assets"])
    total_liab = first_row_with_fallback(qbs, abs_, ["Total Liabilities Net Minority Interest",
                                                     "Total Liab", "Total Liabilities"])
    ca_v = q(cur_assets, 0) if cur_assets is not None else np.nan
    tl_v = q(total_liab, 0) if total_liab is not None else np.nan
    ncav = (ca_v - tl_v) if (pd.notna(ca_v) and pd.notna(tl_v)) else np.nan
    ncav_pct_mcap = safe_div(ncav, market_cap) if (pd.notna(ncav) and market_cap) else np.nan

    # ----- Cheapness composites (per user spec) -----
    # 1) EV/EBIT relative to a weighted growth+NCAV blend.
    #    blend = 1/3 sales_yoy + 1/3 ebitda_yoy + 1/6 fcf_yoy + 1/6 ncav_pct_mcap
    #    cheapness1 = ev_ebit / blend (lower = cheaper). Flag fires when
    #    EV/EBIT < 7x AND blend > 0 (growing cheap company).
    blend_components = []
    if pd.notna(rev_yoy):    blend_components.append((1/3, rev_yoy))
    if pd.notna(ebitda_yoy): blend_components.append((1/3, ebitda_yoy))
    if pd.notna(fcf_yoy):    blend_components.append((1/6, fcf_yoy))
    if pd.notna(ncav_pct_mcap): blend_components.append((1/6, ncav_pct_mcap))
    if blend_components:
        wsum = sum(w for w, _ in blend_components)
        cheapness_growth_blend = sum(w * v for w, v in blend_components) / wsum
    else:
        cheapness_growth_blend = np.nan

    if pd.notna(ev_ebit) and pd.notna(cheapness_growth_blend) and cheapness_growth_blend > 0:
        cheapness_ev_ebit_vs_growth = ev_ebit / cheapness_growth_blend
    else:
        cheapness_ev_ebit_vs_growth = np.nan

    cheapness_under_7x_flag = int(
        pd.notna(ev_ebit) and ev_ebit > 0 and ev_ebit < 7
        and pd.notna(cheapness_growth_blend) and cheapness_growth_blend > 0
    )

    # 2) Blended P/B + EV/EBIT vs blended growth: ((PB + EV/EBIT)/2) / ((sales+ebitda)/2)
    if pd.notna(pb) and pd.notna(ev_ebit):
        val_blend = (pb + ev_ebit) / 2.0
    else:
        val_blend = np.nan
    if pd.notna(rev_yoy) and pd.notna(ebitda_yoy):
        growth_blend2 = (rev_yoy + ebitda_yoy) / 2.0
    else:
        growth_blend2 = np.nan
    if pd.notna(val_blend) and pd.notna(growth_blend2) and growth_blend2 > 0:
        cheapness_blend_vs_growth = val_blend / growth_blend2
    else:
        cheapness_blend_vs_growth = np.nan

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

    # First-positive level crossings get a meaningful nudge in the composite:
    # FCF crossing zero from below is a textbook Yartseva entry signal.
    first_pos_score = 0.20 * (
        fcf_first_positive + ebitda_first_positive + cfo_first_positive
        + net_income_first_positive + roce_first_positive
    )
    # Forward-projected FCF break-even within the lookahead horizon.
    fwd_eta_score = 1.0 if fcf_projected_positive_in_n else 0.0
    # ROCE inflection bonus
    roce_inf_score = 1.0 if roce_inflection else 0.0

    weights = {
        "growth": 0.16,
        "accel": 0.12,
        "margin": 0.12,
        "cash_quality": 0.08,
        "roce": 0.12,
        "leverage": 0.04,
        "valuation": 0.08,
        "fcf_yield": 0.08,
        "first_positive": 0.10,
        "fwd_eta": 0.06,
        "roce_inflect": 0.04,
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
        "first_positive": first_pos_score,
        "fwd_eta": fwd_eta_score,
        "roce_inflect": roce_inf_score,
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
        notes_parts.append("growth-flip")
    fp_tags = []
    if fcf_first_positive: fp_tags.append("FCF")
    if ebitda_first_positive: fp_tags.append("EBITDA")
    if cfo_first_positive: fp_tags.append("CFO")
    if net_income_first_positive: fp_tags.append("NI")
    if roce_first_positive: fp_tags.append("ROCE")
    if fp_tags:
        notes_parts.append("first-positive: " + "/".join(fp_tags))
    if roce_inflection:
        notes_parts.append("ROCE improving from <=0")
    if fcf_projected_positive_in_n:
        eta_disp = (
            f"{fcf_eta_quarters:.1f}q" if pd.notna(fcf_eta_quarters)
            else f"{fcf_eta_years:.1f}y"
        )
        notes_parts.append(f"FCF break-even ETA {eta_disp}")
    if pd.notna(rev_accel) and rev_accel > 0.05:
        notes_parts.append("accelerating sales")
    if pd.notna(not_priced_in_score) and not_priced_in_score > 0.10:
        notes_parts.append("under-priced vs fundamentals")
    if cheapness_under_7x_flag:
        notes_parts.append(f"cheap+grow (EV/EBIT {ev_ebit:.1f}x)")
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
        ev_ebit=ev_ebit,
        pb=pb,
        fcf_yield=fcf_yield,
        ncav=ncav,
        ncav_pct_mcap=ncav_pct_mcap,
        cheapness_growth_blend=cheapness_growth_blend,
        cheapness_ev_ebit_vs_growth=cheapness_ev_ebit_vs_growth,
        cheapness_under_7x_flag=cheapness_under_7x_flag,
        cheapness_blend_vs_growth=cheapness_blend_vs_growth,
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
        ebitda_first_positive=ebitda_first_positive,
        cfo_first_positive=cfo_first_positive,
        fcf_first_positive=fcf_first_positive,
        net_income_first_positive=net_income_first_positive,
        roce_prev=roce_prev,
        roce_delta_yoy=roce_delta_yoy,
        roce_inflection=roce_inflection,
        roce_first_positive=roce_first_positive,
        fcf_run_rate_delta=fcf_run_rate_delta,
        fcf_eta_quarters=fcf_eta_quarters,
        fcf_eta_years=fcf_eta_years,
        ebitda_eta_years=ebitda_eta_years,
        cfo_eta_years=cfo_eta_years,
        ni_eta_years=ni_eta_years,
        fcf_projected_positive_in_n=fcf_projected_positive_in_n,
        price_yoy=price_yoy,
        price_minus_rev_yoy=price_minus_rev_yoy,
        price_minus_ebitda_yoy=price_minus_ebitda_yoy,
        price_minus_fcf_yoy=price_minus_fcf_yoy,
        ev_sales_change_yoy=ev_sales_change_yoy,
        not_priced_in_score=not_priced_in_score,
        yartseva_score=yartseva_score,
        notes=notes,
    )


def get_universe(
    country: str = "Italy",
    min_bucket: Optional[str] = None,
    max_bucket: Optional[str] = None,
) -> pd.DataFrame:
    import financedatabase as fd

    eq = fd.Equities()
    df = eq.select(country=country)
    if country == "Italy":
        # Restrict to .MI listing for Italian names where yfinance returns financials.
        df = df[df.index.str.endswith(".MI")]
    elif country == "United States":
        # Drop OTC / ADR-style suffixed tickers; keep plain NYSE/NASDAQ symbols
        # (no dot suffix) - yfinance supports those directly.
        df = df[~df.index.str.contains(r"\.", regex=True)]
        # Drop SPACs / warrants / rights / units which dominate the nano/micro tail
        # and have no real fundamentals to score.
        spac_terms = (
            "Acquisition", "Acquistion", "SPAC", "Blank Check",
            " Trust ", " Trust,", " Trust$",
            " Warrant", " Warrants", " Right ", " Rights",
            " Unit ", " Units",
        )
        name_pat = "|".join(t.replace(" ", r"\s") for t in spac_terms)
        df = df[~df["name"].astype(str).str.contains(name_pat, case=False, regex=True, na=False)]
        # Drop ticker suffixes typically used for warrants/units/rights/preferred
        # (e.g. ABCW, ABCU, ABCR, ABCP).
        df = df[~df.index.str.match(r".+[WURP]$")]
    order = ["Nano Cap", "Micro Cap", "Small Cap", "Mid Cap", "Large Cap", "Mega Cap"]
    if min_bucket and min_bucket in order:
        lo = order.index(min_bucket)
        allowed_min = set(order[lo:])
        df = df[df["market_cap"].isin(allowed_min)]
    if max_bucket and max_bucket in order:
        hi = order.index(max_bucket)
        allowed_max = set(order[: hi + 1])
        df = df[df["market_cap"].isin(allowed_max)]
    return df


# Backward-compatible alias used elsewhere
def get_italian_universe(min_bucket: Optional[str] = None) -> pd.DataFrame:
    return get_universe(country="Italy", min_bucket=min_bucket)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--country", default="Italy",
                        help='country (financedatabase: "Italy", "United States", ...)')
    parser.add_argument("--max", type=int, default=40, help="max tickers to fetch (0 = all)")
    parser.add_argument("--min-bucket", default="Small Cap",
                        help="minimum financedatabase market_cap bucket (Nano/Micro/Small/Mid/Large)")
    parser.add_argument("--max-bucket", default=None,
                        help="maximum financedatabase market_cap bucket (e.g. Small Cap to cap at smid)")
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--out", default="italian_yartseva.csv")
    parser.add_argument("--top", type=int, default=15, help="rows printed in console summary")
    parser.add_argument("--projection-n", type=int, default=4,
                        help="lookahead periods (quarters) for forward FCF break-even projection")
    args = parser.parse_args()

    # Set module-level so fetch_ticker can read it without threading state.
    globals()["PROJECTION_N_PERIODS"] = args.projection_n

    print(f"[1/3] Loading {args.country} universe (min bucket={args.min_bucket}, max bucket={args.max_bucket}) ...", file=sys.stderr)
    universe = get_universe(country=args.country, min_bucket=args.min_bucket, max_bucket=args.max_bucket)
    print(f"      universe size = {len(universe)}", file=sys.stderr)

    if args.max and args.max > 0:
        universe = universe.head(args.max)
    print(f"      scanning {len(universe)} tickers with {args.workers} workers", file=sys.stderr)

    rows: list[TickerRow] = []
    start = time.time()
    # Write incrementally so a mid-scan kill still leaves a usable CSV.
    partial_path = args.out + ".partial"
    csv_writer = None
    csv_file = None
    try:
        import csv as _csv
        csv_file = open(partial_path, "w", newline="")
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
                    d = asdict(row)
                    if csv_writer is None:
                        csv_writer = _csv.DictWriter(csv_file, fieldnames=list(d.keys()))
                        csv_writer.writeheader()
                    csv_writer.writerow(d)
                    csv_file.flush()
                    rows.append(row)
                if done % 25 == 0:
                    print(f"      {done}/{len(universe)} done ({len(rows)} kept) "
                          f"elapsed {time.time()-start:.0f}s", file=sys.stderr)
    finally:
        if csv_file is not None:
            csv_file.close()

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

    print("\n=== FIRST-POSITIVE LEVEL CROSSINGS (TTM/annual) ===")
    fp_mask = (
        (df["fcf_first_positive"] == 1)
        | (df["ebitda_first_positive"] == 1)
        | (df["cfo_first_positive"] == 1)
        | (df["net_income_first_positive"] == 1)
        | (df["roce_first_positive"] == 1)
    )
    fp = df[fp_mask]
    cols = ["symbol", "name", "fcf_first_positive", "ebitda_first_positive",
            "cfo_first_positive", "net_income_first_positive", "roce_first_positive",
            "fcf_ttm", "ebitda_ttm", "yartseva_score"]
    print(fp.head(args.top)[cols].to_string(index=False) if len(fp) else "  (none)")

    print("\n=== ROCE INFLECTIONS (level >0 first time, or improving from <=0) ===")
    rmask = (df["roce_inflection"] == 1) | (df["roce_first_positive"] == 1)
    rsub = df[rmask].sort_values("roce_delta_yoy", ascending=False)
    cols = ["symbol", "name", "roce", "roce_prev", "roce_delta_yoy",
            "roce_inflection", "roce_first_positive", "yartseva_score"]
    print(rsub.head(args.top)[cols].to_string(index=False) if len(rsub) else "  (none)")

    print(f"\n=== FORWARD FCF BREAK-EVEN PROJECTED <= {args.projection_n} QUARTERS ===")
    fwd = df[df["fcf_projected_positive_in_n"] == 1].sort_values("fcf_eta_quarters", na_position="last")
    cols = ["symbol", "name", "fcf_ttm", "fcf_run_rate_delta",
            "fcf_eta_quarters", "fcf_eta_years", "ebitda_eta_years",
            "yartseva_score", "notes"]
    print(fwd.head(args.top)[cols].to_string(index=False) if len(fwd) else "  (none)")

    print("\n=== CHEAP + GROWING (EV/EBIT < 7x AND blended growth+NCAV > 0) ===")
    cheap1 = df[df["cheapness_under_7x_flag"] == 1].sort_values("cheapness_ev_ebit_vs_growth")
    cols = ["symbol", "name", "ev_ebit", "rev_yoy", "ebitda_yoy", "fcf_yoy",
            "ncav_pct_mcap", "cheapness_growth_blend", "cheapness_ev_ebit_vs_growth",
            "yartseva_score"]
    print(cheap1.head(args.top)[cols].to_string(index=False) if len(cheap1) else "  (none)")

    print("\n=== CHEAPEST ON BLENDED P/B + EV/EBIT vs (sales+EBITDA) growth ===")
    cheap2 = df[(df["cheapness_blend_vs_growth"].notna()) & (df["cheapness_blend_vs_growth"] > 0)] \
        .sort_values("cheapness_blend_vs_growth")
    cols = ["symbol", "name", "pb", "ev_ebit", "rev_yoy", "ebitda_yoy",
            "cheapness_blend_vs_growth", "yartseva_score"]
    print(cheap2.head(args.top)[cols].to_string(index=False) if len(cheap2) else "  (none)")

    print(f"\n[3/3] done in {time.time()-start:.0f}s", file=sys.stderr)


if __name__ == "__main__":
    main()
